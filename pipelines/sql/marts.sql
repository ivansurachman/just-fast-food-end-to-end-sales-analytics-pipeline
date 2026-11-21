-- Target table of `pipelines/load_marts.py`. Applied on every load with
-- CREATE ... IF NOT EXISTS, so it is safe on a fresh and on an existing database.
-- Idempotency comes from the primary key plus the loader's DELETE of the same window.
create table if not exists mart_sales_day_branch_channel (
    order_date date not null,
    branch_key integer not null,
    channel_key text not null,
    total_orders bigint not null,
    completed_orders bigint not null,
    cancelled_orders bigint not null,
    refunded_orders bigint not null,
    gross_amount bigint not null,
    discount_amount bigint not null,
    net_amount bigint not null,
    cogs_amount bigint not null,
    commission_amount bigint not null,
    primary key (order_date, branch_key, channel_key)
);

-- Every dashboard query filters or groups by day.
create index if not exists mart_sales_day_branch_channel_order_date_idx
    on mart_sales_day_branch_channel (order_date);
