"""Create `.env` from `.env.example`, filling every secret with a fresh random value.

Standard library only, so it runs before any dependency is installed:

    python tools/gen_env.py                 # writes .env next to .env.example
    python tools/gen_env.py --out other.env # somewhere else, e.g. for a clean-room clone
    python tools/gen_env.py --print         # show what would be generated, write nothing

It never overwrites an existing file and never prints a value: only variable names. Everything that
is not a secret (ports, user names, e-mails, region, site name) is copied from the example.
"""

from __future__ import annotations

import argparse
import base64
import os
import secrets
import sys
from pathlib import Path

SECRET_NAME_PARTS = ("PASSWORD", "PASS", "SECRET", "KEY", "TOKEN", "CREDENTIAL")
# Characters compose would interpolate or a shell would eat. token_urlsafe and alphanumerics never
# contain them; the check in main() makes that a guarantee rather than a hope.
UNSAFE = set("$\\\"'`")
PASSWORD_BYTES = 24
JWT_BYTES = 64


def is_secret(name: str) -> bool:
    """True when the variable name marks a value that must be random."""
    upper = name.upper()
    return any(part in upper for part in SECRET_NAME_PARTS)


def fernet_key() -> str:
    """A valid Fernet key: url-safe base64 of 32 random bytes."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def alphanumeric(length: int = 32) -> str:
    """A random alphanumeric value, for consumers that reject punctuation."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generated(name: str) -> str:
    """The value this variable gets, decided by the name."""
    upper = name.upper()
    if upper == "AIRFLOW_FERNET_KEY":
        return fernet_key()
    if upper.startswith("S3_"):
        # The SeaweedFS entrypoint writes these into a JSON document.
        return alphanumeric(32)
    if "JWT" in upper:
        return secrets.token_urlsafe(JWT_BYTES)
    return secrets.token_urlsafe(PASSWORD_BYTES)


def build_env(example: str) -> tuple[list[str], dict[str, str], list[str]]:
    """Return the output lines, the generated name/value pairs, and the copied names."""
    lines: list[str] = []
    generated_values: dict[str, str] = {}
    copied_names: list[str] = []
    for raw in example.splitlines():
        text = raw.strip()
        if not text or text.startswith("#") or "=" not in text:
            lines.append(raw)
            continue
        name = text.partition("=")[0].strip()
        if not is_secret(name):
            lines.append(raw)
            copied_names.append(name)
            continue
        value = generated(name)
        lines.append(f"{name}={value}")
        generated_values[name] = value
    return lines, generated_values, copied_names


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--example", type=Path, default=Path(".env.example"))
    parser.add_argument("--out", type=Path, default=Path(".env"))
    parser.add_argument("--print", dest="dry_run", action="store_true", help="write nothing")
    args = parser.parse_args(argv)

    if not args.example.is_file():
        print(f"{args.example} not found")
        return 2
    if args.out.exists() and not args.dry_run:
        print(f"{args.out} already exists, not overwriting it")
        return 2

    lines, generated_values, copied_names = build_env(args.example.read_text(encoding="utf-8"))
    for name in generated_values:
        print(f"generate  {name}")
    for name in copied_names:
        print(f"copy      {name}")

    unsafe = [name for name, value in generated_values.items() if UNSAFE.intersection(value)]
    if unsafe:
        print(f"generated values contain unsafe characters: {', '.join(unsafe)}")
        return 1

    if args.dry_run:
        print(f"would write {args.out} with {len(generated_values)} generated values")
        return 0

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name == "posix":
        args.out.chmod(0o600)
    print(f"wrote {args.out}: {len(generated_values)} generated, {len(copied_names)} copied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
