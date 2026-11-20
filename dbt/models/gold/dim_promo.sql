-- Gold promo dimension plus the NONE member, so an order without a promo still resolves its key.
{{ config(materialized='table') }}

with promos as (

    select
        promo_id as promo_key,
        promo_name,
        discount_type,
        cast(discount_value as integer) as discount_value,
        cast(min_order_amount as bigint) as min_order_amount,
        cast(max_discount_amount as bigint) as max_discount_amount,
        cast(valid_from as date) as valid_from,
        cast(valid_to as date) as valid_to
    from {{ ref('stg_promos') }}

),

none_member as (

    select
        'NONE' as promo_key,
        'No promotion' as promo_name,
        'none' as discount_type,
        0 as discount_value,
        0 as min_order_amount,
        0 as max_discount_amount,
        cast(null as date) as valid_from,
        cast(null as date) as valid_to

)

select * from promos
union all
select * from none_member
