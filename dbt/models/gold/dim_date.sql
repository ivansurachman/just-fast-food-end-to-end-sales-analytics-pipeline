-- Gold calendar, one row per day that silver covers. Full refresh every run: it is tiny.
{{ config(materialized='table') }}

with bounds as (

    select
        min(order_date) as first_day,
        max(order_date) as last_day
    from {{ ref('silver_orders') }}

),

days as (

    select cast(unnest(generate_series(first_day, last_day, interval 1 day)) as date) as date_day
    from bounds

)

select
    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    date_day as "date",
    cast(year(date_day) as integer) as "year",
    cast(month(date_day) as integer) as "month",
    cast(dayofmonth(date_day) as integer) as "day",
    -- 0 is Monday and 6 is Sunday, the same convention as promos.weekday_scope.
    cast(isodow(date_day) - 1 as integer) as weekday_number,
    strftime(date_day, '%A') as weekday_name,
    isodow(date_day) >= 6 as is_weekend
from days
