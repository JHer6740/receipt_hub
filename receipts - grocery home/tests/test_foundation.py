from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from starlette.responses import Response

from grocery_home.config import ConfigurationError, Settings, sqlite_url
from grocery_home.database import (
    CURRENT_SCHEMA_VERSION,
    create_database,
    initialize_schema,
    schema_version,
)
from grocery_home.models import (
    Household,
    PinAttempt,
    ProcessingStatus,
    Receipt,
    ReceiptItem,
    ReceiptSource,
    UploadBatch,
    UploadFile,
    make_receipt_natural_key,
)
from grocery_home.schemas import ParsedReceipt, ReceiptItem as ReceiptItemSchema
from grocery_home.security import (
    InvalidSessionError,
    PinThrottle,
    SessionManager,
    authenticate_shared_pin,
    configure_household,
    get_or_create_session_secret,
    hash_pin,
    session_matches_household,
    verify_csrf_token,
    verify_pin,
)


def test_settings_use_configured_private_data_directory(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "GROCERY_HOME_DATA_DIR": str(tmp_path / "runtime"),
            "GROCERY_HOME_SECURE_COOKIES": "yes",
            "GROCERY_HOME_MAX_PDF_PAGES": "8",
        }
    )

    assert settings.data_dir == tmp_path / "runtime"
    assert settings.database_url.endswith("/runtime/grocery_home.sqlite3")
    assert settings.secure_cookies is True
    assert settings.max_pdf_pages == 8

    settings.ensure_directories()
    assert settings.receipt_dir.is_dir()
    assert settings.temporary_dir.is_dir()


def test_settings_reject_invalid_security_values(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "GROCERY_HOME_DATA_DIR": str(tmp_path),
                "GROCERY_HOME_SECURE_COOKIES": "perhaps",
            }
        )


def test_schema_initialization_is_idempotent_and_enables_foreign_keys() -> None:
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    try:
        assert initialize_schema(database) == CURRENT_SCHEMA_VERSION
        assert initialize_schema(database) == CURRENT_SCHEMA_VERSION
        assert schema_version(database) == CURRENT_SCHEMA_VERSION

        with database.session() as session:
            migration_count = session.scalar(
                select(func.count()).select_from(
                    __import__(
                        "grocery_home.models",
                        fromlist=["SchemaMigration"],
                    ).SchemaMigration
                )
            )
            foreign_keys = session.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert migration_count == CURRENT_SCHEMA_VERSION
        assert foreign_keys == 1
    finally:
        database.dispose()


def test_duplicate_links_preserve_upload_audit_and_decimal_quantities() -> None:
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    natural_key = make_receipt_natural_key(
        merchant="Woolworths",
        purchase_date=date(2026, 7, 20),
        transaction_number="ABC-123",
        total_cents=1099,
        store_number="1208",
        pos_number="3",
    )
    assert natural_key is not None

    with database.session() as session:
        batch = UploadBatch(total_files=2)
        session.add(batch)
        session.flush()
        canonical_file = UploadFile(
            batch_id=batch.id,
            ordinal=1,
            original_filename="first.pdf",
            storage_key="first.pdf",
            media_type="application/pdf",
            file_size=100,
            content_sha256="a" * 64,
            status=ProcessingStatus.COMPLETE,
        )
        session.add(canonical_file)
        session.flush()
        duplicate_file = UploadFile(
            batch_id=batch.id,
            ordinal=2,
            original_filename="copy.pdf",
            storage_key="copy.pdf",
            media_type="application/pdf",
            file_size=100,
            content_sha256="a" * 64,
            status=ProcessingStatus.DUPLICATE,
            duplicate_of_id=canonical_file.id,
        )
        canonical_receipt = Receipt(
            upload_file=canonical_file,
            merchant_key="woolworths",
            merchant_name="Woolworths",
            purchase_date=date(2026, 7, 20),
            transaction_number="ABC-123",
            total_cents=1099,
            status=ProcessingStatus.COMPLETE,
            source_kind=ReceiptSource.TEXT_PDF,
            natural_key=natural_key,
        )
        canonical_receipt.items.append(
            ReceiptItem(
                line_number=1,
                description="Loose bananas",
                quantity=Decimal("1.275"),
                quantity_unit="kg",
                line_total_cents=575,
            )
        )
        session.add_all((duplicate_file, canonical_receipt))

    with database.session() as session:
        item = session.scalar(select(ReceiptItem))
        duplicate = session.scalar(
            select(UploadFile).where(
                UploadFile.status == ProcessingStatus.DUPLICATE
            )
        )
        assert item is not None
        assert item.quantity == Decimal("1.275")
        assert duplicate is not None
        assert duplicate.duplicate_of_id is not None

    database.dispose()


def test_canonical_hash_is_unique_but_linked_duplicate_is_allowed() -> None:
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    try:
        with pytest.raises(IntegrityError):
            with database.session() as session:
                batch = UploadBatch(total_files=2)
                session.add(batch)
                session.flush()
                session.add_all(
                    (
                        UploadFile(
                            batch_id=batch.id,
                            ordinal=1,
                            original_filename="one.pdf",
                            storage_key="one.pdf",
                            media_type="application/pdf",
                            file_size=1,
                            content_sha256="b" * 64,
                        ),
                        UploadFile(
                            batch_id=batch.id,
                            ordinal=2,
                            original_filename="two.pdf",
                            storage_key="two.pdf",
                            media_type="application/pdf",
                            file_size=1,
                            content_sha256="b" * 64,
                        ),
                    )
                )
    finally:
        database.dispose()


def test_receipt_schema_reports_balance_without_float_money() -> None:
    parsed = ParsedReceipt(
        merchant_name="Coles",
        total_cents=725,
        items=[
            ReceiptItemSchema(
                line_number=1,
                description="Milk",
                quantity=Decimal("2"),
                line_total_cents=650,
            ),
            ReceiptItemSchema(
                line_number=2,
                description="Bag",
                line_total_cents=25,
            ),
        ],
    )

    assert parsed.item_total_cents == 675
    assert parsed.balance_difference_cents == 50


def test_argon2_pin_and_signed_session_cookie() -> None:
    pin_hash = hash_pin("4826")
    assert pin_hash.startswith("$argon2")
    assert verify_pin(pin_hash, "4826")
    assert not verify_pin(pin_hash, "4827")

    manager = SessionManager(
        "test-session-secret-that-is-long-enough-123456",
        max_age_seconds=300,
    )
    issued = manager.issue(household_id=1, generation=4)
    loaded = manager.load(issued.token)
    assert loaded.household_id == 1
    assert loaded.generation == 4
    assert verify_csrf_token(loaded.csrf_token, issued.data.csrf_token)
    assert not verify_csrf_token(loaded.csrf_token, "wrong")

    with pytest.raises(InvalidSessionError):
        manager.load(issued.token + "tampered")

    response = Response()
    manager.set_cookie(response, issued)
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


def test_pin_throttle_persists_lockout_and_success_clears_it() -> None:
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    throttle = PinThrottle(
        max_failures=2,
        window_seconds=120,
        lock_seconds=60,
        fingerprint_pepper="test-pepper",
    )
    began = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)

    with database.session() as session:
        household = configure_household(session, "4826")
        generated_secret = get_or_create_session_secret(session)
        assert len(generated_secret) >= 32

    with database.session() as session:
        assert get_or_create_session_secret(session) == generated_secret

    with database.session() as session:
        household = session.get(Household, 1)
        assert household is not None
        first = authenticate_shared_pin(
            session,
            household,
            "0000",
            "192.0.2.10",
            throttle,
            now=began,
        )
        second = authenticate_shared_pin(
            session,
            household,
            "0000",
            "192.0.2.10",
            throttle,
            now=began + timedelta(seconds=1),
        )
        assert not first.authenticated and not first.rate_limited
        assert not second.authenticated and second.rate_limited
        assert second.retry_after_seconds == 60

    # A new transaction observes the persisted lock after the request ended.
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PinAttempt)) == 1
        household = session.get(Household, 1)
        assert household is not None
        blocked = authenticate_shared_pin(
            session,
            household,
            "4826",
            "192.0.2.10",
            throttle,
            now=began + timedelta(seconds=30),
        )
        assert blocked.rate_limited

        accepted = authenticate_shared_pin(
            session,
            household,
            "4826",
            "192.0.2.10",
            throttle,
            now=began + timedelta(seconds=62),
        )
        assert accepted.authenticated
        assert session.scalar(select(func.count()).select_from(PinAttempt)) == 0

        manager = SessionManager("another-long-session-secret-1234567890")
        session_data = manager.issue(1, household.session_generation).data
        assert session_matches_household(session_data, household)
        household.session_generation += 1
        assert not session_matches_household(session_data, household)

    database.dispose()


def test_upgrading_a_version_2_database_scopes_upload_files(tmp_path: Path) -> None:
    """The upgrade path a live database actually takes, not just a fresh one.

    A version 2 database has no ``upload_files.household_id`` and a canonical
    hash unique across every household. This drops the column and index to put
    a database back in that shape, then upgrades it: the column has to be
    added even with foreign keys enabled, backfilled from each file's batch,
    and the uniqueness re-made per household.
    """

    database = create_database(
        database_url=sqlite_url(tmp_path / "upgrade-test.sqlite3")
    )
    try:
        assert initialize_schema(database) == CURRENT_SCHEMA_VERSION

        # Put the table back to what version 2 left behind. The column cannot
        # simply be dropped, because the current schema has a foreign key on
        # it, so this rebuilds upload_files without it.
        with database.engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(text("DROP TABLE upload_files"))
            connection.execute(
                text(
                    """
                    CREATE TABLE upload_files (
                        id VARCHAR(32) NOT NULL PRIMARY KEY,
                        batch_id VARCHAR(32) NOT NULL
                            REFERENCES upload_batches(id) ON DELETE CASCADE,
                        ordinal INTEGER NOT NULL DEFAULT 0,
                        original_filename VARCHAR(255) NOT NULL,
                        storage_key VARCHAR(255) NOT NULL UNIQUE,
                        media_type VARCHAR(100) NOT NULL,
                        file_size INTEGER NOT NULL,
                        content_sha256 VARCHAR(64) NOT NULL,
                        page_count INTEGER NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'queued',
                        duplicate_of_id VARCHAR(32) NULL
                            REFERENCES upload_files(id) ON DELETE RESTRICT,
                        error_code VARCHAR(80) NULL,
                        error_message TEXT NULL,
                        created_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL,
                        CONSTRAINT uq_upload_files_batch_ordinal
                            UNIQUE (batch_id, ordinal)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_upload_files_canonical_hash "
                    "ON upload_files (content_sha256) "
                    "WHERE duplicate_of_id IS NULL"
                )
            )
            connection.execute(
                text("DELETE FROM schema_migrations WHERE version = 3")
            )

        # Two households, each with a batch holding one file. Their hashes
        # differ here only because the old index would not allow otherwise.
        with database.session() as session:
            session.add(Household(id=2, display_name="The second household"))
            session.flush()
            for index, household_id in enumerate((1, 2), start=1):
                batch = UploadBatch(
                    household_id=household_id,
                    status=ProcessingStatus.QUEUED,
                    total_files=1,
                    processed_files=0,
                )
                session.add(batch)
                session.flush()
                session.execute(
                    text(
                        """
                        INSERT INTO upload_files (
                            id, batch_id, ordinal, original_filename,
                            storage_key, media_type, file_size,
                            content_sha256, status, created_at, updated_at
                        ) VALUES (
                            :id, :batch_id, 1, :name, :key, 'image/png', 100,
                            :digest, 'queued', :now, :now
                        )
                        """
                    ),
                    {
                        "id": f"{index:032d}",
                        "batch_id": batch.id,
                        "name": f"page-{index}.png",
                        "key": f"stored-{index}.png",
                        "digest": f"{index:064d}",
                        "now": datetime.now(UTC),
                    },
                )
            session.commit()

        assert schema_version(database) == 2

        assert initialize_schema(database) == CURRENT_SCHEMA_VERSION

        with database.session() as session:
            owners = {
                entry.id: entry.household_id
                for entry in session.scalars(select(UploadFile)).all()
            }
            assert owners == {f"{1:032d}": 1, f"{2:032d}": 2}

            # The same hash is now allowed once per household, and still only
            # once within one.
            for household_id, file_id in ((1, "a" * 32), (2, "b" * 32)):
                batch = UploadBatch(
                    household_id=household_id,
                    status=ProcessingStatus.QUEUED,
                    total_files=1,
                    processed_files=0,
                )
                session.add(batch)
                session.flush()
                session.add(
                    UploadFile(
                        id=file_id,
                        household_id=household_id,
                        batch_id=batch.id,
                        ordinal=1,
                        original_filename="shared.png",
                        storage_key=f"shared-{household_id}.png",
                        media_type="image/png",
                        file_size=100,
                        content_sha256="f" * 64,
                        status=ProcessingStatus.QUEUED,
                    )
                )
            session.commit()

            duplicate_batch = UploadBatch(
                household_id=1,
                status=ProcessingStatus.QUEUED,
                total_files=1,
                processed_files=0,
            )
            session.add(duplicate_batch)
            session.flush()
            session.add(
                UploadFile(
                    id="c" * 32,
                    household_id=1,
                    batch_id=duplicate_batch.id,
                    ordinal=1,
                    original_filename="shared-again.png",
                    storage_key="shared-again.png",
                    media_type="image/png",
                    file_size=100,
                    content_sha256="f" * 64,
                    status=ProcessingStatus.QUEUED,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
    finally:
        database.dispose()
