# Demo script

What to show, in what order, and what to say. The numbers quoted here are the ones in
`docs/pipeline-design.md` section 14; if the window moves, that table is the only place to look.

## Before the demo (once)

```
podman compose up -d
podman compose ps                 # every long-running service healthy
python tools/check_secrets.py     # "secrets in git: NONE"
```

Open `http://localhost:3000` (Metabase), `http://localhost:8080` (Airflow), `http://127.0.0.1:8888/buckets/`
(the SeaweedFS file browser).

## The story, 10 minutes

1. **Source.** `http://127.0.0.1:8888/buckets/jff-raw/`: one folder per file date, three CSVs each,
   plus `_manifests/dt=.../manifest.json` written last. Say: the manifest is what makes a day complete.
2. **Ingest and bronze.** In Airflow, open `jff_daily` and the latest run: seven tasks, green. Bronze is
   Parquet on S3, every column as text, so a dirty value can never fail ingest.
3. **Silver and gold.** `dbt` runs in the scheduler: deduplication, payment variants, recomputed gross,
   refunds rewriting the order's own partition. The lookback guard test fails the run if a change ever
   needs more than the 10-day window.
4. **Marts.** `load_marts` replaces the window in PostgreSQL in one transaction per table. Show the
   five tables and the read-only role: `select count(*) from mart_sales_day_branch_channel;`.
5. **Metabase.** Five pages: Sales overview, Channel and branch, Operations, Menu, Promo. Say what each
   metric answers and that every ratio is computed from numerator and denominator, never averaged from
   stored ratios.
6. **Lake mirror.** `http://127.0.0.1:8888/buckets/jff-lake/`: silver and gold Parquet per order date,
   one object per table per day, rewritten in place. Same command over the same window, same objects.
7. **Recovery.** Delete `jff_duckdb` and re-run the backfill: everything is rebuilt from bronze. That is
   the answer to "what if the database is lost".

## Run one new day (live, 2 minutes)

The DAG only runs days inside `[start_date, end_date]` and only while it is unpaused. The order
matters; the two wrong orders fail silently.

```
# 1. the generator writes the day into the raw bucket, manifest last
podman exec jff_airflow-scheduler_1 /opt/venvs/jff/bin/jff-gen generate \
    --date 2026-11-18 --scale 0.1 --out s3://jff-raw --s3-endpoint http://seaweedfs:8333

# 2. the DAG must cover the day
#    edit dags/jff_daily.py: end_date=datetime(2026, 11, 18)   (and start_date stays 2026-10-01)
podman exec jff_airflow-scheduler_1 airflow dags list-import-errors    # must stay empty

# 3. the DAG must be unpaused
podman exec jff_airflow-scheduler_1 airflow dags unpause jff_daily

# 4. trigger the day: the play button in the UI, or the same thing from the CLI
podman exec jff_airflow-scheduler_1 airflow backfill create \
    --dag-id jff_daily --from-date 2026-11-18 --to-date 2026-11-18

# 5. watch the seven tasks and then the dashboard
podman exec jff_airflow-scheduler_1 airflow tasks states-for-dag-run jff_daily \
    "backfill__2026-11-18T00:00:00+00:00"
```

Then refresh Metabase: the new day is the last point of "Net sales per day" and the coverage chart.

**What does not work** (both observed on 2026-11-23, evidence in
`docs/verification/T07-hardening.md`):

| Attempt | What happens |
|---|---|
| Trigger a day beyond `end_date` | A run with no task instances. Unpaused, the scheduler finalises it `success` in milliseconds; paused, it stays `queued` and never runs |
| Trigger while the DAG is paused | The run waits at `queued` with zero tasks until the DAG is unpaused |
| `airflow dags trigger --logical-date` for a day beyond `end_date` | Same empty run as the row above; `airflow backfill create` is the path that works |

The rule of thumb: extend `end_date` first, unpause second, trigger third.

## Questions the mentor will ask

- *Why is yesterday's number provisional?* Its late orders and refunds arrive in today's file, so the
  partition is rewritten on the next run. The newest day is always the one that still moves.
- *Why DuckDB and not Parquet as the compute store?* The lake is published from DuckDB; silver and gold
  need delete+insert by date, which dbt does on DuckDB and not on partitioned Parquet without custom code.
- *What breaks first?* Memory: the whole stack is capped at 5600 MB against a 7.6 GiB VM; Metabase is the
  tightest container. `docs/security.md` records what is and is not protected.
