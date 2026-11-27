"""dashboards.setup: the mart pre-check, the per-card run, and the pages that report a failure."""

from __future__ import annotations

import pytest

from dashboards import setup


class FakeMetabase(setup.Metabase):
    """Metabase with every HTTP call replaced by a canned answer keyed by (method, path)."""

    def __init__(self, answers: dict[tuple[str, str], object]) -> None:
        super().__init__()
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, object]:
        self.calls.append((method, path))
        return 200, self.answers[(method, path)]


def test_mart_table_exists_true_when_metabase_says_so() -> None:
    answer = {"status": "completed", "data": {"rows": [[True]]}}
    client = FakeMetabase({("POST", "/dataset"): answer})

    assert setup.mart_table_exists(client, 2) is True
    assert client.calls == [("POST", "/dataset")]


def test_mart_table_exists_false_when_the_table_is_missing() -> None:
    answer = {"status": "completed", "data": {"rows": [[False]]}}
    client = FakeMetabase({("POST", "/dataset"): answer})

    assert setup.mart_table_exists(client, 2) is False


def test_mart_table_check_raises_on_a_failed_query() -> None:
    answer = {"status": "failed", "error": "connection refused"}
    client = FakeMetabase({("POST", "/dataset"): answer})

    with pytest.raises(RuntimeError, match="connection refused"):
        setup.mart_table_exists(client, 2)


def test_verify_card_counts_the_rows() -> None:
    answer = {"status": "completed", "data": {"rows": [[1], [2], [3]]}}
    client = FakeMetabase({("POST", "/card/7/query"): answer})

    assert setup.verify_card(client, "Net sales per day", 7) == (3, None)


def test_verify_card_returns_the_error_text() -> None:
    answer = {"status": "failed", "error": "relation mart_sales_day_branch_channel does not exist"}
    client = FakeMetabase({("POST", "/card/7/query"): answer})

    assert setup.verify_card(client, "Net sales per day", 7) == (0, answer["error"])


def test_verify_card_turns_an_http_error_into_text() -> None:
    class Broken(FakeMetabase):
        def request(
            self, method: str, path: str, payload: dict[str, object] | None = None
        ) -> tuple[int, object]:
            raise RuntimeError("POST /card/7/query -> 400: bad query")

    rows, error = setup.verify_card(Broken({}), "Net sales per day", 7)

    assert rows == 0
    assert error is not None and "400" in error


def test_setup_pages_reports_what_was_checked_and_what_failed() -> None:
    answers: dict[tuple[str, str], object] = {
        ("POST", "/card/1/query"): {"status": "completed", "data": {"rows": [[1], [2]]}},
        ("POST", "/card/2/query"): {"status": "failed", "error": "boom"},
        ("PUT", "/dashboard/99"): {},
    }

    class Client(FakeMetabase):
        def ensure_card(self, name: str, definition: dict[str, object]) -> int:
            return 2 if name == "Completed orders" else 1

        def ensure_dashboard(self, page: setup.PageSpec) -> dict[str, object]:
            return {"id": 99}

    pages, report = setup.setup_pages(Client(answers), 2)

    assert report.checked == sum(len(page.cards) for page in setup.PAGES)
    assert report.with_rows == report.checked - 1
    assert [name for name, _error in report.problems] == ["Completed orders"]
    assert report.problems[0][1] == "boom"
    assert pages[0][1] == 99


def test_main_stops_before_the_cards_when_the_mart_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Client(FakeMetabase):
        def wait_healthy(self, timeout_s: int = 300) -> None:
            return None

        def setup_token(self) -> str | None:
            return None

        def login(self, email: str, password: str) -> None:
            return None

        def database_id(self, name: str, create: dict[str, object] | None) -> int:
            return 2

    missing = {"status": "completed", "data": {"rows": [[False]]}}
    monkeypatch.setattr(setup, "Metabase", lambda: Client({("POST", "/dataset"): missing}))
    monkeypatch.setenv("MB_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("MB_ADMIN_PASSWORD", "secret-password")
    monkeypatch.setenv("POSTGRES_ANALYTICS_RO_PASSWORD", "secret-password")

    code = setup.main(dry_run=False)

    assert code == 1
    assert "run the backfill first" in capsys.readouterr().out
