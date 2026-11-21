"""load_marts: window arithmetic, and the empty window that used to leave stale rows behind."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from pipelines import load_marts

CREATE_MART = f"""
create table {load_marts.MART} (
    order_date date, branch_key integer, channel_key text,
    total_orders bigint, completed_orders bigint, cancelled_orders bigint, refunded_orders bigint,
    gross_amount bigint, discount_amount bigint, net_amount bigint, cogs_amount bigint,
    commission_amount bigint
)
"""


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


def mart_file(path: Path, rows: list[tuple[object, ...]]) -> str:
    """A DuckDB file holding the mart table, so read_mart has something real to read."""
    con = duckdb.connect(str(path))
    con.execute(CREATE_MART)
    if rows:
        con.executemany(
            f"insert into {load_marts.MART} values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
    con.close()
    return str(path)


def test_window_starts_lookback_days_before_the_run_date() -> None:
    assert load_marts.window("2026-10-09", 10) == (date(2026, 9, 29), date(2026, 10, 9))


def test_empty_window_still_applies_the_schema_and_the_delete(
    fake_connection: FakeConnection,
) -> None:
    written = load_marts.replace_window([], date(2026, 9, 29), date(2026, 10, 9))

    statements = [sql for sql, _ in fake_connection.cursor_obj.executed]
    assert written == 0
    assert any("create table if not exists" in sql for sql in statements)
    assert any(
        sql.startswith(f"delete from {load_marts.MART} where order_date between")
        for sql in statements
    )
    assert fake_connection.cursor_obj.copied == []
    assert fake_connection.committed


def test_load_marts_on_an_empty_window_replaces_the_window(
    tmp_path: Path, fake_connection: FakeConnection
) -> None:
    path = mart_file(tmp_path / "jff.duckdb", [])

    written = load_marts.load_marts("2026-10-09", duckdb_path=path)

    assert written == 0
    assert any(
        sql.startswith(f"delete from {load_marts.MART}")
        for sql, _ in fake_connection.cursor_obj.executed
    ), "an empty window must still delete, otherwise rows from an earlier run stay"


def test_only_rows_inside_the_window_are_copied(
    tmp_path: Path, fake_connection: FakeConnection
) -> None:
    inside = (date(2026, 10, 9), 1, "grabfood", 10, 9, 1, 0, 100, 10, 90, 40, 5)
    outside = (date(2026, 9, 1), 2, "gofood", 5, 5, 0, 0, 50, 0, 50, 20, 3)
    path = mart_file(tmp_path / "jff.duckdb", [inside, outside])

    written = load_marts.load_marts("2026-10-09", duckdb_path=path)

    assert written == 1
    assert fake_connection.cursor_obj.copied == [inside]
    delete_sql, delete_params = next(
        (sql, params)
        for sql, params in fake_connection.cursor_obj.executed
        if sql.startswith(f"delete from {load_marts.MART}")
    )
    assert delete_params == (date(2026, 9, 29), date(2026, 10, 9))
