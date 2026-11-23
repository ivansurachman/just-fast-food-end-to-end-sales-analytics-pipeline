opencode-go/deepseek-v4.1-flash

# T05 verification: publish silver and gold to the lake as partitioned Parquet

Task: `tasks/T05-publish-parquet.md`. Branch `task/T05-parquet`. Date 2026-11-23.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Decision D1 is unchanged: DuckDB is the compute store and the source for the marts, Parquet is a
derived publish. Anything not run is written as "not run".

## Deliverables

| Path | What it is |
|---|---|
| `pipelines/publish_parquet.py` | CLI `--ds`, `--lookback-days`, `--duckdb-path`, `--lake-root`, `--endpoint`. For every order date in the window and each of `silver_orders`, `silver_order_items`, `fact_order`, `fact_order_item` it writes `COPY (SELECT * ...) TO 's3://jff-lake/<layer>/<table>/order_date=X/part.parquet' (FORMAT PARQUET, COMPRESSION zstd)`. Opens the dbt database **read-only**, `memory_limit 1GB`, `threads 2` |
| `dags/jff_daily.py` | Task `publish_parquet` after `load_marts`, pool `duckdb_writer`, same 10-day window (`LOOKBACK_DAYS`) |
| `docs/lake-layout.md` | Bucket layout for raw, bronze, silver and gold, the fixed object name, the delete rule, and "Parquet derived, DuckDB the source for marts" |
| `pipelines/tests/test_publish_parquet.py` | 7 tests: window, path, date filter, window-only publish, empty-partition delete, delete helper, SeaweedFS roundtrip with ETag stability |
| `docs/verification/T05-parquet.md` | This file |

The window is the same one silver and the marts use, `[ds - lookback_days, ds]`, so the lake is
republished exactly where the pipeline rewrites partitions.

## 1. Objects in the filer

A DAG run for 2026-11-15 (window 11-05..11-15) published its 11 dates:

```
silver_orders: 133516 rows over 11 dates
silver_order_items: 325591 rows over 11 dates
fact_order: 133516 rows over 11 dates
fact_order_item: 325591 rows over 11 dates
[DAG TEST] end task task_id=publish_parquet
44 objects (11 per table)
```

Then the full range was published with the CLI (`--ds 2026-11-15 --lookback-days 45`, 46 dates):

```
total 184
gold/fact_order 46
gold/fact_order_item 46
silver/silver_order_items 46
silver/silver_orders 46
```

The filer serves the same tree: `http://127.0.0.1:8888/buckets/jff-lake/` returns 200 and
`/buckets/jff-lake/silver/` lists `silver_orders` and `silver_order_items`.

Verdict: **pass**, one object per table per day, 46 days.

## 2. Row counts: lake equals DuckDB

`read_parquet('s3://jff-lake/<layer>/<table>/*/part.parquet', hive_partitioning = true)` against the
same table in DuckDB, scoped to the published window (2026-10-01 .. 2026-11-15):

```
silver/silver_orders          lake=   552562 duckdb=   552562 equal=True
silver/silver_order_items     lake=  1345415 duckdb=  1345415 equal=True
gold/fact_order               lake=   552562 duckdb=   552562 equal=True
gold/fact_order_item          lake=  1345415 duckdb=  1345415 equal=True
```

The comparison is scoped because DuckDB also holds 2026-09-30 (the late orders that arrived in the
2026-10-01 file). The demo window starts on 10-01, so the lake starts there too; the DuckDB table is
not filtered, the query is. See "Notes" below.

Verdict: **pass**.

## 3. Partition pruning

`EXPLAIN ANALYZE` over the glob with one equality filter:

```
explain analyze select count(*) from read_parquet('s3://jff-lake/silver/silver_orders/*/part.parquet',
                                                 hive_partitioning = true)
where order_date = date '2026-10-20'

File Filters: (order_date = '2026-10-20')
Scanning Files: 1/46
Total Files Read: 1
Total Time: 0.0266s
```

Only the one partition folder is read, out of 46.

Verdict: **pass**.

## 4. Idempotence

ETags and sizes of all 184 objects were listed, one middle date (2026-10-20) was republished
(`--lookback-days 0`), and the listing was taken again:

```
INFO from the republish: silver_orders 10908 rows over 1 dates, silver_order_items 26423 rows,
                         fact_order 10908, fact_order_item 26423
diff of the 184 ETag+size lines: identical
```

Verdict: **pass**, re-publishing a date changes no object.

## 5. Empty partition deletes the object

A hand-made 5-byte object was written at
`silver/silver_orders/order_date=2026-09-15/part.parquet` (a date with no rows anywhere), then that
date was published:

```
INFO silver_orders 2026-09-15: no rows, deleted the stale object
INFO published {'silver_orders': 0, 'silver_order_items': 0, 'fact_order': 0, 'fact_order_item': 0}
head_object afterwards -> gone (HTTP 404)
objects in the lake -> 184 (nothing else changed)
```

Verdict: **pass**. "Restore" is not needed: the object was the only trace of the fake date.

## 6. Duration and memory of the 46-day publish

The full 46-day publish ran inside the scheduler container while `memory.stat` was sampled every 2 s:

```
exit=0 duration_s=10.5 samples=4 peak_anon_mb=539.6
published {'silver_orders': 552562, 'silver_order_items': 1345415, 'fact_order': 552562,
           'fact_order_item': 1345415}
```

539.6 MB of anonymous memory against the 1700 MB scheduler limit (32%), far from the STOP line. The
whole DAG run for 2026-11-15 (ingest, dbt, marts, publish) took 39.7 s.

Verdict: **pass**.

## 7. Linters and tests

```
python -m ruff check .            -> All checks passed!
python -m ruff format --check .   -> 57 files already formatted
python -m mypy                     -> Success: no issues found in 13 source files
python -m pytest -q                -> 21 passed in 27.78s   (with S3_* exported)
```

The seven new tests include the SeaweedFS roundtrip, which publishes a day to `jff-lake/_test`,
reads it back, republishes and asserts the ETag did not change, then removes the test objects.

Verdict: **pass**.

## Notes and limits

- **2026-09-30 is not in the lake.** It holds only the delayed orders that arrived in the 2026-10-01
  file, and the demo window (and therefore the publish window) starts on 10-01. DuckDB keeps the day,
  the lake does not.
- A partition is deleted only when its own date is republished. If a date disappears from DuckDB
  without ever being published again, its object stays; the delete rule covers the date being rewritten.
- There is no compaction step: one object per day is what the rubric asks for, and at 46 days it is
  184 objects of a few hundred KB to a few MB.
- Not run: reading the lake from Metabase. The dashboard reads the PostgreSQL marts by design; the lake
  is for the rubric and for consumers without the DuckDB file.
- No new dependency: the task runs with the Airflow interpreter (duckdb + boto3 already in the image).
