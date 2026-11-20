-- Bronze channel dimension as text.
{{ config(materialized='view') }}

select
    channel_id,
    order_origin,
    platform,
    service_type,
    commission_rate
from read_parquet('{{ bronze_dimension_path("channels") }}')
