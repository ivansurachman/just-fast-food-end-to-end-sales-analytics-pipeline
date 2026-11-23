# T06: remaining P1 metrics (M10, M12, M15, M17) and dashboard pages

Branch: `task/T06-p1` (from `main`). Serves the rubric item "project delivery: all requirements". P1 metrics are M1, M2, M3, M4, M6, M7, M8, M10, M12, M15, M17. T04 covers M1 to M8 in one mart but the dashboard shows only three cards.

Read first: `docs/data-model.md` (metric definitions and the mapping of metrics to tables), `docs/pipeline-design.md` section 8, and `tasks/T04-marts-metabase.md` (how marts are built and loaded).

## Order of work (evidence for each part before the next)

- **Part A: cards for M1 to M8 on page 1.** No new model. Add the missing cards from `mart_sales_day_branch_channel`, each as a numerator and denominator pair summed in SQL, never an average of stored ratios (M3, M7, M13, M15 rule from the data model).
- **Part B: new marts and load.** `mart_hourly` (grain date, branch, hour; M10), `mart_item_day` (grain date, menu item; M12), `mart_promo_day` (grain date, promo, channel; M15), `mart_branch_coverage` (grain date, branch; M17, expected branches derived from `dim_branch.open_date`, not from the manifest). Each incremental on `order_date`, loaded by `load_marts` with the same delete-window-then-COPY rule, index on `order_date`, read access for `analytics_ro`.
- **Part C: dashboard pages.** Page 2 "Operations": M10 (orders by hour) and M17 (branch coverage). Page 3 "Menu and promo": M12 and M15. Create through the Metabase API (extend `dashboards/setup.py`), SQL of each card in `dashboards/<page>/*.sql`.

## Rules

- Take every column and definition from `docs/data-model.md`. If a definition is missing or ambiguous, STOP and ask Ivan.
- Marts hold numerators and denominators only.
- Load `lean-code` and `podman-windows`. Do not use the `browser` skill; Ivan takes screenshots.
- Do not add P2 metrics (M5, M9, M11, M13, M14, M16, M18).

## Acceptance (evidence for each)

1. Each new mart equals the same measure computed directly from the DuckDB facts, for all 46 days (show the comparison queries and zero differences).
2. M17: show the expected versus received branch-days for the whole window, including the days with simulated dropped branch-days from the manifests (`dropped_branch_ids`). The number of missing branch-days must equal the sum in the manifests.
3. Every card on every page returns the same totals through the API as its SQL file in `psql`.
4. Idempotence: re-run one date; hashes of all marts for that window are identical.
5. DAG still passes end to end for one new day; report duration and scheduler `anon` peak.
6. Memory: `free -m` with at least 1 GiB available; no container above its limit.
7. `ruff`, `mypy`, `pytest` clean. Evidence in `docs/verification/T06-p1.md` with the model ID at the top.

## STOP

- A metric's definition cannot be implemented from the available gold tables. Report which and why.
- Backfill or a DAG run takes more than twice as long as in T04.
