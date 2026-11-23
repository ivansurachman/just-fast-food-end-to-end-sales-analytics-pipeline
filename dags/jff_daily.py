"""`jff_daily`: wait for the generator's manifest, ingest bronze, check bronze, dbt, marts, publish.

One run per generator file date (`ds`), `catchup=True` so a backfill is one run per date, and
`max_active_runs=1` because DuckDB allows a single writer (docs/pipeline-design.md section 4).
The tasks that touch DuckDB take the one slot of the `duckdb_writer` pool.

The DAG is bounded: `start_date` 2026-10-01 and `end_date` 2026-11-17 are the 48-day demo window
(design section 14), so unpausing it can only ever create those 48 runs. `wait_manifest` gives up
after two hours, so a day the generator never wrote fails loudly instead of waiting forever. The
last day is what makes 2026-11-16 final: its late orders arrive in the file of 2026-11-17.

`load_marts` copies the mart window from DuckDB into PostgreSQL and `publish_parquet` mirrors the
silver and gold tables into the lake, one Parquet object per table and order date.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.sensors.python import PythonSensor
from airflow.sdk import dag, get_current_context, task

from pipelines import check_bronze, ingest_bronze, publish_parquet
from pipelines.manifest import manifest_key, object_exists

LOG = logging.getLogger(__name__)

RAW_ROOT = os.environ.get("JFF_RAW_ROOT", ingest_bronze.DEFAULT_RAW_ROOT)
LAKE_ROOT = os.environ.get("JFF_LAKE_ROOT", ingest_bronze.DEFAULT_LAKE_ROOT)
# Inside the compose network this is http://seaweedfs:8333; unset means local paths only.
S3_ENDPOINT = os.environ.get("JFF_S3_ENDPOINT")
RAW_BUCKET = RAW_ROOT.removeprefix("s3://").split("/", 1)[0]
DUCKDB_POOL = "duckdb_writer"
# Design section 6: every task that rewrites partitions uses the same 10-day window.
LOOKBACK_DAYS = 10

DBT_HOME = "/opt/airflow/dbt"
DBT = "/opt/venvs/dbt/bin/dbt"
# run_date is the dbt window's right edge; lookback_days is design section 6's fixed 10-day window.
# The single braces are dbt's JSON var syntax; Airflow renders only `{{ ds }}`.
DBT_ARGS = (
    f"--project-dir {DBT_HOME} --profiles-dir {DBT_HOME} "
    f"""--vars '{{"run_date": "{{{{ ds }}}}", "lookback_days": {LOOKBACK_DAYS}}}'"""
)
DBT_ENV = {
    "JFF_S3_ENDPOINT": S3_ENDPOINT or "",
    "JFF_LAKE_ROOT": LAKE_ROOT,
    "DBT_DUCKDB_PATH": os.environ.get("DBT_DUCKDB_PATH", "/opt/airflow/duckdb/jff.duckdb"),
}
# load_marts runs with the dbt virtualenv, which has both duckdb and psycopg. psycopg reads the PG*
# variables that compose sets, so no credential appears here.
LOAD_MARTS_CMD = (
    f"/opt/venvs/dbt/bin/python -m pipelines.load_marts --ds {{{{ ds }}}} "
    f"--lookback-days {LOOKBACK_DAYS}"
)


def manifest_ready(ds: str) -> bool:
    """True once the generator has written the day's manifest (it writes that object last)."""
    return object_exists(RAW_BUCKET, manifest_key(ds), endpoint=S3_ENDPOINT)


@dag(
    dag_id="jff_daily",
    schedule="@daily",
    start_date=datetime(2026, 10, 1),
    # 48 days, one run per generator file date from 2026-10-01 to 2026-11-17. The end date must stay
    # at least one day past the last day the dashboard should show as final: a day's late orders and
    # refunds arrive in the next day's file.
    end_date=datetime(2026, 11, 17),
    catchup=True,
    max_active_runs=1,
    default_args={"owner": "jff", "retries": 1, "retry_delay": 300},
    tags=["jff"],
    doc_md=__doc__,
)
def jff_daily() -> None:
    wait_manifest = PythonSensor(
        task_id="wait_manifest",
        python_callable=manifest_ready,
        op_kwargs={"ds": "{{ ds }}"},
        mode="reschedule",
        poke_interval=30,
        timeout=2 * 60 * 60,
        doc="Wait for s3://<raw>/_manifests/dt=<ds>/manifest.json in reschedule mode.",
    )

    @task(task_id="ingest_bronze", pool=DUCKDB_POOL)
    def ingest_task() -> dict[str, dict[str, int]]:
        """Dimensions once, then every fact entity of the run's day."""
        ds = get_current_context()["ds"]
        dimensions = ingest_bronze.ingest_dimensions(
            raw_root=RAW_ROOT, lake_root=LAKE_ROOT, endpoint=S3_ENDPOINT
        )
        facts = ingest_bronze.ingest_day(
            ds, raw_root=RAW_ROOT, lake_root=LAKE_ROOT, endpoint=S3_ENDPOINT
        )
        return {"dimensions": dimensions, "facts": facts}

    @task(task_id="check_bronze")
    def check_task() -> dict[str, dict[str, int]]:
        """CSV rows, Parquet rows and the manifest must agree; otherwise the run fails here."""
        ds = get_current_context()["ds"]
        report = check_bronze.check_day(
            ds, raw_root=RAW_ROOT, lake_root=LAKE_ROOT, endpoint=S3_ENDPOINT
        )
        LOG.info("bronze check passed for %s: %s", ds, report)
        return report

    dbt_run = BashOperator(
        task_id="dbt_run",
        pool=DUCKDB_POOL,
        # The seed comes first: `dbt run` does not build seeds, and silver needs payment_method_map.
        bash_command=f"{DBT} seed {DBT_ARGS} && {DBT} run {DBT_ARGS}",
        env=DBT_ENV,
        append_env=True,
        doc="dbt seed + run: silver and gold in DuckDB, windowed on {{ ds }}.",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        pool=DUCKDB_POOL,
        bash_command=f"{DBT} test {DBT_ARGS}",
        env=DBT_ENV,
        append_env=True,
        doc="dbt test: generic tests plus the lookback guard.",
    )
    load_marts = BashOperator(
        task_id="load_marts",
        pool=DUCKDB_POOL,
        bash_command=LOAD_MARTS_CMD,
        append_env=True,
        doc="Load the mart window into PostgreSQL: delete and copy in one transaction.",
    )

    @task(task_id="publish_parquet", pool=DUCKDB_POOL)
    def publish_task() -> dict[str, int]:
        """Publish the run's window to the lake; the lake is derived, DuckDB stays the source."""
        ds = get_current_context()["ds"]
        return publish_parquet.publish_window(
            ds,
            lookback_days=LOOKBACK_DAYS,
            duckdb_path=DBT_ENV["DBT_DUCKDB_PATH"],
            lake_root=LAKE_ROOT,
            endpoint=S3_ENDPOINT,
        )

    wait_manifest >> ingest_task() >> check_task() >> dbt_run >> dbt_test >> load_marts
    load_marts >> publish_task()


jff_daily()
