# Airflow 3.3.2 plus the JFF generator in its own virtualenv. dbt is added by a later task.
#
# The single build file for both compose providers: docker-compose reads build.dockerfile from
# compose.yaml, and podman-compose 1.6.0 on Windows ignores that key (it reads the absolute build
# context "C:\..." as a git URL and skips the -f lookup) but finds Containerfile in the context
# root on its own. Package versions live in generator/constraints.txt and
# infra/airflow/install-generator.sh.
FROM docker.io/apache/airflow:3.3.2-python3.12

USER root

ENV PIP_NO_CACHE_DIR=1 \
    JFF_VENV=/opt/venvs/jff

COPY generator/constraints.txt generator/pyproject.toml /tmp/jff/
COPY generator/src /tmp/jff/src
COPY infra/airflow/install-generator.sh infra/airflow/init-db.sh infra/airflow/wait-for-db.sh /opt/jff/

RUN bash /opt/jff/install-generator.sh

USER airflow
