# T01: Podman compose stack (Postgres, SeaweedFS, Airflow) + RAM baseline

Serves: 22 Nov checkpoint, step 18 Nov. Branch: `task/T01-infra`.
Prerequisite: T00 accepted by Ivan. Use its findings: the compose key that enforces memory limits, the compose provider, and its version.

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

- Memory limits exactly as in the table of `docs/pipeline-design.md` section 2, using the key T00 proved to be enforced. If T00 found no key enforced, use `mem_limit`, say so in the report, and do not claim enforcement.
- Airflow: version 3.x, exact patch tag older than 14 days. Fallback 2.11.x only if Ivan decides after the RAM measurement. LocalExecutor. Triggerer disabled if the version allows it (verify).
- Databases and SeaweedFS data on **named volumes**. Bind mounts only for `dags/` (relative path).
- Healthchecks on postgres, seaweedfs, airflow-api-server. Services use `depends_on` with health conditions if the provider supports it (verify), otherwise a documented start order.
- No credentials in compose files or the repo. Everything from `.env`.
- Windows-safe: bring-up and tear-down must work as plain `podman compose up -d` and `podman compose down` from the repo root in PowerShell.
- Generator S3 settings: endpoint `http://localhost:8333` from the host (verify the SeaweedFS S3 port), `http://seaweedfs:8333` inside the network.

## Acceptance (each item needs evidence in the report)

1. `podman compose up -d` from a clean state (no volumes) brings every service to healthy. Record the time.
2. `podman compose down` then `up -d` again keeps Postgres data and the buckets.
3. Memory limits visible: `podman inspect` (or equivalent) shows the limit for every container.
4. RAM baseline: `podman stats --no-stream` idle, then after step 6. Fill a table: container, idle MB, after-load MB, limit MB. Write it to the report. Also the total against 5.6 GB.
5. Airflow UI reachable at its port; login works with the `.env` credentials; zero DAGs; the `jff` virtualenv runs `/opt/venvs/jff/bin/jff-gen --help` inside the scheduler container.
6. From the host: `jff-gen dim all` and `jff-gen generate --date 2026-10-05 --scale 0.02 --s3-endpoint http://localhost:8333 --out s3://jff-raw` succeed. List the bucket and show the object keys, including `_manifests/dt=2026-10-05/manifest.json`. Run the same command twice: object contents must be identical (compare ETag or download and hash).
7. No file with a secret is tracked by git (`git ls-files | findstr /i env`).

## STOP conditions

- Any container exceeds its limit during idle or step 6, or is OOM-killed. Report the numbers. Do **not** raise limits or change the design. Ivan decides (for example Airflow 2.11.x).
- SeaweedFS rejects path-style S3 requests or the generator's multipart writes. Report the exact error.
- A required image tag cannot be verified as older than 14 days.
