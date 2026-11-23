-- M7: channel contribution margin, net sales minus COGS and platform commission, over net sales.
select
    channel_key,
    sum(net_amount) as net_sales,
    sum(cogs_amount) as cogs_amount,
    sum(commission_amount) as commission_amount,
    sum(net_amount) - sum(cogs_amount) - sum(commission_amount) as contribution_margin,
    100.0 * (sum(net_amount) - sum(cogs_amount) - sum(commission_amount))
        / nullif(sum(net_amount), 0) as contribution_margin_pct
from mart_sales_day_branch_channel
where order_date >= date '2026-10-01'
group by channel_key
order by contribution_margin desc
