"""Unit tests for 318_战斗内操作选项 and 603_狭间暗域 native handlers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import blank, paint_condition, paint_points
from onmyoji_agentflow.convert.handlers import UnsupportedHandler
from onmyoji_agentflow.convert.team_handlers import compile_team_handler, team_workflow
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import run_synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "narrow_realm_handlers.json"


def _load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _build(fid, *, config=None, stop="handler_phase == 0 and elapsed_ms >= 1"):
    data = _load_fixture()
    key = "source_318" if fid == 318 else "source_603"
    colors = data["colors"]
    model = compile_team_handler(data[key], colors, config=config)
    native = team_workflow(
        f"test_{fid}",
        [model],
        config_overrides={str(fid): config or {}},
        common_overrides={"afterClickDelayBase": 0, "afterClickDelayRandom": 0, "loopDelay": 200},
    )
    raw = native["workflow"]
    if stop:
        raw["stop_when"] = stop
    return load_workflow(raw), {c["id"]: c for c in model["handler"]["cases"]}, colors, model


def _frame(colors, *conditions, level=70):
    img = blank(level)
    for cond in conditions:
        paint_condition(img, cond, colors)
    return img


def test_318_xingmie_start_and_skill_toggle():
    wf, cases, colors, model = _build(318, config={"xingMie": True})
    assert model["source_obligations"] == []
    # Start banner triggers op[0] + skill3 tap (falls through to unmatched -> 2 clicks)
    f_start = _frame(colors, cases["start_init_untimed"]["when"]["all"][0]["any"][0])
    run, dev, _ = run_synthetic(wf, [f_start, f_start], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 2
    assert run.variables["fight318_xingMie"] is True
    assert run.variables["run_times_320"] == 1

    # Skill box open with 妖术二 -> waits 250ms and clicks skill 3 (1099..1145)
    f_box2 = _frame(colors, cases["xingmie_skill_box_wait"]["when"], cases["xingmie_skill_to_3"]["when"])
    run, dev, clock = run_synthetic(wf, [f_box2, f_box2, blank(70)], max_seconds=5)
    assert run.status == "success", run.summary()
    assert any(1099 <= item[1] <= 1145 for item in dev.inputs)
    assert clock.ms >= 250
    assert run.variables["run_times_318"] == 1

    # Skill box open without 妖术二 -> clicks skill 2 (1011..1051)
    f_box3 = _frame(colors, cases["xingmie_skill_box_wait"]["when"])
    run, dev, _ = run_synthetic(wf, [f_box3, f_box3, blank(70)], max_seconds=5)
    assert run.status == "success", run.summary()
    assert any(1011 <= item[1] <= 1051 for item in dev.inputs)


def test_318_disitian_start_left_and_right_and_action_bar():
    wf, cases, colors, model = _build(318, config={"diSiTian": True})
    res = model["handler"]["resource_specs"]
    # Opening left (< 1090): anchor at x=1009, y=646 -> clicks near (1009,646) then (979..989, 516..526)
    f_left = _frame(colors, cases["start_init_untimed"]["when"]["all"][0]["any"][0])
    paint_points(f_left, res["帝释天_left"]["groups"][0], 0, 0)
    run, dev, _ = run_synthetic(wf, [f_left, f_left], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 2
    assert 1009 <= dev.inputs[0][1] <= 1019
    assert 979 <= dev.inputs[1][1] <= 989 and 516 <= dev.inputs[1][2] <= 526

    # Opening right (>= 1090): anchor shifted +91 -> x=1100 -> second click at (1020..1030, 516..526)
    f_right = _frame(colors, cases["start_init_untimed"]["when"]["all"][0]["any"][0])
    paint_points(f_right, res["帝释天_right"]["groups"][0], 91, 0)
    run, dev, _ = run_synthetic(wf, [f_right, f_right], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 2
    assert 1100 <= dev.inputs[0][1] <= 1110
    assert 1020 <= dev.inputs[1][1] <= 1030

    # Action bar left -> sleeps 2000ms, clicks 帝释天 + normal attack (-120,-130), clears diSiTian
    f_act = _frame(colors, cases["disitian_action_miss"]["when"])
    paint_points(f_act, res["帝释天_left"]["groups"][0], 0, 0)
    run, dev, clock = run_synthetic(wf, [f_act], max_seconds=10)
    assert run.status == "success", run.summary()
    assert clock.ms >= 2000
    assert run.variables["fight318_diSiTian"] is False
    assert 889 <= dev.inputs[1][1] <= 899


def test_318_timed_exit():
    wf, cases, colors, _ = _build(318, config={"time": 1}, stop="run_times_320 >= 1")
    f_battle = _frame(colors, cases["timer_arm"]["when"])
    # Multiple frames advance virtual clock past 1000ms -> timer_exit clicks exit + confirm
    run, dev, clock = run_synthetic(wf, [f_battle] * 20, max_seconds=10)
    assert run.status == "success", run.summary()
    assert run.variables["run_times_320"] == 1
    assert run.variables["fight318_deadline_ms"] == -1
    assert len(dev.inputs) == 2
    assert 22 <= dev.inputs[0][1] <= 52
    assert 683 <= dev.inputs[1][1] <= 795


def test_603_enter_zone_and_preset_override():
    wf, cases, colors, _ = _build(
        603,
        config={"boss_order": "小到大", "boss_select": ["神龙", "豹子"], "preset_pair_精英": "3,2"},
    )
    f_enter = _frame(colors, cases["enter_zone_0"]["when"])
    run, dev, _ = run_synthetic(wf, [f_enter, f_enter], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1
    assert 108 <= dev.inputs[0][1] <= 293  # 神龙
    assert run.variables["preset_once_groupNum"] == 3
    assert run.variables["preset_once_defaultNum"] == 2
    assert run.variables["preset_once_team_groupNum"] == 3
    assert run.variables["preset_once_team_defaultNum"] == 2
    assert run.variables["shangyushe"] is True
    assert run.variables["change_shikigami_state"] == "flushed"


def test_603_report_targeting_and_bounded_loop():
    # Default 小到大, ['孔雀'(1), '狐狸'(2)]: Real=0 -> zone 1 (孔雀 y=281..345), monster 3 (x=450..509)
    wf, cases, colors, _ = _build(603, stop="handler_phase == 0 and elapsed_ms >= 1")
    f_rep = _frame(colors, cases["report_loop_check"]["when"])
    # 3 loop iterations stay on report screen -> decrements xiajian603_runTime_2 by 1 and exits False
    run, dev, clock = run_synthetic(wf, [f_rep] * 12, max_seconds=10)
    assert run.status == "success", run.summary()
    assert run.variables["xiajian603_runTime_2"] == -1
    assert len(dev.inputs) == 6  # 3 iterations * (zone + monster)
    assert 281 <= dev.inputs[0][2] <= 345  # 孔雀
    assert 450 <= dev.inputs[1][1] <= 509  # 精英3
    assert clock.ms >= 1000  # two 500ms loop sleeps


def test_603_big_to_small_done_and_small_snake():
    wf, cases, colors, _ = _build(603, config={"boss_order": "大到小", "sneak": "2"})
    # When run_times_2 - base < sneak and 小蛇 visible on report screen -> clicks 小蛇
    f_snake = _frame(colors, cases["report_loop_check"]["when"], cases["report_small_snake"]["when"])
    run, dev, _ = run_synthetic(wf, [f_snake, f_snake], max_seconds=5)
    assert run.status == "success", run.summary()
    assert len(dev.inputs) == 1
    assert 472 <= dev.inputs[0][1] <= 536

    # When Real >= 12 (大到小) and on 阴阳寮 screen -> hits narrow_realm_done_rerun gate
    f_guild = _frame(colors, cases["done_return_yard"]["when"])
    run, _, _ = run_synthetic(
        wf,
        [f_guild],
        initial_vars={"xiajian603_base_inited": True, "xiajian603_runTime_2": 0, "run_times_2": 14},
        max_seconds=5,
    )
    assert run.status == "failed"
    assert "narrow_realm_done_rerun" in run.reason


def test_603_rejects_invalid_config():
    data = _load_fixture()
    with pytest.raises(UnsupportedHandler):
        compile_team_handler(data["source_603"], data["colors"], config={"boss_select": ["神龙"]})
    with pytest.raises(UnsupportedHandler):
        compile_team_handler(data["source_603"], data["colors"], config={"preset_pair_精英": "9,1"})
