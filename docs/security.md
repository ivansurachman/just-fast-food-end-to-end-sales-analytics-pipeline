# Security

What this project protects, what it does not, and what the scanners said on 2026-11-23. The stack is a
local demo on one Windows machine; the threats considered are accidental exposure (a port on the LAN, a
secret in git, a role that can write) and, second, the supply chain (pinned packages, scanned images).

## What is protected

| Area | How |
|---|---|
| Network exposure | Every published port is bound to `127.0.0.1` in `compose.yaml`: Postgres (default 5432, 5433 on Ivan's machine because a native server holds 5432), SeaweedFS 8333, the filer 8888, Airflow 8080, Metabase 3000. Nothing listens on the LAN or in WSL |
| Database roles | One Postgres instance, three databases (`airflow`, `metabase`, `analytics`), one role each. Metabase reads the marts as `analytics_ro`, created by `infra/postgres/create-analytics-ro.sh` with `SELECT` only, refreshed on every `up`, and `ALTER DEFAULT PRIVILEGES` covers the tables the loader creates later |
| Secrets | Only in `.env`, which is gitignored; `.env.example` carries placeholders. `tools/gen_env.py` generates fresh values (a valid Fernet key, alphanumerics for the S3 keys, tokens for the passwords) and refuses to overwrite. `tools/check_secrets.py` searches every commit for every value in `.env`: **`secrets in git: NONE`** on 2026-11-23, and it also fails if a `.env`, `.pem`, `.key`, `.p12` or `id_rsa*` file ever entered history |
| Privilege escalation | `security_opt: ["no-new-privileges:true"]` on all nine services, applied and read back with `podman inspect` (`HostConfig.SecurityOpt = [no-new-privileges]`) |
| Blast radius | `mem_limit` on every container, 5600 MB in total against a 7.6 GiB VM, so one runaway service cannot take the machine's memory |
| Supply chain | Every image, Python package and GitHub Action pinned to a release older than 14 days (`docs/versions.md`); `pipelines/constraints.txt` and `generator/constraints*.txt` are the single sources; CI installs exactly those |
| Code access to data | The pipeline writes through dbt and `load_marts`; Metabase never writes. `publish_parquet` opens DuckDB read-only |

## What is not protected

- **The Podman machine is rootful.** Every container is root inside the WSL2 VM, and anyone who can talk
  to the Podman socket is root there. A rootless machine was not adopted because the bind mounts and the
  Postgres volume needed the rootful setup to work (T00).
- **A native Windows PostgreSQL on 5432 is outside the project.** Ivan's machine runs PostgreSQL 18 as a
  Windows service; the project publishes 5433 to avoid it. Nothing in the project protects or configures
  that server.
- **Secrets are readable by the coding agent, and therefore by its model provider.** `.env` sits in the
  repository folder and the agent can read any file it is asked to. Treat every credential in `.env` as
  having been sent to the model provider, and rotate it if that matters.
- **No TLS anywhere.** Everything is loopback HTTP: Airflow, Metabase, the SeaweedFS API. Credentials
  travel in clear text inside the VM and the host.
- **One shared admin account per tool.** Airflow has the single `AIRFLOW_ADMIN_*` user and Metabase the
  single `MB_ADMIN_*` user; there are no per-person accounts and no audit trail of who changed what.
- **No backups.** `podman compose down -v` deletes the volumes (`pgdata`, `seaweedfs_data`, `jff_duckdb`).
  Recovery for DuckDB and the marts is a backfill from bronze; PostgreSQL's Airflow and Metabase
  databases have no backup story in this project.
- **The container environment is visible** with `podman inspect`, which prints every value from `.env` to
  anyone who can use the rootful socket.

## Dependency scan

`pip-audit` 2.10.1 (released 2026-06-10) against each pinned set, 2026-11-23. The pipeline, generator and
dbt sets have no findings; the Airflow image's own environment is the one that carries advisories.

| Set | Packages | Known vulnerabilities |
|---|---|---|
| Pipelines and host tools (`requirements-dev.txt` + `pipelines/constraints.txt`) | 25 | **0** |
| Generator (`generator/constraints.txt` + `constraints-dev.txt`) | 91 | **0** |
| dbt virtualenv (`infra/airflow/dbt-constraints.txt`) | 56 | **0** |
| Airflow image extras (`requirements.txt`: duckdb) | 1 | **0** |
| Airflow base image `apache/airflow:3.3.2-python3.12` (everything it ships) | 443 | **108 advisories in 23 packages** |

Severity of the 108 (from the OSV database, which carries the GHSA severity): **4 CRITICAL, 48 HIGH, 44
MODERATE, 10 LOW**, and 2 advisories that publish only a CVSS vector (both Airflow providers, low
impact). The packages with the most findings:

| Package in the image | Findings | Fixed in |
|---|---|---|
| `virtualenv` 21.7.9 | 24 (13 HIGH) | 21.14.9 |
| `aiohttp` 3.14.3 | 17 (11 HIGH) | 3.14.4 |
| `filelock` 3.32.6 | 13 (1 HIGH) | 4.2.1 |
| `authlib` 1.8.0 | 8 (**1 CRITICAL**) | 1.9.1 |
| `tornado` 6.5.8 | 7 | 6.6.1 |
| `gitpython` 3.1.62 | 6 (5 HIGH) | 3.2.0 |
| `certifi` 2026.7.22 | 2 (**2 CRITICAL**) | 2026.10.18 |
| `uv` 0.12.10 | 2 (**1 CRITICAL**) | 0.13.4 |
| `pyasn1` 0.6.4 | 4 (all HIGH) | 0.6.5 |
| `urllib3` 2.7.0 | 3 | 2.8.0 |

Every one of them has a fixed release. They are not fixed in this task because they all live in the
pinned base image, and T07 explicitly forbids changing image versions: moving the Airflow tag is Ivan's
decision. The same applies to the OS packages below.

## Image scan

`trivy` 0.76.2 (image `aquasec/trivy:0.76.2`, released 2026-11-05) reading the Podman socket, HIGH and
CRITICAL only, 2026-11-23.

| Image | HIGH | CRITICAL | Where it comes from |
|---|---|---|---|
| `postgres:18.4` | 216 | 14 | Debian packages of the base image: `perl*` (12 CRITICAL), `libxml2`, plus Go's `stdlib` in a bundled binary (25 HIGH) and the `krb5` libraries (56 HIGH) |
| `chrislusf/seaweedfs:4.52` | 1 | 0 | `golang.org/x/net` inside the `weed` binary |
| `metabase:v0.65.3` | 1 | 0 | `libfontenc` in Alpine 3.24.3 |
| `jff-airflow:3.3.2` (from `apache/airflow:3.3.2-python3.12`) | 342 | 23 | `aiohttp` (22 HIGH), `rsync` (20 HIGH), the `krb5` and Perl packages, and the CRITICALs: `perl*` (12), `certifi` (2), `uv` (2), `authlib`, `libsqlite3-0`, `libbrotli1`, `zlib1g`, `openssh-client`, `libxml2`, `sqlite3` |

No image tag was changed in this task. To act on this, the candidates are newer patch tags, newer than
the 14-day rule allows today or not yet evaluated: Airflow 3.3.x later patches, Postgres 18.6, Metabase
v0.65.6, SeaweedFS 4.53. Recorded here for Ivan to decide.

## Decision on image and base-image advisories

The 108 Python advisories in the Airflow base image and the HIGH/CRITICAL findings Trivy reports for the
four images are **accepted for this demo** on 2026-11-24, for four reasons:

- the stack runs on one local machine; nothing is published beyond loopback (`127.0.0.1`) and the host
  firewall stays shut;
- the data is synthetic, generated by `jff-gen`; there is no customer, payment or personal data to lose;
- the containers hold no credentials beyond the local `.env` values, which are also loopback-only;
- T07 forbids changing image versions in this task, so acting on the findings is a separate decision.

Revisit this after **29 November 2026**, with two options to evaluate then:

1. move to a newer Airflow patch tag — whether one exists that both fixes these packages and satisfies
   the 14-day rule has **not** been checked yet;
2. add a layer on top of the pinned image that upgrades the packages named in the tables above
   (`virtualenv`, `aiohttp`, `authlib`, `certifi`, `uv`, the `perl*` and `krb5` families), leaving the
   rest of the image pinned.

The numbers above are the measurements of 2026-11-23 and this decision does not change them.

## Reproducing the scans

```
# dependencies (pip-audit pinned in a throwaway venv)
python -m venv /tmp/audit && /tmp/audit/bin/pip install pip-audit==2.10.1
/tmp/audit/bin/pip-audit --path .venv/Lib/site-packages
/tmp/audit/bin/pip-audit -r infra/airflow/dbt-constraints.txt

# images (trivy reads the rootful Podman socket; the Windows host has no Docker socket)
podman run --rm -v /run/podman/podman.sock:/run/podman/podman.sock:ro \
    -e DOCKER_HOST=unix:///run/podman/podman.sock docker.io/aquasec/trivy:0.76.2 \
    image --severity HIGH,CRITICAL postgres:18.4
```
