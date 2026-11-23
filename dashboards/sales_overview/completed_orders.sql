-- M2: completed orders per day. Numerator only; the rate cards divide by their own denominators.
select
    order_date,
    sum(completed_orders) as completed_orders
from mart_sales_day_branch_channel
where order_date >= date '2026-10-01'
group by order_date
order by order_date
