-- Mart for the "Sales overview" dashboard: net sales per day, branch and channel.
--
-- Grain: one row per (order_date, branch_key, channel_key). Only numerators and denominators are
-- stored, never finished ratios, so the dashboard cannot average a rate wrongly
-- (docs/pipeline-design.md section 8, docs/data-model.md metrics M1 to M8):
--   M1 net sales           -> net_amount (completed orders)
--   M2 completed orders    -> completed_orders
--   M3 average order value -> net_amount / completed_orders
--   M4 cancellation rate   -> cancelled_orders / total_orders
--   M6 net sales mix by channel, M7 margin from net, cogs and commission, M8 net sales per branch-day.
--
-- Sums cover completed orders only: cancelled and refunded orders keep their amounts but are not
-- sales (docs/data-dictionary.md, "Business rules"). The counts cover every status, so the rates
-- have a denominator.
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

),

daily as (

    select
        cast(order_ts_local as date) as order_date,
        branch_key,
        channel_key,
        count(*) as total_orders,
        count(*) filter (where status_final = 'completed') as completed_orders,
        count(*) filter (where status_final = 'cancelled') as cancelled_orders,
        count(*) filter (where status_final = 'refunded') as refunded_orders,
        coalesce(sum(gross_amount) filter (where status_final = 'completed'), 0) as gross_amount,
        coalesce(sum(discount_amount) filter (where status_final = 'completed'), 0) as discount_amount,
        coalesce(sum(net_amount) filter (where status_final = 'completed'), 0) as net_amount,
        coalesce(sum(cogs_amount) filter (where status_final = 'completed'), 0) as cogs_amount,
        coalesce(
            sum(platform_commission_amount) filter (where status_final = 'completed'), 0
        ) as commission_amount
    from orders
    group by 1, 2, 3

)

select
    order_date,
    branch_key,
    channel_key,
    cast(total_orders as bigint) as total_orders,
    cast(completed_orders as bigint) as completed_orders,
    cast(cancelled_orders as bigint) as cancelled_orders,
    cast(refunded_orders as bigint) as refunded_orders,
    cast(gross_amount as bigint) as gross_amount,
    cast(discount_amount as bigint) as discount_amount,
    cast(net_amount as bigint) as net_amount,
    cast(cogs_amount as bigint) as cogs_amount,
    cast(commission_amount as bigint) as commission_amount
from daily
