#!/usr/bin/env python3
"""Apply numerical pattern models to weekly grocery and product-price history.

The implementation deliberately uses chronological validation: models learn from
earlier weeks and are scored on later weeks.  This is more honest than fitting and
scoring on the same data, especially for a small and incomplete receipt history.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np


FEATURE_NAMES = ["last week", "two weeks ago", "previous 4-week average",
                 "shops in previous 4 weeks", "annual sine", "annual cosine"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], values: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(values)


def metrics(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float, float]:
    errors = actual - predicted
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors**2)))
    denominator = float(np.sum((actual - np.mean(actual)) ** 2))
    r2 = 1 - float(np.sum(errors**2)) / denominator if denominator else 0.0
    return mae, rmse, r2


def trend_fit(y: np.ndarray, end: int | None = None) -> tuple[float, float]:
    end = len(y) if end is None else end
    x = np.arange(end, dtype=float)
    slope, intercept = np.polyfit(x, y[:end], 1)
    return float(slope), float(intercept)


def features(history: list[float], index: int) -> list[float]:
    recent = history[-4:]
    padded = [0.0] * (4 - len(recent)) + recent
    angle = 2 * math.pi * (index % 52) / 52
    return [padded[-1], padded[-2], statistics.mean(padded),
            float(sum(value > 0 for value in padded)), math.sin(angle), math.cos(angle)]


@dataclass
class TreeNode:
    value: float
    feature: int | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None


@dataclass
class IsolationNode:
    size: int
    feature: int | None = None
    threshold: float | None = None
    left: "IsolationNode | None" = None
    right: "IsolationNode | None" = None


def fit_tree(x: np.ndarray, y: np.ndarray, depth: int = 0,
             max_depth: int = 3, min_leaf: int = 6) -> TreeNode:
    node = TreeNode(float(np.mean(y)))
    if depth >= max_depth or len(y) < min_leaf * 2 or np.var(y) < 1e-8:
        return node
    best: tuple[float, int, float, np.ndarray] | None = None
    for feature_index in range(x.shape[1]):
        unique = np.unique(x[:, feature_index])
        if len(unique) > 30:
            thresholds = np.quantile(unique, np.linspace(.05, .95, 20))
        else:
            thresholds = (unique[:-1] + unique[1:]) / 2
        for threshold in np.unique(thresholds):
            mask = x[:, feature_index] <= threshold
            if mask.sum() < min_leaf or (~mask).sum() < min_leaf:
                continue
            loss = float(np.var(y[mask]) * mask.sum() + np.var(y[~mask]) * (~mask).sum())
            if best is None or loss < best[0]:
                best = loss, feature_index, float(threshold), mask
    if best is None:
        return node
    _, node.feature, node.threshold, mask = best
    node.left = fit_tree(x[mask], y[mask], depth + 1, max_depth, min_leaf)
    node.right = fit_tree(x[~mask], y[~mask], depth + 1, max_depth, min_leaf)
    return node


def tree_predict_one(node: TreeNode, row: list[float] | np.ndarray) -> float:
    while node.feature is not None:
        node = node.left if row[node.feature] <= node.threshold else node.right  # type: ignore[assignment]
    return max(0.0, node.value)


def tree_rules(node: TreeNode, conditions: list[str] | None = None) -> list[dict]:
    conditions = conditions or []
    if node.feature is None:
        return [{"rule": " and ".join(conditions) or "all weeks",
                 "predicted_weekly_spend": f"{node.value:.2f}"}]
    name = FEATURE_NAMES[node.feature]
    return (tree_rules(node.left, conditions + [f"{name} <= {node.threshold:.2f}"]) +
            tree_rules(node.right, conditions + [f"{name} > {node.threshold:.2f}"]))  # type: ignore[arg-type]


def fit_stump(x: np.ndarray, residual: np.ndarray, min_leaf: int = 6) -> TreeNode:
    return fit_tree(x, residual, max_depth=1, min_leaf=min_leaf)


def fit_boosting(x: np.ndarray, y: np.ndarray, rounds: int = 60,
                 rate: float = .05) -> tuple[float, list[TreeNode]]:
    base = float(np.mean(y))
    fitted = np.full(len(y), base)
    trees = []
    for _ in range(rounds):
        tree = fit_stump(x, y - fitted)
        update = np.array([tree_predict_one_raw(tree, row) for row in x])
        fitted += rate * update
        trees.append(tree)
    return base, trees


def tree_predict_one_raw(node: TreeNode, row: list[float] | np.ndarray) -> float:
    while node.feature is not None:
        node = node.left if row[node.feature] <= node.threshold else node.right  # type: ignore[assignment]
    return node.value


def boost_predict(base: float, trees: list[TreeNode], row: list[float], rate: float = .05) -> float:
    return max(0.0, base + rate * sum(tree_predict_one_raw(tree, row) for tree in trees))


def model_matrix(values: list[float], stop: int) -> tuple[np.ndarray, np.ndarray]:
    x, target = [], []
    for index in range(4, stop):
        x.append(features(values[:index], index))
        target.append(values[index])
    return np.asarray(x), np.asarray(target)


def recursive_forecast(model, history: list[float], start_index: int, count: int) -> np.ndarray:
    result = []
    for index in range(start_index, start_index + count):
        prediction = max(0.0, float(model(features(history, index))))
        history.append(prediction)
        result.append(prediction)
    return np.asarray(result)


def holt_winters_fit(values: list[float], period: int, alpha: float, beta: float,
                     gamma: float) -> tuple[float, float, list[float]]:
    if len(values) < period * 2:
        raise ValueError("not enough observations for seasonal model")
    first = statistics.mean(values[:period])
    second = statistics.mean(values[period:period * 2])
    level = first
    trend = (second - first) / period
    seasonal = [values[i] - first for i in range(period)]
    for index, value in enumerate(values):
        slot = index % period
        old_level = level
        level = alpha * (value - seasonal[slot]) + (1 - alpha) * (level + trend)
        trend = beta * (level - old_level) + (1 - beta) * trend
        seasonal[slot] = gamma * (value - level) + (1 - gamma) * seasonal[slot]
    return level, trend, seasonal


def holt_winters_forecast(values: list[float], count: int, period: int = 52,
                          params: tuple[float, float, float] = (.3, .1, .2)) -> np.ndarray:
    level, trend, seasonal = holt_winters_fit(values, period, *params)
    start = len(values)
    return np.asarray([max(0.0, level + step * trend + seasonal[(start + step - 1) % period])
                       for step in range(1, count + 1)])


def choose_hw_params(train: list[float], validation_size: int, period: int = 52):
    inner = train[:-validation_size]
    actual = np.asarray(train[-validation_size:])
    best = None
    for alpha in (.2, .4, .6):
        for beta in (.05, .15):
            for gamma in (.1, .3):
                try:
                    predicted = holt_winters_forecast(inner, validation_size, period,
                                                      (alpha, beta, gamma))
                except ValueError:
                    continue
                score = metrics(actual, predicted)[0]
                if best is None or score < best[0]:
                    best = score, (alpha, beta, gamma)
    return best[1] if best else (.3, .1, .2)


def kmeans(data: np.ndarray, k: int = 3) -> np.ndarray:
    means = data.mean(axis=0)
    stds = data.std(axis=0)
    stds[stds == 0] = 1
    z = (data - means) / stds
    spend_order = np.argsort(data[:, 0])
    seeds = [spend_order[int((len(data) - 1) * q)] for q in (0.1, 0.55, 0.9)]
    centers = z[seeds].copy()
    labels = np.zeros(len(data), dtype=int)
    for _ in range(100):
        new_labels = np.argmin(((z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2), axis=1)
        new_centers = np.asarray([z[new_labels == group].mean(axis=0)
                                  if np.any(new_labels == group) else centers[group]
                                  for group in range(k)])
        if np.array_equal(new_labels, labels):
            break
        labels, centers = new_labels, new_centers
    return labels


def isolation_tree(data: np.ndarray, rng: np.random.Generator, depth: int,
                   max_depth: int) -> IsolationNode:
    node = IsolationNode(len(data))
    usable = [i for i in range(data.shape[1]) if np.ptp(data[:, i]) > 0]
    if depth >= max_depth or len(data) <= 1 or not usable:
        return node
    feature = int(rng.choice(usable))
    low, high = float(data[:, feature].min()), float(data[:, feature].max())
    threshold = float(rng.uniform(low, high))
    mask = data[:, feature] < threshold
    if not np.any(mask) or np.all(mask):
        return node
    node.feature, node.threshold = feature, threshold
    node.left = isolation_tree(data[mask], rng, depth + 1, max_depth)
    node.right = isolation_tree(data[~mask], rng, depth + 1, max_depth)
    return node


def average_path_adjustment(size: int) -> float:
    if size <= 1:
        return 0.0
    if size == 2:
        return 1.0
    return 2 * (math.log(size - 1) + 0.5772156649) - 2 * (size - 1) / size


def isolation_path(node: IsolationNode, row: np.ndarray, depth: int = 0) -> float:
    if node.feature is None:
        return depth + average_path_adjustment(node.size)
    child = node.left if row[node.feature] < node.threshold else node.right
    return isolation_path(child, row, depth + 1)  # type: ignore[arg-type]


def isolation_scores(data: np.ndarray, trees: int = 150, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sample_size = min(64, len(data))
    max_depth = math.ceil(math.log2(sample_size))
    forest = []
    for _ in range(trees):
        indexes = rng.choice(len(data), sample_size, replace=False)
        forest.append(isolation_tree(data[indexes], rng, 0, max_depth))
    normalizer = average_path_adjustment(sample_size)
    return np.asarray([2 ** (-statistics.mean(isolation_path(tree, row) for tree in forest) /
                            normalizer) for row in data])


def product_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, default=Path("analysis"))
    parser.add_argument("--parsed-dir", type=Path, default=Path("parsed"))
    parser.add_argument("--forecast-weeks", type=int, default=12)
    args = parser.parse_args()
    args.analysis_dir.mkdir(parents=True, exist_ok=True)

    weekly = read_csv(args.analysis_dir / "weekly_spend.csv")
    values = [float(row["spend"]) for row in weekly]
    y = np.asarray(values)
    dates = [date.fromisoformat(row["week_start"]) for row in weekly]
    n = len(y)
    if n < 30:
        raise SystemExit("At least 30 weekly observations are needed")
    test_size = min(26, max(12, n // 5))
    split = n - test_size
    actual = y[split:]

    # Linear regression: a straight-line time trend.
    slope, intercept = trend_fit(y, split)
    linear_test = intercept + slope * np.arange(split, n)

    # Seasonal time series: additive Holt-Winters with a 52-week cycle.
    hw_params = choose_hw_params(values[:split], min(13, max(6, split - 104)))
    hw_test = holt_winters_forecast(values[:split], test_size, 52, hw_params)

    # Decision tree and gradient-boosted trees: nonlinear lag/calendar rules.
    train_x, train_y = model_matrix(values, split)
    tree = fit_tree(train_x, train_y)
    tree_test = recursive_forecast(lambda row: tree_predict_one(tree, row),
                                   values[:split], split, test_size)
    boost_base, boost_trees = fit_boosting(train_x, train_y)
    boost_test = recursive_forecast(lambda row: boost_predict(boost_base, boost_trees, row),
                                    values[:split], split, test_size)
    baseline_test = np.full(test_size, statistics.mean(values[max(0, split - 13):split]))

    predictions = {
        "13-week mean baseline": baseline_test,
        "Linear regression": np.maximum(0, linear_test),
        "Holt-Winters (52-week)": hw_test,
        "Decision tree": tree_test,
        "Gradient-boosted trees": boost_test,
    }
    metric_rows = []
    for name, predicted in predictions.items():
        mae, rmse, r2 = metrics(actual, predicted)
        wape = float(np.sum(np.abs(actual - predicted)) / np.sum(np.abs(actual))) \
            if np.sum(np.abs(actual)) else 0.0
        metric_rows.append({"model": name, "validation_weeks": test_size, "mae": f"{mae:.2f}",
                            "rmse": f"{rmse:.2f}", "wape": f"{wape:.3f}",
                            "r_squared": f"{r2:.3f}"})
    metric_rows.sort(key=lambda row: float(row["mae"]))
    write_csv(args.analysis_dir / "model_metrics.csv",
              ["model", "validation_weeks", "mae", "rmse", "wape", "r_squared"], metric_rows)

    # Refit every model on all available observations for forward projections.
    full_slope, full_intercept = trend_fit(y)
    forecast_indexes = np.arange(n, n + args.forecast_weeks)
    linear_future = np.maximum(0, full_intercept + full_slope * forecast_indexes)
    full_hw_params = choose_hw_params(values, 13)
    hw_future = holt_winters_forecast(values, args.forecast_weeks, 52, full_hw_params)
    full_x, full_y = model_matrix(values, n)
    full_tree = fit_tree(full_x, full_y)
    tree_future = recursive_forecast(lambda row: tree_predict_one(full_tree, row),
                                     values.copy(), n, args.forecast_weeks)
    full_base, full_boost = fit_boosting(full_x, full_y)
    boost_future = recursive_forecast(lambda row: boost_predict(full_base, full_boost, row),
                                      values.copy(), n, args.forecast_weeks)
    ensemble = np.median(np.vstack([linear_future, hw_future, tree_future, boost_future]), axis=0)
    forecast_rows = []
    for offset in range(args.forecast_weeks):
        week_start = dates[-1] + timedelta(days=7 * (offset + 1))
        forecast_rows.append({
            "week_start": week_start.isoformat(),
            "linear_regression": f"{linear_future[offset]:.2f}",
            "holt_winters": f"{hw_future[offset]:.2f}",
            "decision_tree": f"{tree_future[offset]:.2f}",
            "gradient_boosting": f"{boost_future[offset]:.2f}",
            "ensemble": f"{ensemble[offset]:.2f}",
        })
    write_csv(args.analysis_dir / "weekly_model_forecast.csv",
              ["week_start", "linear_regression", "holt_winters", "decision_tree",
               "gradient_boosting", "ensemble"], forecast_rows)
    write_csv(args.analysis_dir / "decision_tree_rules.csv", ["rule", "predicted_weekly_spend"],
              tree_rules(full_tree))

    # K-means: group weeks into quiet, typical, and stock-up profiles.
    cluster_data = np.asarray([[float(r["spend"]), float(r["trips"]), float(r["items"]),
                                float(r["average_trip"])] for r in weekly])
    raw_labels = kmeans(cluster_data)
    raw_means = {label: float(y[raw_labels == label].mean()) for label in set(raw_labels)}
    ordered = sorted(raw_means, key=raw_means.get)
    names = {ordered[0]: "Quiet / no recorded shop", ordered[1]: "Typical shop",
             ordered[2]: "Stock-up week"}
    cluster_rows = []
    for raw in ordered:
        mask = raw_labels == raw
        cluster_rows.append({"week_type": names[raw], "weeks": int(mask.sum()),
                             "average_spend": f"{y[mask].mean():.2f}",
                             "average_trips": f"{cluster_data[mask, 1].mean():.2f}",
                             "average_items": f"{cluster_data[mask, 2].mean():.1f}"})
    write_csv(args.analysis_dir / "week_clusters.csv",
              ["week_type", "weeks", "average_spend", "average_trips", "average_items"], cluster_rows)

    # Robust anomaly scores only compare weeks with a recorded purchase.
    positive = y[y > 0]
    median = float(np.median(positive))
    mad = float(np.median(np.abs(positive - median))) or 1.0
    anomaly_rows = []
    for index, value in enumerate(y):
        if value <= 0:
            continue
        score = .6745 * (value - median) / mad
        if abs(score) >= 3.5:
            anomaly_rows.append({"week_start": dates[index].isoformat(), "spend": f"{value:.2f}",
                                 "robust_z_score": f"{score:.2f}",
                                 "pattern": "unusually high" if score > 0 else "unusually low"})
    write_csv(args.analysis_dir / "spend_anomalies.csv",
              ["week_start", "spend", "robust_z_score", "pattern"], anomaly_rows)

    # Isolation Forest: multivariate anomalies among actual shopping weeks.
    shop_indexes = np.flatnonzero(y > 0)
    gap = np.asarray([shop_indexes[i] - shop_indexes[i - 1] if i else 0
                      for i in range(len(shop_indexes))], dtype=float)
    iso_data = np.column_stack([cluster_data[shop_indexes, :], gap])
    iso_score = isolation_scores(iso_data)
    isolation_rows = []
    for position in np.argsort(-iso_score)[:10]:
        index = shop_indexes[position]
        reasons = []
        if y[index] > np.quantile(positive, .9):
            reasons.append("high spend")
        if cluster_data[index, 2] > np.quantile(cluster_data[shop_indexes, 2], .9):
            reasons.append("large item count")
        if gap[position] > np.quantile(gap, .9):
            reasons.append("long gap before shop")
        isolation_rows.append({"week_start": dates[index].isoformat(), "spend": f"{y[index]:.2f}",
                               "items": f"{cluster_data[index, 2]:.0f}",
                               "isolation_score": f"{iso_score[position]:.3f}",
                               "flagged": "yes" if iso_score[position] >= .60 else "review",
                               "reason": ", ".join(reasons) or "unusual combination of values"})
    write_csv(args.analysis_dir / "isolation_anomalies.csv",
              ["week_start", "spend", "items", "isolation_score", "flagged", "reason"],
              isolation_rows)

    # Correlation: descriptive relationships, not evidence that one variable causes another.
    correlation_rows = []
    variables = {"trip count": cluster_data[:, 1], "item count": cluster_data[:, 2],
                 "average trip": cluster_data[:, 3], "week number (trend)": np.arange(n)}
    for name, series in variables.items():
        coefficient = float(np.corrcoef(y, series)[0, 1]) if np.std(series) else 0.0
        correlation_rows.append({"variable": name, "correlation_with_spend": f"{coefficient:.3f}",
                                 "strength": "strong" if abs(coefficient) >= .7 else
                                             "moderate" if abs(coefficient) >= .4 else "weak"})
    write_csv(args.analysis_dir / "numeric_correlations.csv",
              ["variable", "correlation_with_spend", "strength"], correlation_rows)

    # Price trend regression and first-to-last change for repeatedly purchased products.
    receipts = read_csv(args.parsed_dir / "receipts.csv")
    receipt_dates = {r["receipt_id"]: date.fromisoformat(r["purchase_date"]) for r in receipts
                     if not r["store_name"].lower().startswith("big w") and
                     r.get("parse_status") != "duplicate"}
    product_prices: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(list))
    labels: dict[str, str] = {}
    for item in read_csv(args.parsed_dir / "items.csv"):
        if item["receipt_id"] not in receipt_dates or float(item["line_total"]) <= 0:
            continue
        quantity = float(item["quantity"])
        if quantity <= 0 or item["quantity_unit"] != "each":
            continue
        key = product_key(item["description"])
        labels[key] = item["description"]
        product_prices[key][receipt_dates[item["receipt_id"]]].append(float(item["line_total"]) / quantity)
    current = {product_key(r["description"]): r for r in read_csv(args.analysis_dir / "current_prices.csv")} \
        if (args.analysis_dir / "current_prices.csv").exists() else {}
    price_rows = []
    for key, by_date in product_prices.items():
        if len(by_date) < 3:
            continue
        product_dates = sorted(by_date)
        prices = np.asarray([statistics.median(by_date[d]) for d in product_dates])
        days = np.asarray([(d - product_dates[0]).days for d in product_dates])
        annual_slope = float(np.polyfit(days, prices, 1)[0] * 365) if days[-1] else 0.0
        change = (prices[-1] / prices[0] - 1) * 100 if prices[0] else 0.0
        live = current.get(key, {})
        current_price = live.get("price", "") if float(live.get("match_score") or 0) >= .8 else ""
        price_rows.append({"description": labels[key], "observations": len(product_dates),
                           "first_price": f"{prices[0]:.2f}", "last_paid": f"{prices[-1]:.2f}",
                           "first_to_last_pct": f"{change:.1f}",
                           "linear_change_per_year": f"{annual_slope:.2f}" if len(by_date) >= 5 else "",
                           "trend_reliability": "usable" if len(by_date) >= 5 else "limited",
                           "current_price": current_price})
    price_rows.sort(key=lambda row: (-abs(float(row["first_to_last_pct"])), -int(row["observations"])))
    write_csv(args.analysis_dir / "price_trends_numeric.csv",
              ["description", "observations", "first_price", "last_paid", "first_to_last_pct",
               "linear_change_per_year", "trend_reliability", "current_price"], price_rows)

    # Basic +, -, ×, ÷ sequence checks on the most recent non-zero weekly spends.
    nonzero = [float(v) for v in y if v > 0]
    recent = nonzero[-8:]
    differences = np.diff(recent)
    ratios = np.asarray([b / a for a, b in zip(recent, recent[1:]) if a])
    diff_cv = float(np.std(differences) / max(abs(np.mean(differences)), 1)) if len(differences) else 0
    ratio_cv = float(np.std(ratios) / max(abs(np.mean(ratios)), 1)) if len(ratios) else 0
    arithmetic_found = len(differences) >= 3 and diff_cv < .10
    geometric_found = len(ratios) >= 3 and ratio_cv < .10
    summary = {
        "weeks": n,
        "weeks_with_receipts": int(np.sum(y > 0)),
        "weeks_without_receipts": int(np.sum(y == 0)),
        "linear_weekly_slope": round(full_slope, 2),
        "linear_annual_change": round(full_slope * 52, 2),
        "best_validation_model": metric_rows[0]["model"],
        "best_validation_mae": float(metric_rows[0]["mae"]),
        "best_model_improvement_over_baseline": round(
            float(next(r["mae"] for r in metric_rows if r["model"] == "13-week mean baseline")) -
            float(metric_rows[0]["mae"]), 2),
        "next_4_week_ensemble_total": round(float(np.sum(ensemble[:4])), 2),
        "arithmetic_sequence_found": arithmetic_found,
        "geometric_sequence_found": geometric_found,
        "sequence_note": ("A stable addition/subtraction pattern was detected." if arithmetic_found else
                          "A stable multiplication/division pattern was detected." if geometric_found else
                          "No stable +, -, ×, or ÷ sequence appears in the latest non-zero weekly totals."),
        "holt_winters_parameters": {"alpha": full_hw_params[0], "beta": full_hw_params[1],
                                     "gamma": full_hw_params[2], "season_weeks": 52},
        "coverage_warning": (f"{int(np.sum(y == 0))} of {n} calendar weeks have no receipt; forecasts "
                             "model recorded receipt spend, which may not equal all grocery spend.")
    }
    (args.analysis_dir / "numerical_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Applied numerical models to {n} weeks; best holdout MAE: "
          f"{summary['best_validation_model']} (${summary['best_validation_mae']:.2f})")


if __name__ == "__main__":
    main()
