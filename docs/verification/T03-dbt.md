# T03 verification: dbt silver and gold in DuckDB

Task: `tasks/T03-dbt-silver-gold.md`. Branch `task/T03-dbt`. Started 2026-11-20.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Only commands that were run are recorded. Anything not run is written as "not run".

## Step 0 (decided after T02)

### 1. Demo window on the DAG

`dags/jff_daily.py` now bounds the DAG: `start_date=datetime(2026, 10, 1)`,
`end_date=datetime(2026, 11, 14)`, `catchup=True`, `max_active_runs=1`, and `wait_manifest` has
`timeout=2 * 60 * 60`. Read back from the parsed DAG in the scheduler container:

```
python - <<'PY'   (DagBag over /opt/airflow/dags)
start_date 2026-10-01 00:00:00+00:00
end_date 2026-11-14 00:00:00+00:00
catchup True
max_active_runs 1
sensor mode reschedule poke_interval 30.0 timeout_s 7200.0
tasks ['wait_manifest', 'dbt_run', 'dbt_test', 'load_marts', 'ingest_bronze', 'check_bronze']
dbt_run pool duckdb_writer
dbt_test pool duckdb_writer
```

The DAG was **not** unpaused. Every run below was started with `airflow dags test` (or `dbt`
directly), as step 6 asks.

### 2. Lake reset, then the demo days regenerated

Ivan approved the deletion first (it removes data). Both buckets were emptied and the days 2026-10-03
to 2026-10-09 generated again at scale 0.02, inside the scheduler container:

```
empty buckets:  jff-raw: deleted 24 objects
                jff-lake: deleted 19 objects
podman exec jff_airflow-scheduler_1 /opt/venvs/jff/bin/jff-gen generate \
    --out s3://jff-raw --s3-endpoint http://seaweedfs:8333 \
    --start 2026-10-03 --end 2026-10-09 --scale 0.02
2026-10-03: {'orders': 2683, 'order_items': 6665, 'order_changes': 16}
2026-10-04: {'orders': 2505, 'order_items': 6083, 'order_changes': 25}
2026-10-05: {'orders': 2201, 'order_items': 5384, 'order_changes': 22}
2026-10-06: {'orders': 2255, 'order_items': 5461, 'order_changes': 15}
2026-10-07: {'orders': 2339, 'order_items': 5641, 'order_changes': 23}
2026-10-08: {'orders': 2337, 'order_items': 5756, 'order_changes': 26}
2026-10-09: {'orders': 2579, 'order_items': 6186, 'order_changes': 25}
```

The daily files do not include the dimensions; they need `jff-gen dim all` first. That was done too
(120 branches, 5 channels, 21 menu items, 6 promos), then bronze was ingested for all seven days.

### 3. `.env.example`

Every variable in `.env` is present in `.env.example`, including `AIRFLOW_API_AUTH_JWT_SECRET`
(added in T02) and the new `POSTGRES_HOST_PORT`:

```
missing_in_example:
extra_in_example:
```

### 4. Memory evidence includes page cache

`podman machine ssh free -m` before and after the full-scale run, plus `anon` and `file` from
`/sys/fs/cgroup/memory.stat`; the numbers are in acceptance item 6.

### 5. Postgres host port is configurable

`compose.yaml` publishes `127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432`, `.env.example` sets
`POSTGRES_HOST_PORT=5432`, and Ivan's local `.env` sets `POSTGRES_HOST_PORT=5433` (native PostgreSQL
18 holds 5432 on his machine).

```
podman ps --format "{{.Names}} {{.Ports}}"
jff_postgres_1 127.0.0.1:5433->5432/tcp
psql -h 127.0.0.1 -p 5433 -U airflow -d airflow -tAc "select 'connected', current_user, current_database()"
connected|airflow|airflow
psql -h 127.0.0.1 -p 5432 -U airflow -d airflow   -> FATAL: password authentication failed
```

One line was added to the infra notes (`docs/pipeline-design.md` section 9).

## Deliverables

| Path | What it is |
|---|---|
| `dbt/dbt_project.yml` | Project `jff`: staging = view, silver = incremental `delete+insert`, gold = table |
| `dbt/profiles.yml` | dbt-duckdb at `${DBT_DUCKDB_PATH}`, `threads: 2`, `memory_limit: 1GB`, `temp_directory`, path-style S3 from env vars |
| `dbt/macros/bronze_path.sql` | `bronze_fact_glob`, `bronze_dimension_path`, `run_date_sql`, `window_start_sql` |
| `dbt/models/staging/` | `stg_orders`, `stg_order_items`, `stg_order_changes`, `stg_branches`, `stg_channels`, `stg_menu_items`, `stg_promos`: `read_parquet(..., hive_partitioning = true)`, file dates clipped to `run_date`; changes also clipped to the window start |
| `dbt/models/silver/` | `silver_orders`, `silver_order_items`, `silver_order_changes`: typed, deduplicated, `dq_flags` list, incremental on `order_date` |
| `dbt/models/gold/` | `dim_date`, `dim_branch`, `dim_channel`, `dim_promo` (+ NONE), `dim_menu_item` (+ UNKNOWN) as tables; `fact_order`, `fact_order_item` incremental on `date_key` |
| `dbt/seeds/payment_method_map.csv` | canonical payment labels for the variant defect |
| `dbt/tests/` | `assert_lookback_window`, `assert_gross_equals_line_amounts`, `assert_silver_matches_bronze_orders`, `assert_silver_order_items_unique`, `assert_fact_order_item_unique` |
| `dbt/models/{silver,gold}/schema.yml` | generic tests: `unique`, `not_null`, `accepted_values`, `relationships` |
| `infra/airflow/install-dbt.sh`, `infra/airflow/dbt-constraints.txt` | `/opt/venvs/dbt` with dbt-core 1.11.16 + dbt-duckdb 1.11.1, pinned closure |
| `Containerfile` | runs `install-dbt.sh` next to the generator venv |
| `compose.yaml` | named volume `jff_duckdb` on the scheduler only, `./dbt` bind mount, `DBT_DUCKDB_PATH` |
| `dags/jff_daily.py` | `dbt_run` is `dbt seed ... && dbt run ...` and `dbt_test` is `dbt test ...`, both `BashOperator`s calling `/opt/venvs/dbt/bin/dbt` on pool `duckdb_writer`; `load_marts` is still a placeholder |

In the image:

```
podman run --rm --entrypoint /opt/venvs/dbt/bin/dbt jff-airflow:3.3.2 --version
Core:  - installed: 1.11.16
Plugins: - duckdb: 1.11.1 - Up to date!
dbt debug -> Connection test: [OK connection ok]
   settings: {'memory_limit': '1GB', 'temp_directory': '/tmp/dbt-duckdb',
              's3_endpoint': 'seaweedfs:8333', 's3_use_ssl': False, 's3_url_style': 'path', ...}
```

### Window and idempotency, in one place

- A run rebuilds the order-date partitions `[run_date - 10, run_date]`; `delete+insert` with
  `unique_key` `order_date` (silver) and `date_key` (gold) replaces them, so a repeated run cannot
  double count.
- Silver reads file dates `[run_date - 10, run_date]`. For a partition X that is the union of the
  "X and X+1" rule in design section 6, and it is one filter instead of a per-partition loop.
- `order_date` is `cast(cast(order_ts as timestamp) as date)`, the local date, never the file date and
  never parsed from `order_id`.
- Refunds: `silver_order_changes` joins each change to its order to get `order_date`; a change whose
  order is not in silver yet is dropped and reappears on the run that brings the order, while its
  file date is still inside the window.

## Findings while building (fixed in this task)

1. **Empty CSV fields are NULL, not empty string.** The first builds flagged `payment_null 0` and
   `platform_ref_null 0` while the manifests injected 32 and 28. Cause: DuckDB's CSV reader turns an
   empty field into NULL, so `payment_method = ''` was never true. Fix: `coalesce(..., '')` before
   every "is it empty" test in `silver_orders`. After the fix both counts match exactly (item 3).
2. **The reconciliation test compared two different populations.** `assert_silver_matches_bronze_orders`
   first used the staging view (clipped at `run_date`) against the whole `silver_orders`; it failed
   (`FAIL 1`) as soon as a day newer than the run date existed, which is exactly what happened after
   the full-scale day was loaded. Reading the whole lake instead then failed in the opposite direction
   (bronze newer than silver on a cold start). Final version: compare **within the run window** - distinct
   bronze orders whose order date is in `[run_date - lookback_days, run_date]` against
   `silver_orders` in the same window. This is the statement the pipeline actually guarantees.
3. **`dbt run` does not build seeds.** The first version of `dbt_run` was `dbt run`, which works only
   while the `payment_method_map` seed already exists in the database; on a fresh volume the first run
   would fail. `dbt_run` is now `dbt seed ... && dbt run ...`, and the cold start below proves it.
4. **`dbt test` alone does not recompile views.** The staging views store the compiled `run_date` and
   `lookback_days`, so `dbt test --vars ...` after a `dbt run` with other vars tests the old window.
   The guard demo below therefore uses `dbt build --select stg_order_changes assert_lookback_window`.
   In the DAG this cannot happen: `dbt run` and `dbt test` always receive the same vars.

## Acceptance

### 1. `dbt build` on the three T02 days, run dates in order

Started from an empty database (`rm /opt/airflow/duckdb/jff.duckdb`) so the first run builds
everything from bronze:

```
dbt build --vars '{run_date: 2026-10-03, lookback_days: 10}'   exit 0
  Finished running 5 incremental models, 1 seed, 5 table models, 47 data tests, 7 view models in 3.94s
  Done. PASS=65 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=65
dbt build --vars '{run_date: 2026-10-04, lookback_days: 10}'   exit 0
  Finished running ... in 3.30s
  Done. PASS=65 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=65
dbt build --vars '{run_date: 2026-10-05, lookback_days: 10}'   exit 0
  Finished running ... in 3.85s
  Done. PASS=65 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=65
```

Verdict: **pass**.

### 2. Repeating the last run date changes nothing

Snapshot of every silver and gold table (row count and md5 of all rows ordered by their text), then
the same `dbt build` for 2026-10-05 again, then the same snapshot:

```
before                                        after (re-run of 2026-10-05)
silver_orders        7356 d03067b3...a1c6fb4  silver_orders        7356 d03067b3...a1c6fb4
silver_order_items  18057 63330fee...1298a74  silver_order_items  18057 63330fee...1298a74
silver_order_changes   37 e89e8e43...ce691e4  silver_order_changes   37 e89e8e43...ce691e4
dim_date                4 ea2fa0e2...2bacfc2  dim_date                4 ea2fa0e2...2bacfc2
dim_branch            120 9dea301c...b40b1f184 dim_branch            120 9dea301c...b40b1f184
dim_channel             5 1e74ece3...5c6ec61  dim_channel             5 1e74ece3...5c6ec61
dim_promo               7 644e7b57...59385b1  dim_promo               7 644e7b57...59385b1
dim_menu_item          22 62c8138c...84be35860 dim_menu_item         22 62c8138c...84be35860
fact_order           7356 72fcd1ba...ed2ed192f6 fact_order           7356 72fcd1ba...ed2ed192f6
fact_order_item     18057 8b8b99c0...b971ce1b8d fact_order_item     18057 8b8b99c0...b971ce1b8d
repeat exit 0, Done. PASS=65 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=65
diff: identical
```

The hashes are the same for all ten tables, so the incremental `delete+insert` is a fixpoint.

The same check was repeated later, after the fixes below, on the full seven-day dataset: snapshot,
`dbt build` for 2026-10-09 again, snapshot - `diff: identical` with 16812 orders, 40965 lines,
122 changes, 8 dates.

Verdict: **pass**.

### 3. Flag counts against the manifests, three days (2026-10-03 .. 2026-10-05)

| Defect | silver flag | flag name | manifest `injected` sum | match |
|---|---|---|---|---|
| duplicate_orders | 33 | `dup_order` (silver_orders) | 33 | yes |
| duplicate_item_rows | 75 | `dup_item` (silver_order_items) | 75 | yes |
| payment_null | 32 | `payment_null` | 32 | yes |
| payment_variant | 25 | `payment_variant` | 25 | yes |
| platform_ref_null | 28 | `platform_ref_null` | 28 | yes |
| gross_mismatch | 31 | `gross_mismatch` | 31 | yes |
| unknown_menu_item | 22 | `unknown_item` | 22 | yes |
| late arrival | 79 (orders), 193 (lines) | `late_arrival` | delayed_in 48, delayed_out 79 | not comparable, see below |

Manifest values per file:

```
2026-10-03: duplicate_item_rows 28, duplicate_orders 13, gross_mismatch 11, payment_null 11,
            payment_variant 7, platform_ref_null 7, unknown_menu_item 7,
            late_orders_delayed_in 2, late_orders_delayed_out 31
2026-10-04: duplicate_item_rows 29, duplicate_orders 13, gross_mismatch 14, payment_null 13,
            payment_variant 8, platform_ref_null 7, unknown_menu_item 9,
            late_orders_delayed_in 31, late_orders_delayed_out 15
2026-10-05: duplicate_item_rows 18, duplicate_orders 7, gross_mismatch 6, payment_null 8,
            payment_variant 10, platform_ref_null 14, unknown_menu_item 6,
            late_orders_delayed_in 15, late_orders_delayed_out 33
```

The seven defects the generator injects per row match one to one. Two properties make that work:
the flag sits on the row that survives deduplication (so 33 duplicate order rows = 33 orders), and
every injected variant label is a different string from its canonical label (`CASH`, `Cash `,
`tunai`, `QRIS`, `Qris`, ` qris`, `e-wallet`, `E-Wallet`, `EWALLET`, `CARD`, `Card`, `kartu`), which
is what `payment_variant` tests.

Late arrivals cannot match one to one, by construction:

- the manifests count **rows per file** (`late_orders_delayed_in`/`_out`), while `late_arrival` counts
  **orders per order date**; an order held back on day D arrives in the file of D+1 and is flagged on
  order date D, in a different bucket from the one the manifest counts;
- the three-day window of order dates includes orders that arrived in the files of 10-04 to 10-06, so
  the flag also counts arrivals from a file outside the three manifests.

`late_orders_delayed_out` 31 + 15 + 33 = 79 equals the 79 flagged orders only by coincidence of this
window; the number that must match is per file and per date, and the design does not ask for it.

Verdict: **pass**, with the late-arrival mismatch explained as the task requires.

### 4. Refunds land on the original order date

Seven days generated and ingested (2026-10-03 .. 2026-10-09), then built in order. After the last run:

```
bronze order_changes: rows 152, distinct change_id 152, distinct order_id 152
silver_order_changes: rows 122, distinct order_id 122
fact_order refunded: 122
fact_order refunded but no change row: 0
fact_order not refunded but a change row exists: 0
refund lag (changed_at - order_date), days: 0:37, 1:42, 2:21, 3:13, 4:5, 5:2, 6:2
```

Query used for the two numbers the task asks for:

```sql
select count(*) from fact_order where status_final = 'refunded';                          -- 122
select count(distinct order_id) from silver_order_changes;                                 -- 122
select count(distinct order_id)
from read_parquet('s3://jff-lake/bronze/order_changes/*/*.parquet');                       -- 152
```

The 30 change rows that do not reach silver reference orders dated 2026-09-27 .. 2026-10-02, i.e.
before the demo window, which was never generated:

```
order day in id: 20260927 2, 20260928 1, 20260929 1, 20260930 2, 20261001 10, 20261002 14
```

They will be applied by the T04 backfill once 2026-10-01 and 2026-10-02 exist. The 122 applied
refunds are all on the order date of the order (`changed_at` up to 6 days later), which is what the
design asks for.

Verdict: **pass**.

### 5. Lookback guard

Passing on a normal run date:

```
dbt test --select assert_lookback_window --vars '{run_date: 2026-10-09, lookback_days: 10}'
1 of 1 PASS assert_lookback_window
```

Failing on one hand-made change row. A single row was written to a new bronze partition
(`bronze/order_changes/source_file_date=2026-10-10/order_changes.parquet`) for order
`B013-20261002-00013`, an order whose order date is 2026-10-02. The run uses
`run_date=2026-10-10, lookback_days=7`, so the window is 2026-10-03 .. 2026-10-10: every real change
in the data is inside it, and only the hand-made row points outside.

```
dbt build --select stg_order_changes assert_lookback_window \
    --vars '{run_date: 2026-10-10, lookback_days: 7}'          exit 1
  1 of 2 OK created sql view model main.stg_order_changes
  2 of 2 FAIL 1 assert_lookback_window
  Got 1 result, configured to fail if != 0
```

Then the object was deleted and the view rebuilt for the production window:

```
dbt build --select stg_order_changes assert_lookback_window \
    --vars '{run_date: 2026-10-09, lookback_days: 10}'          exit 0
  2 of 2 PASS assert_lookback_window
```

An earlier attempt moved `run_date` to 2026-10-14 instead and reported `Got 29 results`: 28 of them
were real changes for orders of 2026-10-03 that fall outside the window only because no data exists
for 2026-10-10..2026-10-14. That is why the demo above uses a window that contains all real data.

Verdict: **pass**.

### 6. Scheduler memory during `dbt_run` for a full-scale day

Full-scale day 2026-10-20 at scale 1.0 was generated in the container and ingested to bronze
(108,943 orders, 265,359 items, 919 changes), then `dbt_run` for that date was executed by Airflow in
the scheduler container while the container's memory was sampled every ~0.1 s with `podman stats`:

```
podman machine ssh free -m   before: total 7822, used 1862, available 5960
airflow tasks test jff_daily dbt_run 2026-10-20
task=dbt_run ds=2026-10-20 exit=0 duration_s=24.5 samples=49
stats_peak_mb=1201.2 first_mb=542.2 last_mb=567.2
cgroup_peak_before_mb=828.9 cgroup_peak_after_mb=1242.4
memory.stat after: anon_mb=414.6 file_mb=168.3 inactive_file_mb=86.9 active_file_mb=81.4
                   file_dirty_mb=2.8 file_writeback_mb=0.0
podman machine ssh free -m   after:  total 7822, used 2173, available 5648
```

Against the 1700 MiB limit in `compose.yaml`:

| Reading | MiB | Share of 1700 MiB |
|---|---|---|
| Highest `podman stats` sample during `dbt_run` | 1201.2 | 70.7% |
| Container lifetime peak after the run | 1242.4 | 73.1% |
| `anon` after the run (the memory that can trigger an OOM kill) | 414.6 | 24.4% |
| `file` after the run (page cache, reclaimable) | 168.3 | 9.9% |

No OOM kill and no restart. `free -m` shows 5648 MB available afterwards, far above the 1 GiB STOP
line. dbt's own DuckDB is capped at `memory_limit=1GB` and `threads=2` in `profiles.yml`.

Verdict: **pass**.

### 7. A whole DAG run succeeds in Airflow

Final run, from a **cold start**: the DuckDB file was deleted first, so this is the first build of
the database (and the seed has to be created by the task itself). Bronze already held a day newer
than the run date (2026-10-20, full scale), which is the case the reconciliation test used to fail on.

```
podman exec jff_airflow-scheduler_1 airflow dags test jff_daily 2026-10-09
dags_test_exit=0 wall_seconds=30.9
[DAG TEST] end task task_id=wait_manifest
[DAG TEST] end task task_id=ingest_bronze
[DAG TEST] end task task_id=check_bronze
         dbt seed  -> Done. PASS=1  WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=1
         dbt run   -> Done. PASS=17 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=17
[DAG TEST] end task task_id=dbt_run
         dbt test  -> Done. PASS=47 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=47
[DAG TEST] end task task_id=dbt_test
[DAG TEST] end task task_id=load_marts
airflow dags list-runs jff_daily
manual__2026-11-20T13:01:28.640714+00:00 | success | 2026-10-09 | start 13:01:28 | end 13:01:53
```

Task states for that run:

```
wait_manifest  success  13:01:29 -> 13:01:33
ingest_bronze  success  13:01:33 -> 13:01:34
check_bronze   success  13:01:34 -> 13:01:34
dbt_run        success  13:01:34 -> 13:01:46
dbt_test       success  13:01:46 -> 13:01:53
load_marts     success  13:01:53 -> 13:01:53
```

Run duration 24.9 s for the whole graph (`load_marts` is still a no-op placeholder). An earlier run
with the same commands, before the seed fix, succeeded in 19.7 s from a warm database.

Verdict: **pass**.

### 8. Linters and tests

```
python -m ruff check .            -> All checks passed!
python -m ruff format --check .   -> 44 files already formatted
python -m mypy                     -> Success: no issues found in 9 source files
python -m pytest -q                -> 10 passed in 13.05s    (with S3_* exported)
```

Only Python changed (`dags/jff_daily.py`); the dbt project is SQL and YAML, and `sqlfluff` is not
required by the task. `mypy` still reports 9 source files because the dbt project adds no Python.

Verdict: **pass**.

## Not run

- `dbt docs generate` / the documentation site: not asked for.
- `dbt build --full-refresh` on the 45-day window: only on the seven demo days (it was used once while
  fixing the NULL/empty finding).
- A `docker-compose` run of the new compose file (only `podman compose`, as in T02).
- The DAG was never unpaused, so there is no scheduler-driven backfill and no catchup run in this
  task (step 6 explicitly says not to unpause before every day exists).
