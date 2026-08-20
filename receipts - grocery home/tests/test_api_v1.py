"""Contract tests for the /api/v1 JSON layer used by the Flutter client.

These cover the parts a mobile client depends on and cannot discover for
itself: the response envelope, bearer-token authentication and revocation, the
capture-to-ledger flow, the shared shopping list's concurrency rules, and the
filing gate that keeps undated receipts out of dated analytics.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from grocery_home import services
from grocery_home.analytics import _household_today
from grocery_home.app import create_app
from grocery_home.config import Settings, sqlite_url
from grocery_home.database import Database, create_database
from grocery_home.models import (
    AnalyticsSnapshot,
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
from grocery_home.security import configure_household, hash_pin


HOUSEHOLD_PIN = "4826"


@pytest.fixture
def api(tmp_path: Path) -> tuple[TestClient, Database, Settings]:
    runtime = tmp_path / "runtime"
    settings = Settings(
        data_dir=runtime,
        database_url=sqlite_url(runtime / "grocery-home-api-test.sqlite3"),
        session_secret="api-contract-test-session-secret-long-enough",
        pin_max_failures=3,
        pin_window_seconds=60,
        pin_lock_seconds=60,
    )
    database = create_database(settings)
    application = create_app(settings, database=database, start_worker=False)
    with TestClient(application) as client:
        yield client, database, settings
    database.dispose()


def _configure(database: Database) -> None:
    with database.session() as session:
        configure_household(session, HOUSEHOLD_PIN, display_name="The Test Kitchen")


def _token(client: TestClient, database: Database) -> str:
    _configure(database)
    response = client.post("/api/v1/auth/pin", json={"pin": HOUSEHOLD_PIN})
    assert response.status_code == 200, response.text
    return response.json()["data"]["session_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _png_bytes(size: tuple[int, int] = (200, 320)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (240, 240, 240)).save(buffer, format="PNG")
    return buffer.getvalue()


def _seed_review_receipt(database: Database, settings: Settings) -> str:
    """Create a receipt waiting for review, backed by a real stored image."""

    settings.ensure_directories()
    storage_key = "api-test-receipt.png"
    (settings.receipt_dir / storage_key).write_bytes(_png_bytes())
    with database.session() as session:
        batch = UploadBatch(
            status=ProcessingStatus.NEEDS_REVIEW, total_files=1, processed_files=1
        )
        session.add(batch)
        session.flush()
        upload = UploadFile(
            batch_id=batch.id,
            ordinal=1,
            original_filename="shop.png",
            storage_key=storage_key,
            media_type="image/png",
            file_size=(settings.receipt_dir / storage_key).stat().st_size,
            content_sha256="b" * 64,
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
                description="0at m1lk",
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


# ---------------------------------------------------------------------------
# Health and envelope
# ---------------------------------------------------------------------------


def test_health_is_public_and_reports_ok(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, _database, _settings = api
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_successful_response_uses_the_documented_envelope(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)

    body = client.get("/api/v1/bootstrap", headers=_auth(token)).json()

    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["household"]["name"] == "The Test Kitchen"
    assert body["timestamp"] and body["trace_id"]


def test_failure_response_uses_the_documented_error_envelope(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)

    response = client.get("/api/v1/receipts/does-not-exist", headers=_auth(token))

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "RECEIPT_NOT_FOUND"
    assert body["error"]["trace_id"]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_pin_auth_returns_a_token_with_the_configured_lifetime(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api
    _configure(database)

    response = client.post("/api/v1/auth/pin", json={"pin": HOUSEHOLD_PIN})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == settings.session_max_age_seconds
    assert data["household"]["name"] == "The Test Kitchen"


def test_requests_without_a_bearer_header_are_rejected(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    _configure(database)

    response = client.get("/api/v1/bootstrap")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_TOKEN"


def test_a_session_cookie_alone_cannot_authenticate_the_json_api(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """The API must ignore cookies, which is what makes it CSRF-immune."""

    client, database, _settings = api
    _configure(database)
    login = client.get("/login")
    csrf = login.text.split('name="csrf_token" value="')[1].split('"')[0]
    client.post(
        "/login",
        data={"csrf_token": csrf, "pin": HOUSEHOLD_PIN},
        follow_redirects=False,
    )
    assert client.cookies.get("grocery_home_session")

    response = client.get("/api/v1/bootstrap")

    assert response.status_code == 401


def test_a_tampered_token_is_rejected(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    response = client.get("/api/v1/bootstrap", headers=_auth(tampered))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_wrong_pin_is_rejected_then_throttled(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    _configure(database)

    first = client.post("/api/v1/auth/pin", json={"pin": "0000"})
    assert first.status_code == 401
    assert first.json()["error"]["code"] == "INVALID_PIN"

    statuses = {
        client.post("/api/v1/auth/pin", json={"pin": "0000"}).status_code
        for _ in range(5)
    }
    assert 429 in statuses

    throttled = client.post("/api/v1/auth/pin", json={"pin": "0000"})
    assert throttled.status_code == 429
    body = throttled.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["details"]["retry_after_seconds"] > 0


def test_rotating_the_pin_revokes_tokens_already_issued(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)
    assert client.get("/api/v1/bootstrap", headers=_auth(token)).status_code == 200

    with database.session() as session:
        household = session.get(Household, 1)
        assert household is not None
        household.pin_hash = hash_pin("9999")
        household.session_generation += 1

    response = client.get("/api/v1/bootstrap", headers=_auth(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


# ---------------------------------------------------------------------------
# Capture to ledger
# ---------------------------------------------------------------------------


def test_upload_accepts_photos_and_reports_progress(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)

    created = client.post(
        "/api/v1/uploads",
        headers=_auth(token),
        files=[
            ("files", ("page-1.png", _png_bytes(), "image/png")),
            ("files", ("page-2.png", _png_bytes((210, 330)), "image/png")),
        ],
    )

    assert created.status_code == 201, created.text
    batch_id = created.json()["data"]["batch_id"]
    assert created.json()["data"]["total_files"] == 2

    progress = client.get(f"/api/v1/uploads/{batch_id}", headers=_auth(token))
    assert progress.status_code == 200
    data = progress.json()["data"]
    # The worker is not running in tests, so the batch is still queued.
    assert data["status"] == "in_progress"
    assert data["detail_status"] == "queued"
    assert [stage["name"] for stage in data["stages"]] == [
        "upload",
        "detect",
        "read",
        "extract",
        "file",
    ]
    assert data["stages"][0]["status"] == "in_progress"


def test_upload_rejects_more_photos_than_the_host_allows(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api
    token = _token(client, database)

    response = client.post(
        "/api/v1/uploads",
        headers=_auth(token),
        files=[
            ("files", (f"page-{index}.png", _png_bytes(), "image/png"))
            for index in range(settings.max_photo_files + 1)
        ],
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOO_MANY_FILES"


def test_retry_requeues_a_failed_batch_without_a_new_upload(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)
    created = client.post(
        "/api/v1/uploads",
        headers=_auth(token),
        files=[("files", ("page-1.png", _png_bytes(), "image/png"))],
    )
    batch_id = created.json()["data"]["batch_id"]
    with database.session() as session:
        batch = session.get(UploadBatch, batch_id)
        assert batch is not None
        batch.status = ProcessingStatus.FAILED
        stored_keys = [entry.storage_key for entry in batch.files]

    retried = client.post(f"/api/v1/uploads/{batch_id}/retry", headers=_auth(token))

    assert retried.status_code == 200
    with database.session() as session:
        batch = session.get(UploadBatch, batch_id)
        assert batch is not None
        assert batch.status == ProcessingStatus.QUEUED
        # The uploaded draft is preserved so a retry never asks the person to
        # photograph the receipt again.
        assert [entry.storage_key for entry in batch.files] == stored_keys


def test_receipt_images_require_authentication_and_stream_the_stored_file(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api
    token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)

    anonymous = client.get(f"/api/v1/receipts/{receipt_id}/image")
    assert anonymous.status_code == 401

    served = client.get(f"/api/v1/receipts/{receipt_id}/image", headers=_auth(token))
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"] == "private, no-store"
    assert served.content.startswith(b"\x89PNG")

    missing_page = client.get(
        f"/api/v1/receipts/{receipt_id}/image?page=4", headers=_auth(token)
    )
    assert missing_page.status_code == 404


def test_correcting_a_receipt_files_it_and_updates_analytics(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api
    token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)

    detail = client.get(f"/api/v1/receipts/{receipt_id}", headers=_auth(token)).json()
    assert detail["data"]["attention_required"] is True
    assert detail["data"]["line_items"][0]["needs_review"] is True
    assert detail["data"]["image_urls"] == [
        f"/api/v1/receipts/{receipt_id}/image?page=1"
    ]

    purchase_date = _household_today().replace(day=1)
    updated = client.patch(
        f"/api/v1/receipts/{receipt_id}",
        headers=_auth(token),
        json={
            "merchant": "Coles",
            "date": purchase_date.isoformat(),
            "total": 650,
            "line_items": [
                {
                    "description": "Oat milk",
                    "quantity": "2",
                    "unit": "each",
                    "line_total": "6.50",
                    "category": "Dairy",
                }
            ],
        },
    )

    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["status"] == "complete"
    assert data["merchant"] == "Coles"
    assert data["total"] == 650
    assert data["dated"] is True

    with database.session() as session:
        item = session.scalar(
            select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id)
        )
        assert item is not None
        assert item.description == "Oat milk"
        assert item.unit_price_cents == 325
        snapshot = session.scalar(
            select(AnalyticsSnapshot).where(AnalyticsSnapshot.is_current.is_(True))
        )
        assert snapshot is not None
        assert snapshot.total_spend_cents == 650

    listed = client.get("/api/v1/receipts", headers=_auth(token)).json()["data"]
    assert listed["pagination"]["total"] == 1
    assert listed["items"][0]["merchant"] == "Coles"


def test_a_receipt_can_be_filed_without_a_date_but_stays_out_of_dated_totals(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """The filing gate is merchant and total; a date unlocks dated analytics."""

    client, database, settings = api
    token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)

    filed = client.patch(
        f"/api/v1/receipts/{receipt_id}",
        headers=_auth(token),
        json={
            "merchant": "Aldi",
            "total": 1200,
            "line_items": [
                {
                    "description": "Rice",
                    "quantity": "1",
                    "unit": "each",
                    "line_total": "12.00",
                    "category": "pantry",
                }
            ],
        },
    )

    assert filed.status_code == 200, filed.text
    data = filed.json()["data"]
    assert data["status"] == "complete"
    assert data["date"] is None
    assert data["dated"] is False

    with database.session() as session:
        snapshot = session.scalar(
            select(AnalyticsSnapshot).where(AnalyticsSnapshot.is_current.is_(True))
        )
        assert snapshot is not None
        assert snapshot.total_spend_cents == 0

    insights = client.get("/api/v1/insights", headers=_auth(token)).json()["data"]
    assert insights["month_total"] == 0


def test_filing_without_a_merchant_returns_a_typed_field_error(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api
    token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)

    response = client.patch(
        f"/api/v1/receipts/{receipt_id}",
        headers=_auth(token),
        json={"merchant": "   ", "total": 500},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_REQUEST"
    assert error["details"]["field"] == "merchant_name"


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------


def test_shopping_items_can_be_added_toggled_and_removed(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)

    created = client.post(
        "/api/v1/shopping",
        headers=_auth(token),
        json={"product": "Oat milk", "quantity": "2", "unit": "cartons"},
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["description"] == "Oat milk"
    assert item["status"] == "active"

    toggled = client.patch(
        f"/api/v1/shopping/{item['id']}",
        headers=_auth(token),
        json={"status": "completed", "version": item["version"]},
    )
    assert toggled.status_code == 200
    assert toggled.json()["data"]["status"] == "completed"

    listing = client.get("/api/v1/shopping", headers=_auth(token)).json()["data"]
    assert listing["summary"]["pending"] == 0
    assert listing["summary"]["checked"] == 1

    removed = client.delete(f"/api/v1/shopping/{item['id']}", headers=_auth(token))
    assert removed.status_code == 200
    with database.session() as session:
        stored = session.get(ShoppingItem, item["id"])
        assert stored is not None
        assert stored.status == ShoppingStatus.DISMISSED


def test_a_stale_shopping_edit_is_reported_as_a_conflict(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """Two phones share one list, so a stale write must not overwrite silently."""

    client, database, _settings = api
    token = _token(client, database)
    item = client.post(
        "/api/v1/shopping",
        headers=_auth(token),
        json={"product": "Bread", "quantity": "1"},
    ).json()["data"]
    stale_version = item["version"]

    first = client.patch(
        f"/api/v1/shopping/{item['id']}",
        headers=_auth(token),
        json={"product": "Sourdough", "version": stale_version},
    )
    assert first.status_code == 200

    second = client.patch(
        f"/api/v1/shopping/{item['id']}",
        headers=_auth(token),
        json={"product": "Rye", "version": stale_version},
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "VERSION_CONFLICT"
    with database.session() as session:
        stored = session.get(ShoppingItem, item["id"])
        assert stored is not None
        assert stored.description == "Sourdough"


def test_adding_a_blank_shopping_item_is_rejected(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, _settings = api
    token = _token(client, database)

    response = client.post(
        "/api/v1/shopping", headers=_auth(token), json={"product": "   "}
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["field"] == "description"


# ---------------------------------------------------------------------------
# Insights, settings and collections
# ---------------------------------------------------------------------------


def test_insights_and_bootstrap_share_one_set_of_household_figures(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api
    token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)
    client.patch(
        f"/api/v1/receipts/{receipt_id}",
        headers=_auth(token),
        json={
            "merchant": "Coles",
            "date": _household_today().replace(day=1).isoformat(),
            "total": 4500,
            "line_items": [
                {
                    "description": "Weekly shop",
                    "quantity": "1",
                    "unit": "each",
                    "line_total": "45.00",
                    "category": "pantry",
                }
            ],
        },
    )

    bootstrap = client.get("/api/v1/bootstrap", headers=_auth(token)).json()["data"]
    insights = client.get("/api/v1/insights", headers=_auth(token)).json()["data"]

    assert bootstrap["totals"]["month_total"] == 4500
    assert insights["month_total"] == 4500
    assert insights["receipt_count"] == 1
    # Collections are a view of the backend's line-item categories, so the same
    # identifier appears on both surfaces.
    assert bootstrap["collections"] == insights["collections"]
    assert any(row["id"] == "pantry" for row in insights["collections"])


def test_settings_report_host_limits_without_promising_hosted_features(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api
    token = _token(client, database)

    data = client.get("/api/v1/settings", headers=_auth(token)).json()["data"]

    assert data["household_name"] == "The Test Kitchen"
    assert data["max_photo_files"] == settings.max_photo_files
    assert data["session_max_age_seconds"] == settings.session_max_age_seconds
    # The shared price index and hosted backups belong to a later phase.
    assert data["sharing_available"] is False
    assert data["backup_enabled"] is False

def test_deleting_a_receipt_removes_it_for_the_household(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """The client offered delete long before the API did, so a deleted receipt
    reappeared on the next refresh."""

    client, database, settings = api
    token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)

    anonymous = client.delete(f"/api/v1/receipts/{receipt_id}")
    assert anonymous.status_code == 401

    removed = client.delete(f"/api/v1/receipts/{receipt_id}", headers=_auth(token))
    assert removed.status_code == 204

    gone = client.get(f"/api/v1/receipts/{receipt_id}", headers=_auth(token))
    assert gone.status_code == 404

    listed = client.get("/api/v1/receipts", headers=_auth(token)).json()
    assert all(row["id"] != receipt_id for row in listed["data"]["items"])

    missing = client.delete(f"/api/v1/receipts/{receipt_id}", headers=_auth(token))
    assert missing.status_code == 404


def test_a_receipt_reports_the_collection_its_items_fall_into(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """Collections are a view of the line-item categories. `collection_id` was
    hardcoded to None, so every receipt read as permanently unfiled."""

    client, database, settings = api
    token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)

    detail = client.get(f"/api/v1/receipts/{receipt_id}", headers=_auth(token)).json()
    payload = detail["data"]

    # Derived from whichever category holds most of the money, and normalised
    # so the client can match it against the collection list.
    assert "collection_id" in payload
    assert "collection_name" in payload
    if payload["collection_name"] is not None:
        assert payload["collection_id"] == services.normalize_collection_id(
            payload["collection_name"]
        )

    # The review screen edits this, so detail has to carry it.
    assert "transaction_number" in payload

