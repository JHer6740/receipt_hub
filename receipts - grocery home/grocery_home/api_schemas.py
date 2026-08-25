"""Pydantic schemas for /api/v1 JSON request/response validation and OpenAPI documentation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Base model configuration
# ============================================================================


class ApiBaseModel(BaseModel):
    """Base model with API-specific configuration."""
    model_config = ConfigDict(
        populate_by_name=True,  # Accept both field name and alias in input
        use_attribute_docstrings=True,
    )


# ============================================================================
# Enums
# ============================================================================


class StatusEnum(str, Enum):
    """Receipt processing status (mirrors models.ProcessingStatus)."""
    QUEUED = "queued"
    EXTRACTING = "extracting"
    NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"
    DUPLICATE = "duplicate"
    FAILED = "failed"


class ShoppingStatusEnum(str, Enum):
    """Shopping item status."""
    ACTIVE = "active"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


# ============================================================================
# Response Envelope (used for all JSON responses)
# ============================================================================


class ApiError(BaseModel):
    """Structured error response."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="User-facing error message")
    details: dict[str, Any] | None = Field(None, description="Additional context")
    timestamp: datetime = Field(..., description="When the error occurred (ISO 8601 UTC)")
    trace_id: str = Field(..., description="Request trace ID for debugging")


T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """Standard response envelope for all /api/v1 responses."""
    success: bool = Field(..., description="Whether the request succeeded")
    data: dict[str, Any] | list[Any] | None = Field(
        None, 
        description="Response payload (varies by endpoint)"
    )
    error: ApiError | None = Field(None, description="Error details if success=false")
    timestamp: datetime = Field(..., description="Response timestamp (ISO 8601 UTC)")
    trace_id: str = Field(..., description="Request trace ID")


# ============================================================================
# Authentication
# ============================================================================


class PinAuthRequest(BaseModel):
    """Request body for POST /api/v1/auth/pin."""
    pin: str = Field(..., min_length=4, max_length=64, description="Household PIN")


class RegisterRequest(BaseModel):
    """Request body for POST /api/v1/auth/register."""

    email: str = Field(..., max_length=320, description="Email address")
    # Length is enforced in `accounts.validate_password` so the response
    # names what to do instead of returning a bare 422.
    password: str = Field(..., max_length=200)
    display_name: str | None = Field(
        default=None,
        max_length=100,
        description="Shown to others in the household",
    )


class LoginRequest(BaseModel):
    """Request body for POST /api/v1/auth/login."""

    email: str = Field(..., max_length=320)
    password: str = Field(..., max_length=200)


class PasswordResetRequest(BaseModel):
    """Request body for POST /api/v1/auth/reset-password."""

    email: str = Field(..., max_length=320)


class CreateHouseholdRequest(BaseModel):
    """Request body for POST /api/v1/households."""

    name: str = Field(..., min_length=1, max_length=100)


class SessionTokenData(BaseModel):
    """Successful authentication response."""
    session_token: str = Field(..., description="Bearer token for API requests")
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")
    expires_at: datetime = Field(..., description="Token expiration timestamp (ISO 8601 UTC)")


# ============================================================================
# Bootstrap & Settings
# ============================================================================


class HouseholdInfo(BaseModel):
    """Household identity info."""
    name: str = Field(..., description="Household display name")
    created_at: datetime = Field(..., description="When household was created (ISO 8601 UTC)")


class MonthTrendPoint(BaseModel):
    """Monthly spend point in trend."""
    month: str = Field(..., description="ISO month (YYYY-MM)")
    total: int = Field(..., description="Month total in cents")


class TotalsData(BaseModel):
    """Household totals and trends."""
    month_total: int = Field(..., description="Current month total in cents")
    month_trend: list[MonthTrendPoint] = Field(
        ..., 
        description="6-month spend trend"
    )


class CollectionSummary(BaseModel):
    """Collection summary (for Bootstrap)."""
    id: str = Field(..., description="Collection ID")
    name: str = Field(..., description="Collection display name")
    icon: str = Field(..., description="Emoji icon")
    month_total: int = Field(..., description="This month's total in cents")
    month_delta_percent: float | None = Field(
        None,
        description="Month-over-month change as percentage"
    )


class BootstrapSettings(BaseModel):
    """Settings returned in bootstrap."""
    sharing_consent: bool = Field(..., description="Whether user consents to price sharing")
    preferred_merchants: list[str] = Field(
        default_factory=list,
        description="User's preferred merchant codes"
    )
    backup_enabled: bool = Field(..., description="Whether automatic backups are enabled")
    last_backup: datetime | None = Field(
        None,
        description="When the last backup completed"
    )


class BootstrapData(BaseModel):
    """Response body for GET /api/v1/bootstrap."""
    household: HouseholdInfo
    totals: TotalsData
    collections: list[CollectionSummary]
    settings: BootstrapSettings


class SettingsData(BaseModel):
    """Response body for GET /api/v1/settings."""
    household_name: str = Field(..., description="Household display name")
    sharing_consent: bool = Field(..., description="Whether prices are shared")
    sharing_stats: dict[str, int] = Field(
        ...,
        description="Dict with 'contributed_prices', 'shared_this_month', 'merchants_supported'"
    )
    preferred_merchants: list[str]
    backup_enabled: bool
    backup_schedule: Literal["daily", "weekly", "monthly"]
    last_backup_at: datetime | None
    last_backup_size_bytes: int


class UpdateSettingsRequest(BaseModel):
    """Request body for PATCH /api/v1/settings."""
    sharing_consent: bool | None = None
    backup_enabled: bool | None = None
    backup_schedule: Literal["daily", "weekly", "monthly"] | None = None
    preferred_merchants: list[str] | None = None


# ============================================================================
# Receipts
# ============================================================================


class PriceVerdict(BaseModel):
    """Price comparison verdict for a line item."""
    vs_other_merchants: Literal["lowest", "higher", "much_higher", "insufficient_data"]
    savings: int | None = Field(None, description="Savings in cents vs next cheapest")
    comparison_detail: str | None = Field(
        None,
        description="Human-readable comparison (e.g., '$2.45 vs Coles $2.60')"
    )


class LineItemResponse(BaseModel):
    """Line item in receipt response."""
    id: str = Field(..., description="Line item ID")
    product: str = Field(..., description="Product description")
    quantity: Decimal = Field(..., description="Quantity as decimal")
    unit: str = Field(..., description="Unit of measure (e.g., 'unit', 'kg')")
    unit_price: int = Field(..., description="Price per unit in cents")
    total_price: int = Field(..., description="Total for this line in cents")
    category: str = Field(..., description="Product category")
    confidence: float = Field(..., ge=0, le=1, description="OCR confidence (0.0-1.0)")
    product_id: str | None = Field(None, description="Identifier for price comparisons")
    price_verdict: PriceVerdict | None = Field(
        None,
        description="Comparison verdict (if sufficient data)"
    )


class ReceiptBalance(BaseModel):
    """Balance validation data."""
    line_items_sum: int = Field(..., description="Sum of line totals in cents")
    stated_total: int = Field(..., description="Receipt's stated total in cents")
    difference: int = Field(..., description="Difference (stated - sum) in cents")
    reconciled: bool = Field(..., description="Whether totals match")


class ReceiptImageUrl(BaseModel):
    """Image URL in receipt response."""
    page: int = Field(..., ge=1, description="Page number (1-indexed)")
    url: str = Field(..., description="Authenticated download URL")
    expires_at: datetime = Field(..., description="When URL expires (ISO 8601 UTC)")


class ReceiptItemResponse(BaseModel):
    """Receipt response (list view)."""
    id: str = Field(..., description="Receipt ID")
    merchant: str = Field(..., description="Merchant name")
    purchase_date: date = Field(..., alias="date", description="Purchase date (ISO format)")
    total: int = Field(..., description="Total in cents")
    status: StatusEnum
    collection_id: str | None = Field(None, description="Collection ID if filed")
    collection_name: str | None = Field(None, description="Collection name if filed")
    image_count: int = Field(..., description="Number of pages")
    attention_required: bool = Field(..., description="Whether receipt needs review")
    created_at: datetime = Field(..., description="When receipt was created (ISO 8601 UTC)")


class ReceiptDetailResponse(BaseModel):
    """Receipt response (detail view)."""
    id: str = Field(..., description="Receipt ID")
    merchant: str = Field(..., description="Merchant name")
    merchant_confidence: float = Field(..., ge=0, le=1)
    purchase_date: date = Field(..., alias="date", description="Purchase date")
    date_confidence: float = Field(..., ge=0, le=1)
    total: int = Field(..., description="Total in cents")
    total_confidence: float = Field(..., ge=0, le=1)
    tax: int | None = Field(None, description="Tax amount in cents")
    tax_confidence: float | None = Field(None, ge=0, le=1)
    status: StatusEnum
    collection_id: str | None
    collection_name: str | None
    image_count: int
    image_urls: list[ReceiptImageUrl]
    balance: ReceiptBalance
    line_items: list[LineItemResponse]
    created_at: datetime
    updated_at: datetime


class CreateReceiptRequest(BaseModel):
    """Request body for POST /api/v1/receipts."""
    image_count: int = Field(..., ge=1, le=5, description="Number of images to upload")


class UploadUrl(BaseModel):
    """Upload URL for one image."""
    page: int = Field(..., ge=1, description="Page number")
    upload_url: str = Field(..., description="Presigned PUT URL for image upload")
    expires_at: datetime = Field(..., description="When URL expires (ISO 8601 UTC)")


class CreateReceiptResponse(BaseModel):
    """Response body for POST /api/v1/receipts."""
    receipt_id: str = Field(..., description="ID of created receipt")
    upload_batch_id: str = Field(..., description="Batch ID for tracking progress")
    upload_urls: list[UploadUrl] = Field(..., description="Where to upload images")


class UpdateReceiptRequest(BaseModel):
    """Request body for PATCH /api/v1/receipts/{id}."""
    merchant: str | None = None
    purchase_date: date | None = Field(None, alias="date")
    total: int | None = None
    tax: int | None = None
    collection_id: str | None = None
    line_items: list[dict[str, Any]] | None = None


class UpdateReceiptResponse(BaseModel):
    """Response body for PATCH /api/v1/receipts/{id}."""
    id: str
    status: StatusEnum
    merchant: str | None
    purchase_date: date | None = Field(None, alias="date")
    total: int | None


class ReceiptListResponse(BaseModel):
    """Response body for GET /api/v1/receipts."""
    items: list[ReceiptItemResponse]
    pagination: dict[str, Any] = Field(
        ...,
        description="Pagination info: {total, limit, offset, has_more}"
    )


# ============================================================================
# Upload Progress
# ============================================================================


class ProcessingStage(BaseModel):
    """One stage in the OCR pipeline."""
    name: Literal["upload", "detect", "read", "extract", "file"]
    status: Literal["pending", "in_progress", "complete", "failed"]
    progress: int = Field(..., ge=0, le=100, description="Progress as 0-100")


class UploadStatusResponse(BaseModel):
    """Response body for GET /api/v1/uploads/{batch_id}/status."""
    batch_id: str
    receipt_id: str
    status: Literal["in_progress", "complete", "failed"]
    current_stage: str | None
    stages: list[ProcessingStage]
    errors: dict[str, str] | None = Field(
        None,
        description="Error details if failed"
    )


# ============================================================================
# Shopping List
# ============================================================================


class PriceQuote(BaseModel):
    """Price quote for one merchant."""
    merchant: str = Field(..., description="Merchant code (e.g., 'woolworths')")
    price_per_unit: int = Field(..., description="Price per unit in cents")
    total_price: int = Field(..., description="Total for quantity in cents")
    pack_size: str | None = Field(None, description="Pack size (e.g., '2L')")
    confidence: Literal["confirmed", "estimated", "stale"]
    source: Literal["your_receipts", "price_pool", "catalog"]
    observed_date: date = Field(..., alias="date", description="When this price was observed")


class ShoppingItemResponse(BaseModel):
    """Shopping item in list response."""
    id: str
    product: str = Field(..., description="Product description")
    quantity: Decimal
    unit: str = Field(..., description="Unit of measure")
    status: ShoppingStatusEnum
    created_at: datetime
    quotes: list[PriceQuote] = Field(default_factory=list)
    cheapest: str | None = Field(None, description="Cheapest merchant code")
    savings: int | None = Field(None, description="Savings vs most expensive in cents")
    coverage: int = Field(..., description="Number of merchants with quotes")


class ShoppingListResponse(BaseModel):
    """Response body for GET /api/v1/shopping."""
    items: list[ShoppingItemResponse]
    summary: dict[str, Any] = Field(
        ...,
        description="Summary: {total_items, pending, checked, total_lowest_spend}"
    )


class AddShoppingItemRequest(BaseModel):
    """Request body for POST /api/v1/shopping."""
    product: str = Field(..., min_length=1, description="Product description")
    quantity: Decimal = Field(default=Decimal("1"), gt=0, description="Quantity")
    unit: str = Field(default="each", description="Unit of measure")
    note: str | None = Field(default=None, max_length=500, description="Optional note")


class UpdateShoppingItemRequest(BaseModel):
    """Request body for PATCH /api/v1/shopping/{id}.

    ``version`` carries the copy of the item the client last saw.  The shared
    list is edited from several devices, so a mismatch is reported as a conflict
    rather than silently overwriting another person's change.
    """
    product: str | None = Field(default=None, min_length=1)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = None
    note: str | None = Field(default=None, max_length=500)
    status: ShoppingStatusEnum | None = None
    version: int | None = Field(
        default=None, ge=1, description="Version the client last read"
    )


# ============================================================================
# Insights & Comparisons
# ============================================================================


class ProductHistory(BaseModel):
    """One product in purchase history."""
    product: str
    product_id: str | None
    purchase_count: int = Field(..., description="Number of times purchased")
    avg_price: int = Field(..., description="Average price in cents")
    price_trend: Literal["stable", "rising", "falling", "insufficient_data"]
    price_direction: Literal["↑", "↓", "→", "?"]
    category: str


class InsightsResponse(BaseModel):
    """Response body for GET /api/v1/insights."""
    month_total: int
    month_trend: list[MonthTrendPoint]
    collections: list[CollectionSummary]
    product_history: list[ProductHistory]


class MerchantComparison(BaseModel):
    """One merchant in rivalry comparison."""
    merchant: str = Field(..., description="Merchant code")
    price: int = Field(..., description="Price for identical basket in cents")
    pack_size: str | None
    confidence: Literal["confirmed", "estimated"]
    purchase_date: date | None
    wins_on: list[str] = Field(..., description="Competitive advantages (e.g., 'open till 9pm')")
    distance_km: float | None = Field(None, description="Distance from home in km")
    hourly_cost: float | None = Field(
        None,
        description="Cost per hour of driving (in dollars)"
    )


class RivalsResponse(BaseModel):
    """Response body for GET /api/v1/rivals/{product_id}."""
    product: dict[str, str] = Field(
        ...,
        description="Product: {id, name, category}"
    )
    your_basket_spread: int = Field(..., description="Price range in cents")
    merchants: list[MerchantComparison]
    verdict: str = Field(..., description="Human-readable verdict")


# ============================================================================
# Collections
# ============================================================================


class CollectionCreateRequest(BaseModel):
    """Request body for POST /api/v1/collections."""
    name: str = Field(..., min_length=1, description="Collection name")
    icon: str = Field(..., description="Emoji icon")


class CollectionResponse(BaseModel):
    """Collection in list response."""
    id: str
    name: str
    icon: str
    month_total: int = Field(..., description="This month's total in cents")
    receipt_count: int
    month_delta_percent: float | None


class CollectionsListResponse(BaseModel):
    """Response body for GET /api/v1/collections."""
    items: list[CollectionResponse]


# ============================================================================
# Backup
# ============================================================================


class CreateBackupResponse(BaseModel):
    """Response body for POST /api/v1/backup."""
    job_id: str
    status: Literal["in_progress", "complete"]
    expires_at: datetime = Field(..., description="When backup archive expires")


class BackupStatusResponse(BaseModel):
    """Response body for GET /api/v1/backup/{job_id}."""
    job_id: str
    status: Literal["in_progress", "complete", "failed"]
    progress_percent: int | None = Field(None, ge=0, le=100)
    error: str | None = None


__all__ = [
    "AddShoppingItemRequest",
    "ApiError",
    "ApiResponse",
    "BackupStatusResponse",
    "BootstrapData",
    "BootstrapSettings",
    "CollectionCreateRequest",
    "CollectionResponse",
    "CollectionSummary",
    "CollectionsListResponse",
    "CreateBackupResponse",
    "CreateReceiptRequest",
    "CreateReceiptResponse",
    "HouseholdInfo",
    "InsightsResponse",
    "LineItemResponse",
    "MerchantComparison",
    "MonthTrendPoint",
    "PinAuthRequest",
    "PriceQuote",
    "PriceVerdict",
    "ProcessingStage",
    "ReceiptBalance",
    "ReceiptDetailResponse",
    "ReceiptImageUrl",
    "ReceiptItemResponse",
    "ReceiptListResponse",
    "RivalsResponse",
    "SessionTokenData",
    "SettingsData",
    "ShoppingItemResponse",
    "ShoppingListResponse",
    "ShoppingStatusEnum",
    "StatusEnum",
    "TotalsData",
    "UpdateReceiptRequest",
    "UpdateReceiptResponse",
    "UpdateSettingsRequest",
    "UpdateShoppingItemRequest",
    "UploadStatusResponse",
    "UploadUrl",
]
