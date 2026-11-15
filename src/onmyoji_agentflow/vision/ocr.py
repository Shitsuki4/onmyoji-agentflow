"""Optional OCR through PaddleOCR models in ONNX form (``rapidocr_onnxruntime``).

Install with ``pip install onmyoji-agentflow[ocr]``. Without it, OCR
detections report ``unavailable`` and workflows that need them stop with a
clear message instead of guessing.
"""
from __future__ import annotations

import re

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
