-- Bronze order lines as text, one row per CSV row, no cleaning.
-- No date filter, for the same idempotence reason as stg_orders; silver prunes by file date.
{{ config(materialized='view') }}

select
    order_id,
    line_no,
    menu_item_id,
    quantity,
    unit_price,
    line_amount,
    source_file_date
from read_parquet('{{ bronze_fact_glob("order_items") }}', hive_partitioning = true)
