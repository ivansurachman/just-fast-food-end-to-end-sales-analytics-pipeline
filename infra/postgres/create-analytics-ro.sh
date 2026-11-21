#!/bin/bash
# Create or refresh the read-only role Metabase uses against the analytics database.
#
# Runs as a one-shot compose service on every `up`, because infra/postgres/init only runs on a fresh
# data volume. Idempotent: the role is created when missing and its password is re-applied otherwise.
# Grants are given for the tables that exist now and, through ALTER DEFAULT PRIVILEGES, for every
# table the loader creates later as the `analytics` role.
set -euo pipefail

: "${PGPASSWORD:?PGPASSWORD (the postgres superuser password) is required}"
: "${POSTGRES_ANALYTICS_RO_PASSWORD:?POSTGRES_ANALYTICS_RO_PASSWORD is required}"

ro_user="${ANALYTICS_RO_USER:-analytics_ro}"
analytics_db="${ANALYTICS_DB:-analytics}"
owner="${ANALYTICS_OWNER:-analytics}"

psql -v ON_ERROR_STOP=1 -h postgres -U postgres -d postgres \
  -v ro_user="${ro_user}" \
  -v ro_password="${POSTGRES_ANALYTICS_RO_PASSWORD}" \
  -v analytics_db="${analytics_db}" <<'SQL'
select format('create role %I login password %L', :'ro_user', :'ro_password')
where not exists (select 1 from pg_roles where rolname = :'ro_user') \gexec
alter role :"ro_user" with login password :'ro_password';
grant connect on database :"analytics_db" to :"ro_user";
SQL

psql -v ON_ERROR_STOP=1 -h postgres -U postgres -d "${analytics_db}" \
  -v ro_user="${ro_user}" \
  -v owner="${owner}" <<'SQL'
grant usage on schema public to :"ro_user";
grant select on all tables in schema public to :"ro_user";
alter default privileges for role :"owner" in schema public grant select on tables to :"ro_user";
SQL

echo "role ${ro_user} can select from ${analytics_db}.public"
