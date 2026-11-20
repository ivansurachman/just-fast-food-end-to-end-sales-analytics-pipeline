-- Gold order line fact, grain: one line of one order.
--
-- Incremental on date_key, the same window as fact_order. The order status is denormalised from
-- fact_order so a line can be filtered by status without a join (docs/er_diagram.dot).
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='date_key'
) }}

with items as (

    select * from {{ ref('silver_order_items') }}
    {% if is_incremental() %}
    where order_date between {{ window_start_sql() }} and {{ run_date_sql() }}
    {% endif %}

),

orders as (

    select order_id, status_final from {{ ref('fact_order') }}

),

menu_items as (

    select menu_item_key, unit_cost from {{ ref('dim_menu_item') }}

),

keyed as (

    -- An unknown menu item maps to the UNKNOWN member instead of breaking the foreign key.
    select items.*, case when items.is_known_item then items.menu_item_id else 'UNKNOWN' end as item_key
    from items

)

select
    k.order_id,
    k.line_no,
    cast(strftime(k.order_date, '%Y%m%d') as integer) as date_key,
    k.branch_id as branch_key,
    k.item_key as menu_item_key,
    o.status_final as order_status_final,
    k.quantity,
    k.unit_price,
    k.line_amount,
    coalesce(m.unit_cost, 0) as unit_cost,
    k.quantity * coalesce(m.unit_cost, 0) as line_cogs
from keyed as k
inner join orders as o on o.order_id = k.order_id
left join menu_items as m on m.menu_item_key = k.item_key
