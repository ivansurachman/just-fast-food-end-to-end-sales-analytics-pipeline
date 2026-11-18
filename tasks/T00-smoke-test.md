# T00: Windows + Podman smoke test

Serves: 22 Nov checkpoint (removes the largest unverified risk before any compose file is written).
Output: `docs/verification/T00-smoke-test.md`. Branch: `task/T00-smoke-test`.
Do not write compose files, Dockerfiles, DAGs, or any project code in this task. Report only.

## Steps

Run each command in PowerShell from the repo root. For each one, paste the command and the relevant output into the report.

1. Environment: `systeminfo | findstr /C:"OS Name" /C:"Total Physical Memory"`, `wsl -l -v`, `type $env:USERPROFILE\.wslconfig`, `podman --version`, `podman machine list`, `podman machine inspect`.
2. Engine: `podman info --format "{{.Host.CgroupsVersion}} {{.Host.CgroupManager}} {{.Host.Security.Rootless}}"`.
3. Compose provider: `podman compose version`, then `podman compose --help`. Record which provider runs (docker-compose or podman-compose) and its version. Also record `docker-compose --version` and `podman-compose --version` if present.
4. Memory limit enforcement (the key test). Pull `docker.io/library/python:3.12-slim` and run:

       podman run --rm --memory=64m --memory-swap=64m docker.io/library/python:3.12-slim python -c "b = bytearray(b'x') * (300*1024*1024); print('ALLOCATED')"

   Verdict: killed or exit code 137 means limits are enforced. Printing `ALLOCATED` means limits are **not** enforced.
5. Same test through compose: write a throwaway `tmp-compose.yaml` outside the repo (in `$env:TEMP`) with one service running the same command and `mem_limit: 64m`. Run it with `podman compose`. Then repeat with `deploy: resources: limits: memory: 64m`. Record which key, if any, is enforced. Delete the file afterwards.
6. Named volume persistence: start `docker.io/library/postgres` (pinned tag, older than 14 days, record it) on a named volume with a throwaway password, create a table, stop and remove the container, start a new one on the same volume, confirm the table exists. Then remove the container and the volume.
7. Port forwarding: with the Postgres container running, confirm `localhost:5432` is reachable from Windows (`Test-NetConnection localhost -Port 5432`).
8. Generator on Windows: `py -3.12 -m venv .venv`, activate, `pip install -c constraints.txt -e ".[dev,s3test]"` from `generator/`, run `pytest`, then `jff-gen generate --date 2026-10-05 --scale 0.02 --out ./tmp-out`. Record test count and result. Compare `tmp-out` with `sample-data/` for 2026-10-05 using `Get-FileHash`. Byte differences on Windows are a finding to report, not a bug to fix.
9. Disk and speed: free disk on the drive holding the repo, and the time of step 8's `generate`.

## STOP conditions (ask Ivan, do not work around)

- Any step needs `wsl --shutdown`, a `.wslconfig` edit, or installing software not listed above.
- Podman machine is not running and `podman machine start` fails.
- Anything that needs administrator rights.

## Acceptance

- The report contains all nine items with raw output. Items not run are marked "not run" with the reason.
- A final table "Findings" with: limits enforced (yes/no, which compose key), compose provider and version, named volume persistence (yes/no), port forwarding (yes/no), generator tests on Windows (pass count), byte identity with `sample-data/` (yes/no).
- No project files were changed except the report.
