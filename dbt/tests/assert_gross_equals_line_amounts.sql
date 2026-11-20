-- fact_order.gross_amount must equal the sum of the order's lines in fact_order_item.
select
    o.order_id,
    o.gross_amount,
    i.gross_from_lines
from {{ ref('fact_order') }} as o
inner join (
    select order_id, sum(line_amount) as gross_from_lines
    from {{ ref('fact_order_item') }}
    group by order_id
) as i on i.order_id = o.order_id
where o.gross_amount <> i.gross_from_lines
