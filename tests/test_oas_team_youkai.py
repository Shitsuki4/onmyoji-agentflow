"""Offline unit tests for OAS ExperienceYoukai, GoldYoukai, Nian, and Tako."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_team_youkai import (
    compile_experience_youkai_candidate,
    compile_gold_youkai_candidate,
    compile_nian_candidate,
    compile_tako_candidate,
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
        "ExperienceYoukai", "GoldYoukai", "Nian",
        "Component_GeneralBuff", "Component_GeneralRoom", "Component_GeneralInvite", "Component_SwitchSoul",
    ):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, full_ocr_reader=None, single_ocr_reader=None, boxes=None):
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

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, initial_vars=initial_vars, full_ocr_reader=full_ocr_reader,
            single_ocr_reader=single_ocr_reader or (lambda *_a: ""),
        ).run()
    return res, device


def _buff_row_reader(image, _roi, keyword, *_args):
    assert "金币" in keyword or "经验" in keyword
    index = int(image[0, 0, 0]) - 20
    return FullOcrArea((440, 140 + 20 * (index - 1), 180, 15), keyword_complete=True)


def test_experience_and_gold_youkai_room_battle_and_buff_binding(oas_stage):
    stage, src, folder = oas_stage
    courtyard = ("I_CHECK_MAIN", "I_BUFF_1")
    panel = ("I_CLOUD", "I_BUFF_1", "I_AWAKE")

    ey = compile_experience_youkai_candidate(src, folder)
    res_ey_open, dev_ey_open = _run(
        {**ey, "stop_when": "ey_phase == 'goto_team'"},
        stage / "resources",
        [courtyard, (*panel, "I_CLOSE_RED"), (*panel, "I_OPEN_YELLOW"), courtyard],
        params={"ey_buff_exp_50": True},
        full_ocr_reader=_buff_row_reader,
    )
    assert res_ey_open.status == "success" and len(dev_ey_open.inputs) == 3
    assert res_ey_open.variables["ey_buff_before_select_0_helper_status"] == "observed"
    assert res_ey_open.variables["ey_buff_before_select_1_helper_status"] == "unobserved"

    res_ey_close, dev_ey_close = _run(
        ey, stage / "resources",
        [courtyard, (*panel, "I_OPEN_YELLOW"), (*panel, "I_CLOSE_RED"), courtyard],
        params={"ey_buff_exp_50": True},
        initial_vars={"ey_phase": "buff_after"},
        full_ocr_reader=_buff_row_reader,
    )
    assert res_ey_close.status == "success" and res_ey_close.oas_schedule == "ExperienceYoukai"
    assert len(dev_ey_close.inputs) == 3 and res_ey_close.variables["ey_buff_after_select_0_helper_status"] == "observed"

    frames = [
        ("I_CREATE_ROOM",),
        ("I_CREATE_ENSURE", "I_ENSURE_PUBLIC"),
        ("I_FIRE",),  # teammate joined (no I_ADD_5_1)
        ("I_EXP_WIN",),
        ("I_CHECK_MAIN",),
    ]
    res, dev = _run(
        ey, stage / "resources", frames,
        params={"ey_max_runs": 1},
        initial_vars={"ey_phase": "create_room"},
        boxes={"I_CREATE_ROOM": (450, 595, 177, 58)},
    )
    assert res.status == "success", res.summary()
    assert res.oas_schedule == "ExperienceYoukai"
    assert res.variables["ey_runs"] == 1 and res.variables["ey_wins"] == 1
    assert 450 <= dev.inputs[0][1] <= 627 and 595 <= dev.inputs[0][2] <= 653

    gy = compile_gold_youkai_candidate(src, folder)
    res_gy_open, dev_gy_open = _run(
        {**gy, "stop_when": "gy_phase == 'goto_team'"},
        stage / "resources",
        [courtyard, (*panel, "I_CLOSE_RED"), (*panel, "I_OPEN_YELLOW"), courtyard],
        params={"gy_buff_gold_100": True},
        full_ocr_reader=_buff_row_reader,
    )
    assert res_gy_open.status == "success" and len(dev_gy_open.inputs) == 3
    assert res_gy_open.variables["gy_buff_before_select_1_helper_status"] == "observed"

    frames_g = [
        ("I_CREATE_ROOM",),
        ("I_CREATE_ENSURE", "I_ENSURE_PUBLIC"),
        ("I_FIRE",),
        ("I_GOLD_WIN",),
        ("I_CHECK_MAIN",),
    ]
    res_g, _ = _run(
        gy, stage / "resources", frames_g,
        params={"gy_max_runs": 1},
        initial_vars={"gy_phase": "create_room"},
    )
    assert res_g.status == "success", res_g.summary()
    assert res_g.oas_schedule == "GoldYoukai"
    assert res_g.variables["gy_wins"] == 1

    # ExperienceYoukai & GoldYoukai wall-clock time-limit + target schedule
    res_ey_tl, _ = _run(
        ey, stage / "resources", [("I_EXP_WIN",), ("I_CHECK_MAIN",)],
        params={"ey_max_runs": 2, "ey_limit_seconds": 1, "ey_next_delay_s": 14400},
        initial_vars={"ey_phase": "battle"},
    )
    assert res_ey_tl.status == "success", res_ey_tl.summary()
    assert res_ey_tl.variables["ey_exit_reason"] == "time_limit" and res_ey_tl.oas_target[0] == 14400

    res_gy_sched, _ = _run(
        gy, stage / "resources", [("I_CHECK_MAIN",)],
        params={"gy_max_runs": 1, "gy_next_delay_s": 21600},
        initial_vars={"gy_phase": "goto_team", "gy_runs": 1},
    )
    assert res_gy_sched.status == "success", res_gy_sched.summary()
    assert res_gy_sched.variables["gy_exit_reason"] == "count" and res_gy_sched.oas_target[0] == 21600

    # Partial "妖怪" fallback from wrong zone must NOT click ExperienceYoukai zone
    res_ey_partial, dev_ey_partial = _run(
        {**ey, "stop_when": "ey_phase == 'create_room'"},
        stage / "resources",
        [("I_CREATE_ROOM",)],
        initial_vars={"ey_phase": "select_zone"},
        full_ocr_reader=lambda _img, _roi, kw, *_a: FullOcrArea((220, 240, 90, 28), keyword_complete=False)
        if kw == "经验妖怪" else FullOcrArea((0, 0, 0, 0), keyword_complete=False),
    )
    assert res_ey_partial.status == "success" and dev_ey_partial.inputs == []


def test_nian_and_tako_flows(oas_stage):
    stage, src, folder = oas_stage
    courtyard = ("I_CHECK_MAIN", "I_BUFF_1")
    panel = ("I_CLOUD", "I_BUFF_1", "I_AWAKE")

    ni = compile_nian_candidate(src, folder)
    res_ni_open, dev_ni_open = _run(
        {**ni, "stop_when": "ni_phase == 'navigate'"},
        stage / "resources",
        [courtyard, (*panel, "I_CLOSE_RED"), (*panel, "I_OPEN_YELLOW"), courtyard],
        params={"ni_buff_gold_50": True},
        full_ocr_reader=_buff_row_reader,
    )
    assert res_ni_open.status == "success" and len(dev_ni_open.inputs) == 3
    assert res_ni_open.variables["ni_buff_before_select_0_helper_status"] == "observed"

    res_ni, _ = _run(
        ni, stage / "resources",
        [("I_GR_AUTO_MATCH",), ("I_N_WAITING",), ("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_TEAM",)],
        params={"ni_match_timeout_seconds": 1},
        initial_vars={"ni_phase": "check_cd"},
    )
    assert res_ni.status == "success", res_ni.summary()
    assert res_ni.oas_schedule == "Nian"

    res_ni_cd, _ = _run(
        ni, stage / "resources",
        [("I_N_CHECK",)],
        params={"ni_cd_delay_s": 7200},
        initial_vars={"ni_phase": "check_cd"},
        full_ocr_reader=lambda _img, _roi, kw, *_a: FullOcrArea((612, 251, 120, 35), keyword_complete=True)
        if kw == "再次挑战" else None,
    )
    assert res_ni_cd.status == "success", res_ni_cd.summary()
    assert res_ni_cd.oas_schedule == "Nian" and res_ni_cd.variables["ni_exit_reason"] == "cooldown_banner"
    assert res_ni_cd.oas_target is not None and res_ni_cd.oas_target[0] == 7200

    res_ni_cd_ocr, _ = _run(
        ni, stage / "resources",
        [("I_N_CHECK",)],
        params={"ni_cd_delay_s": 7200},
        initial_vars={"ni_phase": "check_cd"},
        full_ocr_reader=lambda _img, _roi, kw, *_a: FullOcrArea((612, 251, 120, 35), keyword_complete=True)
        if kw == "再次挑战" else None,
        single_ocr_reader=lambda *_a: "3时25分后可",
    )
    assert res_ni_cd_ocr.status == "success", res_ni_cd_ocr.summary()
    assert res_ni_cd_ocr.oas_schedule == "Nian"
    assert res_ni_cd_ocr.variables["ni_exit_reason"] == "cooldown_banner_ocr"
    assert res_ni_cd_ocr.variables["ni_cd_ocr_s"] == 12300
    assert res_ni_cd_ocr.oas_target is not None and res_ni_cd_ocr.oas_target[0] == 12300

    res_ni_tl, _ = _run(
        ni, stage / "resources", [("I_GR_AUTO_MATCH",), ()],
        params={"ni_limit_seconds": 1},
        initial_vars={"ni_phase": "check_cd"},
    )
    assert res_ni_tl.status == "success" and res_ni_tl.variables["ni_exit_reason"] == "time_limit"

    # Partial "挑战" (keyword_complete=False) must NOT falsely trigger cooldown banner exit
    res_ni_part, dev_ni_part = _run(
        ni, stage / "resources",
        [("I_N_CHECK", "I_GR_AUTO_MATCH"), ("I_N_WAITING",), ("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_TEAM",)],
        params={"ni_match_timeout_seconds": 1},
        initial_vars={"ni_phase": "check_cd"},
        full_ocr_reader=lambda _img, _roi, kw, *_a: FullOcrArea((612, 251, 120, 35), keyword_complete=False)
        if kw == "再次挑战" else FullOcrArea((0, 0, 0, 0), keyword_complete=False),
    )
    assert res_ni_part.status == "success" and res_ni_part.variables["ni_exit_reason"] != "cooldown_banner"
    assert len(dev_ni_part.inputs) >= 1

    tk = compile_tako_candidate(src, folder)
    res_tk_open, dev_tk_open = _run(
        {**tk, "stop_when": "tk_phase == 'goto_team'"},
        stage / "resources",
        [courtyard, (*panel, "I_CLOSE_RED"), (*panel, "I_OPEN_YELLOW"), courtyard],
        params={"tk_buff_enable": True, "tk_buff_exp_100": True},
        full_ocr_reader=_buff_row_reader,
    )
    assert res_tk_open.status == "success" and len(dev_tk_open.inputs) == 3
    assert res_tk_open.variables["tk_buff_before_select_3_helper_status"] == "observed"

    res_tk, _ = _run(
        tk, stage / "resources",
        [("I_FIRE", "I_ADD_1", "I_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"tk_room_wait_seconds": 1},
        initial_vars={"tk_phase": "wait_room"},
    )
    assert res_tk.status == "success", res_tk.summary()
    assert res_tk.oas_schedule == "Tako"
    assert res_tk.variables["tk_exit_reason"] == "room_wait_timeout"

    res_tk_sched, _ = _run(
        tk, stage / "resources", [("I_BATTLE_INFO", "I_WIN"), ("I_CHECK_MAIN",)],
        params={"tk_max_runs": 2, "tk_limit_seconds": 1, "tk_next_delay_s": 3600},
        initial_vars={"tk_phase": "battle"},
    )
    assert res_tk_sched.status == "success", res_tk_sched.summary()
    assert res_tk_sched.variables["tk_exit_reason"] == "time_limit" and res_tk_sched.oas_target[0] == 3600
