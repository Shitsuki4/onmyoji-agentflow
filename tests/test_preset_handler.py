import json
import os
from pathlib import Path

import pytest

from helpers import blank, paint_points
from onmyoji_agentflow.convert.core_handlers import core_workflow
from onmyoji_agentflow.convert.handlers import DispatchState, compose_handlers, trace_cycle
from onmyoji_agentflow.convert.preset_handler import (
    BATTLE_GROUP, BATTLE_PENDING, BATTLE_PRESET, ONCE_GROUP, ONCE_PRESET, SOURCE, STATE,
    compile_battle_preset, load_preset_handler,
)
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml
from test_handler_runner import run_synthetic


@pytest.fixture(scope="module")
def preset():
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    upstream = root / "onmyoji-agentflow/upstream-src/assttyys"
    if not (upstream / SOURCE).is_file():
        pytest.skip("optional fixed assttyys source checkout unavailable")
    return load_preset_handler(upstream)


def flattened(condition):
    if "all" in condition:
        return [leaf for term in condition["all"] for leaf in flattened(term)]
    if "colors" in condition or "res" in condition:
        return [condition]
    return []


def by_case(model, case):
    return next(branch for branch in model["cases"] if branch["id"] == case)


def test_preset_honors_one_shot_priority_and_applies_both_preset_groups_twice(preset):
    program = compose_handlers("preset", [preset], config_overrides={"510": {"groupNum2": "3", "defaultNum2": "4"}})
    state = DispatchState(variables={ONCE_GROUP: "2", ONCE_PRESET: "3"})
    elapsed = 0
    for case, desired_state, rect in [
        ("first_group_2", "change_team_default_1", [1107, 165, 1229, 211]),
        ("first_preset_once_3", "change_team_default_2", [978, 454, 1004, 482]),
        ("first_preset_twice_second_groud_3", "second_groud", [978, 454, 1004, 482]),
        ("second_group_3", "second_default_1", [1107, 235, 1229, 281]),
        ("second_preset_once_4", "second_default_2", [978, 606, 1001, 625]),
        ("second_preset_twice_4", "finish", [978, 606, 1001, 625]),
        ("fast_leave", "finish", [24, 10, 65, 43]),
    ]:
        facts = flattened(by_case(preset, case)["when"])
        out = trace_cycle(program, facts, now_ms=elapsed, state=state)
        assert out["actions"][0]["click"] == rect
        assert state.variables[STATE] == desired_state
        elapsed += 1000
    assert state.variables[ONCE_GROUP] == state.variables[ONCE_PRESET] == ""
    assert state.run_times == {510: 1}


@pytest.mark.parametrize(("options", "source_gate"), [
    ({}, "fast_list_reset"), ({"fastMode": False}, "ocr_navigation")
])
def test_preset_keeps_unsupported_swipe_and_ocr_before_next_game_input(preset, options, source_gate):
    program = compose_handlers("preset", [preset], config_overrides={"510": options})
    result = trace_cycle(program, flattened(by_case(preset, "fast_list_reset")["when"]), now_ms=0)
    gate = {"fail": "unresolved_source_obligation:preset510." + source_gate}
    prefix = [{"wait": 100}] if source_gate == "fast_list_reset" else []
    assert result["actions"][:len(prefix) + 1] == [*prefix, gate]


def test_preset_runtime_does_not_click_if_the_sidebar_moves_before_input(preset, tmp_path):
    raw = core_workflow("preset", [preset], common_overrides={"afterClickDelayRandom": 0})["workflow"]
    resources = tmp_path / "upstream/assttyys/colors.yaml"
    resources.parent.mkdir(parents=True)
    resources.write_text(dump_yaml({"resources": preset["resource_specs"]}), encoding="utf-8")
    workflow = load_workflow(raw, [tmp_path])
    visible = blank()
    for leaf in flattened(by_case(preset, "first_group_1")["when"]):
        paint_points(visible, leaf["colors"])
    result, replay, _ = run_synthetic(workflow, [visible, blank()])
    assert result.failure_kind == "recognition", result.summary()
    assert not replay.inputs and result.variables[STATE] == "flushed"


def test_preset_native_list_reset_requires_fresh_top_match(preset):
    raw = team_workflow("preset", [{**preset, "resources": []}],
                        common_overrides={"afterClickDelayRandom": 0})["workflow"]
    raw["stop_when"] = "handler_phase == 0 and actions >= 3"
    workflow = load_workflow(raw)
    top = blank()
    top[:] = (255, 0, 255)
    conditions = flattened(by_case(preset, "first_group_1")["when"])
    for condition in conditions:
        paint_points(top, condition["colors"])
    not_top = blank()
    not_top[:] = (255, 0, 255)
    for condition in flattened(by_case(preset, "fast_list_reset")["when"]):
        paint_points(not_top, condition["colors"])
    result, replay, _ = run_synthetic(workflow, [not_top, top, top])
    assert result.status == "success", result.summary()
    assert [row[0] for row in replay.inputs] == ["swipe", "swipe", "tap"], result.history
    assert all(500 <= duration <= 700 for duration in replay.swipe_durations)
    assert result.variables[STATE] == "change_team_default_1"
    result, replay, _ = run_synthetic(workflow, [not_top, not_top])
    assert result.failure_kind == "workflow_fail", result.summary()
    assert [row[0] for row in replay.inputs] == ["swipe", "swipe"]


def test_battle_preset_consumes_one_time_settings_after_three_guarded_clicks():
    saved = Path(__file__).with_name("fixtures") / "battle_preset_handler.json"
    model = compile_battle_preset(json.loads(saved.read_text(encoding="utf-8"))["source"], {})
    raw = team_workflow("battle_preset", [model], common_overrides={"afterClickDelayRandom": 0})["workflow"]
    raw["stop_when"] = "handler_phase == 0 and actions >= 4"
    pending = {BATTLE_PENDING: True, BATTLE_GROUP: 7, BATTLE_PRESET: 4}
    preparation, inside = blank(), blank()
    preparation[:] = inside[:] = (255, 0, 255)
    paint_points(preparation, flattened(by_case(model, "open")["when"])[0]["colors"])
    paint_points(inside, flattened(by_case(model, "apply_7_4")["when"])[0]["colors"])
    workflow = load_workflow(raw)
    # Initial capture, source retest and input recheck all precede the first click.
    result, replay, _ = run_synthetic(workflow, [preparation] * 3 + [inside], initial_vars=pending)
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 4
    for (operation, x, y), rectangle in zip(replay.inputs, ([42, 662, 74, 703], [33, 620, 162, 669],
                                                          [197, 597, 660, 628], [359, 648, 491, 683])):
        assert operation == "tap" and rectangle[0] <= x <= rectangle[2] and rectangle[1] <= y <= rectangle[3]
    assert not result.variables[BATTLE_PENDING]
    assert result.variables[BATTLE_GROUP] == result.variables[BATTLE_PRESET] == ""

    result, replay, _ = run_synthetic(workflow, [inside], initial_vars={**pending, BATTLE_GROUP: 8})
    assert result.failure_kind == "workflow_fail", result.summary()
    assert not replay.inputs and result.variables[BATTLE_PENDING]


def test_weekly_red_leaf_uses_first_configured_group_for_both_preset_paths():
    saved = Path(__file__).with_name("fixtures") / "weekly_preset_handler.json"
    pinned = json.loads(saved.read_text(encoding="utf-8"))
    config = {"weekMode_A": ["镰鼬", "红叶"], "preset_pair_A": "3，4",
              "weekMode_B": ["红叶"], "preset_pair_B": "2,1"}
    model = compile_team_handler(pinned["source"], pinned["resources"], config=config)["handler"]
    raw = team_workflow("weekly_preset", [model])["workflow"]
    raw["stop_when"] = "handler_phase == 0 and miWenChange"
    red_leaf = blank()
    red_leaf[:] = (255, 0, 255)
    paint_points(red_leaf, flattened(by_case(model, "recognize_red_leaf")["when"])[0]["colors"])
    result, replay, _ = run_synthetic(load_workflow(raw), [red_leaf])
    assert result.status == "success" and not replay.inputs, result.summary()
    assert any(state.endswith("red_leaf_A_preset") for _, state in result.history)
    assert result.variables[BATTLE_GROUP] == result.variables[ONCE_GROUP] == 3
    assert result.variables[BATTLE_PRESET] == result.variables[ONCE_PRESET] == 4
    assert result.variables[BATTLE_PENDING] and result.variables[STATE] == "flushed"
