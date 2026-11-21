-- Bronze orders as text, one row per CSV row, no cleaning.
--
-- No date filter here: bronze is the source of truth, and the pruning happens in silver (file dates
-- from the window start). Reading every object is what makes a re-run of an older date a fixpoint:
-- a partition is rebuilt from every file that can hold data for it, including files newer than the
-- run date (Ivan's decision, 2026-11-21, after the T04 idempotence finding).
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
