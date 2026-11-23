-- M15: discount rate by promo, discount over gross for completed orders.
select
    promo_key,
    sum(gross_amount) as gross_amount,
    sum(discount_amount) as discount_amount,
    100.0 * sum(discount_amount) / nullif(sum(gross_amount), 0) as discount_rate_pct
from mart_promo_day
where order_date >= date '2026-10-01'
group by promo_key
order by discount_rate_pct desc
