"""Offline synthetic-frame tests for pinned assttyys handler 605 (寮宴会)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from helpers import blank, paint_condition
from onmyoji_agentflow.convert import team_handlers as team
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "banquet_handler.json"


@pytest.fixture(scope="module")
def fixture_data():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build(fixture_data, *, config=None, stop="handler_phase == 0 and elapsed_ms >= 1", base_ms=0, loop_ms=200):
    packet = team.compile_team_handler(
        fixture_data["source"], copy.deepcopy(fixture_data["resources"]), config=config
    )
    result = team.team_workflow(
        "banquet_605_test",
        [packet],
        config_overrides={"605": config or {}},
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


def test_605_eating_lift_up_and_rotate_flag(fixture_data):
    wf, cases, _ = _build(fixture_data)
    lift_img = _frame(fixture_data, cases["eating_lift_up"]["when"])
    run, device, _ = run_synthetic(wf, [lift_img, lift_img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    group = fixture_data["resources"]["宴会_举高高"]["groups"][0]
    assert device.inputs[0] == ("tap", group[0][0], group[0][1])

    eat_img = _frame(fixture_data, cases["eating_wait"]["when"])
    run2, device2, _ = run_synthetic(wf, [eat_img, eat_img])
    assert run2.status == "success", run2.summary()
    assert len(device2.inputs) == 2

    rot_img = _frame(fixture_data, cases["rotate_already_on"]["when"])
    run3, device3, _ = run_synthetic(wf, [rot_img, rot_img])
    assert run3.status == "success", run3.summary()
    assert run3.variables["banquet_change_flag"] is True
    assert len(device3.inputs) == 1


def test_605_end_screen_hits_rerun_return_courtyard_gate(fixture_data):
    wf, cases, _ = _build(fixture_data)
    end_img = _frame(fixture_data, cases["banquet_end_10"]["when"])
    run, device, _ = run_synthetic(wf, [end_img, end_img])
    assert run.status == "failed" and "banquet_end_rerun" in run.reason
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, "banquet_end_10")[0])


def test_605_admin_prep_not_ready_switches_to_collect_and_ready_times_out_at_3(fixture_data):
    wf, cases, _ = _build(fixture_data, config={"admin": True})
    prep_only = _frame(fixture_data, cases["admin_prep_not_ready"]["when"]["all"][1])
    run, device, _ = run_synthetic(wf, [prep_only])
    assert run.status == "success", run.summary()
    assert run.variables["liao_banquet_collect"] is True
    assert run.variables["liao_banquet_onGoing"] is False
    assert device.inputs == []

    prep_ready = _frame(fixture_data, cases["admin_prep_ready"]["when"])
    run2, device2, _ = run_synthetic(wf, [prep_ready] * 8, max_seconds=30)
    assert run2.status == "failed" and "admin_open_timeout" in run2.reason
    assert run2.variables["banquet605_open_cnt"] == 3
    # 3 iterations x 2 clicks (op[6].oper) = 6 taps
    assert len(device2.inputs) == 6


@pytest.mark.parametrize("rt2,case_name,res_key", [
    (0, "collect_find_tanuki", "宴会筹备_狸猫"),
    (1, "collect_find_hungry", "宴会筹备_饿鬼"),
    (2, "collect_find_kappa", "宴会筹备_河童"),
])
def test_605_collect_mode_finds_target_monster_by_run_times_2(fixture_data, rt2, case_name, res_key):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases[case_name]["when"])
    run, device, _ = run_synthetic(
        wf, [img, img],
        initial_vars={"liao_banquet_collect": True, "liao_banquet_onGoing": False, "run_times_2": rt2},
    )
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    gx, gy = fixture_data["resources"][res_key]["groups"][0][0][:2]
    assert gx + 5 <= device.inputs[0][1] <= gx + 10 and gy + 5 <= device.inputs[0][2] <= gy + 10


def test_605_collect_mode_secret_transition_and_switch_back_at_6(fixture_data):
    wf, cases, _ = _build(fixture_data)
    map_img = _frame(fixture_data, cases["collect_explore_scroll"]["when"])
    run, device, _ = run_synthetic(
        wf, [map_img, map_img, map_img],
        initial_vars={"liao_banquet_collect": True, "liao_banquet_onGoing": False, "run_times_2": 3},
    )
    assert run.status == "success", run.summary()
    assert [op[0] for op in device.inputs] == ["tap", "swipe"]
    assert device.swipe_durations[0] in range(2000, 2051)

    # At run_times_2 == 6 on non-map screen, switches back to ongoing banquet
    run2, device2, _ = run_synthetic(
        wf, [blank(70)],
        initial_vars={"liao_banquet_collect": True, "liao_banquet_onGoing": False, "run_times_2": 6},
    )
    assert run2.status == "success", run2.summary()
    assert run2.variables["liao_banquet_collect"] is False
    assert run2.variables["liao_banquet_onGoing"] is True
    assert device2.inputs == []
