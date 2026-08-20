#!/usr/bin/env python3
"""Map receipt product descriptions onto grocery category types.

Categories follow the classic groceries-dataset taxonomy (whole milk,
rolls/buns, root vegetables, ...) with a few extra labels (clothing,
stationery, pharmacy, electrical) for non-grocery items the taxonomy
does not cover. Run as a script to write analysis/product_categories.csv
and analysis/category_spend.csv and to report anything left unmapped.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

# First matching rule wins. Non-food rules run first so scent and packaging
# words ("Bref ... Lemon", "I Was a Milk Bottle" bin bags) never land in food
# categories; fresh produce runs last for the same reason.
RULES: list[tuple[str, str]] = [
    # receipt discount/offer lines (negative amounts; excluded from spend anyway)
    (r"^(any|buy) \d+ for|\boffer?\b|offe$|member price|price saving", "discounts"),
    # paper, wraps & bags
    (r"paper towel|ppr twl|p/twl|papertowel|towel dbl|towel dl|kitchen towel",
     "kitchen towels"),
    (r"toilet tissue|t/tiss|toilet paper", "hygiene articles"),
    (r"freezer bag|cling|foil\b|baking paper", "cling film/bags"),
    (r"garbage bag|tidy bag|ktb|bin \d+l|compostable bin", "bags"),
    (r"shopping bag|tote bag|chiller bag|paper bag", "shopping bags"),
    # cleaning & laundry
    (r"bref", "toilet cleaner"),
    (r"dish ?tabs|dishmatic liquid|dishwashing|ultra a\w*bac|finish (all|ultimate)",
     "dish cleaner"),
    (r"laundry|omo ", "detergent"),
    (r"fluffy|comfort in-?wash|softener", "softener"),
    (r"mop|bucket|scourer|scrub brush|sprayer|microfibre|superwipe|supa wipes|duster"
     r"|dustpan|glove|peg\b|pegs|dish handle|dish refills|scrubbee|toilet/tidy"
     r"|tile and grout|odour|zenzone|mortein|raid |roach|snail|air ?wick|vipoo"
     r"|extenable|extendable|cotton refill", "house keeping products"),
    (r"disinf|dsnfctnt|diso |wipes|windex|w/purp clnr|m/purp clnr|cleaner", "cleaner"),
    (r"matches|firelighter", "candles"),
    (r"charcoal|bbq fuel", "seasonal products"),
    # personal care
    (r"toothpaste|toothbrush|tpaste|dental", "dental care"),
    (r"pads |extraplus|kotex|sanitary", "female sanitary products"),
    (r"baby powder|baby ", "baby cosmetics"),
    (r"shampoo|shmp|conditioner|cond\d|hair", "hair spray"),
    (r"roll on|deodorant|48hr fresh|cotton tips", "hygiene articles"),
    (r"soap|body wash|shower gel|bw |hwash|hand ?wash|shwr gel|\blhw", "soap"),
    (r"vaseline|intensive care|lip balm|skin", "skin care"),
    (r"nurofen|ibuprofen|panadol", "pharmacy"),
    # household & other
    (r"decor |microsafe|tellfresh|m/cooker|cookware", "cookware"),
    (r"plate|mug\b|corelle|dishes", "dishes"),
    (r"toothpick|utensil", "kitchen utensil"),
    (r"light bulb|globe\b", "light bulbs"),
    (r"pencil|highlighter|paperclick", "stationery"),
    (r"goldair|heater|fan\b", "electrical"),
    (r"fertilis|flower soil|potting", "flower soil/fertilizer"),
    (r"rainboot|bikini|bra\b|sundress|poncho|sock|thong|ctn lc|hb brushd"
     r"|bootsock|classics ba|utility k|lce wf", "clothing"),
    # bakery
    (r"croissant|finger buns", "pastry"),
    (r"rolls|buns", "rolls/buns"),
    (r"wholemeal|sandwich.*(650g|700g|750g)|wonder", "brown bread"),
    # dairy
    (r"milk powder", "UHT-milk"),
    (r"yoghurt|yogurt|yopro|\byog\b", "yogurt"),
    (r"milk", "whole milk"),
    # breakfast & pantry
    (r"cereal|weet ?-?bix|corn flakes|muesli|oats|scht original", "cereals"),
    (r"indo mie|noodles", "Instant food products"),
    (r"soup", "soups"),
    (r"passata|pasta sauce|ketchup", "sauces"),
    (r"flour(?!.*tortilla)", "flour"),
    (r"sugar(?! free)", "sugar"),
    (r"rice cracker|sakata|peckish|pringles|chips \d|multipackchips|crisps", "salty snack"),
    (r"popcorn", "popcorn"),
    (r"\bnut\b|peanut rst", "nut snack"),
    (r"\bsalt\b|sea salt", "salt"),
    (r"olive oil|vegetable oil|canola", "oil"),
    (r"garlic powder|turmeric|garlic minced|pepper ground|spice", "spices"),
    (r"flavouring|vanilla essence|baking", "baking powder"),
    (r"honey", "honey"),
    (r"peanut butter", "sweet spreads"),
    (r"spread original|margarine", "margarine"),
    (r"kidney ?beans|pea split|split pea|lentil", "other vegetables"),
    (r"biscuit|bsct|scotch finger|choc(olate)? ripple|anzac", "long life bakery product"),
    (r"raffaello|ferrero", "specialty chocolate"),
    (r"sour patch|candy|lollies", "candy"),
    # frozen & chilled treats
    (r"superfries|crnch.*chips|crnch.*cut|potato fries|sweet potato fries|gldn crnch",
     "frozen potato products"),
    (r"steam fresh|frozen veg", "frozen vegetables"),
    (r"choc bars|choc coated sticks|caramilk sticks|ice ?cream", "ice cream"),
    # drinks
    (r"cord(ial)?\b", "syrup"),
    (r"juice|nectar|mango drink|fruit drink|prima drink", "fruit/vegetable juice"),
    (r"spring w(a)?t(e)?r|pump water|bottled water", "bottled water"),
    (r"coca cola|fanta|schweppes|bundaberg|soda|lemonade", "soda"),
    (r"milo.*cereal", "cereals"),
    (r"milo", "cocoa drinks"),
    (r"up&go|up & go", "misc. beverages"),
    (r"tea bags|quality tea|tea black|lemon & ginger tb", "tea"),
    (r"coffee", "coffee"),
    # meat
    (r"beef mince|beef", "beef"),
    (r"sausage", "sausage"),
    (r"chicken", "chicken"),
    (r"spam|ham classic", "ham"),
    # produce (last: flavour words above must win first)
    (r"apple|pear packham", "pip fruit"),
    (r"lemon|mandarin|orange navel|lime\b", "citrus fruit"),
    (r"grape", "grapes"),
    (r"berries|strawberr|blueberr", "berries"),
    (r"banana|mango|pineapple|papaya|passionfruit|kiwifruit|coconut|avocado",
     "tropical fruit"),
    (r"carrot|beetroot|ginger|potato washed|sweet potato\b", "root vegetables"),
    (r"garlic|onion", "onions"),
    (r"pumpkin|eggplant|capsicum|cucumber|celery|leek|mushroom|corn|tomato|beanette"
     r"|broccoli|cauliflower|zucchini|lettuce|spinach", "other vegetables"),
]

COMPILED = [(re.compile(pattern, re.I), category) for pattern, category in RULES]


def categorize(description: str) -> str:
    text = description.lower()
    for pattern, category in COMPILED:
        if pattern.search(text):
            return category
    return "unmapped"


def product_key(description: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", description.lower())


def main() -> None:
    root = Path(__file__).resolve().parent
    analysis = root / "analysis"
    analysis.mkdir(exist_ok=True)
    with (root / "parsed" / "receipts.csv").open(encoding="utf-8-sig", newline="") as handle:
        receipts = list(csv.DictReader(handle))
    with (root / "parsed" / "items.csv").open(encoding="utf-8-sig", newline="") as handle:
        items = list(csv.DictReader(handle))
    grocery_ids = {r["receipt_id"] for r in receipts
                   if not r["store_name"].lower().startswith("big w")
                   and r["parse_status"] != "duplicate"}

    best: dict[str, str] = {}
    for item in items:
        key = product_key(item["description"])
        if len(item["description"]) > len(best.get(key, "")):
            best[key] = item["description"]

    assignments = {key: categorize(desc) for key, desc in best.items()}
    rows = sorted(({"key": key, "description": best[key], "category": category}
                   for key, category in assignments.items()),
                  key=lambda r: (r["category"], r["description"]))
    with (analysis / "product_categories.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["key", "description", "category"])
        writer.writeheader()
        writer.writerows(rows)

    spend: dict[str, Decimal] = defaultdict(Decimal)
    lines: dict[str, int] = defaultdict(int)
    total = Decimal("0")
    for item in items:
        if item["receipt_id"] not in grocery_ids or Decimal(item["line_total"]) <= 0:
            continue
        category = assignments[product_key(item["description"])]
        spend[category] += Decimal(item["line_total"])
        lines[category] += 1
        total += Decimal(item["line_total"])
    spend_rows = [{
        "category": category,
        "spend": f"{amount:.2f}",
        "line_items": lines[category],
        "share": f"{amount / total:.3f}",
    } for category, amount in sorted(spend.items(), key=lambda kv: -kv[1])]
    with (analysis / "category_spend.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "spend", "line_items", "share"])
        writer.writeheader()
        writer.writerows(spend_rows)

    unmapped = [r for r in rows if r["category"] == "unmapped"]
    print(f"{len(best)} products -> {len(spend_rows)} categories "
          f"({len(unmapped)} unmapped) -> {analysis / 'category_spend.csv'}")
    for row in unmapped:
        print("  unmapped:", row["description"])


if __name__ == "__main__":
    main()
