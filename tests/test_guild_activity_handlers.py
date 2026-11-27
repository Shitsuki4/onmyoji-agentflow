"""Unit tests for guild activity handlers 601 (狩猎战), 604 (首领退治), 606 (阴界之门)."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "guild_activity_handlers.json"


def _build(fid, *, stop="handler_phase == 0 and elapsed_ms >= 1"):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    colors = data["colors"]
    model = compile_team_handler(data[f"source_{fid}"], colors)
    native = team_workflow(
        f"test_{fid}",
        [model],
        common_overrides={"afterClickDelayBase": 0, "afterClickDelayRandom": 0, "loopDelay": 200},
    )
    raw = native["workflow"]
    if stop:
        raw["stop_when"] = stop
    return load_workflow(raw), {c["id"]: c for c in model["handler"]["cases"]}, colors


def _frame(colors, cond):
    img = blank(70)
    paint_condition(img, cond, colors)
    return img


def test_601_kirin_challenge_and_done_gate():
    wf, cases, colors = _build(601)
    f0 = _frame(colors, cases["kirin_challenge"]["when"])
    run, dev, _ = run_synthetic(wf, [f0, f0], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1
    assert 1139 <= dev.inputs[0][1] <= 1228

    f1 = _frame(colors, cases["hunt_done_return_yard"]["when"])
    run, dev, _ = run_synthetic(wf, [f1, f1], max_seconds=5)
    assert run.status == "failed"
    assert "hunt_done_rerun" in run.reason
    assert len(dev.inputs) == 1
    assert 18 <= dev.inputs[0][1] <= 64


def test_604_retreat_challenge_and_done_gate():
    wf, cases, colors = _build(604)
    f0 = _frame(colors, cases["retreat_challenge"]["when"])
    run, dev, _ = run_synthetic(wf, [f0, f0], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1
    assert 1157 <= dev.inputs[0][1] <= 1232

    f1 = _frame(colors, cases["retreat_done_return_yard"]["when"])
    run, dev, _ = run_synthetic(wf, [f1, f1], max_seconds=5)
    assert run.status == "failed"
    assert "retreat_done_rerun" in run.reason
    assert len(dev.inputs) == 1
    assert 25 <= dev.inputs[0][1] <= 75


def test_606_gate_entries_round36_and_done_gate():
    wf, cases, colors = _build(606)
    for case_id, x_bounds in (
        ("gate_entry_0", (1058, 1268)),
        ("gate_entry_1", (342, 443)),
        ("gate_entry_4", (176, 351)),
        ("gate_entry_5", (187, 330)),
        ("gate_round36_confirm", (699, 816)),
    ):
        f = _frame(colors, cases[case_id]["when"])
        run, dev, _ = run_synthetic(wf, [f, f], max_seconds=5)
        assert run.status == "success", run.summary()
        assert len(dev.inputs) == 1
        assert x_bounds[0] <= dev.inputs[0][1] <= x_bounds[1]

    f_done = _frame(colors, cases["gate_done_return_yard"]["when"])
    run, dev, _ = run_synthetic(wf, [f_done, f_done], max_seconds=5)
    assert run.status == "failed"
    assert "gate_done_rerun" in run.reason
    assert len(dev.inputs) == 1
    assert 1168 <= dev.inputs[0][1] <= 1198
