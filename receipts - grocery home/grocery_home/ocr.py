"""Local OCR helpers and a conservative, retailer-agnostic receipt parser.

The RapidOCR dependency is deliberately imported lazily.  The rest of the
application (including text-PDF imports) therefore remains usable on machines
where the optional OCR runtime has not yet been installed.
"""

from __future__ import annotations

import re
from statistics import median
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Protocol, Sequence, TYPE_CHECKING

from PIL import Image, ImageEnhance, ImageOps

if TYPE_CHECKING:
    from grocery_home.detection import ReceiptRegion


class OCRUnavailable(RuntimeError):
    """Raised when image OCR is requested without a local OCR runtime."""


class OCRProcessingError(RuntimeError):
    """Raised when the OCR runtime cannot process an otherwise valid image."""


@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    confidence: float
    box: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class OCRResult:
    lines: tuple[OCRLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def mean_confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(line.confidence for line in self.lines) / len(self.lines)


@dataclass(frozen=True, slots=True)
class OCRItem:
    description: str
    line_total_cents: int
    quantity: Decimal = Decimal("1")
    quantity_unit: str = "each"
    unit_price_cents: int | None = None
    confidence: float = 0.0


@dataclass(slots=True)
class OCRReceipt:
    merchant: str
    purchase_date: date | None
    purchase_time: str | None
    transaction_number: str | None
    subtotal_cents: int | None
    total_cents: int | None
    gst_cents: int | None
    items: list[OCRItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0


class OCRAdapter(Protocol):
    def read(self, image: Image.Image) -> OCRResult:
        """Extract ordered text lines from a Pillow image."""


_MERCHANT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("BIG W", re.compile(r"\bBIG\s*W\b", re.I)),
    ("Woolworths", re.compile(r"\bWOOLWORTHS\b|\bWOOLIES\b", re.I)),
    ("Coles", re.compile(r"\bCOLES\b", re.I)),
    ("Aldi", re.compile(r"\bALDI\b", re.I)),
    ("IGA", re.compile(r"(?:^|\W)IGA(?:\W|$)|INDEPENDENT GROCERS", re.I)),
)
_DATE_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
        ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"),
    ),
    (
        re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"),
        ("%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y"),
    ),
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), ("%Y-%m-%d",)),
    (
        re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b"),
        ("%d.%m.%Y", "%d.%m.%y"),
    ),
    (
        re.compile(r"\b(\d{1,2}[A-Za-z]{3}\d{2,4})\b"),
        ("%d%b%Y", "%d%b%y"),
    ),
)
_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b")
_MONEY_AT_END = re.compile(
    r"(?P<amount>-?\$?\s*\d{1,5}(?:,\d{3})*\.\d{2})\s*(?:[A-Z*#^]*)\s*$",
    re.I,
)
_QTY = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>kg|ea|each|x)\s*"
    r"(?:@|x)?\s*\$?(?P<unit_price>\d+(?:\.\d+)?)?",
    re.I,
)
_QTY_DETAIL = re.compile(
    r"^Q(?:ty|TY)\s+(?P<qty>\d+(?:\.\d+)?)\s*@\s*\$?\s*"
    r"(?P<unit_price>\d+(?:\.\d+)?)\s*(?:ea|each)\.?\b",
    re.I,
)
_SKIP_ITEM = re.compile(
    r"^(?:"
    r"sub\s*total|subtotal|total|gst|tax|eftpos|visa|mastercard|change|cash|"
    r"balance|savings?|you\s+saved|amount|tender|payment|description|"
    r"receipt|transaction|trans|pos|store|phone|abn|date|time|items?"
    r")\b",
    re.I,
)


def detect_merchant(text: str) -> str:
    """Return a canonical supported merchant label or ``Other``."""

    for merchant, pattern in _MERCHANT_PATTERNS:
        if pattern.search(text):
            return merchant
    return "Other"


def normalize_image(image: Image.Image) -> Image.Image:
    """Apply EXIF orientation and gentle contrast normalization for OCR."""

    normalized = ImageOps.exif_transpose(image)
    if normalized.mode not in {"RGB", "L"}:
        normalized = normalized.convert("RGB")
    # Autocontrast helps photographs under uneven indoor lighting without
    # destroying coloured low-contrast supermarket logos.
    if normalized.mode == "RGB":
        channels = normalized.split()
        normalized = Image.merge("RGB", tuple(ImageOps.autocontrast(c) for c in channels))
    else:
        normalized = ImageOps.autocontrast(normalized)
    return ImageEnhance.Sharpness(normalized).enhance(1.15)


class RapidOCRAdapter:
    """Lazy adapter for either maintained RapidOCR Python package layout."""

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        error: Exception | None = None
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

            self._engine = RapidOCR()
            return self._engine
        except (ImportError, OSError) as exc:
            error = exc
        try:
            from rapidocr import RapidOCR  # type: ignore[import-not-found]

            self._engine = RapidOCR()
            return self._engine
        except (ImportError, OSError) as exc:
            raise OCRUnavailable(
                "Local receipt OCR is not installed. Install the project's OCR "
                "optional dependencies and run setup again."
            ) from (error or exc)

    def read(self, image: Image.Image) -> OCRResult:
        engine = self._get_engine()
        prepared = normalize_image(image)
        try:
            raw = engine(prepared)
        except Exception as exc:  # third-party runtimes expose varied exceptions
            raise OCRProcessingError(f"RapidOCR could not read the image: {exc}") from exc
        return _coerce_rapidocr_result(raw)


def _coerce_rapidocr_result(raw: Any) -> OCRResult:
    """Normalize RapidOCR 1.x/2.x result shapes into stable application types."""

    if raw is None:
        return OCRResult(())
    # rapidocr-onnxruntime returns ``(results, elapsed)``.  RapidOCR 2.x may
    # return a result object exposing ``txts``, ``scores`` and ``boxes``.
    payload = raw[0] if isinstance(raw, tuple) and len(raw) == 2 else raw
    if payload is None:
        return OCRResult(())
    if hasattr(payload, "txts"):
        # RapidOCR 3.x exposes NumPy arrays here.  Do not use ``value or``:
        # NumPy deliberately rejects truth-value testing for multi-element
        # arrays with "truth value ... is ambiguous".
        raw_texts = getattr(payload, "txts", None)
        texts = list(raw_texts) if raw_texts is not None else []
        raw_scores = getattr(payload, "scores", None)
        scores = (
            list(raw_scores)
            if raw_scores is not None
            else [0.0] * len(texts)
        )
        raw_boxes = getattr(payload, "boxes", None)
        boxes = (
            list(raw_boxes)
            if raw_boxes is not None
            else [()] * len(texts)
        )
        return OCRResult(
            tuple(
                OCRLine(str(text).strip(), float(score), _box_tuple(box))
                for text, score, box in zip(texts, scores, boxes, strict=False)
                if str(text).strip()
            )
        )

    lines: list[OCRLine] = []
    for entry in payload:
        if not isinstance(entry, Sequence) or len(entry) < 3:
            continue
        box, text, confidence = entry[0], entry[1], entry[2]
        if str(text).strip():
            lines.append(
                OCRLine(str(text).strip(), float(confidence), _box_tuple(box))
            )
    return OCRResult(tuple(lines))


def _box_tuple(value: Any) -> tuple[tuple[float, float], ...]:
    try:
        return tuple((float(point[0]), float(point[1])) for point in value)
    except (TypeError, ValueError, IndexError):
        return ()


def parse_ocr_receipt(
    results: OCRResult | Iterable[OCRLine],
    *,
    confidence_threshold: float = 0.72,
) -> OCRReceipt:
    """Parse OCR lines conservatively; the caller must still request review.

    Retailer-specific layouts improve merchant identification, while all line
    extraction intentionally follows a generic amount-at-line-end strategy so
    unknown supermarkets remain correctable.
    """

    original = results if isinstance(results, OCRResult) else OCRResult(tuple(results))
    result = OCRResult(_merge_spatial_rows(original.lines))
    text = result.text
    merchant = detect_merchant(text)
    if merchant == "Other":
        merchant = _guess_merchant(result.lines)
    if merchant == "Aldi":
        result = OCRResult(_repair_repeated_aldi_prices(result.lines))
        text = result.text
    parsed = OCRReceipt(
        merchant=merchant,
        purchase_date=_find_date(text),
        purchase_time=_find_time(text),
        transaction_number=_find_transaction(text),
        subtotal_cents=_find_labelled_amount(result.lines, ("SUBTOTAL", "SUB TOTAL")),
        total_cents=_find_total(result.lines),
        gst_cents=_find_labelled_amount(result.lines, ("GST", "TAX")),
        raw_text=text,
        confidence=result.mean_confidence,
    )
    # On long photographed receipts the payment footer is often cropped while
    # the final subtotal remains visible.  It is a safer review default than a
    # completely empty total, and camera inputs still always require review.
    if parsed.total_cents is None and parsed.subtotal_cents is not None:
        parsed.total_cents = parsed.subtotal_cents

    pending_description = ""
    deferred_amount: int | None = None
    line_index = 0
    while line_index < len(result.lines):
        line = result.lines[line_index]
        cleaned = " ".join(line.text.split())
        if re.match(r"^SUB\s*TOTAL\b", cleaned, re.I):
            break
        quantity_detail = _QTY_DETAIL.match(cleaned)
        if quantity_detail and parsed.items:
            quantity = Decimal(quantity_detail.group("qty"))
            unit_price = _money_to_cents(quantity_detail.group("unit_price"))
            parsed.items[-1] = replace(
                parsed.items[-1],
                quantity=quantity,
                quantity_unit="each",
                unit_price_cents=unit_price,
            )
            # A slanted receipt can cause the price from the next product row
            # to be spatially merged onto the end of this quantity detail.
            remainder = cleaned[quantity_detail.end():]
            shifted = _MONEY_AT_END.search(remainder)
            if shifted:
                deferred_amount = _money_to_cents(shifted.group("amount"))
            pending_description = ""
            line_index += 1
            continue
        amount_match = _MONEY_AT_END.search(cleaned)
        if amount_match is None:
            if (
                cleaned.casefold() == parsed.merchant.casefold()
                or _looks_like_receipt_metadata(cleaned)
            ):
                pending_description = ""
            elif _looks_like_description(cleaned):
                if deferred_amount is not None:
                    parsed.items.append(
                        OCRItem(
                            description=cleaned,
                            line_total_cents=deferred_amount,
                            confidence=line.confidence,
                        )
                    )
                    deferred_amount = None
                    pending_description = ""
                else:
                    pending_description = (
                        f"{pending_description} {cleaned}".strip()
                        if pending_description
                        else cleaned
                    )
            line_index += 1
            continue

        description = cleaned[: amount_match.start()].strip(" .:-\t")
        if pending_description and (not description or len(description) < 4):
            description = f"{pending_description} {description}".strip()
        pending_description = ""
        if not description or _SKIP_ITEM.match(description):
            line_index += 1
            continue
        cents = _money_to_cents(amount_match.group("amount"))
        if cents is None:
            line_index += 1
            continue
        if deferred_amount is not None:
            cents, deferred_amount = deferred_amount, cents

        # Some bilingual receipts print the translated description and its
        # weight immediately below a non-Latin item/price row.  Keep those
        # lines with the item instead of treating them as the next product.
        if not re.search(r"[A-Za-z]", description):
            next_index = line_index + 1
            if next_index < len(result.lines):
                next_text = " ".join(result.lines[next_index].text.split())
                if _looks_like_description(next_text):
                    description = f"{description} {next_text}"
                    line_index = next_index
                    quantity_index = line_index + 1
                    if quantity_index < len(result.lines):
                        quantity_text = " ".join(
                            result.lines[quantity_index].text.split()
                        )
                        if _QTY.search(quantity_text):
                            description = f"{description} {quantity_text}"
                            line_index = quantity_index
        qty, unit, unit_price = _parse_quantity(description)
        parsed.items.append(
            OCRItem(
                description=description,
                line_total_cents=cents,
                quantity=qty,
                quantity_unit=unit,
                unit_price_cents=unit_price,
                confidence=line.confidence,
            )
        )
        line_index += 1

    if parsed.merchant == "Other":
        parsed.warnings.append("Merchant was not recognised.")
    if parsed.purchase_date is None:
        parsed.warnings.append("Purchase date was not recognised.")
    if parsed.total_cents is None:
        parsed.warnings.append("Receipt total was not recognised.")
    if not parsed.items:
        parsed.warnings.append("No line items were recognised.")
    low_confidence = sum(
        item.confidence < confidence_threshold for item in parsed.items
    )
    if low_confidence:
        parsed.warnings.append(
            f"{low_confidence} item line{'s' if low_confidence != 1 else ''} "
            "need extra attention."
        )
    if (
        parsed.subtotal_cents is not None
        and parsed.items
        and sum(item.line_total_cents for item in parsed.items)
        != parsed.subtotal_cents
    ):
        parsed.warnings.append("Line items do not balance to the subtotal.")
    return parsed


def parse_detected_receipt(
    image: Image.Image,
    adapter: OCRAdapter,
    regions: Sequence["ReceiptRegion"],
    *,
    whole_result: OCRResult | None = None,
) -> OCRReceipt:
    """Combine whole-receipt OCR with full-resolution semantic region OCR.

    The detector is advisory: a regional result replaces the whole-image
    result only when it supplies missing data or balances closer to the total.
    """

    whole = whole_result or adapter.read(image)
    parsed = parse_ocr_receipt(whole)
    regional_items: list[OCRItem] = []
    amount_candidates: dict[str, list[int]] = {
        "Subtotal": [], "Tax": [], "TotalPrice": []
    }
    semantic_lines: dict[str, list[OCRLine]] = {}
    regional_lines: list[OCRLine] = []

    for region in regions:
        left, top, right, bottom = _padded_crop_box(region.box, image.size)
        cropped = image.crop((left, top, right, bottom))
        result = adapter.read(cropped)
        regional_lines.extend(result.lines)
        semantic_lines.setdefault(region.label, []).extend(result.lines)
        if region.label == "Item":
            regional_items.extend(parse_ocr_receipt(result).items)
        elif region.label in amount_candidates:
            amount = _last_money_amount(result.lines)
            if amount is not None:
                amount_candidates[region.label].append(amount)

    title_lines = semantic_lines.get("Title", []) + semantic_lines.get("Address", [])
    if parsed.merchant == "Other" and title_lines:
        title_result = OCRResult(tuple(title_lines))
        parsed.merchant = detect_merchant(title_result.text)
        if parsed.merchant == "Other":
            parsed.merchant = _guess_merchant(title_result.lines)
    if parsed.purchase_date is None and semantic_lines.get("Date"):
        parsed.purchase_date = _find_date(
            OCRResult(tuple(semantic_lines["Date"])).text
        )
    if parsed.transaction_number is None and semantic_lines.get("OrderId"):
        parsed.transaction_number = _find_transaction(
            OCRResult(tuple(semantic_lines["OrderId"])).text
        )

    detected_total = _best_amount(amount_candidates["TotalPrice"])
    if detected_total is not None and (
        parsed.total_cents is None
        or _amount_fit(detected_total, regional_items) < _amount_fit(parsed.total_cents, regional_items)
    ):
        parsed.total_cents = detected_total
    detected_subtotal = _best_amount(amount_candidates["Subtotal"])
    if parsed.subtotal_cents is None and detected_subtotal is not None:
        parsed.subtotal_cents = detected_subtotal
    detected_tax = _best_amount(amount_candidates["Tax"])
    if parsed.gst_cents is None and detected_tax is not None:
        parsed.gst_cents = detected_tax

    if regional_items and _items_fit(regional_items, parsed.total_cents) < _items_fit(
        parsed.items, parsed.total_cents
    ):
        parsed.items = regional_items

    parsed.raw_text = whole.text + (
        "\n\n--- detected regions ---\n" + "\n".join(line.text for line in regional_lines)
        if regional_lines else ""
    )
    _refresh_parse_warnings(parsed)
    return parsed


def _padded_crop_box(
    box: tuple[int, int, int, int], size: tuple[int, int]
) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    pad_x = max(6, round((right - left) * 0.025))
    pad_y = max(6, round((bottom - top) * 0.025))
    return (
        max(0, left - pad_x), max(0, top - pad_y),
        min(size[0], right + pad_x), min(size[1], bottom + pad_y),
    )


def _last_money_amount(lines: Iterable[OCRLine]) -> int | None:
    values: list[int] = []
    for line in lines:
        match = _MONEY_AT_END.search(" ".join(line.text.split()))
        if match:
            value = _money_to_cents(match.group("amount"))
            if value is not None:
                values.append(value)
    return values[-1] if values else None


def _best_amount(values: Sequence[int]) -> int | None:
    return values[-1] if values else None


def _amount_fit(amount: int, items: Sequence[OCRItem]) -> int:
    return abs(amount - sum(item.line_total_cents for item in items)) if items else 10**9


def _items_fit(items: Sequence[OCRItem], total: int | None) -> tuple[int, int]:
    if not items:
        return (10**9, 0)
    if total is None:
        return (0, -len(items))
    return (abs(sum(item.line_total_cents for item in items) - total), -len(items))


def _refresh_parse_warnings(parsed: OCRReceipt) -> None:
    generated_prefixes = (
        "Merchant was not recognised", "Purchase date was not recognised",
        "Receipt total was not recognised", "No line items were recognised",
        "Line items do not balance", "item line", "item lines",
    )
    parsed.warnings = [
        warning for warning in parsed.warnings
        if not any(prefix in warning for prefix in generated_prefixes)
    ]
    if parsed.merchant == "Other":
        parsed.warnings.append("Merchant was not recognised.")
    if parsed.purchase_date is None:
        parsed.warnings.append("Purchase date was not recognised.")
    if parsed.total_cents is None:
        parsed.warnings.append("Receipt total was not recognised.")
    if not parsed.items:
        parsed.warnings.append("No line items were recognised.")
    low = sum(item.confidence < 0.72 for item in parsed.items)
    if low:
        parsed.warnings.append(f"{low} item line{'s' if low != 1 else ''} need extra attention.")
    expected = parsed.subtotal_cents if parsed.subtotal_cents is not None else parsed.total_cents
    if expected is not None and parsed.items and sum(item.line_total_cents for item in parsed.items) != expected:
        parsed.warnings.append("Line items do not balance to the subtotal.")


def _find_date(text: str) -> date | None:
    for pattern, formats in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1)
            for date_format in formats:
                try:
                    return datetime.strptime(raw, date_format).date()
                except ValueError:
                    continue
    return None


def _find_time(text: str) -> str | None:
    match = _TIME.search(text)
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else None


def _find_transaction(text: str) -> str | None:
    aldi_match = re.search(
        r"\bINV/ROC\s+NO\s+([A-Z0-9-]{3,})",
        text,
        re.I,
    )
    if aldi_match:
        return aldi_match.group(1)
    match = re.search(
        r"\b(?:TRANS(?:ACTION)?|RECEIPT)\b\s*(?:NO|NUMBER|#|:|：)?\s*"
        r"([A-Z0-9-]{3,})",
        text,
        re.I,
    )
    if match:
        candidate = match.group(1)
        if candidate.upper() not in {"TYPE", "DATE", "TIME"}:
            return candidate
    number_match = re.search(
        r"\bNO\s*(?::|：|#)?\s*([A-Z0-9-]{3,})",
        text,
        re.I,
    )
    return number_match.group(1) if number_match else None


def _repair_repeated_aldi_prices(lines: Sequence[OCRLine]) -> tuple[OCRLine, ...]:
    """Repair a truncated price using another occurrence of the same ALDI SKU."""

    complete = re.compile(
        r"^(?P<description>\d{5,7}\s+.+?)\s+"
        r"(?P<amount>-?\d+\.\d{2})\s+[AB]\s*$",
        re.I,
    )
    truncated = re.compile(
        r"^(?P<description>\d{5,7}\s+.+?)\s+"
        r"(?P<amount>-?\d+\.\d)(?:\s+(?P<tax>[AB]))?\s*$",
        re.I,
    )
    known: dict[str, list[str]] = {}
    for line in lines:
        match = complete.match(" ".join(line.text.split()))
        if match:
            known.setdefault(match.group("description").casefold(), []).append(
                match.group("amount")
            )

    repaired: list[OCRLine] = []
    for line in lines:
        cleaned = " ".join(line.text.split())
        match = truncated.match(cleaned)
        candidates = known.get(match.group("description").casefold(), []) if match else []
        if match and candidates:
            amount = max(set(candidates), key=candidates.count)
            suffix = f" {match.group('tax')}" if match.group("tax") else ""
            repaired.append(
                OCRLine(
                    f"{match.group('description')} {amount}{suffix}",
                    line.confidence,
                    line.box,
                )
            )
        else:
            repaired.append(line)
    return tuple(repaired)


def _merge_spatial_rows(lines: Sequence[OCRLine]) -> tuple[OCRLine, ...]:
    """Join OCR fragments occupying the same visual row, left to right."""

    boxed = [line for line in lines if len(line.box) >= 4]
    if len(boxed) != len(lines) or not lines:
        return tuple(lines)

    def bounds(line: OCRLine) -> tuple[float, float, float, float]:
        xs = [point[0] for point in line.box]
        ys = [point[1] for point in line.box]
        return min(xs), min(ys), max(xs), max(ys)

    slopes: list[float] = []
    for line in lines:
        left_point, right_point = line.box[0], line.box[1]
        width = right_point[0] - left_point[0]
        if abs(width) > 1.0:
            slopes.append((right_point[1] - left_point[1]) / width)
    skew = median(slopes) if slopes else 0.0

    def corrected_center(line: OCRLine) -> float:
        left, top, right, bottom = bounds(line)
        return (top + bottom) / 2 - skew * ((left + right) / 2)

    ordered = sorted(lines, key=lambda line: (corrected_center(line), bounds(line)[0]))
    rows: list[list[OCRLine]] = []
    row_centers: list[float] = []
    row_heights: list[float] = []
    for line in ordered:
        left, top, right, bottom = bounds(line)
        center = corrected_center(line)
        height = max(bottom - top, 1.0)
        horizontal_conflict = False
        if rows:
            for existing in rows[-1]:
                existing_left, _top, existing_right, _bottom = bounds(existing)
                overlap = max(
                    0.0,
                    min(right, existing_right) - max(left, existing_left),
                )
                narrower = max(
                    min(right - left, existing_right - existing_left),
                    1.0,
                )
                if overlap / narrower > 0.35:
                    horizontal_conflict = True
                    break
        if (
            rows
            and not horizontal_conflict
            and abs(center - row_centers[-1])
            <= 0.55 * max(height, row_heights[-1])
        ):
            rows[-1].append(line)
            count = len(rows[-1])
            # Keep a stable average centre/height.  Using the row's expanding
            # outer bounds causes neighbouring lines on long receipts to
            # chain together into one enormous row.
            row_centers[-1] += (center - row_centers[-1]) / count
            row_heights[-1] += (height - row_heights[-1]) / count
            continue
        rows.append([line])
        row_centers.append(center)
        row_heights.append(height)

    merged: list[OCRLine] = []
    for row in rows:
        row.sort(key=lambda line: bounds(line)[0])
        text = " ".join(line.text.strip() for line in row if line.text.strip())
        confidence = sum(line.confidence for line in row) / len(row)
        all_points = [point for line in row for point in line.box]
        left = min(point[0] for point in all_points)
        top = min(point[1] for point in all_points)
        right = max(point[0] for point in all_points)
        bottom = max(point[1] for point in all_points)
        merged.append(
            OCRLine(
                text,
                confidence,
                ((left, top), (right, top), (right, bottom), (left, bottom)),
            )
        )
    return tuple(merged)


def _guess_merchant(lines: Sequence[OCRLine]) -> str:
    """Use an obvious shop-like header when it is not a known retailer."""

    merchant_words = re.compile(
        r"\b(?:MARKET|MART|GROCER(?:Y|IES)?|BUTCHER(?:Y)?|MEAT|SHOP|STORE)\b",
        re.I,
    )
    for line in lines[:8]:
        candidate = " ".join(line.text.split()).strip(" .:-\t")
        if merchant_words.search(candidate) and not _SKIP_ITEM.match(candidate):
            return candidate.title()
    return "Other"


def _find_labelled_amount(
    lines: Iterable[OCRLine], labels: tuple[str, ...]
) -> int | None:
    for line in reversed(tuple(lines)):
        upper = line.text.upper()
        if any(label in upper for label in labels):
            match = _MONEY_AT_END.search(line.text)
            if match:
                return _money_to_cents(match.group("amount"))
    return None


def _find_total(lines: Iterable[OCRLine]) -> int | None:
    for line in reversed(tuple(lines)):
        upper = line.text.upper()
        if (
            "TOTAL" not in upper
            or "SUBTOTAL" in upper
            or "SUB TOTAL" in upper
            or "TOTAL ITEMS" in upper
            or "GST" in upper
        ):
            continue
        match = _MONEY_AT_END.search(line.text)
        if match:
            return _money_to_cents(match.group("amount"))
    return None


def _money_to_cents(value: str) -> int | None:
    try:
        amount = Decimal(value.replace("$", "").replace(",", "").replace(" ", ""))
    except InvalidOperation:
        return None
    return int((amount * 100).quantize(Decimal("1")))


def _parse_quantity(description: str) -> tuple[Decimal, str, int | None]:
    match = _QTY.search(description)
    if not match:
        return Decimal("1"), "each", None
    try:
        quantity = Decimal(match.group("qty"))
    except InvalidOperation:
        quantity = Decimal("1")
    unit = "kg" if (match.group("unit") or "").lower() == "kg" else "each"
    unit_price = (
        _money_to_cents(match.group("unit_price"))
        if match.group("unit_price")
        else None
    )
    return quantity, unit, unit_price


def _looks_like_description(text: str) -> bool:
    return (
        len(text) >= 3
        and bool(re.search(r"[A-Za-z]", text))
        and not _SKIP_ITEM.match(text)
        and not re.match(r"^[\d\s:/.-]+$", text)
    )


def _looks_like_receipt_metadata(text: str) -> bool:
    return bool(
        re.match(
            r"^(?:ABN|TEL|PHONE|TAX\s+INVOICE|NO\s*[:：#]|REG\.?\s*[:：]|"
            r"CASHIER\s*[:：]|ADDRESS\b)",
            text,
            re.I,
        )
        or re.search(r"\b(?:NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\b", text, re.I)
    )
