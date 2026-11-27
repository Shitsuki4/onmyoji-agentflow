"""Run emitted handler YAML through the real Runner on synthetic frame arrays.

No device connection, upstream execution, network, or approvals. These tests
require the native handler_control integration and never substitute a dispatcher.
Only complete source-cycle boundaries (handler_phase == 0) support resume.
"""
from __future__ import annotations

import copy
import re

import pytest

from helpers import blank, paint_points
from test_handlers import case, component_fixture, handler
from onmyoji_agentflow.convert.handlers import compose_handlers, phase_workflow
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml


@pytest.fixture(autouse=True)
def native_handler_control_available():
    from onmyoji_agentflow.workflow.schema import ACTION_KEYS
    assert "handler_control" in ACTION_KEYS, "native handler_control integration is required"


class MillisecondClock:
    def __init__(self):
        self.ms = 0

    def __call__(self):
        return self.ms / 1000

    def sleep(self, seconds):
        self.ms += round(seconds * 1000)


class SyntheticFrames(ReplayDevice):
    """The next array is observable only when Runner really requests a frame."""
    def __init__(self, frames):
        super().__init__(frames, advance_on_input=False)
        self.screenshot_calls = 0
        self.swipe_durations = []

    def screenshot(self):
        self.screenshot_calls += 1
        return super().screenshot()

    def swipe(self, p1, p2, duration_ms=400):
        self.swipe_durations.append(duration_ms)
        super().swipe(p1, p2, duration_ms)


RED = {"colors": [[40, 50, "#ff0000"]]}
GREEN = {"colors": [[60, 70, "#00ff00"]]}
BLUE = {"colors": [[80, 90, "#0000ff"]]}


def frame(*conditions):
    image = blank()
    for condition in conditions:
        paint_points(image, condition["colors"])
    return image


def compiled(tmp_path, definitions, *, stop="handler_phase == 0 and done == 1", loop_ms=200, base_ms=0,
             limits=None):
    program = compose_handlers("native_handler_integration", definitions,
                               common_overrides={"loopDelay": loop_ms, "afterClickDelayBase": base_ms,
                                                 "afterClickDelayRandom": 0})
    packet = phase_workflow(program, supported_primitives={"handler_control"}, supported_builtins={"elapsed_ms"})
    assert packet["missing_primitives"] == [] and packet["missing_builtins"] == []
    assert packet["executable"]
    raw = packet["workflow"]
    raw["stop_when"] = stop
    if limits is not None:
        raw["limits"] = copy.deepcopy(limits)
    # Keep fixtures local to pytest's temporary directory. Named find resources
    # need a native resource document; colour comparisons are already inlined.
    raw["resources"] = []
    if program["resource_specs"]:
        (tmp_path / "handler-fixtures.yaml").write_text(
            dump_yaml({"resources": program["resource_specs"]}), encoding="utf-8")
        raw["resources"] = ["handler-fixtures.yaml"]
    # Exercise YAML round-tripping and the real schema, not just dict construction.
    path = tmp_path / "handler-workflow.yaml"
    path.write_text(dump_yaml(raw), encoding="utf-8")
    return load_workflow(path, [tmp_path])


def run_synthetic(workflow, frames, *, initial_vars=None, max_actions=None, max_seconds=30,
                  full_ocr_reader=None, text_reader=None, confirm=None):
    clock = MillisecondClock()
    replay = SyntheticFrames(frames)
    controller = Controller(replay, HumanizeConfig(base_sleep_ms=0, random_sleep_ms=0), sleep=clock.sleep)
    result = Runner(workflow, controller, clock=clock, initial_vars=initial_vars, confirm=confirm,
                    max_actions=max_actions, max_seconds=max_seconds,
                    full_ocr_reader=full_ocr_reader, text_reader=text_reader).run()
    return result, replay, clock


def test_runner_false_yield_reuses_frame_and_has_no_internal_loop_delay(tmp_path):
    first = handler(38, [case("yield", condition=RED, handled=False, counter=38,
                              actions=[{"set": {"seen": "run_times_38"}}])], variables={"seen": 0})
    second = handler(2, [case("take", condition={"all": [RED, {"expr": "seen == 1"}]},
                             actions=[{"click": [100, 100, 100, 100], "delay": 0}, {"inc": "done"}])],
                     variables={"done": 0})
    workflow = compiled(tmp_path, [first, second])
    result, replay, clock = run_synthetic(workflow, [frame(RED), blank()])
    assert result.status == "success", result.summary()
    assert replay.inputs == [("tap", 100, 100)]
    assert replay.screenshot_calls == 1
    assert clock.ms == 200  # One outer loop delay, none between source handlers.
    assert result.variables["run_times_38"] == 1
    assert result.variables["handler_last_handled_ms"] == 0
    assert [sid for _, sid in result.history] == [
        "handler_begin", "handler_0_enter", "h0_yield", "handler_1_enter", "h1_take", "handler_end_true"]


def test_runner_unhandled_cycle_does_not_touch_handled_timestamp(tmp_path):
    source = handler(1, [case("miss", condition=RED)])
    workflow = compiled(tmp_path, [source], stop="handler_phase == 0 and elapsed_ms >= 200")
    result, replay, clock = run_synthetic(workflow, [blank(), frame(RED)])
    assert result.status == "success", result.summary()
    assert not replay.inputs and replay.screenshot_calls == 1
    assert clock.ms == 200
    assert result.variables["handler_last_handled_ms"] == -1
    assert [sid for _, sid in result.history][-1] == "handler_end_false"


def test_runner_retest_uses_fresh_frame_without_restarting_earlier_handler(tmp_path):
    earlier = handler(1, [case("early", condition=RED, actions=[{"fail": "earlier handler preempted retest"}])])
    later = handler(2, [case("old", condition=BLUE, retest_ms=1000, counter=2,
                            actions=[{"fail": "stale branch executed"}]),
                         case("fresh", condition=GREEN, counter=2,
                              actions=[{"click": [200, 200, 200, 200], "delay": 0}, {"inc": "done"}])],
                    variables={"done": 0})
    workflow = compiled(tmp_path, [earlier, later])
    result, replay, clock = run_synthetic(workflow, [frame(BLUE), frame(RED, GREEN), blank()])
    assert result.status == "success", result.summary()
    assert replay.inputs == [("tap", 200, 200)] and replay.screenshot_calls == 2
    assert clock.ms == 1200
    assert result.variables["run_times_2"] == 1
    assert result.variables["handler_last_ms"] == 1000
    assert result.variables["handler_last_handled_ms"] == 1000
    assert "h0_early" not in [sid for _, sid in result.history]
    assert "h1_old" not in [sid for _, sid in result.history]


def test_runner_retest_disappearance_yields_using_updated_cached_frame(tmp_path):
    earlier = handler(1, [case("early", condition=RED, actions=[{"fail": "incorrect priority restart"}])])
    retested = handler(2, [case("vanished", condition=BLUE, retest_ms=1000, counter=2,
                               actions=[{"fail": "stale candidate ran"}])])
    final = handler(3, [case("fresh", condition=GREEN, actions=[{"inc": "done"}])], variables={"done": 0})
    workflow = compiled(tmp_path, [earlier, retested, final])
    result, replay, clock = run_synthetic(workflow, [frame(BLUE), frame(RED, GREEN), blank()])
    assert result.status == "success", result.summary()
    assert not replay.inputs and replay.screenshot_calls == 2
    assert result.variables["run_times_2"] == 0
    assert clock.ms == 1200
    assert "handler_1_group_0_unmatched" in [sid for _, sid in result.history]
    assert "h2_fresh" in [sid for _, sid in result.history]


def test_runner_count_assignments_preserve_click_found_anchor(tmp_path):
    source = handler(1, [case("anchor", condition={"find": "anchor"}, counter=1,
                             actions=[{"click_found": True, "offset": [0, 0, 0, 0], "delay": 0}, {"inc": "done"}])],
                     variables={"done": 0})
    source["resource_specs"] = {"anchor": {"type": "find_colors", "region": [0, 0, 1280, 720],
                                            "groups": [[[250, 150, "#33ff77"]]]}}
    image = blank()
    paint_points(image, [[250, 150, "#33ff77"]])
    result, replay, _ = run_synthetic(compiled(tmp_path, [source]), [image, blank()])
    assert result.status == "success", result.summary()
    assert replay.inputs == [("tap", 250, 150)]
    assert result.variables["run_times_1"] == 1


@pytest.mark.parametrize("period_ms, expected", [(7500, 1), (7501, 3)])
def test_runner_counter_boundary_and_suppressed_timestamp_refresh(tmp_path, period_ms, expected):
    source = handler(1, [case("count", counter=1, actions=[{"inc": "cycles"}])], variables={"cycles": 0})
    workflow = compiled(tmp_path, [source], stop="handler_phase == 0 and cycles == 3", loop_ms=period_ms)
    result, replay, clock = run_synthetic(workflow, [blank()], max_seconds=40)
    assert result.status == "success", result.summary()
    assert result.variables["cycles"] == 3 and result.variables["run_times_1"] == expected
    assert result.variables["handler_last_ms"] == period_ms * 2
    assert result.variables["handler_last_handled_ms"] == period_ms * 2
    assert replay.screenshot_calls == 3 and not replay.inputs
    assert clock.ms == period_ms * 3


def test_runner_actual_038_component_counts_but_yields_to_next_handler(tmp_path):
    source = component_fixture(tmp_path / "component", 38, 4)
    final = handler(2, [case("done", actions=[{"inc": "done"}])], variables={"done": 0})
    workflow = compiled(tmp_path, [source, final])
    image = frame({"colors": [[10, 20, "#ff0000"], [11, 20, "#ff0000"]]})
    result, replay, _ = run_synthetic(workflow, [image, blank()])
    assert result.status == "success", result.summary()
    assert replay.screenshot_calls == 1 and not replay.inputs
    assert result.variables["run_times_38"] == 1
    assert "h0_empty_1" in [sid for _, sid in result.history]
    assert "h1_done" in [sid for _, sid in result.history]


def test_runner_actual_509_component_latches_guard_after_flag_clear(tmp_path):
    source = component_fixture(tmp_path / "component", 509, 17)
    # Existing nav action includes a source-mandated 1000ms wait. Add a test-only
    # completion counter after that complete source handler invocation.
    source["vars"]["done"] = 0
    for branch in source["cases"]:
        if branch["return"] is True:
            branch["do"].append({"inc": "done"})
    workflow = compiled(tmp_path, [source])
    image = frame({"colors": [[13, 20, "#ff0000"], [10, 20, "#ff0000"]]})
    result, replay, clock = run_synthetic(workflow, [image, blank()])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and replay.screenshot_calls == 1
    assert result.variables["change_shikigami_flag"] is False
    assert clock.ms == 1200
    assert "h0_op_3" in [sid for _, sid in result.history]
    assert "h0_op_0" in [sid for _, sid in result.history]


def test_runner_cycle_boundary_resume_continues_elapsed_ms_without_counter_reset(tmp_path):
    source = handler(1, [case("once", counter=1, actions=[{"inc": "done"}])], variables={"done": 0})
    workflow = compiled(tmp_path, [source])
    saved = {"handler_phase": 0, "handler_last_id": 1, "handler_last_ms": 7500,
             "handler_last_handled_ms": 7500, "run_times_1": 1, "elapsed_ms": 15000}
    before = copy.deepcopy(saved)
    result, replay, _ = run_synthetic(workflow, [blank()], initial_vars=saved)
    assert result.status == "success", result.summary()
    assert saved == before  # Caller-owned retry data is not mutated.
    assert result.variables["run_times_1"] == 1  # delta == 7500 is suppressed.
    assert result.variables["handler_last_ms"] == 15000
    assert result.variables["handler_last_handled_ms"] == 15000
    assert result.variables["elapsed_ms"] == 15200
    assert not replay.inputs
    fresh, _, _ = run_synthetic(workflow, [blank()])
    assert fresh.variables["run_times_1"] == 1 and fresh.variables["handler_last_ms"] == 0
    assert fresh.variables["elapsed_ms"] == 200


def test_runner_bounded_stop_preserves_nonzero_phase_and_does_not_replay_on_resume(tmp_path):
    source = handler(1, [case("click", counter=1, actions=[{"click": [300, 300, 300, 300], "delay": 0}])])
    workflow = compiled(tmp_path, [source], stop="False")
    limited, replay, _ = run_synthetic(workflow, [blank()], max_actions=1)
    assert limited.status == "limit", limited.summary()
    assert replay.inputs == [("tap", 300, 300)]
    assert limited.variables["handler_phase"] != 0  # No silent reset after bounded termination.
    try:
        resumed, replay, _ = run_synthetic(workflow, [blank()], initial_vars=limited.variables, max_actions=1)
    except WorkflowError as error:
        assert re.search(r"resume|phase|恢复|中途", str(error), re.I)
    else:
        assert resumed.status == "failed", resumed.summary()
        assert not replay.inputs
        assert resumed.variables["handler_phase"] == limited.variables["handler_phase"]
        assert re.search(r"resume|phase|恢复|中途", resumed.reason, re.I)


def test_runner_handler_control_requires_raw_dispatch_contract(tmp_path):
    workflow = compiled(tmp_path, [handler(1, variables={"done": 0})])
    malformed = copy.deepcopy(workflow.raw)
    malformed.pop("handler_dispatch")
    with pytest.raises(WorkflowError):
        load_workflow(malformed)


def test_runner_not_for_count_and_zero_id_preserve_last_event_metadata(tmp_path):
    source = handler(2, [case("handled", actions=[{"inc": "done"}])], variables={"done": 0})
    source["cases"][0]["count_events"] = [{"counter_id": 2, "not_for_count": True},
                                             {"counter_id": 0, "not_for_count": False}]
    workflow = compiled(tmp_path, [source])
    prior = {"elapsed_ms": 15000, "handler_phase": 0, "handler_last_id": 1,
             "handler_last_ms": 7500, "run_times_1": 3}
    result, replay, _ = run_synthetic(workflow, [blank()], initial_vars=prior)
    assert result.status == "success", result.summary()
    assert not replay.inputs
    assert result.variables["run_times_2"] == 0
    assert result.variables["run_times_1"] == 3
    assert result.variables["handler_last_id"] == 1 and result.variables["handler_last_ms"] == 7500
    assert result.variables["handler_last_handled_ms"] == 15000


@pytest.mark.parametrize("finish", ["completed", "limited", "failed"])
def test_runner_source_timing_contract_is_applied_and_restored_finally(tmp_path, finish):
    actions = [{"click": [400, 400, 400, 400], "delay": 500}, {"inc": "done"}]
    if finish == "failed":
        actions.append({"fail": "synthetic failure after input"})
    source = handler(1, [case("timed", actions=actions)], variables={"done": 0})
    workflow = compiled(tmp_path, [source], base_ms=30)
    clock, replay = MillisecondClock(), SyntheticFrames([blank()])
    original = HumanizeConfig(style="oas", base_sleep_ms=999, random_sleep_ms=0)
    controller = Controller(replay, original, sleep=clock.sleep)
    during = []

    def capture_config(_state, _action, _variables):
        during.append(controller.hcfg)

    result = Runner(workflow, controller, clock=clock, before_input=capture_config,
                    max_actions=1 if finish == "limited" else None, max_seconds=5).run()
    assert result.status == {"completed": "success", "limited": "limit", "failed": "failed"}[finish], result.summary()
    assert replay.inputs == [("tap", 400, 400)]
    assert len(during) == 1
    assert during[0].style == "assttyys" and during[0].base_sleep_ms == 30 and during[0].random_sleep_ms == 0
    assert controller.hcfg is original
    assert clock.ms == (730 if finish == "completed" else 530)


@pytest.mark.parametrize("handler_count", [1, 4])
def test_runner_unknown_timeout_is_not_refreshed_by_internal_wrapper_phases(tmp_path, handler_count):
    definitions = [handler(fid, [case("never_matches", condition=RED)]) for fid in range(1, handler_count + 1)]
    workflow = compiled(tmp_path, definitions, stop="False",
                        limits={"unknown_timeout_s": 1, "max_repeat": 2})
    result, replay, clock = run_synthetic(workflow, [blank()], max_seconds=5)
    assert result.status == "failed" and result.failure_kind == "unknown_screen", result.summary()
    assert not replay.inputs
    assert result.recognized_ticks == 0  # begin/entry/unmatched/end are not source recognition.
    assert 1000 < clock.ms <= 1600  # Timeout, not the unrelated outer five-second trial bound.
    assert replay.screenshot_calls >= 6
    assert result.variables["handler_last_handled_ms"] == -1


def test_runner_repeat_limit_compares_source_case_across_wrapper_cycles(tmp_path):
    disabled = handler(1, [case("disabled")], guard={"expr": "False"})
    repeated = handler(2, [case("again", condition=RED, actions=[{"inc": "hits"}])], variables={"hits": 0})
    workflow = compiled(tmp_path, [disabled, repeated], stop="False", limits={"max_repeat": 2})
    result, replay, clock = run_synthetic(workflow, [frame(RED)], max_seconds=5)
    assert result.status == "failed" and result.failure_kind == "loop", result.summary()
    assert result.failed_state == "h1_again"
    assert result.variables["hits"] == 2  # Third recognition must fail BEFORE re-executing its actions.
    assert not replay.inputs and replay.screenshot_calls == 3
    assert clock.ms == 400


def test_runner_distinct_source_cases_reset_repeat_count(tmp_path):
    source = handler(1, [case("red", condition=RED, actions=[{"inc": "hits"}]),
                         case("green", condition=GREEN, actions=[{"inc": "hits"}])], variables={"hits": 0})
    workflow = compiled(tmp_path, [source], stop="handler_phase == 0 and hits == 4",
                        limits={"max_repeat": 1})
    result, replay, _ = run_synthetic(workflow, [frame(RED), frame(GREEN), frame(RED), frame(GREEN)])
    assert result.status == "success", result.summary()
    assert result.variables["hits"] == 4 and result.recognized_ticks == 4
    assert replay.screenshot_calls == 4 and not replay.inputs


def test_runner_positive_false_return_case_still_refreshes_recognition_timer(tmp_path):
    # An empty-room/probe handler can recognise a screen but legitimately yield.
    # That differs from a cycle in which only generated fallback states matched.
    source = handler(1, [case("probe", condition=RED, handled=False, actions=[{"inc": "hits"}])],
                     variables={"hits": 0})
    workflow = compiled(tmp_path, [source], stop="handler_phase == 0 and hits == 5",
                        limits={"unknown_timeout_s": 0.25})
    result, replay, clock = run_synthetic(workflow, [frame(RED)], max_seconds=5)
    assert result.status == "success", result.summary()
    assert result.recognized_ticks == 5 and result.variables["hits"] == 5
    assert clock.ms == 1000 and replay.screenshot_calls == 5
    assert result.variables["handler_last_handled_ms"] == -1
    assert not replay.inputs
