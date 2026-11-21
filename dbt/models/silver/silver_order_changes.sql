-- Silver refund changes: typed, deduplicated on change_id, with the order_date they rewrite.
--
-- A change whose order is not in silver yet (a refund that arrives before its late order, data
-- dictionary) is dropped: it is picked up by the run that brings the order, while its file date is
-- still inside the lookback window.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date'
) }}

with source as (

    select * from {{ ref('stg_order_changes') }}
    {% if is_incremental() %}
    -- A change in a file older than the window was applied by an earlier run; only newer files can
    -- still change a partition the window rebuilds.
    where source_file_date >= {{ window_start_sql() }}
    {% endif %}

),

deduped as (

    select
        *,
        row_number() over (partition by change_id order by source_file_date) as row_in_change
    from source

),

kept as (

    select * from deduped where row_in_change = 1

),

orders as (

    select order_id, order_date, branch_id from {{ ref('silver_orders') }}

),

final as (

    select
        c.change_id,
        c.order_id,
        c.previous_status,
        c.new_status,
        cast(c.changed_at as timestamp) as changed_at_local,
        o.order_date,
        o.branch_id,
        c.source_file_date
    from kept as c
    inner join orders as o on o.order_id = c.order_id

)

select * from final
{% if is_incremental() %}
where order_date between {{ window_start_sql() }} and {{ run_date_sql() }}
{% endif %}
