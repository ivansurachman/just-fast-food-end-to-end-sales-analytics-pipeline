-- Reconciliation: silver must hold exactly the distinct orders the bronze lake received.
--
-- This reads every bronze object, not the windowed staging view: the staging views stop at
-- run_date, while silver keeps the whole history, so a run for an older date would otherwise
-- compare different populations.
with bronze as (

    select count(distinct order_id) as orders_received
    from read_parquet('{{ bronze_fact_glob("orders") }}', hive_partitioning = true)

),

silver as (

    select count(*) as orders_kept
    from {{ ref('silver_orders') }}

)

select *
from bronze, silver
where bronze.orders_received <> silver.orders_kept
