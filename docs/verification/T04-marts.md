# T04 verification: marts in PostgreSQL, Metabase, full backfill

Task: `tasks/T04-marts-metabase.md`. Branch `task/T04-marts`. Started 2026-11-21.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Model run: `opencode-go/deepseek-v4.1-flash` (the model in `opencode.json`).

Only commands that were run are recorded. Anything not run is written as "not run".
Part A is complete; Part B and Part C follow in the same file.

## Part A: mart and load

### What was built

| Path | What it is |
|---|---|
| `dbt/models/marts/mart_sales_day_branch_channel.sql` | Grain `(order_date, branch_key, channel_key)`. Counts by status plus gross, discount, net, cogs and commission of completed orders. No finished ratios: M3 is `net_amount / completed_orders` and M4 is `cancelled_orders / total_orders` at query time |
| `dbt/tests/assert_mart_grain_unique.sql` | The three-column grain is unique |
| `pipelines/sql/marts.sql` | `CREATE TABLE IF NOT EXISTS` with the primary key on the grain and an index on `order_date`, applied on every load |
| `pipelines/load_marts.py` | DuckDB (read-only) -> `psycopg` `COPY`; `DELETE` the window and `COPY` in one transaction; CLI `--ds`, `--lookback-days`, `--duckdb-path`; connection from the `PG*` variables |
| `infra/postgres/create-analytics-ro.sh` | Creates/refreshes `analytics_ro`, grants `SELECT` on the analytics schema and `ALTER DEFAULT PRIVILEGES` for tables the loader creates later |
| `compose.yaml` | One-shot `postgres-ro` service (256m, not counted in the budget), `PG*` variables for the Airflow services |
| `dags/jff_daily.py` | `load_marts` is a `BashOperator` running `/opt/venvs/dbt/bin/python -m pipelines.load_marts --ds {{ ds }} --lookback-days 10` on pool `duckdb_writer` |
| `infra/airflow/install-dbt.sh`, `dbt-constraints.txt` | `psycopg[binary]==3.3.8` added to the dbt virtualenv, so there is no third venv |

`postgres-ro` on every `up`:

```
podman logs jff_postgres-ro_1
ALTER ROLE
GRANT
GRANT
GRANT
ALTER DEFAULT PRIVILEGES
role analytics_ro can select from analytics.public
```

The target table in PostgreSQL:

```
\d mart_sales_day_branch_channel
 order_date        | date      | not null
 branch_key        | integer   | not null
 channel_key       | text      | not null
 total_orders      | bigint    | not null
 completed_orders  | bigint    | not null
 cancelled_orders  | bigint    | not null
 refunded_orders   | bigint    | not null
 gross_amount      | bigint    | not null
 discount_amount   | bigint    | not null
 net_amount        | bigint    | not null
 cogs_amount       | bigint    | not null
 commission_amount | bigint    | not null
Indexes:
    "mart_sales_day_branch_channel_pkey" PRIMARY KEY, btree (order_date, branch_key, channel_key)
    "mart_sales_day_branch_channel_order_date_idx" btree (order_date)
```

`analytics_ro` reads it: `select count(*), sum(net_amount) ...` -> `3768 | 1024171650`, exit 0.

### Window change approved by Ivan (design section 6)

The first attempt at item 3 failed: re-running 2026-10-06 through the DAG dropped 40 orders of that
day (2251 -> 2211) because their file is `dt=2026-10-07`, outside the window `[09-26, 10-06]` that
the staging views were clipped to. Ivan chose option A: the staging views no longer have an upper
bound, so a partition is a pure function of the bronze content, and the read is pruned only by
`window_start`. `docs/pipeline-design.md` section 6 was updated with that rule and with the new guard.

The guard was changed at the same time from "a change older than `run_date - lookback_days`" to a
lag rule with no `run_date`: for every change, `source_file_date - order_date <= lookback_days`.
Two tests had to follow the new semantics (`assert_silver_matches_bronze_orders` no longer filters
bronze by `source_file_date <= run_date`).

### The seven sample days, end to end through the DAG

DuckDB file deleted first, so the first run builds everything. Each row is one
`airflow dags test jff_daily <ds>`:

| Run date | exit | wall | mart rows loaded | dbt tests |
|---|---|---|---|---|
| 2026-10-03 | 0 | 31.2 s | 536 for 2026-09-23 .. 2026-10-03 | PASS=48 |
| 2026-10-04 | 0 | 33.2 s | 1080 | PASS=48 |
| 2026-10-05 | 0 | 33.8 s | 1615 | PASS=48 |
| 2026-10-06 | 0 | 31.7 s | 2151 | PASS=48 |
| 2026-10-07 | 0 | 31.0 s | 2688 | PASS=48 |
| 2026-10-08 | 0 | 32.5 s | 3223 | PASS=48 |
| 2026-10-09 | 0 | 31.2 s | 3768 | PASS=48 |

PostgreSQL after the last run: `3768` rows, `8` distinct dates (2026-10-02 to 2026-10-09; the two
2026-10-02 orders are late arrivals from the 2026-10-03 file).

### Item 3: re-running a middle date is a fixpoint

Window `2026-09-26 .. 2026-10-06`, hashed before and after `airflow dags test jff_daily 2026-10-06`
(the later files 10-07..10-09 exist, which is the case that used to break):

```
before                                        after
duck window silver_orders        9640 4b2ad1ec...  identical
duck whole  silver_orders      125219 bba525f1...  identical
duck window silver_order_items  23574 4935a2a8...  identical
duck whole  silver_order_items 304991 a1bd5d75...  identical
duck window silver_order_changes   84 09477aee...  identical
duck whole  silver_order_changes  331 0662b874...  identical
duck window mart               2151 0f8c94b9...   identical
duck whole  mart               4345 b1049093...   identical
pg   window mart               2151 f72322b8...   identical
pg   whole  mart               3768 803f3612...   identical
diff: identical
```

Hash = `md5(string_agg(row as text order by row as text))`, so it covers every column of every row.

The extra check Ivan asked for ("re-run three random dates after the backfill, all silver and mart
hashes unchanged") belongs to Part C and is recorded there.

Verdict: **pass** for the seven sample days.

### Item 4a: mart vs fact_order, per day

```
date         pg_total dk_total pg_compl dk_compl       pg_net       dk_net same
2026-10-02          2        2        2        2       108000       108000 True
2026-10-03       2699     2699     2570     2570    164771850    164771850 True
2026-10-04       2476     2476     2364     2364    149385250    149385250 True
2026-10-05       2212     2212     2117     2117    136180400    136180400 True
2026-10-06       2251     2251     2159     2159    138624400    138624400 True
2026-10-07       2296     2296     2184     2184    140221150    140221150 True
2026-10-08       2329     2329     2229     2229    141440000    141440000 True
2026-10-09       2547     2547     2443     2443    153440600    153440600 True
mismatches=0
```

`fact_order` also holds 2026-10-19 and 2026-10-20 (the full-scale day T03 loaded for its memory
test); those dates are outside every window this task loaded, so the mart does not claim to have
them. Part C regenerates 2026-10-01..11-14 at scale 0.1, which replaces that day.

Verdict: **pass** for the loaded days.

### Item 4b: mart count against the raw CSV

The task asks for one clean day. None of the seven days is clean - every one has late orders in or
out - so the full identity is shown for all of them instead:

`mart_total(d) = distinct order_id in the CSV of d - late_orders_delayed_in(d) + late_orders_delayed_out(d)`

| Day | CSV rows | distinct | dup | late_in | late_out | mart total | identity |
|---|---|---|---|---|---|---|---|
| 2026-10-03 | 2683 | 2670 | 13 | 2 | 31 | 2699 | 2670 - 2 + 31 = 2699 |
| 2026-10-04 | 2505 | 2492 | 13 | 31 | 15 | 2476 | 2492 - 31 + 15 = 2476 |
| 2026-10-05 | 2201 | 2194 | 7 | 15 | 33 | 2212 | 2194 - 15 + 33 = 2212 |
| 2026-10-06 | 2255 | 2244 | 11 | 33 | 40 | 2251 | 2244 - 33 + 40 = 2251 |
| 2026-10-07 | 2339 | 2325 | 14 | 40 | 11 | 2296 | 2325 - 40 + 11 = 2296 |
| 2026-10-08 | 2337 | 2325 | 12 | 11 | 15 | 2329 | 2325 - 11 + 15 = 2329 |
| 2026-10-09 | 2579 | 2562 | 17 | 15 | 0 | 2547 | 2562 - 15 + 0 = 2547 |

The duplicates in the manifest are already gone before the mart: `distinct` counts the CSV by
`order_id`, which is exactly the dedup silver does. On a day with no late orders in or out the
identity reduces to `mart_total = distinct`, which is the equality the task describes. Part C checks
that form on the 45-day range if such a day exists there.

Verdict: **pass**, with the reason no single clean day exists in the sample.

### Item 4d: changes whose order is not in the dataset

```
orphan_rows=740
  order date 20260927: 2      order date 20261012: 9    order date 20261016: 61
  order date 20260928: 1      order date 20261013: 20   order date 20261017: 131
  order date 20260929: 1      order date 20261014: 15   order date 20261018: 178
  order date 20260930: 2      order date 20261015: 36   order date 20261019: 260
  order date 20261001: 10     order date 20261020: 209
  order date 20261002: 14
```

At this point bronze still holds the T03 full-scale day (`dt=2026-10-20`), whose 919 refunds point at
orders from 2026-10-12 to 2026-10-20, and the seven-day database has only the orders of those two
days. The 30 rows for 2026-09-27..2026-10-02 are the T03 finding: 16 of them (10-01 and 10-02) are
resolved as soon as those days exist. Part C re-measures this on the 45-day dataset, where the
expected number is the 6 rows for 2026-09-27..2026-09-30.

Not a bug: a change whose order has not been ingested yet cannot be attributed to a partition.

Verdict: **recorded**, re-measured in Part C.

### Lookback guard, lag rule

Passing on the real data:

```
dbt build --select assert_lookback_window --vars '{run_date: 2026-10-09, lookback_days: 10}'
1 of 1 PASS assert_lookback_window
```

Failing on one hand-made row: a refund for `B001-20261003-00001` placed in a file dated 2026-10-14,
so `lag = 11` days. The object was written to
`bronze/order_changes/source_file_date=2026-10-14/order_changes.parquet`, a partition that holds no
real data.

```
1 of 1 FAIL 1 assert_lookback_window
Failure in test assert_lookback_window (tests/assert_lookback_window.sql)
  Got 1 result, configured to fail if != 0
```

The object was then deleted and the test passed again (`1 of 1 PASS`). The guard does not use
`run_date`, so the same row fails on every run until it is fixed.

### T03 re-verification after the window change (Ivan's requirement)

```
dbt build --vars '{run_date: 2026-10-09, lookback_days: 10}'
Finished running 6 incremental models, 1 seed, 5 table models, 48 data tests, 7 view models in 3.88s
Done. PASS=67 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=67
```

Refunds for the T03 window (2026-10-03 .. 2026-10-09), unchanged from T03 acceptance 4:

```
silver changes (rows, distinct order): 122, 122
fact_order refunded                  : 122
refunded without a change row        : 0
change row without a refunded order  : 0
lag distribution (days): 0:37, 1:42, 2:21, 3:13, 4:5, 5:2, 6:2
```

The whole database now also holds the T03 full-scale day: 1071 bronze changes, 331 silver changes,
331 refunded orders, still 0 mismatches in both directions.

Verdict: **pass**, T03 results unchanged.

### Linters

```
python -m ruff check .            -> All checks passed!
python -m ruff format --check .   -> 47 files already formatted
python -m mypy                     -> Success: no issues found in 10 source files
```

`pytest` is unchanged by Part A (no test touches the loader yet) and runs at the end of the task.

## Part B: Metabase

### The PostgreSQL 18 STOP condition

`docs.metabase.com` is not reachable from this machine (transport error, root and path). With Ivan's
permission the same documentation page was read on `www.metabase.com`:

> Metabase supports the oldest supported version of PostgreSQL through the latest stable version.
> (docs/latest/installation-and-operation/configuring-application-database)

PostgreSQL 18 is the latest stable release, so it is supported as the application database. The
operational proof is below: Metabase ran its migrations against it and became healthy.

### Service

`docker.io/metabase/metabase:v0.65.3`, released 2026-11-06 (newest tag older than 14 days; v0.65.6
and v0.64.8 are from 2026-11-18). `mem_limit: 1400m`, `JAVA_OPTS: -Xmx768m`, application database
`metabase` on the compose Postgres, `127.0.0.1:3000:3000`, healthcheck on `/api/health` with a 120 s
start period.

```
podman compose up -d metabase
state=healthy settled_seconds=48.7
curl http://127.0.0.1:3000/api/health -> {"status":"ok"} (200)
GET /api/session/properties -> version v0.65.3
```

The first start also answered the STOP condition: the app database migrations ran against
PostgreSQL 18.4 without an error.

### The retry to Postgres (deliverable: "depends_on plus a retry")

`infra/metabase/wait-for-postgres.sh` is the service entrypoint: it loops on `nc -z postgres 5432`
(60 attempts, 2 s apart) and then `exec`s `/app/run_metabase.sh`. What was measured:

- a normal cold start waits, then Metabase starts (item 6 timings);
- `podman restart jff_metabase_1` while postgres is paused is refused by podman itself:
  `some dependencies of container ... are not started`, so the runtime also enforces the dependency;
- a throwaway container on the compose network, started with the same wrapper and the same app-DB
  variables while postgres was paused, showed the residual gap and the **retry behaviour**: `nc` passes
  as soon as the kernel accepts on the listening socket, the JVM starts, and then Metabase retries its
  own app database:

```
WARN app-db.connection-pool-setup :: metabase-postgres-app-db pool did not hand out a connection within 3000 ms
WARN app-db.connection-pool-setup :: metabase-postgres-app-db pool still unresponsive after rebuild
INFO core.core :: Setting up and migrating Metabase DB...
INFO app-db.setup :: Verifying postgres Database Connection ...
(kept retrying until the 60 s cap of the probe killed it, exit 124)
```

- the running instance was also put through a full pause and back:

```
card 40 query with postgres up            -> 47 rows
podman pause jff_postgres_1, wait 10 s
card 40 query while paused                -> request timed out (the pool cannot hand out a connection)
podman unpause jff_postgres_1
card 40 query after unpause               -> 47 rows again
/api/health                               -> {"status":"ok"}
container                                 -> running healthy
```

So `nc` proves the port accepts a connection, not that the database answers. After the gate, the retry
is Metabase's own connection pool plus `restart: unless-stopped`: the probe above shows the retries and
the pause/unpause run shows the service recovering once Postgres answers again. The probe container was
created for the test only and removed by `--rm`.

### Setup through the REST API

`dashboards/setup.py` (standard library only, credentials from `.env`) does first-run setup, logs in,
creates the `JFF analytics` connection as `analytics_ro`, the three native-SQL questions and the
dashboard. It is idempotent: a second run reuses what exists.

```
INFO first-run setup finished for admin@justfastfood.local
INFO database JFF analytics created (id 2)
INFO card Net sales per day created (id 40)
INFO card Orders by channel created (id 41)
INFO card Top 10 branches by net sales created (id 42)
INFO dashboard Sales overview created (id 2)
INFO dashboard Sales overview (id 2) has 3 cards
dashboard_url=http://localhost:3000/dashboard/2
cards=Net sales per day (id 40), Orders by channel (id 41), Top 10 branches by net sales (id 42)
```

Card SQL lives in `dashboards/sales_overview/`: `net_sales_per_day.sql` (line),
`orders_by_channel.sql` (bar), `top_branches_by_net_sales.sql` (table).

### Item 4c: the cards equal the SQL run in psql

`POST /api/card/{id}/query` compared row by row with `psql -f` on the same files:

```
Net sales per day                psql_rows=  8 card_rows=  8 identical=True   total 1024171650
Orders by channel                psql_rows=  5 card_rows=  5 identical=True   total 16812
Top 10 branches by net sales     psql_rows= 10 card_rows= 10 identical=True   total 147492850
```

Verdict: **pass**.

### Item 1: the stack with Metabase

```
podman ps -a
jff_postgres_1          Up 47 minutes (healthy)
jff_seaweedfs_1         Up 47 minutes (healthy)
jff_postgres-ro_1       Exited (0)
jff_seaweedfs-init_1    Exited (0)
jff_airflow-init_1      Exited (0)
jff_airflow-api-server_1 Up 46 minutes (healthy)
jff_airflow-scheduler_1  Up 46 minutes
jff_airflow-dag-processor_1 Up 46 minutes
jff_metabase_1          Up 3 minutes (healthy)
```

Limits from `podman inspect .HostConfig.Memory`:

| Container | Limit | Kind |
|---|---|---|
| postgres | 600 MB | long-running |
| seaweedfs | 600 MB | long-running |
| airflow-api-server | 800 MB | long-running |
| airflow-scheduler | 1700 MB | long-running |
| airflow-dag-processor | 500 MB | long-running |
| metabase | 1400 MB | long-running |
| **total** | **5600 MB** | the plafon from `docs/pipeline-design.md` section 2, not a usage |
| postgres-ro / seaweedfs-init / airflow-init | 256 / 256 / 512 MB | one-shot, not counted (Ivan's decision) |

Real usage (`podman stats --no-stream`) and the VM:

```
jff_postgres_1            146.4MB / 629.1MB   23%
jff_seaweedfs_1           178.2MB / 629.1MB   28%
jff_airflow-api-server_1  261.8MB / 838.9MB   31%
jff_airflow-scheduler_1   568.9MB / 1.783GB   32%
jff_airflow-dag-processor_1 205.3MB / 524.3MB 39%
jff_metabase_1            1.395GB / 1.468GB   95%   <- see the note below
podman machine ssh free -m: total 7822, used 3239, free 701, buff/cache 4125, available 4583
```

No OOM kill anywhere (`podman inspect .State.OOMKilled` false, `memory.events oom_kill 0`).

**Finding to watch.** Metabase sits at 95% of its own limit and the memory is anonymous, not page
cache (`memory.stat`: `anon` 1.317 GB, `file` 12 MB), so the kernel cannot reclaim it:

```
cat /sys/fs/cgroup/memory.current  -> 1403658240   (1338 MiB of 1400 MiB)
cat /sys/fs/cgroup/memory.peak     -> 1409609728   (1344 MiB)
```

With `-Xmx768m` the heap is bounded; the remaining ~550 MB is JVM non-heap (metaspace, code cache,
threads). The limit is the one the task specifies, so it was not raised. Headroom is about 60 MB: a
heavy dashboard query during a backfill is the case to watch, and the container would need a lower
`-Xmx` or a larger limit decided by Ivan, not by me.

Verdict for item 1: **pass** - all services healthy, limits visible, long-running total is the 5600 MB
plafon, and 4.5 GB is available in the VM (far above the 1 GiB floor), with the Metabase headroom
recorded as a finding.

### Item 5: Ivan's screenshot

Dashboard: **http://localhost:3000/dashboard/2** ("Sales overview"), cards "Net sales per day",
"Orders by channel", "Top 10 branches by net sales". Log in with the admin e-mail in
`MB_ADMIN_EMAIL` (`admin@justfastfood.local`) and the password in `MB_ADMIN_PASSWORD` in `.env`.
Ivan saves the screenshot at `docs/slides/img/dashboard-sales-overview.png`; not taken by me (no
browser skill).

## Part C: full backfill

### Item 2: 45 days through the DAG

Generation inside the scheduler container (54.6 s):

```
jff-gen generate --out s3://jff-raw --s3-endpoint http://seaweedfs:8333 \
    --start 2026-10-01 --end 2026-11-14 --scale 0.1
45 days, 184 objects in jff-raw, 114.7 MB
```

```
airflow backfill create --dag-id jff_daily --from-date 2026-10-01 --to-date 2026-11-14
runs_created=45
```

The scheduler ran 38 of them (the other 7 dates already had a run from Part A and
`--reprocess-behavior none` reuses it), one at a time through `max_active_runs=1` and the
`duckdb_writer` pool:

| Reading | Value |
|---|---|
| Wall time, 38 backfill runs | **19.2 min** (about 30 s per run) |
| Extra time to re-run the 7 older days after the scale changed (see the finding) | 4.2 min |
| Total for all 45 dates | **23.4 min** (the STOP line is 90 min) |
| Run states | all `success`: 46 runs over 46 dates at the end (the 45 days of this section plus 2026-11-15, added by the review follow-up), no failure and no retry left behind |
| Peak scheduler `anon` (sampled every 10 s) | **1344 MiB** (79% of the 1700 MiB limit) |
| Peak `memory.current` (anon + page cache) | 1551 MiB |
| `memory.peak` | 1.782.579.200 B = the 1700 MiB ceiling: the cgroup reached its limit and the kernel reclaimed page cache; `oom_kill 0`, `oom 0` |
| `podman machine ssh free -m` before | total 7822, used 3493, available **4329** |
| `podman machine ssh free -m` after | total 7822, used 4049, available **3772**, swap used 115 MB |

No container was OOM-killed (`podman inspect .State.OOMKilled` false, `memory.events oom_kill 0`).
Afterwards PostgreSQL holds `26.266` mart rows over `47` dates (2026-09-30 to 2026-11-15),
`552.655` orders and `35.195.073.350` of net sales. The 46th day comes from the review follow-up
below; this section measured 45 days and the numbers for those 45 are the ones in the table.

**Finding while running the backfill.** `backfill create` skips dates that already have a run, so the
seven days from Part A kept the bronze of the 0.02 dataset while the rest of the range was regenerated
at 0.1. That showed up as 740 orphan refunds for 2026-10-03..2026-10-09. Re-running those seven dates
(`airflow dags test` per day, 4.2 min total) rebuilt their bronze from the new raw and the orphans
disappeared. A backfill on a range that was already run should use
`--reprocess-behavior completed`, or the days must be re-run after a scale change.

### Item 4a: mart vs fact_order on the whole range

One query per side, both printed by the reconciliation script, compared day by day:

```sql
-- Postgres
select order_date, sum(total_orders)::bigint, sum(completed_orders)::bigint, sum(net_amount)::bigint
from mart_sales_day_branch_channel group by 1 order by 1;

-- DuckDB
select cast(order_ts_local as date) as order_date, count(*),
       count(*) filter (where status_final = 'completed'),
       coalesce(sum(net_amount) filter (where status_final = 'completed'), 0)
from fact_order group by 1 order by 1;
```

Last rows and the verdict (the complete 47-row table is Appendix A, generated from the same run):

```
2026-11-13       12967     12967     12423     12423    838518250    838518250 True
2026-11-14       13404     13404     12888     12888    870181350    870181350 True
2026-11-15       12025     12025     11588     11588    776513600    776513600 True
days=47 mismatches=0
```

Verdict: **pass** for all 47 days.

### Item 4b: the CSV identity, every day, with Ivan's waiver

No day in the generated range is clean: every manifest carries late orders in or out, so the literal
form the task describes (`mart = distinct`) cannot be produced by this generator. Ivan accepted the
general identity as the waiver (2026-11-21):

`mart_total(d) = distinct order_id in the CSV of d - late_orders_delayed_in(d) + late_orders_delayed_out(d)`

```
days_checked=46 identity_holds=45
  exception 2026-11-15: distinct=12208 late_in=183 late_out=45 expected=12070 mart=12025 diff=-45
```

45 of the 46 days obey it exactly. The single exception is the last generated day (2026-11-15): its
45 late orders live in a file dated 2026-11-16, which does not exist, so they can never arrive. That
is the documented "yesterday's number is provisional until the next run" property, now confined to
the newest day instead of the whole window: 2026-11-14 went from 13.221 to 13.404 orders once
2026-11-15 was processed, so it is final.

Verdict: **pass under Ivan's waiver**, with the one edge day stated.

### Item 4d: changes whose order is not in the dataset

One query, so the total and the breakdown come from the same result set:

```sql
select c.change_id, c.order_id, c.source_file_date, split_part(c.order_id, '-', 2) as order_day
from read_parquet('s3://jff-lake/bronze/order_changes/*/order_changes.parquet',
                  hive_partitioning = true) c
left join silver_orders o on o.order_id = c.order_id
where o.order_id is null
order by c.order_id;
```

```
orphan_rows=166
  order date 20260923: 2    order date 20260928: 25   order date 20261002: 1
  order date 20260924: 4    order date 20260929: 38   order date 20261027: 2
  order date 20260925: 8    order date 20260930: 62
  order date 20260926: 10   order date 20260927: 14
```

The 166 rows themselves, `change_id` / `order_id` / `source_file_date`, are in Appendix B; they come
from the same query and the same run as the counts above.

Two causes, neither a pipeline bug:

- **163 rows** reference orders dated 2026-09-23..2026-09-30. The dataset starts on 2026-10-01 and a
  refund can reach 8 days back, so the generator writes refunds for orders it never produced. The task
  estimated about 6 at scale 0.02; at scale 0.1 the same defect produces 163.
- **3 rows** reference branch-days the generator dropped: `B111-20261002-00031` on 2026-10-02 (branch 111,
  in `dropped_branch_ids` of that manifest) and `B019-20261027-00013` plus `B019-20261027-00062` on
  2026-10-27 (branch 19, also listed as dropped). The missing branch-day defect means the order was
  never written while a later file still carries its refund.

An earlier version of this section quoted 740 (an earlier database state, and the number was cut off
by the console filter); 166 is the count of the query above on the final data.


### Ivan's added check: three random dates after the backfill

Dates drawn with `Get-Random -Count 3 -SetSeed 42`: **2026-11-02, 2026-11-04, 2026-11-13**.
Every silver table and the mart were hashed (whole table, every column of every row) before and after
re-running those three dates through the DAG:

```
before                                                  after
silver_orders        540447 95001c49...  identical
silver_order_items  1315840 85ad8a92...  identical
silver_order_changes   4021 cf1d7789...  identical
mart (duckdb)         25693 749dec9a...  identical
mart (postgres)       25693 dc60fa89...  identical
diff: identical
```

Each re-run took 36-38 s.

### Item 6: the whole chain from a cold start, with a new day

```
podman compose down             31.0 s
podman compose up -d            94.0 s
all healthy (Metabase incl.)   151.7 s total
```

Then a day the pipeline had never seen (2026-11-15 was outside the old `end_date`, so it had no
bronze and no mart row):

```
generate 2026-11-15              3.2 s   12.271 orders
airflow dags test jff_daily 2026-11-15   44.8 s, exit 0
  bronze orders 2026-11-15: 12271 rows
  dbt: PASS=1 (seed), PASS=18 (run), PASS=48 (test)
  loaded 6282 rows for 2026-11-05 .. 2026-11-15 into mart_sales_day_branch_channel
```

The day is on the dashboard: card "Net sales per day" went from 46 to 47 rows and now returns
`2026-11-15 = 776.513.600`, total `35.195.073.350`. The mart went from 46 to 47 dates, and the day
before became final in the same run:

```
before: 46 dates, max order_date 2026-11-14, 2026-11-14 orders 13221
after : 47 dates, max order_date 2026-11-15, 2026-11-15 orders 12025, 2026-11-14 orders 13404
```

The 183 orders of 2026-11-14 that live in the 2026-11-15 file are now applied, which is why the
window grew by one day (see Review follow-ups).

Total from `down` to data on the dashboard: 151.7 s of startup + 3.2 s generate + 44.8 s run =
about 200 s.

### Item 7: linters and tests

```
python -m ruff check .            -> All checks passed!
python -m ruff format --check .   -> 49 files already formatted
python -m mypy                     -> Success: no issues found in 11 source files
python -m pytest -q                -> 14 passed in 19.28s    (with S3_* exported)
```

`pytest` now includes `pipelines/tests/test_load_marts.py` (4 tests: window arithmetic, the empty
window still applying the schema and the delete, `load_marts` on an empty window, and only in-window
rows being copied).

### Item 5: Ivan's screenshot

Still open: the dashboard is at **http://localhost:3000/dashboard/2** (cards "Net sales per day",
"Orders by channel", "Top 10 branches by net sales") and Ivan saves the screenshot at
`docs/slides/img/dashboard-sales-overview.png`.

## Review follow-ups (2026-11-21)

The `reviewer` subagent rejected the first submission (4b, 4d, 6 and a loader bug). What changed:

| Finding | Fix |
|---|---|
| **Loader left stale rows on an empty window** (`replace_window` was skipped) | `load_marts` now always calls `replace_window`, which applies the DDL and the `DELETE` even with zero rows; four regression tests in `pipelines/tests/test_load_marts.py` |
| **Item 6 did not show a new day** (11-15 was outside `end_date`, so the run had no tasks) | Ivan approved `end_date = 2026-11-15`; the cold start below processes 2026-11-15 for the first time and the dashboard gains the date |
| **4d numbers inconsistent and sample rows from another run** | Section 4d quotes one query and the numbers from that run; **Appendix B** lists all 166 rows `change_id`/`order_id`/`source_file_date`, generated from the same capture as the counts |
| **4a full range not shown** | Section 4a includes both SQL statements, **Appendix A** holds the complete 47-row comparison and `mismatches=0` |
| **Run list not shown, double-run not verifiable** | **Appendix C** lists every run (logical date, `run_id`, type, state): 46 runs over 46 dates, one per date |
| **4b literal form impossible** | Ivan accepted the late-arrival identity as a waiver; 45 of 46 days hold, the exception is the last generated day |
| **Metabase had no explicit Postgres retry** | `infra/metabase/wait-for-postgres.sh` as the entrypoint, with the paused-postgres probe and its limitation recorded in Part B |
| **Comment still said "clipped to run_date"** | `dbt/models/silver/silver_orders.sql` header updated to the new read rule |
| **`requirements-dev.txt` had a BOM and a stray blank line** | rewritten as UTF-8 without BOM, LF, one trailing newline |
| **Design doc still said 45 days** | `docs/pipeline-design.md` D5 now says 46 days (2026-10-01 to 2026-11-15) and why. `docs/slides/make_charts.py`'s caption describes the profiling dataset passed to it, not the demo window, so it stays |
| Metabase at 95% of its limit | Ivan decided to keep `-Xmx768m` and the 1400m limit and to record the headroom as a finding (below) |

`airflow dags test` on a date after `end_date` still closes the run as successful without creating any
task (that is what happened with 2026-11-15 before the extension). It is recorded here so nobody reads
such a green run as a processed day.

## Findings to hand over

1. Metabase memory is at 95% of its own 1400m limit and almost all of it is anonymous (1.317 GB of
   `anon` against 12 MB of page cache). Not an OOM, no limit raised (Ivan, 2026-11-21: keep `-Xmx768m`
   and record it); with the 5600 MB ceiling there is no headroom to give it more without taking it from
   another service. After the restart in the item 6 run it settled at 1.275 GB (87%).
2. The newest generated day is always provisional: 2026-11-15 misses its 45 late orders because they
   would live in a 2026-11-16 file that does not exist. Extending the window by one day moved this from
   2026-11-14 (now final at 13.404 orders) to 2026-11-15. Every further extension just moves the edge.
3. `airflow backfill create` reuses existing runs, so after regenerating a range at a different scale
   the already-run days keep the old bronze until they are re-run (see item 2). Use
   `--reprocess-behavior completed` for that case.
4. The demo window is now 46 days (2026-10-01 to 2026-11-15) because Ivan approved closing the edge
   day. Two different 45-day numbers must not be confused: the caption in `docs/slides/make_charts.py`
   describes the profiling dataset that script is given (45 days), so it stays; any slide text that
   talks about the *demo window* is the one that has to say 46 days.

## Appendices

Generated from one run of `t04_reconcile_full.py` and the Airflow API, on 2026-11-21.

### Appendix A: mart vs fact_order, all 47 days

| date | mart orders | fact orders | mart completed | fact completed | mart net | fact net | same |
|---|---|---|---|---|---|---|---|
| 2026-09-30 | 93 | 93 | 88 | 88 | 5554050 | 5554050 | True |
| 2026-10-01 | 11564 | 11564 | 11065 | 11065 | 711114250 | 711114250 | True |
| 2026-10-02 | 12803 | 12803 | 12282 | 12282 | 788077700 | 788077700 | True |
| 2026-10-03 | 13495 | 13495 | 12936 | 12936 | 824269150 | 824269150 | True |
| 2026-10-04 | 12362 | 12362 | 11822 | 11822 | 752720650 | 752720650 | True |
| 2026-10-05 | 11075 | 11075 | 10584 | 10584 | 675124300 | 675124300 | True |
| 2026-10-06 | 11252 | 11252 | 10784 | 10784 | 686586850 | 686586850 | True |
| 2026-10-07 | 11468 | 11468 | 11005 | 11005 | 697085350 | 697085350 | True |
| 2026-10-08 | 11648 | 11648 | 11102 | 11102 | 702388800 | 702388800 | True |
| 2026-10-09 | 12746 | 12746 | 12216 | 12216 | 784174250 | 784174250 | True |
| 2026-10-10 | 13482 | 13482 | 12931 | 12931 | 825847550 | 825847550 | True |
| 2026-10-11 | 12301 | 12301 | 11745 | 11745 | 748433600 | 748433600 | True |
| 2026-10-12 | 11077 | 11077 | 10609 | 10609 | 679040500 | 679040500 | True |
| 2026-10-13 | 11148 | 11148 | 10663 | 10663 | 681262700 | 681262700 | True |
| 2026-10-14 | 11452 | 11452 | 10948 | 10948 | 698754800 | 698754800 | True |
| 2026-10-15 | 11715 | 11715 | 11196 | 11196 | 756864550 | 756864550 | True |
| 2026-10-16 | 12887 | 12887 | 12324 | 12324 | 833135550 | 833135550 | True |
| 2026-10-17 | 13346 | 13346 | 12771 | 12771 | 858965600 | 858965600 | True |
| 2026-10-18 | 12152 | 12152 | 11658 | 11658 | 779786750 | 779786750 | True |
| 2026-10-19 | 11007 | 11007 | 10543 | 10543 | 713706600 | 713706600 | True |
| 2026-10-20 | 10908 | 10908 | 10457 | 10457 | 706636800 | 706636800 | True |
| 2026-10-21 | 11283 | 11283 | 10795 | 10795 | 731434750 | 731434750 | True |
| 2026-10-22 | 11775 | 11775 | 11296 | 11296 | 770236550 | 770236550 | True |
| 2026-10-23 | 12904 | 12904 | 12341 | 12341 | 840363100 | 840363100 | True |
| 2026-10-24 | 13511 | 13511 | 12937 | 12937 | 870118600 | 870118600 | True |
| 2026-10-25 | 12160 | 12160 | 11635 | 11635 | 786283500 | 786283500 | True |
| 2026-10-26 | 10988 | 10988 | 10515 | 10515 | 713403500 | 713403500 | True |
| 2026-10-27 | 11156 | 11156 | 10654 | 10654 | 724523300 | 724523300 | True |
| 2026-10-28 | 11392 | 11392 | 10919 | 10919 | 742380700 | 742380700 | True |
| 2026-10-29 | 11666 | 11666 | 11193 | 11193 | 755461350 | 755461350 | True |
| 2026-10-30 | 13107 | 13107 | 12556 | 12556 | 853172350 | 853172350 | True |
| 2026-10-31 | 13537 | 13537 | 12970 | 12970 | 867726950 | 867726950 | True |
| 2026-11-01 | 12164 | 12164 | 11625 | 11625 | 786908300 | 786908300 | True |
| 2026-11-02 | 11107 | 11107 | 10623 | 10623 | 716878350 | 716878350 | True |
| 2026-11-03 | 11120 | 11120 | 10643 | 10643 | 728198400 | 728198400 | True |
| 2026-11-04 | 11288 | 11288 | 10827 | 10827 | 740099250 | 740099250 | True |
| 2026-11-05 | 11597 | 11597 | 11096 | 11096 | 750361600 | 750361600 | True |
| 2026-11-06 | 13007 | 13007 | 12453 | 12453 | 842627550 | 842627550 | True |
| 2026-11-07 | 13374 | 13374 | 12795 | 12795 | 861596100 | 861596100 | True |
| 2026-11-08 | 11946 | 11946 | 11485 | 11485 | 775437200 | 775437200 | True |
| 2026-11-09 | 11013 | 11013 | 10560 | 10560 | 712074850 | 712074850 | True |
| 2026-11-10 | 11221 | 11221 | 10767 | 10767 | 734223450 | 734223450 | True |
| 2026-11-11 | 11317 | 11317 | 10846 | 10846 | 741794550 | 741794550 | True |
| 2026-11-12 | 11645 | 11645 | 11183 | 11183 | 755025550 | 755025550 | True |
| 2026-11-13 | 12967 | 12967 | 12423 | 12423 | 838518250 | 838518250 | True |
| 2026-11-14 | 13404 | 13404 | 12888 | 12888 | 870181350 | 870181350 | True |
| 2026-11-15 | 12025 | 12025 | 11588 | 11588 | 776513600 | 776513600 | True |

`days=47 mismatches=0`

### Appendix B: the 166 orphan order_changes rows

Per order date:

```
order date 20260923: 2
order date 20260924: 4
order date 20260925: 8
order date 20260926: 10
order date 20260927: 14
order date 20260928: 25
order date 20260929: 38
order date 20260930: 62
order date 20261002: 1
order date 20261027: 2
```

| change_id | order_id | source_file_date |
|---|---|---|
| B001-20260929-00076-RF | B001-20260929-00076 | 2026-10-01 |
| B002-20260926-00091-RF | B002-20260926-00091 | 2026-10-03 |
| B003-20260928-00010-RF | B003-20260928-00010 | 2026-10-05 |
| B003-20260928-00030-RF | B003-20260928-00030 | 2026-10-03 |
| B004-20260928-00007-RF | B004-20260928-00007 | 2026-10-03 |
| B006-20260930-00071-RF | B006-20260930-00071 | 2026-10-02 |
| B008-20260925-00054-RF | B008-20260925-00054 | 2026-10-01 |
| B008-20260930-00005-RF | B008-20260930-00005 | 2026-10-06 |
| B010-20260927-00061-RF | B010-20260927-00061 | 2026-10-03 |
| B010-20260928-00079-RF | B010-20260928-00079 | 2026-10-03 |
| B010-20260930-00009-RF | B010-20260930-00009 | 2026-10-01 |
| B011-20260929-00076-RF | B011-20260929-00076 | 2026-10-03 |
| B011-20260930-00026-RF | B011-20260930-00026 | 2026-10-02 |
| B011-20260930-00048-RF | B011-20260930-00048 | 2026-10-02 |
| B011-20260930-00101-RF | B011-20260930-00101 | 2026-10-04 |
| B013-20260930-00045-RF | B013-20260930-00045 | 2026-10-03 |
| B015-20260929-00027-RF | B015-20260929-00027 | 2026-10-03 |
| B015-20260929-00033-RF | B015-20260929-00033 | 2026-10-01 |
| B016-20260929-00079-RF | B016-20260929-00079 | 2026-10-01 |
| B016-20260929-00086-RF | B016-20260929-00086 | 2026-10-07 |
| B016-20260930-00016-RF | B016-20260930-00016 | 2026-10-01 |
| B018-20260930-00003-RF | B018-20260930-00003 | 2026-10-03 |
| B019-20260927-00007-RF | B019-20260927-00007 | 2026-10-02 |
| B019-20261027-00013-RF | B019-20261027-00013 | 2026-10-29 |
| B019-20261027-00062-RF | B019-20261027-00062 | 2026-10-28 |
| B021-20260930-00110-RF | B021-20260930-00110 | 2026-10-07 |
| B022-20260927-00037-RF | B022-20260927-00037 | 2026-10-01 |
| B022-20260927-00191-RF | B022-20260927-00191 | 2026-10-01 |
| B022-20260928-00098-RF | B022-20260928-00098 | 2026-10-01 |
| B022-20260929-00138-RF | B022-20260929-00138 | 2026-10-02 |
| B024-20260927-00027-RF | B024-20260927-00027 | 2026-10-02 |
| B024-20260928-00009-RF | B024-20260928-00009 | 2026-10-01 |
| B024-20260929-00058-RF | B024-20260929-00058 | 2026-10-03 |
| B024-20260930-00062-RF | B024-20260930-00062 | 2026-10-01 |
| B024-20260930-00099-RF | B024-20260930-00099 | 2026-10-01 |
| B025-20260928-00026-RF | B025-20260928-00026 | 2026-10-05 |
| B025-20260929-00116-RF | B025-20260929-00116 | 2026-10-01 |
| B025-20260930-00150-RF | B025-20260930-00150 | 2026-10-02 |
| B026-20260927-00043-RF | B026-20260927-00043 | 2026-10-01 |
| B026-20260928-00121-RF | B026-20260928-00121 | 2026-10-02 |
| B026-20260930-00018-RF | B026-20260930-00018 | 2026-10-01 |
| B026-20260930-00029-RF | B026-20260930-00029 | 2026-10-02 |
| B028-20260929-00076-RF | B028-20260929-00076 | 2026-10-02 |
| B028-20260930-00098-RF | B028-20260930-00098 | 2026-10-02 |
| B028-20260930-00102-RF | B028-20260930-00102 | 2026-10-03 |
| B028-20260930-00121-RF | B028-20260930-00121 | 2026-10-02 |
| B030-20260925-00048-RF | B030-20260925-00048 | 2026-10-02 |
| B031-20260929-00050-RF | B031-20260929-00050 | 2026-10-01 |
| B032-20260927-00055-RF | B032-20260927-00055 | 2026-10-02 |
| B032-20260929-00054-RF | B032-20260929-00054 | 2026-10-01 |
| B032-20260930-00079-RF | B032-20260930-00079 | 2026-10-02 |
| B034-20260927-00013-RF | B034-20260927-00013 | 2026-10-02 |
| B034-20260928-00024-RF | B034-20260928-00024 | 2026-10-02 |
| B034-20260930-00046-RF | B034-20260930-00046 | 2026-10-03 |
| B036-20260929-00073-RF | B036-20260929-00073 | 2026-10-01 |
| B037-20260930-00064-RF | B037-20260930-00064 | 2026-10-02 |
| B039-20260925-00085-RF | B039-20260925-00085 | 2026-10-01 |
| B039-20260929-00041-RF | B039-20260929-00041 | 2026-10-01 |
| B039-20260930-00004-RF | B039-20260930-00004 | 2026-10-05 |
| B040-20260930-00027-RF | B040-20260930-00027 | 2026-10-05 |
| B041-20260928-00075-RF | B041-20260928-00075 | 2026-10-01 |
| B041-20260929-00066-RF | B041-20260929-00066 | 2026-10-02 |
| B042-20260929-00156-RF | B042-20260929-00156 | 2026-10-04 |
| B042-20260930-00048-RF | B042-20260930-00048 | 2026-10-03 |
| B042-20260930-00097-RF | B042-20260930-00097 | 2026-10-01 |
| B042-20260930-00120-RF | B042-20260930-00120 | 2026-10-05 |
| B044-20260925-00080-RF | B044-20260925-00080 | 2026-10-01 |
| B045-20260928-00081-RF | B045-20260928-00081 | 2026-10-01 |
| B045-20260930-00067-RF | B045-20260930-00067 | 2026-10-03 |
| B045-20260930-00091-RF | B045-20260930-00091 | 2026-10-03 |
| B046-20260930-00061-RF | B046-20260930-00061 | 2026-10-02 |
| B047-20260929-00063-RF | B047-20260929-00063 | 2026-10-04 |
| B048-20260927-00073-RF | B048-20260927-00073 | 2026-10-05 |
| B050-20260925-00007-RF | B050-20260925-00007 | 2026-10-01 |
| B051-20260928-00078-RF | B051-20260928-00078 | 2026-10-01 |
| B055-20260929-00096-RF | B055-20260929-00096 | 2026-10-07 |
| B056-20260926-00088-RF | B056-20260926-00088 | 2026-10-02 |
| B056-20260929-00033-RF | B056-20260929-00033 | 2026-10-01 |
| B057-20260923-00073-RF | B057-20260923-00073 | 2026-10-01 |
| B057-20260928-00086-RF | B057-20260928-00086 | 2026-10-01 |
| B057-20260930-00049-RF | B057-20260930-00049 | 2026-10-01 |
| B059-20260926-00015-RF | B059-20260926-00015 | 2026-10-01 |
| B060-20260930-00011-RF | B060-20260930-00011 | 2026-10-01 |
| B060-20260930-00077-RF | B060-20260930-00077 | 2026-10-01 |
| B061-20260925-00088-RF | B061-20260925-00088 | 2026-10-02 |
| B061-20260929-00003-RF | B061-20260929-00003 | 2026-10-04 |
| B061-20260929-00117-RF | B061-20260929-00117 | 2026-10-02 |
| B061-20260930-00013-RF | B061-20260930-00013 | 2026-10-01 |
| B062-20260930-00015-RF | B062-20260930-00015 | 2026-10-02 |
| B062-20260930-00043-RF | B062-20260930-00043 | 2026-10-04 |
| B063-20260924-00017-RF | B063-20260924-00017 | 2026-10-01 |
| B063-20260928-00011-RF | B063-20260928-00011 | 2026-10-03 |
| B065-20260923-00152-RF | B065-20260923-00152 | 2026-10-01 |
| B066-20260929-00098-RF | B066-20260929-00098 | 2026-10-02 |
| B066-20260930-00043-RF | B066-20260930-00043 | 2026-10-01 |
| B067-20260926-00061-RF | B067-20260926-00061 | 2026-10-03 |
| B067-20260926-00100-RF | B067-20260926-00100 | 2026-10-03 |
| B070-20260928-00046-RF | B070-20260928-00046 | 2026-10-01 |
| B070-20260929-00029-RF | B070-20260929-00029 | 2026-10-01 |
| B070-20260930-00043-RF | B070-20260930-00043 | 2026-10-07 |
| B071-20260926-00149-RF | B071-20260926-00149 | 2026-10-04 |
| B073-20260926-00020-RF | B073-20260926-00020 | 2026-10-01 |
| B074-20260926-00103-RF | B074-20260926-00103 | 2026-10-04 |
| B074-20260930-00080-RF | B074-20260930-00080 | 2026-10-01 |
| B077-20260929-00002-RF | B077-20260929-00002 | 2026-10-03 |
| B078-20260930-00065-RF | B078-20260930-00065 | 2026-10-02 |
| B079-20260928-00012-RF | B079-20260928-00012 | 2026-10-01 |
| B079-20260929-00063-RF | B079-20260929-00063 | 2026-10-05 |
| B079-20260930-00074-RF | B079-20260930-00074 | 2026-10-01 |
| B079-20260930-00083-RF | B079-20260930-00083 | 2026-10-02 |
| B080-20260930-00119-RF | B080-20260930-00119 | 2026-10-02 |
| B080-20260930-00145-RF | B080-20260930-00145 | 2026-10-06 |
| B081-20260929-00040-RF | B081-20260929-00040 | 2026-10-03 |
| B082-20260928-00053-RF | B082-20260928-00053 | 2026-10-01 |
| B082-20260929-00053-RF | B082-20260929-00053 | 2026-10-02 |
| B082-20260930-00050-RF | B082-20260930-00050 | 2026-10-01 |
| B082-20260930-00059-RF | B082-20260930-00059 | 2026-10-03 |
| B084-20260930-00029-RF | B084-20260930-00029 | 2026-10-01 |
| B085-20260924-00038-RF | B085-20260924-00038 | 2026-10-02 |
| B089-20260930-00041-RF | B089-20260930-00041 | 2026-10-01 |
| B090-20260930-00013-RF | B090-20260930-00013 | 2026-10-02 |
| B092-20260926-00067-RF | B092-20260926-00067 | 2026-10-03 |
| B092-20260929-00037-RF | B092-20260929-00037 | 2026-10-01 |
| B092-20260929-00064-RF | B092-20260929-00064 | 2026-10-03 |
| B092-20260930-00025-RF | B092-20260930-00025 | 2026-10-03 |
| B092-20260930-00069-RF | B092-20260930-00069 | 2026-10-01 |
| B093-20260924-00022-RF | B093-20260924-00022 | 2026-10-01 |
| B093-20260930-00006-RF | B093-20260930-00006 | 2026-10-05 |
| B094-20260927-00023-RF | B094-20260927-00023 | 2026-10-01 |
| B096-20260929-00087-RF | B096-20260929-00087 | 2026-10-03 |
| B097-20260926-00061-RF | B097-20260926-00061 | 2026-10-03 |
| B098-20260925-00013-RF | B098-20260925-00013 | 2026-10-02 |
| B098-20260928-00058-RF | B098-20260928-00058 | 2026-10-02 |
| B098-20260930-00026-RF | B098-20260930-00026 | 2026-10-01 |
| B099-20260927-00006-RF | B099-20260927-00006 | 2026-10-04 |
| B100-20260930-00027-RF | B100-20260930-00027 | 2026-10-01 |
| B101-20260927-00002-RF | B101-20260927-00002 | 2026-10-04 |
| B101-20260928-00049-RF | B101-20260928-00049 | 2026-10-02 |
| B102-20260924-00044-RF | B102-20260924-00044 | 2026-10-01 |
| B102-20260927-00124-RF | B102-20260927-00124 | 2026-10-03 |
| B102-20260930-00012-RF | B102-20260930-00012 | 2026-10-05 |
| B102-20260930-00060-RF | B102-20260930-00060 | 2026-10-01 |
| B105-20260930-00034-RF | B105-20260930-00034 | 2026-10-02 |
| B105-20260930-00086-RF | B105-20260930-00086 | 2026-10-01 |
| B106-20260929-00018-RF | B106-20260929-00018 | 2026-10-06 |
| B106-20260929-00120-RF | B106-20260929-00120 | 2026-10-02 |
| B106-20260930-00057-RF | B106-20260930-00057 | 2026-10-02 |
| B106-20260930-00087-RF | B106-20260930-00087 | 2026-10-03 |
| B109-20260925-00023-RF | B109-20260925-00023 | 2026-10-02 |
| B109-20260927-00039-RF | B109-20260927-00039 | 2026-10-04 |
| B109-20260928-00049-RF | B109-20260928-00049 | 2026-10-02 |
| B110-20260928-00064-RF | B110-20260928-00064 | 2026-10-06 |
| B110-20260929-00034-RF | B110-20260929-00034 | 2026-10-02 |
| B110-20260930-00014-RF | B110-20260930-00014 | 2026-10-03 |
| B111-20261002-00031-RF | B111-20261002-00031 | 2026-10-04 |
| B112-20260929-00017-RF | B112-20260929-00017 | 2026-10-01 |
| B112-20260929-00080-RF | B112-20260929-00080 | 2026-10-06 |
| B112-20260930-00114-RF | B112-20260930-00114 | 2026-10-01 |
| B112-20260930-00156-RF | B112-20260930-00156 | 2026-10-01 |
| B113-20260928-00050-RF | B113-20260928-00050 | 2026-10-03 |
| B115-20260929-00100-RF | B115-20260929-00100 | 2026-10-03 |
| B116-20260929-00016-RF | B116-20260929-00016 | 2026-10-03 |
| B117-20260928-00164-RF | B117-20260928-00164 | 2026-10-04 |
| B117-20260929-00018-RF | B117-20260929-00018 | 2026-10-01 |
| B118-20260928-00064-RF | B118-20260928-00064 | 2026-10-04 |
| B120-20260928-00084-RF | B120-20260928-00084 | 2026-10-05 |

### Appendix C: DAG runs

`curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/v2/dags/jff_daily/dagRuns?limit=200`

| logical date | run_id | run type | state |
|---|---|---|---|
| 2026-10-01 | `backfill__2026-10-01T00:00:00+00:00` | backfill | success |
| 2026-10-02 | `backfill__2026-10-02T00:00:00+00:00` | backfill | success |
| 2026-10-03 | `manual__2026-11-21T10:31:53.699979+00:00` | manual | success |
| 2026-10-04 | `manual__2026-11-21T10:32:31.567603+00:00` | manual | success |
| 2026-10-05 | `manual__2026-11-21T10:33:07.408771+00:00` | manual | success |
| 2026-10-06 | `manual__2026-11-21T10:33:42.923056+00:00` | manual | success |
| 2026-10-07 | `manual__2026-11-21T10:34:18.617002+00:00` | manual | success |
| 2026-10-08 | `manual__2026-11-21T10:34:53.911265+00:00` | manual | success |
| 2026-10-09 | `manual__2026-11-21T10:35:29.200993+00:00` | manual | success |
| 2026-10-10 | `backfill__2026-10-10T00:00:00+00:00` | backfill | success |
| 2026-10-11 | `backfill__2026-10-11T00:00:00+00:00` | backfill | success |
| 2026-10-12 | `backfill__2026-10-12T00:00:00+00:00` | backfill | success |
| 2026-10-13 | `backfill__2026-10-13T00:00:00+00:00` | backfill | success |
| 2026-10-14 | `backfill__2026-10-14T00:00:00+00:00` | backfill | success |
| 2026-10-15 | `backfill__2026-10-15T00:00:00+00:00` | backfill | success |
| 2026-10-16 | `backfill__2026-10-16T00:00:00+00:00` | backfill | success |
| 2026-10-17 | `backfill__2026-10-17T00:00:00+00:00` | backfill | success |
| 2026-10-18 | `backfill__2026-10-18T00:00:00+00:00` | backfill | success |
| 2026-10-19 | `backfill__2026-10-19T00:00:00+00:00` | backfill | success |
| 2026-10-20 | `backfill__2026-10-20T00:00:00+00:00` | backfill | success |
| 2026-10-21 | `backfill__2026-10-21T00:00:00+00:00` | backfill | success |
| 2026-10-22 | `backfill__2026-10-22T00:00:00+00:00` | backfill | success |
| 2026-10-23 | `backfill__2026-10-23T00:00:00+00:00` | backfill | success |
| 2026-10-24 | `backfill__2026-10-24T00:00:00+00:00` | backfill | success |
| 2026-10-25 | `backfill__2026-10-25T00:00:00+00:00` | backfill | success |
| 2026-10-26 | `backfill__2026-10-26T00:00:00+00:00` | backfill | success |
| 2026-10-27 | `backfill__2026-10-27T00:00:00+00:00` | backfill | success |
| 2026-10-28 | `backfill__2026-10-28T00:00:00+00:00` | backfill | success |
| 2026-10-29 | `backfill__2026-10-29T00:00:00+00:00` | backfill | success |
| 2026-10-30 | `backfill__2026-10-30T00:00:00+00:00` | backfill | success |
| 2026-10-31 | `backfill__2026-10-31T00:00:00+00:00` | backfill | success |
| 2026-11-01 | `backfill__2026-11-01T00:00:00+00:00` | backfill | success |
| 2026-11-02 | `manual__2026-11-21T10:37:06.290885+00:00` | manual | success |
| 2026-11-03 | `backfill__2026-11-03T00:00:00+00:00` | backfill | success |
| 2026-11-04 | `manual__2026-11-21T10:37:43.319776+00:00` | manual | success |
| 2026-11-05 | `backfill__2026-11-05T00:00:00+00:00` | backfill | success |
| 2026-11-06 | `backfill__2026-11-06T00:00:00+00:00` | backfill | success |
| 2026-11-07 | `backfill__2026-11-07T00:00:00+00:00` | backfill | success |
| 2026-11-08 | `backfill__2026-11-08T00:00:00+00:00` | backfill | success |
| 2026-11-09 | `backfill__2026-11-09T00:00:00+00:00` | backfill | success |
| 2026-11-10 | `backfill__2026-11-10T00:00:00+00:00` | backfill | success |
| 2026-11-11 | `backfill__2026-11-11T00:00:00+00:00` | backfill | success |
| 2026-11-12 | `backfill__2026-11-12T00:00:00+00:00` | backfill | success |
| 2026-11-13 | `manual__2026-11-21T10:38:19.492251+00:00` | manual | success |
| 2026-11-14 | `manual__2026-11-21T10:42:23.158780+00:00` | manual | success |
| 2026-11-15 | `manual__2026-11-21T13:48:09.816021+00:00` | manual | success |

46 runs over 46 logical dates, states ['success'].
