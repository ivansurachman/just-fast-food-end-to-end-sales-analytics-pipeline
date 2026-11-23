# T06: remaining P1 metrics, four cheap P2 metrics, five dashboard pages

Branch: `task/T06-p1` (from `main`). Serves the rubric item "project delivery" and the problem-statement claim of 18 metrics. P1 metrics are M1, M2, M3, M4, M6, M7, M8, M10, M12, M15, M17. T04 holds the data for M1 to M8 in one mart but the dashboard shows only three cards. This task also adds four P2 metrics that need no new gold table: M5, M11, M13, M16. Deferred with a stated reason: M9 (28-day rolling index against a peer median), M14 (order-level beverage attach), M18 (needs `fact_dq_daily`).

Read first: `docs/data-model.md` (metric definitions and the mapping of metrics to tables), `docs/pipeline-design.md` section 8, and `tasks/T04-marts-metabase.md` (how marts are built and loaded).

## Order of work (evidence for each part before the next)

- **Part A: cards from the existing mart.** No new model. Cards for M1, M2, M3, M4, M5, M6, M7 from `mart_sales_day_branch_channel`, each as a numerator and denominator pair summed in SQL, never an average of stored ratios (rule from the data model for M3, M5, M7, M13, M15).
- **Part B0: `fact_branch_day` (gold).** T03 left it out. Build it first as in `docs/data-model.md`: grain branch and date, `orders_received`, `is_expected` derived from `dim_branch.open_date` (not from the manifest), `late_arrival_orders`, incremental on the date with the same window. M8 (denominator) and M17 depend on it. Evidence: expected, received and missing branch-days for the whole window.
- **Part B: new marts and load.** `mart_hourly` (grain date, branch, hour; M10 and M11), `mart_item_day` (grain date, menu item; M12 and M13, so it needs `line_cogs`), `mart_promo_day` (grain date, promo, channel with net amount and order count; M15 and M16), `mart_branch_coverage` (grain date, branch; M8 denominator and M17). Each incremental on `order_date`, loaded by `load_marts` with the same delete-window-then-COPY rule, index on `order_date`, read access for `analytics_ro`. M11 is the 95th percentile of M10 per branch, computed in the card SQL from `mart_hourly`.
- **Part C: five dashboard pages**, built through the Metabase API (extend `dashboards/setup.py`), SQL of each card in `dashboards/<page>/*.sql`:
  1. Sales overview: M1 to M5 (the existing three cards stay).
  2. Channel and branch: M6, M7, M8.
  3. Operations: M10, M11, M17.
  4. Menu: M12, M13.
  5. Promo: M15, M16.
  If time is short, cut pages 5 and 4 in that order. Never cut Part B0.

## Rules

- Take every column and definition from `docs/data-model.md`. If a definition is missing or ambiguous, STOP and ask Ivan.
- Marts hold numerators and denominators only.
- Load `lean-code` and `podman-windows`. Do not use the `browser` skill; Ivan takes screenshots.
- Do not add M9, M14 or M18 in this task. If one turns out to be nearly free, say so in the report and let Ivan decide.

## Acceptance (evidence for each)

1. Each new mart equals the same measure computed directly from the DuckDB facts, for all 46 days (show the comparison queries and zero differences).
2. M8 and M17: show the expected versus received branch-days for the whole window, including the days with simulated dropped branch-days from the manifests (`dropped_branch_ids`). The number of missing branch-days must equal the sum in the manifests.
3. Every card on every page returns the same totals through the API as its SQL file in `psql`.
4. Idempotence: re-run one date; hashes of all marts for that window are identical.
5. DAG still passes end to end for one new day; report duration and scheduler `anon` peak.
6. Memory: `free -m` with at least 1 GiB available; no container above its limit.
7. `ruff`, `mypy`, `pytest` clean. Evidence in `docs/verification/T06-p1.md` with the model ID at the top.

## STOP

- A metric's definition cannot be implemented from the available gold tables. Report which and why.
- Backfill or a DAG run takes more than twice as long as in T04.