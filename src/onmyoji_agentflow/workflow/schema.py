"""Workflow YAML format (format: 1) - loading and validation.

See docs/workflow-format.md for the full description. Summary::

    format: 1
    name: orochi
    title: 御魂（个人）
    resources: [assttyys/colors.yaml]
    similarity: 93
    params: {max_runs: {default: 30, min: 1, max: 999, desc: 挑战次数}}
    vars: {runs: 0}
    limits: {timeout_s: 3600, unknown_timeout_s: 60, stuck_timeout_s: 90, no_progress_timeout_s: 600, max_repeat: 20}
    stop_when: "runs >= max_runs"    # optional; or stop on a screen with a `stop` action
    counts: {runs: max_runs}           # optional, which counter a retry subtracts from which param
    requires: [已加入阴阳寮]          # optional, account prerequisites shown to the user
    blockers:                          # optional, screens meaning a prerequisite is missing
      - {id: no_guild, when: {colors: [...]}, message: 账号还没加入阴阳寮}
    states:
      - id: challenge
        when: {colors: [[1180, 630, "#f3cc8a"], ...]}
        do: [{click: [1148, 602, 1235, 663], delay: 1000}, {inc: runs}]
        progress: true

Only conditions, counters and variables exist; there is no way to embed code.
"""
from __future__ import annotations

import re

import copy
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import WorkflowError
from ..yamlio import dump_yaml, load_yaml
from .expr import compile_expr, names_in

RESTART_CONFIRMATION = "重启游戏"
SENSITIVE = ("花勾玉", "抽卡", "购买", "出售", "分解", RESTART_CONFIRMATION)
INPUT_ACTION_KEYS = {"click", "click_random", "click_found", "select_foster", "select_foster_unit",
                     "swipe", "back", "start_app", "restart_app"}
SUPPORTED_IMAGE_METHODS = {"Template matching", "Masked template matching", "Multi-scale template matching", "Sift Flann", "Default"}
FORBIDDEN_ACTION_KEYS = {
    "recharge", "send_social", "invite_return", "feed_rare", "feed_rare_unit", "feed_locked",
    "feed_max_level_soul", "feed_locked_soul", "dismantle_locked", "dismantle_locked_soul",
    "sell_locked", "sell_rare_unit", "delete_account", "change_system_settings",
}
FORBIDDEN_INTENTS = FORBIDDEN_ACTION_KEYS
CONDITION_KEYS = {"colors", "mean_color", "res", "find", "find_near", "find_column", "find_image_above", "image", "expr", "all", "any", "not", "ocr", "ocr_single", "ocr_full", "text", "text_param", "ordered_list", "image_grid", "quiz_answer", "wanted_badge", "wanted_location", "screen_size", "tap_loop", "foreground_game", "scheme_history"}
ACTION_KEYS = {"click", "click_random", "click_found", "capture_region", "navigate", "navigation_return", "handler_control", "select_foster", "select_foster_unit", "scan_tasks", "receipt", "swipe", "back", "wait", "wait_random", "sample_int", "sample_duration", "set", "inc", "stop", "fail", "confirm",
               "start_app", "restart_app", "scheme_transition", "log", "oas_wake"}
DEFAULT_LIMITS = {"timeout_s": 3600, "unknown_timeout_s": 60, "stuck_timeout_s": 90,
                  "no_progress_timeout_s": 600, "max_repeat": 20}
RUN_METRICS = {"actions", "elapsed_s", "elapsed_ms", "screen_captures"}


def bundled_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


@dataclass
class Workflow:
    raw: dict
    path: Path | None = None
    resources: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw["name"]

    @property
    def title(self) -> str:
        return self.raw.get("title", self.name)

    @property
    def states(self) -> list[dict]:
        return self.raw["states"]

    @property
    def limits(self) -> dict:
        return {**DEFAULT_LIMITS, **(self.raw.get("limits") or {})}

    @property
    def similarity(self) -> float:
        return float(self.raw.get("similarity", 93))

    @property
    def requires(self) -> list[str]:
        """Account prerequisites (e.g. 已加入阴阳寮). Not checked automatically; shown to the user."""
        return list(self.raw.get("requires") or [])

    @property
    def blockers(self) -> list[dict]:
        """Screens meaning a prerequisite is missing (e.g. the 未入寮 prompt). Matching one stops the
        run with failure kind ``prerequisite``; the supervisor never repairs the workflow for it."""
        return list(self.raw.get("blockers") or [])

    def param_defaults(self) -> dict:
        return {k: (v.get("default") if isinstance(v, dict) else v) for k, v in (self.raw.get("params") or {}).items()}

    def param_specs(self) -> dict:
        return {k: (v if isinstance(v, dict) else {"default": v})
                for k, v in (self.raw.get("params") or {}).items()}

    def validate_params(self, values: dict | None = None) -> dict:
        """Validate runtime parameters once for CLI, web, MCP and direct callers."""
        values = values or {}
        specs = self.param_specs()
        unknown = set(values) - set(specs)
        if unknown:
            raise WorkflowError(f"工作流 {self.name} 没有参数：{sorted(unknown)}")
        out = {**self.param_defaults(), **values}
        for name, spec in specs.items():
            if name not in out:
                raise WorkflowError(f"参数 {name} 缺少默认值")
            value = out[name]
            default = spec.get("default")
            inferred = {bool: "bool", int: "int", float: "number", str: "string"}.get(type(default), "")
            kind = str(spec.get("type") or inferred).lower()
            if kind in ("int", "integer") and (isinstance(value, bool) or not isinstance(value, int)):
                raise WorkflowError(f"参数 {name} 必须是整数")
            if kind in ("float", "number") and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise WorkflowError(f"参数 {name} 必须是数字")
            if kind in ("bool", "boolean") and not isinstance(value, bool):
                raise WorkflowError(f"参数 {name} 必须是布尔值")
            if kind in ("str", "string") and not isinstance(value, str):
                raise WorkflowError(f"参数 {name} 必须是文字")
            if isinstance(value, (int, float)) and not math.isfinite(value):
                raise WorkflowError(f"参数 {name} 必须是有限数字")
            if "min" in spec and isinstance(value, (int, float)) and value < spec["min"]:
                raise WorkflowError(f"参数 {name} 不能小于 {spec['min']}")
            if "max" in spec and isinstance(value, (int, float)) and value > spec["max"]:
                raise WorkflowError(f"参数 {name} 不能大于 {spec['max']}")
            choices = spec.get("choices")
            if choices is not None and value not in choices:
                raise WorkflowError(f"参数 {name} 必须是 {choices} 之一")
        return out

    def digest(self, runtime: dict | None = None) -> str:
        from .. import __version__
        import importlib.metadata
        try:
            ocr = importlib.metadata.version("rapidocr_onnxruntime")
        except importlib.metadata.PackageNotFoundError:
            ocr = "unavailable"
        material = {"workflow": self.raw, "resources": {}, "engine": __version__, "ocr": ocr,
                    "runtime": runtime or {}}
        for name, spec in sorted(self.resources.items()):
            item = {k: v for k, v in spec.items() if k not in ("path", "mask_path")}
            for field, digest_name in (("path", "file_sha256"), ("mask_path", "mask_sha256")):
                path = spec.get(field)
                if path and Path(path).is_file():
                    item[digest_name] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            material["resources"][name] = item
        return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]

    def sensitive_categories(self) -> set[str]:
        out = set()
        for st in self.states:
            if st.get("sensitive"):
                out.add(st["sensitive"])
            for a in st.get("do", []):
                if "confirm" in a:
                    out.add(a["confirm"])
        return out

    def sensitive_operations(self) -> list[tuple]:
        """One stable guard token for every protected operation."""
        out = []
        for st in self.states:
            active = set([st["sensitive"]]) if st.get("sensitive") else set()
            for index, action in enumerate(st.get("do", []) or []):
                if "confirm" in action:
                    active.add(action["confirm"])
                    out.append((st["id"], "confirm", index, action["confirm"]))
                if set(action) & INPUT_ACTION_KEYS:
                    operation = {key: action[key] for key in INPUT_ACTION_KEYS if key in action}
                    fingerprint = json.dumps(operation, ensure_ascii=False, sort_keys=True)
                    for category in sorted(active):
                        out.append((st["id"], fingerprint, index, category))
        return out

    def copy(self) -> "Workflow":
        return Workflow(copy.deepcopy(self.raw), self.path, self.resources)

    def dump(self) -> str:
        return dump_yaml(self.raw)


# ------------------------------------------------------------------ resources
def load_resource_file(path: Path) -> dict:
    doc = load_yaml(path) or {}
    res = doc.get("resources") or {}
    out = {}
    for name, spec in res.items():
        spec = dict(spec)
        if spec.get("type") == "image":
            spec["path"] = str((path.parent / spec["file"]).resolve())
            if spec.get("mask_file"):
                spec["mask_path"] = str((path.parent / spec["mask_file"]).resolve())
        spec.setdefault("_source", doc.get("source", path.stem))
        out[name] = spec
    return out


def resource_search_path(workflow_path: Path | None, extra: list | None = None) -> list[Path]:
    paths = []
    for p in extra or []:
        paths.append(Path(p))
    if workflow_path is not None:
        paths.append(workflow_path.parent.parent / "resources")
        paths.append(workflow_path.parent / "resources")
    env = os.environ.get("OAF_RESOURCES")
    if env:
        paths.append(Path(env))
    paths.append(bundled_dir() / "resources")
    return paths


def resolve_resources(raw: dict, workflow_path: Path | None, extra_dirs: list | None = None) -> dict:
    out = {}
    qualified = raw.get("resource_namespaces", False)
    owners = {}
    aliases = set()
    for ref in raw.get("resources") or []:
        for base in resource_search_path(workflow_path, extra_dirs):
            p = base / ref
            if p.exists():
                document = load_resource_file(p)
                if not qualified:
                    out.update(document)
                    break
                namespace = Path(ref).stem
                for name, spec in document.items():
                    alias = namespace + "::" + name
                    if alias in aliases and out[alias] != spec:
                        raise WorkflowError(f"资源命名空间冲突 {alias}")
                    out[alias] = spec
                    aliases.add(alias)
                    owners.setdefault(name, set()).add(str(p.resolve()))
                    if len(owners[name]) == 1:
                        out[name] = spec
                    else:
                        # New family composers use explicit aliases. An ambiguous
                        # short name must fail validation rather than silently
                        # taking the last loaded task's image or coordinates.
                        out.pop(name, None)
                break
        else:
            raise WorkflowError(f"找不到资源文件 {ref}（可以先运行 oaf convert 生成）")
    if qualified and aliases & set(raw.get("inline_resources") or {}):
        raise WorkflowError("inline_resources 不能覆盖带命名空间的来源资源")
    out.update(raw.get("inline_resources") or {})
    return out


# ------------------------------------------------------------------ validation
def _check_rect(v, where):
    if not (isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v)):
        raise WorkflowError(f"{where}: 区域必须是 [x1, y1, x2, y2]")


def _check_points(v, where):
    if not isinstance(v, list) or not v:
        raise WorkflowError(f"{where}: colors 需要点列表")
    for p in v:
        if not (isinstance(p, list) and len(p) == 3):
            raise WorkflowError(f"{where}: 每个点是 [x, y, '#rrggbb']")


def _requires_match_anchor(condition, resources, *, allow_point=False):
    """Require match geometry on every successful predicate path."""
    if set(condition) & {"ocr_single", "ocr_full", "find_image_above"}:
        return True
    if allow_point and "ocr" in condition and condition.get("mode") == "max_hourly_rate":
        return True
    name = condition.get("res") or condition.get("image") or condition.get("find")
    kind = resources.get(name, {}).get("type")
    if kind == "image" or (allow_point and (kind == "find_colors" or set(condition) & {"find_column", "find_near"})):
        return True
    if "all" in condition:
        return any(_requires_match_anchor(c, resources, allow_point=allow_point) for c in condition["all"])
    if "any" in condition:
        return bool(condition["any"]) and all(
            _requires_match_anchor(c, resources, allow_point=allow_point) for c in condition["any"])
    return False


def _check_match_projection(rect, where):
    from ..vision.regions import MATCH_COORDS
    if not isinstance(rect, list) or len(rect) != 4:
        raise WorkflowError(f"{where}: 需要四个 xywh 坐标表达式")
    for expr in rect:
        if type(expr) not in (str, int, float) or len(str(expr)) > 256 or names_in(str(expr)) - MATCH_COORDS:
            raise WorkflowError(f"{where}: 表达式只能使用 match_x/y/w/h")


def validate_condition(c, resources: dict, variables: set, where: str):
    if not isinstance(c, dict) or len(set(c) & CONDITION_KEYS) != 1:
        raise WorkflowError(f"{where}: 条件必须恰好是 {sorted(CONDITION_KEYS)} 之一")
    key = next(iter(set(c) & CONDITION_KEYS))
    v = c[key]
    if "template_crop" in c:
        spec = resources.get(v, {}) if isinstance(v, str) else {}
        box = c["template_crop"]
        if (key not in ("res", "image") or spec.get("type") != "image"
                or spec.get("method", "Template matching") != "Template matching" or "scale_range" in c
                or not isinstance(box, list) or len(box) != 4 or any(type(n) is not int for n in box)
                or min(box[:2]) < 0 or min(box[2:]) <= 0):
            raise WorkflowError(f"{where}: template_crop 需要普通模板图片和有效的 xywh 矩形")
    if "scale_range" in c:
        # BaseTask.appear_multi_scale bypasses the resource's normal dispatch.
        # Keep this override local to the condition, never mutate shared assets.
        if (key not in ("res", "image") or not isinstance(v, str)
                or resources.get(v, {}).get("type") != "image"):
            raise WorkflowError(f"{where}: scale_range 只能用于图片条件")
        if not isinstance(c["scale_range"], (list, tuple)) or len(c["scale_range"]) not in (2, 3):
            raise WorkflowError(f"{where}: scale_range 必须是 [start, end, 可选 step]")
        from ..vision.template import _scale_values
        try:
            _scale_values(None, c["scale_range"])
        except (ValueError, TypeError, OverflowError) as error:
            raise WorkflowError(f"{where}: scale_range 无效: {error}") from error
    if key == "foreground_game":
        from ..device.adb import ONMYOJI_PACKAGE_PATTERN
        if not isinstance(v, str) or not re.fullmatch(ONMYOJI_PACKAGE_PATTERN, v, flags=re.ASCII):
            raise WorkflowError(f"{where}: foreground_game 需要阴阳师 Android 包名")
    elif key == "tap_loop":
        if not _valid_tap_id(v):
            raise WorkflowError(f"{where}: tap_loop 需要已标识的点击名称")
    elif key == "screen_size":
        if not isinstance(v, list) or len(v) != 2 or any(type(n) is not int or n <= 0 for n in v):
            raise WorkflowError(f"{where}: screen_size 需要原始截图的 [宽, 高]")
    elif key == "colors":
        _check_points(v, where)
    elif key == "mean_color":
        if not isinstance(v, dict) or set(v) - {"region", "rgb", "tolerance"}:
            raise WorkflowError(f"{where}: mean_color 需要 region/rgb/可选 tolerance")
        region, rgb, limit = v.get("region"), v.get("rgb"), v.get("tolerance", 10)
        if (not isinstance(region, list) or len(region) != 4 or any(type(n) is not int for n in region)
                or min(region[:2]) < 0 or min(region[2:]) <= 0):
            raise WorkflowError(f"{where}: mean_color.region 必须是有效整数 xywh")
        if (not isinstance(rgb, list) or len(rgb) != 3 or
                any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 255 for n in rgb)
                or type(limit) not in (int, float) or not math.isfinite(limit) or not 0 <= limit <= 510):
            raise WorkflowError(f"{where}: mean_color 的 RGB/容差无效")
    elif key == "wanted_badge":
        if not isinstance(v, str) or v not in variables or v in RUN_METRICS:
            raise WorkflowError(f"{where}: wanted_badge 需要已声明的悬赏进度变量")
    elif key == "wanted_location":
        config = {"priority", "secret_cutoff", "excluded", "tickets"}
        outputs = {"slot", "kind", "destination", "runs", "signature", "progress"}
        if (not isinstance(v, dict) or set(v) != config | {"output"} or
                any(not isinstance(v[k], str) or v[k] not in variables for k in config) or
                not isinstance(v["output"], dict) or set(v["output"]) != outputs or
                any(not isinstance(n, str) or n not in variables or n in RUN_METRICS
                    for n in v["output"].values()) or len(set(v["output"].values())) != len(outputs)):
            raise WorkflowError(f"{where}: wanted_location 需要已声明的配置变量及五个不同的输出变量")
    elif key in ("ocr_single", "ocr_full"):
        text_key = "equals" if key == "ocr_single" else "keyword"
        variable_key = text_key + "_var"
        allowed = {"region", text_key, variable_key, "score"}
        if key == "ocr_full":
            allowed.update({"box_equals", "evidence", "selection"})
        if not isinstance(v, dict) or set(v) - allowed:
            raise WorkflowError(f"{where}: {key} 需要 region/{text_key}/可选 score")
        region, expected, score = v.get("region"), v.get(text_key), v.get("score", .6)
        if (not isinstance(region, list) or len(region) != 4 or any(type(n) is not int for n in region)
                or min(region[:2]) < 0 or min(region[2:]) <= 0):
            raise WorkflowError(f"{where}: {key}.region 必须是有效整数 xywh")
        if (text_key in v) == (variable_key in v):
            raise WorkflowError(f"{where}: {key} 必须恰好指定 {text_key} 或 {variable_key}")
        if variable_key in v:
            if not isinstance(v[variable_key], str) or v[variable_key] not in variables:
                raise WorkflowError(f"{where}: {key}.{variable_key} 必须引用已声明变量或参数")
        elif not isinstance(expected, str) or not expected:
            raise WorkflowError(f"{where}: {key}.{text_key} 必须是非空文字")
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise WorkflowError(f"{where}: {key}.score 必须在 0–1 内")
        if "box_equals" in v:
            box = v["box_equals"]
            if (not isinstance(box, list) or len(box) != 4 or
                    any(type(n) not in (int, float) or not math.isfinite(n) for n in box)
                    or min(box[:2]) < 0 or min(box[2:]) <= 0):
                raise WorkflowError(f"{where}: ocr_full.box_equals 必须是有效 xywh")
        if "evidence" in v and v["evidence"] not in ("complete_keyword", "partial_keyword"):
            raise WorkflowError(f"{where}: ocr_full.evidence 只能是 complete_keyword/partial_keyword")
        if "selection" in v and v["selection"] not in ("unique_contains", "unique_equals", "first_contains"):
            raise WorkflowError(f"{where}: ocr_full.selection 需要 unique_contains、unique_equals 或 first_contains")
    elif key == "quiz_answer":
        if not isinstance(v, dict) or set(v) != {"bank", "question", "options", "option_vars", "question_var", "answer_var"}:
            raise WorkflowError(f"{where}: quiz_answer 缺少题库、OCR 或输出字段")
        bank = resources.get(v["bank"], {}) if isinstance(v["bank"], str) else {}
        if bank.get("type") != "answer_bank":
            raise WorkflowError(f"{where}: quiz_answer.bank 需要题库资源")
        question = resources.get(v["question"], {}) if isinstance(v["question"], str) else {}
        options, output = v["options"], v["option_vars"]
        if (question.get("type") != "ocr" or question.get("mode") not in ("Full", "Single")
                or not isinstance(options, list) or len(options) not in (3, 4)
                or any(not isinstance(name, str) or resources.get(name, {}).get("type") != "ocr"
                       or resources[name].get("mode") != "Single" for name in options)
                or len(set(options)) != len(options)):
            raise WorkflowError(f"{where}: quiz_answer 需要一道 Full 或 Single 题目和三个或四个 Single 选项")
        if not isinstance(output, list) or len(output) != len(options):
            raise WorkflowError(f"{where}: quiz_answer.option_vars 必须对应各选项")
        output = [*output, v["question_var"], v["answer_var"]]
        if (any(not isinstance(name, str) or name not in variables or name in RUN_METRICS for name in output)
                or len(set(output)) != len(output)):
            raise WorkflowError(f"{where}: quiz_answer 输出变量必须独立声明")
    elif key == "ordered_list":
        fields = {"region", "labels", "target", "direction_var"}
        if not isinstance(v, dict) or not fields <= set(v) <= fields | {"selected_row"}:
            raise WorkflowError(f"{where}: ordered_list 需要 region、labels、target 和 direction_var")
        region, labels, target, direction = (v[name] for name in ("region", "labels", "target", "direction_var"))
        if (not isinstance(region, list) or len(region) != 4 or any(type(n) is not int for n in region)
                or min(region[:2]) < 0 or min(region[2:]) <= 0
                or region[0] + region[2] > 1280 or region[1] + region[3] > 720):
            raise WorkflowError(f"{where}: ordered_list.region 需要画面内的 xywh 区域")
        if (not isinstance(labels, list) or not 1 <= len(labels) <= 60 or
                any(not isinstance(group, list) or not 1 <= len(group) <= 3 or
                    any(not isinstance(label, str) or not label or label != "".join(label.split()) for label in group)
                    for group in labels)):
            raise WorkflowError(f"{where}: ordered_list.labels 需要有序的名称组")
        names = [label for group in labels for label in group]
        if len(names) != len(set(names)) or target not in names:
            raise WorkflowError(f"{where}: ordered_list 需要唯一的标签及已登记目标")
        if not isinstance(direction, str) or direction not in variables or direction in RUN_METRICS:
            raise WorkflowError(f"{where}: ordered_list.direction_var 必须是已声明的方向变量")
        if "selected_row" in v:
            marker = v["selected_row"]
            if (not isinstance(marker, dict) or set(marker) != {"x", "width", "height", "rgb", "tolerance", "coverage"}
                    or any(type(marker[key]) is not int for key in ("x", "width", "height", "tolerance"))
                    or not 0 <= marker["x"] < marker["x"] + marker["width"] <= 1280
                    or not 1 <= marker["height"] <= 120 or not 0 <= marker["tolerance"] <= 80
                    or not isinstance(marker["rgb"], list) or len(marker["rgb"]) != 3
                    or any(type(channel) is not int or not 0 <= channel <= 255 for channel in marker["rgb"])
                    or type(marker["coverage"]) not in (int, float) or not 0 < marker["coverage"] <= 1):
                raise WorkflowError(f"{where}: ordered_list.selected_row 需要合法的颜色、位置和覆盖率")
    elif key == "image_grid":
        fields = {"templates", "cells", "cell_var"}
        if not isinstance(v, dict) or not fields <= set(v) <= fields | {"exclude"}:
            raise WorkflowError(f"{where}: image_grid 需要优先图片、网格及结果变量")
        templates, cells, out = (v[name] for name in ("templates", "cells", "cell_var"))
        if (not isinstance(templates, list) or not 1 <= len(templates) <= 12
                or any(not isinstance(ref, str) or resources.get(ref, {}).get("type") != "image" for ref in templates)
                or len(templates) != len(set(templates))
                or not isinstance(cells, list) or not 1 <= len(cells) <= 20
                or not isinstance(out, str) or out not in variables or out in RUN_METRICS):
            raise WorkflowError(f"{where}: image_grid 图片、网格数量或结果变量无效")
        regions = list(cells)
        if "exclude" in v:
            exclude = v["exclude"]
            if (not isinstance(exclude, dict) or set(exclude) != {"template", "regions"}
                    or not isinstance(exclude["template"], str)
                    or resources.get(exclude["template"], {}).get("type") != "image"
                    or not isinstance(exclude["regions"], list) or len(exclude["regions"]) != len(cells)):
                raise WorkflowError(f"{where}: image_grid 排除区域必须与网格逐项对应")
            regions.extend(exclude["regions"])
        if any(not isinstance(r, list) or len(r) != 4 or any(type(n) is not int for n in r)
               or not 0 <= r[0] < r[0] + r[2] <= 1280 or not 0 <= r[1] < r[1] + r[3] <= 720 for r in regions):
            raise WorkflowError(f"{where}: image_grid 区域需要画面内的 xywh")
    elif key == "find_image_above":
        fields = {"target", "reference", "x_pad", "max_above", "min_gap", "x_weight", "threshold"}
        if not isinstance(v, dict) or set(v) != fields:
            raise WorkflowError(f"{where}: find_image_above 的字段必须为 {sorted(fields)}")
        for field in ("target", "reference"):
            if not isinstance(v[field], str) or resources.get(v[field], {}).get("type") != "image":
                raise WorkflowError(f"{where}: find_image_above.{field} 需要图片资源")
        if resources[v["target"]].get("method", "Template matching") != "Template matching":
            raise WorkflowError(f"{where}: find_image_above.target 需要普通模板匹配图片")
        if (any(type(v[field]) is not int for field in ("x_pad", "max_above", "min_gap", "x_weight"))
                or not 0 <= v["x_pad"] <= 1280 or not 0 <= v["min_gap"] < v["max_above"] <= 720
                or not 1 <= v["x_weight"] <= 20 or type(v["threshold"]) not in (int, float)
                or not 0 < v["threshold"] <= 1):
            raise WorkflowError(f"{where}: find_image_above 的区域、权重或阈值无效")
    elif key in ("find_near", "find_column"):
        options = {"max_distance", "max_below"} if key == "find_near" else {"x_offsets", "row"}
        if not isinstance(v, dict) or set(v) != {"target", "reference"} | options:
            raise WorkflowError(f"{where}: {key} 需要 target、reference 及 {', '.join(sorted(options))}")
        for field in ("target", "reference"):
            name = v[field]
            if not isinstance(name, str) or resources.get(name, {}).get("type") != "find_colors":
                raise WorkflowError(f"{where}: {key}.{field} 需要 find_colors 资源")
        if key == "find_near":
            distance, below = v["max_distance"], v["max_below"]
            if (type(distance) not in (int, float) or not 0 < distance <= 1500
                    or type(below) is not int or not 0 <= below <= 720):
                raise WorkflowError(f"{where}: find_near 的距离和高度限制超出范围")
        else:
            offsets = v["x_offsets"]
            if (not isinstance(offsets, list) or len(offsets) != 2 or any(type(n) is not int for n in offsets)
                    or not -1279 <= offsets[0] <= offsets[1] <= 1279
                    or v["row"] not in ("second_below", "lowest_else")):
                raise WorkflowError(f"{where}: find_column 的横向偏移或行选择无法识别")
    elif key in ("res", "find", "image", "ocr"):
        if v not in resources:
            raise WorkflowError(f"{where}: 未知资源 {v!r}")
        if resources[v].get("type") == "image":
            spec = resources[v]
            if spec.get("method", "Template matching") not in SUPPORTED_IMAGE_METHODS:
                raise WorkflowError(f"{where}: 图片 {v!r} 的匹配方法尚未转换：{spec['method']}")
            padding = spec.get("roi_expand", 0)
            if type(padding) is not int or not 0 <= padding <= 32:
                raise WorkflowError(f"{where}: 图片 roi_expand 必须是 0–32 的整数")
        if "region_vars" in c:
            names = c["region_vars"]
            if (resources[v].get("type") != "image" or key == "ocr" or
                    not isinstance(names, list) or len(names) != 4 or
                    any(not isinstance(n, str) or n not in variables for n in names)):
                raise WorkflowError(f"{where}: 图片 region_vars 必须引用四个已声明的 xywh 变量")
        if key == "find" and resources[v].get("type") != "find_colors":
            raise WorkflowError(f"{where}: find 只能用 find_colors 资源")
        pick = c.get("pick", resources[v].get("pick") if key == "find" else None)
        if pick is not None and pick not in ("first", "last", "bottom", "top"):
            raise WorkflowError(f"{where}: pick 只能是 first / last / bottom / top")
        if key == "ocr":
            if not isinstance(c.get("var"), str) or c["var"] in RUN_METRICS:
                raise WorkflowError(f"{where}: ocr 条件需要 var")
            if "mode" in c:
                mode = c["mode"]
                ocr_types = {"text_sequence": ("Full",), "duration_seconds": ("Duration", "Single"),
                             "cn_hour_minute": ("Single",), "remaining_times": ("Single",),
                             "counter_remaining": ("DigitCounter",), "counter_current": ("DigitCounter",),
                             "exact_quantity": ("Quantity", "Digit"),
                             "shop_stock": ("Single",), "max_hourly_rate": ("Single", "Full")}.get(mode) if isinstance(mode, str) else None
                if (ocr_types is None or resources[v].get("type") != "ocr" or resources[v].get("mode") not in ocr_types
                        or (mode == "text_sequence" and "test" in c)):
                    raise WorkflowError(f"{where}: ocr.mode 必须与 OCR 资源类型匹配")
                if mode == "max_hourly_rate":
                    label = c.get("hourly_label")
                    if not isinstance(label, str) or not label.strip() or len(label) > 32:
                        raise WorkflowError(f"{where}: max_hourly_rate 需要 hourly_label")
            variables.add(c["var"])
            if "test" in c:
                compile_expr(c["test"])
    elif key == "text":
        if not (isinstance(v, str) or (isinstance(v, list) and all(isinstance(w, str) for w in v))):
            raise WorkflowError(f"{where}: text 是一个词或词列表")
        if not v and not c.get("pattern"):
            raise WorkflowError(f"{where}: text 为空时需要 pattern")
        if c.get("pattern"):
            try:
                re.compile(c["pattern"])
            except re.error as e:
                raise WorkflowError(f"{where}: pattern 不是合法的正则：{e}") from e
        if "region" in c and not (isinstance(c["region"], list) and len(c["region"]) == 4):
            raise WorkflowError(f"{where}: region 是 [x, y, w, h]")
        if c.get("var"):
            variables.add(c["var"])
    elif key == "text_param":
        if not isinstance(v, str) or v not in variables:
            raise WorkflowError(f"{where}: text_param 必须引用已声明参数")
        if "region" in c:
            _check_rect(c["region"], where)
    elif key == "scheme_history":
        from .scheme_lifecycle import valid_history_terms
        if set(c) != {key} or not valid_history_terms(v):
            raise WorkflowError(f"{where}: scheme_history 需要非空有界的方案关键词列表")
    elif key == "expr":
        compile_expr(v)
        unknown = names_in(v) - variables
        if unknown:
            raise WorkflowError(f"{where}: 表达式用到未定义的变量 {sorted(unknown)}")
    elif key in ("all", "any"):
        if not isinstance(v, list) or not v:
            raise WorkflowError(f"{where}: {key} 需要条件列表")
        for i, sub in enumerate(v):
            validate_condition(sub, resources, variables, f"{where}.{key}[{i}]")
    elif key == "not":
        validate_condition(v, resources, variables, f"{where}.not")


def _valid_tap_id(name):
    return isinstance(name, str) and 1 <= len(name) <= 128 and bool(re.fullmatch(r"[\w:]+", name, flags=re.ASCII))


def validate_action(a, resources: dict, variables: set, where: str):
    if isinstance(a, dict) and set(a) & FORBIDDEN_ACTION_KEYS:
        raise WorkflowError(f"{where}: 禁止的操作 {sorted(set(a) & FORBIDDEN_ACTION_KEYS)}")
    if not isinstance(a, dict) or len(set(a) & ACTION_KEYS) != 1:
        raise WorkflowError(f"{where}: 动作必须恰好是 {sorted(ACTION_KEYS)} 之一")
    key = next(iter(set(a) & ACTION_KEYS))
    if "tap_id" in a and (key not in ("click", "click_found", "click_random") or not _valid_tap_id(a["tap_id"])):
        raise WorkflowError(f"{where}: tap_id 只能标识点击动作")
    if "recheck" in a and (type(a["recheck"]) is not bool or key not in ("click", "click_random", "click_found", "swipe", "restart_app")):
        raise WorkflowError(f"{where}: recheck 只支持点击、滑动或重启动作的布尔标记")
    if "recheck_retry" in a and (type(a["recheck_retry"]) is not bool or a.get("recheck") is not True
                                or key not in ("click", "click_random", "click_found") or "attempt_var" in a):
        raise WorkflowError(f"{where}: recheck_retry 需要开启 recheck 的普通点击")
    if "attempt_var" in a and (key not in ("click", "swipe", "restart_app") or not isinstance(a["attempt_var"], str)
                               or a["attempt_var"] not in variables):
        raise WorkflowError(f"{where}: attempt_var 需要点击、滑动或重启动作及已声明变量")
    forbidden = set(a) & FORBIDDEN_ACTION_KEYS
    if forbidden:
        raise WorkflowError(f"{where}: 禁止的操作 {sorted(forbidden)}")
    v = a[key]
    if key == "click":
        if isinstance(v, str):
            if v not in resources or "rect" not in resources[v]:
                raise WorkflowError(f"{where}: click 资源 {v!r} 不存在或没有 rect")
        elif isinstance(v, dict):
            if set(v) == {"rect_vars"}:
                names = v["rect_vars"]
                if (not isinstance(names, list) or len(names) != 4
                        or any(not isinstance(name, str) or name not in variables for name in names)
                        or len(set(names)) != 4):
                    raise WorkflowError(f"{where}: click.rect_vars 需要四个 xywh 变量")
            else:
                references = [value for key, value in v.items() if key.endswith("_param")]
                if (set(v) not in ({"x_param", "y_param"}, {"xy_param"}, {"xy_param", "radius"}, {"rect_param"}) or
                    any(not isinstance(name, str) or name not in variables for name in references) or
                    ("radius" in v and (type(v["radius"]) is not int or not 1 <= v["radius"] <= 20))):
                    raise WorkflowError(f"{where}: click 坐标需要 rect_param、xy_param 或 x_param 与 y_param")
        else:
            _check_rect(v, where)
    elif key == "click_random":
        if not isinstance(v, list) or not v:
            raise WorkflowError(f"{where}: click_random 需要区域列表")
        for r in v:
            _check_rect(r, where)
    elif key == "click_found":
        if "offset" in a:
            _check_rect(a["offset"], where)
        if "point_vars" in a:
            names = a["point_vars"]
            if (a.get("recheck") is not True or not isinstance(names, list) or len(names) != 2
                    or any(not isinstance(name, str) or name not in variables or name in RUN_METRICS for name in names)
                    or len(set(names)) != 2):
                raise WorkflowError(f"{where}: click_found.point_vars 需要重新核对和两个可写变量")
        if "use_match_size" in a and (type(a["use_match_size"]) is not bool or "offset" in a):
            raise WorkflowError(f"{where}: use_match_size 必须是布尔值，且不能与 offset 并用")
        if "projected_rect" in a:
            if a.get("recheck") is not True or "offset" in a or "use_match_size" in a:
                raise WorkflowError(f"{where}: projected_rect 需要重新核对命中及独立的点击矩形")
            _check_match_projection(a["projected_rect"], where)
    elif key == "capture_region":
        if not isinstance(v, dict) or set(v) != {"vars", "rect"}:
            raise WorkflowError(f"{where}: capture_region 需要 vars 和 rect")
        names, rect = v["vars"], v["rect"]
        if (not isinstance(names, list) or len(names) != 4 or any(not isinstance(n, str) for n in names)
                or len(set(names)) != 4 or any(n not in variables or n in RUN_METRICS for n in names)):
            raise WorkflowError(f"{where}: capture_region 需要四个不同的可写变量")
        _check_match_projection(rect, where)
    elif key == "start_app":
        if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", v, flags=re.ASCII):
            raise WorkflowError(f"{where}: start_app 只接受 Android 包名")
    elif key == "restart_app":
        from ..device.adb import ONMYOJI_PACKAGE_PATTERN
        if (not isinstance(v, str) or not re.fullmatch(ONMYOJI_PACKAGE_PATTERN, v, flags=re.ASCII)
                or a.get("recheck") is not True or not a.get("attempt_var")):
            raise WorkflowError(f"{where}: restart_app 需要阴阳师包名、recheck 和 attempt_var")
    elif key == "navigate":
        if (not isinstance(v, dict) or set(v) - {"destination", "done_var", "category", "timeout_s"}
                or not isinstance(v.get("destination"), str) or not isinstance(v.get("done_var"), str)
                or v["done_var"] not in variables):
            raise WorkflowError(f"{where}: navigate 需要 destination 和已声明 done_var")
        timeout = v.get("timeout_s", 30)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise WorkflowError(f"{where}: navigate.timeout_s 必须在 0–30 秒内")
    elif key == "navigation_return":
        if not isinstance(v, str) or not v:
            raise WorkflowError(f"{where}: navigation_return 需要有限调用名称")
    elif key == "handler_control":
        if not isinstance(v, dict) or v.get("op") not in ("begin", "refresh", "end"):
            raise WorkflowError(f"{where}: handler_control 只支持 begin/refresh/end")
        if v["op"] == "begin" and (set(v) != {"op", "version"} or v.get("version") != 1):
            raise WorkflowError(f"{where}: handler_control.begin 需要 version: 1")
        if v["op"] == "end" and (set(v) != {"op", "handled"} or type(v.get("handled")) is not bool):
            raise WorkflowError(f"{where}: handler_control.end 需要 handled 布尔值")
        if v["op"] == "refresh" and set(v) != {"op"}:
            raise WorkflowError(f"{where}: handler_control.refresh 不接受参数")
    elif key == "scheme_transition":
        from .scheme_lifecycle import valid_history_terms
        valid = isinstance(v, dict) and (
            v == {"mode": "previous"}
            or (set(v) == {"mode", "contains"} and v["mode"] == "latest_matching" and valid_history_terms(v["contains"]))
            or (set(v) == {"mode", "target"} and v["mode"] == "rerun" and isinstance(v["target"], str)
                and 0 < len(v["target"]) <= 128 and not v["target"].startswith("__")))
        if set(a) != {key} or not valid:
            raise WorkflowError(f"{where}: scheme_transition 需要现有方案名或受限历史匹配")
    elif key == "sample_int":
        if (not isinstance(v, dict) or set(v) != {"var", "min", "max"}
                or not isinstance(v.get("var"), str) or v["var"] not in variables or v["var"] in RUN_METRICS
                or type(v.get("min")) is not int or type(v.get("max")) is not int
                or not -86400000 <= v["min"] <= v["max"] <= 86400000):
            raise WorkflowError(f"{where}: sample_int 需要已声明变量与有界整数 min/max")
    elif key == "sample_duration":
        if (not isinstance(v, dict) or set(v) != {"var", "range_param", "unit"}
                or any(not isinstance(v[k], str) or v[k] not in variables for k in ("var", "range_param"))
                or v["var"] in RUN_METRICS or v["var"] == v["range_param"]
                or v["unit"] not in ("minutes", "seconds")):
            raise WorkflowError(f"{where}: sample_duration 需要可写变量、时长区间和 minutes/seconds 单位")
    elif key == "select_foster":
        if not isinstance(v, dict) or type(v.get("max_pages", 30)) is not int or not 1 <= v.get("max_pages", 30) <= 60:
            raise WorkflowError(f"{where}: select_foster.max_pages 需要 1–60 的整数")
        if "exhausted_var" in v and ("selected_tabs" not in v or not isinstance(v["exhausted_var"], str)
                                     or v["exhausted_var"] not in variables or v["exhausted_var"] in RUN_METRICS):
            raise WorkflowError(f"{where}: 寄养两区比较完成必须写入已声明的变量")
        if "selected_tabs" in v:
            tabs = v["selected_tabs"]
            if (not isinstance(tabs, list) or len(tabs) != 2 or
                    any(not isinstance(tab, str) or resources.get(tab, {}).get("type") != "image" for tab in tabs)
                    or tabs[0] == tabs[1]):
                raise WorkflowError(f"{where}: select_foster.selected_tabs 需要同区、跨区两个不同的已选标签图片")
        if "cross_nickname_templates" in v:
            from ..foster import foster_friend_key
            names = v["cross_nickname_templates"]
            if ("selected_tabs" not in v or not isinstance(names, dict) or not 1 <= len(names) <= 16
                    or any(not isinstance(name, str) or not name.strip() or not isinstance(ref, str)
                           or resources.get(ref, {}).get("type") != "image" for name, ref in names.items())
                    or len({foster_friend_key(name) for name in names}) != len(names)
                    or len(set(names.values())) != len(names)):
                raise WorkflowError(f"{where}: 跨区昵称校准需要唯一的昵称及图片资源")
        if "enter_realm" in v:
            enter = v["enter_realm"]
            if ("selected_tabs" not in v or not isinstance(enter, dict) or set(enter) != {"button", "entered_var"}
                    or not isinstance(enter["button"], str)
                    or resources.get(enter["button"], {}).get("type") != "image"
                    or not isinstance(enter["entered_var"], str) or enter["entered_var"] not in variables
                    or enter["entered_var"] in RUN_METRICS):
                raise WorkflowError(f"{where}: 进入好友结界需要双区核对、按钮图片和已声明的输出变量")
    elif key == "select_foster_unit":
        if not isinstance(v, dict) or not v.get("required_text"):
            raise WorkflowError(f"{where}: select_foster_unit 需要 required_text")
        if not isinstance(v["required_text"], list) or not all(isinstance(x, str) for x in v["required_text"]):
            raise WorkflowError(f"{where}: required_text 必须是文字列表")
        if "region" in v:
            _check_rect(v["region"], where)
    elif key == "scan_tasks":
        if not isinstance(v, dict) or v.get("scope") not in ("daily", "weekly"):
            raise WorkflowError(f"{where}: scan_tasks 需要 daily/weekly scope")
        if "region" in v:
            _check_rect(v["region"], where)
    elif key == "receipt":
        if not isinstance(v, dict) or not v.get("kind"):
            raise WorkflowError(f"{where}: receipt 需要 kind")
    if "cost" in a:
        if not isinstance(a["cost"], dict) or not a["cost"]:
            raise WorkflowError(f"{where}: cost 必须是资源与数量组成的字典")
        for resource, amount in a["cost"].items():
            if (not isinstance(resource, str) or isinstance(amount, bool)
                    or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0):
                raise WorkflowError(f"{where}: cost 必须是非负有限数字")
    if key == "swipe":
        if isinstance(v, str):
            if v not in resources or resources[v].get("type") != "swipe":
                raise WorkflowError(f"{where}: swipe 资源 {v!r} 不存在")
        elif isinstance(v, dict) and "from_found" in v:
            offset = v["from_found"]
            _check_rect(offset, where)
            _check_rect(v.get("to"), where)
            if (set(v) != {"from_found", "to"} or a.get("recheck") is not True
                    or any(type(n) is not int or not -1280 <= n <= 1280 for n in offset)
                    or offset[0] >= offset[2] or offset[1] >= offset[3]):
                raise WorkflowError(f"{where}: swipe.from_found 需要有限的偏移矩形和画面复核")
        else:
            _check_rect(v.get("from") if isinstance(v, dict) else None, where)
            _check_rect(v.get("to"), where)
    elif key in ("set",):
        if not isinstance(v, dict):
            raise WorkflowError(f"{where}: set 需要 {{变量: 表达式}}")
        for name, expr in v.items():
            if name in RUN_METRICS:
                raise WorkflowError(f"{where}: {name} 是只读运行指标")
            compile_expr(str(expr))
            variables.add(name)
    elif key == "inc":
        if v in RUN_METRICS:
            raise WorkflowError(f"{where}: {v} 是只读运行指标")
        if v not in variables:
            raise WorkflowError(f"{where}: inc 的变量 {v!r} 没在 vars 里声明")
    elif key == "confirm":
        if v not in SENSITIVE:
            raise WorkflowError(f"{where}: confirm 只能是 {SENSITIVE}")
    elif key == "wait":
        if isinstance(v, dict):
            if (set(v) not in ({"var"}, {"var", "minimum_ms"})
                    or not isinstance(v["var"], str) or v["var"] not in variables
                    or ("minimum_ms" in v and (type(v["minimum_ms"]) is not int
                                               or not 5000 <= v["minimum_ms"] <= 600000))):
                raise WorkflowError(f"{where}: wait 需要已声明时长变量，暂停轮询的下限为 5–600 秒")
        elif type(v) not in (int, float) or not 0 <= v <= 600000:
            raise WorkflowError(f"{where}: wait 毫秒数不合理")
    elif key == "wait_random":
        if isinstance(v, dict) and "step_ms" in v:
            if (set(v) != {"min_ms", "max_ms", "step_ms"}
                    or any(type(value) is not int for value in v.values())
                    or not 0 <= v["min_ms"] <= v["max_ms"] <= 600000
                    or v["step_ms"] <= 0
                    or (v["max_ms"] - v["min_ms"]) % v["step_ms"] != 0):
                raise WorkflowError(f"{where}: wait_random.step_ms 需要有界且整除区间的正整数步长")
        elif isinstance(v, dict):
            if (set(v) != {"min_ms", "max_ms", "distribution"} or v["distribution"] != "uniform"
                    or any(type(v[key]) not in (int, float) or not math.isfinite(v[key]) for key in ("min_ms", "max_ms"))
                    or not 0 <= v["min_ms"] <= v["max_ms"] <= 600000):
                raise WorkflowError(f"{where}: wait_random.uniform 需要有界 min_ms/max_ms")
        elif (not isinstance(v, list) or len(v) != 2 or any(type(value) is not int for value in v)
                or not 0 <= v[0] <= v[1] <= 600000):
            raise WorkflowError(f"{where}: wait_random 需要 [最小毫秒, 最大毫秒]，范围 0–600000")
    elif key == "stop":
        if isinstance(v, dict):
            if not v.get("reason"):
                raise WorkflowError(f"{where}: stop 对象需要 reason")
            if v.get("result") not in (None, "completed", "already_done", "blocked", "skipped", "unknown"):
                raise WorkflowError(f"{where}: stop.result 不支持")
            if "verified" in v and not isinstance(v["verified"], bool):
                raise WorkflowError(f"{where}: stop.verified 必须是布尔值")
        elif not isinstance(v, (str, int, float)):
            raise WorkflowError(f"{where}: stop 需要文字或对象")


def validate(raw: dict, resources: dict) -> None:
    if raw.get("format") != 1:
        raise WorkflowError("format 必须是 1")
    for key in ("name", "states"):
        if key not in raw:
            raise WorkflowError(f"缺少 {key}")
    if not isinstance(raw["states"], list) or not raw["states"]:
        raise WorkflowError("states 不能为空")
    variables = set((raw.get("vars") or {}).keys()) | set((raw.get("params") or {}).keys())
    variables |= RUN_METRICS
    if "resource_namespaces" in raw and type(raw["resource_namespaces"]) is not bool:
        raise WorkflowError("resource_namespaces 必须是布尔值")
    for name, resource in resources.items():
        if resource.get("type") == "answer_bank":
            rows = resource.get("rows")
            if (not isinstance(rows, list) or not 1 <= len(rows) <= 5000
                    or any(not isinstance(row, list) or len(row) != 2 or
                           any(not isinstance(line, str) or not 1 <= len(line) <= 320 for line in row)
                           for row in rows)):
                raise WorkflowError(f"{name}: answer_bank 需要有界题目和答案对")
    # first pass: variables introduced by set / ocr anywhere
    for st in raw["states"]:
        for a in st.get("do", []) or []:
            if isinstance(a, dict) and isinstance(a.get("set"), dict):
                variables |= set(a["set"].keys())
    if "navigation" in raw:
        from .navigation import validate_navigation
        validate_navigation(raw["navigation"], resources, set(variables))
    dispatch = raw.get("handler_dispatch")
    if dispatch is not None:
        if (not isinstance(dispatch, dict) or dispatch.get("version") != 1
                or dispatch.get("cached_frame_until_end") is not True or dispatch.get("skip_internal_loop_delay") is not True
                or dispatch.get("clock") != "elapsed_ms"):
            raise WorkflowError("handler_dispatch 缺少 version:1 缓存帧/时钟契约")
        names = [dispatch.get(key) for key in ("phase_var", "last_id_var", "last_ms_var", "last_handled_ms_var")]
        if any(not isinstance(name, str) or name not in (raw.get("vars") or {}) for name in names) or len(set(names)) != 4:
            raise WorkflowError("handler_dispatch 调度变量必须独立声明")
        if raw["vars"][dispatch["phase_var"]] != 0:
            raise WorkflowError("handler_dispatch 必须从外层扫描起点开始")
        common = dispatch.get("common_config", {})
        if not isinstance(common, dict):
            raise WorkflowError("handler_dispatch.common_config 无效")
        for key in ("loopDelay", "afterClickDelayBase", "afterClickDelayRandom"):
            if type(common.get(key)) not in (int, float) or not math.isfinite(common[key]) or not 0 <= common[key] <= 60000:
                raise WorkflowError("handler_dispatch 延时参数无效：" + key)
    lifecycle = raw.get("scheme_lifecycle")
    if lifecycle is not None:
        from .scheme_lifecycle import ACTIVE_SCHEME, validate_lifecycle, writes_active_scheme
        validate_lifecycle(raw)
    ids = set()
    for i, st in enumerate(raw["states"]):
        where = f"states[{i}]"
        sid = st.get("id")
        if not sid or sid in ids:
            raise WorkflowError(f"{where}: id 缺失或重复")
        ids.add(sid)
        where = f"state {sid}"
        if "when" not in st:
            raise WorkflowError(f"{where}: 缺少 when")
        if "retest_ms" in st and (type(st["retest_ms"]) not in (int, float)
                or not math.isfinite(st["retest_ms"]) or not 0 <= st["retest_ms"] <= 60000):
            raise WorkflowError(f"{where}: retest_ms 必须是 0–60000 的有限毫秒数")
        validate_condition(st["when"], resources, variables, where + ".when")
        if lifecycle and writes_active_scheme(st["when"]):
            raise WorkflowError(f"{where}: 当前方案由生命周期管理")
        if lifecycle:
            name = st.get("source_scheme")
            terms = st["when"].get("all", [])
            if (not isinstance(name, str) or name not in lifecycle["schemes"] or len(terms) != 2
                    or terms[0] != {"expr": f"{ACTIVE_SCHEME} == {name!r}"}):
                raise WorkflowError(f"{where}: 状态需要必经的方案归属条件")
        for j, a in enumerate(st.get("do", []) or []):
            validate_action(a, resources, variables, f"{where}.do[{j}]")
            if isinstance(a.get("stop"), dict) and "oas_schedule" in a["stop"]:
                from .oas_schedule import validate_schedule
                validate_schedule(a["stop"]["oas_schedule"], raw.get("params") or {}, raw.get("vars") or {})
            if "oas_wake" in a:
                from .oas_schedule import WAKE_WORKFLOWS, validate_wake
                wake = a["oas_wake"]
                validate_wake(wake, raw.get("params") or {})
                if set(a) != {"oas_wake"}:
                    raise WorkflowError(f"{where}: oas_wake 必须是单独的动作")
                if WAKE_WORKFLOWS[wake["task"]] == raw.get("name"):
                    callback_states = (raw.get("navigation") or {}).get("calls", {})
                    if not any(st["id"] in call["states"] for call in callback_states.values()):
                        raise WorkflowError(f"{where}: 仅导航回调可为当前任务接续调度")
            if isinstance(a.get("click"), dict) and any(
                    value not in (raw.get("params") or {}) for key, value in a["click"].items()
                    if key.endswith("_param")):
                raise WorkflowError(f"{where}: click 坐标只能引用 params 中声明的参数")
            if isinstance(a.get("click"), dict) and any(
                    name not in (raw.get("vars") or {}) for name in a["click"].get("rect_vars", [])):
                raise WorkflowError(f"{where}: click.rect_vars 需要 vars 中声明的目标矩形")
            if any(name not in (raw.get("vars") or {}) for name in a.get("point_vars", ())):
                raise WorkflowError(f"{where}: click_found.point_vars 需要 vars 中声明的变量")
            if "capture_region" in a:
                if (not _requires_match_anchor(st["when"], resources) or
                        any(n not in (raw.get("vars") or {}) for n in a["capture_region"]["vars"])):
                    raise WorkflowError(f"{where}: capture_region 需要必选的正向区域证据和 vars 中声明的输出")
            if "projected_rect" in a and ("click_found" not in a or
                    not _requires_match_anchor(st["when"], resources)):
                raise WorkflowError(f"{where}: projected_rect 需要当前画面的匹配框")
            if "navigate" in a:
                navigation = raw.get("navigation", {})
                if a["navigate"]["destination"] not in navigation.get("pages", {}):
                    raise WorkflowError(f"{where}: navigate 目标不在原生图中")
                if a["navigate"]["done_var"] not in (raw.get("vars") or {}):
                    raise WorkflowError(f"{where}: navigate.done_var 必须在 vars 中声明")
            if "handler_control" in a and dispatch is None:
                raise WorkflowError(f"{where}: handler_control 缺少 handler_dispatch 契约")
            if "scheme_transition" in a:
                transition = a["scheme_transition"]
                if (not lifecycle or j != len(st["do"]) - 1 or (
                        transition["mode"] == "rerun" and transition["target"] not in lifecycle["schemes"])):
                    raise WorkflowError(f"{where}: scheme_transition 必须绑定现有方案并结束当前状态")
            if lifecycle:
                if (ACTIVE_SCHEME in a.get("set", {}) or ACTIVE_SCHEME in a.get("point_vars", ())
                        or a.get("inc") == ACTIVE_SCHEME
                        or a.get("attempt_var") == ACTIVE_SCHEME
                        or a.get("sample_int", {}).get("var") == ACTIVE_SCHEME
                        or a.get("sample_duration", {}).get("var") == ACTIVE_SCHEME
                        or ACTIVE_SCHEME in a.get("capture_region", {}).get("vars", [])):
                    raise WorkflowError(f"{where}: 当前方案由生命周期管理")
            if "sample_int" in a and a["sample_int"]["var"] not in (raw.get("vars") or {}):
                raise WorkflowError(f"{where}: sample_int.var 必须在 vars 中声明")
            if "sample_duration" in a and a["sample_duration"]["var"] not in (raw.get("vars") or {}):
                raise WorkflowError(f"{where}: sample_duration.var 必须在 vars 中声明")
            wait = a.get("wait")
            if isinstance(wait, dict) and "minimum_ms" in wait and any(
                    set(step) & (INPUT_ACTION_KEYS | {"navigate"}) for step in st["do"] if isinstance(step, dict)):
                raise WorkflowError(f"{where}: 暂停轮询状态不能发送输入")
            swipe = a.get("swipe")
            if (isinstance(swipe, dict) and "from_found" in swipe
                    and not _requires_match_anchor(st["when"], resources, allow_point=True)):
                raise WorkflowError(f"{where}: swipe.from_found 需要当前画面的命中位置")
            if a.get("attempt_var") and a["attempt_var"] not in (raw.get("vars") or {}):
                raise WorkflowError(f"{where}: attempt_var 必须在 vars 中声明，不能修改参数")
            if "restart_app" in a:
                from .navigation import _positive
                terms = st["when"].get("all", [])
                foreground_guard = ({"foreground_game": a["restart_app"]} in terms and
                                    {"screen_size": [1280, 720]} in terms)
                if (st.get("sensitive") != RESTART_CONFIRMATION or not (_positive(st["when"]) or foreground_guard)
                        or (raw.get("vars") or {}).get(a["attempt_var"]) != 0
                        or st["do"][0] is not a
                        or any(not isinstance(step, dict) or not set(step) & {"set", "inc", "log"}
                               for step in st["do"][1:])):
                    raise WorkflowError(f"{where}: restart_app 需要单独确认、必经画面或前台证据和初始为零的重启标记")
        if st.get("sensitive") and st["sensitive"] not in SENSITIVE:
            raise WorkflowError(f"{where}: sensitive 只能是 {SENSITIVE}")
        if st.get("on_repeat", "fail") not in ("fail", "stop"):
            raise WorkflowError(f"{where}: on_repeat 只能是 fail 或 stop")
        intent = st.get("intent")
        if ((isinstance(intent, str) and intent in FORBIDDEN_INTENTS)
                or (isinstance(intent, list) and set(intent) & FORBIDDEN_INTENTS)):
            raise WorkflowError(f"{where}: 禁止的意图 {st['intent']}")
        for amount in (st.get("cost") or {}).values():
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise WorkflowError(f"{where}: cost 必须是非负有限数字")
    req = raw.get("requires") or []
    if not isinstance(req, list) or not all(isinstance(x, str) and x.strip() for x in req):
        raise WorkflowError("requires 必须是一组文字说明（账号前置条件），如 [已加入阴阳寮]")
    for i, b in enumerate(raw.get("blockers") or []):
        where = f"blockers[{i}]"
        if not isinstance(b, dict) or not b.get("id") or not b.get("message") or "when" not in b:
            raise WorkflowError(f"{where}: 需要 id、when、message 三项")
        if b["id"] in ids:
            raise WorkflowError(f"{where}: id 和状态重复")
        validate_condition(b["when"], resources, variables, f"blocker {b['id']}.when")
        if lifecycle and writes_active_scheme(b["when"]):
            raise WorkflowError(f"blocker {b['id']}: 当前方案由生命周期管理")
    # Call bodies are ordinary top-level states, so every candidate/safety check
    # inspects their actual actions. Only the active body's states may run.
    calls = raw.get("navigation", {}).get("calls", {})
    active = raw.get("navigation", {}).get("call_active_var")
    owners = {sid: name for name, call in calls.items() for sid in call["states"]}
    if calls:
        if raw.get("handler_dispatch") or (raw.get("vars") or {}).get(active) != "":
            raise WorkflowError("navigation.calls 需要空闲初态且不能嵌套 handler_dispatch")
        if not set(owners) <= ids:
            raise WorkflowError("navigation.calls 引用了不存在的状态")
        for call in calls.values():
            if any(n not in (raw.get("vars") or {}) for n in call["initial_vars"]):
                raise WorkflowError("navigation.calls 不能重置参数；局部变量必须在 vars 中声明")
    returned = set()
    def writes_active(condition):
        if not isinstance(condition, dict):
            return False
        if active and condition.get("var") == active:
            return True
        if "not" in condition:
            return writes_active(condition["not"])
        return any(writes_active(c) for key in ("all", "any") for c in condition.get(key, []))
    for st in raw["states"]:
        if writes_active(st["when"]):
            raise WorkflowError("call_active_var 不能用作识别结果变量")
        body = owners.get(st["id"])
        for index, action in enumerate(st.get("do", [])):
            if "navigation_return" in action:
                name = action["navigation_return"]
                if body != name or index != len(st["do"]) - 1:
                    raise WorkflowError("navigation_return 必须是所属调用状态的最后动作")
                returned.add(name)
            if body and set(action) & {"navigate", "handler_control", "stop"}:
                raise WorkflowError("navigation.calls 内部不能嵌套导航、组件扫描或结束父工作流")
            if active and (active in (action.get("set") or {}) or action.get("inc") == active):
                raise WorkflowError("call_active_var 由原生调用边界独占写入")
            if active and (active in (action.get("capture_region") or {}).get("vars", []) or
                           (action.get("sample_int") or {}).get("var") == active or
                           (action.get("sample_duration") or {}).get("var") == active or
                           (action.get("navigate") or {}).get("done_var") == active):
                raise WorkflowError("call_active_var 不能用作动作输出变量")
    if set(calls) - returned:
        raise WorkflowError("navigation.calls 缺少显式返回状态")
    if raw.get("stop_when"):
        compile_expr(raw["stop_when"])
        unknown = names_in(raw["stop_when"]) - variables
        if unknown:
            raise WorkflowError(f"stop_when 用到未定义的变量 {sorted(unknown)}")
    counts = raw.get("counts")
    if counts is not None:
        if not isinstance(counts, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in counts.items()):
            raise WorkflowError("counts 要写成 {计数变量: 次数参数}，比如 {done: max_runs}")
        unknown = set(counts) - variables
        if unknown:
            raise WorkflowError(f"counts 用到未定义的变量 {sorted(unknown)}")
    for k, spec in (raw.get("params") or {}).items():
        if isinstance(spec, dict) and "default" not in spec:
            raise WorkflowError(f"params.{k} 缺少 default")
        if isinstance(spec, dict):
            kind = str(spec.get("type") or "").lower()
            if kind and kind not in ("int", "integer", "float", "number", "bool", "boolean", "str", "string"):
                raise WorkflowError(f"params.{k}.type 不支持：{kind}")
            if "min" in spec and "max" in spec and spec["min"] > spec["max"]:
                raise WorkflowError(f"params.{k}: min 不能大于 max")


def expand_workflow(raw: dict, workflow_dir: Path | None = None) -> dict:
    if not isinstance(raw, dict):
        raise WorkflowError("不是有效的工作流")
    raw = copy.deepcopy(raw)
    workflow_dir = Path(workflow_dir) if workflow_dir is not None else bundled_dir() / "workflows"
    for include in raw.pop("include_states", []):
        name = include.get("workflow", "")
        if not re.fullmatch(r"[\w-]+", name):
            raise WorkflowError("非法 include_states 工作流名")
        source = workflow_dir / f"{name}.yaml"
        included = load_yaml(source)
        selected = [copy.deepcopy(state) for state in included["states"]
                    if state["id"] in include.get("ids", [])
                    or any(state["id"].startswith(prefix) for prefix in include.get("prefixes", []))]
        raw["states"] = selected + raw["states"]
    if raw.pop("common_popups", False):
        common = load_yaml(bundled_dir() / "common-popups.yaml")
        existing = {state["id"] for state in raw["states"]}
        raw["states"] = [state for state in common["states"] if state["id"] not in existing] + raw["states"]
    return raw


def load_workflow(path_or_raw, extra_resource_dirs: list | None = None) -> Workflow:
    if isinstance(path_or_raw, dict):
        raw, path = path_or_raw, None
    else:
        path = Path(path_or_raw)
        raw = load_yaml(path)
        if not isinstance(raw, dict):
            raise WorkflowError(f"{path}: 不是有效的工作流")
    raw = expand_workflow(raw, path.parent if path is not None else None)
    resources = resolve_resources(raw, path, extra_resource_dirs)
    validate(raw, resources)
    return Workflow(raw, path, resources)
