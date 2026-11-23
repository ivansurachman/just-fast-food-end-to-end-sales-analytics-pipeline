"""Publish: partition paths, the date filter, and the empty-partition delete."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from pipelines import publish_parquet

DAY = date(2026, 10, 9)
SILVER = publish_parquet.TARGETS[0]
GOLD = publish_parquet.TARGETS[2]


@pytest.fixture
def duckdb_file(tmp_path: Path) -> str:
    """A DuckDB file with the two published tables and a few order dates."""
    path = tmp_path / "jff.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create table silver_orders (order_id varchar, order_date date, net_amount bigint)")
    con.executemany(
        "insert into silver_orders values (?, ?, ?)",
        [("o1", DAY, 100), ("o2", DAY, 200), ("o3", date(2026, 10, 8), 50)],
    )
    con.execute("create table fact_order (order_id varchar, date_key integer)")
    con.executemany(
        "insert into fact_order values (?, ?)",
        [("o1", 20261009), ("o2", 20261009), ("o3", 20261008)],
    )
    # The other two targets exist so a full publish works, with no rows at all.
    con.execute("create table silver_order_items (order_id varchar, order_date date)")
    con.execute("create table fact_order_item (order_id varchar, date_key integer)")
    con.close()
    return str(path)


def test_window_is_oldest_first_and_includes_the_run_date() -> None:
    assert publish_parquet.window("2026-10-09", 3) == [
        date(2026, 10, 6),
        date(2026, 10, 7),
        date(2026, 10, 8),
        date(2026, 10, 9),
    ]


def test_partition_path_carries_the_layer_the_table_and_the_date() -> None:
    assert (
        publish_parquet.partition_path("s3://jff-lake", SILVER, DAY)
        == "s3://jff-lake/silver/silver_orders/order_date=2026-10-09/part.parquet"
    )
    assert (
        publish_parquet.partition_path("s3://jff-lake", GOLD, DAY)
        == "s3://jff-lake/gold/fact_order/order_date=2026-10-09/part.parquet"
    )


def test_date_filter_uses_the_column_each_table_has() -> None:
    assert publish_parquet.date_filter(SILVER, DAY) == "order_date = date '2026-10-09'"
    assert publish_parquet.date_filter(GOLD, DAY) == "date_key = 20261009"


def test_publish_writes_the_window_only(duckdb_file: str, tmp_path: Path) -> None:
    lake = tmp_path / "lake"

    written = publish_parquet.publish_window(
        "2026-10-09", lookback_days=0, duckdb_path=duckdb_file, lake_root=lake.as_posix()
    )

    assert written == {
        "silver_orders": 2,
        "silver_order_items": 0,
        "fact_order": 2,
        "fact_order_item": 0,
    }
    silver = lake / "silver" / "silver_orders" / "order_date=2026-10-09" / "part.parquet"
    assert silver.is_file()
    rows = duckdb.sql(f"select count(*) from read_parquet('{silver.as_posix()}')").fetchone()
    assert rows is not None and rows[0] == 2
    # 2026-10-08 is outside the window, and the empty tables wrote nothing.
    assert not (lake / "silver" / "silver_orders" / "order_date=2026-10-08").exists()
    assert not (lake / "silver" / "silver_order_items").exists()


def test_empty_partition_deletes_the_stale_object(duckdb_file: str, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    stale = lake / "silver" / "silver_orders" / "order_date=2026-10-07" / "part.parquet"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"stale")

    publish_parquet.publish_window(
        "2026-10-09", lookback_days=2, duckdb_path=duckdb_file, lake_root=lake.as_posix()
    )

    assert not stale.exists(), "a partition with no rows must not keep its old object"


def test_delete_object_reports_whether_something_was_there(tmp_path: Path) -> None:
    present = tmp_path / "present.parquet"
    present.write_bytes(b"x")
    assert publish_parquet.delete_object(present.as_posix(), None) is True
    assert not present.exists()
    assert publish_parquet.delete_object(present.as_posix(), None) is False


def test_seaweedfs_roundtrip(s3_endpoint: str, s3_client: Any, duckdb_file: str) -> None:
    """Publish one day to the lake, read it back, and check the object is stable on a republish."""
    lake_root = "s3://jff-lake/_test"
    key = "silver/silver_orders/order_date=2026-10-09/part.parquet"
    try:
        written = publish_parquet.publish_window(
            "2026-10-09",
            lookback_days=0,
            duckdb_path=duckdb_file,
            lake_root=lake_root,
            endpoint=s3_endpoint,
        )
        assert written["silver_orders"] == 2
        head = s3_client.head_object(Bucket="jff-lake", Key=f"_test/{key}")
        reader = publish_parquet.connect(duckdb_file, s3_endpoint)
        try:
            counted = reader.execute(
                "select count(*) from read_parquet('s3://jff-lake/_test/silver/silver_orders/"
                "order_date=2026-10-09/part.parquet')"
            ).fetchone()
        finally:
            reader.close()
        assert counted is not None and counted[0] == 2

        publish_parquet.publish_window(
            "2026-10-09",
            lookback_days=0,
            duckdb_path=duckdb_file,
            lake_root=lake_root,
            endpoint=s3_endpoint,
        )
        assert (
            s3_client.head_object(Bucket="jff-lake", Key=f"_test/{key}")["ETag"] == head["ETag"]
        ), "republishing the same day must not change the object"
    finally:
        listing = s3_client.list_objects_v2(Bucket="jff-lake", Prefix="_test/")
        keys = [{"Key": item["Key"]} for item in listing.get("Contents", [])]
        if keys:
            s3_client.delete_objects(Bucket="jff-lake", Delete={"Objects": keys})
