#!/bin/bash
# Gate for the long-running Airflow services. podman-compose 1.6.0 does not honour the
# depends_on completion condition on airflow-init, so each service waits here until the
# metadata schema is migrated, then runs its own command.
set -euo pipefail

attempt=0
until airflow db check-migrations >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 90 ]; then
    echo "Airflow metadata schema is still not migrated after 90 attempts" >&2
    exit 1
  fi
  sleep 2
done

exec "$@"
