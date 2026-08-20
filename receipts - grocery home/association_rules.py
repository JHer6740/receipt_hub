#!/usr/bin/env python3
"""Mine frequent itemsets and association rules from grocery receipt baskets.

Implements the Apriori algorithm (level-wise candidate generation pruned with
the Apriori property, as in Srinivasa Rao et al., IJARSCT-7599): frequent
itemsets of any size are found first, then rules `antecedent -> item` are kept
when they clear the support, confidence and lift thresholds.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from decimal import Decimal
from itertools import combinations
from pathlib import Path

from categorize import categorize

NON_BASKET_CATEGORIES = {"discounts", "shopping bags", "clothing", "unmapped"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def product_key(description: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", description.lower())


def apriori(transactions: list[frozenset[str]], min_count: int) -> dict[frozenset[str], int]:
    """Return every itemset contained in at least min_count baskets."""
    counts = Counter()
    for basket in transactions:
        for item in basket:
            counts[frozenset([item])] += 1
    frequent = {s: c for s, c in counts.items() if c >= min_count}
    all_frequent = dict(frequent)
    size = 2
    while frequent:
        # Extend each frequent set one item at a time; the Apriori property lets
        # us drop any candidate with an infrequent subset before counting.
        previous = set(frequent)
        items = sorted({item for s in frequent for item in s})
        candidates = set()
        for itemset in frequent:
            for item in items:
                if item in itemset:
                    continue
                candidate = itemset | {item}
                if len(candidate) == size and all(
                        candidate - {member} in previous for member in candidate):
                    candidates.add(candidate)
        counts = Counter()
        # Count whichever way is cheaper: enumerating each basket's size-k
        # subsets (fast for many small baskets) or scanning candidates per
        # basket (fast for few large baskets).
        combo_cost = sum(math.comb(len(b), size) for b in transactions if len(b) >= size)
        if combo_cost < len(candidates) * len(transactions):
            for basket in transactions:
                if len(basket) < size:
                    continue
                for combo in combinations(sorted(basket), size):
                    candidate = frozenset(combo)
                    if candidate in candidates:
                        counts[candidate] += 1
        else:
            for basket in transactions:
                for candidate in candidates:
                    if candidate <= basket:
                        counts[candidate] += 1
        frequent = {s: c for s, c in counts.items() if c >= min_count}
        all_frequent.update(frequent)
        size += 1
    return all_frequent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parsed-dir", type=Path, default=Path("parsed"))
    parser.add_argument("--output-dir", type=Path, default=Path("analysis"))
    parser.add_argument("--min-count", type=int, default=3,
                        help="Minimum number of baskets containing an itemset (default 3)")
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--min-lift", type=float, default=1.2)
    args = parser.parse_args()

    receipts = read_csv(args.parsed_dir / "receipts.csv")
    grocery_ids = {r["receipt_id"] for r in receipts
                   if not r["store_name"].lower().startswith("big w")}
    items = read_csv(args.parsed_dir / "items.csv")
    labels: dict[str, str] = {}
    baskets: dict[str, set[str]] = {}
    for item in items:
        if item["receipt_id"] not in grocery_ids or Decimal(item["line_total"]) <= 0:
            continue
        key = product_key(item["description"])
        # Bags reflect checkout behavior rather than a useful grocery association.
        if not key or "paperbag" in key:
            continue
        if len(item["description"]) > len(labels.get(key, "")):
            labels[key] = item["description"]
        baskets.setdefault(item["receipt_id"], set()).add(key)

    product_stats = mine_and_write(baskets, labels, args, prefix="")

    # Category-level pass: the same baskets collapsed to product types (from
    # categorize.py), which yields denser, more general rules than brand-level.
    cat_labels: dict[str, str] = {}
    cat_baskets: dict[str, set[str]] = {}
    for item in items:
        if item["receipt_id"] not in grocery_ids or Decimal(item["line_total"]) <= 0:
            continue
        category = categorize(item["description"])
        if category in NON_BASKET_CATEGORIES:
            continue
        key = product_key(category)
        cat_labels[key] = category
        cat_baskets.setdefault(item["receipt_id"], set()).add(key)
    category_stats = mine_and_write(cat_baskets, cat_labels, args, prefix="category_")

    print(f"{len(baskets)} grocery baskets")
    print(f"  products:   {product_stats}")
    print(f"  categories: {category_stats}")


def mine_and_write(baskets: dict[str, set[str]], labels: dict[str, str],
                   args: argparse.Namespace, prefix: str) -> str:
    transactions = [frozenset(b) for b in baskets.values()]
    transaction_count = len(transactions)
    frequent = apriori(transactions, args.min_count)

    def label_for(itemset: frozenset[str]) -> str:
        return " + ".join(sorted(labels[k] for k in itemset))

    itemset_rows = [{
        "items": label_for(s),
        "size": len(s),
        "basket_count": count,
        "support": f"{count / transaction_count:.3f}",
    } for s, count in frequent.items() if len(s) >= 2]
    itemset_rows.sort(key=lambda r: (-int(r["size"]), -int(r["basket_count"]), r["items"]))

    rules = []
    for itemset, count in frequent.items():
        if len(itemset) < 2:
            continue
        for consequent in itemset:
            antecedent = itemset - {consequent}
            antecedent_count = frequent[antecedent]
            confidence = count / antecedent_count
            consequent_support = frequent[frozenset([consequent])] / transaction_count
            lift = confidence / consequent_support
            if confidence < args.min_confidence or lift < args.min_lift:
                continue
            rules.append({
                "if_bought": label_for(antecedent),
                "then_also_bought": labels[consequent],
                "together_count": count,
                "antecedent_count": antecedent_count,
                "support": f"{count / transaction_count:.3f}",
                "confidence": f"{confidence:.3f}",
                "lift": f"{lift:.2f}",
            })
    rules.sort(key=lambda r: (-float(r["lift"]), -float(r["confidence"]),
                              -int(r["together_count"]), r["if_bought"]))

    # Co-purchase network: an undirected edge for every frequent pair. Node
    # communities (shopping "bundles") come from networkx modularity when the
    # library is available; the CSVs still work without it.
    pair_counts = {s: c for s, c in frequent.items() if len(s) == 2}
    edges = []
    for itemset, count in pair_counts.items():
        a, b = sorted(itemset)
        lift = (count * transaction_count
                / (frequent[frozenset([a])] * frequent[frozenset([b])]))
        edges.append({"source": a, "target": b, "together_count": count,
                      "lift": f"{lift:.2f}",
                      "support": f"{count / transaction_count:.3f}"})
    communities: dict[str, int] = {}
    try:
        import networkx as nx
        graph = nx.Graph()
        for edge in edges:
            graph.add_edge(edge["source"], edge["target"],
                           weight=int(edge["together_count"]))
        groups = nx.community.greedy_modularity_communities(graph, weight="weight")
        for idx, group in enumerate(sorted(groups, key=len, reverse=True)):
            communities.update(dict.fromkeys(group, idx))
    except ImportError:
        pass
    degree = Counter()
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    node_rows = sorted(({
        "key": key,
        "label": labels[key],
        "basket_count": frequent[frozenset([key])],
        "degree": degree[key],
        "community": communities.get(key, ""),
    } for key in degree), key=lambda r: -int(r["basket_count"]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / f"{prefix}network_nodes.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["key", "label", "basket_count",
                                                    "degree", "community"])
        writer.writeheader()
        writer.writerows(node_rows)
    with (args.output_dir / f"{prefix}network_edges.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source", "target", "together_count",
                                                    "lift", "support"])
        writer.writeheader()
        writer.writerows(edges)
    with (args.output_dir / f"{prefix}frequent_itemsets.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["items", "size", "basket_count", "support"])
        writer.writeheader()
        writer.writerows(itemset_rows)
    with (args.output_dir / f"{prefix}association_rules.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["if_bought", "then_also_bought",
                                                    "together_count", "antecedent_count",
                                                    "support", "confidence", "lift"])
        writer.writeheader()
        writer.writerows(rules)
    largest = max((int(r["size"]) for r in itemset_rows), default=0)
    community_count = len(set(communities.values())) if communities else 0
    return (f"{len(itemset_rows)} frequent itemsets (largest size {largest}), "
            f"{len(rules)} rules, network of {len(node_rows)} nodes/"
            f"{len(edges)} links in {community_count} communities")


if __name__ == "__main__":
    main()
