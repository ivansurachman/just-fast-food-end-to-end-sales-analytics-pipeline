-- Mart for M12 (item sales mix) and M13 (item gross margin).
--
-- Grain: (order_date, menu_item_key), completed orders only, because M12 and M13 are sales measures.
-- line_amount and line_cogs are the numerators of the margin; no percentage is stored.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date'
) }}

with items as (

    select * from {{ ref('fact_order_item') }}
    where order_status_final = 'completed'
    {% if is_incremental() %}
      and date_key between cast(strftime({{ window_start_sql() }}, '%Y%m%d') as integer)
                     and cast(strftime({{ run_date_sql() }}, '%Y%m%d') as integer)
    {% endif %}

)

select
    cast(strptime(cast(date_key as varchar), '%Y%m%d') as date) as order_date,
    menu_item_key,
    sum(quantity) as quantity,
    sum(line_amount) as line_amount,
    sum(line_cogs) as line_cogs
from items
group by 1, 2
