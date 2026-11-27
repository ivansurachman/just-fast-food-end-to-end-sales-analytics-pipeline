# Conclusion and recommendation

Every figure below is measured and every figure names the report it comes from. Nothing here is an
estimate; where a number does not exist yet, the sentence says so.

## What the platform does

A single daily batch pipeline (`jff_daily`) takes the generator's CSV files from S3-compatible storage
through bronze Parquet, silver and gold models in DuckDB, and five PostgreSQL marts, to five Metabase
pages with 17 cards. The lake is a replayable mirror of silver and gold, published per order date; bronze
is the source of truth for a full rebuild (`docs/pipeline-design.md`).

It runs as six long-running containers plus three one-shot helpers on one Podman machine, capped at
5600 MB, and everything is bound to `127.0.0.1` (`docs/security.md`).

## Evidence

| Claim | Measurement | Report |
|---|---|---|
| The pipeline runs end to end from an empty clone | Clean-room: build 3.8 min, healthy in 1.8 min, seven days generated and processed, dashboard returns 8 dates | T07 section 1 |
| A 45-day backfill fits the machine | 23.4 min for 45 runs, peak scheduler `anon` 1344 MiB of a 1700 MiB limit, no OOM kill | T04 |
| Re-running a date changes nothing | Mart hashes identical before and after a re-run, in DuckDB and PostgreSQL | T05 section 4, T06 section 4 |
| The lake equals the database | Whole tables, as of 2026-11-24: 574,838 orders and 1,399,537 lines on both sides; 196 objects over 49 dates (the baseline and the per-day breakdown are in design section 14) | T07 section 8 |
| The dashboard equals its SQL | 17 of 17 cards return the same rows through the API as their file in `psql` | T06 section 3 |
| The injected defects are detected | Seven row-level defects match the manifests one to one; nine missing branch-days equal the nine `dropped_branch_ids` | T03 section 3, T06 section 2 |
| The stack fits its budget while loaded | postgres 165 MB, seaweedfs 326.8 MB, metabase 1.357 GB, api-server 331.8 MB, scheduler 1.077 GB, dag-processor 205.8 MB | T06 section 6 |
| One day costs about a minute | 42.3 s for the seven tasks, peak `anon` 661.4 MB | T06 section 5 |
| Tests and checks are green | dbt 49 tests, `pytest` 23, generator 41, ruff/mypy clean, CI green on `task/T07-hardening` and `main` | T06 section 7, T01, T07 section 5 |
| Our own dependencies have no known advisories | pip-audit: 0 findings in the pipeline, generator and dbt sets | T07 section 3 |
| The base image is the remaining risk | 108 advisories in the Airflow image (4 CRITICAL, 48 HIGH) and Trivy 342 HIGH / 23 CRITICAL for it; accepted for a local demo with a review after 29 Nov 2026 | T07 section 4, `docs/security.md` |

Window counts (days, rows, objects) are in `docs/pipeline-design.md` section 14 and are not repeated here.

## Limitations

- **Single-writer DuckDB.** One DAG run at a time and one `duckdb_writer` pool slot; two writers would
  corrupt the file. Throughput therefore comes from doing more per run, not from parallelism
  (`docs/pipeline-design.md` section 4).
- **Synthetic data.** Every insight reflects the generator's assumptions, not a real market. The
  generator's config is the world model (`docs/data-profile.md`).
- **Commission rates are placeholders**, not platform contracts; revenue per channel is directionally
  useful and arithmetically consistent, nothing more (`docs/data-dictionary.md`).
- **The newest day is provisional.** Its late orders and refunds arrive in the next file and rewrite its
  partition on the next run (T04).
- **Orphan refunds before the window.** 163 refund rows reference orders dated 2026-09-23 .. 2026-09-30,
  before the dataset starts, and do not attach to an order; three more reference dropped branch-days, so
  the orphan count is 166 (docs/verification/T04-marts.md).
- **No real-time view.** The schedule is daily and the window is closed at the run date; there is no
  streaming path and none is planned for this project (`docs/pipeline-design.md` section 11).
- **No backups and no TLS**, and the Podman machine is rootful: the demo assumes one trusted local machine
  (`docs/security.md`).

## What to change at 100 times the volume

As a judgment rather than a measurement, the current shape is probably right up to about a million
orders; the following are the parts that would break first, in the order they would break.

1. **The compute store.** A single DuckDB file with one writer stops being the answer. Move silver and
   gold to a warehouse with concurrent writers and partition-level metadata (Iceberg or a managed
   warehouse), keeping dbt as the transformation layer; the models and tests carry over unchanged.
2. **The publish step.** One object per table per day becomes too many small files. Publish per month, or
   let the table format compact; the current per-date writer is `pipelines/publish_parquet.py`.
3. **The marts.** `DELETE` + `COPY` per window is fine at 27,410 rows in `mart_sales_day_branch_channel` (T07 section 8);
   at 100x it wants partitioning by date and `COPY` into staging tables, or a warehouse that reads the
   gold tables directly.
4. **The orchestrator.** LocalExecutor with one worker becomes Celery or Kubernetes; the DAG stays as it
   is, the pool and concurrency settings change.
5. **The window.** A fixed 10 days is cheap at about 12k orders per day (the window in section 14 averages to that); at 100x, recomputing 10 partitions per
   run needs either a wider machine or dynamic affected-date detection (the alternative rejected in D2).
6. **Retention.** Bronze keeps everything today. At 100x it needs a lifecycle policy, and the lake's
   orphan-partition behaviour (`docs/lake-layout.md`) needs an explicit cleanup job.

## Recommendation

The project meets its checkpoint: the pipeline runs end to end, the numbers are measured and reproducible,
and every limitation above is written down with a report behind it. Before treating it as more than a
demo, do three things in this order:

1. **Patch the images** after the 29 November review window, following `docs/security.md`; that is the
   only finding class still open.
2. **Turn the dashboard date filter into a Metabase parameter** (17 cards carry a fixed date today,
   `docs/later.md`), so a different dataset is a dropdown rather than 17 edits.
3. **Add M9, M14 and M18 if the project should deliver all 18 metrics it defined**, starting with M18
   (`fact_dq_daily`), which is the only one that needs a new gold table. The rubric does not name a
   metric count; the 18 comes from `docs/data-model.md`.
