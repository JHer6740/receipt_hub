"""FastAPI routes for the ``/api/v1`` JSON layer used by the Flutter client.

These routes are a second transport over the same household logic the Jinja web
UI uses: everything substantive lives in :mod:`grocery_home.services`.  The two
differences from the web routes are authentication and error shape.

Authentication uses the *same* signed session token the browser receives in its
cookie, but presented as an ``Authorization: Bearer`` header.  Because browsers
never attach that header automatically, the JSON API needs no CSRF token, while
the cookie-authenticated web UI keeps its existing CSRF protection.  A PIN
rotation bumps ``Household.session_generation`` and therefore revokes issued API
tokens along with browser sessions.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Sequence

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi import UploadFile as UploadPart
from fastapi.responses import FileResponse
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session, selectinload

from . import api_schemas as schemas
from . import services
from .config import Settings, get_settings
from .database import create_database, initialize_schema
from .ingestion import (
    UploadValidationError,
    create_upload_batch,
    validate_and_store_uploads,
)
from .jobs import enqueue_job
from .models import (
    Household,
    ProcessingStatus,
    Receipt,
    UploadBatch,
    UploadFile,
    utc_now,
)
from .security import (
    InvalidSessionError,
    PinThrottle,
    SessionManager,
    authenticate_shared_pin,
    session_matches_household,
)


router = APIRouter(prefix="/api/v1", tags=["api"])

HOUSEHOLD_ID = 1

# Every terminal upload state maps onto one of three client-facing outcomes so
# the Flutter processing screen never has to know the server's internal states.
UPLOAD_OUTCOME: dict[str, str] = {
    "queued": "in_progress",
    "extracting": "in_progress",
    "needs_review": "complete",
    "complete": "complete",
    "duplicate": "complete",
    "failed": "failed",
}

PROCESSING_STAGES: tuple[str, ...] = ("upload", "detect", "read", "extract", "file")

# How far each stage has advanced once a batch reaches a given status.
STAGE_PROGRESS: dict[str, int] = {
    "queued": 1,
    "extracting": 3,
    "needs_review": 5,
    "complete": 5,
    "duplicate": 5,
    "failed": 2,
}


# ============================================================================
# Request plumbing
# ============================================================================


def get_db(request: Request) -> Any:
    """Provide a per-request SQLAlchemy session for API endpoints."""

    active_database = getattr(request.app.state, "database", None)
    if active_database is None:
        active_database = create_database(get_settings())
        request.app.state.database = active_database
        initialize_schema(active_database)
    with active_database.session() as session:
        yield session


def get_settings_for(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def trace_id_for(request: Request) -> str:
    return getattr(request.state, "trace_id", None) or str(uuid.uuid4())[:8]


def api_response(
    success: bool = True,
    data: dict[str, Any] | list[Any] | None = None,
    error: schemas.ApiError | None = None,
    trace_id: str = "",
) -> dict[str, Any]:
    """Build the standard API response envelope."""

    return {
        "success": success,
        "data": data,
        "error": error.model_dump(mode="json") if error else None,
        "timestamp": datetime.now(UTC).isoformat(),
        "trace_id": trace_id or str(uuid.uuid4())[:8],
    }


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    trace_id: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    """Raise a failure that the app's handler renders as the error envelope."""

    error = schemas.ApiError(
        code=code,
        message=message,
        details=details,
        timestamp=datetime.now(UTC),
        trace_id=trace_id,
    )
    return HTTPException(status_code=status_code, detail=error.model_dump(mode="json"))


def service_error(exc: services.ServiceError, trace_id: str) -> HTTPException:
    """Translate a shared-service failure into a typed JSON field error."""

    return api_error(
        exc.status_code,
        exc.code,
        exc.message,
        trace_id=trace_id,
        details={"field": exc.field} if exc.field else None,
    )


# ============================================================================
# Authentication
# ============================================================================


def get_bearer_token(request: Request) -> str:
    """Read the bearer token, ignoring cookies so the API stays CSRF-immune."""

    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "MISSING_TOKEN",
            "Provide an Authorization: Bearer token.",
            trace_id=trace_id_for(request),
        )
    return token.strip()


def authenticate_api_request(
    request: Request,
    session: Session = Depends(get_db),
    token: str = Depends(get_bearer_token),
) -> tuple[Household, str]:
    """Validate the signed bearer token and return its household."""

    trace = trace_id_for(request)
    manager: SessionManager | None = getattr(request.app.state, "session_manager", None)
    if manager is None:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "NOT_CONFIGURED",
            "This Receipts Hub is still starting up. Try again shortly.",
            trace_id=trace,
        )
    try:
        data = manager.load(token)
    except InvalidSessionError as exc:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "This session has expired or is not valid. Sign in again.",
            trace_id=trace,
        ) from exc

    household = session.get(Household, data.household_id)
    if household is None or not session_matches_household(data, household):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "This session has expired or is not valid. Sign in again.",
            trace_id=trace,
        )
    return household, trace


AuthenticatedHousehold = Annotated[
    tuple[Household, str], Depends(authenticate_api_request)
]
DbSession = Annotated[Session, Depends(get_db)]


# ============================================================================
# Health
# ============================================================================


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe for Docker, the Flutter first-connection screen, and LAN
    recovery after the host sleeps."""

    return {
        "status": "ok",
        "service": "grocery-home",
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ============================================================================
# Authentication endpoints
# ============================================================================


@router.post("/auth/pin")
def authenticate_with_pin(
    request: Request,
    body: schemas.PinAuthRequest,
    session: DbSession,
) -> dict[str, Any]:
    """Exchange the household PIN for a signed bearer token."""

    trace = trace_id_for(request)
    settings = get_settings_for(request)

    household = session.get(Household, HOUSEHOLD_ID)
    if household is None:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "NOT_CONFIGURED",
            "Run the one-time setup command on the host PC first.",
            trace_id=trace,
        )

    throttle: PinThrottle = request.app.state.pin_throttle
    client_key = request.client.host if request.client else "unknown"
    result = authenticate_shared_pin(
        session, household, body.pin, client_key, throttle
    )

    if not result.authenticated:
        # The throttle counts this attempt in the same session. Raising here
        # would roll that write back with the request transaction, so the
        # counter is committed first -- otherwise the PIN could be brute
        # forced over this API no matter how many attempts failed.
        session.commit()
        if result.rate_limited:
            raise api_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "RATE_LIMITED",
                f"Too many failed attempts. Try again in {result.retry_after_seconds} seconds.",
                trace_id=trace,
                details={"retry_after_seconds": result.retry_after_seconds},
            )
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_PIN",
            "That PIN did not match.",
            trace_id=trace,
        )

    manager: SessionManager = request.app.state.session_manager
    issued = manager.issue(household.id, household.session_generation)
    expires_in = settings.session_max_age_seconds
    payload = schemas.SessionTokenData(
        session_token=issued.token,
        token_type="Bearer",
        expires_in=expires_in,
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
    )
    return api_response(
        data={
            **payload.model_dump(mode="json"),
            "household": {"name": household.display_name},
        },
        trace_id=trace,
    )


@router.delete("/auth")
def logout(auth: AuthenticatedHousehold) -> dict[str, Any]:
    """Sign out this device.

    Tokens are stateless signatures, so this endpoint confirms the client should
    discard its copy.  To revoke tokens already handed out, rotate the household
    PIN, which bumps the session generation and invalidates every issued token.
    """

    _household, trace = auth
    return api_response(data={"status": "logged_out"}, trace_id=trace)


# ============================================================================
# Bootstrap
# ============================================================================


def _collection_summaries(
    overview: services.HouseholdOverview,
) -> list[schemas.CollectionSummary]:
    """Present category spending as the client's Collections.

    Collections are backed by the backend's existing line-item categories rather
    than a parallel taxonomy, so a category rename stays consistent everywhere.
    """

    return [
        schemas.CollectionSummary(
            id=services.normalize_collection_id(row["category"]),
            name=str(row["category"]).title(),
            icon=services.collection_icon(row["category"]),
            month_total=row["spend_cents"],
            month_delta_percent=None,
        )
        for row in overview.categories
    ]


@router.get("/bootstrap")
def bootstrap(auth: AuthenticatedHousehold, session: DbSession) -> dict[str, Any]:
    """Return the initial app state a client needs on launch."""

    household, trace = auth
    overview = services.household_overview(session)

    data = schemas.BootstrapData(
        household=schemas.HouseholdInfo(
            name=household.display_name,
            created_at=household.created_at,
        ),
        totals=schemas.TotalsData(
            month_total=overview.month_spend_cents,
            month_trend=[
                schemas.MonthTrendPoint(month=row["month"], total=row["total_cents"])
                for row in overview.monthly_trend
            ],
        ),
        collections=_collection_summaries(overview),
        settings=schemas.BootstrapSettings(
            sharing_consent=False,
            preferred_merchants=[],
            backup_enabled=False,
            last_backup=None,
        ),
    )
    return api_response(
        data={
            **data.model_dump(mode="json"),
            "counts": {
                "receipts": overview.receipt_count,
                "active_list_items": overview.active_list_count,
            },
        },
        trace_id=trace,
    )


# ============================================================================
# Receipts
# ============================================================================


def _image_count(receipt: Receipt) -> int:
    upload = receipt.upload_file
    if upload is None:
        return 0
    batch = upload.batch
    return len(batch.files) if batch is not None else 1


def _receipt_summary(receipt: Receipt) -> dict[str, Any]:
    return {
        "id": receipt.id,
        "merchant": receipt.merchant_name or receipt.store_name or "Unknown shop",
        "date": receipt.purchase_date.isoformat() if receipt.purchase_date else None,
        "total": receipt.total_cents or 0,
        "status": services.enum_value(receipt.status),
        "collection_id": None,
        "collection_name": None,
        "image_count": _image_count(receipt),
        "item_count": len(receipt.items),
        "attention_required": receipt.status in services.REVIEWABLE_STATUSES,
        # An undated receipt is filed but held out of dated analytics until a
        # date is supplied; the client surfaces this without blocking filing.
        "dated": receipt.purchase_date is not None,
        "created_at": receipt.created_at.isoformat(),
    }


@router.get("/receipts")
def list_receipts(
    auth: AuthenticatedHousehold,
    session: DbSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    attention_only: bool = Query(False),
    merchant: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> dict[str, Any]:
    """List receipts newest first, with pagination and filters."""

    _household, trace = auth

    filters: list[Any] = []
    if attention_only:
        filters.append(Receipt.status.in_(list(services.REVIEWABLE_STATUSES)))
    else:
        filters.append(Receipt.duplicate_of_id.is_(None))
    if merchant:
        filters.append(Receipt.merchant_name.ilike(f"%{merchant}%"))
    if start_date:
        filters.append(Receipt.purchase_date >= start_date)
    if end_date:
        filters.append(Receipt.purchase_date <= end_date)

    condition = and_(*filters) if filters else True
    total = session.scalar(select(func.count(Receipt.id)).where(condition)) or 0
    receipts = session.scalars(
        select(Receipt)
        .where(condition)
        .order_by(desc(Receipt.purchase_date), desc(Receipt.created_at))
        .offset(offset)
        .limit(limit)
        .options(
            selectinload(Receipt.items),
            selectinload(Receipt.upload_file).selectinload(UploadFile.batch),
        )
    ).all()

    return api_response(
        data={
            "items": [_receipt_summary(receipt) for receipt in receipts],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(receipts) < total,
            },
        },
        trace_id=trace,
    )


@router.get("/receipts/{receipt_id}")
def get_receipt(
    receipt_id: str,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Return one receipt with its line items and balance strip."""

    _household, trace = auth
    try:
        receipt = services.load_receipt(session, receipt_id)
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc

    items = services.resolve_receipt_items(session, receipt)
    image_count = _image_count(receipt)
    detail = {
        **_receipt_summary(receipt),
        "subtotal": receipt.subtotal_cents,
        "tax": receipt.gst_cents,
        "savings": receipt.savings_cents,
        "is_grocery": receipt.is_grocery,
        "duplicate_of_id": receipt.duplicate_of_id,
        "balance": services.receipt_balance(receipt),
        "warnings": services.receipt_warnings(receipt),
        "image_urls": [
            f"/api/v1/receipts/{receipt.id}/image?page={page}"
            for page in range(1, image_count + 1)
        ],
        "line_items": [
            {
                "id": item.id,
                "product": item.description,
                "quantity": str(item.quantity.normalize()),
                "unit": item.quantity_unit,
                "unit_price": item.unit_price_cents,
                "total_price": item.line_total_cents or 0,
                "category": item.category,
                "product_id": item.product_key,
                "product_number": item.product_number,
                # Line items flagged during OCR keep their uncertainty marker so
                # the client can highlight exactly what a person should check.
                "needs_review": item.needs_review,
            }
            for item in items
        ],
        "updated_at": receipt.updated_at.isoformat(),
    }
    return api_response(data=detail, trace_id=trace)


@router.patch("/receipts/{receipt_id}")
def update_receipt(
    receipt_id: str,
    body: schemas.UpdateReceiptRequest,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Apply a reviewer's corrections and file the receipt.

    This is the JSON twin of the web review form: both call
    :func:`services.confirm_receipt`, so duplicate detection, the filing gate and
    the analytics refresh behave identically.
    """

    _household, trace = auth
    try:
        receipt = services.load_receipt(session, receipt_id)
        existing = services.resolve_receipt_items(session, receipt)
        if body.line_items is not None:
            rows = body.line_items
        else:
            rows = [
                {
                    "description": item.description,
                    "quantity": str(item.quantity),
                    "unit": item.quantity_unit,
                    "line_total": services.money_input(item.line_total_cents),
                    "category": item.category,
                    "product_number": item.product_number,
                }
                for item in existing
            ]

        draft = services.ReceiptDraft(
            merchant_name=body.merchant
            if body.merchant is not None
            else (receipt.merchant_name or ""),
            total_cents=(
                body.total if body.total is not None else (receipt.total_cents or 0)
            ),
            purchase_date=(
                body.purchase_date
                if body.purchase_date is not None
                else receipt.purchase_date
            ),
            purchase_time=receipt.purchase_time,
            subtotal_cents=receipt.subtotal_cents,
            gst_cents=body.tax if body.tax is not None else receipt.gst_cents,
            savings_cents=receipt.savings_cents,
            is_grocery=receipt.is_grocery,
            items=services.build_line_drafts(rows),
        )
        result = services.confirm_receipt(session, receipt, draft)
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc

    session.commit()
    return api_response(
        data={
            **_receipt_summary(result.receipt),
            "is_duplicate": result.is_duplicate,
            "duplicate_of_id": result.duplicate_of_id,
        },
        trace_id=trace,
    )


@router.get("/receipts/{receipt_id}/image")
def get_receipt_image(
    receipt_id: str,
    request: Request,
    auth: AuthenticatedHousehold,
    session: DbSession,
    page: int = Query(1, ge=1),
) -> FileResponse:
    """Serve a stored receipt photo to an authenticated client.

    Household receipts are private, so images are streamed through this
    bearer-authenticated route rather than a public or guessable static path.
    """

    _household, trace = auth
    try:
        receipt = services.load_receipt(session, receipt_id)
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc

    upload = receipt.upload_file
    if upload is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "IMAGE_NOT_FOUND",
            "This receipt has no stored image.",
            trace_id=trace,
        )
    batch_files = sorted(upload.batch.files, key=lambda row: row.ordinal) if upload.batch else [upload]
    if page > len(batch_files):
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "IMAGE_NOT_FOUND",
            f"This receipt has {len(batch_files)} page(s).",
            trace_id=trace,
        )
    target = batch_files[page - 1]

    settings = get_settings_for(request)
    root = settings.receipt_dir.resolve()
    path = (root / target.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "IMAGE_NOT_FOUND",
            "That receipt file is no longer on the host.",
            trace_id=trace,
        )
    return FileResponse(
        path,
        media_type=target.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ============================================================================
# Uploads and processing
# ============================================================================


def _stage_report(status_value: str) -> list[dict[str, Any]]:
    """Expand a batch status into the client's five-stage progress display."""

    reached = STAGE_PROGRESS.get(status_value, 1)
    failed = status_value == "failed"
    stages: list[dict[str, Any]] = []
    for index, name in enumerate(PROCESSING_STAGES, start=1):
        if index < reached:
            state, progress = "complete", 100
        elif index == reached:
            if failed:
                state, progress = "failed", 0
            elif status_value in {"needs_review", "complete", "duplicate"}:
                state, progress = "complete", 100
            else:
                state, progress = "in_progress", 50
        else:
            state, progress = "pending", 0
        stages.append({"name": name, "status": state, "progress": progress})
    return stages


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def create_upload(
    request: Request,
    auth: AuthenticatedHousehold,
    session: DbSession,
    files: Annotated[list[UploadPart], File()],
) -> dict[str, Any]:
    """Accept one to five ordered receipt photos and queue them for reading."""

    _household, trace = auth
    settings = get_settings_for(request)

    if not files:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "NO_FILES",
            "Attach at least one receipt photo.",
            trace_id=trace,
        )
    if len(files) > settings.max_photo_files:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "TOO_MANY_FILES",
            f"Attach at most {settings.max_photo_files} photos per receipt.",
            trace_id=trace,
        )

    stored: list[Any] = []
    try:
        stored = await asyncio.to_thread(
            validate_and_store_uploads, files, settings.receipt_dir
        )
        batch = create_upload_batch(session, stored)
        enqueue_job(
            session,
            "receipt_extract",
            {"batch_id": batch.id},
            dedupe_key=f"receipt:{batch.id}",
        )
        session.commit()
    except UploadValidationError as exc:
        for entry in stored:
            entry.path.unlink(missing_ok=True)
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_UPLOAD",
            str(exc),
            trace_id=trace,
        ) from exc
    except Exception:
        for entry in stored:
            entry.path.unlink(missing_ok=True)
        raise
    finally:
        for upload in files:
            await upload.close()

    return api_response(
        data={
            "batch_id": batch.id,
            "status": services.enum_value(batch.status),
            "total_files": batch.total_files,
            "poll_url": f"/api/v1/uploads/{batch.id}",
        },
        trace_id=trace,
    )


@router.get("/uploads/{batch_id}")
def get_upload_status(
    batch_id: str,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Report processing progress for an upload batch."""

    _household, trace = auth
    job = services.job_payload(session, batch_id)
    if job is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "BATCH_NOT_FOUND",
            f"Upload batch {batch_id} not found.",
            trace_id=trace,
        )
    status_value = job["status"]
    return api_response(
        data={
            "batch_id": job["id"],
            "receipt_id": job["receipt_id"],
            "status": UPLOAD_OUTCOME.get(status_value, "in_progress"),
            "detail_status": status_value,
            "progress": job["progress"],
            "heading": job["heading"],
            "message": job["message"],
            "stages": _stage_report(status_value),
            "total_files": job["total_files"],
            "processed_files": job["processed_files"],
            "can_retry": status_value == "failed",
        },
        trace_id=trace,
    )


@router.post("/uploads/{batch_id}/retry")
def retry_upload(
    batch_id: str,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Re-queue a failed batch without asking the person to photograph it again.

    The stored files are kept, so a retry preserves the uploaded draft and the
    client can fall back to manual entry against the same images.
    """

    _household, trace = auth
    batch = session.scalar(
        select(UploadBatch)
        .where(UploadBatch.id == batch_id)
        .options(selectinload(UploadBatch.files))
    )
    if batch is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "BATCH_NOT_FOUND",
            f"Upload batch {batch_id} not found.",
            trace_id=trace,
        )

    batch.status = ProcessingStatus.QUEUED
    batch.processed_files = 0
    batch.completed_at = None
    for entry in batch.files:
        entry.status = ProcessingStatus.QUEUED
        entry.error_code = None
        entry.error_message = None
    enqueue_job(
        session,
        "receipt_extract",
        {"batch_id": batch.id},
        dedupe_key=f"receipt:{batch.id}:{utc_now().timestamp():.0f}",
    )
    session.commit()

    return api_response(
        data={"batch_id": batch.id, "status": "in_progress"},
        trace_id=trace,
    )


# ============================================================================
# Shopping list
# ============================================================================


def _shopping_response(session: Session, trace: str) -> dict[str, Any]:
    active = services.active_shopping_items(session)
    completed = services.completed_shopping_items(session)
    payload = services.snapshot_payload(session, create=True)
    return api_response(
        data={
            "items": [services.shopping_item_view(item) for item in active],
            "completed": [services.shopping_item_view(item) for item in completed],
            "suggestions": [
                {
                    "key": row["key"],
                    "description": row["description"],
                    "due": row["due"].isoformat(),
                    "due_label": row["due_label"],
                    "quantity": row["quantity"],
                    "estimated_cost": row["estimated_cost_cents"],
                    "confidence": row["confidence"],
                }
                for row in services.due_suggestions(session, payload, limit=10)
            ],
            "summary": {
                "total_items": len(active),
                "pending": len(active),
                "checked": len(completed),
                "estimated_spend": sum(
                    item.estimated_price_cents or 0 for item in active
                ),
            },
        },
        trace_id=trace,
    )


@router.get("/shopping")
def list_shopping_items(
    auth: AuthenticatedHousehold, session: DbSession
) -> dict[str, Any]:
    """Return the shared household list, completed items and suggestions."""

    _household, trace = auth
    return _shopping_response(session, trace)


@router.post("/shopping", status_code=status.HTTP_201_CREATED)
def add_shopping_item(
    body: schemas.AddShoppingItemRequest,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Add an item to the shared household list."""

    _household, trace = auth
    try:
        item = services.add_shopping_item(
            session,
            description=body.product,
            quantity=body.quantity,
            unit=body.unit or "each",
            note=body.note,
        )
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc
    session.commit()
    return api_response(data=services.shopping_item_view(item), trace_id=trace)


@router.patch("/shopping/{item_id}")
def update_shopping_item(
    item_id: str,
    body: schemas.UpdateShoppingItemRequest,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Edit a list item, rejecting writes made against a stale copy."""

    _household, trace = auth
    try:
        if body.status is not None:
            item = services.toggle_shopping_item(
                session, item_id, expected_version=body.version
            )
        else:
            item = services.update_shopping_item(
                session,
                item_id,
                description=body.product,
                quantity=body.quantity,
                unit=body.unit,
                note=body.note,
                expected_version=body.version,
            )
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc
    session.commit()
    return api_response(data=services.shopping_item_view(item), trace_id=trace)


@router.delete("/shopping/{item_id}")
def delete_shopping_item(
    item_id: str,
    auth: AuthenticatedHousehold,
    session: DbSession,
    version: int | None = Query(None),
) -> dict[str, Any]:
    """Remove an item from the shared list."""

    _household, trace = auth
    try:
        item = services.remove_shopping_item(
            session, item_id, expected_version=version
        )
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc
    session.commit()
    return api_response(
        data={"id": item.id, "status": services.enum_value(item.status)},
        trace_id=trace,
    )


@router.post("/shopping/suggestions/{key:path}/accept", status_code=status.HTTP_201_CREATED)
def accept_shopping_suggestion(
    key: str,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Promote a due-soon suggestion onto the shared list."""

    _household, trace = auth
    try:
        item = services.accept_suggestion(session, key)
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc
    session.commit()
    return api_response(data=services.shopping_item_view(item), trace_id=trace)


@router.post("/shopping/suggestions/{key:path}/dismiss")
def dismiss_shopping_suggestion(
    key: str,
    auth: AuthenticatedHousehold,
    session: DbSession,
) -> dict[str, Any]:
    """Hide a due-soon suggestion for thirty days."""

    _household, trace = auth
    try:
        services.dismiss_suggestion(session, key)
    except services.ServiceError as exc:
        raise service_error(exc, trace) from exc
    session.commit()
    return api_response(data={"key": key, "status": "dismissed"}, trace_id=trace)


# ============================================================================
# Insights
# ============================================================================


@router.get("/insights")
def get_insights(auth: AuthenticatedHousehold, session: DbSession) -> dict[str, Any]:
    """Return spend trends, category breakdown and product history."""

    _household, trace = auth
    payload = services.snapshot_payload(session, create=True)
    overview = services.household_overview(session, payload=payload, trend_months=12)

    products = [
        {
            "product_key": str(row.get("product_key") or ""),
            "description": str(row.get("description") or ""),
            "purchase_count": int(row.get("purchase_count") or 0),
            "total_spend": int(row.get("spend_cents") or 0),
            "last_purchased": row.get("last_purchased"),
            "average_price": int(row.get("average_price_cents") or 0),
        }
        for row in (payload.get("products") or [])[:50]
    ]

    return api_response(
        data={
            "month_total": overview.month_spend_cents,
            "previous_month_total": overview.previous_month_spend_cents,
            "month_change_percent": (
                float(overview.month_change_percent)
                if overview.month_change_percent is not None
                else None
            ),
            "recorded_spend": overview.recorded_spend_cents,
            "forecast_30d": overview.forecast_30d_cents,
            "receipt_count": overview.receipt_count,
            "month_trend": [
                {"month": row["month"], "total": row["total_cents"]}
                for row in overview.monthly_trend
            ],
            "collections": [
                summary.model_dump(mode="json")
                for summary in _collection_summaries(overview)
            ],
            "categories": [
                {
                    "category": row["category"],
                    "spend": row["spend_cents"],
                    "item_count": row["item_count"],
                }
                for row in overview.categories
            ],
            "product_history": products,
        },
        trace_id=trace,
    )


# ============================================================================
# Settings
# ============================================================================


@router.get("/settings")
def get_settings_endpoint(
    request: Request, auth: AuthenticatedHousehold, session: DbSession
) -> dict[str, Any]:
    """Return household settings and host details the client displays."""

    household, trace = auth
    settings = get_settings_for(request)
    receipt_count = (
        session.scalar(
            select(func.count(Receipt.id)).where(
                Receipt.status == ProcessingStatus.COMPLETE
            )
        )
        or 0
    )
    return api_response(
        data={
            "household_name": household.display_name,
            "timezone": household.timezone,
            "currency": household.currency,
            "receipt_count": receipt_count,
            "session_max_age_seconds": settings.session_max_age_seconds,
            "max_photo_files": settings.max_photo_files,
            "max_upload_bytes": settings.max_upload_bytes,
            # The shared price index and hosted backups belong to the later
            # hosted phase; the client shows them as unavailable rather than
            # implying a capability this LAN build does not have.
            "sharing_consent": False,
            "sharing_available": False,
            "backup_enabled": False,
        },
        trace_id=trace,
    )


__all__ = ["router"]
