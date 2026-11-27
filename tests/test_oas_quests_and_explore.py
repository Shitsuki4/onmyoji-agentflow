"""Offline unit tests for OAS WantedQuests, BondlingFairyland, Dokan, and Exploration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_quests_and_explore import (
    compile_bondling_fairyland_candidate,
    compile_dokan_candidate,
    compile_exploration_candidate,
    compile_wanted_quests_candidate,
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
    for task in ("WantedQuests", "BondlingFairyland", "Dokan", "Exploration", "RichMan",
                 "Component_GeneralBuff", "Component_SwitchSoul", "Component_GeneralRoom", "Component_GeneralInvite",
                 "Component_ReplaceShikigami"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, full_ocr_reader=None, ocr_single=None, confirm=None):
    wf = load_workflow(raw, [root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, *_a, **_kw):
        vis = frames[int(image[0, 0, 0]) - 20]
        hit = bool(set(vis) & aliases.get(Path(path).resolve(), set()))
        return hit, float(hit), (200, 120, 40, 32)

    def read_single(image, region, score=0.6):
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, initial_vars=initial_vars,
            full_ocr_reader=full_ocr_reader, single_ocr_reader=read_single, confirm=confirm,
        ).run()
    return res, device


def test_wanted_quests_and_bondling_fairyland(oas_stage):
    stage, src, folder = oas_stage
    wq = compile_wanted_quests_candidate(src, folder)
    res_gate, dev = _run(wq, stage / "resources", [()], params={"wq_cooperation_only": True})
    assert res_gate.status == "failed" and "wq_confirm_invite" in res_gate.reason
    assert dev.inputs == []

    res_wq, _ = _run(
        wq, stage / "resources",
        [("I_WQ_BOX",), ("I_WQC_FIRE",), ("I_BATTLE_INFO", "I_WIN"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"wq_max_battles": 1},
        initial_vars={"wq_phase": "board"},
    )
    assert res_wq.status == "success", res_wq.summary()
    assert res_wq.variables["wq_wins"] == 1 and res_wq.variables["wq_rewards"] == 1

    # Pre-work trace + exploration list scroll + optional Secret oas_wake
    res_wq_pre, _ = _run(
        wq, stage / "resources",
        [
            ("I_CHECK_MAIN", "I_WQ_SEAL"),
            ("I_TRACE_ENABLE",),
            ("I_TRACE_DISABLE", "I_UI_BACK_RED"),
            ("I_CHECK_MAIN", "I_MAIN_GOTO_EXPLORATION"),
            ("I_CHECK_EXPLORATION",),
            ("I_CHECK_EXPLORATION",),
            ("I_CHECK_EXPLORATION",),
            ("I_CHECK_EXPLORATION", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MAIN",),
        ],
        params={"wq_run_pre_work": True, "wq_wake_secret": True},
        initial_vars={"wq_phase": "pre_work"},
    )
    assert res_wq_pre.status == "success", res_wq_pre.summary()
    assert res_wq_pre.variables["wq_pre_traced"] is True and res_wq_pre.variables["wq_list_swipes"] == 3
    assert res_wq_pre.variables["wq_secret_woken"] is True and list(res_wq_pre.oas_wakes) == ["Secret"]

    # Guarded cooperation invite flow (requires both wq_cooperation_only and wq_confirm_invite)
    res_wq_coop, _ = _run(
        wq, stage / "resources",
        [
            ("I_CHECK_MAIN", "I_WQ_SEAL"),
            ("I_WQ_INVITE_1",),
            ("I_WQ_INVITE_DIFF_SVR",),
            ("I_WQ_INVITE_DIFF_SVR_HIGHLIGHT", "I_WQ_INVITE_FRIEND_LIST_APPEAR", "I_WQ_FRIEND_1"),
            ("I_WQ_INVITE_SELECTED", "I_WQ_INVITE_ENSURE"),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "wq_cooperation_only": True, "wq_confirm_invite": True,
            "wq_coop_cross_server": True, "wq_coop_max_invites": 1,
        },
        initial_vars={"wq_phase": "dispatch_pre"},
    )
    assert res_wq_coop.status == "success", res_wq_coop.summary()
    assert res_wq_coop.variables["wq_coop_invites"] == 1

    res_wq_tl, _ = _run(
        wq, stage / "resources",
        [("I_CHECK_EXPLORATION",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"wq_limit_seconds": 1, "wq_next_delay_s": 14400},
        initial_vars={"wq_phase": "board"},
    )
    assert res_wq_tl.status == "success", res_wq_tl.summary()
    assert res_wq_tl.variables["wq_exit_reason"] == "time_limit"
    assert res_wq_tl.oas_target is not None and res_wq_tl.oas_target[0] == 14400

    bf = compile_bondling_fairyland_candidate(src, folder)
    res_buy, dev = _run(bf, stage / "resources", [()], params={"bf_confirm_buy_stone": True})
    assert res_buy.status == "failed" and "勾玉" in res_buy.reason
    assert dev.inputs == []

    res_bf, _ = _run(
        bf, stage / "resources",
        [("I_BF_SEARSH",), ("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_MAIN",)],
        params={"bf_limit_count": 1},
        initial_vars={"bf_phase": "loop"},
    )
    assert res_bf.status == "success", res_bf.summary()
    assert res_bf.variables["bf_wins"] == 1

    res_bf_lead, _ = _run(
        bf, stage / "resources",
        [
            ("I_BALL_HELP",), ("I_CREATE_TEAM",), ("I_GI_EMOJI_1", "I_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"), ("I_GI_EMOJI_1", "I_BACK_YELLOW"), ("I_UI_CONFIRM",), ("I_CHECK_MAIN",),
        ],
        params={"bf_user_status": "leader", "bf_limit_count": 1},
        initial_vars={"bf_phase": "loop"},
    )
    assert res_bf_lead.status == "success" and res_bf_lead.variables["bf_wins"] == 1, res_bf_lead.summary()

    # Mall bondling-memory pre-check cap exit
    res_bf_mem, _ = _run(
        bf, stage / "resources",
        [("I_MALL_SCCALES",), ("I_MALL_SCCALES_CHECK", "I_MALL_BONDLINGS_SURE"),
         ("I_MALL_BONDLINGS_ON", "I_CHECK_MAIN")],
        params={"bf_check_memory_enable": True, "bf_memory_limit": 500},
        initial_vars={"bf_phase": "mall_scales"},
        ocr_single={2: "600/1000"},
    )
    assert res_bf_mem.status == "success", res_bf_mem.summary()
    assert res_bf_mem.variables["bf_memory_count"] == 600 and res_bf_mem.variables["bf_memory_capped"] is True
    assert res_bf_mem.variables["bf_exit_reason"] == "memory_capped"

    # 5-slot bondling ball detection + capture settlement
    res_bf_cap, _ = _run(
        bf, stage / "resources",
        [("I_BF_LOCAL_2_SNOWBALL",), ("I_BALL_FIRE",), ("I_BATTLE_SUCCESS",),
         ("I_CAP_SUCCESS",), ("I_CHECK_MAIN",)],
        params={"bf_mode": "catch", "bf_ball_scan_enable": True, "bf_limit_count": 1},
        initial_vars={"bf_phase": "loop"},
    )
    assert res_bf_cap.status == "success", res_bf_cap.summary()
    assert res_bf_cap.variables["bf_ball_selected"] == 2 and res_bf_cap.variables["bf_cap_wins"] == 1
    assert res_bf_cap.variables["bf_wins"] == 1

    # Area selection + capture plate setting + plate count zero exit
    res_bf_cfg, _ = _run(
        bf, stage / "resources",
        [
            ("I_BALL_AREA",),
            ("I_CHECK_AREA",),
            ("I_BALL_AREA", "I_CLICK_CAPTION"),
            ("I_CAPTION_ENSURE", "I_C_AUTO_FALSE"),
            ("I_CAPTION_ENSURE", "I_C_MINIMAL_MODE_DISABLE"),
            ("I_CAPTION_ENSURE", "I_C_MIDUM_FALSE"),
            ("I_CAPTION_ENSURE", "I_C_CONTINUOUS_ENABLE"),
            ("I_CAPTION_ENSURE", "I_C_FIRST_ENABLE"),
            ("I_CAPTION_ENSURE",),
            ("I_BALL_FIRE", "I_CHECK_MAIN"),
        ],
        params={
            "bf_mode": "catch",
            "bf_area_select": "area2",
            "bf_config_catch_plates": True,
            "bf_catch_plate_tier": "medium",
            "bf_check_plate_count": True,
            "bf_limit_count": 1,
            "bf_next_delay_s": 21600,
        },
        initial_vars={"bf_phase": "loop"},
        ocr_single={9: "0/50"},
    )
    assert res_bf_cfg.status == "success", res_bf_cfg.summary()
    assert res_bf_cfg.variables["bf_area_selected"] is True
    assert res_bf_cfg.variables["bf_capture_configured"] is True
    assert res_bf_cfg.variables["bf_plate_count"] == 0
    assert res_bf_cfg.variables["bf_exit_reason"] == "no_plate_number"
    assert res_bf_cfg.oas_target is not None and res_bf_cfg.oas_target[0] == 21600

    # Guarded stone purchase: confirm_denied stops before spending; confirm=True completes
    res_stone_deny, dev_deny = _run(
        bf, stage / "resources",
        [("I_STONE_ENTER",), ("I_BUY_PLUS",), ("I_STONE_SURE",)],
        params={"bf_confirm_buy_stone": True, "bf_confirm_stone_spend": True, "bf_stone_buy_clicks": 1},
        initial_vars={"bf_phase": "loop"},
        confirm=lambda _c, _d: False,
    )
    assert res_stone_deny.status == "failed" and res_stone_deny.failure_kind == "confirm_denied"
    assert len(dev_deny.inputs) == 2

    asks = []
    res_stone_ok, _ = _run(
        bf, stage / "resources",
        [("I_STONE_ENTER",), ("I_BUY_PLUS",), ("I_STONE_SURE",), ("I_STONE_CLOSE",),
         ("I_BF_SEARSH",), ("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_MAIN",)],
        params={"bf_confirm_buy_stone": True, "bf_confirm_stone_spend": True, "bf_stone_buy_clicks": 1, "bf_limit_count": 1},
        initial_vars={"bf_phase": "loop"},
        confirm=lambda cat, _d: (asks.append(cat) or True),
    )
    assert res_stone_ok.status == "success", res_stone_ok.summary()
    assert res_stone_ok.variables["bf_stone_bought"] is True and asks == ["花勾玉"]
    assert res_stone_ok.variables["bf_wins"] == 1

    # O_B_BALL_NUMBER 0/99 exits cleanly in alone catch & leader catch; I_UI_CONFIRM popup after I_BALL_HELP is dismissed
    res_ball_zero, dev_ball_zero = _run(
        bf, stage / "resources", [("I_BALL_FIRE", "I_CHECK_MAIN")],
        params={"bf_mode": "catch", "bf_check_ball_count": True, "bf_limit_count": 5},
        initial_vars={"bf_phase": "loop"},
        ocr_single={0: "0/99"},
    )
    assert res_ball_zero.status == "success" and res_ball_zero.variables["bf_ball_count"] == 0
    assert res_ball_zero.variables["bf_exit_reason"] == "no_ball_number" and dev_ball_zero.inputs == []

    res_lead_popup, _ = _run(
        bf, stage / "resources",
        [
            ("I_BALL_HELP",),
            ("I_UI_CONFIRM",),
            ("I_CREATE_TEAM",),
            ("I_GI_EMOJI_1", "I_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_GI_EMOJI_1", "I_BACK_YELLOW"),
            ("I_UI_CONFIRM",),
            ("I_CHECK_MAIN",),
        ],
        params={"bf_mode": "catch", "bf_user_status": "leader", "bf_check_ball_count": True, "bf_limit_count": 1},
        initial_vars={"bf_phase": "loop"},
        ocr_single={0: "12/99"},
    )
    assert res_lead_popup.status == "success" and res_lead_popup.variables["bf_wins"] == 1
    assert res_lead_popup.variables["bf_ball_count"] == 12

    # O_B_STONE_NUMBER 0/30 closes stone modal without prompting spend or clicking I_STONE_SURE
    res_stone_zero, dev_stone_zero = _run(
        bf, stage / "resources",
        [("I_STONE_ENTER",), ("I_STONE_SURE", "I_BUY_PLUS", "I_STONE_CLOSE"),
         ("I_BF_SEARSH",), ("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_MAIN",)],
        params={
            "bf_confirm_buy_stone": True, "bf_confirm_stone_spend": True,
            "bf_check_stone_count": True, "bf_limit_count": 1,
        },
        initial_vars={"bf_phase": "loop"},
        ocr_single={1: "0/30"},
        confirm=lambda _c, _d: pytest.fail("0 stones must never prompt sensitive spend"),
    )
    assert res_stone_zero.status == "success" and res_stone_zero.variables["bf_stone_bought"] is False
    assert res_stone_zero.variables["bf_stone_exhausted"] is True and res_stone_zero.variables["bf_stone_count"] == 0


def test_exploration_scrolls_and_time_limit(oas_stage):
    stage, source, resources = oas_stage
    raw = compile_exploration_candidate(source, resources)
    root = stage / "resources"
    chapter = ("I_E_EXPLORATION_CLICK", "I_EXP_CREATE_TEAM", "I_UI_BACK_YELLOW")
    home = ("I_CHECK_MAIN",)
    params = {"exp_scrolls_mode": True, "exp_scrolls_exploration_failure_seconds": 600}
    result, device = _run(raw, root, [chapter, home], params=params,
                          initial_vars={"exp_phase": "chapter_verify"}, ocr_single={0: "25/30"})
    assert result.status == "success", result.summary()
    assert result.variables["exp_exit_reason"] == "scrolls_ticket_threshold"
    assert result.oas_schedule == "Exploration" and result.oas_target[0] == 600
    assert set(result.oas_wakes) == {"RealmRaid", "MemoryScrolls"}
    assert result.oas_wakes["MemoryScrolls"][2]["oas_server_update_seconds"] == 32400
    assert len(device.inputs) == 1

    for value in ("24/30", "25/", "31/30"):
        staged = {**raw, "stop_when": "exp_phase == 'chapter_opening'"}
        result, device = _run(
            staged, root, [chapter, ()], params=params, initial_vars={"exp_phase": "chapter_verify"},
            ocr_single={0: value},
        )
        assert result.status == "failed" and not result.oas_wakes and not device.inputs

    result, device = _run(raw, root, [chapter, home], params={**params, "exp_limit_seconds": 0},
                          initial_vars={"exp_phase": "chapter_verify"}, ocr_single={0: "30/30"})
    assert result.status == "success" and result.variables["exp_exit_reason"] == "time_limit_reached"
    assert not result.oas_wakes and len(device.inputs) == 1


def test_dokan_and_exploration(oas_stage):
    stage, src, folder = oas_stage
    dk = compile_dokan_candidate(src, folder)
    res_admin, dev = _run(dk, stage / "resources", [()], params={"dk_try_start_dokan": True})
    assert res_admin.status == "failed" and "dk_confirm_start_dokan" in res_admin.reason
    assert dev.inputs == []

    res_dk, _ = _run(
        dk, stage / "resources",
        [("I_RYOU_DOKAN_START_CHALLENGE",), ("I_BATTLE_INFO", "I_WIN"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"dk_max_battles": 1},
        initial_vars={"dk_phase": "loop"},
    )
    assert res_dk.status == "success", res_dk.summary()
    assert res_dk.variables["dk_wins"] == 1

    # DokanScene dispatch: GATHERING priority pick -> MASTER_BATTLING (limit 1) -> exit
    res_dk_scene, _ = _run(
        dk, stage / "resources",
        [
            ("I_RYOU_DOKAN_GATHERING", "I_RYOU_DOKAN_ATTACK_PRIORITY"),
            ("I_RYOU_DOKAN_ATTACK_PRIORITY_2",),
            ("I_RYOU_DOKAN_MASTER_BATTLE", "I_RYOU_DOKAN_START_CHALLENGE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_RYOU_DOKAN_MASTER_BATTLE", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MAIN",),
        ],
        params={"dk_attack_priority": 2, "dk_master_limit": 1, "dk_max_battles": 5},
        initial_vars={"dk_phase": "loop"},
    )
    assert res_dk_scene.status == "success", res_dk_scene.summary()
    assert res_dk_scene.variables["dk_priority_selected"] is True
    assert res_dk_scene.variables["dk_master_battles"] == 1
    assert res_dk_scene.variables["dk_exit_reason"] == "master_limit_reached"

    # Dokan guarded abandon gate & master 1st/2nd battle stages + abandon
    res_ab_gate, dev_ab = _run(dk, stage / "resources", [()], params={"dk_abandon_after_master": True})
    assert res_ab_gate.status == "failed" and "dk_confirm_abandon" in res_ab_gate.reason
    assert dev_ab.inputs == []

    res_dk_m2, _ = _run(
        dk, stage / "resources",
        [
            ("I_RYOU_DOKAN_BATTLE_MASTER_FIRST",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_RYOU_DOKAN_BATTLE_MASTER_SECOND",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_DOKAN_ABANDONED_TOPPA",),
            ("I_DOKAN_ABANDONED_TOPPA_ENSURE",),
            ("I_CHECK_MAIN",),
        ],
        params={"dk_master_limit": 2, "dk_abandon_after_master": True, "dk_confirm_abandon": True},
        initial_vars={"dk_phase": "loop"},
    )
    assert res_dk_m2.status == "success", res_dk_m2.summary()
    assert res_dk_m2.variables["dk_master_stage"] == 2 and res_dk_m2.variables["dk_master_battles"] == 2
    assert res_dk_m2.variables["dk_abandoned"] is True and res_dk_m2.variables["dk_exit_reason"] == "dokan_abandoned"

    # Dokan guarded admin create (sensitive confirm denied + approved create + vote keep_bounty)
    res_dk_deny, dev_dk_deny = _run(
        dk, stage / "resources", [("I_RYOU_DOKAN_CREATE_DOKAN_ENSURE",)],
        params={"dk_try_start_dokan": True, "dk_confirm_start_dokan": True},
        initial_vars={"dk_phase": "loop"},
        confirm=lambda _c, _d: False,
    )
    assert res_dk_deny.status == "failed" and res_dk_deny.failure_kind == "confirm_denied"
    assert dev_dk_deny.inputs == []

    dk_asks = []
    res_dk_cr, _ = _run(
        dk, stage / "resources",
        [
            ("I_RYOU_DOKAN_CREATE_DOKAN",),
            ("I_RYOU_DOKAN_CREATE_DOKAN_ENSURE",),
            ("I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY",),
            ("I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MAIN",),
        ],
        params={"dk_try_start_dokan": True, "dk_confirm_start_dokan": True, "dk_vote_mode": "keep_bounty"},
        initial_vars={"dk_phase": "loop"},
        confirm=lambda c, _d: (dk_asks.append(c) or True),
    )
    assert res_dk_cr.status == "success", res_dk_cr.summary()
    assert dk_asks == ["购买"] and res_dk_cr.variables["dk_created"] is True
    assert res_dk_cr.variables["dk_exit_reason"] == "no_remain_count"

    # Dokan closed-day schedule target + cheering click
    res_dk_closed, _ = _run(
        dk, stage / "resources",
        [("I_CHECK_MAIN",)],
        params={"dk_is_open_day": False, "dk_next_open_delay_s": 86400},
    )
    assert res_dk_closed.status == "success", res_dk_closed.summary()
    assert res_dk_closed.variables["dk_exit_reason"] == "closed_day"
    assert res_dk_closed.variables["dk_target_delay_s"] == 86400

    res_dk_cheer, _ = _run(
        dk, stage / "resources",
        [
            ("I_RYOU_DOKAN_CHEERING_ATTACKING_SAMA",),
            ("I_RYOU_DOKAN_CHEERING",),
            ("I_RYOU_DOKAN_ABANDONED_TOPPA_CONTINUE",),
            ("I_RYOU_DOKAN_SPOILS_OF_DOKAN",),
            ("I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE", "I_RYOU_DOKAN_DOKAN_QUIT"),
            ("I_CHECK_MAIN",),
        ],
        params={"dk_cheering_enable": True, "dk_abandon_vote_mode": "continue"},
        initial_vars={"dk_phase": "loop"},
    )
    assert res_dk_cheer.status == "success", res_dk_cheer.summary()
    assert res_dk_cheer.variables["dk_cheers"] == 2
    assert res_dk_cheer.variables["dk_exit_reason"] == "no_remain_count"

    # Dokan in-battle ExtendGreenMark + master vs normal preset tracking
    res_dk_gm, _ = _run(
        dk, stage / "resources",
        [
            ("I_RYOU_DOKAN_IN_FIELD",),
            ("I_RYOU_DOKAN_FIGHTING",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_RYOU_DOKAN_BATTLE_MASTER_FIRST",),
            ("I_RYOU_DOKAN_FIGHTING",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "dk_green_enable": True, "dk_green_mark": "left3",
            "dk_preset_group_1": 2, "dk_preset_team_1": 1,
            "dk_preset_group_2": 4, "dk_preset_team_2": 3,
            "dk_max_battles": 2, "dk_master_limit": 1,
        },
        initial_vars={"dk_phase": "loop"},
    )
    assert res_dk_gm.status == "success", res_dk_gm.summary()
    assert res_dk_gm.variables["dk_green_marks"] == 2
    assert res_dk_gm.variables["dk_active_preset_group"] == 4 and res_dk_gm.variables["dk_active_preset_team"] == 3
    assert res_dk_gm.variables["dk_wins"] == 2

    exp = compile_exploration_candidate(src, folder)
    res_rr, _ = _run(
        exp, stage / "resources",
        [("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"exp_check_realm_raid": True},
        initial_vars={"exp_phase": "enter_chapter"},
        ocr_single={0: "30/30"},
    )
    assert res_rr.status == "success", res_rr.summary()
    assert res_rr.variables["exp_rr_woken"] is True
    assert res_rr.variables["exp_exit_reason"] == "realm_raid_tickets_full"

    res_exp, _ = _run(
        exp, stage / "resources",
        [("I_BOSS_BATTLE_BUTTON",), ("I_BATTLE_INFO", "I_WIN"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"exp_limit_count": 1},
        initial_vars={"exp_phase": "inside"},
    )
    assert res_exp.status == "success", res_exp.summary()
    assert res_exp.variables["exp_wins"] == 1

    def read_row(image, _roi, keyword, *_args):
        assert "金币" in keyword or "经验" in keyword
        index = int(image[0, 0, 0]) - 20
        return FullOcrArea((440, 140 + 20 * (index - 1), 180, 15), keyword_complete=True)

    courtyard = ("I_CHECK_MAIN", "I_BUFF_1")
    panel = ("I_CLOUD", "I_BUFF_1", "I_AWAKE")
    res_open, dev_open = _run(
        {**exp, "stop_when": "exp_phase == 'navigate'"},
        stage / "resources",
        [courtyard, (*panel, "I_CLOSE_RED"), (*panel, "I_OPEN_YELLOW"), courtyard],
        params={"exp_buff_enable": True, "exp_buff_exp_100": True},
        full_ocr_reader=read_row,
    )
    assert res_open.status == "success" and len(dev_open.inputs) == 3
    assert res_open.variables["exp_buff_before_select_1_helper_status"] == "observed"

    res_close, dev_close = _run(
        exp, stage / "resources",
        [courtyard, (*panel, "I_OPEN_YELLOW"), (*panel, "I_CLOSE_RED"), courtyard],
        params={"exp_buff_enable": True, "exp_buff_exp_100": True},
        initial_vars={"exp_phase": "buff_after"},
        full_ocr_reader=read_row,
    )
    assert res_close.status == "success" and res_close.oas_schedule == "Exploration"
    assert len(dev_close.inputs) == 3 and res_close.variables["exp_buff_after_select_1_helper_status"] == "observed"
