-- M16: promo average order value lift against orders without a promotion (promo_key = NONE).
-- Two ratios of sums, compared; no stored AOV is averaged.
with per_promo as (

    select
        promo_key,
        sum(order_count) as orders,
        sum(net_amount) as net_amount
    from mart_promo_day
    where order_date >= date '2026-10-01'
    group by promo_key

),

with_aov as (

    select promo_key, orders, net_amount / nullif(orders, 0) as aov
    from per_promo

)

select
    p.promo_key,
    p.orders,
    p.aov,
    b.aov as aov_without_promo,
    100.0 * (p.aov - b.aov) / nullif(b.aov, 0) as aov_lift_pct
from with_aov as p
cross join (select aov from with_aov where promo_key = 'NONE') as b
where p.promo_key <> 'NONE'
order by aov_lift_pct desc
