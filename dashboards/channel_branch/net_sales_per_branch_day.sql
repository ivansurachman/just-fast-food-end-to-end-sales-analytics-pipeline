-- M8: net sales per branch-day. The numerator is completed net sales, the denominator is the number
-- of expected branch-days that came from fact_branch_day, not from the manifests.
select
    branch_key,
    sum(net_amount) as net_sales,
    count(*) filter (where is_expected) as expected_days,
    sum(net_amount) / nullif(count(*) filter (where is_expected), 0) as net_sales_per_branch_day
from mart_branch_coverage
where order_date >= date '2026-10-01'
group by branch_key
order by net_sales_per_branch_day desc
