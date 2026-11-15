"""Multi-point colour comparison and multi-point colour search (assttyys style).

assttyys describes a screen as ``[[anchor, x, y, 0xRRGGBB], ...]`` in 1280x720
and compares with a similarity (default 93). ``anchor`` (left/center/right)
only matters for non-16:9 screens; at 1280x720 coordinates are used as is.
"""
from __future__ import annotations

import numpy as np


def parse_color(c) -> tuple[int, int, int]:
    """Accept 0xRRGGBB int, '#RRGGBB' / 'RRGGBB' / '0xRRGGBB' string. Returns (R, G, B)."""
    if isinstance(c, str):
        s = c.strip().lower().removeprefix("#").removeprefix("0x")
        v = int(s, 16)
    else:
        v = int(c)
    return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF


def tolerance(similarity: float) -> int:
    """Max per-channel difference allowed for a similarity in percent."""
    return int(round(255 * (100 - float(similarity)) / 100))


def _pixel(img: np.ndarray, x: int, y: int):
    h, w = img.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    b, g, r = img[y, x][:3]
    return int(r), int(g), int(b)


def compare_colors(img: np.ndarray, points, similarity: float = 93) -> bool:
    """True when every point matches. points: [[x, y, color], ...] (anchor already stripped)."""
    tol = tolerance(similarity)
    for x, y, color in points:
        px = _pixel(img, int(x), int(y))
        if px is None:
            return False
        r, g, b = parse_color(color)
        if abs(px[0] - r) > tol or abs(px[1] - g) > tol or abs(px[2] - b) > tol:
            return False
    return True


def color_score(img: np.ndarray, points, similarity: float = 93) -> float:
    """Fraction of matching points (used by diagnostics to show near misses)."""
    if not points:
        return 0.0
    tol = tolerance(similarity)
    ok = 0
    for x, y, color in points:
        px = _pixel(img, int(x), int(y))
        if px is None:
            continue
        r, g, b = parse_color(color)
        if abs(px[0] - r) <= tol and abs(px[1] - g) <= tol and abs(px[2] - b) <= tol:
            ok += 1
    return ok / len(points)


def find_multi_color(img: np.ndarray, region, groups, similarity: float = 93, max_results: int = 1):
    """Search ``region`` (x1, y1, x2, y2) for any of ``groups``.

    Each group is a list of absolute points [[x, y, color], ...] as written in
    assttyys multiFindColors.ts; the first point is the anchor and the others are
    matched at the same offsets. Returns a list of (x, y) of the anchor.
    """
    tol = tolerance(similarity)
    h, w = img.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in region)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w - 1, x2), min(h - 1, y2)
    rgb = img[..., 2::-1].astype(np.int16) if img.ndim == 3 else None
    results: list[tuple[int, int]] = []
    for group in groups:
        if not group:
            continue
        ax, ay, acolor = group[0]
        offsets = [(int(x) - int(ax), int(y) - int(ay), parse_color(c)) for x, y, c in group[1:]]
        sub = rgb[y1:y2 + 1, x1:x2 + 1]
        target = np.array(parse_color(acolor), dtype=np.int16)
        mask = np.all(np.abs(sub - target) <= tol, axis=2)
        ys, xs = np.nonzero(mask)
        for yy, xx in zip(ys, xs):
            cx, cy = int(xx) + x1, int(yy) + y1
            good = True
            for dx, dy, (r, g, b) in offsets:
                px, py = cx + dx, cy + dy
                if not (0 <= px < w and 0 <= py < h):
                    good = False
                    break
                pr, pg, pb = rgb[py, px]
                if abs(pr - r) > tol or abs(pg - g) > tol or abs(pb - b) > tol:
                    good = False
                    break
            if good:
                if all(abs(cx - rx) > 10 or abs(cy - ry) > 10 for rx, ry in results):
                    results.append((cx, cy))
                if len(results) >= max_results:
                    return results
    return results
