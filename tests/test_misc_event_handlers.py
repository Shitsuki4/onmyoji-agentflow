"""Unit tests for 304 (绘卷进度), 401 (对弈竞猜), and 1110 (神秘商店) native handlers."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import blank, paint_condition
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "misc_event_handlers.json"


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


def test_304_donate_small_close_and_ocr_gates():
    wf, cases, colors = _build(304, config={"osp": False, "rankOpen": "50"})
    # Progress screen with paiMing > 50 and small scrolls available -> 4 clicks + 61s sleep
    f_prog = _frame(colors, cases["progress_rank_ok_close"]["when"])
    run, dev, clock = run_synthetic(wf, [f_prog, f_prog], initial_vars={"paiMing": 80}, max_seconds=120)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 4
    assert clock.ms >= 61000

    # Progress screen with paiMing <= 50 -> close only + 61s sleep
    run, dev, _ = run_synthetic(wf, [f_prog, f_prog], initial_vars={"paiMing": 30}, max_seconds=120)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1

    # Main emaki list hits explicit OCR rank gate
    f_list = _frame(colors, cases["emaki_rank_ocr"]["when"])
    run, _, _ = run_synthetic(wf, [f_list], max_seconds=5)
    assert run.status == "failed"
    assert "emaki_rank_ocr_and_enter" in run.reason


def test_401_yard_probe_and_bet_wager_gate():
    wf, cases, colors = _build(401, config={"follow_whose": "面灵气喵", "data_source": "api"})
    f_yard = _frame(colors, cases["yard_probe_init"]["when"]["any"][0])
    f_icon = _frame(colors, cases["yard_click_bet"]["when"])
    run, dev, clock = run_synthetic(wf, [f_yard, f_icon, f_icon], max_seconds=10)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1
    assert clock.ms >= 1480

    # Bet selection screen hits explicit external feed + economic wager gate
    f_bet = _frame(colors, cases["bet_select_side"]["when"])
    run, _, _ = run_synthetic(wf, [f_bet], max_seconds=5)
    assert run.status == "failed"
    assert "bet_external_feed_and_wager" in run.reason


def test_1110_nav_scroll_and_economic_guards():
    wf, cases, colors = _build(1110, config={"black": True})
    # Shop entry nav clicks natively
    f_nav = _frame(colors, cases["shop_nav_3"]["when"])
    run, dev, _ = run_synthetic(wf, [f_nav, f_nav], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1

    # Buy dialog is economically gated (never auto-buys)
    f_buy = _frame(colors, cases["shop_confirm_buy_dialog"]["when"])
    run, dev, _ = run_synthetic(wf, [f_buy], max_seconds=5)
    assert run.status == "failed"
    assert "mystery_shop_confirm_purchase" in run.reason
    assert dev.inputs == []

    # 3 misses in mystery shop -> native swipe down via lowerings
    f_shop = _frame(colors, cases["shop_loop_check"]["when"])
    run, dev, _ = run_synthetic(wf, [f_shop] * 8, max_seconds=10)
    assert run.status == "success", run.summary()
    assert len(dev.swipe_durations) == 1
    assert 700 <= dev.swipe_durations[0] <= 800
