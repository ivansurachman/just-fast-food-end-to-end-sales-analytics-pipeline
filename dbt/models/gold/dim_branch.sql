-- Gold branch dimension. The natural key is used as the surrogate: branch_key = branch_id.
{{ config(materialized='table') }}

select
    cast(branch_id as integer) as branch_key,
    branch_code,
    branch_name,
    city,
    region,
    timezone,
    outlet_type,
    size_tier,
    cast(open_date as date) as open_date
from {{ ref('stg_branches') }}
