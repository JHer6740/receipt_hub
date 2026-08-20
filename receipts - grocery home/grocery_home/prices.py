"""Stale-safe Woolworths live-price refresh services.

Only product descriptions/SKUs are sent to Woolworths.  Receipt files and
images never leave Grocery Home.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fetch_prices import (
    PRODUCT_URL,
    WooliesClient,
    clean_term,
    match_score,
)


PRICE_DISCLOSURE = (
    "Grocery Home sends product descriptions, never receipt images, to "
    "Woolworths when checking live prices."
)
REFRESH_INTERVAL = timedelta(days=7)


def _sydney_zone() -> timezone | ZoneInfo:
    try:
        return ZoneInfo("Australia/Sydney")
    except ZoneInfoNotFoundError:  # pragma: no cover - tzdata is a dependency
        return timezone(timedelta(hours=10), name="Australia/Sydney")


SYDNEY = _sydney_zone()


@dataclass(frozen=True, slots=True)
class PriceRefreshTerm:
    product_key: str
    description: str
    product_number: str | None = None
    merchant_key: str = "woolworths"
    active: bool = False
    needed: bool = False


@dataclass(frozen=True, slots=True)
class LivePriceQuote:
    product_key: str
    merchant_key: str
    product_number: str | None
    description: str
    price_cents: int
    unit_price_cents: int | None
    unit_label: str | None
    source: str
    fetched_at: datetime
    valid_until: datetime
    raw_payload: Mapping[str, Any]
    stale: bool = False
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PriceRefreshFailure:
    product_key: str
    description: str
    error: str
    stale_quote_preserved: bool


@dataclass(frozen=True, slots=True)
class PriceRefreshResult:
    attempted: int
    refreshed: tuple[LivePriceQuote, ...]
    preserved: tuple[LivePriceQuote, ...]
    failures: tuple[PriceRefreshFailure, ...]
    skipped_not_due: tuple[str, ...]

    @property
    def successful(self) -> int:
        return len(self.refreshed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def weekly_refresh_due(
    quote_or_fetched_at: LivePriceQuote | datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Use Sydney calendar time for the household's weekly refresh boundary."""
    if quote_or_fetched_at is None:
        return True
    now = _aware_utc(now or datetime.now(timezone.utc))
    if isinstance(quote_or_fetched_at, LivePriceQuote):
        valid_until = quote_or_fetched_at.valid_until
        if valid_until:
            return now >= _aware_utc(valid_until)
        fetched_at = quote_or_fetched_at.fetched_at
    else:
        fetched_at = quote_or_fetched_at
    local_now = now.astimezone(SYDNEY)
    local_fetched = _aware_utc(fetched_at).astimezone(SYDNEY)
    return local_now >= local_fetched + REFRESH_INTERVAL


def _next_week(now: datetime) -> datetime:
    """Keep the household wall-clock refresh time across daylight saving."""
    return (now.astimezone(SYDNEY) + REFRESH_INTERVAL).astimezone(timezone.utc)


def eligible_price_terms(
    terms: Iterable[PriceRefreshTerm],
) -> tuple[PriceRefreshTerm, ...]:
    """Keep only active/needed Woolworths products and de-duplicate by key."""
    selected: dict[str, PriceRefreshTerm] = {}
    for term in terms:
        if term.merchant_key.casefold() != "woolworths":
            continue
        if not (term.active or term.needed):
            continue
        prior = selected.get(term.product_key)
        if prior is None:
            selected[term.product_key] = term
        else:
            selected[term.product_key] = replace(
                prior,
                description=(
                    term.description
                    if len(term.description) > len(prior.description)
                    else prior.description
                ),
                product_number=prior.product_number or term.product_number,
                active=prior.active or term.active,
                needed=prior.needed or term.needed,
            )
    return tuple(
        sorted(selected.values(), key=lambda term: term.description.casefold())
    )


def _cents(value: Any) -> int:
    return int(
        (Decimal(str(value)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _optional_cents(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return _cents(value)
    except (ValueError, TypeError, ArithmeticError):
        return None


def _best_candidate(
    term: str, candidates: Sequence[Mapping[str, Any]]
) -> tuple[Mapping[str, Any] | None, Decimal]:
    best: Mapping[str, Any] | None = None
    best_score = Decimal("0")
    for candidate in candidates:
        if not candidate or candidate.get("Price") is None:
            continue
        label = (
            f"{candidate.get('DisplayName') or candidate.get('Name', '')} "
            f"{candidate.get('PackageSize', '')}"
        )
        score = Decimal(str(match_score(term, label)))
        if score > best_score:
            best = candidate
            best_score = score
    return best, best_score


def _quote_from_candidate(
    refresh_term: PriceRefreshTerm,
    search_term: str,
    candidate: Mapping[str, Any],
    score: Decimal,
    now: datetime,
) -> LivePriceQuote:
    stockcode = str(candidate.get("Stockcode") or "")
    matched_name = str(
        candidate.get("DisplayName") or candidate.get("Name") or refresh_term.description
    )
    cup_price = (
        candidate.get("CupPrice")
        or candidate.get("UnitPrice")
        or candidate.get("CupPriceValue")
    )
    raw_payload = {
        "search_term": search_term,
        "matched_name": matched_name,
        "package_size": candidate.get("PackageSize"),
        "stockcode": stockcode,
        "was_price": candidate.get("WasPrice"),
        "on_special": bool(candidate.get("IsOnSpecial")),
        "available": bool(candidate.get("IsAvailable", True)),
        "match_score": str(score),
        "url": PRODUCT_URL.format(stockcode=stockcode),
    }
    return LivePriceQuote(
        product_key=refresh_term.product_key,
        merchant_key="woolworths",
        product_number=refresh_term.product_number or stockcode or None,
        description=refresh_term.description,
        price_cents=_cents(candidate["Price"]),
        unit_price_cents=_optional_cents(cup_price),
        unit_label=str(candidate.get("CupString") or "") or None,
        source="woolworths_live",
        fetched_at=now,
        valid_until=_next_week(now),
        raw_payload=raw_payload,
    )


def refresh_price_terms(
    terms: Iterable[PriceRefreshTerm],
    current_quotes: Mapping[str, LivePriceQuote] | None = None,
    *,
    now: datetime | None = None,
    force: bool = False,
    delay_seconds: float = 2.0,
    client_factory: Callable[[float], Any] = WooliesClient,
) -> PriceRefreshResult:
    """Refresh selected terms while retaining the last quote on every failure."""
    now = _aware_utc(now or datetime.now(timezone.utc))
    current_quotes = current_quotes or {}
    due: list[PriceRefreshTerm] = []
    skipped: list[str] = []
    for term in eligible_price_terms(terms):
        existing = current_quotes.get(term.product_key)
        if force or weekly_refresh_due(existing, now=now):
            due.append(term)
        else:
            skipped.append(term.product_key)
    if not due:
        return PriceRefreshResult(0, (), (), (), tuple(skipped))

    refreshed: list[LivePriceQuote] = []
    preserved: list[LivePriceQuote] = []
    failures: list[PriceRefreshFailure] = []
    client: Any | None = None
    for refresh_term in due:
        existing = current_quotes.get(refresh_term.product_key)
        try:
            if client is None:
                # WooliesClient performs the actual monotonic rate limiting.
                client = client_factory(delay_seconds)
            search_term = clean_term(refresh_term.description)
            candidates = client.search(search_term)
            if not candidates:
                raise LookupError("No Woolworths product match was returned")
            candidate, score = _best_candidate(search_term, candidates)
            if candidate is None:
                raise LookupError("No priced Woolworths product match was returned")
            refreshed.append(
                _quote_from_candidate(
                    refresh_term, search_term, candidate, score, now
                )
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if existing is not None:
                preserved.append(replace(existing, stale=True, error=error))
            failures.append(
                PriceRefreshFailure(
                    product_key=refresh_term.product_key,
                    description=refresh_term.description,
                    error=error,
                    stale_quote_preserved=existing is not None,
                )
            )
    return PriceRefreshResult(
        attempted=len(due),
        refreshed=tuple(refreshed),
        preserved=tuple(preserved),
        failures=tuple(failures),
        skipped_not_due=tuple(skipped),
    )


def quote_from_model(record: Any) -> LivePriceQuote:
    fetched_at = _aware_utc(record.fetched_at)
    valid_until = getattr(record, "valid_until", None) or (
        _next_week(fetched_at)
    )
    return LivePriceQuote(
        product_key=record.product_key,
        merchant_key=record.merchant_key,
        product_number=getattr(record, "product_number", None),
        description=record.description,
        price_cents=record.price_cents,
        unit_price_cents=getattr(record, "unit_price_cents", None),
        unit_label=getattr(record, "unit_label", None),
        source=getattr(record, "source", "woolworths_live"),
        fetched_at=fetched_at,
        valid_until=_aware_utc(valid_until),
        raw_payload=getattr(record, "raw_payload", None) or {},
    )


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value)).casefold()


def collect_refresh_terms(
    session: Any,
    *,
    shopping_model: type[Any] | None = None,
    snapshot_model: type[Any] | None = None,
) -> tuple[PriceRefreshTerm, ...]:
    """Collect needed list items and active recurring products from the DB."""
    from sqlalchemy import select

    if shopping_model is None or snapshot_model is None:
        from . import models

        shopping_model = shopping_model or models.ShoppingItem
        snapshot_model = snapshot_model or models.AnalyticsSnapshot
    from .analytics import product_identity

    terms: list[PriceRefreshTerm] = []
    for row in session.scalars(select(shopping_model)).all():
        if _status_value(row.status) != "active":
            continue
        terms.append(
            PriceRefreshTerm(
                product_key=row.product_key
                or product_identity(None, row.description),
                description=row.description,
                merchant_key="woolworths",
                needed=True,
            )
        )
    current = session.scalars(
        select(snapshot_model)
        .where(snapshot_model.is_current.is_(True))
        .order_by(snapshot_model.generated_at.desc())
        .limit(1)
    ).first()
    if current is not None:
        for product in (current.payload or {}).get("products", []):
            if not product.get("active"):
                continue
            terms.append(
                PriceRefreshTerm(
                    product_key=str(product["product_key"]),
                    description=str(product["description"]),
                    product_number=product.get("product_number"),
                    merchant_key="woolworths",
                    active=True,
                )
            )
    return eligible_price_terms(terms)


def latest_quotes_by_product(
    session: Any, *, quote_model: type[Any] | None = None
) -> Mapping[str, LivePriceQuote]:
    from sqlalchemy import select

    if quote_model is None:
        from .models import PriceQuote as quote_model

    records = session.scalars(
        select(quote_model).order_by(quote_model.fetched_at.desc())
    ).all()
    latest: dict[str, LivePriceQuote] = {}
    for record in records:
        if (
            record.merchant_key.casefold() == "woolworths"
            and record.product_key not in latest
        ):
            latest[record.product_key] = quote_from_model(record)
    return latest


def persist_price_refresh(
    session: Any,
    result: PriceRefreshResult,
    *,
    quote_model: type[Any] | None = None,
) -> tuple[Any, ...]:
    """Insert successful historical quote rows; stale rows are never replaced."""
    if quote_model is None:
        from .models import PriceQuote as quote_model

    rows: list[Any] = []
    with session.begin_nested():
        for quote in result.refreshed:
            row = quote_model(
                product_key=quote.product_key,
                merchant_key=quote.merchant_key,
                product_number=quote.product_number,
                description=quote.description,
                price_cents=quote.price_cents,
                unit_price_cents=quote.unit_price_cents,
                unit_label=quote.unit_label,
                source=quote.source,
                fetched_at=quote.fetched_at,
                valid_until=quote.valid_until,
                raw_payload=dict(quote.raw_payload),
            )
            session.add(row)
            rows.append(row)
        session.flush()
    return tuple(rows)


def refresh_live_prices(
    session: Any,
    *,
    terms: Iterable[PriceRefreshTerm] | None = None,
    now: datetime | None = None,
    force: bool = False,
    delay_seconds: float = 2.0,
    client_factory: Callable[[float], Any] = WooliesClient,
    shopping_model: type[Any] | None = None,
    snapshot_model: type[Any] | None = None,
    quote_model: type[Any] | None = None,
) -> PriceRefreshResult:
    """Run the weekly worker operation and stage successful quote history."""
    selected = (
        tuple(terms)
        if terms is not None
        else collect_refresh_terms(
            session,
            shopping_model=shopping_model,
            snapshot_model=snapshot_model,
        )
    )
    existing = latest_quotes_by_product(session, quote_model=quote_model)
    result = refresh_price_terms(
        selected,
        existing,
        now=now,
        force=force,
        delay_seconds=delay_seconds,
        client_factory=client_factory,
    )
    persist_price_refresh(session, result, quote_model=quote_model)
    return result


def manual_refresh_prices(session: Any, **kwargs: Any) -> PriceRefreshResult:
    """Settings-page operation: bypass the weekly-age gate, not term scope."""
    return refresh_live_prices(session, force=True, **kwargs)


__all__ = [
    "LivePriceQuote",
    "PRICE_DISCLOSURE",
    "PriceRefreshFailure",
    "PriceRefreshResult",
    "PriceRefreshTerm",
    "REFRESH_INTERVAL",
    "collect_refresh_terms",
    "eligible_price_terms",
    "latest_quotes_by_product",
    "manual_refresh_prices",
    "persist_price_refresh",
    "quote_from_model",
    "refresh_live_prices",
    "refresh_price_terms",
    "weekly_refresh_due",
]
