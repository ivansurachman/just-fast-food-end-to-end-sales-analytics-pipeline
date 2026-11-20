-- Bronze branch dimension as text (written once, no date partition).
{{ config(materialized='view') }}

select
    branch_id,
    branch_code,
    branch_name,
    city,
    region,
    timezone,
    outlet_type,
    size_tier,
    open_date
from read_parquet('{{ bronze_dimension_path("branches") }}')
