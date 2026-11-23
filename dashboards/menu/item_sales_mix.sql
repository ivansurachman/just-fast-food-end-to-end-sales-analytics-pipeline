-- M12: item sales mix, each menu item's share of completed line sales.
select
    menu_item_key,
    sum(quantity) as quantity,
    sum(line_amount) as line_amount,
    100.0 * sum(line_amount) / sum(sum(line_amount)) over () as share_pct
from mart_item_day
where order_date >= date '2026-10-01'
group by menu_item_key
order by line_amount desc
