from __future__ import annotations

import csv
from pathlib import Path

from pypdf import PdfWriter
from sqlalchemy import func, select

from grocery_home.database import create_database, initialize_schema
from grocery_home.importer import import_existing
from grocery_home.models import Receipt, ReceiptItem, UploadFile


RECEIPT_FIELDS = [
    "receipt_id",
    "filename",
    "store_number",
    "store_name",
    "purchase_date",
    "purchase_time",
    "pos",
    "transaction_number",
    "subtotal",
    "total",
    "gst",
    "savings",
    "item_count_reported",
    "item_count_parsed",
    "parse_status",
    "warnings",
]
ITEM_FIELDS = [
    "receipt_id",
    "line_number",
    "description",
    "quantity",
    "quantity_unit",
    "unit_price",
    "line_total",
    "taxable",
    "promotional",
    "price_reduced",
    "product_number",
]


def write_pdf(path: Path, *, title: str) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=400)
    writer.add_metadata({"/Title": title})
    with path.open("wb") as handle:
        writer.write(handle)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_mini_archive(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    write_pdf(source / "one.pdf", title="canonical")
    # The duplicate deliberately has identical bytes, exercising the partial
    # canonical-hash unique index and pre-flush duplicate link.
    (source / "one-copy.pdf").write_bytes((source / "one.pdf").read_bytes())
    write_pdf(source / "bigw.pdf", title="big w")
    receipts_csv = tmp_path / "receipts.csv"
    items_csv = tmp_path / "items.csv"
    base = {
        "store_number": "1208",
        "purchase_time": "17:25",
        "pos": "003",
        "subtotal": "4.50",
        "total": "4.50",
        "gst": "0.00",
        "savings": "",
        "item_count_reported": "1",
        "item_count_parsed": "1",
    }
    write_csv(
        receipts_csv,
        RECEIPT_FIELDS,
        [
            {
                **base,
                "receipt_id": "r1",
                "filename": "one.pdf",
                "store_name": "Rutherford",
                "purchase_date": "2026-07-01",
                "transaction_number": "100",
                "parse_status": "ok",
                "warnings": "",
            },
            {
                **base,
                "receipt_id": "r1",
                "filename": "one-copy.pdf",
                "store_name": "Rutherford",
                "purchase_date": "2026-07-01",
                "transaction_number": "100",
                "parse_status": "duplicate",
                "warnings": "duplicate of one.pdf; line items excluded",
            },
            {
                **base,
                "receipt_id": "r2",
                "filename": "bigw.pdf",
                "store_name": "BIG W Jesmond",
                "purchase_date": "2026-07-02",
                "transaction_number": "101",
                "parse_status": "ok",
                "warnings": "",
            },
        ],
    )
    write_csv(
        items_csv,
        ITEM_FIELDS,
        [
            {
                "receipt_id": "r1",
                "line_number": "1",
                "description": "Full Cream Milk",
                "quantity": "1",
                "quantity_unit": "each",
                "unit_price": "4.50",
                "line_total": "4.50",
                "taxable": "False",
                "promotional": "False",
                "price_reduced": "False",
                "product_number": "12345",
            },
            {
                "receipt_id": "r2",
                "line_number": "1",
                "description": "Coffee Mug",
                "quantity": "1",
                "quantity_unit": "each",
                "unit_price": "4.50",
                "line_total": "4.50",
                "taxable": "True",
                "promotional": "False",
                "price_reduced": "False",
                "product_number": "98765",
            },
        ],
    )
    return source, receipts_csv, items_csv


def test_import_is_transactional_idempotent_and_preserves_duplicates(
    tmp_path: Path,
) -> None:
    source, receipts_csv, items_csv = create_mini_archive(tmp_path)
    managed = tmp_path / "managed"
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)

    with database.session() as session:
        summary = import_existing(
            session,
            source_dir=source,
            receipts_csv=receipts_csv,
            items_csv=items_csv,
            storage_dir=managed,
            verify_expected_counts=False,
        )
        assert (summary.uploads, summary.canonical_receipts) == (3, 2)
        assert (summary.duplicate_receipts, summary.items) == (1, 2)
        assert summary.files_copied == 3

    source_hashes = {path.name: path.read_bytes() for path in source.iterdir()}
    with database.session() as session:
        again = import_existing(
            session,
            source_dir=source,
            receipts_csv=receipts_csv,
            items_csv=items_csv,
            storage_dir=managed,
            verify_expected_counts=False,
        )
        assert again.already_imported
        assert again.files_copied == 0
        assert session.scalar(select(func.count()).select_from(UploadFile)) == 3
        assert session.scalar(select(func.count()).select_from(Receipt)) == 3
        assert session.scalar(select(func.count()).select_from(ReceiptItem)) == 2

        duplicate = session.scalar(
            select(Receipt).where(Receipt.duplicate_of_id.is_not(None))
        )
        assert duplicate is not None
        assert duplicate.items == []
        big_w = session.scalar(
            select(Receipt).where(Receipt.merchant_key == "big_w")
        )
        assert big_w is not None
        assert not big_w.is_grocery

    assert {path.name: path.read_bytes() for path in source.iterdir()} == source_hashes
    assert len(list(managed.glob("*.pdf"))) == 3
    database.dispose()


def test_verified_project_archive_imports_expected_counts(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    source = project / "receipts"
    receipts_csv = project / "parsed" / "receipts.csv"
    items_csv = project / "parsed" / "items.csv"
    if not (source.is_dir() and receipts_csv.is_file() and items_csv.is_file()):
        return
    fingerprints_before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in source.glob("*.pdf")
    }
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)

    with database.session() as session:
        summary = import_existing(
            session,
            source_dir=source,
            receipts_csv=receipts_csv,
            items_csv=items_csv,
            storage_dir=tmp_path / "managed",
        )
        assert (
            summary.uploads,
            summary.canonical_receipts,
            summary.duplicate_receipts,
            summary.items,
        ) == (103, 100, 3, 752)
        assert session.scalar(
            select(func.count())
            .select_from(Receipt)
            .where(Receipt.merchant_key == "big_w")
        ) == 7
        assert session.scalar(
            select(func.count())
            .select_from(Receipt)
            .where(Receipt.is_grocery.is_(False))
        ) == 7

    assert fingerprints_before == {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in source.glob("*.pdf")
    }
    database.dispose()
