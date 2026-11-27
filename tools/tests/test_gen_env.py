"""gen_env: LF endings, the Postgres port choice, and the refusal to overwrite."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import gen_env

EXAMPLE = """# a comment
POSTGRES_HOST_PORT=5432
POSTGRES_PASSWORD=example-password
S3_ACCESS_KEY=jffexampleaccesskey
MB_ADMIN_EMAIL=admin@example.com
"""


def write_example(tmp_path: Path) -> Path:
    """A tiny .env.example with one secret, one S3 key and one port."""
    path = tmp_path / ".env.example"
    path.write_text(EXAMPLE, encoding="utf-8")
    return path


def generate(tmp_path: Path, *extra: str) -> tuple[int, Path]:
    """Run main() against a fresh example; return the exit code and the output path."""
    out = tmp_path / ".env"
    code = gen_env.main(["--example", str(write_example(tmp_path)), "--out", str(out), *extra])
    return code, out


def test_writes_lf_line_endings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen_env, "is_listening", lambda port: False)
    code, out = generate(tmp_path)

    assert code == 0
    data = out.read_bytes()
    assert b"\r\n" not in data, "compose reads a carriage return as part of the value"
    assert data.endswith(b"\n")


def test_postgres_port_flag_wins(tmp_path: Path) -> None:
    code, out = generate(tmp_path, "--postgres-port", "5444")

    assert code == 0
    assert "POSTGRES_HOST_PORT=5444" in out.read_text(encoding="utf-8").splitlines()


def test_a_listening_5432_moves_the_port_to_5433(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gen_env, "is_listening", lambda port: port == 5432)
    code, out = generate(tmp_path)

    assert code == 0
    assert "POSTGRES_HOST_PORT=5433" in out.read_text(encoding="utf-8").splitlines()


def test_a_free_5432_keeps_the_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen_env, "is_listening", lambda port: False)
    code, out = generate(tmp_path)

    assert code == 0
    assert "POSTGRES_HOST_PORT=5432" in out.read_text(encoding="utf-8").splitlines()


def test_refuses_to_overwrite(tmp_path: Path) -> None:
    out = tmp_path / ".env"
    out.write_text("keep me\n", encoding="utf-8")

    code = gen_env.main(
        ["--example", str(write_example(tmp_path)), "--out", str(out), "--postgres-port", "5432"]
    )

    assert code == 2
    assert out.read_text(encoding="utf-8") == "keep me\n"
