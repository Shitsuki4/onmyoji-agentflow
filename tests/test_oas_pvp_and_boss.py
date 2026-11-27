"""Offline unit tests for OAS Duel, RyouToppa, RealmRaid, and AreaBoss."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_pvp_and_boss import (
    compile_area_boss_candidate,
    compile_duel_candidate,
    compile_realm_raid_candidate,
    compile_ryou_toppa_candidate,
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
    for task in ("Duel", "RyouToppa", "RealmRaid", "AreaBoss", "Component_SwitchSoul", "Component_SwitchOnmyoji"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_int=None, ocr_single=None,
         text_reader=None, full_ocr_reader=None, confirm=None):
    wf = load_workflow(raw, [root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, *_a, **_kw):
        vis = frames[int(image[0, 0, 0]) - 20]
        hit = bool(set(vis) & aliases.get(Path(path).resolve(), set()))
        return hit, float(hit), (200, 120, 40, 32)

    def read_int(image, region):
        return (ocr_int or {}).get(int(image[0, 0, 0]) - 20, 0)

    def read_single(image, region, score=0.6):
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, ocr_reader=read_int, single_ocr_reader=read_single,
            text_reader=text_reader, full_ocr_reader=full_ocr_reader, confirm=confirm,
            initial_vars=initial_vars,
        ).run()
    return res, device


def test_duel_battle_and_score_exit(oas_stage):
    stage, src, folder = oas_stage
    du = compile_duel_candidate(src, folder)
    res_win, _ = _run(
        du, stage / "resources",
        [
            ("I_D_BATTLE",), ("I_D_PREPARE",), ("I_D_VICTORY",), ("I_D_VICTORY",),
            ("I_CHECK_DUEL", "I_D_HELP", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",),
        ],
        params={"du_max_battles": 1},
        initial_vars={"du_phase": "duel_main"},
        ocr_single={0: "1500/2000", 4: "2100/2400"},
    )
    assert res_win.status == "success", res_win.summary()
    assert res_win.oas_schedule == "Duel" and res_win.variables["du_wins"] == 1
    assert res_win.variables["du_talisman_woken"] is True

    res_score, score_device = _run(
        du, stage / "resources",
        [("I_D_BATTLE", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"du_target_score": 1000},
        initial_vars={"du_phase": "duel_main"},
        ocr_single={0: "1000/1200"},
    )
    assert res_score.status == "success" and res_score.variables["du_exit_reason"] == "target_score"
    assert res_score.variables["du_score"] == 1000 and res_score.variables["du_battles"] == 0
    assert len(score_device.inputs) == 1

    res_honor, _ = _run(
        du, stage / "resources",
        [("I_DUEL_HONOR", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"du_honor_full_exit": True},
        initial_vars={"du_phase": "duel_main"},
        ocr_single={0: "2400/2400"},
    )
    assert res_honor.status == "success" and res_honor.variables["du_exit_reason"] == "honor_full"
    assert res_honor.variables["du_talisman_woken"] is True

    # Component_SwitchOnmyoji: switch to michinaga (hero tab) then resume navigate
    res_so, dev_so = _run(
        {**du, "stop_when": "du_phase == 'navigate'"},
        stage / "resources",
        [
            ("I_ONMYOJI_CHECK",),
            ("I_HERO_CHECK", "I_ONMYOJI_SWITCH"),
            ("I_YORIMITSU_BATTLE",),
            ("I_MICHINAGA_BATTLE", "I_UI_BACK_BLUE"),
            ("I_HERO_CHECK",),
        ],
        params={"du_switch_onmyoji": True, "du_onmyoji": "michinaga"},
        initial_vars={"du_phase": "onmyoji_tab"},
    )
    assert res_so.status == "success" and res_so.variables["du_onmyoji_switched"] is True
    assert len(dev_so.inputs) == 4

    # Celebrity ban OCR mismatch -> duel_exit_battle -> settle loss -> exit
    res_ban, _ = _run(
        du, stage / "resources",
        [
            ("I_BAN",),
            ("I_DUEL_EXIT",),
            ("I_UI_CONFIRM",),
            ("I_D_FAIL",),
            ("I_CHECK_DUEL", "I_D_HELP", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MAIN",),
        ],
        params={"du_celeb_battle": True, "du_ban_name": "不知火", "du_max_battles": 1},
        initial_vars={"du_phase": "prepare", "du_battles": 1},
        ocr_single={1: "须佐之男"},
        text_reader=lambda img, _roi: [("须佐之男", 120, 105)] if int(img[0, 0, 0]) - 20 == 1 else [],
    )
    assert res_ban.status == "success", res_ban.summary()
    assert res_ban.variables["du_is_celeb"] is True and res_ban.variables["du_ban_exits"] == 1
    assert res_ban.variables["du_losses"] == 1

    res_du_out, _ = _run(
        du, stage / "resources", [()],
        params={"du_in_window": False, "du_next_window_delay_s": 3600},
    )
    assert res_du_out.status == "success" and res_du_out.variables["du_exit_reason"] == "outside_window"
    assert res_du_out.oas_target is not None and res_du_out.oas_target[0] == 3600

    # Celebrity score +100 tracking + in-battle green mark after auto-battle OCR
    res_celeb_gm, _ = _run(
        du, stage / "resources",
        [
            ("I_D_CELEB_STAR", "I_D_BATTLE"),
            ("I_D_PREPARE",),
            (),  # O_D_AUTO -> triggers green mark left_3
            ("I_D_VICTORY",),
            ("I_CHECK_DUEL", "I_D_HELP", "I_D_CELEB_STAR", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MAIN",),
        ],
        params={
            "du_celeb_battle": True, "du_initial_score": 3000, "du_target_score": 3100,
            "du_green_enable": True, "du_green_mark": "left_3", "du_max_battles": 5,
        },
        initial_vars={"du_phase": "duel_main"},
        full_ocr_reader=lambda img, _r, kw, *_a, **_kw: (
            (35, 645, 50, 30) if int(img[0, 0, 0]) - 20 == 2 and kw == "自动" else (0, 0, 0, 0)
        ),
    )
    assert res_celeb_gm.status == "success", res_celeb_gm.summary()
    assert res_celeb_gm.variables["du_is_celeb"] is True
    assert res_celeb_gm.variables["du_green_marks"] == 1
    assert res_celeb_gm.variables["du_celeb_score"] == 3100
    assert res_celeb_gm.variables["du_exit_reason"] == "celeb_target_score"


def test_ryou_toppa_and_realm_raid_flows(oas_stage):
    stage, src, folder = oas_stage
    rt = compile_ryou_toppa_candidate(src, folder)
    res_rt, _ = _run(
        rt, stage / "resources",
        [
            ("I_TOPPA_RECORD",), ("I_FIRE",), ("I_BATTLE_INFO", "I_WIN"),
            ("I_TOPPA_RECORD", "I_BACK_RED"), ("I_CHECK_MAIN",),
        ],
        params={"rt_limit_count": 1, "rt_unlimited_hours": True},
        initial_vars={"rt_phase": "cycle"},
    )
    assert res_rt.status == "success", res_rt.summary()
    assert res_rt.oas_schedule == "RyouToppa" and res_rt.variables["rt_wins"] == 1

    all_failed = ("I_TOPPA_RECORD", *(f"I_AREA_{i}_IS_FAILURE" for i in range(1, 9)))
    res_rt_flush, _ = _run(
        rt, stage / "resources",
        [all_failed, (*all_failed, "I_BACK_RED"), ("I_CHECK_MAIN",)],
        params={"rt_max_flushes": 1, "rt_unlimited_hours": True},
        initial_vars={"rt_phase": "cycle"},
    )
    assert res_rt_flush.status == "success", res_rt_flush.summary()
    assert res_rt_flush.variables["rt_flushes"] == 1
    assert res_rt_flush.variables["rt_exit_reason"] == "areas_exhausted"

    res_rt_fin, _ = _run(
        rt, stage / "resources",
        [("I_TOPPA_RECORD", "I_AREA_1_FINISHED", "I_BACK_RED"), ("I_CHECK_MAIN",)],
        params={"rt_tomorrow_delay_s": 43200, "rt_unlimited_hours": True},
        initial_vars={"rt_phase": "cycle"},
    )
    assert res_rt_fin.status == "success", res_rt_fin.summary()
    assert res_rt_fin.variables["rt_exit_reason"] == "all_finished"
    assert res_rt_fin.oas_target is not None and res_rt_fin.oas_target[0] == 43200

    # RyouToppa guild-admin start gate (fail closed without confirm + runtime sensitive denial + approved start + rt_next_delay_s)
    res_rt_gate, dev_rt_gate = _run(rt, stage / "resources", [()], params={"rt_ryou_access": True})
    assert res_rt_gate.status == "failed" and "rt_confirm_admin_start" in res_rt_gate.reason
    assert dev_rt_gate.inputs == []

    res_rt_deny, dev_rt_deny = _run(
        rt, stage / "resources", [("I_START_TOPPA_BUTTON",)],
        params={"rt_ryou_access": True, "rt_confirm_admin_start": True},
        initial_vars={"rt_phase": "admin_start"},
        confirm=lambda _c, _d: False,
    )
    assert res_rt_deny.status == "failed" and res_rt_deny.failure_kind == "confirm_denied"
    assert dev_rt_deny.inputs == []

    rt_asks = []
    res_rt_admin, _ = _run(
        rt, stage / "resources",
        [
            ("I_START_TOPPA_BUTTON",),
            ("I_RYOU_REWARD", "I_TOPPA_UNLOCK_TEAM", "I_TOPPA_RECORD", "I_BACK_RED"),
            ("I_CHECK_MAIN",),
        ],
        params={
            "rt_ryou_access": True, "rt_confirm_admin_start": True,
            "rt_limit_count": 0, "rt_next_delay_s": 7200, "lock_team_enable": False,
        },
        initial_vars={"rt_phase": "admin_start"},
        confirm=lambda c, _d: (rt_asks.append(c) or True),
    )
    assert res_rt_admin.status == "success", res_rt_admin.summary()
    assert rt_asks == ["购买"] and res_rt_admin.variables["rt_admin_started"] is True
    assert res_rt_admin.oas_target is not None and res_rt_admin.oas_target[0] == 7200

    rr = compile_realm_raid_candidate(src, folder)
    board = ("I_BACK_RED", "I_RR_PERSON")
    retreat_cycle = [board, ("I_FIRE",), ("I_EXIT",), ("I_UI_CONFIRM",), ("I_FALSE",)]
    res_e4, _ = _run(
        rr, stage / "resources",
        retreat_cycle * 4 + [board, ("I_FIRE",), ("I_BATTLE_INFO", "I_WIN"), board, ("I_CHECK_MAIN",)],
        params={"rr_exit_four": True, "rr_number_attack": 1, "rr_number_base": 10},
        initial_vars={"rr_phase": "cycle"},
        ocr_single={i: "10/30" for i in range(25)},
    )
    assert res_e4.status == "success", res_e4.summary()
    assert res_e4.variables["rr_retreats"] == 4 and res_e4.variables["rr_wins"] == 1

    res_rr, _ = _run(
        rr, stage / "resources",
        [board, ("I_FIRE",), ("I_BATTLE_INFO", "I_WIN"), board, ("I_CHECK_MAIN",)],
        params={"rr_number_attack": 1},
        initial_vars={"rr_phase": "cycle"},
        ocr_single={0: "30/30", 3: "29/30"},
    )
    assert res_rr.status == "success", res_rr.summary()
    assert res_rr.oas_schedule == "RealmRaid" and res_rr.variables["rr_wins"] == 1

    # Ranked medal mode: safe opt-in refresh when board has no matching ranked target
    rr_ranked = compile_realm_raid_candidate(src, folder, order_attack="5>4>3")
    res_rr_ref, _ = _run(
        rr_ranked, stage / "resources",
        [(*board, "I_FRESH"), ("I_UI_CONFIRM",), board, ("I_CHECK_MAIN",)],
        params={"rr_refresh_when_no_target": True, "rr_max_refreshes": 1},
        initial_vars={"rr_phase": "cycle"},
        ocr_single={0: "20/30", 2: "20/30"},
    )
    assert res_rr_ref.status == "success", res_rr_ref.summary()
    assert res_rr_ref.variables["rr_refreshes"] == 1
    assert res_rr_ref.variables["rr_exit_reason"] == "no_targets"

    # RealmRaid wall-clock time limit + target schedule
    res_rr_tl, _ = _run(
        rr, stage / "resources",
        [("I_SOUL_RAID",), board, ("I_CHECK_MAIN",)],
        params={"rr_limit_seconds": 1, "rr_next_delay_s": 14400},
        initial_vars={"rr_phase": "cycle"},
    )
    assert res_rr_tl.status == "success", res_rr_tl.summary()
    assert res_rr_tl.variables["rr_exit_reason"] == "time_limit"
    assert res_rr_tl.oas_target is not None and res_rr_tl.oas_target[0] == 14400


def test_area_boss_reputation_and_fight(oas_stage):
    stage, src, folder = oas_stage
    ab = compile_area_boss_candidate(src, folder)
    res, _ = _run(
        ab, stage / "resources",
        [
            ("I_AB_FILTER_OPENED",), ("I_BATTLE_1",), ("I_FIRE", "I_AB_CLOSE_RED"),
            ("I_BATTLE_INFO", "I_WIN"), ("I_AB_CLOSE_RED",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",),
        ],
        initial_vars={"ab_phase": "open_filter"},
        ocr_int={1: 1500},
    )
    assert res.status == "success", res.summary()
    assert res.oas_schedule == "AreaBoss" and res.variables["ab_fought"] == 1

    # Reward boss scan + ji_10 difficulty floor switch
    res_rew, _ = _run(
        ab, stage / "resources",
        [
            ("I_AB_FILTER_OPENED",),
            ("I_AB_FILTER_TITLE_REWARD",),
            ("I_AB_CLOSE_RED", "I_FIRE", "I_AB_DIFFICULTY_NORMAL"),
            ("I_AB_CLOSE_RED", "I_FIRE", "I_AB_DIFFICULTY_JI"),
            ("I_AB_CLOSE_RED", "I_FIRE", "I_AB_JI_FLOOR_LIST_CHECK", "I_AB_JI_FLOOR_TEN"),
            ("I_AB_CLOSE_RED", "I_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_AB_CLOSE_RED",),
            ("I_AB_FILTER_OPENED",),
            ("I_BATTLE_1", "I_UI_BACK_YELLOW"),
            ("I_CHECK_MAIN",),
        ],
        params={"ab_boss_reward": True, "ab_reward_floor": "ji_10"},
        initial_vars={"ab_phase": "dispatch_mode"},
        ocr_int={2: 25000, 9: 1500},
    )
    assert res_rew.status == "success", res_rew.summary()
    assert res_rew.variables["ab_reward_done"] is True
    assert res_rew.variables["ab_difficulty_set"] is True
    assert res_rew.variables["ab_fought"] == 1

    # Custom boss count override + close_detail reward dismissal + time limit exit
    res_cust, _ = _run(
        ab, stage / "resources",
        [
            ("I_BATTLE_1",), ("I_FIRE",), ("I_BATTLE_INFO", "I_WIN"),
            ("I_UI_REWARD",), ("I_AB_CLOSE_RED",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",),
        ],
        params={"ab_use_custom_count": True, "ab_boss_number": 1},
        initial_vars={"ab_phase": "read_rep"},
    )
    assert res_cust.status == "success", res_cust.summary()
    assert res_cust.variables["ab_target_count"] == 1 and res_cust.variables["ab_fought"] == 1

    res_ab_tl, _ = _run(
        ab, stage / "resources", [("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"ab_limit_seconds": 0, "ab_next_delay_s": 86400},
        initial_vars={"ab_phase": "pick_boss"},
    )
    assert res_ab_tl.status == "success" and res_ab_tl.variables["ab_exit_reason"] == "time_limit"
    assert res_ab_tl.oas_target is not None and res_ab_tl.oas_target[0] == 86400

    # 5-slot reward scan (bottom swipe slot 4) + O_AB_BOSS_NAME defeated-boss deduplication
    res_ab_dedup, _ = _run(
        ab, stage / "resources",
        [
            ("I_AB_FILTER_TITLE_REWARD",),
            ("I_AB_FILTER_TITLE_REWARD",),
            ("I_AB_CLOSE_RED", "I_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_AB_CLOSE_RED",),
            ("I_AB_FILTER_OPENED",),
            ("I_BATTLE_1",),
            ("I_AB_CLOSE_RED", "I_FIRE"),
            ("I_BATTLE_2",),
            ("I_AB_CLOSE_RED", "I_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_AB_CLOSE_RED",),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        params={"ab_boss_reward": True, "ab_dedup_reward_boss": True},
        initial_vars={"ab_phase": "reward_pick", "ab_reward_slot": 4, "ab_in_reward_phase": True},
        ocr_int={2: 25000, 6: 5000},
        text_reader=lambda img, _roi: [("以津真天" if int(img[0, 0, 0]) - 20 == 9 else "姑获鸟", 140, 50)],
    )
    assert res_ab_dedup.status == "success", res_ab_dedup.summary()
    assert res_ab_dedup.variables["ab_reward_swiped"] is True
    assert "姑获鸟" in res_ab_dedup.variables["ab_reward_boss_name"]
    assert res_ab_dedup.variables["ab_skipped_dups"] == 1
    assert res_ab_dedup.variables["ab_fought"] == 2 and res_ab_dedup.variables["ab_wins"] == 2
