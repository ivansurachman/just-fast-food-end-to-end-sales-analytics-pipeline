"""Render slide charts from a generated dataset: python make_charts.py <data folder> <out folder>."""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from jff_gen.profiling import load_dataset

COLORS = {
    "offline": "#f0a030",
    "online": "#5b9bd5",
    "bar": "#5b9bd5",
    "sales": "#f0a030",
}
CAPTION = "Synthetic data, 45 days, scale 0.1, seed 42"


def _style(ax: plt.Axes, title: str) -> None:
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def _save(fig: plt.Figure, path: Path) -> None:
    fig.text(0.01, 0.01, CAPTION, fontsize=9, color="#666666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def orders_frame(data: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    ds = load_dataset(data)
    orders = ds.orders.drop_duplicates()
    online_ids = set(
        ds.channels.loc[ds.channels["order_origin"] == "online", "channel_id"]
    )
    orders = orders.assign(
        hour=orders["order_ts"].str[11:13].astype(int),
        origin=orders["channel_id"].map(
            lambda c: "online" if c in online_ids else "offline"
        ),
        order_date=orders["order_ts"].str[:10],
    )
    return orders, ds.channels


def chart_hourly(orders: pd.DataFrame, out: Path) -> None:
    share = orders.groupby(["hour", "origin"]).size().unstack(fill_value=0)
    share = 100 * share / share.sum()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for origin in ("offline", "online"):
        ax.plot(
            share.index,
            share[origin],
            marker="o",
            linewidth=2.5,
            color=COLORS[origin],
            label=origin,
        )
    ax.set_xticks(share.index)
    ax.set_xlabel("Local hour of day")
    ax.set_ylabel("Share of orders (%)")
    ax.legend(frameon=False)
    _style(ax, "Lunch and dinner peaks, online skews to evening")
    _save(fig, out / "chart_hourly_share.png")


def chart_channels(orders: pd.DataFrame, out: Path) -> None:
    done = orders[orders["status"] == "completed"]
    order_share = 100 * orders["channel_id"].value_counts(normalize=True)
    sales = done.groupby("channel_id")["total_amount"].sum()
    sales_share = 100 * sales / sales.sum()
    table = pd.DataFrame({"orders": order_share, "net sales": sales_share}).sort_values(
        "orders"
    )
    fig, ax = plt.subplots(figsize=(10, 5.6))
    positions = range(len(table))
    height = 0.38
    ax.barh(
        [p - height / 2 for p in positions],
        table["orders"],
        height,
        color=COLORS["bar"],
        label="orders",
    )
    ax.barh(
        [p + height / 2 for p in positions],
        table["net sales"],
        height,
        color=COLORS["sales"],
        label="net sales",
    )
    ax.set_yticks(list(positions), table.index)
    ax.set_xlabel("Share (%)")
    ax.legend(frameon=False)
    _style(ax, "Channel mix: share of orders vs net sales")
    ax.grid(axis="x", alpha=0.25)
    ax.grid(axis="y", visible=False)
    _save(fig, out / "chart_channel_mix.png")


def chart_weekday(orders: pd.DataFrame, out: Path) -> None:
    daily = orders.groupby(["order_date", "branch_id"]).size().reset_index(name="n")
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    daily["weekday"] = pd.to_datetime(daily["order_date"]).dt.dayofweek.map(
        dict(enumerate(names))
    )
    mean = daily.groupby("weekday")["n"].mean().reindex(names)
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.bar(mean.index, mean.to_numpy(), color=COLORS["bar"])
    ax.set_ylabel("Orders per branch per day")
    _style(ax, "Weekend uplift in daily orders per branch")
    _save(fig, out / "chart_weekday.png")


def main(data: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    orders, _ = orders_frame(data)
    chart_hourly(orders, out)
    chart_channels(orders, out)
    chart_weekday(orders, out)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
