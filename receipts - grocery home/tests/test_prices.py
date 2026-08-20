from __future__ import annotations

from datetime import datetime, timedelta, timezone

from grocery_home.prices import (
    LivePriceQuote,
    PriceRefreshTerm,
    eligible_price_terms,
    refresh_price_terms,
    weekly_refresh_due,
)


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


def quote(*, fetched_at: datetime) -> LivePriceQuote:
    return LivePriceQuote(
        product_key="sku:123",
        merchant_key="woolworths",
        product_number="123",
        description="Milk",
        price_cents=450,
        unit_price_cents=225,
        unit_label="$2.25 / 1L",
        source="woolworths_live",
        fetched_at=fetched_at,
        valid_until=fetched_at + timedelta(days=7),
        raw_payload={},
    )


class FailingClient:
    def __init__(self, _delay: float) -> None:
        pass

    def search(self, _term: str) -> list[dict]:
        raise RuntimeError("offline")


class SuccessfulClient:
    def __init__(self, _delay: float) -> None:
        pass

    def search(self, _term: str) -> list[dict]:
        return [
            {
                "DisplayName": "Fresh Full Cream Milk",
                "PackageSize": "2L",
                "Stockcode": "123",
                "Price": 4.75,
                "CupPrice": 2.375,
                "CupString": "$2.38 / 1L",
                "IsAvailable": True,
            }
        ]


def test_term_scope_is_woolworths_and_active_or_needed_only() -> None:
    selected = eligible_price_terms(
        (
            PriceRefreshTerm("a", "Active", active=True),
            PriceRefreshTerm("b", "Needed", needed=True),
            PriceRefreshTerm("c", "Dormant"),
            PriceRefreshTerm(
                "d", "Other merchant", merchant_key="coles", needed=True
            ),
        )
    )

    assert {term.product_key for term in selected} == {"a", "b"}


def test_weekly_due_gate() -> None:
    assert not weekly_refresh_due(quote(fetched_at=NOW - timedelta(days=6)), now=NOW)
    assert weekly_refresh_due(quote(fetched_at=NOW - timedelta(days=7)), now=NOW)
    assert weekly_refresh_due(None, now=NOW)


def test_failure_preserves_stale_quote() -> None:
    old = quote(fetched_at=NOW - timedelta(days=8))
    result = refresh_price_terms(
        (PriceRefreshTerm("sku:123", "Milk", needed=True),),
        {"sku:123": old},
        now=NOW,
        client_factory=FailingClient,
    )

    assert result.attempted == 1
    assert result.refreshed == ()
    assert result.preserved[0].price_cents == 450
    assert result.preserved[0].fetched_at == old.fetched_at
    assert result.preserved[0].stale is True
    assert result.failures[0].stale_quote_preserved is True


def test_success_creates_new_cents_quote() -> None:
    result = refresh_price_terms(
        (PriceRefreshTerm("sku:123", "Fresh Full Cream Milk 2L", active=True),),
        {},
        now=NOW,
        client_factory=SuccessfulClient,
    )

    assert result.successful == 1
    assert result.refreshed[0].price_cents == 475
    assert result.refreshed[0].unit_price_cents == 238
    assert result.refreshed[0].valid_until == NOW + timedelta(days=7)


def test_database_refresh_keeps_expired_history_on_failure() -> None:
    from sqlalchemy import func, select

    from grocery_home.database import create_database, initialize_schema
    from grocery_home.models import (
        PriceQuote,
        ShoppingItem,
        ShoppingSource,
        ShoppingStatus,
    )
    from grocery_home.prices import refresh_live_prices

    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    with database.session() as session:
        session.add(
            ShoppingItem(
                product_key="sku:123",
                description="Milk",
                status=ShoppingStatus.ACTIVE,
                source=ShoppingSource.MANUAL,
            )
        )
        session.add(
            PriceQuote(
                product_key="sku:123",
                merchant_key="woolworths",
                product_number="123",
                description="Milk",
                price_cents=450,
                fetched_at=NOW - timedelta(days=8),
                valid_until=NOW - timedelta(days=1),
            )
        )

    with database.session() as session:
        result = refresh_live_prices(
            session, now=NOW, client_factory=FailingClient
        )
        assert result.failures[0].stale_quote_preserved is True
        assert session.scalar(select(func.count()).select_from(PriceQuote)) == 1

    database.dispose()
