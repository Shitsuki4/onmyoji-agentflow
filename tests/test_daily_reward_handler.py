"""Unit tests for 518_领取日常奖励 native handler."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "daily_reward_handler.json"


def _build(*, stop="handler_phase == 0 and elapsed_ms >= 1"):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    colors = data["colors"]
    model = compile_team_handler(data["source"], colors)
    native = team_workflow(
        "test_518",
        [model],
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


def test_518_email_claim_and_finish():
    wf, cases, colors = _build()
    f_mail = _frame(colors, cases["email_claim_8"]["when"])
    run, dev, _ = run_synthetic(wf, [f_mail, f_mail], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["email_yuHun"] == 1
    assert len(dev.inputs) == 1
    assert 1137 <= dev.inputs[0][1] <= 1171

    f_del = _frame(colors, cases["email_finish_17"]["when"])
    run, dev, _ = run_synthetic(wf, [f_del, f_del], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["daily518_email"] is False


def test_518_email_yuhun_full_push_gate():
    wf, _, _ = _build()
    run, _, _ = run_synthetic(wf, [blank(70)], initial_vars={"email_yuHun": 8}, max_seconds=5)
    assert run.status == "failed"
    assert "email_yuhun_full_push" in run.reason


def test_518_agency_done_and_bounded_loop():
    wf, cases, colors = _build()
    f_done = _frame(colors, cases["agency_already_done"]["when"])
    run, _, _ = run_synthetic(wf, [f_done], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["daily518_agency"] is False

    # 2 clicks of op[2] -> disables agency and returns True
    f_ag = _frame(colors, cases["agency_loop_tap"]["when"])
    approvals = []
    run, dev, clock = run_synthetic(wf, [f_ag] * 6, max_seconds=10,
                                    confirm=lambda category, _: approvals.append(category) or True)
    assert run.status == "success", run.summary()
    assert run.variables["daily518_agency"] is False
    assert len(dev.inputs) == 2
    assert approvals == ["购买", "分解"] * 2
    assert clock.ms >= 1000


def test_518_agency_refuses_unapproved_material_submission():
    wf, cases, colors = _build()
    frame = _frame(colors, cases["agency_loop_tap"]["when"])
    run, dev, _ = run_synthetic(wf, [frame], max_seconds=5, confirm=lambda category, _: category == "购买")
    assert run.failure_kind == "confirm_denied" and not dev.inputs
    assert run.variables["daily518_loop_cnt"] == 0


def test_518_shop_daruma_and_daily_tab():
    wf, cases, colors = _build()
    f_open = _frame(colors, cases["shop_loop_check"]["when"])
    f_daruma = _frame(colors, cases["shop_claim_daruma"]["when"])
    run, dev, _ = run_synthetic(wf, [f_open, f_daruma, f_daruma], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["daily518_shop"] is False
    assert len(dev.inputs) == 3  # daruma + confirm + exit shop

    f_tab = _frame(colors, cases["shop_open_daily_tab"]["when"])
    run, dev, _ = run_synthetic(wf, [f_open, f_tab, f_tab], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1
    assert run.variables["daily518_shop"] is True


def test_518_flower_claim_and_exit_and_godlike_gate():
    wf, cases, colors = _build()
    f_claim = _frame(colors, cases["flower_claim_all"]["when"])
    run, dev, _ = run_synthetic(wf, [f_claim, f_claim], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 2
    assert run.variables["daily518_flower"] is True

    f_exit = _frame(colors, cases["flower_exit"]["when"])
    run, dev, _ = run_synthetic(wf, [f_exit, f_exit], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["daily518_flower"] is False

    # All 5 in-game switches finished -> hits explicit godlike Dashen gate
    run, _, _ = run_synthetic(
        wf,
        [blank(70)],
        initial_vars={
            "daily518_agency": False,
            "daily518_shop": False,
            "daily518_friend": False,
            "daily518_flower": False,
            "daily518_email": False,
        },
        max_seconds=5,
    )
    assert run.status == "failed"
    assert "godlike_dashen_app" in run.reason
