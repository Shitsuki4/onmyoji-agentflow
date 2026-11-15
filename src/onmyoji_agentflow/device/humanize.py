"""Click / swipe point selection and delays, ported from two mature projects.

Nothing here is a guarantee against detection: it only reproduces what
OnmyojiAutoScript (OAS) and assttyys_autojs already do.

* ``style="oas"`` (default): points come from OAS
  ``module/base/utils/utils.py::random_rectangle_point`` (a normal distribution
  centred on the rectangle, n=3) and swipes follow OAS's ``insert_swipe``
  bezier path when the backend supports point-by-point input (MuMu nemu_ipc).
  GPLv3, see ``device/_oas``.
* ``style="assttyys"``: points come from assttyys ``getRegionBiasRnd2`` around a
  per-device bias point (``strHashToNum`` of a device id), press time is
  ``random(10, 60)`` ms and the delay after an operation is ``getNormalRandom``
  between ``[delay+base, delay+base+random]`` - ported from
  ``src/system/helperBridge.ts`` and ``src/common/toolAuto.ts``.
  assttyys_autojs: MIT License, Copyright (c) 2019 Chaos (zzliux). See NOTICE.md.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ._oas.utils import random_rectangle_point

Rect = tuple[int, int, int, int]  # x1, y1, x2, y2 (inclusive), in 1280x720 space


# ---------------------------------------------------------------- assttyys port
def str_hash_to_num(text: str, start: float, end: float) -> float:
    """Port of assttyys ``strHashToNum``: a stable value inside the middle half of [start, end]."""
    s_start = (end - start) / 4 + start
    s_end = (start - end) / 4 + end
    factor = 13
    total = sum(ord(c) * factor for c in text)
    span = s_end - s_start - 1
    if span <= 0:  # tiny regions: JS would produce NaN here; use the centre instead
        return (start + end) / 2
    return (total * max(total % factor, 1)) % span + s_start


def get_normal_random(rng: tuple[float, float], mean: float, _depth: int = 0) -> float:
    """Port of assttyys ``getNormalRandom``."""
    lo, hi = rng
    if lo == hi:
        return lo
    if lo > hi:
        return get_normal_random((hi, lo), mean)
    mean = min(max(mean, lo), hi)
    m = min(hi - mean, mean - lo)
    if m <= 0:
        return float(math.floor(mean))
    std = (hi - lo) / ((hi - lo) * 4 / m)
    for _ in range(1000):
        u = random.random() or 1e-12
        v = random.random() or 1e-12
        z = math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)
        num = z * std + mean
        if lo <= num <= hi:
            return float(math.floor(num))
    return float(math.floor(mean))


def get_region_bias_rnd2(region: Rect, bias: tuple[float, float], influence: float = 1.0) -> tuple[float, float]:
    """Port of assttyys ``getRegionBiasRnd2`` (2-D normal around ``bias``, retried inside region)."""
    x1, y1, x2, y2 = region
    for _ in range(64):
        sd_x = 0.1 / (influence * influence) * (x2 - x1)
        sd_y = 0.1 / (influence * influence) * (y2 - y1)
        u = random.random() or 1e-12
        v = random.random() or 1e-12
        r = math.sqrt(-2.0 * math.log(u))
        x = bias[0] + r * math.cos(2.0 * math.pi * v) * sd_x
        y = bias[1] + r * math.sin(2.0 * math.pi * v) * sd_y
        if x1 <= x <= x2 and y1 <= y <= y2:
            return x, y
        influence *= 2
    return (x1 + x2) / 2, (y1 + y2) / 2


# ---------------------------------------------------------------- public API
@dataclass
class HumanizeConfig:
    style: str = "oas"           # "oas" or "assttyys"
    device_id: str = "default"   # assttyys bias seed (assttyys uses the Android id)
    base_sleep_ms: int = 0        # assttyys afterClickDelay
    random_sleep_ms: int = 200    # assttyys afterClickDelayRandom (default 200 in assttyys)
    swipe_duration_ms: tuple[int, int] = (300, 600)


def normalize_rect(rect) -> Rect:
    x1, y1, x2, y2 = (int(round(v)) for v in rect[:4])
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def pick_point(rect, cfg: HumanizeConfig) -> tuple[int, int]:
    """Choose the point to press inside ``rect`` (x1, y1, x2, y2)."""
    x1, y1, x2, y2 = normalize_rect(rect)
    if x1 == x2 and y1 == y2:
        return x1, y1
    if cfg.style == "assttyys":
        bias = (str_hash_to_num(cfg.device_id, x1, x2), str_hash_to_num(cfg.device_id, y1, y2))
        x, y = get_region_bias_rnd2((x1, y1, x2, y2), bias, 1)
        return int(x), int(y)
    # OAS: random_rectangle_point takes (upper_left_x, upper_left_y, bottom_right_x, bottom_right_y)
    x, y = random_rectangle_point((x1, y1, x2, y2), n=3)
    return int(x), int(y)


def press_ms(cfg: HumanizeConfig, hint: int | None = None) -> int:
    """assttyys: ``item[5] ? random(item[5], item[5]+50) : random(10, 60)``."""
    if hint:
        return random.randint(int(hint), int(hint) + 50)
    return random.randint(10, 60)


def after_delay_ms(cfg: HumanizeConfig, delay_ms: int) -> int:
    """Delay after an operation, as assttyys regionClick computes it."""
    lo = delay_ms + cfg.base_sleep_ms
    hi = lo + cfg.random_sleep_ms
    if cfg.style == "assttyys":
        return int(get_normal_random((lo, hi), str_hash_to_num(cfg.device_id, lo, hi)))
    return int(random.uniform(lo, hi))


def swipe_points(start_rect, end_rect, cfg: HumanizeConfig) -> tuple[tuple[int, int], tuple[int, int], int]:
    """Random start/end inside two rects and a random duration (assttyys ``regionSwipe``)."""
    s = normalize_rect(start_rect)
    e = normalize_rect(end_rect)
    p1 = (random.randint(s[0], s[2]), random.randint(s[1], s[3]))
    p2 = (random.randint(e[0], e[2]), random.randint(e[1], e[3]))
    duration = random.randint(*cfg.swipe_duration_ms)
    return p1, p2, duration
