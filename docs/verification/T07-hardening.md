opencode-go/deepseek-v4.1-flash

# T07 verification: clean-room run, hardening, CI

Task: `tasks/T07-hardening-and-clean-room.md`. Branch `task/T07-hardening`. Date 2026-11-23.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Two stacks never ran at the same time: the original stack was stopped with `podman compose down` (no
`-v`) before the clean-room started, and `podman ps -a --filter name=jff` was empty at that point.

## Deliverables

| Path | What it is |
|---|---|
| `tools/gen_env.py` | Creates `.env` from `.env.example` with fresh random secrets, standard library only, refuses to overwrite, prints names only |
| `pipelines/constraints.txt` | Every pin for the pipeline test environment (runtime libraries at the container versions, tools at the host versions) |
| `requirements-dev.txt` | Now only names, constrained by `pipelines/constraints.txt` |
| `generator/constraints-dev.txt` | Pins for the generator's test and lint tools, which used to float |
| `.github/workflows/ci.yml` | Two jobs, ubuntu-24.04 and Python 3.12: pipelines and generator |
| `compose.yaml` | `security_opt: ["no-new-privileges:true"]` on all nine services |
| `docs/security.md` | What is protected, what is not, and the two scans |
| `docs/demo-script.md`, `README.md`, `AGENTS.md` | The demo storyline, the one-day procedure, and the supported test commands per environment |

## 1. Clean-room

The clone was taken from the local repository (`git clone "D:\...\just-fast-food" C:\Users\acer-\jff-clean-room`)
because this branch is not pushed; the remote is
`https://github.com/ivansurachman/just-fast-food-end-to-end-sales-analytics-pipeline.git`. The path has
no spaces, as the task requires, and the working tree started clean at `0a19d40`.

```
podman compose down
podman ps -a --filter "name=jff" --format "{{.Names}} {{.Status}}"   -> (empty)
podman volume ls --format "{{.Name}}" | grep '^jff'                  -> jff_pgdata, jff_seaweedfs_data, jff_jff_duckdb
```

Memory, `podman machine ssh free -m`:

| Moment | total | used | free | available | swap used |
|---|---|---|---|---|---|
| Original stack up | 7822 | 3079 | 2031 | **4742** | 64 |
| After `down` | 7822 | 706 | 4446 | **7116** | 2 |
| Clean-room starting | 7822 | 2945 | 1739 | **4877** | 2 |
| Clean-room running | 7822 | 2992 | 1646 | **4830** | 2 |
| Clean-room with 7 days loaded | 7822 | 3843 | 846 | **3979** | 2 |

`python tools/gen_env.py` (the `python` on PATH is 3.15.1; the script needs nothing else):

```
wrote .env: 12 generated, 6 copied
```

`podman compose -p jff-clean build --no-cache`: **3.8 minutes**, exit 0, `Successfully tagged
localhost/jff-airflow:3.3.2`.

`podman compose -p jff-clean up -d`: healthy after **1.8 minutes** (`jff-clean_postgres_1`,
`jff-clean_seaweedfs_1`, `jff-clean_airflow-api-server_1`, `jff-clean_metabase_1` all `(healthy)`;
scheduler and dag-processor have no healthcheck in this stack).

```
podman exec jff-clean_airflow-scheduler_1 /opt/venvs/jff/bin/jff-gen generate \
    --start 2026-10-03 --end 2026-10-09 --scale 0.02 --out s3://jff-raw --s3-endpoint http://seaweedfs:8333
2026-10-03 ... 2026-10-09, 8.6 s, 2337 to 2579 orders per day
```

First DAG attempt, `airflow backfill create --dag-id jff_daily --from-date 2026-10-03 --to-date 2026-10-09`:
**all seven runs failed** in `ingest_bronze`:

```
IngestError: cannot copy s3://jff-raw/dimensions/branches.csv to
s3://jff-lake/bronze/dimensions/branches.parquet: HTTP GET error reading
's3://jff-raw/dimensions/branches.csv' in region 'us-east-1' (HTTP 404 Not Found)
```

The dimensions had never been generated. Two more findings came out of the same attempt:

- Unpausing a `catchup=True` DAG whose `start_date` is 2026-10-01 schedules a run for every day up to
  `end_date`, not only the days of the backfill: a `scheduled__2026-10-01` run appeared, its
  `wait_manifest` sat `up_for_reschedule`, and with `max_active_runs=1` it blocked the backfill. It was
  marked `failed` through the REST API (`PATCH .../dagRuns/{run_id}` with `{"state":"failed"}`).
- The DAG boundary has to match the data. `start_date` was set to 2026-10-03 and `end_date` to
  2026-10-09 in the clone, the parser reported no import errors, and the second backfill
  (`--reprocess-behavior failed`) produced:

```
state=success runs=7
state=failed  runs=1     (the discarded scheduled 2026-10-01 run)
backfill__2026-10-09 start 08:49:37 end 08:53:07     (3.5 minutes for the seven runs)
```

Dashboard through the API (`python dashboards/setup.py` from the clone created the connection and the
five pages, then `POST /api/card/{id}/query`):

```
Sales overview: http://localhost:3000/dashboard/2 (7 cards)
Channel and branch: http://localhost:3000/dashboard/3 (3 cards)
Operations: http://localhost:3000/dashboard/4 (3 cards)
Menu: http://localhost:3000/dashboard/5 (2 cards)
Promo: http://localhost:3000/dashboard/6 (2 cards)

card=Net sales per day rows=8
  2026-10-02 108000
  2026-10-03 164771850
  2026-10-04 149385250
  2026-10-05 136180400
  2026-10-06 138624400
  2026-10-07 140221150
  2026-10-08 141440000
  2026-10-09 153440600
```

(2026-10-02 carries a late order that arrived in the 10-03 file, which is the documented behaviour.)

Container memory of the clean stack (`podman stats --no-stream`):

```
jff-clean_postgres_1          193.8MB / 629.1MB  30.80%
jff-clean_seaweedfs_1         114.2MB / 629.1MB  18.15%
jff-clean_metabase_1          1.506GB / 1.678GB  89.78%
jff-clean_airflow-api-server_1 321.1MB / 629.1MB 51.03%
jff-clean_airflow-scheduler_1 1.25GB / 1.783GB   70.14%
jff-clean_airflow-dag-processor_1 207MB / 524.3MB 39.47%
```

Verdict: **pass**, with four manual steps beyond the README (see the last section).

### Manual steps the README did not state

1. **Host port.** `POSTGRES_HOST_PORT` must be changed from 5432 to 5433 when a native PostgreSQL holds
   5432 (verified: `Get-NetTCPConnection -LocalPort 5432` showed a listener, pid 6912).
2. **Dimensions.** `jff-gen dim all --out s3://jff-raw --s3-endpoint http://seaweedfs:8333` has to run
   once before the first pipeline run; the README only generated them into a local folder.
3. **DAG boundary.** `start_date` and `end_date` have to cover exactly the generated days; otherwise
   catchup schedules runs for days without data whose `wait_manifest` waits two hours and, with
   `max_active_runs=1`, blocks the backfill.
4. **Python first.** The very first step needs a Python on PATH (`python tools/gen_env.py`); the README
   started at `pip`.

All four are now in `README.md` (the "First run from a fresh clone" section). `AGENTS.md` carries the
supported test commands per environment, not the clean-room steps.

### Teardown and restore

Before deleting anything, Ivan asked for three checks. The volumes of the two projects are separate and
none shares a name, the compose `volumes:` block has no explicit `name:` key, and this file carries the
evidence above:

```
podman volume ls --format "{{.Name}}" | grep '^jff'
jff_pgdata
jff_seaweedfs_data
jff_jff_duckdb
jff-clean_pgdata
jff-clean_seaweedfs_data
jff-clean_jff_duckdb

podman compose -p jff-clean config --volumes     -> podman-compose 1.6.0: usage error, the flag does not exist
grep -n "name:" compose.yaml (volumes block, lines 253-257)
253: volumes:
254:   pgdata:
255:   seaweedfs_data:
257:   jff_duckdb:                                   (no explicit name, the project prefix applies)
```

Only the clean project was removed:

```
podman compose -p jff-clean down -v
jff-clean_pgdata
jff-clean_seaweedfs_data
jff-clean_jff_duckdb
jff-clean_default
exit 0

podman volume ls --format "{{.Name}}" | grep '^jff'
jff_pgdata
jff_seaweedfs_data
jff_jff_duckdb                                    (the three originals are intact)

podman ps -a --filter "name=jff-clean"            -> (empty)
```

The original stack came back on its own volumes:

```
podman compose up -d
podman ps
jff_postgres_1             Up About a minute (healthy)
jff_seaweedfs_1            Up About a minute (healthy)
jff_metabase_1             Up About a minute (healthy)
jff_airflow-api-server_1   Up 49 seconds (healthy)
jff_airflow-scheduler_1    Up 29 seconds
jff_airflow-dag-processor_1 Up 11 seconds
airflow /api/v2/monitor/health -> metadatabase healthy

card=Net sales per day id=40 rows=48
first=2026-10-01 711114250
last =2026-11-17 730360400

free -m after restoring: total 7822, used 3127, available 4695
```

Verdict for the clean-room and the teardown: **pass**.


## 2. `check_secrets.py` on the clone

```
python tools/check_secrets.py
clean  POSTGRES_PASSWORD
clean  POSTGRES_AIRFLOW_PASSWORD
clean  POSTGRES_METABASE_PASSWORD
clean  POSTGRES_ANALYTICS_PASSWORD
clean  POSTGRES_ANALYTICS_RO_PASSWORD
clean  S3_ACCESS_KEY
clean  S3_SECRET_KEY
clean  AIRFLOW_ADMIN_PASSWORD
clean  AIRFLOW_FERNET_KEY
clean  AIRFLOW_API_SECRET_KEY
clean  AIRFLOW_API_AUTH_JWT_SECRET
clean  MB_ADMIN_PASSWORD
skipped (name does not look like a credential): AWS_DEFAULT_REGION, AIRFLOW_ADMIN_EMAIL, MB_ADMIN_EMAIL, MB_SITE_NAME
secrets in git: NONE
exit 0
```

Verdict: **pass**.

## 3. Dependency scan

`pip-audit` 2.10.1 (released 2026-06-10) in a throwaway virtualenv, 2026-11-23.

| Set | Command | Packages | Vulnerabilities |
|---|---|---|---|
| Pipelines and host tools | `pip-audit --path .venv/Lib/site-packages` | 25 | **0** |
| Generator | `pip-audit --path generator/.venv/Lib/site-packages` | 91 | **0** |
| dbt virtualenv | `pip-audit -r infra/airflow/dbt-constraints.txt` | 56 | **0** |
| Airflow image extras | `pip-audit -r requirements.txt` | 1 | **0** |
| Airflow base image | `podman run --rm jff-airflow:3.3.2 ... pip-audit -r /tmp/freeze.txt --no-deps --disable-pip` | 443 | **108 in 23 packages** |

Severity of the 108, from the OSV database: **4 CRITICAL, 48 HIGH, 44 MODERATE, 10 LOW**, plus 2 that
publish only a CVSS vector. Worst packages: `virtualenv` 21.7.9 (24), `aiohttp` 3.14.3 (17), `filelock`
3.32.6 (13), `authlib` 1.8.0 (8, one CRITICAL), `tornado` 6.5.8 (7), `gitpython` 3.1.62 (6), `certifi`
2026.7.22 (2 CRITICAL), `uv` 0.12.10 (2, one CRITICAL). Every one has a fixed release.

No direct dependency of this project has a finding, so there was nothing to upgrade under the rule ("fix
only direct dependencies where a fixed version exists and is older than 14 days"). The image packages are
the pinned base image; T07 forbids changing image versions, so they are recorded in `docs/security.md`
for Ivan to decide.

Verdict: **pass** (no unfixed CRITICAL in a direct dependency).

## 4. Image scan

`aquasec/trivy:0.76.2` (released 2026-11-05), reading the rootful Podman socket
(`-v /run/podman/podman.sock:/run/podman/podman.sock:ro -e DOCKER_HOST=unix:///run/podman/podman.sock`),
HIGH and CRITICAL only, 2026-11-23.

```
podman run --rm -v /run/podman/podman.sock:/run/podman/podman.sock:ro \
    -e DOCKER_HOST=unix:///run/podman/podman.sock docker.io/aquasec/trivy:0.76.2 \
    image --quiet --severity HIGH,CRITICAL --format json <image>

postgres:18.4                  HIGH=216 CRITICAL=14  packages=42
chrislusf/seaweedfs:4.52       HIGH=1   CRITICAL=0   packages=1
metabase:v0.65.3               HIGH=1   CRITICAL=0   packages=1
jff-airflow:3.3.2              HIGH=342 CRITICAL=23  packages=79
```

CRITICAL detail: postgres -> `perl`, `perl-base`, `perl-modules-5.40`, `libperl5.40` (3 each), `stdlib`,
`libxml2`; airflow -> `perl*` (12), `certifi` (2), `uv` (2), `authlib`, `libsqlite3-0`, `libbrotli1`,
`zlib1g`, `openssh-client`, `libxml2`, `sqlite3`. Nothing was changed, as the task requires; the
candidate next tags are in `docs/security.md`.

Verdict: **pass** (scanned and recorded; no image changed).

## 5. CI on GitHub

Ivan pushed `task/T07-hardening` and merged it; both runs are green. Numbers read from the GitHub
Actions API on 2026-11-24:

```
runs (workflow "ci"):
  45314833633  task/T07-hardening  sha 124f5dd  push  completed  success
  45316653703  main                sha 124f5dd  push  completed  success

run 45314833633, jobs:
  generator             success   88 s   Install, Tests, Lint, Format, Types  (all success)
  pipelines and dags    success   37 s   Install, Lint, Format, Types, Tests  (all success)
```

Run URL: <https://github.com/ivansurachman/just-fast-food-end-to-end-sales-analytics-pipeline/actions/runs/45314833633>

Verdict: **pass**.

## 6. `no-new-privileges`

`podman compose -p jff config` renders `security_opt: [no-new-privileges:true]` for every service.
`podman compose up -d` recreated the containers and `podman inspect` reads it back:

```
jff_postgres_1              [no-new-privileges] running healthy
jff_seaweedfs_1             [no-new-privileges] running healthy
jff_airflow-scheduler_1     [no-new-privileges] running -
jff_airflow-api-server_1    [no-new-privileges] running healthy
jff_airflow-dag-processor_1 [no-new-privileges] running -
jff_metabase_1              [no-new-privileges] running healthy
```

The three one-shot services (`postgres-ro`, `seaweedfs-init`, `airflow-init`) carry it as well in the
compose file and exit normally. `podman-compose` 1.6.0 accepts the key; it did not reject it.

Verdict: **pass**.

## 7. Demo-safe way to run one day

2026-11-17 was generated inside the scheduler
(`11,291 orders, 27,546 items, 95 changes`, 3.7 s) and then triggered three ways:

| Attempt | Conditions | Result |
|---|---|---|
| `airflow dags trigger --logical-date 2026-11-16` (T06, 2026-11-23) | day beyond `end_date` 2026-11-15, DAG unpaused | run finalised `success` in 28 ms with **0 task instances** |
| `POST /api/v2/dags/jff_daily/dagRuns` with `logical_date: 2026-11-17` (the UI button) | day beyond `end_date` 2026-11-16, DAG paused | run created `queued`, **0 task instances**, still queued after three minutes |
| same API trigger, after `end_date` was set to 2026-11-17 and the DAG was unpaused | inside the window, unpaused | **7 task instances**, run `success` in about 40 s |

```
15.12.35 state=running tis=7 [success,running,,,success,success,]
15.13.05 state=running tis=7 [success,success,success,,success,success,]
15.13.15 state=success tis=7 [success,success,success,success,success,success,success]
```

The procedure in `README.md` and `docs/demo-script.md` is: generate, extend `end_date`, unpause, then
trigger (UI or `airflow backfill create`), and both documents say which orders fail silently.

Verdict: **pass**.

## Notes and limits

- **The demo window is now 48 days** (2026-10-01 .. 2026-11-17) because this task generates one more day
  to test the procedure. Section 14 of `docs/pipeline-design.md` carries the counts (49 lake dates,
  5760 branch-days, 196 objects, 574,838 orders); the dashboard still shows 48 days.
- **The clean-room build retags `jff-airflow:3.3.2`**: the image name is not project-scoped, so building
  the clone replaced the local image with an identical rebuild of the same Containerfile. No behaviour
  changed, and the original stack came back on that image.
- **Two runs of the clean-room were needed** because of the missing dimensions; the failed attempt is
  reported above rather than hidden, and the second one is the evidence.
- Not run: nothing. Item 4 deliberately moved no image tag; the scans are recorded and the decision is Ivan's.

## 8. Counts behind section 14 of the design

`docs/pipeline-design.md` section 14 carries the window numbers. They were measured again on the
restored stack after 2026-11-17 had been processed, with the same script the earlier tasks used
(DuckDB read-only, boto3 listing of `jff-lake`, and `psql` as `analytics`):

```
podman exec jff_airflow-scheduler_1 python /tmp/t07_numbers.py
orders           574838
order lines      1399537
fact_branch_day  5760
sales mart days  49
max order date   2026-11-17
lake objects     196 bytes 29136488
lake dates       49 2026-09-30 2026-11-17
per table        {'gold/fact_order': 49, 'gold/fact_order_item': 49, 'silver/silver_order_items': 49, 'silver/silver_orders': 49}

psql -U analytics -d analytics -tAc "select count(*), count(distinct order_date), max(order_date)
                                      from mart_sales_day_branch_channel;
                                      select count(*) from mart_branch_coverage"
27410|49|2026-11-17
5760
```

The dashboard shows 48 of the 49 dates because every card filters `order_date >= date '2026-10-01'`;
2026-09-30 is the late-arrival partition. 5760 = 48 x 120 and 196 = 49 x 4.

