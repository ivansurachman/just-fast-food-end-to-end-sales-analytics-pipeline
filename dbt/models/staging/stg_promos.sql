-- Bronze promo dimension as text.
{{ config(materialized='view') }}

select
    promo_id,
    promo_name,
    discount_type,
    discount_value,
    min_order_amount,
    max_discount_amount,
    valid_from,
    valid_to,
    channel_scope,
    weekday_scope
from read_parquet('{{ bronze_dimension_path("promos") }}')
