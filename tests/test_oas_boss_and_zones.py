"""Offline unit tests for OAS Hunt, DemonRetreat, TrueOrochi, and Secret."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_boss_and_zones import (
    compile_demon_retreat_candidate,
    compile_hunt_candidate,
    compile_secret_candidate,
    compile_true_orochi_candidate,
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
    for task in (
        "Hunt", "DemonRetreat", "TrueOrochi", "Orochi", "Secret", "WeeklyTrifles",
        "Component_GeneralBuff", "Component_GeneralRoom", "Component_GeneralInvite", "Component_SwitchSoul",
    ):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_full=None, ocr_int=None,
         ocr_single=None, text_reader=None, wall_clock=None, max_seconds=60, advance_on_input=True):
    wf = load_workflow(raw, [root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, *_a, **_kw):
        vis = frames[int(image[0, 0, 0]) - 20]
        hit = bool(set(vis) & aliases.get(Path(path).resolve(), set()))
        return hit, float(hit), (200, 120, 40, 32)

    def full_ocr(image, region, keyword, score=0.6, **_kw):
        if callable(ocr_full):
            return ocr_full(image, region, keyword, score)
        idx = int(image[0, 0, 0]) - 20
        for kw, box in (ocr_full or {}).get(idx, []):
            if kw == keyword:
                return box if isinstance(box, FullOcrArea) else FullOcrArea(box, keyword_complete=True)
        return FullOcrArea((0, 0, 0, 0), keyword_complete=False)

    def read_int(image, region):
        if callable(ocr_int):
            return ocr_int(image, region)
        return (ocr_int or {}).get(int(image[0, 0, 0]) - 20, 0)

    def read_single(image, region, score=0.6):
        if callable(ocr_single):
            return ocr_single(image, region)
        return (ocr_single or {}).get(int(image[0, 0, 0]) - 20, "")

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=advance_on_input)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=max_seconds,
            params=params, full_ocr_reader=full_ocr, ocr_reader=read_int,
            single_ocr_reader=read_single, text_reader=text_reader, initial_vars=initial_vars,
            wall_clock=wall_clock,
        ).run()
    return res, device


def test_hunt_kirin_and_netherworld_paths(oas_stage):
    stage, src, folder = oas_stage
    hu = compile_hunt_candidate(src, folder)
    res_k, _ = _run(
        hu, stage / "resources",
        [("I_KIRIN_CHALLAGE",), ("I_PREPARE_HIGHLIGHT",), ("I_BATTLE_INFO", "I_WIN"), ("I_KIRIN_END",)],
        initial_vars={"hu_phase": "kirin_enter"},
    )
    assert res_k.status == "success", res_k.summary()
    assert res_k.oas_schedule == "Hunt" and res_k.variables["hu_wins"] == 1

    res_nw, _ = _run(
        hu, stage / "resources",
        [("I_NW_DONE", "I_UI_BACK_RED"), ("I_CHECK_GUILD",)],
        params={"hu_kirin_day": False},
        initial_vars={"hu_phase": "nw_enter"},
    )
    assert res_nw.status == "success" and res_nw.variables["hu_exit_reason"] == "nw_already_done"

    res_sched, _ = _run(
        hu, stage / "resources", [()],
        params={"hu_calendar_mode": "manual", "hu_in_window": False, "hu_next_delay_s": 14400},
    )
    assert res_sched.status == "success" and res_sched.variables["hu_exit_reason"] == "outside_window"
    assert res_sched.oas_target is not None and res_sched.oas_target[0] == 14400

    res_hu_tl, _ = _run(
        hu, stage / "resources", [("I_KIRIN_CHALLAGE",), ()],
        params={"hu_calendar_mode": "manual", "hu_limit_seconds": 1, "hu_next_delay_s": 14400},
        initial_vars={"hu_phase": "kirin_enter"},
    )
    assert res_hu_tl.status == "success" and res_hu_tl.variables["hu_exit_reason"] == "time_limit"
    assert res_hu_tl.oas_target is not None and res_hu_tl.oas_target[0] == 14400


def test_hunt_source_calendar_boundaries(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_hunt_candidate(src, folder)
    probe = {**raw, "stop_when": "hu_phase == 'nav_kirin' or hu_phase == 'nav_nw'"}
    params = {"hu_kirin_time_s": 69300, "hu_netherworld_time_s": 70200}
    cases = [
        (datetime(2026, 11, 26, 5, 59, 59), "calendar_today", (69300, 0)),
        (datetime(2026, 11, 26, 6), "nav_kirin", None),
        (datetime(2026, 11, 26, 23), "nav_kirin", None),
        (datetime(2026, 11, 26, 23, 0, 0, 1000), "calendar_tomorrow", (70200, 1)),
        (datetime(2026, 11, 27, 16, 59, 59), "calendar_today", (70200, 0)),
        (datetime(2026, 11, 27, 17), "nav_nw", None),
        (datetime(2026, 11, 29, 23, 0, 1), "calendar_tomorrow", (69300, 1)),
    ]
    for start, phase, schedule in cases:
        result, device = _run(probe, stage / "resources", [()], params=params,
                              wall_clock=start.timestamp)
        assert result.status == "success" and not device.inputs, (start, result.summary())
        assert result.variables["hu_phase"] == phase and result.oas_calendar_target == schedule

    result, _ = _run(raw, stage / "resources", [("I_NW_DONE", "I_UI_BACK_RED"), ("I_CHECK_GUILD",)],
                     params=params, initial_vars={"hu_phase": "nw_enter"},
                     wall_clock=datetime(2026, 11, 29, 20).timestamp)
    assert result.status == "success" and result.oas_calendar_target == (69300, 1)


def test_hunt_netherworld_fire_requires_room_and_a_battle_transition(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_hunt_candidate(src, folder)
    probe = {**raw, "stop_when": "hu_phase == 'battle'"}
    resource_root = stage / "resources"
    initial = {"hu_phase": "nw_enter"}
    result, device = _run(probe, resource_root, [("I_FIRE",)], initial_vars=initial)
    assert result.status != "success" and not device.inputs

    room = ("I_FIRE", "I_GI_EMOJI_1")
    result, device = _run(probe, resource_root, [room, ("I_PREPARE_HIGHLIGHT",)], initial_vars=initial)
    assert result.status == "success" and result.variables["hu_phase"] == "battle"
    assert len(device.inputs) == 1

    result, device = _run(probe, resource_root, [room], initial_vars=initial)
    assert result.failed_state == "hu_nw_room_start_timeout" and len(device.inputs) == 3


def test_hunt_wait_closes_only_the_observed_result_and_services_late_ready(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_hunt_candidate(src, folder)
    initial = {"hu_phase": "battle", "hu_battle_phase": "battle_wait"}
    result, device = _run(raw, stage / "resources", [
        ("I_PREPARE_HIGHLIGHT",), ("I_WIN", "I_FALSE"), ("I_WIN",), ("I_REWARD",),
    ], initial_vars=initial)
    assert result.status == "success" and result.variables["hu_wins"] == 1, result.summary()
    assert result.variables["hu_battle_result_marker"] == "I_WIN"
    assert len(device.inputs) == 3

    result, device = _run(raw, stage / "resources", [("I_FALSE",), ("I_NW_DONE",)], initial_vars=initial)
    assert result.status == "success" and result.variables["hu_wins"] == 0, result.summary()
    assert result.variables["hu_battle_result_marker"] == "I_FALSE"
    assert len(device.inputs) == 1

    result, device = _run(raw, stage / "resources", [("I_WIN",), ("I_REWARD",)],
                          initial_vars=initial, advance_on_input=False)
    assert result.status == "success" and result.variables["hu_wins"] == 1, result.summary()
    assert not device.inputs


def test_hunt_wait_does_not_treat_reward_alone_as_a_win(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_hunt_candidate(src, folder)
    result, device = _run(raw, stage / "resources", [("I_REWARD",)], max_seconds=485,
                          initial_vars={"hu_phase": "battle", "hu_battle_phase": "battle_wait"})
    assert result.failed_state == "hu_battle_hunt_wait_timeout", result.summary()
    assert result.variables["hu_battle_hunt_reset_stuck"] is True
    assert result.variables["hu_battle_outcome_known"] is False and not device.inputs
    assert result.history[-1][0] >= 480


def test_hunt_selects_mode_before_switch_soul_and_uses_independent_battle_settings(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_hunt_candidate(src, folder)
    resources = stage / "resources"
    params = {"hu_calendar_mode": "manual", "hu_kirin_soul_group": 2, "hu_kirin_soul_team": 3,
              "hu_netherworld_soul_group": 6, "hu_netherworld_soul_team": 4,
              "hu_kirin_preset_group": 2, "hu_netherworld_preset_group": 6}
    preset_probe = {**raw, "stop_when": "hu_phase == 'soul_records' or hu_phase == 'records_only'"}
    for kirin, expected, phase, frames, inputs in (
        (True, (2, 3), "kirin_enter", [("I_PREPARE_HIGHLIGHT",)], 0),
        (False, (6, 4), "nw_enter", [("I_GI_SPEAK", "I_FIRE"), ("I_BATTLE_INFO",)], 1),
    ):
        config = {**params, "hu_kirin_day": kirin}
        result, device = _run(preset_probe, resources, [()], params=config)
        assert result.variables["hu_phase"] == "soul_records" and not device.inputs
        assert (result.variables["hu_soul_group"], result.variables["hu_soul_team"]) == expected
        probe = {**raw, "stop_when": "hu_phase == 'battle'"}
        result, device = _run(probe, resources, frames, params=config, initial_vars={"hu_phase": phase})
        assert result.status == "success" and len(device.inputs) == inputs, result.summary()
        assert result.variables["hu_battle_config_preset_group"] == expected[0]

    result, device = _run(preset_probe, resources, [()], params={**params, "hu_netherworld_soul_group": -1,
                          "hu_netherworld_soul_team": -1, "hu_kirin_day": False})
    assert result.variables["hu_phase"] == "records_only" and not device.inputs


def test_demon_retreat_saturday_battle_and_reward(oas_stage):
    stage, src, folder = oas_stage
    dr = compile_demon_retreat_candidate(src, folder)
    res_skip, _ = _run(dr, stage / "resources", [()], params={"dr_is_saturday": False})
    assert res_skip.status == "success" and res_skip.oas_schedule == "DemonRetreat"

    res, _ = _run(
        dr, stage / "resources",
        [("I_HUNT_CHECK", "I_ENTER_FIRE"), ("I_BATTLE_INFO", "I_WIN"), ("I_REWARD_ALL",), ("I_CHECK_MAIN",)],
        initial_vars={"dr_phase": "enter_shrine"},
    )
    assert res.status == "success", res.summary()
    assert res.variables["dr_reward_claimed"] is True and res.variables["dr_wins"] == 1

    # 3-round DemonRetreat + Saturday custom_next_run target schedule
    res_dr3, _ = _run(
        dr, stage / "resources",
        [
            ("I_HUNT_CHECK", "I_ENTER_FIRE"), ("I_BATTLE_INFO", "I_WIN"),
            ("I_ENTER_FIRE",), ("I_BATTLE_INFO", "I_WIN"),
            ("I_ENTER_FIRE",), ("I_BATTLE_INFO", "I_WIN"),
            ("I_REWARD_ALL",), ("I_CHECK_MAIN",),
        ],
        params={"dr_max_rounds": 3, "dr_next_saturday_delay_s": 604800},
        initial_vars={"dr_phase": "enter_shrine"},
    )
    assert res_dr3.status == "success", res_dr3.summary()
    assert res_dr3.variables["dr_rounds"] == 3 and res_dr3.variables["dr_wins"] == 3
    assert res_dr3.oas_target is not None and res_dr3.oas_target[0] == 604800

    res_dr_tl, _ = _run(
        dr, stage / "resources", [("I_SHRINE",), ("I_CHECK_MAIN",)],
        params={"dr_limit_seconds": 1, "dr_next_saturday_delay_s": 604800},
        initial_vars={"dr_phase": "enter_shrine"},
    )
    assert res_dr_tl.status == "success" and res_dr_tl.variables["dr_exit_reason"] == "time_limit"
    assert res_dr_tl.oas_target is not None and res_dr_tl.oas_target[0] == 604800

    # Partial "集" (keyword_complete=False) must NOT falsely stall in gather_wait when I_ENTER_FIRE is present
    res_dr_partial, _ = _run(
        dr, stage / "resources",
        [("I_DEMON_GATHER", "I_ENTER_FIRE"), ("I_BATTLE_INFO", "I_WIN"), ("I_REWARD_ALL",), ("I_CHECK_MAIN",)],
        initial_vars={"dr_phase": "check_gather"},
        ocr_full={0: [("集结", FullOcrArea((120, 200, 60, 24), keyword_complete=False))]},
    )
    assert res_dr_partial.status == "success" and res_dr_partial.variables["dr_wins"] == 1


def test_true_orochi_and_secret_flows(oas_stage):
    stage, src, folder = oas_stage
    to = compile_true_orochi_candidate(src, folder)
    res_to, _ = _run(
        to, stage / "resources",
        [
            ("I_FIND_TS",), ("I_ST_CREATE_ROOM", "I_ENSURE_PRIVATE"),
            ("I_ST_FIRE_PREPARE",), ("I_ST_FRAME",), ("I_GREED_GHOST",), ("I_CHECK_OROCHI",),
        ],
        initial_vars={"to_phase": "check_ts"},
    )
    assert res_to.status == "success", res_to.summary()
    assert res_to.oas_schedule == "TrueOrochi" and res_to.variables["to_true_runs"] == 1

    # Layer.TEN selection + unlock + second stored True Orochi entry loop
    res_to2, _ = _run(
        to, stage / "resources",
        [
            ("I_OROCHI_FIRE", "I_OROCHI_LOCK"),
            ("I_OROCHI_LOCK",),
            ("I_FIND_TS",),
            ("I_ST_CREATE_ROOM", "I_ENSURE_PRIVATE"),
            ("I_ST_FIRE_PREPARE",),
            ("I_GREED_GHOST",),
            ("I_OROCHI_CHECK_10", "I_FIND_TS"),
            ("I_ST_CREATE_ROOM", "I_ENSURE_PRIVATE"),
            ("I_ST_FIRE_PREPARE",),
            ("I_GREED_GHOST",),
            ("I_CHECK_OROCHI",),
        ],
        params={"to_select_layer_ten": True, "to_max_true_runs": 2},
        initial_vars={"to_phase": "check_ts"},
        text_reader=lambda _img, roi: [("拾层", roi[0] + 24, roi[1] + 100)],
    )
    assert res_to2.status == "success", res_to2.summary()
    assert res_to2.variables["to_layer_ready"] is True and res_to2.variables["to_true_runs"] == 2

    res_to_mon, _ = _run(
        to, stage / "resources", [()],
        params={"to_next_monday_delay_s": 604800},
        initial_vars={"to_phase": "inspect_module"},
    )
    assert res_to_mon.status == "success" and res_to_mon.variables["to_exit_reason"] == "weekly_done"
    assert res_to_mon.oas_target is not None and res_to_mon.oas_target[0] == 604800

    res_to_tl, _ = _run(
        to, stage / "resources", [("I_ST_FRAME",), ()],
        params={"to_limit_seconds": 1, "to_next_monday_delay_s": 604800},
        initial_vars={"to_phase": "ts_fight"},
    )
    assert res_to_tl.status == "success" and res_to_tl.variables["to_exit_reason"] == "time_limit"
    assert res_to_tl.oas_target is not None and res_to_tl.oas_target[0] == 604800

    se = compile_secret_candidate(src, folder)
    res_se, _ = _run(
        se, stage / "resources",
        [
            ("I_SE_FIRE", "I_SE_PLACEMENT"),
            ("I_SE_FIRE",),
            ("I_SE_BATTLE_WIN",),
            ("I_SE_FINISHED_1", "I_UI_BACK_BLUE"),
            ("I_UI_BACK_YELLOW",),
            ("I_CHECK_MAIN",),
        ],
        initial_vars={"se_phase": "enter_zone"},
        ocr_full={0: [("未通关", (300, 200, 80, 30))]},
    )
    assert res_se.status == "success", res_se.summary()
    assert res_se.oas_schedule == "Secret" and res_se.variables["se_wins"] == 1

    # Secret layer-9 gate via O_SE_JADE (63 = 9*7) + weekly total-time clear + gold_50 courtyard buff
    res_l9, _ = _run(
        se, stage / "resources",
        [("I_SE_FIRE", "I_UI_BACK_BLUE"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"se_check_layer_ocr": True, "se_layer_9": False},
        initial_vars={"se_phase": "find_layer"},
        ocr_int={0: 63},
    )
    assert res_l9.status == "success" and res_l9.variables["se_exit_reason"] == "layer_9_disabled"

    res_tt, _ = _run(
        se, stage / "resources",
        [("I_SE_FIRE", "I_UI_BACK_BLUE"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"se_check_layer_ocr": True},
        initial_vars={"se_phase": "find_layer"},
        ocr_single={0: "00:05:12"},
    )
    assert res_tt.status == "success" and res_tt.variables["se_exit_reason"] == "total_time_cleared"
    assert res_tt.variables["se_total_time"] == 312

    # Unpassed Secret shows "尚未通关" in O_SE_TOTAL_TIME -> must NOT falsely exit as cleared
    res_unpassed, dev_unpassed = _run(
        se, stage / "resources",
        [("I_SE_FIRE",), ("I_SE_FINISHED_1", "I_UI_BACK_BLUE"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"se_check_layer_ocr": True},
        initial_vars={"se_phase": "find_layer"},
        ocr_single={0: "尚未通关"},
    )
    assert res_unpassed.status == "success"
    assert res_unpassed.variables["se_exit_reason"] == "finished_1"
    assert res_unpassed.variables["se_total_time"] == -1
    assert res_unpassed.variables["se_swipes"] == 1
    assert dev_unpassed.inputs[0][0] == "swipe"

    # Partial "已通关" fallback (keyword_complete=False) must NOT click a cleared layer
    res_partial_np, dev_partial_np = _run(
        se, stage / "resources",
        [("I_SE_FIRE",), ("I_SE_FINISHED_1", "I_UI_BACK_BLUE"), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        initial_vars={"se_phase": "find_layer"},
        ocr_full={0: [("未通关", FullOcrArea((300, 200, 80, 30), keyword_complete=False))]},
    )
    assert res_partial_np.status == "success" and res_partial_np.variables["se_battles"] == 0
    assert res_partial_np.variables["se_swipes"] == 1 and dev_partial_np.inputs[0][0] == "swipe"

    courtyard = ("I_CHECK_MAIN", "I_BUFF_1")
    panel = ("I_CLOUD", "I_BUFF_1", "I_AWAKE")
    res_buff, dev_buff = _run(
        {**se, "stop_when": "se_phase == 'navigate'"},
        stage / "resources",
        [courtyard, (*panel, "I_CLOSE_RED"), (*panel, "I_OPEN_YELLOW"), courtyard],
        params={"se_gold_50": True},
        ocr_full=lambda img, _r, kw, _s: FullOcrArea((440, 140 + 20 * (int(img[0, 0, 0]) - 21), 180, 15), keyword_complete=True),
    )
    assert res_buff.status == "success" and len(dev_buff.inputs) == 3
    assert res_buff.variables["se_buff_before_select_0_helper_status"] == "observed"

    res_se_mon, _ = _run(
        se, stage / "resources", [()],
        params={"se_monday_before_8": True, "se_monday_open_delay_s": 7200},
    )
    assert res_se_mon.status == "success" and res_se_mon.variables["se_exit_reason"] == "monday_before_8"
    assert res_se_mon.oas_target is not None and res_se_mon.oas_target[0] == 7200

    res_se_tl, _ = _run(
        se, stage / "resources", [("I_SE_FIRE",), ("I_SE_FIRE", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"se_limit_seconds": 1, "se_next_monday_delay_s": 604800},
        initial_vars={"se_phase": "find_layer"},
    )
    assert res_se_tl.status == "success" and res_se_tl.variables["se_exit_reason"] == "time_limit"
    assert res_se_tl.oas_target is not None and res_se_tl.oas_target[0] == 604800
