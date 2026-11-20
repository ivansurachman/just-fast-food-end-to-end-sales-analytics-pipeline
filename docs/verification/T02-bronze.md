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

## Remaining T02 work

Not started: `dags/jff_daily.py`, `pipelines/ingest_bronze.py`, `pipelines/tests/`, DuckDB extensions
in the image, acceptance items 1 to 6.
