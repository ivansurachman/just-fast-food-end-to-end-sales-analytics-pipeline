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

with first_file_day as (

    -- The first day the generator produced a file. Days before it are not pipeline days: the orders
    -- of 2026-09-30 arrived in the 2026-10-01 file, and no file of their own exists to be covered.
    select min(source_file_date) as day from {{ ref('fact_order') }}

),

-- The spine is the run's window, clamped at the first file date: a branch-day is only "expected"
-- for a day the pipeline was supposed to receive. That keeps 2026-09-30 out of the coverage numbers
-- and makes the missing branch-days equal the branches the generator dropped.
days as (

    select cast(day as date) as day
    from unnest(
        generate_series(
            greatest(cast({{ window_start_sql() }} as date), (select day from first_file_day)),
            cast({{ run_date_sql() }} as date),
            interval 1 day
        )
    ) as t(day)

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
