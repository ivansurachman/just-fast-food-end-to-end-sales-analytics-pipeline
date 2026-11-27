"""run_backfill: it waits for the runs it created and never pauses while one is in flight."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tools import run_backfill

DAY = date(2026, 10, 1)
RUN = "backfill__2026-10-01T00:00:00+00:00"
OLD_RUN = "manual__2026-10-01T09:00:00+00:00"


def test_the_wait_keeps_polling_after_one_run_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshots = [
        {RUN: (DAY, "running"), OLD_RUN: (DAY, "failed")},
        {RUN: (DAY, "success"), OLD_RUN: (DAY, "failed")},
    ]
    polls: list[int] = []

    def fake_list_runs(project: str | None, service: str) -> dict[str, tuple[date, str]]:
        polls.append(len(polls))
        return snapshots[len(polls) - 1]

    monkeypatch.setattr(run_backfill, "list_runs", fake_list_runs)
    ok, states = run_backfill.wait_for_runs(
        None, "svc", {RUN, OLD_RUN}, [DAY], timedelta(minutes=1), 0
    )

    assert ok is False
    assert states == {RUN: "success", OLD_RUN: "failed"}
    assert len(polls) == 2, "a failed run must not end the wait while another one still runs"


def test_the_wait_polls_while_a_run_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshots = [
        {RUN: (DAY, "queued")},
        {RUN: (DAY, "running")},
        {RUN: (DAY, "success")},
    ]
    polls: list[int] = []

    def fake_list_runs(project: str | None, service: str) -> dict[str, tuple[date, str]]:
        polls.append(len(polls))
        return snapshots[min(len(polls) - 1, len(snapshots) - 1)]

    monkeypatch.setattr(run_backfill, "list_runs", fake_list_runs)
    ok, states = run_backfill.wait_for_runs(None, "svc", {RUN}, [DAY], timedelta(minutes=1), 0)

    assert ok is True
    assert states == {RUN: "success"}
    assert len(polls) == 3


def test_main_pauses_only_after_the_new_run_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []
    polls: list[int] = []

    def fake_airflow(project: str | None, service: str, *args: str) -> list[str]:
        commands.append(args)
        return []

    def fake_list_runs(project: str | None, service: str) -> dict[str, tuple[date, str]]:
        polls.append(len(polls))
        if len(polls) == 1:
            return {OLD_RUN: (DAY, "success")}
        return {OLD_RUN: (DAY, "success"), RUN: (DAY, "running" if len(polls) < 3 else "success")}

    monkeypatch.setattr(run_backfill, "airflow", fake_airflow)
    monkeypatch.setattr(run_backfill, "list_runs", fake_list_runs)

    code = run_backfill.main(
        ["--from-date", "2026-10-01", "--to-date", "2026-10-01", "--interval", "0"]
    )

    assert code == 0
    assert commands[0] == ("dags", "unpause", "jff_daily")
    assert commands[-1] == ("dags", "pause", "jff_daily"), "pause must be the last command"
    assert len(polls) >= 3, "the running run has to be polled again before pausing"


def test_main_leaves_the_dag_unpaused_when_the_poll_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []
    polls: list[int] = []

    def fake_airflow(project: str | None, service: str, *args: str) -> list[str]:
        commands.append(args)
        return []

    def fake_list_runs(project: str | None, service: str) -> dict[str, tuple[date, str]]:
        polls.append(len(polls))
        if len(polls) == 1:
            return {OLD_RUN: (DAY, "success")}
        if len(polls) == 2:
            return {OLD_RUN: (DAY, "success"), RUN: (DAY, "running")}
        raise SystemExit(2)

    monkeypatch.setattr(run_backfill, "airflow", fake_airflow)
    monkeypatch.setattr(run_backfill, "list_runs", fake_list_runs)

    with pytest.raises(SystemExit):
        run_backfill.main(["--from-date", "2026-10-01", "--to-date", "2026-10-01"])

    assert ("dags", "pause", "jff_daily") not in commands, "a pause would stop the run in flight"


def test_main_reports_reused_runs_without_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_airflow(project: str | None, service: str, *args: str) -> list[str]:
        commands.append(args)
        return []

    monkeypatch.setattr(run_backfill, "airflow", fake_airflow)
    monkeypatch.setattr(run_backfill, "list_runs", lambda p, s: {OLD_RUN: (DAY, "success")})

    code = run_backfill.main(["--from-date", "2026-10-01", "--to-date", "2026-10-01"])

    assert code == 0
    assert commands[-1] == ("dags", "pause", "jff_daily")


def test_main_leaves_the_dag_unpaused_when_the_budget_runs_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commands: list[tuple[str, ...]] = []
    polls: list[int] = []

    def fake_airflow(project: str | None, service: str, *args: str) -> list[str]:
        commands.append(args)
        return []

    def fake_list_runs(project: str | None, service: str) -> dict[str, tuple[date, str]]:
        polls.append(len(polls))
        return {} if len(polls) == 1 else {RUN: (DAY, "running")}

    monkeypatch.setattr(run_backfill, "airflow", fake_airflow)
    monkeypatch.setattr(run_backfill, "list_runs", fake_list_runs)

    code = run_backfill.main(
        ["--from-date", "2026-10-01", "--to-date", "2026-10-01", "--timeout-minutes", "0"]
    )

    assert code == 1
    assert ("dags", "pause", "jff_daily") not in commands
    assert "left unpaused" in capsys.readouterr().out


def test_main_waits_for_a_live_catchup_run_when_nothing_new_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    polls: list[int] = []

    def fake_airflow(project: str | None, service: str, *args: str) -> list[str]:
        commands.append(args)
        return []

    def fake_list_runs(project: str | None, service: str) -> dict[str, tuple[date, str]]:
        polls.append(len(polls))
        state = "success" if len(polls) >= 4 else "running"
        return {OLD_RUN: (DAY, state)}

    monkeypatch.setattr(run_backfill, "airflow", fake_airflow)
    monkeypatch.setattr(run_backfill, "list_runs", fake_list_runs)

    code = run_backfill.main(
        ["--from-date", "2026-10-01", "--to-date", "2026-10-01", "--interval", "0"]
    )

    assert code == 0
    assert len(polls) >= 4, "the catchup run has to be polled until it finishes"
    assert commands[-1] == ("dags", "pause", "jff_daily")


def test_failed_tasks_reads_the_states_table(monkeypatch: pytest.MonkeyPatch) -> None:
    table = [
        "dag_id    | logical_date              | task_id         | state   | start_date | end_date",
        "==========+===========================+=================+=========+============+========",
        "jff_daily | 2026-10-01T00:00:00+00:00 | wait_manifest   | success | -          | -",
        "jff_daily | 2026-10-01T00:00:00+00:00 | dbt_run         | failed  | -          | -",
        "jff_daily | 2026-10-01T00:00:00+00:00 | load_marts      | upstream_failed | - | -",
    ]
    monkeypatch.setattr(run_backfill, "airflow", lambda p, s, *args: table)

    assert run_backfill.failed_tasks(None, "svc", RUN) == [
        ("dbt_run", "failed"),
        ("load_marts", "upstream_failed"),
    ]
