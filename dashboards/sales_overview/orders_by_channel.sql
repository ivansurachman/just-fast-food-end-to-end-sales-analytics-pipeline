-- Card 2: orders by channel.
-- total_orders counts every status, which is the denominator of the cancellation rate (M4); the
-- channel mix of orders is what the dashboard shows next to net sales (M6).
select
    channel_key,
    sum(total_orders) as orders
from mart_sales_day_branch_channel
group by channel_key
order by orders desc
