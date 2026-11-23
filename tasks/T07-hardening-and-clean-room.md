# T07: clean-room run, hardening, CI

Branch: `task/T07-hardening` (from `main`). Serves "deployment best practices" and turns the "verify" claims in the docs into facts.

## Deliverables

- `tools/gen_env.py`: creates `.env` from `.env.example` by generating random values for every secret variable (passwords, `AIRFLOW_FERNET_KEY` as a valid 32-byte url-safe base64 key, JWT and API secrets, S3 keys) with the standard library. Refuses to overwrite an existing `.env`. Prints names only, never values.
- `.github/workflows/ci.yml`: on push and pull request, ubuntu runner, Python 3.12, installs `generator/constraints.txt`, runs `ruff`, `mypy`, `pytest` for the generator and pipelines tests that need no containers. Pin action versions (verify tags and dates, older than 14 days).
- `security_opt: ["no-new-privileges:true"]` on every service in `compose.yaml` if `podman-compose` accepts it (verify). Do not add `cap_drop` or read-only roots now.
- `docs/security.md`: what is protected (loopback ports, read-only analytics role, per-service roles, secrets only in `.env`, `check_secrets.py`), what is not (rootful Podman machine, native Windows Postgres on 5432 outside the project, secrets visible to the coding agent's model provider), and the dependency and image scan results below.
- `docs/verification/T07-hardening.md`.

## Acceptance (evidence for each)

1. **Clean-room.** Clone the public repository into a new empty folder (path without spaces), run `python tools/gen_env.py`, then `podman compose build --no-cache`, `podman compose up -d`, wait for healthy, generate 7 days (2026-10-03 to 2026-10-09, scale 0.02) inside the scheduler, run the DAG for those days, and show the dashboard data through the API. Ask Ivan before running `podman compose down -v` on the existing stack, and use a different compose project name (`-p jff-clean`) and different host ports through `.env` so both stacks do not collide. Report every manual step you had to take beyond the README as a documentation bug.
2. `check_secrets.py` clean on the clone.
3. **Dependency scan.** Run `pip-audit` for each pinned set (generator, Airflow image extras, dbt venv). Report counts by severity and the packages. Fix only direct dependencies where a fixed version exists and is older than 14 days; otherwise record in `docs/security.md`.
4. **Image scan.** Scan the images used (Postgres, SeaweedFS, Metabase, the Airflow image) with Trivy (run it as a container; verify the image and pin it). Report HIGH and CRITICAL counts per image. Do not change image versions in this task; record and let Ivan decide.
5. CI passes on GitHub (Ivan confirms the run result; report the run URL or say "not run").
6. `no-new-privileges` applied and the stack is healthy, or the evidence that `podman-compose` rejects it.

## Rules

- Load `podman-windows`, `lean-code`, `debug-protocol` as needed. No `browser` skill.
- Docs may claim Windows with Podman only as tested. Docker, Linux and macOS stay "expected to work, not tested here" unless you actually test them.

## STOP

- The clean-room run needs a step that the README does not state and you cannot resolve in 30 minutes. Report the step list.
- A scan finds a CRITICAL issue in a direct dependency with no fixed version.
