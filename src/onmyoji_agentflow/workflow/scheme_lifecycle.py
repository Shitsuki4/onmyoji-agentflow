"""Validated, run-local assttyys named-scheme bindings."""
from __future__ import annotations

import math
import re

from ..errors import WorkflowError

ACTIVE_SCHEME = "source_active_scheme"
SWITCH_DELAY_S = 0.510
MAX_SWITCHES = 32
CLOCKS = {"core0_run_start_ms", "core0_current_date_ms"}
_BUILTINS = {"elapsed_s", "elapsed_ms", "actions"}


def valid_history_terms(terms):
    return (isinstance(terms, list) and 0 < len(terms) <= 32
            and all(isinstance(term, str) and 0 < len(term) <= 128 and term.strip() == term for term in terms))


def latest_scheme(history, terms):
    return next((entry["scheme"] for entry in reversed(history)
                 if any(term in entry["scheme"] for term in terms)), None)


def resume_elapsed_ms(raw, checkpoint, now):
    """Validate the persisted boundary and compute the host-based source clock."""
    if not isinstance(checkpoint, dict) or set(checkpoint) != {"version", "vars", "history", "elapsed_ms", "paused_at"}:
        raise WorkflowError("方案暂停记录格式无效")
    values, history = checkpoint["vars"], checkpoint["history"]
    elapsed, paused_at = checkpoint["elapsed_ms"], checkpoint["paused_at"]
    lifecycle, dispatch = raw["scheme_lifecycle"], raw["handler_dispatch"]
    if (checkpoint["version"] != 1 or not isinstance(values, dict) or set(values) != set(raw["vars"])
            or any(type(v) not in (str, int, float, bool, type(None)) or
                   (type(v) is float and not math.isfinite(v)) for v in values.values())
            or type(values[dispatch["phase_var"]]) is not int or values[dispatch["phase_var"]] != 0
            or type(elapsed) is not int or elapsed < 0 or not math.isfinite(now)
            or type(paused_at) not in (int, float) or not math.isfinite(paused_at) or not 0 <= paused_at <= now
            or not isinstance(history, list) or not 1 <= len(history) <= MAX_SWITCHES + 1):
        raise WorkflowError("方案暂停记录缺少可恢复的状态或时钟")
    previous = 0
    for entry in history:
        if (not isinstance(entry, dict) or set(entry) != {"scheme", "entered_ms"}
                or not isinstance(entry["scheme"], str) or entry["scheme"] not in lifecycle["schemes"]
                or type(entry["entered_ms"]) is not int or not previous <= entry["entered_ms"] <= elapsed):
            raise WorkflowError("方案暂停历史无效")
        previous = entry["entered_ms"]
    if (history[0] != {"scheme": raw["vars"][ACTIVE_SCHEME], "entered_ms": 0}
            or history[-1]["scheme"] != values[ACTIVE_SCHEME]):
        raise WorkflowError("方案暂停历史与当前方案不一致")
    return elapsed + int((now - paused_at) * 1000)


def writes_active_scheme(condition):
    quiz = condition.get("quiz_answer", {})
    return (condition.get("var") == ACTIVE_SCHEME
            or condition.get("ordered_list", {}).get("direction_var") == ACTIVE_SCHEME
            or condition.get("wanted_badge") == ACTIVE_SCHEME
            or ACTIVE_SCHEME in condition.get("wanted_location", {}).get("output", {}).values()
            or ACTIVE_SCHEME in (*quiz.get("option_vars", ()), quiz.get("question_var"), quiz.get("answer_var"))
            or any(writes_active_scheme(child) for key in ("all", "any") for child in condition.get(key, ()))
            or ("not" in condition and writes_active_scheme(condition["not"])))


def validate_lifecycle(raw):
    spec = raw["scheme_lifecycle"]
    dispatch = raw.get("handler_dispatch")
    if (not isinstance(spec, dict) or set(spec) != {"version", "schemes"} or spec["version"] != 1
            or raw.get("navigation") or dispatch is None):
        raise WorkflowError("scheme_lifecycle 需要 version:1 的组件调度契约")
    schemes = spec["schemes"]
    initial = raw.get("vars") or {}
    active = initial.get(ACTIVE_SCHEME)
    if (not isinstance(schemes, dict) or not 1 <= len(schemes) <= 120
            or not isinstance(active, str) or active not in schemes or raw.get("params")):
        raise WorkflowError("scheme_lifecycle 需要明确初始方案和固定方案配置")
    preserve = {dispatch["last_id_var"], dispatch["last_ms_var"], "super_next_scheme_name"}
    local_names = set(initial) - {ACTIVE_SCHEME} - preserve
    if local_names & _BUILTINS or ACTIVE_SCHEME in (
        dispatch["phase_var"], dispatch["last_id_var"], dispatch["last_ms_var"], dispatch["last_handled_ms_var"]
    ):
        raise WorkflowError("scheme_lifecycle 保留名称不能作为局部变量")
    for name, binding in schemes.items():
        if (not isinstance(name, str) or not name.strip() or len(name) > 128 or name.startswith("__")
                or not isinstance(binding, dict) or set(binding) != {"reset", "clocks", "handled_var"}):
            raise WorkflowError("scheme_lifecycle 方案绑定无效")
        resets, clocks = binding["reset"], binding["clocks"]
        if (not isinstance(resets, dict) or set(resets) != local_names
                or any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_]\w*", key, flags=re.ASCII)
                       for key in resets)
                or any(type(value) not in (str, int, float, bool, type(None)) or
                       (type(value) is float and not math.isfinite(value)) for value in resets.values())
                or type(resets.get(dispatch["phase_var"])) is not int or resets[dispatch["phase_var"]] != 0
                or not isinstance(binding["handled_var"], str)
                or type(resets.get(binding["handled_var"])) not in (int, float)
                or not isinstance(clocks, list)
                or any(not isinstance(key, str) or key not in CLOCKS or key not in resets for key in clocks)
                or len(clocks) != len(set(clocks))):
            raise WorkflowError(f"scheme_lifecycle 方案 {name} 的局部重置或时钟无效")
    if any(initial[key] != value for key, value in schemes[active]["reset"].items()):
        raise WorkflowError("scheme_lifecycle 初始变量与初始方案不一致")
