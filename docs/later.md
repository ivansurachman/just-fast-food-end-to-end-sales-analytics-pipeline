# Later list

Ideas that do not serve the next checkpoint. Add new ones here instead of building them.

Iceberg, ClickHouse, monitoring tooling, Telegram alerting, platform settlement as a second source, dynamic branches,
TikTok voucher, customer dimension, Metabase as code, full-year scale test, generator DAG (`simulate_source`),
dynamic affected-date detection, Postgres table partitioning.

The dashboard cards also hardcode `order_date >= date '2026-10-01'`. A Metabase date filter (a native
variable with a default of the first day in the marts) replaces that when the pages are rebuilt, so a
different dataset is a dropdown, not an empty chart.

`docs/er_diagram.dot` is maintained by hand. Generating it from the dbt manifest (tables, columns, keys)
would make it impossible to drift, and would say so when a model changes without the diagram.
