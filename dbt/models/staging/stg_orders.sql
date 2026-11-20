-- Bronze orders as text, one row per CSV row, no cleaning.
-- Filtered to file dates up to the run date so a run never reads a day that is still arriving.
{{ config(materialized='view') }}

select
    order_id,
    branch_id,
    channel_id,
    order_ts,
    status,
    gross_amount,
    discount_amount,
    promo_id,
    total_amount,
    platform_commission_amount,
    payment_method,
    platform_order_ref,
    source_file_date
from read_parquet('{{ bronze_fact_glob("orders") }}', hive_partitioning = true)
where source_file_date <= {{ run_date_sql() }}
