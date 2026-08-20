#!/usr/bin/env python3
"""Fetch current Woolworths prices for products in the receipt history.

Searches the woolworths.com.au product API for each product, picks the best
match by name, and writes analysis/current_prices.csv comparing the live price
with the typical price paid in the receipts. Results are cached in
analysis/price_cache.json so re-runs only hit the site for stale entries.

Intended for occasional personal use: requests are throttled (default 2s apart)
and each product is one search request.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency. Install it with: python -m pip install requests") from exc

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "analysis"
SEARCH_URL = "https://www.woolworths.com.au/apis/ui/Search/products"
HOME_URL = "https://www.woolworths.com.au/"
PRODUCT_URL = "https://www.woolworths.com.au/shop/productdetails/{stockcode}"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

ABBREVIATIONS = {
    "ww": "woolworths",
    "wlwths": "woolworths",
    "bkry": "bakery",
    "ppr": "paper",
    "twl": "towel",
    "hmgnsed": "homogenised",
    "wtr": "water",
    "dbl": "double",
    "rl": "roll",
    "wht": "white",
    "tb": "tea bags",
    "ktb": "kitchen tidy bags",
}
TOKEN_SYNONYMS = {"pk": "pack", "pck": "pack"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean_term(description: str) -> str:
    """Turn a terse receipt description into a searchable phrase."""
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", description)  # WholemealSandwich -> Wholemeal Sandwich
    text = re.sub(r"(?<=[a-zA-Z])(?=\d+(?:\.\d+)?(?:g|kg|ml|l|pk|pack)\b)", " ", text, flags=re.I)
    words = [ABBREVIATIONS.get(w.lower(), w) for w in text.split()]
    return " ".join(words)


def tokens(text: str) -> list[str]:
    """Word tokens with sizes split apart, so '20x250mlPck' ~ '250mL x 20 pack'."""
    raw = re.findall(r"\d+(?:\.\d+)?|[a-z]+", text.lower())
    return [TOKEN_SYNONYMS.get(t, t) for t in raw if t != "x"]


def match_score(term: str, candidate: str) -> float:
    """F1 over name tokens (prefix matches count), so a candidate stuffed with
    unrelated words scores below one that is just the product."""
    wanted = set(tokens(term))
    have = set(tokens(candidate))
    if not wanted or not have:
        return 0.0

    def covered(needles: set[str], hay: set[str]) -> int:
        return sum(any(h == n or (len(n) >= 3 and h.startswith(n)) or (len(h) >= 3 and n.startswith(h))
                       for h in hay) for n in needles)

    recall = covered(wanted, have) / len(wanted)
    precision = covered(have, wanted) / len(have)
    if not recall or not precision:
        return 0.0
    return 2 * precision * recall / (precision + recall)


class WooliesClient:
    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.last_request = 0.0
        self.session = self._new_session()

    @staticmethod
    def _new_session() -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-AU,en;q=0.9",
        })
        session.get(HOME_URL, timeout=30)  # collect the cookies the API expects
        return session

    def search(self, term: str) -> list[dict]:
        wait = self.delay - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        payload = {
            "Filters": [],
            "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={term}",
            "PageNumber": 1,
            "PageSize": 24,
            "SearchTerm": term,
            "SortType": "TraderRelevance",
        }
        headers = {"Origin": "https://www.woolworths.com.au",
                   "Referer": f"https://www.woolworths.com.au/shop/search/products?searchTerm={term}"}
        for attempt in (1, 2):
            response = self.session.post(SEARCH_URL, json=payload, headers=headers, timeout=30)
            self.last_request = time.monotonic()
            if response.ok and "json" in (response.headers.get("content-type") or ""):
                groups = response.json().get("Products") or []
                return [p for g in groups for p in (g.get("Products") or [])]
            if attempt == 1:  # likely an expired session cookie; refresh once
                time.sleep(3)
                self.session = self._new_session()
        raise RuntimeError(f"search blocked (HTTP {response.status_code}); try again later")


def load_products(args: argparse.Namespace) -> list[str]:
    if args.terms:
        return args.terms
    if args.source == "shopping":
        rows = read_csv(ANALYSIS / "suggested_shopping_list.csv")
        if not rows:
            raise SystemExit("No suggested_shopping_list.csv; run analyze_groceries.py first "
                             "or use --source products")
        return [r["description"] for r in rows]
    rows = read_csv(ANALYSIS / "product_patterns.csv")
    if not rows:
        raise SystemExit("No product_patterns.csv; run analyze_groceries.py first")
    return [r["description"] for r in rows if int(r["purchase_dates"]) >= args.min_purchases]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=("shopping", "products"), default="shopping",
                        help="shopping = suggested shopping list (default); "
                             "products = recurring products from product_patterns.csv")
    parser.add_argument("--min-purchases", type=int, default=3,
                        help="With --source products, only fetch products bought this many times (default 3)")
    parser.add_argument("--terms", nargs="*", help="Ad-hoc search terms instead of a CSV source")
    parser.add_argument("--limit", type=int, help="Fetch at most this many products")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between requests (default 2)")
    parser.add_argument("--max-age-hours", type=float, default=24.0,
                        help="Reuse cached results younger than this (default 24h); 0 forces refresh")
    args = parser.parse_args()

    descriptions = load_products(args)
    if args.limit:
        descriptions = descriptions[: args.limit]
    typical = {r["description"]: r["typical_unit_price"]
               for r in read_csv(ANALYSIS / "product_patterns.csv")}

    cache_path = ANALYSIS / "price_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    now = datetime.now(timezone.utc)

    client: WooliesClient | None = None
    results: list[dict[str, object]] = []
    fetched = failures = 0
    for description in descriptions:
        term = clean_term(description)
        entry = cache.get(term)
        if entry and args.max_age_hours > 0:
            age_hours = (now - datetime.fromisoformat(entry["fetched_at"])).total_seconds() / 3600
            if age_hours <= args.max_age_hours:
                results.append({**entry["row"], "description": description})
                continue
        if client is None:
            print("Connecting to woolworths.com.au ...")
            client = WooliesClient(args.delay)
        try:
            candidates = client.search(term)
            if not candidates:
                # Sizes the store doesn't sell online often blank the search;
                # retry on the name alone and let scoring sort out the size.
                slim = re.sub(r"\b\d+(?:\.\d+)?\s*(?:g|kg|ml|l|pk|pack)\b", "", term, flags=re.I).strip()
                if slim and slim.lower() != term.lower():
                    candidates = client.search(slim)
            fetched += 1
        except Exception as exc:
            failures += 1
            print(f"  FAILED  {description}: {exc}", file=sys.stderr)
            continue

        best, best_score = None, 0.0
        for product in candidates:
            if not product or product.get("Price") is None:
                continue
            label = f"{product.get('DisplayName') or product.get('Name', '')} {product.get('PackageSize', '')}"
            score = match_score(term, label)
            if score > best_score:
                best, best_score = product, score
        if best is None:
            row = {"search_term": term, "matched_name": "", "package_size": "", "stockcode": "",
                   "price": "", "was_price": "", "unit_price": "", "on_special": "",
                   "available": "", "match_score": "0.00", "url": ""}
            print(f"  no match  {description}")
        else:
            row = {
                "search_term": term,
                "matched_name": best.get("DisplayName") or best.get("Name", ""),
                "package_size": best.get("PackageSize", ""),
                "stockcode": best.get("Stockcode", ""),
                "price": f"{best['Price']:.2f}",
                "was_price": f"{best.get('WasPrice') or best['Price']:.2f}",
                "unit_price": best.get("CupString", ""),
                "on_special": "yes" if best.get("IsOnSpecial") else "no",
                "available": "yes" if best.get("IsAvailable", True) else "no",
                "match_score": f"{best_score:.2f}",
                "url": PRODUCT_URL.format(stockcode=best.get("Stockcode", "")),
            }
            special = "  ON SPECIAL" if best.get("IsOnSpecial") else ""
            print(f"  ${best['Price']:>6.2f}  {description}  ->  {row['matched_name']} "
                  f"{row['package_size']}{special}")
        cache[term] = {"fetched_at": now.isoformat(), "row": row}
        results.append({**row, "description": description})

    ANALYSIS.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    for row in results:
        paid = typical.get(str(row["description"]), "")
        row["typical_paid"] = paid
        if paid and row.get("price"):
            change = float(row["price"]) - float(paid)
            row["price_vs_paid"] = f"{change:+.2f}"
            row["price_vs_paid_pct"] = f"{change / float(paid):+.1%}" if float(paid) else ""
        else:
            row["price_vs_paid"] = row["price_vs_paid_pct"] = ""

    out_path = ANALYSIS / "current_prices.csv"
    fields = ["description", "search_term", "matched_name", "package_size", "stockcode",
              "price", "was_price", "unit_price", "on_special", "available",
              "typical_paid", "price_vs_paid", "price_vs_paid_pct", "match_score", "url"]
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    cached_count = len(results) - fetched - failures + failures  # rows served from cache
    matched = sum(1 for r in results if r["matched_name"])
    weak = sum(1 for r in results if r["matched_name"] and float(str(r["match_score"])) < 0.6)
    print(f"\n{len(results)} products: {matched} matched ({weak} weak matches to double-check), "
          f"{fetched} fetched live, {len(results) - fetched} from cache, {failures} failed.")
    print(f"Wrote {out_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
