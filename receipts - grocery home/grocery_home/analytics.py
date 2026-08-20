"""Pure analytics services for Grocery Home.

The calculation functions in this module deliberately operate on small,
immutable facts rather than SQLAlchemy objects.  This keeps money arithmetic
exact, makes the rules straightforward to test, and lets the web layer publish
one complete analytics snapshot instead of exposing half-refreshed tables.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Hashable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from categorize import categorize as _legacy_categorize
except ImportError:  # pragma: no cover - only relevant when packaged alone
    def _legacy_categorize(_description: str) -> str:
        return "unmapped"


ELIGIBLE_STATUSES = frozenset({"complete", "confirmed"})
NON_FORECAST_CATEGORIES = frozenset(
    {"discounts", "shopping bags", "clothing", "unmapped"}
)


def _household_today() -> date:
    try:
        household_zone = ZoneInfo("Australia/Sydney")
    except ZoneInfoNotFoundError:  # pragma: no cover - tzdata is a dependency
        household_zone = timezone(timedelta(hours=10), name="Australia/Sydney")
    return datetime.now(household_zone).date()


@dataclass(frozen=True, slots=True)
class ReceiptFact:
    receipt_id: Hashable
    purchase_date: date | None
    total_cents: int
    merchant: str = ""
    is_grocery: bool = True
    status: str = "complete"
    duplicate_of_id: Hashable | None = None
    is_duplicate: bool = False


@dataclass(frozen=True, slots=True)
class ItemFact:
    receipt_id: Hashable
    description: str
    line_total_cents: int
    quantity: Decimal = Decimal("1")
    product_number: str | None = None
    category: str | None = None


@dataclass(frozen=True, slots=True)
class SpendBucket:
    period_start: date
    period_end: date
    spend_cents: int
    trips: int
    has_receipts: bool


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    category: str
    spend_cents: int
    line_items: int
    share: Decimal


@dataclass(frozen=True, slots=True)
class ProductCadence:
    product_key: str
    description: str
    product_number: str | None
    purchase_dates: int
    last_bought: date
    typical_interval_days: int | None
    typical_quantity: Decimal
    typical_unit_price_cents: int
    expected_purchase_cost_cents: int
    active: bool
    estimated_due: date | None
    confidence: str


@dataclass(frozen=True, slots=True)
class DueSoonSuggestion:
    product_key: str
    description: str
    estimated_due: date
    days_from_as_of: int
    quantity: Decimal
    estimated_unit_cost_cents: int
    expected_cost_cents: int
    confidence: str


@dataclass(frozen=True, slots=True)
class PriceHistoryPoint:
    product_key: str
    description: str
    purchase_date: date
    unit_price_cents: int
    quantity: Decimal
    line_total_cents: int


@dataclass(frozen=True, slots=True)
class AssociationInsight:
    antecedent_keys: tuple[str, ...]
    antecedent_labels: tuple[str, ...]
    consequent_key: str
    consequent_label: str
    together_count: int
    support: Decimal
    confidence: Decimal
    lift: Decimal


@dataclass(frozen=True, slots=True)
class InsightStatus:
    status: str
    message: str
    sample_size: int
    minimum_required: int


@dataclass(frozen=True, slots=True)
class AssociationResult:
    status: InsightStatus
    insights: tuple[AssociationInsight, ...] = ()


@dataclass(frozen=True, slots=True)
class Overview:
    current_month_spend_cents: int
    previous_month_spend_cents: int
    month_change_percent: Decimal | None
    recorded_spend_cents: int
    average_trip_cents: int
    receipt_count: int
    forecast_30d_cents: int
    forecast_basis_days: int
    due_soon_count: int
    due_soon_cost_cents: int
    data_start: date | None
    data_end: date | None


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshotData:
    generated_at: datetime
    as_of: date
    overview: Overview
    monthly: tuple[SpendBucket, ...]
    weekly: tuple[SpendBucket, ...]
    categories: tuple[CategoryTotal, ...]
    products: tuple[ProductCadence, ...]
    suggestions: tuple[DueSoonSuggestion, ...]
    price_history: tuple[PriceHistoryPoint, ...]
    association_rules: AssociationResult
    advanced_insights: Mapping[str, InsightStatus]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe payload while retaining cents as integers."""
        return _json_safe(asdict(self))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _status_value(value: Any) -> str:
    if value is None:
        return "complete"
    return str(getattr(value, "value", value)).lower()


def normalize_description(description: str) -> str:
    """Normalize harmless receipt typography without inventing product aliases."""
    return re.sub(r"[^a-z0-9]+", "", description.casefold())


def product_identity(product_number: str | int | None, description: str) -> str:
    """Prefer the retailer SKU, falling back to a normalized description."""
    number = str(product_number or "").strip()
    if number and number not in {"0", "none", "null"}:
        return f"sku:{number.casefold()}"
    return f"name:{normalize_description(description)}"


def eligible_receipts(receipts: Iterable[ReceiptFact]) -> tuple[ReceiptFact, ...]:
    """Apply the single canonical analytics eligibility policy."""
    return tuple(
        receipt
        for receipt in receipts
        if receipt.is_grocery
        and not receipt.is_duplicate
        and receipt.duplicate_of_id is None
        and receipt.purchase_date is not None
        and _status_value(receipt.status) in ELIGIBLE_STATUSES
    )


def monthly_spend(receipts: Iterable[ReceiptFact]) -> tuple[SpendBucket, ...]:
    eligible = eligible_receipts(receipts)
    if not eligible:
        return ()
    grouped: dict[tuple[int, int], list[int]] = defaultdict(list)
    for receipt in eligible:
        grouped[(receipt.purchase_date.year, receipt.purchase_date.month)].append(
            receipt.total_cents
        )
    cursor = date(
        min(receipt.purchase_date for receipt in eligible).year,
        min(receipt.purchase_date for receipt in eligible).month,
        1,
    )
    last_date = max(receipt.purchase_date for receipt in eligible)
    last = date(last_date.year, last_date.month, 1)
    rows: list[SpendBucket] = []
    while cursor <= last:
        next_month = (
            date(cursor.year + 1, 1, 1)
            if cursor.month == 12
            else date(cursor.year, cursor.month + 1, 1)
        )
        amounts = grouped.get((cursor.year, cursor.month), [])
        rows.append(
            SpendBucket(
                period_start=cursor,
                period_end=next_month - timedelta(days=1),
                spend_cents=sum(amounts),
                trips=len(amounts),
                has_receipts=bool(amounts),
            )
        )
        cursor = next_month
    return tuple(rows)


def weekly_spend(receipts: Iterable[ReceiptFact]) -> tuple[SpendBucket, ...]:
    eligible = eligible_receipts(receipts)
    if not eligible:
        return ()
    grouped: dict[date, list[int]] = defaultdict(list)
    for receipt in eligible:
        start = receipt.purchase_date - timedelta(days=receipt.purchase_date.weekday())
        grouped[start].append(receipt.total_cents)
    cursor = min(grouped)
    last = max(grouped)
    rows: list[SpendBucket] = []
    while cursor <= last:
        amounts = grouped.get(cursor, [])
        rows.append(
            SpendBucket(
                period_start=cursor,
                period_end=cursor + timedelta(days=6),
                spend_cents=sum(amounts),
                trips=len(amounts),
                has_receipts=bool(amounts),
            )
        )
        cursor += timedelta(days=7)
    return tuple(rows)


def _eligible_item_rows(
    receipts: Iterable[ReceiptFact], items: Iterable[ItemFact]
) -> tuple[tuple[ItemFact, ReceiptFact], ...]:
    by_id = {receipt.receipt_id: receipt for receipt in eligible_receipts(receipts)}
    return tuple(
        (item, by_id[item.receipt_id])
        for item in items
        if item.receipt_id in by_id and item.line_total_cents > 0
    )


def category_breakdown(
    receipts: Iterable[ReceiptFact],
    items: Iterable[ItemFact],
    *,
    categorizer: Callable[[str], str] = _legacy_categorize,
) -> tuple[CategoryTotal, ...]:
    spend: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for item, _receipt in _eligible_item_rows(receipts, items):
        category = item.category or categorizer(item.description)
        spend[category] += item.line_total_cents
        counts[category] += 1
    total = sum(spend.values())
    rows = [
        CategoryTotal(
            category=category,
            spend_cents=amount,
            line_items=counts[category],
            share=(Decimal(amount) / Decimal(total) if total else Decimal("0")),
        )
        for category, amount in spend.items()
    ]
    rows.sort(key=lambda row: (-row.spend_cents, row.category.casefold()))
    return tuple(rows)


def _median_decimal(values: Sequence[Decimal], default: Decimal) -> Decimal:
    if not values:
        return default
    return Decimal(str(statistics.median(values)))


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def product_cadence(
    receipts: Iterable[ReceiptFact],
    items: Iterable[ItemFact],
    *,
    as_of: date,
    horizon_days: int = 30,
    categorizer: Callable[[str], str] = _legacy_categorize,
) -> tuple[tuple[ProductCadence, ...], tuple[DueSoonSuggestion, ...]]:
    """Calculate recurring purchase cadence and quantity-aware due costs."""
    rows = _eligible_item_rows(receipts, items)
    if not rows:
        return (), ()
    data_end = max(receipt.purchase_date for _item, receipt in rows)
    grouped: dict[str, list[tuple[ItemFact, ReceiptFact]]] = defaultdict(list)
    for item, receipt in rows:
        category = item.category or categorizer(item.description)
        if category.casefold() in NON_FORECAST_CATEGORIES:
            continue
        key = product_identity(item.product_number, item.description)
        if key != "name:":
            grouped[key].append((item, receipt))

    products: list[ProductCadence] = []
    suggestions: list[DueSoonSuggestion] = []
    horizon_end = as_of + timedelta(days=horizon_days)
    for key, product_rows in grouped.items():
        per_receipt: dict[Hashable, tuple[date, Decimal, int]] = {}
        for item, receipt in product_rows:
            quantity = item.quantity if item.quantity > 0 else Decimal("1")
            if receipt.receipt_id in per_receipt:
                bought, prior_quantity, prior_cents = per_receipt[receipt.receipt_id]
                per_receipt[receipt.receipt_id] = (
                    bought,
                    prior_quantity + quantity,
                    prior_cents + item.line_total_cents,
                )
            else:
                per_receipt[receipt.receipt_id] = (
                    receipt.purchase_date,
                    quantity,
                    item.line_total_cents,
                )
        purchase_rows = list(per_receipt.values())
        dates = sorted({row[0] for row in purchase_rows})
        quantities = [row[1] for row in purchase_rows if row[1] > 0]
        unit_prices = [
            Decimal(row[2]) / row[1] for row in purchase_rows if row[1] > 0
        ]
        typical_quantity = _median_decimal(quantities, Decimal("1"))
        typical_unit_price = _median_decimal(unit_prices, Decimal("0"))
        expected_cost = _round_cents(typical_quantity * typical_unit_price)
        intervals = [
            (later - earlier).days
            for earlier, later in zip(dates, dates[1:])
            if later > earlier
        ]
        interval = (
            max(1, int(Decimal(str(statistics.median(intervals))).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )))
            if intervals
            else None
        )
        active = bool(interval) and (data_end - dates[-1]).days <= max(
            90, interval * 3
        )
        due = dates[-1] + timedelta(days=interval) if interval else None
        if active and due is not None:
            while due < as_of:
                due += timedelta(days=interval)
        purchase_date_count = len(dates)
        confidence = (
            "high"
            if purchase_date_count >= 5
            else "medium"
            if purchase_date_count >= 3
            else "low"
        )
        representative = max(
            (item.description for item, _receipt in product_rows),
            key=lambda value: (len(value), value),
        )
        product_number = next(
            (
                str(item.product_number)
                for item, _receipt in product_rows
                if item.product_number
            ),
            None,
        )
        product = ProductCadence(
            product_key=key,
            description=representative,
            product_number=product_number,
            purchase_dates=purchase_date_count,
            last_bought=dates[-1],
            typical_interval_days=interval,
            typical_quantity=typical_quantity,
            typical_unit_price_cents=_round_cents(typical_unit_price),
            expected_purchase_cost_cents=expected_cost,
            active=active,
            estimated_due=due if active else None,
            confidence=confidence,
        )
        products.append(product)
        if (
            purchase_date_count >= 2
            and active
            and due is not None
            and due <= horizon_end
        ):
            suggestions.append(
                DueSoonSuggestion(
                    product_key=key,
                    description=representative,
                    estimated_due=due,
                    days_from_as_of=(due - as_of).days,
                    quantity=typical_quantity,
                    estimated_unit_cost_cents=_round_cents(typical_unit_price),
                    expected_cost_cents=expected_cost,
                    confidence=confidence,
                )
            )
    products.sort(key=lambda row: (-row.purchase_dates, row.description.casefold()))
    suggestions.sort(key=lambda row: (row.estimated_due, row.description.casefold()))
    return tuple(products), tuple(suggestions)


def price_history(
    receipts: Iterable[ReceiptFact], items: Iterable[ItemFact]
) -> tuple[PriceHistoryPoint, ...]:
    rows: list[PriceHistoryPoint] = []
    for item, receipt in _eligible_item_rows(receipts, items):
        quantity = item.quantity if item.quantity > 0 else Decimal("1")
        rows.append(
            PriceHistoryPoint(
                product_key=product_identity(item.product_number, item.description),
                description=item.description,
                purchase_date=receipt.purchase_date,
                unit_price_cents=_round_cents(
                    Decimal(item.line_total_cents) / quantity
                ),
                quantity=quantity,
                line_total_cents=item.line_total_cents,
            )
        )
    rows.sort(
        key=lambda row: (row.product_key, row.purchase_date, row.description.casefold())
    )
    return tuple(rows)


def spending_run_rate(
    receipts: Iterable[ReceiptFact], *, horizon_days: int = 30, max_days: int = 90
) -> tuple[int, int]:
    """Return a horizon forecast and its actual observation-day denominator.

    Unlike a fixed 90-day denominator, this behaves sensibly for a household
    with only a few weeks of imported history.
    """
    eligible = eligible_receipts(receipts)
    if not eligible:
        return 0, 0
    first = min(receipt.purchase_date for receipt in eligible)
    latest = max(receipt.purchase_date for receipt in eligible)
    observed_days = min(max_days, max(1, (latest - first).days + 1))
    window_start = latest - timedelta(days=observed_days - 1)
    spend = sum(
        receipt.total_cents
        for receipt in eligible
        if window_start <= receipt.purchase_date <= latest
    )
    forecast = _round_cents(
        Decimal(spend) * Decimal(horizon_days) / Decimal(observed_days)
    )
    return forecast, observed_days


def overview(
    receipts: Iterable[ReceiptFact],
    suggestions: Iterable[DueSoonSuggestion],
    *,
    as_of: date,
) -> Overview:
    eligible = eligible_receipts(receipts)
    due = tuple(suggestions)
    current_start = date(as_of.year, as_of.month, 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = date(previous_end.year, previous_end.month, 1)
    current = sum(
        row.total_cents
        for row in eligible
        if current_start <= row.purchase_date <= as_of
    )
    previous = sum(
        row.total_cents
        for row in eligible
        if previous_start <= row.purchase_date <= previous_end
    )
    change = (
        (Decimal(current - previous) / Decimal(previous) * Decimal("100"))
        if previous
        else None
    )
    total = sum(row.total_cents for row in eligible)
    forecast, basis = spending_run_rate(eligible)
    return Overview(
        current_month_spend_cents=current,
        previous_month_spend_cents=previous,
        month_change_percent=change,
        recorded_spend_cents=total,
        average_trip_cents=(
            _round_cents(Decimal(total) / Decimal(len(eligible))) if eligible else 0
        ),
        receipt_count=len(eligible),
        forecast_30d_cents=forecast,
        forecast_basis_days=basis,
        due_soon_count=len(due),
        due_soon_cost_cents=sum(row.expected_cost_cents for row in due),
        data_start=min((row.purchase_date for row in eligible), default=None),
        data_end=max((row.purchase_date for row in eligible), default=None),
    )


def mine_association_insights(
    receipts: Iterable[ReceiptFact],
    items: Iterable[ItemFact],
    *,
    minimum_baskets: int = 5,
    minimum_count: int = 2,
    minimum_confidence: Decimal = Decimal("0.30"),
    minimum_lift: Decimal = Decimal("1.20"),
    limit: int = 20,
    categorizer: Callable[[str], str] = _legacy_categorize,
) -> AssociationResult:
    """Mine association rules through the legacy, tested Apriori function."""
    eligible = {row.receipt_id for row in eligible_receipts(receipts)}
    baskets: dict[Hashable, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for item in items:
        if item.receipt_id not in eligible or item.line_total_cents <= 0:
            continue
        category = item.category or categorizer(item.description)
        if category.casefold() in NON_FORECAST_CATEGORIES:
            continue
        key = product_identity(item.product_number, item.description)
        if key == "name:":
            continue
        baskets[item.receipt_id].add(key)
        if len(item.description) > len(labels.get(key, "")):
            labels[key] = item.description
    transactions = [frozenset(basket) for basket in baskets.values() if basket]
    if len(transactions) < minimum_baskets:
        return AssociationResult(
            status=InsightStatus(
                status="insufficient_history",
                message=(
                    f"Add {minimum_baskets - len(transactions)} more grocery "
                    "receipts to unlock basket patterns."
                ),
                sample_size=len(transactions),
                minimum_required=minimum_baskets,
            )
        )
    try:
        from association_rules import apriori

        frequent = apriori(transactions, max(1, minimum_count))
    except Exception as exc:  # a snapshot refresh must not take down the app
        return AssociationResult(
            status=InsightStatus(
                status="unavailable",
                message=f"Basket patterns could not be refreshed: {type(exc).__name__}.",
                sample_size=len(transactions),
                minimum_required=minimum_baskets,
            )
        )
    basket_count = Decimal(len(transactions))
    insights: list[AssociationInsight] = []
    for itemset, together_count in frequent.items():
        if len(itemset) < 2:
            continue
        for consequent in itemset:
            antecedent = itemset - {consequent}
            antecedent_count = frequent.get(antecedent, 0)
            consequent_count = frequent.get(frozenset({consequent}), 0)
            if not antecedent_count or not consequent_count:
                continue
            confidence = Decimal(together_count) / Decimal(antecedent_count)
            lift = confidence / (Decimal(consequent_count) / basket_count)
            if confidence < minimum_confidence or lift < minimum_lift:
                continue
            antecedent_keys = tuple(sorted(antecedent))
            insights.append(
                AssociationInsight(
                    antecedent_keys=antecedent_keys,
                    antecedent_labels=tuple(labels[key] for key in antecedent_keys),
                    consequent_key=consequent,
                    consequent_label=labels[consequent],
                    together_count=together_count,
                    support=Decimal(together_count) / basket_count,
                    confidence=confidence,
                    lift=lift,
                )
            )
    insights.sort(
        key=lambda row: (
            -row.lift,
            -row.confidence,
            -row.together_count,
            row.antecedent_labels,
            row.consequent_label,
        )
    )
    message = (
        f"{len(insights[:limit])} useful basket patterns found."
        if insights
        else "There is enough history, but no strong basket patterns yet."
    )
    return AssociationResult(
        status=InsightStatus(
            status="ready",
            message=message,
            sample_size=len(transactions),
            minimum_required=minimum_baskets,
        ),
        insights=tuple(insights[:limit]),
    )


def advanced_insight_status(
    receipts: Iterable[ReceiptFact], *, minimum_weeks: int = 8
) -> Mapping[str, InsightStatus]:
    eligible = eligible_receipts(receipts)
    weeks = {
        row.purchase_date - timedelta(days=row.purchase_date.weekday())
        for row in eligible
    }
    if len(weeks) < minimum_weeks:
        numerical = InsightStatus(
            status="insufficient_history",
            message=(
                f"Add receipts across {minimum_weeks - len(weeks)} more weeks "
                "to unlock advanced trend modelling."
            ),
            sample_size=len(weeks),
            minimum_required=minimum_weeks,
        )
    else:
        numerical = InsightStatus(
            status="ready",
            message="Advanced trend modelling has enough weekly history.",
            sample_size=len(weeks),
            minimum_required=minimum_weeks,
        )
    return {"numerical_patterns": numerical}


def build_analytics_snapshot(
    receipts: Iterable[ReceiptFact],
    items: Iterable[ItemFact],
    *,
    as_of: date | None = None,
    generated_at: datetime | None = None,
    horizon_days: int = 30,
) -> AnalyticsSnapshotData:
    """Build every basic view in memory, ready for one atomic DB insert."""
    receipts = tuple(receipts)
    items = tuple(items)
    as_of = as_of or _household_today()
    generated_at = generated_at or datetime.now(timezone.utc)
    products, suggestions = product_cadence(
        receipts, items, as_of=as_of, horizon_days=horizon_days
    )
    associations = mine_association_insights(receipts, items)
    advanced = dict(advanced_insight_status(receipts))
    advanced["association_rules"] = associations.status
    return AnalyticsSnapshotData(
        generated_at=generated_at,
        as_of=as_of,
        overview=overview(receipts, suggestions, as_of=as_of),
        monthly=monthly_spend(receipts),
        weekly=weekly_spend(receipts),
        categories=category_breakdown(receipts, items),
        products=products,
        suggestions=suggestions,
        price_history=price_history(receipts, items),
        association_rules=associations,
        advanced_insights=advanced,
    )


def _value(record: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(record, name):
            return getattr(record, name)
        if isinstance(record, Mapping) and name in record:
            return record[name]
    return default


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _decimal_value(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def receipt_facts(records: Iterable[Any]) -> tuple[ReceiptFact, ...]:
    """Adapt mappings or ORM receipts to the stable analytics fact type."""
    facts: list[ReceiptFact] = []
    for record in records:
        cents = _value(record, "total_cents")
        if cents is None:
            cents = _round_cents(_decimal_value(_value(record, "total")) * 100)
        merchant = str(
            _value(record, "merchant", "store_name", "merchant_name", default="")
        )
        grocery_value = _value(record, "is_grocery")
        is_grocery = (
            bool(grocery_value)
            if grocery_value is not None
            else not merchant.casefold().startswith("big w")
        )
        duplicate_of = _value(
            record, "duplicate_of_id", "duplicate_receipt_id", default=None
        )
        purchase_value = _value(
            record, "purchase_date", "purchased_at", "transaction_date"
        )
        facts.append(
            ReceiptFact(
                receipt_id=_value(record, "id", "receipt_id"),
                purchase_date=(
                    _date_value(purchase_value)
                    if purchase_value not in (None, "")
                    else None
                ),
                total_cents=int(cents),
                merchant=merchant,
                is_grocery=is_grocery,
                status=_status_value(
                    _value(record, "status", "parse_status", default="complete")
                ),
                duplicate_of_id=duplicate_of,
                is_duplicate=bool(
                    _value(record, "is_duplicate", default=False)
                ),
            )
        )
    return tuple(facts)


def item_facts(records: Iterable[Any]) -> tuple[ItemFact, ...]:
    """Adapt mappings or ORM line items to the stable analytics fact type."""
    facts: list[ItemFact] = []
    for record in records:
        cents = _value(record, "line_total_cents", "total_cents")
        if cents is None:
            cents = _round_cents(
                _decimal_value(_value(record, "line_total", "total")) * 100
            )
        facts.append(
            ItemFact(
                receipt_id=_value(record, "receipt_id"),
                description=str(_value(record, "description", default="")).strip(),
                line_total_cents=int(cents),
                quantity=_decimal_value(_value(record, "quantity"), "1"),
                product_number=(
                    str(_value(record, "product_number", "sku")).strip() or None
                    if _value(record, "product_number", "sku") is not None
                    else None
                ),
                category=_value(record, "category"),
            )
        )
    return tuple(facts)


def persist_analytics_snapshot(
    session: Any,
    snapshot: AnalyticsSnapshotData,
    *,
    snapshot_model: type[Any] | None = None,
) -> Any:
    """Stage one atomic snapshot row in the caller's transaction.

    The function flushes but intentionally does not commit: a web request,
    worker, or setup command remains the owner of the surrounding transaction.
    It recognizes the common JSON column names used by Grocery Home migrations.
    """
    if snapshot_model is None:
        from .models import AnalyticsSnapshot as snapshot_model

    columns = {
        column.name: column
        for column in getattr(snapshot_model, "__table__").columns
    }
    payload = snapshot.as_dict()
    kwargs: dict[str, Any] = {}
    for name in ("generated_at", "created_at"):
        if name in columns:
            kwargs[name] = snapshot.generated_at
            break
    for name in ("as_of", "as_of_date"):
        if name in columns:
            kwargs[name] = snapshot.as_of
            break
    payload_name = next(
        (
            name
            for name in ("payload", "data", "snapshot", "payload_json")
            if name in columns
        ),
        None,
    )
    if payload_name is None:
        raise TypeError(
            "AnalyticsSnapshot needs a payload, data, snapshot, or payload_json column"
        )
    try:
        python_type = columns[payload_name].type.python_type
    except (AttributeError, NotImplementedError):
        python_type = dict
    kwargs[payload_name] = json.dumps(payload) if python_type is str else payload
    if "version" in columns:
        kwargs["version"] = 1
    overview_data = snapshot.overview
    fingerprint_payload = dict(payload)
    fingerprint_payload.pop("generated_at", None)
    source_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    exact_values = {
        "period_start": date(snapshot.as_of.year, snapshot.as_of.month, 1),
        "period_end": snapshot.as_of,
        "total_spend_cents": overview_data.current_month_spend_cents,
        "prior_spend_cents": overview_data.previous_month_spend_cents,
        "projected_30d_cents": overview_data.forecast_30d_cents,
        "receipt_count": overview_data.receipt_count,
        "included_through": snapshot.generated_at,
        "source_fingerprint": source_fingerprint,
        "is_current": True,
    }
    kwargs.update(
        {
            name: value
            for name, value in exact_values.items()
            if name in columns
        }
    )
    with session.begin_nested():
        if "is_current" in columns:
            from sqlalchemy import select, update

            session.execute(
                update(snapshot_model)
                .where(snapshot_model.is_current.is_(True))
                .values(is_current=False)
            )
            session.flush()
        row = None
        if "source_fingerprint" in columns:
            row = session.scalar(
                select(snapshot_model).where(
                    snapshot_model.source_fingerprint == source_fingerprint
                )
            )
        if row is None:
            row = snapshot_model(**kwargs)
            session.add(row)
        else:
            for name, value in kwargs.items():
                setattr(row, name, value)
        session.flush()
    return row


def refresh_analytics_snapshot(
    session: Any,
    *,
    as_of: date | None = None,
    receipt_model: type[Any] | None = None,
    item_model: type[Any] | None = None,
    snapshot_model: type[Any] | None = None,
) -> Any:
    """Load confirmed data, calculate in memory, and stage one snapshot row."""
    from sqlalchemy import select

    if receipt_model is None or item_model is None:
        from . import models

        receipt_model = receipt_model or models.Receipt
        item_model = item_model or getattr(models, "ReceiptItem", None)
        if item_model is None:
            item_model = models.Item
    receipt_rows = session.scalars(select(receipt_model)).all()
    item_rows = session.scalars(select(item_model)).all()
    snapshot = build_analytics_snapshot(
        receipt_facts(receipt_rows), item_facts(item_rows), as_of=as_of
    )
    return persist_analytics_snapshot(
        session, snapshot, snapshot_model=snapshot_model
    )


__all__ = [
    "AnalyticsSnapshotData",
    "AssociationInsight",
    "AssociationResult",
    "CategoryTotal",
    "DueSoonSuggestion",
    "InsightStatus",
    "ItemFact",
    "Overview",
    "PriceHistoryPoint",
    "ProductCadence",
    "ReceiptFact",
    "SpendBucket",
    "advanced_insight_status",
    "build_analytics_snapshot",
    "category_breakdown",
    "eligible_receipts",
    "item_facts",
    "mine_association_insights",
    "monthly_spend",
    "normalize_description",
    "overview",
    "persist_analytics_snapshot",
    "price_history",
    "product_cadence",
    "product_identity",
    "receipt_facts",
    "refresh_analytics_snapshot",
    "spending_run_rate",
    "weekly_spend",
]
