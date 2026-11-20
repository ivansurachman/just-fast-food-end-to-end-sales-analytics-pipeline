# T02 verification: bronze ingest and DAG skeleton

Task: `tasks/T02-ingest-bronze-dag.md`. Branch `task/T02-bronze`. Started 2026-11-20.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Only commands that were run are recorded. Anything not run is written as "not run".

## Step 0 (T01 follow-ups)

### 1. Ports on loopback

Not run yet. `compose.yaml` still publishes `5432:5432`, `8333:8333`, `8080:8080`.

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

## Remaining T02 work

Not started: `dags/jff_daily.py`, `pipelines/ingest_bronze.py`, `pipelines/tests/`, DuckDB extensions
in the image, acceptance items 1 to 6.
