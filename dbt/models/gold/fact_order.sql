-- Gold order fact, grain: one order.
--
-- Incremental on date_key (the local order date), the same window as silver: every run replaces the
-- partitions [run_date - lookback_days, run_date], so a refund that arrives today rewrites the
-- partition of the order date (docs/data-model.md).
--
-- Rules from docs/data-model.md: gross_amount is recomputed from the lines, net_amount is gross minus
-- discount, status_final turns refunded when a refund change exists, order_ts_utc uses the branch
-- timezone, cogs_amount is quantity times unit_cost over the order's lines.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='date_key'
) }}

with orders as (

    select * from {{ ref('silver_orders') }}
    {% if is_incremental() %}
    where order_date between {{ window_start_sql() }} and {{ run_date_sql() }}
    {% endif %}

),

refunds as (

    -- A refund is attributed to the order date, never to the day it happened.
    select order_id, min(changed_at_local) as refunded_at_local
    from {{ ref('silver_order_changes') }}
    where new_status = 'refunded'
    group by order_id

),

item_cogs as (

    select
        i.order_id,
        sum(i.quantity * coalesce(m.unit_cost, 0)) as cogs_amount
    from {{ ref('silver_order_items') }} as i
    left join {{ ref('dim_menu_item') }} as m on m.menu_item_key = i.menu_item_id
    {% if is_incremental() %}
    where i.order_date between {{ window_start_sql() }} and {{ run_date_sql() }}
    {% endif %}
    group by i.order_id

)

select
    o.order_id,
    cast(strftime(o.order_date, '%Y%m%d') as integer) as date_key,
    o.branch_id as branch_key,
    o.channel_id as channel_key,
    coalesce(o.promo_id, 'NONE') as promo_key,
    o.order_ts_local,
    timezone('UTC', timezone(b.timezone, o.order_ts_local)) as order_ts_utc,
    cast(extract(hour from o.order_ts_local) as integer) as hour_local,
    case when r.order_id is not null then 'refunded' else o.status end as status_final,
    r.refunded_at_local,
    o.source_file_date,
    o.gross_amount,
    o.discount_amount,
    o.gross_amount - o.discount_amount as net_amount,
    o.platform_commission_amount,
    coalesce(c.cogs_amount, 0) as cogs_amount,
    o.payment_method,
    o.platform_order_ref,
    o.dq_flags
from orders as o
inner join {{ ref('dim_branch') }} as b on b.branch_key = o.branch_id
left join refunds as r on r.order_id = o.order_id
left join item_cogs as c on c.order_id = o.order_id
