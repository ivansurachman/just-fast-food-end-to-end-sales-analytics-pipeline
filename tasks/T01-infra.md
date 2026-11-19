# T01: Podman compose stack (Postgres, SeaweedFS, Airflow) + RAM baseline

Serves: 22 Nov checkpoint, step 18 Nov. Branch: `task/T01-infra`.
Prerequisite: T00 accepted by Ivan. Ivan decided to run **without `.wslconfig`**, on the WSL2 default (about 7.6 GiB visible in the VM). Do not create or edit `.wslconfig`.
Findings from `docs/verification/T00-smoke-test.md` that this task relies on:

- Compose provider: Ivan switched `podman compose` permanently to **`podman-compose` 1.6.0** (Python, installed in miniconda base) through `compose_providers` in `%APPDATA%\containers\containers.conf`. It is called by absolute path, so it works from shells that do not load the conda profile. Do not change this setting.
- With `podman-compose`, container names use underscores (`project_service_1`), not hyphens.
- `docker-compose` v5.6.1 is still installed. The compose file must work with both providers. Use only features both support, and test with `podman compose` (the permanent provider) first.
- With docker-compose v5.6.1, `up --abort-on-container-exit` hung after the container exited. Use `up -d` plus `podman wait` or `podman inspect` for deterministic checks. This was not re-tested with `podman-compose`.
- Memory limits are enforced for `podman run --memory`, `mem_limit`, and `deploy.resources.limits.memory`, under both providers (exit 137, `OOMKilled=true`). Use `mem_limit`.
- The Podman machine is **rootful**, cgroups v2, provider WSL. Named volumes and UID 50000 should not need `user:` tricks here. Document that rootless Linux hosts may differ (verify, do not test).
- The `Resources.Memory` value shown by `podman machine inspect` is not applied under the WSL provider. Only `.wslconfig` limits the VM.
- Python on the host is 3.15.1. Containers use the image's Python. Keep both working.

## Step 0 (before anything else)

1. Run `podman info --format "{{.Host.MemTotal}}"` and record it (expect about 8.2 GB, roughly 7.6 GiB).
2. Overwrite `generator/tests/test_s3_sink.py` with the corrected version Ivan provides (the moto server now binds to `127.0.0.1`). Run `pytest` in `generator/`. Expected: 41 passed. Record the result.

## Deliverables

| Path | Content |
|---|---|
| `compose.yaml` | Services: `postgres`, `seaweedfs`, `airflow-init` (one-shot), `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`. Metabase is **not** in this task |
| `.env.example` | Every variable with a harmless example value. Real `.env` stays untracked |
| `infra/postgres/init/01-databases.sql` | Creates databases `airflow`, `metabase`, `analytics` with separate roles |
| `infra/seaweedfs/` | Config that gives the S3 API one identity read from env, and a script that creates buckets `jff-raw` and `jff-lake` |
| `infra/airflow/Dockerfile` | Pinned Airflow image plus a virtualenv `/opt/venvs/jff` with the generator installed using `generator/constraints.txt`. dbt comes later |
| `docs/versions.md` | Every pinned image tag and package, with release date and why it was chosen |
| `docs/verification/T01-infra.md` | Evidence for the acceptance items below |

## Constraints

- Memory limits exactly as in the table of `docs/pipeline-design.md` section 2, using `mem_limit`.
- Airflow: version 3.x, exact patch tag older than 14 days. Fallback 2.11.x only if Ivan decides after the RAM measurement. LocalExecutor. Triggerer disabled if the version allows it (verify).
- Databases and SeaweedFS data on **named volumes**. Bind mounts only for `dags/` (relative path).
- Healthchecks on postgres, seaweedfs, airflow-api-server. Use `depends_on` with `condition: service_healthy`. `podman-compose` 1.6.0 may ignore or only partly honor health conditions (verify in the bring-up test: start with postgres artificially slow and watch the order). If it is not honored, use a small wait step (`airflow-init` retrying until Postgres answers) and document it. Do not rely on start order alone.
- No credentials in compose files or the repo. Everything from `.env`.
- Windows-safe: bring-up and tear-down must work as plain `podman compose up -d` and `podman compose down` from the repo root in PowerShell.
- Generator S3 settings: endpoint `http://localhost:8333` from the host (verify the SeaweedFS S3 port), `http://seaweedfs:8333` inside the network.

## Acceptance (each item needs evidence in the report)

1. `podman compose up -d` from a clean state (no volumes) brings every service to healthy. Record the time.
2. `podman compose down` then `up -d` again keeps Postgres data and the buckets.
3. Memory limits visible: `podman inspect` (or equivalent) shows the limit for every container.
4. RAM baseline: `podman stats --no-stream` idle, then after step 6. Fill a table: container, idle MB, after-load MB, limit MB. Write it to the report. Also the total against 5.6 GB, and `podman machine ssh free -m` (used, available, buff/cache) at both moments, because the VM has about 7.6 GiB, not 9 GB.
5. Airflow UI reachable at its port; login works with the `.env` credentials; zero DAGs; the `jff` virtualenv runs `/opt/venvs/jff/bin/jff-gen --help` inside the scheduler container.
6. From the host: `jff-gen dim all` and `jff-gen generate --date 2026-10-05 --scale 0.02 --s3-endpoint http://localhost:8333 --out s3://jff-raw` succeed. List the bucket and show the object keys, including `_manifests/dt=2026-10-05/manifest.json`. Run the same command twice: object contents must be identical (compare ETag or download and hash).
7. No file with a secret is tracked by git (`git ls-files | findstr /i env`).

## STOP conditions

- Any container exceeds its limit during idle or step 6, or is OOM-killed, or `free -m` shows less than 1 GiB available in the VM after step 6. Report the numbers. Do **not** raise limits or change the design. Ivan decides (for example Airflow 2.11.x).
- SeaweedFS rejects path-style S3 requests or the generator's multipart writes. Report the exact error.
- A required image tag cannot be verified as older than 14 days.
- Postgres: do not reuse `16.4` from T00. Pick the newest patch of a major version that both the chosen Airflow release and Metabase document as supported for their databases (verify in their docs), older than 14 days, and record it in `docs/versions.md`.
