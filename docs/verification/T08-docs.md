opencode-go/deepseek-v4.1-flash

# T08 verification: README, architecture diagram, conclusion

Task: `tasks/T08-readme-and-docs.md`. Branch `task/T08-docs` (from `main` = `124f5dd`). Date 2026-11-24.

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

**Not run by me**: the task gives this check to Ivan. The runbook he needs is "Run it on Windows with
Podman" in the README, the same six steps that passed on 2026-11-23 (T07 section 1). Every place he gets
stuck becomes a documentation fix here.

### 2. `git grep -n "verify"` in `docs/` and `README.md`

```
docs/cli-guide.md:108:| Clean data to verify metrics | add `--clean` |
docs/verification/T04-marts.md:289:INFO app-db.setup :: Verifying postgres Database Connection ...
```

Neither is an unverified claim: the first is a recipe row where "verify" is the verb, the second is a
Metabase log line quoted as evidence. No unverified claim remains; the earlier live ones were resolved in
this task:

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
checked=57 missing=0
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

## Numbers and their sources

Every number in the README and in the conclusion points at one of: `docs/pipeline-design.md` section 14
(window), `docs/verification/T03-dbt.md` (defects), T04 (backfill and memory), T05 (publish, idempotence),
T06 (marts, cards, single-run cost), T07 (clean-room, scans, CI). No figure was estimated for these two
documents.
