# T05: publish silver and gold to the lake as partitioned Parquet

Branch: `task/T05-parquet` (from `main`). Serves the rubric items on partitioning and the question "where is the lake". Decision D1 stays: DuckDB is the compute store and Parquet is a derived, published layer.

Read first: `docs/pipeline-design.md` sections 3, 4, 5.

## Deliverables

- `pipelines/publish_parquet.py`: CLI `--ds`, `--lookback-days`. For every `order_date` in the window and for each of `silver_orders`, `silver_order_items`, `fact_order`, `fact_order_item`: `COPY (SELECT * FROM <table> WHERE <order date column> = X) TO 's3://jff-lake/<layer>/<table>/order_date=X/part.parquet' (FORMAT PARQUET, COMPRESSION zstd)`. One file per partition with a fixed name, so a rewrite overwrites the same object. If a partition has zero rows, delete the object if it exists, so no stale partition survives.
- DAG task `publish_parquet` after `load_marts`, same pool `duckdb_writer`.
- `docs/lake-layout.md`: bucket layout for bronze, silver and gold, the rule "Parquet is derived, DuckDB is the source for marts", and the delete rule above.
- Tests for the partition path and the empty-partition delete (against the compose SeaweedFS, skipped if unreachable).
- `docs/verification/T05-parquet.md`.

## Rules

- Use DuckDB `COPY`; no pandas. Memory limit stays `1GB`, `threads=2`.
- Same command, same objects: re-running a date must not change any object.
- Load `lean-code` first. No new dependencies unless unavoidable (pin and record in `docs/versions.md`).

## Acceptance (evidence for each)

1. After a DAG run, the SeaweedFS filer (`http://127.0.0.1:8888/buckets/jff-lake/`) shows partitions for all four tables. Report the object count per table (expect one per day, 46 days).
2. Row counts: for each table, rows read back with `read_parquet('s3://jff-lake/<layer>/<table>/*/part.parquet', hive_partitioning=true)` equal rows in the DuckDB table.
3. Partition pruning: `EXPLAIN ANALYZE` of a filter on one `order_date` over the Parquet glob shows only one file scanned. Paste the relevant lines.
4. Idempotence: re-run one date in the middle. ETags (or hashes) of all objects are identical before and after.
5. Empty partition: show the delete rule working with one hand-made case (then restore).
6. Scheduler peak `anon` memory and duration of the task for the 46-day backfill.
7. `ruff`, `mypy`, `pytest` clean.

## STOP

- DuckDB cannot write the S3 path with the existing endpoint settings. Report the exact error.
- The task pushes the scheduler near its limit. Report numbers.
