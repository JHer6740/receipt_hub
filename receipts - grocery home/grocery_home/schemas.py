"""Validated boundary types used by routes, parsers and analytics services."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from .models import (
    JobStatus,
    ProcessingStatus,
    ReceiptSource,
    ShoppingSource,
    ShoppingStatus,
    UploadSource,
)


class DomainSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class ReceiptItem(DomainSchema):
    id: str | None = None
    line_number: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=255)
    normalized_description: str | None = Field(default=None, max_length=255)
    product_key: str | None = Field(default=None, max_length=120)
    product_number: str | None = Field(default=None, max_length=80)
    category: str = Field(default="Uncategorised", max_length=100)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=12, decimal_places=3)
    quantity_unit: str = Field(default="each", min_length=1, max_length=32)
    unit_price_cents: int | None = None
    line_total_cents: int | None = None
    taxable: bool = False
    promotional: bool = False
    price_reduced: bool = False
    confidence: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )
    needs_review: bool = False


class ParsedReceipt(DomainSchema):
    id: str | None = None
    upload_file_id: str | None = None
    merchant_key: str | None = Field(default=None, max_length=80)
    merchant_name: str | None = Field(default=None, max_length=160)
    store_number: str | None = Field(default=None, max_length=40)
    store_name: str | None = Field(default=None, max_length=160)
    purchase_date: date | None = None
    purchase_time: time | None = None
    timezone: str = "Australia/Sydney"
    transaction_number: str | None = Field(default=None, max_length=80)
    pos_number: str | None = Field(default=None, max_length=40)
    subtotal_cents: int | None = None
    total_cents: int | None = None
    gst_cents: int | None = None
    savings_cents: int | None = None
    item_count_reported: int | None = Field(default=None, ge=0)
    is_grocery: bool = True
    status: ProcessingStatus = ProcessingStatus.NEEDS_REVIEW
    source_kind: ReceiptSource = ReceiptSource.MANUAL
    parse_confidence: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )
    natural_key: str | None = Field(default=None, min_length=64, max_length=64)
    duplicate_of_id: str | None = None
    items: list[ReceiptItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def item_total_cents(self) -> int | None:
        values = [item.line_total_cents for item in self.items]
        if not values or any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    @computed_field
    @property
    def balance_difference_cents(self) -> int | None:
        item_total = self.item_total_cents
        if item_total is None or self.total_cents is None:
            return None
        return self.total_cents - item_total


class UploadFileState(DomainSchema):
    id: str
    ordinal: int = Field(ge=0)
    original_filename: str
    media_type: str
    file_size: int = Field(ge=0)
    status: ProcessingStatus
    receipt_id: str | None = None
    duplicate_of_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class UploadJob(DomainSchema):
    """Polling response for a user-facing upload batch."""

    id: str
    status: ProcessingStatus
    source: UploadSource = UploadSource.WEB
    total_files: int = Field(ge=0)
    processed_files: int = Field(ge=0)
    files: list[UploadFileState] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_progress(self) -> "UploadJob":
        if self.processed_files > self.total_files:
            raise ValueError("processed_files cannot exceed total_files")
        return self

    @computed_field
    @property
    def progress_percent(self) -> int:
        if self.total_files == 0:
            return 0
        return min(100, round((self.processed_files / self.total_files) * 100))


class ShoppingItem(DomainSchema):
    id: str
    product_key: str | None = None
    description: str
    quantity: Decimal
    unit: str
    note: str | None = None
    status: ShoppingStatus
    source: ShoppingSource
    estimated_price_cents: int | None = None
    due_date: date | None = None
    completed_at: datetime | None = None
    dismissed_until: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ShoppingItemCreate(DomainSchema):
    description: str = Field(min_length=1, max_length=255)
    product_key: str | None = Field(default=None, max_length=120)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(default="each", min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    source: ShoppingSource = ShoppingSource.MANUAL
    estimated_price_cents: int | None = Field(default=None, ge=0)
    due_date: date | None = None


class ShoppingItemUpdate(DomainSchema):
    description: str | None = Field(default=None, min_length=1, max_length=255)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    status: ShoppingStatus | None = None
    due_date: date | None = None
    expected_version: int = Field(ge=1)


class AnalyticsSnapshot(DomainSchema):
    id: str
    generated_at: datetime
    period_start: date | None = None
    period_end: date | None = None
    total_spend_cents: int
    prior_spend_cents: int
    projected_30d_cents: int
    receipt_count: int = Field(ge=0)
    included_through: datetime | None = None
    source_fingerprint: str
    payload: dict[str, Any] = Field(default_factory=dict)
    is_current: bool


class PriceQuote(DomainSchema):
    id: str
    product_key: str
    merchant_key: str
    product_number: str | None = None
    description: str
    price_cents: int = Field(ge=0)
    unit_price_cents: int | None = Field(default=None, ge=0)
    unit_label: str | None = None
    source: str
    fetched_at: datetime
    valid_until: datetime | None = None

    @computed_field
    @property
    def is_stale(self) -> bool:
        if self.valid_until is None:
            return False
        valid_until = self.valid_until
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        return valid_until <= datetime.now(UTC)


class BackgroundJobState(DomainSchema):
    id: str
    kind: str
    status: JobStatus
    attempts: int = Field(ge=0)
    max_attempts: int = Field(gt=0)
    scheduled_for: datetime
    locked_at: datetime | None = None
    locked_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None


class LoginRequest(DomainSchema):
    pin: str = Field(min_length=4, max_length=64)


__all__ = [
    "AnalyticsSnapshot",
    "BackgroundJobState",
    "DomainSchema",
    "LoginRequest",
    "ParsedReceipt",
    "PriceQuote",
    "ReceiptItem",
    "ShoppingItem",
    "ShoppingItemCreate",
    "ShoppingItemUpdate",
    "UploadFileState",
    "UploadJob",
]
