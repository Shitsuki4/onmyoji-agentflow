"""Source-pinned assttyys preset controls for preparation and records."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .assttyys import convert_colors
from .core_handlers import HELPER_PINS, _all, _case, _expr, _operators, _push, _rerun
from .handlers import UnsupportedHandler, _count, _data, _defaults, _operator_case, _used_resources
from .jsliteral import extract_literal_after, find_consts, parse


SOURCE = "src/common/funcList/510_式神录预设过滤.ts"
SOURCE_PIN = "59a018c9484c60126cd8083a2931a382e0903780c710cc09ec6eb92342fa2804"
STATE = "change_shikigami_state"
ONCE_GROUP = "preset_once_groupNum"
ONCE_PRESET = "preset_once_defaultNum"
BATTLE_SOURCE = "src/common/funcList/315_上预设阵容.ts"
BATTLE_PIN = "dacd770c5bb021d998abf20c25d57ee35638b7a0ef0af72ccc3aec131235bbed"
BATTLE_PENDING = "shangyushe"
BATTLE_GROUP = "preset_once_team_groupNum"
BATTLE_PRESET = "preset_once_team_defaultNum"
WEEKLY_GROUPS = "ABCD"


def normalize_weekly_preset_config(config):
    """Lower the source's sole active weekly preset selector, 红叶."""
    result = dict(config)
    for suffix in WEEKLY_GROUPS:
        modes = f"weekMode_{suffix}"
        if modes in result:
            selected = result.pop(modes)
            if not isinstance(selected, list) or any(not isinstance(name, str) for name in selected):
                raise UnsupportedHandler(f"034 {modes} must be a list of upstream mode names")
            result[f"red_leaf_{suffix}"] = "红叶" in selected
        pair = f"preset_pair_{suffix}"
        if pair in result:
            configured = result.pop(pair)
            match = re.fullmatch(r"\s*([0-7])\s*[,，]\s*([0-4])\s*", configured) if isinstance(configured, str) else None
            if not match:
                raise UnsupportedHandler(f"034 {pair} needs a preset group 0–7 and a slot 0–4")
            result[f"preset_group_{suffix}"], result[f"preset_slot_{suffix}"] = map(int, match.groups())
    return result


def build_weekly_preset(b):
    switched = "miWenChange"
    b.model["vars"] = {switched: False, ONCE_GROUP: "", ONCE_PRESET: "", BATTLE_GROUP: "",
                       BATTLE_PRESET: "", STATE: "flushed", BATTLE_PENDING: False, "change_shikigami_flag": True}
    red_leaf = _all(_expr(f"not {switched}"), b.when(8))
    b.add("recognize_red_leaf", red_leaf, counts=[_count(34)], outcome=None, internal=True)
    for suffix in WEEKLY_GROUPS:
        selected = _all(red_leaf, _expr(f"red_leaf_{suffix}"))
        group, slot = f"preset_group_{suffix}", f"preset_slot_{suffix}"
        common = {switched: True, ONCE_GROUP: group, ONCE_PRESET: slot, BATTLE_GROUP: group, BATTLE_PRESET: slot}
        b.add(f"red_leaf_{suffix}_preset", _all(selected, _expr(f"{group} > 0")),
              [{"set": {**common, BATTLE_PENDING: True, STATE: repr("flushed"), "change_shikigami_flag": True}}])
        b.add(f"red_leaf_{suffix}_without_preset", selected,
              [{"set": {**common, BATTLE_PENDING: False, STATE: repr("finish")}}])
    # The source returns true on this image even when no group lists 红叶.
    b.add("red_leaf_without_selected_group", red_leaf)
    for index in range(8):
        b.add(f"weekly_{index}", b.when(index), [{**action, "recheck": True} for action in b.actions(index)])
    b.model["proof"]["source_state_bindings"] = {
        "global.miWenChange": switched, "global.preset_once_groupNum": ONCE_GROUP,
        "global.preset_once_defaultNum": ONCE_PRESET, "global.preset_once_team_groupNum": BATTLE_GROUP,
        "global.preset_once_team_defaultNum": BATTLE_PRESET, "global.shangyushe": BATTLE_PENDING,
        "global.change_shikigami_state": STATE, "global.change_shikigami_flag": "change_shikigami_flag",
    }


def build_weekly_orochi_preset(b):
    remaining = "zhenShe"
    pending = "change_shikigami_flag"
    b.model["vars"] = {remaining: 2, pending: True, STATE: "flushed", ONCE_GROUP: "", ONCE_PRESET: ""}
    active = _expr(f"{remaining} > 0")
    counter = [_count(1106)]

    def taps(index):
        return [{**action, "recheck": True} for action in b.actions(index)]

    for index in (0, 5):
        condition = _all(active, b.when(index))
        select_new = _expr("switch_group != '0' and switch_default != '0'")
        override = {ONCE_GROUP: "switch_group", ONCE_PRESET: "switch_default"}
        b.add(f"rearm_new_preset_{index}", _all(condition, select_new),
              [*taps(index), {"set": {**override, pending: True, STATE: repr("flushed")}}], counts=counter)
        b.add(f"keep_preset_{index}", condition, [*taps(index), {"set": override}], counts=counter)
    restore = {pending: True, STATE: repr("flushed"), ONCE_GROUP: repr(""), ONCE_PRESET: repr(""),
               remaining: f"{remaining} - 1"}
    b.add("restore_record_preset", _all(active, b.when(4)), [*taps(4), {"set": restore}], counts=counter)
    b.add("one_attempt_left", _all(active, b.when(6)), [*taps(6), {"set": {remaining: 1}}, {"log": "检测到只剩一次"}],
          counts=counter, outcome=None, internal=True)
    b.add("battle_room", _all(active, b.when(1)), taps(1), counts=counter)
    done = _expr(f"{remaining} == 0")
    b.add("clear_preset_on_finish", done, [{"set": {pending: False}}], outcome=None, internal=True)
    finished = _all(done, b.when(9))
    finish = b.gap("weekly_result_route", (219, 229), finished,
                  [_push("已完成两次真蛇，请查看。"), _rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 2000}],
                  True, ["source Push and confirmed rerun lifecycle"])
    b.add("weekly_finished", finished, [finish], counts=counter)
    for index in (2, 4):
        b.add(f"misc_{index}", b.when(index), taps(index), counts=counter)
    jade = b.when(8)
    jade_gate = b.gap("jade_conversion_dialog", (232, 237), jade,
                     [{"effect": "source_operators", "index": 8, "operations": b.ops[8]["oper"]}], True,
                     ["verify the jade dialog's transaction and obtain the user's decision if needed"])
    b.add("jade_conversion_dialog", jade, [jade_gate], counts=counter)
    b.add("close_result", b.when(10), taps(10), counts=counter)
    b.gap("left_notice", (203, 209), _all(active, b.when(6)),
          [{"effect": "source_toast", "text": "检测到只剩一次"}], "continued scanning",
          ["source toast presentation"], blocking=False)
    b.model["proof"]["source_state_bindings"] = {
        "global.zhenShe": remaining, "global.change_shikigami_flag": pending,
        "global.change_shikigami_state": STATE, "510.groupNum/defaultNum": [ONCE_GROUP, ONCE_PRESET],
    }


def compile_battle_preset(source, colors):
    source = source.replace("\r\n", "\n")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != BATTLE_PIN:
        raise UnsupportedHandler("315 source fingerprint mismatch")
    config, _ = extract_literal_after(source, r"\bconfig\s*=")
    params = _defaults(parse(config, find_consts(source)))
    operators, ranges = _operators(source)

    def tap(operation):
        return {**_operator_case(315, 0, {"oper": [operation]}, colors)["do"][0], "recheck": True}

    def picked(param, override, value):
        return _expr(f"{override} == {value} or {override} == {str(value)!r} "
                     f"or (not {override} and {param} == {str(value)!r})")

    opened = _operator_case(315, 0, operators[0], colors)
    cases = [_case("open", _all(_expr(BATTLE_PENDING), opened["when"]),
                   [{**action, "recheck": True} for action in opened["do"]])]
    cases[0]["retest_ms"] = opened["retest_ms"]
    inside = _operator_case(315, 1, operators[1], colors)["when"]
    x1, y1, x2, y2, spacing = operators[2]["oper"][0][3:]
    params["groupNum"]["choices"] = [str(n) for n in range(1, 8)]
    params["defaultNum"]["choices"] = [str(n) for n in range(1, 5)]
    deploy = tap(operators[4]["oper"][0])
    clear_pending = {"set": {BATTLE_PENDING: False, BATTLE_GROUP: repr(""), BATTLE_PRESET: repr("")}}
    for group in range(1, 8):
        dy = spacing * (group - 1)
        select_group = tap([*operators[2]["oper"][0][:3], x1, y1 + dy, x2, y2 + dy, 500])
        for slot, rectangle in enumerate(operators[3]["oper"], 1):
            condition = _all(inside, picked("groupNum", BATTLE_GROUP, group),
                             picked("defaultNum", BATTLE_PRESET, slot))
            cases.append(_case(f"apply_{group}_{slot}", condition,
                               [select_group, tap(rectangle), deploy, clear_pending]))
    cases.append(_case("invalid_pending_preset", inside, [{"fail": "战斗预设分组或阵容超出配置范围"}]))
    model = {"id": 315, "name": "上预设阵容", "params": params,
             "vars": {BATTLE_PENDING: False, BATTLE_GROUP: "", BATTLE_PRESET: ""},
             "cases": cases, "unmatched_return": False, "resources": [], "resource_specs": {},
             "proof": {"scope": "pinned-battle-preset-handler", "source_path": BATTLE_SOURCE,
                       "source_sha256": BATTLE_PIN, "source_operator_ranges": ranges,
                       "source_complete": True, "unresolved_source_obligations": [],
                       "adaptations": ["Use an empty value for unset one-time overrides.",
                                       "Recheck the preset screen before all three inputs.",
                                       "Fail on preset slots outside the declared range."]}}
    _data(model)
    return model


def load_preset_handler(upstream_root):
    root = Path(upstream_root)
    for path, fingerprint in {**HELPER_PINS, SOURCE: SOURCE_PIN}.items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != fingerprint:
            raise UnsupportedHandler(f"510 source fingerprint mismatch: {path}")
    return _compile((root / SOURCE).read_text(encoding="utf-8"), convert_colors(root / "src/common"))


def _compile(source, colors):
    config, _ = extract_literal_after(source, r"\bconfig\s*=")
    params = _defaults(parse(config, find_consts(source)))
    operators, ranges = _operators(source)
    cases, gaps = [], []

    def op(index, *, compare_only=False):
        raw = operators[index]
        return _operator_case(510, index, {"desc": raw["desc"]} if compare_only else raw, colors)

    def click(raw):
        action = _operator_case(510, 0, {"oper": [raw]}, colors)["do"][0]
        return {**action, "recheck": True}

    def when_state(value):
        return _expr(f"{STATE} == {value!r}")

    def assign_state(value):
        return {"set": {STATE: repr(value)}}

    def gap(key, lines, when, effects):
        identifier = f"preset510.{key}"
        gaps.append({"id": identifier,
                     "source": {"path": SOURCE, "start_line": lines[0], "end_line": lines[1]},
                     "condition": when, "ordered_effects": effects, "blocking": True,
                     "required_contracts": [effect["effect"] for effect in effects]})
        cases.append(_case(key, when, [{"fail": f"unresolved_source_obligation:{identifier}"}]))

    for index in (3, 4, 5, 6, 10):
        popup = op(index)
        cases.append(_case(f"popup_{index}", popup["when"],
                           [{**action, "recheck": True} for action in popup["do"]], counts=[_count(510)]))

    records = op(0, compare_only=True)["when"]
    sidebar = op(1)
    cases.append(_case("open_sidebar", _all(records, sidebar["when"]),
                       [{**action, "recheck": True} for action in sidebar["do"]]))
    expanded = _all(records, op(2, compare_only=True)["when"])
    fast = _all(expanded, _expr("fastMode"))
    top = op(9, compare_only=True)["when"]
    start = _all(fast, when_state("flushed"))
    gap("fast_list_reset", (229, 240), _all(start, {"not": top}),
        [{"effect": "source_bezier_swipe", "count": 2, "duration_ms_range": [500, 700],
          "after_delay_ms": 800, "pre_delay_ms": 100,
          "start": operators[2]["oper"][0], "end": operators[2]["oper"][1]}])
    reset = cases[-1]
    gate = reset["do"][0]
    reset["do"] = [{"wait": 100}, gate, {"wait": 100}, gate, {"handler_control": {"op": "refresh"}}]
    reset["return"] = None
    reset["retest_group"] = "list_reset"
    cases.append(_case("fast_reset_unverified", _all(start, {"not": top}),
                       [{"fail": "两次重置滑动后仍未识别到预设列表顶部"}]))

    def is_number(config_name, one_shot, value):
        configured = f"{config_name} == {str(value)!r}"
        if one_shot is None:
            return _expr(configured)
        return _expr(f"{one_shot} == {str(value)!r} or ({one_shot} and {one_shot} == {value}) "
                     f"or (not {one_shot} and {configured})")

    gap("fast_zero_group", (241, 249), _all(start, top, is_number("groupNum", ONCE_GROUP, 0)),
        [{"effect": "source_toast", "message": "预设参数为0,跳过"},
         {"effect": "source_global_write", "key": STATE, "value": "finish"}])
    group = operators[7]["oper"][0]

    def groups(identifier, condition, config_name, one_shot, next_state):
        for number in range(1, 9):
            x1, y1, x2, y2, spacing = group[3:]
            dy = spacing * (number - 1)
            action = click([*group[:3], x1, y1 + dy, x2, y2 + dy, 500])
            guarded = _all(condition, is_number(config_name, one_shot, number))
            cases.append(_case(f"{identifier}_{number}", guarded, [action, assign_state(next_state)]))
        gap(identifier + "_unresolved", (241, 260) if one_shot else (280, 291), condition,
            [{"effect": "source_Number_and_preset_group_bounds"}])

    def presets(identifier, current, config_name, one_shot, next_state):
        condition = _all(fast, when_state(current))
        for number, rect in enumerate(operators[8]["oper"], 1):
            cases.append(_case(f"{identifier}_{number}", _all(condition, is_number(config_name, one_shot, number)),
                               [click(rect), assign_state(next_state)]))
        gap(identifier + "_unresolved", (261, 279) if one_shot else (292, 303), condition,
            [{"effect": "source_Number_and_preset_slot_bounds"}])

    groups("first_group", _all(start, top), "groupNum", ONCE_GROUP, "change_team_default_1")
    presets("first_preset_once", "change_team_default_1", "defaultNum", ONCE_PRESET, "change_team_default_2")
    # 510 chooses a second group based on the persisted source config.
    second = _all(fast, when_state("change_team_default_2"))
    for having_second, next_state in ((True, "second_groud"), (False, "finish")):
        branch = _all(second, _expr("groupNum2 != '0'" if having_second else "groupNum2 == '0'"))
        for number, rect in enumerate(operators[8]["oper"], 1):
            cases.append(_case(f"first_preset_twice_{next_state}_{number}",
                               _all(branch, is_number("defaultNum", ONCE_PRESET, number)),
                               [click(rect), assign_state(next_state)]))
    gap("first_preset_twice_unresolved", (261, 279), second, [{"effect": "source_Number_and_preset_slot_bounds"}])
    groups("second_group", _all(fast, when_state("second_groud")), "groupNum2", None, "second_default_1")
    presets("second_preset_once", "second_default_1", "defaultNum2", None, "second_default_2")
    presets("second_preset_twice", "second_default_2", "defaultNum2", None, "finish")
    leave = click(operators[2]["oper"][4])
    cases.append(_case("fast_leave", _all(fast, when_state("finish")),
        [leave, {"set": {ONCE_GROUP: repr(""), ONCE_PRESET: repr("")}}], counts=[_count(510)]))

    ocr = _all(expanded, {"not": _expr("fastMode")})
    cases.append(_case("ocr_leave", _all(ocr, when_state("finish")), [leave], counts=[_count(510)]))
    gap("ocr_navigation", (315, 417), _all(ocr, {"any": [when_state(state) for state in (
            "flushed", "search_group", "search_default", "change_team_default_1", "change_team_default_2")]}),
        [{"effect": "source_OCR_scroll_search_and_double_apply"}])
    start_rect, end_rect = [rect[3:7] for rect in operators[2]["oper"][:2]]
    reset_swipe = {"gate_prefix": gate["fail"], "native_intent": {
        "swipe": {"from": start_rect, "to": end_rect}, "delay": 800, "duration_ms": [500, 700]}}
    proof = {"scope": "pinned-preset-handler-partial", "source_path": SOURCE, "source_sha256": SOURCE_PIN,
             "source_operator_ranges": ranges, "source_complete": False,
             "unresolved_source_obligations": gaps,
             "source_native_lowerings": {"fast_list_reset": [reset_swipe, reset_swipe]},
             "adaptations": ["Recheck input against a new frame; commit preset progress after successful input.",
                 "Fast group/slot inputs are restricted to the declared canonical positions.",
                 "Empty strings represent no one-time override. OCR paths fail explicitly.",
                 "The native swipe host requires a fresh list-top match after the two source swipes."]}
    model = {"id": 510, "name": "更改式神录御魂", "params": params,
             "vars": {STATE: "flushed", ONCE_GROUP: "", ONCE_PRESET: ""}, "cases": cases,
             "unmatched_return": False, "resources": ["upstream/assttyys/colors.yaml"],
             "resource_specs": _used_resources(cases, colors), "proof": proof}
    _data(model)
    return model
