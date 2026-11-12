# Check Point 1 slide spec

For the Check Point 1 presentation (PPT due 14 Nov, presented 15 Nov). It follows the three parts of the bootcamp template: Introduction, Overview Project, Main Project. Text is a ready-to-paste draft; design and layout are yours. Numbers come from `docs/data-profile.md` (45 days, scale 0.1, seed 42) unless stated.

Assumption: slides are in English like the docs. Say so if you want Indonesian text.

## Slide by slide

| # | Slide | Must contain | Visual and placement | Status |
|---|---|---|---|---|
| 1 | Title | Project name "Just Fast Food: end-to-end sales analytics", your name, bootcamp, Check Point 1, date | None | Needs your name and date |
| 2 | Introduction | Self-overview, education (degree, institution, concentration), working experience (roles, projects, achievements) | Optional photo, left | Needs your input |
| 3 | Overview Project | One row per bootcamp project: title, short description (goal, analysis, result, technology). Add this project as the last row | Table, full width | Needs the list of your other projects |
| 4 | Project background | Fictional fast food chain, 100+ branches across Indonesia, about 120 thousand orders per day, five sales channels. Reports are split by channel and arrive late, duplicated or dirty. Goal: one trusted sales view and a reproducible pipeline. Beneficiaries: operations, regional managers, marketing, finance | None, or a small channel icon row | Text ready |
| 5 | Problem statement and success | Problems: (1) net sales by channel after platform commission is unknown, (2) peak hours per branch are not visible, (3) promo cost versus effect is unclear, (4) late and dirty data make daily numbers unreliable. Success metrics: all 11 P1 metrics answerable, daily run succeeds end to end, every injected defect detected (9 of 9 today) | Right: table of the 11 P1 metrics (M1, M2, M3, M4, M6, M7, M8, M10, M12, M15, M17) | Targets below need your approval |
| 6 | Data platform understanding | Source to storage to transform to serving, in one sentence each. All services run in Podman containers under a 9 GB memory limit | **Full width: `architecture.png`** | Design v1, final after Phase 3 |
| 7 | Data understanding: source and structure | Collection: seeded Python generator, daily CSV to S3-compatible storage. Entities and grain: orders (one row per order), order_items (one per line), order_changes (one per refund), 4 dimension tables. Volume: full scale about 120 thousand orders and 290 thousand lines per day, about 44 million orders per year. Dev window: 541 thousand orders, 1.3 million lines, 109 MB | Left: entity table. Right: screenshot of the head of `orders.csv` (you capture) | Text ready, screenshot needed |
| 8 | Data understanding: patterns | Peaks at lunch and dinner, online skews to evening, weekend uplift, online is half of orders but a smaller share of net sales | **Left: `chart_hourly_share.png`. Right top: `chart_channel_mix.png`. Right bottom: `chart_weekday.png`** (or one chart per slide) | Ready |
| 9 | Data understanding: quality | Nine production-style defects are injected: duplicate rows, late-arriving orders, missing branch-days, empty or inconsistent payment labels, total not equal to item sum, unknown menu item, empty platform reference. The data profile finds every one, and the counts match the generator manifest | Table: defect, detected, injected (copy from section 7 of `data-profile.md`) | Ready |
| 10 | Data modeling | Star schema: two fact tables (order, order line), a branch-day coverage fact, a data-quality fact, five dimensions. Partitioned by order date. Refunds are attributed to the order date, so a refund rewrites that order's partition | **Full width: `er_diagram.png`** (from `docs/er_diagram.dot`) | Ready |
| 11 | Transformation and considerations | Why batch: about 4 to 5 orders per second at peak, daily reporting, refunds arrive up to 8 days later. Engine choice: DuckDB + dbt fits the 9 GB budget (Trino was estimated at about 2.6 GB alone). Layers: raw CSV, bronze Parquet, silver cleaned, gold star schema, marts in PostgreSQL | Left: decision table (option, RAM, verdict). Right: layer strip | Text ready, strip is yours to draw |
| 12 | Plan and risks | Timeline to 22 Nov (pipeline end to end) and 29 Nov (review). Risks: 9 GB limit on Podman and WSL2, S3 integration untested, Windows setup untested | Simple timeline bar plus a three-row risk table | Text ready |
| 13 | Done so far and next | Done: generator with 37 tests, seeded and reproducible, repo with commit history, data model, data profile. Next: infrastructure, DAGs, dbt models, dashboard | Three small screenshots (you capture): `git log --oneline`, `pytest` summary, `jff-gen generate` run | Screenshots needed |

## Image inventory

| File (in `docs/`) | Used on slide | Placement | Notes |
|---|---|---|---|
| `slides/architecture.png` and `.svg` | 6 | Full width | Source `slides/architecture.dot`, edit and re-render with Graphviz |
| `er_diagram.png` and `.svg` | 10 | Full width | Source `er_diagram.dot` |
| `slides/chart_hourly_share.png` | 8 | Left | Regenerate with `slides/make_charts.py` |
| `slides/chart_channel_mix.png` | 8 | Right top | |
| `slides/chart_weekday.png` | 8 | Right bottom | |

SVG files can be recolored in PowerPoint to match your design.

## Still needed from you

1. The slide template file, if the bootcamp requires it.
2. Your name, education and working experience (slide 2).
3. The list of your other bootcamp projects with a one-line description each (slide 3).
4. Screenshots from your machine: head of `orders.csv`, `git log --oneline`, the `pytest` summary, a `jff-gen generate` run (slides 7 and 13).
5. Confirmation which template sections Check Point 1 requires. Slides 11 and 12 go beyond the Design stage, so drop them if the mentor only wants dataset, diagram, data model and repo.
6. Approval of these proposed success targets for slide 5: daily pipeline run succeeds at least 95% of days in the test window, yesterday's data is available on the dashboard by a fixed morning time, defect detection stays at 9 of 9.

## Caveats to state honestly on the slides

- The architecture is design v1. It has not been run yet, and RAM figures are estimates.
- Running the generator as an Airflow DAG is a proposal, not yet confirmed.
- All data is synthetic, so insights reflect the generator's assumptions, not real customers.
