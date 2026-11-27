"""Offline unit tests for OAS KittyShop, MysteryShop, DailyTrifles, and WeeklyTrifles."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_trifles_and_shops import (
    compile_daily_trifles_candidate,
    compile_kitty_shop_candidate,
    compile_mystery_shop_candidate,
    compile_weekly_trifles_candidate,
)
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.workflow import engine
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import MillisecondClock
from test_navigation_family import converted, inert_source


@pytest.fixture(scope="module")
def oas_stage(inert_source, converted):
    stage, folder = converted
    for task in ("KittyShop", "ActivityShikigami", "MysteryShop", "DailyTrifles", "WeeklyTrifles",
                 "RichMan", "Component_Buy", "Component_Summon", "Component_GeneralInvite"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_int=None, ocr_single=None, ocr_seq=None, full_ocr_reader=None, confirm=None, boxes=None):
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

    def read_int(image, region):
        return (ocr_int or {}).get(int(image[0, 0, 0]) - 20, 0)

    def read_single(image, region, score=0.6):
        if callable(ocr_single):
            return ocr_single(image, region)
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    def read_boxes(image, region):
        txt = (ocr_seq or {}).get(int(image[0, 0, 0]) - 20, "")
        return [(txt, 0.99, (10, 10, 40, 20))] if txt else []

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match), patch("onmyoji_agentflow.vision.ocr.read_boxes", read_boxes):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, ocr_reader=read_int, single_ocr_reader=read_single,
            full_ocr_reader=full_ocr_reader, confirm=confirm, initial_vars=initial_vars,
        ).run()
    return res, device


def test_kitty_shop_one_attempt_and_exit(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_kitty_shop_candidate(src, folder)
    frames = [
        ("I_GO1",),
        ("I_START_FARMING",),
        ("I_START_ENSURE", "I_UNSELECTED"),
        ("I_START_ENSURE",),
        ("I_MAIN_FLAG", "I_MAIN_GIFT"),
        ("I_MAIN_SHARE",),
        ("I_START_FARMING", "I_UI_BACK_YELLOW"),
        ("I_CHECK_MAIN",),
    ]
    res, dev = _run(
        raw, stage / "resources", frames,
        initial_vars={"ks_phase": "enter_shop"},
        boxes={"I_MAIN_GIFT": (920, 410, 55, 46)},
    )
    assert res.status == "success", res.summary()
    assert res.oas_schedule == "KittyShop"
    assert res.variables["ks_runs_done"] == 1
    assert 920 <= dev.inputs[4][1] <= 975 and 410 <= dev.inputs[4][2] <= 456

    res_ks_tl, _ = _run(
        raw, stage / "resources", [(), ("I_START_FARMING", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"ks_attempts": 5, "ks_limit_seconds": 1, "ks_next_delay_s": 86400},
        initial_vars={"ks_phase": "close_result"},
    )
    assert res_ks_tl.status == "success", res_ks_tl.summary()
    assert res_ks_tl.variables["ks_exit_reason"] == "time_limit" and res_ks_tl.oas_target[0] == 86400

    res_ks_farm_tl, _ = _run(
        raw, stage / "resources",
        [("I_MAIN_FLAG", "I_MAIN_GIFT"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"ks_attempts": 5, "ks_limit_seconds": 1, "ks_next_delay_s": 86400},
        initial_vars={"ks_phase": "farming"},
    )
    assert res_ks_farm_tl.status == "success", res_ks_farm_tl.summary()
    assert res_ks_farm_tl.variables["ks_exit_reason"] == "time_limit" and res_ks_farm_tl.oas_target[0] == 86400


def test_mystery_shop_economic_guard_and_free_rewards(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_mystery_shop_candidate(src, folder)
    res_buy, dev_buy = _run(
        raw, stage / "resources", [("I_MS_SHARE",)],
        params={"mshop_mystery_amulet": True},
        initial_vars={"mshop_phase": "enter_shop"},
    )
    assert res_buy.status == "failed" and "经济确认" in res_buy.reason
    assert dev_buy.inputs == []

    res_ok, _ = _run(
        raw, stage / "resources",
        [("I_MS_SHARE", "I_MS_REWARD_3"), ("I_UI_REWARD",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MALL",)],
        initial_vars={"mshop_phase": "enter_shop"},
        ocr_int={0: 3},
    )
    assert res_ok.status == "success", res_ok.summary()
    assert res_ok.variables["mshop_rewards_claimed"] == 1

    # Share gate fails closed without mshop_confirm_share
    res_share_gate, dev_sg = _run(
        raw, stage / "resources", [("I_MS_SHARE",)],
        params={"mshop_share_enable": True},
        initial_vars={"mshop_phase": "enter_shop"},
    )
    assert res_share_gate.status == "failed" and "mshop_confirm_share" in res_share_gate.reason
    assert dev_sg.inputs == []

    # Guarded friend share + friend storefront traversal + scheduled Wed/Sat target
    from onmyoji_agentflow.vision.ocr import FullOcrArea
    res_share, _ = _run(
        raw, stage / "resources",
        [
            ("I_MS_SHARE",),
            ("I_FLAG_1_OFF", "I_INVITE_ENSURE"),
            ("I_INVITE_ENSURE",),
            ("I_SELECTED", "I_INVITE_ENSURE"),
            ("I_MS_SHARE", "I_MS_NEXT"),
            ("I_MS_BEFORE", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MALL",),
        ],
        params={
            "mshop_share_enable": True, "mshop_confirm_share": True, "mshop_share_friend": "阿离",
            "mshop_mystery_amulet": True, "mshop_max_jade": 100, "mshop_max_friends": 1,
            "mshop_next_open_delay_s": 259200,
        },
        initial_vars={"mshop_phase": "enter_shop"},
        full_ocr_reader=lambda img, _r, kw, *_a, **_k: (
            FullOcrArea((400, 220, 80, 24), keyword_complete=True)
            if int(img[0, 0, 0]) - 20 == 2 and kw == "阿离" else (0, 0, 0, 0)
        ),
        ocr_int={5: 0},
    )
    assert res_share.status == "success", res_share.summary()
    assert res_share.variables["mshop_shared"] is True
    assert res_share.variables["mshop_friends_visited"] == 1
    assert res_share.oas_target[0] == 259200

    # Multi-quantity purchase (mshop_buy_quantity=2): +1 tap -> verified total price 120 -> sensitive="花勾玉" -> balance debit
    mq_asks = []

    def mq_ocr(img, roi):
        idx = int(img[0, 0, 0]) - 20
        if roi[1] < 60:  # O_MALL_RESOURCE_5 jade balance
            return "500" if idx < 4 else "380"
        if roi[1] == 537:  # O_BUY_PRICE
            return "60" if idx == 1 else "120"
        if roi[0] == 578:  # O_BUY_NUMBER
            return "1" if idx == 1 else "2"
        return "剩余购买次数5"  # MS_STOCK_BLACK

    res_mq, _ = _run(
        raw, stage / "resources",
        [
            ("I_MS_SHARE", "I_MS_BLACK"),
            ("I_MS_CHECK_BLACK", "I_BUY_JADE", "I_BUY_PLUS"),
            ("I_MS_CHECK_BLACK", "I_BUY_JADE", "I_BUY_PLUS"),
            ("I_UI_REWARD",),
            ("I_MS_SHARE", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MALL",),
        ],
        params={
            "mshop_black_daruma_scrap": True, "mshop_buy_quantity": 2,
            "mshop_max_jade": 150, "mshop_jade_reserve": 200,
        },
        initial_vars={"mshop_phase": "offer"},
        ocr_single=mq_ocr,
        ocr_int={4: 0},
        confirm=lambda c, _d: (mq_asks.append(c) or True),
    )
    assert res_mq.status == "success", res_mq.summary()
    assert res_mq.variables["mshop_spent"] == 120 and res_mq.variables["mshop_transactions"] == 1
    assert res_mq.variables["mshop_quoted_quantity"] == 2 and mq_asks == ["花勾玉"]

    res_ms_tl, _ = _run(
        raw, stage / "resources", [("I_ME_ENTER",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MALL",)],
        params={"mshop_limit_seconds": 1, "mshop_next_open_delay_s": 259200},
        initial_vars={"mshop_phase": "enter_shop"},
    )
    assert res_ms_tl.status == "success" and res_ms_tl.variables["mshop_exit_reason"] == "time_limit"
    assert res_ms_tl.oas_target is not None and res_ms_tl.oas_target[0] == 259200

    # Multi-friend share (2 friends) + O_MS_FRIEND OCR friend-to-friend storefront switch + closed-day target schedule
    res_ms_multi, _ = _run(
        raw, stage / "resources",
        [
            ("I_MS_SHARE",),
            ("I_INVITE_ENSURE",),
            ("I_SELECTED", "I_INVITE_ENSURE"),
            ("I_MS_SHARE",),
            ("I_INVITE_ENSURE",),
            ("I_SELECTED", "I_INVITE_ENSURE"),
            ("I_MS_SHARE", "I_MS_NEXT"),
            ("I_MS_BEFORE", "I_MS_NEXT"),
            ("I_MS_BEFORE", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MALL",),
        ],
        params={
            "mshop_share_enable": True, "mshop_confirm_share": True,
            "mshop_share_friend": "阿离", "mshop_share_friend_2": "晴明",
            "mshop_mystery_amulet": True, "mshop_max_jade": 100, "mshop_max_friends": 2,
        },
        initial_vars={"mshop_phase": "enter_shop"},
        full_ocr_reader=lambda img, _r, kw, *_a, **_k: (
            FullOcrArea((400, 220, 80, 24), keyword_complete=True)
            if (int(img[0, 0, 0]) - 20, kw) in ((1, "阿离"), (4, "晴明")) else (0, 0, 0, 0)
        ),
        ocr_seq={7: "好友甲", 8: "好友乙"},
        ocr_int={8: 0},
    )
    assert res_ms_multi.status == "success", res_ms_multi.summary()
    assert res_ms_multi.variables["mshop_shares_sent"] == 2
    assert res_ms_multi.variables["mshop_friends_visited"] == 2
    assert "好友乙" in res_ms_multi.variables["mshop_cur_friend_name"]

    res_ms_closed, _ = _run(
        raw, stage / "resources", [()],
        params={"mshop_is_open_day": False, "mshop_next_open_delay_s": 172800},
    )
    assert res_ms_closed.status == "success" and res_ms_closed.variables["mshop_exit_reason"] == "closed_day"
    assert res_ms_closed.oas_target is not None and res_ms_closed.oas_target[0] == 172800


def test_daily_and_weekly_trifles_guards_and_safe_paths(oas_stage):
    stage, src, folder = oas_stage
    dt = compile_daily_trifles_candidate(src, folder)
    res_sushi, dev_sushi = _run(dt, stage / "resources", [()], params={"dt_buy_sushi_count": 2})
    assert res_sushi.status == "failed" and "勾玉" in res_sushi.reason
    assert dev_sushi.inputs == []

    res_love, _ = _run(
        dt, stage / "resources",
        [("I_L_LOVE", "I_L_COLLECT"), ("I_UI_REWARD",), ("I_UI_BACK_RED",), ("I_CHECK_MAIN",)],
        params={"dt_friend_love": True},
        initial_vars={"dt_phase": "love_open"},
    )
    assert res_love.status == "success", res_love.summary()
    assert res_love.variables["dt_friend_done"] is True

    res_dt_sched, _ = _run(
        dt, stage / "resources", [()],
        params={"dt_next_delay_s": 86400},
    )
    assert res_dt_sched.status == "success" and res_dt_sched.oas_target is not None
    assert res_dt_sched.oas_target[0] == 86400

    wt = compile_weekly_trifles_candidate(src, folder)
    res_am, dev_am = _run(
        wt, stage / "resources", [()],
        params={"wt_share_collect": False, "wt_share_area_boss": False, "wt_share_secret": False, "wt_broken_amulet": 50},
    )
    assert res_am.status == "failed" and "抽卡确认" in res_am.reason
    assert dev_am.inputs == []

    res_wt, dev_wt = _run(
        wt, stage / "resources",
        [("I_WT_LOGO", "I_WT_COLLECT_WECHAT"), ("I_WT_QR_CODE",), ("I_UI_REWARD",), ("I_UI_BACK_RED",), ("I_WT_SHIKIAGMI",)],
        params={"wt_share_collect": True, "wt_share_area_boss": False, "wt_share_secret": False, "wt_broken_amulet": 0},
        initial_vars={"wt_phase": "collect_enter"},
        boxes={"I_WT_COLLECT_WECHAT": (780, 645, 50, 45)},
    )
    assert res_wt.status == "success", res_wt.summary()
    assert res_wt.variables["wt_collect_done"] is True
    assert 780 <= dev_wt.inputs[0][1] <= 830 and 645 <= dev_wt.inputs[0][2] <= 690

    res_sign, dev_sign = _run(
        dt, stage / "resources",
        [("I_GIFT_SIGN",), ("I_UI_REWARD",), ("I_CHECK_MAIN",)],
        params={"dt_store_sign": True},
        initial_vars={"dt_phase": "store_gift_room", "dt_nav_arrived_sub": 1},
        boxes={"I_GIFT_SIGN": (640, 380, 115, 83)},
    )
    assert res_sign.status == "success" and res_sign.variables["dt_sign_done"] is True
    assert 640 <= dev_sign.inputs[0][1] <= 755 and 380 <= dev_sign.inputs[0][2] <= 463

    # Partial "吉" (keyword_complete=False) must NOT click luck_ocr_enter
    from onmyoji_agentflow.vision.ocr import FullOcrArea
    res_luck_part, dev_luck_part = _run(
        {**dt, "stop_when": "dt_phase == 'luck_collect'"},
        stage / "resources",
        [("I_LUCK_TITLE",)],
        params={"dt_luck_msg": True},
        initial_vars={"dt_phase": "luck_open"},
        full_ocr_reader=lambda *_a, **_k: FullOcrArea((120, 200, 60, 24), keyword_complete=False),
    )
    assert res_luck_part.status == "success" and dev_luck_part.inputs == []

    # DailyTrifles confirmed daily summon (sensitive="抽卡") + denied confirmation + 0/unreadable ticket guards + recall tab cycling
    asks = []
    res_sm, _ = _run(
        dt, stage / "resources",
        [("I_BLUE_TICKET",), ("I_ONE_TICKET",), ("I_SM_CONFIRM",), ("I_BLUE_TICKET",)],
        params={"dt_one_summon": True, "dt_confirm_summon": True},
        initial_vars={"dt_phase": "summon_open"},
        ocr_int={0: 5},
        confirm=lambda cat, _d: (asks.append(cat) or True),
    )
    assert res_sm.status == "success" and res_sm.variables["dt_summon_done"] is True and asks == ["抽卡"]
    assert res_sm.variables["dt_summon_ticket"] == 5

    res_sm_zero, dev_sm_zero = _run(
        dt, stage / "resources", [("I_BLUE_TICKET",)],
        params={"dt_one_summon": True, "dt_confirm_summon": True},
        initial_vars={"dt_phase": "summon_open"},
        ocr_int={0: 0},
        confirm=lambda _c, _d: pytest.fail("0 tickets must never prompt or summon"),
    )
    assert res_sm_zero.status == "success" and res_sm_zero.variables["dt_summon_done"] is False
    assert res_sm_zero.variables["dt_summon_ticket"] == 0 and dev_sm_zero.inputs == []

    res_sm_unreadable, dev_sm_unreadable = _run(
        dt, stage / "resources", [("I_BLUE_TICKET",)],
        params={"dt_one_summon": True, "dt_confirm_summon": True},
        initial_vars={"dt_phase": "summon_open"},
        ocr_int={0: None},
        confirm=lambda _c, _d: pytest.fail("unreadable ticket count must never prompt or summon"),
    )
    assert res_sm_unreadable.status == "success" and res_sm_unreadable.variables["dt_summon_done"] is False
    assert res_sm_unreadable.variables["dt_summon_ticket"] == -1 and dev_sm_unreadable.inputs == []

    recall_asks = []
    res_recall, _ = _run(
        dt, stage / "resources",
        [
            ("I_BLUE_TICKET",),  # recall tab 0 (O_SELECT_SM2)
            ("I_BLUE_TICKET",),  # recall tab 1 (O_SELECT_SM3)
            ("I_RECALL_TICKET",),
            ("I_RECALL_ONE_TICKET",),
            ("I_RECALL_SM_CONFIRM",),
            ("I_BLUE_TICKET",),
        ],
        params={"dt_one_summon": True, "dt_confirm_summon": True, "dt_summon_type": "今忆召唤"},
        initial_vars={"dt_phase": "summon_open"},
        ocr_int={2: 3},
        confirm=lambda cat, _d: (recall_asks.append(cat) or True),
    )
    assert res_recall.status == "success" and res_recall.variables["dt_summon_done"] is True
    assert res_recall.variables["dt_recall_tab"] == 2 and recall_asks == ["抽卡"]

    res_sm_deny, dev_sm_deny = _run(
        dt, stage / "resources", [("I_BLUE_TICKET",), ("I_ONE_TICKET",)],
        params={"dt_one_summon": True, "dt_confirm_summon": True},
        initial_vars={"dt_phase": "summon_open"},
        ocr_int={0: 5},
        confirm=lambda _c, _d: False,
    )
    assert res_sm_deny.status == "failed" and res_sm_deny.failure_kind == "confirm_denied"
    assert len(dev_sm_deny.inputs) == 1

    # WeeklyTrifles confirmed broken-amulet batch summon with remain-deduction check
    wt_asks = []
    res_ba, _ = _run(
        wt, stage / "resources",
        [("I_BM_ENTER",), ("I_BM_AGAIN", "I_BM_CONFIRM"), ("I_CHECK_SUMMON",)],
        params={
            "wt_share_collect": False, "wt_share_area_boss": False, "wt_share_secret": False,
            "wt_broken_amulet": 10, "wt_confirm_broken_amulet": True,
        },
        initial_vars={"wt_phase": "broken_loop"},
        ocr_single={0: "25", 1: "15"},
        confirm=lambda cat, _d: (wt_asks.append(cat) or True),
    )
    assert res_ba.status == "success" and res_ba.variables["wt_ba_summoned"] == 10
    assert res_ba.variables["wt_broken_done"] is True and wt_asks == ["抽卡"]

    res_wt_mon, _ = _run(
        wt, stage / "resources", [()],
        params={
            "wt_share_collect": False, "wt_share_area_boss": False, "wt_share_secret": False,
            "wt_broken_amulet": 0, "wt_next_monday_delay_s": 604800,
        },
    )
    assert res_wt_mon.status == "success" and res_wt_mon.oas_target is not None
    assert res_wt_mon.oas_target[0] == 604800

    res_dt_tl, _ = _run(
        dt, stage / "resources", [("I_FRIENDSHIP_UP",), ("I_UI_BACK_RED",), ("I_CHECK_MAIN",)],
        params={"dt_friend_love": True, "dt_luck_msg": True, "dt_limit_seconds": 1, "dt_next_delay_s": 86400},
        initial_vars={"dt_phase": "love_open"},
    )
    assert res_dt_tl.status == "success" and res_dt_tl.variables["dt_exit_reason"] == "time_limit"
    assert res_dt_tl.oas_target is not None and res_dt_tl.oas_target[0] == 86400

    res_wt_tl, _ = _run(
        wt, stage / "resources", [("I_WT_SHIKIAGMI",), ("I_WT_SHIKIAGMI",)],
        params={
            "wt_share_collect": True, "wt_share_area_boss": True,
            "wt_limit_seconds": 1, "wt_next_monday_delay_s": 604800,
        },
        initial_vars={"wt_phase": "collect_enter"},
    )
    assert res_wt_tl.status == "success" and res_wt_tl.variables["wt_exit_reason"] == "time_limit"
    assert res_wt_tl.oas_target is not None and res_wt_tl.oas_target[0] == 604800
