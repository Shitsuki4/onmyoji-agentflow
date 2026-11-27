"""Offline unit tests for OAS Delegation, MemoryScrolls, and SoulsTidy."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_daily_utilities import (
    compile_delegation_candidate,
    compile_memory_scrolls_candidate,
    compile_souls_tidy_candidate,
)
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.vision.ocr import FullOcrArea
from onmyoji_agentflow.workflow import engine
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import MillisecondClock
from test_navigation_family import converted, inert_source


@pytest.fixture(scope="module")
def oas_stage(inert_source, converted):
    stage, folder = converted
    for task in ("Delegation", "MemoryScrolls", "SoulsTidy"):
        convert_task(inert_source / "tasks" / task, folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_full=None, ocr_int=None, ocr_seq=None, confirm=None, boxes=None):
    wf = load_workflow(raw, [root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, *_a, **_kw):
        vis = frames[int(image[0, 0, 0]) - 20]
        hits = set(vis) & aliases.get(Path(path).resolve(), set())
        if not hits:
            return False, 0.0, (0, 0, 0, 0)
        for h in hits:
            if boxes and h in boxes:
                return True, 1.0, boxes[h]
        return True, 1.0, (200, 120, 40, 32)

    def full_ocr(image, region, keyword, score=0.6, **_kw):
        idx = int(image[0, 0, 0]) - 20
        for kw, box in (ocr_full or {}).get(idx, []):
            if kw == keyword:
                return box if isinstance(box, FullOcrArea) else FullOcrArea(box, keyword_complete=True)
        return FullOcrArea((0, 0, 0, 0), keyword_complete=False)

    def read_int(image, region):
        return (ocr_int or {}).get(int(image[0, 0, 0]) - 20, 0)

    def read_boxes(image, region):
        txt = (ocr_seq or {}).get(int(image[0, 0, 0]) - 20, "")
        return [(txt, 0.99, (10, 10, 40, 20))] if txt else []

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match), patch("onmyoji_agentflow.vision.ocr.read_boxes", read_boxes):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, ocr_reader=read_int, full_ocr_reader=full_ocr,
            confirm=confirm, initial_vars=initial_vars,
        ).run()
    return res, device


def test_delegation_reward_jade_cancel_and_start(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_delegation_candidate(src, folder)
    frames = [
        ("I_REWARDS_GET",),
        ("I_REWARDS_MIN",),  # dispatch bird_feather
        ("I_UI_CANCEL",),    # jade safety cancel first!
        ("I_D_START",),      # select 1
        ("I_D_START", "I_D_SELECT_1"),
        ("I_D_START", "I_D_SELECT_2"),
        ("I_D_START", "I_D_SELECT_3"),
        ("I_D_START", "I_D_SELECT_4"),
        ("I_REWARDS_MIN",),
    ]
    res, dev = _run(
        raw, stage / "resources", frames,
        params={"del_bird_feather": True},
        initial_vars={"del_phase": "check_reward"},
        ocr_full={1: [("鸟羽", (300, 200, 80, 30))]},
        boxes={"I_UI_CANCEL": (400, 560, 177, 62)},
    )
    assert res.status == "success", res.summary()
    assert res.oas_schedule == "Delegation"
    assert res.variables["del_rewards_claimed"] == 1
    assert res.variables["del_started_count"] == 1
    assert len(dev.inputs) >= 7
    assert 400 <= dev.inputs[2][1] <= 577 and 560 <= dev.inputs[2][2] <= 622

    res_del_tl, _ = _run(
        raw, stage / "resources",
        [("I_REWARDS_GET",), ("I_REWARDS_MIN",)],
        params={"del_bird_feather": True, "del_limit_seconds": 1, "del_next_delay_s": 10800},
        initial_vars={"del_phase": "check_reward"},
    )
    assert res_del_tl.status == "success", res_del_tl.summary()
    assert res_del_tl.variables["del_exit_reason"] == "time_limit" and res_del_tl.oas_target[0] == 10800

    # Multi-card "完成" ribbon uses first_contains + projected_rect (directly below ribbon box)
    seen_selections = []

    def full_ocr_ribbon(image, region, keyword, score=0.6, **kw):
        idx = int(image[0, 0, 0]) - 20
        seen_selections.append((idx, keyword, kw.get("selection")))
        if idx == 0 and keyword == "完成":
            return (220, 180, 60, 24)
        return (0, 0, 0, 0)

    wf = load_workflow(raw, [stage / "resources"])
    aliases = {Path(spec["path"]).resolve(): name.rsplit("::", 1)[-1]
               for name, spec in wf.resources.items() if spec["type"] == "image"}
    frames_ribbon = [("I_REWARDS_MIN",), ("I_REWARDS_GET",), ("I_REWARDS_MIN",)]
    dev_ribbon = ReplayDevice([blank(20 + i) for i in range(len(frames_ribbon))], advance_on_input=True)
    clk_ribbon = MillisecondClock()
    with patch.object(engine, "match_template",
                      lambda img, p, *_a, **_k: (
                          aliases.get(Path(p).resolve()) in frames_ribbon[int(img[0, 0, 0]) - 20], 1.0, (200, 120, 40, 32)
                      )):
        res_ribbon = engine.Runner(
            wf, Controller(dev_ribbon, sleep=clk_ribbon.sleep), clock=clk_ribbon, max_seconds=60,
            initial_vars={"del_phase": "check_reward"}, full_ocr_reader=full_ocr_ribbon,
        ).run()
    assert res_ribbon.status == "success", res_ribbon.summary()
    assert res_ribbon.variables["del_rewards_claimed"] == 1
    assert (0, "完成", "first_contains") in seen_selections
    # Click 0 must land inside projected [220, 204, 280, 228] (match_y + match_h .. match_y + 2*match_h)
    assert 220 <= dev_ribbon.inputs[0][1] <= 280
    assert 204 <= dev_ribbon.inputs[0][2] <= 228

    # Partial "寻找秘宝" match (keyword_complete=False) must NEVER click "寻找耳环"
    res_part, dev_part = _run(
        raw, stage / "resources", [("I_REWARDS_MIN",)],
        params={"del_find_earring": True},
        initial_vars={"del_phase": "dispatch"},
        ocr_full={0: [("寻找耳环", FullOcrArea((300, 200, 90, 28), keyword_complete=False))]},
    )
    assert res_part.status == "success" and res_part.variables["del_started_count"] == 0
    assert dev_part.inputs == []


def test_memory_scrolls_contribute_and_50_gate(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_memory_scrolls_candidate(src, folder)
    # Below 50 fails as upstream requires
    res_low, _ = _run(
        raw, stage / "resources", [("I_MS_FRAGMENT_S_VERIFICATION",)],
        params={"ms_auto_finish_exploration": True},
        initial_vars={"ms_phase": "check_50"},
    )
    assert res_low.status == "failed" and "未达50" in res_low.reason

    # Reached 50 wakes Exploration via oas_wake, closes verification popup, and proceeds to enter_scroll
    res_50, _ = _run(
        {**raw, "stop_when": "ms_phase == 'enter_scroll'"},
        stage / "resources",
        [("I_MS_FRAGMENT_S_VERIFICATION", "I_MS_FRAGMENT_S_50"), ("I_MS_FRAGMENT_S",)],
        params={"ms_auto_finish_exploration": True},
        initial_vars={"ms_phase": "check_50"},
    )
    assert res_50.status == "success", res_50.summary()
    assert res_50.variables["ms_exploration_woken"] is True
    assert list(res_50.oas_wakes) == ["Exploration"]

    # Contribute 1 round then zero -> exit cleanly
    frames = [
        ("I_MS_ENTER",),
        ("I_MS_FRAGMENT_S",),
        *[("I_UI_BACK_RED", "I_MS_CONTRIBUTE")] * 7,
        ("I_UI_BACK_RED", "I_MS_ZERO_S", "I_MS_ZERO_M", "I_MS_ZERO_L"),
        ("I_UI_BACK_YELLOW",),
        ("I_CHECK_SUMMON",),
    ]
    res, _ = _run(raw, stage / "resources", frames, initial_vars={"ms_phase": "enter_main"})
    assert res.status == "success", res.summary()
    assert res.oas_schedule == "MemoryScrolls"
    assert res.variables["ms_rounds"] == 1

    # Complete scroll: default ms_auto_close_exploration fails closed; opt-in local close logs and exits cleanly
    res_close_gate, dev_close = _run(
        raw, stage / "resources", [("I_MS_COMPLETE",)],
        params={"ms_auto_close_exploration": True},
        initial_vars={"ms_phase": "inspect_scroll"},
    )
    assert res_close_gate.status == "failed" and dev_close.inputs == []

    res_close_ok, _ = _run(
        raw, stage / "resources",
        [("I_MS_COMPLETE", "I_UI_BACK_RED"), ("I_UI_BACK_YELLOW",), ("I_CHECK_SUMMON",)],
        params={
            "ms_notification_95": True, "ms_auto_close_exploration": True,
            "ms_allow_local_close_log": True, "ms_next_delay_s": 86400,
        },
        initial_vars={"ms_phase": "inspect_scroll"},
    )
    assert res_close_ok.status == "success", res_close_ok.summary()
    assert res_close_ok.variables["ms_notified_95"] is True
    assert res_close_ok.variables["ms_exploration_closed"] is True
    assert res_close_ok.variables["ms_exit_reason"] == "scroll_complete_close_exploration"
    assert res_close_ok.oas_target is not None and res_close_ok.oas_target[0] == 86400

    res_ms_tl, _ = _run(
        raw, stage / "resources",
        [("I_MS_CONTRIBUTED",), ("I_UI_BACK_RED",), ("I_UI_BACK_YELLOW",), ("I_CHECK_SUMMON",)],
        params={"ms_limit_seconds": 1, "ms_next_delay_s": 86400},
        initial_vars={"ms_phase": "contribute"},
    )
    assert res_ms_tl.status == "success" and res_ms_tl.variables["ms_exit_reason"] == "time_limit"
    assert res_ms_tl.oas_target is not None and res_ms_tl.oas_target[0] == 86400


def test_souls_tidy_consume_gate_and_confirmed_flow(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_souls_tidy_candidate(src, folder)
    # Default st_confirm_consume=False blocks greed feeding with 0 inputs
    res_gate, dev_gate = _run(
        raw, stage / "resources", [("I_ST_FEED_NOW",)],
        initial_vars={"st_phase": "greed_feed"},
    )
    assert res_gate.status == "failed" and "st_confirm_consume" in res_gate.reason
    assert dev_gate.inputs == []

    # Confirmed stack donate + return to records
    frames = [
        ("I_ST_SOUL_STACK",),
        ("I_ST_DONATE", "I_ST_GOLD"),
        ("I_ST_GOD_PRESENT", "I_ST_GOLD"),
        ("I_ST_CAT", "I_UI_BACK_YELLOW"),
        ("I_CHECK_RECORDS",),
    ]
    asks = []
    res, _ = _run(
        raw, stage / "resources", frames,
        params={"st_confirm_consume": True, "st_max_donate_rounds": 1, "st_next_delay_s": 21600},
        initial_vars={"st_phase": "maneki_select"},
        ocr_int={1: 12000},
        confirm=lambda cat, _d: (asks.append(cat) or True),
    )
    assert res.status == "success", res.summary()
    assert res.oas_target is not None and res.oas_target[0] == 21600
    assert res.oas_schedule == "SoulsTidy"

    # Partial "+15" match (keyword_complete=False) must NEVER donate an upgraded soul
    res_plus15, dev_plus15 = _run(
        raw, stage / "resources", [("I_ST_LEVEL_0", "I_CHECK_RECORDS")],
        params={"st_confirm_consume": True},
        initial_vars={"st_phase": "maneki_select"},
        ocr_full={0: [("+0", FullOcrArea((120, 120, 30, 18), keyword_complete=False))]},
        confirm=lambda _c, _d: pytest.fail("+15 partial match must never prompt or donate"),
    )
    assert res_plus15.status == "success"
    assert res_plus15.variables["st_exit_reason"] == "non_zero_level"
    assert dev_plus15.inputs == []
    assert res.variables["st_donate_rounds"] == 1 and asks == ["分解"]

    # Runtime confirm_denied stops before donating
    res_deny, dev_deny = _run(
        raw, stage / "resources", [("I_ST_DONATE", "I_ST_GOLD")],
        params={"st_confirm_consume": True},
        initial_vars={"st_phase": "maneki_check_gold"},
        ocr_int={0: 12000},
        confirm=lambda _c, _d: False,
    )
    assert res_deny.status == "failed" and res_deny.failure_kind == "confirm_denied" and dev_deny.inputs == []

    # Greed idle timeout exits cleanly to to_cat -> sort_mode="type" -> no level 0 -> back_records
    res_timeout, _ = _run(
        raw, stage / "resources",
        [("I_ST_CAT", "I_ST_ABANDONED_SELECTED", "I_UI_BACK_YELLOW"), ("I_CHECK_RECORDS",)],
        params={"st_greed_timeout_s": 1, "st_sort_mode": "type"},
        initial_vars={"st_phase": "greed_feed"},
        ocr_full={0: [("类型", (414, 118, 64, 43))]},
    )
    assert res_timeout.status == "success", res_timeout.summary()
    assert res_timeout.variables["st_exit_reason"] == "no_level_0"

    res_st_tl, _ = _run(
        raw, stage / "resources",
        [(), ("I_ST_ABANDONED_SELECTED", "I_CHECK_RECORDS")],
        params={"st_limit_seconds": 1, "st_next_delay_s": 21600},
        initial_vars={"st_phase": "maneki_abandoned"},
    )
    assert res_st_tl.status == "success" and res_st_tl.variables["st_exit_reason"] == "time_limit"
    assert res_st_tl.oas_target is not None and res_st_tl.oas_target[0] == 21600
