from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from PIL import Image

from grocery_home.ocr import (
    OCRLine,
    OCRResult,
    RapidOCRAdapter,
    _merge_spatial_rows,
    detect_merchant,
    normalize_image,
    parse_ocr_receipt,
)


def test_detects_supported_merchants_without_false_big_w_match() -> None:
    assert detect_merchant("WOOLWORTHS 1410 ABERGLASSLYN") == "Woolworths"
    assert detect_merchant("BIG W JESMOND") == "BIG W"
    assert detect_merchant("Coles Supermarkets Australia") == "Coles"
    assert detect_merchant("Welcome to ALDI") == "Aldi"
    assert detect_merchant("Friendly Grocer IGA") == "IGA"
    assert detect_merchant("Corner Food Shop") == "Other"


def test_generic_parser_extracts_receipt_and_flags_low_confidence() -> None:
    result = OCRResult(
        (
            OCRLine("WOOLWORTHS", 0.99),
            OCRLine("12/07/2026 17:42", 0.98),
            OCRLine("TRANS 84321", 0.96),
            OCRLine("Milk 3L 4.50", 0.94),
            OCRLine("2 ea @ $1.25 Bananas 2.50", 0.60),
            OCRLine("SUBTOTAL $7.00", 0.99),
            OCRLine("TOTAL $7.00", 0.99),
            OCRLine("GST $0.41", 0.98),
        )
    )

    parsed = parse_ocr_receipt(result)

    assert parsed.merchant == "Woolworths"
    assert parsed.purchase_date == date(2026, 7, 12)
    assert parsed.purchase_time == "17:42"
    assert parsed.transaction_number == "84321"
    assert parsed.subtotal_cents == 700
    assert parsed.total_cents == 700
    assert parsed.gst_cents == 41
    assert [item.line_total_cents for item in parsed.items] == [450, 250]
    assert parsed.items[1].quantity == 2
    assert any("extra attention" in warning for warning in parsed.warnings)


def test_generic_parser_does_not_treat_totals_as_items() -> None:
    result = OCRResult(
        (
            OCRLine("Other Market", 0.9),
            OCRLine("Bread $3.20", 0.9),
            OCRLine("SUB TOTAL $3.20", 0.9),
            OCRLine("TOTAL $3.20", 0.9),
        )
    )

    parsed = parse_ocr_receipt(result)

    assert [item.description for item in parsed.items] == ["Bread"]
    assert parsed.merchant == "Other Market"


def test_aldi_quantity_details_attach_to_previous_item_and_shift_prices() -> None:
    result = OCRResult(tuple(
        OCRLine(text, 0.98) for text in (
            "ALDI STORES",
            "562517 Alm Laund Cap 50pk 12.99 B",
            "399116 LaundrySoaker1kg 6.98 B",
            "Qty 2 @ $3.49 ea. 2.49 B",
            "618623 MultiPurpSponge5pk 1.98 B",
            "644945 Cloth Wipes 10pk",
            "Qty 2 @ $0.99 ea. 7.29 A",
            "398949 a2 Fl Crm Milk 2L $31.73",
            "Total (INCL GST) 31.73",
        )
    ))

    parsed = parse_ocr_receipt(result)

    assert [item.description for item in parsed.items] == [
        "562517 Alm Laund Cap 50pk",
        "399116 LaundrySoaker1kg",
        "618623 MultiPurpSponge5pk",
        "644945 Cloth Wipes 10pk",
        "398949 a2 Fl Crm Milk 2L",
    ]
    assert [item.line_total_cents for item in parsed.items] == [1299, 698, 249, 198, 729]
    assert [item.quantity for item in parsed.items] == [
        Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2"), Decimal("1")
    ]
    assert parsed.items[1].unit_price_cents == 349
    assert parsed.items[3].unit_price_cents == 99


def test_parser_reconstructs_bilingual_item_and_unknown_market_from_boxes() -> None:
    def line(text: str, confidence: float, box: tuple[int, int, int, int]) -> OCRLine:
        left, top, right, bottom = box
        return OCRLine(
            text,
            confidence,
            ((left, top), (right, top), (right, bottom), (left, bottom)),
        )

    result = OCRResult(
        (
            line("WING FAT MEAT MARKET", 0.99, (100, 10, 500, 50)),
            line("No：P2607250037", 0.98, (700, 100, 1000, 140)),
            line("Date:25/07/2026", 0.98, (100, 100, 400, 140)),
            line("$29.85", 0.99, (850, 200, 1000, 240)),
            line("瘦牛肉", 0.99, (100, 200, 250, 240)),
            line("lean beef", 0.99, (100, 250, 300, 290)),
            line("1.422kg @ $20.99/kg", 0.98, (100, 300, 500, 340)),
            line("TOTAL:$29.85", 0.99, (500, 400, 1000, 450)),
            line("Transaction: 25/07/2026 10:30:01", 0.99, (100, 500, 800, 540)),
        )
    )

    parsed = parse_ocr_receipt(result)

    assert parsed.merchant == "Wing Fat Meat Market"
    assert parsed.transaction_number == "P2607250037"
    assert parsed.total_cents == 2985
    assert len(parsed.items) == 1
    assert "lean beef" in parsed.items[0].description
    assert parsed.items[0].quantity == Decimal("1.422")
    assert parsed.items[0].unit_price_cents == 2099


def test_spatial_rows_do_not_chain_down_a_long_receipt() -> None:
    lines: list[OCRLine] = []
    for row, description in enumerate(("Bread", "Milk", "Eggs")):
        top = row * 30
        lines.extend(
            (
                OCRLine(
                    description,
                    0.98,
                    ((0, top), (100, top), (100, top + 20), (0, top + 20)),
                ),
                OCRLine(
                    f"{row + 1}.00",
                    0.99,
                    ((200, top + 3), (260, top + 3), (260, top + 23), (200, top + 23)),
                ),
            )
        )

    merged = _merge_spatial_rows(lines)

    assert [line.text for line in merged] == [
        "Bread 1.00",
        "Milk 2.00",
        "Eggs 3.00",
    ]


def test_rapidocr_adapter_normalises_v1_result_shape() -> None:
    def fake_engine(_image: Image.Image):
        return (
            [
                (
                    [[0, 0], [100, 0], [100, 20], [0, 20]],
                    "COLES",
                    0.97,
                )
            ],
            {"elapsed": 0.1},
        )

    result = RapidOCRAdapter(fake_engine).read(Image.new("RGB", (100, 100), "white"))

    assert result.lines[0].text == "COLES"
    assert result.lines[0].confidence == 0.97
    assert result.lines[0].box[2] == (100.0, 20.0)


def test_rapidocr_adapter_normalises_v3_numpy_result_shape() -> None:
    numpy = __import__("numpy")

    def fake_engine(_image: Image.Image):
        return SimpleNamespace(
            txts=numpy.array(["WING FAT MEAT MARKET", "TOTAL: $29.85"]),
            scores=numpy.array([0.98, 0.99]),
            boxes=numpy.array(
                [
                    [[0, 0], [100, 0], [100, 20], [0, 20]],
                    [[0, 30], [100, 30], [100, 50], [0, 50]],
                ]
            ),
        )

    result = RapidOCRAdapter(fake_engine).read(Image.new("RGB", (100, 100), "white"))

    assert [line.text for line in result.lines] == [
        "WING FAT MEAT MARKET",
        "TOTAL: $29.85",
    ]
    assert result.lines[1].confidence == 0.99
    assert result.lines[1].box[2] == (100.0, 50.0)


def test_normalize_image_returns_upright_supported_mode() -> None:
    image = Image.new("RGBA", (80, 40), (255, 255, 255, 128))

    normalized = normalize_image(image)

    assert normalized.mode == "RGB"
    assert normalized.size == (80, 40)
