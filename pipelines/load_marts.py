"""Copy one window of the sales mart from DuckDB into PostgreSQL.

Runs as a plain module (no Airflow imports) with the dbt virtualenv, which has both `duckdb` and
`psycopg`:

    /opt/venvs/dbt/bin/python -m pipelines.load_marts --ds 2026-10-09 --lookback-days 10

For the window [ds - lookback_days, ds] the target table is emptied and refilled inside one
transaction, so re-running a date cannot change the mart (docs/pipeline-design.md section 5).
The connection comes from the standard PG* variables, which compose fills from .env; no credential
is written in the code.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Final

import duckdb
import psycopg

LOG = logging.getLogger(__name__)

MART: Final = "mart_sales_day_branch_channel"
DEFAULT_DUCKDB_PATH: Final = "/opt/airflow/duckdb/jff.duckdb"
DEFAULT_LOOKBACK_DAYS: Final = 10
COLUMNS: Final = (
    "order_date",
    "branch_key",
    "channel_key",
    "total_orders",
    "completed_orders",
    "cancelled_orders",
    "refunded_orders",
    "gross_amount",
    "discount_amount",
    "net_amount",
    "cogs_amount",
    "commission_amount",
)
SQL_FILE: Final = Path(__file__).parent / "sql" / "marts.sql"
COPY_SQL: Final = f"copy {MART} ({', '.join(COLUMNS)}) from stdin"


def window(ds: str, lookback_days: int) -> tuple[date, date]:
    """The closed window a run for file date `ds` rewrites."""
    run_date = date.fromisoformat(ds)
    return run_date - timedelta(days=lookback_days), run_date


def read_mart(duckdb_path: str, start: date, end: date) -> list[tuple[object, ...]]:
    """Mart rows for the window, straight out of the dbt database (opened read-only)."""
    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        rows = con.execute(
            f"select {', '.join(COLUMNS)} from {MART} "
            "where order_date between ? and ? "
            "order by order_date, branch_key, channel_key",
            [start, end],
        ).fetchall()
    finally:
        con.close()
    return rows


def replace_window(rows: list[tuple[object, ...]], start: date, end: date) -> int:
    """Delete the window and copy the rows in, in one transaction. Returns the rows written."""
    with psycopg.connect("") as connection, connection.cursor() as cursor:
        cursor.execute(SQL_FILE.read_text(encoding="utf-8"))
        cursor.execute(f"delete from {MART} where order_date between %s and %s", (start, end))
        with cursor.copy(COPY_SQL) as copy:
            for row in rows:
                copy.write_row(row)
    return len(rows)


def load_marts(
    ds: str,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    duckdb_path: str = DEFAULT_DUCKDB_PATH,
) -> int:
    """Load the mart window for `ds` into PostgreSQL; returns the rows written."""
    start, end = window(ds, lookback_days)
    rows = read_mart(duckdb_path, start, end)
    # An empty window still needs the DELETE (and the DDL), otherwise rows from an earlier run
    # linger in PostgreSQL. Never return early just because there is nothing new to load.
    if not rows:
        LOG.info("mart %s has no rows for %s .. %s, only the window is replaced", MART, start, end)
    written = replace_window(rows, start, end)
    LOG.info("loaded %s rows for %s .. %s into %s", written, start, end, MART)
    return written


def main(argv: list[str] | None = None) -> int:
    """CLI for the Airflow task and for a manual re-load."""
    parser = argparse.ArgumentParser(description="Load the sales mart window into PostgreSQL.")
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
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    written = load_marts(args.ds, lookback_days=args.lookback_days, duckdb_path=args.duckdb_path)
    LOG.info("done, %s rows", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
