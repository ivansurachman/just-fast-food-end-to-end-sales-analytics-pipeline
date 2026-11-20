# T02 verification: bronze ingest and DAG skeleton

Task: `tasks/T02-ingest-bronze-dag.md`. Branch `task/T02-bronze`. Started 2026-11-20.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Only commands that were run are recorded. Anything not run is written as "not run".

## Step 0 (T01 follow-ups)

### 1. Ports on loopback

`compose.yaml` publishes every host port on loopback only:
`127.0.0.1:5432:5432` (postgres), `127.0.0.1:8333:8333` (seaweedfs),
`127.0.0.1:8080:8080` (airflow-api-server). Applied with `podman compose down` then
`podman compose up -d`, exit 0, stack settled healthy in 15.1 s.

```
podman ps --format "{{.Names}} {{.Ports}}"
jff_postgres_1 127.0.0.1:5432->5432/tcp
jff_seaweedfs_1 127.0.0.1:8333->8333/tcp, 7333/tcp, 8080/tcp, 8888/tcp, 9333/tcp, 18080/tcp, 18888/tcp, 19333/tcp
jff_airflow-api-server_1 127.0.0.1:8080->8080/tcp
jff_airflow-scheduler_1 8080/tcp
jff_airflow-dag-processor_1 8080/tcp
```

(Unmapped container ports such as `8080/tcp` on the scheduler are internal only; nothing is
published for them.)

The host listeners agree for the two S3/Airflow ports:

```
Get-NetTCPConnection -State Listen -LocalPort 5432,8333,8080 | Select LocalAddress,LocalPort
LocalAddress LocalPort
------------ ---------
::                5432
127.0.0.1         8333
127.0.0.1         8080
0.0.0.0           5432
```

The generator still writes and reads from the host through loopback (`boto3` against
`http://localhost:8333`, path-style):

```
buckets ['jff-lake', 'jff-raw']
raw_objects 8
```

and the Airflow API answers on loopback: `curl http://127.0.0.1:8080/api/v2/monitor/health` -> 200.

Verdict: **pass for the ports this stack actually serves**. Finding: host port 5432 is answered by
a **native Windows PostgreSQL 18 service** (`postgresql-x64-18`, pid 6912, listening on
`0.0.0.0:5432` and `[::]:5432`), which shadows the container binding. Proof: connecting to
`127.0.0.1:5432` as the container-only role `airflow` is rejected with `FATAL: password
authentication failed`, while `podman exec jff_postgres_1 psql -U airflow -d airflow` succeeds.
Nothing in the pipeline uses host port 5432 (Airflow and, later, Metabase reach Postgres over the
compose network as `postgres:5432`), and T01 never used it either. A host-side `psql` or GUI client
would hit the native service instead, so if that is ever needed the host port has to move (for
example `127.0.0.1:5433:5432`) or the native service has to be stopped; both are outside this task
and are left to Ivan.

### 2. One build file

`compose.yaml` now builds with `dockerfile: Containerfile`, and `infra/airflow/Dockerfile` is deleted,
so the two files cannot drift.

Only one build file exists and git tracks only that one:

```
Test-Path .\Containerfile                 -> True
Test-Path .\infra\airflow\Dockerfile      -> False
git ls-files | findstr /i "dockerfile containerfile"
Containerfile
```

`podman compose config` resolves the key in both providers' view of the project:

```
context: D:\File Campuran\Certification\Dibimbing\Final Project\files\just-fast-food
dockerfile: Containerfile
```

Build with the permanent provider, exit code 0:

```
podman compose build
build_exit=0
```

`podman-compose --verbose build` shows the command it builds, and it succeeds without `-f` because
podman finds the same file in the context root (this is the podman-compose 1.6.0 behaviour recorded
in `docs/verification/T01-infra.md`, finding 1):

```
INFO:podman_compose:podman build -t jff-airflow:3.3.2 D:\File Campuran\Certification\Dibimbing\Final Project\files\just-fast-food
Successfully tagged localhost/jff-airflow:3.3.2
```

Because `infra/airflow/Dockerfile` no longer exists, a successful build can only have come from the
root `Containerfile`, which podman looks for by default. The build command above, not the image ID,
is the evidence for the path: the first build after the switch reused every cached layer and kept
image `89ab7fae503b`, and the build after a comment change in
`infra/airflow/install-generator.sh` produced a new image `774c152e19d1`.

The image still carries the build output:

```
podman run --rm --entrypoint /bin/ls jff-airflow:3.3.2 /opt/jff
init-db.sh
install-generator.sh
wait-for-db.sh
```

Bring-up with the permanent provider settles healthy (`podman compose down` then `podman compose up -d`,
so every container runs the image built above; see the note after this block):

```
podman compose up -d
up_exit=0
settled_seconds=75.8
jff_postgres_1	Up About a minute (healthy)
jff_seaweedfs_1	Up About a minute (healthy)
jff_seaweedfs-init_1	Exited (0) 45 seconds ago
jff_airflow-init_1	Exited (0) 4 seconds ago
jff_airflow-api-server_1	Up 41 seconds (healthy)
jff_airflow-scheduler_1	Up 29 seconds
jff_airflow-dag-processor_1	Up 15 seconds
```

`podman inspect jff_airflow-api-server_1 --format "{{.ImageName}} {{.Image}}"`:

```
localhost/jff-airflow:3.3.2 774c152e19d188fd434ab7edca5f1affa5a4d3e475404ff8a6e1858634e743e1
```

The S3 objects from T01 are still there after the `down`/`up` cycle (8 objects, same sizes):

```
objects 8
_manifests/dt=2026-10-05/manifest.json 506
dimensions/branches.csv 11676
dimensions/channels.csv 261
dimensions/menu_items.csv 1011
dimensions/promos.csv 746
order_changes/dt=2026-10-05/order_changes.csv 1861
order_items/dt=2026-10-05/order_items.csv 230269
orders/dt=2026-10-05/orders.csv 236131
```

Note for later tasks: `podman compose up -d` does **not** recreate the long-running services when only
the image tag moved. After `podman compose build` with a changed image, the api-server still ran the
previous image (`89ab7fae503b`) until `podman compose down` followed by `podman compose up -d`.
This will matter as soon as the image gains DuckDB extensions.

The second provider reads the same file:

```
docker-compose -f compose.yaml config --quiet
dc_config_exit=0
docker-compose -f compose.yaml config | grep dockerfile
      dockerfile: Containerfile
```

Verdict: **pass**. `podman compose build` exit 0, `podman compose up -d` exit 0 with the stack
healthy after 76.1 s, `docker-compose -f compose.yaml config --quiet` exit 0, one build file
(`Containerfile`) in the repository.

### 3. Quote paths

Applied in this step: every command recorded above that contains the repository path is quoted, and
`docker-compose -f compose.yaml config` was run from the repo root with relative file names. No script
was added in this step.

### 4. Airflow 3.3.2 API verified inside the scheduler

Run in the running scheduler container (`/opt/venvs/jff` is not on that path, on purpose: the DAG uses
the Airflow interpreter). First attempt failed on quoting, not on Airflow:

```
podman exec jff_airflow-scheduler_1 /bin/bash -lc 'python - <<PY ... PY'
  File "<stdin>", line 7
    print(m, OK, getattr(mod, __version__, "))
                                           ^
SyntaxError: unterminated string literal (detected at line 7)
```

Hypothesis: the nested quotes of the here-document were mangled by the PowerShell -> podman -> bash
chain, so the Python source arrived truncated. Change: pipe the script through standard input instead
of a here-document. Result below.

```
@'...'@ | podman exec -i jff_airflow-scheduler_1 python -
python 3.12.14
airflow.sdk DAG dag task BaseOperator OK
standard provider PythonOperator/PythonSensor/EmptyOperator OK
airflow 3.3.2
```

The same probe before the fix reported `duckdb MISSING` and `pytest MISSING` (both are added to the
image later in this task; the DAG itself only needs Airflow, boto3 and DuckDB from `pipelines/`).

### 5. Written up

Sections 1 to 4 above are the result of steps 1 to 3 (and 4) of the T02 spec.

### Environment observations for later steps

- The repo path contains spaces, so every command quoted it with double quotes on the PowerShell side.
- Nested quoting through `podman exec ... bash -lc '...'` is unreliable here. Scripts are piped through
  standard input or run from files instead.

## Deliverables

| Path | What it is |
|---|---|
| `dags/jff_daily.py` | DAG `jff_daily`: daily, `catchup=True`, `max_active_runs=1`, `wait_manifest` (PythonSensor, reschedule) -> `ingest_bronze` (pool `duckdb_writer`) -> `check_bronze` -> placeholders `dbt_run`, `dbt_test`, `load_marts` |
| `pipelines/ingest_bronze.py` | DuckDB over httpfs: CSV to Parquet, `all_varchar`, `memory_limit='1GB'`, `threads=2`; CLI `--ds`, `--dimensions`, `--endpoint`, `--raw-root`, `--lake-root` |
| `pipelines/check_bronze.py` | CSV rows, Parquet rows and manifest rows must agree; CLI `--ds` |
| `pipelines/manifest.py` | boto3 reader for `_manifests/dt=<ds>/manifest.json` (path-style, credentials from `S3_*` or `AWS_*`) |
| `pipelines/tests/` | 10 tests: local tree, repeatability, failure cases, and a SeaweedFS round trip that skips when the endpoint is unreachable |
| `requirements.txt`, `requirements-dev.txt` | DuckDB for the image; host tooling for tests and linters |
| `infra/airflow/install-duckdb.sh` | Installs `requirements.txt` as the airflow user and `INSTALL`s `httpfs` + `parquet` at build time |
| `pyproject.toml` (root) | ruff, mypy and pytest settings for `dags/` and `pipelines/` |

DuckDB is in the image and its extensions are pre-installed:

```
podman run --rm --entrypoint python jff-airflow:3.3.2 -c 'import duckdb;print(duckdb.__version__)'
1.5.6
podman run --rm --entrypoint /bin/ls jff-airflow:3.3.2 /home/airflow/.duckdb/extensions/v1.5.6/linux_amd64
httpfs.duckdb_extension
httpfs.duckdb_extension.info
parquet.duckdb_extension
parquet.duckdb_extension.info
```

The DAG is registered with no import errors, and the pool exists:

```
airflow dags list
jff_daily | /opt/airflow/dags/jff_daily.py | jff | True | dags-folder | None
airflow dags list-import-errors
No data found
airflow pools list
duckdb_writer | 1 | DuckDB single writer: one task that opens DuckDB at a time
```

`is_paused: True` is Airflow's default for a new DAG; the runs below were created with
`airflow backfill create` after `airflow dags unpause`, and the DAG is paused again afterwards.

## Deliverable defects found while running (fixed in this task)

### SeaweedFS ran out of volumes for the second bucket

First S3 write to `jff-lake` failed with HTTP 500. The DuckDB error alone is not enough to explain it,
so the server log was read (`podman logs jff_seaweedfs_1`):

```
E1120 09:10:03 upload_chunked.go:283 chunked upload failed: assign volume: ... failed to find
writable volumes for collection:jff-lake ... No writable volumes and no free volumes left
```

and the topology confirmed `hdd(volume:8/8 active:8 free:0)`: the default cap of 8 volumes was used up
by the empty-collection volumes plus the `jff-raw` volume, so a new collection had nowhere to write.
Change: `-volume.max=0` in `infra/seaweedfs/entrypoint.sh` (0 = as many as the free disk allows).
After `podman restart jff_seaweedfs_1`:

```
Topology volumeSizeLimit:30720 MB hdd(volume:8/30 active:8 free:22 remote:0)
```

The volume files are sparse (`du -sh /data` = 432 KiB with 8 volumes), so this costs no disk.
Boto3 had already written to `jff-raw`, which is why T01 did not hit this.

### Airflow 3 task tokens failed signature validation

With the stack up, scheduler-driven runs died after four seconds:

```
Process exited exit_code=<Negsignal.SIGKILL: -9> ... signal_sent=SIGKILL
```

The api-server log named the cause:

```
Failed to validate JWT  [airflow.api_fastapi.execution_api.security]
JWT reissue middleware failed to refresh token  error='Signature verification failed'
PATCH /execution/task-instances/<id>/run  status_code=403
```

Airflow 3 signs task tokens with `[api_auth] jwt_secret`; when it is unset, `get_signing_key()` in
`airflow/api_fastapi/auth/tokens.py` generates a random key **per process**. Evidence:

```
podman exec jff_airflow-api-server_1 airflow config get-value api_auth jwt_secret
lJnW/2/Qdso7kJ1Odu9mpQ==
podman exec jff_airflow-scheduler_1 airflow config get-value api_auth jwt_secret
R1VjpcegymJw8oGGiUdRUg==
```

Change: `AIRFLOW__API_AUTH__JWT_SECRET` (from `AIRFLOW_API_AUTH_JWT_SECRET` in `.env`) for every
Airflow service. After `podman compose down` + `up -d` both containers report the same value and the
runs below complete. `airflow tasks test` had worked all along because it runs the task in the same
process that signs the token.

## Acceptance

### 1. Three days, three successful runs

Generated days 2026-10-03 to 2026-10-05 at scale 0.02 (the 10-05 numbers match the T01 manifest):

```
jff-gen generate --out s3://jff-raw --s3-endpoint http://localhost:8333 --start 2026-10-03 --end 2026-10-05 --scale 0.02
2026-10-03: {'orders': 2683, 'order_items': 6665, 'order_changes': 16}
2026-10-04: {'orders': 2505, 'order_items': 6083, 'order_changes': 25}
2026-10-05: {'orders': 2201, 'order_items': 5384, 'order_changes': 22}
gen_exit=0
airflow backfill create --dag-id jff_daily --from-date 2026-10-03 --to-date 2026-10-05
backfill_runs=3
airflow dags list-runs jff_daily
jff_daily | backfill__2026-10-05T00:00:00+00:00 | success | ... | 2026-11-20T09:48:12 | 2026-11-20T09:48:22
jff_daily | backfill__2026-10-04T00:00:00+00:00 | success | ... | 2026-11-20T09:48:12 | 2026-11-20T09:48:21
jff_daily | backfill__2026-10-03T00:00:00+00:00 | success | ... | 2026-11-20T09:48:12 | 2026-11-20T09:48:17
```

The runs are scheduler-driven (`LocalExecutor`), so they also prove the token fix above.

One catchup run for 2026-10-01 appeared when the DAG was unpaused (`catchup=True` from the DAG
start_date). It was set to failed and deleted through the REST API
(`PATCH`/`DELETE /api/v2/dags/jff_daily/dagRuns/...`) so that the queue holds only the acceptance runs.

Verdict: **pass**.

### 2. Re-running the same days gives byte-identical Parquet

Bronze objects and their S3 ETags (ETag = MD5 for a single-part PUT) before the re-run:

```
24ac74b6cc6d8b54169527bd17c40e46     5236 bronze/dimensions/branches.parquet
f6c4faf55f6a03b6e1d13de0083faa77     1285 bronze/dimensions/channels.parquet
bbb1520625b942c3045f2c1d2ad66477     2038 bronze/dimensions/menu_items.parquet
bc16c2d183496ab8f74cefbbcd6e9784     2286 bronze/dimensions/promos.parquet
4997074699ffab7cee37b24c9f08ae90     2287 bronze/order_changes/source_file_date=2026-10-03/order_changes.parquet
48cbd9139931143976ec6668c31773d5     2523 bronze/order_changes/source_file_date=2026-10-04/order_changes.parquet
9ea27f923c8293e749797e1b8b6c948f     2486 bronze/order_changes/source_file_date=2026-10-05/order_changes.parquet
ddacdf2e49c7a3b842a2283dcdf26cd1    38566 bronze/order_items/source_file_date=2026-10-03/order_items.parquet
14ac7fa8c0d06aac1a02db0beb95d4f0    35583 bronze/order_items/source_file_date=2026-10-04/order_items.parquet
4881240b036e0376a5b4094fadc7c903    32160 bronze/order_items/source_file_date=2026-10-05/order_items.parquet
441c7d5390d1eecd3bac4a80c0ded00c    67468 bronze/orders/source_file_date=2026-10-03/orders.parquet
c9642eae46f11860058ab4789ded16a8    63795 bronze/orders/source_file_date=2026-10-04/orders.parquet
ca6c4a2907155bdb3fb46f8bab3dfeff    56291 bronze/orders/source_file_date=2026-10-05/orders.parquet
objects=13
```

Re-ran the same three dates with the same generator output:

```
airflow backfill create --dag-id jff_daily --from-date 2026-10-03 --to-date 2026-10-05 --reprocess-behavior completed
new_runs=3
jff_daily | backfill__2026-10-05T00:00:00+00:00 | success
jff_daily | backfill__2026-10-04T00:00:00+00:00 | success
jff_daily | backfill__2026-10-03T00:00:00+00:00 | success
```

The listing after the re-run is identical, line for line, including every ETag:

```
24ac74b6cc6d8b54169527bd17c40e46     5236 bronze/dimensions/branches.parquet
... (same 13 lines, same ETags and sizes)
objects=13
```

Verdict: **pass, byte-identical** (not just equal row hashes). The Parquet writer is stable here
because nothing time-dependent is written: no ingestion timestamp, and `source_file_date` comes from
the run date.

The same check exists as a test against SeaweedFS: `test_seaweedfs_roundtrip` ingests the day twice
and asserts the ETag is unchanged.

### 6. Linters and tests

```
python -m ruff --version
ruff 0.17.4
python -m ruff check .
All checks passed!
python -m ruff format --check .
43 files already formatted
python -m mypy
Success: no issues found in 9 source files
python -m pytest -q
10 passed in 12.09s
```

`pytest` ran with `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `JFF_S3_ENDPOINT` exported, so nothing was
skipped. `ruff` and `mypy` are pinned in `requirements-dev.txt`; `docs/` is excluded from `ruff`
because the slide script predates this task.

Verdict: **pass**.

### 3. `check_bronze` reconciles counts, and fails when it should

Every entity and day reconciles, from the CLI in the scheduler container:

```
python -m pipelines.check_bronze --ds 2026-10-03   (then 10-04, 10-05, 10-06)
orders: {'csv': 2683, 'parquet': 2683, 'manifest': 2683}
order_items: {'csv': 6665, 'parquet': 6665, 'manifest': 6665}
order_changes: {'csv': 16, 'parquet': 16, 'manifest': 16}
branches: {'csv': 120, 'parquet': 120}
channels: {'csv': 5, 'parquet': 5}
menu_items: {'csv': 21, 'parquet': 21}
promos: {'csv': 6, 'parquet': 6}
--
orders: {'csv': 2505, 'parquet': 2505, 'manifest': 2505}
order_items: {'csv': 6083, 'parquet': 6083, 'manifest': 6083}
order_changes: {'csv': 25, 'parquet': 25, 'manifest': 25}
--
orders: {'csv': 2201, 'parquet': 2201, 'manifest': 2201}
order_items: {'csv': 5384, 'parquet': 5384, 'manifest': 5384}
order_changes: {'csv': 22, 'parquet': 22, 'manifest': 22}
--
orders: {'csv': 2255, 'parquet': 2255, 'manifest': 2255}
order_items: {'csv': 5461, 'parquet': 5461, 'manifest': 5461}
order_changes: {'csv': 15, 'parquet': 15, 'manifest': 15}
```

(The dimension lines are identical on all four days: 120/5/21/6.)

**Failure 1, a deleted bronze object.** Deleted
`s3://jff-lake/bronze/orders/source_file_date=2026-10-06/orders.parquet`, then ran the task:

```
airflow tasks test jff_daily check_bronze 2026-10-06
[error] Task failed with exception  [task] loc=task_runner.py:1676
pipelines.check_bronze.CheckFailed: cannot read
s3://jff-lake/bronze/orders/source_file_date=2026-10-06/orders.parquet:
HTTP Error: HTTP GET error reading '...' in region 'us-east-1' (HTTP 404 Not Found)
```

Note: `airflow tasks test` exits 0 even when the task fails, so the exit code is not the evidence
here; the `Task failed with exception` line and the CheckFailed message are.

Restored by re-running the ingest task, and the check passed again with the counts above.

**Failure 2, a manifest that disagrees (whole DAG).** Bumped `rows.orders` in
`_manifests/dt=2026-10-06/manifest.json` from 2255 to 2256 (the original bytes were saved first),
then ran the DAG synchronously:

```
airflow dags test jff_daily 2026-10-06
dags_test_exit=1
pipelines.check_bronze.CheckFailed: orders 2026-10-06: csv=2255, parquet=2255, manifest=2256
```

`ingest_bronze` succeeded, `check_bronze` failed, and the rest of the graph did not run;
`dags test` exited 1. The manifest was then restored byte-for-byte and the check passed again.

Verdict: **pass**, both failures are loud and name the object and the numbers.

### 4. `wait_manifest` really waits

A run for 2026-10-06 existed before that day was generated, because unpausing the DAG let the scheduler
create a catchup run for the next interval. `wait_manifest` went to reschedule mode and polled every
30 s without holding a slot:

```
airflow tasks states-for-dag-run jff_daily scheduled__2026-10-06T00:00:00+00:00
wait_manifest | up_for_reschedule | start 2026-11-20T10:13:54 | end 2026-11-20T10:13:55
ingest_bronze | (not started)
scheduler log:
10:11:19 Poking callable: <function manifest_ready ...> run_id=scheduled__2026-10-06T00:00:00+00:00
10:11:50 Poking callable: <function manifest_ready ...>
10:12:21 Poking callable: <function manifest_ready ...>
10:12:53 Poking callable: <function manifest_ready ...>
10:13:23 Poking callable: <function manifest_ready ...>
10:13:55 Poking callable: <function manifest_ready ...>
```

Then 2026-10-06 was generated (`jff-gen generate --date 2026-10-06 --scale 0.02` -> 2255 orders,
manifest written last) and the DAG was unpaused again. The sensor proceeded on its first poke:

```
11:02:52 wait_manifest success
11:02:53 ingest_bronze success
11:02:54 check_bronze  success
11:02:55 dbt_run       success  (placeholder)
11:02:56 dbt_test      success  (placeholder)
11:02:56 load_marts    success  (placeholder)
run scheduled__2026-10-06T00:00:00+00:00: success
```

Verdict: **pass**. A day whose manifest is absent is waited for, and the run continues as soon as the
generator has written it.

### 5. Peak memory of the scheduler for a full-scale day

Day 2026-10-09 at scale 1.0 was generated (128,743 orders, 314,038 order items, 983 order changes)
and the whole DAG was run synchronously in the scheduler container while the container's memory was
sampled every ~1 s with `podman stats --no-stream`:

```
generator: {'orders': 128743, 'order_items': 314038, 'order_changes': 983}
podman exec jff_airflow-scheduler_1 airflow dags test jff_daily 2026-10-09
dag=jff_daily ds=2026-10-09 exit=0 samples=30
sample_max_mb=1555.5 sample_first_mb=1142.8 sample_last_mb=1138.7
cgroup_peak_before_mb=1565.1 cgroup_peak_after_mb=1565.1
```

Task log for the same run:

```
bronze orders 2026-10-09: 128743 rows
bronze order_items 2026-10-09: 314038 rows
bronze order_changes 2026-10-09: 983 rows
[DAG TEST] end task task_id=check_bronze
```

Against the limit in `compose.yaml` (`mem_limit: 1700m`, and the cgroup agrees:

```
cat /sys/fs/cgroup/memory.max   -> 1782579200  (1700 MiB)
cat /sys/fs/cgroup/memory.events -> oom 0, oom_kill 0
```

| Reading | MiB | Share of 1700 MiB |
|---|---|---|
| Highest `podman stats` sample during the run | 1555.5 | 91.5% |
| Container lifetime peak (`memory.peak`, unchanged by this run) | 1565.1 | 92.1% |
| Limit | 1700 | 100% |
| Headroom at the highest sample | 144.5 | 8.5% |

The full-scale day fits, with no OOM kill and no restart (`podman inspect ... .State.OOMKilled`
is false and `memory.events` shows `oom_kill 0`). The margin is thin: about 145 MiB. The design's rule
applies - if a future task is OOM-killed, lower DuckDB `threads` before touching the limit.

Caveat: `memory.peak` cannot be reset in this container (the cgroup file is read-only), so the
lifetime peak includes the earlier runs of this session. The `podman stats` samples are the reading
for this run, and the lifetime peak did not move, i.e. the ingest did not set a new record.

Verdict: **pass**, under the limit, with the margin recorded.

## Extra: SeaweedFS filer on the host

`compose.yaml` publishes the filer on `127.0.0.1:8888:8888`; `weed server` already starts it on 8888,
so no change to the entrypoint and no change to the design.

```
podman ps --format "{{.Names}} {{.Ports}}"
jff_seaweedfs_1 127.0.0.1:8333->8333/tcp, 127.0.0.1:8888->8888/tcp, ...
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8888/          -> 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8888/buckets/  -> 200
curl -s http://127.0.0.1:8888/buckets/
<a href="/buckets/jff-lake/" > jff-lake
<a href="/buckets/jff-raw/" >  jff-raw
```

Both buckets are listed, and the port is on loopback only.

## Final state

```
podman ps --format "{{.Names}} {{.Ports}}"
jff_postgres_1 127.0.0.1:5432->5432/tcp
jff_seaweedfs_1 127.0.0.1:8333->8333/tcp, 127.0.0.1:8888->8888/tcp, ...
jff_airflow-api-server_1 127.0.0.1:8080->8080/tcp
airflow dags list-runs jff_daily
manual__2026-11-20T11:14:50+00:00   | success | 2026-10-06
manual__2026-11-20T11:11:30+00:00   | success | 2026-10-09
backfill__2026-10-05T00:00:00+00:00 | success
backfill__2026-10-04T00:00:00+00:00 | success
backfill__2026-10-03T00:00:00+00:00 | success
```

The DAG is paused after the runs, which is the state Airflow gives a new DAG. Bronze holds
2026-10-03 to 2026-10-06 at scale 0.02 and 2026-10-09 at scale 1.0.

Note on `airflow dags test`: it writes a run id `manual__<timestamp>` and, when a run already exists
for that logical date, it replaces it. That is why the successful `scheduled__2026-10-06` run recorded
in item 4 no longer appears in this list: the deliberate failing run for item 3 and the final passing
run both reused the 2026-10-06 logical date. Its success at 11:02:57 is quoted in item 4.

## Not run

- A clean image build with no cache (`podman compose build` reused layers).
- `docker-compose` bring-up of this stack (only `config --quiet` was run in Step 0; T01 ran the full
  cycle).
- Rerunning the SeaweedFS volume-cap failure after the fix, i.e. a second collection written with a
  fresh stack: the fix is verified by the topology (`8/30`) and by every successful lake write.

