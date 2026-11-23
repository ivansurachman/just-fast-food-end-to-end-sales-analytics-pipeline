-- Mart for M10 (orders by hour and weekday) and M11 (peak-hour load, the 95th percentile per branch).
--
-- Grain: (order_date, branch_key, hour_local). Counts only: M10 is the volume per hour, M11 is
-- computed from these counts in the card, never stored as a ratio or a percentile.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date'
) }}

with orders as (

    select * from {{ ref('fact_order') }}
    {% if is_incremental() %}
    where cast(order_ts_local as date) between {{ window_start_sql() }} and {{ run_date_sql() }}
    {% endif %}

)

select
    cast(order_ts_local as date) as order_date,
    branch_key,
    hour_local,
    count(*) as total_orders,
    count(*) filter (where status_final = 'completed') as completed_orders
from orders
group by 1, 2, 3
