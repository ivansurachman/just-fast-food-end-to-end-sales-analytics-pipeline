-- (order_id, line_no) is the grain of fact_order_item.
select order_id, line_no, count(*) as rows_in_gold
from {{ ref('fact_order_item') }}
group by order_id, line_no
having count(*) > 1
