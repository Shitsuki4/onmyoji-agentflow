"""Unit tests for 320 (百鬼棋局), 519 (寮管理攻打道馆), and 600 (进入寮活动)."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "guild_launcher_handlers.json"


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


def test_320_battle_start_600_coins_and_buy_loop():
    wf, cases, colors = _build(320)
    f_start = _frame(colors, cases["battle_start_enter"]["when"])
    run, dev, _ = run_synthetic(
        wf, [f_start, f_start], initial_vars={"chess320_ini": False, "chess320_levelFive": True}, max_seconds=5
    )
    assert run.status == "success", run.summary()
    assert run.variables["chess320_ini"] is True
    assert run.variables["chess320_levelFive"] is False
    assert len(dev.inputs) == 1

    f_600 = _frame(colors, cases["battle_start_enter"]["when"], cases["battle_start_600_coins"]["when"]["all"][1]["any"][0])
    run, _, _ = run_synthetic(wf, [f_600], max_seconds=5)
    assert run.status == "failed"
    assert "chess_600_coin_rerun" in run.reason

    # 8 misses in shop buy loop without 10 coins -> closes shop (op[14].oper[1])
    f_shop = _frame(colors, cases["buy_loop_check"]["when"])
    run, dev, clock = run_synthetic(wf, [f_shop] * 20, max_seconds=15)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1
    assert 627 <= dev.inputs[0][2] <= 668
    assert clock.ms >= 1400


def test_519_weekend_done_and_attack_click():
    wf, cases, colors = _build(519)
    # Weekend stop when dojo519_is_fri_sat_sun is True
    run, _, _ = run_synthetic(wf, [blank(70)], initial_vars={"dojo519_is_fri_sat_sun": True}, max_seconds=5)
    assert run.status == "failed"
    assert "dojo519_weekend_stop" in run.reason

    # Zero chances left -> done rerun gate
    f_zero = _frame(colors, cases["zero_chances_return_yard"]["when"]["any"][0])
    run, _, _ = run_synthetic(wf, [f_zero], max_seconds=5)
    assert run.status == "failed"
    assert "dojo519_done_rerun" in run.reason

    # Attack selected dojo when daoGuan_click is True
    f_atk = _frame(colors, cases["attack_selected_dojo"]["when"])
    run, dev, _ = run_synthetic(wf, [f_atk, f_atk], initial_vars={"daoGuan_click": True}, max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["daoGuan_click"] is False
    assert run.variables["daoGuan_swip"] is True
    assert len(dev.inputs) == 1


def test_600_all_false_gate_dojo_and_shrine_wait():
    # Default all switches False -> hits all_activities_done_push_rerun gate
    wf_empty, _, _ = _build(600)
    run, _, _ = run_synthetic(wf_empty, [blank(70)], max_seconds=5)
    assert run.status == "failed"
    assert "all_activities_done_push_rerun" in run.reason

    # Dojo enabled on Monday -> first shrine visit backs out (liao_cheak -1 -> 0)
    wf, cases, colors = _build(600, config={"a_ctivity_dojo": True})
    f_shrine = _frame(colors, cases["first_shrine_reenter"]["when"])
    run, dev, _ = run_synthetic(wf, [f_shrine, f_shrine], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["liao_cheak"] == 0
    assert run.variables["super_next_scheme_name"] == "寮活动启动器"
    assert len(dev.inputs) == 1

    # Inside dojo -> disables dojo switch and hits rerun_dojo_scheme gate
    f_dojo = _frame(colors, cases["dojo_inside_switch"]["when"])
    run, _, _ = run_synthetic(wf, [f_dojo], max_seconds=5)
    assert run.status == "failed"
    assert "rerun_dojo_scheme" in run.reason
    assert run.variables["act600_sw_dojo"] is False
