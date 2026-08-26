"""Receipt upload validation, private storage, and parser orchestration."""

from __future__ import annotations

import hashlib
import io
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO, Protocol, Sequence

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from grocery_home.ocr import (
    OCRAdapter,
    OCRReceipt,
    RapidOCRAdapter,
    detect_merchant,
    normalize_image,
    parse_detected_receipt,
    parse_ocr_receipt,
)
from grocery_home.detection import ReceiptRegionDetector, YOLOReceiptDetector


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PHOTOS_PER_RECEIPT = 5
MAX_PDF_PAGES = 10
MAX_IMAGE_PIXELS = 50_000_000
MIN_IMAGE_EDGE = 32
PHOTO_KINDS = frozenset({"jpeg", "png", "webp", "heic"})
SUPPORTED_KINDS = PHOTO_KINDS | {"pdf"}
STATUS_QUEUED = "queued"
STATUS_EXTRACTING = "extracting"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_COMPLETE = "complete"
STATUS_DUPLICATE = "duplicate"
STATUS_FAILED = "failed"


class UploadValidationError(ValueError):
    """A safe, user-facing upload validation error."""


class ReceiptExtractionError(RuntimeError):
    """An upload was valid, but receipt extraction could not complete."""


class UploadLike(Protocol):
    filename: str | None
    file: BinaryIO


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    original_filename: str
    media_kind: str
    media_type: str
    byte_size: int
    sha256: str
    data: bytes
    page_count: int = 1
    width: int | None = None
    height: int | None = None
    has_extractable_text: bool = False


@dataclass(frozen=True, slots=True)
class StoredUpload:
    original_filename: str
    storage_name: str
    path: Path
    media_kind: str
    media_type: str
    byte_size: int
    sha256: str
    page_count: int
    has_extractable_text: bool


@dataclass(slots=True)
class ReceiptItemData:
    line_number: int
    description: str
    quantity: Decimal
    quantity_unit: str
    unit_price_cents: int | None
    line_total_cents: int
    taxable: bool = False
    promotional: bool = False
    price_reduced: bool = False
    product_number: str | None = None
    confidence: float | None = None


@dataclass(slots=True)
class ParsedReceiptData:
    merchant: str
    store_name: str | None
    store_number: str | None
    purchase_date: date | None
    purchase_time: str | None
    pos: str | None
    transaction_number: str | None
    subtotal_cents: int | None
    total_cents: int | None
    gst_cents: int | None
    savings_cents: int | None
    is_grocery: bool
    status: str
    item_count_reported: int | None = None
    confidence: float | None = None
    items: list[ReceiptItemData] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None
    parser_name: str = "generic"

    @property
    def is_balanced(self) -> bool:
        if not self.items:
            return False
        expected = (
            self.subtotal_cents
            if self.subtotal_cents is not None
            else self.total_cents
        )
        if expected is None:
            return False
        return sum(item.line_total_cents for item in self.items) == expected


# Public domain terms used by route/service code.
ParsedReceipt = ParsedReceiptData
ReceiptItem = ReceiptItemData


_MEDIA_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
    "pdf": "application/pdf",
}
_EXTENSIONS = {
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
    "heic": ".heic",
    "pdf": ".pdf",
}


def validate_upload_batch(
    uploads: Sequence[UploadLike | tuple[str, bytes] | bytes],
) -> list[ValidatedUpload]:
    """Read and validate one logical receipt without writing it to disk."""

    if not uploads:
        raise UploadValidationError("Choose at least one receipt file.")
    validated = [_read_and_validate(upload, index) for index, upload in enumerate(uploads)]
    kinds = {entry.media_kind for entry in validated}
    if "pdf" in kinds and len(validated) != 1:
        raise UploadValidationError(
            "Upload one PDF, or up to five receipt photos—not a mixture."
        )
    if kinds <= PHOTO_KINDS and len(validated) > MAX_PHOTOS_PER_RECEIPT:
        raise UploadValidationError(
            f"A receipt can contain at most {MAX_PHOTOS_PER_RECEIPT} photos."
        )
    return validated


def store_validated_uploads(
    uploads: Sequence[ValidatedUpload], storage_dir: Path
) -> list[StoredUpload]:
    """Atomically save validated originals under generated names.

    The storage location is explicitly rejected when it sits in a web ``static``
    tree.  Files are never addressed by the client-provided filename.
    """

    storage_dir = Path(storage_dir).expanduser().resolve()
    if any(part.casefold() == "static" for part in storage_dir.parts):
        raise ValueError("Raw receipts must not be stored under a static directory.")
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored: list[StoredUpload] = []
    created: list[Path] = []
    try:
        for upload in uploads:
            storage_name = f"{uuid.uuid4().hex}{_EXTENSIONS[upload.media_kind]}"
            destination = storage_dir / storage_name
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=storage_dir, prefix=".upload-", delete=False
            ) as handle:
                handle.write(upload.data)
                temporary = Path(handle.name)
            temporary.replace(destination)
            created.append(destination)
            stored.append(
                StoredUpload(
                    original_filename=upload.original_filename,
                    storage_name=storage_name,
                    path=destination,
                    media_kind=upload.media_kind,
                    media_type=upload.media_type,
                    byte_size=upload.byte_size,
                    sha256=upload.sha256,
                    page_count=upload.page_count,
                    has_extractable_text=upload.has_extractable_text,
                )
            )
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return stored


def validate_and_store_uploads(
    uploads: Sequence[UploadLike | tuple[str, bytes] | bytes],
    storage_dir: Path,
) -> list[StoredUpload]:
    return store_validated_uploads(validate_upload_batch(uploads), storage_dir)


def find_exact_duplicate(
    session: object,
    sha256: str,
    *,
    household_id: int | None = None,
) -> object | None:
    """Find an existing upload by hash without coupling callers to query syntax.

    Scoped to one household when given. A hash matched across households links
    this household's receipt to another household's row, and the duplicate path
    copies that row's merchant and totals — so an unscoped match is a way for
    one tenant's figures to surface inside another tenant's ledger.
    """

    from sqlalchemy import select

    from grocery_home.models import UploadFile

    query = select(UploadFile).where(
        UploadFile.content_sha256 == sha256,
        UploadFile.duplicate_of_id.is_(None),
    )
    if household_id is not None:
        query = query.where(UploadFile.household_id == household_id)
    return session.scalar(query)


def extract_stored_receipt(
    uploads: Sequence[StoredUpload],
    *,
    ocr_adapter: OCRAdapter | None = None,
    region_detector: ReceiptRegionDetector | None = None,
) -> ParsedReceiptData:
    """Parse one text PDF or one-to-five receipt images.

    Text PDFs that cleanly balance can complete automatically.  Every
    camera/scanned input remains ``needs_review`` regardless of OCR confidence.
    """

    if not uploads:
        raise ReceiptExtractionError("The upload contains no stored files.")
    if uploads[0].media_kind == "pdf" and uploads[0].has_extractable_text:
        return _parse_text_pdf(uploads[0].path)

    adapter = ocr_adapter or RapidOCRAdapter()
    images: list[Image.Image] = []
    used_regions = False
    try:
        for upload in uploads:
            if upload.media_kind == "pdf":
                images.extend(_render_pdf(upload.path))
            else:
                with Image.open(upload.path) as image:
                    images.append(normalize_image(image).copy())
        if len(images) == 1:
            image = images[0]
            detector = region_detector
            if detector is None and ocr_adapter is None:
                default_detector = YOLOReceiptDetector()
                detector = default_detector if default_detector.available else None
            try:
                regions = detector.detect(image) if detector is not None else []
            except Exception:
                # Detection is an accuracy enhancement. A missing/incompatible
                # model must never prevent the established OCR fallback.
                regions = []
            whole = adapter.read(image)
            receipt = (
                parse_detected_receipt(image, adapter, regions, whole_result=whole)
                if regions else parse_ocr_receipt(whole)
            )
            used_regions = bool(regions)
        else:
            lines = []
            for image in images:
                lines.extend(adapter.read(image).lines)
            receipt = parse_ocr_receipt(lines)
    except ReceiptExtractionError:
        raise
    except Exception as exc:
        raise ReceiptExtractionError(f"Local OCR failed: {exc}") from exc
    finally:
        for image in images:
            image.close()
    parsed = _from_ocr(receipt)
    if used_regions:
        parsed.parser_name = "yolov8n_regions+rapidocr"
    return parsed


def _batch_household_id(batch: object) -> int:
    """Which household owns an upload batch, defaulting to the first one.

    Rows that predate tenancy carry no value, and for those the original single
    household is the right answer rather than "no household".
    """

    return getattr(batch, "household_id", None) or 1


def transaction_identity(parsed: ParsedReceiptData) -> tuple[object, ...] | None:
    """Stable semantic identity used after file-hash deduplication."""

    if (
        not parsed.merchant
        or parsed.purchase_date is None
        or not parsed.transaction_number
        or parsed.total_cents is None
    ):
        return None
    return (
        parsed.merchant.casefold(),
        parsed.purchase_date,
        parsed.transaction_number.casefold(),
        parsed.total_cents,
    )


def find_transaction_duplicate(
    session: object,
    parsed: ParsedReceiptData,
    *,
    household_id: int | None = None,
) -> object | None:
    """Find the same transaction already filed, within one household."""

    from sqlalchemy import func, select

    from grocery_home.models import Receipt

    identity = transaction_identity(parsed)
    if identity is None:
        return None
    merchant, purchase_date, transaction_number, total_cents = identity
    query = select(Receipt).where(
        func.lower(Receipt.merchant_name) == merchant,
        Receipt.purchase_date == purchase_date,
        func.lower(Receipt.transaction_number) == transaction_number,
        Receipt.total_cents == total_cents,
        Receipt.duplicate_of_id.is_(None),
    )
    if household_id is not None:
        query = query.where(Receipt.household_id == household_id)
    return session.scalar(query)


def create_upload_batch(
    session: object,
    uploads: Sequence[StoredUpload],
    *,
    source: str = "web",
    household_id: int = 1,
) -> object:
    """Persist a validated logical receipt and its privately stored files.

    Exact hash matches are linked before the first flush so the database's
    canonical-hash uniqueness rule remains race-safe and auditable.

    The batch has to carry the household that uploaded it. Left on the default,
    every upload landed in household 1: the reading screen polled a batch its
    own household could not see and reported the batch as not found, and the
    receipt that came out of it was filed into a household the person who
    photographed it is not a member of.
    """

    if not uploads:
        raise ValueError("Cannot create an empty upload batch.")
    from grocery_home.models import (
        ProcessingStatus,
        UploadBatch,
        UploadFile,
        UploadSource,
        new_id,
    )

    source_value = UploadSource(source)
    batch = UploadBatch(
        id=new_id(),
        household_id=household_id,
        status=ProcessingStatus.QUEUED,
        source=source_value,
        total_files=len(uploads),
        processed_files=0,
    )
    session.add(batch)
    seen_in_batch: dict[str, object] = {}
    for ordinal, stored in enumerate(uploads, start=1):
        duplicate = seen_in_batch.get(stored.sha256)
        if duplicate is None:
            duplicate = find_exact_duplicate(
                session, stored.sha256, household_id=household_id
            )
        upload_file = UploadFile(
            id=new_id(),
            household_id=household_id,
            batch_id=batch.id,
            ordinal=ordinal,
            original_filename=stored.original_filename,
            storage_key=stored.storage_name,
            media_type=stored.media_type,
            file_size=stored.byte_size,
            content_sha256=stored.sha256,
            page_count=stored.page_count,
            status=(
                ProcessingStatus.DUPLICATE
                if duplicate is not None
                else ProcessingStatus.QUEUED
            ),
            duplicate_of_id=getattr(duplicate, "id", None),
        )
        session.add(upload_file)
        batch.files.append(upload_file)
        if duplicate is None:
            seen_in_batch[stored.sha256] = upload_file
    session.flush()
    return batch


def persist_parsed_receipt(
    session: object,
    batch: object,
    parsed: ParsedReceiptData,
    *,
    source_kind: str,
) -> object:
    """Create a receipt/items result and apply transaction-level deduplication."""

    from datetime import UTC, datetime

    from sqlalchemy import select

    from grocery_home.models import (
        ProcessingStatus,
        Receipt,
        ReceiptItem,
        ReceiptSource,
        make_receipt_natural_key,
        new_id,
        normalize_key_part,
    )

    files = sorted(batch.files, key=lambda entry: entry.ordinal)
    if not files:
        raise ReceiptExtractionError("The upload batch has no files.")
    primary = next(
        (entry for entry in files if entry.duplicate_of_id is None),
        files[0],
    )
    existing_for_upload = session.scalar(
        select(Receipt).where(Receipt.upload_file_id == primary.id)
    )
    if existing_for_upload is not None:
        return existing_for_upload

    household_id = _batch_household_id(batch)
    duplicate = find_transaction_duplicate(
        session, parsed, household_id=household_id
    )
    merchant_key = _merchant_key(parsed.merchant)
    natural_key = make_receipt_natural_key(
        merchant=merchant_key,
        purchase_date=parsed.purchase_date,
        transaction_number=parsed.transaction_number,
        total_cents=parsed.total_cents,
        store_number=parsed.store_number,
        pos_number=parsed.pos,
    )
    status = (
        ProcessingStatus.DUPLICATE
        if duplicate is not None
        else ProcessingStatus(parsed.status)
    )
    confidence = (
        Decimal(str(round(parsed.confidence, 4)))
        if parsed.confidence is not None
        else (Decimal("1.0000") if parsed.parser_name == "woolworths_pdf" else None)
    )
    receipt = Receipt(
        id=new_id(),
        household_id=household_id,
        upload_file_id=primary.id,
        merchant_key=merchant_key,
        merchant_name=parsed.merchant,
        store_number=parsed.store_number,
        store_name=parsed.store_name,
        purchase_date=parsed.purchase_date,
        purchase_time=_parse_time_value(parsed.purchase_time),
        timezone="Australia/Sydney",
        transaction_number=parsed.transaction_number,
        pos_number=parsed.pos,
        subtotal_cents=parsed.subtotal_cents,
        total_cents=parsed.total_cents,
        gst_cents=parsed.gst_cents,
        savings_cents=parsed.savings_cents,
        item_count_reported=parsed.item_count_reported,
        is_grocery=parsed.is_grocery,
        status=status,
        source_kind=ReceiptSource(source_kind),
        parse_confidence=confidence,
        natural_key=natural_key,
        duplicate_of_id=getattr(duplicate, "id", None),
        confirmed_at=(
            datetime.now(UTC)
            if status == ProcessingStatus.COMPLETE
            else None
        ),
    )
    session.add(receipt)

    if duplicate is None:
        for item in parsed.items:
            normalized = normalize_key_part(item.description)
            product_key = (
                f"sku:{item.product_number}"
                if item.product_number
                else f"name:{normalized}"
            )
            try:
                from categorize import categorize

                category = categorize(item.description)
            except ImportError:
                category = "Uncategorised"
            item_confidence = (
                Decimal(str(round(item.confidence, 4)))
                if item.confidence is not None
                else confidence
            )
            session.add(
                ReceiptItem(
                    id=new_id(),
                    receipt_id=receipt.id,
                    line_number=item.line_number,
                    description=item.description,
                    normalized_description=normalized,
                    product_key=product_key,
                    product_number=item.product_number,
                    category=category,
                    quantity=item.quantity,
                    quantity_unit=item.quantity_unit,
                    unit_price_cents=item.unit_price_cents,
                    line_total_cents=item.line_total_cents,
                    taxable=item.taxable,
                    promotional=item.promotional,
                    price_reduced=item.price_reduced,
                    confidence=item_confidence,
                    needs_review=(
                        status == ProcessingStatus.NEEDS_REVIEW
                        or (item.confidence is not None and item.confidence < 0.72)
                    ),
                )
            )
    else:
        canonical_upload_id = getattr(duplicate, "upload_file_id", None)
        for upload_file in files:
            upload_file.status = ProcessingStatus.DUPLICATE
            if upload_file.duplicate_of_id is None and canonical_upload_id:
                upload_file.duplicate_of_id = canonical_upload_id

    for upload_file in files:
        if status != ProcessingStatus.DUPLICATE:
            upload_file.status = status
    batch.status = status
    batch.processed_files = batch.total_files
    batch.completed_at = (
        datetime.now(UTC)
        if status in {ProcessingStatus.COMPLETE, ProcessingStatus.DUPLICATE}
        else None
    )
    session.flush()
    return receipt


def process_upload_batch(
    session: object,
    batch_id: str,
    *,
    storage_dir: Path,
    ocr_adapter: OCRAdapter | None = None,
) -> object:
    """Extract and persist one queued batch; safe to call again after success."""

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from grocery_home.models import (
        ProcessingStatus,
        Receipt,
        ReceiptSource,
        UploadBatch,
        UploadFile,
    )

    batch = session.scalar(
        select(UploadBatch)
        .where(UploadBatch.id == batch_id)
        .options(selectinload(UploadBatch.files))
    )
    if batch is None:
        raise ReceiptExtractionError(f"Upload batch {batch_id} does not exist.")
    file_ids = [entry.id for entry in batch.files]
    existing = session.scalar(
        select(Receipt).where(Receipt.upload_file_id.in_(file_ids))
    )
    if existing is not None:
        return existing

    files = sorted(batch.files, key=lambda entry: entry.ordinal)
    batch.status = ProcessingStatus.EXTRACTING
    for upload_file in files:
        if upload_file.status != ProcessingStatus.DUPLICATE:
            upload_file.status = ProcessingStatus.EXTRACTING
    session.flush()

    # A repeated single-file upload can be recorded without rerunning OCR.
    if files and all(entry.duplicate_of_id for entry in files):
        canonical = session.scalar(
            select(Receipt)
            .join(UploadFile, Receipt.upload_file_id == UploadFile.id)
            .where(
                UploadFile.id.in_([entry.duplicate_of_id for entry in files]),
                Receipt.duplicate_of_id.is_(None),
                Receipt.household_id == _batch_household_id(batch),
            )
        )
        if canonical is not None:
            return _persist_exact_duplicate(session, batch, files[0], canonical)
        # A file can be the second or later photo in an older multi-photo
        # batch.  Only that batch's primary file owns its Receipt row, so the
        # hash match above cannot safely identify a canonical receipt for this
        # individual image.  OCR the newly stored copy normally instead of
        # treating it as an unavailable duplicate and creating a blank review.

    stored = [
        _stored_from_upload_file(entry, Path(storage_dir))
        for entry in files
    ]
    parsed = extract_stored_receipt(stored, ocr_adapter=ocr_adapter)
    if stored[0].media_kind == "pdf":
        source_kind = (
            ReceiptSource.TEXT_PDF.value
            if stored[0].has_extractable_text
            else ReceiptSource.SCANNED_PDF.value
        )
    else:
        source_kind = ReceiptSource.IMAGE.value
    return persist_parsed_receipt(
        session,
        batch,
        parsed,
        source_kind=source_kind,
    )


def make_receipt_extraction_handler(
    storage_dir: Path,
    *,
    ocr_adapter: OCRAdapter | None = None,
):
    """Return a ``SingleWorker`` handler for ``receipt_extract`` jobs."""

    private_dir = Path(storage_dir)

    def handler(session: object, payload: dict[str, object]) -> None:
        batch_id = str(payload.get("batch_id") or "")
        if not batch_id:
            raise ReceiptExtractionError("Receipt extraction job has no batch_id.")
        process_upload_batch(
            session,
            batch_id,
            storage_dir=private_dir,
            ocr_adapter=ocr_adapter,
        )

    return handler


def _persist_exact_duplicate(
    session: object,
    batch: object,
    primary_upload: object,
    canonical: object,
) -> object:
    from datetime import UTC, datetime

    from grocery_home.models import ProcessingStatus, Receipt, new_id

    duplicate = Receipt(
        id=new_id(),
        household_id=_batch_household_id(batch),
        upload_file_id=primary_upload.id,
        merchant_key=canonical.merchant_key,
        merchant_name=canonical.merchant_name,
        store_number=canonical.store_number,
        store_name=canonical.store_name,
        purchase_date=canonical.purchase_date,
        purchase_time=canonical.purchase_time,
        timezone=canonical.timezone,
        transaction_number=canonical.transaction_number,
        pos_number=canonical.pos_number,
        subtotal_cents=canonical.subtotal_cents,
        total_cents=canonical.total_cents,
        gst_cents=canonical.gst_cents,
        savings_cents=canonical.savings_cents,
        item_count_reported=canonical.item_count_reported or len(canonical.items),
        is_grocery=canonical.is_grocery,
        status=ProcessingStatus.DUPLICATE,
        source_kind=canonical.source_kind,
        parse_confidence=canonical.parse_confidence,
        natural_key=canonical.natural_key,
        duplicate_of_id=canonical.id,
        confirmed_at=None,
    )
    session.add(duplicate)
    for upload_file in batch.files:
        upload_file.status = ProcessingStatus.DUPLICATE
    batch.status = ProcessingStatus.DUPLICATE
    batch.processed_files = batch.total_files
    batch.completed_at = datetime.now(UTC)
    session.flush()
    return duplicate


def _stored_from_upload_file(upload_file: object, storage_dir: Path) -> StoredUpload:
    storage_dir = Path(storage_dir).resolve()
    path = (storage_dir / upload_file.storage_key).resolve()
    if not path.is_relative_to(storage_dir):
        raise ReceiptExtractionError("An upload has an unsafe storage key.")
    if not path.is_file():
        raise ReceiptExtractionError(
            f"Stored receipt {upload_file.storage_key} is missing."
        )
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != upload_file.content_sha256:
        raise ReceiptExtractionError(
            f"Stored receipt {upload_file.storage_key} failed its integrity check."
        )
    kind = sniff_media_kind(data)
    if kind is None:
        raise ReceiptExtractionError(
            f"Stored receipt {upload_file.storage_key} has an unsupported format."
        )
    if kind == "pdf":
        page_count, has_text = _validate_pdf(data, upload_file.original_filename)
    else:
        _validate_image(data, upload_file.original_filename, kind)
        page_count, has_text = 1, False
    return StoredUpload(
        original_filename=upload_file.original_filename,
        storage_name=upload_file.storage_key,
        path=path,
        media_kind=kind,
        media_type=_MEDIA_TYPES[kind],
        byte_size=len(data),
        sha256=digest,
        page_count=page_count,
        has_extractable_text=has_text,
    )


def _merchant_key(merchant: str) -> str:
    return {
        "woolworths": "woolworths",
        "big w": "big_w",
        "coles": "coles",
        "aldi": "aldi",
        "iga": "iga",
    }.get(merchant.strip().casefold(), "other")


def _parse_time_value(value: str | None):
    from datetime import time

    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def _read_and_validate(
    upload: UploadLike | tuple[str, bytes] | bytes, index: int
) -> ValidatedUpload:
    filename, data = _read_upload(upload, index)
    if not data:
        raise UploadValidationError(f"{filename} is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise UploadValidationError(f"{filename} is larger than 20 MB.")
    kind = sniff_media_kind(data)
    if kind is None:
        raise UploadValidationError(
            f"{filename} is not a supported JPEG, PNG, WebP, HEIC, or PDF."
        )
    digest = hashlib.sha256(data).hexdigest()
    if kind == "pdf":
        page_count, has_text = _validate_pdf(data, filename)
        return ValidatedUpload(
            filename,
            kind,
            _MEDIA_TYPES[kind],
            len(data),
            digest,
            data,
            page_count=page_count,
            has_extractable_text=has_text,
        )
    width, height = _validate_image(data, filename, kind)
    return ValidatedUpload(
        filename,
        kind,
        _MEDIA_TYPES[kind],
        len(data),
        digest,
        data,
        width=width,
        height=height,
    )


def _read_upload(
    upload: UploadLike | tuple[str, bytes] | bytes, index: int
) -> tuple[str, bytes]:
    if isinstance(upload, bytes):
        return f"receipt-{index + 1}", upload
    if isinstance(upload, tuple):
        filename, data = upload
        return Path(filename).name or f"receipt-{index + 1}", bytes(data)
    filename = Path(upload.filename or f"receipt-{index + 1}").name
    stream = upload.file
    try:
        stream.seek(0)
    except (AttributeError, OSError):
        pass
    # Read one byte beyond the ceiling to reject before retaining huge payloads.
    data = stream.read(MAX_FILE_BYTES + 1)
    return filename, data


def sniff_media_kind(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12].lower()
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return "heic"
    return None


def _validate_image(data: bytes, filename: str, kind: str) -> tuple[int, int]:
    try:
        if kind == "heic":
            _register_heif()
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            detected = (image.format or "").upper()
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        SyntaxError,
    ) as exc:
        raise UploadValidationError(f"{filename} is not a valid {kind.upper()} image.") from exc
    expected = {
        "jpeg": {"JPEG"},
        "png": {"PNG"},
        "webp": {"WEBP"},
        "heic": {"HEIF", "HEIC"},
    }[kind]
    if detected not in expected:
        raise UploadValidationError(
            f"{filename}'s content does not match its detected file type."
        )
    if min(width, height) < MIN_IMAGE_EDGE:
        raise UploadValidationError(f"{filename} is too small to read as a receipt.")
    if width * height > MAX_IMAGE_PIXELS:
        raise UploadValidationError(f"{filename} has excessively large dimensions.")
    return width, height


def _register_heif() -> None:
    try:
        from pillow_heif import register_heif_opener  # type: ignore[import-not-found]

        register_heif_opener()
    except ImportError as exc:
        raise UploadValidationError(
            "HEIC support is not installed on this Grocery Home host."
        ) from exc


def _validate_pdf(data: bytes, filename: str) -> tuple[int, bool]:
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception:
                unlocked = 0
            if not unlocked:
                raise UploadValidationError(
                    f"{filename} is password protected and cannot be read."
                )
        page_count = len(reader.pages)
        if not 1 <= page_count <= MAX_PDF_PAGES:
            raise UploadValidationError(
                f"A receipt PDF must contain 1–{MAX_PDF_PAGES} pages."
            )
        extracted = "\n".join((page.extract_text() or "") for page in reader.pages)
    except UploadValidationError:
        raise
    except Exception as exc:
        raise UploadValidationError(f"{filename} is not a valid PDF.") from exc
    # A few characters such as a page number do not make a scan a text receipt.
    has_text = len(re.sub(r"\s+", "", extracted)) >= 40
    return page_count, has_text


def _parse_text_pdf(path: Path) -> ParsedReceiptData:
    try:
        from parse_receipts import parse_pdf

        receipt, items = parse_pdf(path)
        reader = PdfReader(path)
        raw_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ReceiptExtractionError(f"The receipt PDF could not be parsed: {exc}") from exc
    merchant = detect_merchant(f"{receipt.store_name}\n{raw_text}")
    if merchant == "Other" and not receipt.store_name.upper().startswith("BIG W"):
        merchant = "Woolworths"
    parsed_items = [
        ReceiptItemData(
            line_number=item.line_number,
            description=item.description,
            quantity=_decimal(item.quantity, Decimal("1")),
            quantity_unit=item.quantity_unit or "each",
            unit_price_cents=_cents(item.unit_price),
            line_total_cents=_cents(item.line_total) or 0,
            taxable=bool(item.taxable),
            promotional=bool(item.promotional),
            price_reduced=bool(item.price_reduced),
            product_number=item.product_number or None,
        )
        for item in items
    ]
    warnings = [
        part.strip()
        for part in receipt.warnings.split(";")
        if part.strip() and part.strip() != "filename did not match expected pattern"
    ]
    parsed = ParsedReceiptData(
        merchant=merchant,
        store_name=receipt.store_name or None,
        store_number=receipt.store_number or None,
        purchase_date=date.fromisoformat(receipt.purchase_date)
        if receipt.purchase_date
        else None,
        purchase_time=receipt.purchase_time or None,
        pos=receipt.pos or None,
        transaction_number=receipt.transaction_number or None,
        subtotal_cents=_cents(receipt.subtotal),
        total_cents=_cents(receipt.total),
        gst_cents=_cents(receipt.gst),
        savings_cents=_cents(receipt.savings),
        is_grocery=merchant != "BIG W",
        status=STATUS_NEEDS_REVIEW,
        item_count_reported=(
            int(Decimal(receipt.item_count_reported))
            if receipt.item_count_reported
            else None
        ),
        confidence=1.0 if not warnings else 0.9,
        items=parsed_items,
        warnings=warnings,
        raw_text=raw_text,
        parser_name="woolworths_pdf",
    )
    if (
        parsed.is_balanced
        and not warnings
        and parsed.purchase_date is not None
        and parsed.total_cents is not None
        and parsed.merchant != "Other"
    ):
        parsed.status = STATUS_COMPLETE
    return parsed


def _from_ocr(receipt: OCRReceipt) -> ParsedReceiptData:
    return ParsedReceiptData(
        merchant=receipt.merchant,
        store_name=None,
        store_number=None,
        purchase_date=receipt.purchase_date,
        purchase_time=receipt.purchase_time,
        pos=None,
        transaction_number=receipt.transaction_number,
        subtotal_cents=receipt.subtotal_cents,
        total_cents=receipt.total_cents,
        gst_cents=receipt.gst_cents,
        savings_cents=None,
        is_grocery=receipt.merchant != "BIG W",
        status=STATUS_NEEDS_REVIEW,
        confidence=receipt.confidence,
        items=[
            ReceiptItemData(
                line_number=index,
                description=item.description,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                unit_price_cents=item.unit_price_cents,
                line_total_cents=item.line_total_cents,
                confidence=item.confidence,
            )
            for index, item in enumerate(receipt.items, start=1)
        ],
        warnings=list(receipt.warnings),
        raw_text=receipt.raw_text,
        parser_name="rapidocr_generic",
    )


def _render_pdf(path: Path) -> list[Image.Image]:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ReceiptExtractionError(
            "Scanned PDF support is not installed on this Grocery Home host."
        ) from exc
    try:
        document = pdfium.PdfDocument(str(path))
        images = [
            page.render(scale=2.0).to_pil().convert("RGB")
            for page in document
        ]
        document.close()
        return images
    except Exception as exc:
        raise ReceiptExtractionError(f"The scanned PDF could not be rendered: {exc}") from exc


def _cents(value: str | Decimal | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int((Decimal(str(value).replace(",", "")) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def _decimal(value: str | Decimal | None, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return default
