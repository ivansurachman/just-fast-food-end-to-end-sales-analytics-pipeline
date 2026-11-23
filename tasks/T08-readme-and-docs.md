# T08: README, architecture diagram, conclusion

Branch: `task/T08-docs` (from `main`, after T07). Serves "code documentation" (10% of the grade), the 29 Nov review and the final slides.

## Deliverables

- `README.md` in English: what the project is; the as-built architecture diagram; layers and data flow (raw CSV, bronze, silver, gold, marts, dashboard); how to run it on Windows with Podman (the only tested path) with the exact commands from T07; short sections for Docker, Linux and macOS marked "expected to work, not tested here" with the known differences (compose provider, rootless Podman, bind mounts); the DAG and its tasks; the reprocessing window and why (refunds up to 8 days later, late orders); the nine injected defects and how each is detected; measured resource numbers (RAM per container, backfill time, peak scheduler memory, rows and sizes); the dashboard pages with a screenshot path; a decisions table with trade-offs and rejected alternatives; limitations; repo layout.
- Update `docs/slides/architecture.*` to the as-built design (Podman, SeaweedFS, Airflow 3.3.2, dbt-duckdb, PostgreSQL, Metabase). Regenerate with the existing tooling.
- `docs/conclusion.md`: conclusion and recommendation with **measured** results only. Sections: what the platform does, evidence (numbers and the verification reports it comes from), limitations (single-writer DuckDB, synthetic data so insights reflect generator assumptions, commission rates are placeholders, newest day is provisional, orphan refunds before the window, no real-time view), and what to change at 100 times the volume.
- `docs/verification/T08-docs.md`.

## Rules

- Every number in the docs must come from a file under `docs/verification/` or a command you ran now. Cite the report. No estimates presented as results.
- Do not claim behavior that was not tested. Use "not tested" explicitly.
- Do not change code in this task except fixing a documentation bug you find; list each one.
- Load `lean-code`. No `browser` skill.

## Acceptance (evidence for each)

1. A person who has not seen the project can follow the README on Windows with Podman from `git clone` to the dashboard. Ivan performs this on a clean clone and reports each place he got stuck; fix them.
2. `git grep -n "verify"` in `docs/` and `README.md` lists every remaining unverified claim, each with a reason, or none.
3. Links and paths in the README resolve (`git ls-files` check for each referenced path).
4. The architecture diagram matches `compose.yaml` services and the DAG task list (show the comparison).
