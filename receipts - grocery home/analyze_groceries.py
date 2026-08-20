#!/usr/bin/env python3
"""Find spending patterns and forecast recurring purchases from parsed receipts."""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from categorize import categorize

# Categories that are checkout artifacts or non-grocery, not shopping needs.
NON_FORECAST_CATEGORIES = {"discounts", "shopping bags", "clothing", "unmapped"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def money(value: Decimal | float) -> str:
    return f"{Decimal(str(value)):.2f}"


def key_for(description: str) -> str:
    """Normalize harmless spacing/punctuation differences without guessing aliases."""
    return re.sub(r"[^a-z0-9]+", "", description.lower())


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parsed-dir", type=Path, default=Path("parsed"))
    parser.add_argument("--output-dir", type=Path, default=Path("analysis"))
    parser.add_argument("--horizon-days", type=int, default=30)
    parser.add_argument("--as-of", type=date.fromisoformat,
                        help="Forecast start date (YYYY-MM-DD); defaults to today")
    args = parser.parse_args()

    receipts = read_csv(args.parsed_dir / "receipts.csv")
    items = read_csv(args.parsed_dir / "items.csv")
    grocery_receipts = [r for r in receipts
                        if not r["store_name"].lower().startswith("big w")
                        and r.get("parse_status") != "duplicate"]
    grocery_ids = {r["receipt_id"] for r in grocery_receipts}
    grocery_items = [i for i in items if i["receipt_id"] in grocery_ids and Decimal(i["line_total"]) > 0]
    if not grocery_receipts:
        raise SystemExit("No grocery receipts found")

    latest = max(date.fromisoformat(r["purchase_date"]) for r in grocery_receipts)
    earliest = min(date.fromisoformat(r["purchase_date"]) for r in grocery_receipts)
    as_of = args.as_of or date.today()
    horizon_end = as_of + timedelta(days=args.horizon_days)
    # Rates and recency are always measured against the data, which may end well
    # before as_of; due dates are then rolled forward into the forecast window.
    data_gap_days = max((as_of - latest).days, 0)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    monthly: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"spend": Decimal("0"), "trips": 0, "items": Decimal("0")}
    )
    for r in grocery_receipts:
        month = r["purchase_date"][:7]
        monthly[month]["spend"] += Decimal(r["total"])
        monthly[month]["trips"] += 1
        monthly[month]["items"] += Decimal(r["item_count_reported"] or 0)
    monthly_rows = []
    year, month_number = earliest.year, earliest.month
    while (year, month_number) <= (latest.year, latest.month):
        month = f"{year}-{month_number:02d}"
        values = monthly[month]
        trips = int(values["trips"])
        monthly_rows.append({
            "month": month,
            "spend": money(values["spend"]),
            "trips": trips,
            "items": str(values["items"]),
            "average_trip": money(values["spend"] / trips) if trips else "0.00",
            "has_receipts": "yes" if trips else "no",
        })
        year, month_number = (year + 1, 1) if month_number == 12 else (year, month_number + 1)
    write_csv(args.output_dir / "monthly_spend.csv",
              ["month", "spend", "trips", "items", "average_trip", "has_receipts"], monthly_rows)

    weekly: dict[date, dict[str, Decimal | int]] = defaultdict(
        lambda: {"spend": Decimal("0"), "trips": 0, "items": Decimal("0")}
    )
    for r in grocery_receipts:
        purchase_day = date.fromisoformat(r["purchase_date"])
        week_start = purchase_day - timedelta(days=purchase_day.weekday())
        weekly[week_start]["spend"] += Decimal(r["total"])
        weekly[week_start]["trips"] += 1
        weekly[week_start]["items"] += Decimal(r["item_count_reported"] or 0)
    first_week = earliest - timedelta(days=earliest.weekday())
    last_week = latest - timedelta(days=latest.weekday())
    weekly_rows = []
    week = first_week
    while week <= last_week:
        values = weekly[week]
        trips = int(values["trips"])
        weekly_rows.append({
            "week_start": week.isoformat(),
            "week_end": (week + timedelta(days=6)).isoformat(),
            "spend": money(values["spend"]),
            "trips": trips,
            "items": str(values["items"]),
            "average_trip": money(values["spend"] / trips) if trips else "0.00",
            "has_receipts": "yes" if trips else "no",
        })
        week += timedelta(days=7)
    write_csv(args.output_dir / "weekly_spend.csv",
              ["week_start", "week_end", "spend", "trips", "items", "average_trip",
               "has_receipts"], weekly_rows)

    receipt_dates = {r["receipt_id"]: date.fromisoformat(r["purchase_date"]) for r in grocery_receipts}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in grocery_items:
        grouped[key_for(item["description"])].append(item)

    product_rows = []
    shopping_rows = []
    expected_cost = Decimal("0")
    history_days = max((latest - earliest).days, 1)
    for product_items in grouped.values():
        by_date: dict[date, list[dict[str, str]]] = defaultdict(list)
        for item in product_items:
            by_date[receipt_dates[item["receipt_id"]]].append(item)
        dates = sorted(by_date)
        prices = [Decimal(i["line_total"]) / Decimal(i["quantity"])
                  for i in product_items if Decimal(i["quantity"]) > 0 and i["quantity_unit"] == "each"]
        if not prices:
            prices = [Decimal(i["line_total"]) for i in product_items]
        typical_price = Decimal(str(statistics.median(prices)))
        intervals = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
        typical_interval = statistics.median(intervals) if intervals else None
        description = max((i["description"] for i in product_items), key=len)
        occurrence_count = len(dates)
        recent_cutoff = latest - timedelta(days=365)
        recent_count = sum(d >= recent_cutoff for d in dates)
        rate_days = min(history_days, 365)
        expected_qty = Decimal(recent_count) * Decimal(args.horizon_days) / Decimal(max(rate_days, 1))
        expected_cost += expected_qty * typical_price

        next_due = dates[-1] + timedelta(days=round(typical_interval)) if typical_interval else None
        product_rows.append({
            "description": description,
            "purchase_dates": occurrence_count,
            "last_bought": dates[-1].isoformat(),
            "typical_interval_days": "" if typical_interval is None else round(typical_interval),
            "typical_unit_price": money(typical_price),
            "next_due": "" if next_due is None else next_due.isoformat(),
        })
        # Drop apparently discontinued products, judged against the end of the data
        # so a gap between the last receipt and as_of does not disqualify everything.
        # For active products, roll a missed cadence forward so the suggestion falls
        # in the useful forecast window.
        active = bool(typical_interval) and (latest - dates[-1]).days <= max(90, round(typical_interval * 3))
        projected_due = next_due
        if active and projected_due:
            interval_days = max(1, round(typical_interval))
            while projected_due < as_of:
                projected_due += timedelta(days=interval_days)
        if occurrence_count >= 2 and active and projected_due and projected_due <= horizon_end:
            shopping_rows.append({
                "description": description,
                "last_bought": dates[-1].isoformat(),
                "typical_interval_days": round(typical_interval),
                "estimated_due": projected_due.isoformat(),
                "days_from_forecast_start": (projected_due - as_of).days,
                "estimated_unit_cost": money(typical_price),
                "confidence": "high" if occurrence_count >= 5 else "medium" if occurrence_count >= 3 else "low",
            })

    product_rows.sort(key=lambda r: (-int(r["purchase_dates"]), r["description"]))
    shopping_rows.sort(key=lambda r: (int(r["days_from_forecast_start"]), r["description"]))
    write_csv(args.output_dir / "product_patterns.csv",
              ["description", "purchase_dates", "last_bought", "typical_interval_days",
               "typical_unit_price", "next_due"], product_rows)
    write_csv(args.output_dir / "suggested_shopping_list.csv",
              ["description", "last_bought", "typical_interval_days", "estimated_due",
               "days_from_forecast_start", "estimated_unit_cost", "confidence"], shopping_rows)

    # Category-level view: purchases grouped by the type of thing bought, which
    # recurs far more regularly than any single brand, so cadence and spend-rate
    # predictions stay usable even when specific products churn.
    category_days: dict[str, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for item in grocery_items:
        category = categorize(item["description"])
        if category in NON_FORECAST_CATEGORIES:
            continue
        category_days[category][receipt_dates[item["receipt_id"]]] += Decimal(item["line_total"])

    rate_days = Decimal(min(history_days, 365))
    window_start = latest - timedelta(days=365)
    category_rows = []
    category_forecast_total = Decimal("0")
    for category, by_day in category_days.items():
        dates = sorted(by_day)
        intervals = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
        typical_interval = statistics.median(intervals) if intervals else None
        recent = [d for d in dates if d > window_start]
        expected_spend = (sum(by_day[d] for d in recent)
                          * Decimal(args.horizon_days) / rate_days)
        active = bool(typical_interval) and (
            (latest - dates[-1]).days <= max(90, round(typical_interval * 3)))
        projected_due = None
        if active:
            interval_days = max(1, round(typical_interval))
            projected_due = dates[-1] + timedelta(days=interval_days)
            while projected_due < as_of:
                projected_due += timedelta(days=interval_days)
        if active:
            category_forecast_total += expected_spend
        category_rows.append({
            "category": category,
            "purchase_dates": len(dates),
            "last_bought": dates[-1].isoformat(),
            "typical_interval_days": "" if typical_interval is None else round(typical_interval),
            "estimated_due": projected_due.isoformat() if projected_due else "",
            "days_from_forecast_start": (projected_due - as_of).days if projected_due else "",
            "expected_spend_30d": money(expected_spend),
            "confidence": ("high" if len(dates) >= 10 else
                           "medium" if len(dates) >= 5 else "low"),
        })
    category_rows.sort(key=lambda r: -Decimal(r["expected_spend_30d"]))
    write_csv(args.output_dir / "category_forecast.csv",
              ["category", "purchase_dates", "last_bought", "typical_interval_days",
               "estimated_due", "days_from_forecast_start", "expected_spend_30d",
               "confidence"], category_rows)

    recent_start = latest - timedelta(days=90)
    recent_spend = sum(Decimal(r["total"]) for r in grocery_receipts
                       if recent_start < date.fromisoformat(r["purchase_date"]) <= latest)
    run_rate_forecast = recent_spend * Decimal(args.horizon_days) / Decimal(90)
    all_spend = sum(Decimal(r["total"]) for r in grocery_receipts)
    summary = f"""# Grocery patterns and forecast

- Data range: {earliest.isoformat()} to {latest.isoformat()}
- Grocery receipts: {len(grocery_receipts)} (BIG W receipts excluded)
- Recorded grocery spend: ${money(all_spend)}
- Average grocery trip: ${money(all_spend / len(grocery_receipts))}
- Forecast period: {as_of.isoformat()} to {horizon_end.isoformat()}
- Days without receipts before forecast: {data_gap_days}
- 90-day spending run-rate forecast: ${money(run_rate_forecast)}
- Recurring-product forecast: ${money(expected_cost)}
- Category-based forecast: ${money(category_forecast_total)}
- Suggested recurring products due: {len(shopping_rows)}

The run-rate forecast is the better overall budget estimate. The recurring-product
forecast only represents products that appeared in the receipt history and will
usually be lower because irregular and new purchases cannot be predicted reliably.
Spending rates and purchase cadences are measured over the receipt history; when
the receipts end before the forecast start, due dates are rolled forward on each
product's usual cadence, assuming shopping continued unrecorded in between.
"""
    (args.output_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(f"Wrote analysis for {len(grocery_receipts)} grocery receipts to {args.output_dir.resolve()}")
    print(f"30-day run-rate forecast: ${money(run_rate_forecast)}")
    print(f"Suggested recurring products: {len(shopping_rows)}")


if __name__ == "__main__":
    main()
