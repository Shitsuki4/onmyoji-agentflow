"""Test helpers: synthesise 1280x720 frames that satisfy a state's condition."""
from __future__ import annotations

import hashlib
import itertools

import numpy as np

from onmyoji_agentflow.vision.colors import parse_color


def blank(value: int = 40) -> np.ndarray:
    return np.full((720, 1280, 3), value, np.uint8)


def paint_points(img: np.ndarray, points, dx: int = 0, dy: int = 0) -> None:
    for x, y, c in points:
        r, g, b = parse_color(c)
        img[int(y) + dy, int(x) + dx] = (b, g, r)


# text a synthetic frame "shows": sha1(frame bytes) -> [(text, cx, cy)], read back by fake_text_reader
FRAME_TEXTS: dict[str, list] = {}


def _key(img: np.ndarray) -> str:
    return hashlib.sha1(np.ascontiguousarray(img).tobytes()).hexdigest()


def register_texts(img: np.ndarray, texts: list) -> np.ndarray:
    FRAME_TEXTS[_key(img)] = list(texts)
    return img


def fake_text_reader(img: np.ndarray, region=None):
    """Stand-in for OCR: the texts painted into the frame that lie inside ``region``."""
    out = FRAME_TEXTS.get(_key(img), [])
    if region is None:
        return list(out)
    x, y, w, h = region
    return [(t, cx, cy) for t, cx, cy in out if x <= cx < x + w and y <= cy < y + h]


def _text_for(cond: dict) -> str:
    words = cond.get("text")
    if isinstance(words, list):
        words = words[0]
    if words:
        return words
    pat = cond.get("pattern", "")
    return {r"刷新\d{1,2}[:：]\d{2}": "刷新04:59",
            r"第\s*\d+\s*签": "第208签"}.get(pat, pat)


def paint_condition(img: np.ndarray, cond: dict, resources: dict, texts: list | None = None) -> None:
    if "text" in cond:
        x, y, w, h = cond.get("region", (0, 0, 1280, 720))
        if texts is not None:
            texts.append((_text_for(cond), x + w // 2, y + h // 2))
    elif "colors" in cond:
        paint_points(img, cond["colors"])
    elif "res" in cond or "find" in cond:
        spec = resources[cond.get("res") or cond.get("find")]
        if spec["type"] == "colors":
            paint_points(img, spec["points"])
        else:
            region = cond.get("region", spec["region"])
            group = spec["groups"][0]
            ax, ay = group[0][0], group[0][1]
            # place the pattern so that its anchor lies inside the region
            tx = min(max(ax, region[0] + 5), region[2] - 5)
            ty = min(max(ay, region[1] + 5), region[3] - 5)
            paint_points(img, group, tx - ax, ty - ay)
    elif "all" in cond:
        for c in cond["all"]:
            paint_condition(img, c, resources, texts)
    elif "any" in cond:
        paint_condition(img, cond["any"][0], resources, texts)
    elif "expr" in cond or "not" in cond:
        pass
    else:
        raise ValueError(cond)


def frame_for(wf, state_id: str, base: int = 40) -> np.ndarray:
    img = blank(base)
    st = next(s for s in wf.states if s["id"] == state_id)
    texts: list = []
    paint_condition(img, st["when"], wf.resources, texts)
    if texts:
        register_texts(img, texts)
    return img


class FakeClock:
    def __init__(self, step: float = 0.5):
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def counter():
    return itertools.count()
