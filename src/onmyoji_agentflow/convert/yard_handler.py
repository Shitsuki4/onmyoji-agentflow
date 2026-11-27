"""Pinned AutoJS 503 native return-to-courtyard handler and explicit effects.

This translates the actual 50-operator helper, not a generic GotoMain shortcut.
Runtime targets and superGlobal targets remain distinct. Source Push, lifecycle
and app-exit branches remain ordered failure gates until their host contracts
exist. No raw source, callbacks or device operations execute during compilation.
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

from .assttyys import convert_colors
from .core_handlers import (
    CURRENT_DATE_VAR, HELPER_PINS, PUSH_SELECTION, PUSH_SELECTION_PIN,
    _local_notice, _local_stop, _operators, _push, _rerun, _stop, core_workflow,
)
from .handlers import UnsupportedHandler
from .handlers import _data, _defaults, _operator_case, _used_resources
from .jsliteral import extract_literal_after, find_consts, parse

SOURCE_FILE = "src/common/funcList/503_返回庭院界面.ts"
SOURCE_PIN = "718f7fe901842d50d2727433115e455adee4ea05a380132f179f74db8a541658"
CONFIG_ALIASES = {"oper_find_-1": "oper_find_minus_1"}


def _expr(value):
    return {"expr": value}


def _all(*items):
    return {"all": list(items)}


def _normalize_config_aliases(values, *, label):
    if not isinstance(values, dict):
        raise UnsupportedHandler(f"503 {label} must be a mapping")
    normalized = {}
    original_names = {}
    for key, value in values.items():
        canonical = CONFIG_ALIASES.get(key, key)
        if canonical in normalized:
            raise UnsupportedHandler(f"503 config alias collision: {original_names[canonical]} / {key}")
        normalized[canonical] = value
        original_names[canonical] = key
    return normalized


def compile_yard_handler(source, colors, *, config=None, runtime_params=None, super_target=None,
                         local_notifications=False):
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != SOURCE_PIN:
        raise UnsupportedHandler("503 source fingerprint mismatch")
    if runtime_params is not None and not isinstance(runtime_params, dict):
        raise UnsupportedHandler("503 runtime payload must be inert JSON data")
    runtime_params = copy.deepcopy(runtime_params or {})
    _data(runtime_params)
    runtime_target = runtime_params.get("next_scheme_name")
    if any(value is not None and not isinstance(value, str) for value in (runtime_target, super_target)):
        raise UnsupportedHandler("503 target must be a literal scheme name or absent")
    literal, _ = extract_literal_after(source, r"\bconfig\s*=")
    declaration = parse(literal, find_consts(source))
    normalized = copy.deepcopy(declaration)
    for group in normalized:
        for item in group.get("config", []):
            item["name"] = CONFIG_ALIASES.get(item["name"], item["name"])
    params = _defaults(normalized)
    # This property is used in the source but absent from its UI declaration.
    # It can be injected by scheme config; missing/other values cause no effect.
    params["afterCountOper"] = {"default": ""}
    configured = _normalize_config_aliases({} if config is None else config, label="config")
    if set(configured) - set(params):
        raise UnsupportedHandler("503 contains undeclared/untranslated config keys")
    for key, value in configured.items():
        expected = params[key]["default"]
        if type(value) is not type(expected):
            raise UnsupportedHandler("503 config type mismatch: " + key)
        params[key]["default"] = value
    operators, ranges = _operators(source)
    if len(operators) != 50:
        raise UnsupportedHandler("503 requires all 50 pinned operators")
    cases, obligations, internal = [], [], []
    model = {"id": 503, "name": "返回庭院界面", "params": params,
        "vars": {"back": True, "back_time": 0, CURRENT_DATE_VAR: 0, "core0_run_start_ms": 0,
                 "yard503_runtime_target": runtime_target or "", "super_next_scheme_name": super_target or "",
                 "yard503_next_scheme": "", "yard503_arrived": False},
        "resources": [], "resource_specs": {}, "cases": cases, "unmatched_return": False,
        "proof": {"scope": "pinned-yard-family-partial", "source_sha256": SOURCE_PIN, "source_path": SOURCE_FILE,
            "source_complete": False, "helper_pins": copy.deepcopy(HELPER_PINS),
            "config_declaration": declaration, "config_aliases": copy.deepcopy(CONFIG_ALIASES),
            "source_operator_ranges": ranges, "runtime_payload": runtime_params,
            "framework_bindings": {"last_handled_ms_var": CURRENT_DATE_VAR, "fresh_current_date_ms": 0},
            "source_state_bindings": {"global.back": "back", "global.back_time": "back_time",
                "runtimeParams.next_scheme_name": "yard503_runtime_target",
                "superGlobal.next_scheme_name": "super_next_scheme_name (empty means null)",
                "lastFuncDateTime": "handler_last_ms", "runDate": "core0_run_start_ms"}}}

    def case(name, condition, actions=(), *, outcome=True, counts=(), group=None, bookkeeping=False):
        value = {"id": name, "when": condition, "do": list(actions), "return": outcome,
                 "count_events": list(counts), "retest_group": group or name}
        cases.append(value)
        if bookkeeping:
            internal.append(name)
        return value

    def gap(name, lines, condition, effects, source_return, required):
        issue = {"id": "yard503." + name, "source": {"path": SOURCE_FILE,
            "start_line": lines[0], "end_line": lines[1]}, "condition": condition,
            "ordered_effects": copy.deepcopy(effects), "source_return": source_return,
            "blocking": True, "required_contracts": required}
        obligations.append(issue)
        return {"fail": "unresolved_source_obligation:" + issue["id"]}

    too_many = "返回庭院次数过多，强行停止"
    if local_notifications:
        excessive = [_local_notice(too_many), {"wait": 2000}, _local_stop(too_many)]
    else:
        excessive = [gap("too_many_returns", (836, 842), "back_time > 10",
            [_push("返回庭院次数过多,强行停止"), {"effect": "sleep", "ms": 2000}, _stop()], True,
            ["source_push", "source_lifecycle/stop"])]
    case("too_many_returns", _expr("back_time > 10"), excessive)
    case("local_reset", _expr("True"), [{"set": {"yard503_arrived": False, "yard503_next_scheme": repr("")}}],
         outcome=None, bookkeeping=True)
    enabled_order = []
    # JS Object.keys on these non-integer keys keeps declaration insertion order.
    for group in declaration:
        for item in group.get("config", []):
            name = item["name"]
            if not re.fullmatch(r"oper_\d+", name):
                continue
            index = int(name.split("_")[1])
            if index >= len(operators):
                raise UnsupportedHandler("503 configured operator is outside the source declaration")
            enabled_order.append(index)
            branch = _operator_case(503, index, operators[index], colors)
            branch.update(id="enabled_" + str(index), when=_all(_expr("back and " + name), branch["when"]),
                          retest_group="enabled_operators")
            branch["do"].append({"inc": "back_time"})
            cases.append(branch)
    model["proof"]["enabled_operator_order"] = enabled_order
    idle = ("back and oper_find_minus_1 and elapsed_ms - core0_run_start_ms > 3000 "
            "and elapsed_ms - " + CURRENT_DATE_VAR + " > 3000 "
            "and (handler_last_ms < 0 or elapsed_ms - handler_last_ms > 3000)")
    case("fallback_home_icon", _all(_expr(idle), {"find": "左上_返回庭院"}),
         [{"click_found": True, "offset": [0, 0, 15, 15], "delay": 1200},
          {"inc": "back_time"}, {"log": "点击左上角返回庭院图标"}])
    source_conditions = [_operator_case(503, index, {"desc": operators[index]["desc"]}, colors)["when"]
                         for index in (8, 9, 13, 16)]
    yard = _all(_expr("back"), {"any": source_conditions})
    town = _operator_case(503, 4, operators[4], colors)
    town.update(id="old_town_before_yard", when=_all(yard, town["when"]), retest_group="yard_nested")
    cases.append(town)  # This path deliberately does NOT increment back_time.
    arrival = _operator_case(503, 12, {"desc": operators[12]["desc"]}, colors)["when"]
    case("arrived_resolve_runtime", _all(yard, arrival), [{"set": {
        "yard503_arrived": True, "yard503_next_scheme": "yard503_runtime_target"}}], outcome=None)
    reached = "back and yard503_arrived"
    case("consume_super_target", _expr(reached + " and not yard503_next_scheme"), [{"set": {
        "yard503_next_scheme": "super_next_scheme_name", "super_next_scheme_name": repr("")}}],
        outcome=None, bookkeeping=True)
    case("configured_target", _expr(reached + " and scheme_switch_enabled"),
         [{"set": {"yard503_next_scheme": "next_scheme"}}], outcome=None, bookkeeping=True)
    case("target_no_action", _expr(reached + " and yard503_next_scheme == '__不做动作__'"),
         [{"wait": 3000}])
    rerun = gap("target_rerun", (878, 906), "resolved target is truthy and not __不做动作__",
        [{**_rerun({"var": "yard503_next_scheme"}), "runtime_params_after_setCurrentScheme": None},
         {"effect": "sleep", "ms": 3000}], True,
        ["source_rerun/actual named target or special sentinel", "source_lifecycle"])
    case("target_rerun", _expr(reached + " and yard503_next_scheme and yard503_next_scheme != '__不做动作__'"), [rerun])
    if local_notifications:
        stopping = [_local_notice("已返回庭院并停止，请查看。"), _local_stop("已返回庭院并停止")]
    else:
        stopping = [gap("arrived_stop", (907, 909), "no target and afterCountOper == 停止脚本",
            [_push("[${schemeHistory names joined by 、}]已停止，请查看。"), _stop()],
            "false if the stop broadcast does not interrupt first", ["source_push", "source_lifecycle/stop"])]
    case("arrived_stop", _expr(reached + " and not yard503_next_scheme and afterCountOper == '停止脚本'"),
         stopping, outcome=False)
    closing = gap("arrived_close_app", (910, 917), "no target and afterCountOper == 关闭应用",
        [{"effect": "source_stop_related_apps", "settings": ["defaultLaunchAppList", "kill_related_app_mode"]},
         _push("[${schemeHistory}]已停止，应用[${packageNames}]已杀，请查看。"),
         {"effect": "sleep", "ms": 2000}, _stop()], True,
        ["source_stop_related_apps", "source_push", "source_lifecycle/stop"])
    case("arrived_close_app", _expr(reached + " and not yard503_next_scheme and afterCountOper == '关闭应用'"),
         [{"wait": 1000}, closing])
    case("arrived_no_target", _expr(reached), outcome=False)
    model["resource_specs"] = _used_resources(cases, colors)
    model["proof"].update(unresolved_source_obligations=copy.deepcopy(obligations), bookkeeping_cases=internal,
        local_notifications=bool(local_notifications),
        limitations=["source rerun/Push/stop/app-exit are explicit failure gates",
                     "runtime payload/superGlobal target are initial inert snapshots until source lifecycle exists",
                     "vendor find misalignment and non-16:9 anchor behavior require separate evidence"],
        source_behavior_adaptations=[{"source": "myToast('点击左上角返回庭院图标')",
            "native": "log event after the same click and back_time increment",
            "difference": "does not render an in-game toast"}])
    packet = {"handler": model, "source_obligations": obligations, "complete": False,
              "original_task_complete": False, "coverage": "guarded-yard-handler-partial"}
    _data(packet)
    return packet


def load_yard_handler(upstream_root, **options):
    root = Path(upstream_root)
    pins = HELPER_PINS | ({PUSH_SELECTION: PUSH_SELECTION_PIN} if options.get("local_notifications") else {})
    for relative, pin in pins.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != pin:
            raise UnsupportedHandler("503 helper fingerprint mismatch: " + relative)
    return compile_yard_handler((root / SOURCE_FILE).read_text(encoding="utf-8"),
                                convert_colors(root / "src/common"), **options)


def yard_workflow(name, definitions, *, scheme=None, config_overrides=None, **options):
    """Lower with the exact source config alias and shared currentDate binding."""
    scheme = copy.deepcopy(scheme or {})
    if "503" in scheme.get("config", {}):
        scheme["config"]["503"] = _normalize_config_aliases(scheme["config"]["503"], label="scheme config")
    overrides = copy.deepcopy({} if config_overrides is None else config_overrides)
    if "503" in overrides:
        overrides["503"] = _normalize_config_aliases(overrides["503"], label="config overrides")
    result = core_workflow(name, definitions, scheme=scheme, config_overrides=overrides, **options)
    result["workflow"]["yard_handler_contract"] = {"version": 1, "source_complete": False,
        "config_aliases": copy.deepcopy(CONFIG_ALIASES), "source": SOURCE_FILE,
        "return_scheme_is_not_goto_main": True}
    return result
