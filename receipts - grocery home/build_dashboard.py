#!/usr/bin/env python3
"""Build a self-contained grocery analysis HTML dashboard from the analysis CSVs."""

from __future__ import annotations

import csv
import html
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "analysis"
D3_PATH = ROOT / "vendor" / "d3.v7.min.js"
D3_URL = "https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def d3_source() -> str:
    """Return d3 inlined from vendor/, downloading it once if missing."""
    if not D3_PATH.exists():
        import requests
        print(f"Downloading d3 to {D3_PATH} ...")
        response = requests.get(D3_URL, timeout=60)
        response.raise_for_status()
        D3_PATH.parent.mkdir(parents=True, exist_ok=True)
        D3_PATH.write_bytes(response.content)
    return D3_PATH.read_text(encoding="utf-8")


def rows(name: str) -> list[dict[str, str]]:
    path = ANALYSIS / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def summary_values() -> dict[str, str]:
    text = (ANALYSIS / "summary.md").read_text(encoding="utf-8")
    result = {}
    for line in text.splitlines():
        match = re.match(r"- ([^:]+):\s*(.+)", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt_money(value: str | float, decimals: int = 2) -> str:
    return f"${float(value):,.{decimals}f}"


def fmt_date(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")


def fmt_month(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%B %Y")


def nice_ticks(max_value: float) -> list[int]:
    """Round tick steps so the axis lands on clean numbers with 3-5 lines."""
    for step in (50, 100, 150, 200, 250, 500, 1000):
        if max_value / step <= 4:
            break
    top = max(step, math.ceil(max_value / step) * step)
    return list(range(0, top + 1, step))


def monthly_chart(monthly: list[dict[str, str]]) -> str:
    """Render the monthly spend column chart as inline SVG plus a tooltip layer."""
    left, right, top, bottom = 46, 10, 20, 26
    plot_h = 200
    slot = max(14, min(28, 600 // max(len(monthly), 1)))
    bar_w = min(24, slot - 7)
    width = left + right + slot * len(monthly)
    height = top + plot_h + bottom
    baseline = top + plot_h

    spends = [float(r["spend"]) for r in monthly]
    ticks = nice_ticks(max(spends, default=1))
    scale_top = ticks[-1]
    max_index = spends.index(max(spends)) if spends else -1

    grid, bars, hits, labels = [], [], [], []
    for value in ticks:
        y = baseline - plot_h * value / scale_top
        if value:  # the baseline itself is drawn once, heavier
            grid.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        grid.append(f'<text class="tick" x="{left - 8}" y="{y + 3.5:.1f}" text-anchor="end">${value:,}</text>')
    grid.append(f'<line class="axis" x1="{left}" y1="{baseline}" x2="{width - right}" y2="{baseline}"/>')

    for i, row in enumerate(monthly):
        spend = float(row["spend"])
        x = left + i * slot + (slot - bar_w) / 2
        cx = left + i * slot + slot / 2
        month_date = datetime.strptime(row["month"], "%Y-%m")
        if month_date.month in (1, 4, 7, 10):
            text = month_date.strftime("Jan ’%y") if month_date.month == 1 else month_date.strftime("%b")
            labels.append(f'<text class="tick" x="{cx:.1f}" y="{baseline + 16}" text-anchor="middle">{text}</text>')
        if spend > 0:
            h = plot_h * spend / scale_top
            y = baseline - h
            r = min(4.0, h)
            bars.append(
                f'<path id="bar-{i}" class="bar" d="M{x:.1f},{baseline} L{x:.1f},{y + r:.1f} '
                f'Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} L{x + bar_w - r:.1f},{y:.1f} '
                f'Q{x + bar_w:.1f},{y:.1f} {x + bar_w:.1f},{y + r:.1f} L{x + bar_w:.1f},{baseline} Z"/>'
            )
            if i == max_index:
                labels.append(f'<text class="peak" x="{cx:.1f}" y="{y - 6:.1f}" '
                              f'text-anchor="middle">${spend:,.0f}</text>')
            trips = int(row["trips"])
            detail = f"{trips} trip{'s' if trips != 1 else ''} · avg {fmt_money(row['average_trip'])}"
            value_text = fmt_money(spend)
        else:
            detail, value_text = "", "No receipts"
        hits.append(
            f'<rect class="hit" x="{left + i * slot:.1f}" y="{top}" width="{slot}" height="{plot_h}" '
            f'tabindex="0" data-bar="bar-{i}" data-label="{esc(fmt_month(row["month"]))}" '
            f'data-value="{esc(value_text)}" data-detail="{esc(detail)}" '
            f'aria-label="{esc(fmt_month(row["month"]))}: {esc(value_text)}"/>'
        )

    table_rows = "".join(
        f"<tr><td>{esc(fmt_month(r['month']))}</td><td class='num'>{fmt_money(r['spend'])}</td>"
        f"<td class='num'>{esc(r['trips'])}</td><td class='num'>{fmt_money(r['average_trip'])}</td></tr>"
        for r in monthly
    )
    return f'''<div class="chart-box" id="chartbox">
      <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"
           aria-label="Monthly grocery spend, {esc(fmt_month(monthly[0]['month']))} to {esc(fmt_month(monthly[-1]['month']))}">
        {''.join(grid)}
        {''.join(bars)}
        {''.join(labels)}
        {''.join(hits)}
      </svg>
      <div class="tooltip" id="charttip" hidden>
        <div class="t-value"></div><div class="t-label"></div><div class="t-detail"></div>
      </div>
    </div>
    <details class="table-view"><summary>View as table</summary>
      <div class="table-wrap"><table><thead><tr><th>Month</th><th class="num">Spend</th>
      <th class="num">Trips</th><th class="num">Average trip</th></tr></thead>
      <tbody>{table_rows}</tbody></table></div>
    </details>'''


def confidence_badge(level: str) -> str:
    return f'<span class="badge {esc(level)}"><span class="dot"></span>{esc(level)}</span>'


def price_cell(row: dict[str, str], live: dict[str, dict[str, str]]) -> str:
    match = live.get(row["description"])
    if not match or not match.get("price") or float(match.get("match_score") or 0) < 0.6:
        return '<td class="num" data-value="-1">—</td>'
    extras = []
    if match.get("on_special") == "yes":
        extras.append('<span class="badge special">special</span>')
    delta = match.get("price_vs_paid", "")
    if delta and float(delta):
        klass = "delta-up" if float(delta) > 0 else "delta-down"
        extras.append(f'<span class="{klass}">{esc(delta)}</span>')
    extra_html = (" " + " ".join(extras)) if extras else ""
    return (f'<td class="num" data-value="{esc(match["price"])}" title="{esc(match["matched_name"])}">'
            f'{fmt_money(match["price"])}{extra_html}</td>')


def shopping_table(shopping: list[dict[str, str]], live: dict[str, dict[str, str]]) -> str:
    body = []
    for row in shopping:
        days = int(row["days_from_forecast_start"])
        due_in = "due now" if days <= 0 else f"in {days} day{'s' if days != 1 else ''}"
        body.append(f'''<tr data-search="{esc(row['description'].lower())}">
          <td><strong>{esc(row['description'])}</strong></td>
          <td data-value="{days}">{esc(fmt_date(row['estimated_due']))} <span class="muted">({due_in})</span></td>
          <td class="num" data-value="{esc(row['typical_interval_days'])}">{esc(row['typical_interval_days'])} days</td>
          <td class="num" data-value="{esc(row['estimated_unit_cost'])}">{fmt_money(row['estimated_unit_cost'])}</td>
          {price_cell(row, live)}
          <td data-value="{CONFIDENCE_RANK.get(row['confidence'], 0)}">{confidence_badge(row['confidence'])}</td>
        </tr>''')
    return "".join(body)


def calendar_section(shopping: list[dict[str, str]], categories: list[dict[str, str]],
                     as_of: date, horizon_end: date) -> str:
    """A Monday-aligned month grid of the forecast window with due items as chips."""
    chips_by_day: dict[date, list[str]] = {}
    cost_by_day: dict[date, float] = {}
    for row in shopping:
        due = date.fromisoformat(row["estimated_due"])
        title = f"{row['description']} · est {fmt_money(row['estimated_unit_cost'])}"
        chips_by_day.setdefault(due, []).append(
            f'<span class="chip" data-kind="product" data-full="{esc(row["description"])}" '
            f'data-cost="{esc(row["estimated_unit_cost"])}" title="{esc(title)}">'
            f'{esc(row["description"])}</span>')
        cost_by_day[due] = cost_by_day.get(due, 0) + float(row["estimated_unit_cost"])
    for row in categories:
        if not row["estimated_due"]:
            continue
        due = date.fromisoformat(row["estimated_due"])
        title = (f"{row['category']} (category) · expected "
                 f"{fmt_money(row['expected_spend_30d'])}/30d")
        chips_by_day.setdefault(due, []).append(
            f'<span class="chip cat" data-kind="cat" data-full="{esc(row["category"])}" '
            f'title="{esc(title)}">{esc(row["category"])}</span>')

    start = as_of - timedelta(days=as_of.weekday())
    end = horizon_end + timedelta(days=6 - horizon_end.weekday())
    cells = [f'<div class="cal-dow">{dow}</div>'
             for dow in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")]
    day = start
    while day <= end:
        classes = "cal-cell"
        if not as_of <= day <= horizon_end:
            classes += " dim"
        if day == as_of:
            classes += " today"
        date_label = (day.strftime("%d %b").lstrip("0")
                      if day.day == 1 or day == start else str(day.day))
        chips = chips_by_day.get(day, [])
        # Every chip is rendered so the day panel can list them; past three they
        # are hidden in the grid behind a "+N more" marker.
        shown = "".join(chip if i < 3 else chip.replace('class="chip', 'class="chip overflow', 1)
                        for i, chip in enumerate(chips))
        if len(chips) > 3:
            shown += f'<span class="chip more">+{len(chips) - 3} more</span>'
        cost = cost_by_day.get(day)
        footer = f'<div class="cal-cost">{fmt_money(cost)}</div>' if cost else ""
        cells.append(f'<div class="{classes}" data-date="{day.isoformat()}" tabindex="0" '
                     f'role="button" aria-label="{esc(fmt_date(day.isoformat()))}, '
                     f'{len(chips)} item{"s" if len(chips) != 1 else ""} due">'
                     f'<div class="cal-date">{esc(date_label)}</div>{shown}{footer}</div>')
        day += timedelta(days=1)
    return f'''<section class="panel wide">
      <h2>Shopping calendar</h2>
      <p class="sub">Estimated due dates over the 30-day forecast window ({esc(fmt_date(as_of.isoformat()))}
        – {esc(fmt_date(horizon_end.isoformat()))}). Solid chips are products, dashed chips are category
        types; a day's figure is its products' combined cost. Click a day to see everything due and tick
        items off as you buy them — ticks are remembered on this device.</p>
      <div class="cal-wrap"><div class="cal">{''.join(cells)}</div></div>
      <div class="cal-detail" id="caldetail" hidden></div>
    </section>'''


def category_table(categories: list[dict[str, str]]) -> str:
    body = []
    for row in categories:
        if row["estimated_due"]:
            days = int(row["days_from_forecast_start"])
            due_in = "due now" if days <= 0 else f"in {days} day{'s' if days != 1 else ''}"
            due = f'{esc(fmt_date(row["estimated_due"]))} <span class="muted">({due_in})</span>'
            due_sort = days
        else:
            due = '<span class="muted">lapsed</span>'
            due_sort = 9999
        interval = row["typical_interval_days"]
        body.append(f'''<tr data-search="{esc(row['category'].lower())}">
          <td><strong>{esc(row['category'])}</strong></td>
          <td class="num" data-value="{esc(row['expected_spend_30d'])}">{fmt_money(row['expected_spend_30d'])}</td>
          <td data-value="{due_sort}">{due}</td>
          <td class="num" data-value="{esc(interval) or 0}">{esc(interval) + ' days' if interval else '—'}</td>
          <td data-value="{esc(row['last_bought'])}">{esc(fmt_date(row['last_bought']))}</td>
          <td class="num" data-value="{esc(row['purchase_dates'])}">{esc(row['purchase_dates'])}</td>
          <td data-value="{CONFIDENCE_RANK.get(row['confidence'], 0)}">{confidence_badge(row['confidence'])}</td>
        </tr>''')
    return "".join(body)


def product_table(products: list[dict[str, str]]) -> str:
    body = []
    for row in products:
        interval = row["typical_interval_days"]
        body.append(f'''<tr data-search="{esc(row['description'].lower())}">
          <td>{esc(row['description'])}</td>
          <td class="num" data-value="{esc(row['purchase_dates'])}">{esc(row['purchase_dates'])}</td>
          <td data-value="{esc(row['last_bought'])}">{esc(fmt_date(row['last_bought']))}</td>
          <td class="num" data-value="{esc(interval) or 0}">{esc(interval) + ' days' if interval else '—'}</td>
          <td class="num" data-value="{esc(row['typical_unit_price'])}">{fmt_money(row['typical_unit_price'])}</td>
        </tr>''')
    return "".join(body)


def rules_table(rules: list[dict[str, str]]) -> str:
    body = []
    for row in rules:
        search = esc((row["if_bought"] + " " + row["then_also_bought"]).lower())
        body.append(f'''<tr data-search="{search}">
          <td>{esc(row['if_bought'])}</td>
          <td class="arrow">→</td>
          <td>{esc(row['then_also_bought'])}</td>
          <td class="num" data-value="{esc(row['confidence'])}">{float(row['confidence']):.0%}</td>
          <td class="num" data-value="{esc(row['lift'])}">{esc(row['lift'])}×</td>
          <td class="num" data-value="{esc(row['together_count'])}">{esc(row['together_count'])}</td>
        </tr>''')
    return "".join(body)


def weekly_table(weekly: list[dict[str, str]]) -> str:
    body = []
    for row in reversed(weekly):
        empty = ' class="empty-week"' if row["has_receipts"] == "no" else ""
        body.append(f'''<tr{empty}>
          <td data-value="{esc(row['week_start'])}">{esc(fmt_date(row['week_start']))} – {esc(fmt_date(row['week_end']))}</td>
          <td class="num" data-value="{esc(row['spend'])}"><strong>{fmt_money(row['spend'])}</strong></td>
          <td class="num" data-value="{esc(row['trips'])}">{esc(row['trips'])}</td>
          <td class="num" data-value="{esc(row['items'])}">{esc(row['items'])}</td>
          <td class="num" data-value="{esc(row['average_trip'])}">{fmt_money(row['average_trip'])}</td>
        </tr>''')
    return "".join(body)


def numerical_section(summary: dict, model_metrics: list[dict[str, str]],
                      forecasts: list[dict[str, str]], clusters: list[dict[str, str]],
                      correlations: list[dict[str, str]], anomalies: list[dict[str, str]],
                      price_trends: list[dict[str, str]], tree_rules: list[dict[str, str]]) -> str:
    """Render the experimental numerical-model suite with its caveats visible."""
    if not summary or not model_metrics:
        return ""
    best = model_metrics[0]
    improvement = float(summary.get("best_model_improvement_over_baseline", 0))
    best_wape = float(best["wape"])
    best_r2 = float(best["r_squared"])
    reliability = ("No reliable forecast yet" if best_wape >= .8 or best_r2 <= 0 else
                   "Small predictive advantage" if improvement < 5 else "Useful predictive advantage")
    r2_note = ("All holdout RÂ² values are below zero, so none beats a simple mean convincingly yet."
               if max(float(row["r_squared"]) for row in model_metrics) < 0 else
               "At least one model has positive holdout RÂ², but continued validation is still needed.")
    trend = float(summary.get("linear_annual_change", 0))
    sign = "+" if trend >= 0 else "âˆ’"
    metric_rows = "".join(
        f'''<tr><td>{esc(row['model'])}</td><td class="num">{fmt_money(row['mae'])}</td>
        <td class="num">{fmt_money(row['rmse'])}</td><td class="num">{float(row['wape']):.0%}</td>
        <td class="num">{float(row['r_squared']):.2f}</td></tr>'''
        for row in model_metrics)
    forecast_rows = "".join(
        f'''<tr><td>{esc(fmt_date(row['week_start']))}</td>
        <td class="num">{fmt_money(row['ensemble'])}</td>
        <td class="num">{fmt_money(row['linear_regression'])}</td>
        <td class="num">{fmt_money(row['holt_winters'])}</td>
        <td class="num">{fmt_money(row['decision_tree'])}</td>
        <td class="num">{fmt_money(row['gradient_boosting'])}</td></tr>'''
        for row in forecasts)
    cluster_rows = "".join(
        f'''<tr><td>{esc(row['week_type'])}</td><td class="num">{esc(row['weeks'])}</td>
        <td class="num">{fmt_money(row['average_spend'])}</td>
        <td class="num">{esc(row['average_trips'])}</td><td class="num">{esc(row['average_items'])}</td></tr>'''
        for row in clusters)
    correlation_rows = "".join(
        f'''<tr><td>{esc(row['variable'])}</td><td class="num">{esc(row['correlation_with_spend'])}</td>
        <td>{esc(row['strength'])}</td></tr>''' for row in correlations)
    anomaly_rows = "".join(
        f'''<tr><td>{esc(fmt_date(row['week_start']))}</td><td class="num">{fmt_money(row['spend'])}</td>
        <td class="num">{esc(row['items'])}</td><td class="num">{esc(row['isolation_score'])}</td>
        <td>{esc(row['flagged'])}</td><td>{esc(row['reason'])}</td></tr>''' for row in anomalies)
    price_rows = "".join(
        f'''<tr><td>{esc(row['description'])}</td><td class="num">{esc(row['observations'])}</td>
        <td class="num">{fmt_money(row['first_price'])}</td><td class="num">{fmt_money(row['last_paid'])}</td>
        <td class="num">{float(row['first_to_last_pct']):+.1f}%</td>
        <td class="num">{fmt_money(row['linear_change_per_year']) + '/yr' if row['linear_change_per_year'] else 'â€”'}</td></tr>'''
        for row in price_trends[:25])
    rule_rows = "".join(
        f'''<tr><td>{esc(row['rule'])}</td><td class="num">{fmt_money(row['predicted_weekly_spend'])}</td></tr>'''
        for row in tree_rules)
    return f'''
    <section class="panel wide">
      <h2>Numerical pattern lab</h2>
      <p class="sub">Linear regression, seasonal time series, decision trees, gradient boosting,
        K-means clustering, correlations, Isolation Forest anomalies, price trends, and basic sequence tests.
        Models were evaluated on the final {esc(best['validation_weeks'])} weeks, never on their training weeks.</p>
      <div class="cards model-cards">
        <div class="card"><small>Best holdout model</small><b class="model-name">{esc(best['model'])}</b>
          <div class="note">MAE {fmt_money(best['mae'])} per week</div></div>
        <div class="card"><small>4-week ensemble</small><b>{fmt_money(summary['next_4_week_ensemble_total'])}</b>
          <div class="note">forecast after the last receipt week</div></div>
        <div class="card"><small>Linear trend</small><b>{sign}{fmt_money(abs(trend))}</b>
          <div class="note">change per year</div></div>
        <div class="card"><small>Model verdict</small><b class="model-name">{esc(reliability)}</b>
          <div class="note">best model improves MAE by only {fmt_money(improvement)}</div></div>
      </div>
      <p class="gap-note"><strong>Coverage warning:</strong> {esc(summary['coverage_warning'])}
        {r2_note} Treat the forecasts
        as experimental ranges, not a shopping budget.</p>

      <h3>12-week recorded-spend forecast</h3>
      <p class="sub">The ensemble is the median of the four fitted algorithms, which reduces any one model's extremes.</p>
      <div class="table-wrap"><table><thead><tr><th>Week starting</th><th class="num">Ensemble</th>
        <th class="num">Linear</th><th class="num">Holt-Winters</th><th class="num">Decision tree</th>
        <th class="num">Boosted trees</th></tr></thead><tbody>{forecast_rows}</tbody></table></div>

      <details class="table-view"><summary>Model holdout scores and decision-tree rules</summary>
        <p class="sub" style="margin-top:8px">Lower MAE/RMSE/WAPE is better; RÂ² above zero is desirable.
        WAPE is used instead of MAPE because many weeks are zero.</p>
        <div class="table-wrap"><table><thead><tr><th>Model</th><th class="num">MAE</th><th class="num">RMSE</th>
        <th class="num">WAPE</th><th class="num">RÂ²</th></tr></thead><tbody>{metric_rows}</tbody></table></div>
        <h3>Decision-tree rules</h3><div class="table-wrap"><table><thead><tr><th>Lag/calendar rule</th>
        <th class="num">Predicted spend</th></tr></thead><tbody>{rule_rows}</tbody></table></div>
      </details>

      <div class="grid">
        <div><h3>K-means week types</h3><p class="sub">Descriptive clusters, not forecasts.</p>
          <div class="table-wrap"><table><thead><tr><th>Week type</th><th class="num">Weeks</th>
          <th class="num">Avg spend</th><th class="num">Avg trips</th><th class="num">Avg items</th></tr></thead>
          <tbody>{cluster_rows}</tbody></table></div></div>
        <div><h3>Numeric relationships</h3><p class="sub">Correlation describes association, not causation.</p>
          <div class="table-wrap"><table><thead><tr><th>Variable</th><th class="num">Correlation</th><th>Strength</th></tr></thead>
          <tbody>{correlation_rows}</tbody></table></div></div>
      </div>

      <details class="table-view"><summary>Isolation Forest: unusual shopping weeks</summary>
        <p class="sub" style="margin-top:8px">Flags unusual combinations of spend, trips, items, basket size, and time since the prior shop. A stock-up week is not necessarily an error.</p>
        <div class="table-wrap"><table><thead><tr><th>Week</th><th class="num">Spend</th><th class="num">Items</th>
        <th class="num">Score</th><th>Status</th><th>Reason</th></tr></thead><tbody>{anomaly_rows}</tbody></table></div>
      </details>
      <details class="table-view"><summary>Linear price-change patterns</summary>
        <p class="sub" style="margin-top:8px">First-versus-last paid price; yearly trend is only shown for products with at least five purchase dates.</p>
        <div class="table-wrap"><table><thead><tr><th>Product</th><th class="num">Observations</th><th class="num">First</th>
        <th class="num">Last paid</th><th class="num">Change</th><th class="num">Linear trend</th></tr></thead><tbody>{price_rows}</tbody></table></div>
      </details>
      <p class="sub"><strong>Basic arithmetic test:</strong> {esc(summary['sequence_note'])}</p>
    </section>'''


CSS = """
    :root { color-scheme: light dark; }
    .page {
      --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
      --muted: #898781; --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,.10);
      --series: #2a78d6; --series-hover: #3987e5;
      --good-bg: #e3f2e3; --good-ink: #006300; --good-dot: #0ca30c;
      --warn-bg: #fdf0d0; --warn-ink: #7a5200; --warn-dot: #fab219;
      --low-bg: #fbe5dc; --low-ink: #8c3416; --low-dot: #ec835a;
      --cat0: #2a78d6; --cat1: #008300; --cat2: #e87ba4; --cat3: #eda100;
      --cat4: #1baf7a; --cat5: #eb6834; --cat6: #4a3aa7; --cat7: #e34948;
    }
    @media (prefers-color-scheme: dark) {
      .page {
        --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
        --muted: #898781; --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,.10);
        --series: #3987e5; --series-hover: #5598e7;
        --good-bg: rgba(12,163,12,.16); --good-ink: #6fd06f; --good-dot: #0ca30c;
        --warn-bg: rgba(250,178,25,.14); --warn-ink: #e8c15e; --warn-dot: #fab219;
        --low-bg: rgba(236,131,90,.14); --low-ink: #f0a181; --low-dot: #ec835a;
        --cat0: #3987e5; --cat1: #008300; --cat2: #d55181; --cat3: #c98500;
        --cat4: #199e70; --cat5: #d95926; --cat6: #9085e9; --cat7: #e66767;
      }
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    .page {
      background: var(--page); color: var(--ink); min-height: 100vh;
      font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    main { max-width: 1140px; margin: auto; padding: 32px 24px 56px; }
    .head h1 { margin: 0; font-size: 26px; font-weight: 650; letter-spacing: -.02em; }
    .head p { margin: 6px 0 0; color: var(--ink-2); }
    .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 22px; }
    .card, .panel {
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    }
    .card { padding: 16px 18px; }
    .card small {
      color: var(--ink-2); font-size: 12px; display: block;
    }
    .card b { display: block; font-size: 26px; font-weight: 650; margin-top: 4px; letter-spacing: -.01em; }
    .card b.model-name { font-size: 17px; line-height: 1.25; min-height: 42px; }
    .model-cards { margin: 14px 0; }
    .card .note { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .grid { display: grid; grid-template-columns: 1.9fr 1fr; gap: 14px; margin-top: 14px; }
    .panel { padding: 20px 22px; min-width: 0; }
    .panel.wide { margin-top: 14px; }
    h2 { margin: 0; font-size: 16px; font-weight: 650; }
    h3 { margin: 22px 0 4px; font-size: 14px; font-weight: 650; }
    .sub { color: var(--ink-2); margin: 3px 0 14px; font-size: 13px; }
    .chart-box { position: relative; overflow-x: auto; }
    svg { display: block; }
    svg .grid { stroke: var(--grid); stroke-width: 1; }
    svg .axis { stroke: var(--axis); stroke-width: 1; }
    svg .tick { fill: var(--muted); font-size: 10.5px; font-variant-numeric: tabular-nums; }
    svg .peak { fill: var(--ink); font-size: 11px; font-weight: 600; }
    svg .bar { fill: var(--series); }
    svg .bar.lift { fill: var(--series-hover); }
    svg .hit { fill: transparent; cursor: default; outline-offset: -2px; }
    svg .hit:focus-visible { outline: 2px solid var(--series); }
    .tooltip {
      position: absolute; pointer-events: none; background: var(--surface);
      border: 1px solid var(--border); border-radius: 8px; padding: 8px 11px;
      box-shadow: 0 4px 16px rgba(0,0,0,.14); min-width: 130px; z-index: 3;
    }
    .tooltip .t-value { font-size: 15px; font-weight: 650; }
    .tooltip .t-label { color: var(--ink-2); font-size: 12px; }
    .tooltip .t-detail { color: var(--muted); font-size: 12px; }
    .table-view { margin-top: 10px; }
    .table-view summary { color: var(--ink-2); font-size: 13px; cursor: pointer; }
    table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
    th, td { padding: 9px 10px; border-bottom: 1px solid var(--grid); text-align: left; }
    th {
      color: var(--ink-2); font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em;
      position: sticky; top: 0; background: var(--surface); cursor: pointer; user-select: none;
      white-space: nowrap;
    }
    th.num, td.num { text-align: right; }
    td.num { font-variant-numeric: tabular-nums; }
    th[aria-sort="ascending"]::after { content: " \\2191"; }
    th[aria-sort="descending"]::after { content: " \\2193"; }
    tbody tr:hover { background: color-mix(in srgb, var(--series) 6%, transparent); }
    td .muted { color: var(--muted); }
    td.arrow { color: var(--muted); }
    .table-wrap { overflow: auto; max-height: 480px; border-top: 1px solid var(--grid); }
    input[type="search"] {
      width: 100%; max-width: 340px; padding: 8px 12px; margin: 0 0 12px;
      border: 1px solid var(--border); border-radius: 8px;
      background: var(--page); color: var(--ink); font: inherit;
    }
    input[type="search"]:focus { outline: 2px solid var(--series); border-color: transparent; }
    .badge {
      display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px 2px 8px;
      border-radius: 99px; font-size: 12px; font-weight: 550;
    }
    .badge .dot { width: 7px; height: 7px; border-radius: 50%; }
    .badge.high { background: var(--good-bg); color: var(--good-ink); }
    .badge.high .dot { background: var(--good-dot); }
    .badge.medium { background: var(--warn-bg); color: var(--warn-ink); }
    .badge.medium .dot { background: var(--warn-dot); }
    .badge.low { background: var(--low-bg); color: var(--low-ink); }
    .badge.low .dot { background: var(--low-dot); }
    .empty-week td { color: var(--muted); }
    .hero { font-size: 48px; font-weight: 650; letter-spacing: -.02em; margin: 10px 0 2px; }
    .fc-row { display: flex; justify-content: space-between; gap: 10px; padding: 9px 0;
      border-top: 1px solid var(--grid); font-size: 13px; }
    .fc-row:first-of-type { margin-top: 14px; }
    .fc-row b { font-variant-numeric: tabular-nums; font-weight: 600; }
    .fc-row span { color: var(--ink-2); }
    .gap-note { background: var(--warn-bg); color: var(--warn-ink); border-radius: 8px;
      padding: 10px 12px; font-size: 12.5px; margin: 12px 0 0; }
    .badge.special { background: var(--good-bg); color: var(--good-ink); padding: 2px 8px; }
    .delta-up { color: var(--low-ink); font-size: 12px; }
    .delta-down { color: var(--good-ink); font-size: 12px; }
    .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .chart-card { margin: 0; background: #fcfcfb; border: 1px solid var(--border);
      border-radius: 10px; padding: 12px; }
    .chart-card.span2 { grid-column: span 2; }
    .chart-card img { width: 100%; height: auto; display: block; }
    .chart-card figcaption { color: var(--ink-2); font-size: 12.5px; padding: 8px 4px 0; }
    code { background: color-mix(in srgb, var(--ink) 7%, transparent);
      padding: 1px 5px; border-radius: 4px; font-size: 12px; }
    .net-box { position: relative; }
    #netsvg { width: 100%; height: auto; display: block; }
    .net-link { stroke: var(--axis); stroke-opacity: .45; }
    .net-node { stroke: var(--surface); stroke-width: 2; cursor: grab; }
    .net-node:active { cursor: grabbing; }
    .net-label { font-size: 10.5px; fill: var(--ink-2); pointer-events: none;
      paint-order: stroke; stroke: var(--surface); stroke-width: 3px; stroke-linejoin: round; }
    #netsvg.dimmed .net-node:not(.hi) { opacity: .15; }
    #netsvg.dimmed .net-link { stroke-opacity: .06; }
    #netsvg.dimmed .net-link.hi { stroke-opacity: .85; stroke: var(--ink-2); }
    #netsvg.dimmed .net-label:not(.hi) { opacity: .12; }
    .cat-0 { fill: var(--cat0); background: var(--cat0); } .cat-1 { fill: var(--cat1); background: var(--cat1); }
    .cat-2 { fill: var(--cat2); background: var(--cat2); } .cat-3 { fill: var(--cat3); background: var(--cat3); }
    .cat-4 { fill: var(--cat4); background: var(--cat4); } .cat-5 { fill: var(--cat5); background: var(--cat5); }
    .cat-6 { fill: var(--cat6); background: var(--cat6); } .cat-7 { fill: var(--cat7); background: var(--cat7); }
    .cat-x { fill: var(--muted); background: var(--muted); }
    .net-legend { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 10px; }
    .net-legend[hidden] { display: none; }
    .legend-item { display: inline-flex; align-items: center; gap: 7px;
      font-size: 12.5px; color: var(--ink-2); }
    .ldot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: none; }
    .net-toggle { display: inline-flex; border: 1px solid var(--border); border-radius: 10px;
      overflow: hidden; margin-bottom: 12px; }
    .net-toggle input { position: absolute; opacity: 0; pointer-events: none; }
    .net-toggle span { display: inline-block; padding: 7px 16px; font-size: 13px;
      color: var(--ink-2); cursor: pointer; user-select: none; }
    .net-toggle input:checked + span { background: var(--series); color: #fff; }
    .net-toggle input:focus-visible + span { outline: 2px solid var(--series); outline-offset: -2px; }
    .cal-wrap { overflow-x: auto; }
    .cal { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; min-width: 720px; }
    .cal-dow { color: var(--muted); font-size: 11px; text-transform: uppercase;
      letter-spacing: .05em; padding: 0 4px 2px; }
    .cal-cell { border: 1px solid var(--grid); border-radius: 8px; min-height: 96px;
      padding: 6px; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
    .cal-cell.dim { opacity: .4; }
    .cal-cell.today { border-color: var(--series); box-shadow: inset 0 0 0 1px var(--series); }
    .cal-date { font-size: 11.5px; color: var(--ink-2); font-weight: 600; }
    .cal-cell.today .cal-date::after { content: " · today"; color: var(--series); }
    .chip { display: block; font-size: 11px; line-height: 1.4; padding: 1px 6px; border-radius: 5px;
      background: color-mix(in srgb, var(--series) 13%, transparent); color: var(--ink-2);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .chip.cat { background: transparent; border: 1px dashed var(--axis); }
    .chip.more { background: transparent; color: var(--muted); }
    .cal-cost { margin-top: auto; font-size: 11px; color: var(--muted);
      font-variant-numeric: tabular-nums; }
    .cal-cell { cursor: pointer; }
    .cal-cell:focus-visible { outline: 2px solid var(--series); }
    .cal-cell.selected { background: color-mix(in srgb, var(--series) 8%, transparent); }
    .chip.overflow { display: none; }
    .chip.done { text-decoration: line-through; opacity: .5; }
    .cal-detail { margin-top: 14px; border-top: 1px solid var(--grid); padding-top: 4px; }
    .cal-detail h3 { font-size: 14px; font-weight: 650; margin: 10px 0 4px; }
    .cal-empty { color: var(--muted); font-size: 13px; }
    .cal-item { display: flex; align-items: center; gap: 10px; padding: 8px 2px;
      border-bottom: 1px solid var(--grid); font-size: 13.5px; cursor: pointer; }
    .cal-item input { accent-color: var(--series); width: 15px; height: 15px; flex: none; }
    .cal-item.done span { text-decoration: line-through; color: var(--muted); }
    .cal-item em { font-style: normal; font-size: 11px; color: var(--muted);
      border: 1px dashed var(--axis); border-radius: 99px; padding: 0 8px; flex: none; }
    .cal-item b { margin-left: auto; font-weight: 600; font-variant-numeric: tabular-nums; }
    .cal-item.cal-sum { border-bottom: 0; color: var(--ink-2); cursor: default; }
    @media (max-width: 860px) { .charts-grid { grid-template-columns: 1fr; }
      .chart-card.span2 { grid-column: auto; } }
    footer { text-align: center; color: var(--muted); padding: 26px 0 0; font-size: 12.5px; }
    @media (max-width: 860px) { .cards { grid-template-columns: 1fr 1fr; } .grid { grid-template-columns: 1fr; } }
    @media (max-width: 480px) { .cards { grid-template-columns: 1fr; } }
"""

JS = """
    document.querySelectorAll('input[type="search"]').forEach(input => {
      const table = document.getElementById(input.dataset.target);
      input.addEventListener('input', () => {
        const q = input.value.toLowerCase();
        table.querySelectorAll('tbody tr').forEach(r => r.hidden = !(r.dataset.search || '').includes(q));
      });
    });

    document.querySelectorAll('table.sortable thead th').forEach((th, idx) => {
      th.addEventListener('click', () => {
        const table = th.closest('table');
        const dir = th.getAttribute('aria-sort') === 'descending' ? 1 : -1;
        table.querySelectorAll('thead th').forEach(h => h.removeAttribute('aria-sort'));
        th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
        const numeric = th.classList.contains('num') || th.dataset.sort === 'num';
        const tbody = table.tBodies[0];
        Array.from(tbody.rows).sort((a, b) => {
          const av = a.cells[idx].dataset.value ?? a.cells[idx].textContent.trim();
          const bv = b.cells[idx].dataset.value ?? b.cells[idx].textContent.trim();
          if (numeric) return dir * (parseFloat(av) - parseFloat(bv));
          return dir * av.localeCompare(bv);
        }).forEach(r => tbody.appendChild(r));
      });
    });

    const netsvg = document.getElementById('netsvg');
    if (netsvg && window.NETWORK && window.d3) {
      const W = 960, H = 540;
      const netbox = document.getElementById('netbox');
      const nettip = document.getElementById('nettip');
      const svg = d3.select(netsvg);
      let simulation = null;
      let tipNode = null;

      function hideTip() {
        tipNode = null;
        nettip.hidden = true;
        netsvg.classList.remove('dimmed');
        netsvg.querySelectorAll('.hi').forEach(el => el.classList.remove('hi'));
      }

      function placeTip(el) {
        const target = el.getBoundingClientRect();
        const frame = netbox.getBoundingClientRect();
        let x = target.left - frame.left + target.width / 2 - nettip.offsetWidth / 2;
        x = Math.max(4, Math.min(x, frame.width - nettip.offsetWidth - 4));
        nettip.style.left = x + 'px';
        nettip.style.top = Math.max(2, target.top - frame.top - nettip.offsetHeight - 8) + 'px';
      }

      function render(mode) {
        hideTip();
        if (simulation) simulation.stop();
        svg.selectAll('*').remove();
        const data = NETWORK[mode];
        const basketTotal = data.baskets || NETWORK.baskets;
        const maxCount = Math.max(...data.nodes.map(d => d.count), 1);
        const nodes = data.nodes.map(d => ({...d, r: 5 + 14 * Math.sqrt(d.count / maxCount)}));
        const links = data.edges.map(e => ({source: e.s, target: e.t, count: e.count, lift: e.lift}));

        // The Observable force-directed-graph recipe: link + many-body + centering
        // forces, with a collide radius so labels stay readable.
        simulation = d3.forceSimulation(nodes)
          .force('link', d3.forceLink(links).id(d => d.id)
            .distance(l => 50 + l.source.r + l.target.r + 40 / l.lift))
          .force('charge', d3.forceManyBody().strength(-220))
          .force('center', d3.forceCenter(W / 2, H / 2))
          .force('collide', d3.forceCollide().radius(d => d.r + 8))
          .force('x', d3.forceX(W / 2).strength(0.05))
          .force('y', d3.forceY(H / 2).strength(0.09));

        const partners = {};
        links.forEach(l => {
          (partners[l.source.id] = partners[l.source.id] || []).push({node: l.target, lift: l.lift});
          (partners[l.target.id] = partners[l.target.id] || []).push({node: l.source, lift: l.lift});
        });

        const link = svg.append('g').selectAll('line').data(links).join('line')
          .attr('class', 'net-link')
          .attr('stroke-width', l => Math.min(4.5, 0.6 + l.lift * 0.35));
        const node = svg.append('g').selectAll('circle').data(nodes).join('circle')
          .attr('class', d => 'net-node cat-' + (d.community < 0 ? 'x' : d.community % 8))
          .attr('r', d => d.r)
          .attr('tabindex', 0)
          .attr('aria-label', d => d.label + ', in ' + d.count + ' baskets');
        const labelled = new Set(nodes.slice().sort((a, b) => b.count - a.count)
          .slice(0, mode === 'products' ? 12 : 16).map(d => d.id));
        const label = svg.append('g').selectAll('text')
          .data(nodes.filter(d => labelled.has(d.id))).join('text')
          .attr('class', 'net-label')
          .attr('text-anchor', 'middle')
          .text(d => d.label.length > 26 ? d.label.slice(0, 25) + '…' : d.label);

        function showTip(d, el) {
          hideTip();
          tipNode = {d, el};
          nettip.querySelector('.t-value').textContent = d.label;
          nettip.querySelector('.t-label').textContent = 'In ' + d.count.toLocaleString() + ' of ' + basketTotal.toLocaleString() + ' baskets';
          const best = (partners[d.id] || []).sort((x, y) => y.lift - x.lift).slice(0, 3)
            .map(p => p.node.label + ' (' + p.lift.toFixed(1) + '×)').join(', ');
          nettip.querySelector('.t-detail').textContent = best ? 'Often with: ' + best : '';
          nettip.hidden = false;
          placeTip(el);
          netsvg.classList.add('dimmed');
          const near = new Set([d.id]);
          link.classed('hi', l => {
            const touches = l.source === d || l.target === d;
            if (touches) { near.add(l.source.id); near.add(l.target.id); }
            return touches;
          });
          node.classed('hi', n => near.has(n.id));
          label.classed('hi', n => near.has(n.id));
        }

        node
          .on('pointerenter', (event, d) => { if (!event.buttons) showTip(d, event.currentTarget); })
          .on('focus', (event, d) => showTip(d, event.currentTarget))
          .on('pointerleave', hideTip)
          .on('blur', hideTip)
          .call(d3.drag()
            .on('start', (event, d) => {
              if (!event.active) simulation.alphaTarget(0.3).restart();
              d.fx = d.x; d.fy = d.y;
              hideTip();
            })
            .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
            .on('end', (event, d) => {
              if (!event.active) simulation.alphaTarget(0);
              d.fx = null; d.fy = null;
            }));
        if (mode === 'products') {
          node.on('click', (event, d) => {
            const input = document.querySelector('input[data-target="rules"]');
            if (!input) return;
            input.value = input.value === d.label ? '' : d.label;
            input.dispatchEvent(new Event('input'));
          });
        }

        simulation.on('tick', () => {
          nodes.forEach(d => {
            d.x = Math.max(d.r + 4, Math.min(W - d.r - 4, d.x));
            d.y = Math.max(d.r + 4, Math.min(H - d.r - 4, d.y));
          });
          link
            .attr('x1', l => l.source.x).attr('y1', l => l.source.y)
            .attr('x2', l => l.target.x).attr('y2', l => l.target.y);
          node.attr('cx', d => d.x).attr('cy', d => d.y);
          label.attr('x', d => d.x).attr('y', d => d.y + d.r + 12);
          if (tipNode) placeTip(tipNode.el);
        });

        document.querySelectorAll('.net-legend[data-mode]').forEach(el => {
          el.hidden = el.dataset.mode !== mode;
        });
      }

      document.querySelectorAll('input[name="netmode"]').forEach(radio => {
        radio.addEventListener('change', () => render(radio.value));
      });
      render(document.querySelector('input[name="netmode"]:checked')?.value || 'products');
    }

    const cal = document.querySelector('.cal');
    if (cal) {
      const detail = document.getElementById('caldetail');
      const STORE = 'grocery-calendar-checked';
      let checked = {};
      try { checked = JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { checked = {}; }
      const save = () => { try { localStorage.setItem(STORE, JSON.stringify(checked)); } catch (e) {} };
      const chipKey = chip => chip.closest('.cal-cell').dataset.date + '|' + chip.dataset.full;
      const applyDone = () => {
        cal.querySelectorAll('.chip[data-full]').forEach(chip => {
          chip.classList.toggle('done', !!checked[chipKey(chip)]);
        });
      };

      function openDay(cell) {
        cal.querySelectorAll('.cal-cell.selected').forEach(c => c.classList.remove('selected'));
        cell.classList.add('selected');
        const chips = [...cell.querySelectorAll('.chip[data-full]')];
        detail.hidden = false;
        detail.textContent = '';
        const heading = document.createElement('h3');
        heading.textContent = new Date(cell.dataset.date + 'T00:00')
          .toLocaleDateString(undefined, {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
        detail.appendChild(heading);
        if (!chips.length) {
          const empty = document.createElement('p');
          empty.className = 'cal-empty';
          empty.textContent = 'Nothing estimated due this day.';
          detail.appendChild(empty);
          return;
        }
        let total = 0;
        chips.forEach(chip => {
          const row = document.createElement('label');
          row.className = 'cal-item';
          const box = document.createElement('input');
          box.type = 'checkbox';
          box.checked = !!checked[chipKey(chip)];
          box.addEventListener('change', () => {
            if (box.checked) checked[chipKey(chip)] = 1; else delete checked[chipKey(chip)];
            save();
            applyDone();
            row.classList.toggle('done', box.checked);
          });
          row.classList.toggle('done', box.checked);
          const name = document.createElement('span');
          name.textContent = chip.dataset.full;
          row.append(box, name);
          if (chip.dataset.kind === 'cat') {
            const tag = document.createElement('em');
            tag.textContent = 'category';
            row.appendChild(tag);
          }
          if (chip.dataset.cost) {
            total += parseFloat(chip.dataset.cost) || 0;
            const cost = document.createElement('b');
            cost.textContent = '$' + parseFloat(chip.dataset.cost).toFixed(2);
            row.appendChild(cost);
          }
          detail.appendChild(row);
        });
        if (total > 0) {
          const sum = document.createElement('div');
          sum.className = 'cal-item cal-sum';
          const label = document.createElement('span');
          label.textContent = 'Estimated products total';
          const value = document.createElement('b');
          value.textContent = '$' + total.toFixed(2);
          sum.append(label, value);
          detail.appendChild(sum);
        }
      }

      cal.querySelectorAll('.cal-cell').forEach(cell => {
        cell.addEventListener('click', () => openDay(cell));
        cell.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDay(cell); }
        });
      });
      applyDone();
      const today = cal.querySelector('.cal-cell.today');
      if (today) openDay(today);
    }

    const box = document.getElementById('chartbox');
    if (box) {
      const tip = document.getElementById('charttip');
      let lifted = null;
      const hide = () => {
        tip.hidden = true;
        if (lifted) { lifted.classList.remove('lift'); lifted = null; }
      };
      box.querySelectorAll('.hit').forEach(hit => {
        const show = () => {
          hide();
          tip.querySelector('.t-value').textContent = hit.dataset.value;
          tip.querySelector('.t-label').textContent = hit.dataset.label;
          tip.querySelector('.t-detail').textContent = hit.dataset.detail;
          tip.hidden = false;
          const bar = document.getElementById(hit.dataset.bar);
          if (bar) { bar.classList.add('lift'); lifted = bar; }
          const target = (bar || hit).getBoundingClientRect();
          const frame = box.getBoundingClientRect();
          let x = target.left - frame.left + box.scrollLeft + target.width / 2 - tip.offsetWidth / 2;
          x = Math.max(4, Math.min(x, box.scrollWidth - tip.offsetWidth - 4));
          const y = Math.max(2, target.top - frame.top - tip.offsetHeight - 8);
          tip.style.left = x + 'px';
          tip.style.top = y + 'px';
        };
        hit.addEventListener('pointerenter', show);
        hit.addEventListener('focus', show);
        hit.addEventListener('pointerleave', hide);
        hit.addEventListener('blur', hide);
      });
    }
"""


def main() -> None:
    monthly = rows("monthly_spend.csv")
    weekly = rows("weekly_spend.csv")
    products = rows("product_patterns.csv")
    shopping = rows("suggested_shopping_list.csv")
    categories = rows("category_forecast.csv")
    rules = rows("association_rules.csv")
    live_prices = {r["description"]: r for r in rows("current_prices.csv")}
    summary = summary_values()
    numerical_path = ANALYSIS / "numerical_summary.json"
    numerical_summary = (json.loads(numerical_path.read_text(encoding="utf-8"))
                         if numerical_path.exists() else {})
    numerical_html = numerical_section(
        numerical_summary,
        rows("model_metrics.csv"),
        rows("weekly_model_forecast.csv"),
        rows("week_clusters.csv"),
        rows("numeric_correlations.csv"),
        rows("isolation_anomalies.csv"),
        rows("price_trends_numeric.csv"),
        rows("decision_tree_rules.csv"),
    )

    def network_payload(nodes_file: str, edges_file: str, min_lift: float = 0.0) -> dict:
        edges = [e for e in rows(edges_file) if float(e["lift"]) >= min_lift]
        connected = {e["source"] for e in edges} | {e["target"] for e in edges}
        return {
            "nodes": [{"id": n["key"], "label": n["label"], "count": int(n["basket_count"]),
                       "community": int(n["community"]) if n["community"] != "" else -1}
                      for n in rows(nodes_file) if n["key"] in connected],
            "edges": [{"s": e["source"], "t": e["target"], "count": int(e["together_count"]),
                       "lift": float(e["lift"])} for e in edges],
        }

    basket_total = summary.get("Grocery receipts", "0").split()[0]
    own_baskets = int(basket_total) if basket_total.isdigit() else 0
    stats_path = ANALYSIS / "benchmark_stats.json"
    benchmark_baskets = (json.loads(stats_path.read_text(encoding="utf-8"))["baskets"]
                         if stats_path.exists() else 0)
    network_json = json.dumps({
        "baskets": own_baskets,
        "products": {"baskets": own_baskets,
                     **network_payload("network_nodes.csv", "network_edges.csv")},
        # Category links are dense; keep only clearly-beyond-chance pairs readable.
        "categories": {"baskets": own_baskets,
                       **network_payload("category_network_nodes.csv",
                                         "category_network_edges.csv", min_lift=1.8)},
        "benchmark": {"baskets": benchmark_baskets,
                      **network_payload("benchmark_network_nodes.csv",
                                        "benchmark_network_edges.csv", min_lift=1.2)},
    }).replace("</", "<\\/")

    def community_legend(nodes_file: str, mode: str) -> str:
        groups: dict[str, list[dict[str, str]]] = {}
        for n in rows(nodes_file):
            groups.setdefault(n["community"], []).append(n)
        parts = []
        for com, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            if com == "":
                continue
            members.sort(key=lambda n: -int(n["basket_count"]))
            more = len(members) - 1
            parts.append(f'<span class="legend-item"><i class="ldot cat-{int(com) % 8}"></i>'
                         f'{esc(members[0]["label"][:28])}{f" bundle +{more}" if more else ""}</span>')
        return f'<div class="net-legend" data-mode="{mode}">{"".join(parts)}</div>'

    legend_html = (community_legend("network_nodes.csv", "products")
                   + community_legend("category_network_nodes.csv", "categories")
                   + community_legend("benchmark_network_nodes.csv", "benchmark"))

    comparison = [r for r in rows("pair_comparison.csv")][:10]
    comparison_html = ""
    if comparison:
        comp_rows = "".join(
            f'''<tr><td>{esc(r["category_a"])} + {esc(r["category_b"])}</td>
            <td class="num">{esc(r["your_lift"])}×</td>
            <td class="num">{esc(r["benchmark_lift"]) + "×" if r["benchmark_lift"] else '<span class="muted">rare</span>'}</td></tr>'''
            for r in comparison)
        comparison_html = f'''<details class="table-view"><summary>Your strongest category pairings vs the benchmark</summary>
          <p class="sub" style="margin:8px 0 4px">Benchmark baskets average ~2.4 items, so benchmark lifts run close to 1;
          "rare" means the pair wasn't frequent enough there to measure.</p>
          <div class="table-wrap"><table><thead><tr><th>Pair</th><th class="num">Your lift</th>
          <th class="num">Benchmark</th></tr></thead><tbody>{comp_rows}</tbody></table></div>
        </details>'''

    chart_files = [
        ("monthly_trend.png", "Monthly spend with a 3-month rolling average.", True),
        ("price_trends.png", "Unit price paid over time for the six most-bought products — "
                             "your personal grocery inflation.", True),
        ("weekday_pattern.png", "When shopping happens and how big the basket is by weekday.", False),
        ("basket_hist.png", "Distribution of receipt totals: many small top-ups, few big shops.", False),
        ("top_spend.png", "Where the money has gone, by product.", True),
        ("category_spend.png", "Where the money has gone, by category type.", True),
        ("savings.png", "Promotional savings recorded on the receipts.", False),
    ]
    chart_cards = "".join(
        f'<figure class="chart-card{" span2" if wide else ""}">'
        f'<img src="charts/{name}" alt="{esc(caption)}" loading="lazy">'
        f'<figcaption>{esc(caption)}</figcaption></figure>'
        for name, caption, wide in chart_files if (ANALYSIS / "charts" / name).exists()
    )

    date_range = summary.get("Data range", "")
    range_match = re.match(r"(\S+) to (\S+)", date_range)
    range_text = (f"{fmt_date(range_match.group(1))} – {fmt_date(range_match.group(2))}"
                  if range_match else date_range)
    trip_count = summary.get("Grocery receipts", "—").split()[0]
    spend_total = summary.get("Recorded grocery spend", "")
    spend_text = fmt_money(spend_total.lstrip("$")) if spend_total.startswith("$") else "—"
    avg_trip = summary.get("Average grocery trip", "—")
    forecast_raw = summary.get("90-day spending run-rate forecast", "").lstrip("$")
    recurring_raw = summary.get("Recurring-product forecast", "").lstrip("$")
    category_raw = summary.get("Category-based forecast", "").lstrip("$")
    period_match = re.match(r"(\S+) to (\S+)", summary.get("Forecast period", ""))
    period_text = (f"{fmt_date(period_match.group(1))} – {fmt_date(period_match.group(2))}"
                   if period_match else "—")
    calendar_html = ""
    if period_match and shopping:
        calendar_html = calendar_section(shopping, categories,
                                         date.fromisoformat(period_match.group(1)),
                                         date.fromisoformat(period_match.group(2)))
    gap_days = int(summary.get("Days without receipts before forecast", "0") or 0)
    gap_note = ""
    if gap_days > 14 and range_match:
        gap_note = (f'<p class="gap-note">No receipts recorded for the {gap_days} days before the '
                    f'forecast start (last receipt {esc(fmt_date(range_match.group(2)))}). Due dates '
                    f'assume shopping continued at the usual cadence.</p>')

    recurring_products = sum(1 for p in products if int(p["purchase_dates"]) >= 2)

    document = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Grocery outlook</title>
  <style>{CSS}</style>
</head>
<body>
<div class="page">
  <main>
    <div class="head">
      <h1>Grocery outlook</h1>
      <p>{esc(trip_count)} Woolworths receipts · {esc(range_text)} · BIG W and duplicate receipts excluded</p>
    </div>

    <section class="cards">
      <div class="card"><small>Recorded spend</small><b>{esc(spend_text)}</b><div class="note">across all receipts</div></div>
      <div class="card"><small>Grocery trips</small><b>{esc(trip_count)}</b><div class="note">average {esc(avg_trip)} per trip</div></div>
      <div class="card"><small>Recurring products</small><b>{recurring_products}</b><div class="note">bought two or more times</div></div>
      <div class="card"><small>Due in next 30 days</small><b>{len(shopping)}</b><div class="note">see shopping list below</div></div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Monthly spending</h2>
        <p class="sub">Receipt totals by calendar month; months without receipts are shown empty</p>
        {monthly_chart(monthly)}
      </div>
      <div class="panel">
        <h2>30-day budget estimate</h2>
        <div class="hero">{fmt_money(forecast_raw, 0) if forecast_raw else "—"}</div>
        <p class="sub">Run-rate from the last 90 days of receipts, projected over {esc(period_text)}</p>
        <div class="fc-row"><span>Exact run-rate estimate</span><b>{fmt_money(forecast_raw) if forecast_raw else "—"}</b></div>
        <div class="fc-row"><span>Recurring products alone</span><b>{fmt_money(recurring_raw) if recurring_raw else "—"}</b></div>
        <div class="fc-row"><span>By category type</span><b>{fmt_money(category_raw) if category_raw else "—"}</b></div>
        <div class="fc-row"><span>Products likely due</span><b>{len(shopping)}</b></div>
        {gap_note}
      </div>
    </section>

    {numerical_html}

    <section class="panel wide">
      <h2>Suggested shopping list</h2>
      <p class="sub">Inferred from repeat-purchase cadence — an estimate of what may be running low, not a guarantee</p>
      <input type="search" placeholder="Filter products…" data-target="shopping" aria-label="Filter shopping list">
      <div class="table-wrap"><table id="shopping" class="sortable">
        <thead><tr><th>Product</th><th aria-sort="ascending" data-sort="num">Estimated due</th><th class="num">Usual interval</th>
        <th class="num">Paid before</th><th class="num">Price now</th><th>Confidence</th></tr></thead>
        <tbody>{shopping_table(shopping, live_prices)}</tbody></table></div>
      {'<p class="sub" style="margin:10px 0 0">“Price now” is the closest woolworths.com.au match (hover a price for the matched product); the +/− figure compares it with the price you typically paid. Refresh with <code>python fetch_prices.py</code>.</p>' if live_prices else ''}
    </section>

    {calendar_html}

    <section class="panel wide">
      <h2>Category outlook — what type of thing you'll need</h2>
      <p class="sub">The same purchases grouped by product type instead of brand. Category cadence is
        steadier than any single product's, so these estimates hold up better across the receipt gap.
        "Lapsed" means the category has gone quiet for over three times its usual cycle.</p>
      <input type="search" placeholder="Filter categories…" data-target="categories" aria-label="Filter categories">
      <div class="table-wrap"><table id="categories" class="sortable">
        <thead><tr><th>Category</th><th class="num" aria-sort="descending">Expected 30-day spend</th>
        <th data-sort="num">Estimated due</th><th class="num">Usual interval</th><th>Last bought</th>
        <th class="num">Purchases</th><th>Confidence</th></tr></thead>
        <tbody>{category_table(categories)}</tbody></table></div>
    </section>

    <section class="panel wide">
      <h2>Frequently purchased products</h2>
      <p class="sub">Every product on record — click a column heading to sort, or filter by name</p>
      <input type="search" placeholder="Filter products…" data-target="products" aria-label="Filter products">
      <div class="table-wrap"><table id="products" class="sortable">
        <thead><tr><th>Product</th><th class="num" aria-sort="descending">Purchases</th><th>Last bought</th>
        <th class="num">Typical interval</th><th class="num">Typical price</th></tr></thead>
        <tbody>{product_table(products)}</tbody></table></div>
    </section>

    <section class="panel wide">
      <h2>Products bought together</h2>
      <p class="sub">Each link joins two products that landed in the same basket at least three times;
        thicker lines mean the pairing beats chance by more (lift). Node size is how many baskets the
        product appears in; colors are shopping bundles found by community detection.
        Drag nodes, hover for detail, click a product node to filter the rules table below.
        "All shoppers" shows the same graph mined from 14,963 baskets in the Kaggle groceries dataset.</p>
      <div class="net-toggle" role="radiogroup" aria-label="Network level">
        <label><input type="radio" name="netmode" value="products" checked><span>Products</span></label>
        <label><input type="radio" name="netmode" value="categories"><span>Categories</span></label>
        <label><input type="radio" name="netmode" value="benchmark"><span>All shoppers</span></label>
      </div>
      <div class="net-box" id="netbox">
        <svg id="netsvg" viewBox="0 0 960 540" role="img" aria-label="Co-purchase network of products"></svg>
        <div class="tooltip" id="nettip" hidden>
          <div class="t-value"></div><div class="t-label"></div><div class="t-detail"></div>
        </div>
      </div>
      {legend_html}
      {comparison_html}
      <p class="sub" style="margin-top:22px">Confidence: how often the second product was in the basket when the first was.
        Lift: how much more often than chance.</p>
      <input type="search" placeholder="Filter rules…" data-target="rules" aria-label="Filter rules">
      <div class="table-wrap"><table id="rules" class="sortable">
        <thead><tr><th>If you bought</th><th></th><th>You also bought</th>
        <th class="num">Confidence</th><th class="num" aria-sort="descending">Lift</th><th class="num">Together</th></tr></thead>
        <tbody>{rules_table(rules)}</tbody></table></div>
    </section>

    {f"""<section class="panel wide">
      <h2>Deeper analysis</h2>
      <p class="sub">Generated by <code>make_charts.py</code>; charts render in a light theme</p>
      <div class="charts-grid">{chart_cards}</div>
    </section>""" if chart_cards else ""}

    <section class="panel wide">
      <h2>Week-by-week breakdown</h2>
      <p class="sub">Monday to Sunday, newest first; weeks without a recorded receipt are dimmed</p>
      <div class="table-wrap"><table id="weekly" class="sortable">
        <thead><tr><th aria-sort="descending">Week</th><th class="num">Spend</th><th class="num">Trips</th>
        <th class="num">Items</th><th class="num">Average trip</th></tr></thead>
        <tbody>{weekly_table(weekly)}</tbody></table></div>
    </section>

    <footer>Generated from parsed eReceipt data · forecasts assume the receipts cover all grocery shopping</footer>
  </main>
</div>
<script>{d3_source()}</script>
<script>window.NETWORK = {network_json};</script>
<script>{JS}</script>
</body>
</html>'''
    output = ANALYSIS / "dashboard.html"
    output.write_text(document, encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
