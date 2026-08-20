#!/usr/bin/env python3
"""Mine benchmark association rules from the Kaggle groceries dataset.

Source: https://www.kaggle.com/datasets/heeraldedhia/groceries-dataset
(38k purchases by 3,898 shoppers, item names matching our category taxonomy).
A basket is one member's purchases on one day. Outputs benchmark_* CSVs via
the same Apriori as association_rules.py, plus pair_comparison.csv putting
your own category pairings next to the benchmark's lift for the same pair.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from association_rules import mine_and_write, product_key


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path,
                        default=Path("data/Groceries_dataset.csv/Groceries_dataset.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("analysis"))
    parser.add_argument("--min-count", type=int, default=15,
                        help="Minimum baskets containing an itemset (default 15 ~ 0.1%%)")
    parser.add_argument("--min-confidence", type=float, default=0.05,
                        help="Baskets here are small (~2.4 items), so confidence runs low")
    parser.add_argument("--min-lift", type=float, default=1.2)
    args = parser.parse_args()

    labels: dict[str, str] = {}
    baskets: dict[tuple[str, str], set[str]] = {}
    for row in read_csv(args.data):
        key = product_key(row["itemDescription"])
        labels[key] = row["itemDescription"]
        baskets.setdefault((row["Member_number"], row["Date"]), set()).add(key)
    stats = mine_and_write(baskets, labels, args, prefix="benchmark_")
    (args.output_dir / "benchmark_stats.json").write_text(
        json.dumps({"baskets": len(baskets), "members": 0, "items": len(labels)}),
        encoding="utf-8")
    print(f"{len(baskets)} benchmark baskets ({len(labels)} items): {stats}")

    # Side-by-side of your category pairings against the benchmark.
    own_edges = read_csv(args.output_dir / "category_network_edges.csv")
    own_labels = {n["key"]: n["label"]
                  for n in read_csv(args.output_dir / "category_network_nodes.csv")}
    bench = {frozenset((e["source"], e["target"])): e["lift"]
             for e in read_csv(args.output_dir / "benchmark_network_edges.csv")}
    comparison = [{
        "category_a": own_labels[e["source"]],
        "category_b": own_labels[e["target"]],
        "your_baskets": e["together_count"],
        "your_lift": e["lift"],
        "benchmark_lift": bench.get(frozenset((e["source"], e["target"])), ""),
    } for e in sorted(own_edges, key=lambda e: -float(e["lift"]))]
    target = args.output_dir / "pair_comparison.csv"
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category_a", "category_b",
                                                    "your_baskets", "your_lift",
                                                    "benchmark_lift"])
        writer.writeheader()
        writer.writerows(comparison)
    matched = sum(1 for r in comparison if r["benchmark_lift"])
    print(f"{len(comparison)} of your category pairs compared "
          f"({matched} also frequent in the benchmark) -> {target}")


if __name__ == "__main__":
    main()
