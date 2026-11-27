"""Offline synthetic-frame tests for pinned assttyys handler 702 (式神寄养)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from helpers import blank, paint_condition
from onmyoji_agentflow.convert import team_handlers as team
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "foster_handler.json"


@pytest.fixture(scope="module")
def fixture_data():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build(fixture_data, *, config=None, stop="handler_phase == 0 and elapsed_ms >= 1", base_ms=0, loop_ms=200):
    packet = team.compile_team_handler(
        fixture_data["source"], copy.deepcopy(fixture_data["resources"]), config=config
    )
    result = team.team_workflow(
        "foster_702_test",
        [packet],
        config_overrides={"702": config or {}},
        common_overrides={"loopDelay": loop_ms, "afterClickDelayBase": base_ms, "afterClickDelayRandom": 0},
    )
    assert result["guarded_executable"] and result["complete"] is False
    raw = result["workflow"]
    assert raw["resources"] == []
    if stop:
        raw["stop_when"] = stop
    wf = load_workflow(raw)
    cases = {branch["id"]: branch for branch in packet["handler"]["cases"]}
    return wf, cases, packet


def _frame(fixture_data, *conditions, level=70):
    image = blank(level)
    for cond in conditions:
        paint_condition(image, cond, fixture_data["resources"])
    return image


def _tap_in(inp, rect):
    kind, x, y = inp
    assert kind == "tap" and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3], (inp, rect)


def _clicks(cases, name):
    return [step["click"] for step in cases[name]["do"] if "click" in step]


def test_702_foster_screen_opens_empty_slot_or_waits_10s(fixture_data):
    wf, cases, _ = _build(fixture_data)
    slot_img = _frame(fixture_data, cases["foster_open_slot"]["when"])
    run, device, _ = run_synthetic(wf, [slot_img, slot_img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, "foster_open_slot")[0])

    # Without op[1], waits 10s then taps back (op[12].oper[0]).
    wait_img = _frame(fixture_data, cases["foster_wait_and_back"]["when"])
    run2, device2, clock2 = run_synthetic(wf, [wait_img], max_seconds=30)
    assert run2.status == "success", run2.summary()
    assert len(device2.inputs) == 1
    assert clock2.ms == 10000 + 1000 + 200
    _tap_in(device2.inputs[0], _clicks(cases, "foster_wait_and_back")[0])


def test_702_initial_list_refresh_and_cross_tab_sets_index_1(fixture_data):
    wf, cases, _ = _build(fixture_data)
    top_img = _frame(fixture_data, cases["list_top_refresh"]["when"])
    run, device, clock = run_synthetic(wf, [top_img, top_img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1 and device.inputs[0][0] == "swipe"
    assert device.swipe_durations[0] in range(700, 801)
    assert clock.ms == 3000 + 200

    cross_bot = _frame(fixture_data, cases["cross_bottom_to_friends"]["when"])
    run2, device2, clock2 = run_synthetic(wf, [cross_bot, cross_bot])
    assert run2.status == "success", run2.summary()
    assert run2.variables["jy_enchantment_index"] == 1
    assert clock2.ms == 1200 + 1000 + 200


def test_702_priority_match_clicks_found_card_and_enters_realm(fixture_data):
    wf, cases, _ = _build(fixture_data, config={"priority": "太鼓6->太鼓5->太鼓4"})
    # priority choice index 3, position 1 => 结界卡_太鼓6星
    card_img = _frame(fixture_data, cases["priority_3_1"]["when"])
    run, device, _ = run_synthetic(wf, [card_img, card_img], initial_vars={"jy_enchantment_index": 1})
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 2
    _tap_in(device.inputs[1], _clicks(cases, "priority_3_1")[0])


def test_702_empty_card_switches_tabs_and_increments_index(fixture_data):
    wf, cases, _ = _build(fixture_data)
    friends_empty = _frame(fixture_data, cases["empty_friends_to_cross"]["when"])
    run, device, _ = run_synthetic(wf, [friends_empty, friends_empty], initial_vars={"jy_enchantment_index": 1})
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1 and run.variables["jy_enchantment_index"] == 1
    _tap_in(device.inputs[0], _clicks(cases, "empty_friends_to_cross")[0])

    cross_empty = _frame(fixture_data, cases["empty_cross_to_friends"]["when"])
    run2, device2, _ = run_synthetic(wf, [cross_empty, cross_empty], initial_vars={"jy_enchantment_index": 1})
    assert run2.status == "success", run2.summary()
    assert len(device2.inputs) == 1 and run2.variables["jy_enchantment_index"] == 2
    _tap_in(device2.inputs[0], _clicks(cases, "empty_cross_to_friends")[0])


def test_702_list_scrolls_when_card_not_empty_and_not_matched(fixture_data):
    wf, cases, _ = _build(fixture_data)
    list_img = _frame(fixture_data, cases["foster_list_idle"]["when"])
    run, device, _ = run_synthetic(wf, [list_img, list_img], initial_vars={"jy_enchantment_index": 1})
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1 and device.inputs[0][0] == "swipe"
    assert device.swipe_durations[0] in range(350, 361)


def test_702_priority_exhausted_closes_twice_and_hits_not_found_gate(fixture_data):
    wf, cases, _ = _build(fixture_data, config={"priority": "太鼓6->太鼓5->太鼓4"})
    list_img = _frame(fixture_data, cases["foster_list_idle"]["when"])
    run, device, _ = run_synthetic(wf, [list_img, list_img], initial_vars={"jy_enchantment_index": 4})
    assert run.status == "failed" and "foster_card_not_found" in run.reason
    assert len(device.inputs) == 2


def test_702_place_n_loop_completes_on_already_fostered_or_hits_max_level_push(fixture_data):
    wf, cases, _ = _build(fixture_data)
    op8 = _frame(fixture_data, cases["place_n_8"]["when"])
    op10 = _frame(fixture_data, cases["place_n_10"]["when"])
    op12 = _frame(fixture_data, cases["foster_done_exit"]["when"])
    run, device, _ = run_synthetic(wf, [op8, op8, op10, op10, op12, op12])
    assert run.status == "failed" and "foster_complete_rerun" in run.reason
    # 3 clicks (op8) + 1 click (op10) + 2 clicks (op12) = 6 taps
    assert len(device.inputs) == 6

    op11 = _frame(fixture_data, cases["place_n_all_max"]["when"])
    run2, device2, _ = run_synthetic(wf, [op8, op8, op8, op8, op8, op8, op11, op11])
    assert run2.status == "failed" and "foster_n_cards_max_level" in run2.reason
    assert run2.variables["foster702_n_cnt"] == 3
    # 3*3 clicks (op8) + 3 clicks (op11) = 12 taps
    assert len(device2.inputs) == 12
