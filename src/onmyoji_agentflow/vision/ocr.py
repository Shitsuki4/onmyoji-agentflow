"""Optional OCR through PaddleOCR models in ONNX form (``rapidocr_onnxruntime``).

Install with ``pip install onmyoji-agentflow[ocr]``. Without it, OCR
detections report ``unavailable`` and workflows that need them stop with a
clear message instead of guessing.
"""
from __future__ import annotations

import re
import math
import unicodedata

import cv2
import numpy as np

_engine = None
_single_engine = None


def parse_hourly_rate(text: str, label: str) -> int | None:
    """Read a complete resource rate such as 勾玉+9/h."""
    normalized = "".join(unicodedata.normalize("NFKC", text).split())
    match = re.fullmatch(re.escape(label) + r"\+([0-9]{1,5})/(?:h|小时)", normalized)
    return int(match[1]) if match else None


class OcrUnavailable(RuntimeError):
    pass


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except ImportError as e:  # pragma: no cover - optional dependency
            raise OcrUnavailable("未安装 OCR：pip install onmyoji-agentflow[ocr]") from e
        _engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
    return _engine


def _get_single_engine():
    global _single_engine
    if _single_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except ImportError as e:  # pragma: no cover - optional dependency
            raise OcrUnavailable("未安装 OCR：pip install onmyoji-agentflow[ocr]") from e
        # Keep raw confidences for the source's >= / > boundary decisions.
        # A separate engine avoids changing the existing detector's threshold.
        _single_engine = RapidOCR(text_score=0.0, intra_op_num_threads=2, inter_op_num_threads=1)
    return _single_engine


# OAS-derived Single confidence/padding/order contract: GPL-3.0, runhey and contributors.
def read_single(img: np.ndarray, roi, score: float = .6) -> str:
    """OAS Single's whole-line result, then its first eligible vertical result.

    Source normalization is identity: spaces and punctuation are preserved.
    The recognition backend is native RapidOCR rather than importing OAS.
    An invalid crop or malformed model result raises; it cannot make a negated
    observation authorize an input. No text boxes are joined or searched.
    """
    if (not isinstance(roi, (list, tuple)) or len(roi) != 4 or
            any(type(v) is not int for v in roi) or min(roi[:2]) < 0 or min(roi[2:]) <= 0 or
            img.ndim != 3 or img.shape[2] != 3):
        raise ValueError("ocr_single needs a valid BGR crop and integer xywh region")
    x, y, width, height = roi
    if x + width > img.shape[1] or y + height > img.shape[0]:
        raise ValueError("ocr_single region is outside the current frame")
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("ocr_single score must be finite and in 0..1")
    crop = img[y:y + height, x:x + width]
    engine = _get_single_engine()

    def result_text(value):
        if (not isinstance(value, (list, tuple)) or len(value) != 2 or
                not isinstance(value[0], str) or isinstance(value[1], (bool, str))):
            raise ValueError("invalid single OCR result")
        confidence = float(value[1])
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid single OCR confidence")
        return value[0], confidence

    lines, _ = engine(crop, use_det=False, use_cls=False, use_rec=True)
    if lines:
        if len(lines) != 1:
            raise ValueError("single OCR returned multiple unsegmented lines")
        text, confidence = result_text(lines[0])
        if text and confidence >= score:
            return text

    # BaseCor.enlarge_canvas pads only bottom/right to the NEXT multiple of 32.
    length = max(width, height) // 32 * 32 + 32
    padded = cv2.copyMakeBorder(crop, 0, length - height, 0, length - width,
                                cv2.BORDER_CONSTANT, value=(0, 0, 0))
    detected, _ = engine(padded, use_det=True, use_cls=False, use_rec=True)
    rows = []
    for item in detected or []:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError("invalid vertical OCR result")
        box = np.asarray(item[0], dtype=float)
        if box.shape != (4, 2) or not np.isfinite(box).all():
            raise ValueError("invalid vertical OCR bounding box")
        text, confidence = result_text(item[1:])
        rows.append((box, text, confidence))
    # OAS ppocr.sorted_boxes sorts rows then swaps close rows by their x value.
    rows.sort(key=lambda row: (row[0][0][1], row[0][0][0]))
    for index in range(len(rows) - 1):
        for position in range(index, -1, -1):
            left, right = rows[position][0][0], rows[position + 1][0][0]
            if abs(right[1] - left[1]) < 10 and right[0] < left[0]:
                rows[position], rows[position + 1] = rows[position + 1], rows[position]
            else:
                break
    eligible = [row for row in rows if row[2] >= score]
    if eligible:
        _, text, confidence = eligible[0]
        if text and confidence > score:  # Source's fallback is strictly greater.
            return text
    return ""


class FullOcrArea(tuple):
    """Source-compatible xywh plus native provenance for guarded consumers."""

    def __new__(cls, area, *, keyword_complete):
        if type(keyword_complete) is not bool:
            raise ValueError("keyword_complete must be boolean")
        value = super().__new__(cls, area)
        value.keyword_complete = keyword_complete
        return value


# OAS Full/BaseCor/merge_area contract: GPL-3.0, runhey and contributors.
def read_full(img: np.ndarray, roi, keyword: str, score: float = .6, *, selection="source") -> tuple:
    """Full-mode keyword area, including the audited source's filtering quirks.

    A missing result is (0,0,0,0). Multiple matches retain the source merge of
    min(x/y), max(width/height), rather than silently fixing it to a union.
    The per-character fallback can select partial words; callers must supply
    their own UI context before using an area to authorize input.
    """
    from .regions import checked_box
    roi = checked_box(roi, img, integral=True)
    if (not isinstance(keyword, str) or not keyword or type(score) not in (int, float)
            or not math.isfinite(score) or not 0 <= score <= 1):
        raise ValueError("ocr_full needs a nonempty keyword and finite score in 0..1")
    if selection not in ("source", "unique_contains", "unique_equals", "first_contains"):
        raise ValueError("invalid Full OCR selection")
    x, y, width, height = roi
    crop = img[y:y + height, x:x + width]
    length = max(width, height) // 32 * 32 + 32
    padded = cv2.copyMakeBorder(crop, 0, length - height, 0, length - width,
                                cv2.BORDER_CONSTANT, value=(0, 0, 0))
    detected, _ = _get_single_engine()(padded, use_det=True, use_cls=False, use_rec=True)
    rows = []
    for item in detected or []:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError("invalid full OCR result")
        box, text, confidence = np.asarray(item[0], dtype=float), item[1], item[2]
        if (box.shape != (4, 2) or not np.isfinite(box).all() or not isinstance(text, str)
                or isinstance(confidence, (bool, str))):
            raise ValueError("invalid full OCR bounding box or text")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid full OCR confidence")
        rows.append((box, text, confidence))
    # ppocr's order is part of the filter's concatenated-string behavior.
    rows.sort(key=lambda row: (row[0][0][1], row[0][0][0]))
    for index in range(len(rows) - 1):
        for position in range(index, -1, -1):
            left, right = rows[position][0][0], rows[position + 1][0][0]
            if abs(right[1] - left[1]) < 10 and right[0] < left[0]:
                rows[position], rows[position + 1] = rows[position + 1], rows[position]
            else:
                break
    rows = [row for row in rows if row[2] >= score]
    strings = [row[1] for row in rows]
    if selection == "unique_equals":
        indices = [i for i, word in enumerate(strings) if keyword == word]
    elif selection == "unique_contains":
        indices = [i for i, word in enumerate(strings) if keyword in word]
    elif selection == "first_contains":
        indices = [i for i, word in enumerate(strings) if keyword in word][:1]
    elif keyword in "".join(strings):
        indices = [i for i, word in enumerate(strings) if keyword in word]
    else:
        indices = []
        for char in keyword:
            for i, word in enumerate(strings):
                if char in word:
                    indices.append(i)
                    break
        indices = sorted(set(indices))
    if not indices or (selection != "source" and len(indices) != 1):
        return FullOcrArea((0, 0, 0, 0), keyword_complete=False)
    areas = [(float(rows[i][0][0, 0]), float(rows[i][0][0, 1]),
              float(rows[i][0][1, 0] - rows[i][0][0, 0]),
              float(rows[i][0][2, 1] - rows[i][0][0, 1])) for i in indices]
    area = (min(a[0] for a in areas) + x, min(a[1] for a in areas) + y,
            max(a[2] for a in areas), max(a[3] for a in areas))
    checked_box(area, img)
    if selection != "source":
        ax, ay, aw, ah = area
        if ax < x or ay < y or ax + aw > x + width or ay + ah > y + height:
            return FullOcrArea((0, 0, 0, 0), keyword_complete=False)
    return FullOcrArea(area, keyword_complete=any(keyword in word for word in strings))


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


def read_boxes(img: np.ndarray, roi=None, pad: int = 24, *, min_score=None) -> list[tuple[str, int, int]]:
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
    for box, text, score in result or []:
        if min_score is not None and not float(score) > min_score:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = int(sum(xs) / len(xs)) + x0 - 16
        cy = int(sum(ys) / len(ys)) + y0 - 16
        if x <= cx < x + w and y <= cy < y + h:
            out.append((str(text), cx, cy))
    return out


def ordered_list_position(rows, labels, target):
    """Return the target point or the direction indicated by a recognized ordered viewport."""
    order = {label: index for index, aliases in enumerate(labels) for label in aliases}
    target_index = order[target]
    visible = [(order[label], x, y) for text, x, y in rows if (label := "".join(text.split())) in order]
    visible.sort(key=lambda row: row[2])
    indices = [index for index, _, _ in visible]
    if not indices or indices != sorted(set(indices)):
        return None, None
    if target_index in indices:
        _, x, y = visible[indices.index(target_index)]
        return 0, (x, y)
    if target_index < indices[0]:
        return -1, None
    if target_index > indices[-1]:
        return 1, None
    return None, None


def parse_oas_duration(text: str) -> int | None:
    """Read a complete OAS duration and distinguish unreadable text from zero."""
    corrected = text.translate(str.maketrans("IDSolOB：.", "1050108::"))
    corrected = "".join(corrected.split())
    match = re.fullmatch(r"([0-9]{1,2}):?([0-5][0-9]):?([0-5][0-9])", corrected)
    if match is None:
        return None
    hours, minutes, seconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds


def parse_oas_cn_hour_minute(text: str) -> int | None:
    """Read an OAS Chinese countdown such as '3时25分后可' into seconds."""
    token = "".join(unicodedata.normalize("NFKC", text).split())
    match = re.search(r"(?<![0-9])([0-9]{1,2})时([0-5]?[0-9])分后可", token)
    if match is None:
        return None
    hours, minutes = map(int, match.groups())
    if hours > 24 or minutes >= 60:
        return None
    return hours * 3600 + minutes * 60


def parse_oas_remaining_times(text: str) -> int | None:
    """Read an OAS remaining-count badge such as '剩2次' or '剩余3次'."""
    token = "".join(unicodedata.normalize("NFKC", text).split())
    match = re.search(r"剩余?([0-9]{1,2})次", token)
    return int(match[1]) if match else None


def parse_exact_quantity(text: str) -> int | None:
    """Read a complete integer display without estimating abbreviated balances."""
    text = text.strip().replace("，", ",")
    if not re.fullmatch(r"[0-9]{1,12}|[0-9]{1,3}(?:,[0-9]{3}){1,3}", text):
        return None
    return int(text.replace(",", ""))


def parse_shop_stock(text: str) -> int | None:
    token = "".join(text.split())
    match = re.fullmatch(r"(?:剩余购买次数|购买次数|本周剩余数量)[:：]?([0-9]{1,3})", token)
    return int(match[1]) if match else None


def parse_oas_counter_current(text: str) -> int | None:
    """Read a complete current/total currency counter without glyph substitution."""
    match = re.fullmatch(r"([0-9]{1,12})\s*[/／]\s*([0-9]{1,12})", text.strip())
    if match is None:
        return None
    current, total = map(int, match.groups())
    return current if current <= total and total > 0 else None


def parse_oas_counter_remaining(text: str) -> int | None:
    """Read remaining count from a single, valid OAS DigitCounter pair."""
    corrected = text.translate(str.maketrans("IDSB？?doO→", "1058226001"))
    match = re.fullmatch(r"([0-9]+)\s*/\s*([0-9]+)", corrected.strip())
    if match is None:
        return None
    current, total = map(int, match.groups())
    return total - current if 0 <= current <= total and total > 0 else None


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
