-- Lookback guard (docs/pipeline-design.md section 6).
--
-- A run rebuilds order_date partitions [run_date - lookback_days, run_date]. If a refund in the
-- window points at an order older than that, the refund would be applied to a partition nobody
-- rewrites, so the fixpoint would be silently wrong. Fail loudly instead.
--
-- Order dates come from bronze, not from silver: on a fresh build silver does not hold orders older
-- than the window either, and the guard has to see them.
select distinct
    c.change_id,
    c.order_id,
    cast(cast(o.order_ts as timestamp) as date) as order_date,
    c.source_file_date
from {{ ref('stg_order_changes') }} as c
inner join {{ ref('stg_orders') }} as o on o.order_id = c.order_id
where cast(cast(o.order_ts as timestamp) as date) < {{ window_start_sql() }}
