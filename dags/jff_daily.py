"""`jff_daily`: wait for the generator's manifest, ingest bronze, check bronze.

One run per generator file date (`ds`), `catchup=True` so a backfill is one run per date, and
`max_active_runs=1` because DuckDB allows a single writer (docs/pipeline-design.md section 4).
The ingest task also takes the one slot of the `duckdb_writer` pool.

Silver, gold and marts are **placeholders** in this task: they are `EmptyOperator`s named after the
steps in docs/pipeline-design.md section 5 so the graph already has its final shape. They do
nothing and are replaced in T03.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.sensors.python import PythonSensor
from airflow.sdk import dag, get_current_context, task

from pipelines import check_bronze, ingest_bronze
from pipelines.manifest import manifest_key, object_exists

LOG = logging.getLogger(__name__)

RAW_ROOT = os.environ.get("JFF_RAW_ROOT", ingest_bronze.DEFAULT_RAW_ROOT)
LAKE_ROOT = os.environ.get("JFF_LAKE_ROOT", ingest_bronze.DEFAULT_LAKE_ROOT)
# Inside the compose network this is http://seaweedfs:8333; unset means local paths only.
S3_ENDPOINT = os.environ.get("JFF_S3_ENDPOINT")
RAW_BUCKET = RAW_ROOT.removeprefix("s3://").split("/", 1)[0]
DUCKDB_POOL = "duckdb_writer"


def manifest_ready(ds: str) -> bool:
    """True once the generator has written the day's manifest (it writes that object last)."""
    return object_exists(RAW_BUCKET, manifest_key(ds), endpoint=S3_ENDPOINT)


@dag(
    dag_id="jff_daily",
    schedule="@daily",
    start_date=datetime(2026, 10, 1),
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
        timeout=12 * 60 * 60,
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

    # Placeholders: the design's steps 4 to 6, added by T03 and later. They do nothing.
    dbt_run = EmptyOperator(
        task_id="dbt_run", doc="Placeholder (T03): dbt run for silver and gold."
    )
    dbt_test = EmptyOperator(
        task_id="dbt_test", doc="Placeholder (T03): dbt tests and the lookback guard."
    )
    load_marts = EmptyOperator(
        task_id="load_marts", doc="Placeholder (T04): load the PostgreSQL marts."
    )

    wait_manifest >> ingest_task() >> check_task() >> dbt_run >> dbt_test >> load_marts


jff_daily()
