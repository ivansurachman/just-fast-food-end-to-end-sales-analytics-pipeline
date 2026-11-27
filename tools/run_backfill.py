"""Run one DAG backfill and wait until every run in the range finishes.

    python tools/run_backfill.py --from-date 2026-10-01 --to-date 2026-10-07
    python tools/run_backfill.py ... --project jff-readme

The script unpauses the DAG, creates the backfill, polls `airflow dags list-runs` every 15 seconds
until every run whose logical date is inside the range is `success` or `failed` (45 minutes at
most), and only then pauses the DAG. Pausing earlier stops the scheduler mid-backfill without an
error, which is the trap this script exists to close. Exits non-zero when a run failed or the budget
ran out, after printing the failed run and its task states.

The Airflow commands run through `podman compose exec`, so the container name never appears here:
the script uses the compose project from the current directory, or the one given with `--project`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Final

DAG_ID: Final = "jff_daily"
SERVICE: Final = "airflow-scheduler"
TIMEOUT_MINUTES: Final = 45
INTERVAL_SECONDS: Final = 15
ANSI_RESET: Final = "\x1b[0m"


def compose_command(project: str | None, service: str, *args: str) -> list[str]:
    """The podman command that runs one Airflow CLI call inside the scheduler container."""
    command = ["podman", "compose"]
    if project:
        command += ["-p", project]
    return command + ["exec", "-T", service, "airflow", *args]


def airflow(project: str | None, service: str, *args: str) -> list[str]:
    """Run one Airflow CLI call and return its stdout lines; exit when the CLI fails."""
    command = compose_command(project, service, *args)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        stderr = result.stderr.replace(ANSI_RESET, "").strip().splitlines()
        print(f"command failed: {' '.join(command)}")
        for line in stderr[-5:]:
            print(f"  {line}")
        raise SystemExit(2)
    return [line.replace(ANSI_RESET, "") for line in result.stdout.splitlines()]


def table_rows(lines: list[str], columns: int) -> list[list[str]]:
    """Rows of an `airflow` plain table: skip the header, the ===+=== separator and stray output."""
    rows: list[list[str]] = []
    for line in lines:
        if "|" not in line or "====" in line:
            continue
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) != columns or cells[0] == "dag_id":
            continue
        rows.append(cells)
    return rows


def run_states(project: str | None, service: str) -> dict[date, set[str]]:
    """Every state seen for each logical date.

    A date can have more than one run (a manual run from earlier work, the backfill run now); the
    date is only as good as its worst run, so they are collected together rather than overwritten.
    """
    lines = airflow(project, service, "dags", "list-runs", DAG_ID)
    states: dict[date, set[str]] = {}
    for _dag_id, _run_id, state, _after, logical_date, *_rest in table_rows(lines, 7):
        day = date.fromisoformat(logical_date[:10])
        states.setdefault(day, set()).add(state)
    return states


def aggregate(states: set[str] | None) -> str:
    """One word for the date: success when every run succeeded, failed when any failed."""
    if not states:
        return "missing"
    if "failed" in states:
        return "failed"
    if states == {"success"}:
        return "success"
    return "pending"


def failed_tasks(project: str | None, service: str, logical_date: date) -> list[tuple[str, str]]:
    """Task id and state for every task that did not succeed on the backfill run of one day."""
    run_id = f"backfill__{logical_date.isoformat()}T00:00:00+00:00"
    lines = airflow(project, service, "tasks", "states-for-dag-run", DAG_ID, run_id)
    tasks: list[tuple[str, str]] = []
    for _dag_id, _logical, task_id, state, *_rest in table_rows(lines, 6):
        if state != "success":
            tasks.append((task_id, state))
    return tasks


def wait_for_dates(
    project: str | None,
    service: str,
    dates: list[date],
    timeout: timedelta,
    interval: int,
) -> tuple[bool, dict[date, str]]:
    """Poll until every date finished; return (all_success, state per date)."""
    deadline = time.monotonic() + timeout.total_seconds()
    while True:
        seen = run_states(project, service)
        current = {day: aggregate(seen.get(day)) for day in dates}
        if all(state == "success" for state in current.values()):
            return True, current
        if any(state == "failed" for state in current.values()):
            return False, current
        if time.monotonic() >= deadline:
            return False, current
        counts = Counter(current.values())
        summary = ", ".join(f"{state} {count}" for state, count in sorted(counts.items()))
        print(f"[{datetime.now():%H:%M:%S}] {dates[0]} .. {dates[-1]}: {summary}", flush=True)
        time.sleep(interval)


def report_failures(project: str | None, service: str, states: dict[date, str]) -> None:
    """Print every date that did not succeed and the tasks that stopped it."""
    for day, state in sorted(states.items()):
        if state == "success":
            continue
        print(f"run {day}: {state}")
        if state == "missing":
            continue
        for task_id, task_state in failed_tasks(project, service, day):
            print(f"  task {task_id}: {task_state}")


def main(argv: list[str] | None = None) -> int:
    """CLI: unpause, backfill, wait, pause, and report."""
    parser = argparse.ArgumentParser(description="Run one DAG backfill and wait for it.")
    parser.add_argument("--from-date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--to-date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument(
        "--project", help="compose project name, when it is not the one in compose.yaml"
    )
    parser.add_argument("--service", default=SERVICE, help=f"compose service (default {SERVICE})")
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=TIMEOUT_MINUTES,
        help=f"budget in minutes (default {TIMEOUT_MINUTES})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=INTERVAL_SECONDS,
        help=f"poll interval in seconds (default {INTERVAL_SECONDS})",
    )
    args = parser.parse_args(argv)
    if args.from_date > args.to_date:
        parser.error("--from-date must not be after --to-date")

    dates = [
        args.from_date + timedelta(days=offset)
        for offset in range((args.to_date - args.from_date).days + 1)
    ]
    print(f"unpause {DAG_ID}", flush=True)
    airflow(args.project, args.service, "dags", "unpause", DAG_ID)
    try:
        print(f"backfill {dates[0]} .. {dates[-1]} ({len(dates)} runs)", flush=True)
        airflow(
            args.project,
            args.service,
            "backfill",
            "create",
            "--dag-id",
            DAG_ID,
            "--from-date",
            dates[0].isoformat(),
            "--to-date",
            dates[-1].isoformat(),
        )
        ok, states = wait_for_dates(
            args.project,
            args.service,
            dates,
            timedelta(minutes=args.timeout_minutes),
            args.interval,
        )
    finally:
        print(f"pause {DAG_ID}", flush=True)
        airflow(args.project, args.service, "dags", "pause", DAG_ID)

    if ok:
        print(f"done: {len(dates)} runs success", flush=True)
        return 0
    report_failures(args.project, args.service, states)
    print(f"failed: not every run succeeded within {args.timeout_minutes} minutes", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
