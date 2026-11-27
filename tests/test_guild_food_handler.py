"""Offline synthetic-frame tests for pinned assttyys handler 700 (进入结界并领取食盒)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from helpers import blank, paint_condition, paint_points
from onmyoji_agentflow.convert import team_handlers as team
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml
from test_handler_runner import run_synthetic

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "guild_food_handler.json"


@pytest.fixture(scope="module")
def fixture_data():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build(fixture_data, *, stop="handler_phase == 0 and elapsed_ms >= 1", base_ms=0, loop_ms=200):
    packet = team.compile_team_handler(fixture_data["source"], copy.deepcopy(fixture_data["resources"]))
    result = team.team_workflow(
        "guild_food_700_test",
        [packet],
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


@pytest.mark.parametrize("index", [0, 1, 2, 4, 5, 6])
def test_700_entry_and_popups_click_without_counting(fixture_data, index):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases[f"enter_{index}"]["when"])
    run, device, _ = run_synthetic(wf, [img, img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, f"enter_{index}")[0])
    assert run.variables["run_times_700"] == 0


@pytest.mark.parametrize("branch,res_name", [("home_ap", "阴阳寮_奖励体力"), ("home_gold", "阴阳寮_奖励金币")])
def test_700_guild_home_claims_ap_or_gold_on_found_point(fixture_data, branch, res_name):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases[branch]["when"])
    run, device, _ = run_synthetic(wf, [img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    group = fixture_data["resources"][res_name]["groups"][0]
    assert device.inputs[0] == ("tap", group[0][0], group[0][1])


def test_700_guild_home_opens_realm_after_three_empty_probes(fixture_data):
    wf, cases, _ = _build(fixture_data)
    home_only = _frame(fixture_data, cases["home_miss"]["when"])
    run, device, clock = run_synthetic(wf, [home_only, home_only, home_only, home_only])
    assert run.status == "success", run.summary()
    assert run.variables["guild700_home_cnt"] == 3
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, "home_open_realm")[0])
    assert clock.ms == 500 + 500 + 2500 + 200


def test_700_guild_home_loop_exits_if_page_changes_before_third_probe(fixture_data):
    wf, cases, _ = _build(fixture_data, stop="handler_phase == 0 and elapsed_ms >= 500")
    home_only = _frame(fixture_data, cases["home_miss"]["when"])
    run, device, _ = run_synthetic(wf, [home_only, blank(70)])
    assert run.status == "success", run.summary()
    assert device.inputs == []
    assert run.variables["guild700_home_cnt"] == 1


def test_700_own_realm_ap_and_exp_capped(fixture_data):
    wf, cases, _ = _build(fixture_data)
    ap_frame = _frame(fixture_data, cases["realm_ap"]["when"])
    run, device, _ = run_synthetic(wf, [ap_frame, ap_frame])
    assert run.status == "success", run.summary()
    assert run.variables["run_times_700"] == 1
    expected_rects = _clicks(cases, "realm_ap")
    assert len(device.inputs) == len(expected_rects) == 4
    for inp, rect in zip(device.inputs, expected_rects, strict=True):
        _tap_in(inp, rect)

    # When shiHe_jingYan is True, own realm yields False without clicking EXP box.
    wf2, cases2, _ = _build(fixture_data, stop="handler_phase == 0 and elapsed_ms >= 400")
    exp_frame = _frame(fixture_data, cases2["realm_exp_claim"]["when"])
    run2, device2, _ = run_synthetic(wf2, [exp_frame], initial_vars={"shiHe_jingYan": True})
    assert run2.status == "success", run2.summary()
    assert device2.inputs == []
    assert run2.variables["shiHe_jingYan"] is True


def test_700_exp_claim_change_loop_replaces_fodder_and_exits(fixture_data):
    wf, cases, _ = _build(fixture_data)
    exp_frame = _frame(fixture_data, cases["realm_exp_claim"]["when"])
    own_realm = _frame(fixture_data, cases["change_enter_10"]["when"])
    fodder_empty_all = _frame(fixture_data, cases["change_fodder_switch_n"]["when"])
    fodder_empty = _frame(fixture_data, cases["change_fodder_add_n"]["when"])
    fodder_full_top = _frame(fixture_data, cases["change_fodder_clear_full"]["when"])
    fodder_clean = _frame(fixture_data, cases["change_fodder_done"]["when"])

    # Each recheck=True state consumes one extra verification capture before clicking.
    frames = [
        exp_frame, exp_frame,
        own_realm, own_realm,
        fodder_empty_all, fodder_empty_all,
        fodder_empty, fodder_empty,
        fodder_full_top, fodder_full_top,
        fodder_clean, fodder_clean,
    ]
    run, device, _ = run_synthetic(wf, frames, max_seconds=30)
    assert run.status == "success", run.summary()
    assert run.variables["guild700_in_change"] is False
    assert run.variables["shiHe_jingYan"] is False
    # 2 clicks (EXP) + 1 (enter fodder) + 2 (switch N) + 1 (place N) + 1 (clear full) + 1 (exit) = 8 taps
    assert len(device.inputs) == 8
    _tap_in(device.inputs[-1], _clicks(cases, "change_fodder_done")[0])


def test_700_exp_claim_change_loop_marks_exp_full_on_op14(fixture_data):
    wf, cases, _ = _build(fixture_data)
    exp_frame = _frame(fixture_data, cases["realm_exp_claim"]["when"])
    exp_full_dialog = _frame(fixture_data, cases["change_exp_full"]["when"])
    run, device, _ = run_synthetic(wf, [exp_frame, exp_frame, exp_full_dialog, exp_full_dialog])
    assert run.status == "success", run.summary()
    assert run.variables["shiHe_jingYan"] is True
    assert run.variables["guild700_in_change"] is False
    assert len(device.inputs) == 3
    _tap_in(device.inputs[-1], _clicks(cases, "change_exp_full")[0])


def test_700_change_loop_fails_closed_on_all_n_max_level_push(fixture_data):
    wf, cases, _ = _build(fixture_data)
    exp_frame = _frame(fixture_data, cases["realm_exp_claim"]["when"])
    all_n_full = _frame(fixture_data, cases["change_fodder_add_n"]["when"])
    # Paint max-level marker inside bottom region [910, 473, 1138, 568] (group[1] is at 981, 489)
    paint_points(all_n_full, fixture_data["resources"]["寄养狗粮_满级标识"]["groups"][1])
    run, device, _ = run_synthetic(wf, [exp_frame, exp_frame, all_n_full, all_n_full, all_n_full])
    assert run.status == "failed" and "all_n_cards_max_level" in run.reason
    # 2 clicks (EXP) + 2 clicks (op[13].oper) before Push gate
    assert len(device.inputs) == 4


def test_700_change_loop_times_out_cleanly_after_10_misses(fixture_data):
    wf, cases, _ = _build(fixture_data)
    exp_frame = _frame(fixture_data, cases["realm_exp_claim"]["when"])
    run, device, _ = run_synthetic(wf, [exp_frame, exp_frame] + [blank(70)] * 12, max_seconds=30)
    assert run.status == "success", run.summary()
    assert run.variables["guild700_change_cnt"] == 10
    assert run.variables["guild700_in_change"] is False
    assert len(device.inputs) == 2
