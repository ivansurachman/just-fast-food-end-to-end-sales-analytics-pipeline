"""Run read-only SQL against the project DuckDB file and print the result.

Examples (inside the scheduler container, dbt virtualenv):
    python duckdb_query.py --tables
    python duckdb_query.py "select status_final, count(*) from fact_order group by 1"

DuckDB allows one writer. While a dbt run is active the file is locked and this
tool reports that instead of failing with a stack trace.
"""

import argparse
import os
import sys

import duckdb

DEFAULT_DB = os.environ.get("DBT_DUCKDB_PATH", "/opt/airflow/duckdb/jff.duckdb")
MAX_ROWS = 50
MAX_WIDTH = 200


def list_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Print every table and view with its row count."""
    objects = con.execute(
        "select table_name from information_schema.tables "
        "where table_schema = 'main' order by table_name"
    ).fetchall()
    for (name,) in objects:
        (count,) = con.execute(f'select count(*) from "{name}"').fetchall()[0]
        print(f"{name:<28}{count:>12,}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql", nargs="?", help="SQL to run")
    parser.add_argument("--tables", action="store_true", help="list tables with row counts")
    parser.add_argument("--db", default=DEFAULT_DB, help="path of the DuckDB file")
    args = parser.parse_args(argv)
    if not args.sql and not args.tables:
        parser.error("give a SQL statement or --tables")
    try:
        con = duckdb.connect(args.db, read_only=True)
    except duckdb.IOException as error:
        print(f"Cannot open {args.db}: {error}\nIf a dbt run is active, wait and retry.")
        return 1
    if args.tables:
        list_tables(con)
    if args.sql:
        con.sql(args.sql).show(max_rows=MAX_ROWS, max_width=MAX_WIDTH)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
