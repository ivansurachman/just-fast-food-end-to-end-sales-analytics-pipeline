-- M11: peak-hour load per branch, the 95th percentile of the hourly order volume.
-- The percentile is computed here from the hourly counts, never stored in a mart.
select
    branch_key,
    round(avg(hourly_orders), 1) as average_hourly_orders,
    percentile_cont(0.95) within group (order by hourly_orders) as peak_hour_orders_p95
from (
    select
        branch_key,
        order_date,
        hour_local,
        sum(total_orders) as hourly_orders
    from mart_hourly
    where order_date >= date '2026-10-01'
    group by 1, 2, 3
) as hourly
group by branch_key
order by peak_hour_orders_p95 desc
