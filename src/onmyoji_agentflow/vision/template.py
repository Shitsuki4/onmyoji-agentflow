"""Native OAS image matching; upstream source is never imported or executed.

The positional API retains legacy plain matching (including ROI growth and an
inclusive threshold). Explicit OAS masked/multi-scale methods use strict source
thresholds and a caller-supplied, already-expanded ``roi_back``. SIFT uses the
source's fixed feature/geometry tests, not a correlation threshold.
"""
from __future__ import annotations

import os
from functools import lru_cache
from numbers import Real
from pathlib import Path

import cv2
import numpy as np


@lru_cache(maxsize=512)
def load_image(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


class ImageMatch(tuple):
    """Backward-compatible three-tuple with method-specific evidence metadata.

    ``scale`` is the winning template scale, even below threshold, for the
    multi-scale method only. SIFT leaves ``score=-1`` and ``scale=None`` just as
    OAS does; its boolean must not be re-tested against a correlation threshold.
    Its box retains original template dimensions, not the projected bounding box.
    ``method`` retains source metadata; literal OAS ``Default`` dispatches to
    SIFT, exposed separately as ``effective_method``.
    """

    def __new__(cls, matched, score, box, *, method, roi, scale=None, mask_used=False,
                mask_fallback=None, reason=None, corners=None, good_matches=0):
        result = super().__new__(cls, (bool(matched), float(score), tuple(int(v) for v in box)))
        result.method, result.roi, result.scale = method, roi, scale
        result.effective_method = "Sift Flann" if method == "Default" else method
        result.mask_used, result.mask_fallback = mask_used, mask_fallback
        result.reason, result.corners, result.good_matches = reason, corners, good_matches
        return result

    matched = property(lambda self: self[0])
    score = property(lambda self: self[1])
    box = property(lambda self: self[2])


@lru_cache(maxsize=512)
def load_mask(path: str):
    """OAS sibling masks are decoded as uint8 grayscale; unreadable means absent."""
    try:
        return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_GRAYSCALE)
    except (OSError, ValueError, cv2.error):
        return None


def _mask_for(template, path, mask):
    if mask is None and path is not None:
        path = Path(path)
        mask = path.with_name(f"{path.stem}_mask{path.suffix}")
    if isinstance(mask, (str, os.PathLike)):
        mask = load_mask(str(mask))
        if mask is None:
            return None, "unavailable"
    if mask is None:
        return None, "not_provided"
    if not isinstance(mask, np.ndarray) or mask.ndim != 2 or mask.dtype != np.uint8:
        return None, "malformed"
    if mask.shape != template.shape[:2]:
        return None, "shape_mismatch"
    return mask, None


def _degenerate(template, mask=None):
    # CCOEFF_NORMED returns 1 for per-channel constants (or NaN with a
    # degenerate mask). Zero selected pixels must never fall back to plain.
    channels = template.shape[-1] if template.ndim == 3 else 1
    selected = template if mask is None else template[mask > 0]
    if selected.size == 0:
        return True
    samples = selected.reshape(-1, channels)
    return all(float(samples[:, channel].std()) == 0 for channel in range(channels))


def _best_match(area, template, mask=None):
    if mask is None:
        result = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
    else:
        result = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED, mask=mask)
    finite = np.isfinite(result)
    if not result.size or not finite.any():
        return -1.0, None
    result = np.nan_to_num(result, nan=-1.0, posinf=-1.0, neginf=-1.0)
    _, score, _, location = cv2.minMaxLoc(result)
    # Keep invalid positions from becoming evidence even with a negative threshold.
    return (float(score), location) if finite[location[1], location[0]] else (-1.0, None)


def match_template_above(img, path, anchor, *, x_pad, max_above, min_gap, x_weight, threshold):
    """Choose the qualifying template closest to the column above a matched image."""
    template = load_image(path)
    height, width = img.shape[:2]
    x, y, w, h = anchor
    if not 0 <= x < x + w <= width or not 0 <= y < y + h <= height:
        return None
    left = max(0, x - x_pad)
    right = min(width, x + w + x_pad)
    top, bottom = max(0, y - max_above), max(0, y - min_gap)
    th, tw = template.shape[:2]
    if right - left < tw or bottom - top < th or _degenerate(template):
        return None
    area = img[top:bottom, left:right]
    scores = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
    rows, columns = np.where(np.isfinite(scores) & (scores >= threshold))
    if not len(rows):
        return None
    x_distance = np.abs(left + columns + tw / 2 - (x + w / 2))
    y_distance = np.abs(top + rows + th / 2 - (y + h / 2))
    index = int(np.argmin(x_weight * x_distance + y_distance))
    return left + int(columns[index]), top + int(rows[index]), tw, th


def _scale_values(scales, scale_range):
    if scale_range is not None:
        if not isinstance(scale_range, (tuple, list)) or len(scale_range) not in (2, 3):
            raise ValueError("scale_range must be (start, end[, step])")
        values = list(scale_range) + ([0.1] if len(scale_range) == 2 else [])
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
               or not np.isfinite(value) for value in values):
            raise ValueError("scale_range requires finite numbers")
        start, end, step = values
        if start <= 0 or end < start or step <= 0:
            raise ValueError("scale_range requires 0 < start <= end and a positive step")
        count = (float(end) + float(step) - float(start)) / float(step)
        if not np.isfinite(count) or count > 4096:
            raise ValueError("scale_range exceeds the explicit 4096-step work bound")
        # OAS includes end + step and rounds to one decimal, including its
        # possible one-step overshoot for ranges not divisible by step.
        scales = np.arange(start, end + step, step)
    elif scales is None:
        return _scale_values(None, (0.6, 1.2))  # RuleImage.match dispatch default
    if not isinstance(scales, (list, tuple, np.ndarray)) or np.ndim(scales) != 1 or len(scales) > 4096:
        raise ValueError("scales must be a bounded one-dimensional sequence")
    if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
           or not np.isfinite(value) or value <= 0 for value in scales):
        raise ValueError("scales must contain finite positive numbers")
    return sorted(set(round(value, 1) for value in scales))


def _rectangle(points):
    # Source module/base/utils/utils.py:angle/is_approx_rectangle, atol=30deg.
    points = points.astype(np.float64)
    for index in range(4):
        p1, p2, p3 = points[index], points[(index + 1) % 4], points[(index + 2) % 4]
        first, second = p2 - p1, p3 - p2
        denominator = np.linalg.norm(first) * np.linalg.norm(second)
        if denominator == 0 or not np.isfinite(denominator):
            return False
        angle = np.degrees(np.arccos(np.clip(np.dot(first, second) / denominator, -1.0, 1.0)))
        if not np.isclose(angle, 90, atol=30):
            return False
    return True


def _sift_match(area, template, make_result, origin):
    factory = getattr(cv2, "SIFT_create", None)
    if factory is None:
        raise NotImplementedError("Sift Flann requires an OpenCV build with SIFT_create")
    if area.dtype != np.uint8 or template.dtype != np.uint8:
        return make_result(False, -1, reason="SIFT requires uint8 images")
    # Native frames/load_image are BGR. OAS passes RGB arrays to SIFT; preserve
    # those exact color inputs rather than changing its implicit grayscale mix.
    def rgb(image):
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if image.ndim == 3 and image.shape[2] == 3 else image

    try:
        sift = factory()
        source_points, source_des = sift.detectAndCompute(rgb(area), None)
        template_points, template_des = sift.detectAndCompute(rgb(template), None)
        if source_des is None or template_des is None or len(source_des) < 2 or not len(template_des):
            return make_result(False, -1, reason="insufficient SIFT descriptors")
        matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))
        pairs = matcher.knnMatch(template_des, source_des, k=2)
        good = []
        for pair in pairs:
            if len(pair) != 2:
                continue
            first, second = pair
            if (np.isfinite(first.distance) and np.isfinite(second.distance)
                    and first.distance < 0.6 * second.distance):
                good.append(first)
        if len(good) < 10:
            return make_result(False, -1, good_matches=len(good), reason="fewer than 10 SIFT ratio matches")
        source = np.float32([template_points[item.queryIdx].pt for item in good]).reshape(-1, 1, 2)
        target = np.float32([source_points[item.trainIdx].pt for item in good]).reshape(-1, 1, 2)
        matrix, _ = cv2.findHomography(source, target, cv2.RANSAC, 5.0)
        if matrix is None or not np.isfinite(matrix).all():
            return make_result(False, -1, good_matches=len(good), reason="invalid SIFT homography")
        height, width = template.shape[:2]
        corners = np.float32([[0, 0], [0, height - 1], [width - 1, height - 1], [width - 1, 0]]).reshape(-1, 1, 2)
        projected = cv2.perspectiveTransform(corners, matrix)
        if (not np.isfinite(projected).all() or np.abs(projected).max() >= np.iinfo(np.int32).max):
            return make_result(False, -1, good_matches=len(good), reason="nonfinite SIFT projection")
        projected = np.int32(projected).reshape(4, 2)  # source truncates before its angle test
        box = (int(projected[0, 0]) + origin[0], int(projected[0, 1]) + origin[1], width, height)
        evidence = tuple((int(x) + origin[0], int(y) + origin[1]) for x, y in projected)
        matched = _rectangle(projected)
        return make_result(matched, -1, box, corners=evidence, good_matches=len(good),
                           reason=None if matched else "SIFT projection is not approximately rectangular")
    except (cv2.error, IndexError, TypeError, ValueError):
        # OAS can raise on absent descriptors/bad homographies. An unusable
        # native observation is a non-match, never a fallback to correlation.
        return make_result(False, -1, reason="invalid SIFT feature geometry")


def match_template(img: np.ndarray, template: np.ndarray | str, roi=None, threshold: float = 0.8,
                    *, method="Template matching", mask=None, scales=None, scale_range=None, strict_roi=False,
                    template_crop=None):
    """Return ``(matched, score, (x,y,w,h))`` plus ``ImageMatch`` metadata.

    ``roi`` is xywh in frame coordinates; new methods crop exactly that ROI,
    clipped to the frame. Apply OAS's 2px ROI_BACK_EXPAND once in the caller.
    Masked matching auto-loads ``<stem>_mask<suffix>`` for a path template. Missing,
    undecodable, wrong-size or non-uint8/grayscale masks fall back to ordinary
    CCOEFF; all-zero or selected-flat masks reject the observation.

    Multi-scale defaults to RuleImage.match's 0.6..1.2 by 0.1. Explicit scales or
    scale_range reproduce match_multi_scale's rounding/order/resize/strict best
    selection; call sites using its direct 0.5..1.2 default must pass those scales.
    Scales below 10px are skipped; grids over 4096 steps are explicitly rejected.
    Literal ``Default`` follows RuleImage.match's non-template fallback to SIFT,
    not the legacy native default argument. Unknown labels remain explicit errors.
    """
    if method not in ("Template matching", "Masked template matching", "Multi-scale template matching", "Sift Flann", "Default"):
        raise ValueError(f"Unsupported image matching method: {method!r}")
    path = template if isinstance(template, (str, os.PathLike)) else None
    if isinstance(template, (str, os.PathLike)):
        template = load_image(str(template))
    if not isinstance(template, np.ndarray) or template.ndim not in (2, 3):
        raise ValueError("template must be a decoded grayscale or color image")
    if template_crop is not None:
        from .regions import checked_box
        if method != "Template matching":
            raise ValueError("template_crop requires ordinary template matching")
        tx, ty, width, height = checked_box(template_crop, template, integral=True)
        template = template[ty:ty + height, tx:tx + width]
    h, w = img.shape[:2]
    if roi is None:
        rx, ry, rw, rh = 0, 0, w, h
    else:
        rx, ry, rw, rh = (int(v) for v in roi)
    th, tw = template.shape[:2]
    if method == "Template matching" and not strict_roi:
        # Preserve the old native signature's ROI growth; new OAS methods must
        # not grow or move an explicitly restricted search region.
        rw, rh = max(rw, tw), max(rh, th)
        rx, ry = max(0, min(rx, w - rw)), max(0, min(ry, h - rh))
    else:
        right, bottom = min(w, max(0, rx + rw)), min(h, max(0, ry + rh))
        rx, ry = min(w, max(0, rx)), min(h, max(0, ry))
        rw, rh = max(0, right - rx), max(0, bottom - ry)
    area = img[ry:ry + rh, rx:rx + rw]
    used_mask, fallback = _mask_for(template, path, mask) if method == "Masked template matching" else (None, None)

    def result(matched, score, box=None, **metadata):
        return ImageMatch(matched, score, box if box is not None else (0, 0, tw, th),
                          method=method, roi=(rx, ry, area.shape[1], area.shape[0]),
                          mask_used=used_mask is not None, mask_fallback=fallback, **metadata)

    if not area.size or not template.size or not np.isfinite(template).all() or not np.isfinite(area).all():
        return result(False, -1, reason="empty or nonfinite image")
    if method in ("Sift Flann", "Default"):
        return _sift_match(area, template, result, (rx, ry))
    if _degenerate(template, used_mask):
        return result(False, -1, reason="flat template or empty matching mask")
    if method == "Multi-scale template matching":
        best_score, best_location, best_scale, best_shape = 0.0, None, None, None
        for scale in _scale_values(scales, scale_range):
            with np.errstate(over="ignore", invalid="ignore"):
                scaled_width, scaled_height = tw * scale, th * scale
            if not np.isfinite(scaled_width) or not np.isfinite(scaled_height):
                continue
            sw, sh = int(scaled_width), int(scaled_height)
            if sw < 10 or sh < 10 or sw > area.shape[1] or sh > area.shape[0]:
                continue
            try:
                scaled = cv2.resize(template, (sw, sh))
                if _degenerate(scaled):
                    continue
                score, location = _best_match(area, scaled)
            except cv2.error:
                continue
            if location is not None and score > best_score:
                best_score, best_location, best_scale, best_shape = score, location, float(scale), (sw, sh)
        box = (rx + best_location[0], ry + best_location[1], *best_shape) if best_location is not None else None
        return result(best_location is not None and best_score > threshold, best_score, box, scale=best_scale)
    if area.shape[0] < th or area.shape[1] < tw:
        return result(False, 0, reason="template exceeds search ROI")
    score, location = _best_match(area, template, used_mask)
    box = (rx + location[0], ry + location[1], tw, th) if location is not None else None
    matched = location is not None and (score >= threshold if method == "Template matching" and not strict_roi else score > threshold)
    return result(matched, score, box)
