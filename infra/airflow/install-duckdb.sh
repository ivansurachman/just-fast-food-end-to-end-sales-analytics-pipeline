#!/bin/bash
# Build-time step: DuckDB for the Airflow interpreter, plus the httpfs and parquet extensions.
#
# Runs as the airflow user (see the Containerfile), so the site-packages and the extensions land in
# /home/airflow and are readable by the api-server, scheduler and dag-processor at run time. That is
# what lets a run work without internet: nothing is downloaded when a DAG executes.
set -euo pipefail

python -m pip install --no-cache-dir -r /opt/jff/requirements.txt

python - <<'PY'
import duckdb

con = duckdb.connect()
for extension in ("httpfs", "parquet"):
    con.execute(f"INSTALL {extension}")
con.close()
print("duckdb", duckdb.__version__, "with httpfs and parquet")
PY
