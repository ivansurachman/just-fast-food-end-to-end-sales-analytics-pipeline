-- M6: net sales mix by channel, the channel's share of completed net sales.
select
    channel_key,
    sum(net_amount) as net_sales,
    100.0 * sum(net_amount) / sum(sum(net_amount)) over () as share_pct
from mart_sales_day_branch_channel
where order_date >= date '2026-10-01'
group by channel_key
order by net_sales desc
