"""Bronze ingest: the generator's CSV on S3 to one Parquet object per entity per day.

Plain Python, no Airflow imports: `dags/jff_daily.py` imports this module and the same functions run
from the command line, so ingest can be tested and re-run without Airflow.

What it writes (docs/pipeline-design.md section 3):

    <lake>/bronze/<entity>/source_file_date=<ds>/<entity>.parquet   facts, one object per day
    <lake>/bronze/dimensions/<entity>.parquet                       dimensions, written once

Every column is read as text (`all_varchar`), so a dirty value can never fail ingest; casting is
silver's job. Each row keeps `_source_file` (the CSV object it came from) and, for facts,
`source_file_date` (the day that file describes). No timestamp is added, so re-ingesting a day
produces the same bytes.
"""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
from pathlib import Path
from typing import Final

import duckdb

LOG = logging.getLogger(__name__)

FACT_ENTITIES: Final = ("orders", "order_items", "order_changes")
DIMENSION_ENTITIES: Final = ("branches", "channels", "menu_items", "promos")

DEFAULT_RAW_ROOT: Final = "s3://jff-raw"
DEFAULT_LAKE_ROOT: Final = "s3://jff-lake"
MEMORY_LIMIT: Final = "1GB"
THREADS: Final = 2


class IngestError(RuntimeError):
    """Raised when bronze cannot be written, with the reason in the message."""


def connect(endpoint: str | None) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with the memory, thread and temp limits from the design.

    `endpoint` is the S3 endpoint (`http://host:port`); without one, only local paths work.
    """
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET threads = {THREADS}")
    temp_dir = Path(tempfile.gettempdir()) / "jff-duckdb"
    temp_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{temp_dir.as_posix()}'")
    if endpoint:
        configure_s3(con, endpoint)
    return con


def configure_s3(con: duckdb.DuckDBPyConnection, endpoint: str) -> None:
    """Point httpfs at a path-style S3 endpoint, using the credentials compose exports."""
    access_key = os.environ.get("S3_ACCESS_KEY") or os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("S3_SECRET_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        raise IngestError(
            "set S3_ACCESS_KEY/S3_SECRET_KEY or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY"
        )

    use_ssl = endpoint.startswith("https://")
    host = endpoint.split("://", 1)[1].rstrip("/") if "://" in endpoint else endpoint.rstrip("/")
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"SET s3_endpoint = '{host}'")
    con.execute(f"SET s3_use_ssl = {'true' if use_ssl else 'false'}")
    con.execute("SET s3_url_style = 'path'")
    con.execute(f"SET s3_region = '{os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')}'")
    con.execute(f"SET s3_access_key_id = '{access_key}'")
    con.execute(f"SET s3_secret_access_key = '{secret_key}'")


def raw_day_path(raw_root: str, entity: str, ds: str) -> str:
    """CSV object the generator wrote for one entity and day."""
    return f"{raw_root}/{entity}/dt={ds}/{entity}.csv"


def raw_dimension_path(raw_root: str, entity: str) -> str:
    """CSV object the generator wrote for one dimension."""
    return f"{raw_root}/dimensions/{entity}.csv"


def bronze_day_path(lake_root: str, entity: str, ds: str) -> str:
    """Parquet object bronze owns for one entity and day."""
    return f"{lake_root}/bronze/{entity}/source_file_date={ds}/{entity}.parquet"


def bronze_dimension_path(lake_root: str, entity: str) -> str:
    """Parquet object bronze owns for one dimension."""
    return f"{lake_root}/bronze/dimensions/{entity}.parquet"


def count_rows(con: duckdb.DuckDBPyConnection, parquet_path: str) -> int:
    """Rows in a Parquet object, so a missing object fails with the path in the message."""
    try:
        row = con.execute(
            f"SELECT count(*) FROM read_parquet('{_literal(parquet_path)}')"
        ).fetchone()
    except duckdb.Error as exc:
        raise IngestError(f"cannot read {parquet_path}: {exc}") from exc
    if row is None:
        raise IngestError(f"no row count for {parquet_path}")
    return int(row[0])


def count_csv_rows(con: duckdb.DuckDBPyConnection, csv_path: str) -> int:
    """Rows in a CSV object, read exactly as ingest reads it."""
    try:
        row = con.execute(f"SELECT count(*) FROM {_read_csv(csv_path)}").fetchone()
    except duckdb.Error as exc:
        raise IngestError(f"cannot read {csv_path}: {exc}") from exc
    if row is None:
        raise IngestError(f"no row count for {csv_path}")
    return int(row[0])


def _read_csv(path: str) -> str:
    """`read_csv` call used for every CSV, so ingest and the checks read files the same way.

    `all_varchar` because bronze never casts; `hive_partitioning` off so a `dt=` segment in the
    path does not appear as an extra column.
    """
    return (
        f"read_csv('{_literal(path)}', all_varchar = true, header = true, "
        "hive_partitioning = false)"
    )


def ingest_day(
    ds: str,
    *,
    raw_root: str = DEFAULT_RAW_ROOT,
    lake_root: str = DEFAULT_LAKE_ROOT,
    endpoint: str | None = None,
) -> dict[str, int]:
    """Write every fact entity of day `ds`; return the rows written per entity."""
    con = connect(endpoint)
    try:
        counts = {}
        for entity in FACT_ENTITIES:
            source = raw_day_path(raw_root, entity, ds)
            target = bronze_day_path(lake_root, entity, ds)
            _write_parquet(con, source, target, source_file_date=ds)
            counts[entity] = count_rows(con, target)
            LOG.info("bronze %s %s: %d rows", entity, ds, counts[entity])
        return counts
    finally:
        con.close()


def ingest_dimensions(
    *,
    raw_root: str = DEFAULT_RAW_ROOT,
    lake_root: str = DEFAULT_LAKE_ROOT,
    endpoint: str | None = None,
) -> dict[str, int]:
    """Write every dimension to `bronze/dimensions/`; small tables, rewritten every run."""
    con = connect(endpoint)
    try:
        counts = {}
        for entity in DIMENSION_ENTITIES:
            source = raw_dimension_path(raw_root, entity)
            target = bronze_dimension_path(lake_root, entity)
            _write_parquet(con, source, target, source_file_date=None)
            counts[entity] = count_rows(con, target)
            LOG.info("bronze dimension %s: %d rows", entity, counts[entity])
        return counts
    finally:
        con.close()


def _write_parquet(
    con: duckdb.DuckDBPyConnection,
    source: str,
    target: str,
    *,
    source_file_date: str | None,
) -> None:
    """Copy one CSV object to one Parquet object, overwriting it (same input, same bytes)."""
    if "://" not in target:
        # DuckDB writes objects itself; for a local path it will not create the directory.
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    extra_columns = (
        # DATE, because DuckDB derives the same column from the `source_file_date=` directory when
        # a read enables hive partitioning; storing a date keeps both readings identical.
        f", CAST('{source_file_date}' AS DATE) AS source_file_date" if source_file_date else ""
    )
    try:
        con.execute(
            f"COPY (SELECT *{extra_columns}, '{_literal(source)}' AS _source_file "
            f"FROM {_read_csv(source)}) TO '{_literal(target)}' (FORMAT parquet)"
        )
    except duckdb.Error as exc:
        raise IngestError(f"cannot copy {source} to {target}: {exc}") from exc


def _literal(value: str) -> str:
    """Guard a path for a SQL string literal; these are our own paths, so quotes are a bug."""
    if "'" in value:
        raise IngestError(f"unsupported quote in path: {value}")
    return value


def _env_roots() -> tuple[str, str]:
    return (
        os.environ.get("JFF_RAW_ROOT", DEFAULT_RAW_ROOT),
        os.environ.get("JFF_LAKE_ROOT", DEFAULT_LAKE_ROOT),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: `python -m pipelines.ingest_bronze --ds YYYY-MM-DD` and/or `--dimensions`."""
    parser = argparse.ArgumentParser(description="Ingest generator CSV into Parquet bronze.")
    parser.add_argument("--ds", help="generator file date, YYYY-MM-DD")
    parser.add_argument("--dimensions", action="store_true", help="(re)write the dimension objects")
    parser.add_argument("--endpoint", help="S3 endpoint, e.g. http://localhost:8333")
    parser.add_argument("--raw-root", help=f"CSV root (default {DEFAULT_RAW_ROOT})")
    parser.add_argument("--lake-root", help=f"Parquet root (default {DEFAULT_LAKE_ROOT})")
    args = parser.parse_args(argv)

    if not args.ds and not args.dimensions:
        parser.error("pass --ds, --dimensions or both")

    default_raw, default_lake = _env_roots()
    raw_root = args.raw_root or default_raw
    lake_root = args.lake_root or default_lake
    endpoint = args.endpoint or os.environ.get("JFF_S3_ENDPOINT")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.dimensions:
        LOG.info(
            "dimensions: %s",
            ingest_dimensions(raw_root=raw_root, lake_root=lake_root, endpoint=endpoint),
        )
    if args.ds:
        LOG.info(
            "day %s: %s",
            args.ds,
            ingest_day(args.ds, raw_root=raw_root, lake_root=lake_root, endpoint=endpoint),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
