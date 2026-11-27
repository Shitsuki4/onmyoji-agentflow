"""Multi-point colour comparison and multi-point colour search (assttyys style).

assttyys describes a screen as ``[[anchor, x, y, 0xRRGGBB], ...]`` in 1280x720
and compares with a similarity (default 93). ``anchor`` (left/center/right)
only matters for non-16:9 screens; at 1280x720 coordinates are used as is.
"""
from __future__ import annotations

import numpy as np


def mean_rgb_similar(img: np.ndarray, region, rgb, threshold=10) -> bool:
    """OAS get_color + color_similar on an xywh region of a native BGR frame.

    Truncate mean/reference RGB components, then compare max(positive diff)
    minus min(negative diff). Invalid ROIs raise so a negated empty observation
    cannot authorize an input.
    """
    x, y, width, height = region
    frame_h, frame_w = img.shape[:2]
    if (x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > frame_w or y + height > frame_h
            or img.ndim != 3 or img.shape[2] < 3):
        raise ValueError("mean_color region is outside the current BGR frame")
    mean = img[y:y + height, x:x + width, :3].mean(axis=(0, 1))[::-1]
    if not np.isfinite(mean).all():
        raise ValueError("mean_color cannot use nonfinite pixels")
    difference = mean.astype(int) - np.asarray(rgb).astype(int)
    distance = np.maximum(difference, 0).max() - np.minimum(difference, 0).min()
    return bool(distance <= threshold)


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


def find_multi_color(img: np.ndarray, region, groups, similarity: float = 93, max_results: int = 1, *,
                     deduplicate: bool = True):
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
                if not deduplicate or all(abs(cx - rx) > 10 or abs(cy - ry) > 10 for rx, ry in results):
                    results.append((cx, cy))
                if len(results) >= max_results:
                    return results
    return results


def distinct_color_matches(img, spec, similarity):
    """Collect bounded, ordered assttyys-style matches with 30px suppression."""
    limit = 256
    points = find_multi_color(img, spec["region"], spec["groups"], float(spec.get("similarity", similarity)),
                              max_results=limit + 1, deduplicate=False)
    if len(points) > limit:
        return None
    # findMultiColorEx drops a point if any later hit is within 30 px.
    return [(x, y) for i, (x, y) in enumerate(points)
            if all((x - lx) ** 2 + (y - ly) ** 2 >= 30 ** 2 for lx, ly in points[i + 1:])]


def nearest_color_match(img, target, reference, similarity, max_distance, max_below):
    """Return the target anchor nearest any reference within the geometry limits."""
    references = distinct_color_matches(img, reference, similarity)
    if not references:
        return None
    targets = distinct_color_matches(img, target, similarity) or []
    best_distance = max_distance ** 2
    best = None
    for rx, ry in references:
        for tx, ty in targets:
            distance = (tx - rx) ** 2 + (ty - ry) ** 2
            if ty - ry <= max_below and distance < best_distance:
                best = tx, ty
                best_distance = distance
    return best


def column_color_match(img, target, reference, similarity, x_offsets, row):
    """Match against the first reference in scan order and the lowest nearby rows."""
    markers = find_multi_color(img, reference["region"], reference["groups"],
                               float(reference.get("similarity", similarity)))
    if not markers:
        return None
    points = distinct_color_matches(img, target, similarity)
    if points is None:
        return None
    x, y = markers[0]
    first, last = x_offsets
    ordered = sorted((point for point in points if first <= x - point[0] <= last),
                     key=lambda point: -point[1])
    if not ordered:
        return None
    second_below = len(ordered) > 1 and y < ordered[1][1]
    if row == "second_below":
        return ordered[1] if second_below else None
    return ordered[0] if not second_below else None
