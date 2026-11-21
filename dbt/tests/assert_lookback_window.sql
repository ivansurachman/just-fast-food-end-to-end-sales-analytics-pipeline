-- Lookback guard (docs/pipeline-design.md section 6).
--
-- A refund is applied to the order_date partition of its order, and a run only rebuilds the
-- partitions [run_date - lookback_days, run_date]. If a refund reaches its order later than
-- lookback_days, a run can miss it and the partition is silently wrong.
--
-- The guard is therefore about the lag of every change, not about the run date: for each change,
-- lag = source_file_date - order_date must be at most lookback_days. It reads the bronze changes
-- through staging (which no longer filters by date), so it sees the whole history on every run.
-- A change whose order is not in the dataset at all cannot be measured and is not counted here;
-- acceptance item 4d lists those separately.
with changes as (

    select
        c.change_id,
        c.order_id,
        c.source_file_date,
        cast(cast(o.order_ts as timestamp) as date) as order_date
    from {{ ref('stg_order_changes') }} as c
    inner join {{ ref('stg_orders') }} as o on o.order_id = c.order_id

)

select
    change_id,
    order_id,
    order_date,
    source_file_date,
    date_diff('day', order_date, source_file_date) as lag_days
from changes
where date_diff('day', order_date, source_file_date) > {{ var('lookback_days', 10) }}
