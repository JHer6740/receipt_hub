"""Shared application services used by both the Jinja web UI and the JSON API.

Every piece of household logic that is not purely presentational lives here so
the HTML routes in :mod:`grocery_home.app` and the ``/api/v1`` routes in
:mod:`grocery_home.api` stay behaviourally identical.  Routes remain thin: they
parse their own transport (form encoding vs. JSON), call into this module, and
render the result.

The module deliberately avoids importing FastAPI.  Failures are reported with
:class:`ServiceError` so each transport can map them to its own error shape --
an HTML 422 page or a typed JSON field error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from .analytics import product_identity, refresh_analytics_snapshot
from .jobs import enqueue_job
from .models import (
    RECONCILE_TOLERANCE_CENTS,
    AnalyticsSnapshot,
    BackgroundJob,
    Household,
    JobStatus,
    ProcessingStatus,
    Receipt,
    ReceiptItem,
    ShoppingItem,
    ShoppingSource,
    ShoppingStatus,
    UploadBatch,
    make_receipt_natural_key,
    new_id,
    normalize_key_part,
    utc_now,
)


TERMINAL_UPLOAD_STATUSES = {
    ProcessingStatus.NEEDS_REVIEW,
    ProcessingStatus.COMPLETE,
    ProcessingStatus.DUPLICATE,
    ProcessingStatus.FAILED,
}

REVIEWABLE_STATUSES = {ProcessingStatus.NEEDS_REVIEW, ProcessingStatus.FAILED}

STATUS_PRESENTATION: dict[str, tuple[str, str]] = {
    "queued": ("Queued", "muted"),
    "extracting": ("Reading", "working"),
    "needs_review": ("Needs review", "warning"),
    "complete": ("Confirmed", "success"),
    "duplicate": ("Duplicate", "muted"),
    "failed": ("Needs help", "danger"),
}

JOB_PROGRESS: dict[str, int] = {
    "queued": 12,
    "extracting": 58,
    "needs_review": 100,
    "complete": 100,
    "duplicate": 100,
    "failed": 100,
}

JOB_COPY: dict[str, tuple[str, str]] = {
    "queued": ("In the reading queue.", "Grocery Home will start shortly."),
    "extracting": ("Reading your receipt.", "Finding its shop, totals and items locally."),
    "needs_review": ("Ready for a quick check.", "Confirm the fields before they affect trends."),
    "complete": ("Filed in the ledger.", "Household totals are up to date."),
    "duplicate": ("Already in the ledger.", "This upload is retained but will not count twice."),
    "failed": ("This receipt needs help.", "Open it and enter the details manually."),
}


class ServiceError(Exception):
    """A caller-correctable failure raised by a shared service.

    ``field`` names the offending input where one exists so the JSON API can
    return a typed field error and the HTML form can highlight the same input.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "INVALID_REQUEST",
        field: str | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field
        self.status_code = status_code


class NotFoundError(ServiceError):
    """The requested household record does not exist."""

    def __init__(self, message: str, *, code: str = "NOT_FOUND") -> None:
        super().__init__(message, code=code, status_code=404)


class ConflictError(ServiceError):
    """An optimistic-concurrency check failed; the caller holds stale state."""

    def __init__(self, message: str, *, code: str = "VERSION_CONFLICT") -> None:
        super().__init__(message, code=code, status_code=409)


# ---------------------------------------------------------------------------
# Money, quantity and label formatting
# ---------------------------------------------------------------------------


def money(cents: int | None) -> str:
    """Format integer cents as a display string such as ``$12.34``."""

    value = Decimal(cents or 0) / Decimal(100)
    return f"${value:,.2f}"


def money_input(cents: int | None) -> str:
    """Format integer cents for a numeric form input, without a currency sign."""

    return f"{Decimal(cents or 0) / Decimal(100):.2f}"


def parse_money(
    value: Any,
    *,
    required: bool = False,
    field_name: str | None = None,
) -> int | None:
    """Parse a user-supplied dollar amount into integer cents."""

    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        if required:
            raise ServiceError("A dollar amount is required.", field=field_name)
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ServiceError(
            f"{value!s} is not a valid dollar amount.", field=field_name
        ) from exc
    return int((amount * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_quantity(value: Any, *, field_name: str | None = None) -> Decimal:
    """Parse a positive quantity, normalised to at most three decimal places."""

    try:
        quantity = Decimal(str(value or "1").strip())
    except InvalidOperation as exc:
        raise ServiceError("Quantity must be a number.", field=field_name) from exc
    if quantity <= 0:
        raise ServiceError("Quantity must be greater than zero.", field=field_name)
    return quantity.quantize(Decimal("0.001")).normalize()


def parse_date(value: Any, *, field_name: str = "purchase_date") -> date | None:
    """Parse an ISO date, returning ``None`` for blank input."""

    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ServiceError("Enter the date as YYYY-MM-DD.", field=field_name) from exc


def parse_time(value: Any, *, field_name: str = "purchase_time") -> time | None:
    """Parse a 24-hour ``HH:MM`` time, returning ``None`` for blank input."""

    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%H:%M").time()
    except (TypeError, ValueError) as exc:
        raise ServiceError("Purchase time is invalid.", field=field_name) from exc


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def status_presentation(value: Any) -> tuple[str, str]:
    status = enum_value(value)
    return STATUS_PRESENTATION.get(
        status, (status.replace("_", " ").title(), "muted")
    )


def date_label(value: date | None) -> tuple[str, str]:
    if value is None:
        return ("—", "")
    return (str(value.day), value.strftime("%b").upper())


def human_date(value: date | None) -> str:
    return f"{value.day} {value.strftime('%B %Y')}" if value else "Date unknown"


def quantity_label(quantity: Decimal, unit: str) -> str:
    clean = format(quantity.normalize(), "f")
    return clean if unit == "each" else f"{clean} {unit}"


def household_today() -> date:
    """Return the local calendar date used as an empty-household fallback."""

    return datetime.now().astimezone().date()


def next_weekly_price_run(now: datetime | None = None) -> datetime:
    """Return the next Sunday 03:00 Australia/Sydney boundary in UTC."""

    local_now = (now or utc_now()).astimezone(ZoneInfo("Australia/Sydney"))
    days_until_sunday = (6 - local_now.weekday()) % 7
    candidate_date = local_now.date() + timedelta(days=days_until_sunday)
    candidate = datetime(
        candidate_date.year,
        candidate_date.month,
        candidate_date.day,
        3,
        tzinfo=local_now.tzinfo,
    )
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate.astimezone(UTC)


# ---------------------------------------------------------------------------
# Analytics snapshot access
# ---------------------------------------------------------------------------


def current_snapshot(session: Session, *, create: bool = False) -> AnalyticsSnapshot | None:
    snapshot = session.scalar(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.is_current.is_(True))
        .order_by(AnalyticsSnapshot.generated_at.desc())
        .limit(1)
    )
    if snapshot is None and create:
        snapshot = refresh_analytics_snapshot(session)
    return snapshot


def snapshot_payload(session: Session, *, create: bool = False) -> dict[str, Any]:
    snapshot = current_snapshot(session, create=create)
    return dict(snapshot.payload or {}) if snapshot is not None else {}


def due_suggestions(
    session: Session,
    payload: Mapping[str, Any],
    *,
    limit: int | None = None,
    household_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return due-soon suggestions minus anything already listed or dismissed."""

    now = utc_now()
    blocked_keys: set[str] = set()
    blocking_query = select(ShoppingItem)
    if household_id is not None:
        blocking_query = blocking_query.where(
            ShoppingItem.household_id == household_id
        )
    for item in session.scalars(blocking_query).all():
        if item.status == ShoppingStatus.ACTIVE:
            blocked_keys.add(item.product_key or product_identity(None, item.description))
        elif (
            item.status == ShoppingStatus.DISMISSED
            and item.dismissed_until is not None
            and item.dismissed_until > now
        ):
            blocked_keys.add(item.product_key or product_identity(None, item.description))

    output: list[dict[str, Any]] = []
    for raw in payload.get("suggestions", []):
        key = str(raw.get("product_key") or "")
        if not key or key in blocked_keys:
            continue
        try:
            due = date.fromisoformat(str(raw["estimated_due"]))
        except (KeyError, TypeError, ValueError):
            continue
        days = int(raw.get("days_from_as_of") or 0)
        cadence = (
            "due today"
            if days == 0
            else f"due in {days} day{'s' if abs(days) != 1 else ''}"
            if days > 0
            else f"usually bought {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
        )
        output.append(
            {
                "key": key,
                "description": str(raw.get("description") or "Household item"),
                "due": due,
                "due_day": str(due.day),
                "due_month": due.strftime("%b").upper(),
                "due_label": cadence,
                "cadence_label": cadence,
                "quantity": str(raw.get("quantity") or "1"),
                "estimated_cost_cents": int(raw.get("expected_cost_cents") or 0),
                "estimated_cost": money(int(raw.get("expected_cost_cents") or 0)),
                "confidence": str(raw.get("confidence") or "low"),
                "interval_label": (
                    "its usual rhythm"
                    if raw.get("typical_interval_days") is None
                    else f"{raw['typical_interval_days']} days"
                ),
            }
        )
    output.sort(key=lambda item: (item["due"], item["description"].casefold()))
    return output[:limit] if limit is not None else output


def find_suggestion(session: Session, key: str) -> dict[str, Any]:
    """Return a single due-soon suggestion by product key."""

    suggestion = next(
        (
            item
            for item in due_suggestions(session, snapshot_payload(session, create=True))
            if item["key"] == key
        ),
        None,
    )
    if suggestion is None:
        raise NotFoundError("Suggestion not found.", code="SUGGESTION_NOT_FOUND")
    return suggestion


@dataclass(frozen=True, slots=True)
class HouseholdOverview:
    """The month-level figures shared by Home, bootstrap and insights."""

    month_spend_cents: int
    previous_month_spend_cents: int
    month_change_percent: Decimal | None
    recorded_spend_cents: int
    forecast_30d_cents: int
    receipt_count: int
    active_list_count: int
    monthly_trend: tuple[dict[str, Any], ...]
    categories: tuple[dict[str, Any], ...]

    @property
    def month_delta_label(self) -> str | None:
        if self.month_change_percent is None:
            return None
        change = self.month_change_percent
        return f"{abs(change):.0f}% {'less' if change < 0 else 'more'}"

    @property
    def month_delta_direction(self) -> str:
        if self.month_change_percent is None:
            return ""
        return "down" if self.month_change_percent < 0 else "up"


def household_overview(
    session: Session,
    *,
    payload: Mapping[str, Any] | None = None,
    trend_months: int = 6,
) -> HouseholdOverview:
    """Summarise household spending from the current analytics snapshot."""

    data = dict(payload) if payload is not None else snapshot_payload(session, create=True)
    overview_data = data.get("overview", {}) or {}
    change_raw = overview_data.get("month_change_percent")
    change = Decimal(str(change_raw)) if change_raw is not None else None

    active_count = (
        session.scalar(
            select(func.count(ShoppingItem.id)).where(
                ShoppingItem.status == ShoppingStatus.ACTIVE
            )
        )
        or 0
    )

    monthly = [
        {
            "month": str(bucket.get("period_start", ""))[:7],
            "total_cents": int(bucket.get("spend_cents") or 0),
            "receipt_count": int(bucket.get("trips") or 0),
        }
        for bucket in data.get("monthly", []) or []
    ]
    monthly.sort(key=lambda row: row["month"])

    categories = [
        {
            "category": str(row.get("category") or "Uncategorised"),
            "spend_cents": int(row.get("spend_cents") or 0),
            "item_count": int(row.get("line_items") or 0),
        }
        for row in data.get("categories", []) or []
    ]

    return HouseholdOverview(
        month_spend_cents=int(overview_data.get("current_month_spend_cents") or 0),
        previous_month_spend_cents=int(
            overview_data.get("previous_month_spend_cents") or 0
        ),
        month_change_percent=change,
        recorded_spend_cents=int(overview_data.get("recorded_spend_cents") or 0),
        forecast_30d_cents=int(overview_data.get("forecast_30d_cents") or 0),
        receipt_count=int(overview_data.get("receipt_count") or 0),
        active_list_count=int(active_count),
        monthly_trend=tuple(monthly[-trend_months:] if trend_months else monthly),
        categories=tuple(categories),
    )


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

# Collections in the client are a presentation of the backend's existing
# line-item categories rather than a second taxonomy, so a receipt only ever
# has one categorisation to keep correct.
COLLECTION_ICONS: dict[str, str] = {
    "bakery": "🍞",
    "dairy": "🥛",
    "drinks": "🧃",
    "frozen": "🧊",
    "fruit": "🍎",
    "household": "🧻",
    "meat": "🥩",
    "pantry": "🥫",
    "personal": "🧼",
    "produce": "🥬",
    "seafood": "🐟",
    "snacks": "🍫",
    "vegetables": "🥕",
}
DEFAULT_COLLECTION_ICON = "🛒"


def normalize_collection_id(category: str) -> str:
    """Turn a category name into a stable identifier the client can persist."""

    return normalize_key_part(str(category or "uncategorised")).replace(" ", "_")[:80]


def collection_icon(category: str) -> str:
    return COLLECTION_ICONS.get(str(category or "").strip().casefold(), DEFAULT_COLLECTION_ICON)


# ---------------------------------------------------------------------------
# Receipt presentation
# ---------------------------------------------------------------------------


def receipt_view(receipt: Receipt) -> dict[str, Any]:
    """Build the shared receipt summary used by list and detail surfaces."""

    label, tone = status_presentation(receipt.status)
    day, month = date_label(receipt.purchase_date)
    filename = (
        receipt.upload_file.original_filename
        if receipt.upload_file is not None
        else "Manual receipt"
    )
    return {
        "id": receipt.id,
        "merchant": receipt.merchant_name or receipt.store_name or "Unknown shop",
        "merchant_name": receipt.merchant_name or receipt.store_name or "Unknown shop",
        "filename": filename,
        "purchase_date": receipt.purchase_date.isoformat() if receipt.purchase_date else "",
        "purchase_date_label": human_date(receipt.purchase_date),
        "day": day,
        "month": month,
        "item_count": (
            receipt.item_count_reported
            if receipt.duplicate_of_id and receipt.item_count_reported is not None
            else len(receipt.items)
        ),
        "is_grocery": receipt.is_grocery,
        "status": enum_value(receipt.status),
        "status_label": label,
        "status_tone": tone,
        "total": money(receipt.total_cents),
        "gst": money(receipt.gst_cents),
        "savings": money(receipt.savings_cents),
        "transaction_number": receipt.transaction_number,
        "can_review": receipt.status in REVIEWABLE_STATUSES,
        "can_edit": receipt.duplicate_of_id is None,
        "destination": (
            f"/receipts/{receipt.id}/review"
            if receipt.status in REVIEWABLE_STATUSES
            else f"/receipts/{receipt.id}"
        ),
    }


def pin_configured_household(session: Session, household_id: int = 1) -> Household | None:
    """The shared-PIN household, or None when setup has not been run.

    Household 1 now always exists: every household-owned table defaults its
    `household_id` to it, so the foreign key needs that row. Existence is
    therefore no longer evidence that anyone has set a PIN, which is what the
    login and PIN-auth paths actually need to know.
    """

    household = session.get(Household, household_id)
    if household is None or not household.pin_hash:
        return None
    return household


def receipt_collection(receipt: Receipt) -> tuple[str | None, str | None]:
    """Which collection a receipt belongs to.

    A collection is a view of the line-item categories, so a receipt belongs to
    whichever category accounts for most of its money. This is derived rather
    than stored so there is only one categorisation to keep correct.

    Returns ``(None, None)`` when nothing has been categorised yet, so the
    interface can say "unfiled" instead of inventing a collection.
    """

    totals: dict[str, int] = {}
    for item in receipt.items:
        category = str(item.category or "").strip()
        if not category or category.casefold() == "uncategorised":
            continue
        totals[category] = totals.get(category, 0) + int(item.line_total_cents or 0)
    if not totals:
        return None, None
    name = max(totals, key=lambda key: totals[key])
    return normalize_collection_id(name), name


def delete_receipt(
    session: Session,
    receipt_id: str,
    *,
    household_id: int | None = None,
) -> None:
    """Remove a receipt and its line items.

    The client offered a delete action long before this existed, so a deleted
    receipt reappeared on the next refresh. Scoped, so one household cannot
    delete another's receipt by guessing an id.
    """

    receipt = load_receipt(
        session,
        receipt_id,
        with_items=False,
        household_id=household_id,
    )
    session.delete(receipt)
    session.flush()


def receipt_warnings(receipt: Receipt) -> list[str]:
    """List the things a person still needs to fix before a receipt is filed."""

    line_sum = sum(item.line_total_cents or 0 for item in receipt.items)
    warnings: list[str] = []
    if not receipt.merchant_name:
        warnings.append("Store name is missing.")
    if receipt.purchase_date is None:
        warnings.append("Purchase date is missing.")
    if receipt.total_cents is None:
        warnings.append("Receipt total is missing.")
    if not receipt.items:
        warnings.append("No line items were recognised. Add at least one item.")
    if (
        receipt.total_cents is not None
        and receipt.total_cents > 0
        and receipt.items
        and abs(line_sum - receipt.total_cents) > RECONCILE_TOLERANCE_CENTS
    ):
        # Name both numbers and say which one to look at. "Line items differ
        # from the total by $6.48" told someone that something was wrong
        # without saying what to do about it, and the answer is almost never
        # to re-read every line.
        gap = receipt.total_cents - line_sum
        if gap > 0:
            warnings.append(
                f"The total reads {money(receipt.total_cents)} but the lines "
                f"add to {money(line_sum)}, so {money(gap)} of lines are "
                "missing."
            )
        else:
            warnings.append(
                f"The lines add to {money(line_sum)}, more than the stated "
                f"total of {money(receipt.total_cents)}. Check the total."
            )
    uncertain = sum(1 for item in receipt.items if item.needs_review)
    if uncertain:
        warnings.append(
            f"{uncertain} line item{'s' if uncertain != 1 else ''} had uncertain text."
        )
    return warnings


def receipt_review_view(receipt: Receipt) -> dict[str, Any]:
    """Build the editable review payload, including correction warnings."""

    view = receipt_view(receipt)
    view.update(
        {
            "merchant_name": receipt.merchant_name or "",
            "purchase_date": receipt.purchase_date.isoformat() if receipt.purchase_date else "",
            "purchase_time": (
                receipt.purchase_time.strftime("%H:%M") if receipt.purchase_time else ""
            ),
            "subtotal": money_input(receipt.subtotal_cents),
            "total": money_input(receipt.total_cents),
            "gst": money_input(receipt.gst_cents),
            "savings": money_input(receipt.savings_cents),
            "warnings": receipt_warnings(receipt),
            "preview_kind": (
                "image"
                if receipt.upload_file
                and receipt.upload_file.media_type.startswith("image/")
                else "pdf"
            ),
            "items": [
                {
                    "description": item.description,
                    "quantity": format(item.quantity.normalize(), "f"),
                    "unit": item.quantity_unit,
                    "line_total": money_input(item.line_total_cents),
                    "category": item.category,
                    "product_number": item.product_number or "",
                }
                for item in receipt.items
            ],
        }
    )
    return view


def receipt_balance(receipt: Receipt) -> dict[str, Any]:
    """Compare the sum of line items against the stated receipt total."""

    line_sum = sum(item.line_total_cents or 0 for item in receipt.items)
    stated = receipt.total_cents or 0
    difference = stated - line_sum
    return {
        "line_items_sum": line_sum,
        "stated_total": stated,
        "difference": difference,
        # Small rounding differences are normal on real receipts; five cents
        # matches the review warning threshold.
        "reconciled": receipt.total_cents is not None and abs(difference) <= 5,
    }


def load_receipt(
    session: Session,
    receipt_id: str,
    *,
    with_items: bool = True,
    household_id: int | None = None,
) -> Receipt:
    """Fetch a receipt with its items and upload file, or raise ``NotFoundError``.

    When `household_id` is given, a receipt belonging to a different household
    is reported as *not found* rather than *forbidden*, so the API never
    confirms that someone else's receipt id exists.
    """

    query = select(Receipt).where(Receipt.id == receipt_id)
    if household_id is not None:
        query = query.where(Receipt.household_id == household_id)
    if with_items:
        query = query.options(
            selectinload(Receipt.items), selectinload(Receipt.upload_file)
        )
    receipt = session.scalar(query)
    if receipt is None:
        raise NotFoundError(
            f"Receipt {receipt_id} not found.", code="RECEIPT_NOT_FOUND"
        )
    return receipt


def resolve_receipt_items(session: Session, receipt: Receipt) -> Sequence[ReceiptItem]:
    """Return a receipt's items, falling back to its canonical duplicate source."""

    if receipt.items or not receipt.duplicate_of_id:
        return receipt.items
    canonical = session.scalar(
        select(Receipt)
        .where(Receipt.id == receipt.duplicate_of_id)
        .options(selectinload(Receipt.items))
    )
    return canonical.items if canonical is not None else receipt.items


# ---------------------------------------------------------------------------
# Upload job progress
# ---------------------------------------------------------------------------


def job_payload(
    session: Session,
    batch_id: str,
    *,
    household_id: int | None = None,
) -> dict[str, Any] | None:
    """Describe an upload batch's processing stage for polling clients."""

    query = select(UploadBatch).where(UploadBatch.id == batch_id)
    if household_id is not None:
        query = query.where(UploadBatch.household_id == household_id)
    batch = session.scalar(query.options(selectinload(UploadBatch.files)))
    if batch is None:
        return None
    receipt = session.scalar(
        select(Receipt)
        .where(Receipt.upload_file_id.in_([entry.id for entry in batch.files]))
        .order_by(Receipt.created_at.desc())
        .limit(1)
    )
    status = receipt.status if receipt is not None else batch.status
    failed_job = None
    if status not in TERMINAL_UPLOAD_STATUSES:
        jobs = session.scalars(
            select(BackgroundJob)
            .where(BackgroundJob.kind == "receipt_extract")
            .order_by(BackgroundJob.created_at.desc())
        ).all()
        failed_job = next(
            (
                job
                for job in jobs
                if str((job.payload or {}).get("batch_id")) == batch.id
                and job.status == JobStatus.FAILED
            ),
            None,
        )
        if failed_job is not None:
            status = ProcessingStatus.FAILED
    status_value = enum_value(status)
    heading, message = JOB_COPY[status_value]
    if status_value == "failed":
        message = str(
            getattr(failed_job, "last_error", "") or "Open it and enter the details manually."
        )
    destination = None
    if receipt is not None:
        destination = (
            f"/receipts/{receipt.id}/review"
            if receipt.status in REVIEWABLE_STATUSES
            else f"/receipts/{receipt.id}"
        )
    elif status_value == "failed":
        destination = "/receipts"
    return {
        "id": batch.id,
        "status": status_value,
        "progress": JOB_PROGRESS.get(status_value, 10),
        "heading": heading,
        "message": message,
        "destination": destination,
        "receipt_id": receipt.id if receipt is not None else None,
        "total_files": batch.total_files,
        "processed_files": batch.processed_files,
    }


# ---------------------------------------------------------------------------
# Receipt confirmation (shared write path)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReceiptLineDraft:
    """One corrected line item supplied by a reviewer."""

    description: str
    quantity: Decimal
    unit: str
    line_total_cents: int
    category: str
    product_number: str | None = None


@dataclass(frozen=True, slots=True)
class ReceiptDraft:
    """The corrected receipt a reviewer is asking to file.

    ``purchase_date`` may be ``None``: the filing gate only requires a merchant
    and a total.  An undated receipt is still filed and visible, but analytics
    eligibility excludes it until a date is supplied, so it cannot skew dated
    trends or contribute a price observation.
    """

    merchant_name: str
    total_cents: int
    purchase_date: date | None = None
    purchase_time: time | None = None
    subtotal_cents: int | None = None
    gst_cents: int | None = None
    savings_cents: int | None = None
    is_grocery: bool = True
    items: tuple[ReceiptLineDraft, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    receipt: Receipt
    is_duplicate: bool
    duplicate_of_id: str | None
    dated: bool


def categorize_description(description: str) -> str:
    """Classify a line item, falling back to ``unmapped`` without the ruleset."""

    try:
        from categorize import categorize

        return categorize(description)
    except ImportError:
        return "unmapped"


def available_categories() -> list[str]:
    """List the categories a reviewer can choose from."""

    try:
        from categorize import RULES

        return sorted({"unmapped", *(category for _, category in RULES)})
    except ImportError:
        return ["unmapped"]


def confirm_receipt(
    session: Session,
    receipt: Receipt,
    draft: ReceiptDraft,
) -> ConfirmationResult:
    """Apply a reviewer's corrections and file the receipt in the ledger.

    Shared by the HTML review form and the JSON API so both enforce the same
    filing gate, duplicate detection and analytics refresh.
    """

    merchant = draft.merchant_name.strip()
    if not merchant:
        raise ServiceError("Store name is required.", field="merchant_name")
    # A missing line item is surfaced by receipt_warnings rather than blocking
    # the filing gate: a person correcting a receipt may legitimately clear the
    # items OCR guessed wrong and keep only the merchant and total.

    merchant_key = normalize_key_part(merchant).replace(" ", "_")[:80] or "unknown"
    natural_key = make_receipt_natural_key(
        merchant=merchant_key,
        purchase_date=draft.purchase_date,
        transaction_number=receipt.transaction_number,
        total_cents=draft.total_cents,
        store_number=receipt.store_number,
        pos_number=receipt.pos_number,
    )
    duplicate = None
    if natural_key:
        duplicate = session.scalar(
            select(Receipt).where(
                Receipt.id != receipt.id,
                Receipt.natural_key == natural_key,
                Receipt.duplicate_of_id.is_(None),
            )
        )

    receipt.merchant_name = merchant
    receipt.merchant_key = merchant_key
    receipt.purchase_date = draft.purchase_date
    receipt.purchase_time = draft.purchase_time
    receipt.subtotal_cents = draft.subtotal_cents
    receipt.total_cents = draft.total_cents
    receipt.gst_cents = draft.gst_cents
    receipt.savings_cents = draft.savings_cents
    receipt.is_grocery = draft.is_grocery
    receipt.natural_key = natural_key
    receipt.duplicate_of_id = duplicate.id if duplicate else None
    receipt.status = (
        ProcessingStatus.DUPLICATE if duplicate else ProcessingStatus.COMPLETE
    )
    receipt.confirmed_at = utc_now()

    session.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id))
    for line_number, item in enumerate(draft.items, start=1):
        unit_price = None
        if item.quantity:
            unit_price = int(
                (Decimal(item.line_total_cents) / item.quantity).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
        session.add(
            ReceiptItem(
                id=new_id(),
                receipt_id=receipt.id,
                line_number=line_number,
                description=item.description,
                normalized_description=normalize_key_part(item.description),
                product_key=product_identity(item.product_number, item.description),
                product_number=item.product_number,
                category=item.category,
                quantity=item.quantity,
                quantity_unit=item.unit,
                unit_price_cents=unit_price,
                line_total_cents=item.line_total_cents,
                needs_review=False,
            )
        )

    if receipt.upload_file is not None:
        receipt.upload_file.status = receipt.status
        batch = receipt.upload_file.batch
        if batch is not None:
            batch.status = receipt.status
            batch.processed_files = batch.total_files
            batch.completed_at = utc_now()

    session.flush()
    refresh_analytics_snapshot(session)
    enqueue_job(
        session,
        "advanced_analytics",
        {"receipt_id": receipt.id},
        dedupe_key=f"advanced:{receipt.id}",
    )
    return ConfirmationResult(
        receipt=receipt,
        is_duplicate=duplicate is not None,
        duplicate_of_id=duplicate.id if duplicate else None,
        dated=draft.purchase_date is not None,
    )


def build_line_drafts(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[ReceiptLineDraft, ...]:
    """Validate raw line-item rows from either transport into drafts."""

    drafts: list[ReceiptLineDraft] = []
    for index, row in enumerate(rows):
        position = index + 1
        description = str(row.get("description") or "").strip()
        if not description:
            raise ServiceError(
                f"Item {position} needs a description.",
                field=f"items.{index}.description",
            )
        try:
            quantity = parse_quantity(
                row.get("quantity"), field_name=f"items.{index}.quantity"
            )
            line_total = parse_money(
                row.get("line_total"),
                required=True,
                field_name=f"items.{index}.line_total",
            )
        except ServiceError as exc:
            raise ServiceError(
                f"Item {position}: {exc.message}", field=exc.field
            ) from exc
        category = str(row.get("category") or "").strip() or categorize_description(
            description
        )
        product_number = str(row.get("product_number") or "").strip() or None
        drafts.append(
            ReceiptLineDraft(
                description=description,
                quantity=quantity,
                unit=str(row.get("unit") or "each").strip() or "each",
                line_total_cents=int(line_total or 0),
                category=category,
                product_number=product_number,
            )
        )
    return tuple(drafts)


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------


def shopping_item_view(item: ShoppingItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "description": item.description,
        "quantity": format(item.quantity.normalize(), "f"),
        "quantity_label": quantity_label(item.quantity, item.unit),
        "unit": item.unit,
        "note": item.note,
        "status": enum_value(item.status),
        "source": (
            "prediction" if item.source == ShoppingSource.PREDICTED else "manual"
        ),
        "completed_label": (
            f"{item.completed_at.astimezone().day} "
            f"{item.completed_at.astimezone().strftime('%b')}"
            if item.completed_at
            else ""
        ),
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "estimated_price_cents": item.estimated_price_cents,
        "version": item.version,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def active_shopping_items(session: Session) -> Sequence[ShoppingItem]:
    return session.scalars(
        select(ShoppingItem)
        .where(ShoppingItem.status == ShoppingStatus.ACTIVE)
        .order_by(ShoppingItem.created_at, ShoppingItem.description)
    ).all()


def completed_shopping_items(session: Session, *, limit: int = 20) -> Sequence[ShoppingItem]:
    return session.scalars(
        select(ShoppingItem)
        .where(ShoppingItem.status == ShoppingStatus.COMPLETED)
        .order_by(ShoppingItem.completed_at.desc())
        .limit(limit)
    ).all()


def load_shopping_item(session: Session, item_id: str) -> ShoppingItem:
    item = session.get(ShoppingItem, item_id)
    if item is None:
        raise NotFoundError(
            "Shopping item not found.", code="SHOPPING_ITEM_NOT_FOUND"
        )
    return item


def _check_version(item: ShoppingItem, expected_version: int | None) -> None:
    """Reject a write made against a stale copy of a shared list item."""

    if expected_version is not None and expected_version != item.version:
        raise ConflictError(
            "Another household device changed this item. Reload the list."
        )


def add_shopping_item(
    session: Session,
    *,
    description: str,
    quantity: Any = "1",
    unit: str = "each",
    note: str | None = None,
) -> ShoppingItem:
    cleaned = description.strip()
    if not cleaned:
        raise ServiceError("Enter an item to add.", field="description")
    item = ShoppingItem(
        id=new_id(),
        product_key=product_identity(None, cleaned),
        description=cleaned[:255],
        quantity=parse_quantity(quantity, field_name="quantity"),
        unit=(unit or "each").strip()[:32] or "each",
        note=(note or "").strip()[:500] or None,
        status=ShoppingStatus.ACTIVE,
        source=ShoppingSource.MANUAL,
    )
    session.add(item)
    session.flush()
    return item


def update_shopping_item(
    session: Session,
    item_id: str,
    *,
    description: str | None = None,
    quantity: Any = None,
    unit: str | None = None,
    note: str | None = None,
    expected_version: int | None = None,
) -> ShoppingItem:
    item = load_shopping_item(session, item_id)
    _check_version(item, expected_version)
    cleaned = (description if description is not None else item.description).strip()
    if not cleaned:
        raise ServiceError("Item description is required.", field="description")
    item.description = cleaned[:255]
    item.product_key = product_identity(None, item.description)
    item.quantity = parse_quantity(
        quantity if quantity is not None else item.quantity, field_name="quantity"
    )
    item.unit = (unit if unit is not None else item.unit).strip()[:32] or "each"
    if note is not None:
        item.note = note.strip()[:500] or None
    item.version += 1
    session.flush()
    return item


def toggle_shopping_item(
    session: Session,
    item_id: str,
    *,
    expected_version: int | None = None,
) -> ShoppingItem:
    item = load_shopping_item(session, item_id)
    _check_version(item, expected_version)
    if item.status == ShoppingStatus.COMPLETED:
        item.status = ShoppingStatus.ACTIVE
        item.completed_at = None
    else:
        item.status = ShoppingStatus.COMPLETED
        item.completed_at = utc_now()
    item.version += 1
    session.flush()
    return item


def remove_shopping_item(
    session: Session,
    item_id: str,
    *,
    expected_version: int | None = None,
) -> ShoppingItem:
    item = load_shopping_item(session, item_id)
    _check_version(item, expected_version)
    item.status = ShoppingStatus.DISMISSED
    item.dismissed_until = utc_now() + timedelta(days=30)
    item.version += 1
    session.flush()
    return item


def accept_suggestion(session: Session, key: str) -> ShoppingItem:
    suggestion = find_suggestion(session, key)
    item = ShoppingItem(
        id=new_id(),
        product_key=suggestion["key"],
        description=suggestion["description"],
        quantity=parse_quantity(suggestion["quantity"]),
        unit="each",
        status=ShoppingStatus.ACTIVE,
        source=ShoppingSource.PREDICTED,
        estimated_price_cents=suggestion["estimated_cost_cents"],
        due_date=suggestion["due"],
    )
    session.add(item)
    session.flush()
    return item


def dismiss_suggestion(session: Session, key: str) -> ShoppingItem:
    suggestion = find_suggestion(session, key)
    item = ShoppingItem(
        id=new_id(),
        product_key=suggestion["key"],
        description=suggestion["description"],
        quantity=parse_quantity(suggestion["quantity"]),
        status=ShoppingStatus.DISMISSED,
        source=ShoppingSource.PREDICTED,
        estimated_price_cents=suggestion["estimated_cost_cents"],
        due_date=suggestion["due"],
        dismissed_until=utc_now() + timedelta(days=30),
    )
    session.add(item)
    session.flush()
    return item


__all__ = [
    "COLLECTION_ICONS",
    "receipt_collection",
    "pin_configured_household",
    "delete_receipt",
    "REVIEWABLE_STATUSES",
    "TERMINAL_UPLOAD_STATUSES",
    "ConflictError",
    "ConfirmationResult",
    "collection_icon",
    "normalize_collection_id",
    "HouseholdOverview",
    "NotFoundError",
    "ReceiptDraft",
    "ReceiptLineDraft",
    "ServiceError",
    "accept_suggestion",
    "active_shopping_items",
    "add_shopping_item",
    "available_categories",
    "build_line_drafts",
    "categorize_description",
    "completed_shopping_items",
    "confirm_receipt",
    "current_snapshot",
    "date_label",
    "dismiss_suggestion",
    "due_suggestions",
    "enum_value",
    "find_suggestion",
    "household_overview",
    "household_today",
    "human_date",
    "job_payload",
    "load_receipt",
    "load_shopping_item",
    "money",
    "money_input",
    "next_weekly_price_run",
    "parse_date",
    "parse_money",
    "parse_quantity",
    "parse_time",
    "quantity_label",
    "receipt_balance",
    "receipt_review_view",
    "receipt_view",
    "receipt_warnings",
    "remove_shopping_item",
    "resolve_receipt_items",
    "shopping_item_view",
    "snapshot_payload",
    "status_presentation",
    "toggle_shopping_item",
    "update_shopping_item",
]
