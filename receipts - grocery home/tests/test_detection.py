from __future__ import annotations

from PIL import Image

from grocery_home.detection import ReceiptRegion, YOLOReceiptDetector, merge_regions
from grocery_home.ocr import OCRLine, OCRResult, parse_detected_receipt


class _Input:
    name = "images"


class FakeSession:
    def __init__(self, output):
        self.output = output

    def get_inputs(self):
        return [_Input()]

    def run(self, _outputs, inputs):
        assert inputs["images"].shape == (1, 3, 640, 640)
        return [self.output]


class SequencedOCR:
    def __init__(self, results):
        self.results = iter(results)

    def read(self, _image):
        return next(self.results)


def test_tiled_detector_maps_predictions_to_original_coordinates():
    import numpy as np

    output = np.zeros((1, 12, 8400), dtype=np.float32)
    output[0, :4, 0] = (320, 320, 320, 320)
    output[0, 6, 0] = 0.9  # class 2: Item
    detector = YOLOReceiptDetector(session=FakeSession(output), confidence=0.5)

    regions = detector.detect(Image.new("RGB", (800, 800)))

    assert [(region.label, region.box) for region in regions] == [
        ("Item", (200, 200, 600, 600))
    ]
    assert round(regions[0].confidence, 2) == 0.9


def test_item_regions_from_overlapping_tiles_are_unioned():
    merged = merge_regions([
        ReceiptRegion("Item", 0.8, (10, 100, 500, 500)),
        ReceiptRegion("Item", 0.7, (15, 420, 510, 800)),
        ReceiptRegion("TotalPrice", 0.9, (200, 820, 500, 880)),
    ])

    assert merged[0].box == (10, 100, 510, 800)
    assert merged[0].label == "Item"


def test_region_items_only_replace_whole_ocr_when_they_balance_better():
    whole = OCRResult((
        OCRLine("ALDI", 0.99), OCRLine("21/07/2026", 0.99),
        OCRLine("Bad item 1.00", 0.9), OCRLine("TOTAL 5.00", 0.99),
    ))
    regional = OCRResult((
        OCRLine("Good item 5.00", 0.98),
    ))
    adapter = SequencedOCR([regional])

    parsed = parse_detected_receipt(
        Image.new("RGB", (500, 1000)), adapter,
        [ReceiptRegion("Item", 0.9, (0, 100, 500, 800))],
        whole_result=whole,
    )

    assert parsed.total_cents == 500
    assert [(item.description, item.line_total_cents) for item in parsed.items] == [
        ("Good item", 500)
    ]
    assert not parsed.warnings
