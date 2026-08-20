"""Relational domain model for Grocery Home."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Date, DateTime, TypeDecorator

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    """Return a non-sequential identifier suitable for URLs and file metadata."""

    return uuid.uuid4().hex


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC timestamps in SQLite and restore timezone awareness."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class ProcessingStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"
    DUPLICATE = "duplicate"
    FAILED = "failed"


class UploadSource(str, Enum):
    WEB = "web"
    IMPORT = "import"


class ReceiptSource(str, Enum):
    TEXT_PDF = "text_pdf"
    SCANNED_PDF = "scanned_pdf"
    IMAGE = "image"
    IMPORT = "import"
    MANUAL = "manual"


class ShoppingStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class ShoppingSource(str, Enum):
    MANUAL = "manual"
    PREDICTED = "predicted"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


def _enum_type(enum_class: type[Enum], name: str) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        nullable=False,
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Household(TimestampMixin, Base):
    """The single household identity used by the v1 shared-PIN experience."""

    __tablename__ = "households"
    __table_args__ = (CheckConstraint("id = 1", name="ck_households_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Our household",
    )
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Australia/Sydney",
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AUD")


class PinAttempt(Base):
    """Persistent throttle state keyed by an irreversible client fingerprint."""

    __tablename__ = "pin_attempts"

    attempt_key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_started_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    last_attempt_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class UploadBatch(TimestampMixin, Base):
    __tablename__ = "upload_batches"
    __table_args__ = (
        CheckConstraint("total_files >= 0", name="ck_upload_batches_total_files"),
        CheckConstraint(
            "processed_files >= 0 AND processed_files <= total_files",
            name="ck_upload_batches_processed_files",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    status: Mapped[ProcessingStatus] = mapped_column(
        _enum_type(ProcessingStatus, "processing_status"),
        nullable=False,
        default=ProcessingStatus.QUEUED,
        index=True,
    )
    source: Mapped[UploadSource] = mapped_column(
        _enum_type(UploadSource, "upload_source"),
        nullable=False,
        default=UploadSource.WEB,
    )
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    files: Mapped[list["UploadFile"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="UploadFile.ordinal",
    )


class UploadFile(TimestampMixin, Base):
    __tablename__ = "upload_files"
    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", name="uq_upload_files_batch_ordinal"),
        Index(
            "uq_upload_files_canonical_hash",
            "content_sha256",
            unique=True,
            sqlite_where=text("duplicate_of_id IS NULL"),
        ),
        Index("ix_upload_files_content_sha256", "content_sha256"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ProcessingStatus] = mapped_column(
        _enum_type(ProcessingStatus, "upload_file_processing_status"),
        nullable=False,
        default=ProcessingStatus.QUEUED,
        index=True,
    )
    duplicate_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("upload_files.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch: Mapped["UploadBatch"] = relationship(back_populates="files")
    duplicate_of: Mapped["UploadFile | None"] = relationship(
        back_populates="duplicates",
        remote_side="UploadFile.id",
    )
    duplicates: Mapped[list["UploadFile"]] = relationship(back_populates="duplicate_of")
    receipt: Mapped["Receipt | None"] = relationship(
        back_populates="upload_file",
        uselist=False,
    )


class Receipt(TimestampMixin, Base):
    __tablename__ = "receipts"
    __table_args__ = (
        Index(
            "uq_receipts_canonical_natural_key",
            "natural_key",
            unique=True,
            sqlite_where=text(
                "duplicate_of_id IS NULL AND natural_key IS NOT NULL"
            ),
        ),
        Index("ix_receipts_purchase_date", "purchase_date"),
        Index("ix_receipts_merchant_date", "merchant_key", "purchase_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    upload_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("upload_files.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    merchant_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    merchant_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    store_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    store_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Australia/Sydney",
    )
    transaction_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pos_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subtotal_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gst_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    savings_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_count_reported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_grocery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[ProcessingStatus] = mapped_column(
        _enum_type(ProcessingStatus, "receipt_processing_status"),
        nullable=False,
        default=ProcessingStatus.NEEDS_REVIEW,
        index=True,
    )
    source_kind: Mapped[ReceiptSource] = mapped_column(
        _enum_type(ReceiptSource, "receipt_source"),
        nullable=False,
        default=ReceiptSource.MANUAL,
    )
    parse_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    natural_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    upload_file: Mapped["UploadFile | None"] = relationship(back_populates="receipt")
    duplicate_of: Mapped["Receipt | None"] = relationship(
        back_populates="duplicates",
        remote_side="Receipt.id",
    )
    duplicates: Mapped[list["Receipt"]] = relationship(back_populates="duplicate_of")
    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptItem.line_number",
    )


class ReceiptItem(TimestampMixin, Base):
    __tablename__ = "receipt_items"
    __table_args__ = (
        UniqueConstraint(
            "receipt_id",
            "line_number",
            name="uq_receipt_items_receipt_line",
        ),
        Index("ix_receipt_items_product_key", "product_key"),
        Index("ix_receipt_items_product_number", "product_number"),
        Index("ix_receipt_items_category", "category"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    receipt_id: Mapped[str] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    product_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Uncategorised",
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=Decimal("1"),
    )
    quantity_unit: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="each",
    )
    unit_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_total_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promotional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    price_reduced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    receipt: Mapped["Receipt"] = relationship(back_populates="items")


class ShoppingItem(TimestampMixin, Base):
    __tablename__ = "shopping_items"
    __table_args__ = (
        Index("ix_shopping_items_status_due", "status", "due_date"),
        Index("ix_shopping_items_product_key", "product_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=Decimal("1"),
    )
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="each")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ShoppingStatus] = mapped_column(
        _enum_type(ShoppingStatus, "shopping_status"),
        nullable=False,
        default=ShoppingStatus.ACTIVE,
        index=True,
    )
    source: Mapped[ShoppingSource] = mapped_column(
        _enum_type(ShoppingSource, "shopping_source"),
        nullable=False,
        default=ShoppingSource.MANUAL,
    )
    estimated_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dismissed_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        Index(
            "uq_analytics_snapshots_current",
            "is_current",
            unique=True,
            sqlite_where=text("is_current = 1"),
        ),
        Index("ix_analytics_snapshots_generated_at", "generated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    generated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_spend_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prior_spend_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    projected_30d_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    receipt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    included_through: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )
    source_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BackgroundJob(TimestampMixin, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_background_jobs_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_background_jobs_max_attempts"),
        Index("ix_background_jobs_claim", "status", "scheduled_for", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(
        _enum_type(JobStatus, "background_job_status"),
        nullable=False,
        default=JobStatus.QUEUED,
        index=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        unique=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    scheduled_for: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class PriceQuote(TimestampMixin, Base):
    __tablename__ = "price_quotes"
    __table_args__ = (
        UniqueConstraint(
            "merchant_key",
            "product_key",
            "fetched_at",
            name="uq_price_quotes_product_fetch",
        ),
        Index(
            "ix_price_quotes_product_latest",
            "merchant_key",
            "product_key",
            "fetched_at",
        ),
        CheckConstraint("price_cents >= 0", name="ck_price_quotes_price"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_key: Mapped[str] = mapped_column(String(120), nullable=False)
    merchant_key: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="woolworths",
    )
    product_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="woolworths_search",
    )
    fetched_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


_KEY_WHITESPACE = re.compile(r"\s+")
_KEY_PUNCTUATION = re.compile(r"[^a-z0-9]+")


def normalize_key_part(value: object | None) -> str:
    """Normalize user/receipt text for stable natural and product keys."""

    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    normalized = _KEY_PUNCTUATION.sub(" ", normalized)
    return _KEY_WHITESPACE.sub(" ", normalized).strip()


def make_receipt_natural_key(
    *,
    merchant: str | None,
    purchase_date: date | str | None,
    transaction_number: str | None,
    total_cents: int | None,
    store_number: str | None = None,
    pos_number: str | None = None,
) -> str | None:
    """Hash the transaction identity used for duplicate detection.

    A key is only emitted when merchant, date, transaction number and total are
    known.  Incomplete OCR drafts therefore remain reviewable without producing
    accidental collisions.
    """

    required = (merchant, purchase_date, transaction_number, total_cents)
    if any(value is None or str(value).strip() == "" for value in required):
        return None

    date_value = (
        purchase_date.isoformat()
        if isinstance(purchase_date, date)
        else str(purchase_date)
    )
    parts = (
        normalize_key_part(merchant),
        normalize_key_part(store_number),
        normalize_key_part(date_value),
        normalize_key_part(pos_number),
        normalize_key_part(transaction_number),
        str(total_cents),
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


__all__ = [
    "AnalyticsSnapshot",
    "AppSetting",
    "BackgroundJob",
    "Household",
    "JobStatus",
    "PinAttempt",
    "PriceQuote",
    "ProcessingStatus",
    "Receipt",
    "ReceiptItem",
    "ReceiptSource",
    "SchemaMigration",
    "ShoppingItem",
    "ShoppingSource",
    "ShoppingStatus",
    "UTCDateTime",
    "UploadBatch",
    "UploadFile",
    "UploadSource",
    "make_receipt_natural_key",
    "new_id",
    "normalize_key_part",
    "utc_now",
]
