"""Bronze checks for one day: CSV rows, Parquet rows and the manifest must agree.

`check_bronze` in `jff_daily` runs this between ingest and the dbt step, so a short or missing
bronze object stops the run instead of reaching silver. Plain Python, no Airflow imports.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Mapping
from typing import Any

from pipelines.ingest_bronze import (
    DEFAULT_LAKE_ROOT,
    DEFAULT_RAW_ROOT,
    DIMENSION_ENTITIES,
    FACT_ENTITIES,
    IngestError,
    bronze_day_path,
    bronze_dimension_path,
    connect,
    count_csv_rows,
    count_rows,
    raw_day_path,
    raw_dimension_path,
)
from pipelines.manifest import read_manifest

LOG = logging.getLogger(__name__)


class CheckFailed(RuntimeError):
    """Raised when bronze does not match its source or the manifest, with every problem listed."""


def check_day(
    ds: str,
    *,
    raw_root: str = DEFAULT_RAW_ROOT,
    lake_root: str = DEFAULT_LAKE_ROOT,
    endpoint: str | None = None,
    expected_rows: Mapping[str, int] | None = None,
) -> dict[str, dict[str, int]]:
    """Compare CSV, Parquet and manifest row counts for day `ds`.

    `expected_rows` overrides the manifest (the test path); by default the manifest is read from
    the raw bucket. Returns `{entity: {"csv": n, "parquet": n, "manifest": n or -1}}`.
    """
    expected = (
        expected_rows if expected_rows is not None else _manifest_rows(ds, raw_root, endpoint)
    )
    con = connect(endpoint)
    try:
        report: dict[str, dict[str, int]] = {}
        problems: list[str] = []
        for entity in FACT_ENTITIES:
            try:
                counts = {
                    "csv": count_csv_rows(con, raw_day_path(raw_root, entity, ds)),
                    "parquet": count_rows(con, bronze_day_path(lake_root, entity, ds)),
                    "manifest": int(expected.get(entity, -1)),
                }
            except IngestError as exc:
                problems.append(str(exc))
                continue
            report[entity] = counts
            if not counts["csv"] == counts["parquet"] == counts["manifest"]:
                problems.append(_describe(entity, ds, counts))
        for entity in DIMENSION_ENTITIES:
            try:
                counts = {
                    "csv": count_csv_rows(con, raw_dimension_path(raw_root, entity)),
                    "parquet": count_rows(con, bronze_dimension_path(lake_root, entity)),
                }
            except IngestError as exc:
                problems.append(str(exc))
                continue
            report[entity] = counts
            if counts["csv"] != counts["parquet"]:
                problems.append(_describe(entity, "dimensions", counts))
        if problems:
            raise CheckFailed("; ".join(problems))
        return report
    finally:
        con.close()


def _manifest_rows(ds: str, raw_root: str, endpoint: str | None) -> Mapping[str, int]:
    """Row counts recorded by the generator for the fact entities."""
    if not raw_root.startswith("s3://"):
        raise CheckFailed(f"no manifest for a local raw root: {raw_root}")
    bucket = raw_root[len("s3://") :].split("/", 1)[0]
    manifest: dict[str, Any] = read_manifest(ds, bucket=bucket, endpoint=endpoint)
    rows: dict[str, int] = manifest.get("rows", {})
    missing = [entity for entity in FACT_ENTITIES if entity not in rows]
    if missing:
        raise CheckFailed(f"manifest for {ds} has no row count for {missing}")
    return rows


def _describe(entity: str, scope: str, counts: Mapping[str, int]) -> str:
    """One readable line per mismatch, so the log names the entity and both sides."""
    return f"{entity} {scope}: " + ", ".join(f"{name}={count}" for name, count in counts.items())


def main(argv: list[str] | None = None) -> int:
    """CLI: `python -m pipelines.check_bronze --ds YYYY-MM-DD`."""
    parser = argparse.ArgumentParser(
        description="Check bronze against CSV and manifest row counts."
    )
    parser.add_argument("--ds", required=True, help="generator file date, YYYY-MM-DD")
    parser.add_argument("--endpoint", help="S3 endpoint, e.g. http://localhost:8333")
    parser.add_argument("--raw-root", help=f"CSV root (default {DEFAULT_RAW_ROOT})")
    parser.add_argument("--lake-root", help=f"Parquet root (default {DEFAULT_LAKE_ROOT})")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = check_day(
        args.ds,
        raw_root=args.raw_root or os.environ.get("JFF_RAW_ROOT", DEFAULT_RAW_ROOT),
        lake_root=args.lake_root or os.environ.get("JFF_LAKE_ROOT", DEFAULT_LAKE_ROOT),
        endpoint=args.endpoint or os.environ.get("JFF_S3_ENDPOINT"),
    )
    for entity, counts in report.items():
        LOG.info("%s: %s", entity, counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
