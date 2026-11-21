-- Card 3: top 10 branches by net sales (M8 aggregated over the window).
select
    branch_key,
    sum(net_amount) as net_sales
from mart_sales_day_branch_channel
group by branch_key
order by net_sales desc
limit 10
