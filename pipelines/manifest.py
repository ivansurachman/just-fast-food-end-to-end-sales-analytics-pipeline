"""The generator's day-complete manifest on S3, read with boto3.

The manifest marks a day as complete and records the row count per entity. It is written last by
`jff-gen`, so its presence is what `wait_manifest` waits for. Transformations never read it
(docs/pipeline-design.md section 7); only the sensor and `pipelines.check_bronze` do.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

DEFAULT_ENDPOINT = "http://seaweedfs:8333"
DEFAULT_BUCKET = "jff-raw"
MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


def s3_client(endpoint: str | None = None) -> Any:
    """S3 client with path-style addressing, as SeaweedFS needs.

    Credentials come from `S3_ACCESS_KEY`/`S3_SECRET_KEY` (the names compose sets) or from the
    standard `AWS_*` variables.
    """
    access_key = os.environ.get("S3_ACCESS_KEY") or os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("S3_SECRET_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    return boto3.client(
        "s3",
        endpoint_url=endpoint or os.environ.get("JFF_S3_ENDPOINT", DEFAULT_ENDPOINT),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )


def manifest_key(ds: str) -> str:
    """Object key of the manifest for the generator file date `ds`."""
    return f"_manifests/dt={ds}/manifest.json"


def object_exists(bucket: str, key: str, *, endpoint: str | None = None) -> bool:
    """True when the object is on the endpoint. Any other S3 error is raised, not swallowed."""
    try:
        s3_client(endpoint).head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in MISSING_CODES:
            return False
        raise
    return True


def read_manifest(
    ds: str, *, bucket: str = DEFAULT_BUCKET, endpoint: str | None = None
) -> dict[str, Any]:
    """Read and parse `_manifests/dt=<ds>/manifest.json`."""
    body = s3_client(endpoint).get_object(Bucket=bucket, Key=manifest_key(ds))["Body"].read()
    manifest: dict[str, Any] = json.loads(body)
    return manifest
