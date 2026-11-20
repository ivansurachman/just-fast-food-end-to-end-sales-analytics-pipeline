-- (order_id, line_no) is the grain of the item tables; a generic `unique` test only covers one column.
select order_id, line_no, count(*) as rows_in_silver
from {{ ref('silver_order_items') }}
group by order_id, line_no
having count(*) > 1
