# Entry point that podman finds without a -f flag, because podman-compose 1.6.0 on Windows
# ignores build.dockerfile: it sees "C:\..." as a git URL and skips the dockerfile lookup
# entirely, then podman looks for Containerfile/Dockerfile in the context root.
#
# The build is described twice on purpose: docker-compose uses
# infra/airflow/Dockerfile (the deliverable path), podman-compose on Windows lands here.
# Both files call infra/airflow/install-generator.sh, so versions live in one place.
FROM docker.io/apache/airflow:3.3.2-python3.12

USER root

ENV PIP_NO_CACHE_DIR=1 \
    JFF_VENV=/opt/venvs/jff

COPY generator/constraints.txt generator/pyproject.toml /tmp/jff/
COPY generator/src /tmp/jff/src
COPY infra/airflow/install-generator.sh infra/airflow/init-db.sh infra/airflow/wait-for-db.sh /opt/jff/

RUN bash /opt/jff/install-generator.sh

USER airflow
