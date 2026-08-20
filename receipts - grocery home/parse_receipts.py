#!/usr/bin/env python3
"""Parse Woolworths/BIG W eReceipt PDFs into receipt and line-item CSV files."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency. Install it with: python -m pip install pypdf") from exc


MONEY = r"\$?(-?\d[\d,]*\.\d{2})"
ITEM_LINE = re.compile(rf"^\s*(.*?)\s+{MONEY}\s*$")
QTY_LINE = re.compile(rf"^\s*Qty\s+(\d+(?:\.\d+)?)\s+@\s+\$([\d.]+)\s+each\s+{MONEY}\s*$", re.I)
WEIGHT_LINE = re.compile(rf"^\s*(\d+(?:\.\d+)?)\s*kg\s+NET\s+@\s+\$([\d.]+)/kg\s+{MONEY}\s*$", re.I)
# Annotation printed on its own line above the item it applies to.
PRICE_REDUCED_LINE = re.compile(r"^\s*PRICE REDUCED BY \$[\d.]+(?:\s+each)?\s*$", re.I)
FILENAME = re.compile(
    r"^eReceipt_(?P<store_number>\d+)_(?P<store_name>.+?)_"
    r"(?P<date>\d{2}[A-Za-z]{3}\d{4})__.+\.pdf$",
    re.I,
)


@dataclass
class Receipt:
    receipt_id: str
    filename: str
    store_number: str
    store_name: str
    purchase_date: str
    purchase_time: str
    pos: str
    transaction_number: str
    subtotal: str
    total: str
    gst: str
    savings: str
    item_count_reported: str
    item_count_parsed: int
    parse_status: str
    warnings: str


@dataclass
class Item:
    receipt_id: str
    line_number: int
    description: str
    quantity: str
    quantity_unit: str
    unit_price: str
    line_total: str
    taxable: bool
    promotional: bool
    price_reduced: bool
    product_number: str


def amount(value: str | None) -> str:
    if not value:
        return ""
    try:
        return f"{Decimal(value.replace(',', '')):.2f}"
    except InvalidOperation:
        return ""


def first_match(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def parse_pdf(path: Path) -> tuple[Receipt, list[Item]]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    warnings: list[str] = []
    name_match = FILENAME.match(path.name)
    if name_match:
        store_number = name_match["store_number"]
        store_name = name_match["store_name"]
        purchase_date = datetime.strptime(name_match["date"], "%d%b%Y").date().isoformat()
    else:
        store_number = first_match(r"(?m)^\s*(\d{4})\s+.+?(?:PH:|$)", text)
        store_name = ""
        purchase_date = ""
        warnings.append("filename did not match expected pattern")

    terminal = re.search(
        r"POS\s+(\d+)\s+TRANS\s+(\d+)\s+(\d{1,2}:\d{2})\s+(\d{2}/\d{2}/\d{4})",
        text,
        re.I,
    )
    pos = transaction = purchase_time = ""
    if terminal:
        pos, transaction, purchase_time, terminal_date = terminal.groups()
        parsed_terminal_date = datetime.strptime(terminal_date, "%d/%m/%Y").date().isoformat()
        if purchase_date and parsed_terminal_date != purchase_date:
            warnings.append(f"filename date differs from receipt date {parsed_terminal_date}")
        purchase_date = parsed_terminal_date
    else:
        warnings.append("POS/transaction footer not found")

    subtotal_match = re.search(rf"(?m)^\s*(\d+)\s+SUBTOTAL\s+{MONEY}\s*$", text, re.I)
    item_count_reported = subtotal_match.group(1) if subtotal_match else ""
    subtotal = amount(subtotal_match.group(2)) if subtotal_match else ""
    total = amount(first_match(rf"(?m)^\s*TOTAL\s+{MONEY}\s*$", text, re.I))
    gst = amount(first_match(rf"TOTAL includes GST\s+{MONEY}", text, re.I))
    savings = amount(first_match(rf"You saved\s+{MONEY}", text, re.I))

    receipt_id = f"{store_number}-{purchase_date}-{pos}-{transaction}" if transaction else path.stem
    items: list[Item] = []
    table_match = re.search(r"(?ms)^Description\s+\$\s*\n(.*?)^\s*\d+\s+SUBTOTAL\b", text)
    if not table_match:
        warnings.append("item table not found")
    else:
        pending_description = ""
        price_reduced = False
        for raw_line in table_match.group(1).splitlines():
            line = raw_line.rstrip()
            if not line.strip() or line.lstrip().startswith("^Promotional Price"):
                continue
            if PRICE_REDUCED_LINE.match(line):
                price_reduced = True
                continue
            qty_match = QTY_LINE.match(line)
            weight_match = WEIGHT_LINE.match(line)
            if (qty_match or weight_match) and pending_description:
                match = qty_match or weight_match
                qty, unit, line_total = match.groups()
                quantity_unit = "each" if qty_match else "kg"
                description = pending_description
                pending_description = ""
            else:
                item_match = ITEM_LINE.match(line)
                if not item_match:
                    pending_description = (pending_description + " " + line.strip()).strip()
                    continue
                description_part, line_total = item_match.groups()
                description = (pending_description + " " + description_part.strip()).strip()
                pending_description = ""
                qty, quantity_unit, unit = "1", "each", amount(line_total)

            markers = re.match(r"^([#^]*)(.*)$", description)
            prefix, description = markers.groups() if markers else ("", description)
            product_match = re.match(r"#?(\d{5,})\s+(.*)", description)
            product_number = ""
            if product_match:
                product_number, description = product_match.groups()
            items.append(Item(
                receipt_id=receipt_id,
                line_number=len(items) + 1,
                description=description.strip(),
                quantity=qty,
                quantity_unit=quantity_unit,
                unit_price=amount(unit),
                line_total=amount(line_total),
                taxable="#" in prefix or bool(product_number),
                promotional="^" in prefix,
                price_reduced=price_reduced,
                product_number=product_number,
            ))
            price_reduced = False
        if pending_description:
            warnings.append(f"unmatched item text: {pending_description}")

    # Receipt item counts treat weighed products as one and do not count discounts.
    parsed_item_count = sum(
        0 if Decimal(i.line_total) < 0 else (Decimal(i.quantity) if i.quantity_unit == "each" else 1)
        for i in items
    )
    if item_count_reported and Decimal(item_count_reported) != parsed_item_count:
        warnings.append("reported item quantity does not equal parsed quantity")
    if subtotal and items:
        parsed_sum = sum(Decimal(i.line_total) for i in items)
        if parsed_sum != Decimal(subtotal):
            warnings.append(f"line items sum to {parsed_sum:.2f}, expected subtotal {subtotal}")

    receipt = Receipt(
        receipt_id, path.name, store_number, store_name, purchase_date, purchase_time,
        pos, transaction, subtotal, total, gst, savings, item_count_reported,
        len(items), "warning" if warnings else "ok", "; ".join(warnings),
    )
    return receipt, items


def write_csv(path: Path, rows: list[object], row_type: type) -> None:
    fields = list(row_type.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", nargs="?", type=Path, default=Path("receipts"))
    parser.add_argument("--output-dir", type=Path, default=Path("parsed"))
    args = parser.parse_args()

    pdfs = sorted(args.input_dir.glob("*.pdf"))
    if not pdfs:
        parser.error(f"no PDF files found in {args.input_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    receipts: list[Receipt] = []
    items: list[Item] = []
    seen: dict[str, str] = {}
    failures = duplicates = 0
    for pdf in pdfs:
        try:
            receipt, receipt_items = parse_pdf(pdf)
        except Exception as exc:  # continue so one malformed PDF does not stop the batch
            failures += 1
            print(f"ERROR {pdf.name}: {exc}", file=sys.stderr)
            continue
        # The same transaction can be exported to several PDFs; keep one copy so
        # spend totals and baskets are not double counted.
        original = seen.get(receipt.receipt_id)
        if original:
            duplicates += 1
            receipt.parse_status = "duplicate"
            note = f"duplicate of {original}; line items excluded"
            receipt.warnings = f"{receipt.warnings}; {note}" if receipt.warnings else note
        else:
            seen[receipt.receipt_id] = receipt.filename
            items.extend(receipt_items)
        receipts.append(receipt)

    write_csv(args.output_dir / "receipts.csv", receipts, Receipt)
    write_csv(args.output_dir / "items.csv", items, Item)
    warnings = sum(r.parse_status == "warning" for r in receipts)
    print(f"Parsed {len(receipts)}/{len(pdfs)} PDFs, {len(items)} line items, "
          f"{warnings} receipts with warnings, {duplicates} duplicates, {failures} failures.")
    print(f"Output: {args.output_dir.resolve()}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
