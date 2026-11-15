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
    stop_when: "runs >= max_runs"
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

import copy
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import WorkflowError
from ..yamlio import dump_yaml, load_yaml
from .expr import compile_expr, names_in

SENSITIVE = ("花勾玉", "抽卡", "购买", "出售", "分解")
CONDITION_KEYS = {"colors", "res", "find", "image", "expr", "all", "any", "not", "ocr"}
ACTION_KEYS = {"click", "click_random", "click_found", "swipe", "back", "wait", "set", "inc", "stop", "fail", "confirm",
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

    def digest(self) -> str:
        return hashlib.sha256(dump_yaml(self.raw).encode("utf-8")).hexdigest()[:16]

    def sensitive_categories(self) -> set[str]:
        out = set()
        for st in self.states:
            if st.get("sensitive"):
                out.add(st["sensitive"])
            for a in st.get("do", []):
                if "confirm" in a:
                    out.add(a["confirm"])
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
        if key == "ocr":
            if "var" not in c:
                raise WorkflowError(f"{where}: ocr 条件需要 var")
            variables.add(c["var"])
            if "test" in c:
                compile_expr(c["test"])
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
    if not isinstance(a, dict) or len(set(a) & ACTION_KEYS) != 1:
        raise WorkflowError(f"{where}: 动作必须恰好是 {sorted(ACTION_KEYS)} 之一")
    key = next(iter(set(a) & ACTION_KEYS))
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
    elif key == "swipe":
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
        if st.get("sensitive") and st["sensitive"] not in SENSITIVE:
            raise WorkflowError(f"{where}: sensitive 只能是 {SENSITIVE}")
        if st.get("on_repeat", "fail") not in ("fail", "stop"):
            raise WorkflowError(f"{where}: on_repeat 只能是 fail 或 stop")
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
    for k, spec in (raw.get("params") or {}).items():
        if isinstance(spec, dict) and "default" not in spec:
            raise WorkflowError(f"params.{k} 缺少 default")


def load_workflow(path_or_raw, extra_resource_dirs: list | None = None) -> Workflow:
    if isinstance(path_or_raw, dict):
        raw, path = path_or_raw, None
    else:
        path = Path(path_or_raw)
        raw = load_yaml(path)
        if not isinstance(raw, dict):
            raise WorkflowError(f"{path}: 不是有效的工作流")
    resources = resolve_resources(raw, path, extra_resource_dirs)
    validate(raw, resources)
    return Workflow(raw, path, resources)
