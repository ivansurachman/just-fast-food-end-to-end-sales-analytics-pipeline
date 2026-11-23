-- Target tables of `pipelines/load_marts.py`. Applied on every load with CREATE ... IF NOT EXISTS, so
-- it is safe on a fresh and on an existing database. Idempotency comes from the primary key plus the
-- loader's DELETE of the same window.
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

create table if not exists mart_hourly (
    order_date date not null,
    branch_key integer not null,
    hour_local integer not null,
    total_orders bigint not null,
    completed_orders bigint not null,
    primary key (order_date, branch_key, hour_local)
);

create table if not exists mart_item_day (
    order_date date not null,
    menu_item_key text not null,
    quantity bigint not null,
    line_amount bigint not null,
    line_cogs bigint not null,
    primary key (order_date, menu_item_key)
);

create table if not exists mart_promo_day (
    order_date date not null,
    promo_key text not null,
    channel_key text not null,
    order_count bigint not null,
    gross_amount bigint not null,
    discount_amount bigint not null,
    net_amount bigint not null,
    primary key (order_date, promo_key, channel_key)
);

create table if not exists mart_branch_coverage (
    order_date date not null,
    branch_key integer not null,
    is_expected boolean not null,
    orders_received bigint not null,
    late_arrival_orders bigint not null,
    completed_orders bigint not null,
    net_amount bigint not null,
    primary key (order_date, branch_key)
);

-- Every dashboard query filters or groups by day.
create index if not exists mart_sales_day_branch_channel_order_date_idx
    on mart_sales_day_branch_channel (order_date);
create index if not exists mart_hourly_order_date_idx on mart_hourly (order_date);
create index if not exists mart_item_day_order_date_idx on mart_item_day (order_date);
create index if not exists mart_promo_day_order_date_idx on mart_promo_day (order_date);
create index if not exists mart_branch_coverage_order_date_idx
    on mart_branch_coverage (order_date);
