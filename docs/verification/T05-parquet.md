opencode-go/deepseek-v4.1-flash

# T05 verification: publish silver and gold to the lake as partitioned Parquet

Task: `tasks/T05-publish-parquet.md`. Branch `task/T05-parquet`. Date 2026-11-23.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Decision D1 is unchanged: DuckDB is the compute store and the source for the marts, Parquet is a
derived publish. Anything not run is written as "not run". Ivan decided on 23 Nov that the lake is a
**full mirror** of DuckDB, so `2026-09-30` is part of it (47 dates, see item 2).

## Deliverables

| Path | What it is |
|---|---|
| `pipelines/publish_parquet.py` | CLI `--ds`, `--lookback-days`, `--duckdb-path`, `--lake-root`, `--endpoint`. For every order date in the window and each of `silver_orders`, `silver_order_items`, `fact_order`, `fact_order_item` it writes `COPY (SELECT * ... ORDER BY <key>) TO 's3://jff-lake/<layer>/<table>/order_date=X/part.parquet' (FORMAT PARQUET, COMPRESSION zstd)`. Opens the dbt database **read-only**, `memory_limit 1GB`, `threads 2` |
| `dags/jff_daily.py` | Task `publish_parquet` after `load_marts`, pool `duckdb_writer`, same window (`LOOKBACK_DAYS = 10`) |
| `docs/lake-layout.md` | Bucket layout for raw, bronze, silver and gold, the fixed object name, the delete rule, and "Parquet derived, DuckDB the source for marts" |
| `pipelines/tests/test_publish_parquet.py` | 8 tests: window, path, date filter, window-only publish, empty-partition delete (local), delete helper, SeaweedFS roundtrip with ETag stability, SeaweedFS empty-partition delete |
| `docs/verification/T05-parquet.md` | This file |

`ORDER BY` is on the table's key (`order_id`, or `order_id, line_no` for the item tables). It does not
guarantee identical bytes, it removes row order as a source of variation; the ETag evidence in item 4
is the measurement.

## 1. Objects in the lake after a DAG run

The acceptance scenario is a DAG run, so the 46-day range was executed through the DAG, not through
the CLI: DAG paused, backfill created, then unpaused by the monitor script.

```
airflow backfill create --dag-id jff_daily --from-date 2026-10-01 --to-date 2026-11-15 \
    --reprocess-behavior completed
created=46
# then: airflow dags unpause jff_daily ... wait ... airflow dags pause jff_daily
elapsed_min=24.8 done=True
state=success runs=46
```

Every run published its window, and the run for `ds = 2026-10-01` also published `2026-09-30` (the
late orders that arrived in the 10-01 file), so the lake mirrors DuckDB exactly:

```
# boto3 list_objects_v2 over jff-lake, prefix silver/ and gold/
objects 188 bytes 28024692
gold/fact_order 47
gold/fact_order_item 47
silver/silver_order_items 47
silver/silver_orders 47
distinct dates 47 2026-09-30 2026-11-15
```

Per table: 46 demo days plus 2026-09-30. The filer shows the same tree:
`http://127.0.0.1:8888/buckets/jff-lake/` returns 200, `/buckets/jff-lake/silver/` lists
`silver_orders` and `silver_order_items`, and `/buckets/jff-lake/gold/` lists `fact_order` and
`fact_order_item`.

Verdict: **pass** (47 objects per table, one per day, from DAG runs).

## 2. Row counts: lake equals DuckDB

Read back with hive partitioning, compared with the DuckDB tables **without any filter**:

```sql
select count(*) from read_parquet('s3://jff-lake/<layer>/<table>/*/part.parquet',
                                  hive_partitioning = true);
select count(*) from <table>;                       -- jff.duckdb
```

```
silver/silver_orders          lake=   552655 duckdb=   552655 equal=True
silver/silver_order_items     lake=  1345630 duckdb=  1345630 equal=True
gold/fact_order               lake=   552655 duckdb=   552655 equal=True
gold/fact_order_item          lake=  1345630 duckdb=  1345630 equal=True
```

Verdict: **pass**, exact equality for the whole tables, no scoping needed.

## 3. Partition pruning

```
explain analyze select count(*) from read_parquet('s3://jff-lake/silver/silver_orders/*/part.parquet',
                                                 hive_partitioning = true)
where order_date = date '2026-10-20'

File Filters: (order_date = '2026-10-20')
Scanning Files: 1/47
Total Files Read: 1
Total Time: 0.0209s
```

Only one of the 47 partitions is read.

Verdict: **pass**.

## 4. Idempotence

All 188 objects were listed with their ETag and size (`boto3 list_objects_v2`, paginated), one middle
date was published twice, and the listing was compared after each step:

```
list1 (before)                     188 objects
publish --ds 2026-10-20 --lookback-days 0
published {'silver_orders': 10908, 'silver_order_items': 26423,
           'fact_order': 10908, 'fact_order_item': 26423}
list2                              188 objects
publish --ds 2026-10-20 --lookback-days 0   (same command again)
list3                              188 objects

diff list1 vs list2: identical
diff list2 vs list3: identical
```

Even the first republish after the `ORDER BY` change produced the same ETags, and the second was
identical again.

Verdict: **pass**.

## 5. Empty partition deletes the object

Hand-made case on the live lake, then the same behaviour as a test against SeaweedFS.

Live:

```
put silver/silver_orders/order_date=2026-09-15/part.parquet   (5 bytes, a date with no rows)
python -m pipelines.publish_parquet --ds 2026-09-15 --lookback-days 0
INFO silver_orders 2026-09-15: no rows, deleted the stale object
INFO published {'silver_orders': 0, 'silver_order_items': 0, 'fact_order': 0, 'fact_order_item': 0}
head_object -> gone (HTTP 404)
objects in the lake -> 184 (this live case ran before the DAG backfill of item 1; at that time the lake
was the 46-day CLI publish, 46 x 4 = 184. After the backfill it is 188 and nothing else changed)
```

Test (`test_seaweedfs_empty_partition_deletes_the_object`): writes a stale object under
`jff-lake/_test_empty/`, publishes that date, asserts `head_object` raises, then removes the prefix
with a paginated delete. It runs in the suite of item 7.

Verdict: **pass**.

## 6. Duration and memory

The 46-day backfill ran in the scheduler container while `memory.stat` was sampled every 10 s:

```
elapsed_min=24.8 runs=46 all success
samples=104 peak_anon_mb=1122
podman machine ssh free -m after: total 7822, used 3800, available 4021, swap used 597 MB
cgroup memory.peak 1782751232 B = the 1700 MB ceiling (page cache, reclaimed; oom_kill 0)
```

A single publish of 46 dates (the CLI path, used earlier in the task) took **10.5 s** with a peak
`anon` of **539.6 MB**, so the task itself is small; the 24.8 minutes are 46 DAG runs including ingest,
dbt, the dbt tests and the mart load.

Verdict: **pass**: 1122 MB of 1700 MB (66%) at the worst sample, no OOM.

## 7. Linters and tests

```
python -m ruff check .            -> All checks passed!
python -m ruff format --check .   -> 57 files already formatted
python -m mypy                     -> Success: no issues found in 13 source files
python -m pytest -q                -> 22 passed in 40.77s   (with S3_* exported)
```

Verdict: **pass**.

## Notes and limits

- The lake is a full mirror: 47 dates because DuckDB holds 2026-09-30 (late orders of the 10-01 file).
  A partition is deleted only when its own date is published again; a date that disappears from DuckDB
  and is never republished keeps its object until it is.
- No compaction step: one object per table per day, 188 objects, 28 MB.
- Not run: reading the lake from Metabase (the dashboard reads the PostgreSQL marts by design).
- No new dependency: the task runs with the Airflow interpreter (duckdb + boto3 already in the image).
