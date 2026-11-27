"""Unit tests for mini-feature handlers 017, 302, 309, 310, 319 (小功能合集)."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "mini_feature_handlers.json"


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


def test_017_parade_drag_beans_and_throw():
    wf, cases, colors = _build(17, config={"bossPosition": "2", "Inv": False})
    f_drag = _frame(colors, cases["parade_drag_10_beans"]["when"])
    run, dev, _ = run_synthetic(wf, [f_drag, f_drag], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.swipe_durations) == 1
    assert 100 <= dev.swipe_durations[0] <= 300

    f_boss = _frame(colors, cases["parade_boss_2"]["when"])
    run, dev, _ = run_synthetic(wf, [f_boss, f_boss], max_seconds=10)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 2
    assert 591 <= dev.inputs[0][1] <= 654


def test_302_309_310_soul_and_glutton_flows():
    wf302, c302, colors = _build(302)
    f_done = _frame(colors, c302["glutton_feed_done"]["when"])
    run, dev, _ = run_synthetic(wf302, [f_done, f_done], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["fengNa"] is True

    wf309, c309, _ = _build(309, config={"speed": True})
    f_init = _frame(colors, c309["enhance_init_speed_switch"]["when"])
    run, dev, _ = run_synthetic(wf309, [f_init, f_init], max_seconds=10)
    assert run.status == "success", run.summary()
    assert run.variables["upYuHunIni"] is False
    assert len(dev.inputs) == 5

    wf310, c310, _ = _build(310)
    f_full = _frame(colors, c310["glutton_exp_full"]["when"])
    run, _, _ = run_synthetic(wf310, [f_full], max_seconds=5)
    assert run.status == "failed"
    assert "glutton_exp_full_stop" in run.reason


def test_319_yuanjie_jade_buy_guard_and_single_switch():
    wf_buy, c319, colors = _build(319, config={"buy": True})
    f_lt10 = _frame(colors, c319["yuanjie_buy_tickets"]["when"])
    run, dev, _ = run_synthetic(wf_buy, [f_lt10], max_seconds=5)
    assert run.status == "failed"
    assert "yuanjie_buy_tickets_jade" in run.reason
    assert dev.inputs == []

    wf_nobuy, _, _ = _build(319, config={"buy": False})
    run, dev, _ = run_synthetic(wf_nobuy, [f_lt10, f_lt10], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["youjiequyuan_ten"] is False
    assert len(dev.inputs) == 1
