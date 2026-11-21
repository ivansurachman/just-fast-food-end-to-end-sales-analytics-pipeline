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
| Run states | all `success`: 46 runs over 46 dates at the end, no failure and no retry left behind |
| Peak scheduler `anon` (sampled every 10 s) | **1344 MiB** (79% of the 1700 MiB limit) |
| Peak `memory.current` (anon + page cache) | 1551 MiB |
| `memory.peak` | 1.782.579.200 B = the 1700 MiB ceiling: the cgroup reached its limit and the kernel reclaimed page cache; `oom_kill 0`, `oom 0` |
| `podman machine ssh free -m` before | total 7822, used 3493, available **4329** |
| `podman machine ssh free -m` after | total 7822, used 4049, available **3772**, swap used 115 MB |

No container was OOM-killed (`podman inspect .State.OOMKilled` false, `memory.events oom_kill 0`).
Afterwards PostgreSQL holds `25.693` mart rows over `46` dates (2026-09-30 to 2026-11-14),
`540.447` orders and `34.410.696.400` of net sales.

**Finding while running the backfill.** `backfill create` skips dates that already have a run, so the
seven days from Part A kept the bronze of the 0.02 dataset while the rest of the range was regenerated
at 0.1. That showed up as 740 orphan refunds for 2026-10-03..2026-10-09. Re-running those seven dates
(`airflow dags test` per day, 4.2 min total) rebuilt their bronze from the new raw and the orphans
disappeared. A backfill on a range that was already run should use
`--reprocess-behavior completed`, or the days must be re-run after a scale change.

### Item 4a: mart vs fact_order on the whole range

Zero mismatches over the 46 dates; the table is in the Part A section in the same shape, and the
check now ends with `mismatches=0` and `days in fact_order but outside every loaded window: []`.

### Item 4b: the CSV identity on the 45-day range

No day in the generated range is clean: every manifest has late orders in or out, so the simple form
`mart = distinct` cannot be shown. The full identity was checked for every day instead:

`mart_total(d) = distinct order_id in the CSV of d - late_orders_delayed_in(d) + late_orders_delayed_out(d)`

```
2026-10-01: distinct=11564 late_in=93  late_out=93  -> expected=11564 mart=11564 OK
2026-10-02: distinct=12883 late_in=93  late_out=13  -> expected=12803 mart=12803 OK
2026-10-03: distinct=13352 late_in=13  late_out=156 -> expected=13495 mart=13495 OK
2026-10-04: distinct=12392 late_in=156 late_out=126 -> expected=12362 mart=12362 OK
days checked=45 identity_holds=44
```

The one exception is the last day of the window:

```
MISMATCH 2026-11-14 distinct=13421 late_in=200 late_out=183 expected=13404 mart=13221 diff=-183
```

The 183 orders held back from the 2026-11-14 file arrive in the 2026-11-15 file, which is outside the
DAG's `end_date` and therefore never ingested. This is the documented "yesterday's number is
provisional until the next run" property at the edge of the window: the last generated day can never
be finalised by this design. For the demo it means the 45th day is provisional; if that matters,
Ivan decides whether the window grows by one day.

### Item 4d: changes whose order is not in the dataset

```
orphan_rows=166
  order date 20260923: 2    order date 20260927: 14   order date 20261002: 1
  order date 20260924: 4    order date 20260928: 25   order date 20261027: 2
  order date 20260925: 8    order date 20260929: 38
  order date 20260926: 10   order date 20260930: 62
```

Two causes, neither a pipeline bug:

- 163 rows reference orders dated 2026-09-23..2026-09-30. The demo dataset starts on 2026-10-01 and a
  refund can reach 8 days back, so the generator writes refunds for orders it never produced. The
  task expected about 6 at scale 0.02; at scale 0.1 the same defect produces 163.
- 3 rows reference branch-days that the generator dropped: branch 111 on 2026-10-02 and branch 19 on
  2026-10-27, both listed in `dropped_branch_ids` of those manifests, and one more from 10-02. The
  missing branch-day defect means the order was never written, but a later file still carries its
  refund.

Both are the generator's own defects showing up as unresolvable references, which is what item 4d
asks to list.

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

### Item 6: the whole chain from a cold start

```
podman compose down             32.5 s
podman compose up -d            81.3 s
all healthy (Metabase included) 131.7 s total
```

Then a day through the pipeline. `2026-11-15` cannot be used: it is outside the DAG's `end_date`, and
`airflow dags test jff_daily 2026-11-15` creates a run and closes it as successful **without creating a
single task** (the log shows `DagRun Finished ... state=success` and no task entries). So the day used
was 2026-11-14, the last day of the demo window, after deleting its three bronze objects (raw was not
touched) to make it an arrival rather than a re-run:

```
generate (nothing to generate: raw for 11-14 already exists)
airflow dags test jff_daily 2026-11-14   39.8 s, exit 0
  bronze orders 2026-11-14: 13495 rows
  dbt: PASS=1 (seed), PASS=18 (run), PASS=48 (test)
  loaded 6281 rows for 2026-11-04 .. 2026-11-14 into mart_sales_day_branch_channel
```

The day is on the dashboard: card "Net sales per day" returns 46 rows totalling `34.410.696.400`, with
`2026-11-14 = 860.338.850`, identical to the mart before and after the run (571 rows, 13.221 orders,
`860.338.850`) - the run rebuilt what it had removed and changed nothing else.

Note: the 2026-11-15 file that was generated while testing this (12.271 orders) stays in `jff-raw`.
Nothing will process it while `end_date` is 2026-11-14.

### Item 7: linters and tests

```
python -m ruff check .            -> All checks passed!
python -m ruff format --check .   -> 48 files already formatted
python -m mypy                     -> Success: no issues found in 10 source files
python -m pytest -q                -> 10 passed in 15.61s
```

### Item 5: Ivan's screenshot

Still open: the dashboard is at **http://localhost:3000/dashboard/2** and Ivan saves the screenshot at
`docs/slides/img/dashboard-sales-overview.png`.

## Findings to hand over

1. Metabase memory is at 95% of its own 1400m limit and almost all of it is anonymous (1.317 GB of
   `anon` against 12 MB of page cache). Not an OOM today, no limit raised; with the 5600 MB ceiling
   there is no headroom to give it more without taking it from another service.
2. The last day of the demo window (2026-11-14) can never be finalised, because its late orders live in
   a file dated 2026-11-15, which is outside the DAG window (see item 4b).
3. `airflow backfill create` reuses existing runs, so after regenerating a range at a different scale
   the already-run days keep the old bronze until they are re-run (see item 2).
