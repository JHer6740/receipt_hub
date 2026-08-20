"""FastAPI web application for the private Grocery Home household service."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import secrets
import sqlite3
import zipfile
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Generator, Mapping
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import UploadFile as StarletteUploadFile

from . import api as api_v1
from . import services
from .analytics import product_identity, refresh_analytics_snapshot
from .config import Settings, get_settings
from .database import Database, create_database, initialize_schema
from .ingestion import (
    ReceiptExtractionError,
    UploadValidationError,
    create_upload_batch,
    process_upload_batch,
    validate_and_store_uploads,
)
from .jobs import SingleWorker, enqueue_job
from .models import (
    AnalyticsSnapshot,
    BackgroundJob,
    Household,
    JobStatus,
    PriceQuote,
    ProcessingStatus,
    Receipt,
    ReceiptItem,
    ReceiptSource,
    ShoppingItem,
    ShoppingSource,
    ShoppingStatus,
    UploadBatch,
    UploadFile,
    make_receipt_natural_key,
    new_id,
    normalize_key_part,
    utc_now,
)
from .prices import manual_refresh_prices, refresh_live_prices
from .security import (
    InvalidSessionError,
    PinThrottle,
    SessionData,
    SessionManager,
    authenticate_shared_pin,
    configure_household,
    generate_csrf_token,
    get_or_create_session_secret,
    session_matches_household,
    verify_csrf_token,
    verify_pin,
)


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
TEMPLATES = Jinja2Templates(directory=PACKAGE_DIR / "templates")
LOGIN_CSRF_COOKIE = "grocery_home_login_csrf"
TERMINAL_UPLOAD_STATUSES = {
    ProcessingStatus.NEEDS_REVIEW,
    ProcessingStatus.COMPLETE,
    ProcessingStatus.DUPLICATE,
    ProcessingStatus.FAILED,
}
NOTICE_MESSAGES: dict[str, tuple[str, str]] = {
    "receipt-confirmed": ("success", "Receipt confirmed and household totals updated."),
    "list-added": ("success", "Added to the shared household list."),
    "list-updated": ("success", "The shared household list is up to date."),
    "suggestion-dismissed": ("info", "Suggestion hidden for 30 days."),
    "household-saved": ("success", "Household settings saved."),
    "pin-changed": ("success", "PIN changed. Other household devices must sign in again."),
    "prices-queued": ("info", "The Woolworths price check is queued."),
    "backup-created": ("success", "A private backup archive was created."),
}


class AuthenticationRequired(Exception):
    """Internal signal used to redirect browser requests to the PIN screen."""


_money = services.money
_money_input = services.money_input
_enum_value = services.enum_value
_status_presentation = services.status_presentation


def _service_http_error(exc: services.ServiceError) -> HTTPException:
    """Map a shared-service failure onto this transport's HTTP response."""

    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _parse_money(value: Any, *, required: bool = False) -> int | None:
    return services.parse_money(value, required=required)


def _parse_quantity(value: Any) -> Decimal:
    return services.parse_quantity(value)


def _safe_next(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def _with_notice(path: str, notice: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urlencode({'notice': notice})}"


def _notice(request: Request) -> dict[str, str] | None:
    value = request.query_params.get("notice", "")
    if value not in NOTICE_MESSAGES:
        return None
    kind, message = NOTICE_MESSAGES[value]
    return {"kind": kind, "message": message}


# Analytics already normalises the household timezone. Sydney differs from UTC
# by at most one calendar day, so use the configured service snapshot date
# wherever available and this only as an empty-household fallback.
_today = services.household_today
_next_weekly_price_run = services.next_weekly_price_run
_date_label = services.date_label
_human_date = services.human_date
_quantity_label = services.quantity_label
_current_snapshot = services.current_snapshot
_payload = services.snapshot_payload


_suggestions = services.due_suggestions
_receipt_view = services.receipt_view
_receipt_review_view = services.receipt_review_view
_job_payload = services.job_payload


def _fallback_receipt(session: Session, batch_id: str, error: BaseException) -> Receipt:
    """Keep a valid upload correctable even when OCR itself is unavailable."""

    batch = session.scalar(
        select(UploadBatch)
        .where(UploadBatch.id == batch_id)
        .options(selectinload(UploadBatch.files))
    )
    if batch is None or not batch.files:
        raise ReceiptExtractionError(f"Upload batch {batch_id} has no stored files.") from error
    primary = sorted(batch.files, key=lambda row: row.ordinal)[0]
    existing = session.scalar(
        select(Receipt).where(Receipt.upload_file_id == primary.id)
    )
    if existing is not None:
        return existing
    source = (
        ReceiptSource.SCANNED_PDF
        if primary.media_type == "application/pdf"
        else ReceiptSource.IMAGE
    )
    receipt = Receipt(
        id=new_id(),
        upload_file_id=primary.id,
        merchant_name=None,
        merchant_key=None,
        status=ProcessingStatus.NEEDS_REVIEW,
        source_kind=source,
        is_grocery=True,
    )
    session.add(receipt)
    for upload_file in batch.files:
        upload_file.status = ProcessingStatus.NEEDS_REVIEW
        upload_file.error_code = error.__class__.__name__
        upload_file.error_message = str(error)[:2000]
    batch.status = ProcessingStatus.NEEDS_REVIEW
    batch.processed_files = batch.total_files
    session.flush()
    return receipt


async def _worker_loop(worker: SingleWorker, stop: asyncio.Event) -> None:
    worker.recover()
    while not stop.is_set():
        claim = await asyncio.to_thread(worker.run_once)
        if claim is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.8)
            except TimeoutError:
                pass


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    start_worker: bool = True,
) -> FastAPI:
    """Create an app instance; tests can supply an isolated database."""

    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_settings.ensure_directories()
        active_database = database or create_database(active_settings)
        application.state.database = active_database
        initialize_schema(active_database)
        with active_database.session() as session:
            secret = get_or_create_session_secret(
                session, active_settings.session_secret
            )
        application.state.session_manager = SessionManager(
            secret,
            cookie_name=active_settings.session_cookie_name,
            max_age_seconds=active_settings.session_max_age_seconds,
            secure_cookie=active_settings.secure_cookies,
        )
        application.state.pin_throttle = PinThrottle(
            max_failures=active_settings.pin_max_failures,
            window_seconds=active_settings.pin_window_seconds,
            lock_seconds=active_settings.pin_lock_seconds,
            fingerprint_pepper=secret[:32],
        )

        def receipt_handler(session: Session, payload: Mapping[str, Any]) -> None:
            batch_id = str(payload.get("batch_id") or "")
            try:
                receipt = process_upload_batch(
                    session,
                    batch_id,
                    storage_dir=active_settings.receipt_dir,
                )
            except Exception as exc:
                receipt = _fallback_receipt(session, batch_id, exc)
            if receipt.status == ProcessingStatus.COMPLETE:
                refresh_analytics_snapshot(session)
                enqueue_job(
                    session,
                    "advanced_analytics",
                    {"receipt_id": receipt.id},
                    dedupe_key=f"advanced:{receipt.id}",
                )

        def analytics_handler(session: Session, _payload: Mapping[str, Any]) -> None:
            refresh_analytics_snapshot(session)

        def price_handler(session: Session, payload: Mapping[str, Any]) -> None:
            if payload.get("force"):
                manual_refresh_prices(session)
            else:
                refresh_live_prices(session)

        worker = SingleWorker(
            active_database,
            {
                "receipt_extract": receipt_handler,
                "analytics_refresh": analytics_handler,
                "advanced_analytics": analytics_handler,
                "price_refresh": price_handler,
            },
        )
        stop_event = asyncio.Event()
        worker_task: asyncio.Task[None] | None = None
        if start_worker:
            with active_database.session() as session:
                scheduled_for = _next_weekly_price_run()
                enqueue_job(
                    session,
                    "price_refresh",
                    {},
                    dedupe_key=f"weekly-prices:{scheduled_for.date().isoformat()}",
                    scheduled_for=scheduled_for,
                )
            worker_task = asyncio.create_task(_worker_loop(worker, stop_event))
        try:
            yield
        finally:
            stop_event.set()
            if worker_task is not None:
                await worker_task
            if database is None:
                active_database.dispose()

    application = FastAPI(
        title="Grocery Home",
        version="0.1.0",
        # The household web UI is server-rendered and has no schema to publish,
        # but the mobile client is a separate codebase that needs a contract it
        # can check itself against, so /api/v1 documents itself.
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.settings = active_settings
    application.mount(
        "/static",
        StaticFiles(directory=PACKAGE_DIR / "static"),
        name="static",
    )
    application.mount(
        "/vendor",
        StaticFiles(directory=PROJECT_DIR / "vendor"),
        name="vendor",
    )

    def database_session(request: Request) -> Generator[Session, None, None]:
        active_database: Database | None = getattr(request.app.state, "database", None)
        if active_database is None:
            active_database = create_database(active_settings)
            request.app.state.database = active_database
            initialize_schema(active_database)
        with active_database.session() as session:
            yield session

    def authenticated(
        request: Request,
        session: Session,
    ) -> tuple[Household, SessionData]:
        manager: SessionManager = request.app.state.session_manager
        try:
            data = manager.load_request(request)
        except InvalidSessionError as exc:
            raise AuthenticationRequired from exc
        household = session.get(Household, data.household_id)
        if household is None or not session_matches_household(data, household):
            raise AuthenticationRequired
        return household, data

    def require_csrf(
        request: Request,
        session: Session,
        supplied: Any,
    ) -> tuple[Household, SessionData]:
        household, data = authenticated(request, session)
        if not verify_csrf_token(data.csrf_token, str(supplied or "")):
            raise HTTPException(status_code=403, detail="The form expired. Reload and try again.")
        return household, data

    def render(
        request: Request,
        name: str,
        session: Session,
        *,
        active_page: str,
        status_code: int = 200,
        **context: Any,
    ) -> HTMLResponse:
        household, data = authenticated(request, session)
        values = {
            "request": request,
            "authenticated": True,
            "household": household,
            "csrf_token": data.csrf_token,
            "active_page": active_page,
            "flash": _notice(request),
            "status_code": status_code,
            **context,
        }
        return TEMPLATES.TemplateResponse(
            request=request,
            name=name,
            context=values,
            status_code=status_code,
        )

    @application.exception_handler(AuthenticationRequired)
    async def auth_redirect(request: Request, _exc: AuthenticationRequired) -> Response:
        next_path = request.url.path
        if request.url.query:
            next_path += f"?{request.url.query}"
        return RedirectResponse(
            f"/login?{urlencode({'next': next_path})}",
            status_code=303,
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        if request.url.path.startswith("/api/v1"):
            # /api/v1 speaks the documented envelope. Routes raise a fully
            # formed error dict; anything else (including FastAPI's own
            # validation failures) is wrapped in the same shape.
            detail = exc.detail
            error = (
                detail
                if isinstance(detail, dict) and "code" in detail
                else {
                    "code": "REQUEST_FAILED",
                    "message": str(detail),
                    "details": None,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "trace_id": "",
                }
            )
            return JSONResponse(
                {
                    "success": False,
                    "data": None,
                    "error": error,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "trace_id": error.get("trace_id", ""),
                },
                status_code=exc.status_code,
            )
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        if exc.status_code == 404:
            try:
                with request.app.state.database.session() as session:
                    return render(
                        request,
                        "error.html",
                        session,
                        active_page="",
                        status_code=404,
                        heading="That page is not in the ledger.",
                        message="It may have moved, or the receipt may no longer be available.",
                        action_label="Return home",
                        destination="/",
                    )
            except AuthenticationRequired:
                return RedirectResponse("/login", status_code=303)
        return HTMLResponse(
            f"<!doctype html><title>Grocery Home</title><h1>{exc.status_code}</h1>"
            f"<p>{str(exc.detail)}</p>",
            status_code=exc.status_code,
        )

    @application.get("/login", response_class=HTMLResponse)
    def login_page(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        try:
            authenticated(request, session)
        except AuthenticationRequired:
            pass
        else:
            return RedirectResponse(_safe_next(request.query_params.get("next")), status_code=303)
        token = generate_csrf_token()
        household = session.get(Household, 1)
        response = TEMPLATES.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "authenticated": False,
                "csrf_token": token,
                "error": (
                    None
                    if household is not None
                    else "Grocery Home needs its one-time setup on the host PC."
                ),
            },
        )
        response.set_cookie(
            LOGIN_CSRF_COOKIE,
            token,
            httponly=True,
            secure=active_settings.secure_cookies,
            samesite="lax",
            max_age=600,
            path="/login",
        )
        return response

    @application.post("/login")
    async def login(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        supplied_csrf = str(form.get("csrf_token") or "")
        expected_csrf = request.cookies.get(LOGIN_CSRF_COOKIE, "")
        if not verify_csrf_token(expected_csrf, supplied_csrf):
            raise HTTPException(status_code=403, detail="The login form expired. Reload it.")
        household = session.get(Household, 1)
        token = generate_csrf_token()
        error: str | None = None
        retry_after = 0
        if household is None:
            error = "Run the one-time setup command on the host PC first."
        else:
            client_key = request.client.host if request.client else "unknown"
            result = authenticate_shared_pin(
                session,
                household,
                str(form.get("pin") or ""),
                client_key,
                request.app.state.pin_throttle,
            )
            if result.authenticated:
                manager: SessionManager = request.app.state.session_manager
                issued = manager.issue(household.id, household.session_generation)
                response = RedirectResponse(
                    _safe_next(request.query_params.get("next")),
                    status_code=303,
                )
                manager.set_cookie(response, issued)
                response.delete_cookie(LOGIN_CSRF_COOKIE, path="/login")
                return response
            if result.rate_limited:
                retry_after = result.retry_after_seconds
                error = f"Too many attempts. Try again in {retry_after} seconds."
            else:
                error = "That PIN did not match."
        response = TEMPLATES.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "authenticated": False,
                "csrf_token": token,
                "error": error,
            },
            status_code=429 if retry_after else 401,
        )
        response.set_cookie(
            LOGIN_CSRF_COOKIE,
            token,
            httponly=True,
            secure=active_settings.secure_cookies,
            samesite="lax",
            max_age=600,
            path="/login",
        )
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    @application.post("/logout")
    async def logout(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        response = RedirectResponse("/login", status_code=303)
        request.app.state.session_manager.clear_cookie(response)
        return response

    @application.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        payload = _payload(session, create=True)
        overview_data = payload.get("overview", {})
        change = overview_data.get("month_change_percent")
        if change is None:
            delta = None
            direction = ""
        else:
            change_value = Decimal(str(change))
            direction = "down" if change_value < 0 else "up"
            delta = f"{abs(change_value):.0f}% {'less' if change_value < 0 else 'more'}"
        active_count = session.scalar(
            select(func.count(ShoppingItem.id)).where(
                ShoppingItem.status == ShoppingStatus.ACTIVE
            )
        ) or 0
        overview = {
            "month_spend": _money(
                int(overview_data.get("current_month_spend_cents") or 0)
            ),
            "month_delta": delta,
            "month_delta_direction": direction,
            "projected_30d": _money(
                int(overview_data.get("forecast_30d_cents") or 0)
            ),
            "receipt_count": int(overview_data.get("receipt_count") or 0),
            "active_list_count": active_count,
            "period_label": "confirmed grocery history",
            "category_period": "Confirmed groceries",
        }
        categories = list(payload.get("categories", []))[:5]
        max_spend = max((int(item.get("spend_cents") or 0) for item in categories), default=1)
        category_preview = [
            {
                "name": str(item.get("category") or "Uncategorised").title(),
                "amount": _money(int(item.get("spend_cents") or 0)),
                "percent": round(int(item.get("spend_cents") or 0) / max_spend * 100),
            }
            for item in categories
        ]
        receipts = session.scalars(
            select(Receipt)
            .where(
                Receipt.status == ProcessingStatus.COMPLETE,
                Receipt.duplicate_of_id.is_(None),
            )
            .options(selectinload(Receipt.items), selectinload(Receipt.upload_file))
            .order_by(Receipt.purchase_date.desc(), Receipt.created_at.desc())
            .limit(6)
        ).all()
        recent = [_receipt_view(receipt) for receipt in receipts]
        processing = session.scalars(
            select(UploadBatch).where(
                UploadBatch.status.in_(
                    [ProcessingStatus.QUEUED, ProcessingStatus.EXTRACTING]
                )
            )
        ).all()
        return render(
            request,
            "home.html",
            session,
            active_page="home",
            today_label=(
                f"{_today().strftime('%A')}, {_today().day} "
                f"{_today().strftime('%B')}"
            ),
            overview=overview,
            suggestions=_suggestions(session, payload, limit=5),
            category_preview=category_preview,
            recent_receipts=recent,
            processing_jobs=processing,
        )

    @application.get("/upload", response_class=HTMLResponse)
    def upload_page(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        return render(request, "upload.html", session, active_page="upload")

    @application.post("/upload")
    async def upload_receipt(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        files = [
            value
            for value in form.getlist("files")
            if isinstance(value, StarletteUploadFile)
        ]
        if not files:
            raise HTTPException(status_code=400, detail="Choose at least one receipt file.")
        stored = []
        try:
            stored = await asyncio.to_thread(
                validate_and_store_uploads,
                files,
                active_settings.receipt_dir,
            )
            batch = create_upload_batch(session, stored)
            enqueue_job(
                session,
                "receipt_extract",
                {"batch_id": batch.id},
                dedupe_key=f"receipt:{batch.id}",
            )
        except UploadValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            for entry in stored:
                entry.path.unlink(missing_ok=True)
            raise
        finally:
            for upload in files:
                await upload.close()
        return RedirectResponse(f"/jobs/{batch.id}", status_code=303)

    @application.get("/jobs/{batch_id}", response_class=HTMLResponse)
    def job_page(
        batch_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        job = _job_payload(session, batch_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Receipt job not found.")
        return render(
            request,
            "job_status.html",
            session,
            active_page="upload",
            job=job,
        )

    @application.get("/api/jobs/{batch_id}")
    def job_status(
        batch_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        job = _job_payload(session, batch_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Receipt job not found.")
        return JSONResponse(job)

    @application.get("/receipts", response_class=HTMLResponse)
    def receipts_page(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        query = request.query_params.get("q", "").strip().casefold()
        status_filter = request.query_params.get("status", "").strip()
        period_filter = request.query_params.get("period", "all").strip()
        cutoff: date | None = None
        if period_filter in {"30", "90", "365"}:
            cutoff = _today() - timedelta(days=int(period_filter))

        records = session.scalars(
            select(Receipt)
            .options(selectinload(Receipt.items), selectinload(Receipt.upload_file))
            .order_by(Receipt.purchase_date.desc(), Receipt.created_at.desc())
        ).all()
        rows: list[dict[str, Any]] = []
        for receipt in records:
            row = _receipt_view(receipt)
            if cutoff is not None and (
                receipt.purchase_date is None or receipt.purchase_date < cutoff
            ):
                continue
            if status_filter and row["status"] != status_filter:
                continue
            if query and query not in (
                f"{row['merchant']} {row['filename']}".casefold()
            ):
                continue
            rows.append(row)

        # A newly queued upload has no receipt row yet. Keep it visible in the
        # household archive instead of making the queue a hidden side channel.
        batches = session.scalars(
            select(UploadBatch)
            .where(
                UploadBatch.status.in_(
                    [ProcessingStatus.QUEUED, ProcessingStatus.EXTRACTING]
                )
            )
            .options(selectinload(UploadBatch.files))
            .order_by(UploadBatch.created_at.desc())
        ).all()
        for batch in batches:
            if not batch.files:
                continue
            filename = batch.files[0].original_filename
            status_value = _enum_value(batch.status)
            if status_filter and status_filter not in {status_value, "processing"}:
                continue
            if query and query not in f"reading receipt {filename}".casefold():
                continue
            label, tone = _status_presentation(batch.status)
            rows.insert(
                0,
                {
                    "id": batch.id,
                    "merchant": "Reading receipt",
                    "filename": filename,
                    "purchase_date": "",
                    "day": "…",
                    "month": "",
                    "item_count": None,
                    "status": status_value,
                    "status_label": label,
                    "status_tone": tone,
                    "total": "—",
                    "destination": f"/jobs/{batch.id}",
                },
            )
        result_total = sum(
            receipt.total_cents or 0
            for receipt in records
            if receipt.status == ProcessingStatus.COMPLETE
            and receipt.is_grocery
            and receipt.duplicate_of_id is None
            and (cutoff is None or (receipt.purchase_date and receipt.purchase_date >= cutoff))
        )
        return render(
            request,
            "receipts.html",
            session,
            active_page="receipts",
            receipts=rows,
            result_count=len(rows),
            result_total=_money(result_total),
            filters={
                "q": request.query_params.get("q", ""),
                "status": status_filter,
                "period": period_filter,
            },
            status_options=[
                ("queued", "Queued"),
                ("extracting", "Reading"),
                ("needs_review", "Needs review"),
                ("complete", "Confirmed"),
                ("duplicate", "Duplicate"),
                ("failed", "Needs help"),
            ],
        )

    @application.get("/receipts/{receipt_id}", response_class=HTMLResponse)
    def receipt_detail(
        receipt_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        receipt = session.scalar(
            select(Receipt)
            .where(Receipt.id == receipt_id)
            .options(selectinload(Receipt.items), selectinload(Receipt.upload_file))
        )
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found.")
        if receipt.status in {ProcessingStatus.NEEDS_REVIEW, ProcessingStatus.FAILED}:
            return RedirectResponse(f"/receipts/{receipt.id}/review", status_code=303)
        view = _receipt_view(receipt)
        items = receipt.items
        if receipt.duplicate_of_id and not items:
            canonical = session.scalar(
                select(Receipt)
                .where(Receipt.id == receipt.duplicate_of_id)
                .options(selectinload(Receipt.items))
            )
            if canonical is not None:
                items = canonical.items
        view["items"] = [
            {
                "description": item.description,
                "quantity_label": _quantity_label(item.quantity, item.quantity_unit),
                "category": item.category.title(),
                "line_total": _money(item.line_total_cents),
            }
            for item in items
        ]
        return render(
            request,
            "receipt_detail.html",
            session,
            active_page="receipts",
            receipt=view,
        )

    @application.get("/receipts/{receipt_id}/review", response_class=HTMLResponse)
    def receipt_review(
        receipt_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        receipt = session.scalar(
            select(Receipt)
            .where(Receipt.id == receipt_id)
            .options(selectinload(Receipt.items), selectinload(Receipt.upload_file))
        )
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found.")
        return render(
            request,
            "receipt_review.html",
            session,
            active_page="receipts",
            receipt=_receipt_review_view(receipt),
            categories=services.available_categories(),
        )

    @application.post("/receipts/{receipt_id}/review")
    async def confirm_receipt(
        receipt_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        receipt = session.scalar(
            select(Receipt)
            .where(Receipt.id == receipt_id)
            .options(
                selectinload(Receipt.items),
                selectinload(Receipt.upload_file).selectinload(UploadFile.batch),
            )
        )
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found.")

        descriptions = [str(value).strip() for value in form.getlist("item_description")]
        quantities = list(form.getlist("item_quantity"))
        units = [str(value).strip() or "each" for value in form.getlist("item_unit")]
        totals = list(form.getlist("item_total"))
        categories = [str(value).strip() for value in form.getlist("item_category")]
        product_numbers = [
            str(value).strip() or None for value in form.getlist("item_product_number")
        ]
        if {
            len(quantities),
            len(units),
            len(totals),
            len(categories),
            len(product_numbers),
        } != {len(descriptions)}:
            raise HTTPException(status_code=422, detail="Receipt item fields are incomplete.")

        try:
            draft = services.ReceiptDraft(
                merchant_name=str(form.get("merchant_name") or ""),
                total_cents=services.parse_money(
                    form.get("total"), required=True, field_name="total"
                )
                or 0,
                purchase_date=services.parse_date(form.get("purchase_date")),
                purchase_time=services.parse_time(form.get("purchase_time")),
                subtotal_cents=services.parse_money(
                    form.get("subtotal"), field_name="subtotal"
                ),
                gst_cents=services.parse_money(form.get("gst"), field_name="gst"),
                savings_cents=services.parse_money(
                    form.get("savings"), field_name="savings"
                ),
                is_grocery=form.get("is_grocery") == "true",
                items=services.build_line_drafts(
                    {
                        "description": descriptions[index],
                        "quantity": quantities[index],
                        "unit": units[index],
                        "line_total": totals[index],
                        "category": categories[index],
                        "product_number": product_numbers[index],
                    }
                    for index in range(len(descriptions))
                ),
            )
            services.confirm_receipt(session, receipt, draft)
        except services.ServiceError as exc:
            raise _service_http_error(exc) from exc

        return RedirectResponse(
            _with_notice(f"/receipts/{receipt.id}", "receipt-confirmed"),
            status_code=303,
        )

    @application.get("/receipts/{receipt_id}/preview")
    def receipt_preview(
        receipt_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        receipt = session.scalar(
            select(Receipt)
            .where(Receipt.id == receipt_id)
            .options(selectinload(Receipt.upload_file))
        )
        if receipt is None or receipt.upload_file is None:
            raise HTTPException(status_code=404, detail="Receipt file not found.")
        root = active_settings.receipt_dir.resolve()
        path = (root / receipt.upload_file.storage_key).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(status_code=404, detail="Receipt file not found.")
        safe_name = receipt.upload_file.original_filename.replace('"', "")
        return FileResponse(
            path,
            media_type=receipt.upload_file.media_type,
            headers={
                "Content-Disposition": f'inline; filename="{safe_name}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    shopping_item_view = services.shopping_item_view

    @application.get("/shopping", response_class=HTMLResponse)
    def shopping_page(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        payload = _payload(session, create=True)
        return render(
            request,
            "shopping.html",
            session,
            active_page="shopping",
            active_items=[
                shopping_item_view(item)
                for item in services.active_shopping_items(session)
            ],
            completed_items=[
                shopping_item_view(item)
                for item in services.completed_shopping_items(session)
            ],
            suggestions=_suggestions(session, payload),
        )

    @application.post("/shopping")
    async def add_shopping_item(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        try:
            services.add_shopping_item(
                session,
                description=str(form.get("description") or ""),
                quantity=form.get("quantity"),
                unit=str(form.get("unit") or "each"),
                note=str(form.get("note") or ""),
            )
        except services.ServiceError as exc:
            raise _service_http_error(exc) from exc
        return RedirectResponse(
            _with_notice("/shopping", "list-added"),
            status_code=303,
        )

    @application.post("/shopping/{item_id}")
    async def edit_shopping_item(
        item_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        try:
            services.update_shopping_item(
                session,
                item_id,
                description=(
                    str(form["description"]) if "description" in form else None
                ),
                quantity=form.get("quantity") or None,
                unit=str(form["unit"]) if "unit" in form else None,
                note=str(form.get("note") or ""),
            )
        except services.ServiceError as exc:
            raise _service_http_error(exc) from exc
        return RedirectResponse(
            _with_notice("/shopping", "list-updated"),
            status_code=303,
        )

    @application.post("/shopping/{item_id}/toggle")
    async def toggle_shopping_item(
        item_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        try:
            services.toggle_shopping_item(session, item_id)
        except services.ServiceError as exc:
            raise _service_http_error(exc) from exc
        return RedirectResponse("/shopping", status_code=303)

    @application.post("/shopping/{item_id}/delete")
    async def remove_shopping_item(
        item_id: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        try:
            services.remove_shopping_item(session, item_id)
        except services.ServiceError as exc:
            raise _service_http_error(exc) from exc
        return RedirectResponse("/shopping", status_code=303)

    @application.post("/shopping/suggestions/{key:path}/add")
    async def add_suggestion(
        key: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        try:
            services.accept_suggestion(session, key)
        except services.ServiceError as exc:
            raise _service_http_error(exc) from exc
        return RedirectResponse(
            _with_notice("/shopping", "list-added"),
            status_code=303,
        )

    @application.post("/shopping/suggestions/{key:path}/dismiss")
    async def dismiss_suggestion(
        key: str,
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        try:
            services.dismiss_suggestion(session, key)
        except services.ServiceError as exc:
            raise _service_http_error(exc) from exc
        return RedirectResponse(
            _with_notice("/shopping", "suggestion-dismissed"),
            status_code=303,
        )

    @application.get("/trends", response_class=HTMLResponse)
    def trends_page(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        selected_range = request.query_params.get("range", "12m")
        range_days = {"90d": 90, "6m": 183, "12m": 365, "all": None}
        if selected_range not in range_days:
            selected_range = "12m"
        days = range_days[selected_range]
        cutoff = _today() - timedelta(days=days) if days else None
        receipts = session.scalars(
            select(Receipt)
            .where(
                Receipt.status == ProcessingStatus.COMPLETE,
                Receipt.is_grocery.is_(True),
                Receipt.duplicate_of_id.is_(None),
            )
            .options(selectinload(Receipt.items))
            .order_by(Receipt.purchase_date)
        ).all()
        selected = [
            receipt
            for receipt in receipts
            if receipt.purchase_date is not None
            and (cutoff is None or receipt.purchase_date >= cutoff)
        ]
        total_spend = sum(receipt.total_cents or 0 for receipt in selected)
        trip_count = len(selected)
        item_count = sum(len(receipt.items) for receipt in selected)
        savings = sum(receipt.savings_cents or 0 for receipt in selected)
        period_label = {
            "90d": "Last 90 days",
            "6m": "Last 6 months",
            "12m": "Last 12 months",
            "all": "All-time",
        }[selected_range]

        previous_total: int | None = None
        if days:
            previous_start = cutoff - timedelta(days=days)
            previous_total = sum(
                receipt.total_cents or 0
                for receipt in receipts
                if receipt.purchase_date is not None
                and previous_start <= receipt.purchase_date < cutoff
            )
        if previous_total in (None, 0):
            change_label = "No comparable earlier period"
            change_direction = ""
        else:
            percent = Decimal(total_spend - previous_total) / Decimal(previous_total) * 100
            change_direction = "down" if percent < 0 else "up"
            change_label = (
                f"{abs(percent):.0f}% {'less' if percent < 0 else 'more'} "
                "than the previous period"
            )
        trends = {
            "period_label": period_label,
            "total_spend": _money(total_spend),
            "average_trip": _money(round(total_spend / trip_count) if trip_count else 0),
            "trip_count": trip_count,
            "item_count": item_count,
            "savings": _money(savings),
            "change_label": change_label,
            "change_direction": change_direction,
        }

        payload = _payload(session, create=True)
        bucket_key = "weekly" if selected_range == "90d" else "monthly"
        points: list[dict[str, Any]] = []
        for raw in payload.get(bucket_key, []):
            try:
                bucket_date = date.fromisoformat(str(raw["period_start"]))
            except (KeyError, TypeError, ValueError):
                continue
            if cutoff and bucket_date < cutoff:
                continue
            amount_cents = int(raw.get("spend_cents") or 0)
            points.append(
                {
                    "date": bucket_date.isoformat(),
                    "label": (
                        f"Week of {bucket_date.day} {bucket_date.strftime('%b')}"
                        if bucket_key == "weekly"
                        else bucket_date.strftime("%B %Y")
                    ),
                    "amount": amount_cents / 100,
                    "amount_label": _money(amount_cents),
                    "trips": int(raw.get("trips") or 0),
                }
            )

        category_totals: dict[str, int] = {}
        for receipt in selected:
            for item in receipt.items:
                category_totals[item.category] = (
                    category_totals.get(item.category, 0) + (item.line_total_cents or 0)
                )
        category_points = [
            {
                "name": name.title(),
                "amount": cents / 100,
                "amount_label": _money(cents),
            }
            for name, cents in sorted(
                category_totals.items(), key=lambda pair: pair[1], reverse=True
            )
            if cents > 0
        ][:8]
        recurring = [
            {
                "description": str(product.get("description") or "Household item"),
                "purchase_label": (
                    f"{int(product.get('purchase_dates') or 0)} purchase dates"
                ),
                "cadence_label": (
                    f"about every {product['typical_interval_days']} days"
                    if product.get("typical_interval_days")
                    else "building a rhythm"
                ),
                "typical_price": _money(
                    int(product.get("expected_purchase_cost_cents") or 0)
                ),
            }
            for product in payload.get("products", [])
            if int(product.get("purchase_dates") or 0) >= 2
        ][:12]

        latest_quotes: dict[str, PriceQuote] = {}
        quote_rows = session.scalars(
            select(PriceQuote).order_by(PriceQuote.fetched_at.desc())
        ).all()
        for row in quote_rows:
            latest_quotes.setdefault(row.product_key, row)
        now = utc_now()
        price_quotes = []
        for row in list(latest_quotes.values())[:10]:
            raw = row.raw_payload or {}
            price_quotes.append(
                {
                    "description": row.description,
                    "price": _money(row.price_cents),
                    "url": raw.get("url") or "#",
                    "fetched_label": (
                        f"{row.fetched_at.astimezone().day} "
                        f"{row.fetched_at.astimezone().strftime('%b')}"
                    ),
                    "is_stale": bool(row.valid_until and row.valid_until < now),
                    "delta_direction": "",
                    "delta_label": "",
                }
            )
        association_data = payload.get("association_rules", {})
        association_status = association_data.get("status", {})
        associations = []
        for raw in association_data.get("insights", [])[:5]:
            labels = [str(value) for value in raw.get("antecedent_labels", [])]
            left = labels[0] if labels else "Related basket"
            if len(labels) > 1:
                left += f" + {len(labels) - 1} other{'s' if len(labels) > 2 else ''}"
            associations.append(
                {
                    "left": left,
                    "right": str(raw.get("consequent_label") or ""),
                    "confidence_label": (
                        f"{Decimal(str(raw.get('confidence') or 0)) * 100:.0f}%"
                    ),
                }
            )
        advanced_available = association_status.get("status") == "ready"
        advanced = {
            "available": advanced_available,
            "status_tone": "success" if advanced_available else "muted",
            "status_label": "Ready" if advanced_available else "Building history",
            "message": association_status.get(
                "message", "Add more confirmed shops to unlock this pattern."
            ),
        }
        return render(
            request,
            "trends.html",
            session,
            active_page="trends",
            range_options=[
                ("90d", "Last 90 days"),
                ("6m", "Last 6 months"),
                ("12m", "Last 12 months"),
                ("all", "All time"),
            ],
            selected_range=selected_range,
            trends=trends,
            spend_points=points,
            spend_points_json=json.dumps(points, separators=(",", ":")),
            category_points=category_points,
            category_points_json=json.dumps(category_points, separators=(",", ":")),
            recurring_products=recurring,
            price_quotes=price_quotes,
            advanced=advanced,
            associations=associations,
        )

    def settings_view(session: Session, household: Household) -> dict[str, Any]:
        latest_quote = session.scalar(
            select(PriceQuote).order_by(PriceQuote.fetched_at.desc()).limit(1)
        )
        latest_job = session.scalar(
            select(BackgroundJob)
            .where(BackgroundJob.kind == "price_refresh")
            .order_by(BackgroundJob.created_at.desc())
            .limit(1)
        )
        upload_count = session.scalar(select(func.count(UploadFile.id))) or 0
        database_size = (
            active_settings.database_path.stat().st_size
            if active_settings.database_path.is_file()
            else 0
        )
        if database_size < 1024 * 1024:
            database_size_label = f"{max(1, round(database_size / 1024))} KB"
        else:
            database_size_label = f"{database_size / (1024 * 1024):.1f} MB"
        result_label = "Not run yet"
        if latest_job is not None:
            result_label = {
                JobStatus.QUEUED: "Queued",
                JobStatus.RUNNING: "Running",
                JobStatus.COMPLETE: "Completed",
                JobStatus.FAILED: "Unavailable; last prices retained",
            }[latest_job.status]
        return {
            "household_name": household.display_name,
            "data_dir": str(active_settings.data_dir),
            "upload_count": upload_count,
            "database_size": database_size_label,
            "price_last_run": (
                f"{latest_quote.fetched_at.astimezone().day} "
                f"{latest_quote.fetched_at.astimezone().strftime('%b %Y, %H:%M')}"
                if latest_quote
                else "Not run yet"
            ),
            "price_next_run": (
                f"{latest_quote.valid_until.astimezone().day} "
                f"{latest_quote.valid_until.astimezone().strftime('%b %Y, %H:%M')}"
                if latest_quote and latest_quote.valid_until
                else "When active products are available"
            ),
            "price_last_result": result_label,
        }

    @application.get("/settings", response_class=HTMLResponse)
    def settings_page(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        household, _ = authenticated(request, session)
        return render(
            request,
            "settings.html",
            session,
            active_page="settings",
            settings=settings_view(session, household),
        )

    @application.post("/settings/household")
    async def save_household(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        household, _ = require_csrf(request, session, form.get("csrf_token"))
        name = str(form.get("household_name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Household name is required.")
        household.display_name = name[:100]
        return RedirectResponse(
            _with_notice("/settings", "household-saved"),
            status_code=303,
        )

    @application.post("/settings/pin")
    async def change_pin(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        household, _ = require_csrf(request, session, form.get("csrf_token"))
        if not verify_pin(household.pin_hash, str(form.get("current_pin") or "")):
            raise HTTPException(status_code=422, detail="Current PIN did not match.")
        try:
            household = configure_household(
                session,
                str(form.get("new_pin") or ""),
                display_name=household.display_name,
                timezone=household.timezone,
                currency=household.currency,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        issued = request.app.state.session_manager.issue(
            household.id, household.session_generation
        )
        response = RedirectResponse(
            _with_notice("/settings", "pin-changed"),
            status_code=303,
        )
        request.app.state.session_manager.set_cookie(response, issued)
        return response

    @application.post("/settings/prices/refresh")
    async def queue_price_refresh(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        enqueue_job(
            session,
            "price_refresh",
            {"force": True},
            dedupe_key=f"manual-prices:{utc_now().strftime('%Y%m%d%H%M')}",
        )
        destination = (
            "/trends"
            if request.headers.get("referer", "").endswith("/trends")
            else "/settings"
        )
        return RedirectResponse(
            _with_notice(destination, "prices-queued"),
            status_code=303,
        )

    @application.get("/settings/export.csv")
    def export_csv(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        authenticated(request, session)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "receipt_id",
                "purchase_date",
                "merchant",
                "receipt_status",
                "is_grocery",
                "receipt_total",
                "item_description",
                "quantity",
                "unit",
                "category",
                "line_total",
            ]
        )
        receipts = session.scalars(
            select(Receipt)
            .options(selectinload(Receipt.items))
            .order_by(Receipt.purchase_date, Receipt.id)
        ).all()
        for receipt in receipts:
            items: list[ReceiptItem | None] = list(receipt.items) or [None]
            for item in items:
                writer.writerow(
                    [
                        receipt.id,
                        receipt.purchase_date.isoformat() if receipt.purchase_date else "",
                        receipt.merchant_name or "",
                        _enum_value(receipt.status),
                        str(receipt.is_grocery).lower(),
                        _money_input(receipt.total_cents),
                        item.description if item else "",
                        format(item.quantity.normalize(), "f") if item else "",
                        item.quantity_unit if item else "",
                        item.category if item else "",
                        _money_input(item.line_total_cents) if item else "",
                    ]
                )
        filename = f"grocery-home-{_today().isoformat()}.csv"
        return StreamingResponse(
            iter([output.getvalue().encode("utf-8-sig")]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
            },
        )

    @application.post("/settings/backup")
    async def create_backup(
        request: Request,
        session: Session = Depends(database_session),
    ) -> Response:
        form = await request.form()
        require_csrf(request, session, form.get("csrf_token"))
        # Commit the request transaction before the SQLite online-backup API
        # opens its separate read connection.
        session.flush()
        backups = active_settings.data_dir / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().strftime("%Y%m%d-%H%M%S")
        archive_path = backups / f"grocery-home-{stamp}.zip"
        database_copy = active_settings.temporary_dir / f"backup-{stamp}.sqlite3"
        try:
            with sqlite3.connect(active_settings.database_path) as source:
                with sqlite3.connect(database_copy) as destination:
                    source.backup(destination)
            with zipfile.ZipFile(
                archive_path,
                mode="x",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.write(database_copy, "grocery_home.sqlite3")
                for path in active_settings.receipt_dir.iterdir():
                    if path.is_file():
                        archive.write(path, f"receipts/{path.name}")
        finally:
            database_copy.unlink(missing_ok=True)
        return RedirectResponse(
            _with_notice("/settings", "backup-created"),
            status_code=303,
        )

    # Register /api/v1 routes. The router opens its own session per request via
    # its own dependency, so adding this app's session dependency here would
    # only open a second, unused transaction on every API call.
    application.include_router(api_v1.router)

    return application


app = create_app()
