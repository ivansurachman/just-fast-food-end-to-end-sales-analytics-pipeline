{% macro lake_root() -%}
{{ var('lake_root', env_var('JFF_LAKE_ROOT', 's3://jff-lake')) }}
{%- endmacro %}


{# Glob of every daily object of one entity: bronze/<entity>/source_file_date=*/<entity>.parquet #}
{% macro bronze_fact_glob(entity) -%}
{{ lake_root() }}/bronze/{{ entity }}/*/{{ entity }}.parquet
{%- endmacro %}


{# The dimensions are written once, not per day. #}
{% macro bronze_dimension_path(entity) -%}
{{ lake_root() }}/bronze/dimensions/{{ entity }}.parquet
{%- endmacro %}


{# Right edge of the reprocessing window: the run's file date (design section 6). #}
{% macro run_date_sql() -%}
date '{{ var("run_date") }}'
{%- endmacro %}


{# Left edge of the window: run_date minus the fixed lookback of 10 days. #}
{% macro window_start_sql() -%}
{{ run_date_sql() }} - interval {{ var('lookback_days', 10) }} day
{%- endmacro %}
