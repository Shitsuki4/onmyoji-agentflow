"""Compile inert AutoJS handlers into a data-only native dispatcher contract.

Integration entry points are ``component_handler`` (existing pinned fragments),
``literal_handler`` (strict data declarations or pinned small methods),
``compose_handlers``, and ``phase_workflow``. No upstream module is imported and
no source, callback, JavaScript, or Python expression is executed. Scalar
expressions use the same restricted AST evaluator as format:1.

Once per outer tick the compiled phases scan source order against ONE cached
frame. A false return yields
to the next handler; true ends the scan; null continues the current handler.
Evaluate a handler's guard once on entry, not again after its own assignments.
Retests refresh the frame and rescan ONLY the indicated operator group, once,
without restarting earlier handlers or applying another retest. Count events
occur before the branch's inputs, including detection-only events and events
in a handler returning false. Read elapsed_ms at EACH event:
increment if id != lastFunc OR now-lastFuncDateTime > 7500; update the timestamp
even for a suppressed increment. notForCnt/id=0 events change neither field.
Only true returns refresh Script.currentDate (the inactivity clock).

``scheme_transition`` is a second, explicit native action for audited rerun
calls. It must resolve the actual named scheme (including its config and
history), not replace it with a home-navigation click. Unresolved targets are
reported. The compiler never claims these models are executable by an engine
which lacks the required actions. ``trace_cycle`` is a pure offline contract
oracle, not a device runner: it consumes supplied recognition facts and returns
native action intents. It neither captures frames nor sends input.

Preferred narrow integration: ``phase_workflow`` expands the dispatch into
ordinary phase-guarded states and native set/click/wait actions. It requires only
``handler_control`` with finite begin/end operations. begin caches the existing frame; internal
phases reuse it without outer-loop sleeping; end releases it and applies one
normal loop delay. Explicit retests refresh that cached frame; phase guards
automatically scope the existing full-state rescan to the operator group.
The read-only elapsed_ms built-in supplies counting time; its origin must stay
consistent with stored timestamps across resume. Counting is ordinary atomic
set expressions and preserves the matcher's found-position anchor. Host cancellation and
budgets still run at every native input boundary. Phase metadata is declarative;
there are no callbacks. native_workflow aliases this same narrow lowering.

Lifecycle boundary: initial_vars may resume only phase 0 (a completed source
scan). Runner continues elapsed_ms from its saved value; this preserves logical
retry time but does not include downtime between Runner instances. Mid-handler
resume is unsupported and must fail with handler_resume, without resetting PC
or replaying inputs: the required cached frame/found anchor is not persisted.
This is not a complete implementation of Script.pause/rerun/stop. In source,
_run resets currentDate even on pause-resume; fresh _run clears runTimes/global,
while runFDate/history and superGlobal have distinct lifetimes. lastFunc and
lastFuncDateTime are instance fields, not reset by fresh _run. Their cross-rerun
behavior, inactivity handler 000, named transitions and wall-clock pause gaps
still require a source lifecycle controller. A new native source session uses
the declared initial defaults; the compiler never infers a rerun from retries.

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from ..workflow.expr import compile_expr, evaluate
from ..workflow.schema import ACTION_KEYS, validate_action, validate_condition
from .jsliteral import Parser, extract_literal_after, find_consts, parse


class UnsupportedHandler(ValueError):
    """Source/model cannot be translated without silently losing behavior."""


CONTRACT_VERSION = 1
COMMON_DEFAULTS = {"loopDelay": 200, "afterClickDelayBase": 0,
                   "afterClickDelayRandom": 200, "colorSimilar": 93,
                   "multiColorSimilar": 97}
# Exact text as read by Path.read_text; arbitrary operatorFunc bodies never use this path.
AUDITED_METHODS = {
    601: "4d073142f3b7f2f299814ecd1af14fb5a673f01d50e43900f9d4dce052f11c76",
    604: "a3832ae56285a98162dac7df9a7cbf37820d9219ad8bc471e2280b858c101c79",
    606: "06e2488c6b9a4cd51cc43619d095cae5652d52604bc813b25f6a6ad05ad3b884",
}
NATIVE_CONTRACT = {
    "version": CONTRACT_VERSION, "frame": "cached-until-explicit-retest",
    "priority": "source-order-first-true", "guard": "latched-on-handler-entry",
    "returns": {"true": "end-cycle", "false": "next-handler", "null": "next-case"},
    "counter": {"suppression_ms": 7500, "comparison": ">", "clock": "monotonic-ms-per-event",
                "timestamp_on_suppressed": True, "before_inputs": True,
                "not_for_count_mutates_clock": False},
    "retest": "one-refresh-rescan-same-operator-group-no-retest",
    "config_precedence": ["declaration-default", "scheme-config", "explicit-override"],
    "shared_state": "one-session; reset-on-fresh-start; preserve-on-resume",
    "inactivity_clock": "refresh-only-on-true-return",
    "input_policy": "native-validation-budget-cancellation-and-recheck-per-input",
    "host_limits": "apply-recognition/progress/repeat-limits-to-handler-outcomes-not-dispatch-wrapper",
    "geometry": "1280x720-normalized; raw anchor metadata retained",
    "timing": "operation delay + common base + native sampled common jitter",
    "resume": {"boundary": "completed-source-cycle-phase-0-only", "mid_handler": "handler_resume-error",
               "elapsed_ms": "saved-clock-plus-active-run-time; excludes-between-run-downtime",
               "source_pause_rerun_stop_equivalence": False},
}


def _data(value):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise UnsupportedHandler("handler model must contain finite JSON data only") from error
    if isinstance(value, dict):
        if "$ref" in value:
            raise UnsupportedHandler("unresolved JavaScript identifier")
        if set(value) & {"code", "eval", "exec", "callback", "operatorFunc", "javascript", "python"}:
            raise UnsupportedHandler("code/callback fields are forbidden")
        for item in value.values():
            _data(item)
    elif isinstance(value, list):
        for item in value:
            _data(item)


def _ident(name):
    if not isinstance(name, str) or not name.isidentifier():
        raise UnsupportedHandler(f"invalid scalar variable name: {name!r}")
    return name


def _number(value, label, *, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise UnsupportedHandler(f"{label} must be a finite number >= {minimum}")
    return value


def _expr(text, renames):
    tree = compile_expr(str(text))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in renames:
            node.id = renames[node.id]
    return ast.unparse(tree)


def _condition(condition, renames):
    out = copy.deepcopy(condition)
    if "expr" in out:
        out["expr"] = _expr(out["expr"], renames)
    for key in ("all", "any"):
        if key in out:
            out[key] = [_condition(c, renames) for c in out[key]]
    if "not" in out:
        out["not"] = _condition(out["not"], renames)
    if "test" in out:
        out["test"] = _expr(out["test"], renames)
    if "text_param" in out:
        out["text_param"] = renames.get(out["text_param"], out["text_param"])
    for condition_key, param_key in (("ocr_full", "keyword_var"), ("ocr_single", "equals_var")):
        spec = out.get(condition_key)
        if spec is not None and param_key in spec:
            spec[param_key] = renames.get(spec[param_key], spec[param_key])
    return out


def _defaults(groups):
    out = {}
    if not isinstance(groups, list):
        raise UnsupportedHandler("config declaration must be a list")
    for group in groups:
        if not isinstance(group, dict):
            raise UnsupportedHandler("malformed config group")
        for item in group.get("config", []):
            if not isinstance(item, dict) or "name" not in item or "default" not in item:
                raise UnsupportedHandler("config item requires name/default")
            name = _ident(item["name"])
            if name in out:
                raise UnsupportedHandler(f"duplicate config key: {name}")
            out[name] = {"default": copy.deepcopy(item["default"])}
    return out


def _count(counter_id, not_for_count=False):
    return {"counter_id": counter_id, "not_for_count": not_for_count}


def _used_resources(cases, specs):
    names = set()

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"res", "find", "image", "ocr", "click", "swipe"} and isinstance(item, str):
                    names.add(item)
                elif key in {"find_near", "find_column"} and isinstance(item, dict):
                    names.update(item[field] for field in ("target", "reference") if isinstance(item.get(field), str))
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(cases)
    missing = names - set(specs)
    if missing:
        raise UnsupportedHandler(f"missing recognition resources: {sorted(missing)}")
    return {name: copy.deepcopy(specs[name]) for name in sorted(names)}


def component_handler(entry, root, *, pins=None):
    """Adapt the existing ComponentBuilder interface, retaining framework effects.

    ``pins`` must come from an audited catalog when provided. The default is the
    installed component-pins.yaml. Fingerprint misses return None before reads.
    """
    from .components import ComponentBuilder, matches_component_pin
    from ..workflow.schema import bundled_dir
    from ..yamlio import load_yaml
    if entry.get("source") != "assttyys" or entry.get("kind") != "component":
        return None
    if pins is None:
        pins = load_yaml(bundled_dir() / "translations/component-pins.yaml") or {}
    if not matches_component_pin(entry, pins):
        return None
    fingerprint = entry["fingerprint"]
    from pathlib import Path
    snapshots = Path(root).resolve() / "resources/upstream/assttyys/programs/src"
    for relative in entry.get("entry_files", []):
        if not (snapshots / (relative + ".txt")).resolve().is_relative_to(snapshots):
            raise UnsupportedHandler("source snapshot path escapes the inert source root")
    builder = ComponentBuilder(entry, root)
    raw = builder.build()
    contract = raw.get("component_contract")
    if not contract:
        raise UnsupportedHandler("component requires an explicit framework contract")
    fid = contract["id"]
    if entry["id"] != f"assttyys:func:{fid:03d}":
        raise UnsupportedHandler("catalog/component id mismatch")
    cases = []
    for state in raw["states"]:
        branch = {"id": state["id"], "when": copy.deepcopy(state["when"]),
                  "do": copy.deepcopy(state["do"]), "return": True, "count_events": []}
        match = re.match(r"op_(\d+)", state["id"])
        index = int(match[1]) if match else None
        counter_id = contract.get("counter_id")
        if counter_id is not None and index is not None:
            branch["count_events"] = [_count(counter_id, builder.ops[index].get("not_for_count", False))]
        if state.get("retest_ms"):
            branch["retest_ms"] = state["retest_ms"]
        if fid == 1:
            branch["retest_group"] = ("auto" if "_auto_" in state["id"] else "ready")
        if fid == 38:
            # Two nested Script.oper(id:38) matches, even for an unhandled empty room.
            if index == 1:
                for empty_index in (1, 2, 3):
                    empty = copy.deepcopy(branch)
                    empty.update(id=f"empty_{empty_index}",
                                 when={"all": [builder.when(0), builder.when(empty_index)]},
                                 do=[], **{"return": False})
                    empty["count_events"] = [_count(38), _count(38, builder.ops[empty_index].get("not_for_count", False))]
                    cases.append(empty)
                continue
            branch["count_events"] = [_count(38), _count(38)]
        elif fid == 509:
            # The source's outer guard remains true for this invocation after flag clearing.
            branch["when"] = branch["when"]["all"][1]
            if index == 3:
                branch["do"] = [{"set": {"change_shikigami_flag": False}}]
                branch["return"] = None
                branch["retest_group"] = "records_check"
            else:
                branch["retest_group"] = "navigation"
        elif fid == 990 and index in (5, 6):
            branch["do"] = [{"set": {"shaoTiao": False}}]
        elif fid == 990 and index is None:
            branch["do"] = []  # Original active fall-through returns true without sleeping.
        cases.append(branch)
    handler = {"id": fid, "name": entry.get("title", str(fid)), "params": raw.get("params", {}),
               "vars": raw.get("vars", {}), "resources": raw.get("resources", []),
               "resource_specs": _used_resources(cases, builder.colors), "cases": cases,
               "unmatched_return": False,
               "proof": {"catalog_id": entry["id"], "fingerprint": fingerprint,
                         "source_sha256": hashlib.sha256(builder.source.encode("utf-8")).hexdigest(),
                         "scope": "audited-component-adapter"}}
    if fid == 509:
        handler["guard"] = {"expr": "change_shikigami_flag"}
    return handler


def _declaration(source):
    """Parse only class data members, rejecting all unrecognised executable syntax."""
    header = re.search(r"export\s+class\s+(\w+)(?:\s+implements\s+[\w,\s]+)?\s*\{", source)
    if not header:
        raise UnsupportedHandler("expected an exported data-only class")
    prefix = Parser(source[:header.start()])
    while True:
        prefix.ws()
        if prefix.i == len(prefix.s):
            break
        rest = prefix.s[prefix.i:]
        match = re.match(r"import\s+(?:\{[^}]*\}|\w+)\s+from\s+['\"][^'\"]+['\"]\s*;", rest)
        if not match:
            match = re.match(r"const\s+\w+\s*=\s*-?\d+\s*;", rest)
        if not match:
            raise UnsupportedHandler("unrecognised top-level executable syntax")
        prefix.i += match.end()
    parser = Parser(source, find_consts(source))
    parser.i = header.end()
    members = {}
    while True:
        parser.ws()
        if parser.i >= len(source):
            raise UnsupportedHandler("unterminated class")
        if source[parser.i] == "}":
            parser.i += 1
            break
        match = re.match(r"(id|name|desc|config|operator)\s*(?::\s*IFuncOperatorOrigin\[\])?\s*=", source[parser.i:])
        if not match or match[1] in members:
            raise UnsupportedHandler("custom methods/duplicate/unknown class members need a pinned translator")
        parser.i += match.end()
        value_start = parser.i
        members[match[1]] = parser.value()
        literal_source = source[value_start:parser.i]
        if re.search(r"`(?:\\.|[^`])*\$\{", literal_source):
            raise UnsupportedHandler("template interpolation is code, not a data literal")
        if re.search(r"\\(?:[bfrv0xu]|[1-9])", literal_source):
            raise UnsupportedHandler("string escape is outside the audited literal subset")
        value_end = parser.i
        parser.ws()
        if parser.i < len(source) and source[parser.i] == ";":
            parser.i += 1
        elif parser.i < len(source) and source[parser.i] != "}" and not re.search(r"[\r\n]", source[value_end:parser.i]):
            raise UnsupportedHandler("class members need a semicolon or source newline")
    parser.ws()
    tail = source[parser.i:].strip()
    if tail and not re.fullmatch(r";?\s*export\s+default\s+new\s+" + re.escape(header[1]) + r"\(\)\s*;?", tail):
        raise UnsupportedHandler("unrecognised code after declaration")
    return members


def _operator_case(fid, index, raw, colors):
    if not isinstance(raw, dict) or set(raw) - {"desc", "oper", "operStepRandom", "retest", "notForCnt"}:
        raise UnsupportedHandler("unsupported operator fields")
    desc = raw.get("desc")
    if isinstance(desc, str) and desc:
        if desc not in colors or colors[desc].get("type") != "colors":
            raise UnsupportedHandler(f"unknown/non-colour comparison resource: {desc}")
        condition = {"res": desc}
    elif isinstance(desc, list) and len(desc) == 3 and desc[:2] == [1280, 720]:
        points = desc[2]
        if not isinstance(points, list) or any(not isinstance(p, list) or len(p) != 4 for p in points):
            raise UnsupportedHandler("malformed colour points")
        if any(type(p[0]) is not int or p[0] not in (-1, 0, 1, 2) or
               any(type(v) is not int for v in p[1:]) or not 0 <= p[3] <= 0xffffff for p in points):
            raise UnsupportedHandler("invalid anchored colour point")
        condition = {"colors": [[p[1], p[2], f"#{p[3]:06x}"] for p in points]}
    elif desc is None or desc == [] or desc == "":
        condition = {"expr": "True"}
    else:
        raise UnsupportedHandler("unsupported recognition declaration")
    if "operStepRandom" in raw:
        # Upstream chooses via device-id hash, not uniform per-click random.
        raise UnsupportedHandler("operStepRandom requires audited device-hash choice semantics")
    actions = []
    operations = raw.get("oper", [])
    if not isinstance(operations, list):
        raise UnsupportedHandler("oper must be a native operation list")
    for operation in operations:
        if (not isinstance(operation, list) or len(operation) not in (8, 9) or
                operation[:3] not in [[a, 1280, 720] for a in (-1, 0, 1, 2)]):
            raise UnsupportedHandler("malformed native operation; nothing may be silently discarded")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in operation):
            raise UnsupportedHandler("operation contains non-numeric values")
        delay = _number(operation[7], "operation delay")
        rect = operation[3:7]
        if rect == [-1, -1, -1, -1]:
            actions.append({"wait": delay})
        elif any(v < 0 for v in rect) or rect[0] > rect[2] or rect[1] > rect[3]:
            raise UnsupportedHandler("invalid click rectangle")
        else:
            action = {"click": rect, "delay": delay}
            if len(operation) == 9 and operation[8]:
                action["press_ms"] = _number(operation[8], "press time")
            actions.append(action)
    if type(raw.get("notForCnt", False)) is not bool:
        raise UnsupportedHandler("notForCnt must be boolean")
    case = {"id": f"op_{index}", "when": condition, "do": actions, "return": True,
            "count_events": [_count(fid, raw.get("notForCnt", False))],
            "source_operator": copy.deepcopy(raw)}
    retest = raw.get("retest", 0)
    if retest not in (0, -1):
        _number(retest, "retest")
        if retest > 60000:
            raise UnsupportedHandler("retest exceeds bounded native limit")
        case["retest_ms"] = retest
    return case


def literal_handler(source: str, colors: dict, *, expected_sha256: str):
    """Compile a fingerprint-constrained data class or an audited operatorFunc.

    expected_sha256 is a caller-owned audit pin, never derived as approval here.
    Method translators additionally require their built-in source pin.
    """
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256 or "") or digest != expected_sha256.lower():
        raise UnsupportedHandler("source fingerprint mismatch")
    audited_id = next((fid for fid, pin in AUDITED_METHODS.items() if pin == digest), None)
    if audited_id is None:
        members = _declaration(source)
    else:
        literal, _ = extract_literal_after(source, r"operator\s*:\s*IFuncOperatorOrigin\[\]\s*=")
        name = {601: "狩猎战", 604: "首领退治", 606: "阴门之门"}[audited_id]
        members = {"id": audited_id, "name": name,
                   "operator": parse(literal, find_consts(source))}
    fid = members.get("id")
    if type(fid) is not int or fid < 0 or not isinstance(members.get("operator"), list) or not members["operator"]:
        raise UnsupportedHandler("handler needs a nonnegative id and nonempty operator declaration")
    cases = [_operator_case(fid, i, op, colors) for i, op in enumerate(members["operator"])]
    if audited_id is not None:
        for case in cases:
            case["count_events"] = []  # These methods omit id in nested oper().
        rerun_case = cases[3] if audited_id == 606 else cases[1]
        rerun_case["do"].append({"scheme_transition": {"mode": "rerun", "target": "返回庭院"}})
        if audited_id == 604:
            rerun_case["do"].append({"wait": 1000})
        if audited_id == 606:
            # The first oper() call scans the entry/altar group before either popup.
            cases = [cases[i] for i in (0, 1, 4, 5, 2, 3)]
    handler = {"id": fid, "name": members.get("name", str(fid)), "params": _defaults(members.get("config", [])),
               "vars": {}, "resources": [], "resource_specs": _used_resources(cases, colors),
               "cases": cases, "unmatched_return": False,
               "proof": {"source_sha256": digest, "scope": "audited-method" if audited_id else "strict-literal-class"}}
    _data(handler)
    return handler


def compose_handlers(name, handlers, *, scheme=None, config_overrides=None, common_defaults=None,
                     common_overrides=None, shared_defaults=None):
    """Compose definitions using the source scheme's list/config precedence.

    Missing definitions fail closed. Repeated IDs in a source list remain repeated
    slots sharing one config and state. Runtime parameters used by rerun are NOT
    treated as scheme config. Conflicting shared defaults require an explicit
    shared_defaults value rather than depending on handler order.
    """
    definitions = {}
    for handler in handlers:
        _data(handler)
        if set(handler) - {"id", "name", "proof", "params", "vars", "resources", "resource_specs",
                           "cases", "guard", "unmatched_return"}:
            raise UnsupportedHandler("unsupported handler fields")
        fid = handler["id"]
        if type(fid) is not int or fid < 0 or fid in definitions:
            raise UnsupportedHandler("duplicate/invalid handler definition")
        if not handler.get("proof") or not handler.get("cases"):
            raise UnsupportedHandler("handler requires audit proof and nonempty cases")
        if handler.get("unmatched_return", False) is not False:
            raise UnsupportedHandler("unmatched handler must return false")
        definitions[fid] = copy.deepcopy(handler)
    scheme = copy.deepcopy(scheme or {})
    order = scheme.get("list", list(definitions))
    if not isinstance(order, list) or not order or any(type(fid) is not int or fid not in definitions for fid in order):
        raise UnsupportedHandler("scheme list contains a missing/invalid handler")
    config_overrides = config_overrides or {}
    common = {**COMMON_DEFAULTS, **(common_defaults or {}), **scheme.get("commonConfig", {}), **(common_overrides or {})}
    for key in ("loopDelay", "afterClickDelayBase", "afterClickDelayRandom"):
        _number(common[key], key)
    for key in ("colorSimilar", "multiColorSimilar"):
        if not 0 <= _number(common[key], key) <= 100:
            raise UnsupportedHandler("similarity must be 0..100")
    shared, params, resources, specs, slots = {}, {}, [], {}, []
    explicit_shared = shared_defaults or {}
    selected = set(order)
    for fid, handler in definitions.items():
        if fid not in selected:
            continue
        for key, value in handler.get("vars", {}).items():
            _ident(key)
            if key in shared and shared[key] != value and key not in explicit_shared:
                raise UnsupportedHandler(f"conflicting shared default: {key}")
            shared[key] = copy.deepcopy(value)
        for ref in handler.get("resources", []):
            if ref not in resources:
                resources.append(ref)
        for key, spec in handler.get("resource_specs", {}).items():
            if key in specs and specs[key] != spec:
                raise UnsupportedHandler(f"conflicting recognition resource: {key}")
            specs[key] = copy.deepcopy(spec)
    shared.update(copy.deepcopy(explicit_shared))
    for key in shared:
        _ident(key)
    for slot, fid in enumerate(order):
        handler = definitions[fid]
        renames = {key: f"cfg_{fid}_{_ident(key)}" for key in handler.get("params", {})}
        configured = {**scheme.get("config", {}).get(str(fid), {}), **config_overrides.get(str(fid), {})}
        if set(configured) - set(renames):
            raise UnsupportedHandler(f"handler {fid} has unsupported config keys")
        for key, original in handler.get("params", {}).items():
            spec = copy.deepcopy(original if isinstance(original, dict) else {"default": original})
            if key in configured:
                spec["default"] = copy.deepcopy(configured[key])
            params[renames[key]] = spec
        if set(renames.values()) & set(shared):
            raise UnsupportedHandler("shared variables cannot shadow namespaced config")
        compiled = {"id": fid, "slot": slot, "name": handler.get("name", str(fid)),
                    "proof": copy.deepcopy(handler["proof"]), "unmatched_return": False, "cases": []}
        if "guard" in handler:
            compiled["guard"] = _condition(handler["guard"], renames)
        for case in handler["cases"]:
            if (set(case) - {"id", "when", "do", "return", "count_events", "retest_ms", "retest_group", "source_operator"}
                    or "return" not in case):
                raise UnsupportedHandler("unsupported case fields or missing return")
            out = copy.deepcopy(case)
            out["id"] = f"h{slot}_{case['id']}"
            out["when"] = _condition(case["when"], renames)
            if out.get("return") is not None and type(out["return"]) is not bool:
                raise UnsupportedHandler("handler return must be true, false or null")
            for action in out.get("do", []):
                if isinstance(action.get("click"), dict):
                    action["click"] = {key: renames.get(value, value) if key.endswith("_param") else value
                                       for key, value in action["click"].items()}
                if "sample_duration" in action:
                    duration = action["sample_duration"]
                    duration["range_param"] = renames.get(duration["range_param"], duration["range_param"])
                if "set" in action:
                    if any(key in renames.values() or re.fullmatch(r"run_times_\d+", key) for key in action["set"]):
                        raise UnsupportedHandler("config/counter aliases are dispatcher-owned")
                    action["set"] = {key: _expr(expr, renames) for key, expr in action["set"].items()}
            compiled["cases"].append(out)
        slots.append(compiled)
    readonly = {"elapsed_s", "elapsed_ms", "actions", "handler_last_id", "handler_last_ms", "handler_last_handled_ms"}
    if set(shared) & readonly:
        raise UnsupportedHandler("read-only builtins cannot have shared defaults")
    variables = set(shared) | set(params) | readonly
    required = {"handler_control"}
    targets = set()
    for handler in slots:
        for case in handler["cases"]:
            for event in case.get("count_events", []):
                if set(event) - {"counter_id", "not_for_count"} or "counter_id" not in event:
                    raise UnsupportedHandler("unsupported count event fields")
                cid = event.get("counter_id")
                if cid is not None and (type(cid) is not int or cid < 0):
                    raise UnsupportedHandler("counter_id must be nonnegative or null")
                if type(event.get("not_for_count", False)) is not bool:
                    raise UnsupportedHandler("not_for_count must be boolean")
                if cid:
                    key = f"run_times_{cid}"
                    shared.setdefault(key, 0)
                    variables.add(key)
            for action in case.get("do", []):
                if "set" in action:
                    if set(action["set"]) & readonly:
                        raise UnsupportedHandler("cannot assign a read-only builtin")
                    variables.update(action["set"])
                if action.get("inc") in readonly:
                    raise UnsupportedHandler("cannot increment a read-only builtin")
    for handler in slots:
        if "guard" in handler:
            validate_condition(handler["guard"], specs, variables, "handler.guard")
        seen = set()
        for case in handler["cases"]:
            if case["id"] in seen:
                raise UnsupportedHandler("duplicate case id")
            seen.add(case["id"])
            validate_condition(case["when"], specs, variables, "handler.when")
            _number(case.get("retest_ms", 0), "retest_ms")
            if case.get("retest_ms", 0) > 60000:
                raise UnsupportedHandler("retest exceeds bounded native limit")
            for action in case.get("do", []):
                if "scheme_transition" in action:
                    transition = action["scheme_transition"]
                    validate_action(action, specs, variables, "handler.do")
                    required.add("scheme_transition")
                    if transition["mode"] == "rerun":
                        targets.add(transition["target"])
                else:
                    validate_action(action, specs, variables, "handler.do")
    program = {"kind": "autojs-handler-program", "version": CONTRACT_VERSION, "name": name,
               "handlers": slots, "params": params, "vars": shared, "resources": resources,
               "resource_specs": specs, "common_config": common,
               "native_contract": copy.deepcopy(NATIVE_CONTRACT), "required_primitives": sorted(required),
               "required_schemes": sorted(targets), "coverage": "handler_model",
               "original_task_complete": False}
    _data(program)
    return program


def native_workflow(program, *, supported_primitives=(), supported_builtins=()):
    """Alias for phase_workflow; no opaque dispatcher interpreter is required."""
    return phase_workflow(program, supported_primitives=supported_primitives,
                          supported_builtins=supported_builtins)


def phase_workflow(program, *, supported_primitives=(), supported_builtins=()):
    """Lower to ordinary format:1 states plus narrow begin/end controls.

    Required host semantics are in ``workflow.handler_dispatch``. An old host
    rejects the unknown handler_control action rather than silently running
    incorrectly with a fresh screenshot between yielding handlers. No file is
    written. Named colour comparisons are inlined so literal-only programs do
    not require a generated resource file; find/image/OCR assets retain refs.
    """
    _data(program)
    phase_var = "handler_phase"
    reserved = {phase_var, "handler_last_id", "handler_last_ms", "handler_last_handled_ms"}
    if reserved & (set(program["vars"]) | set(program["params"])):
        raise UnsupportedHandler("handler compiler reserved variable collision")
    for handler in program["handlers"]:
        for branch in handler["cases"]:
            for action in branch.get("do", []):
                if reserved & set(action.get("set", {})) or action.get("inc") in reserved:
                    raise UnsupportedHandler("handler writes a compiler reserved variable")

    def inline(condition):
        out = copy.deepcopy(condition)
        if "res" in out and program["resource_specs"][out["res"]].get("type") == "colors":
            spec = program["resource_specs"][out.pop("res")]
            out["colors"] = copy.deepcopy(spec["points"])
            if "similarity" in spec and "similarity" not in out:
                out["similarity"] = spec["similarity"]
        for key in ("all", "any"):
            if key in out:
                out[key] = [inline(c) for c in out[key]]
        if "not" in out:
            out["not"] = inline(out["not"])
        return out

    layout, cursor = [], 1
    for handler in program["handlers"]:
        groups = []
        for branch in handler["cases"]:
            key = branch.get("retest_group", "operators")
            if not groups or groups[-1]["key"] != key or groups[-1]["cases"][-1]["return"] is None:
                groups.append({"key": key, "cases": []})
            groups[-1]["cases"].append(branch)
        for group in groups:
            if any(c.get("retest_ms") for c in group["cases"]) and sum(g["key"] == group["key"] for g in groups) != 1:
                raise UnsupportedHandler("fallthrough/retest requires explicit separate operator groups")
        entry_phase = cursor
        cursor += 1
        for group in groups:
            group["phase"] = cursor
            cursor += 1
        layout.append({"handler": handler, "entry": entry_phase, "groups": groups})
    end_true, end_false = cursor, cursor + 1
    states = []

    def state(sid, phase, actions, *, condition=None, **metadata):
        when = {"expr": f"{phase_var} == {phase}"}
        if condition is not None:
            when = {"all": [when, inline(condition)]}
        states.append({"id": sid, "when": when, "do": actions, **metadata})

    state("handler_begin", 0, [{"handler_control": {"op": "begin", "version": 1}},
                                {"set": {phase_var: layout[0]["entry"]}}],
          handler_step={"kind": "begin"})
    for position, item in enumerate(layout):
        handler = item["handler"]
        next_handler = layout[position + 1]["entry"] if position + 1 < len(layout) else end_false
        prefix = f"handler_{handler['slot']}"
        state(prefix + "_enter", item["entry"], [{"set": {phase_var: item["groups"][0]["phase"]}}],
              condition=handler.get("guard", {"expr": "True"}), handler_step={"kind": "entry", "slot": handler["slot"]})
        state(prefix + "_disabled", item["entry"], [{"set": {phase_var: next_handler}}],
              handler_step={"kind": "unhandled", "slot": handler["slot"]})
        for index, group in enumerate(item["groups"]):
            next_group = item["groups"][index + 1]["phase"] if index + 1 < len(item["groups"]) else next_handler
            for branch in group["cases"]:
                outcome = branch["return"]
                target = next_group if outcome is None else end_true if outcome else next_handler
                actions = []
                for event in branch.get("count_events", []):
                    cid = event["counter_id"]
                    if cid and not event.get("not_for_count", False):
                        eligible = f"(handler_last_id != {cid} or elapsed_ms - handler_last_ms > 7500)"
                        # set evaluates every RHS against the same pre-action environment.
                        actions.append({"set": {f"run_times_{cid}": f"run_times_{cid} + {eligible}",
                                                "handler_last_id": cid, "handler_last_ms": "elapsed_ms"}})
                actions.extend(copy.deepcopy(branch.get("do", [])))
                actions.append({"set": {phase_var: target}})
                metadata = {"handler_step": {"kind": "case", "slot": handler["slot"], "return": outcome,
                                              "operator_group": group["key"],
                                              "count_events": copy.deepcopy(branch.get("count_events", []))},
                            "progress": outcome is True}
                if branch.get("retest_ms"):
                    metadata["retest_ms"] = branch["retest_ms"]
                state(branch["id"], group["phase"], actions, condition=branch["when"], **metadata)
            state(f"{prefix}_group_{index}_unmatched", group["phase"], [{"set": {phase_var: next_group}}],
                  handler_step={"kind": "unhandled-group", "slot": handler["slot"]})
    for handled, phase in ((True, end_true), (False, end_false)):
        state("handler_end_" + str(handled).lower(), phase,
              [{"set": {phase_var: 0}}, {"handler_control": {"op": "end", "handled": handled}}],
              handler_step={"kind": "end", "handled": handled})
    required = set(program["required_primitives"])
    missing = sorted(required - (set(supported_primitives) & set(ACTION_KEYS)))
    missing_builtins = sorted({"elapsed_ms"} - set(supported_builtins))
    control = {"version": 1, "phase_var": phase_var, "last_id_var": "handler_last_id",
               "last_ms_var": "handler_last_ms", "last_handled_ms_var": "handler_last_handled_ms",
               "counter_prefix": "run_times_", "suppression_ms": 7500, "comparison": ">",
               "source_order": [h["id"] for h in program["handlers"]],
               "common_config": copy.deepcopy(program["common_config"]),
               "cached_frame_until_end": True, "skip_internal_loop_delay": True,
               "count_preserves_found_anchor": True, "clock": "elapsed_ms",
               "clock_origin": "preserve-across-source-session-resume; reset-with-counters-on-fresh-start",
               "counting": "ordinary-atomic-set-actions", "required_builtins": ["elapsed_ms"],
               "resume_policy": copy.deepcopy(NATIVE_CONTRACT["resume"])}
    workflow = {"format": 1, "name": program["name"], "resources": copy.deepcopy(program["resources"]),
                "params": copy.deepcopy(program["params"]),
                "vars": {**copy.deepcopy(program["vars"]), phase_var: 0, "handler_last_id": -1,
                         "handler_last_ms": -1, "handler_last_handled_ms": -1},
                "loop_delay_ms": program["common_config"]["loopDelay"],
                "similarity": program["common_config"]["colorSimilar"],
                "handler_dispatch": control, "states": states}
    numeric_resources = {name: copy.deepcopy(spec) for name, spec in program["resource_specs"].items()
                         if spec.get("type") in ("find_colors", "ocr", "click", "swipe")}
    if numeric_resources:
        # Core loaders can supply exact numeric recognition data without an
        # external document, notably jade's explicit source similarity of 98.
        workflow["inline_resources"] = numeric_resources
    return {"workflow": workflow, "executable": not missing and not missing_builtins and not program["required_schemes"],
            "missing_primitives": missing, "required_schemes": copy.deepcopy(program["required_schemes"]),
            "missing_builtins": missing_builtins,
            "coverage": "handler_model", "original_task_complete": False}


@dataclass
class DispatchState:
    """Shared per-scheme state; retain this object on resume, replace on fresh start."""
    variables: dict = field(default_factory=dict)
    run_times: dict[int, int] = field(default_factory=dict)
    last_func: int | None = None
    last_func_ms: int | float | None = None
    last_handled_ms: int | float | None = None
    last_clock_ms: int | float | None = None
    started_ms: int | float | None = None

    def count(self, counter_id, now_ms, *, not_for_count=False):
        if counter_id is not None and (type(counter_id) is not int or counter_id < 0):
            raise UnsupportedHandler("invalid counter id")
        if type(not_for_count) is not bool:
            raise UnsupportedHandler("not_for_count must be boolean")
        _number(now_ms, "monotonic timestamp")
        if self.last_clock_ms is not None and now_ms < self.last_clock_ms:
            raise UnsupportedHandler("monotonic clock moved backwards")
        self.last_clock_ms = now_ms
        if counter_id is None or counter_id == 0 or not_for_count:
            return False
        increment = self.last_func != counter_id or (self.last_func_ms is not None and now_ms - self.last_func_ms > 7500)
        if increment:
            self.run_times[counter_id] = self.run_times.get(counter_id, self.variables.get(f"run_times_{counter_id}", 0)) + 1
            self.last_func = counter_id
            self.variables[f"run_times_{counter_id}"] = self.run_times[counter_id]
        self.last_func_ms = now_ms
        return increment


def _fact_key(condition):
    return json.dumps(condition, sort_keys=True, ensure_ascii=False)


def trace_cycle(program, facts: Iterable[dict], *, now_ms, state=None, refreshed_facts=()):
    """Offline oracle: native recognition facts in, state/action/return trace out.

    Each supplied fact is a visual leaf condition that matched this frame.
    Missing facts are false. Retests require an explicitly supplied fresh fact
    frame; no old-frame fallback is permitted. Native input intents are recorded,
    never executed. This oracle does not sample humanization/device-id jitter.
    """
    _data(program)
    _number(now_ms, "monotonic timestamp")
    state = state if state is not None else DispatchState()
    if state.last_clock_ms is not None and now_ms < state.last_clock_ms:
        raise UnsupportedHandler("monotonic clock moved backwards")
    state.last_clock_ms = now_ms
    if state.started_ms is None:
        state.started_ms = now_ms
    for key, value in program["vars"].items():
        state.variables.setdefault(key, copy.deepcopy(value))
    for cid, value in state.run_times.items():
        state.variables[f"run_times_{cid}"] = value
    params = {key: spec["default"] for key, spec in program["params"].items()}
    matched = {_fact_key(fact) for fact in facts}
    refreshed = iter(refreshed_facts)
    actions, returns, counts = [], [], []

    def env():
        return {**params, **state.variables, "elapsed_s": (now_ms - state.started_ms) // 1000,
                "elapsed_ms": now_ms - state.started_ms,
                "handler_last_id": state.last_func if state.last_func is not None else -1,
                "handler_last_ms": state.last_func_ms - state.started_ms if state.last_func_ms is not None else -1,
                "handler_last_handled_ms": state.last_handled_ms - state.started_ms if state.last_handled_ms is not None else -1,
                "actions": len(actions)}

    def match(condition):
        if "expr" in condition:
            return bool(evaluate(condition["expr"], env()))
        if "all" in condition:
            return all(match(c) for c in condition["all"])
        if "any" in condition:
            return any(match(c) for c in condition["any"])
        if "not" in condition:
            return not match(condition["not"])
        if any(key in condition for key in ("ocr", "text_param")) or condition.get("var"):
            raise UnsupportedHandler("offline oracle requires side-effect-free visual facts")
        return _fact_key(condition) in matched

    for handler in program["handlers"]:
        if not match(handler.get("guard", {"expr": "True"})):
            returns.append({"id": handler["id"], "slot": handler["slot"], "handled": False})
            continue
        index, returned = 0, False
        while index < len(handler["cases"]):
            case = handler["cases"][index]
            index += 1
            if not match(case["when"]):
                continue
            if case.get("retest_ms"):
                now_ms += case["retest_ms"]
                try:
                    matched = {_fact_key(fact) for fact in next(refreshed)}
                except StopIteration as error:
                    raise UnsupportedHandler("retest requires a fresh supplied fact frame") from error
                group = case.get("retest_group", "operators")
                case = next((candidate for candidate in handler["cases"]
                             if candidate.get("retest_group", "operators") == group and match(candidate["when"])), None)
                if case is None:
                    # That nested oper() returned false; subsequent statement groups still run.
                    while index < len(handler["cases"]) and handler["cases"][index].get("retest_group", "operators") == group:
                        index += 1
                    continue
                index = handler["cases"].index(case) + 1
            for event in case.get("count_events", []):
                changed = state.count(event["counter_id"], now_ms, not_for_count=event.get("not_for_count", False))
                counts.append({**event, "incremented": changed, "at_ms": now_ms})
            for action in case.get("do", []):
                if "set" in action:
                    before = env()
                    for key, expression in action["set"].items():
                        state.variables[key] = evaluate(str(expression), before)
                elif "inc" in action:
                    key = action["inc"]
                    state.variables[key] = state.variables.get(key, 0) + action.get("by", 1)
                else:
                    actions.append(copy.deepcopy(action))
                    now_ms += action.get("wait", action.get("delay", 0))
            result = case["return"]
            if result is None:
                continue
            returns.append({"id": handler["id"], "slot": handler["slot"], "handled": result})
            returned = True
            if result:
                state.last_handled_ms = now_ms
                state.last_clock_ms = now_ms
                return {"handled": True, "state": state, "actions": actions, "returns": returns, "counts": counts}
            break
        if not returned:
            returns.append({"id": handler["id"], "slot": handler["slot"], "handled": False})
    state.last_clock_ms = now_ms
    return {"handled": False, "state": state, "actions": actions, "returns": returns, "counts": counts}
