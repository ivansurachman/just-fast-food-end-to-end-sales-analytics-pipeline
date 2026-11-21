# AGENTS.md

Project: Just Fast Food (JFF), a bootcamp final project (Dibimbing, data engineering, individual).
End-to-end sales analytics for a fictional fast-food chain on generated data. Batch pipeline:
CSV on S3-compatible storage -> Parquet bronze -> DuckDB + dbt silver/gold -> PostgreSQL marts -> Metabase.
Owner: Ivan. Hard checkpoint: **22 Nov 2026, pipeline runs end to end** (Mentoring 2).

Read before working: `docs/pipeline-design.md` (approved design), `docs/data-model.md`, `docs/data-dictionary.md`.
Task specs live in `tasks/`. Work on one task at a time, in order, only the one Ivan names.

## Language

- Code, comments, docstrings, commit messages, documentation: English.
- Talk to Ivan in Indonesian.

## Decided architecture (do not change; if you think it is wrong, stop and tell Ivan)

- Source: CSV only, on SeaweedFS (S3 API). No PostgreSQL OLTP.
- Lake: Parquet bronze on S3. Silver/gold computed with DuckDB + dbt (incremental delete+insert by `order_date`, 10-day lookback). Parquet publish by `order_date` is P2.
- Marts: PostgreSQL. Dashboard: Metabase. Orchestrator: Airflow. One Postgres instance, three databases (airflow, metabase, analytics).
- Everything in containers with **Podman on Windows Home** (WSL2 backend; no `.wslconfig`, so the VM has the WSL2 default of about 7.6 GiB on Ivan's machine; do not edit `.wslconfig`). Docs must also cover Docker, Linux, macOS.
- Out of scope: Iceberg, ClickHouse, monitoring stack, Telegram alerts, Kafka/Spark, TikTok voucher.

## Hard rules

- Memory budget: whole stack hard limit 5.6 GB (the VM has about 7.6 GiB, so headroom is about 2 GiB; keep it) (see the table in `docs/pipeline-design.md`). Every container gets an explicit memory limit. Never raise a limit to make something pass; report instead.
- Pin every version (images, Python packages). Choose releases older than 14 days. Record choices in `docs/versions.md`.
- No scope creep. Do not add features, services, or tools that the task does not name. Put ideas in `docs/later.md` instead.
- Never commit `.env`, credentials, or generated data other than `sample-data/`.
- Do not edit `generator/` behaviour or `sample-data/` unless the task says so. Generator output must stay byte-deterministic.
- Do not run `wsl --shutdown`, edit `.wslconfig`, delete volumes, or run `git push`/`git reset --hard` without asking Ivan first.
- Windows-safe: relative paths, forward slashes in compose files, LF line endings, no bash-only scripts as the only entry point (provide PowerShell and sh variants or a Python script).
- If you are not sure about a version, a flag, or Podman compatibility, write "verify" and test it. Do not guess.

## Commands

Generator (run from `generator/`):

    pip install -c constraints.txt -e ".[dev,s3test]"
    pytest
    ruff check . && ruff format --check .
    mypy src tests

Clean code applies to all code: small flat functions, clear names, type hints, docstrings, no dead code.

## Definition of done

A task is done only when every acceptance item in its spec has evidence. Write the evidence to the file the spec names
(`docs/verification/<task>.md`): the exact command, the relevant output, and a verdict. Anything not run is written as
"not run", never as passed. End your final message with a list of what you verified and how, and what you did not verify.

## Skills

Project skills live in `.opencode/skills/`. Load `lean-code` before writing or editing code, `podman-windows` before touching compose files, Dockerfiles or Podman commands, and `debug-protocol` on the first failure. Do not add or install other skills.

## Agents

One builder agent executes a task spec. Do not start subagents that edit files, and do not run writers in parallel: tasks share `compose.yaml`, `dags/`, and `dbt/`. The `reviewer` subagent is read-only and runs only when Ivan asks for it.

## Workflow

- One git branch per task: `task/T01-infra`, etc. Small commits with Conventional Commit messages.
- Stop and ask when a STOP condition in the task spec is hit.
