"""Offline unit tests for OAS FindJade, Quiz, OtherWorldTwilight, MetaDemon, and HeroTest."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_events_and_trials import (
    compile_find_jade_candidate,
    compile_hero_test_candidate,
    compile_meta_demon_candidate,
    compile_other_world_twilight_candidate,
    compile_quiz_candidate,
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
    for task in ("Quiz", "ActivityShikigami", "OtherWorldTwilight", "MetaDemon", "HeroTest",
                 "Component_GeneralBuff", "Component_SwitchSoul", "Component_GeneralRoom", "Component_GeneralInvite",
                 "Component_SwitchAccount"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_int=None, ocr_single=None,
         full_ocr_reader=None, confirm=None, boxes=None):
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
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, ocr_reader=read_int, single_ocr_reader=read_single,
            full_ocr_reader=full_ocr_reader, confirm=confirm, initial_vars=initial_vars,
        ).run()
    return res, device


def test_find_jade_and_quiz(oas_stage):
    stage, src, folder = oas_stage
    fj = compile_find_jade_candidate(src, folder)
    res_gate, dev = _run(fj, stage / "resources", [()], params={"fj_has_pending_account": True})
    assert res_gate.status == "failed" and "fj_confirm_switch_account" in res_gate.reason
    assert dev.inputs == []

    res_sched, _ = _run(fj, stage / "resources", [()], params={"fj_next_window_delay_s": 3600})
    assert res_sched.status == "success" and res_sched.oas_schedule == "FindJade"
    assert res_sched.oas_target is not None and res_sched.oas_target[0] == 3600

    # FindJade guarded SwitchAccount: runtime sensitive denial + approved switch -> WantedQuests wake
    res_fj_deny, dev_fj_deny = _run(
        fj, stage / "resources", [("I_SA_SWITCH_ACCOUNT_BTN",)],
        params={
            "fj_has_pending_account": True, "fj_confirm_switch_account": True,
            "fj_target_account": "alt@163.com", "fj_target_character": "小号甲",
        },
        initial_vars={"fj_phase": "exit_current"},
        confirm=lambda _c, _d: False,
    )
    assert res_fj_deny.status == "failed" and res_fj_deny.failure_kind == "confirm_denied"
    assert dev_fj_deny.inputs == []

    fj_asks = []

    def fj_ocr(image, _region, keyword, score=0.6, **_kw):
        idx = int(image[0, 0, 0]) - 20
        if idx == 3 and keyword == "alt@163.com":
            return FullOcrArea((500, 300, 120, 28), keyword_complete=True)
        if idx == 6 and keyword == "小号甲":
            return FullOcrArea((480, 240, 80, 28), keyword_complete=True)
        return (0, 0, 0, 0)

    res_fj_sw, _ = _run(
        fj, stage / "resources",
        [
            ("I_CHECK_MAIN",),
            ("I_SA_USER_CENTER",),
            ("I_SA_SWITCH_ACCOUNT_BTN",),
            ("I_SA_NETEASE_GAME_LOGO", "I_SA_ACCOUNT_DROP_DOWN_CLOSED", "I_SA_ACCOUNT_LOGIN_BTN"),
            ("I_CHECK_LOGIN_FORM",),
            ("I_SA_CHECK_SELECT_SVR_1",),
            ("I_SA_CHECK_SELECT_SVR_2",),
            ("I_CHECK_LOGIN_FORM",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "fj_has_pending_account": True, "fj_confirm_switch_account": True,
            "fj_target_account": "alt@163.com", "fj_target_character": "小号甲",
            "fj_next_window_delay_s": 7200,
        },
        full_ocr_reader=fj_ocr,
        confirm=lambda c, _d: (fj_asks.append(c) or True),
    )
    assert res_fj_sw.status == "success", res_fj_sw.summary()
    assert fj_asks == ["重启游戏"]
    assert res_fj_sw.variables["fj_account_switched"] is True
    assert res_fj_sw.variables["fj_wq_woken"] is True and list(res_fj_sw.oas_wakes) == ["WantedQuests"]
    assert res_fj_sw.oas_target is not None and res_fj_sw.oas_target[0] == 7200

    res_fj_tl, _ = _run(
        fj, stage / "resources", [("I_CHECK_MAIN",), ()],
        params={
            "fj_has_pending_account": True, "fj_confirm_switch_account": True,
            "fj_target_account": "alt@163.com", "fj_target_character": "小号甲",
            "fj_limit_seconds": 1, "fj_next_window_delay_s": 7200,
        },
        initial_vars={"fj_phase": "exit_current"},
    )
    assert res_fj_tl.status == "success" and res_fj_tl.variables["fj_exit_reason"] == "time_limit"
    assert res_fj_tl.oas_target is not None and res_fj_tl.oas_target[0] == 7200

    qz = compile_quiz_candidate(src, folder)
    res_qz, _ = _run(
        qz, stage / "resources",
        [
            ("I_START",), ("I_MESSAGE", "I_UI_REWARD"), ("I_MESSAGE",),
            ("I_SHARE", "I_UI_BACK_RED"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",),
        ],
        params={"qz_max_rounds": 1, "qz_enable_answer_bank": False},
        initial_vars={"qz_phase": "lobby"},
        ocr_int={2: 3},
    )
    assert res_qz.status == "success", res_qz.summary()
    assert res_qz.variables["qz_rounds"] == 1 and res_qz.variables["qz_answers_clicked"] >= 1
    assert res_qz.variables["qz_rewards_dismissed"] == 1

    res_qz_tl, _ = _run(
        qz, stage / "resources",
        [("I_START",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"qz_max_rounds": 5, "qz_limit_seconds": 1, "qz_next_delay_s": 86400},
        initial_vars={"qz_phase": "lobby"},
    )
    assert res_qz_tl.status == "success", res_qz_tl.summary()
    assert res_qz_tl.variables["qz_exit_reason"] == "time_limit" and res_qz_tl.oas_target[0] == 86400

    # Quiz tall vertical I_SHI + I_ENTRY clicked dynamically inside matched boxes
    res_qz_dyn, dev_qz_dyn = _run(
        {**qz, "stop_when": "qz_phase == 'lobby'"},
        stage / "resources",
        [("I_SHI",), ("I_ENTRY",), ("I_START",)],
        initial_vars={"qz_phase": "enter"},
        boxes={"I_SHI": (1185, 160, 39, 28), "I_ENTRY": (770, 300, 33, 139)},
    )
    assert res_qz_dyn.status == "success"
    assert 1185 <= dev_qz_dyn.inputs[0][1] <= 1224 and 160 <= dev_qz_dyn.inputs[0][2] <= 188
    assert 770 <= dev_qz_dyn.inputs[1][1] <= 803 and 300 <= dev_qz_dyn.inputs[1][2] <= 439


def test_other_world_twilight_and_meta_demon(oas_stage):
    stage, src, folder = oas_stage
    owt = compile_other_world_twilight_candidate(src, folder)
    res_lead, _ = _run(
        owt, stage / "resources",
        [
            ("I_OWT_TEAM",), ("I_CREATE_ROOM",), ("I_CREATE_ENSURE", "I_ENSURE_PRIVATE"),
            ("I_GI_EMOJI_1", "I_FIRE"), ("I_BATTLE_INFO", "I_WIN"),
            ("I_GI_EMOJI_1", "I_BACK_YELLOW"), ("I_UI_CONFIRM",), ("I_CHECK_MAIN",),
        ],
        params={"owt_user_status": "leader", "owt_limit_count": 1},
        initial_vars={"owt_phase": "leader_open_team"},
    )
    assert res_lead.status == "success" and res_lead.variables["owt_wins"] == 1, res_lead.summary()

    res_owt, _ = _run(
        owt, stage / "resources",
        [("I_OWT_LOCK", "I_OWT_FIRE"), ("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_MAIN",)],
        params={"owt_limit_count": 1, "lock_team_enable": True},
        initial_vars={"owt_phase": "lock_check"},
    )
    assert res_owt.status == "success", res_owt.summary()
    assert res_owt.variables["owt_wins"] == 1

    # Wall-clock time limit stop (alone) & member wait timeout stop
    res_owt_time, _ = _run(
        owt, stage / "resources", [("I_CHECK_MAIN",)],
        params={"owt_limit_seconds": 0, "owt_limit_count": 10},
        initial_vars={"owt_phase": "fire_loop"},
    )
    assert res_owt_time.status == "success" and res_owt_time.variables["owt_exit_reason"] == "time_limit"

    res_owt_mem, _ = _run(
        owt, stage / "resources", [("I_CHECK_MAIN",)],
        params={"owt_user_status": "member", "owt_member_wait_seconds": 0},
        initial_vars={"owt_phase": "member_accept"},
    )
    assert res_owt_mem.status == "success" and res_owt_mem.variables["owt_exit_reason"] == "member_wait_timeout"

    # Alone-mode in-battle takeover recovery + unknown-page navigation recovery
    res_owt_rec, _ = _run(
        owt, stage / "resources",
        [("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_MAIN",)],
        params={"owt_limit_count": 1, "owt_next_delay_s": 14400},
        initial_vars={"owt_phase": "fire_loop"},
    )
    assert res_owt_rec.status == "success", res_owt_rec.summary()
    assert res_owt_rec.variables["owt_battle_recoveries"] == 1 and res_owt_rec.variables["owt_wins"] == 1
    assert res_owt_rec.oas_target is not None and res_owt_rec.oas_target[0] == 14400

    res_owt_unk, _ = _run(
        {**owt, "stop_when": "owt_page_recoveries == 1"},
        stage / "resources",
        [()],
        params={"owt_unknown_page_timeout_s": 1, "owt_limit_count": 5},
        initial_vars={"owt_phase": "fire_loop"},
    )
    assert res_owt_unk.status == "success", res_owt_unk.summary()
    assert res_owt_unk.variables["owt_page_recoveries"] == 1 and res_owt_unk.variables["owt_phase"] == "navigate"

    md = compile_meta_demon_candidate(src, folder)
    res_craft, dev = _run(md, stage / "resources", [()], params={"md_crafting_card": True})
    assert res_craft.status == "failed" and "md_confirm_craft" in res_craft.reason
    assert dev.inputs == []

    asks = []
    res_craft_ok, _ = _run(
        md, stage / "resources",
        [
            ("I_CRAFTING_1",),
            ("I_CRAFTING_START", "I_CRAFTING_EMPTY", "I_CRAFTING_CARD_STAR_1"),
            ("I_CRAFTING_START",),
            ("I_UI_BACK_RED",),
            ("I_BATTLE_DEMON", "I_STAR56_HP_THRESHOLD_F"),
            ("I_MD_WIN",),
            ("I_UI_BACK_RED",),
            ("I_CHECK_MAIN",),
        ],
        params={"md_crafting_card": True, "md_confirm_craft": True, "md_max_crafts": 1, "md_limit_count": 1},
        initial_vars={"md_phase": "craft_open"},
        ocr_single={1: "一星梦告铃鼓", 2: "一星梦告铃鼓", 4: "10/100"},
        confirm=lambda cat, detail: (asks.append((cat, detail)) or True),
    )
    assert res_craft_ok.status == "success", res_craft_ok.summary()
    assert res_craft_ok.variables["md_crafted"] == 1 and asks[0][0] == "分解"
    assert res_craft_ok.variables["md_is_star56"] is True and res_craft_ok.variables["md_hp_low"] is True
    assert res_craft_ok.variables["md_wins"] == 1

    res_craft_deny, dev_deny = _run(
        md, stage / "resources",
        [("I_CRAFTING_START",)],
        params={"md_crafting_card": True, "md_confirm_craft": True},
        initial_vars={"md_phase": "craft_loop"},
        ocr_single={0: "一星梦告铃鼓"},
        confirm=lambda _c, _d: False,
    )
    assert res_craft_deny.status == "failed" and res_craft_deny.failure_kind == "confirm_denied"
    assert dev_deny.inputs == []

    res_md, _ = _run(
        md, stage / "resources",
        [("I_BATTLE_DEMON", "I_UI_BACK_RED"), ("I_CHECK_MAIN",)],
        initial_vars={"md_phase": "loop"},
        ocr_single={0: "100/100"},
    )
    assert res_md.status == "success", res_md.summary()
    assert res_md.oas_schedule == "MetaDemon"

    # Star56 full-name OCR strategy routing + summon exhaustion cap (< 90) + boss idle timeout
    with patch("onmyoji_agentflow.vision.ocr.read_boxes",
               lambda img, _r: [("须佐之男", 0.99, (480, 140, 80, 30))] if int(img[0, 0, 0]) - 20 == 0 else []):
        res_md_strat, _ = _run(
            md, stage / "resources",
            [
                ("I_BATTLE_DEMON", "I_STAR56_HP_THRESHOLD_F"),
                ("I_MD_WIN",),
                ("I_FIND_DEMON", "I_UI_BACK_RED"),
                ("I_CHECK_MAIN",),
            ],
            params={
                "md_use_strategy": True,
                "md_star56_low_hp_group": 3, "md_star56_low_hp_team": 4,
                "md_limit_count": 5, "md_summon_exhaustion_cap": 90,
            },
            initial_vars={"md_phase": "loop"},
            ocr_single={0: "40/100", 2: "92/100"},
        )
    assert res_md_strat.status == "success", res_md_strat.summary()
    assert "须佐之男" in res_md_strat.variables["md_boss_name"]
    assert res_md_strat.variables["md_preset_group"] == 3 and res_md_strat.variables["md_preset_team"] == 4
    assert res_md_strat.variables["md_exit_reason"] == "summon_exhaustion_cap"

    res_md_idle, _ = _run(
        md, stage / "resources",
        [("I_UI_BACK_RED",), ("I_CHECK_MAIN",)],
        params={"md_boss_idle_timeout_s": 1, "md_limit_count": 5, "md_next_delay_s": 3600},
        initial_vars={"md_phase": "loop"},
    )
    assert res_md_idle.status == "success", res_md_idle.summary()
    assert res_md_idle.variables["md_exit_reason"] == "boss_idle_timeout"
    assert res_md_idle.oas_target is not None and res_md_idle.oas_target[0] == 3600

    res_md_tl, _ = _run(
        md, stage / "resources",
        [("I_BATTLE_DEMON",), ("I_MD_WIN",), ("I_UI_BACK_RED",), ("I_CHECK_MAIN",)],
        params={"md_limit_count": 5, "md_limit_seconds": 1},
        initial_vars={"md_phase": "loop"},
        ocr_single={0: "40/100", 2: "45/100"},
    )
    assert res_md_tl.status == "success" and res_md_tl.variables["md_exit_reason"] == "time_limit"

    # Entry reward/red-back dismissal -> self boss open -> easy default preset -> yellow-back exit
    res_md_self, _ = _run(
        md, stage / "resources",
        [
            ("I_UI_REWARD",),
            ("I_UI_BACK_RED",),
            ("I_FIND_DEMON", "I_BOSS_CONVENE"),
            ("I_BATTLE_DEMON", "I_STAR56_POS_1"),
            ("I_MD_WIN",),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        params={
            "md_limit_count": 1, "md_use_strategy": True,
            "md_default_group": 1, "md_default_team": 2,
        },
        initial_vars={"md_phase": "enter"},
        ocr_single={2: "10/100", 3: "10/100"},
    )
    assert res_md_self.status == "success", res_md_self.summary()
    assert res_md_self.variables["md_self_boss_opens"] == 1
    assert res_md_self.variables["md_preset_group"] == 1 and res_md_self.variables["md_preset_team"] == 2
    assert res_md_self.variables["md_first_easy_battle"] is False and res_md_self.variables["md_wins"] == 1

    # MetaDemon tall right-bar I_RIGHT_ENTER clicked dynamically inside matched box
    res_md_dyn, dev_md_dyn = _run(
        {**md, "stop_when": "md_phase == 'loop'"},
        stage / "resources",
        [("I_RIGHT_ENTER",), ("I_FIND_DEMON",)],
        initial_vars={"md_phase": "enter"},
        boxes={"I_RIGHT_ENTER": (1180, 410, 37, 26)},
    )
    assert res_md_dyn.status == "success"
    assert 1180 <= dev_md_dyn.inputs[0][1] <= 1217 and 410 <= dev_md_dyn.inputs[0][2] <= 436

    res_owt_sched, _ = _run(
        owt, stage / "resources", [("I_CHECK_MAIN",)],
        params={"owt_limit_seconds": 0, "owt_next_delay_s": 14400},
        initial_vars={"owt_phase": "fire_loop"},
    )
    assert res_owt_sched.status == "success" and res_owt_sched.variables["owt_exit_reason"] == "time_limit"
    assert res_owt_sched.oas_target is not None and res_owt_sched.oas_target[0] == 14400


def test_hero_test_real_money_stop_and_fight(oas_stage):
    stage, src, folder = oas_stage
    ht = compile_hero_test_candidate(src, folder)
    res_stop, _ = _run(
        ht, stage / "resources",
        [("I_REAL_MONEY", "I_GBB_BACK"), ("I_CHECK_MAIN",)],
        params={"ht_next_delay_s": 14400},
        initial_vars={"ht_phase": "fight_loop"},
    )
    assert res_stop.status == "success", res_stop.summary()
    assert res_stop.variables["ht_exit_reason"] == "ticket_empty_real_money_popup"
    assert res_stop.oas_target is not None and res_stop.oas_target[0] == 14400

    res_fight, _ = _run(
        ht, stage / "resources",
        [("I_BATTLE",), ("I_BATTLE_INFO", "I_WIN"), ("I_GBB_BACK",), ("I_CHECK_MAIN",)],
        params={"ht_limit_count": 1},
        initial_vars={"ht_phase": "fight_loop"},
    )
    assert res_fight.status == "success", res_fight.summary()
    assert res_fight.variables["ht_wins"] == 1

    def read_row(image, _roi, keyword, *_args):
        assert "经验" in keyword
        index = int(image[0, 0, 0]) - 20
        return FullOcrArea((440, 140 + 20 * (index - 1), 180, 15), keyword_complete=True)

    courtyard = ("I_CHECK_MAIN", "I_BUFF_1")
    panel = ("I_CLOUD", "I_BUFF_1", "I_AWAKE")
    res_open, dev_open = _run(
        {**ht, "stop_when": "ht_phase == 'navigate'"},
        stage / "resources",
        [courtyard, (*panel, "I_CLOSE_RED"), (*panel, "I_OPEN_YELLOW"), courtyard],
        params={"ht_exp_buff": True, "ht_buff_exp_50": True},
        full_ocr_reader=read_row,
    )
    assert res_open.status == "success" and len(dev_open.inputs) == 3
    assert res_open.variables["ht_buff_before_select_0_helper_status"] == "observed"

    res_close, dev_close = _run(
        ht, stage / "resources",
        [courtyard, (*panel, "I_OPEN_YELLOW"), (*panel, "I_CLOSE_RED"), courtyard],
        params={"ht_exp_buff": True, "ht_buff_exp_50": True},
        initial_vars={"ht_phase": "buff_after"},
        full_ocr_reader=read_row,
    )
    assert res_close.status == "success" and res_close.oas_schedule == "HeroTest"
    assert len(dev_close.inputs) == 3 and res_close.variables["ht_buff_after_select_0_helper_status"] == "observed"

    # Ticket OCR empty stop in skill mode + hero2 skill blessing priority pick
    res_card, _ = _run(
        ht, stage / "resources",
        [("I_GBB_BACK",), ("I_CHECK_MAIN",)],
        params={"ht_mode": "skill", "ht_check_ticket_ocr": True},
        initial_vars={"ht_phase": "fight_loop"},
        ocr_int={0: 0},
    )
    assert res_card.status == "success" and res_card.variables["ht_exit_reason"] == "art_war_card_empty"

    res_bless, dev_bless = _run(
        ht, stage / "resources",
        [("I_BCMJ_SKILL_ADD_CONFIRM", "I_HERO2_SKILL2"), ("I_BCMJ_SKILL_ADD_CONFIRM",),
         ("I_GBB_BACK",), ("I_CHECK_MAIN",)],
        params={"ht_hero": "hero2", "ht_mode": "skill", "ht_limit_count": 0},
        initial_vars={"ht_phase": "fight_loop"},
        boxes={"I_HERO2_SKILL2": (140, 358, 61, 36)},
    )
    assert res_bless.status == "success" and res_bless.variables["ht_bless_count"] == 1
    assert len(dev_bless.inputs) == 3
    assert 140 <= dev_bless.inputs[0][1] <= 201 and 358 <= dev_bless.inputs[0][2] <= 394

    # HeroTest AP OCR stop + wall-clock time-limit stop
    res_ap, _ = _run(
        ht, stage / "resources",
        [("I_GBB_BACK",), ("I_CHECK_MAIN",)],
        params={"ht_mode": "exp", "ht_check_ap_ocr": True, "ht_ap_min": 12},
        initial_vars={"ht_phase": "fight_loop"},
        ocr_single={0: "8/100"},
    )
    assert res_ap.status == "success" and res_ap.variables["ht_exit_reason"] == "ap_insufficient"

    res_ht_tl, _ = _run(
        ht, stage / "resources",
        [("I_BATTLE",), ("I_BATTLE_INFO", "I_WIN"), ("I_GBB_BACK",), ("I_CHECK_MAIN",)],
        params={"ht_limit_count": 5, "ht_limit_seconds": 1},
        initial_vars={"ht_phase": "fight_loop"},
    )
    assert res_ht_tl.status == "success" and res_ht_tl.variables["ht_exit_reason"] == "time_limit"
