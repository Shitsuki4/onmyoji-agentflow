"""Exact inert source fixtures, phase YAML, and real Runner; no live I/O."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from helpers import blank, paint_points
from test_handler_runner import MillisecondClock, run_synthetic
from test_handlers import case, handler
from onmyoji_agentflow.convert.core_handlers import (
    CURRENT_DATE_VAR, NORMAL_SETTLEMENT_ORDER, SOURCE_PINS, compile_core_handler,
    core_workflow, load_core_handler, source_device_hash31,
)
from onmyoji_agentflow.convert.handlers import UnsupportedHandler
from onmyoji_agentflow.convert.jsliteral import extract_literal_after, find_consts, parse
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml


FIXTURE = json.loads((Path(__file__).parent / "fixtures/core_handlers.json").read_text(encoding="utf-8"))


def build(fid, **kwargs):
    return compile_core_handler(FIXTURE["sources"][str(fid)], copy.deepcopy(FIXTURE["resources"]), **kwargs)


def source_ops(fid):
    source = FIXTURE["sources"][str(fid)]
    literal, _ = extract_literal_after(source, r"operator\s*:\s*IFuncOperatorOrigin\[\]\s*=")
    return parse(literal, find_consts(source))


def image_for(fid, *indices, first_only=False, jade=False):
    image = blank()
    for index in indices:
        desc = source_ops(fid)[index]["desc"]
        points = FIXTURE["resources"][desc]["points"] if isinstance(desc, str) else [
            [x, y, f"#{color:06x}"] for _, x, y, color in desc[2]]
        paint_points(image, points[:1] if first_only else points)
    if jade:
        paint_points(image, FIXTURE["resources"]["勾协判定"]["groups"][0])
    return image


def executable(tmp_path, packets, *, stop="handler_phase == 0 and elapsed_ms >= 1", limits=None,
               config_overrides=None, loop_ms=200):
    result = core_workflow("core_source_test", packets, config_overrides=config_overrides,
        common_overrides={"loopDelay": loop_ms, "afterClickDelayBase": 0, "afterClickDelayRandom": 0})
    assert result["guarded_executable"] and not result["executable"] and not result["complete"]
    raw = result["workflow"]
    raw["stop_when"] = stop
    if limits:
        raw["limits"] = limits
    raw["resources"] = []
    if result["program"]["resource_specs"]:
        (tmp_path / "core-resources.yaml").write_text(
            dump_yaml({"resources": result["program"]["resource_specs"]}), encoding="utf-8")
        raw["resources"] = ["core-resources.yaml"]
    path = tmp_path / "core.yaml"
    path.write_text(dump_yaml(raw), encoding="utf-8")
    return load_workflow(path, [tmp_path])


def tapped_in(replay, operation):
    _, _, _, x1, y1, x2, y2, *_ = operation
    return any(kind == "tap" and x1 <= x <= x2 and y1 <= y <= y2 for kind, x, y in replay.inputs)


@pytest.mark.parametrize("fid", [0, 2, 3])
def test_exact_sources_all_config_defaults_and_no_fingerprint_bypass(fid):
    source = FIXTURE["sources"][str(fid)]
    assert hashlib.sha256(source.encode()).hexdigest() == SOURCE_PINS[fid]
    literal, _ = extract_literal_after(source, r"\bconfig\s*=")
    groups = parse(literal, find_consts(source))
    defaults = {item["name"]: item["default"] for group in groups for item in group["config"]}
    packet = build(fid)
    assert {k: v["default"] for k, v in packet["handler"]["params"].items()} == defaults
    changed = source + "\n"
    with pytest.raises(UnsupportedHandler, match="fingerprint"):
        compile_core_handler(changed, {}, expected_sha256=hashlib.sha256(changed.encode()).hexdigest())
    assert not packet["complete"] and not packet["original_task_complete"]
    assert packet["source_obligations"]


@pytest.mark.parametrize("text,expected", [("", 0), ("abc", 96354), ("Aa", 2112),
                                           ("BB", 2112), ("😀", 1772899), ("zzzzzz", 1461697984)])
def test_device_hash_matches_utf16_signed_js_hash(text, expected):
    assert source_device_hash31(text) == expected


def test_002_all_41_operators_normal_priority_retest_notforcnt_and_targets(tmp_path):
    packet = build(2, device_hash31=7)
    cases = packet["handler"]["cases"]
    normal = [c for c in cases if c["id"].startswith("normal_")]
    assert [int(c["id"].split("_")[-1]) for c in normal] == list(NORMAL_SETTLEMENT_ORDER)
    assert {int(c["id"].split("_")[-1]) for c in cases} == set(range(41))
    assert [c["id"] for c in cases[:6]] == ["rechallenge_20", "rechallenge_22",
        "no_sushi_switch_19", "no_sushi_stop_19", "fail_9", "fail_10"]
    assert cases[0]["retest_ms"] == 800
    assert normal[4]["retest_ms"] == 300  # source index3, normal order index4
    assert next(c for c in normal if c["id"] == "normal_5")["count_events"] == [
        {"counter_id": 2, "not_for_count": True}]
    assert len(packet["source_obligations"]) == 4
    assert all(item["source"]["path"].endswith("002_退出结算.ts") for item in packet["source_obligations"])
    assert not any("click_random" in action for c in cases for action in c["do"])
    executable(tmp_path, [packet])  # Every operator/action survives real schema validation.


@pytest.mark.parametrize("hashed", [0, 1, 2, 7, 0x7fffffff])
def test_002_device_choice_is_source_modulo_and_ninth_value_is_press(tmp_path, hashed):
    packet = build(2, device_hash31=hashed)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(2, 0)])
    assert result.status == "success", result.summary()
    selected = source_ops(2)[0]["operStepRandom"][0][hashed % 3]
    branch = next(c for c in packet["handler"]["cases"] if c["id"] == "normal_0")
    assert branch["do"] == [{"click": selected[3:7], "delay": selected[7], "press_ms": selected[8]}]
    assert tapped_in(replay, selected)
    assert result.variables["run_times_2"] == 1


def test_002_missing_hash_fails_in_matched_operator_not_uniform_random(tmp_path):
    packet = build(2)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(2, 0)])
    assert result.status == "failed" and "device_choice" in result.reason
    assert result.failure_kind == "workflow_fail" and not replay.inputs
    assert result.variables["run_times_2"] == 1  # Source counting precedes missing input.


def test_002_notforcnt_confirm_is_not_counted(tmp_path):
    result, replay, clock = run_synthetic(executable(tmp_path, [build(2)]), [image_for(2, 5)])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 2 and clock.ms == 1000  # 300+500+one loop delay
    assert result.variables["run_times_2"] == 0 and result.variables["handler_last_id"] == -1


def test_002_rechallenge_retest_reselects_within_group_then_notforcnt(tmp_path):
    packet = build(2, config={"rechallenge": True}, device_hash31=0)
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]),
        [image_for(2, 20), image_for(2, 22)])
    assert result.status == "success", result.summary()
    assert "h0_rechallenge_22" in [name for _, name in result.history]
    assert "h0_rechallenge_20" not in [name for _, name in result.history]
    assert len(replay.inputs) == 2 and replay.screenshot_calls == 2
    assert result.variables["run_times_2"] == 0 and clock.ms == 1800


@pytest.mark.parametrize("switch", [False, True])
def test_002_no_sushi_branches_are_explicit_and_yield_not_handled(switch, tmp_path):
    packet = build(2, config={"no_sushi_switch_enabled": switch, "next_scheme": "actual chosen target"})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(2, 19)])
    assert result.status == "failed" and "no_sushi" in result.reason and not replay.inputs
    assert result.variables["run_times_2"] == 1
    branch = next(c for c in packet["handler"]["cases"] if c["id"] == (
        "no_sushi_switch_19" if switch else "no_sushi_stop_19"))
    assert branch["return"] is False
    obligation = next(o for o in packet["source_obligations"] if o["id"].endswith(branch["id"]))
    assert obligation["source_return"].startswith("undefined")
    assert obligation["ordered_effects"][0]["effect"] == ("source_rerun" if switch else "source_push")
    assert result.variables["handler_last_handled_ms"] == -1


def test_002_failure_branch_performs_source_input_then_blocks_push_transition(tmp_path):
    packet = build(2, config={"fail": True, "next_scheme": "返回庭院"}, device_hash31=1)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(2, 9)])
    assert result.status == "failed" and "fail_9_transition" in result.reason
    assert tapped_in(replay, source_ops(2)[9]["operStepRandom"][0][1])
    obligation = next(o for o in packet["source_obligations"] if o["id"] == "core2.fail_9_transition")
    assert [e["effect"] for e in obligation["ordered_effects"]] == ["source_push", "source_rerun", "sleep"]
    assert obligation["ordered_effects"][1]["target"] == {"config": "next_scheme"}
    assert obligation["source_return"] is True


@pytest.mark.parametrize("kind", ["关闭", "接受", "拒绝"])
@pytest.mark.parametrize("yykind", ["关闭", "接受", "拒绝"])
@pytest.mark.parametrize("jade_only", [False, True])
@pytest.mark.parametrize("screen", [0, 5])
def test_003_every_config_branch_with_real_runner(tmp_path, kind, yykind, jade_only, screen):
    packet = build(3, config={"type": kind, "yytype": yykind, "switch": jade_only})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(3, screen)])
    assert result.status == "success", result.summary()
    selected = {"关闭": 0, "接受": 1, "拒绝": 2}[kind if screen == 0 else yykind]
    if screen == 0 and jade_only and kind == "接受":
        selected = 0  # No jade colors: source closes, without a second count event.
        assert "h0_non_jade_close" in [sid for _, sid in result.history]
    assert len(replay.inputs) == 1 and tapped_in(replay, source_ops(3)[screen]["oper"][selected])
    assert result.variables["run_times_3"] == 1


def test_003_jade_entry_uses_first_point_only_and_two_count_events(tmp_path):
    packet = build(3, config={"type": "接受", "switch": True})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]),
        [image_for(3, 0, first_only=True, jade=True)])
    assert result.status == "failed" and "jade_push" in result.reason
    assert len(replay.inputs) == 1 and tapped_in(replay, source_ops(3)[0]["oper"][1])
    assert result.variables["run_times_3"] == 1  # The second event is suppressed at the same timestamp.
    assert result.variables["handler_last_ms"] == 0
    assert "h0_jade_probe" in [sid for _, sid in result.history]


def test_003_jade_probe_suppresses_invitation_even_if_full_bounty_comparison_misses(tmp_path):
    packet = build(3, config={"type": "接受", "switch": True, "yytype": "接受"})
    later = handler(99, [case("done", actions=[{"inc": "done"}])], variables={"done": 0})
    image = image_for(3, 5)
    first = source_ops(3)[0]["desc"][2][0]
    paint_points(image, [[first[1], first[2], first[3]]])
    result, replay, _ = run_synthetic(executable(tmp_path, [packet, later],
        stop="handler_phase == 0 and done == 1"), [image])
    assert result.status == "success", result.summary()
    assert not replay.inputs and result.variables["run_times_3"] == 1
    assert "h0_jade_unhandled" in [sid for _, sid in result.history]
    assert "h1_done" in [sid for _, sid in result.history]


def test_003_jade_search_requires_98_similarity_not_older_lossy_conversion(tmp_path):
    colors = copy.deepcopy(FIXTURE["resources"])
    colors["勾协判定"].pop("similarity")
    packet = compile_core_handler(FIXTURE["sources"]["3"], colors, config={"switch": True, "type": "接受"})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(3, 0)])
    assert result.status == "failed" and "jade_search_resource" in result.reason and not replay.inputs


def test_003_unexpected_login_has_native_click_but_explicit_push_stop_gap(tmp_path):
    packet = build(3)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(3, 4)])
    assert result.status == "failed" and "unexpected_login" in result.reason
    assert len(replay.inputs) == 1 and tapped_in(replay, source_ops(3)[4]["oper"][0])
    assert result.variables["run_times_3"] == 1


@pytest.mark.parametrize("fid, config, initial, screen, reason, inputs", [
    (0, {"jspd_enabled_1": True, "jspd_times_1": 2, "after_operation": "停止脚本"},
     {"run_times_1": 2}, None, "达到方案停止条件", 0),
    (2, {}, {}, 19, "体力不足", 0),
    (3, {}, {}, 4, "出现意外登录", 1),
])
def test_explicit_local_notice_stops_without_claiming_business_success(
        tmp_path, fid, config, initial, screen, reason, inputs):
    packet = build(fid, config=config, local_notifications=True)
    assert any(item["id"].endswith("local_notification_tone") and not item["blocking"]
               for item in packet["source_obligations"])
    workflow = executable(tmp_path, [packet], stop="False")
    result, replay, _ = run_synthetic(workflow, [blank() if screen is None else image_for(fid, screen)],
                                      initial_vars=initial)
    assert result.status == "success" and result.reason == reason and not result.business_ok
    assert len(replay.inputs) == inputs


@pytest.mark.parametrize("name,config,initial", [
    ("inactivity", {"jspd_times_longtime_nodo": 1}, {"elapsed_ms": 60000}),
    ("total_duration", {"jspd_enabled_longtime_nodo": False, "jspd_enabled_zjsj": True,
                        "jspd_times_zjsj": 1}, {"elapsed_ms": 60000}),
    ("count_1", {"jspd_enabled_1": True, "jspd_times_1": 2}, {"run_times_1": 2}),
    ("count_2", {"jspd_enabled_2": True, "jspd_times_2": 2}, {"run_times_2": 2}),
])
@pytest.mark.parametrize("mode", ["停止脚本", "切换方案", "随机等待"])
def test_000_all_terminal_triggers_and_effect_modes_fail_explicitly(tmp_path, name, config, initial, mode):
    config = {**config, "after_operation": mode, "after_operation_sleep": "1,1"}
    packet = build(0, config=config)
    result, replay, clock = run_synthetic(executable(tmp_path, [packet], stop="False"),
                                         [blank()], initial_vars=initial)
    assert result.status == "failed" and name in result.reason
    assert result.variables["core0_stop_reason"] == name and not replay.inputs
    # Strict '>' time comparisons do not fire at the exact 60000ms boundary.
    if name in ("inactivity", "total_duration"):
        assert replay.screenshot_calls == 2 and clock.ms >= 200
    if mode == "随机等待":
        assert clock.ms >= 1000


def test_000_inactivity_timestamp_binds_true_returns_only(tmp_path):
    packet = build(0, config={"jspd_times_longtime_nodo": 1})
    later = handler(99, [case("handled")])
    result, replay, _ = run_synthetic(executable(tmp_path, [packet, later],
        stop="handler_phase == 0 and elapsed_ms >= 600"), [blank()])
    assert result.status == "success", result.summary()
    assert result.variables[CURRENT_DATE_VAR] == 400
    assert not replay.inputs and result.variables["core0_stop_reason"] == ""


def test_000_bookkeeping_notices_do_not_mask_unknown_timeout(tmp_path):
    packet = build(0, config={"jspd_enabled_longtime_nodo": False, "jspd_enabled_zjsj": True,
                             "jspd_txpl_zjsj": 0})
    workflow = executable(tmp_path, [packet], stop="False", limits={"unknown_timeout_s": 0.5})
    result, replay, _ = run_synthetic(workflow, [blank()])
    assert result.status == "failed" and result.failure_kind == "unknown_screen", result.summary()
    assert result.recognized_ticks == 0 and not replay.inputs


def test_000_bookkeeping_does_not_reset_source_repeat_limit(tmp_path):
    packet = build(0, config={"jspd_enabled_longtime_nodo": False, "jspd_enabled_zjsj": True,
                             "jspd_txpl_zjsj": 0})
    later = handler(99, [case("same")])
    result, _, _ = run_synthetic(executable(tmp_path, [packet, later], stop="False",
        limits={"max_repeat": 2}), [blank()])
    assert result.status == "failed" and result.failure_kind == "loop", result.summary()
    assert result.failed_state == "h1_same"


def test_000_counter_zero_alias_preserves_source_undefined_threshold_behavior(tmp_path):
    packet = build(0, config={"jspd_enabled_1": True, "jspd_times_1": 0})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet],
        stop="handler_phase == 0 and elapsed_ms >= 200"), [blank()])
    assert result.status == "success", result.summary()
    assert not replay.inputs and result.variables["core0_stop_reason"] == ""


def test_000_fixed_pause_deadlines_wait_resume_and_resample_next_invocation(tmp_path):
    packet = build(0, config={"jspd_enabled_longtime_nodo": False, "pause_enabled": True,
                             "define_run_time": "0.005,0.005", "define_pause_time": "0.01,0.01"})
    workflow = executable(tmp_path, [packet],
        stop="handler_phase == 0 and core0_running == -1 and elapsed_ms >= 5800")
    result, replay, clock = run_synthetic(workflow, [blank()])
    assert result.status == "success", result.summary()
    states = [sid for _, sid in result.history]
    assert states.count("h0_pause_init") == 1
    assert states.count("h0_pause_begin") == states.count("h0_pause_wait") == states.count("h0_pause_complete") == 1
    assert result.variables[CURRENT_DATE_VAR] == 5800 and clock.ms == 6000
    assert result.variables["core0_running_until_ms"] == 300
    assert result.variables["core0_pause_until_ms"] == 900 and not replay.inputs


def test_000_samples_random_pause_from_runtime_config(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("random.randint", lambda lo, hi: calls.append((lo, hi)) or hi)
    packet = build(0, config={"pause_enabled": True})
    workflow = executable(tmp_path, [packet])
    device = ReplayDevice([blank()])
    clock = MillisecondClock()
    result = Runner(workflow, Controller(device, sleep=clock.sleep), clock=clock,
                    params={"cfg_0_define_run_time": "1,2"}).run()
    assert result.status == "success" and not device.inputs
    assert result.variables["core0_running_until_ms"] == 120000
    assert result.variables["core0_pause_until_ms"] == 540000
    assert calls == [(60000, 120000), (120000, 420000)]


def test_000_planned_pause_survives_screen_and_repeat_limits(tmp_path):
    packet = build(0, config={"pause_enabled": True, "define_run_time": "0,0", "define_pause_time": "2,2",
                             "jspd_enabled_longtime_nodo": False})
    workflow = executable(tmp_path, [packet], stop="handler_phase == 0 and core0_running == -1 and elapsed_ms > 0",
                          limits={"stuck_timeout_s": 10, "no_progress_timeout_s": 10, "max_repeat": 2})
    result, replay, clock = run_synthetic(workflow, [blank()], max_seconds=150)
    assert result.status == "success" and not replay.inputs, result.summary()
    assert sum(sid == "h0_pause_wait" for _, sid in result.history) == 10
    assert 120000 <= clock.ms < 123000


def test_000_invalid_range_fails_before_wait(tmp_path):
    packet = build(0, config={"pause_enabled": True, "define_pause_time": "9,2"})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [blank()])
    assert result.failure_kind == "workflow_error" and "cfg_0_define_pause_time" in result.reason
    assert clock.ms == 0 and not replay.inputs


@pytest.mark.parametrize("history,expected", [(None, "loop_history"),
    (["A", "B", "A"], "loop_limit"), (["A", "B"], None)])
def test_000_history_counts_occurrences_of_last_entry_strictly_over_limit(tmp_path, history, expected):
    packet = build(0, config={"loop_enabled": True, "loop_times": 1}, scheme_history=history)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [blank()], initial_vars={"loop_add": True})
    assert not replay.inputs
    if expected:
        assert result.status == "failed" and expected in result.reason
    else:
        assert result.status == "success", result.summary()
        assert result.variables["loop_add"] is False
    loop = next(o for o in packet["source_obligations"] if o["id"] == "core0.loop_limit")
    assert loop["ordered_effects"][1] == {"effect": "set_super_global", "name": "next_scheme_name", "value": "返回庭院"}
    assert loop["ordered_effects"][2]["target"] == "关闭BUFF"


def test_000_app_exit_keeps_push_before_conditional_app_close_before_stop():
    packet = build(0, config={"stop_with_launched_app_exit": True})
    assert all(set(action) <= {"set", "wait", "log", "fail", "sample_duration"}
               for branch in packet["handler"]["cases"] for action in branch["do"])
    obligation = next(o for o in packet["source_obligations"] if o["id"] == "core0.inactivity_1")
    assert [e["effect"] for e in obligation["ordered_effects"]] == [
        "source_push", "source_stop_related_apps", "source_stop", "sleep"]
    assert obligation["ordered_effects"][1]["if_config"] == "stop_with_launched_app_exit"


def test_000_loop_add_is_initially_true_and_requires_history_when_enabled(tmp_path):
    packet = build(0, config={"loop_enabled": True})
    assert packet["handler"]["vars"]["loop_add"] is True  # GlobalStore/index.ts:291
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [blank()])
    assert result.status == "failed" and "loop_history" in result.reason and not replay.inputs


def test_002_rechallenge_preempts_failure_switch_and_normal_exit(tmp_path):
    packet = build(2, config={"rechallenge": True, "fail": True}, device_hash31=0)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(2, 20)])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped_in(replay, source_ops(2)[20]["oper"][0])
    assert "h0_rechallenge_20" in [sid for _, sid in result.history]
    assert result.variables["run_times_2"] == 1


def test_002_source_32_has_priority_over_reward_exit_zero(tmp_path):
    image = image_for(2, 0, 32)
    result, replay, _ = run_synthetic(executable(tmp_path, [build(2, device_hash31=0)]), [image])
    assert result.status == "success", result.summary()
    assert "h0_normal_32" in [sid for _, sid in result.history]
    assert len(replay.inputs) == 2 and result.variables["run_times_2"] == 0


def test_003_cleanup_preempts_bounty_and_empty_invitation_type_closes(tmp_path):
    packet = build(3, config={"type": "接受", "yytype": ""})
    image = image_for(3, 0, 2)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped_in(replay, source_ops(3)[2]["oper"][0])
    assert "h0_cleanup_2" in [sid for _, sid in result.history]
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(3, 5)])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped_in(replay, source_ops(3)[5]["oper"][0])


def test_shared_config_precedence_and_completeness_cannot_be_claimed():
    packet = build(2)
    out = core_workflow("precedence", [packet], scheme={"list": [2], "config": {"2": {"fail": True}}},
                        config_overrides={"2": {"fail": False}})
    assert out["workflow"]["params"]["cfg_2_fail"]["default"] is False
    assert out["guarded_executable"] and out["executable"] is False
    assert out["original_task_complete"] is False and out["complete"] is False
    assert out["workflow"]["core_handler_contract"]["source_complete"] is False
    with pytest.raises(UnsupportedHandler, match="boolean"):
        core_workflow("bad", [packet], config_overrides={"2": {"fail": "false"}})


def test_loader_refuses_drifted_helpers_and_bad_hashes(tmp_path):
    script = tmp_path / "src/system/script.ts"
    script.parent.mkdir(parents=True)
    script.write_text("inert drifted helper", encoding="utf-8")
    with pytest.raises(UnsupportedHandler, match="helper fingerprint"):
        load_core_handler(tmp_path, 0)
    with pytest.raises(UnsupportedHandler, match="31-bit"):
        build(2, device_hash31=-1)
    with pytest.raises(UnsupportedHandler, match="only core"):
        load_core_handler(tmp_path, 1)


def test_core_jade_resource_is_self_contained_with_source_similarity():
    packet = build(3)
    output = core_workflow("core_jade_resource", [packet])
    wf = load_workflow(output["workflow"])
    assert wf.resources["勾协判定"]["similarity"] == 98
