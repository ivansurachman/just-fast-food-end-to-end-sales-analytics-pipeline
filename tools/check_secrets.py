"""Check that values from the local .env never appeared in git, in any commit.

Only variables whose names look like credentials are checked unless --all is given.
Prints variable names and commit hashes only, never values. Exit code 1 means a
value was found and the secret must be rotated, not just removed from the file.

    python tools/check_secrets.py            # reads .env in the current folder
    python tools/check_secrets.py --env path/to/.env
"""

import argparse
import subprocess
import sys
from pathlib import Path

MIN_VALUE_LENGTH = 8
RISKY_PATHS = (".env", "*.pem", "*.key", "*.p12", "id_rsa*")
SECRET_NAME_PARTS = ("PASSWORD", "PASS", "SECRET", "KEY", "TOKEN", "CREDENTIAL")


def read_env(path: Path) -> dict[str, str]:
    """Return KEY=VALUE pairs of an env file, skipping comments and short values."""
    pairs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, value = text.partition("=")
        value = value.strip().strip("'\"")
        if len(value) >= MIN_VALUE_LENGTH:
            pairs[key.strip()] = value
    return pairs


def is_secret_name(name: str) -> bool:
    """True when the variable name suggests a credential (PASSWORD, KEY, TOKEN, ...)."""
    upper = name.upper()
    return any(part in upper for part in SECRET_NAME_PARTS)


def git(*args: str) -> str:
    """Run a git command without a shell and return its stdout."""
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", check=False
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def commits_with_value(value: str) -> list[str]:
    """Commits in any branch whose diff adds or removes this exact text."""
    out = git(
        "log",
        "--all",
        "-S",
        value,
        "--format=%h",
        "--fixed-strings",
        "--no-textconv",
        "--no-ext-diff",
    )
    return out.split()


def tracked_files_with_value(value: str) -> list[str]:
    """Tracked files in the working tree that contain this exact text."""
    result = subprocess.run(
        ["git", "grep", "-I", "-l", "-F", "-e", value],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout.split()


def risky_files_in_history() -> list[str]:
    """Names of key or env files that were ever committed."""
    out = git("log", "--all", "--name-only", "--format=", "--", *RISKY_PATHS)
    return sorted({name for name in out.splitlines() if name and name != ".env.example"})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument(
        "--all",
        action="store_true",
        help="check every variable, not only names that look like credentials",
    )
    args = parser.parse_args(argv)
    if not args.env.exists():
        print(f"{args.env} not found")
        return 2
    problems = 0
    skipped: list[str] = []
    for name, value in read_env(args.env).items():
        if not args.all and not is_secret_name(name):
            skipped.append(name)
            continue
        history = commits_with_value(value)
        files = tracked_files_with_value(value)
        if history or files:
            problems += 1
            print(f"FOUND  {name}: commits {history or '-'}, tracked files {files or '-'}")
        else:
            print(f"clean  {name}")
    if skipped:
        print(f"skipped (name does not look like a credential): {', '.join(skipped)}")
    for name in risky_files_in_history():
        problems += 1
        print(f"FOUND  file in history: {name}")
    print("secrets in git: NONE" if not problems else f"secrets in git: {problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
