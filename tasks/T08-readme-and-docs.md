# T08: README, architecture diagram, conclusion

Branch: `task/T08-docs` (from `main`, after T07). Serves "code documentation" (10% of the grade), the 29 Nov review and the final slides.

## Step 0: corrections to `docs/security.md` (do these first, nothing else changes there)

1. Replace the sentence that gives a reason for the rootful machine ("A rootless machine was not adopted because ... (T00)") with: "The machine was already rootful when T00 ran; rootless was not tested." T00 never tested rootless.
2. Network exposure row: add the Windows-side evidence Ivan measured on 2026-11-24. `podman ps` shows every published port as `127.0.0.1:<host>->...`. `netstat -ano` shows ports 3000, 5433, 8080, 8333 and 8888 in state LISTENING only on `127.0.0.1`, all owned by one process (the Podman port forwarder; PID 15320 at that time, which changes). `Test-NetConnection` to the machine's own LAN address (192.168.18.138 at that time) failed on all five ports (`lan_ip=False`) while `127.0.0.1` succeeded. Say that `Get-NetTCPConnection -State Listen` returned nothing for these ports on this machine, so `netstat` is the evidence. Say that this was not tested from another device.
3. Decision section: add one sentence of evidence for the firewall: "Windows Defender Firewall is enabled on the Domain, Private and Public profiles, checked 2026-11-24 with `Get-NetFirewallProfile`."
4. "What is not protected": add "GitHub Actions are pinned by version tag, not by commit SHA." Optional `timeout-minutes: 15` on both CI jobs.
5. The candidate newer versions (Postgres 18.6, Metabase v0.65.6, SeaweedFS 4.53) need a source and check date, or the words "not verified".
6. Do not change any Trivy or pip-audit number.

## Content that must be in `README.md` (from the findings of T01 to T07)

- Link to `docs/demo-script.md` for running one day; do not copy it. State that `airflow dags trigger --logical-date` creates an empty run and `airflow backfill create` is the path that runs the tasks.
- Window numbers come from the table in `docs/pipeline-design.md` section 14 (47 days on the dashboard, 48 lake dates per table, and so on). Link it; do not restate numbers that can drift.
- Metrics: 15 of 18 implemented (all 11 P1 plus M5, M11, M13, M16), 17 dashboard cards on 5 pages. M9, M14 and M18 deferred, each with its reason (M9 needs a rolling 28-day peer median, M14 an order-level measure, M18 needs `fact_dq_daily`).
- Test commands per environment: generator tests on the host virtualenv, pipelines tests on the host virtualenv with `pipelines/constraints.txt`, and what CI runs. CI checks lint, types and unit tests; the tests that need SeaweedFS skip themselves there, so CI does not prove the pipeline works end to end. That proof is the clean-room run and the reports T04 to T06.
- Limitations, each with its source report: lake keeps a partition if its date disappears from DuckDB and is never republished; the dashboard date filter is a fixed date in 17 cards (`docs/later.md`); the newest day is provisional until the next file arrives; `fact_branch_day` starts at the first file date; 6 refund changes refer to orders before the window; adding a mart to an existing dataset needs one wide `load_marts --lookback-days` run; two stacks cannot run at once in 7.6 GiB; host port 5432 is held by a native PostgreSQL on Ivan's machine (`POSTGRES_HOST_PORT`); the Podman machine is rootful; no backups; no TLS; commission rates are synthetic placeholders; insights reflect generator assumptions.
- Host Python is 3.15.1 on Ivan's machine, containers and CI use 3.12.
- Docker, Linux and macOS: "expected to work, not tested here" and nothing stronger.

## Deliverables

- `README.md` in English: what the project is; the as-built architecture diagram; layers and data flow (raw CSV, bronze, silver, gold, marts, dashboard); how to run it on Windows with Podman (the only tested path) with the exact commands from T07; short sections for Docker, Linux and macOS marked "expected to work, not tested here" with the known differences (compose provider, rootless Podman, bind mounts); the DAG and its tasks; the reprocessing window and why (refunds up to 8 days later, late orders); the nine injected defects and how each is detected; measured resource numbers (RAM per container, backfill time, peak scheduler memory, rows and sizes); the dashboard pages with a screenshot path; a decisions table with trade-offs and rejected alternatives; limitations; repo layout.
- Update `docs/slides/architecture.*` to the as-built design (Podman, SeaweedFS, Airflow 3.3.2, dbt-duckdb, PostgreSQL, Metabase). Regenerate with the existing tooling.
- `docs/conclusion.md`: conclusion and recommendation with **measured** results only, every figure with the report it comes from (for example backfill durations and scheduler memory from `docs/verification/T04-marts.md` and `T05-parquet.md`, row counts from the section 14 table, defect detection from `T03-dbt.md`, scan results from `T07-hardening.md`). Sections: what the platform does, evidence (numbers and the verification reports it comes from), limitations (single-writer DuckDB, synthetic data so insights reflect generator assumptions, commission rates are placeholders, newest day is provisional, orphan refunds before the window, no real-time view), and what to change at 100 times the volume.
- `docs/verification/T08-docs.md`.

## Rules

- Every number in the docs must come from a file under `docs/verification/` or a command you ran now. Cite the report. No estimates presented as results.
- Do not claim behavior that was not tested. Use "not tested" explicitly.
- Do not change code in this task except fixing a documentation bug you find; list each one.
- Load `lean-code`. No `browser` skill.

## Acceptance (evidence for each)

1. A person who has not seen the project can follow the README on Windows with Podman from `git clone` to the dashboard. Ivan performs this on a clean clone and reports each place he got stuck; fix them.
2. `git grep -n "verify"` in `docs/` and `README.md` lists every remaining unverified claim, each with a reason, or none.
3. Links and paths in the README resolve (`git ls-files` check for each referenced path).
4. The architecture diagram matches `compose.yaml` services and the DAG task list (show the comparison).