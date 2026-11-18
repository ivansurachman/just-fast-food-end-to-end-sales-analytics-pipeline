# T02: bronze ingest and DAG skeleton

Serves: 22 Nov checkpoint, step 19 Nov. Branch: `task/T02-bronze`.
Prerequisite: T01 accepted by Ivan. Do not start earlier.

## Deliverables

- `dags/jff_daily.py`: DAG `jff_daily`, daily, `catchup=True`, `max_active_runs=1`, pool `duckdb_writer` (1 slot). Tasks `wait_manifest`, `ingest_bronze`, `check_bronze` as in `docs/pipeline-design.md` section 5. Later tasks are placeholders that do nothing and are clearly marked.
- `pipelines/ingest_bronze.py`: a plain Python module with a CLI (`--ds`, `--endpoint`), no Airflow imports, so it can be tested without Airflow. Uses DuckDB with `memory_limit='1GB'`, `threads=2`. Reads CSV with `all_varchar=true`. Writes one Parquet file per entity per day to `s3://jff-lake/bronze/<entity>/source_file_date=<ds>/<entity>.parquet`, adding `source_file_date` and `_source_file`. Dimensions are ingested once to `bronze/dimensions/`.
- `pipelines/tests/`: pytest tests that run against a local folder and against the compose SeaweedFS if reachable (skipped otherwise).
- DuckDB extensions `httpfs` and `parquet` installed at image build time (no internet at run time).
- `docs/verification/T02-bronze.md`.

## Acceptance

1. Generate 3 days (2026-10-03 to 2026-10-05, scale 0.02) to `jff-raw`. Trigger `jff_daily` for each. All three runs succeed.
2. Re-run the same three dates. Parquet objects are byte-identical or, if the Parquet writer is not byte-stable, row hashes are identical. State which, with evidence.
3. `check_bronze`: for every entity and day, rows in CSV equal rows in Parquet, and the manifest `rows` equal bronze counts. Show the output. Prove it fails: delete one bronze object and show the task failing.
4. `wait_manifest` really waits: trigger a run for a date whose manifest does not exist yet, show it waiting in reschedule mode, then generate that day and show it proceeding.
5. Peak memory of the scheduler container during ingest of one full-scale day (`--scale 1.0`, about 120k orders) from `podman stats`. Report against the 1.7 GB limit.
6. `ruff`, `mypy`, `pytest` clean for the new code.

## STOP conditions

- DuckDB cannot read or write the SeaweedFS endpoint (path-style, no SSL). Report the exact error and the DuckDB version.
- The ingest of one full-scale day exceeds the container limit.
