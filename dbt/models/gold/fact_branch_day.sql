-- Gold branch-day fact: one row per branch and calendar day, expected or not.
--
-- `is_expected` comes from dim_branch.open_date, never from the generator manifest (docs/data-model.md):
-- a branch is expected on every day from its opening date on. A day the branch sent no file still has a
-- row, with `orders_received = 0`, which is what M17 (coverage) and the M8 denominator need.
--
-- Incremental on date_key with the same 10-day window as the other facts.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='date_key'
) }}

with bounds as (

    select
        min(cast(order_ts_local as date)) as first_day,
        max(cast(order_ts_local as date)) as last_day
    from {{ ref('fact_order') }}

),

-- The spine is the run's window, not all of history: a branch-day is only "expected" for a day the
-- pipeline processes. That keeps 2026-09-30 (late arrivals of the 2026-10-01 file, no file of its
-- own) out of the coverage numbers.
days as (

    select day
    from (
        select cast(unnest(generate_series(first_day, last_day, interval 1 day)) as date) as day
        from bounds
    )
    where day between {{ window_start_sql() }} and {{ run_date_sql() }}

),

branches as (

    select branch_key, open_date from {{ ref('dim_branch') }}

),

received as (

    select
        cast(order_ts_local as date) as day,
        branch_key,
        count(*) as orders_received,
        count(*) filter (
            where source_file_date > cast(order_ts_local as date)
        ) as late_arrival_orders
    from {{ ref('fact_order') }}
    group by 1, 2

),

spine as (

    select d.day, b.branch_key, b.open_date <= d.day as is_expected
    from days as d
    cross join branches as b

)

select
    cast(strftime(s.day, '%Y%m%d') as integer) as date_key,
    s.branch_key,
    s.is_expected,
    coalesce(r.orders_received, 0) as orders_received,
    coalesce(r.late_arrival_orders, 0) as late_arrival_orders
from spine as s
left join received as r on r.day = s.day and r.branch_key = s.branch_key
