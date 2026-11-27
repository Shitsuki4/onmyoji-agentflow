"""Pinned, data-only translations of AutoJS 000/002/003, with fail-closed gaps.

``compile_core_handler`` returns a packet containing a normal handler definition
and exact unresolved source obligations. ``core_workflow`` composes such packets
(and ordinary handler definitions) using the existing phase compiler. It binds
000's currentDate through the existing handler_dispatch timestamp contract and
marks scalar bookkeeping phases so they cannot defeat unknown/repeat limits.
Use this wrapper when 000 is present; compose_handlers alone cannot bind clocks.

The emitted YAML is runnable with explicit failure gates. An explicitly bound
local notification profile supports the no-client stop paths of 000/002/003.
Rerun, external Push and stopRelatedApp still require caller contracts.
Effects preceding the first missing effect are retained; later effects and source
return values remain ordered data in the obligation. No upstream code executes.

Coordinates use the existing 1280x720 handler convention. Vendor anchor/search
and input-humanization equivalence remain declared limitations. Fresh starts and
completed-cycle retries work within the existing lifecycle contract; source
worker pause/resume, wall-clock downtime and mid-handler resume remain separate
from the timed pause cycle in handler 000.

Audited source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos.
"""
from __future__ import annotations

import copy
import hashlib
import math
import re
from pathlib import Path

from .handlers import (
    UnsupportedHandler, _count, _data, _defaults, _operator_case,
    _used_resources, compose_handlers, phase_workflow,
)
from .jsliteral import Parser, extract_literal_after, find_consts, parse


SOURCE_FILES = {
    0: "src/common/funcList/000_结束判断.ts",
    2: "src/common/funcList/002_退出结算.ts",
    3: "src/common/funcList/003.悬赏协作.ts",
}
SOURCE_PINS = {
    0: "adb976acd074e772040f3311de13f25eda5166e7281b768919ba431df363cbf1",
    2: "b208153d1dda34902e1aaa42d63153cb1624cf08b5633067bfba15d8da6deb7c",
    3: "7e1280a0cc8cc05400f81058430267aa25bf07b23f1f4df8ce9a5daecef14f01",
}
HELPER_PINS = {
    "src/system/script.ts": "839c55ffb354cc307170fa55babdfa64a1f8c339f1a54f94c23231d8d7fed3bd",
    "src/system/helperBridge.ts": "f7a595ed7aba8a41ce8ab9c71507f379273d9d26a25191fd1f53f34217dc2dae",
    "src/common/toolAuto.ts": "d0cf56ab35ff69b3308e2c0750698f9e866264698de6d7d9c170c310268eb5b8",
    "src/common/multiFindColors.ts": "c4b8c97a6110fa36f87cedc4398c91fc8c813b2dc6ed0c47899cc4083e727091",
    "src/common/multiDetectColors.ts": "bbead5d49fe2307bb28c368ea5bb5e853e148946819ffc5fed2a14a2d117e18a",
    "src/system/GlobalStore/index.ts": "5887bb21ca8e97d7819563043a0979310ac6a86f0ac5c9edb372594ecc3966d5",
}
PUSH_SELECTION = "src/system/PushClient/index.ts"
PUSH_SELECTION_PIN = "6138a962006f52cd143c5107fdeaf1a644f52b3ddcdc69284fee94271d217631"
NORMAL_SETTLEMENT_ORDER = (
    32, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 25, 10, 21, 12, 13, 14, 15,
    16, 17, 18, 11, 23, 24, 26, 27, 28, 29, 30, 31, 33, 34, 35, 36,
    37, 38, 39, 40,
)
CURRENT_DATE_VAR = "core0_current_date_ms"


def source_device_hash31(text: str) -> int:
    """Finite port of toolAuto.ts:248-259; accepts a caller-supplied literal only.

    No device identifier is read or retained. JS charCodeAt uses UTF-16 units,
    including surrogate pairs, and the sign bit is cleared before modulo.
    """
    if not isinstance(text, str):
        raise UnsupportedHandler("device hash input must be a literal string")
    raw, value = text.encode("utf-16-le", errors="surrogatepass"), 0
    for i in range(0, len(raw), 2):
        value = (31 * value + int.from_bytes(raw[i:i + 2], "little")) & 0xffffffff
    return value & 0x7fffffff


def _all(*conditions):
    return {"all": list(conditions)}


def _expr(text):
    return {"expr": text}


def _case(name, condition, actions=(), *, outcome=True, counts=(), group=None):
    result = {"id": name, "when": condition, "do": list(actions),
              "return": outcome, "count_events": list(counts)}
    if group:
        result["retest_group"] = group
    return result


def _reference(fid, start, end):
    return {"path": SOURCE_FILES[fid], "start_line": start, "end_line": end}


def _push(text):
    return {"effect": "source_push", "text": text,
            "attachment": "cached-helper-bitmap",
            "suffix": "runFDate/current wall time/formatted total runtime",
            "fallback": "play notification ringtone if no configured push client"}


def _rerun(target):
    return {"effect": "source_rerun", "target": target,
            "target_resolution": "Script.rerun special sentinels or actual named scheme; never navigate"}


def _stop():
    return {"effect": "source_stop", "lifetime": "Script._stop/thread/job/history/runFDate"}


def _local_notice(text):
    return {"log": text}


def _local_stop(reason):
    return {"stop": {"reason": reason, "result": "unknown", "verified": False,
                     "evidence": {"scope": "assttyys_local_stop"}}}


def _obligation(packet, key, start, end, condition, effects, source_return,
                *, blocking=True, required=()):
    item = {"id": f"core{packet['handler']['id']}.{key}",
            "source": _reference(packet["handler"]["id"], start, end),
            "condition": condition, "ordered_effects": copy.deepcopy(effects),
            "source_return": source_return, "blocking": blocking,
            "required_contracts": list(required)}
    packet["source_obligations"].append(item)
    return {"fail": f"unresolved_source_obligation:{item['id']} "
                    f"{item['source']['path']}:{start}-{end}"}


def _operators(source):
    literal, end = extract_literal_after(source, r"operator\s*:\s*IFuncOperatorOrigin\[\]\s*=")
    if not literal:
        return [], []
    parser, ops, ranges = Parser(literal, find_consts(source)), [], []
    parser.i = 1  # Opening array bracket; parse each object as inert data.
    offset = end - len(literal)
    while True:
        parser.ws()
        if literal[parser.i] == "]":
            return ops, ranges
        start = parser.i
        ops.append(parser.value())
        ranges.append([source.count("\n", 0, offset + start) + 1,
                       source.count("\n", 0, offset + parser.i - 1) + 1])
        parser.ws()
        if literal[parser.i] == ",":
            parser.i += 1


def _validate_config(params, configured):
    if not isinstance(configured, dict) or set(configured) - set(params):
        raise UnsupportedHandler("unknown core handler config key")
    for name, value in configured.items():
        default = params[name]["default"]
        if type(default) is bool and type(value) is not bool:
            raise UnsupportedHandler(f"{name} must be boolean")
        if type(default) is int and (type(value) not in (int, float) or
                                     not math.isfinite(value) or value < 0):
            raise UnsupportedHandler(f"{name} must be finite and nonnegative")
        if type(default) is str and not isinstance(value, str):
            raise UnsupportedHandler(f"{name} must be a string")
    for key, choices in (("after_operation", ("停止脚本", "切换方案", "随机等待")),
                         ("type", ("关闭", "接受", "拒绝")), ("yytype", ("", "关闭", "接受", "拒绝"))):
        if key in configured and configured[key] not in choices:
            raise UnsupportedHandler(f"unsupported {key}: {configured[key]!r}")


def compile_core_handler(source: str, colors: dict, *, expected_sha256=None,
                         config=None, device_hash31=None, scheme_history=None, local_notifications=False):
    """Compile ONLY exact audited bytes. Config sets defaults, never deletes arms.

    ``device_hash31`` is the nonnegative 31-bit result from the source's hash;
    absent hashes generate failure gates on random-choice operators, not uniform
    click_random actions. ``scheme_history`` is an optional initial ordered list
    of scheme names including the current scheme; it is valid only until rerun.
    Fixed text ranges such as '1,1' specialize pause/wait without sampling. A
    later runtime range change fails closed and requires recompilation.
    """
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    fid = next((key for key, pin in SOURCE_PINS.items() if pin == digest), None)
    if fid is None or (expected_sha256 is not None and expected_sha256.lower() != digest):
        raise UnsupportedHandler("core handler source fingerprint mismatch")
    if device_hash31 is not None and (type(device_hash31) is not int or not 0 <= device_hash31 <= 0x7fffffff):
        raise UnsupportedHandler("device_hash31 must be a nonnegative 31-bit integer")
    if scheme_history is not None and (not isinstance(scheme_history, list) or
                                       not all(isinstance(x, str) for x in scheme_history)):
        raise UnsupportedHandler("scheme_history must be an ordered literal list of names")
    if type(local_notifications) is not bool:
        raise UnsupportedHandler("local_notifications must explicitly describe a fresh no-client session")
    literal, _ = extract_literal_after(source, r"\bconfig\s*=")
    declaration = parse(literal, find_consts(source))
    params = _defaults(declaration)
    _validate_config(params, config or {})
    for key, value in (config or {}).items():
        params[key]["default"] = copy.deepcopy(value)
    name = re.search(r"\bname\s*=\s*'([^']*)'", source)[1]
    model = {"id": fid, "name": name, "params": params, "vars": {}, "resources": [],
             "resource_specs": {}, "cases": [], "unmatched_return": False,
             "proof": {"source_sha256": digest, "source_path": SOURCE_FILES[fid],
                       "scope": "pinned-core-family-partial", "source_complete": False,
                       "helper_pins": copy.deepcopy(HELPER_PINS),
                       "config_declaration": declaration,
                       "resource_costs": "No explicit source debits; no inferred stamina/jade charge."}}
    packet = {"handler": model, "source_obligations": [], "bookkeeping_cases": [],
              "framework_bindings": {}, "complete": False, "original_task_complete": False,
              "coverage": "guarded-core-handler-partial"}
    ops, ranges = _operators(source)
    model["proof"]["source_operator_count"] = len(ops)
    model["proof"]["source_operator_ranges"] = ranges
    if fid == 2:
        _settlement(packet, ops, colors, device_hash31, local_notifications)
    elif fid == 3:
        _collaboration(packet, ops, colors, local_notifications)
    else:
        _termination(packet, scheme_history, local_notifications)
    if local_notifications:
        model["proof"]["notification_profile"] = {
            "source": PUSH_SELECTION, "sha256": PUSH_SELECTION_PIN,
            "scope": "Fresh session with no configured Push client. The candidate records a native log.",
            "external_push": False,
        }
        _obligation(packet, "local_notification_tone", 1, 1, {"profile": "local_notifications"},
            [{"effect": "source_ringtone", "source": "src/common/toolAuto.ts:339-356",
              "native_substitute": "local log"}], "unchanged", blocking=False)
    model["resource_specs"] = _used_resources(model["cases"], colors)
    model["proof"]["unresolved_source_obligations"] = copy.deepcopy(packet["source_obligations"])
    model["proof"]["bookkeeping_cases"] = list(packet["bookkeeping_cases"])
    model["proof"]["framework_bindings"] = copy.deepcopy(packet["framework_bindings"])
    model["proof"]["source_lifecycle_contract"] = {
        "source": "src/system/script.ts:549-570,598-607,682-776",
        "fresh_run": "reset currentDate/runDate/runTimes/global; append scheme; keep existing runFDate",
        "pause_resume": "reset currentDate; preserve runDate/runTimes/global/history/runFDate",
        "last_count_event": "lastFunc/lastFuncDateTime are instance fields; fresh _run does not reset them",
        "stop": "SCRIPT_STOP broadcast; _stop clears history/runFDate and completes job unless flag/isPause",
        "rerun": "resolve source scheme/config/history then SCRIPT_RERUN broadcast; do not silently reset PC",
        "rerun_special_targets": {
            "__停止脚本__": "Push -> stop -> sleep(3000)",
            "__返回上个方案__": "previous history name, or Push/stop when no previous scheme",
            "__关闭应用__": "sleep(1000) -> stopRelatedApp -> Push -> sleep(2000) -> stop",
            "__不做动作__": "return false without broadcast",
            "__暂停__": "isPause=true -> stop -> sleep(3000)",
        },
        "named_target": "store schemeList .includes validation; setCurrentScheme(target); missing target Push/stop",
        "current_target": "rerun() without target broadcasts restart of current scheme",
    }
    model["proof"]["helper_dependencies"] = [
        "src/system/script.ts:598-607 source priority/currentDate/loopDelay",
        "src/system/script.ts:788-851 cached comparison/retest/count-before-input/notForCnt",
        "src/system/helperBridge.ts:57-97 anchor transforms;107-135 input bias/press/delay sampling",
        "src/system/helperBridge.ts:142-163 step choice; src/common/toolAuto.ts:248-259 32-bit UTF-16 hash",
        "src/system/script.ts:118-122 Push runtime suffix; src/common/toolAuto.ts:339-376 Push bitmap/ringtone",
        "src/system/script.ts:375-431 findMultiColor similarity/misalignedMatch",
        "src/common/multiFindColors.ts:1809-1821 jade points/region/similar=98 (003)",
        "src/system/script.ts:549-570,682-776 source reset/stop/rerun/pause lifecycle",
        "src/system/script.ts:921-963 app exit settings/API-vs-root behavior",
        "src/system/GlobalStore/index.ts:157-168,291 initial state (loop_add=true, running=undefined);319-324 superGlobal",
    ]
    model["proof"]["limitations"] = [
        "1280x720 coordinates; vendor non-16:9 anchors need a separate geometry contract",
        "Native rectangular inputs/common jitter do not reproduce getRegionBiasRnd2/getNormalRandom/press sampling",
        "No source rerun/pause/stop lifecycle equivalence or downtime-inclusive wall clock",
    ]
    packet["required_contracts"] = sorted({contract for item in packet["source_obligations"]
                                            for contract in item["required_contracts"]})
    _data(packet)
    return packet


def _settlement(packet, ops, colors, device_hash31, local_notifications):
    if len(ops) != 41:
        raise UnsupportedHandler("002 requires all 41 audited operators")
    model, cases = packet["handler"], packet["handler"]["cases"]
    model["proof"]["normal_operator_order"] = list(NORMAL_SETTLEMENT_ORDER)
    model["proof"]["priority"] = ["rechallenge:20,22", "no-sushi:19", "fail:9,10", "normal"]
    model["proof"]["device_choice"] = {"hash_supplied": device_hash31 is not None,
        "selection": "(source hash & 0x7fffffff) modulo candidate count; old weights ignored",
        "ninth_literal": "retained as press duration after selection, not discarded as old weight"}

    def op(index, prefix, guard="True", group="normal"):
        raw = copy.deepcopy(ops[index])
        missing = None
        if "operStepRandom" in raw:
            choices = raw.pop("operStepRandom")
            if device_hash31 is None:
                missing = _obligation(packet, f"{prefix}_{index}_device_choice", *model["proof"]["source_operator_ranges"][index],
                    {"config": guard, "operator": index, "group": group},
                    [{"effect": "device_hash_step_choice", "steps": choices,
                      "helper": "src/system/helperBridge.ts:142-163; src/common/toolAuto.ts:248-259"}],
                    True, required=["compile-time device_hash31 or native device_hash_step_choice"])
            else:
                raw["oper"] = [step[device_hash31 % len(step)] for step in choices]
        branch = _operator_case(2, index, raw, colors)
        branch.update(id=f"{prefix}_{index}", when=_all(_expr(guard), branch["when"]), retest_group=group)
        branch["source_operator"] = copy.deepcopy(ops[index])
        if missing:
            branch["do"] = [missing]
        return branch

    for index in (20, 22):
        cases.append(op(index, "rechallenge", "rechallenge", "rechallenge"))
    for enabled in (True, False):
        branch = op(19, "no_sushi_switch" if enabled else "no_sushi_stop", "no_sushi_switch_enabled" if enabled
                    else "not no_sushi_switch_enabled", "no_sushi")
        if not enabled and local_notifications:
            branch["do"].extend([_local_notice("体力不够已停止，请查看。"), _local_stop("体力不足")])
            branch["return"] = False
            cases.append(branch)
            continue
        effects = [_rerun({"config": "next_scheme"})] if enabled else [
            _push("体力不够已停止，请查看。"), _stop()]
        effects.append({"effect": "sleep", "ms": 3000})
        branch["do"].append(_obligation(packet, branch["id"], 508, 522,
            {"config": "no_sushi_switch_enabled" if enabled else "not no_sushi_switch_enabled", "operator": 19},
            effects, "undefined (yields; does not refresh currentDate)",
            required=["source_rerun" if enabled else "source_push", "source_lifecycle"]))
        branch["return"] = False
        cases.append(branch)
    for index in (9, 10):
        branch = op(index, "fail", "fail", "fail")
        message = "战斗失败，已停止，请查看。"
        effects = [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 3000}]
        required = ["source_rerun", "source_lifecycle"]
        if local_notifications:
            branch["do"].append(_local_notice(message))
        else:
            effects.insert(0, _push(message))
            required.insert(0, "source_push")
        branch["do"].append(_obligation(packet, branch["id"] + "_transition", 524, 532,
            {"config": "fail", "operator": index}, effects, True, required=required))
        cases.append(branch)
    for index in NORMAL_SETTLEMENT_ORDER:
        cases.append(op(index, "normal"))


def _collaboration(packet, ops, colors, local_notifications):
    if len(ops) != 6:
        raise UnsupportedHandler("003 requires all six audited declarations")
    cases = packet["handler"]["cases"]

    def op(index, name, *, operation=None, condition=None, counts=None, group=None):
        raw = copy.deepcopy(ops[index])
        if operation is not None:
            raw["oper"] = [raw["oper"][operation]]
        branch = _operator_case(3, index, raw, colors)
        branch["id"] = name
        if condition is not None:
            branch["when"] = _all(condition, branch["when"])
        if counts is not None:
            branch["count_events"] = counts
        if group:
            branch["retest_group"] = group
        return branch

    for index in (2, 3):
        cases.append(op(index, f"cleanup_{index}", group="cleanup"))
    unexpected = op(4, "unexpected_login", group="unexpected")
    if local_notifications:
        unexpected["do"].extend([_local_notice("意外情况已停止，请查看。"), _local_stop("出现意外登录")])
    else:
        unexpected["do"].append(_obligation(packet, "unexpected_login", 148, 156, {"operator": 4},
            [_push("意外情况已停止，请查看。"), _stop(), {"effect": "sleep", "ms": 3000}], True,
            required=["source_push", "source_lifecycle"]))
    cases.append(unexpected)
    first = _operator_case(3, 0, {"desc": [1280, 720, [ops[0]["desc"][2][0]]]}, colors)["when"]
    gate = _all(_expr("switch and type == '接受'"), first)
    cases.append(_case("jade_probe", gate, outcome=None, counts=[_count(3)], group="jade_probe"))
    jade = colors.get("勾协判定")
    if not jade or jade.get("type") != "find_colors" or jade.get("similarity") != 98:
        failure = _obligation(packet, "jade_search_resource", 165, 183,
            {"first_point_gate": True, "config": "switch and type == '接受'"},
            [{"effect": "find_colors", "resource": "勾协判定", "similarity": 98,
              "source": "src/common/multiFindColors.ts:1809-1821", "misalignedMatch": True}],
            "true on accept/close; undefined if non-jade full comparison misses",
            required=["exact jade find resource including explicit similar:98"])
        cases.append(_case("jade_resource_blocked", gate, [failure], group="jade_result"))
    else:
        accept = _operator_case(3, 0, {"oper": [ops[0]["oper"][1]]}, colors)
        accept.update(id="jade_accept", when=_all(gate, {"find": "勾协判定"}), retest_group="jade_result")
        jade_notice = "接受到勾协，请确认是否影响到主体方案"
        accept["do"].append(_local_notice(jade_notice) if local_notifications else
            _obligation(packet, "jade_push", 165, 174, {"first_point_gate": True, "find": "勾协判定"},
                        [_push(jade_notice)], True, required=["source_push"]))
        cases.append(accept)
        # The close oper() deliberately has NO id; its retest argument is zero.
        close = op(0, "non_jade_close", operation=0,
                   condition=_all(gate, {"not": {"find": "勾协判定"}}), counts=[], group="jade_result")
        cases.append(close)
        # A matched jade-only probe suppresses the entire normal/yytype else arm.
        cases.append(_case("jade_unhandled", gate, outcome=False, group="jade_result"))
    normal = {"not": gate}
    for index, config_name, prefix in ((0, "type", "bounty"), (5, "yytype", "invitation")):
        for choice, action_index in (("关闭", 0), ("接受", 1), ("拒绝", 2)):
            selected = f"{config_name} == {choice!r}"
            if config_name == "yytype" and choice == "关闭":
                selected = f"({selected} or not yytype)"
            cases.append(op(index, prefix + "_" + str(action_index), operation=action_index,
                            condition=_all(normal, _expr(selected)), group="normal_" + prefix))
    packet["handler"]["proof"]["jade_semantics"] = {
        "entry": "first transformed point only; detection counts id3",
        "accept": "second id3 event before click, then Push",
        "non_jade_close": "no id/counter; retest=0; requires full desc",
        "fallthrough": "undefined; invitation skipped whenever jade-only probe matched",
        "unused_declaration": 1,
        "search_limit": "vendor FindMultiColor misalignedMatch=true is not modelled by exact native search",
    }


def _termination(packet, history, local_notifications):
    model, cases = packet["handler"], packet["handler"]["cases"]
    model["vars"] = {CURRENT_DATE_VAR: 0, "core0_run_start_ms": 0, "run_times_1": 0, "run_times_2": 0,
        "core0_time_notice_ms": 0, "core0_time_notice_set": False,
        "core0_count_notice_1": 0, "core0_count_notice_2": 0,
        "loop_add": True, "core0_history_available": history is not None,
        "core0_history_count": history.count(history[-1]) if history else 0,
        "core0_running": -1, "core0_running_until_ms": 0, "core0_pause_until_ms": 0,
        "core0_run_sample_ms": 0, "core0_pause_sample_ms": 0, "core0_pause_poll_ms": 0, "core0_rerun_delay_ms": 0,
        "core0_pause_notice_ms": 0, "core0_stop_reason": ""}
    packet["framework_bindings"] = {"last_handled_ms_var": CURRENT_DATE_VAR,
        "fresh_current_date_ms": 0, "source_run_start_ms": "core0_run_start_ms",
        "history_scope": "initial ordered snapshot, valid until any source rerun",
        "history_names": history, "counter_absence": "zero alias treated as absent until first positive count"}
    model["proof"]["shared_scalar_mapping"] = {
        "global.loop_add": "loop_add", "global.running": "core0_running (-1=undefined,1=true,0=false)",
        "global.currentNotifyDate": "core0_time_notice_ms plus core0_time_notice_set",
        "global.currentRunTimes": "core0_count_notice_1/core0_count_notice_2",
        "global.notifyTime": "core0_pause_notice_ms", "runDate": "core0_run_start_ms"}

    def internal(name, condition, actions):
        cases.append(_case(name, condition, actions, outcome=None, group=name))
        packet["bookkeeping_cases"].append(name)

    def sample(variable, config, unit):
        return {"sample_duration": {"var": variable, "range_param": config, "unit": unit}}

    def terminal(name, condition, lines):
        for mode in ("切换方案", "停止脚本", "随机等待"):
            actions = [{"set": {"core0_stop_reason": repr(name)}}]
            effects = []
            selected = _expr(f"after_operation == {mode!r}")
            if mode == "切换方案":
                effects = [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 3000}]
                needed = ["source_rerun", "source_lifecycle"]
            elif mode == "停止脚本":
                if local_notifications:
                    cases.append(_case(name + "_local_stop",
                        _all(condition, selected, _expr("not stop_with_launched_app_exit")),
                        [*actions, _local_notice("已达到方案停止条件，请查看。"), _local_stop("达到方案停止条件")],
                        group=name))
                    selected = _all(selected, _expr("stop_with_launched_app_exit"))
                effects = [_push("[${schemeHistory names joined by 、}]已停止，请查看。"),
                    {"effect": "source_stop_related_apps", "if_config": "stop_with_launched_app_exit",
                     "settings": ["defaultLaunchAppList", "kill_related_app_mode"],
                     "source": "src/system/script.ts:921-963"}, _stop(), {"effect": "sleep", "ms": 3000}]
                needed = ["source_push", "source_stop_related_apps (when enabled)", "source_lifecycle"]
            else:
                actions.extend([sample("core0_rerun_delay_ms", "after_operation_sleep", "seconds"),
                                {"wait": {"var": "core0_rerun_delay_ms"}}])
                effects = [_rerun(None), {"effect": "sleep", "ms": 3000}]
                needed = ["source_rerun (current scheme)", "source_lifecycle"]
            fail = _obligation(packet, name + "_" + str(("切换方案", "停止脚本", "随机等待").index(mode)),
                240, 261, {"trigger": _reference(0, *lines), "config": f"after_operation == {mode!r}"},
                effects, True, required=needed)
            actions.append(fail)
            cases.append(_case(name + "_" + str(len(cases)), _all(condition, selected), actions, group=name))

    terminal("inactivity", _expr("jspd_enabled_longtime_nodo and elapsed_ms - core0_current_date_ms > jspd_times_longtime_nodo * 60000"), (127, 133))
    internal("time_notice_init", _expr("jspd_enabled_zjsj and not core0_time_notice_set"),
        [{"set": {"core0_time_notice_ms": "elapsed_ms", "core0_time_notice_set": True}},
         {"log": "000 source total-duration notification initialized"}])
    internal("time_notice_update", _expr("jspd_enabled_zjsj and elapsed_ms - core0_time_notice_ms > jspd_txpl_zjsj * 1000"),
        [{"set": {"core0_time_notice_ms": "elapsed_ms"}}, {"log": "000 source remaining-duration notification due"}])
    terminal("total_duration", _expr("jspd_enabled_zjsj and core0_run_start_ms + jspd_times_zjsj * 60000 < elapsed_ms"), (136, 152))
    for cid, lines in ((1, (155, 167)), (2, (169, 180))):
        terminal(f"count_{cid}", _expr(f"jspd_enabled_{cid} and run_times_{cid} > 0 and run_times_{cid} >= jspd_times_{cid}"), lines)
        internal(f"count_notice_{cid}", _expr(f"jspd_enabled_{cid} and run_times_{cid} > 0 and run_times_{cid} != core0_count_notice_{cid}"),
            [{"set": {f"core0_count_notice_{cid}": f"run_times_{cid}"}}, {"log": f"000 source counter {cid} notification changed"}])
    history_failure = _obligation(packet, "loop_history", 183, 200,
        {"config": "loop_enabled", "shared": "loop_add and not core0_history_available"},
        [{"effect": "count_history", "value": "number of entries equal to last schemeName; includes current entry"}],
        "continues unless count > loop_times", required=["literal history snapshot or source lifecycle history"])
    cases.append(_case("loop_history_blocked", _expr("loop_enabled and loop_add and not core0_history_available"),
                       [history_failure], group="loop_history"))
    loop_failure = _obligation(packet, "loop_limit", 191, 196,
        {"config": "loop_enabled", "shared": "loop_add and core0_history_count > loop_times"},
        [_push("[${schemeHistory names joined by 、}]已停止，请查看。"),
         {"effect": "set_super_global", "name": "next_scheme_name", "value": "返回庭院"}, _rerun("关闭BUFF")],
        True, required=["source_push", "source_rerun", "source_lifecycle/superGlobal"])
    cases.append(_case("loop_limit", _expr("loop_enabled and loop_add and core0_history_available and core0_history_count > loop_times"),
                       [loop_failure], group="loop_limit"))
    internal("loop_clear", _expr("loop_enabled and loop_add and core0_history_available"),
             [{"log": "000 completed loops = history occurrence count minus one"}, {"set": {"loop_add": False}}])

    internal("pause_init", _expr("pause_enabled and core0_running == -1"),
        [sample("core0_run_sample_ms", "define_run_time", "minutes"),
         sample("core0_pause_sample_ms", "define_pause_time", "minutes"),
         {"set": {"core0_running": 1, "core0_running_until_ms": "elapsed_ms + core0_run_sample_ms",
                  "core0_pause_until_ms": "elapsed_ms + core0_run_sample_ms + core0_pause_sample_ms",
                  "core0_pause_poll_ms": "core0_pause_sample_ms // 10"}}])
    cases.append(_case("pause_begin", _expr("pause_enabled and core0_running == 1 and elapsed_ms >= core0_running_until_ms"),
        [{"set": {"core0_running": 0}}, {"log": "脚本暂停"}], group="pause_begin"))
    internal("pause_run_notice_init", _expr("pause_enabled and core0_running == 1 and not core0_pause_notice_ms"),
             [{"set": {"core0_pause_notice_ms": "elapsed_ms"}}])
    internal("pause_run_notice", _expr("pause_enabled and core0_running == 1 and elapsed_ms - core0_pause_notice_ms > 10000"),
             [{"set": {"core0_pause_notice_ms": "elapsed_ms"}}, {"log": "000 run-to-pause notification due"}])
    cases.append(_case("pause_complete", _expr("pause_enabled and core0_running == 0 and elapsed_ms >= core0_pause_until_ms"),
                      [{"set": {"core0_running": -1}}], group="pause_complete"))
    internal("pause_wait_notice", _expr("pause_enabled and core0_running == 0 and elapsed_ms - core0_pause_notice_ms > 10000"),
             [{"set": {"core0_pause_notice_ms": "elapsed_ms"}}, {"log": "000 pause-to-run notification due"}])
    cases.append(_case("pause_wait", _expr("pause_enabled and core0_running == 0"),
                      [{"wait": {"var": "core0_pause_poll_ms", "minimum_ms": 5000}}], group="pause_wait"))
    _obligation(packet, "toast_presentation", 126, 270, {"config": "enabled notification branches"},
        [{"effect": "source_toast", "format": "cvtTime: >3600 hours, >60 minutes, otherwise seconds; toFixed(2)",
          "native_substitute": "static log plus exact scalar notification clocks; not an equivalent toast"}],
        "unchanged", blocking=False, required=["finite source notification renderer"])


def core_workflow(name, definitions, *, scheme=None, config_overrides=None,
                  common_overrides=None, shared_defaults=None,
                  supported_primitives=("handler_control",), supported_builtins=("elapsed_ms",)):
    """Compose packets with normal handlers and lower guarded partial native YAML.

    ``executable`` means source-obligation-free and is always false for these
    families today. ``guarded_executable`` means the host can execute the native
    subset and will fail on a missing effect. Metadata survives serialization.
    """
    models = []
    for definition in definitions:
        if "handler" in definition:
            models.append(copy.deepcopy(definition["handler"]))
        else:
            models.append(copy.deepcopy(definition))
    program = compose_handlers(name, models, scheme=scheme, config_overrides=config_overrides,
                               common_overrides=common_overrides, shared_defaults=shared_defaults)
    for model in models:
        if model["id"] in SOURCE_FILES and model.get("proof", {}).get("scope") == "pinned-core-family-partial":
            configured = {key: program["params"][f"cfg_{model['id']}_{key}"]["default"] for key in model["params"]
                          if f"cfg_{model['id']}_{key}" in program["params"]}
            _validate_config(model["params"], configured)
    lowered = phase_workflow(program, supported_primitives=supported_primitives,
                             supported_builtins=supported_builtins)
    raw = lowered["workflow"]
    obligations, bindings = [], {}
    by_slot = {handler["slot"]: handler for handler in program["handlers"]}
    for handler in program["handlers"]:
        proof = handler.get("proof", {})
        for item in proof.get("unresolved_source_obligations", []):
            obligations.append({**copy.deepcopy(item), "slot": handler["slot"]})
        binding = proof.get("framework_bindings", {})
        if binding:
            bindings[str(handler["slot"])] = copy.deepcopy(binding)
            raw["handler_dispatch"]["last_handled_ms_var"] = binding["last_handled_ms_var"]
    for state in raw["states"]:
        step = state.get("handler_step", {})
        if step.get("kind") == "case":
            handler = by_slot[step["slot"]]
            internal_ids = handler.get("proof", {}).get("bookkeeping_cases", [])
            if state["id"] in {f"h{handler['slot']}_{key}" for key in internal_ids}:
                step["kind"] = "bookkeeping"
    contract = {"version": 1, "coverage": "guarded-core-handler-partial", "source_complete": False,
                "source_obligations": obligations, "framework_bindings": bindings,
                "required_contracts": sorted({contract for item in obligations for contract in item["required_contracts"]}),
                "lifecycle": "fresh/completed-cycle retry only; no source rerun or wall-clock downtime",
                "missing_effect_policy": "native prefix then explicit workflow_fail; never successful completion"}
    raw["core_handler_contract"] = contract
    guarded = lowered["executable"]
    lowered.update(executable=False, guarded_executable=guarded, coverage="guarded-core-handler-partial",
                   complete=False, source_obligations=obligations, program=program)
    _data(lowered)
    return lowered


def load_core_handler(upstream_root, fid, **options):
    """Read audited source and only required resource literals, never import them.

    Raw helper pins are verified against the supplied inert root. Resource
    conversion retains similar:98 (the older general converter omits it).
    """
    if fid not in SOURCE_FILES:
        raise UnsupportedHandler("only core handlers 000/002/003 are supported")
    root = Path(upstream_root)
    for relative, pin in HELPER_PINS.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != pin:
            raise UnsupportedHandler(f"core helper fingerprint mismatch: {relative}")
    if options.get("local_notifications") and hashlib.sha256((root / PUSH_SELECTION).read_bytes()).hexdigest() != PUSH_SELECTION_PIN:
        raise UnsupportedHandler("core Push client selection fingerprint mismatch")
    colors = {}
    if fid in (2, 3):
        from .assttyys import points_from_desc
        for filename, member, find in (("multiDetectColors.ts", "multiDetectColors", False),
                                       ("multiFindColors.ts", "multiFindColors", True)):
            source = (root / "src/common" / filename).read_text(encoding="utf-8")
            literal, _ = extract_literal_after(source, member + r"\s*:\s*\w+\s*=")
            for key, value in parse(literal, find_consts(source)).items():
                if find:
                    spec = {"type": "find_colors", "groups": [points_from_desc(g) for g in value["desc"]],
                            "region": value["region"][3:7] if value.get("region") else [0, 0, 1280, 720]}
                else:
                    spec = {"type": "colors", "points": points_from_desc(value["desc"])}
                if value.get("similar"):
                    spec["similarity"] = value["similar"]
                colors[key] = spec
    return compile_core_handler((root / SOURCE_FILES[fid]).read_text(encoding="utf-8"), colors, **options)
