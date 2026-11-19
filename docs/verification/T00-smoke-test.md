# T00: Windows + Podman smoke test — evidence

- Date: 2026-11-19
- Branch: `task/T00-smoke-test`
- Machine: Windows 11 Home Single Language, 16.147 MB physical RAM
- Shell: Windows PowerShell, commands run from the repo root unless noted
- Podman: 6.1.4

This task was **report-only**: no compose files, Dockerfiles, DAGs or project code were written.
Throwaway compose files lived in `%TEMP%` and were deleted. `generator/tmp-out/` (generated data)
was deleted afterwards. `generator/.venv/` remains but is gitignored.

## Deviation (approved by Ivan)

Step 8 asks for `py -3.12`. Python 3.12 is **not installed** on the machine; `py -0p` lists only
3.15.1 (`C:\Python315`) and a uv-managed 3.14.5. Installing an interpreter is a STOP condition, so
I asked Ivan, who chose to **use the existing Python 3.15.1**. All step-8 commands therefore ran on
3.15.1, which satisfies `requires-python = ">=3.11"`.

```
> py -0p
 -V:3.15 *        C:\Python315\python.exe
 -V:Astral/CPython3.14.5 C:\Users\acer-\AppData\Roaming\uv\python\cpython-3.14.5-windows-x86_64-none\python.exe
```

## 1. Environment

Command: `systeminfo | findstr /C:"OS Name" /C:"Total Physical Memory"`

```
OS Name:                       Microsoft Windows 11 Home Single Language
Total Physical Memory:         16.147 MB
```

Command: `wsl -l -v` (run before the Podman machine was started)

```
  NAME                   STATE           VERSION
* Ubuntu-24.04           Stopped         2
  podman-machine-default  Stopped         2
  Ubuntu                 Stopped         2
```

Note: `wsl -l -v` emits UTF-16 with interleaved spaces in this shell; transcribed above.
The Podman machine (`podman-machine-default`) was stopped. `podman machine start` **succeeded**,
so the "machine not running and start fails" STOP condition was not hit.

```
> podman machine start
Starting machine "podman-machine-default"
...
Machine "podman-machine-default" started successfully
```

Command: `type $env:USERPROFILE\.wslconfig`

```
type : Cannot find path 'C:\Users\acer-\.wslconfig' because it does not exist.
...
Exit code: 1
```

**Finding:** `.wslconfig` does **not** exist, although `docs/pipeline-design.md` assumes
`memory=9GB`. See "Memory vs. design intent" below.

Command: `podman --version`

```
podman version 6.1.4
```

Command: `podman machine list` (before start)

```
NAME                    VM TYPE     CREATED      LAST UP      CPUS        MEMORY      DISK SIZE
podman-machine-default  wsl         4 weeks ago  2 weeks ago  6           2GiB        100GiB
```

Command: `podman machine inspect` (key fields)

```
"Name": "podman-machine-default",
"Resources": { "CPUs": 6, "DiskSize": 100, "Memory": 2048 },
"State": "stopped",
"Rootful": true
```

## 2. Engine

Command: `podman info --format "{{.Host.CgroupsVersion}} {{.Host.CgroupManager}} {{.Host.Security.Rootless}}"`

```
v2 cgroupfs false
```

cgroups **v2**, cgroup manager **cgroupfs**, **rootful** (`false` = not rootless).

## 3. Compose provider

Command: `podman compose version`

```
>>>> Executing external compose provider "C:\Users\acer-\AppData\Local\Microsoft\WindowsApps\docker-compose.exe"...
Docker Compose version v5.6.1
```

`podman compose --help` confirms it is a thin wrapper that delegates to an external provider
(`docker-compose` takes precedence when present). At the time of this step the provider in use was the
**docker-compose standalone binary, v5.6.1**. **Superseded:** in the follow-up at the end of this
report the Python provider `podman-compose` 1.6.0 was made permanent, so `podman compose` now uses
`podman-compose`.

Command: `docker-compose --version`

```
Docker Compose version v5.6.1
```

Command: `podman-compose --version` (in the agent's `-NoProfile` shell)

```
podman-compose : The term 'podman-compose' is not recognized as the name of a cmdlet, function,
script file, or operable program. ...
Exit code: 1
```

This is a **PATH** effect, not a missing install. The agent shell runs PowerShell with `-NoProfile`,
so `conda init` in `C:\Users\acer-\Documents\WindowsPowerShell\profile.ps1` does not run and the
conda base directory is not on `PATH`. With the profile loaded (nested `powershell -Command`, conda
base active) the tool is present:

```
> powershell -NoLogo -Command "where.exe podman-compose; (Get-Command podman-compose).Source"
C:\Users\acer-\miniconda3\Scripts\podman-compose.exe
C:\Users\acer-\miniconda3\Scripts\podman-compose.exe

> powershell -NoLogo -Command "podman-compose --version"
podman version 6.1.4
podman-compose version 1.6.0

> conda list podman-compose
podman-compose             1.6.0            pypi_0           pypi
```

**`podman-compose` 1.6.0 IS installed** — pip in conda base
(`C:\Users\acer-\miniconda3\Scripts\podman-compose.exe`, 108,333 bytes) — and is also present in WSL
Ubuntu-24.04 (`/home/ubuntu/.local/bin/podman-compose`, 1.6.0, with podman 4.9.3 inside WSL). It is
simply not on the machine's default PATH / the `-NoProfile` PATH, which is why a plain `cmd` or
`where.exe` from the agent does not see it. A correction to my first pass, which wrongly said it was
not installed.

Important: even with conda active, `podman compose version` still reported
`Docker Compose version v5.6.1` at the time of this step. `docker-compose` is on PATH and, per
`podman compose --help`, takes precedence over `podman-compose`. That was changed afterwards by
setting `compose_providers` in `containers.conf` (see the permanent-provider section).

## 4. Memory limit enforcement — direct engine

Command:

```
podman run --rm --memory=64m --memory-swap=64m docker.io/library/python:3.12-slim python -c "b = bytearray(b'x') * (300*1024*1024); print('ALLOCATED')"
```

Output:

```
exitcode=137
```

`ALLOCATED` was **not** printed. Exit code **137** (SIGKILL / OOM) means the limit is **enforced**.

Image pulled: `docker.io/library/python:3.12-slim`
(`78976a69c067520ef8be34cde307ef9f6fea6dcefa50edb57039773d241ca0db`).

## 5. Memory limit enforcement — through `podman compose`

Throwaway file `%TEMP%\tmp-compose-memlimit.yaml`:

```yaml
services:
  memtest:
    image: docker.io/library/python:3.12-slim
    mem_limit: 64m
    command: ["python", "-c", "b = bytearray(b'x') * (300*1024*1024); print('ALLOCATED')"]
```

Command: `podman compose -f %TEMP%\tmp-compose-memlimit.yaml up --abort-on-container-exit --exit-code-from memtest`

```
 Container temp-memtest-1 Started
memtest-1 exited with code 137
...
exitcode=137
```

`mem_limit: 64m` is **enforced** (exit 137).

Throwaway file `%TEMP%\tmp-compose-deploylimits.yaml` (same service, Deploy key instead):

```yaml
services:
  memtest:
    image: docker.io/library/python:3.12-slim
    command: ["python", "-c", "b = bytearray(b'x') * (300*1024*1024); print('ALLOCATED')"]
    deploy:
      resources:
        limits:
          memory: 64m
```

Command: `podman compose -f %TEMP%\tmp-compose-deploylimits.yaml up --abort-on-container-exit --exit-code-from memtest`

```
memtest-1 exited with code 137
...
exitcode=137
```

`deploy.resources.limits.memory: 64m` is **also enforced** (exit 137).

Both throwaway files and both compose projects (`down -v`) were removed afterwards; no `temp`
network or container remained.

## 6. Named volume persistence

Pinned image: **`docker.io/library/postgres:16.4`** (a fixed historical tag, released well over
14 days before 2026-11-19; `docs/versions.md` does not exist yet, so this is the tag recorded for
this test — confirm it for the real stack when `docs/versions.md` is created).

Steps and raw output:

```
> podman volume create jff_pgtest
jff_pgtest
> podman run -d --name pgtest1 -e POSTGRES_PASSWORD=throwaway -v jff_pgtest:/var/lib/postgresql/data -p 5432:5432 docker.io/library/postgres:16.4
0c94a1be1fbac307f95eaeb72cd5ace971bf8a6acd841fa662098b12e23b2889
> ... wait until pg_isready ...
ready=True
pgtest1 | Up 3 seconds | 0.0.0.0:5432->5432/tcp

> podman exec pgtest1 psql -U postgres -c "CREATE TABLE smoke_test(id int primary key, note text); INSERT INTO smoke_test VALUES (1, 'persisted');"
CREATE TABLE
INSERT 0 1
> podman exec pgtest1 psql -U postgres -c "SELECT * FROM smoke_test;"
 id |   note
----+-----------
  1 | persisted
(1 row)

> podman rm -f pgtest1
pgtest1
> podman run -d --name pgtest2 -e POSTGRES_PASSWORD=throwaway -v jff_pgtest:/var/lib/postgresql/data -p 5432:5432 docker.io/library/postgres:16.4
c1247960cb7a74843bc361681f20ff2f6276f80a1ca043aba80b0a6c6fddea46
> ... wait until pg_isready ...
ready=True
> podman exec pgtest2 psql -U postgres -c "SELECT * FROM smoke_test;"
 id |   note
----+-----------
  1 | persisted
(1 row)

> podman rm -f pgtest2
> podman volume rm jff_pgtest
```

Table survived removal and recreation of the container on the same named volume.
Container **and** volume were then removed (verified: no test containers, `jff_pgtest` gone).

## 7. Port forwarding (Windows -> container)

Command: `Test-NetConnection localhost -Port 5432` (run while `pgtest1` was up)

```
ComputerName     : localhost
RemoteAddress    : ::1
RemotePort       : 5432
InterfaceAlias   : Loopback Pseudo-Interface 1
SourceAddress    : ::1
TcpTestSucceeded : True
```

`TcpTestSucceeded: True`. The container published `0.0.0.0:5432->5432/tcp` and Windows reached
`localhost:5432`.

## 8. Generator on Windows

Run from `generator/`. Python 3.15.1 and its venv:

```
> py -m venv .venv
> .\.venv\Scripts\Activate.ps1
> python --version
Python 3.15.1
> pip --version
pip 26.2.2 ... (python 3.15)
```

Install:

```
> pip install -c constraints.txt -e ".[dev,s3test]"
...
Successfully installed aiobotocore-3.10.0 ... moto-5.2.5 ... pandas-3.0.6 ... numpy-2.5.4 ...
pip_exitcode=0
```

All pinned packages had cp315 Windows wheels (numpy, pandas, pydantic-core, etc.); `pyyaml`
built from source successfully. Install exit code 0.

Tests:

```
> pytest
platform win32 -- Python 3.15.1, pytest-9.2.0, pluggy-1.7.0
collected 41 items
...
tests\test_s3_sink.py E.                                                 [ 82%]
...
=================================== ERRORS ====================================
ERROR tests/test_s3_sink.py::test_s3_output_matches_local_output
E   botocore.exceptions.EndpointConnectionError: Could not connect to the endpoint URL: "http://0.0.0.0:50656/jff-raw"
E   ... OSError: [WinError 10049] The requested address is not valid in its context
=========================== short test summary info ===========================
ERROR tests/test_s3_sink.py::test_s3_output_matches_local_output
======================== 40 passed, 1 error in 10.15s =========================
pytest_exitcode=1
```

**Result: 40 passed, 1 error.** Re-run on 2026-11-19 (second invocation): `40 passed, 1 error in
10.62s` — the same error, reproducible and not flaky. The single error is Windows-specific:
`ThreadedMotoServer` reports host `0.0.0.0`, and Windows refuses to connect to `0.0.0.0`
(`WinError 10049`). On Linux this test presumably connects fine. This is a finding to report, not
a generator bug to fix (generator behaviour must not be edited here).

Generate (timed):

```
> jff-gen generate --date 2026-10-05 --scale 0.02 --out ./tmp-out
2026-11-19 14:04:00,961 INFO 2026-10-05: {'orders': 2201, 'order_items': 5384, 'order_changes': 22}
generate_exitcode=0
generate_seconds=2.56
```

Byte identity vs `sample-data/` for `dt=2026-10-05` (`Get-FileHash -Algorithm SHA256`):

| File (relative) | Bytes (gen / sample) | SHA-256 | Match |
|---|---|---|---|
| `orders/dt=2026-10-05/orders.csv` | 236131 / 236131 | `CB692142314BBECED9E6EC282A6FE3AF85ABEAAAB1B3C569C778B3300FFC2469` | yes |
| `order_changes/dt=2026-10-05/order_changes.csv` | 1861 / 1861 | `23C18AD029A787D4A0365E603CCB75EB0B9F3EE0DC8105B82C010395174A0D34` | yes |
| `order_items/dt=2026-10-05/order_items.csv` | 230269 / 230269 | `08321D143B0A373D5C4E7A777826C8224CB8CCA011616A029C894101BA8D6D02` | yes |
| `_manifests/dt=2026-10-05/manifest.json` | 506 / 506 | `579A1F4F018DA4914F747AEA741C3D4125DE2D96D0A6BF45E40E40C8E1E7E134` | yes |

`all_match=True`. **All four files are byte-identical** to `sample-data/` on Windows for this date
(contrary to the design doc's expectation that byte identity is Linux-only).

## 9. Disk and speed

Free disk on the repo drive (`D:`):

```
Get-Volume -DriveLetter D
DriveLetter : D
FileSystemLabel : New Volume
FreeGB : 485,7
SizeGB : 931,5
```

- Free on `D:`: **485.7 GB** of 931.5 GB.
- `jff-gen generate` (2026-10-05, scale 0.02): **2.56 s**.

## Memory vs. design intent (extra finding)

`podman machine inspect` advertises `Resources.Memory = 2048` MB and `CPUs = 6`, and
`podman machine list` shows `MEMORY 2GiB`. But the engine and containers actually see:

```
> podman info --format "MemTotal={{.Host.MemTotal}} CPUs={{.Host.CPUs}}"
MemTotal=8202760192 CPUs=12

> podman run --rm docker.io/library/python:3.12-slim python -c "import os; print('mem_gib', round(os.sysconf('SC_PHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')/1024**3,2)); print('cpus', os.cpu_count())"
mem_gib 7.64
cpus 12
```

So the per-machine 2 GiB / 6 CPU setting is **not** what the WSL VM applies; the VM follows the
WSL2 default (about 50% of 16 GB RAM) = **~7.64 GiB and 12 CPUs**.

Implications:

- The 5.6 GB stack budget **fits** in ~7.64 GiB (headroom ~2 GiB), but the design doc's stated
  `9GB` target is **not** met. There is ~1.4 GiB less than planned.
- `.wslconfig` is absent. Setting `memory=9GB` (or raising the machine limit) is a configuration
  change and therefore out of scope for this task — Ivan must decide and apply it before the
  full stack is brought up.

## Full re-run (2026-11-19, second pass)

Ivan asked to run the whole T00 again. All nine steps were repeated end-to-end.

| Step | Re-run result |
|---|---|
| 1 Environment | Windows 11 Home Single Language, 16.147 MB RAM; `.wslconfig` **still absent**; Podman 6.1.4; `podman-machine-default` **running**; `machine list` still shows 2 GiB / 6 CPU; `machine inspect` `Resources.Memory = 2048`, `State = running` |
| 2 Engine | `v2 cgroupfs false`; `MemTotal=8202760192 CPUs=12` (containers still actually see ~7.64 GiB / 12 CPU) |
| 3 Compose provider | as measured: docker-compose **v5.6.1** via `podman compose` (default PATH); `podman-compose` 1.6.0 exists in conda base + WSL. **Afterwards** made permanent: provider is now `podman-compose` |
| 4 Direct memory | exit **137** |
| 5 Compose memory | `mem_limit: 64m` → exit **137**, `OOMKilled=true`; `deploy.resources.limits.memory: 64m` → exit **137**, `OOMKilled=true` |
| 6 Named volume | table persisted across container replacement (**yes**) |
| 7 Port forwarding | `TcpTestSucceeded: True` on `localhost:5432` |
| 8 Generator | `pip install` exit **0**; `pytest` **40 passed, 1 error in 16.15s** (same `0.0.0.0` / `WinError 10049`); generate **2.15 s**; **4/4 files byte-identical** |
| 9 Disk/speed | `D:` **485.2 GB** free of 931.5 GB; generate **2.15 s** |

Behaviour difference on this pass: the first `podman compose ... up --abort-on-container-exit` for
the `mem_limit` file **did not return** even though the container had already `Exited (137)`; the
attach/abort path hung and the process tree was killed manually. The limit itself was enforced
(`podman ps` showed `Exited (137)`). To get a deterministic exit code, both compose keys were then
re-measured with `up -d` followed by `podman wait`:

```
> podman compose -f tmp-compose-memlimit.yaml up -d
> podman wait temp-memtest-1
137
> podman inspect temp-memtest-1 --format "ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}"
ExitCode=137 OOMKilled=true
```

Same for the deploy-key file: `137 / OOMKilled=true`. Both throwaway files and projects were then
deleted, and `generator/tmp-out/` was removed again.

**New finding:** `podman compose` (docker-compose v5.6.1 provider) can hang on
`up --abort-on-container-exit` after the container exits; `up -d` + `podman wait` is reliable.
Not re-tested with `podman-compose`, which became the provider afterwards.

## Step 5 re-test with the `podman-compose` provider (2026-11-19)

After the correction above, step 5 was repeated with the Python provider instead of docker-compose.
The provider was first selected with an environment variable for the session only (no config file
edit); it was made permanent afterwards (see the permanent-provider section below).

```
> $env:PODMAN_COMPOSE_PROVIDER = 'C:\Users\acer-\miniconda3\Scripts\podman-compose.exe'
> podman compose version
>>>> Executing external compose provider "C:\Users\acer-\miniconda3\Scripts\podman-compose.exe"...
podman version 6.1.4
podman-compose version 1.6.0
```

`mem_limit: 64m` (throwaway `%TEMP%\tmp-compose-memlimit.yaml`):

```
> podman compose -f tmp-compose-memlimit.yaml up -d
up_exit=0
temp_memtest_1 | Exited (137)
> podman inspect temp_memtest_1 --format "ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}"
ExitCode=137 OOMKilled=true
```

`deploy.resources.limits.memory: 64m` (throwaway `%TEMP%\tmp-compose-deploylimits.yaml`):

```
> podman compose -f tmp-compose-deploylimits.yaml up -d
up_exit=0
temp_memtest_1 | Exited (137)
> podman inspect temp_memtest_1 --format "ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}"
ExitCode=137 OOMKilled=true
```

Both keys are enforced with the `podman-compose` provider as well. Note the container name differs by
provider: `temp_memtest_1` (podman-compose, underscores) vs `temp-memtest-1` (docker-compose,
hyphens). Both throwaway projects (`down -v`) and files were removed afterwards; no container or
`temp` network remained.

## Permanent provider = `podman-compose` (2026-11-19 follow-up)

Ivan asked to make the `podman-compose` provider permanent. On this Windows setup Podman reads
`containers.conf` from `%APPDATA%\containers\containers.conf`
(`C:\Users\acer-\AppData\Roaming\containers\containers.conf`). The file now contains:

```toml
# User-level Podman configuration.
# Set by the T00 smoke-test follow-up so `podman compose` uses the Python
# podman-compose provider (conda base) instead of docker-compose.
[engine]
compose_providers = ['C:\Users\acer-\miniconda3\Scripts\podman-compose.exe']
```

Verification with **no** `PODMAN_COMPOSE_PROVIDER` in the environment:

```
> podman compose version
>>>> Executing external compose provider "C:\Users\acer-\miniconda3\Scripts\podman-compose.exe"...
podman version 6.1.4
podman-compose version 1.6.0
```

Functional check through the permanent config (`up -d` + inspect):

```
> podman compose -f tmp-compose-memlimit.yaml up -d
up_exit=0
temp_memtest_1 | Exited (137)
> podman inspect temp_memtest_1 --format "ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}"
ExitCode=137 OOMKilled=true
```

**Path finding:** a `containers.conf` first created at `~/.config/containers/containers.conf` was
**ignored** — `podman compose version` still picked docker-compose. Only
`%APPDATA%\containers\containers.conf` took effect. The ignored file was removed. This is a user
config change outside the repo; no project file was changed.

## Findings

| Item | Result |
|---|---|
| Memory limits enforced | **Yes** — `podman run --memory` (137), compose `mem_limit` (137) **and** `deploy.resources.limits.memory` (137); also enforced with the `podman-compose` provider (both keys, 137 / `OOMKilled=true`) |
| Compose provider and version | **`podman-compose` 1.6.0** (conda base, `C:\Users\acer-\miniconda3\Scripts\podman-compose.exe`) — made the permanent provider via `%APPDATA%\containers\containers.conf` `[engine] compose_providers`; verified with no env var. Before that change the provider was docker-compose v5.6.1. `podman-compose` is not on the default / `-NoProfile` PATH, so the absolute path is used |
| Named volume persistence | **Yes** — table survived container remove/recreate on `jff_pgtest` |
| Port forwarding | **Yes** — `localhost:5432` reachable (`TcpTestSucceeded: True`) |
| Generator tests on Windows | **40 passed, 1 error** (moto `0.0.0.0` `WinError 10049`) |
| Byte identity with `sample-data/` | **Yes** — 4/4 files SHA-256 identical for `dt=2026-10-05` |

Additional findings:

- `.wslconfig` missing; actual VM memory ~7.64 GiB / 12 CPUs, not the configured 2 GiB / 6 CPUs
  and not the design's 9 GB.
- Python 3.12 absent; step 8 run on 3.15.1 after Ivan's approval.
- `podman-compose` 1.6.0 is installed in conda base
  (`C:\Users\acer-\miniconda3\Scripts\podman-compose.exe`) and WSL Ubuntu-24.04
  (`/home/ubuntu/.local/bin/podman-compose`), but not on the default `-NoProfile` PATH, which is why
  `containers.conf` points at the absolute path. (My first pass wrongly reported it as not
  installed; corrected here.)
- `podman compose` uses **`podman-compose` 1.6.0** permanently now, set in
  `C:\Users\acer-\AppData\Roaming\containers\containers.conf`. The same file placed at
  `~/.config/containers/containers.conf` was ignored by this Podman build. This is a user-level
  config change outside the repo, at Ivan's request; no project file was changed.
- `test_s3_sink.py::test_s3_output_matches_local_output` errors on Windows because the moto server
  host is `0.0.0.0` and Windows cannot connect to it.

## Acceptance check

- [x] All nine items have raw output above.
- [x] Findings table completed.
- [x] No project files changed except this report (`tmp-out/` removed; `.venv/` is gitignored).
- [x] The only change outside the repo is the user-level Podman config
  `%APPDATA%\containers\containers.conf` (provider preference), made at Ivan's request and recorded
  in the permanent-provider section.
