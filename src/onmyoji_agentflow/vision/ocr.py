"""Optional OCR through PaddleOCR models in ONNX form (``rapidocr_onnxruntime``).

Install with ``pip install onmyoji-agentflow[ocr]``. Without it, OCR
detections report ``unavailable`` and workflows that need them stop with a
clear message instead of guessing.
"""
from __future__ import annotations

import re

import cv2
import numpy as np

_engine = None


class OcrUnavailable(RuntimeError):
    pass


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except ImportError as e:  # pragma: no cover - optional dependency
            raise OcrUnavailable("未安装 OCR：pip install onmyoji-agentflow[ocr]") from e
        _engine = RapidOCR()
    return _engine


def read_text(img: np.ndarray, roi=None) -> str:
    if roi is not None:
        x, y, w, h = (int(v) for v in roi)
        img = img[y:y + h, x:x + w]
    result, _ = _get_engine()(img)
    if not result:
        return ""
    return "".join(r[1] for r in result)


def read_number(img: np.ndarray, roi=None) -> int | None:
    """First integer in the area; '3/30' -> 3 (OAS uses the same convention for counters)."""
    text = read_text(img, roi)
    m = re.search(r"\d+", text.replace(" ", ""))
    return int(m.group(0)) if m else None


def read_boxes(img: np.ndarray, roi=None, pad: int = 24) -> list[tuple[str, int, int]]:
    """OCR the area; returns [(text, cx, cy)] in screen coordinates.

    The text detector misses words in tight crops, so the area is cut out with ``pad`` pixels of
    context and a white-ish border; only boxes whose centre lies inside ``roi`` are returned."""
    H, W = img.shape[:2]
    x, y, w, h = (0, 0, W, H) if roi is None else (int(v) for v in roi)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
    crop = img[y0:y1, x0:x1]
    crop = cv2.copyMakeBorder(crop, 16, 16, 16, 16, cv2.BORDER_REPLICATE)
    result, _ = _get_engine()(crop)
    out = []
    for box, text, _score in result or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = int(sum(xs) / len(xs)) + x0 - 16
        cy = int(sum(ys) / len(ys)) + y0 - 16
        if x <= cx < x + w and y <= cy < y + h:
            out.append((str(text), cx, cy))
    return out


def find_text(boxes: list[tuple[str, int, int]], words=None, pattern: str | None = None):
    """First box whose text contains one of ``words`` (or matches ``pattern``): (text, cx, cy)."""
    if isinstance(words, str):
        words = [words]
    for text, cx, cy in boxes:
        t = text.replace(" ", "")
        if words and any(w in t for w in words):
            return text, cx, cy
        if pattern and re.search(pattern, t):
            return text, cx, cy
    return None
