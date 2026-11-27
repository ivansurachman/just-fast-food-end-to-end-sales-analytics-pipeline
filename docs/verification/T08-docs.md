opencode-go/deepseek-v4.1-flash

# T08 verification: README, architecture diagram, conclusion

Task: `tasks/T08-readme-and-docs.md`. Branch `task/T08-docs` (from `main` = `667094b`, Ivan's expanded spec). Date 2026-11-24.

## Deliverables

| Path | What it is |
|---|---|
| `README.md` | Rewritten for someone who has never seen the project: architecture, layers, Windows runbook, other platforms, DAG, window, defects, metrics, measured resources, decisions, limitations, tests, layout |
| `docs/slides/architecture.dot`, `.svg`, `.png` | Regenerated as the as-built diagram |
| `docs/conclusion.md` | Conclusion and recommendation, every figure with its report |
| `docs/security.md` | Step 0 corrections (six items) |
| `docs/verification/T08-docs.md` | This file |

## Step 0: `docs/security.md`

| # | Change | Evidence |
|---|---|---|
| 1 | Rootful reason replaced by "The machine was already rootful when T00 ran; rootless was not tested." | T00 never tested rootless |
| 2 | Network exposure row now points at a measured paragraph: `podman ps`, `netstat -ano`, `Test-NetConnection`, `Get-NetTCPConnection` | run on 2026-11-24, output below |
| 3 | Decision section gains the firewall sentence | `Get-NetFirewallProfile` on 2026-11-24 |
| 4 | "GitHub Actions are pinned by version tag, not by commit SHA." plus `timeout-minutes: 15` on both CI jobs | workflow parses, `{'pipelines': 15, 'generator': 15}` |
| 5 | Candidate newer tags now carry release dates and the words "not verified" / "not scanned" | `docs/versions.md` |
| 6 | No Trivy or pip-audit number changed | `git diff` shows no changed numeric line |

The measurement the row now cites, run in this session:

```
podman ps --format "{{.Names}} {{.Ports}}"
jff_postgres_1        127.0.0.1:5433->5432/tcp
jff_seaweedfs_1       127.0.0.1:8333->8333/tcp, 127.0.0.1:8888->8888/tcp, ...
jff_metabase_1        127.0.0.1:3000->3000/tcp
jff_airflow-api-server_1  127.0.0.1:8080->8080/tcp

netstat -ano | findstr ":3000 :5433 :8080 :8333 :8888"
  TCP    127.0.0.1:3000   0.0.0.0:0  LISTENING  15320
  TCP    127.0.0.1:5433   0.0.0.0:0  LISTENING  15320
  TCP    127.0.0.1:8080   0.0.0.0:0  LISTENING  15320
  TCP    127.0.0.1:8333   0.0.0.0:0  LISTENING  15320
  TCP    127.0.0.1:8888   0.0.0.0:0  LISTENING  15320

Get-NetTCPConnection -State Listen -LocalPort <port>   (all five, 2026-11-24)
3000 LISTENING local=127.0.0.1 pid=15320   (same for 5433, 8080, 8333, 8888)

Test-NetConnection -ComputerName 192.168.18.138 -Port <port> -InformationLevel Quiet
port=3000 lan_ip=False loopback=True
port=5433 lan_ip=False loopback=True
port=8080 lan_ip=False loopback=True
port=8333 lan_ip=False loopback=True
port=8888 lan_ip=False loopback=True

Get-NetFirewallProfile
Domain  True
Private True
Public  True
```

Two honest notes: `Get-NetTCPConnection` did return the five ports when re-run here, although Ivan's
earlier attempt returned nothing for them, which is why `netstat` is the recorded evidence; and the ports
were not tested from another device.

## README content against the task list

| Asked | Where in `README.md` |
|---|---|
| What the project is | opening paragraph |
| As-built architecture diagram | "Architecture (as built)" with `docs/slides/architecture.svg` and the service/limit table |
| Layers and data flow | "Data flow" block |
| Windows with Podman, exact commands | "Run it on Windows with Podman (the only tested path)", the six steps from T07 |
| Docker, Linux, macOS as "expected to work, not tested here" | "Other platforms" table with the known difference per platform |
| DAG and its tasks | "The DAG" table, seven tasks with the idempotence reason |
| Reprocessing window and why | "Reprocessing window", refunds and late orders, guard test |
| Nine injected defects and detection | "Injected defects and how each is detected", with the T03 counts |
| Measured resources | "Measured resources", every row with its report |
| Dashboard pages with a screenshot path | "Metrics and dashboard", five pages, five PNG paths |
| Decisions table | "Decisions", D1-D6 with the rejected alternative |
| Limitations | "Limitations", twelve items, each with its report |
| Repo layout | "Repo layout" |

Window numbers are not restated: the README links `docs/pipeline-design.md` section 14 everywhere a count
would drift.

## Architecture diagram

Regenerated with graphviz 12.2.1 (from `docker.io/library/alpine:3.24.3`, released 2026-10-23) because no
`dot` binary is installed on the host:

```
podman run --rm -v "$(Resolve-Path docs\slides):/w" docker.io/library/alpine:3.24.3 \
  sh -c "apk add --no-cache graphviz >/dev/null && dot -Tsvg /w/architecture.dot -o /w/architecture.svg \
         && dot -Tpng /w/architecture.dot -o /w/architecture.png"
dot - graphviz version 12.2.1 (20241206.2353)
```

The diagram was rewritten from the pre-build sketch (which still said "9 GB", "DAG simulate_source" and
"6 pages, 18 metrics"). It now names every compose service and every DAG task, which is the comparison
below.

## Acceptance

### 1. Clean clone on Windows

Run by Ivan on 2026-11-27 (`C:\dev\jff-readme-test-report.md`, clone `C:\dev\jff-readme-test`). The run
reached the dashboard only after a manual recovery; the six findings are handled in "README test
follow-up" below. The re-test with the fixed README has not been done yet.

### 2. `git grep -n "verify"` in `docs/` and `README.md`

```
$ git grep -n -i "verify" -- docs README.md
docs/cli-guide.md:108:| Clean data to verify metrics | add `--clean` |
docs/verification/T04-marts.md:289:INFO app-db.setup :: Verifying postgres Database Connection ...
docs/verification/T08-docs.md: ... (15 lines: this section and the table below)

17 lines: 1 recipe row, 1 quoted log line, 15 in this record.
```

None of them is an unverified claim. The first is a recipe row where "verify" is the verb; the second is
a Metabase log line quoted as evidence; the rest is this section quoting that grep. No claim in the living
docs is left unverified: every earlier marker was resolved in this task.

| Was | Now |
|---|---|
| `docs/pipeline-design.md` status "draft for approval, nothing has been run, items marked verify" | "implemented, 24 Nov 2026", with the measured outcome or "not tested" written in each place |
| D1 option B "(verify)" | "(not tested: option A was chosen)" |
| `load_marts` postgres extension "(verify)" | "(not measured: the loader never used that path)" |
| §9 "All verify until the smoke test passes" | "Measured on Ivan's machine in T00 and refined by T04-T07" |
| §9 rootless UID "(verify)" | "Not needed in practice ... (T00, T04)" |
| D3 "(verify tag on 18 Nov)" | "3.3.2, pinned on 2026-09-17" |
| `docs/cli-guide.md` "Windows steps not yet tested (verify)" | tested on Windows 11 with Python 3.15.1 (T00, T04-T07) |
| `docs/cli-guide.md` S3 "not yet tested ... verify variable names" | tested against SeaweedFS from host and container; credentials named |
| `docs/data-dictionary.md` commission "verify against real terms" | "not real platform terms" |

### 3. Links and paths

A checker extracted every repo path mentioned in `README.md`, `docs/conclusion.md`, `docs/security.md`
and `docs/demo-script.md` and required it to exist and be tracked:

```
checked=59 missing=0
```

The same checker over every file in `docs/`: `checked=47 missing=0`.

### 4. Diagram against `compose.yaml` and the DAG

```
compose services (9):
  postgres, postgres-ro, seaweedfs, seaweedfs-init, airflow-init,
  airflow-api-server, airflow-scheduler, airflow-dag-processor, metabase
all present in docs/slides/architecture.dot: True

airflow tasks list jff_daily (7):
  check_bronze, dbt_run, dbt_test, ingest_bronze, load_marts, publish_parquet, wait_manifest
all present in docs/slides/architecture.dot: True
```

## Documentation bugs fixed in this task

1. `docs/pipeline-design.md` still described itself as an unrun draft and carried six stale "verify"
   markers; the smoke test and T04-T07 settled them.
2. `docs/cli-guide.md` claimed the Windows steps and the SeaweedFS output were untested; both ran in T00,
   T04 and T07.
3. `docs/data-dictionary.md` told the reader to "verify against real terms" as if that were pending; the
   value is a synthetic placeholder by design.
4. `README.md` restated counts and the one-day procedure; it now links `docs/pipeline-design.md` section 14
   and `docs/demo-script.md`.
5. `docs/slides/architecture.dot` still showed the pre-build plan (9 GB, a generator DAG, 6 pages).

No application code changed in this task except the two `timeout-minutes` lines the task asked for.

## Review follow-up (2026-11-24)

The reviewer found one wrong number and two wrong citations; all six findings are closed here.

| Finding | Fix |
|---|---|
| **Blocker:** "6 refund changes" was the task text's estimate at scale 0.02. At scale 0.1 the measured value is 163 rows referencing orders before the window, 166 orphan rows with the three dropped branch-days | `README.md` and `docs/conclusion.md` now say 163 and 166 and cite `docs/verification/T04-marts.md` |
| README claimed the exact sequence ran from an empty clone in one pass | it now says every step ran in the T07 clean-room and the order is the corrected one, because that run needed two attempts |
| "generator 41" cited T06 section 7 and T07 section 5, neither of which counts the generator tests | the source is now T06 section 7, T01 (41 passed) and T07 section 5 |
| 27,410 rows in `mart_sales_day_branch_channel` had no citation where it was used | now cites T07 section 8 |
| "about a million orders" and "12k orders per day" read as measurements | the first is labelled a judgment, the second a derivation from section 14 |
| The diagram showed a machine-specific host port and Metabase only inside a cluster label | the label is now `${POSTGRES_HOST_PORT:-5432}` and Metabase has its own `services: metabase` line |

The diagram was re-rendered after the label change and still carries all nine compose services and all
seven DAG tasks.

## Six documentation fixes (2026-11-27)

Ivan asked for six corrections, with one constraint: no Trivy or pip-audit number may change.

| # | File | Change |
|---|---|---|
| 1 | `docs/security.md` | "Loopback evidence" moved out of the "What is protected" table into a subsection below it; the table is one contiguous block again |
| 2 | `docs/security.md` | The candidate-tag sentence now reads the day counts at scan time: Postgres 18.6 is 17 days, SeaweedFS 4.53 is 15 days (both older than 14, neither scanned), Metabase v0.65.6 is 5 days and still too new. The dates match `docs/versions.md` |
| 3 | `docs/security.md` | The LAN IP and the words "Wi-Fi" are gone; the text says "the machine's own LAN address" |
| 4 | `docs/pipeline-design.md` section 14 | Added the "as of 2026-11-24" line about 49 lake dates and the demo day that T07 item 7 added; the table numbers are unchanged |
| 5 | `docs/conclusion.md` | 574,838 / 1,399,537 / 196 / 49 now carry "as of 2026-11-24" and point at section 14 for the baseline |
| 6 | `docs/conclusion.md` | "if the rubric needs 18 of 18" became "if the project should deliver all 18 metrics it defined". The rubric does not name a metric count; the 18 comes from `docs/data-model.md` |

`git diff --stat` before this section was added:

```
 docs/conclusion.md      |  7 ++++---
 docs/pipeline-design.md |  4 ++++
 docs/security.md        | 30 ++++++++++++++++--------------
 3 files changed, 24 insertions(+), 17 deletions(-)
```

Checks run for these fixes:

- Table contiguity: start line 9, end line 17, 9 row lines, 0 blank lines inside.
- `Select-String` for `192.168` and `Wi-Fi` in `docs/security.md`: no matches.
- Day counts on 2026-11-23, computed with `python -c`: 17, 15 and 5 days (older than 14 only for the
  first two).
- `git diff` of the three files filtered for `216`, `342`, `108`, `CRITICAL`, `HIGH |`: no changed line
  carries a scan number.

## README test follow-up (2026-11-27)

Ivan's clean-clone test (`C:\dev\jff-readme-test-report.md`) found that the README as written does not
reach a dashboard: the container name is project-dependent, `.env` editing is undocumented, and the
`pause` line stops the backfill before the marts are loaded. Six fixes, in the report's language.

| Report item | Fix |
|---|---|
| #3 `backfill create` is asynchronous and the next line pauses the DAG | New `tools/run_backfill.py`: unpause, backfill, poll `airflow dags list-runs` every 15 s until every run in the range is finished (45 min budget, progress each poll), then pause; non-zero exit on failure or timeout, printing the failed run and its task states. The README step is now one call |
| #1 container names depend on the project | `podman compose exec -T airflow-scheduler ...` replaces `podman exec jff_airflow-scheduler_1 ...` in the README and the demo script, and both say to add `-p <name>` when the stack was started with one |
| #2, `.env` | `tools/gen_env.py --postgres-port` writes the port, and without the flag it probes 127.0.0.1:5432 and writes 5433 with a reason when the port is taken. The file is written with LF endings (`write_text(..., newline="\n")`); the README warns that an editor which saves CRLF (or `Set-Content -NoNewline`) joins the lines |
| #5 "Point the DAG at the days that exist" | removed. The quick start generates 2026-10-01 .. 2026-10-07, inside the committed `start_date` (2026-10-01) and `end_date` (2026-11-17), so no DAG edit is needed |
| #4 pause/unpause print the old status | one sentence in the README: they print the status from before the change, `airflow dags details` shows the current one |
| #6 `podman machine list` shows 2 GiB | one sentence: the VM really has about 7.6 GiB, `podman machine ssh free -m` shows it |
| #6 dashboard with empty marts | `dashboards/setup.py` now asks Metabase whether `mart_sales_day_branch_channel` exists before creating cards, stops with "run the backfill first" and exits 1; after each card it runs the query, names every card that errors and exits 1 at the end |

Evidence from this session:

```
# the compose form works on this machine (podman-compose 1.6.0, project jff)
podman compose exec -T airflow-scheduler airflow version
3.3.2            exit 0

# one day, then the quick-start range, through the new script
python tools/run_backfill.py --from-date 2026-11-16 --to-date 2026-11-16 --interval 3
unpause jff_daily / backfill 2026-11-16 .. 2026-11-16 (1 runs)
nothing to run: 1 dates already have a successful run (Airflow reuses it)
pause jff_daily                 exit 0

python tools/run_backfill.py --from-date 2026-10-01 --to-date 2026-10-07 --interval 3
unpause jff_daily / backfill 2026-10-01 .. 2026-10-07 (7 runs)
nothing to run: 7 dates already have a successful run (Airflow reuses it)
pause jff_daily                 exit 0

# gen_env picks the host port and writes LF
python tools/gen_env.py --out %TEMP%\env-check
port      POSTGRES_HOST_PORT=5433 (5432 is already in use on the host)
wrote C:\Users\acer-\AppData\Local\Temp\opencode\t08-env-check: 12 generated, 5 copied
bytes: crlf=0, ends_with_lf=True

# the dashboard script now runs every card and says so
python dashboards/setup.py
Sales overview: http://localhost:3000/dashboard/2 (7 cards)
... five pages ...
exit 0 in 141.7 s
```

Checks (local run of every CI job):

```
ruff check .            All checks passed!
ruff format --check .   66 files already formatted
mypy                    Success: no issues found in 24 source files
pytest -q               45 passed (42 without the SeaweedFS credentials)
generator: pytest 41 passed, ruff/mypy clean
pip-audit -r pipelines/constraints.txt   No known vulnerabilities found
pip-audit -r generator/constraints.txt   No known vulnerabilities found
```

Unit tests added for the two behaviours the report needed: `tools/tests/test_gen_env.py` (LF endings,
`--postgres-port`, auto-detect on a listening 5432, refusal to overwrite) and
`dashboards/tests/test_setup.py` (mart check, per-card run, the card that errors is named, `main` stops
before the cards with "run the backfill first"). `pyproject.toml` now lists the two new test directories,
and mypy checks `tools` and `dashboards` as well (24 source files instead of 13).

CI caught one dependency that the local run hid: the `main` test read `POSTGRES_ANALYTICS_RO_PASSWORD`
from the developer's `.env` through `load_dotenv()`, which the runner does not have. The test sets it
itself now, and the whole suite was re-run from a directory without `.env` (39 passed, 3 skipped).

### The pause guarantee, after review

The first version paused in a `finally`. A focused review found three paths where that paused too
early, and a second pass found two more in the same code; all five are fixed and covered by tests:

| Path | Before | Now |
|---|---|---|
| One run fails while another is still running | the loop returned on the first `failed`, and the `finally` paused a live backfill | the loop continues until every run it created is terminal; the failure decides the exit code, not the moment |
| `list-runs` itself fails mid-poll | `SystemExit` from inside the loop, `finally` paused a live backfill | the pause is skipped and the script says the DAG is left unpaused |
| A range that already succeeded | an old successful run counted, so it exited 0 before the new runs had run | the run ids are snapshotted before `backfill create`; only the new runs are waited for, and when Airflow reuses the old ones the script says "nothing to run" |
| The budget runs out while a run is still going | paused anyway, stopping it | the DAG is left unpaused with the run states, exit 1 |
| A catchup run starts between the unpause and the backfill | it was not a new run, so it was ignored and paused | live runs for the range dates are added to the wait set |

`tools/tests/test_run_backfill.py` (8 tests) proves the ordering: the wait keeps polling after a
failure and while a run is `running`; `main` pauses only as its last command; a poll failure and an
exhausted budget leave the DAG unpaused; a live catchup run is waited for even when the backfill
created nothing new; a reused range is reported without waiting; the task-state table is parsed. Live
evidence for the waiting path itself is not reproduced on the demo stack, because every date in its
window already has a successful run; the run above shows the reuse message instead.

Not verified: the quick start on a **fresh clone**. When a `catchup=True` DAG is unpaused, the scheduler
can also queue runs for later dates inside `[start_date, end_date]`; with `max_active_runs=1` a date with
no manifest holds the slot until its sensor times out. The script snapshots the run ids right after
`backfill create` and waits only for those, so a later date cannot be mistaken for one of the seven, but
the ordering in a brand-new project was not re-tested. If it happens, the script reports the run states
and the failing tasks when the budget runs out; it never pauses early.

One limit of the LF guard: the test now writes its `.env.example` with CRLF bytes, so the assertion bites
on Linux CI as well, but the real failure the tester hit (an editor or `Set-Content -NoNewline` joining
the lines) can only be reproduced on Windows; that part is documented in the README, not tested.

## README re-test follow-up (2026-11-27)

The re-test in `C:\dev\jff-readme-test-report.md` (section 5) found **no blockers**: the six steps ran
with nothing beyond `-p jff-readme`, and left three non-blocking notes. Four changes close them.

| Note | Change |
|---|---|
| #1 the README never says `compose.yaml` sets `name: jff` | a sentence now states the default project is `jff` and the containers are `jff_<service>_1`; a second clone or a test stack needs `-p <name>` on every `podman compose` command and `--project <name>` for `tools/run_backfill.py` |
| #2 a catchup run for 2026-10-08 stays `up_for_reschedule` and blocks the runs after it | a sentence now says the quick start leaves the DAG paused, a new day goes through `tools/run_backfill.py` or `docs/demo-script.md`, and unpausing with `catchup=True` creates a run for a day with no data whose `wait_manifest` waits up to two hours while `max_active_runs=1` blocks everything behind it |
| #3 `airflow dags pause` / `unpause` print the status from before the change | already documented in the previous round; no change |
| the scheduler and dag-processor never show `(healthy)` | a sentence now says they have no healthcheck; their health is `Up` plus a DAG run that advances |
| `setup.py` should say what it did | it now ends with `"<N> cards checked, <M> returned rows, <K> failed"` and still exits 1 when a card errored |

`verify_card` returns `(row count, error)` and `setup_pages` returns a `CardReport` (checked, with rows,
problems), which the tests assert. The live run on the restarted stack ended with:

```
17 cards checked, 17 returned rows, 0 failed
```

No measured number changed in this round.

Not verified: the re-test after these fixes; Ivan runs it.

## Numbers and their sources

Every number in the README and in the conclusion points at one of: `docs/pipeline-design.md` section 14
(window), `docs/verification/T03-dbt.md` (defects), T04 (backfill and memory), T05 (publish, idempotence),
T06 (marts, cards, single-run cost), T07 (clean-room, scans, CI). No figure was estimated for these two
documents.
