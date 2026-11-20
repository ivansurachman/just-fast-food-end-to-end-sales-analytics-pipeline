"""Ingest: one Parquet object per entity per day, from a local folder and from SeaweedFS."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from pipelines import ingest_bronze
from pipelines.manifest import read_manifest

DAY = "2026-10-05"
TEST_PREFIX = "_test"


def test_ingest_day_writes_one_parquet_per_entity(raw_root: Path, tmp_path: Path) -> None:
    lake = tmp_path / "jff-lake"

    counts = ingest_bronze.ingest_day(DAY, raw_root=raw_root.as_posix(), lake_root=lake.as_posix())

    assert counts == {"orders": 3, "order_items": 3, "order_changes": 1}
    target = lake / "bronze" / "orders" / f"source_file_date={DAY}" / "orders.parquet"
    assert target.is_file()

    columns = duckdb.sql(
        f"DESCRIBE SELECT * FROM read_parquet('{target.as_posix()}', hive_partitioning = false)"
    ).fetchall()
    assert [(name, type_) for name, type_, *_ in columns] == [
        ("order_id", "VARCHAR"),
        ("order_ts", "VARCHAR"),
        ("branch_id", "VARCHAR"),
        ("channel", "VARCHAR"),
        ("gross_amount", "VARCHAR"),
        ("source_file_date", "DATE"),
        ("_source_file", "VARCHAR"),
    ]
    first = duckdb.sql(
        f"SELECT source_file_date, _source_file FROM "
        f"read_parquet('{target.as_posix()}', hive_partitioning = false) LIMIT 1"
    ).fetchone()
    assert first == (date.fromisoformat(DAY), f"{raw_root.as_posix()}/orders/dt={DAY}/orders.csv")


def test_ingest_day_is_repeatable_byte_for_byte(raw_root: Path, tmp_path: Path) -> None:
    lake = tmp_path / "jff-lake"
    target = lake / "bronze" / "orders" / f"source_file_date={DAY}" / "orders.parquet"

    ingest_bronze.ingest_day(DAY, raw_root=raw_root.as_posix(), lake_root=lake.as_posix())
    first = target.read_bytes()
    ingest_bronze.ingest_day(DAY, raw_root=raw_root.as_posix(), lake_root=lake.as_posix())

    assert target.read_bytes() == first


def test_ingest_dimensions_has_no_source_file_date(raw_root: Path, tmp_path: Path) -> None:
    lake = tmp_path / "jff-lake"

    counts = ingest_bronze.ingest_dimensions(
        raw_root=raw_root.as_posix(), lake_root=lake.as_posix()
    )

    assert counts == {"branches": 2, "channels": 3, "menu_items": 2, "promos": 1}
    target = lake / "bronze" / "dimensions" / "branches.parquet"
    columns = duckdb.sql(f"DESCRIBE SELECT * FROM '{target.as_posix()}'").fetchall()
    assert [name for name, *_ in columns] == ["branch_id", "name", "open_date", "_source_file"]


def test_ingest_day_reports_the_missing_csv(raw_root: Path, tmp_path: Path) -> None:
    (raw_root / "orders" / f"dt={DAY}" / "orders.csv").unlink()

    with pytest.raises(ingest_bronze.IngestError, match="orders.csv"):
        ingest_bronze.ingest_day(
            DAY, raw_root=raw_root.as_posix(), lake_root=(tmp_path / "lake").as_posix()
        )


def test_seaweedfs_roundtrip(s3_endpoint: str, s3_client: Any) -> None:
    """Ingest the day T01 generated into a throwaway prefix, twice, and compare the object ETag."""
    lake_root = f"s3://jff-lake/{TEST_PREFIX}"
    expected = read_manifest(DAY, endpoint=s3_endpoint)["rows"]
    key = f"{TEST_PREFIX}/bronze/orders/source_file_date={DAY}/orders.parquet"
    try:
        counts = ingest_bronze.ingest_day(DAY, endpoint=s3_endpoint, lake_root=lake_root)
        assert counts == expected

        head = s3_client.head_object(Bucket="jff-lake", Key=key)
        ingest_bronze.ingest_day(DAY, endpoint=s3_endpoint, lake_root=lake_root)
        assert s3_client.head_object(Bucket="jff-lake", Key=key)["ETag"] == head["ETag"]
    finally:
        _delete_prefix(s3_client, bucket="jff-lake", prefix=f"{TEST_PREFIX}/")


def _delete_prefix(client: Any, *, bucket: str, prefix: str) -> None:
    listing = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = [{"Key": item["Key"]} for item in listing.get("Contents", [])]
    if keys:
        client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
