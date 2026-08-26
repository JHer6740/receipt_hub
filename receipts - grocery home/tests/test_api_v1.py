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

# ============================================================================
# Accounts, households and tenancy
# ============================================================================


def _register(client: TestClient, email: str, password: str = "correct-horse-9") -> str:
    """Create an account and return its (household-less) token."""

    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": email.split("@")[0]},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["token"]


def _create_household(client: TestClient, token: str, name: str) -> tuple[int, str]:
    """Create a household and return its id and a token scoped to it."""

    response = client.post(
        "/api/v1/households",
        json={"name": name},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    return payload["id"], payload["session"]["token"]


def test_an_account_can_be_created_and_used_to_sign_in(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, _database, _settings = api

    token = _register(client, "alex@example.com")
    assert token

    # The same address cannot be registered twice.
    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "alex@example.com", "password": "correct-horse-9"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EMAIL_TAKEN"

    # A short password is refused with something a person can act on.
    weak = client.post(
        "/api/v1/auth/register",
        json={"email": "sam@example.com", "password": "short"},
    )
    assert weak.status_code == 400
    assert weak.json()["error"]["code"] == "INVALID_PASSWORD"

    signed_in = client.post(
        "/api/v1/auth/login",
        json={"email": "ALEX@example.com", "password": "correct-horse-9"},
    )
    assert signed_in.status_code == 200, signed_in.text

    # A wrong password and an unknown address are indistinguishable, so this
    # cannot be used to discover who has an account.
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "alex@example.com", "password": "not-the-password"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "not-the-password"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_an_account_without_a_household_cannot_read_a_ledger(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """An account is not a ledger: receipts need a household."""

    client, _database, _settings = api
    token = _register(client, "alex@example.com")

    response = client.get("/api/v1/receipts", headers=_auth(token))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_HOUSEHOLD_SELECTED"


def test_one_household_cannot_read_another(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """The cross-tenant denial that multi-tenancy stands or falls on."""

    client, database, settings = api

    # Household 1 holds a receipt, reachable with the shared-PIN session.
    pin_token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)
    owner_view = client.get(f"/api/v1/receipts/{receipt_id}", headers=_auth(pin_token))
    assert owner_view.status_code == 200

    # A different account, with its own household.
    intruder = _register(client, "intruder@example.com")
    _household_id, intruder_token = _create_household(
        client, intruder, "Somewhere else"
    )

    # Reading someone else's receipt is *not found*, not *forbidden*: the API
    # does not confirm that the id exists.
    denied = client.get(
        f"/api/v1/receipts/{receipt_id}", headers=_auth(intruder_token)
    )
    assert denied.status_code == 404

    # It is absent from their ledger entirely.
    listed = client.get("/api/v1/receipts", headers=_auth(intruder_token)).json()
    assert listed["data"]["items"] == []
    assert listed["data"]["pagination"]["total"] == 0

    # And it cannot be deleted out from under its household.
    deletion = client.delete(
        f"/api/v1/receipts/{receipt_id}", headers=_auth(intruder_token)
    )
    assert deletion.status_code == 404

    still_there = client.get(
        f"/api/v1/receipts/{receipt_id}", headers=_auth(pin_token)
    )
    assert still_there.status_code == 200


def test_joining_a_household_is_a_request_until_someone_approves_it(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, database, settings = api

    owner = _register(client, "owner@example.com")
    household_id, owner_token = _create_household(client, owner, "The Morgans")

    joiner = _register(client, "joiner@example.com")
    requested = client.post(
        f"/api/v1/households/{household_id}/join-requests",
        headers=_auth(joiner),
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["data"]["status"] == "pending"
    # A pending request never carries the join code.
    assert requested.json()["data"]["join_code"] is None

    # Pending is not access: the household cannot be selected.
    blocked = client.post(
        f"/api/v1/households/{household_id}/select",
        headers=_auth(joiner),
    )
    assert blocked.status_code == 404

    # The owner sees the request with who it is from.
    members = client.get(
        f"/api/v1/households/{household_id}/members",
        headers=_auth(owner_token),
    ).json()["data"]["items"]
    pending = [row for row in members if row["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["email"] == "joiner@example.com"
    membership_id = pending[0]["id"]

    # A requester cannot approve themselves.
    self_approval = client.post(
        f"/api/v1/households/{household_id}/join-requests/{membership_id}/approve",
        headers=_auth(joiner),
    )
    assert self_approval.status_code in (403, 404)

    approved = client.post(
        f"/api/v1/households/{household_id}/join-requests/{membership_id}/approve",
        headers=_auth(owner_token),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "active"

    # Now they can select it and read the ledger.
    selected = client.post(
        f"/api/v1/households/{household_id}/select",
        headers=_auth(joiner),
    )
    assert selected.status_code == 200
    scoped = selected.json()["data"]["token"]
    assert client.get("/api/v1/receipts", headers=_auth(scoped)).status_code == 200

    # Removing them revokes it, even though their token is unchanged.
    removed = client.delete(
        f"/api/v1/households/{household_id}/members/{membership_id}",
        headers=_auth(owner_token),
    )
    assert removed.status_code == 204
    assert client.get("/api/v1/receipts", headers=_auth(scoped)).status_code == 403


def test_an_owner_cannot_be_removed_from_their_household(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, _database, _settings = api

    owner = _register(client, "owner@example.com")
    household_id, owner_token = _create_household(client, owner, "The Morgans")
    members = client.get(
        f"/api/v1/households/{household_id}/members",
        headers=_auth(owner_token),
    ).json()["data"]["items"]
    owner_membership = next(row for row in members if row["role"] == "owner")

    response = client.delete(
        f"/api/v1/households/{household_id}/members/{owner_membership['id']}",
        headers=_auth(owner_token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CANNOT_REMOVE_OWNER"


def test_a_password_reset_never_reveals_whether_an_account_exists(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, _database, _settings = api
    _register(client, "alex@example.com")

    known = client.post(
        "/api/v1/auth/reset-password", json={"email": "alex@example.com"}
    )
    unknown = client.post(
        "/api/v1/auth/reset-password", json={"email": "nobody@example.com"}
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json()["data"] == unknown.json()["data"]


def test_deleting_an_account_leaves_the_household_ledger_intact(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """Receipts belong to the household, not to whoever photographed them."""

    client, database, settings = api
    pin_token = _token(client, database)
    receipt_id = _seed_review_receipt(database, settings)

    joiner = _register(client, "joiner@example.com")
    gone = client.delete("/api/v1/auth/account", headers=_auth(joiner))
    assert gone.status_code == 204

    # The token stops working.
    assert client.get("/api/v1/households", headers=_auth(joiner)).status_code == 401
    # The ledger is untouched.
    assert (
        client.get(f"/api/v1/receipts/{receipt_id}", headers=_auth(pin_token)).status_code
        == 200
    )


def test_refreshing_a_session_keeps_the_chosen_household(
    api: tuple[TestClient, Database, Settings],
) -> None:
    client, _database, _settings = api
    owner = _register(client, "owner@example.com")
    household_id, scoped = _create_household(client, owner, "The Morgans")

    refreshed = client.post("/api/v1/auth/refresh", headers=_auth(scoped))
    assert refreshed.status_code == 200, refreshed.text
    new_token = refreshed.json()["data"]["token"]

    # Still scoped: the ledger is readable without choosing again.
    assert client.get("/api/v1/receipts", headers=_auth(new_token)).status_code == 200
    assert refreshed.json()["data"]["household_name"] == "The Morgans"
    assert household_id


def test_repeated_sign_in_failures_are_throttled(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """Only /auth/pin was throttled, so sign-in could be guessed at forever."""

    client, _database, _settings = api
    _register(client, "alex@example.com")

    statuses = []
    for _ in range(8):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alex@example.com", "password": "not-the-password"},
        )
        statuses.append(response.status_code)

    assert 429 in statuses, statuses
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "alex@example.com", "password": "not-the-password"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["details"]["retry_after_seconds"] > 0

    # Registration keeps its own counter, so failed sign-ins do not lock
    # somebody out of creating an account.
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "correct-horse-9"},
        ).status_code
        == 201
    )


def test_a_household_can_export_its_ledger_and_only_its_own(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """Deleting an account is only fair if the data can be taken out first."""

    client, database, settings = api
    _token(client, database)
    _seed_review_receipt(database, settings)

    # Household 1's own member exports it. The PIN session is not an account
    # session, so export is reached with an account that belongs to it.
    owner = _register(client, "owner@example.com")
    with database.session() as db:
        from grocery_home.models import (
            HouseholdMembership,
            MembershipRole,
            MembershipStatus,
            User,
        )
        from sqlalchemy import select as sa_select

        user = db.scalar(sa_select(User).where(User.email == "owner@example.com"))
        db.add(
            HouseholdMembership(
                household_id=1,
                user_id=user.id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    selected = client.post("/api/v1/households/1/select", headers=_auth(owner))
    assert selected.status_code == 200, selected.text

    export = client.get("/api/v1/households/1/export", headers=_auth(owner))
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("text/csv")
    assert "attachment" in export.headers["content-disposition"]
    body = export.text
    assert "receipt_id,purchase_date,merchant" in body
    assert len(body.strip().splitlines()) > 1

    # Someone else's household cannot be exported.
    intruder = _register(client, "intruder@example.com")
    _create_household(client, intruder, "Somewhere else")
    denied = client.get("/api/v1/households/1/export", headers=_auth(intruder))
    assert denied.status_code == 404


def test_an_upload_belongs_to_the_household_that_made_it(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """The reading screen has to be able to poll the batch it just created.

    Upload wrote the batch with the default household while the status route
    read it scoped to the caller's, so a capture on a real account reported
    "Upload batch ... not found" on the phone, and the receipt that came out of
    it was filed into a household the person who photographed it is not in.
    The existing upload tests missed this because they authenticate with the
    household PIN, which is household 1 — the same value the default supplied.
    """

    client, database, _settings = api
    account = _register(client, "alex@example.com")
    household_id, token = _create_household(client, account, "The Alex household")

    created = client.post(
        "/api/v1/uploads",
        headers=_auth(token),
        files=[("files", ("page-1.png", _png_bytes(), "image/png"))],
    )
    assert created.status_code == 201, created.text
    batch_id = created.json()["data"]["batch_id"]

    progress = client.get(f"/api/v1/uploads/{batch_id}", headers=_auth(token))
    assert progress.status_code == 200, progress.text
    assert progress.json()["data"]["batch_id"] == batch_id

    with database.session() as session:
        batch = session.get(UploadBatch, batch_id)
        assert batch is not None
        assert batch.household_id == household_id


def test_another_household_cannot_read_or_requeue_an_upload(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """A batch id is not a capability."""

    client, _database, _settings = api
    alex_account = _register(client, "alex@example.com")
    _alex_id, alex = _create_household(client, alex_account, "The Alex household")
    sam_account = _register(client, "sam@example.com")
    _sam_id, sam = _create_household(client, sam_account, "The Sam household")

    created = client.post(
        "/api/v1/uploads",
        headers=_auth(alex),
        files=[("files", ("page-1.png", _png_bytes(), "image/png"))],
    )
    assert created.status_code == 201, created.text
    batch_id = created.json()["data"]["batch_id"]

    # 404 rather than 403: answering differently would confirm the batch exists.
    denied = client.get(f"/api/v1/uploads/{batch_id}", headers=_auth(sam))
    assert denied.status_code == 404
    denied_retry = client.post(
        f"/api/v1/uploads/{batch_id}/retry", headers=_auth(sam)
    )
    assert denied_retry.status_code == 404

    # The household that made it still can.
    assert (
        client.get(f"/api/v1/uploads/{batch_id}", headers=_auth(alex)).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/uploads/{batch_id}/retry", headers=_auth(alex)
        ).status_code
        == 200
    )


def test_the_same_photo_in_two_households_stays_separate(
    api: tuple[TestClient, Database, Settings],
) -> None:
    """File-hash deduplication must not reach across households.

    An unscoped hash match links this household's upload to another's receipt,
    and the duplicate path copies that receipt's merchant and totals — so one
    tenant's figures would appear inside another tenant's ledger.
    """

    client, database, _settings = api
    photo = _png_bytes()
    alex_account = _register(client, "alex@example.com")
    alex_id, alex = _create_household(client, alex_account, "The Alex household")
    sam_account = _register(client, "sam@example.com")
    sam_id, sam = _create_household(client, sam_account, "The Sam household")

    for token in (alex, sam):
        response = client.post(
            "/api/v1/uploads",
            headers=_auth(token),
            files=[("files", ("page-1.png", photo, "image/png"))],
        )
        assert response.status_code == 201, response.text

    with database.session() as session:
        uploads = session.scalars(select(UploadFile)).all()
        assert len(uploads) == 2
        assert [entry.duplicate_of_id for entry in uploads] == [None, None]
        batches = session.scalars(select(UploadBatch)).all()
        assert {batch.household_id for batch in batches} == {alex_id, sam_id}
