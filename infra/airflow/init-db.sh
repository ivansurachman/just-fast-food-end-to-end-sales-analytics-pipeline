#!/bin/bash
# One-shot bootstrap for the Airflow metadata database. Runs as the airflow-init service
# before the api-server, scheduler and dag-processor start.
#
# It waits for Postgres itself instead of trusting depends_on: podman-compose 1.6.0 does
# not honour every depends_on condition, so start order alone is not a guarantee.
set -euo pipefail

: "${AIRFLOW_ADMIN_USER:?AIRFLOW_ADMIN_USER is required}"
: "${AIRFLOW_ADMIN_PASSWORD:?AIRFLOW_ADMIN_PASSWORD is required}"
: "${AIRFLOW_ADMIN_EMAIL:?AIRFLOW_ADMIN_EMAIL is required}"

attempt=0
until airflow db check >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 60 ]; then
    echo "Airflow metadata database did not answer after 60 attempts" >&2
    exit 1
  fi
  sleep 2
done

airflow db migrate

if airflow users list -o json 2>/dev/null | grep -q "\"${AIRFLOW_ADMIN_USER}\""; then
  echo "Airflow admin user ${AIRFLOW_ADMIN_USER} already exists"
else
  airflow users create \
    --username "${AIRFLOW_ADMIN_USER}" \
    --password "${AIRFLOW_ADMIN_PASSWORD}" \
    --firstname JFF --lastname Admin --role Admin \
    --email "${AIRFLOW_ADMIN_EMAIL}"
fi
