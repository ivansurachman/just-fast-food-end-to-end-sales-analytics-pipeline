-- The mart grain is (order_date, branch_key, channel_key); a generic `unique` test only covers one
-- column, so the combination is checked here.
select
    order_date,
    branch_key,
    channel_key,
    count(*) as rows_in_mart
from {{ ref('mart_sales_day_branch_channel') }}
group by order_date, branch_key, channel_key
having count(*) > 1
