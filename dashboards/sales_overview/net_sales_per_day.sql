-- Card 1: net sales per day.
-- Numerators only: the mart stores net_amount of completed orders, the sum is the metric M1.
select
    order_date,
    sum(net_amount) as net_sales
from mart_sales_day_branch_channel
group by order_date
order by order_date
