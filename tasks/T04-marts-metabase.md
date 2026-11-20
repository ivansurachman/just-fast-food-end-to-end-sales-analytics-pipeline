# T04: marts in PostgreSQL, Metabase, full backfill

Serves: 22 Nov checkpoint (Sunday). Branch: `task/T04-marts`.
Prerequisite: T03 accepted by Ivan. Scope is **one mart, one dashboard page, one end-to-end run over 45 days**. P2 metrics, other marts and more pages are out until after 22 Nov.

Read first: `docs/pipeline-design.md` sections 5, 8; `docs/data-model.md` (metric definitions M1 to M8).

## Deliverables

| Path | Content |
|---|---|
| `dbt/models/marts/mart_sales_day_branch_channel.sql` | Grain: `order_date`, branch, channel. Numerators and denominators only, never finished ratios (counts of orders by status, gross, discount, net, cogs, commission as defined in `docs/data-model.md`). Incremental on `order_date`, same window as silver |
| `pipelines/load_marts.py` | DuckDB to PostgreSQL with `psycopg` `COPY`. For the window: `DELETE` the window rows and `COPY` the new ones in one transaction. CLI `--ds`, `--lookback-days`. Connection from env, no secrets in code |
| `pipelines/sql/marts.sql` | `CREATE TABLE IF NOT EXISTS` for the mart and an index on `order_date`, applied idempotently by `load_marts` |
| `infra/postgres/` | Script that creates read-only role `analytics_ro` (SELECT on the mart) on an existing volume, idempotent. The init SQL only runs on a fresh volume, so do not rely on it |
| `compose.yaml` | Service `metabase`: pinned image older than 14 days, `mem_limit: 1400m`, `-Xmx768m`, app database = `metabase` on the compose Postgres, port `127.0.0.1:3000:3000`, healthcheck on `/api/health`, `depends_on` plus a retry for Postgres |
| `dashboards/sales_overview/*.sql` | The SQL of each dashboard card, one file per card |
| `dags/jff_daily.py` | `load_marts` placeholder replaced by the real task |
| `docs/versions.md`, `docs/verification/T04-marts.md` | Pins and evidence |

Dashboard "Sales overview" has three cards: net sales per day (line), orders by channel (bar), top 10 branches by net sales (table). Create the Metabase connection (user `analytics_ro`), the three native-SQL questions and the dashboard through the Metabase REST API on `localhost`, not by clicking. Use the `browser` skill only to take one screenshot of the dashboard at `http://localhost:3000`, and never open any other address.

## Rules

- Load `lean-code` and `podman-windows` first.
- Metabase credentials come from `.env`. The first-run setup uses an admin account from `.env`; do not hard-code a password.
- Tables in Postgres are idempotent targets: re-running a date must not change the mart.

## Acceptance (evidence for each)

1. Compose starts with Metabase: all healthy, limits visible with `podman inspect`, total of all containers against 5.6 GB, and `podman machine ssh free -m` showing at least 1 GiB available.
2. Generate 2026-10-01 to 2026-11-14 at scale 0.1 inside the scheduler container (seed 42), then run the DAG for the whole range (`airflow backfill create`). Report: total time, run states, peak scheduler `anon` memory, and `free -m` before and after.
3. Idempotence: re-run one date in the middle. Hash of the mart rows for that date's window is identical before and after.
4. Reconciliation (show all three):
   a. total net sales and order count per day in the Postgres mart equal the same numbers computed directly from `fact_order` in DuckDB;
   b. for one clean day, the mart's order count equals the number of distinct `order_id` in the raw CSV, after removing the duplicates reported in the manifest;
   c. the three dashboard cards return the same totals as the SQL files run in `psql`.
5. A screenshot of the dashboard saved at `docs/slides/img/dashboard-sales-overview.png`.
6. The full chain from one cold start: `podman compose down`, `up -d`, generate one new day, trigger the DAG, and see the day on the dashboard. Time it.
7. `ruff`, `mypy`, `pytest` clean.

## STOP conditions

- Metabase does not support Postgres 18 for its application database (check its documentation first). Report; Ivan decides between Postgres 17 (needs `down -v`) and another option.
- Total memory exceeds 5.6 GB, a container is OOM-killed, or less than 1 GiB is available in the VM.
- The backfill takes longer than 90 minutes. Report the time per day and stop; Ivan decides how many days the demo needs.
