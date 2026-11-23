-- M13: item gross margin, line sales minus line COGS over line sales.
select
    menu_item_key,
    sum(line_amount) as line_amount,
    sum(line_cogs) as line_cogs,
    sum(line_amount) - sum(line_cogs) as gross_margin,
    100.0 * (sum(line_amount) - sum(line_cogs)) / nullif(sum(line_amount), 0) as gross_margin_pct
from mart_item_day
where order_date >= date '2026-10-01'
group by menu_item_key
order by gross_margin_pct desc
