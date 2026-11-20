-- Silver order lines: typed, deduplicated on (order_id, line_no), defects flagged.
--
-- The line's order_date and branch come from silver_orders, so a refund or a late order rebuilds the
-- same partitions in both tables. A line whose order is not in the window is not built here.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date'
) }}

with source as (

    select * from {{ ref('stg_order_items') }}
    {% if is_incremental() %}
    where source_file_date >= {{ window_start_sql() }}
    {% endif %}

),

deduped as (

    -- duplicate_item_rows: the same (order_id, line_no) sent twice. Keep the earliest file date.
    select
        *,
        row_number() over (
            partition by order_id, line_no order by source_file_date
        ) as row_in_line,
        count(*) over (partition by order_id, line_no) as rows_in_line
    from source

),

kept as (

    select * from deduped where row_in_line = 1

),

orders as (

    select order_id, order_date, branch_id from {{ ref('silver_orders') }}

),

final as (

    select
        k.order_id,
        cast(k.line_no as integer) as line_no,
        k.menu_item_id,
        cast(k.quantity as integer) as quantity,
        cast(k.unit_price as bigint) as unit_price,
        cast(k.line_amount as bigint) as line_amount,
        o.order_date,
        o.branch_id,
        k.source_file_date,
        m.menu_item_id is not null as is_known_item,
        list_filter([
            case when k.rows_in_line > 1 then 'dup_item' end,
            case when m.menu_item_id is null then 'unknown_item' end,
            case when k.source_file_date > o.order_date then 'late_arrival' end
        ], flag -> flag is not null) as dq_flags
    from kept as k
    inner join orders as o on o.order_id = k.order_id
    left join {{ ref('stg_menu_items') }} as m on m.menu_item_id = k.menu_item_id

)

select * from final
{% if is_incremental() %}
where order_date between {{ window_start_sql() }} and {{ run_date_sql() }}
{% endif %}
