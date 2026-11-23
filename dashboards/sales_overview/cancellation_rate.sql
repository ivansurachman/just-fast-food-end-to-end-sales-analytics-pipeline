-- M4: cancellation rate, cancelled orders over all orders.
select
    order_date,
    sum(cancelled_orders) as cancelled_orders,
    sum(total_orders) as total_orders,
    100.0 * sum(cancelled_orders) / nullif(sum(total_orders), 0) as cancellation_rate_pct
from mart_sales_day_branch_channel
where order_date >= date '2026-10-01'
group by order_date
order by order_date
