-- Bronze refund changes as text. Only file dates inside the reprocessing window are read: a change
-- older than that cannot affect any order_date the run rebuilds (design section 6).
{{ config(materialized='view') }}

select
    change_id,
    order_id,
    previous_status,
    new_status,
    changed_at,
    source_file_date
from read_parquet('{{ bronze_fact_glob("order_changes") }}', hive_partitioning = true)
where source_file_date <= {{ run_date_sql() }}
  and source_file_date >= {{ window_start_sql() }}
