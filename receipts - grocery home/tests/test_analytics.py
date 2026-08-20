from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from grocery_home.analytics import (
    ItemFact,
    ReceiptFact,
    build_analytics_snapshot,
    category_breakdown,
    monthly_spend,
    product_cadence,
    product_identity,
    receipt_facts,
    spending_run_rate,
)


def receipt(
    receipt_id: str,
    day: date,
    cents: int,
    **changes: object,
) -> ReceiptFact:
    values = {
        "receipt_id": receipt_id,
        "purchase_date": day,
        "total_cents": cents,
    }
    values.update(changes)
    return ReceiptFact(**values)


def test_empty_history_returns_zero_snapshot_and_insufficient_insights() -> None:
    snapshot = build_analytics_snapshot(
        (),
        (),
        as_of=date(2026, 7, 24),
        generated_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )

    assert snapshot.overview.receipt_count == 0
    assert snapshot.overview.forecast_30d_cents == 0
    assert snapshot.monthly == ()
    assert snapshot.suggestions == ()
    assert (
        snapshot.advanced_insights["association_rules"].status
        == "insufficient_history"
    )
    assert (
        snapshot.advanced_insights["numerical_patterns"].status
        == "insufficient_history"
    )


def test_short_history_run_rate_uses_observed_days_not_fixed_ninety() -> None:
    receipts = (
        receipt("one", date(2026, 7, 1), 1_000),
        receipt("two", date(2026, 7, 15), 2_000),
    )

    forecast, basis_days = spending_run_rate(receipts)

    assert basis_days == 15
    assert forecast == 6_000


def test_duplicates_and_non_grocery_are_excluded_everywhere() -> None:
    receipts = (
        receipt("included", date(2026, 7, 1), 1_000),
        receipt(
            "duplicate",
            date(2026, 7, 1),
            99_000,
            duplicate_of_id="included",
        ),
        receipt(
            "big-w",
            date(2026, 7, 2),
            88_000,
            merchant="BIG W",
            is_grocery=False,
        ),
    )
    items = (
        ItemFact("included", "Milk", 1_000, category="dairy"),
        ItemFact("duplicate", "Television", 99_000, category="other"),
        ItemFact("big-w", "Clothes", 88_000, category="clothing"),
    )

    assert monthly_spend(receipts)[0].spend_cents == 1_000
    categories = category_breakdown(receipts, items)
    assert [(row.category, row.spend_cents) for row in categories] == [
        ("dairy", 1_000)
    ]


def test_prediction_uses_sku_and_quantity_aware_expected_cost() -> None:
    receipts = tuple(
        receipt(str(index), day, 1_000)
        for index, day in enumerate(
            (date(2026, 7, 1), date(2026, 7, 8), date(2026, 7, 15)),
            start=1,
        )
    )
    items = (
        ItemFact(
            "1",
            "Brand Milk 2L",
            1_000,
            Decimal("2"),
            product_number="12345",
            category="dairy",
        ),
        ItemFact(
            "2",
            "BRAND MILK TWO LITRE",
            1_000,
            Decimal("2"),
            product_number="12345",
            category="dairy",
        ),
        ItemFact(
            "3",
            "Brand Milk 2L",
            1_000,
            Decimal("2"),
            product_number="12345",
            category="dairy",
        ),
    )

    products, suggestions = product_cadence(
        receipts, items, as_of=date(2026, 7, 16)
    )

    assert len(products) == 1
    assert products[0].product_key == "sku:12345"
    assert products[0].typical_quantity == Decimal("2")
    assert products[0].typical_unit_price_cents == 500
    assert products[0].expected_purchase_cost_cents == 1_000
    assert suggestions[0].estimated_due == date(2026, 7, 22)
    assert suggestions[0].expected_cost_cents == 1_000


def test_product_identity_falls_back_to_normalized_description() -> None:
    assert product_identity(None, "Wholemeal Sandwich 700 g") == (
        "name:wholemealsandwich700g"
    )


def test_incomplete_draft_with_no_date_is_safely_excluded() -> None:
    facts = receipt_facts(
        (
            {
                "id": "draft",
                "purchase_date": None,
                "total_cents": None,
                "status": "needs_review",
            },
        )
    )

    assert build_analytics_snapshot(
        facts, (), as_of=date(2026, 7, 24)
    ).overview.receipt_count == 0


def test_snapshot_persistence_is_atomic_and_idempotent() -> None:
    from sqlalchemy import func, select

    from grocery_home.analytics import persist_analytics_snapshot
    from grocery_home.database import create_database, initialize_schema
    from grocery_home.models import AnalyticsSnapshot

    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    first = build_analytics_snapshot(
        (receipt("one", date(2026, 7, 1), 1_000),),
        (),
        as_of=date(2026, 7, 24),
        generated_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    changed = build_analytics_snapshot(
        (receipt("one", date(2026, 7, 1), 2_000),),
        (),
        as_of=date(2026, 7, 24),
        generated_at=datetime(2026, 7, 24, 1, tzinfo=timezone.utc),
    )

    with database.session() as session:
        persist_analytics_snapshot(session, first)
        persist_analytics_snapshot(session, first)
        assert session.scalar(select(func.count()).select_from(AnalyticsSnapshot)) == 1
        persist_analytics_snapshot(session, changed)
        assert session.scalar(select(func.count()).select_from(AnalyticsSnapshot)) == 2
        assert session.scalar(
            select(func.count())
            .select_from(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.is_current.is_(True))
        ) == 1

    database.dispose()
