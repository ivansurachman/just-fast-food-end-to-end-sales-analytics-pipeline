-- M5: refund rate, refunded orders over completed plus refunded orders.
select
    order_date,
    sum(refunded_orders) as refunded_orders,
    sum(completed_orders) as completed_orders,
    sum(completed_orders) + sum(refunded_orders) as settled_orders,
    100.0 * sum(refunded_orders)
        / nullif(sum(completed_orders) + sum(refunded_orders), 0) as refund_rate_pct
from mart_sales_day_branch_channel
where order_date >= date '2026-10-01'
group by order_date
order by order_date
