"""Template matching (OAS ``RuleImage`` style: search ``roi_back`` for the template)."""
from __future__ import annotations

import os
from functools import lru_cache

import cv2
import numpy as np


@lru_cache(maxsize=512)
def load_image(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


def match_template(img: np.ndarray, template: np.ndarray | str, roi=None, threshold: float = 0.8):
    """Return (matched, score, (x, y, w, h)) of the best match inside ``roi`` (x, y, w, h)."""
    if isinstance(template, (str, os.PathLike)):
        template = load_image(str(template))
    h, w = img.shape[:2]
    if roi is None:
        rx, ry, rw, rh = 0, 0, w, h
    else:
        rx, ry, rw, rh = (int(v) for v in roi)
    th, tw = template.shape[:2]
    # Grow the ROI so the template always fits (OAS does the same when roi_back is tight)
    rw, rh = max(rw, tw), max(rh, th)
    rx = max(0, min(rx, w - rw))
    ry = max(0, min(ry, h - rh))
    area = img[ry:ry + rh, rx:rx + rw]
    if area.shape[0] < th or area.shape[1] < tw:
        return False, 0.0, (0, 0, tw, th)
    res = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    box = (rx + loc[0], ry + loc[1], tw, th)
    return bool(score >= threshold), float(score), box
