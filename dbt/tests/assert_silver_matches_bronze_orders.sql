-- Reconciliation for the run's window: silver must hold every distinct order bronze received whose
-- order date falls in [run_date - lookback_days, run_date].
--
-- The comparison is scoped to the window on purpose. Reading the whole lake would fail as soon as a
-- day newer than run_date exists, and reading the staging view alone would miss the older days that
-- silver still holds.
with bronze_orders as (

    select distinct order_id
    from read_parquet('{{ bronze_fact_glob("orders") }}', hive_partitioning = true)
    where cast(cast(order_ts as timestamp) as date)
        between {{ window_start_sql() }} and {{ run_date_sql() }}
      and source_file_date <= {{ run_date_sql() }}

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
