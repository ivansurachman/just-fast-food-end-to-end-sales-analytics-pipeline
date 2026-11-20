---
name: podman-windows
description: Use before creating or changing compose files, Dockerfiles, container scripts or anything that runs Podman on Ivan's Windows machine. A checklist of what behaves differently here, taken from the T00 smoke test.
---

# podman-windows

Facts measured on this machine (see `docs/verification/T00-smoke-test.md`):

- Podman 6.1.4, rootful machine on WSL2, cgroups v2. The VM has the WSL2 default of about 7.6 GiB. There is no `.wslconfig`. Never create or edit it.
- `podman compose` runs `podman-compose` 1.6.0 through `containers.conf`. Never change that setting. Container names use underscores (`project_service_1`).
- Memory limits are enforced for `mem_limit` and `deploy.resources.limits.memory`. Use `mem_limit` on every service.

Rules:

- Bring up and tear down with `podman compose up -d` and `podman compose down` from the repo root. For checks use `podman inspect` or `podman wait`. Do not use `up --abort-on-container-exit`: it hung with docker-compose and was not tested with podman-compose.
- `depends_on` with `condition: service_healthy` may not be honored by podman-compose. Test it, and add a retry step in the init container as a fallback.
- Data lives on **named volumes** (Postgres, SeaweedFS, DuckDB file). Bind mounts only for code, with relative paths and forward slashes.
- Publish ports on loopback only: `127.0.0.1:5432:5432`, never `0.0.0.0`.
- Secrets come from `.env` (untracked). `.env.example` has harmless values. Never put credentials in compose files, Dockerfiles or logs.
- Pin every image tag, and pick a release older than 14 days. Record tag, release date and reason in `docs/versions.md`.
- Files that run inside Linux containers keep LF line endings. Do not rely on a bash script as the only entry point; provide a PowerShell or Python alternative.
- PowerShell quoting is fragile. For anything with nested quotes, write a script file instead of a one-liner.
- Useful checks: `podman stats --no-stream`, `podman machine ssh free -m`, `podman inspect <name> --format "{{.State.OOMKilled}}"`.
- Never run, without asking Ivan: `wsl --shutdown`, `podman system prune`, `podman volume rm` on project volumes, `podman machine rm`, anything that edits `containers.conf` or `.wslconfig`.
- Anything about rootless Podman, Docker Desktop, Linux or macOS that was not tested here is written as "verify" in the docs, never as fact.
