"""Test helpers: synthesise 1280x720 frames that satisfy a state's condition."""
from __future__ import annotations

import itertools

import numpy as np

from onmyoji_agentflow.vision.colors import parse_color


def blank(value: int = 40) -> np.ndarray:
    return np.full((720, 1280, 3), value, np.uint8)


def paint_points(img: np.ndarray, points, dx: int = 0, dy: int = 0) -> None:
    for x, y, c in points:
        r, g, b = parse_color(c)
        img[int(y) + dy, int(x) + dx] = (b, g, r)


def paint_condition(img: np.ndarray, cond: dict, resources: dict) -> None:
    if "colors" in cond:
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
            paint_condition(img, c, resources)
    elif "any" in cond:
        paint_condition(img, cond["any"][0], resources)
    elif "expr" in cond or "not" in cond:
        pass
    else:
        raise ValueError(cond)


def frame_for(wf, state_id: str, base: int = 40) -> np.ndarray:
    img = blank(base)
    st = next(s for s in wf.states if s["id"] == state_id)
    paint_condition(img, st["when"], wf.resources)
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
