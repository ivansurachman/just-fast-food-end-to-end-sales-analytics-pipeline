"""Pipeline code shared by the Airflow DAGs and the command line.

Modules here import no Airflow code, so they can be run and tested without Airflow:
`pipelines.ingest_bronze` (CSV -> Parquet bronze) and `pipelines.check_bronze` (the checks
that gate the rest of `jff_daily`).
"""
