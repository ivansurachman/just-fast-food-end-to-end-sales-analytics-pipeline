# Just Fast Food: sales analytics pipeline

Bootcamp final project: end-to-end sales analytics for a fictional fast food chain, on generated data.
The stack is Podman on Windows (WSL2); Docker, Linux and macOS are expected to work but are not tested
here. Architecture and decisions: `docs/pipeline-design.md`.

## Layout

- `generator/`: seeded synthetic data generator (Python CLI, tests)
- `pipelines/`: ingest, bronze checks, marts loader, lake publisher
- `dags/`: the Airflow DAG `jff_daily`
- `dbt/`: silver, gold and mart models
- `dashboards/`: Metabase setup script and one SQL file per card
- `infra/`: container support files (Postgres roles, SeaweedFS, Airflow entrypoints)
- `docs/`: design, data model and dictionary, version pins, security, demo script, verification
- `sample-data/`: seven days (2026-10-03 to 2026-10-09) at `--scale 0.02`, for review

## Generate data

```
cd generator
pip install -c constraints.txt -c constraints-dev.txt -e ".[dev,s3test]"
jff-gen dim all --out ../data
jff-gen generate --start 2026-09-16 --end 2026-10-30 --scale 0.1 --out ../data
jff-gen profile --data ../data --out ../docs/data-profile.md
pytest && ruff check . && mypy src tests
```

Full command reference: `docs/cli-guide.md`. Dataset profile: `docs/data-profile.md`. The same date
always produces identical files for the same seed and library versions, so keep the constraints pinned.

## First run from a fresh clone

A clean-room run on 2026-11-23 (empty folder, no volumes, own project name) needed exactly this:

```
# 1. Python must exist before anything else: gen_env.py is standard library only
python tools/gen_env.py                 # writes .env, prints names, never values

# 2. If a native PostgreSQL already holds 5432, change the host port in .env
#    POSTGRES_HOST_PORT=5433             (the container still reaches Postgres as postgres:5432)

# 3. Build and start
podman compose build --no-cache
podman compose up -d
podman compose ps                       # wait for healthy

# 4. Dimensions once, then the fact days, inside the scheduler
podman exec jff_airflow-scheduler_1 /opt/venvs/jff/bin/jff-gen dim all \
    --out s3://jff-raw --s3-endpoint http://seaweedfs:8333
podman exec jff_airflow-scheduler_1 /opt/venvs/jff/bin/jff-gen generate \
    --start 2026-10-03 --end 2026-10-09 --scale 0.02 \
    --out s3://jff-raw --s3-endpoint http://seaweedfs:8333

# 5. Point the DAG at the days that exist (start_date and end_date in dags/jff_daily.py),
#    otherwise catchup schedules runs for days without data and their wait_manifest blocks
#    the backfill behind max_active_runs=1.
podman exec jff_airflow-scheduler_1 airflow dags unpause jff_daily
podman exec jff_airflow-scheduler_1 airflow backfill create \
    --dag-id jff_daily --from-date 2026-10-03 --to-date 2026-10-09
podman exec jff_airflow-scheduler_1 airflow dags pause jff_daily

# 6. Dashboards
python dashboards/setup.py              # prints one URL per page
```

A `python` on PATH is enough for steps 1 and 6; they use the standard library only.

## Test environments

Three environments, three commands. Anything else is untested; the containers run the pipeline and do
not carry pytest, so the tests run on the host.

**Pipeline code (`dags/`, `pipelines/`), host virtualenv.** Versions are pinned in
`pipelines/constraints.txt` (runtime libraries at the versions the containers run, plus the host tools):

```
python -m venv .venv
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q
```

The SeaweedFS cases in `pipelines/tests` skip themselves unless the credentials are exported and the
stack is up. On PowerShell (values from `.env`):

```
$env:S3_ACCESS_KEY = (Select-String -Path .env -Pattern '^S3_ACCESS_KEY=' | % { $_.Line.Split('=',2)[1] })
$env:S3_SECRET_KEY = (Select-String -Path .env -Pattern '^S3_SECRET_KEY=' | % { $_.Line.Split('=',2)[1] })
$env:JFF_S3_ENDPOINT = "http://localhost:8333"
python -m pytest -q
```

**Generator**, its own virtualenv in `generator/` (`constraints.txt` pins the runtime,
`constraints-dev.txt` the tools):

```
cd generator
python -m pip install -c constraints.txt -c constraints-dev.txt -e ".[dev,s3test]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
```

**CI** runs those two sets in two jobs: `.github/workflows/ci.yml`, ubuntu-24.04, Python 3.12.

## Run one new day

The DAG is bounded by `start_date` and `end_date` in `dags/jff_daily.py`, and it only runs while it is
unpaused. A day outside that window never executes. The working order is:

1. Generate the day into the raw bucket, inside the scheduler container:
   `podman exec jff_airflow-scheduler_1 /opt/venvs/jff/bin/jff-gen generate --date 2026-11-17 --scale 0.1 --out s3://jff-raw --s3-endpoint http://seaweedfs:8333`
2. Make sure `end_date` covers it: extend it in `dags/jff_daily.py` and wait for the next parse
   (`airflow dags list-import-errors` stays empty).
3. Unpause: `podman exec jff_airflow-scheduler_1 airflow dags unpause jff_daily` (or the toggle in the UI).
4. Trigger the day from the UI (the play button) or with
   `podman exec jff_airflow-scheduler_1 airflow backfill create --dag-id jff_daily --from-date 2026-11-17 --to-date 2026-11-17`.
5. Watch it: `airflow tasks states-for-dag-run jff_daily <run_id>` shows the seven tasks. The dashboard
   picks the day up once `load_marts` has run.

Two paths do not work, both silently:

- Triggering a day **beyond `end_date`** creates a run with no task instances: with the DAG unpaused it
  is finalised `success` in milliseconds, with the DAG paused it sits `queued` forever.
- Triggering while the DAG is **paused** does nothing until you unpause.

Pause it again afterwards if the stack should stay quiet. The demo storyline is in
`docs/demo-script.md`.
