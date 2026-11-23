-- The grain of fact_branch_day is (date_key, branch_key).
select date_key, branch_key, count(*) as rows_in_fact
from {{ ref('fact_branch_day') }}
group by date_key, branch_key
having count(*) > 1
