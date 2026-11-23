-- M10: order volume by hour of day and weekday. weekday_number counts from Monday = 0, the same
-- convention as dim_date, so the card does not need the DuckDB dimension in PostgreSQL.
select
    cast(extract(isodow from order_date) as integer) - 1 as weekday_number,
    to_char(order_date, 'Dy') as weekday,
    hour_local,
    sum(total_orders) as orders
from mart_hourly
where order_date >= date '2026-10-01'
group by 1, 2, 3
order by 1, 3
