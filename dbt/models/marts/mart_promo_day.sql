-- Mart for M15 (discount rate by promo) and M16 (promo average order value lift).
--
-- Grain: (order_date, promo_key, channel_key), completed orders. gross_amount is the denominator of
-- the discount rate and net_amount / order_count the AOV; neither ratio is stored.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date'
) }}

with orders as (

    select * from {{ ref('fact_order') }}
    where status_final = 'completed'
    {% if is_incremental() %}
      and cast(order_ts_local as date) between {{ window_start_sql() }} and {{ run_date_sql() }}
    {% endif %}

)

select
    cast(order_ts_local as date) as order_date,
    promo_key,
    channel_key,
    count(*) as order_count,
    sum(gross_amount) as gross_amount,
    sum(discount_amount) as discount_amount,
    sum(net_amount) as net_amount
from orders
group by 1, 2, 3
