-- Bronze menu item dimension as text.
{{ config(materialized='view') }}

select
    menu_item_id,
    item_name,
    category,
    unit_price,
    unit_cost,
    is_active
from read_parquet('{{ bronze_dimension_path("menu_items") }}')
