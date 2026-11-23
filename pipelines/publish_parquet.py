"""Publish silver and gold tables to the lake as partitioned Parquet.

Decision D1 keeps DuckDB as the compute store; the lake is a **derived** copy. For every order date
in the window and for each table below, one object is written:

    s3://jff-lake/<layer>/<table>/order_date=<date>/part.parquet
    (FORMAT PARQUET, COMPRESSION zstd)

The name is fixed, so re-publishing a date overwrites the same object and the same command produces
the same objects. A partition with no rows deletes its object first, so a partition that disappears
from DuckDB cannot survive in the lake.

Runs with the Airflow interpreter (duckdb + boto3) and opens the dbt database read-only: DuckDB
allows one writer and this module never writes to it.
"""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Final

import duckdb
from botocore.exceptions import ClientError

from pipelines.ingest_bronze import MEMORY_LIMIT, THREADS, configure_s3
from pipelines.manifest import MISSING_CODES, s3_client

LOG = logging.getLogger(__name__)

DEFAULT_DUCKDB_PATH: Final = "/opt/airflow/duckdb/jff.duckdb"
DEFAULT_LAKE_ROOT: Final = "s3://jff-lake"
DEFAULT_LOOKBACK_DAYS: Final = 10
OBJECT_NAME: Final = "part.parquet"


@dataclass(frozen=True)
class Target:
    """One table published to the lake, with the column that carries its order date."""

    table: str
    layer: str
    column: str
    is_date_key: bool = False


TARGETS: Final = (
    Target(table="silver_orders", layer="silver", column="order_date"),
    Target(table="silver_order_items", layer="silver", column="order_date"),
    Target(table="fact_order", layer="gold", column="date_key", is_date_key=True),
    Target(table="fact_order_item", layer="gold", column="date_key", is_date_key=True),
)

# A fixed row order keeps a rewritten partition as close to byte-identical as the writer allows; it
# is not a guarantee of identical bytes, only the removal of one source of variation.
ORDER_BY: Final = {
    "silver_orders": "order_id",
    "silver_order_items": "order_id, line_no",
    "fact_order": "order_id",
    "fact_order_item": "order_id, line_no",
}


def window(ds: str, lookback_days: int) -> list[date]:
    """Every order date a run for file date `ds` republishes, oldest first."""
    end = date.fromisoformat(ds)
    return [end - timedelta(days=offset) for offset in range(lookback_days, -1, -1)]


def partition_path(lake_root: str, target: Target, day: date) -> str:
    """Object path of one partition; the name is fixed so a rewrite overwrites it."""
    return f"{lake_root}/{target.layer}/{target.table}/order_date={day.isoformat()}/{OBJECT_NAME}"


def date_filter(target: Target, day: date) -> str:
    """SQL predicate for one order date, using the column the table actually has."""
    if target.is_date_key:
        return f"{target.column} = {day.strftime('%Y%m%d')}"
    return f"{target.column} = date '{day.isoformat()}'"


def connect(duckdb_path: str, endpoint: str | None) -> duckdb.DuckDBPyConnection:
    """Read-only connection to the dbt database, with the memory limits and the S3 settings."""
    con = duckdb.connect(duckdb_path, read_only=True)
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET threads = {THREADS}")
    temp_dir = Path(tempfile.gettempdir()) / "jff-duckdb"
    temp_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{temp_dir.as_posix()}'")
    if endpoint:
        configure_s3(con, endpoint)
    return con


def delete_object(path: str, endpoint: str | None) -> bool:
    """Remove one object or local file; True when something was there."""
    if path.startswith("s3://"):
        bucket, _, key = path[len("s3://") :].partition("/")
        client = s3_client(endpoint)
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in MISSING_CODES:
                return False
            raise
        client.delete_object(Bucket=bucket, Key=key)
        return True
    local = Path(path.removeprefix("file://"))
    if local.is_file():
        local.unlink()
        return True
    return False


def publish_partition(
    con: duckdb.DuckDBPyConnection,
    target: Target,
    day: date,
    lake_root: str,
    endpoint: str | None,
) -> int:
    """Publish one table partition; returns the rows written (0 when the object was deleted)."""
    path = partition_path(lake_root, target, day)
    predicate = date_filter(target, day)
    row = con.execute(f"SELECT count(*) FROM {target.table} WHERE {predicate}").fetchone()
    rows = int(row[0]) if row else 0
    if rows == 0:
        if delete_object(path, endpoint):
            LOG.info("%s %s: no rows, deleted the stale object", target.table, day)
        return 0
    if "://" not in path:
        # DuckDB writes objects itself; for a local path it will not create the directory.
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT * FROM {target.table} WHERE {predicate} ORDER BY {ORDER_BY[target.table]}) "
        f"TO '{path}' (FORMAT PARQUET, COMPRESSION zstd)"
    )
    LOG.info("%s %s: %d rows -> %s", target.table, day, rows, path)
    return rows


def publish_window(
    ds: str,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    duckdb_path: str = DEFAULT_DUCKDB_PATH,
    lake_root: str = DEFAULT_LAKE_ROOT,
    endpoint: str | None = None,
) -> dict[str, int]:
    """Publish every table for every order date in the window; returns rows per table."""
    days = window(ds, lookback_days)
    con = connect(duckdb_path, endpoint)
    try:
        written: dict[str, int] = {}
        for target in TARGETS:
            written[target.table] = sum(
                publish_partition(con, target, day, lake_root, endpoint) for day in days
            )
            LOG.info("%s: %d rows over %d dates", target.table, written[target.table], len(days))
        return written
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    """CLI for the Airflow task and for a manual republish."""
    parser = argparse.ArgumentParser(description="Publish the silver and gold window as Parquet.")
    parser.add_argument("--ds", required=True, help="run date, YYYY-MM-DD")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"window size in days (default {DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--duckdb-path",
        default=os.environ.get("DBT_DUCKDB_PATH", DEFAULT_DUCKDB_PATH),
        help="DuckDB file written by dbt",
    )
    parser.add_argument(
        "--lake-root",
        default=os.environ.get("JFF_LAKE_ROOT", DEFAULT_LAKE_ROOT),
        help="root the partitions are written under",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("JFF_S3_ENDPOINT"),
        help="S3 endpoint, e.g. http://seaweedfs:8333",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    written = publish_window(
        args.ds,
        lookback_days=args.lookback_days,
        duckdb_path=args.duckdb_path,
        lake_root=args.lake_root,
        endpoint=args.endpoint,
    )
    LOG.info("published %s", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
