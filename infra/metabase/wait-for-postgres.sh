#!/bin/sh
# Gate for Metabase before its own startup. A depends_on condition is not enough:
# podman-compose 1.6.0 does not honour service_healthy on postgres, and Metabase's JVM takes
# longer than Postgres to accept connections. After the wait the official entrypoint runs.
#
# nc is the only tool needed, and it is already in the metabase image.
set -eu

attempt=0
until nc -z postgres 5432 >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 60 ]; then
    echo "Postgres did not answer on postgres:5432 after 60 attempts" >&2
    exit 1
  fi
  sleep 2
done

exec /app/run_metabase.sh "$@"
