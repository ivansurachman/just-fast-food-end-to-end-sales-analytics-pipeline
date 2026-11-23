# T04b: small fixes after T04 review

Branch: `task/T04b-fixes` (from `main` after T04 is merged). About 20 minutes. Only the four items below.

## Items

1. **Memory rebalance.** In `compose.yaml` set `airflow-api-server` `mem_limit` to `600m` (was `800m`) and `metabase` to `1600m` (was `1400m`). The total of the long-running limits stays 5600 MB. Reason: T04 measured Metabase at 95% of 1400m and the api-server at 262 MB of 800m. Update the table in `docs/pipeline-design.md` section 2.
   Evidence: `podman inspect` shows the new limits; `podman compose down` then `up -d`; `podman stats --no-stream` for api-server and metabase after opening the Airflow UI and the dashboard once; `podman machine ssh free -m`.
2. **Chart start date.** The card "Net sales per day" starts at 2026-09-30 with 93 delayed orders, which looks like a ramp from zero. Add `where order_date >= date '2026-10-01'` to `dashboards/sales_overview/net_sales_per_day.sql` and update the card through the Metabase API (the setup script must update an existing card's query, not only create new ones). Evidence: the API returns 46 rows for the card; the dashboard card shows no 2026-09-30 point.
3. **Window wording.** Replace "45 days" with "46 days (2026-10-01 to 2026-11-15)" wherever the demo window is described in `docs/`, `README.md` and `AGENTS.md`. Evidence: `git grep -n "45 days\|45 hari"` output before and after.
4. **Secrets check.** Add `tools/check_secrets.py` (Ivan provides the file). Evidence: run `python tools\check_secrets.py` and paste the output.

## Rules

- Load `podman-windows` and `lean-code`. Do not use the `browser` skill.
- Write the evidence to `docs/verification/T04b-fixes.md`, with the model ID at the top.

## STOP

- A limit change makes any container unhealthy or OOM-killed. Report numbers; do not raise other limits.
