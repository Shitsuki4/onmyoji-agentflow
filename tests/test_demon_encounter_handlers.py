"""Unit tests for 023_逢魔答题 and 508_逢魔首领 native handlers."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "demon_encounter_handlers.json"


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


def test_023_quiz_dialog_gate_and_unmatched_passthrough():
    wf, cases, colors = _build(23)
    # Non-quiz frame passes through cleanly without failing
    run, dev, _ = run_synthetic(wf, [blank(70)], max_seconds=5)
    assert run.status == "success", run.summary()
    assert dev.inputs == []

    # Quiz dialog frame hits explicit OCR + question bank obligation
    f_quiz = _frame(colors, cases["demon_quiz_dialog"]["when"])
    run, _, _ = run_synthetic(wf, [f_quiz], max_seconds=5)
    assert run.status == "failed"
    assert "demon_quiz_ocr_lookup" in run.reason


def test_508_gathering_trash_and_boss_page_retry():
    wf, cases, colors = _build(508)
    f_trash = _frame(colors, cases["gathering_pick_trash"]["when"])
    run, dev, _ = run_synthetic(wf, [f_trash, f_trash], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["fm_kiss_boss_flag"] is True
    assert len(dev.inputs) == 1

    # Boss challenge page increments checked_yard_count and sleeps 1000ms
    f_boss = _frame(colors, cases["boss_page_challenge"]["when"]["any"][0])
    run, dev, clock = run_synthetic(wf, [f_boss, f_boss], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["checked_yard_count"] == 1
    assert clock.ms >= 1000
    assert 1062 <= dev.inputs[0][1] <= 1161

    # At checked_yard_count == 5 -> resets to 0, closes boss page, sleeps 2000ms
    run, dev, clock = run_synthetic(
        wf,
        [f_boss, f_boss],
        initial_vars={"checked_yard_count": 5},
        max_seconds=5,
    )
    assert run.status == "success", run.summary()
    assert run.variables["checked_yard_count"] == 0
    assert len(dev.inputs) == 2
    assert clock.ms >= 2000


def test_508_search_ji_fallback_and_done_rerun_gate():
    wf, cases, colors = _build(
        508,
        config={"switch_ji_enabled": True, "times_for_search_boss": 2, "next_scheme": "每日签到与收取邮件"},
    )
    # Click 0 with ji enabled and op[9] visible -> clicks ji button (903..940)
    f_ji = _frame(colors, cases["boss_done_return_yard"]["when"], cases["search_click_ji"]["when"])
    run, dev, clock = run_synthetic(wf, [f_ji, f_ji], max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["fm_boss_btn_click_cnt"] == 1
    assert 903 <= dev.inputs[0][1] <= 940
    assert clock.ms >= 2000

    # At cnt == 4 (>= 2*2) on op[0] -> marks fm_kiss_boss_flag = True
    f_norm = _frame(colors, cases["boss_done_return_yard"]["when"])
    run, dev, _ = run_synthetic(wf, [f_norm, f_norm], initial_vars={"fm_boss_btn_click_cnt": 4}, max_seconds=5)
    assert run.status == "success", run.summary()
    assert run.variables["fm_kiss_boss_flag"] is True
    assert run.variables["fm_boss_btn_click_cnt"] == 5

    # When fm_kiss_boss_flag is True -> sets super_next_scheme_name and hits rerun gate
    run, _, _ = run_synthetic(wf, [f_norm], initial_vars={"fm_kiss_boss_flag": True}, max_seconds=5)
    assert run.status == "failed"
    assert "demon_boss_done_rerun" in run.reason
    assert run.variables["super_next_scheme_name"] == "每日签到与收取邮件"
