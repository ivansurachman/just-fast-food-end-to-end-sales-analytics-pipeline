# T01 verification: Podman compose stack (Postgres, SeaweedFS, Airflow)

Task: `tasks/T01-infra.md`. Branch `task/T01-infra`. Date: 2026-11-19.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).
Podman 6.1.4, rootful, cgroups v2, WSL provider on Windows 11 Home, no `.wslconfig`.

This report records only commands that were actually run and their real output. Anything not run is
written as "not run".

## Step 0

### 0.1 VM memory

Command:

```
podman info --format "{{.Host.MemTotal}}"
```

Output:

```
8202760192
```

8202760192 bytes = **7.64 GiB**, which is the WSL2 default for this machine (no `.wslconfig`, as Ivan
decided). The task expected about 8.2 GB, so this matches.

### 0.2 Generator tests

`generator/tests/test_s3_sink.py` in the branch already binds the moto server to `127.0.0.1`
(commit `8c117af`, "fix(tests): bind moto server to loopback address for Windows compatibility"), so
the corrected version Ivan announced is in place. No overwrite was needed, and `generator/` is
byte-identical to the T00 state.

Command, from `generator/` with the host venv (Python 3.15.1):

```
pytest
```

Output, final lines:

```
collected 41 items

tests\test_daily_and_cli.py ................                             [ 39%]
tests\test_data_dictionary.py ..                                         [ 43%]
tests\test_plan_and_baskets.py ........                                  [ 63%]
tests\test_profiling.py ......                                           [ 78%]
tests\test_s3_sink.py ..                                                 [ 82%]
tests\test_seeding_and_dims.py .......                                   [100%]

============================= 41 passed in 12.11s =============================
```

Verdict: **41 passed** (exit code 0).

## Files delivered

| Path | Content |
|---|---|
| `compose.yaml` | `postgres`, `seaweedfs`, `seaweedfs-init`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`; healthchecks, `mem_limit` per service, named volumes `pgdata` and `seaweedfs_data`, bind mount `./dags` only |
| `.env.example` | Every variable, placeholder values only |
| `.env` (untracked, created locally) | Real local passwords and keys; git-ignored |
| `infra/postgres/init/01-databases.sql` | Roles and databases `airflow`, `metabase`, `analytics`, passwords read from the environment with `psql` `\getenv` |
| `infra/seaweedfs/entrypoint.sh` | Renders the single S3 identity from `S3_ACCESS_KEY`/`S3_SECRET_KEY`, starts `weed server` with S3 on 8333 |
| `infra/seaweedfs/create-buckets.sh` | Creates `jff-raw` and `jff-lake`, idempotent (checks `s3.bucket.list` first) |
| `infra/airflow/Dockerfile` | Pinned Airflow base plus `/opt/venvs/jff` with the generator from `generator/constraints.txt` |
| `Containerfile` (repo root) | Same build, needed on Windows; see finding 1 |
| `infra/airflow/install-generator.sh` | The single place where the venv, `pip` and `setuptools` versions are defined |
| `infra/airflow/init-db.sh` | One-shot bootstrap: wait for Postgres, `airflow db migrate`, create the admin user idempotently |
| `infra/airflow/wait-for-db.sh` | Gate used by the three long-running Airflow services; see finding 2 |
| `.dockerignore` | Keeps the build context small |

`dags/.gitkeep` keeps the bind-mount directory in git.

## Findings that shaped the implementation

### 1. `podman-compose` 1.6.0 on Windows ignores `build.dockerfile`

`podman compose build` failed with:

```
Error: no Containerfile or Dockerfile specified or found in context directory,
D:\File Campuran\Certification\Dibimbing\Final Project\files\just-fast-food: The system cannot find the file specified.
```

`podman-compose --verbose build` shows the command it builds:

```
INFO:podman_compose:podman build -t jff-airflow:3.3.2 D:\...\just-fast-food
```

No `-f`. In `podman_compose.py` (`container_to_build_args`, ~line 3296) the `-f` lookup is skipped when
`is_context_git_url(ctx)` is true, and `is_context_git_url` uses `urllib.parse.urlparse`: a Windows
path `C:\...` parses as scheme `c`, path non-empty, so it is treated as a git URL. The same happens
with a two-service throwaway compose file in `%TEMP%`, so it is not specific to this project. The
bug is Windows-only (a POSIX path has no scheme).

Workaround: the repo-root `Containerfile` is the file podman finds by default. `compose.yaml` still
sets `dockerfile: infra/airflow/Dockerfile`, which `docker-compose` uses; both files call
`infra/airflow/install-generator.sh`, so versions are defined once. Evidence that the workaround
works is acceptance item 1 below.

### 2. `podman-compose` 1.6.0 does not honour `depends_on: condition: service_completed_successfully`

First bring-up with a plain `airflow-init` (no gate). Container start times from `podman inspect`:

```
jff_postgres_1            started 2026-11-19 14:57:53
jff_seaweedfs_1           started 2026-11-19 14:57:53
jff_airflow-api-server_1  started 2026-11-19 14:58:17
jff_airflow-scheduler_1   started 2026-11-19 14:58:29
jff_airflow-init_1        started 2026-11-19 14:58:42
```

The api-server and scheduler started before `airflow-init` had even started, so the completion
condition was ignored. In `podman_compose.py` the condition is mapped (`service_completed_successfully`
-> `ServiceDependencyCondition.STOPPED`, line 1576) and `check_dep_conditions` is only called from
`run_container` when the command contains `start` (line ~3544), and `podman wait` on a container that
does not exist yet makes the loop fall through to `sleep 1` and retry, so ordering is not guaranteed.

Fix: `infra/airflow/wait-for-db.sh` runs as the entrypoint of the api-server, scheduler and
dag-processor and polls `airflow db check-migrations` (90 attempts, 2 s apart) before `exec`-ing the
real command. `airflow-init` also polls `airflow db check` itself before migrating. After the fix,
start times show the intended order: `airflow-init` exits before the gate lets the long-running
services start their commands (see item 1).

`docker-compose` v5.6.1 does honour the conditions; with that provider `airflow-init` exits before
the api-server starts (see the cross-provider section).

### 3. `podman compose up -d` builds only when the image is missing

`prepare_images` in `podman_compose.py` calls `build` with `if_not_exists=(not args.build)`, so after
editing a Dockerfile an explicit `podman compose build` is required. This bit me once: `up -d`
recreated containers from the previous image and the new `wait-for-db.sh` was not found
(`crun: executable file /opt/jff/wait-for-db.sh not found`). Documented here so it does not look like
a random failure later.

### 4. `SimpleAuthManager` cannot create users in 3.3.2

With the default auth manager, `airflow users create` in the init container fails:

```
AttributeError: 'AirflowSecurityManagerV2' object has no attribute 'find_role'
Airflow admin user already exists
```

(the second line was my early `|| echo` fallback, now removed). Fix: set
`AIRFLOW__CORE__AUTH_MANAGER=airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager`
(bundled `apache-airflow-providers-fab` 3.9.0). The same command then succeeds:

```
User "probe" created with role "Admin"
```

and the real init script creates `admin` from `.env`. Recorded in `docs/versions.md`.

### 5. Postgres 18 data directory

`podman image inspect postgres:18.4` reports `PGDATA=/var/lib/postgresql/18/docker` and the image
declares the volume `/var/lib/postgresql`. The named volume is therefore mounted at
`/var/lib/postgresql`, not `/var/lib/postgresql/data`.

## Acceptance

### 1. `podman compose up -d` from a clean state

Clean state: `podman compose down -v` (no containers, `podman volume ls` shows no `jff` volume). The
image was already built at this point (`podman compose build`, exit 0).

```
podman compose up -d
```

```
up_exit=0 up_seconds=68.5
settled_seconds=83.8
jff_postgres_1	Up About a minute (healthy)
jff_seaweedfs_1	Up About a minute (healthy)
jff_seaweedfs-init_1	Exited (0) About a minute ago
jff_airflow-init_1	Exited (0) 3 seconds ago
jff_airflow-api-server_1	Up 41 seconds (healthy)
jff_airflow-scheduler_1	Up 29 seconds
jff_airflow-dag-processor_1	Up 15 seconds
```

`up_seconds` is the wall time of `podman compose up -d`; `settled_seconds` is the time until every
container with a healthcheck reported `healthy` and both one-shot containers had exited 0 (polled
every 3 s). The scheduler and dag-processor have no healthcheck in this task, they are `Up`.

Verdict: **pass**, 68.5 s for `up -d`, 83.8 s to a fully healthy stack, on a built image.

Airflow configuration in the running scheduler, read back from the container:

```
airflow config get-value core executor      -> LocalExecutor
airflow config get-value core auth_manager  -> airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager
airflow config get-value core load_examples -> false
```

`airflow triggerer` exists as a command in 3.3.2 (`airflow --help`), but no triggerer container is
deployed and no triggerer process runs, so it is disabled.

### 2. `down` then `up -d` keeps Postgres data and the buckets

State before `podman compose down` (the S3 objects came from item 6):

```
select count(*) from ab_user                  -> 1
s3.bucket.list
  jff-lake	size:0	logical:0	chunk:0
  jff-raw	size:289816	logical:97468	chunk:8
```

`podman compose down` (volumes kept): the two named volumes survive.

```
volumes kept:
jff_pgdata
jff_seaweedfs_data
```

After `podman compose up -d` (`up_exit=0`, `settled_seconds=79.7`, all healthy as in item 1):

```
select count(*) from ab_user                  -> 1
databases                                      -> airflow, analytics, metabase
s3.bucket.list
  jff-lake	size:0	logical:0	chunk:0
  jff-raw	size:289816	logical:97468	chunk:8
```

`airflow-init` re-ran and stayed idempotent:

```
Airflow admin user admin already exists
```

Verdict: **pass**.

### 3. Memory limits visible

`podman inspect <name> --format "{{.HostConfig.Memory}}"` for every container:

| Container | Limit (bytes) | Limit |
|---|---|---|
| `jff_postgres_1` | 629145600 | 600 MiB |
| `jff_seaweedfs_1` | 629145600 | 600 MiB |
| `jff_airflow-api-server_1` | 838860800 | 800 MiB |
| `jff_airflow-scheduler_1` | 1782579200 | 1700 MiB |
| `jff_airflow-dag-processor_1` | 524288000 | 500 MiB |
| `jff_seaweedfs-init_1` (one-shot) | 268435456 | 256 MiB |
| `jff_airflow-init_1` (one-shot) | 536870912 | 512 MiB |

Matches `docs/pipeline-design.md` section 2 for the five services the design names. The two one-shot
containers are not in that table; they are bounded to 256 MiB and 512 MiB so the peak still fits.
Long-running sum 4200 MiB = 4.10 GiB; with both one-shots alive 4968 MiB = 4.85 GiB, below the
5.6 GB budget.

Verdict: **pass**.

### 4. RAM baseline

Idle, about one minute after a clean bring-up (`podman stats --no-stream`):

| Container | Idle | Limit | % of limit |
|---|---|---|---|
| `jff_postgres_1` | 65.34 MB | 629.1 MB | 10.38% |
| `jff_seaweedfs_1` | 34.8 MB | 629.1 MB | 5.53% |
| `jff_airflow-api-server_1` | 302.2 MB | 838.9 MB | 36.03% |
| `jff_airflow-scheduler_1` | 406.9 MB | 1.783 GB | 22.83% |
| `jff_airflow-dag-processor_1` | 165.7 MB | 524.3 MB | 31.61% |

After step 6 (`jff-gen dim all` + `jff-gen generate`, run on the host):

| Container | After load | Limit |
|---|---|---|
| `jff_postgres_1` | 68.82 MB | 629.1 MB |
| `jff_seaweedfs_1` | 53.21 MB | 629.1 MB |
| `jff_airflow-api-server_1` | 302.3 MB | 838.9 MB |
| `jff_airflow-scheduler_1` | 409.5 MB | 1.783 GB |
| `jff_airflow-dag-processor_1` | 165.7 MB | 524.3 MB |

`podman machine ssh free -m`, idle:

```
               total        used        free      shared  buff/cache   available
Mem:            7822        1848        1748          26        4628        5974
Swap:           2048          59        1988
```

after step 6:

```
               total        used        free      shared  buff/cache   available
Mem:            7822        1855        1739          29        4632        5966
Swap:           2048          59        1988
```

Total container usage is about 1.0 GB against the 5.6 GB limit budget; the VM has 5966 MB available,
well above the 1 GiB floor in the STOP conditions.

Honest note: step 6's load runs in the host venv, so the container columns barely move. The load that
exercises the scheduler's 1.7 GB limit (DuckDB with `memory_limit='1GB'`, `threads=2`) only exists
once the ingest and dbt tasks are written (T02/T03). This baseline measures the stack, not DuckDB.

No container was OOM-killed and nothing restarted:

```
jff_postgres_1 oom=false restarts=0
jff_seaweedfs_1 oom=false restarts=0
jff_seaweedfs-init_1 oom=false restarts=0
jff_airflow-init_1 oom=false restarts=0
jff_airflow-api-server_1 oom=false restarts=0
jff_airflow-scheduler_1 oom=false restarts=0
jff_airflow-dag-processor_1 oom=false restarts=0
```

Verdict: **pass**, no STOP condition hit.

### 5. Airflow UI, login, zero DAGs, generator virtualenv

```
curl -s -o NUL -w "%{http_code}" http://localhost:8080/api/v2/monitor/health   -> 200
curl -s -o NUL -w "%{http_code}" http://localhost:8080/                        -> 200
curl -s -o NUL -w "%{http_code}" http://localhost:8080/auth/login/             -> 200
```

Login with the `.env` credentials, then the DAG list with the returned token:

```
POST /auth/token  {"username":"admin","password":"<from .env>"}  -> 201 Created
GET /api/v2/dags?limit=100  ->  {"dags":[],"total_entries":0}
```

The token endpoint expects a JSON body with `FabAuthManager` (a form-encoded body returns 422).

Generator virtualenv inside the scheduler container:

```
podman exec jff_airflow-scheduler_1 /opt/venvs/jff/bin/jff-gen --help
usage: jff-gen [-h] {dim,generate,profile} ...
```

The in-network S3 endpoint resolves and answers from inside the container (403 is what an unsigned
S3 request gets, so the port and the service name are both right):

```
podman exec jff_airflow-scheduler_1 /opt/venvs/jff/bin/python -c \
  "import urllib.request; print(urllib.request.urlopen('http://seaweedfs:8333/').status)"
urllib.error.HTTPError: HTTP Error 403: Forbidden
```

Verdict: **pass**.

### 6. Generator writes to SeaweedFS from the host

Environment for the host process: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from `.env`,
`AWS_DEFAULT_REGION=us-east-1`.

```
jff-gen dim all --out s3://jff-raw --s3-endpoint http://localhost:8333          -> exit 0
jff-gen generate --date 2026-10-05 --scale 0.02 --s3-endpoint http://localhost:8333 --out s3://jff-raw
                                                                                -> exit 0
2026-11-19 15:17:59,635 INFO 2026-10-05: {'orders': 2201, 'order_items': 5384, 'order_changes': 22}
```

Note: `--out` is the bucket root, because `dim` appends `dimensions/` itself; `--out s3://jff-raw/dimensions`
produces `dimensions/dimensions/...`.

Bucket listing after the two commands (boto3, path-style addressing, every object downloaded and
hashed):

```
objects=8
_manifests/dt=2026-10-05/manifest.json	506
dimensions/branches.csv	11676
dimensions/channels.csv	261
dimensions/menu_items.csv	1011
dimensions/promos.csv	746
order_changes/dt=2026-10-05/order_changes.csv	1861
order_items/dt=2026-10-05/order_items.csv	230269
orders/dt=2026-10-05/orders.csv	236131
```

Manifest content:

```json
{
  "date": "2026-10-05",
  "defects_enabled": true,
  "dropped_branch_ids": [],
  "expected_branches": 120,
  "injected": {
    "duplicate_item_rows": 18,
    "duplicate_orders": 7,
    "gross_mismatch": 6,
    "late_orders_delayed_in": 15,
    "late_orders_delayed_out": 33,
    "payment_null": 8,
    "payment_variant": 10,
    "platform_ref_null": 14,
    "unknown_menu_item": 6
  },
  "rows": {
    "order_changes": 22,
    "order_items": 5384,
    "orders": 2201
  },
  "scale": 0.02,
  "seed": 42
}
```

Second run of the same two commands, then a second snapshot of all eight objects (size + SHA-256):

```
identical: 8 objects match by size and sha256
```

Snapshot 1 hashes, for the record:

```
_manifests/dt=2026-10-05/manifest.json	506	579a1f4f018da4914f747aea741c3d4125de2d96d0a6bf45e40e40c8e1e7e134
dimensions/branches.csv	11676	1f89e94af6c932ce473f36e5166f780bc38395f8ff5ed1672a5998cc0646fec0
dimensions/channels.csv	261	a8c5608253b3afaad754d8d69bd7b89719b3414defeaf8aa0005f43ad051e5b7
dimensions/menu_items.csv	1011	f7f3f9429c7c536e99681bc0735abafadbdcaaaac8d2f2c9cffd807345f7a7fa
dimensions/promos.csv	746	82434c6a114e538e4baf80e49a956b701b0d9ee64eb27fc7b998fd8ac42be451
order_changes/dt=2026-10-05/order_changes.csv	1861	23c18ad029a787d4a0365e603ccb75eb0b9f3ee0dc8105b82c010395174a0d34
order_items/dt=2026-10-05/order_items.csv	230269	08321d143b0a373d5c4e7a777826c8224cb8cca011616a029c894101ba8d6d02
orders/dt=2026-10-05/orders.csv	236131	cb692142314bbeced9e6ec282a6fe3af85abeaaab1b3c569c778b3300ffc2469
```

Path-style addressing and the SeaweedFS S3 port (8333, host mapping `8333:8333`) work; SeaweedFS did
not reject the generator's writes, so that STOP condition was not hit.

Verdict: **pass**, byte-identical on the second run.

### 7. No tracked secret

```
git ls-files | findstr /i env
.env.example

git check-ignore -v .env
.gitignore:9:.env	.env
```

Only the placeholder file is tracked; the real `.env` is ignored and was never added.

Verdict: **pass**.

## Cross-provider check with docker-compose v5.6.1

The task requires the compose file to work with both providers. `docker-compose -f compose.yaml config --quiet`
exits 0. Full bring-up with the podman stack stopped:

```
docker-compose -p jffdc -f compose.yaml up -d
dc_up_exit=0 dc_up_seconds=30
dc_settled_seconds=52
jffdc-postgres-1	Up 51 seconds (healthy)
jffdc-seaweedfs-1	Up 51 seconds (healthy)
jffdc-airflow-init-1	Exited (0) 23 seconds ago
jffdc-seaweedfs-init-1	Exited (0) 44 seconds ago
jffdc-airflow-scheduler-1	Up 22 seconds
jffdc-airflow-dag-processor-1	Up 22 seconds
jffdc-airflow-api-server-1	Up 22 seconds (healthy)
```

With this provider `airflow-init` exits before the others start, so the completion condition is
honoured (the `wait-for-db.sh` gate then passes immediately).

Also checked with this provider: `mem_limit` is applied (600/600/800/1700/500/256/512 MiB), login
returns a token, `/api/v2/dags` returns `{"dags":[],"total_entries":0}`, and `seaweedfs-init` created
`jff-raw` and `jff-lake` in a fresh volume.

`docker-compose -p jffdc -f compose.yaml down -v` removed the containers, the network `jffdc_default`
and the volume `jffdc_pgdata`. Container names use hyphens (`jffdc-postgres-1`), while
`podman-compose` uses underscores (`jff_postgres_1`), as T00 found.

Afterwards the permanent provider stack was restored with `podman compose up -d`
(`settled_seconds=77.1`, all healthy, buckets still holding the 8 objects / 289816 bytes).

## Not verified

- Memory-limit enforcement on a rootless Linux host with `userns_mode` or `user:` overrides: not run,
  this machine is rootful Podman on WSL2 and UID 50000 needed no tricks.
- Docker Engine on Linux or Docker Desktop on macOS/Windows: not run. Only the compose file was
  validated with `docker-compose` against the podman socket.
- The scheduler's memory use with DuckDB under `memory_limit='1GB'`: not run, no DuckDB task exists
  yet (T02/T03).
- `podman-compose` `service_healthy` condition for the api-server: the api-server was already healthy
  in every run, so a negative test (start with Postgres artificially slow) was not run. The completion
  condition was measured as ignored (finding 2) and is not relied on.
- `restart: unless-stopped` behaviour after a Podman machine restart: not run.
- Metabase: out of scope for T01.
