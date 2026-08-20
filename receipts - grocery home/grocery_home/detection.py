"""Local tiled YOLO receipt-region detection using ONNX Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


CLASS_NAMES = (
    "Address", "Date", "Item", "OrderId", "Subtotal", "Tax", "Title", "TotalPrice"
)


@dataclass(frozen=True, slots=True)
class ReceiptRegion:
    label: str
    confidence: float
    box: tuple[int, int, int, int]


class ReceiptRegionDetector(Protocol):
    def detect(self, image: Image.Image) -> list[ReceiptRegion]: ...


class YOLOReceiptDetector:
    """Detect semantic regions in overlapping full-width receipt tiles."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        *,
        session: Any | None = None,
        confidence: float = 0.30,
        tile_aspect: float = 1.25,
        tile_overlap: float = 0.25,
    ) -> None:
        self.model_path = Path(model_path or Path(__file__).with_name("receipt_layout.onnx"))
        self._session = session
        self.confidence = confidence
        self.tile_aspect = tile_aspect
        self.tile_overlap = tile_overlap

    @property
    def available(self) -> bool:
        return self._session is not None or self.model_path.is_file()

    def _get_session(self) -> Any:
        if self._session is None:
            import onnxruntime as ort  # type: ignore[import-not-found]

            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
        return self._session

    def detect(self, image: Image.Image) -> list[ReceiptRegion]:
        import numpy as np

        if not self.available:
            return []
        rgb = image.convert("RGB")
        found: list[ReceiptRegion] = []
        for top, bottom in self._tiles(rgb.width, rgb.height):
            tile = rgb.crop((0, top, rgb.width, bottom))
            array = np.asarray(tile.resize((640, 640)), dtype=np.float32) / 255.0
            tensor = np.transpose(array, (2, 0, 1))[None]
            session = self._get_session()
            output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
            found.extend(self._decode(output, rgb.width, bottom - top, top))
        return merge_regions(found)

    def _tiles(self, width: int, height: int) -> list[tuple[int, int]]:
        tile_height = min(height, max(width, round(width * self.tile_aspect)))
        if tile_height >= height:
            return [(0, height)]
        step = max(1, round(tile_height * (1.0 - self.tile_overlap)))
        starts = list(range(0, height - tile_height + 1, step))
        final = height - tile_height
        if starts[-1] != final:
            starts.append(final)
        return [(start, start + tile_height) for start in starts]

    def _decode(
        self, output: Any, tile_width: int, tile_height: int, top: int
    ) -> list[ReceiptRegion]:
        import numpy as np

        predictions = np.asarray(output)[0]
        if predictions.shape[0] == 4 + len(CLASS_NAMES):
            predictions = predictions.T
        regions: list[ReceiptRegion] = []
        for row in predictions:
            class_id = int(np.argmax(row[4:]))
            score = float(row[4 + class_id])
            if score < self.confidence:
                continue
            cx, cy, width, height = (float(value) for value in row[:4])
            left = max(0, round((cx - width / 2) * tile_width / 640))
            right = min(tile_width, round((cx + width / 2) * tile_width / 640))
            upper = max(0, round((cy - height / 2) * tile_height / 640)) + top
            lower = min(tile_height, round((cy + height / 2) * tile_height / 640)) + top
            if right > left and lower > upper:
                regions.append(
                    ReceiptRegion(CLASS_NAMES[class_id], score, (left, upper, right, lower))
                )
        return regions


def merge_regions(regions: list[ReceiptRegion]) -> list[ReceiptRegion]:
    """Merge tile duplicates; union adjoining Item predictions transitively."""

    pending = sorted(regions, key=lambda region: region.confidence, reverse=True)
    merged: list[ReceiptRegion] = []
    while pending:
        current = pending.pop(0)
        group = [current]
        changed = True
        while changed:
            changed = False
            remainder = []
            union_box = _union([entry.box for entry in group])
            for candidate in pending:
                same_label = candidate.label == current.label
                overlap = _intersection_over_smaller(union_box, candidate.box)
                threshold = 0.20 if current.label == "Item" else 0.55
                if same_label and overlap >= threshold:
                    group.append(candidate)
                    changed = True
                else:
                    remainder.append(candidate)
            pending = remainder
        merged.append(
            ReceiptRegion(current.label, max(entry.confidence for entry in group), _union([entry.box for entry in group]))
        )
    return sorted(merged, key=lambda region: (region.box[1], region.box[0]))


def _union(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    return (
        min(box[0] for box in boxes), min(box[1] for box in boxes),
        max(box[2] for box in boxes), max(box[3] for box in boxes),
    )


def _intersection_over_smaller(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> float:
    width = max(0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0, min(first[3], second[3]) - max(first[1], second[1]))
    intersection = width * height
    smaller = min(
        (first[2] - first[0]) * (first[3] - first[1]),
        (second[2] - second[0]) * (second[3] - second[1]),
    )
    return intersection / smaller if smaller else 0.0
