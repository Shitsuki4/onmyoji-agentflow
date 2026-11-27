"""Offline synthetic-frame tests for pinned assttyys handler 701 (结界卡更换)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from helpers import blank, paint_condition, paint_points
from onmyoji_agentflow.convert import team_handlers as team
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "realm_card_handler.json"


@pytest.fixture(scope="module")
def fixture_data():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build(fixture_data, *, config=None, stop="handler_phase == 0 and elapsed_ms >= 1", base_ms=0, loop_ms=200):
    packet = team.compile_team_handler(
        fixture_data["source"], copy.deepcopy(fixture_data["resources"]), config=config
    )
    result = team.team_workflow(
        "realm_card_701_test",
        [packet],
        config_overrides={"701": config or {}},
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


def test_701_expiring_soon_closes_and_waits_60s(fixture_data):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases["expiring_soon"]["when"])
    run, device, clock = run_synthetic(wf, [img, img], max_seconds=120)
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, "expiring_soon")[0])
    assert clock.ms == 1000 + 60000 + 200
    assert run.variables["run_times_701"] == 1


def test_701_own_realm_opens_card_directly_without_reward(fixture_data):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases["realm_open_card"]["when"])
    run, device, _ = run_synthetic(wf, [img, img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, "realm_open_card")[0])


def test_701_realm_reward_runs_change_loop_then_opens_card(fixture_data):
    wf, cases, _ = _build(fixture_data)
    reward_f = _frame(fixture_data, cases["realm_reward_claim"]["when"])
    enter_f = _frame(fixture_data, cases["change_enter_12"]["when"])
    empty_all = _frame(fixture_data, cases["change_fodder_switch_n"]["when"])
    empty_n = _frame(fixture_data, cases["change_fodder_add_n"]["when"])
    full_top = _frame(fixture_data, cases["change_fodder_clear_full"]["when"])
    clean_f = _frame(fixture_data, cases["change_fodder_done"]["when"])

    frames = [
        reward_f, reward_f,
        enter_f, enter_f,
        empty_all, empty_all,
        empty_n, empty_n,
        full_top, full_top,
        clean_f, clean_f,
    ]
    run, device, _ = run_synthetic(wf, frames, max_seconds=30)
    assert run.status == "success", run.summary()
    assert run.variables["card701_in_change"] is False
    # 1 (reward) + 1 (enter fodder) + 2 (switch N) + 1 (place N) + 1 (clear full) + 2 (exit + open card) = 8 taps
    assert len(device.inputs) == 8
    _tap_in(device.inputs[-1], _clicks(cases, "realm_open_card")[0])


@pytest.mark.parametrize("card_type,case_name", [("太鼓", "select_card_0"), ("斗鱼", "select_card_1")])
def test_701_dropdown_selects_configured_card_type(fixture_data, card_type, case_name):
    wf, cases, _ = _build(fixture_data, config={"change_enchantment_type": card_type})
    img = _frame(fixture_data, cases[case_name]["when"])
    run, device, _ = run_synthetic(wf, [img, img])
    assert run.status == "success", run.summary()
    expected = _clicks(cases, case_name)
    assert len(device.inputs) == len(expected) == 2
    for inp, rect in zip(device.inputs, expected, strict=True):
        _tap_in(inp, rect)


@pytest.mark.parametrize("idx", [2, 4, 6])
def test_701_card_misc_clicks(fixture_data, idx):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases[f"card_misc_{idx}"]["when"])
    run, device, _ = run_synthetic(wf, [img, img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, f"card_misc_{idx}")[0])


@pytest.mark.parametrize("star_index", [0, 1])
def test_701_activated_card_closes_then_hits_finish_obligation(fixture_data, star_index):
    wf, cases, _ = _build(fixture_data)
    page_cond, stars = cases["card_activated_finish"]["when"]["all"]
    img = _frame(fixture_data, page_cond, stars["any"][star_index])
    run, device, _ = run_synthetic(wf, [img, img])
    assert run.status == "failed" and "card_activated_finish" in run.reason
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, "card_activated_finish")[0])


def test_701_card_page_idle_yields_recognized(fixture_data):
    wf, cases, _ = _build(fixture_data, stop="handler_phase == 0 and elapsed_ms >= 400")
    img = _frame(fixture_data, cases["card_page_idle"]["when"])
    run, device, _ = run_synthetic(wf, [img])
    assert run.status == "success", run.summary()
    assert device.inputs == [] and run.recognized_ticks > 0
