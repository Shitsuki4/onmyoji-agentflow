"""Offline unit tests for OAS RichMan, SixRealms, Hyakkiyakou, and AutoCheckinBigGod."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_final_four import (
    compile_auto_checkin_big_god_candidate,
    compile_hyakkiyakou_candidate,
    compile_rich_man_candidate,
    compile_six_realms_candidate,
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
    for task in ("RichMan", "SixRealms", "Hyakkiyakou", "Component_SwitchSoul", "Component_Buy"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_int=None, ocr_single=None, ocr_full=None,
         confirm=None, roi_filter=None):
    wf = load_workflow(raw, [root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, roi=None, *_a, **_kw):
        idx = int(image[0, 0, 0]) - 20
        vis = frames[idx]
        names = aliases.get(Path(path).resolve(), set())
        hit = bool(set(vis) & names)
        if hit and roi_filter is not None and not roi_filter(idx, names, roi):
            hit = False
        return hit, float(hit), (200, 120, 40, 32)

    def read_int(image, region):
        return (ocr_int or {}).get(int(image[0, 0, 0]) - 20, 0)

    def read_single(image, region, score=0.6):
        if callable(ocr_single):
            return ocr_single(image, region)
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    def read_full(image, region, keyword, *_a, **_kw):
        text = (ocr_full or {}).get(int(image[0, 0, 0]) - 20, "")
        return (100, 25, 60, 24) if keyword and keyword in text else (0, 0, 0, 0)

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, initial_vars=initial_vars,
            ocr_reader=read_int, single_ocr_reader=read_single, full_ocr_reader=read_full, confirm=confirm,
        ).run()
    return res, device


def test_rich_man_and_six_realms(oas_stage):
    stage, src, folder = oas_stage
    rm = compile_rich_man_candidate(src, folder)
    res_gate, dev = _run(rm, stage / "resources", [()], params={"rm_enable_purchases": True})
    assert res_gate.status == "failed" and "rm_confirm_spend" in res_gate.reason
    assert dev.inputs == []

    res_skip, _ = _run(rm, stage / "resources", [()])
    assert res_skip.status == "success" and res_skip.oas_schedule == "RichMan"

    # Positive GuildStore purchase with balance, budget, reserve, confirm, and post-purchase debit check
    guild_screen = ("I_GUILD_CLOSE_RED", "I_GUILD_SCRAP")
    guild_dialog = ("I_GUILD_CHECK_SCRAP",)
    asks = []

    def guild_ocr(image, roi):
        idx = int(image[0, 0, 0]) - 20
        if roi[1] == 16:  # O_GUILD_TOTAL
            return "800" if idx < 3 else "600"
        if roi[1] == 537:  # O_BUY_PRICE
            return "200"
        return "1"

    res_guild, dev_guild = _run(
        rm, stage / "resources",
        [guild_screen, guild_dialog, ("I_UI_REWARD",), guild_screen, ("I_GUILD_SHRINE", "I_CHECK_MAIN")],
        params={
            "rm_enable_purchases": True, "rm_confirm_spend": True,
            "rm_guild_enable": True, "rm_guild_black_daruma_scrap": True,
            "rm_guild_max_budget": 200, "rm_guild_reserve": 500,
        },
        initial_vars={"rm_phase": "guild_offer"},
        ocr_single=guild_ocr,
        confirm=lambda cat, desc: (asks.append((cat, desc)) or True),
    )
    assert res_guild.status == "success", res_guild.summary()
    assert res_guild.variables["rm_guild_spent"] == 200 and res_guild.variables["rm_transactions"] == 1
    assert len(asks) == 1 and asks[0][0] == "购买" and "功勋" in asks[0][1] and len(dev_guild.inputs) == 4

    # Denied confirmation stops with confirm_denied and never clicks buy
    res_deny, dev_deny = _run(
        rm, stage / "resources", [guild_screen, guild_dialog],
        params={
            "rm_enable_purchases": True, "rm_confirm_spend": True,
            "rm_guild_enable": True, "rm_guild_black_daruma_scrap": True,
            "rm_guild_max_budget": 200,
        },
        initial_vars={"rm_phase": "guild_offer"},
        ocr_single=guild_ocr,
        confirm=lambda _c, _d: False,
    )
    assert res_deny.status == "failed" and res_deny.failure_kind == "confirm_denied" and len(dev_deny.inputs) == 1

    # RMB icon in dialog cancels purchase with 0 spend and 0 confirmations
    res_rmb, dev_rmb = _run(
        rm, stage / "resources",
        [guild_screen, ("I_GUILD_CHECK_SCRAP", "I_BUY_RMB"), guild_screen, ("I_GUILD_SHRINE", "I_CHECK_MAIN")],
        params={
            "rm_enable_purchases": True, "rm_confirm_spend": True,
            "rm_guild_enable": True, "rm_guild_black_daruma_scrap": True,
            "rm_guild_max_budget": 200,
        },
        initial_vars={"rm_phase": "guild_offer"},
        ocr_single=guild_ocr,
        confirm=lambda _c, _d: pytest.fail("RMB dialog must never ask to confirm"),
    )
    assert res_rmb.status == "success" and res_rmb.variables["rm_guild_spent"] == 0

    # Shrine positive purchase with balance deduction verification
    shrine_asks = []

    def shrine_ocr(image, roi):
        idx = int(image[0, 0, 0]) - 20
        return "2000" if idx < 4 else "500"

    res_sh, _ = _run(
        rm, stage / "resources",
        [("I_S_NEXT_PERIOD", "I_S_BLACK"), ("I_S_BUY_BLACK",), ("I_S_CONFIRM_BLACK",),
         ("I_UI_REWARD",), ("I_S_NEXT_PERIOD", "I_CHECK_MAIN")],
        params={
            "rm_enable_purchases": True, "rm_confirm_spend": True,
            "rm_shrine_enable": True, "rm_shrine_black_daruma": True,
            "rm_shrine_max_budget": 1500, "rm_shrine_reserve": 500,
        },
        initial_vars={"rm_phase": "shrine_offer"},
        ocr_single=shrine_ocr,
        confirm=lambda cat, desc: (shrine_asks.append((cat, desc)) or True),
    )
    assert res_sh.status == "success" and res_sh.variables["rm_shrine_spent"] == 1500
    assert len(shrine_asks) == 1 and shrine_asks[0][0] == "购买" and "御札" in shrine_asks[0][1]
    assert res_sh.variables["rm_transactions"] == 1

    # Consignment jade purchase (sensitive="花勾玉") + Charisma purchase
    jade_asks = []
    res_con, _ = _run(
        rm, stage / "resources",
        [("I_CON_ENTER_CHECK", "I_CON_TICKET"), ("I_BUY_PLUS",), ("I_UI_REWARD",),
         ("I_CON_ENTER_CHECK", "I_CHECK_MAIN")],
        params={
            "rm_enable_purchases": True, "rm_confirm_spend": True,
            "rm_consignment_enable": True, "rm_consignment_sale_ticket": True,
            "rm_consignment_max_jade": 100, "rm_consignment_jade_reserve": 500,
        },
        initial_vars={"rm_phase": "consignment_offer"},
        ocr_single=lambda img, roi: (
            ("1000" if int(img[0, 0, 0]) - 20 < 3 else "900") if roi[0] == 533
            else ("100" if roi[1] == 537 else "1")
        ),
        confirm=lambda cat, desc: (jade_asks.append((cat, desc)) or True),
    )
    assert res_con.status == "success" and res_con.variables["rm_consignment_spent"] == 100
    assert len(jade_asks) == 1 and jade_asks[0][0] == "花勾玉"

    res_rm_sched, _ = _run(
        rm, stage / "resources", [("I_CHECK_MAIN",)],
        params={"rm_next_delay_s": 86400},
        initial_vars={"rm_phase": "exit_main"},
    )
    assert res_rm_sched.status == "success" and res_rm_sched.oas_target is not None
    assert res_rm_sched.oas_target[0] == 86400

    res_rm_tl, _ = _run(
        rm, stage / "resources", [("I_TT_ENTER",), ("I_CHECK_MAIN",)],
        params={"rm_limit_seconds": 1, "rm_next_delay_s": 86400},
        initial_vars={"rm_phase": "tt_enter"},
    )
    assert res_rm_tl.status == "success", res_rm_tl.summary()
    assert res_rm_tl.variables["rm_exit_reason"] == "time_limit"
    assert res_rm_tl.oas_target is not None and res_rm_tl.oas_target[0] == 86400

    sr = compile_six_realms_candidate(src, folder)
    res_ap, dev = _run(sr, stage / "resources", [("I_MSTART",)], initial_vars={"sr_phase": "gate"})
    assert res_ap.status == "failed" and "sr_confirm_ap_cost" in res_ap.reason
    assert dev.inputs == []

    # 60 AP start requires runtime sensitive="购买" confirmation
    res_ap_deny, dev_ap_deny = _run(
        sr, stage / "resources", [("I_MSTART",)],
        params={"sr_confirm_ap_cost": True},
        initial_vars={"sr_phase": "gate"},
        confirm=lambda _c, _d: False,
    )
    assert res_ap_deny.status == "failed" and res_ap_deny.failure_kind == "confirm_denied"
    assert dev_ap_deny.inputs == []

    sr_asks = []
    res_sr_full, _ = _run(
        sr, stage / "resources",
        [
            ("I_MSTART",),
            ("I_MSTART_CONFIRM",),
            ("I_MFIRST_SKILL",),
            ("I_ISLAND_MARKER_104",),
            ("I_SKILL101", "I_SELECT_1"),
            ("I_BOSS_FIRE", "I_BOSS_TEAM_UNLOCK"),
            ("I_BOSS_FIRE",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_BOSS_USE_DOUBLE",),
            ("I_BOSS_SHARE",),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        params={"sr_confirm_ap_cost": True, "sr_use_double_ticket": True, "sr_confirm_double_ticket": True},
        initial_vars={"sr_phase": "gate"},
        confirm=lambda cat, _d: (sr_asks.append(cat) or True),
    )
    assert res_sr_full.status == "success", res_sr_full.summary()
    assert sr_asks == ["购买", "花勾玉"]
    assert res_sr_full.variables["sr_ap_started"] == 1 and res_sr_full.variables["sr_double_used"] == 1
    assert res_sr_full.variables["sr_skills_picked"] == 2 and res_sr_full.variables["sr_wins"] == 1

    res_sr, _ = _run(
        sr, stage / "resources",
        [("I_BOSS_FIRE",), ("I_BATTLE_INFO", "I_WIN"), ("I_BOSS_SHARE",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        initial_vars={"sr_phase": "inside"},
    )
    assert res_sr.status == "success", res_sr.summary()
    assert res_sr.variables["sr_wins"] == 1 and res_sr.variables["sr_runs"] == 1

    # Skill refresh (coin>=50 + 剩N次>0 + soft-wind<5) -> fallback pick I_SELECT_3 first,
    # MoonSea store refresh with coin + O_STORE_REFRESH_TIME OCR, and wall-clock temporary leave
    res_sr_shop, _ = _run(
        sr, stage / "resources",
        [
            ("I_SKILL_REFRESH", "I_SELECT_2", "I_SELECT_3"),
            ("I_SKILL_REFRESH", "I_UI_CONFIRM"),
            ("I_SKILL_REFRESH", "I_SELECT_2", "I_SELECT_3"),
            ("I_M_STORE_ACTIVITY",),
            ("I_STORE_REFRESH", "I_STORE_EXIT"),
            ("I_STORE_REFRESH", "I_STORE_EXIT"),
            ("I_BOSS_SHARE",),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "sr_shop_refresh_enable": True, "sr_max_shop_refreshes": 1,
            "sr_shop_min_coins": 50, "sr_max_skill_refreshes": 1,
        },
        initial_vars={"sr_phase": "inside"},
        ocr_int={0: 120, 2: 120, 4: 120, 5: 40},
        ocr_single={0: "剩2次", 2: "剩1次", 4: "剩2次", 5: "剩1次"},
    )
    assert res_sr_shop.status == "success", res_sr_shop.summary()
    assert res_sr_shop.variables["sr_skill_refreshes"] == 1
    assert res_sr_shop.variables["sr_skills_picked"] == 1
    assert res_sr_shop.variables["sr_shop_refreshes"] == 1
    assert res_sr_shop.variables["sr_skill_refresh_left"] == 2
    assert res_sr_shop.variables["sr_store_refresh_left"] == 2

    # Column-aware I_SKILL101/I_SKILL105 matching, 剩0次 refresh guard, and NPC battle team lock
    def _col2_only(idx, names, roi):
        if idx == 0 and "I_SKILL101_COL2" in names:
            return roi is not None and roi[0] >= 600
        if idx == 1 and "I_SKILL105_COL2" in names:
            return roi is not None and roi[0] >= 600
        return True

    res_sr_cols, dev_sr_cols = _run(
        sr, stage / "resources",
        [
            ("I_SKILL101", "I_SELECT_0", "I_SELECT_1", "I_SELECT_2", "I_SELECT_3"),
            ("I_SKILL105", "I_SELECT_0", "I_SELECT_1", "I_SELECT_2", "I_SELECT_3"),
            ("I_SKILL_REFRESH", "I_SELECT_0", "I_SELECT_3"),  # 剩0次 -> must NOT refresh, picks I_SELECT_3
            ("I_NPC_FIRE", "I_BATTLE_TEAM_UNLOCK"),
            ("I_NPC_FIRE",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_BOSS_SHARE",),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        params={"sr_max_skill_refreshes": 2},
        initial_vars={"sr_phase": "inside"},
        ocr_int={2: 200},
        ocr_single={2: "剩0次"},
        roi_filter=_col2_only,
    )
    assert res_sr_cols.status == "success", res_sr_cols.summary()
    assert res_sr_cols.variables["sr_soft_wind_level"] == 2
    assert res_sr_cols.variables["sr_skills_picked"] == 3
    assert res_sr_cols.variables["sr_skill_refreshes"] == 0
    assert res_sr_cols.variables["sr_team_locked"] is True
    # First two clicks must target I_SELECT_2 (x in 696..836), third click I_SELECT_3 (x in 1016..1161)
    assert 696 <= dev_sr_cols.inputs[0][1] <= 836
    assert 696 <= dev_sr_cols.inputs[1][1] <= 836
    assert 1016 <= dev_sr_cols.inputs[2][1] <= 1161

    res_sr_tl, _ = _run(
        sr, stage / "resources",
        [("I_BACK_EXIT",), ("I_EXIT_SIXREALMS",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"sr_limit_seconds": 0, "sr_next_delay_s": 86400},
        initial_vars={"sr_phase": "inside"},
    )
    assert res_sr_tl.status == "success", res_sr_tl.summary()
    assert res_sr_tl.variables["sr_exit_reason"] == "time_limit"
    assert res_sr_tl.oas_target is not None and res_sr_tl.oas_target[0] == 86400

    # MoonSea islands l101 (soft-wind store buy), l102 (imitation + transfer skip), l104/l105 OCR NPC engage + I_BOSS_SHUTU
    res_sr_isl, _ = _run(
        sr, stage / "resources",
        [
            ("I_STORE_EXIT", "I_STORE_SKILL_101"),
            ("I_STORE_EXIT", "I_UI_CONFIRM"),
            ("I_STORE_EXIT",),
            ("I_IMITATE",),
            ("I_IMITATE_1",),
            ("I_IMITATE_SUCCESS",),
            ("I_COIN_RIGHT_TOP", "I_BACK_EXIT"),
            (),  # O_ISLAND_NAME -> 鏖战 (l104)
            ("I_NPC_FIRE",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_COIN",),
            ("I_BOSS_SHARE",),
            ("I_BOSS_SHUTU",),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        initial_vars={"sr_phase": "inside"},
        ocr_int={0: 450},
        ocr_full={7: "鏖战之屿"},
    )
    assert res_sr_isl.status == "success", res_sr_isl.summary()
    assert res_sr_isl.variables["sr_store_buys"] == 1
    assert res_sr_isl.variables["sr_soft_wind_level"] == 3
    assert res_sr_isl.variables["sr_island_kind"] == "l104"
    assert res_sr_isl.variables["sr_wins"] == 1 and res_sr_isl.variables["sr_runs"] == 1


def test_hyakkiyakou_and_auto_checkin_big_god(oas_stage):
    stage, src, folder = oas_stage
    hya = compile_hyakkiyakou_candidate(src, folder)
    res_ticket, dev = _run(hya, stage / "resources", [()])
    assert res_ticket.status == "failed" and "hya_confirm_tickets" in res_ticket.reason
    assert dev.inputs == []

    res_hya_deny, dev_hya_deny = _run(
        hya, stage / "resources", [("I_HACCESS",)],
        params={"hya_limit_count": 1, "hya_confirm_tickets": True},
        initial_vars={"hya_phase": "lobby"},
        confirm=lambda _c, _d: False,
    )
    assert res_hya_deny.status == "failed" and res_hya_deny.failure_kind == "confirm_denied"
    assert dev_hya_deny.inputs == []

    hya_asks = []
    res_hya, _ = _run(
        hya, stage / "resources",
        [("I_HACCESS",), ("I_HTITLE",), ("I_HSTART",), ("I_HEND",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"hya_limit_count": 1, "hya_confirm_tickets": True},
        initial_vars={"hya_phase": "lobby"},
        confirm=lambda c, _d: (hya_asks.append(c) or True),
    )
    assert res_hya.status == "success", res_hya.summary()
    assert res_hya.variables["hya_runs"] == 1 and hya_asks == ["购买"]

    res_hya_sched, _ = _run(
        hya, stage / "resources", [("I_HCLOSE_RED",), ("I_CHECK_MAIN",)],
        params={"hya_limit_count": 1, "hya_confirm_tickets": True, "hya_limit_seconds": 0, "hya_next_delay_s": 43200},
        initial_vars={"hya_phase": "lobby"},
    )
    assert res_hya_sched.status == "success" and res_hya_sched.variables["hya_exit_reason"] == "time_limit"
    assert res_hya_sched.oas_target is not None and res_hya_sched.oas_target[0] == 43200

    # Hyakkiyakou friend invite + boss slot 3 + freeze + red close + time limit
    hya_asks_2 = []
    res_hya_inv, _ = _run(
        hya, stage / "resources",
        [
            ("I_HINVITE",),
            ("I_HINVITE", "I_ENSURE_RECALL"),
            ("I_HACCESS",),
            ("I_HTITLE",),
            ("I_HSTART",),
            ("I_HFREEZE",),
            ("I_HEND",),
            ("I_HCLOSE_RED",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "hya_limit_count": 1, "hya_confirm_tickets": True,
            "hya_invite_friend": True, "hya_friend_slot": 3,
            "hya_boss_slot": 3, "hya_freeze_enabled": True,
        },
        initial_vars={"hya_phase": "lobby"},
        confirm=lambda c, _d: (hya_asks_2.append(c) or True),
    )
    assert res_hya_inv.status == "success", res_hya_inv.summary()
    assert res_hya_inv.variables["hya_runs"] == 1 and hya_asks_2 == ["购买"]

    res_hya_tl, _ = _run(
        hya, stage / "resources", [("I_HCLOSE_RED",), ("I_CHECK_MAIN",)],
        params={"hya_limit_count": 5, "hya_limit_seconds": 0, "hya_confirm_tickets": True},
        initial_vars={"hya_phase": "lobby"},
    )
    assert res_hya_tl.status == "success" and res_hya_tl.variables["hya_exit_reason"] == "time_limit"

    # Verified boss-bet selection (I_HSELECTED) before I_HSTART even when both I_HTITLE and I_HSTART appear together
    hya_asks_3 = []
    res_hya_sel, _ = _run(
        hya, stage / "resources",
        [
            ("I_HACCESS",),
            ("I_HTITLE", "I_HSTART"),
            ("I_HTITLE", "I_HSELECTED", "I_HSTART"),
            ("I_HFREEZE",),
            ("I_HEND",),
            ("I_HCLOSE_RED",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "hya_limit_count": 1, "hya_confirm_tickets": True,
            "hya_boss_slot": 2, "hya_require_boss_selected": True, "hya_freeze_enabled": True,
        },
        initial_vars={"hya_phase": "lobby"},
        confirm=lambda c, _d: (hya_asks_3.append(c) or True),
    )
    assert res_hya_sel.status == "success", res_hya_sel.summary()
    assert res_hya_sel.variables["hya_boss_selected_count"] == 1
    assert res_hya_sel.variables["hya_freezes_used"] == 1 and hya_asks_3 == ["购买"]

    bg = compile_auto_checkin_big_god_candidate(src, folder)
    res_blk, dev = _run(bg, stage / "resources", [()], params={"bg_enable_external_checkin": True})
    assert res_blk.status == "failed" and "frida-server" in res_blk.reason
    assert dev.inputs == []

    res_safe, _ = _run(bg, stage / "resources", [()])
    assert res_safe.status == "success" and res_safe.oas_schedule == "AutoCheckinBigGod"
