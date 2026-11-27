"""Closed, frame-bounded geometry for native visual observations (xywh)."""
from __future__ import annotations

import math
import re

from ..errors import WorkflowError
from ..workflow.expr import evaluate


MATCH_COORDS = {"match_x", "match_y", "match_w", "match_h"}


def parameter_click_rect(target, params):
    if "rect_param" in target:
        value = params[target["rect_param"]]
        pieces = [part.strip() for part in value.split(",")] if isinstance(value, str) else []
        if len(pieces) != 4 or any(not re.fullmatch(r"[0-9]{1,4}", part) for part in pieces):
            raise WorkflowError("点击矩形需要 x1,y1,x2,y2 格式的四个整数")
        x1, y1, x2, y2 = map(int, pieces)
        if not (0 <= x1 <= x2 < 1280 and 0 <= y1 <= y2 < 720):
            raise WorkflowError("点击矩形需要在 1280×720 画面内按左上、右下顺序排列")
        return [x1, y1, x2, y2]
    radius = target.get("radius", 10)
    if "xy_param" in target:
        value = params[target["xy_param"]]
        normalized = re.sub(r"\s+", "", value) if isinstance(value, str) else ""
        points = [part for part in re.split("[,，]", normalized) if part]
        if len(points) != 2 or any(not re.fullmatch(r"[+-]?[0-9]{1,4}", part) for part in points):
            raise WorkflowError("点击坐标需要 x,y 格式的整数")
        x, y = map(int, points)
    else:
        x, y = (params[target[axis]] for axis in ("x_param", "y_param"))
    if (type(x) is not int or type(y) is not int or
            not (radius <= x <= 1279 - radius and radius <= y <= 719 - radius)):
        raise WorkflowError(f"点击坐标需要在 1280×720 画面内保留 {radius} 像素边距")
    return [x - radius, y - radius, x + radius, y + radius]


def checked_box(value, image, *, integral=False):
    if (not isinstance(value, (list, tuple)) or len(value) != 4 or
            any(type(n) not in (int, float) or not math.isfinite(n) for n in value)):
        raise WorkflowError("visual region needs four finite numeric xywh values")
    x, y, width, height = value
    if integral and any(type(n) is not int for n in value):
        raise WorkflowError("visual search region needs integer xywh values")
    if (min(x, y) < 0 or min(width, height) <= 0 or
            x + width > image.shape[1] or y + height > image.shape[0]):
        raise WorkflowError("visual region is outside the current frame")
    return tuple(value)


def project_region(box, expressions, image):
    box = checked_box(box, image)
    env = dict(zip(("match_x", "match_y", "match_w", "match_h"), box))
    values = [evaluate(str(expr), env) for expr in expressions]
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in values):
        raise WorkflowError("capture_region needs finite numeric results")
    # OAS get_area/get_area_image truncate only after computing the projection.
    return checked_box(tuple(int(n) for n in values), image, integral=True)
