"""Checks: bronze must agree with the CSV and with the manifest, and say why when it does not."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines import check_bronze, ingest_bronze

DAY = "2026-10-05"
EXPECTED = {"orders": 3, "order_items": 3, "order_changes": 1}


@pytest.fixture
def lake(raw_root: Path, tmp_path: Path) -> Path:
    """A lake with the day and the dimensions already ingested."""
    lake_root = tmp_path / "jff-lake"
    ingest_bronze.ingest_day(DAY, raw_root=raw_root.as_posix(), lake_root=lake_root.as_posix())
    ingest_bronze.ingest_dimensions(raw_root=raw_root.as_posix(), lake_root=lake_root.as_posix())
    return lake_root


def test_check_day_passes(raw_root: Path, lake: Path) -> None:
    report = check_bronze.check_day(
        DAY,
        raw_root=raw_root.as_posix(),
        lake_root=lake.as_posix(),
        expected_rows=EXPECTED,
    )

    assert report["orders"] == {"csv": 3, "parquet": 3, "manifest": 3}
    assert report["branches"] == {"csv": 2, "parquet": 2}


def test_check_day_fails_when_a_bronze_object_is_missing(raw_root: Path, lake: Path) -> None:
    (lake / "bronze" / "order_items" / f"source_file_date={DAY}" / "order_items.parquet").unlink()

    with pytest.raises(check_bronze.CheckFailed, match="order_items.parquet"):
        check_bronze.check_day(
            DAY,
            raw_root=raw_root.as_posix(),
            lake_root=lake.as_posix(),
            expected_rows=EXPECTED,
        )


def test_check_day_fails_when_the_manifest_disagrees(raw_root: Path, lake: Path) -> None:
    with pytest.raises(check_bronze.CheckFailed, match="orders 2026-10-05: csv=3, parquet=3"):
        check_bronze.check_day(
            DAY,
            raw_root=raw_root.as_posix(),
            lake_root=lake.as_posix(),
            expected_rows={"orders": 4, "order_items": 3, "order_changes": 1},
        )


def test_check_day_fails_when_a_dimension_is_stale(raw_root: Path, lake: Path) -> None:
    branches = raw_root / "dimensions" / "branches.csv"
    branches.write_text(
        branches.read_text(encoding="utf-8") + "103,Gamma,2026-02-01\n", encoding="utf-8"
    )

    with pytest.raises(check_bronze.CheckFailed, match="branches dimensions"):
        check_bronze.check_day(
            DAY,
            raw_root=raw_root.as_posix(),
            lake_root=lake.as_posix(),
            expected_rows=EXPECTED,
        )


def test_check_day_needs_a_manifest_for_an_s3_root(raw_root: Path, lake: Path) -> None:
    with pytest.raises(check_bronze.CheckFailed, match="no manifest for a local raw root"):
        check_bronze.check_day(
            DAY,
            raw_root=raw_root.as_posix(),
            lake_root=lake.as_posix(),
            expected_rows=None,
        )
