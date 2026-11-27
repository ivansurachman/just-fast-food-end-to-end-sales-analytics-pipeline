"""Set up the Metabase pages through its REST API: admin account, connection, cards, dashboards.

Idempotent and *updating*: on a database that is already set up it logs in, reuses the connection,
**replaces the SQL of every question** with the files next to this script and rewrites each page's
cards, so changing a `.sql` file and re-running this script is enough.

Two checks keep a half-built pipeline from looking finished: before creating anything it asks
Metabase whether the sales mart exists, and stops with "run the backfill first" when it does not;
after each card is created or updated it runs that card's query, names every card that returns an
error and exits non-zero at the end.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

LOG = logging.getLogger("setup_metabase")

BASE_URL: Final = "http://localhost:3000"
DASHBOARD_HOME: Final = Path(__file__).parent
DATABASE_NAME: Final = "JFF analytics"
MART_TABLE: Final = "mart_sales_day_branch_channel"


@dataclass(frozen=True)
class CardSpec:
    """One question: its name, its SQL file under the page folder, and where it sits on the page."""

    name: str
    sql_file: str
    display: str
    row: int
    col: int
    size_x: int = 12
    size_y: int = 6


@dataclass(frozen=True)
class PageSpec:
    """One dashboard page and its cards."""

    name: str
    folder: str
    description: str
    cards: tuple[CardSpec, ...]


PAGES: Final = (
    PageSpec(
        name="Sales overview",
        folder="sales_overview",
        description="Net sales, orders, order value, cancellation and refund rates, channels.",
        cards=(
            CardSpec("Net sales per day", "net_sales_per_day.sql", "line", 0, 0, 24),
            CardSpec("Completed orders", "completed_orders.sql", "bar", 6, 0),
            CardSpec("Average order value", "average_order_value.sql", "line", 6, 12),
            CardSpec("Cancellation rate", "cancellation_rate.sql", "line", 12, 0),
            CardSpec("Refund rate", "refund_rate.sql", "line", 12, 12),
            CardSpec("Orders by channel", "orders_by_channel.sql", "bar", 18, 0),
            CardSpec(
                "Top 10 branches by net sales", "top_branches_by_net_sales.sql", "table", 18, 12
            ),
        ),
    ),
    PageSpec(
        name="Channel and branch",
        folder="channel_branch",
        description="Net sales mix, contribution margin and net sales per branch-day.",
        cards=(
            CardSpec("Net sales by channel", "net_sales_by_channel.sql", "bar", 0, 0),
            CardSpec(
                "Channel contribution margin", "channel_contribution_margin.sql", "table", 0, 12
            ),
            CardSpec("Net sales per branch-day", "net_sales_per_branch_day.sql", "table", 6, 0, 24),
        ),
    ),
    PageSpec(
        name="Operations",
        folder="operations",
        description="Order volume by hour and weekday, peak-hour load, branch reporting coverage.",
        cards=(
            CardSpec("Orders by hour and weekday", "orders_by_hour.sql", "line", 0, 0, 24),
            CardSpec("Peak-hour load per branch", "peak_hour_load.sql", "table", 6, 0),
            CardSpec("Branch reporting coverage", "branch_reporting_coverage.sql", "line", 6, 12),
        ),
    ),
    PageSpec(
        name="Menu",
        folder="menu",
        description="Item sales mix and item gross margin.",
        cards=(
            CardSpec("Item sales mix", "item_sales_mix.sql", "bar", 0, 0),
            CardSpec("Item gross margin", "item_gross_margin.sql", "table", 0, 12),
        ),
    ),
    PageSpec(
        name="Promo",
        folder="promo",
        description="Discount rate by promotion and the average order value lift against no promo.",
        cards=(
            CardSpec("Discount rate by promo", "discount_rate_by_promo.sql", "bar", 0, 0),
            CardSpec("Promo AOV lift", "promo_aov_lift.sql", "table", 0, 12),
        ),
    ),
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
            raise RuntimeError(f"{method} {path} -> {error.code}: {body[:500]}") from error

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

    def search(self, model: str) -> list[dict[str, Any]]:
        """Every item of one model (card, dashboard) in the search index."""
        _, result = self.request("GET", f"/search?q=&models={model}&limit=200")
        return result.get("data", [])

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

    def ensure_card(self, name: str, definition: dict[str, Any]) -> int:
        """Create the card, or replace the definition of the card with that name.

        Updating matters: the SQL of a card lives in this repository, so re-running the setup after
        changing a file must change the card, not leave the old query in Metabase. Only the fields
        this script owns are sent, so a dashboard or a display setting changed in the UI is kept.
        """
        for card in self.search("card"):
            if card.get("name") == name:
                owned: dict[str, Any] = {
                    key: definition[key]
                    for key in ("name", "description", "display", "dataset_query")
                    if key in definition
                }
                self.request("PUT", f"/card/{card['id']}", owned)
                LOG.info("card %s updated (id %s)", name, card["id"])
                return int(card["id"])
        _, created = self.request("POST", "/card", definition)
        LOG.info("card %s created (id %s)", name, created["id"])
        return int(created["id"])

    def ensure_dashboard(self, page: PageSpec) -> dict[str, Any]:
        for dashboard in self.search("dashboard"):
            if dashboard.get("name") == page.name:
                LOG.info("dashboard %s already exists (id %s)", page.name, dashboard["id"])
                return dashboard
        _, created = self.request(
            "POST", "/dashboard", {"name": page.name, "description": page.description}
        )
        LOG.info("dashboard %s created (id %s)", page.name, created["id"])
        return created


def card_definition(page: PageSpec, card: CardSpec, database_id: int) -> dict[str, Any]:
    """The Metabase payload of one card, with the SQL read from its file."""
    sql = (DASHBOARD_HOME / page.folder / card.sql_file).read_text(encoding="utf-8")
    return {
        "name": card.name,
        "description": f"{page.name}: {card.sql_file}",
        "display": card.display,
        "visualization_settings": {},
        "dataset_query": {
            "database": database_id,
            "type": "native",
            "native": {"query": sql, "template-tags": {}},
        },
    }


def mart_table_exists(client: Metabase, database_id: int) -> bool:
    """True when the sales mart table exists in the analytics database.

    The check runs through Metabase's own connection, so it needs nothing beyond the standard
    library and proves the same role the cards will use can see the table.
    """
    _, result = client.request(
        "POST",
        "/dataset",
        {
            "database": database_id,
            "type": "native",
            "native": {
                "query": f"select to_regclass('public.{MART_TABLE}') is not null",
                "template-tags": {},
            },
        },
    )
    if result.get("status") != "completed":
        # A broken connection and a missing table look alike in the rows; do not report the second
        # when the first is what happened.
        raise RuntimeError(f"the mart check failed: {result.get('error') or result.get('status')}")
    rows = (result.get("data") or {}).get("rows") or []
    return bool(rows and rows[0] and rows[0][0])


@dataclass
class CardReport:
    """What the card run produced: how many were checked, returned rows, or failed."""

    checked: int = 0
    with_rows: int = 0
    problems: list[tuple[str, str]] = field(default_factory=list)


def verify_card(client: Metabase, name: str, card_id: int) -> tuple[int, str | None]:
    """Run one card's query; return (row count, error)."""
    try:
        _, result = client.request("POST", f"/card/{card_id}/query")
    except RuntimeError as error:
        return 0, str(error)
    status = result.get("status")
    if status != "completed":
        return 0, str(result.get("error") or status)
    rows = (result.get("data") or {}).get("rows") or []
    return len(rows), None


def setup_pages(
    client: Metabase, database_id: int
) -> tuple[list[tuple[str, int, int]], CardReport]:
    """Create or update every page and run every card.

    Returns (page name, dashboard id, card count) per page and the card report: how many cards were
    checked and returned rows, and the (card name, error) pairs of the ones that failed.
    """
    pages: list[tuple[str, int, int]] = []
    report = CardReport()
    for page in PAGES:
        card_ids: list[int] = []
        for card in page.cards:
            card_id = client.ensure_card(card.name, card_definition(page, card, database_id))
            card_ids.append(card_id)
            rows, error = verify_card(client, card.name, card_id)
            report.checked += 1
            if error:
                report.problems.append((card.name, error))
            elif rows:
                report.with_rows += 1
        dashboard = client.ensure_dashboard(page)
        dashcards = [
            {
                "id": -index,
                "card_id": card_id,
                "row": card.row,
                "col": card.col,
                "size_x": card.size_x,
                "size_y": card.size_y,
                "parameter_mappings": [],
                "visualization_settings": {},
            }
            for index, (card, card_id) in enumerate(zip(page.cards, card_ids, strict=True), start=1)
        ]
        client.request("PUT", f"/dashboard/{dashboard['id']}", {"dashcards": dashcards})
        LOG.info("dashboard %s (id %s) has %d cards", page.name, dashboard["id"], len(dashcards))
        pages.append((page.name, int(dashboard["id"]), len(dashcards)))
    return pages, report


def main(dry_run: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    env = {**load_dotenv(), **os.environ}
    email = env["MB_ADMIN_EMAIL"]
    password = env["MB_ADMIN_PASSWORD"]
    site_name = env.get("MB_SITE_NAME", "Just Fast Food")

    client = Metabase()
    client.wait_healthy()
    if dry_run:
        LOG.info("healthy at %s, would set up %d pages", BASE_URL, len(PAGES))
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

    if not mart_table_exists(client, database_id):
        print(
            f"the analytics table {MART_TABLE} does not exist in PostgreSQL: "
            "run the backfill first (python tools/run_backfill.py --from-date ... --to-date ...)"
        )
        return 1

    pages, report = setup_pages(client, database_id)
    for name, dashboard_id, cards in pages:
        print(f"{name}: {BASE_URL}/dashboard/{dashboard_id} ({cards} cards)")
    for name, error in report.problems:
        print(f"card {name} failed: {error}")
    print(
        f"{report.checked} cards checked, {report.with_rows} returned rows, "
        f"{len(report.problems)} failed"
    )
    return 1 if report.problems else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    sys.exit(main(parser.parse_args().dry_run))
