"""Offline unit tests for OAS AbyssShadows, CollectiveMissions, KekkaiActivation, and Restart."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_guild_and_restart import (
    compile_abyss_shadows_candidate,
    compile_collective_missions_candidate,
    compile_kekkai_activation_candidate,
    compile_restart_candidate,
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
    for task in ("AbyssShadows", "CollectiveMissions", "KekkaiActivation", "KekkaiUtilize",
                 "Component_SwitchSoul", "Component_ReplaceShikigami"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_single=None, ocr_int=None, confirm=None):
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
        if callable(ocr_single):
            return ocr_single(image, region)
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, ocr_reader=read_int, single_ocr_reader=read_single,
            confirm=confirm, initial_vars=initial_vars,
        ).run()
    return res, device


def test_abyss_shadows_closed_day_and_fight(oas_stage):
    stage, src, folder = oas_stage
    ab = compile_abyss_shadows_candidate(src, folder)
    res_skip, _ = _run(ab, stage / "resources", [()], params={"as_is_open_day": False})
    assert res_skip.status == "success" and res_skip.oas_schedule == "AbyssShadows"

    res, _ = _run(
        ab, stage / "resources",
        [("I_ABYSS_MAP",), ("I_ABYSS_MAP",), ("I_ABYSS_FIRE",), ("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_MAIN",)],
        params={"as_max_battles": 1},
        initial_vars={"as_phase": "fight_cycle"},
    )
    assert res.status == "success", res.summary()
    assert res.variables["as_wins"] == 1

    # 4-area switching (Dragon -> Peacock) when target slots wrap
    res_sw, _ = _run(
        {**ab, "stop_when": "as_areas_switched == 1"},
        stage / "resources",
        [("I_ABYSS_MAP_EXIT",), ("I_CHANGE_AREA",), ("I_ABYSS_DRAGON",), ("I_PEACOCK_AREA",)],
        params={"as_switch_areas": True},
        initial_vars={"as_phase": "pick_target", "as_target_idx": 6, "as_area_idx": 0},
    )
    assert res_sw.status == "success" and res_sw.variables["as_area_idx"] == 1

    # Smart combat timer early retreat via I_EXIT -> I_UI_CONFIRM -> I_ABYSS_NAVIGATION
    res_tm, _ = _run(
        ab, stage / "resources",
        [("I_EXIT",), ("I_UI_CONFIRM",), ("I_ABYSS_NAVIGATION", "I_CHECK_MAIN")],
        params={"as_max_battles": 1, "as_combat_time_enable": True, "as_boss_combat_seconds": 5},
        initial_vars={
            "as_phase": "battle", "as_battles": 1, "as_battle_started": -10000, "as_current_combat_ms": 5000,
        },
    )
    assert res_tm.status == "success", res_tm.summary()
    assert res_tm.variables["as_retreats"] == 1

    # Closed-day weekday target schedule & fight-cycle wall-clock time limit
    res_sched, _ = _run(
        ab, stage / "resources", [()],
        params={"as_is_open_day": False, "as_next_open_delay_s": 172800},
    )
    assert res_sched.status == "success" and res_sched.oas_target[0] == 172800
    assert res_sched.variables["as_exit_reason"] == "closed_day"

    res_tl, _ = _run(
        ab, stage / "resources", [("I_CHECK_MAIN",)],
        params={"as_limit_seconds": 0, "as_next_open_delay_s": 86400},
        initial_vars={"as_phase": "fight_cycle"},
    )
    assert res_tl.status == "success" and res_tl.variables["as_exit_reason"] == "time_limit"
    assert res_tl.oas_target[0] == 86400


def test_collective_missions_gate_and_already_30(oas_stage):
    stage, src, folder = oas_stage
    cm = compile_collective_missions_candidate(src, folder)
    res_gate, dev = _run(
        cm, stage / "resources", [("I_CM_RECORDS",)],
        initial_vars={"cm_phase": "check_count"},
        ocr_single={0: "10/30"},
    )
    assert res_gate.status == "failed" and "cm_confirm_donate" in res_gate.reason
    assert dev.inputs == []

    res_done, _ = _run(
        cm, stage / "resources", [("I_CM_RECORDS", "I_UI_BACK_RED"), ("I_CM_SHRINE",)],
        params={"cm_next_delay_s": 86400},
        initial_vars={"cm_phase": "check_count"},
        ocr_single={0: "30/30"},
    )
    assert res_done.status == "success" and res_done.oas_schedule == "CollectiveMissions"
    assert res_done.oas_target is not None and res_done.oas_target[0] == 86400

    asks = []
    res_don, _ = _run(
        cm, stage / "resources",
        [
            ("I_CM_RECORDS",),
            ("I_CM_PRESENT",),
            ("I_CM_PRESENT", "I_CM_MATTER"),
            ("I_UI_REWARD",),
            ("I_UI_REWARD",),
            ("I_CM_RECORDS", "I_UI_BACK_RED"),
            ("I_CM_SHRINE",),
        ],
        params={"cm_confirm_donate": True},
        initial_vars={"cm_phase": "check_count"},
        ocr_single={0: "10/30", 5: "11/30"},
        confirm=lambda c, d: (asks.append((c, d)) or True),
    )
    assert res_don.status == "success", res_don.summary()
    assert asks[0][0] == "分解" and res_don.variables["cm_rewards_claimed"] == 2
    assert res_don.variables["cm_exit_reason"] == "donated_verified"

    res_deny, dev_deny = _run(
        cm, stage / "resources", [("I_CM_PRESENT", "I_CM_MATTER")],
        params={"cm_confirm_donate": True},
        initial_vars={"cm_phase": "donate"},
        confirm=lambda _c, _d: False,
    )
    assert res_deny.status == "failed" and res_deny.failure_kind == "confirm_denied"
    assert dev_deny.inputs == []

    # BondlingFairyland cross-task wake + 2h target reschedule
    res_bl, _ = _run(
        cm, stage / "resources", [("I_CM_RECORDS", "I_UI_BACK_RED"), ("I_CM_SHRINE",)],
        params={"cm_mission_mode": "bondling"},
        initial_vars={"cm_phase": "check_count"},
        ocr_single={0: "10/30"},
    )
    assert res_bl.status == "success", res_bl.summary()
    assert res_bl.variables["cm_bondling_woken"] is True
    assert list(res_bl.oas_wakes) == ["BondlingFairyland"]
    assert res_bl.oas_target is not None and res_bl.oas_target[0] == 7200

    # Soul & N-card feed branches require sensitive="分解"
    soul_asks = []
    res_soul, _ = _run(
        cm, stage / "resources",
        [("I_CM_RECORDS",), ("I_SL_SUBMIT",), ("I_SL_SUBMIT",), ("I_UI_REWARD",),
         ("I_CM_RECORDS", "I_UI_BACK_RED"), ("I_CM_SHRINE",)],
        params={"cm_mission_mode": "soul", "cm_confirm_donate": True},
        initial_vars={"cm_phase": "check_count"},
        ocr_single={0: "10/30", 4: "11/30"},
        ocr_int={1: 0, 2: 3},
        confirm=lambda c, _d: (soul_asks.append(c) or True),
    )
    assert res_soul.status == "success" and res_soul.variables["cm_soul_submitted"] is True and soul_asks == ["分解"]

    feed_asks = []
    res_feed, _ = _run(
        cm, stage / "resources",
        [("I_CM_RECORDS",), ("I_FEED_HEAP",), ("I_FEED_HEAP",), ("I_FEED_SUBMIT",), ("I_UI_REWARD",),
         ("I_CM_RECORDS", "I_UI_BACK_RED"), ("I_CM_SHRINE",)],
        params={"cm_mission_mode": "feed", "cm_confirm_donate": True},
        initial_vars={"cm_phase": "check_count"},
        ocr_single={0: "10/30", 5: "11/30"},
        confirm=lambda c, _d: (feed_asks.append(c) or True),
    )
    assert res_feed.status == "success" and res_feed.variables["cm_feed_submitted"] is True and feed_asks == ["分解"]

    # 3-slot OCR title ranking overrides default slot 1 to pick slot 3
    ocr_asks = []
    res_ocr_slot, _ = _run(
        cm, stage / "resources",
        [
            ("I_CM_RECORDS",),
            ("I_CM_PRESENT", "I_CM_MATTER"),
            ("I_UI_REWARD",),
            ("I_CM_RECORDS", "I_UI_BACK_RED"),
            ("I_CM_SHRINE",),
        ],
        params={"cm_confirm_donate": True, "cm_prefer_slot": 1, "cm_ocr_prefer_title": "御灵"},
        initial_vars={"cm_phase": "check_count"},
        ocr_single=lambda img, roi: (
            ("10/30" if int(img[0, 0, 0]) - 20 == 0 else "11/30")
            if roi[0] == 1105 else ("御灵" if roi[0] == 889 else "")
        ),
        confirm=lambda c, _d: (ocr_asks.append(c) or True),
    )
    assert res_ocr_slot.status == "success", res_ocr_slot.summary()
    assert res_ocr_slot.variables["cm_selected_slot"] == 3 and ocr_asks == ["分解"]

    res_cm_tl, _ = _run(
        cm, stage / "resources", [("I_CM_SHRINE",), ("I_CM_SHRINE",)],
        params={"cm_limit_seconds": 1, "cm_next_delay_s": 86400},
        initial_vars={"cm_phase": "enter_cm"},
    )
    assert res_cm_tl.status == "success" and res_cm_tl.variables["cm_exit_reason"] == "time_limit"
    assert res_cm_tl.oas_target is not None and res_cm_tl.oas_target[0] == 86400

    # Long-click assets (L_SL_LONG, L_FEED_CLICK_1/2) must preserve YAML press_ms=1500
    by_id = {st["id"]: st for st in cm["states"]}
    assert by_id["cm_soul_select_long"]["do"][0]["press_ms"] == 1500
    assert by_id["cm_feed_select_cards"]["do"][0]["press_ms"] == 1500
    assert by_id["cm_feed_select_cards"]["do"][1]["press_ms"] == 1500
    assert by_id["cm_feed_select_cards"]["do"][1]["recheck"] is False

    # Opt-in mission refresh via I_CM_SWITCH when preferred OCR title is absent on initial board
    sw_asks = []
    res_sw, _ = _run(
        cm, stage / "resources",
        [
            ("I_CM_RECORDS", "I_CM_SWITCH"),
            ("I_CM_RECORDS",),
            ("I_CM_PRESENT", "I_CM_MATTER"),
            ("I_UI_REWARD",),
            ("I_CM_RECORDS", "I_UI_BACK_RED"),
            ("I_CM_SHRINE",),
        ],
        params={
            "cm_confirm_donate": True, "cm_prefer_slot": 2,
            "cm_ocr_prefer_title": "御灵", "cm_switch_mission_enable": True, "cm_max_switches": 3,
        },
        initial_vars={"cm_phase": "check_count"},
        ocr_single=lambda img, roi: (
            ("10/30" if int(img[0, 0, 0]) - 20 < 4 else "11/30")
            if roi[0] == 1105
            else ("御灵" if int(img[0, 0, 0]) - 20 == 1 and roi[0] == 217 else "")
        ),
        confirm=lambda c, _d: (sw_asks.append(c) or True),
    )
    assert res_sw.status == "success", res_sw.summary()
    assert res_sw.variables["cm_switches"] == 1
    assert res_sw.variables["cm_selected_slot"] == 1 and sw_asks == ["分解"]


def test_kekkai_activation_and_restart(oas_stage):
    stage, src, folder = oas_stage
    ka = compile_kekkai_activation_candidate(src, folder)
    res_gate, dev = _run(
        ka, stage / "resources", [("I_A_ACTIVATE_YELLOW",)],
        initial_vars={"ka_phase": "check_card"},
    )
    assert res_gate.status == "failed" and "ka_confirm_activate" in res_gate.reason
    assert dev.inputs == []

    res_ka_deny, dev_ka_deny = _run(
        ka, stage / "resources", [("I_A_ACTIVATE_YELLOW",)],
        params={"ka_confirm_activate": True},
        initial_vars={"ka_phase": "check_card"},
        confirm=lambda _c, _d: False,
    )
    assert res_ka_deny.status == "failed" and res_ka_deny.failure_kind == "confirm_denied"
    assert dev_ka_deny.inputs == []

    ka_asks = []
    res_ka_ok, _ = _run(
        ka, stage / "resources",
        [("I_A_ACTIVATE_YELLOW",), ("I_A_INVITE", "I_UI_BACK_RED"), ("I_REALM_SHIN", "I_CHECK_MAIN")],
        params={"ka_confirm_activate": True},
        initial_vars={"ka_phase": "check_card"},
        ocr_single={1: "04:00:00"},
        confirm=lambda c, _d: (ka_asks.append(c) or True),
    )
    assert res_ka_ok.status == "success" and res_ka_ok.variables["ka_activated"] is True and ka_asks == ["购买"]

    res_active, _ = _run(
        ka, stage / "resources",
        [("I_A_INVITE", "I_UI_BACK_RED"), ("I_REALM_SHIN", "I_CHECK_MAIN")],
        initial_vars={"ka_phase": "check_card"},
        ocr_single={0: "02:30:00"},
    )
    assert res_active.status == "success", res_active.summary()
    assert res_active.oas_schedule == "KekkaiActivation"
    assert res_active.oas_target is not None and res_active.oas_target[0] == 9000

    # Harvest before + Taiko filter + 4-star selection + sensitive activate
    ka_asks2 = []
    res_ka_full, _ = _run(
        ka, stage / "resources",
        [
            ("I_A_HARVEST_KAIKO_6", "I_REALM_SHIN"),
            ("I_REALM_SHIN", "I_SHI_CARD"),
            ("I_A_CHECK_CARD", "I_A_EMPTY"),
            ("I_A_EMPTY", "I_A_CARD_KAIKO"),
            ("I_A_EMPTY", "I_CARDS_KAIKO_4"),
            ("I_A_ACTIVATE_YELLOW",),
            ("I_A_INVITE", "I_UI_BACK_RED"),
            ("I_REALM_SHIN", "I_CHECK_MAIN"),
        ],
        params={"ka_harvest_before": True, "ka_confirm_activate": True, "ka_card_type": "太鼓"},
        initial_vars={"ka_phase": "enter_realm"},
        ocr_single={6: "03:00:00"},
        confirm=lambda c, _d: (ka_asks2.append(c) or True),
    )
    assert res_ka_full.status == "success", res_ka_full.summary()
    assert res_ka_full.variables["ka_harvested"] == 1 and res_ka_full.variables["ka_filter_selected"] is True
    assert res_ka_full.variables["ka_activated"] is True and ka_asks2 == ["购买"]
    assert res_ka_full.oas_target is not None and res_ka_full.oas_target[0] == 10800

    # Card not found after swipe limit -> 180m retry schedule
    res_ka_nf, _ = _run(
        ka, stage / "resources",
        [("I_A_EMPTY",), ("I_A_EMPTY", "I_UI_BACK_RED"), ("I_REALM_SHIN", "I_CHECK_MAIN")],
        params={"ka_confirm_activate": True, "ka_max_swipes": 1, "ka_not_found_delay_s": 10800},
        initial_vars={"ka_phase": "check_card", "ka_filter_selected": True},
    )
    assert res_ka_nf.status == "success", res_ka_nf.summary()
    assert res_ka_nf.variables["ka_swipes"] == 1 and res_ka_nf.variables["ka_exit_reason"] == "card_not_found"
    assert res_ka_nf.oas_target is not None and res_ka_nf.oas_target[0] == 10800

    # Growth shikigami replacement before and after card check (ka_exchange_before + ka_exchange_max)
    res_ka_gr, _ = _run(
        ka, stage / "resources",
        [
            ("I_REALM_SHIN", "I_SHI_GROWN"),
            ("I_RS_RECORDS_SHIKI", "I_RS_LEVEL_MAX"),
            ("I_RS_RECORDS_SHIKI", "I_RS_N_SELECTED", "I_RS_NO_ADD", "I_DETECT_EMPTY_1"),
            ("I_RS_RECORDS_SHIKI", "I_UI_BACK_BLUE"),
            ("I_REALM_SHIN", "I_SHI_GROWN", "I_SHI_CARD"),
            ("I_A_CHECK_CARD", "I_A_INVITE", "I_UI_BACK_RED"),
            ("I_REALM_SHIN", "I_SHI_GROWN"),
            ("I_RS_RECORDS_SHIKI", "I_UI_BACK_BLUE"),
            ("I_REALM_SHIN", "I_SHI_GROWN", "I_CHECK_MAIN"),
        ],
        params={"ka_exchange_before": True, "ka_exchange_max": True, "ka_shikigami_class": "N"},
        initial_vars={"ka_phase": "enter_realm"},
        ocr_single={5: "02:00:00"},
    )
    assert res_ka_gr.status == "success", res_ka_gr.summary()
    assert res_ka_gr.variables["ka_growth_exchanged_before"] is True
    assert res_ka_gr.variables["ka_growth_exchanged_max"] is True
    assert res_ka_gr.variables["ka_exit_reason"] == "already_active"
    assert res_ka_gr.oas_target is not None and res_ka_gr.oas_target[0] == 7200

    res_ka_tl, _ = _run(
        ka, stage / "resources",
        [("I_A_EMPTY",), ("I_A_EMPTY", "I_UI_BACK_RED"), ("I_REALM_SHIN", "I_CHECK_MAIN")],
        params={"ka_confirm_activate": True, "ka_max_swipes": 5, "ka_limit_seconds": 1, "ka_not_found_delay_s": 10800},
        initial_vars={"ka_phase": "check_card", "ka_filter_selected": True},
    )
    assert res_ka_tl.status == "success" and res_ka_tl.variables["ka_exit_reason"] == "time_limit"
    assert res_ka_tl.oas_target is not None and res_ka_tl.oas_target[0] == 10800

    rs = compile_restart_candidate(src, folder)
    res_wed, _ = _run(rs, stage / "resources", [()], params={"rs_wednesday_maintenance": True})
    assert res_wed.status == "failed" and "维护" in res_wed.reason

    res_ok, _ = _run(rs, stage / "resources", [()], initial_vars={"rs_phase": "login", "rs_login_returned": True})
    assert res_ok.status == "success" and res_ok.oas_schedule == "Restart"

    res_wed_sched, _ = _run(
        rs, stage / "resources", [()],
        params={"rs_wednesday_maintenance": True, "rs_wednesday_delay_s": 7200},
    )
    assert res_wed_sched.status == "success" and res_wed_sched.oas_target is not None and res_wed_sched.oas_target[0] == 7200

    res_ap_sched, _ = _run(
        rs, stage / "resources", [()],
        params={"rs_ap_delay_s": 28800},
        initial_vars={"rs_phase": "login", "rs_login_returned": True},
    )
    assert res_ap_sched.status == "success" and res_ap_sched.oas_target is not None and res_ap_sched.oas_target[0] == 28800

    res_rs_tl, _ = _run(
        rs, stage / "resources", [()],
        params={"rs_limit_seconds": 1, "rs_ap_delay_s": 14400},
        initial_vars={"rs_phase": "login"},
    )
    assert res_rs_tl.status == "success", res_rs_tl.summary()
    assert res_rs_tl.variables["rs_exit_reason"] == "time_limit"
    assert res_rs_tl.oas_target is not None and res_rs_tl.oas_target[0] == 14400
