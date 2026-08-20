#!/usr/bin/env python3
"""Render deeper-analysis charts (matplotlib) from the parsed receipt data.

Writes PNGs to analysis/charts/:
  monthly_trend.png   monthly spend with a 3-month rolling average
  price_trends.png    unit price paid over time for the most-bought products
  weekday_pattern.png shopping trips and median basket by day of week
  basket_hist.png     distribution of receipt totals
  top_spend.png       products ranked by total recorded spend
  savings.png         monthly promotional savings and savings rate
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
CHARTS = ROOT / "analysis" / "charts"

INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
BLUE = "#2a78d6"
BLUE_DARK = "#104281"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "font.size": 9,
    "text.color": INK,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK2,
    "axes.titlecolor": INK,
    "axes.titlesize": 11,
    "axes.titleweight": "semibold",
    "axes.titlelocation": "left",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
})


def read_csv(name: str, base: Path = ROOT / "analysis") -> list[dict[str, str]]:
    path = base / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def style(ax: plt.Axes, money_axis: bool = True) -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=0)
    if money_axis:
        ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(CHARTS / name, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  {CHARTS / name}")


def product_key(description: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", description.lower())


def monthly_trend(monthly: list[dict[str, str]]) -> None:
    months = [datetime.strptime(r["month"], "%Y-%m") for r in monthly]
    spend = [float(r["spend"]) for r in monthly]
    rolling = [sum(spend[max(0, i - 2): i + 1]) / len(spend[max(0, i - 2): i + 1])
               for i in range(len(spend))]
    fig, ax = plt.subplots(figsize=(8.4, 3.4))
    ax.bar(months, spend, width=22, color=BLUE, zorder=2)
    ax.plot(months, rolling, color=BLUE_DARK, linewidth=2, solid_capstyle="round",
            zorder=3, label="3-month average")
    ax.set_title("Monthly grocery spend")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b ’%y"))
    ax.legend(frameon=False, loc="upper left")
    style(ax)
    save(fig, "monthly_trend.png")


def price_trends(items: list[dict[str, str]], receipts: list[dict[str, str]]) -> None:
    receipt_dates = {r["receipt_id"]: date.fromisoformat(r["purchase_date"])
                     for r in receipts if r["parse_status"] != "duplicate"}
    series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    labels: dict[str, str] = {}
    units: dict[str, str] = {}
    for item in items:
        when = receipt_dates.get(item["receipt_id"])
        if when is None or float(item["line_total"]) <= 0:
            continue
        key = product_key(item["description"])
        if float(item["quantity"]) <= 0:
            continue
        if item["quantity_unit"] == "kg":
            unit_price, unit = float(item["unit_price"]), "$/kg"
        else:
            unit_price, unit = float(item["line_total"]) / float(item["quantity"]), "$ each"
        if len(item["description"]) > len(labels.get(key, "")):
            labels[key] = item["description"]
        units[key] = unit
        series[key].append((when, unit_price))

    ranked = sorted(series, key=lambda k: -len({d for d, _ in series[k]}))[:6]
    fig, axes = plt.subplots(2, 3, figsize=(8.4, 4.6), sharex=True)
    for ax, key in zip(axes.flat, ranked):
        points = sorted(series[key])
        ax.plot([p[0] for p in points], [p[1] for p in points], color=BLUE,
                linewidth=1.6, marker="o", markersize=3.5, zorder=3)
        first, last = points[0][1], points[-1][1]
        arrow = "→" if abs(last - first) < 0.005 else ("↑" if last > first else "↓")
        ax.set_title(f"{labels[key][:34]}\n${first:.2f} {arrow} ${last:.2f} ({units[key]})",
                     fontsize=8.5)
        ax.margins(y=0.25)
        style(ax, money_axis=False)
        ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.2f}")
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("’%y"))
    fig.suptitle("Unit price paid over time — most-bought products", x=0.005, y=1.0,
                 ha="left", fontsize=11, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    save(fig, "price_trends.png")


def weekday_pattern(receipts: list[dict[str, str]]) -> None:
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    trips = [0] * 7
    baskets: list[list[float]] = [[] for _ in range(7)]
    for r in receipts:
        weekday = date.fromisoformat(r["purchase_date"]).weekday()
        trips[weekday] += 1
        baskets[weekday].append(float(r["total"]))
    medians = [sorted(b)[len(b) // 2] if b else 0 for b in baskets]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.4, 3.0))
    ax1.bar(day_names, trips, color=BLUE, zorder=2)
    ax1.set_title("Shopping trips by day of week")
    ax1.margins(y=0.12)
    style(ax1, money_axis=False)
    ax2.bar(day_names, medians, color=BLUE, zorder=2)
    ax2.set_title("Median basket by day of week")
    ax2.margins(y=0.12)
    style(ax2)
    fig.tight_layout()
    save(fig, "weekday_pattern.png")


def basket_hist(receipts: list[dict[str, str]]) -> None:
    totals = sorted(float(r["total"]) for r in receipts)
    median = totals[len(totals) // 2]
    top = max(totals)
    bins = range(0, int(top) + 20, 20)
    fig, ax = plt.subplots(figsize=(8.4, 3.0))
    ax.hist(totals, bins=bins, color=BLUE, zorder=2, rwidth=0.92)
    ax.axvline(median, color=BLUE_DARK, linewidth=1.6, linestyle=(0, (4, 3)))
    ax.annotate(f"median ${median:,.0f}", (median, ax.get_ylim()[1] * 0.95),
                xytext=(6, 0), textcoords="offset points", color=INK2, fontsize=8.5)
    ax.set_title("How big is a shop? Receipt totals")
    ax.set_ylabel("receipts")
    ax.xaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    style(ax, money_axis=False)
    save(fig, "basket_hist.png")


def top_spend(items: list[dict[str, str]], receipts: list[dict[str, str]]) -> None:
    grocery_ids = {r["receipt_id"] for r in receipts}
    spend: dict[str, float] = defaultdict(float)
    labels: dict[str, str] = {}
    for item in items:
        if item["receipt_id"] not in grocery_ids or float(item["line_total"]) <= 0:
            continue
        key = product_key(item["description"])
        spend[key] += float(item["line_total"])
        if len(item["description"]) > len(labels.get(key, "")):
            labels[key] = item["description"]
    ranked = sorted(spend.items(), key=lambda kv: kv[1])[-15:]
    names = [labels[k][:36] for k, _ in ranked]
    values = [v for _, v in ranked]
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    ax.barh(names, values, color=BLUE, zorder=2, height=0.62)
    for i, v in enumerate(values):
        ax.annotate(f"${v:,.0f}", (v, i), xytext=(4, -3), textcoords="offset points",
                    color=INK2, fontsize=8.5)
    ax.set_title("Products by total recorded spend (top 15)")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.xaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    save(fig, "top_spend.png")


def category_spend(rows: list[dict[str, str]]) -> None:
    shown = [r for r in rows if r["category"] not in ("discounts", "shopping bags", "clothing")][:16]
    shown.reverse()
    names = [r["category"] for r in shown]
    values = [float(r["spend"]) for r in shown]
    shares = [float(r["share"]) for r in shown]
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.barh(names, values, color=BLUE, zorder=2, height=0.62)
    for i, (v, s) in enumerate(zip(values, shares)):
        ax.annotate(f"${v:,.0f} · {s:.0%}", (v, i), xytext=(4, -3),
                    textcoords="offset points", color=INK2, fontsize=8.5)
    ax.set_title("Spend by category type (top 16, share of total)")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.margins(x=0.12)
    ax.xaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    save(fig, "category_spend.png")


def savings(receipts: list[dict[str, str]]) -> None:
    monthly_saved: dict[str, float] = defaultdict(float)
    monthly_spend: dict[str, float] = defaultdict(float)
    for r in receipts:
        month = r["purchase_date"][:7]
        monthly_saved[month] += float(r["savings"] or 0)
        monthly_spend[month] += float(r["total"])
    months = sorted(monthly_spend)
    dates = [datetime.strptime(m, "%Y-%m") for m in months]
    saved = [monthly_saved[m] for m in months]
    total_saved = sum(saved)
    total_spend = sum(monthly_spend.values())
    rate = total_saved / (total_saved + total_spend)
    fig, ax = plt.subplots(figsize=(8.4, 3.0))
    ax.bar(dates, saved, width=22, color=BLUE, zorder=2)
    ax.set_title(f'Promotional savings by month — "you saved" totals '
                 f"(${total_saved:,.0f} overall, {rate:.0%} off gross)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b ’%y"))
    style(ax)
    save(fig, "savings.png")


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    monthly = read_csv("monthly_spend.csv")
    receipts = [r for r in read_csv("receipts.csv", ROOT / "parsed")
                if not r["store_name"].lower().startswith("big w")
                and r["parse_status"] != "duplicate"]
    items = read_csv("items.csv", ROOT / "parsed")
    if not monthly or not receipts:
        raise SystemExit("Run parse_receipts.py and analyze_groceries.py first")
    print("Writing charts:")
    monthly_trend(monthly)
    price_trends(items, receipts)
    weekday_pattern(receipts)
    basket_hist(receipts)
    top_spend(items, receipts)
    category_spend(read_csv("category_spend.csv"))
    savings(receipts)


if __name__ == "__main__":
    main()
