"""Run one DAG backfill and wait until every run it created finishes.

    python tools/run_backfill.py --from-date 2026-10-01 --to-date 2026-10-07
    python tools/run_backfill.py ... --project jff-readme

The script unpauses the DAG, creates the backfill, polls `airflow dags list-runs` every 15 seconds
until every run that the backfill created is `success` or `failed` (45 minutes at most), and only
then pauses the DAG. Pausing earlier stops the scheduler mid-backfill without an error, which is the
trap this script exists to close.

It pauses only after it has seen every run finish. If the backfill fails, the poll command fails,
or the budget runs out while a run is still going, the DAG is left unpaused and the script says so,
because a pause would stop that run. When every date already has a successful run, Airflow reuses
it, nothing new runs, and the script reports that instead of waiting.

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
TERMINAL: Final = frozenset({"success", "failed"})
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


def list_runs(project: str | None, service: str) -> dict[str, tuple[date, str]]:
    """Every run of the DAG as run_id -> (logical date, state)."""
    lines = airflow(project, service, "dags", "list-runs", DAG_ID)
    runs: dict[str, tuple[date, str]] = {}
    for _dag_id, run_id, state, _after, logical_date, *_rest in table_rows(lines, 7):
        runs[run_id] = (date.fromisoformat(logical_date[:10]), state)
    return runs


def wait_for_runs(
    project: str | None,
    service: str,
    run_ids: set[str],
    dates: list[date],
    timeout: timedelta,
    interval: int,
) -> tuple[bool, dict[str, str]]:
    """Poll until every run is `success` or `failed`; return (all_success, state per run).

    A failed run does not end the wait on its own: the other runs of the backfill are still
    executing, and pausing the DAG here would stop them.
    """
    deadline = time.monotonic() + timeout.total_seconds()
    while True:
        seen = list_runs(project, service)
        current = {run_id: seen.get(run_id, (None, "missing"))[1] for run_id in run_ids}
        if current and all(state in TERMINAL for state in current.values()):
            return all(state == "success" for state in current.values()), current
        if time.monotonic() >= deadline:
            return False, current
        counts = Counter(current.values())
        summary = ", ".join(f"{state} {count}" for state, count in sorted(counts.items()))
        print(f"[{datetime.now():%H:%M:%S}] {dates[0]} .. {dates[-1]}: {summary}", flush=True)
        time.sleep(interval)


def failed_tasks(project: str | None, service: str, run_id: str) -> list[tuple[str, str]]:
    """Task id and state for every task that did not succeed on one run."""
    lines = airflow(project, service, "tasks", "states-for-dag-run", DAG_ID, run_id)
    tasks: list[tuple[str, str]] = []
    for _dag_id, _logical, task_id, state, *_rest in table_rows(lines, 6):
        if state != "success":
            tasks.append((task_id, state))
    return tasks


def report_failures(
    project: str | None, service: str, states: dict[str, str], new_runs: dict[str, date]
) -> None:
    """Print every run that did not succeed and the tasks that stopped it."""
    for run_id, state in sorted(states.items(), key=lambda item: new_runs.get(item[0], date.min)):
        if state == "success":
            continue
        print(f"run {new_runs.get(run_id)} ({run_id}): {state}")
        if state == "missing":
            continue
        for task_id, task_state in failed_tasks(project, service, run_id):
            print(f"  task {task_id}: {task_state}")


def pause(project: str | None, service: str) -> None:
    """Pause the DAG; only call this once no run of the backfill is executing."""
    print(f"pause {DAG_ID}", flush=True)
    airflow(project, service, "dags", "pause", DAG_ID)


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

    before = set(list_runs(args.project, args.service))
    print(f"backfill {dates[0]} .. {dates[-1]} ({len(dates)} runs)", flush=True)
    try:
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
    except SystemExit:
        print(
            f"{DAG_ID} is left unpaused: the backfill was not created and the scheduler may be "
            "running"
        )
        raise

    after = list_runs(args.project, args.service)
    new_runs = {run_id: runs[0] for run_id, runs in after.items() if run_id not in before}
    # A catchup run for a date in the range can start between the unpause and the backfill. It is
    # not new to the backfill, but pausing while it runs stops it like pausing the backfill would.
    live_old = {
        run_id: day
        for run_id, (day, state) in after.items()
        if run_id not in new_runs and day in dates and state not in TERMINAL
    }
    targets = {**new_runs, **live_old}
    if not targets:
        done = {
            day for run_id, (day, state) in after.items() if day in dates and state == "success"
        }
        awaiting = [day for day in dates if day not in done]
        if not awaiting:
            print(
                f"nothing to run: {len(dates)} dates already have a successful run "
                "(Airflow reuses it)"
            )
            pause(args.project, args.service)
            return 0
        print(f"no run was created for {', '.join(str(day) for day in awaiting)}")
        pause(args.project, args.service)
        return 1

    try:
        ok, states = wait_for_runs(
            args.project,
            args.service,
            set(targets),
            dates,
            timedelta(minutes=args.timeout_minutes),
            args.interval,
        )
    except SystemExit:
        print(
            f"{DAG_ID} is left unpaused: the run states could not be read while a backfill may be "
            "running"
        )
        raise

    if any(state not in TERMINAL for state in states.values()):
        # The budget ran out with work in flight: pausing now would stop it without an error.
        print(
            f"{DAG_ID} is left unpaused: the {args.timeout_minutes}-minute budget ran out with "
            f"{sum(state not in TERMINAL for state in states.values())} run(s) still going"
        )
        for run_id, state in sorted(
            states.items(), key=lambda item: targets.get(item[0], date.min)
        ):
            print(f"  run {targets.get(run_id)} ({run_id}): {state}")
        return 1

    pause(args.project, args.service)
    if ok:
        print(f"done: {len(targets)} runs success", flush=True)
        return 0
    report_failures(args.project, args.service, states, targets)
    print(
        f"failed: {sum(state == 'failed' for state in states.values())} run(s) failed", flush=True
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
