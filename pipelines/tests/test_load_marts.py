"""load_marts: the window, the registry of marts, and an empty window that still clears rows."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from pipelines import load_marts

COLUMN_TYPES = {
    "order_date": "DATE",
    "branch_key": "INTEGER",
    "hour_local": "INTEGER",
    "menu_item_key": "VARCHAR",
    "promo_key": "VARCHAR",
    "channel_key": "VARCHAR",
    "is_expected": "BOOLEAN",
}


class FakeCopy:
    def __init__(self, sink: list[tuple[object, ...]]) -> None:
        self.sink = sink

    def __enter__(self) -> FakeCopy:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def write_row(self, row: tuple[object, ...]) -> None:
        self.sink.append(row)


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []
        self.copied: list[tuple[object, ...]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))

    def copy(self, sql: str) -> FakeCopy:
        self.executed.append((sql, None))
        return FakeCopy(self.copied)


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.committed = True
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_obj


@pytest.fixture
def fake_connection(monkeypatch: pytest.MonkeyPatch) -> FakeConnection:
    connection = FakeConnection()
    monkeypatch.setattr(load_marts.psycopg, "connect", lambda *args, **kwargs: connection)
    return connection


def create_marts(path: Path) -> str:
    """A DuckDB file with one empty table per registered mart, typed like the real ones."""
    con = duckdb.connect(str(path))
    for mart in load_marts.MARTS:
        columns = ", ".join(
            f"{column} {COLUMN_TYPES.get(column, 'BIGINT')}" for column in mart.columns
        )
        con.execute(f"create table {mart.name} ({columns})")
    con.close()
    return str(path)


def insert_rows(path: Path, mart: load_marts.Mart, rows: list[tuple[object, ...]]) -> None:
    con = duckdb.connect(str(path))
    placeholders = ", ".join("?" for _ in mart.columns)
    con.executemany(f"insert into {mart.name} values ({placeholders})", rows)
    con.close()


def test_window_starts_lookback_days_before_the_run_date() -> None:
    assert load_marts.window("2026-10-09", 10) == (date(2026, 9, 29), date(2026, 10, 9))


def test_every_mart_starts_its_columns_with_the_order_date() -> None:
    assert [mart.name for mart in load_marts.MARTS] == [
        "mart_sales_day_branch_channel",
        "mart_hourly",
        "mart_item_day",
        "mart_promo_day",
        "mart_branch_coverage",
    ]
    for mart in load_marts.MARTS:
        assert mart.columns[0] == "order_date", mart.name


def test_empty_window_still_applies_the_schema_and_the_delete(
    fake_connection: FakeConnection,
) -> None:
    mart = load_marts.MARTS[2]

    written = load_marts.replace_window(mart, [], date(2026, 9, 29), date(2026, 10, 9))

    statements = [sql for sql, _ in fake_connection.cursor_obj.executed]
    assert written == 0
    assert any("create table if not exists" in sql for sql in statements)
    assert any(
        sql.startswith(f"delete from {mart.name} where order_date between") for sql in statements
    )
    assert fake_connection.cursor_obj.copied == []
    assert fake_connection.committed, "the empty window must still commit the delete"


def test_load_marts_on_an_empty_window_clears_every_mart(
    tmp_path: Path, fake_connection: FakeConnection
) -> None:
    path = create_marts(tmp_path / "jff.duckdb")

    written = load_marts.load_marts("2026-10-09", duckdb_path=path)

    assert written == {mart.name: 0 for mart in load_marts.MARTS}
    deletes = [
        sql for sql, _ in fake_connection.cursor_obj.executed if sql.startswith("delete from ")
    ]
    assert sorted(deletes) == sorted(
        f"delete from {mart.name} where order_date between %s and %s" for mart in load_marts.MARTS
    ), "an empty window must still delete, otherwise rows from an earlier run stay"


def test_only_rows_inside_the_window_are_copied(
    tmp_path: Path, fake_connection: FakeConnection
) -> None:
    mart = load_marts.MARTS[2]
    path = create_marts(tmp_path / "jff.duckdb")
    inside = (date(2026, 10, 9), "MI-001", 3, 75000, 30000)
    outside = (date(2026, 9, 1), "MI-002", 1, 25000, 10000)
    insert_rows(tmp_path / "jff.duckdb", mart, [inside, outside])

    written = load_marts.load_marts("2026-10-09", duckdb_path=path)

    assert written[mart.name] == 1
    assert written["mart_hourly"] == 0
    assert inside in fake_connection.cursor_obj.copied
    assert outside not in fake_connection.cursor_obj.copied
