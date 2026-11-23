-- Card 1: net sales per day.
-- Numerators only: the mart stores net_amount of completed orders, the sum is the metric M1.
-- 2026-09-30 is not part of the demo window: it only holds the delayed orders that arrived in the
-- 2026-10-01 file, so showing it would look like a ramp from zero (T04b fix).
select
    order_date,
    sum(net_amount) as net_sales
from mart_sales_day_branch_channel
where order_date >= date '2026-10-01'
group by order_date
order by order_date
