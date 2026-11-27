"""Unit tests for 316_六道椒图 native handler."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "six_realms_handler.json"


def _build(*, config=None, stop="handler_phase == 0 and elapsed_ms >= 1"):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    colors = data["colors"]
    model = compile_team_handler(data["source"], colors, config=config)
    native = team_workflow(
        "test_316",
        [model],
        config_overrides={"316": config or {}},
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


def test_316_event_select_and_buff_upgrade():
    wf, cases, colors = _build()
    f_ev = _frame(colors, cases["event_select_found"]["when"])
    run, dev, _ = run_synthetic(wf, [f_ev, f_ev], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1

    f_up = _frame(colors, cases["buff_upgrade"]["when"])
    run, dev, _ = run_synthetic(wf, [f_up, f_up], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["d6RouFeng"] == 1
    assert len(dev.inputs) == 1

    # When d6RouFeng == 5, buff screen skips directly to 万相之赐 (1034..1137)
    f_buff = _frame(colors, cases["buff_skip_fallback"]["when"])
    run, dev, _ = run_synthetic(wf, [f_buff, f_buff], initial_vars={"d6RouFeng": 5}, max_seconds=5)
    assert run.status == "success", run.summary()
    assert 1034 <= dev.inputs[0][1] <= 1137


def test_316_shop_confirm_forge_and_start_reset():
    wf, cases, colors = _build()
    f_conf = _frame(colors, cases["shop_confirm_buy"]["when"])
    run, dev, _ = run_synthetic(wf, [f_conf, f_conf], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["d6RouFeng"] == 1
    assert len(dev.inputs) == 2

    f_start = _frame(colors, cases["start_reset_run"]["when"])
    run, dev, _ = run_synthetic(wf, [f_start, f_start], initial_vars={"d6RouFeng": 4}, max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["d6RouFeng"] == 1
    assert run.variables["d6_times"] == 1


def test_316_only_double_stop_and_over_times_rerun():
    wf, cases, colors = _build(config={"onlyDouble": True, "overTimes": "2", "pushResult": False})
    f_zero = _frame(colors, cases["only_double_stop"]["when"])
    run, _, _ = run_synthetic(wf, [f_zero], max_seconds=5)
    assert run.status == "failed"
    assert "only_double_exhausted_stop" in run.reason

    f_end = _frame(colors, cases["finish_continue"]["when"])
    run, dev, _ = run_synthetic(wf, [f_end, f_end], initial_vars={"d6_times": 1}, max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1

    run, _, _ = run_synthetic(wf, [f_end, f_end], initial_vars={"d6_times": 2}, max_seconds=5)
    assert run.status == "failed"
    assert "finish_over_times_rerun" in run.reason
