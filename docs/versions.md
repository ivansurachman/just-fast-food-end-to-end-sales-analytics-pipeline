# Versions

Every version used by the stack, with its release date and the reason it was chosen. The rule from
`AGENTS.md`: pin everything, and choose releases older than 14 days (today is 2026-11-19, so the
cutoff is 2026-11-05).

## Container images

| Image | Tag | Released | Why |
|---|---|---|---|
| Airflow | `docker.io/apache/airflow:3.3.2-python3.12` | 2026-09-17 | Newest 3.x patch older than 14 days. 3.4.0 was published 2026-11-06, which is 13 days old, so it is excluded. Python 3.12 because the image publishes a 3.12 tag and the generator requires Python >= 3.11. The runtime reports Python 3.12.14. |
| PostgreSQL | `docker.io/library/postgres:18.4` | 2026-08-06 | Airflow 3.3.2 documents PostgreSQL 14–18 as tested; Metabase documents support for the latest stable PostgreSQL, which is 18. 18.6 (2026-11-06) is too new, so 18.4 is the newest eligible patch of the newest major both tools support. |
| SeaweedFS | `docker.io/chrislusf/seaweedfs:4.52` | 2026-11-02 | Newest stable tag older than 14 days. 4.53 (2026-11-08) and 4.54 (2026-11-16) are too new. |

The local image `jff-airflow:3.3.2` is built from `docker.io/apache/airflow:3.3.2-python3.12` by the
repo-root `Containerfile`, the single build file. `compose.yaml` names it in `build.dockerfile`;
`podman-compose` 1.6.0 on Windows ignores that key (it reads the absolute build context `C:\...` as a
git URL, skips the `-f` lookup, and lets podman fall back to the file in the context root) but lands
on the same `Containerfile`. Python package versions live in `infra/airflow/install-generator.sh`
and `generator/constraints.txt`.

Bundled in that Airflow image and used here: `apache-airflow-providers-fab` 3.9.0 (auth manager
`FabAuthManager`, so the admin user from `.env` is stored in the metadata database).

## Tooling

| Tool | Version | Note |
|---|---|---|
| Podman | 6.1.4 | Rootful, cgroups v2, WSL provider (T00) |
| `podman-compose` | 1.6.0 | Permanent `podman compose` provider (T00), Python |
| `docker-compose` | 5.6.1 | Second provider; the compose file must work with both |

## Python packages in the Airflow image

The generator virtualenv `/opt/venvs/jff` installs its runtime dependencies from
`generator/constraints.txt`, the same file the host venv uses. `pip` and `setuptools` are the only
extra pins, because they have to exist before the constraints can be applied.

| Package | Version | Released | Why |
|---|---|---|---|
| `pip` | 26.3 | 2026-11-02 | Newest pip older than 14 days; used only inside the venv. |
| `setuptools` | 84.2.1 | 2026-10-20 | Newest setuptools older than 14 days; build backend for the generator (`requires = setuptools>=68`). |

The generator pins, all inherited from `generator/constraints.txt` (byte-identical to the T00
state; T01 does not edit `generator/`):

| Package | Version | Released |
|---|---|---|
| `aiobotocore` | 3.10.0 | 2026-10-23 |
| `aiohappyeyeballs` | 2.7.1 | 2026-07-01 |
| `aiohttp` | 3.14.5 | 2026-10-11 |
| `aioitertools` | 0.13.0 | 2025-11-06 |
| `aiosignal` | 1.4.0 | 2025-07-03 |
| `annotated-types` | 0.8.0 | 2026-07-23 |
| `attrs` | 26.1.0 | 2026-03-19 |
| `blinker` | 1.9.0 | 2024-11-08 |
| `boto3` | 1.43.117 | 2026-10-21 |
| `botocore` | 1.43.117 | 2026-10-21 |
| `certifi` | 2026.10.23 | 2026-10-23 |
| `cffi` | 2.1.1 | 2026-08-03 |
| `charset-normalizer` | 3.5.2 | 2026-09-30 |
| `click` | 8.5.1 | 2026-11-06 |
| `cryptography` | 50.0.2 | 2026-09-30 |
| `flask-cors` | 6.0.5 | 2026-06-08 |
| `Flask` | 3.1.3 | 2026-02-19 |
| `frozenlist` | 1.8.0 | 2025-10-06 |
| `fsspec` | 2026.9.0 | 2026-09-18 |
| `idna` | 3.20 | 2026-09-17 |
| `itsdangerous` | 2.2.0 | 2024-04-16 |
| `Jinja2` | 3.1.6 | 2025-03-05 |
| `jmespath` | 1.1.0 | 2026-01-22 |
| `MarkupSafe` | 3.0.4 | 2026-10-02 |
| `moto` | 5.2.5 | 2026-10-27 |
| `multidict` | 7.2.1 | 2026-10-24 |
| `numpy` | 2.5.4 | 2026-10-10 |
| `pandas` | 3.0.6 | 2026-09-17 |
| `propcache` | 0.5.4 | 2026-09-16 |
| `pycparser` | 3.12 | 2026-10-22 |
| `pydantic` | 2.14.3 | 2026-11-05 |
| `pydantic_core` | 2.50.4 | 2026-11-05 |
| `python-dateutil` | 2.9.0.post0 | 2024-03-01 |
| `PyYAML` | 6.0.3 | 2025-09-25 |
| `requests` | 2.34.2 | 2026-05-14 |
| `responses` | 0.26.3 | 2026-08-26 |
| `s3fs` | 2026.9.0 | 2026-09-18 |
| `s3transfer` | 0.19.3 | 2026-10-19 |
| `six` | 1.17.0 | 2024-12-04 |
| `typing-inspection` | 0.4.5 | 2026-11-04 |
| `typing_extensions` | 4.16.0 | 2026-07-02 |
| `urllib3` | 2.8.0 | 2026-09-15 |
| `Werkzeug` | 3.1.9 | 2026-09-27 |
| `wrapt` | 2.5.2 | 2026-10-29 |
| `xmltodict` | 1.0.4 | 2026-02-22 |
| `yarl` | 1.25.1 | 2026-09-15 |

Observation: three of these pins (`click` 8.5.1, `pydantic` 2.14.3, `typing-inspection` 0.4.5) were
published on 2026-11-04 to 2026-11-06, i.e. less than 14 days ago. They come from the T00 generator
work and are not re-pinned here because `generator/` must not change in T01.

## Pipeline code (T02)

`requirements.txt` holds what the Airflow image does not already ship; the image installs it as the
airflow user and then installs the DuckDB extensions (see `infra/airflow/install-duckdb.sh`).
`requirements-dev.txt` is the host venv for tests and linters.

| Package | Version | Released | Why |
|---|---|---|---|
| `duckdb` | 1.5.6 | 2026-09-28 | Newest 1.5.x and older than 14 days; DuckDB 2.0.0 (2026-10-21) is a major release and not taken for a first pipeline. Has a cp312 manylinux wheel and installs the `httpfs` and `parquet` extensions. |
| `boto3` | 1.43.117 | 2026-10-21 | Host-only, for the manifest and the S3 tests; the same pin the generator already uses. |
| `pytest` | 9.2.0 | 2026-10-27 | Host-only, same version as the generator venv. |
| `ruff` | 0.17.4 | 2026-11-05 | Host-only, newest release older than 14 days; 0.17.5 (2026-11-12) is too new. |
| `mypy` | 2.4.1 | 2026-10-28 | Host-only, same version as the generator venv. |

## dbt virtualenv (T03)

`infra/airflow/install-dbt.sh` creates `/opt/venvs/dbt` and installs from
`infra/airflow/dbt-constraints.txt`, which pins the resolved closure (55 packages). dbt-core and
dbt-duckdb are the only versions chosen by hand; the rest were resolved on Python 3.12 and then pinned
so a rebuild cannot pick a newer one.

| Package | Version | Released | Why |
|---|---|---|---|
| `dbt-core` | 1.11.16 | 2026-10-14 | Newest 1.11 patch older than 14 days, the line the duckdb adapter 1.11.x targets. 1.11.17 (2026-11-06) and 1.12.7 (2026-11-12) are too new. |
| `dbt-duckdb` | 1.11.1 | 2026-10-26 | Newest adapter older than 14 days; requires `duckdb>=1.0.0`, so the 1.5.6 already in the image is used and both venvs share `/home/airflow/.duckdb`. |
| `duckdb` | 1.5.6 | 2026-09-28 | Same pin as the Airflow interpreter (see the T02 table). |
| `dbt-adapters` | 1.24.5 | 2026-07-15 | 1.24.6 (2026-11-17) is newer than the cutoff, so 1.24.5 is pinned. |
| `pydantic` | 2.14.3 | 2026-11-05 | 2.14.4 (2026-11-19) is newer than the cutoff; 2.14.3 is also the generator's pin. |
| `pydantic_core` | 2.50.4 | 2026-11-05 | Must match `pydantic`; 2.50.5 (2026-11-19) is too new. |
| `python-slugify` | 9.1.3 | 2026-10-07 | 9.2.0 (2026-11-16) is newer than the cutoff. |

Everything else in `dbt-constraints.txt` came from the resolver and is pinned as resolved.

## Not yet pinned

- Metabase: T04.
