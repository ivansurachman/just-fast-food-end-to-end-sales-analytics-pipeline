#!/bin/bash
# Build-time step: create /opt/venvs/dbt with dbt-core and dbt-duckdb, pinned by
# infra/airflow/dbt-constraints.txt. Runs as root inside the Airflow image; the venv is handed to
# the airflow user at the end, because the DAG runs dbt as airflow.
#
# duckdb is pinned to the same 1.5.6 as the Airflow interpreter, so both venvs share the extension
# directory /home/airflow/.duckdb (extensions are keyed by DuckDB version and platform).
set -euo pipefail

DBT_VENV=/opt/venvs/dbt

python -m venv "${DBT_VENV}"
"${DBT_VENV}/bin/pip" install --upgrade "pip==26.3"
"${DBT_VENV}/bin/pip" install --no-cache-dir -c /opt/jff/dbt-constraints.txt \
  "dbt-core==1.11.16" "dbt-duckdb==1.11.1"

"${DBT_VENV}/bin/dbt" --version
chown -R airflow:root "${DBT_VENV}"
