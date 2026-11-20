"""Fixtures: a tiny raw tree on disk, and the compose SeaweedFS endpoint when it is reachable."""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

# Columns the generator writes are wider than this; the tests only need the ones they assert on.
FACT_HEADERS = {
    "orders": "order_id,order_ts,branch_id,channel,gross_amount",
    "order_items": "order_id,line_no,menu_item_id,quantity,line_amount",
    "order_changes": "change_id,order_id,change_ts,change_type,refund_amount",
}
FACT_ROWS = {
    "orders": [
        "1,2026-10-05T10:00:00,101,dine_in,25000",
        "2,2026-10-05T11:30:00,102,delivery,18000",
        "3,2026-10-05T12:15:00,101,takeaway,9000",
    ],
    "order_items": [
        "1,1,501,2,25000",
        "2,1,502,1,18000",
        "3,1,501,1,9000",
    ],
    "order_changes": ["1,3,2026-10-05T13:00:00,refund,9000"],
}
DIMENSION_HEADERS = {
    "branches": "branch_id,name,open_date",
    "channels": "channel_id,name",
    "menu_items": "menu_item_id,name,price",
    "promos": "promo_id,name",
}
DIMENSION_ROWS = {
    "branches": ["101,Alpha,2025-01-01", "102,Beta,2026-01-01"],
    "channels": ["dine_in,Dine in", "delivery,Delivery", "takeaway,Takeaway"],
    "menu_items": ["501,Burger,12500", "502,Fries,18000"],
    "promos": ["p1,Opening promo"],
}
DAY = "2026-10-05"


@pytest.fixture
def raw_root(tmp_path: Path) -> Path:
    """A raw tree shaped like the generator's output, for one day plus the dimensions."""
    root = tmp_path / "jff-raw"
    for entity, header in FACT_HEADERS.items():
        path = root / entity / f"dt={DAY}" / f"{entity}.csv"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join([header, *FACT_ROWS[entity]]) + "\n", encoding="utf-8")
    (root / "dimensions").mkdir()
    for entity, header in DIMENSION_HEADERS.items():
        path = root / "dimensions" / f"{entity}.csv"
        path.write_text("\n".join([header, *DIMENSION_ROWS[entity]]) + "\n", encoding="utf-8")
    return root


@pytest.fixture
def s3_endpoint() -> str:
    """The compose SeaweedFS endpoint, or skip when it is not reachable or unconfigured."""
    endpoint = os.environ.get("JFF_S3_ENDPOINT", "http://localhost:8333")
    if not os.environ.get("S3_ACCESS_KEY") or not os.environ.get("S3_SECRET_KEY"):
        pytest.skip("S3_ACCESS_KEY/S3_SECRET_KEY are not exported")
    parsed = urlparse(endpoint)
    try:
        with socket.create_connection(
            (parsed.hostname or "localhost", parsed.port or 80), timeout=2
        ):
            pass
    except OSError:
        pytest.skip(f"no S3 endpoint at {endpoint}")
    return endpoint


@pytest.fixture
def s3_client(s3_endpoint: str) -> Iterator[Any]:
    """boto3 client for cleanup and for reading object metadata."""
    from pipelines.manifest import s3_client as make_client

    client = make_client(s3_endpoint)
    yield client
    client.close()
