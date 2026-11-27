"""Offline unit tests for OAS EvoZone, EternitySea, FallenSun, and Orochi."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_zone_farming import (
    compile_eternity_sea_candidate,
    compile_evo_zone_candidate,
    compile_fallen_sun_candidate,
    compile_orochi_candidate,
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
    for task in ("EvoZone", "EternitySea", "FallenSun", "Orochi", "TrueOrochi",
                 "Component_SwitchSoul", "Component_GeneralRoom", "Component_GeneralInvite"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, layer=None):
    wf = load_workflow(raw, [root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, *_a, **_kw):
        vis = frames[int(image[0, 0, 0]) - 20]
        hit = bool(set(vis) & aliases.get(Path(path).resolve(), set()))
        return hit, float(hit), (200, 120, 40, 32)

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, initial_vars=initial_vars,
            text_reader=lambda _image, roi: [(layer, roi[0] + 24, roi[1] + 100)] if layer else [],
        ).run()
    return res, device


def test_evo_zone_and_fallen_sun_solo_battle_and_gates(oas_stage):
    stage, src, folder = oas_stage
    ez = compile_evo_zone_candidate(src, folder)
    res_wild, _ = _run(ez, stage / "resources", [()], params={"ez_user_status": "wild"})
    assert res_wild.status == "failed" and "野队" in res_wild.reason

    res_leader, _ = _run(
        ez, stage / "resources",
        [
            ("I_FORM_TEAM",),
            ("I_CREATE_ROOM",),
            ("I_CREATE_ENSURE", "I_ENSURE_PRIVATE"),
            ("I_GI_EMOJI_1", "I_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_REWARD",),
            ("I_GI_EMOJI_1", "I_BACK_YELLOW"),
            ("I_UI_CONFIRM",),
            ("I_CHECK_MAIN",),
        ],
        params={"ez_user_status": "leader", "ez_limit_count": 1},
        initial_vars={"ez_phase": "leader_open_team"},
    )
    assert res_leader.status == "success", res_leader.summary()
    assert res_leader.variables["ez_wins"] == 1 and res_leader.oas_schedule == "EvoZone"

    res_ez, _ = _run(
        ez, stage / "resources",
        [
            ("I_LIGHTNING_KIRIN",), ("I_FORM_TEAM", "I_EVOZONE_UNLOCK", "I_EVOZONE_FIRE"),
            ("I_EVOZONE_UNLOCK", "I_EVOZONE_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_REWARD",),
            ("I_EVOZONE_FIRE", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",),
        ],
        params={"ez_limit_count": 1, "lock_team_enable": False},
        initial_vars={"ez_phase": "open_zone"}, layer="拾",
    )
    assert res_ez.status == "success", res_ez.summary()
    assert res_ez.oas_schedule == "EvoZone" and res_ez.variables["ez_wins"] == 1

    fs = compile_fallen_sun_candidate(src, folder)
    res_fs, _ = _run(
        fs, stage / "resources",
        [
            ("I_FALLEN_SUN",), ("I_FORM_TEAM", "I_FALLEN_SUN_LOCK", "I_FALLEN_SUN_FIRE"),
            ("I_FALLEN_SUN_LOCK", "I_FALLEN_SUN_FIRE"),
            ("I_BATTLE_INFO", "I_WIN"),
            ("I_REWARD_GOLD_SNAKE_SKIN",),
            ("I_FALLEN_SUN_FIRE", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",),
        ],
        params={"fs_limit_count": 1, "lock_team_enable": True},
        initial_vars={"fs_phase": "open_zone"}, layer="叁",
    )
    assert res_fs.status == "success", res_fs.summary()
    assert res_fs.oas_schedule == "FallenSun" and res_fs.variables["fs_wins"] == 1

    # FallenSun leader time limit + I_UI_BACK_BLUE exit + target schedule
    res_fs_tl, _ = _run(
        fs, stage / "resources",
        [("I_GI_EMOJI_1", "I_BACK_YELLOW"), ("I_UI_CONFIRM",), ("I_UI_BACK_BLUE",), ("I_CHECK_MAIN",)],
        params={"fs_user_status": "leader", "fs_limit_seconds": 0, "fs_next_delay_s": 86400},
        initial_vars={"fs_phase": "leader_invite"},
    )
    assert res_fs_tl.status == "success", res_fs_tl.summary()
    assert res_fs_tl.variables["fs_exit_reason"] == "time"
    assert res_fs_tl.oas_target is not None and res_fs_tl.oas_target[0] == 86400

    res_ez_sched, _ = _run(
        ez, stage / "resources", [("I_EVOZONE_FIRE", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"ez_limit_count": 0, "ez_next_delay_s": 43200},
        initial_vars={"ez_phase": "cycle"},
    )
    assert res_ez_sched.status == "success" and res_ez_sched.oas_target[0] == 43200


def test_evo_zone_strategy_requires_reward_and_services_late_ready(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_evo_zone_candidate(src, folder)
    assert raw["oas_ez_contract"]["battle_wait_dispatch"] == "pinned BattleWait default strategy hooks"
    start = {"ez_phase": "battle", "ez_battle_phase": "battle_wait", "ez_battle_current_count": 1}

    no_reward, device = _run(
        raw, stage / "resources", [("I_WIN",), ("I_EVOZONE_FIRE", "I_UI_BACK_YELLOW")],
        params={"ez_limit_count": 1}, initial_vars=start,
    )
    assert no_reward.variables["ez_wins"] == 0 and not no_reward.variables["ez_battle_returned"]
    assert len(device.inputs) == 1

    loss, device = _run(
        raw, stage / "resources",
        [("I_PREPARE_HIGHLIGHT",), ("I_FALSE",), ("I_EVOZONE_FIRE", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"ez_limit_count": 1}, initial_vars=start,
    )
    assert loss.status == "success" and loss.variables["ez_attempts"] == 1 and loss.variables["ez_wins"] == 0
    assert loss.variables["ez_battle_returned"] and len(device.inputs) == 3


def test_eternity_sea_lock_guard_and_orochi_true_orochi_schedule(oas_stage):
    stage, src, folder = oas_stage
    es = compile_eternity_sea_candidate(src, folder)
    res_nolock, _ = _run(es, stage / "resources", [()], params={"lock_team_enable": False})
    assert res_nolock.status == "failed" and "锁定阵容" in res_nolock.reason

    res_es, _ = _run(
        es, stage / "resources",
        [
            ("I_ETERNITY_SEA_FIRE",), ("I_BATTLE_INFO", "I_WIN"),
            ("I_ETERNITY_SEA_FIRE", "I_BACK_BOTTOM"), ("I_CHECK_MAIN",),
        ],
        params={"es_limit_count": 1, "lock_team_enable": True},
        initial_vars={"es_phase": "cycle"},
    )
    assert res_es.status == "success", res_es.summary()
    assert res_es.oas_schedule == "EternitySea" and res_es.variables["es_wins"] == 1

    # EternitySea dual-team preset gate + I_BACK_YELLOW_SEA exit
    assert {"es2_switch_soul", "es2_switch_soul_by_name", "es2_numbered_group", "es2_numbered_team"} <= set(es["params"])
    res_es_bad2, _ = _run(
        es, stage / "resources", [()],
        params={"lock_team_enable": True, "es2_switch_soul": True},
        initial_vars={"es_phase": "team2_presets"},
    )
    assert res_es_bad2.status == "failed" and "编号预设" in res_es_bad2.reason

    res_es_sea, _ = _run(
        es, stage / "resources",
        [("I_ETERNITY_SEA_FIRE", "I_BACK_YELLOW_SEA"), ("I_CHECK_MAIN",)],
        params={"es_limit_count": 0, "lock_team_enable": True, "es_next_delay_s": 21600},
        initial_vars={"es_phase": "cycle"},
    )
    assert res_es_sea.status == "success" and res_es_sea.variables["es_exit_reason"] == "count"
    assert res_es_sea.oas_target is not None and res_es_sea.oas_target[0] == 21600

    oro = compile_orochi_candidate(src, folder)
    res_ts, _ = _run(
        oro, stage / "resources",
        [("I_OROCHI_FIRE", "I_OROCHI_CHECK_10", "I_FIND_TS", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"or_limit_count": 0, "or_check_true_orochi": True, "or_layer": "拾层"},
        initial_vars={"or_phase": "cycle"},
    )
    assert res_ts.status == "success" and res_ts.oas_schedule == "Orochi", res_ts.summary()
    assert res_ts.oas_wakes["TrueOrochi"][0] == 86400
