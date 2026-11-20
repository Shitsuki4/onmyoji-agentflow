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

SENSITIVE = ("花勾玉", "抽卡", "购买", "出售", "分解")
FORBIDDEN_ACTION_KEYS = {
    "recharge", "send_social", "invite_return", "feed_rare", "feed_rare_unit", "feed_locked",
    "feed_max_level_soul", "feed_locked_soul", "dismantle_locked", "dismantle_locked_soul",
    "sell_locked", "sell_rare_unit", "delete_account", "change_system_settings",
}
FORBIDDEN_INTENTS = FORBIDDEN_ACTION_KEYS
CONDITION_KEYS = {"colors", "res", "find", "image", "expr", "all", "any", "not", "ocr", "text", "text_param"}
ACTION_KEYS = {"click", "click_random", "click_found", "select_foster", "select_foster_unit", "scan_tasks", "receipt", "swipe", "back", "wait", "set", "inc", "stop", "fail", "confirm",
               "start_app", "log"}
DEFAULT_LIMITS = {"timeout_s": 3600, "unknown_timeout_s": 60, "stuck_timeout_s": 90,
                  "no_progress_timeout_s": 600, "max_repeat": 20}


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
            item = {k: v for k, v in spec.items() if k != "path"}
            path = spec.get("path")
            if path and Path(path).is_file():
                item["file_sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
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
        input_keys = {"click", "click_random", "click_found", "select_foster", "select_foster_unit", "swipe", "back", "start_app"}
        for st in self.states:
            active = set([st["sensitive"]]) if st.get("sensitive") else set()
            for index, action in enumerate(st.get("do", []) or []):
                if "confirm" in action:
                    active.add(action["confirm"])
                    out.append((st["id"], "confirm", index, action["confirm"]))
                if set(action) & input_keys:
                    operation = {key: action[key] for key in input_keys if key in action}
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
    for ref in raw.get("resources") or []:
        for base in resource_search_path(workflow_path, extra_dirs):
            p = base / ref
            if p.exists():
                out.update(load_resource_file(p))
                break
        else:
            raise WorkflowError(f"找不到资源文件 {ref}（可以先运行 oaf convert 生成）")
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


def validate_condition(c, resources: dict, variables: set, where: str):
    if not isinstance(c, dict) or len(set(c) & CONDITION_KEYS) != 1:
        raise WorkflowError(f"{where}: 条件必须恰好是 {sorted(CONDITION_KEYS)} 之一")
    key = next(iter(set(c) & CONDITION_KEYS))
    v = c[key]
    if key == "colors":
        _check_points(v, where)
    elif key in ("res", "find", "image", "ocr"):
        if v not in resources:
            raise WorkflowError(f"{where}: 未知资源 {v!r}")
        if key == "find" and resources[v].get("type") != "find_colors":
            raise WorkflowError(f"{where}: find 只能用 find_colors 资源")
        pick = c.get("pick", resources[v].get("pick") if key == "find" else None)
        if pick is not None and pick not in ("first", "last", "bottom", "top"):
            raise WorkflowError(f"{where}: pick 只能是 first / last / bottom / top")
        if key == "ocr":
            if "var" not in c:
                raise WorkflowError(f"{where}: ocr 条件需要 var")
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


def validate_action(a, resources: dict, variables: set, where: str):
    if isinstance(a, dict) and set(a) & FORBIDDEN_ACTION_KEYS:
        raise WorkflowError(f"{where}: 禁止的操作 {sorted(set(a) & FORBIDDEN_ACTION_KEYS)}")
    if not isinstance(a, dict) or len(set(a) & ACTION_KEYS) != 1:
        raise WorkflowError(f"{where}: 动作必须恰好是 {sorted(ACTION_KEYS)} 之一")
    key = next(iter(set(a) & ACTION_KEYS))
    if "recheck" in a and (type(a["recheck"]) is not bool or key not in ("click", "click_random", "swipe")):
        raise WorkflowError(f"{where}: recheck 只支持点击/滑动动作的布尔标记")
    if "attempt_var" in a and (key not in ("click", "swipe") or not isinstance(a["attempt_var"], str)
                               or a["attempt_var"] not in variables):
        raise WorkflowError(f"{where}: attempt_var 需要点击/滑动动作及已声明变量")
    forbidden = set(a) & FORBIDDEN_ACTION_KEYS
    if forbidden:
        raise WorkflowError(f"{where}: 禁止的操作 {sorted(forbidden)}")
    v = a[key]
    if key == "click":
        if isinstance(v, str):
            if v not in resources or "rect" not in resources[v]:
                raise WorkflowError(f"{where}: click 资源 {v!r} 不存在或没有 rect")
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
    elif key == "select_foster":
        if not isinstance(v, dict) or type(v.get("max_pages", 30)) is not int or not 1 <= v.get("max_pages", 30) <= 60:
            raise WorkflowError(f"{where}: select_foster.max_pages 需要 1–60 的整数")
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
        else:
            _check_rect(v.get("from"), where)
            _check_rect(v.get("to"), where)
    elif key in ("set",):
        if not isinstance(v, dict):
            raise WorkflowError(f"{where}: set 需要 {{变量: 表达式}}")
        for name, expr in v.items():
            compile_expr(str(expr))
            variables.add(name)
    elif key == "inc":
        if v not in variables:
            raise WorkflowError(f"{where}: inc 的变量 {v!r} 没在 vars 里声明")
    elif key == "confirm":
        if v not in SENSITIVE:
            raise WorkflowError(f"{where}: confirm 只能是 {SENSITIVE}")
    elif key == "wait":
        if not isinstance(v, (int, float)) or v < 0 or v > 600000:
            raise WorkflowError(f"{where}: wait 毫秒数不合理")
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
    variables |= {"elapsed_s", "actions"}
    # first pass: variables introduced by set / ocr anywhere
    for st in raw["states"]:
        for a in st.get("do", []) or []:
            if isinstance(a, dict) and isinstance(a.get("set"), dict):
                variables |= set(a["set"].keys())
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
        validate_condition(st["when"], resources, variables, where + ".when")
        for j, a in enumerate(st.get("do", []) or []):
            validate_action(a, resources, variables, f"{where}.do[{j}]")
            if a.get("attempt_var") and a["attempt_var"] not in (raw.get("vars") or {}):
                raise WorkflowError(f"{where}: attempt_var 必须在 vars 中声明，不能修改参数")
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
