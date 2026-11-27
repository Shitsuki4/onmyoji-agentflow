"""Offline unit tests for OAS BudokaiTournament, ActivityShikigami, FrogBoss, and DemonEncounter."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_climb_and_demon import (
    compile_activity_shikigami_candidate,
    compile_budokai_tournament_candidate,
    compile_demon_encounter_candidate,
    compile_frog_boss_candidate,
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
    for task in ("BudokaiTournament", "ActivityShikigami", "FrogBoss", "DemonEncounter",
                 "Component_SwitchSoul", "Component_Buy"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_int=None, ocr_single=None, confirm=None):
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
        if callable(ocr_int):
            return ocr_int(image, region)
        return (ocr_int or {}).get(int(image[0, 0, 0]) - 20, 0)

    def read_single(image, region, score=0.6):
        if callable(ocr_single):
            return ocr_single(image, region)
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, initial_vars=initial_vars, ocr_reader=read_int,
            single_ocr_reader=read_single, confirm=confirm,
        ).run()
    return res, device


def test_budokai_and_activity_shikigami(oas_stage):
    stage, src, folder = oas_stage
    bt = compile_budokai_tournament_candidate(src, folder)
    res_bt, _ = _run(
        bt, stage / "resources",
        [("I_LOCK", "I_IMG3"), ("I_BATTLE_INFO", "I_WIN"), ("I_BACK_GREEN",), ("I_CHECK_MAIN",)],
        params={"bt_limit_count": 1, "lock_team_enable": True},
        initial_vars={"bt_phase": "lock_check"},
    )
    assert res_bt.status == "success", res_bt.summary()
    assert res_bt.variables["bt_wins"] == 1

    # Reverse sequence (cultivation_drills -> daily_training) + I_UI_BACK_CIRCLE exit
    res_bt_rev, _ = _run(
        bt, stage / "resources",
        [
            ("I_IMG3",),
            ("I_UI_BACK_CIRCLE",),
            ("I_TO_BATTLE_MAIN",),
            ("I_LOCK", "I_IMG3"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_UI_BACK_CIRCLE",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "bt_mode": "both", "bt_run_drills_first": True,
            "bt_check_tickets_ocr": True, "bt_limit_count": 1,
        },
        initial_vars={"bt_phase": "fight_loop"},
        ocr_int={0: 0, 3: 5},
    )
    assert res_bt_rev.status == "success", res_bt_rev.summary()
    assert res_bt_rev.variables["bt_active_stage"] == "daily_training" and res_bt_rev.variables["bt_wins"] == 1

    # Multi-phase BudokaiTournament: daily_training AP empty -> cultivation_drills search & battle -> SoulsTidy wake
    def bt_ocr(image, region):
        idx = int(image[0, 0, 0]) - 20
        if region[0] == 777:  # O_REMAIN_AP
            return 0
        return 1 if idx < 5 else 0  # O_REMAIN_BOSS

    res_bt_seq, _ = _run(
        bt, stage / "resources",
        [
            ("I_UI_BACK_YELLOW",),
            ("I_TO_BATTLE_BOSS",),
            ("I_CHECK_BATTLE_BOSS", "I_IMG1"),
            ("I_IMG2",),
            ("I_IMG3",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_IMG3",),  # O_REMAIN_BOSS == 0 -> C_BOSS_DETAIL_CLOSE -> exit
            ("I_BACK_GREEN",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "bt_mode": "both", "bt_check_tickets_ocr": True, "bt_limit_count": 5,
            "bt_drills_limit": 2, "bt_active_souls_clean": True,
        },
        initial_vars={"bt_phase": "fight_loop"},
        ocr_int=bt_ocr,
    )
    assert res_bt_seq.status == "success", res_bt_seq.summary()
    assert res_bt_seq.variables["bt_scouts"] == 1 and res_bt_seq.variables["bt_wins"] == 1
    assert res_bt_seq.variables["bt_exit_reason"] == "boss_tickets_empty"
    assert res_bt_seq.variables["bt_souls_tidy_woken"] is True and list(res_bt_seq.oas_wakes) == ["SoulsTidy"]

    # Super-long battle timeout early retreat via I_EXIT -> I_UI_CONFIRM -> I_FALSE
    res_bt_to, _ = _run(
        bt, stage / "resources",
        [("I_EXIT",), ("I_UI_CONFIRM",), ("I_FALSE",), ("I_BACK_GREEN",), ("I_CHECK_MAIN",)],
        params={"bt_limit_count": 1, "bt_battle_timeout_s": 1},
        initial_vars={"bt_phase": "in_battle", "bt_battle_started_ms": 0},
    )
    assert res_bt_to.status == "success", res_bt_to.summary()
    assert res_bt_to.variables["bt_battle_timeouts"] == 1 and res_bt_to.variables["bt_battles"] == 1

    act = compile_activity_shikigami_candidate(src, folder)
    res_gate, dev = _run(act, stage / "resources", [()], params={"act_buy_ap": True})
    assert res_gate.status == "failed" and "勾玉" in res_gate.reason
    assert dev.inputs == []

    res_act, _ = _run(
        act, stage / "resources",
        [("I_PASS_13",), ("I_BATTLE_INFO", "I_WIN"), ("I_BACK_GREEN",), ("I_CHECK_MAIN",)],
        params={"act_limit_count": 1},
        initial_vars={"act_phase": "fight_loop"},
    )
    assert res_act.status == "success", res_act.summary()
    assert res_act.variables["act_wins"] == 1

    # ActivityShikigami AP100 depletion + guarded jade ticket purchase confirmation
    res_ap100, _ = _run(
        act, stage / "resources",
        [("I_BACK_GREEN",), ("I_CHECK_MAIN",)],
        params={"act_mode": "ap100", "act_check_resource_ocr": True},
        initial_vars={"act_phase": "fight_loop"},
        ocr_int={0: 0},
    )
    assert res_ap100.status == "success" and res_ap100.variables["act_exit_reason"] == "ap100_empty"

    res_buy_deny, dev_buy_deny = _run(
        act, stage / "resources", [("I_UI_CONFIRM",)],
        params={"act_buy_ap": True, "act_confirm_buy_ap": True, "act_buy_max_clicks": 1},
        initial_vars={"act_phase": "fight_loop"},
        ocr_single={0: "5/10"},
        confirm=lambda _c, _d: False,
    )
    assert res_buy_deny.status == "failed" and res_buy_deny.failure_kind == "confirm_denied"
    assert dev_buy_deny.inputs == []

    # Multi-phase sequence: pass depleted via OCR -> switch to ap -> ap battle -> switch to boss -> boss depleted exit
    def act_ocr(image, region):
        idx = int(image[0, 0, 0]) - 20
        if region[0] == 1153:  # O_REMAIN_PASS
            return 0
        if region[0] == 777:   # O_REMAIN_AP
            return 10 if idx < 3 else 0
        return 0  # O_REMAIN_BOSS

    res_seq, _ = _run(
        act, stage / "resources",
        [("I_CLIMB_MODE_PASS",), ("I_PASS_13",), ("I_BATTLE_INFO", "I_WIN"),
         ("I_UI_BACK_YELLOW",), ("I_TO_BATTLE_BOSS",), ("I_CHECK_BATTLE_BOSS", "I_BACK_GREEN"),
         ("I_CHECK_MAIN",)],
        params={
            "act_mode": "pass", "act_run_ap_after_pass": True, "act_run_boss_after_ap": True,
            "act_check_resource_ocr": True, "act_limit_count": 5, "act_ap_limit": 5, "act_boss_limit": 5,
            "act_active_souls_clean": True,
        },
        initial_vars={"act_phase": "fight_loop"},
        ocr_int=act_ocr,
    )
    assert res_seq.status == "success", res_seq.summary()
    assert res_seq.variables["act_wins"] == 1 and res_seq.variables["act_exit_reason"] == "boss_empty"
    assert res_seq.variables["act_souls_tidy_woken"] is True and list(res_seq.oas_wakes) == ["SoulsTidy"]

    res_act_time, _ = _run(
        act, stage / "resources", [("I_BACK_GREEN",), ("I_CHECK_MAIN",)],
        params={"act_limit_seconds": 0, "act_next_delay_s": 86400},
        initial_vars={"act_phase": "fight_loop"},
    )
    assert res_act_time.status == "success" and res_act_time.variables["act_exit_reason"] == "time_limit"
    assert res_act_time.oas_target is not None and res_act_time.oas_target[0] == 86400

    # Full ap -> ap100 -> boss sequence via I_UI_BACK_CIRCLE
    res_ap100_seq, _ = _run(
        act, stage / "resources",
        [
            ("I_PASS_13",), ("I_BATTLE_INFO", "I_WIN"),
            ("I_PASS_13",), ("I_BATTLE_INFO", "I_WIN"),
            ("I_UI_BACK_CIRCLE",), ("I_TO_BATTLE_BOSS",),
            ("I_CHECK_BATTLE_BOSS", "I_BACK_GREEN"), ("I_CHECK_MAIN",),
        ],
        params={
            "act_mode": "ap", "act_run_ap100_after_ap": True, "act_run_boss_after_ap": True,
            "act_ap_limit": 1, "act_ap100_limit": 1, "act_boss_limit": 5, "act_check_resource_ocr": True,
        },
        initial_vars={"act_phase": "fight_loop"},
        ocr_int=lambda img, roi: 5 if int(img[0, 0, 0]) - 20 < 4 else 0,
    )
    assert res_ap100_seq.status == "success", res_ap100_seq.summary()
    assert res_ap100_seq.variables["act_wins"] == 2 and res_ap100_seq.variables["act_exit_reason"] == "boss_empty"

    res_bt_sched, _ = _run(
        bt, stage / "resources", [("I_BACK_GREEN",), ("I_CHECK_MAIN",)],
        params={"bt_limit_seconds": 0, "bt_next_delay_s": 43200},
        initial_vars={"bt_phase": "fight_loop"},
    )
    assert res_bt_sched.status == "success" and res_bt_sched.variables["bt_exit_reason"] == "time_limit"
    assert res_bt_sched.oas_target is not None and res_bt_sched.oas_target[0] == 43200


def test_frog_boss_and_demon_encounter(oas_stage):
    stage, src, folder = oas_stage
    fb = compile_frog_boss_candidate(src, folder)
    res_gate, dev = _run(
        fb, stage / "resources", [("I_BET_LEFT", "I_BET_RIGHT")],
        initial_vars={"fb_phase": "lobby"},
    )
    assert res_gate.status == "failed" and "fb_confirm_bet" in res_gate.reason
    assert dev.inputs == []

    res_rest, _ = _run(fb, stage / "resources", [("I_FROG_BOSS_REST",)], initial_vars={"fb_phase": "lobby"})
    assert res_rest.status == "success" and res_rest.oas_schedule == "FrogBoss"

    # FrogBoss 30w gold bet requires sensitive="购买" runtime confirmation
    res_fb_deny, dev_fb_deny = _run(
        fb, stage / "resources", [("I_BET_SURE",)],
        params={"fb_confirm_bet": True},
        initial_vars={"fb_phase": "confirm_bet"},
        confirm=lambda _c, _d: False,
    )
    assert res_fb_deny.status == "failed" and res_fb_deny.failure_kind == "confirm_denied"
    assert dev_fb_deny.inputs == []

    fb_asks = []
    res_fb_ok, _ = _run(
        fb, stage / "resources",
        [("I_BET_LEFT", "I_BET_RIGHT"), ("I_GOLD_30",), ("I_BET_SURE",), ("I_BETTED",)],
        params={"fb_confirm_bet": True, "fb_bet_side": "left"},
        initial_vars={"fb_phase": "lobby"},
        confirm=lambda c, _d: (fb_asks.append(c) or True),
    )
    assert res_fb_ok.status == "success" and fb_asks == ["购买"]

    res_fb_2h, _ = _run(
        fb, stage / "resources", [("I_BETTED",)],
        params={"fb_round_delay_s": 7200},
        initial_vars={"fb_phase": "lobby"},
    )
    assert res_fb_2h.status == "success" and res_fb_2h.oas_target is not None and res_fb_2h.oas_target[0] == 7200

    res_fb_tl, _ = _run(
        fb, stage / "resources", [("I_FROG_BOSS_ENTER",), ("I_FROG_CHECK",)],
        params={"fb_limit_seconds": 1, "fb_round_delay_s": 7200},
        initial_vars={"fb_phase": "enter"},
    )
    assert res_fb_tl.status == "success" and res_fb_tl.variables["fb_exit_reason"] == "time_limit"
    assert res_fb_tl.oas_target is not None and res_fb_tl.oas_target[0] == 7200

    de = compile_demon_encounter_candidate(src, folder)
    res_closed, _ = _run(de, stage / "resources", [()], params={"de_is_open_window": False})
    assert res_closed.status == "success" and res_closed.oas_schedule == "DemonEncounter"

    res_boss, _ = _run(
        de, stage / "resources",
        [("I_JADE_50", "I_DE_FIND"), ("I_BOSS_FIRE",), ("I_BATTLE_INFO", "I_WIN"), ("I_BOSS_BACK_WHITE",), ("I_CHECK_MAIN",)],
        initial_vars={"de_phase": "boss"},
    )
    assert res_boss.status == "success", res_boss.summary()
    assert res_boss.variables["de_wins"] == 1

    # O_DE_CHALLENGE_COUNT == 0/1 early exit
    res_de_done, de_done_device = _run(
        de, stage / "resources", [("I_DE_FIND", "I_UI_BACK_YELLOW")],
        params={"oas_success_seconds": 3600},
        initial_vars={"de_phase": "lanterns"},
        ocr_single={0: "0/1"},
    )
    assert res_de_done.status == "success" and res_de_done.variables["de_exit_reason"] == "already_challenged_ocr"
    assert res_de_done.business_result == "already_done" and not de_done_device.inputs
    assert res_de_done.oas_target is not None and res_de_done.oas_target[0] == 3600

    # Realm lantern battle + crowded boss (>=290/300) reselect + confirm/gather -> battle
    res_de_full, _ = _run(
        de, stage / "resources",
        [
            ("I_DE_AWARD", "I_DE_REALM"),
            ("I_DE_REALM_FIRE",),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_DE_AWARD", "I_BOSS_FIRE", "I_UI_BACK_RED"),
            ("I_BOSS_FIRE",),
            ("I_BOSS_CONFIRM", "I_BOSS_NO_SELECT"),
            ("I_BOSS_CONFIRM", "I_BOSS_SELECTED"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_BOSS_BACK_WHITE",),
            ("I_CHECK_MAIN",),
        ],
        params={"de_battle_lanterns": True, "de_check_boss_people": True, "de_wait_boss_gather": True},
        initial_vars={"de_phase": "scan_letters", "de_lantern": 4},
        ocr_single={3: "295/300", 4: "120/300"},
    )
    assert res_de_full.status == "success", res_de_full.summary()
    assert res_de_full.variables["de_lantern_battles"] == 1 and res_de_full.variables["de_crowded_skips"] == 1
    assert res_de_full.variables["de_wins"] == 2

    # Additional lantern classes: balloon, mystery, and find-boss shortcut
    res_de_bal, _ = _run(
        de, stage / "resources",
        [("I_DE_AWARD", "I_DE_BALLOON", "I_BOSS_DONE_CHECK", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        initial_vars={"de_phase": "scan_letters", "de_lantern": 4},
    )
    assert res_de_bal.status == "success" and res_de_bal.variables["de_lantern_balloon_hits"] == 1

    res_de_mys, _ = _run(
        de, stage / "resources",
        [("I_DE_AWARD", "I_DE_MYSTERY", "I_BOSS_DONE_CHECK", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        initial_vars={"de_phase": "scan_letters", "de_lantern": 4},
    )
    assert res_de_mys.status == "success" and res_de_mys.variables["de_lantern_mystery_hits"] == 1

    res_de_fb, _ = _run(
        de, stage / "resources",
        [("I_DE_AWARD", "I_DE_FIND_BOSS"), ("I_BOSS_DONE_CHECK", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"de_find_boss_lantern": True},
        initial_vars={"de_phase": "scan_letters", "de_lantern": 4},
    )
    assert res_de_fb.status == "success" and res_de_fb.variables["de_boss_lantern_found"] is True

    # Closed-window target schedule + bounded boss search exhaustion exit
    res_de_sched, _ = _run(
        de, stage / "resources", [()],
        params={"de_is_open_window": False, "de_next_open_delay_s": 36000},
    )
    assert res_de_sched.status == "success" and res_de_sched.oas_target[0] == 36000

    res_de_nf, _ = _run(
        de, stage / "resources",
        [("I_DE_BOSS",), ("I_DE_BOSS",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"de_boss_search_max": 1, "de_next_open_delay_s": 1800},
        initial_vars={"de_phase": "boss"},
    )
    assert res_de_nf.status == "success" and res_de_nf.variables["de_exit_reason"] == "boss_not_found"
    assert res_de_nf.oas_target[0] == 1800

    res_de_tl, _ = _run(
        de, stage / "resources", [("I_DE_FIND",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"de_limit_seconds": 1, "de_next_open_delay_s": 36000},
        initial_vars={"de_phase": "lanterns"},
        ocr_single={0: "4/4"},
    )
    assert res_de_tl.status == "success" and res_de_tl.variables["de_exit_reason"] == "time_limit"
    assert res_de_tl.oas_target is not None and res_de_tl.oas_target[0] == 36000
