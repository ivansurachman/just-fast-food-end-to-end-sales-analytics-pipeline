# T03: dbt silver and gold in DuckDB

Serves: 22 Nov checkpoint. Branch: `task/T03-dbt`.
Prerequisite: T02 accepted by Ivan (bronze Parquet for at least 3 days, DAG skeleton running).
Scope for 22 Nov is deliberately **minimal**: orders, order items, order changes, and the five dimensions. Out of this task (later list for the checkpoint): `fact_branch_day`, `fact_dq_daily`, P2 metrics, quarantine table, Parquet publish.

Read first: `docs/pipeline-design.md` sections 4, 6, 7, 8; `docs/data-model.md`; `docs/data-dictionary.md`. Take every column name and type from those files. Do not invent columns.

## Deliverables

| Path | Content |
|---|---|
| `dbt/dbt_project.yml`, `dbt/profiles.yml` | dbt-duckdb project. Profile reads S3 endpoint and keys from env. DuckDB file at `/opt/airflow/duckdb/jff.duckdb`. `memory_limit='1GB'`, `threads=2`. No secrets in files |
| `dbt/models/staging/` | Views over bronze Parquet with `read_parquet(..., hive_partitioning=true)`, filtered by `source_file_date` so reads are pruned to the window in design section 6 |
| `dbt/models/silver/` | `silver_orders`, `silver_order_items`, `silver_order_changes`: typed, deduplicated, defects flagged in `dq_flags` per the table in design section 7. Incremental, `delete+insert` on `order_date` for the window `[run_date - lookback_days, run_date]` |
| `dbt/models/gold/` | Dimensions `dim_date`, `dim_branch`, `dim_channel`, `dim_promo` (with NONE member), `dim_menu_item` (with UNKNOWN member), full refresh. Facts `fact_order`, `fact_order_item`, incremental on `order_date`, with the refund and cancel status applied from the changes |
| `dbt/seeds/payment_method_map.csv` | Canonical payment labels for `payment_variant` |
| `dbt/tests/` | Singular tests: lookback guard (design section 6), gross equals the sum of line amounts, silver orders equal bronze distinct orders |
| `infra/airflow/` + `Containerfile` | venv `/opt/venvs/dbt` with `dbt-core` and `dbt-duckdb`, pinned, releases older than 14 days, compatible with the image's Python (verify). DuckDB extensions `httpfs` and `parquet` pre-installed at build time |
| `compose.yaml` | New named volume `jff_duckdb` mounted into the scheduler only. `dbt/` bind-mounted (relative path) |
| `dags/jff_daily.py` | Replace the `dbt_run` and `dbt_test` placeholders with real tasks (BashOperator calling `/opt/venvs/dbt/bin/dbt`), pool `duckdb_writer` |
| `docs/versions.md` | New pins |
| `docs/verification/T03-dbt.md` | Evidence for the acceptance items |

## Rules

- Window logic follows design section 6 exactly: orders and items from file dates `X` and `X+1`, changes from file dates `X` to `run_date`. Order date is the **local date of `order_ts`**, never the file date and never parsed out of `order_id`.
- Duplicates: keep one row per `order_id` (earliest `source_file_date`) and per `(order_id, line_no)`.
- Money is integer rupiah. No floating point for money.
- One run must be safe to repeat: same command, same result.
- Load `lean-code` before writing SQL and macros. Prefer dbt generic tests over custom ones.

## Acceptance (evidence required for each)

1. `dbt build` (run plus test) passes on the 3 days from T02 with run dates in order. Show the output.
2. Repeat the last run date. Row counts and a hash of every silver and gold table are identical before and after. Show both.
3. Defects: for the 3 days, compare counts of flagged rows in silver with the sum of `injected` values in the manifests (`duplicate_orders`, `duplicate_item_rows`, `payment_null`, `payment_variant`, `platform_ref_null`, `gross_mismatch`, `unknown_menu_item`). Report both numbers per defect. A mismatch is a finding to explain, not to hide. Late-order defects are not expected to match one to one; say why.
4. Refunds: generate and ingest `2026-10-03` to `2026-10-09` (sample-data range, scale 0.02). After the last run, orders refunded in `order_changes` have status `refunded` in `fact_order` with the original `order_date`. Show a query that counts them and the count of distinct refunded `order_id` in bronze changes after dedup.
5. Lookback guard: show it passing, and show it failing on one hand-made change row older than the window (remove the row afterwards).
6. Scheduler memory peak during `dbt_run` for one full-scale day, from `podman stats`, against the 1.7 GB limit. Also `podman machine ssh free -m` before and after.
7. The whole DAG run for one date succeeds in Airflow: `wait_manifest`, `ingest_bronze`, `check_bronze`, `dbt_run`, `dbt_test`. Show the task states and the run duration.
8. `ruff`, `mypy`, `pytest` clean for any Python added. `sqlfluff` is not required.

## STOP conditions

- dbt-duckdb cannot read S3 Parquet from the container network (path style, no SSL). Report the exact error and versions.
- A full-scale day pushes the scheduler past its limit or `free -m` shows less than 1 GiB available. Report numbers; do not raise limits.
- `dbt-duckdb` does not support `delete+insert` incremental on the installed version. Report; do not switch strategy silently.
- Any column needed is missing from `docs/data-model.md`. Ask Ivan.
