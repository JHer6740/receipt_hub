"""Idempotent migration of the existing eReceipt archive into Grocery Home."""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from grocery_home.ingestion import STATUS_DUPLICATE
from grocery_home.models import (
    ProcessingStatus,
    Receipt,
    ReceiptItem,
    ReceiptSource,
    UploadBatch,
    UploadFile,
    UploadSource,
    make_receipt_natural_key,
    new_id,
)


LEGACY_IMPORT_SOURCE = UploadSource.IMPORT
EXPECTED_UPLOADS = 103
EXPECTED_CANONICAL_RECEIPTS = 100
EXPECTED_DUPLICATES = 3
EXPECTED_ITEMS = 752


class LegacyImportError(RuntimeError):
    """Raised before committing an incomplete or inconsistent legacy import."""


@dataclass(frozen=True, slots=True)
class ImportSummary:
    batch_id: str
    uploads: int
    canonical_receipts: int
    duplicate_receipts: int
    items: int
    files_copied: int
    already_imported: bool


def import_existing(
    session: Session,
    *,
    source_dir: Path,
    receipts_csv: Path,
    items_csv: Path,
    storage_dir: Path,
    verify_expected_counts: bool = True,
) -> ImportSummary:
    """Copy and import the legacy archive in one database transaction.

    The function never modifies source PDFs or CSVs.  Managed filenames use a
    deterministic UUID derived from the source name and digest, which makes a
    retry safe even if a prior process stopped after copying but before commit.
    The caller owns the outer commit.
    """

    source_dir = Path(source_dir).resolve()
    receipts_csv = Path(receipts_csv).resolve()
    items_csv = Path(items_csv).resolve()
    storage_dir = Path(storage_dir).resolve()
    _assert_private_storage(storage_dir)
    if storage_dir == source_dir or storage_dir.is_relative_to(source_dir):
        raise LegacyImportError(
            "Managed storage must be outside the legacy receipt directory."
        )
    receipt_rows = _read_csv(receipts_csv)
    item_rows = _read_csv(items_csv)
    _validate_archive(
        source_dir,
        receipt_rows,
        item_rows,
        verify_expected_counts=verify_expected_counts,
    )

    existing = session.scalar(
        select(UploadBatch)
        .where(UploadBatch.source == LEGACY_IMPORT_SOURCE)
        .order_by(UploadBatch.created_at)
    )
    if existing is not None:
        files_copied = _repair_managed_files(
            session, existing, source_dir=source_dir, storage_dir=storage_dir
        )
        summary = _summarize(
            session,
            existing,
            files_copied=files_copied,
            already_imported=True,
        )
        _verify_summary(summary, verify_expected_counts)
        return summary

    copied_paths: list[Path] = []
    try:
        with session.begin_nested():
            batch = UploadBatch(
                id=new_id(),
                status=ProcessingStatus.EXTRACTING,
                source=LEGACY_IMPORT_SOURCE,
                total_files=len(receipt_rows),
                processed_files=0,
            )
            session.add(batch)
            session.flush()

            uploads_by_filename: dict[str, UploadFile] = {}
            receipt_by_legacy_id: dict[str, Receipt] = {}
            receipt_rows_by_id: dict[str, Mapping[str, str]] = {}
            duplicate_rows: list[Mapping[str, str]] = []

            storage_dir.mkdir(parents=True, exist_ok=True)
            for ordinal, row in enumerate(receipt_rows, start=1):
                source_path = source_dir / row["filename"]
                digest = _sha256_file(source_path)
                storage_key = _legacy_storage_key(row["filename"], digest)
                destination = storage_dir / storage_key
                if not destination.exists():
                    _copy_verified(source_path, destination, digest)
                    copied_paths.append(destination)

                is_duplicate = row.get("parse_status") == STATUS_DUPLICATE
                upload = UploadFile(
                    id=new_id(),
                    batch_id=batch.id,
                    ordinal=ordinal,
                    original_filename=row["filename"],
                    storage_key=storage_key,
                    media_type="application/pdf",
                    file_size=source_path.stat().st_size,
                    content_sha256=digest,
                    page_count=_pdf_page_count(source_path),
                    status=(
                        ProcessingStatus.DUPLICATE
                        if is_duplicate
                        else ProcessingStatus.COMPLETE
                    ),
                )
                session.add(upload)
                uploads_by_filename[row["filename"]] = upload
                if is_duplicate:
                    duplicate_rows.append(row)
                    continue
                receipt = _receipt_from_row(row, upload.id)
                session.add(receipt)
                receipt_by_legacy_id[row["receipt_id"]] = receipt
                receipt_rows_by_id[row["receipt_id"]] = row

            # Duplicate CSV rows reuse the same legacy receipt_id as their
            # canonical transaction.  Both raw uploads and receipt audit rows
            # explicitly point back to that canonical record.
            for row in duplicate_rows:
                original_name = _duplicate_original_filename(row)
                canonical_upload = uploads_by_filename.get(original_name)
                canonical_receipt = receipt_by_legacy_id.get(row["receipt_id"])
                if canonical_upload is None or canonical_receipt is None:
                    raise LegacyImportError(
                        f"Duplicate {row['filename']} has no canonical source."
                    )
                duplicate_upload = uploads_by_filename[row["filename"]]
                duplicate_upload.duplicate_of_id = canonical_upload.id
                duplicate_receipt = _receipt_from_row(
                    row,
                    duplicate_upload.id,
                    duplicate_of_id=canonical_receipt.id,
                )
                session.add(duplicate_receipt)

            session.flush()
            for row in item_rows:
                receipt = receipt_by_legacy_id.get(row["receipt_id"])
                if receipt is None:
                    raise LegacyImportError(
                        f"Item references unknown canonical receipt {row['receipt_id']}."
                    )
                session.add(_item_from_row(row, receipt.id))

            batch.processed_files = len(receipt_rows)
            batch.status = ProcessingStatus.COMPLETE
            batch.completed_at = datetime.now(timezone.utc)
            session.flush()

            summary = _summarize(
                session,
                batch,
                files_copied=len(copied_paths),
                already_imported=False,
            )
            _verify_summary(summary, verify_expected_counts)
            return summary
    except Exception:
        # Only remove files newly introduced by this attempt.  A deterministic
        # pre-existing destination may belong to a prior safe retry.
        for path in copied_paths:
            path.unlink(missing_ok=True)
        raise


def _receipt_from_row(
    row: Mapping[str, str],
    upload_file_id: str,
    *,
    duplicate_of_id: str | None = None,
) -> Receipt:
    is_big_w = row.get("store_name", "").upper().startswith("BIG W")
    merchant_key = "big_w" if is_big_w else "woolworths"
    merchant_name = "BIG W" if is_big_w else "Woolworths"
    purchase_date = _date(row.get("purchase_date"))
    total_cents = _cents(row.get("total"))
    transaction = _none(row.get("transaction_number"))
    natural_key = make_receipt_natural_key(
        merchant=merchant_key,
        purchase_date=purchase_date,
        transaction_number=transaction,
        total_cents=total_cents,
        store_number=_none(row.get("store_number")),
        pos_number=_none(row.get("pos")),
    )
    return Receipt(
        id=new_id(),
        upload_file_id=upload_file_id,
        merchant_key=merchant_key,
        merchant_name=merchant_name,
        store_number=_none(row.get("store_number")),
        store_name=_none(row.get("store_name")),
        purchase_date=purchase_date,
        purchase_time=_time(row.get("purchase_time")),
        timezone="Australia/Sydney",
        transaction_number=transaction,
        pos_number=_none(row.get("pos")),
        subtotal_cents=_cents(row.get("subtotal")),
        total_cents=total_cents,
        gst_cents=_cents(row.get("gst")),
        savings_cents=_cents(row.get("savings")),
        item_count_reported=_integer(row.get("item_count_reported")),
        is_grocery=not is_big_w,
        status=(
            ProcessingStatus.DUPLICATE
            if duplicate_of_id
            else ProcessingStatus.COMPLETE
        ),
        source_kind=ReceiptSource.IMPORT,
        parse_confidence=Decimal("1.000"),
        natural_key=natural_key,
        duplicate_of_id=duplicate_of_id,
        confirmed_at=None if duplicate_of_id else datetime.now(timezone.utc),
    )


def _item_from_row(row: Mapping[str, str], receipt_id: str) -> ReceiptItem:
    description = row.get("description", "").strip()
    normalized = _normalize_description(description)
    product_number = _none(row.get("product_number"))
    try:
        from categorize import categorize

        category = categorize(description)
    except ImportError:
        category = None
    return ReceiptItem(
        id=new_id(),
        receipt_id=receipt_id,
        line_number=_integer(row.get("line_number")) or 0,
        description=description,
        normalized_description=normalized,
        product_key=f"sku:{product_number}" if product_number else f"name:{normalized}",
        product_number=product_number,
        category=category,
        quantity=_decimal(row.get("quantity"), Decimal("1")),
        quantity_unit=_none(row.get("quantity_unit")) or "each",
        unit_price_cents=_cents(row.get("unit_price")),
        line_total_cents=_cents(row.get("line_total")) or 0,
        taxable=_boolean(row.get("taxable")),
        promotional=_boolean(row.get("promotional")),
        price_reduced=_boolean(row.get("price_reduced")),
        confidence=Decimal("1.000"),
        needs_review=False,
    )


def _summarize(
    session: Session,
    batch: UploadBatch,
    *,
    files_copied: int,
    already_imported: bool,
) -> ImportSummary:
    upload_ids = select(UploadFile.id).where(UploadFile.batch_id == batch.id)
    receipt_ids = select(Receipt.id).where(Receipt.upload_file_id.in_(upload_ids))
    uploads = session.scalar(
        select(func.count()).select_from(UploadFile).where(UploadFile.batch_id == batch.id)
    ) or 0
    canonical = session.scalar(
        select(func.count())
        .select_from(Receipt)
        .where(Receipt.upload_file_id.in_(upload_ids), Receipt.duplicate_of_id.is_(None))
    ) or 0
    duplicates = session.scalar(
        select(func.count())
        .select_from(Receipt)
        .where(Receipt.upload_file_id.in_(upload_ids), Receipt.duplicate_of_id.is_not(None))
    ) or 0
    items = session.scalar(
        select(func.count())
        .select_from(ReceiptItem)
        .where(ReceiptItem.receipt_id.in_(receipt_ids))
    ) or 0
    return ImportSummary(
        batch_id=str(batch.id),
        uploads=int(uploads),
        canonical_receipts=int(canonical),
        duplicate_receipts=int(duplicates),
        items=int(items),
        files_copied=files_copied,
        already_imported=already_imported,
    )


def _repair_managed_files(
    session: Session,
    batch: UploadBatch,
    *,
    source_dir: Path,
    storage_dir: Path,
) -> int:
    copied = 0
    storage_dir.mkdir(parents=True, exist_ok=True)
    uploads = session.scalars(
        select(UploadFile)
        .where(UploadFile.batch_id == batch.id)
        .order_by(UploadFile.ordinal)
    )
    for upload in uploads:
        source = source_dir / upload.original_filename
        destination = storage_dir / upload.storage_key
        if destination.exists():
            if _sha256_file(destination) != upload.content_sha256:
                raise LegacyImportError(
                    f"Managed receipt {upload.storage_key} failed its hash check."
                )
            continue
        if not source.is_file() or _sha256_file(source) != upload.content_sha256:
            raise LegacyImportError(
                f"Source receipt {upload.original_filename} is missing or changed."
            )
        _copy_verified(source, destination, upload.content_sha256)
        copied += 1
    return copied


def _validate_archive(
    source_dir: Path,
    receipt_rows: list[dict[str, str]],
    item_rows: list[dict[str, str]],
    *,
    verify_expected_counts: bool,
) -> None:
    if not source_dir.is_dir():
        raise LegacyImportError(f"Receipt source directory not found: {source_dir}")
    required_receipt_fields = {
        "receipt_id",
        "filename",
        "purchase_date",
        "total",
        "parse_status",
    }
    required_item_fields = {
        "receipt_id",
        "line_number",
        "description",
        "quantity",
        "line_total",
    }
    if receipt_rows and not required_receipt_fields <= receipt_rows[0].keys():
        raise LegacyImportError("Legacy receipts CSV has an unexpected schema.")
    if item_rows and not required_item_fields <= item_rows[0].keys():
        raise LegacyImportError("Legacy items CSV has an unexpected schema.")
    filenames = [row["filename"] for row in receipt_rows]
    if len(set(filenames)) != len(filenames):
        raise LegacyImportError("Legacy receipts CSV contains duplicate filenames.")
    missing = [name for name in filenames if not (source_dir / name).is_file()]
    if missing:
        raise LegacyImportError(f"Missing {len(missing)} legacy receipt PDF(s).")
    unsupported = [name for name in filenames if (source_dir / name).suffix.lower() != ".pdf"]
    if unsupported:
        raise LegacyImportError("The legacy archive contains a non-PDF receipt.")
    if verify_expected_counts:
        duplicates = sum(
            row.get("parse_status") == STATUS_DUPLICATE for row in receipt_rows
        )
        if (
            len(receipt_rows) != EXPECTED_UPLOADS
            or len(receipt_rows) - duplicates != EXPECTED_CANONICAL_RECEIPTS
            or duplicates != EXPECTED_DUPLICATES
            or len(item_rows) != EXPECTED_ITEMS
        ):
            raise LegacyImportError(
                "Legacy archive counts differ from the verified 103 uploads, "
                "100 canonical receipts, 3 duplicates, and 752 items."
            )


def _verify_summary(summary: ImportSummary, verify: bool) -> None:
    if not verify:
        return
    if (
        summary.uploads,
        summary.canonical_receipts,
        summary.duplicate_receipts,
        summary.items,
    ) != (
        EXPECTED_UPLOADS,
        EXPECTED_CANONICAL_RECEIPTS,
        EXPECTED_DUPLICATES,
        EXPECTED_ITEMS,
    ):
        raise LegacyImportError("Imported database counts do not match the archive.")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise LegacyImportError(f"Legacy CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _duplicate_original_filename(row: Mapping[str, str]) -> str:
    match = re.search(r"duplicate of ([^;]+)", row.get("warnings", ""), re.I)
    if not match:
        raise LegacyImportError(
            f"Duplicate {row.get('filename', '')} does not identify its original."
        )
    return match.group(1).strip()


def _legacy_storage_key(filename: str, digest: str) -> str:
    stable_id = uuid.uuid5(uuid.NAMESPACE_URL, f"grocery-home:{filename}:{digest}")
    return f"{stable_id.hex}.pdf"


def _copy_verified(source: Path, destination: Path, digest: str) -> None:
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copyfile(source, temporary)
        if _sha256_file(temporary) != digest:
            raise LegacyImportError(f"Copy verification failed for {source.name}.")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _pdf_page_count(path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(path).pages)


def _assert_private_storage(storage_dir: Path) -> None:
    if any(part.casefold() == "static" for part in storage_dir.parts):
        raise LegacyImportError("Legacy receipts cannot be copied into static storage.")


def _normalize_description(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _none(value: str | None) -> str | None:
    stripped = (value or "").strip()
    return stripped or None


def _cents(value: str | None) -> int | None:
    if not _none(value):
        return None
    try:
        return int((Decimal(str(value).replace(",", "")) * 100).quantize(Decimal("1")))
    except InvalidOperation as exc:
        raise LegacyImportError(f"Invalid money value {value!r}.") from exc


def _decimal(value: str | None, default: Decimal) -> Decimal:
    if not _none(value):
        return default
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise LegacyImportError(f"Invalid decimal value {value!r}.") from exc


def _integer(value: str | None) -> int | None:
    if not _none(value):
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError) as exc:
        raise LegacyImportError(f"Invalid integer value {value!r}.") from exc


def _date(value: str | None) -> date | None:
    if not _none(value):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise LegacyImportError(f"Invalid date value {value!r}.") from exc


def _time(value: str | None) -> time | None:
    if not _none(value):
        return None
    try:
        return time.fromisoformat(str(value))
    except ValueError as exc:
        raise LegacyImportError(f"Invalid time value {value!r}.") from exc


def _boolean(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "y"}


__all__ = [
    "EXPECTED_CANONICAL_RECEIPTS",
    "EXPECTED_DUPLICATES",
    "EXPECTED_ITEMS",
    "EXPECTED_UPLOADS",
    "ImportSummary",
    "LEGACY_IMPORT_SOURCE",
    "LegacyImportError",
    "import_existing",
]
