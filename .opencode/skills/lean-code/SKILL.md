---
name: lean-code
description: Use before writing or editing Python, SQL, dbt models, Dockerfiles or compose files in this repo. Write only the code that needs to exist, reuse what DuckDB, dbt, the standard library and pinned dependencies already do, and keep what remains readable.
---

# lean-code

## 1. Decide what to write (stop at the first rung that holds)

1. Does the task's acceptance list need it? If not, do not write it. Add the idea to `docs/later.md`.
2. Can DuckDB do it in SQL? (`read_csv`, `read_parquet`, hive partitioning, `COPY ... TO`, window functions, `QUALIFY`.) Use SQL, not Python loops and not pandas.
3. Can dbt do it? (generic tests `unique`, `not_null`, `relationships`, `accepted_values`; seeds; incremental strategies; vars.) Use those before custom macros or singular tests.
4. Can the standard library or an already pinned dependency do it? (`pathlib`, `argparse`, `dataclasses`, `logging`; see `generator/constraints.txt`.) A new dependency needs a reason, a pinned version older than 14 days, and a line in `docs/versions.md`.
5. Can the image or compose feature do it (healthcheck, `mem_limit`, `depends_on`) instead of a wrapper script? Use it.
6. Only then write new code, the minimum that works.

Never cut: input validation at boundaries, clear error messages, idempotent writes (same input, same output path), determinism, explicit memory limits.

## 2. Shape what remains

- Names reveal intent; functions are verb + noun; booleans read as questions. No magic numbers, use named constants.
- One job per function, guard clauses, flat over nested, at most three arguments (otherwise a dataclass).
- Type hints and an English docstring on public functions. Comments explain why, never what.
- Do not mutate inputs. No dead code. No `utils` module for one function.
- Use `logging`, not `print`. Never build SQL by string formatting with external values; use DuckDB or psycopg parameters.
- Never load a full-scale day into pandas. The memory budget in `AGENTS.md` is real.

## 3. Before and after editing

- Before: find what imports or references the file (search for the module and function names). Edit every dependent in the same task. No broken imports or stale call sites.
- After: run the checks listed in `AGENTS.md`. Say plainly which checks were not run.
- If a requirement is unclear or the fix needs changes outside the task, ask one targeted question. If it is a bug inside the task, fix it without a lecture.
