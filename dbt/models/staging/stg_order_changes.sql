-- Bronze refund changes as text.
-- No date filter: silver and the lookback guard decide which file dates matter, so a re-run of an
-- older date still sees refunds that arrived later.
{{ config(materialized='view') }}

select
    change_id,
    order_id,
    previous_status,
    new_status,
    changed_at,
    source_file_date
from read_parquet('{{ bronze_fact_glob("order_changes") }}', hive_partitioning = true)
