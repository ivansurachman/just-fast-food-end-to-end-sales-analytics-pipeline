-- M3: average order value, net sales divided by completed orders. A ratio of two sums, never an
-- average of per-row values (docs/data-model.md).
select
    order_date,
    sum(net_amount) / nullif(sum(completed_orders), 0) as average_order_value
from mart_sales_day_branch_channel
where order_date >= date '2026-10-01'
group by order_date
order by order_date
