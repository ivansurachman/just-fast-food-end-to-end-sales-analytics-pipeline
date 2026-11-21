-- Reconciliation for the run's window: silver must hold every distinct order bronze received whose
-- order date falls in [run_date - lookback_days, run_date].
--
-- Both sides are scoped to the window, and the bronze side reads every file (a late order for a
-- window date can arrive in a file newer than run_date), which is the same rule silver follows.
with bronze_orders as (

    select distinct order_id
    from read_parquet('{{ bronze_fact_glob("orders") }}', hive_partitioning = true)
    where cast(cast(order_ts as timestamp) as date)
        between {{ window_start_sql() }} and {{ run_date_sql() }}

),

silver_orders as (

    select order_id
    from {{ ref('silver_orders') }}
    where order_date between {{ window_start_sql() }} and {{ run_date_sql() }}

)

select
    (select count(*) from bronze_orders) as bronze_orders,
    (select count(*) from silver_orders) as silver_orders
where (select count(*) from bronze_orders) <> (select count(*) from silver_orders)
