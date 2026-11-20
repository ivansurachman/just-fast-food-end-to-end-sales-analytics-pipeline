-- Silver orders: typed, deduplicated, defects flagged, one row per order_id.
--
-- Window (docs/pipeline-design.md section 6): an order with order_date X can arrive in the file of
-- X or X+1, so a run for run_date reads file dates [run_date - lookback_days, run_date] and rebuilds
-- the order_date partitions [run_date - lookback_days, run_date]. The incremental strategy replaces
-- those partitions, so running the same day twice gives the same table.
--
-- order_date is the local date of order_ts, never the file date (design section 6, data dictionary).
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date'
) }}

with source as (

    select * from {{ ref('stg_orders') }}
    {% if is_incremental() %}
    where source_file_date >= {{ window_start_sql() }}
    {% endif %}

),

deduped as (

    -- duplicate_orders: the same order sent twice. Keep the earliest file date.
    select
        *,
        row_number() over (partition by order_id order by source_file_date, order_ts) as row_in_order,
        count(*) over (partition by order_id) as rows_in_order
    from source

),

kept as (

    select * from deduped where row_in_order = 1

),

item_lines as (

    select
        order_id,
        cast(line_amount as bigint) as line_amount,
        row_number() over (partition by order_id, line_no order by source_file_date) as row_in_line
    from {{ ref('stg_order_items') }}
    {% if is_incremental() %}
    where source_file_date >= {{ window_start_sql() }}
    {% endif %}

),

item_totals as (

    -- gross_mismatch: recompute the gross from the lines instead of trusting the order row.
    select order_id, sum(line_amount) as gross_amount_from_items
    from item_lines
    where row_in_line = 1
    group by order_id

),

enriched as (

    select
        k.order_id,
        k.channel_id,
        k.status,
        k.rows_in_order,
        cast(k.branch_id as integer) as branch_id,
        cast(k.order_ts as timestamp) as order_ts_local,
        cast(cast(k.order_ts as timestamp) as date) as order_date,
        cast(k.gross_amount as bigint) as gross_amount_raw,
        t.gross_amount_from_items,
        cast(k.discount_amount as bigint) as discount_amount,
        nullif(trim(k.promo_id), '') as promo_id,
        cast(k.total_amount as bigint) as total_amount,
        cast(k.platform_commission_amount as bigint) as platform_commission_amount,
        -- DuckDB reads an empty CSV field as NULL, so every "is it empty" test coalesces first.
        coalesce(k.payment_method, '') as payment_method_raw,
        coalesce(pm.canonical_label, 'unknown') as payment_method,
        coalesce(trim(k.platform_order_ref), '') as platform_order_ref,
        k.source_file_date,
        coalesce(ch.order_origin, 'offline') as order_origin
    from kept as k
    left join item_totals as t on t.order_id = k.order_id
    left join {{ ref('payment_method_map') }} as pm
        on lower(trim(k.payment_method)) = pm.raw_label
    left join {{ ref('stg_channels') }} as ch on ch.channel_id = k.channel_id

),

final as (

    select
        order_id,
        branch_id,
        channel_id,
        order_ts_local,
        order_date,
        status,
        coalesce(gross_amount_from_items, gross_amount_raw) as gross_amount,
        gross_amount_raw,
        discount_amount,
        promo_id,
        total_amount,
        platform_commission_amount,
        payment_method,
        payment_method_raw,
        platform_order_ref,
        source_file_date,
        list_filter([
            case when rows_in_order > 1 then 'dup_order' end,
            case when payment_method_raw = '' then 'payment_null' end,
            case
                when payment_method_raw <> '' and payment_method <> payment_method_raw
                    then 'payment_variant'
            end,
            case when order_origin = 'online' and platform_order_ref = '' then 'platform_ref_null' end,
            case
                when gross_amount_from_items is not null
                    and gross_amount_raw <> gross_amount_from_items
                    then 'gross_mismatch'
            end,
            case when source_file_date > order_date then 'late_arrival' end
        ], flag -> flag is not null) as dq_flags
    from enriched

)

select * from final
{% if is_incremental() %}
where order_date between {{ window_start_sql() }} and {{ run_date_sql() }}
{% endif %}
