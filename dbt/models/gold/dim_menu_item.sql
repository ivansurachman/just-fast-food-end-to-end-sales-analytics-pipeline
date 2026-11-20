-- Gold menu item dimension plus the UNKNOWN member for the unknown_menu_item defect, so every
-- line resolves a key. The UNKNOWN member has zero cost, so an unknown item adds no COGS.
{{ config(materialized='table') }}

with items as (

    select
        menu_item_id as menu_item_key,
        item_name,
        category,
        cast(unit_price as bigint) as unit_price,
        cast(unit_cost as bigint) as unit_cost,
        cast(is_active as boolean) as is_active
    from {{ ref('stg_menu_items') }}

),

unknown_member as (

    select
        'UNKNOWN' as menu_item_key,
        'Unknown item' as item_name,
        'unknown' as category,
        0 as unit_price,
        0 as unit_cost,
        false as is_active

)

select * from items
union all
select * from unknown_member
