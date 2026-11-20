-- Gold channel dimension. channel_key = channel_id.
{{ config(materialized='table') }}

select
    channel_id as channel_key,
    order_origin,
    platform,
    service_type,
    cast(commission_rate as decimal(9, 6)) as commission_rate
from {{ ref('stg_channels') }}
