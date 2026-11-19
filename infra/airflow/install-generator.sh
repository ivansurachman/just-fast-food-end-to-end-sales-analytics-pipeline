#!/bin/bash
# Build-time step: create /opt/venvs/jff and install the JFF generator into it with the
# pins from generator/constraints.txt. Runs as root inside the Airflow image.
#
# Both the repo-root Containerfile and infra/airflow/Dockerfile call this script, so the
# package versions live in exactly one place.
set -euo pipefail

python -m venv "${JFF_VENV}"
"${JFF_VENV}/bin/pip" install --upgrade "pip==26.3" "setuptools==84.2.1"
"${JFF_VENV}/bin/pip" install --no-build-isolation -c /tmp/jff/constraints.txt "/tmp/jff[s3]"
rm -rf /tmp/jff
chown -R airflow:root "${JFF_VENV}"
