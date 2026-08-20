from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from grocery_home.analytics import _household_today
from grocery_home.app import create_app
from grocery_home.config import Settings, sqlite_url
from grocery_home.database import Database, create_database
from grocery_home.models import (
    AnalyticsSnapshot,
    BackgroundJob,
    Household,
    ProcessingStatus,
    Receipt,
    ReceiptItem,
    ReceiptSource,
    ShoppingItem,
    ShoppingStatus,
    UploadBatch,
    UploadFile,
)
from grocery_home.security import configure_household


HOUSEHOLD_PIN = "4826"


def _current_month_purchase_date() -> date:
    """Return a purchase date inside the snapshot's current month.

    ``AnalyticsSnapshot.total_spend_cents`` reports current-month spend against
    the household's own clock, so a hard-coded calendar date stops exercising
    that assertion as soon as the month rolls over.  Deriving the date from the
    same clock the snapshot uses keeps the test meaningful on any run date.
    """

    return _household_today().replace(day=1)


CSRF_PATTERN = re.compile(
    r'name="csrf_token"\s+value="([^"]+)"',
    flags=re.IGNORECASE,
)
CSRF_META_PATTERN = re.compile(
    r'name="csrf-token"\s+content="([^"]+)"',
    flags=re.IGNORECASE,
)


@pytest.fixture
def web_app(
    tmp_path: Path,
) -> tuple[TestClient, Database, Settings]:
    runtime = tmp_path / "runtime"
    settings = Settings(
        data_dir=runtime,
        database_url=sqlite_url(runtime / "grocery-home-test.sqlite3"),
        session_secret="integration-test-session-secret-that-is-long-enough",
        pin_max_failures=3,
        pin_window_seconds=60,
        pin_lock_seconds=60,
    )
    database = create_database(settings)
    application = create_app(
        settings,
        database=database,
        start_worker=False,
    )

    with TestClient(application) as client:
        yield client, database, settings

    database.dispose()


def _csrf(response) -> str:
    match = CSRF_PATTERN.search(response.text) or CSRF_META_PATTERN.search(response.text)
    assert match is not None, "response did not include a CSRF form field"
    return match.group(1)


def _configure(database: Database) -> Household:
    with database.session() as session:
        household = configure_household(
            session,
            HOUSEHOLD_PIN,
            display_name="The Test Kitchen",
        )
        household_id = household.id
    with database.session() as session:
        configured = session.get(Household, household_id)
        assert configured is not None
        return configured


def _login(client: TestClient, database: Database) -> str:
    _configure(database)
    login_page = client.get("/login")
    assert login_page.status_code == 200
    login_csrf = _csrf(login_page)

    response = client.post(
        "/login",
        data={"csrf_token": login_csrf, "pin": HOUSEHOLD_PIN},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert client.cookies.get("grocery_home_session")

    home = client.get("/")
    assert home.status_code == 200
    return _csrf(home)


def _create_review_receipt(
    database: Database,
    settings: Settings,
) -> str:
    settings.ensure_directories()
    storage_key = "private-test-receipt.png"
    (settings.receipt_dir / storage_key).write_bytes(
        b"\x89PNG\r\n\x1a\nprivate receipt fixture"
    )
    with database.session() as session:
        batch = UploadBatch(
            status=ProcessingStatus.NEEDS_REVIEW,
            total_files=1,
            processed_files=1,
        )
        session.add(batch)
        session.flush()
        upload = UploadFile(
            batch_id=batch.id,
            ordinal=1,
            original_filename="family-shop.png",
            storage_key=storage_key,
            media_type="image/png",
            file_size=(settings.receipt_dir / storage_key).stat().st_size,
            content_sha256="a" * 64,
            status=ProcessingStatus.NEEDS_REVIEW,
        )
        session.add(upload)
        session.flush()
        receipt = Receipt(
            upload_file_id=upload.id,
            merchant_name=None,
            purchase_date=None,
            total_cents=None,
            is_grocery=True,
            status=ProcessingStatus.NEEDS_REVIEW,
            source_kind=ReceiptSource.IMAGE,
        )
        receipt.items.append(
            ReceiptItem(
                line_number=1,
                description="M1lk?",
                quantity=Decimal("1"),
                quantity_unit="each",
                line_total_cents=600,
                category="unmapped",
                needs_review=True,
            )
        )
        session.add(receipt)
        session.flush()
        return receipt.id


def test_household_setup_login_and_csrf_protection(
    web_app: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = web_app

    not_configured = client.get("/login")
    assert not_configured.status_code == 200
    assert "one-time setup" in not_configured.text

    _configure(database)
    login_page = client.get("/login")
    assert login_page.status_code == 200
    login_csrf = _csrf(login_page)

    rejected = client.post(
        "/login",
        data={"csrf_token": "tampered", "pin": HOUSEHOLD_PIN},
        follow_redirects=False,
    )
    assert rejected.status_code == 403

    accepted = client.post(
        "/login?next=%2Fshopping",
        data={"csrf_token": login_csrf, "pin": HOUSEHOLD_PIN},
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/shopping"
    cookie = accepted.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie

    protected = client.post(
        "/shopping",
        data={
            "csrf_token": "not-the-session-token",
            "description": "Milk",
            "quantity": "1",
        },
        follow_redirects=False,
    )
    assert protected.status_code == 403
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ShoppingItem)) == 0


def test_private_receipt_preview_requires_authentication(
    web_app: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = web_app
    receipt_id = _create_review_receipt(database, settings)

    response = client.get(
        f"/receipts/{receipt_id}/preview",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")
    assert "preview" in response.headers["location"]


def test_authenticated_mobile_routes_render_shared_navigation(
    web_app: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = web_app
    _login(client, database)

    for path in ("/", "/shopping", "/upload", "/trends", "/receipts", "/settings"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert 'name="viewport"' in response.text
        assert "viewport-fit=cover" in response.text
        assert 'class="bottom-nav"' in response.text
        for destination in ("/", "/shopping", "/upload", "/trends", "/receipts"):
            assert f'href="{destination}"' in response.text


def test_api_pin_auth_issues_and_validates_signed_session(
    web_app: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = web_app
    _configure(database)

    auth_response = client.post(
        "/api/v1/auth/pin",
        json={"pin": HOUSEHOLD_PIN},
    )
    assert auth_response.status_code == 200, auth_response.text
    payload = auth_response.json()
    assert payload["success"] is True
    token = payload["data"]["session_token"]
    assert token
    assert payload["data"]["token_type"] == "Bearer"
    assert payload["data"]["expires_in"] == settings.session_max_age_seconds

    ok = client.get(
        "/api/v1/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["success"] is True

    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    rejected = client.get(
        "/api/v1/bootstrap",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert rejected.status_code == 401


def test_shopping_item_can_be_added_and_toggled(
    web_app: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = web_app
    csrf_token = _login(client, database)

    added = client.post(
        "/shopping",
        data={
            "csrf_token": csrf_token,
            "description": "Oat milk",
            "quantity": "2",
            "unit": "cartons",
            "note": "Barista",
        },
        follow_redirects=False,
    )
    assert added.status_code == 303
    assert added.headers["location"].startswith("/shopping?notice=")

    with database.session() as session:
        item = session.scalar(select(ShoppingItem))
        assert item is not None
        assert item.description == "Oat milk"
        assert item.quantity == Decimal("2.000")
        assert item.status == ShoppingStatus.ACTIVE
        item_id = item.id

    shopping_page = client.get("/shopping")
    assert shopping_page.status_code == 200
    assert "Oat milk" in shopping_page.text
    page_csrf = _csrf(shopping_page)
    toggled = client.post(
        f"/shopping/{item_id}/toggle",
        data={"csrf_token": page_csrf},
        follow_redirects=False,
    )
    assert toggled.status_code == 303
    assert toggled.headers["location"] == "/shopping"

    with database.session() as session:
        item = session.get(ShoppingItem, item_id)
        assert item is not None
        assert item.status == ShoppingStatus.COMPLETED
        assert item.completed_at is not None
        assert item.version == 2


def test_upload_rejects_spoofed_image_before_creating_records(
    web_app: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = web_app
    _login(client, database)
    upload_page = client.get("/upload")
    csrf_token = _csrf(upload_page)

    response = client.post(
        "/upload",
        data={"csrf_token": csrf_token},
        files={
            "files": (
                "../../family-receipt.jpg",
                b"<html>this is not an image</html>",
                "image/jpeg",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "not a supported" in response.text
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(UploadBatch)) == 0
        assert session.scalar(select(func.count()).select_from(UploadFile)) == 0
    assert list(settings.receipt_dir.iterdir()) == []


def test_receipt_review_confirmation_updates_atomic_snapshot(
    web_app: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = web_app
    _login(client, database)
    receipt_id = _create_review_receipt(database, settings)

    review = client.get(f"/receipts/{receipt_id}/review")
    assert review.status_code == 200
    assert "Review receipt" in review.text
    assert "M1lk?" in review.text
    csrf_token = _csrf(review)

    confirmed = client.post(
        f"/receipts/{receipt_id}/review",
        data={
            "csrf_token": csrf_token,
            "merchant_name": "Coles",
            "purchase_date": _current_month_purchase_date().isoformat(),
            "purchase_time": "18:30",
            "subtotal": "6.50",
            "total": "6.50",
            "gst": "0.00",
            "savings": "1.00",
            "is_grocery": "true",
            "item_description": ["Oat milk"],
            "item_quantity": ["2"],
            "item_unit": ["each"],
            "item_total": ["6.50"],
            "item_category": ["Dairy"],
            "item_product_number": [""],
        },
        follow_redirects=False,
    )
    assert confirmed.status_code == 303
    assert confirmed.headers["location"].startswith(f"/receipts/{receipt_id}?notice=")

    with database.session() as session:
        receipt = session.scalar(
            select(Receipt).where(Receipt.id == receipt_id)
        )
        assert receipt is not None
        assert receipt.status == ProcessingStatus.COMPLETE
        assert receipt.merchant_name == "Coles"
        assert receipt.total_cents == 650
        assert receipt.is_grocery is True
        assert receipt.confirmed_at is not None
        item = session.scalar(
            select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id)
        )
        assert item is not None
        assert item.description == "Oat milk"
        assert item.quantity == Decimal("2.000")
        assert item.line_total_cents == 650
        assert item.unit_price_cents == 325
        snapshot = session.scalar(
            select(AnalyticsSnapshot).where(AnalyticsSnapshot.is_current.is_(True))
        )
        assert snapshot is not None
        assert snapshot.receipt_count == 1
        assert snapshot.total_spend_cents == 650
        queued = session.scalar(
            select(BackgroundJob).where(
                BackgroundJob.kind == "advanced_analytics"
            )
        )
        assert queued is not None

    detail = client.get(f"/receipts/{receipt_id}")
    assert detail.status_code == 200
    assert "Oat milk" in detail.text
    assert "$6.50" in detail.text
    assert f'href="/receipts/{receipt_id}/review">Edit receipt' in detail.text

    edit = client.get(f"/receipts/{receipt_id}/review")
    assert edit.status_code == 200
    removed = client.post(
        f"/receipts/{receipt_id}/review",
        data={
            "csrf_token": _csrf(edit),
            "merchant_name": "Coles",
            "purchase_date": _current_month_purchase_date().isoformat(),
            "purchase_time": "18:30",
            "subtotal": "0.00",
            "total": "0.00",
            "gst": "0.00",
            "savings": "0.00",
            "is_grocery": "true",
        },
        follow_redirects=False,
    )
    assert removed.status_code == 303
    with database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(ReceiptItem).where(
                ReceiptItem.receipt_id == receipt_id
            )
        ) == 0
