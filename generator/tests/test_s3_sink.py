from collections.abc import Iterator
from pathlib import Path

import pytest

from jff_gen.cli import main

pytest.importorskip("moto")
boto3 = pytest.importorskip("boto3")
from moto.server import ThreadedMotoServer  # noqa: E402

BUCKET = "jff-raw"
COMMANDS = (
    ["dim", "all", "--branches", "5", "--seed", "7"],
    ["generate", "--date", "2026-10-05", "--scale", "0.02", "--branches", "5", "--seed", "7"],
)


@pytest.fixture
def s3_endpoint(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    url = f"http://{host}:{port}"
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    boto3.client("s3", endpoint_url=url).create_bucket(Bucket=BUCKET)
    yield url
    server.stop()


def _s3_objects(url: str) -> dict[str, bytes]:
    client = boto3.client("s3", endpoint_url=url)
    keys = [o["Key"] for o in client.list_objects_v2(Bucket=BUCKET)["Contents"]]
    return {k: client.get_object(Bucket=BUCKET, Key=k)["Body"].read() for k in keys}


def test_s3_output_matches_local_output(s3_endpoint: str, tmp_path: Path) -> None:
    for command in COMMANDS:
        main([*command, "--out", str(tmp_path)])
        main([*command, "--out", f"s3://{BUCKET}", "--s3-endpoint", s3_endpoint])
    local = {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert _s3_objects(s3_endpoint) == local
    assert "_manifests/dt=2026-10-05/manifest.json" in local


def test_s3_endpoint_requires_s3_url(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["dim", "all", "--out", str(tmp_path), "--s3-endpoint", "http://localhost:8333"])
    assert exc.value.code == 2
