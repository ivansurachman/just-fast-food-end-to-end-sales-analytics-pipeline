-- M17: branch reporting coverage per day, expected branch-days that actually sent orders.
select
    order_date,
    count(*) filter (where is_expected) as expected_branch_days,
    count(*) filter (where is_expected and orders_received > 0) as received_branch_days,
    count(*) filter (where is_expected and orders_received = 0) as missing_branch_days,
    100.0 * count(*) filter (where is_expected and orders_received > 0)
        / nullif(count(*) filter (where is_expected), 0) as coverage_pct
from mart_branch_coverage
where order_date >= date '2026-10-01'
group by order_date
order by order_date
