# Lake layout

Two buckets on SeaweedFS (S3 API), both reachable from the host at `http://127.0.0.1:8333` and from
the containers at `http://seaweedfs:8333`. The file browser is at `http://127.0.0.1:8888/buckets/`.

| Bucket | Written by | Content |
|---|---|---|
| `jff-raw` | `jff-gen` | The generator's CSV, one folder per file date, plus the day-complete manifest |
| `jff-lake` | `ingest_bronze`, `publish_parquet` | Bronze Parquet, and the published silver and gold Parquet |

## `jff-raw` (source of truth for replay)

```
jff-raw/orders/dt=YYYY-MM-DD/orders.csv
jff-raw/order_items/dt=YYYY-MM-DD/order_items.csv
jff-raw/order_changes/dt=YYYY-MM-DD/order_changes.csv
jff-raw/dimensions/{branches,channels,menu_items,promos}.csv
jff-raw/_manifests/dt=YYYY-MM-DD/manifest.json      written last, so its presence means complete
```

`dt=` is the **file date**: the day the file was produced. It is not always the order date, because a
day's file also carries the previous day's late orders.

## `jff-lake/bronze` (all columns as text, replayable)

```
jff-lake/bronze/<entity>/source_file_date=YYYY-MM-DD/<entity>.parquet     orders, order_items, order_changes
jff-lake/bronze/dimensions/<dimension>.parquet                            branches, channels, menu_items, promos
```

One object per entity per file date, written by `ingest_bronze` and overwritten on every re-ingest
(same input, same bytes). `source_file_date` is a real column in the object **and** the hive
partition; DuckDB derives it from the path when `hive_partitioning = true`.

## `jff-lake/silver` and `jff-lake/gold` (derived from DuckDB)

```
jff-lake/silver/silver_orders/order_date=YYYY-MM-DD/part.parquet
jff-lake/silver/silver_order_items/order_date=YYYY-MM-DD/part.parquet
jff-lake/gold/fact_order/order_date=YYYY-MM-DD/part.parquet
jff-lake/gold/fact_order_item/order_date=YYYY-MM-DD/part.parquet
```

- One object per table per **order date**, named `part.parquet` every time. A rewrite of a date
  overwrites the same object, so the same command over the same window produces the same objects.
- Written with `COPY ... (FORMAT PARQUET, COMPRESSION zstd)` by `pipelines/publish_parquet.py`.
- `silver_orders` and `silver_order_items` partition on their `order_date` column; `fact_order` and
  `fact_order_item` partition on the same day expressed as their `date_key` (`YYYYMMDD` integer), so
  the folder name is still the order date.
- **A partition with no rows deletes its object** instead of writing an empty file, so a partition that
  disappears from DuckDB cannot survive in the lake.
- The window is the same 10-day window the rest of the pipeline uses (`--ds`, `--lookback-days`), so a
  daily run republishes its last ten days and a backfill of the whole range leaves one object per day.

Reading it:

```sql
select * from read_parquet('s3://jff-lake/silver/silver_orders/*/part.parquet', hive_partitioning = true);
```

The partition column comes from the path, and DuckDB prunes to the folders a filter names.

## The rule that decides where to look

**Parquet is derived; DuckDB is the source for the marts.** `jff.duckdb` (named volume `jff_duckdb`)
holds silver and gold and is what dbt and `load_marts` write and read; the lake is a copy published
for the rubric item on partitioning and for anyone who wants the data without the database file.
Losing `jff.duckdb` is recoverable: delete it, re-run the backfill, and `publish_parquet` rewrites the
same objects.

Bronze is the one exception: it is written before dbt and is the replay source for silver and gold, so
it is a source, not a derived copy.
