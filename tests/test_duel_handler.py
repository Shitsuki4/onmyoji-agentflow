"""Offline synthetic-frame tests for pinned assttyys handler 030 (斗技_杂项)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from helpers import blank, paint_condition
from onmyoji_agentflow.convert import team_handlers as team
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "duel_handler.json"


@pytest.fixture(scope="module")
def fixture_data():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build(fixture_data, *, config=None, stop="handler_phase == 0 and elapsed_ms >= 1", base_ms=0, loop_ms=200):
    packet = team.compile_team_handler(
        fixture_data["source"], copy.deepcopy(fixture_data["resources"]), config=config
    )
    result = team.team_workflow(
        "duel_030_test",
        [packet],
        config_overrides={"30": config or {}},
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


def test_030_auto_deploy_clicks_and_clears_red_flag(fixture_data):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases["auto_deploy"]["when"])
    run, device, _ = run_synthetic(wf, [img, img], initial_vars={"redFlag": True})
    assert run.status == "success", run.summary()
    assert run.variables["redFlag"] is False
    assert run.variables["run_times_30"] == 1
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, "auto_deploy")[0])


@pytest.mark.parametrize("idx", [0, 1, 2, 3, 6, 7, 8, 9, 12, 13, 20])
def test_030_standard_duel_screens_click(fixture_data, idx):
    wf, cases, _ = _build(fixture_data)
    img = _frame(fixture_data, cases[f"duel_screen_{idx}"]["when"])
    run, device, _ = run_synthetic(wf, [img, img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1
    # Source operators 8 and 9 add checks to the patterns already matched by 1 and 2.
    matched_idx = {8: 1, 9: 2}.get(idx, idx)
    matched = f"duel_screen_{matched_idx}"
    assert f"h0_{matched}" in [state for _, state in run.history]
    _tap_in(device.inputs[0], _clicks(cases, matched)[0])


@pytest.mark.parametrize("idx", [14, 15])
def test_030_ledge_pro_pvp_stops_when_enabled(fixture_data, idx):
    wf, cases, _ = _build(fixture_data, config={"ledgeProPvP": True})
    img = _frame(fixture_data, cases[f"ledge_pro_stop_{idx}"]["when"])
    run, device, _ = run_synthetic(wf, [img, img])
    assert run.status == "failed" and "ledge_pro_pvp_stop" in run.reason
    assert len(device.inputs) == 1
    _tap_in(device.inputs[0], _clicks(cases, f"ledge_pro_stop_{idx}")[0])


def test_030_knowledge_pvp_screens_ban_exit_and_knockout_gate(fixture_data):
    wf, cases, _ = _build(fixture_data, config={"isKnowledgePvP": True, "banList": "面龙"})
    for idx in (5, 10):
        img = _frame(fixture_data, cases[f"knowledge_screen_{idx}"]["when"])
        run, device, _ = run_synthetic(wf, [img, img])
        assert run.status == "success", run.summary()
        assert len(device.inputs) == 1
        _tap_in(device.inputs[0], _clicks(cases, f"knowledge_screen_{idx}")[0])

    # Ban match for '龙' (ban_exit_1) clicks back + confirm
    ban_img = _frame(fixture_data, cases["ban_exit_1"]["when"])
    run_b, dev_b, _ = run_synthetic(wf, [ban_img, ban_img])
    assert run_b.status == "success", run_b.summary()
    expected = _clicks(cases, "ban_exit_1")
    assert len(dev_b.inputs) == len(expected) == 2
    for inp, rect in zip(dev_b.inputs, expected, strict=True):
        _tap_in(inp, rect)

    # Knockout screen with loss marker fails closed on two-losses multi-match check
    ko_img = _frame(fixture_data, cases["knockout_loss_marker"]["when"])
    run_k, dev_k, _ = run_synthetic(wf, [ko_img])
    assert run_k.status == "failed" and "knockout_two_losses_check" in run_k.reason
    assert dev_k.inputs == []


def test_030_courtyard_to_town_and_town_to_duel_uncounted(fixture_data):
    wf, cases, _ = _build(fixture_data)
    yard_conds = cases["courtyard_to_town"]["when"]["all"]
    yard_img = _frame(fixture_data, yard_conds[0]["any"][0], yard_conds[1])
    run, device, clock = run_synthetic(wf, [yard_img, yard_img])
    assert run.status == "success", run.summary()
    assert len(device.inputs) == 1 and run.variables["run_times_30"] == 0
    assert clock.ms == 1000 + 2000 + 200

    town_img = _frame(fixture_data, cases["town_to_duel"]["when"])
    run2, device2, _ = run_synthetic(wf, [town_img, town_img])
    assert run2.status == "success", run2.summary()
    assert len(device2.inputs) == 1 and run2.variables["run_times_30"] == 0
    _tap_in(device2.inputs[0], _clicks(cases, "town_to_duel")[0])
