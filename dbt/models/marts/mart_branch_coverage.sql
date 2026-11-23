-- Mart for M17 (branch reporting coverage) and the M8 denominator (orders received per branch-day).
--
-- Grain: (order_date, branch_key). is_expected comes from fact_branch_day, which derives it from
-- dim_branch.open_date; orders_received counts every order that arrived, net_amount and
-- completed_orders only the completed ones.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date'
) }}

with branch_days as (

    select * from {{ ref('fact_branch_day') }}
    {% if is_incremental() %}
    where date_key between cast(strftime({{ window_start_sql() }}, '%Y%m%d') as integer)
                      and cast(strftime({{ run_date_sql() }}, '%Y%m%d') as integer)
    {% endif %}

),

sales as (

    select
        cast(order_ts_local as date) as order_date,
        branch_key,
        count(*) filter (where status_final = 'completed') as completed_orders,
        coalesce(sum(net_amount) filter (where status_final = 'completed'), 0) as net_amount
    from {{ ref('fact_order') }}
    {% if is_incremental() %}
    where cast(order_ts_local as date) between {{ window_start_sql() }} and {{ run_date_sql() }}
    {% endif %}
    group by 1, 2

)

select
    cast(strptime(cast(b.date_key as varchar), '%Y%m%d') as date) as order_date,
    b.branch_key,
    b.is_expected,
    b.orders_received,
    b.late_arrival_orders,
    coalesce(s.completed_orders, 0) as completed_orders,
    coalesce(s.net_amount, 0) as net_amount
from branch_days as b
left join sales as s on s.order_date = cast(strptime(cast(b.date_key as varchar), '%Y%m%d') as date)
                    and s.branch_key = b.branch_key
