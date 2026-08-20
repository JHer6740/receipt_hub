from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from PIL import Image

from grocery_home.ingestion import (
    MAX_FILE_BYTES,
    ReceiptExtractionError,
    UploadValidationError,
    create_upload_batch,
    extract_stored_receipt,
    process_upload_batch,
    sniff_media_kind,
    store_validated_uploads,
    transaction_identity,
    validate_upload_batch,
)
from grocery_home.database import create_database, initialize_schema
from grocery_home.models import ProcessingStatus, Receipt, ReceiptItem
from grocery_home.ocr import OCRLine, OCRResult


def image_bytes(kind: str = "PNG", size: tuple[int, int] = (640, 1200)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "white").save(output, format=kind)
    return output.getvalue()


class FakeOCR:
    def read(self, _image: Image.Image) -> OCRResult:
        return OCRResult(
            (
                OCRLine("COLES", 0.98),
                OCRLine("18/07/2026", 0.97),
                OCRLine("Bread $4.20", 0.92),
                OCRLine("TOTAL $4.20", 0.99),
            )
        )


def test_sniffing_uses_content_not_extension() -> None:
    data = image_bytes()

    assert sniff_media_kind(data) == "png"
    upload = validate_upload_batch([("misleading.pdf", data)])[0]
    assert upload.media_kind == "png"
    assert upload.media_type == "image/png"


def test_rejects_unsupported_and_oversized_files() -> None:
    with pytest.raises(UploadValidationError, match="not a supported"):
        validate_upload_batch([("receipt.jpg", b"not an image")])

    with pytest.raises(UploadValidationError, match="larger than 20 MB"):
        validate_upload_batch([("large.jpg", b"\xff\xd8\xff" + b"x" * MAX_FILE_BYTES)])


def test_rejects_too_many_photos_and_mixed_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    photo = image_bytes(size=(64, 64))
    with pytest.raises(UploadValidationError, match="at most 5"):
        validate_upload_batch([(f"{index}.png", photo) for index in range(6)])

    # A minimal fake is enough here because the batch-shape rule is exercised
    # after individual validation; avoid coupling this test to PDF generation.
    from grocery_home import ingestion

    original = ingestion._read_and_validate
    valid_photo = original(("one.png", photo), 0)
    valid_pdf = valid_photo.__class__(
        "one.pdf",
        "pdf",
        "application/pdf",
        len(photo),
        valid_photo.sha256,
        photo,
    )
    values = iter((valid_pdf, valid_photo))
    monkeypatch.setattr(ingestion, "_read_and_validate", lambda *_args: next(values))
    with pytest.raises(UploadValidationError, match="not a mixture"):
        validate_upload_batch([b"a", b"b"])


def test_private_storage_uses_generated_name(tmp_path: Path) -> None:
    validated = validate_upload_batch([("../../family receipt.png", image_bytes())])

    [stored] = store_validated_uploads(validated, tmp_path / "private" / "receipts")

    assert stored.path.exists()
    assert stored.path.parent == (tmp_path / "private" / "receipts").resolve()
    assert stored.original_filename == "family receipt.png"
    assert re.fullmatch(r"[0-9a-f]{32}\.png", stored.storage_name)
    assert stored.sha256 == validated[0].sha256


def test_storage_refuses_static_tree(tmp_path: Path) -> None:
    validated = validate_upload_batch([("receipt.png", image_bytes())])

    with pytest.raises(ValueError, match="static"):
        store_validated_uploads(validated, tmp_path / "static" / "receipts")


def test_all_image_receipts_need_review_even_when_ocr_balances(tmp_path: Path) -> None:
    validated = validate_upload_batch([("receipt.png", image_bytes())])
    stored = store_validated_uploads(validated, tmp_path / "private")

    parsed = extract_stored_receipt(stored, ocr_adapter=FakeOCR())

    assert parsed.merchant == "Coles"
    assert parsed.total_cents == 420
    assert parsed.is_balanced
    assert parsed.status == "needs_review"
    assert parsed.items[0].description == "Bread"


def test_transaction_identity_requires_complete_semantic_key(tmp_path: Path) -> None:
    validated = validate_upload_batch([("receipt.png", image_bytes())])
    stored = store_validated_uploads(validated, tmp_path / "private")
    parsed = extract_stored_receipt(stored, ocr_adapter=FakeOCR())

    assert transaction_identity(parsed) is None
    parsed.transaction_number = "A-123"
    assert transaction_identity(parsed) == (
        "coles",
        parsed.purchase_date,
        "a-123",
        420,
    )


def test_extract_rejects_empty_stored_batch() -> None:
    with pytest.raises(ReceiptExtractionError, match="no stored files"):
        extract_stored_receipt([])


def test_balanced_legacy_text_pdf_can_complete_after_private_rename(
    tmp_path: Path,
) -> None:
    project_receipts = Path(__file__).resolve().parents[1] / "receipts"
    sample = next(project_receipts.glob("*BIG W*.pdf"), None)
    if sample is None:
        return
    stored = store_validated_uploads(
        validate_upload_batch([(sample.name, sample.read_bytes())]),
        tmp_path / "private",
    )

    parsed = extract_stored_receipt(stored)

    assert parsed.merchant == "BIG W"
    assert parsed.status == "complete"
    assert parsed.is_balanced


def test_batch_processing_persists_items_and_exact_duplicate_audit(
    tmp_path: Path,
) -> None:
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    storage = tmp_path / "private"
    data = image_bytes()

    stored = store_validated_uploads(
        validate_upload_batch([("receipt.png", data)]),
        storage,
    )
    with database.session() as session:
        batch = create_upload_batch(session, stored)
        first_batch_id = batch.id
    with database.session() as session:
        receipt = process_upload_batch(
            session,
            first_batch_id,
            storage_dir=storage,
            ocr_adapter=FakeOCR(),
        )
        canonical_id = receipt.id
        assert receipt.status == ProcessingStatus.NEEDS_REVIEW
        assert len(receipt.items) == 1
        assert receipt.items[0].category

    stored_again = store_validated_uploads(
        validate_upload_batch([("same-again.png", data)]),
        storage,
    )
    with database.session() as session:
        batch = create_upload_batch(session, stored_again)
        duplicate_batch_id = batch.id
        assert batch.files[0].duplicate_of_id is not None
    with database.session() as session:
        duplicate = process_upload_batch(
            session,
            duplicate_batch_id,
            storage_dir=storage,
            ocr_adapter=FakeOCR(),
        )
        assert duplicate.status == ProcessingStatus.DUPLICATE
        assert duplicate.duplicate_of_id == canonical_id
        assert duplicate.items == []
        assert duplicate.item_count_reported == 1

    with database.session() as session:
        assert len(session.query(Receipt).all()) == 2
        assert len(session.query(ReceiptItem).all()) == 1
    database.dispose()


def test_secondary_photo_hash_match_is_ocrd_as_its_own_receipt(
    tmp_path: Path,
) -> None:
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    storage = tmp_path / "private"
    first_data = image_bytes(size=(640, 1200))
    second_data = image_bytes(size=(641, 1200))

    stored = store_validated_uploads(
        validate_upload_batch(
            [("first.png", first_data), ("second.png", second_data)]
        ),
        storage,
    )
    with database.session() as session:
        first_batch = create_upload_batch(session, stored)
        first_batch_id = first_batch.id
    with database.session() as session:
        process_upload_batch(
            session,
            first_batch_id,
            storage_dir=storage,
            ocr_adapter=FakeOCR(),
        )

    stored_again = store_validated_uploads(
        validate_upload_batch([("second-again.png", second_data)]),
        storage,
    )
    with database.session() as session:
        second_batch = create_upload_batch(session, stored_again)
        second_batch_id = second_batch.id
        assert second_batch.files[0].duplicate_of_id is not None
    with database.session() as session:
        receipt = process_upload_batch(
            session,
            second_batch_id,
            storage_dir=storage,
            ocr_adapter=FakeOCR(),
        )

        assert receipt.status == ProcessingStatus.NEEDS_REVIEW
        assert receipt.duplicate_of_id is None
        assert receipt.merchant_name == "Coles"
        assert [item.description for item in receipt.items] == ["Bread"]

    database.dispose()
