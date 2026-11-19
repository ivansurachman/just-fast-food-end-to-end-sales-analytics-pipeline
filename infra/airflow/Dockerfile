# Airflow 3.3.2 (released 2026-09-17) plus the JFF generator in its own virtualenv.
# dbt is added by a later task. Package versions live in generator/constraints.txt
# (generator runtime) and infra/airflow/install-generator.sh (pip, setuptools).
#
# The same build is described by the repo-root Containerfile. podman-compose 1.6.0 on
# Windows ignores build.dockerfile because it misreads an absolute build context as a
# git URL, so podman falls back to the Dockerfile in the context root; docker-compose
# uses this path. Keep the two files in step.
FROM docker.io/apache/airflow:3.3.2-python3.12

USER root

ENV PIP_NO_CACHE_DIR=1 \
    JFF_VENV=/opt/venvs/jff

COPY generator/constraints.txt generator/pyproject.toml /tmp/jff/
COPY generator/src /tmp/jff/src
COPY infra/airflow/install-generator.sh infra/airflow/init-db.sh infra/airflow/wait-for-db.sh /opt/jff/

RUN bash /opt/jff/install-generator.sh

USER airflow
