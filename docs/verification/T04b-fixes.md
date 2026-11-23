opencode-go/deepseek-v4.1-flash

# T04b verification: small fixes after the T04 review

Task: `tasks/T04b-fixes.md`. Branch `task/T04b-fixes`. Date 2026-11-23.
Provider: `podman compose` -> `podman-compose` 1.6.0 (permanent setting from T00).

Only the four items of the spec, plus one fix Ivan approved while item 1 was being verified (item 5
below). Anything not run is written as "not run".

## 1. Memory rebalance

`compose.yaml`: `airflow-api-server` 800m -> **600m**, `metabase` 1400m -> **1600m**, with a comment on
each explaining where the 200 MB came from. `docs/pipeline-design.md` section 2 has the updated table
(api-server typical 0.3 GB / limit 0.6 GB, Metabase typical 1.35 GB / limit 1.6 GB, total unchanged)
and a paragraph dated 23 Nov with the reason.

Limits after `podman compose down` + `podman compose up -d` (`podman inspect .HostConfig.Memory`):

```
jff_postgres_1                    600 MB  long-running
jff_seaweedfs_1                   600 MB  long-running
jff_airflow-api-server_1          600 MB  long-running
jff_airflow-scheduler_1          1700 MB  long-running
jff_airflow-dag-processor_1       500 MB  long-running
jff_metabase_1                   1600 MB  long-running
long_running_total_mb=5600
jff_postgres-ro_1                 256 MB  one-shot
jff_seaweedfs-init_1              256 MB  one-shot
jff_airflow-init_1                512 MB  one-shot
```

The total of the long-running limits is still 5600 MB. Bring-up after the change: all containers
healthy (one-shots `Exited (0)`) after 95 s.

Usage after opening the Airflow UI once (`GET /` -> 200, health 200) and running the three dashboard
cards once through the Metabase API (46 / 5 / 10 rows):

```
jff_airflow-api-server_1   261.7MB / 629.1MB   41.59%
jff_metabase_1             1.264GB / 1.678GB   75.34%
podman machine ssh free -m: total 7822, used 2926, free 2211, buff/cache 2937, available 4896
```

Metabase was at 95% of 1400m before this change and is at 75% of 1600m with the same workload, so the
rebalance did what it was meant to do. No container was OOM-killed (`podman inspect .State.OOMKilled`
false everywhere). `docker-compose -f compose.yaml config --quiet` exits 0.

Verdict: **pass**.

## 2. Chart start date

`dashboards/sales_overview/net_sales_per_day.sql` now filters `where order_date >= date '2026-10-01'`,
with a comment on why 2026-09-30 is excluded (it only holds the delayed orders that arrived in the
2026-10-01 file).

`dashboards/setup.py` changed from "create if missing" to `ensure_card`, which **updates the query of
an existing card** with `PUT /api/card/{id}`; the docstring says so. Re-running the script against the
running Metabase:

```
INFO database JFF analytics already exists (id 2)
INFO card Net sales per day updated (id 40)
INFO card Orders by channel updated (id 41)
INFO card Top 10 branches by net sales updated (id 42)
INFO dashboard Sales overview already exists (id 2)
INFO dashboard Sales overview (id 2) has 3 cards
```

Card 40 through the API (`POST /api/card/40/query`):

```
rows=46 first=2026-10-01T00:00:00Z last=2026-11-15T00:00:00Z sum=35189519300
has_2026-09-30=False
```

The same query in `psql` (46 rows, 2026-10-01..2026-11-15, 35.189.519.300) matches, and the sum is the
old 35.195.073.350 minus the 5.554.050 of 2026-09-30, which is exactly the point of the change. The
card's stored `dataset_query` returns the new SQL with the `where` clause, so the dashboard card has no
2026-09-30 point.

Verdict: **pass**.

## 3. Window wording

`git grep -n "45 days|45 hari" -- docs README.md AGENTS.md` before and after.

Before, the four statements that describe the **demo window**:

```
docs/pipeline-design.md:96:  ... wasteful at 45 days (about 500 partition writes) ...
docs/pipeline-design.md:173: Row counts at 45 days, scale 0.1, ...
docs/pipeline-design.md:202: | 20 | dbt silver and gold, tests | `dbt test` green on the 45-day window |
docs/pipeline-design.md:204: | 22 | Full 45-day backfill, run end to end, demo rehearsal | ...
```

After:

```
docs/pipeline-design.md:96:  ... wasteful at 46 days (about 500 partition writes) ...
docs/pipeline-design.md:173: Row counts at 46 days (2026-10-01 to 2026-11-15), scale 0.1, ...
docs/pipeline-design.md:202: | 20 | ... `dbt test` green on the 46-day window (2026-10-01 to 2026-11-15) |
docs/pipeline-design.md:204: | 22 | Full 46-day backfill (2026-10-01 to 2026-11-15), run end to end, ... |
```

Two forward references in `docs/verification/T04-marts.md` that promised a "45-day" Part C were changed
to "the full demo range/dataset"; they were written before the 46th day existed.

Deliberately **not** changed, because they describe the profiling dataset, not the demo window:

```
docs/cli-guide.md:28            the generator's default development window (45 days), 540k orders
docs/data-profile.md:9          date range 2026-09-16 to 2026-10-30 (45 days)
docs/slides/cp1-slide-spec.md:3,32   45 hari, angka dari data-profile
docs/slides/make_charts.py:19   caption "Synthetic data, 45 days, scale 0.1, seed 42"
```

Also not changed: the historical measurements inside `docs/verification/T02..T04*.md` that say the T04
backfill measured 45 days before the window grew (changing them would falsify the evidence, and the same
documents explain the 46th day). `README.md` and `AGENTS.md` never mentioned the window length, so they
have nothing to change.

Verdict: **pass**.

## 4. Secrets check

`tools/check_secrets.py` (Ivan's file) run from the repo root with the local `.env`:

```
clean  POSTGRES_PASSWORD
clean  POSTGRES_AIRFLOW_PASSWORD
clean  POSTGRES_METABASE_PASSWORD
clean  POSTGRES_ANALYTICS_PASSWORD
clean  POSTGRES_ANALYTICS_RO_PASSWORD
clean  S3_ACCESS_KEY
clean  S3_SECRET_KEY
clean  AIRFLOW_ADMIN_PASSWORD
clean  AIRFLOW_FERNET_KEY
clean  AIRFLOW_API_SECRET_KEY
clean  AIRFLOW_API_AUTH_JWT_SECRET
clean  MB_ADMIN_PASSWORD
skipped (name does not look like a credential): AWS_DEFAULT_REGION, AIRFLOW_ADMIN_EMAIL, MB_ADMIN_EMAIL, MB_SITE_NAME
secrets in git: NONE
exit=0
```

The script checks every commit on every branch for each value and lists key/env files ever committed.

Verdict: **pass**, no secret in git history.

## 5. SeaweedFS init retried (Ivan's decision during item 1)

The first `up -d` for item 1 left `jff_seaweedfs-init_1` at `Exited (1)`:

```
error: rpc error: code = Unknown desc = raft.Server: Not current leader
```

The SeaweedFS healthcheck answers while the master is still campaigning for raft leadership, so
`weed shell` can fail in that window. The buckets were intact (`jff-raw` and `jff-lake` listed), and
`podman start -a jff_seaweedfs-init_1` exited 0. Ivan asked for the fix rather than a note.

`infra/seaweedfs/create-buckets.sh` now wraps every `weed shell` call in `weed_shell`, which retries up
to 5 attempts, 3 s apart, then prints the last output and exits 1.

Positive path: two full `down` + `up -d` cycles, both with `jff_seaweedfs-init_1` at `Exited (0)` and
every long-running container healthy (95 s on the second cycle).

Negative path, to prove the retry really runs: the same script in a throwaway container pointed at a
port where no master listens:

```
weed shell attempt 1 failed, retrying in 3s
weed shell attempt 2 failed, retrying in 3s
weed shell attempt 3 failed, retrying in 3s
weed shell attempt 4 failed, retrying in 3s
weed shell failed after 5 attempts:
cannot connect to master localhost:9999 within 30s
probe_exit=1 elapsed_s=163.7
```

So a truly absent master now takes about 2.7 minutes to fail (5 x the 30 s connect timeout plus the
retries) instead of failing instantly. That is the cost of the retry and it only happens when
SeaweedFS never comes up.

## Checks

```
python -m ruff check .            -> All checks passed!
python -m ruff format --check .   -> 49 files already formatted
python -m mypy                     -> Success: no issues found in 11 source files
python -m pytest -q                -> 14 passed (with S3_* exported)
docker-compose -f compose.yaml config --quiet -> exit 0
```

Not run: the `browser` skill was not used and no screenshots were taken.

## Not run / notes

- `sqlfluff`, `shellcheck`: not part of the project tooling.
- The retry path of `weed_shell` was proven with the negative test above, not by waiting for the real
  raft race to happen again.
