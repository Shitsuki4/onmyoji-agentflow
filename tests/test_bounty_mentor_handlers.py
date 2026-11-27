"""Unit tests for 018 (每日悬赏) and 693 (师傅流程) native handlers."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "bounty_mentor_handlers.json"


def _build(fid, *, config=None, stop="handler_phase == 0 and elapsed_ms >= 1"):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    colors = data["colors"]
    model = compile_team_handler(data[f"source_{fid}"], colors, config=config)
    native = team_workflow(
        f"test_{fid}",
        [model],
        config_overrides={str(fid): config or {}},
        common_overrides={"afterClickDelayBase": 0, "afterClickDelayRandom": 0, "loopDelay": 200},
    )
    raw = native["workflow"]
    if stop:
        raw["stop_when"] = stop
    return load_workflow(raw), {c["id"]: c for c in model["handler"]["cases"]}, colors


def _frame(colors, *conds):
    img = blank(70)
    for c in conds:
        paint_condition(img, c, colors)
    return img


def test_018_location_dialog_and_explore_loop():
    wf, cases, colors = _build(18)
    # Location dialog with challenge copy -> clicks +440 offset then confirm (1082..1127)
    f_chal = _frame(colors, cases["loc_challenge_copy"]["when"])
    run, dev, _ = run_synthetic(wf, [f_chal, f_chal], max_seconds=10)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 2
    assert 1082 <= dev.inputs[1][1] <= 1127

    # Explore map with chest -> claims chest on iteration 1 (op[4] has retest_ms=500)
    f_exp = _frame(colors, cases["explore_loop_check"]["when"])
    f_chest = _frame(colors, cases["explore_claim_chest"]["when"])
    run, dev, _ = run_synthetic(wf, [f_exp, f_exp, f_chest, f_chest], max_seconds=10)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1

    # 5 misses on explore map without coop -> leaves explore and hits next_scheme rerun gate
    run, dev, clock = run_synthetic(wf, [f_exp] * 20, max_seconds=20)
    assert run.status == "failed"
    assert "bounty_next_scheme_rerun" in run.reason
    assert len(dev.inputs) == 1
    assert clock.ms >= 2000


def test_018_coop_done_return_yard_gate():
    wf, cases, colors = _build(18, config={"next_scheme": "地鬼日常"})
    f_page = _frame(colors, cases["coop_done_return_yard"]["when"])
    run, dev, _ = run_synthetic(wf, [f_page, f_page], initial_vars={"xsXieZuo": True}, max_seconds=10)
    assert run.status == "failed"
    assert "bounty_coop_done_rerun" in run.reason
    assert run.variables["super_next_scheme_name"] == "地鬼日常"
    assert len(dev.inputs) == 1


def test_693_exit_reset_accept_and_timed_exit():
    wf, cases, colors = _build(693, config={"preset_pair_金币": "2,1", "coin": "1"})
    # Kraken exit clears preset overrides and sets change_shikigami_state = 'flushed'
    f_exit = _frame(colors, cases["master_exit_5"]["when"])
    run, dev, _ = run_synthetic(
        wf,
        [f_exit, f_exit],
        initial_vars={"preset_once_groupNum": 2, "change_shikigami_state": "finish"},
        max_seconds=5,
    )
    assert run.status == "success", run.summary()
    assert run.variables["preset_once_groupNum"] == ""
    assert run.variables["change_shikigami_state"] == "flushed"
    assert len(dev.inputs) == 2

    # Banner OCR gate fires on op[1]
    f_banner = _frame(colors, cases["banner_invite_ocr"]["when"])
    run, _, _ = run_synthetic(wf, [f_banner], max_seconds=5)
    assert run.status == "failed"
    assert "master_banner_ocr_preset" in run.reason

    # Timed exit arms on battle start and exits battle once deadline passes
    wf_t, cases_t, colors_t = _build(693, stop="handler_phase == 0 and master693_duration_s == 0")
    f_start = _frame(colors_t, cases_t["timer_arm_on_battle_start"]["when"])
    f_bat = _frame(colors_t, cases_t["timer_exit_battle"]["when"])
    run, dev, _ = run_synthetic(
        wf_t,
        [f_start] + [f_bat] * 20,
        initial_vars={"master693_duration_s": 1},
        max_seconds=10,
    )
    assert run.status == "success", run.summary()
    assert run.variables["master693_deadline_ms"] == -1
    assert len(dev.inputs) == 2
