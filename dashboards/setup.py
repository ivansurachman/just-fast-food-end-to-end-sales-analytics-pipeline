"""Set up Metabase through its REST API: admin account, analytics connection, cards, dashboard.

Idempotent: on a database that is already set up it logs in, then reuses or creates the connection,
the three questions and the dashboard, so running it twice does not duplicate anything.

    python dashboards/setup.py            # from the repo root, with the stack up
    python dashboards/setup.py --dry-run  # print what it would do

Only the standard library is used. Credentials come from the environment or from `.env`; nothing is
written into this file.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final

LOG = logging.getLogger("setup_metabase")

BASE_URL: Final = "http://localhost:3000"
SQL_DIR: Final = Path(__file__).parent / "sales_overview"
DASHBOARD_NAME: Final = "Sales overview"
DATABASE_NAME: Final = "JFF analytics"
# name, SQL file, display, grid row, grid column, width, height
CARDS: Final = (
    ("Net sales per day", "net_sales_per_day.sql", "line", 0, 0, 24, 6),
    ("Orders by channel", "orders_by_channel.sql", "bar", 6, 0, 12, 6),
    ("Top 10 branches by net sales", "top_branches_by_net_sales.sql", "table", 6, 12, 12, 6),
)


def load_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    """Read simple KEY=VALUE lines so the script works from a plain shell."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


class Metabase:
    """Minimal REST client with a session token."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id: str | None = None

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        url = f"{self.base_url}/api{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.session_id:
            request.add_header("X-Metabase-Session", self.session_id)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read().decode()
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            body = error.read().decode()
            detail = body[:500]
            raise RuntimeError(f"{method} {path} -> {error.code}: {detail}") from error

    def wait_healthy(self, timeout_s: int = 300) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                status, body = self.request("GET", "/health")
                if status == 200 and body == {"status": "ok"}:
                    return
            except (urllib.error.URLError, RuntimeError, ConnectionError):
                pass
            time.sleep(3)
        raise RuntimeError(f"Metabase at {self.base_url} did not become healthy")

    def setup_token(self) -> str | None:
        _, properties = self.request("GET", "/session/properties")
        return properties.get("setup-token")

    def setup(self, token: str, email: str, password: str, site_name: str) -> None:
        self.request(
            "POST",
            "/setup",
            {
                "token": token,
                "user": {
                    "email": email,
                    "password": password,
                    "first_name": "JFF",
                    "last_name": "Admin",
                },
                "prefs": {"site_name": site_name},
            },
        )

    def login(self, email: str, password: str) -> None:
        _, body = self.request("POST", "/session", {"username": email, "password": password})
        self.session_id = body["id"]

    def database_id(self, name: str, create: dict[str, Any] | None) -> int:
        _, databases = self.request("GET", "/database")
        for database in databases.get("data", databases if isinstance(databases, list) else []):
            if database.get("name") == name:
                LOG.info("database %s already exists (id %s)", name, database["id"])
                return int(database["id"])
        if create is None:
            raise RuntimeError(f"database {name} does not exist and no definition was given")
        _, created = self.request("POST", "/database", create)
        LOG.info("database %s created (id %s)", name, created["id"])
        return int(created["id"])

    def card_id(self, name: str, create: dict[str, Any] | None) -> int:
        _, cards = self.request("GET", "/search?q=&models=card&limit=200")
        for card in cards.get("data", []):
            if card.get("name") == name:
                LOG.info("card %s already exists (id %s)", name, card["id"])
                return int(card["id"])
        if create is None:
            raise RuntimeError(f"card {name} does not exist and no definition was given")
        _, created = self.request("POST", "/card", create)
        LOG.info("card %s created (id %s)", name, created["id"])
        return int(created["id"])

    def dashboard(self) -> dict[str, Any]:
        _, dashboards = self.request("GET", "/search?q=&models=dashboard&limit=200")
        for dashboard in dashboards.get("data", []):
            if dashboard.get("name") == DASHBOARD_NAME:
                LOG.info("dashboard %s already exists (id %s)", DASHBOARD_NAME, dashboard["id"])
                return dashboard
        _, created = self.request(
            "POST",
            "/dashboard",
            {"name": DASHBOARD_NAME, "description": "Net sales, channel mix and top branches."},
        )
        LOG.info("dashboard %s created (id %s)", DASHBOARD_NAME, created["id"])
        return created


def main(dry_run: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    env = {**load_dotenv(), **os.environ}
    email = env["MB_ADMIN_EMAIL"]
    password = env["MB_ADMIN_PASSWORD"]
    site_name = env.get("MB_SITE_NAME", "Just Fast Food")

    client = Metabase()
    client.wait_healthy()
    if dry_run:
        LOG.info("healthy at %s, would set up %s", BASE_URL, DASHBOARD_NAME)
        return 0

    token = client.setup_token()
    if token:
        client.setup(token, email, password, site_name)
        LOG.info("first-run setup finished for %s", email)
    client.login(email, password)

    database_id = client.database_id(
        DATABASE_NAME,
        {
            "engine": "postgres",
            "name": DATABASE_NAME,
            "details": {
                "host": "postgres",
                "port": 5432,
                "dbname": "analytics",
                "user": "analytics_ro",
                "password": env["POSTGRES_ANALYTICS_RO_PASSWORD"],
                "ssl": False,
            },
            "is_full_sync": True,
            "is_sample": False,
            "auto_run_queries": True,
            "schedules": {},
        },
    )

    card_ids: dict[str, int] = {}
    for name, sql_file, display, _row, _col, _x, _y in CARDS:
        sql = (SQL_DIR / sql_file).read_text(encoding="utf-8")
        card_ids[name] = client.card_id(
            name,
            {
                "name": name,
                "description": sql_file,
                "display": display,
                "visualization_settings": {},
                "dataset_query": {
                    "database": database_id,
                    "type": "native",
                    "native": {"query": sql, "template-tags": {}},
                },
            },
        )

    dashboard = client.dashboard()
    dashcards = [
        {
            "id": -index,
            "card_id": card_ids[name],
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
            "parameter_mappings": [],
            "visualization_settings": {},
        }
        for index, (name, _sql, _display, row, col, size_x, size_y) in enumerate(CARDS, start=1)
    ]
    client.request("PUT", f"/dashboard/{dashboard['id']}", {"dashcards": dashcards})
    LOG.info(
        "dashboard %s (id %s) has %d cards",
        DASHBOARD_NAME,
        dashboard["id"],
        len(dashcards),
    )
    print(f"dashboard_url={BASE_URL}/dashboard/{dashboard['id']}")
    print("cards=" + ", ".join(f"{name} (id {card_ids[name]})" for name, *_ in CARDS))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    sys.exit(main(parser.parse_args().dry_run))
