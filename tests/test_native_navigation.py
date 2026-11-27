import copy

import pytest

from helpers import FakeClock, blank, fake_text_reader, paint_points, register_texts
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.navigation import NativeNavigator, validate_navigation
from onmyoji_agentflow.workflow.schema import load_workflow


def graph():
    return {"format": 1, "pages": {
        "home": {"when": {"res": "home"}, "category": "global"},
        "explore": {"when": {"res": "explore"}, "category": "global"},
        "other": {"when": {"res": "other"}, "category": "global"}},
        "links": [{"key": "out", "from": "explore", "to": "home", "action": {
            "when": {"res": "back"}, "action": {"click": [10, 10, 20, 20]}}}], "unknown_closers": []}


def matching(*names):
    def match(condition):
        if "res" in condition:
            return condition["res"] in names
        if "all" in condition:
            return all(match(item) for item in condition["all"])
        if "any" in condition:
            return any(match(item) for item in condition["any"])
        if "not" in condition:
            return not match(condition["not"])
        raise AssertionError(condition)
    return match


def test_arrival_needs_two_frames_and_priority_only_reorders_first_frame_candidates():
    raw = graph()
    raw["pages"]["other"]["priority"] = 100
    nav = NativeNavigator(raw, "home")
    assert not nav.step(matching("home"), 0).arrived
    assert nav.step(matching("home", "other"), .5).arrived
    nav = NativeNavigator(raw, "other")
    assert not nav.step(matching("home", "other"), 0).arrived
    assert nav.step(matching("home", "other"), .5).arrived


def test_first_frame_only_match_is_never_arrival():
    nav = NativeNavigator(graph(), "home")
    nav.step(matching("home"), 0)
    assert not nav.step(matching(), .5).arrived
    assert nav.step(matching(), 31).blocked


def test_input_acknowledgement_and_two_frame_edge_arrival():
    nav = NativeNavigator(graph(), "home")
    assert not nav.step(matching("explore", "back"), 0).action
    action = nav.step(matching("explore", "back"), .5)
    assert action.action["click"] == [10, 10, 20, 20]
    assert action.guard == {"res": "back"}
    with pytest.raises(WorkflowError, match="确认导航动作"):
        nav.step(matching("home"), 1)
    nav.acknowledge(True)
    assert not nav.step(matching("home"), 1).arrived
    assert nav.step(matching("home"), 1.5).arrived


def test_observing_an_input_does_not_advance_to_its_target():
    nav = NativeNavigator(graph(), "home")
    nav.step(matching("explore", "back"), 0)
    nav.step(matching("explore", "back"), .5)
    nav.acknowledge(False)
    assert not nav.step(matching("explore", "back"), 1).arrived
    assert nav.phase == "edge_action"


def test_weighted_paths_respect_categories_and_failed_edge_penalties():
    raw = graph()
    raw["links"].extend([
        {"key": "detour", "from": "explore", "to": "other", "cost": 0, "action": {"blocked": "test"}},
        {"key": "other-home", "from": "other", "to": "home", "cost": 0, "action": {"blocked": "test"}}])
    nav = NativeNavigator(raw, "home")
    assert [edge["key"] for edge in nav.path("explore")] == ["out"]
    nav.penalties["out"] = 5
    assert [edge["key"] for edge in nav.path("explore")] == ["detour", "other-home"]
    raw["pages"]["other"]["category"] = "unrelated"
    assert [edge["key"] for edge in nav.path("explore")] == ["out"]


def test_repeated_failed_edge_does_not_reset_no_progress_forever():
    nav = NativeNavigator(graph(), "home")
    nav.step(matching("explore"), 0)
    assert not nav.step(matching("explore"), .1).action
    assert not nav.step(matching("explore"), 7).action
    assert nav.penalties == {"out": 1}
    assert nav.step(matching("explore"), 40).blocked


def test_enter_hooks_run_before_arrival_and_once_per_entry():
    raw = graph()
    raw["pages"]["home"]["hooks"] = {"enter_success": [
        {"when": {"res": "ad"}, "action": {"click": [1, 1, 2, 2]}},
        {"when": {"res": "cancel"}, "action": {"click": [2, 2, 3, 3]}}]}
    nav = NativeNavigator(raw, "home")
    nav.step(matching("home", "ad"), 0)
    assert nav.step(matching("home", "ad"), .1).action
    nav.acknowledge(True)
    assert nav.step(matching("home"), .2).arrived
    assert nav.step(matching("home", "ad"), .3).arrived


def test_no_generic_callback_or_unguarded_raw_hook_runs():
    raw = graph()
    raw["pages"]["home"]["hooks"] = {"enter_success": [{"blocked": "login contract"}]}
    nav = NativeNavigator(raw, "home")
    nav.step(matching("home"), 0)
    assert nav.step(matching("home"), .1).blocked == "login contract"
    raw["pages"]["home"]["hooks"] = {"enter_success": [{"callback": "anything"}]}
    with pytest.raises(WorkflowError):
        validate_navigation(raw, {}, set())


def test_native_runner_uses_cancellation_and_trial_input_boundaries():
    # A persistent frame should still need two observations before one tap,
    # then the trial limit must stop any second planner input.
    resources = {name: {"type": "colors", "points": [[x, 50, "#ffffff"]]}
                 for name, x in (("home", 50), ("explore", 60), ("other", 70), ("back", 80))}
    raw = {"format": 1, "name": "native-navigation", "inline_resources": resources,
           "vars": {"arrived": 0}, "navigation": graph(), "states": [
               {"id": "done", "when": {"all": [{"expr": "arrived == 1"}, {"res": "home"}]},
                "do": [{"stop": {"reason": "home", "result": "completed", "verified": True}}]},
               {"id": "navigation", "when": {"any": [{"res": name} for name in resources]},
                "do": [{"navigate": {"destination": "home", "done_var": "arrived"}}]}]}
    wf = load_workflow(raw)
    image = blank()
    for name in ("explore", "back"):
        paint_points(image, resources[name]["points"])
    device = ReplayDevice([image])
    ctl = Controller(device, sleep=lambda _: None)
    calls = []
    result = Runner(wf, ctl, clock=FakeClock(.05), max_actions=1,
                    before_input=lambda *args: calls.append(args[0]["when"])).run()
    assert result.status == "limit", result.summary()
    assert result.actions == 1
    assert calls == [{"res": "back"}]
    assert len(device.inputs) == 1


def test_unknown_graph_target_is_rejected_before_execution():
    raw = {"format": 1, "name": "bad", "vars": {"done": 0}, "states": [{"id": "nav",
        "when": {"expr": "True"}, "do": [{"navigate": {"destination": "missing", "done_var": "done"}}]}]}
    with pytest.raises(WorkflowError, match="目标不在"):
        load_workflow(raw)


def test_click_found_uses_position_from_fresh_recheck_frame():
    raw = {"format": 1, "name": "fresh-position", "states": [{"id": "click", "when": {"text": "退出"},
        "do": [{"click_found": True, "offset": [0, 0, 1, 1], "recheck": True}, {"stop": "finished"}]}]}
    frames = [register_texts(blank(40), [("退出", 100, 200)]),
              register_texts(blank(50), [("退出", 700, 400)])]
    device = ReplayDevice(frames)
    result = Runner(load_workflow(raw), Controller(device, sleep=lambda _: None),
                    text_reader=fake_text_reader, clock=FakeClock(.01)).run()
    assert result.status == "success", result.summary()
    assert len(device.inputs) == 1
    assert 700 <= device.inputs[0][1] <= 701
    assert 400 <= device.inputs[0][2] <= 401


def test_click_found_can_use_actual_image_match_size_after_recheck(tmp_path):
    import cv2
    import numpy as np
    template = np.random.default_rng(41).integers(0, 255, (17, 23, 3), dtype=np.uint8)
    path = tmp_path / "target.png"
    cv2.imencode(".png", template)[1].tofile(str(path))
    frames = [blank(), blank()]
    frames[0][100:117, 200:223] = template
    frames[1][400:417, 700:723] = template
    raw = {"format": 1, "name": "match-box", "inline_resources": {
        "target": {"type": "image", "path": str(path)}}, "states": [{"id": "click",
        "when": {"res": "target"}, "do": [{"click_found": True, "use_match_size": True, "recheck": True}, {"stop": "done"}]}]}
    device = ReplayDevice(frames)
    result = Runner(load_workflow(raw), Controller(device, sleep=lambda _: None), clock=FakeClock(.01)).run()
    assert result.status == "success", result.summary()
    assert len(device.inputs) == 1
    assert 700 <= device.inputs[0][1] <= 723 and 400 <= device.inputs[0][2] <= 417


def test_native_engine_passes_source_matching_method_mask_and_padded_roi(monkeypatch):
    calls = []
    def matching(image, template, roi, threshold, **kwargs):
        calls.append((template, roi, threshold, kwargs))
        return True, .95, (10, 20, 30, 40)
    monkeypatch.setattr("onmyoji_agentflow.workflow.engine.match_template", matching)
    raw = {"format": 1, "name": "source-method", "inline_resources": {"asset": {
        "type": "image", "path": "unused.png", "mask_path": "unused-mask.png", "roi": [1, 1, 30, 40],
        "roi_expand": 2, "threshold": .92, "method": "Masked template matching"}},
        "states": [{"id": "image", "when": {"res": "asset"}, "do": [{"wait": 1}]}]}
    runner = Runner(load_workflow(raw), Controller(ReplayDevice([blank()]), sleep=lambda _: None))
    assert runner.diagnose_frame(blank())[0]["match"]
    assert calls == [("unused.png", [0, 0, 33, 43], .92,
                      {"method": "Masked template matching", "mask": "unused-mask.png"})]


def test_projected_match_outside_frame_is_rejected_before_budget_or_input(monkeypatch):
    monkeypatch.setattr("onmyoji_agentflow.workflow.engine.match_template", lambda *args, **kwargs:
                        (True, -1, (-10, 20, 50, 60)))
    raw = {"format": 1, "name": "invalid-projection", "inline_resources": {"asset": {
        "type": "image", "path": "unused.png", "method": "Sift Flann"}}, "states": [{
        "id": "click", "when": {"res": "asset"}, "do": [{"click_found": True, "use_match_size": True, "recheck": True}]}]}
    device = ReplayDevice([blank()])
    calls = []
    result = Runner(load_workflow(raw), Controller(device, sleep=lambda _: None), clock=FakeClock(.01),
                    before_input=lambda *args: calls.append(args)).run()
    assert result.failure_kind == "recognition" and result.actions == 0
    assert not calls and not device.inputs


def test_choice_short_circuits_and_sequence_keeps_success_index():
    raw = graph()
    raw["pages"]["home"]["hooks"] = {"enter_success": [{"choice": [
        {"when": {"res": "ad"}, "action": {"click": [1, 1, 2, 2]}},
        {"action": {"click": [9, 9, 10, 10]}}]}]}
    nav = NativeNavigator(raw, "home")
    nav.step(matching("home", "ad"), 0)
    assert nav.step(matching("home", "ad"), .1).action["click"] == [1, 1, 2, 2]
    nav.acknowledge(True)
    assert nav.step(matching("home"), .2).arrived


def test_optional_blocked_branch_only_blocks_when_condition_applies():
    raw = graph()
    raw["pages"]["home"]["hooks"] = {"enter_success": [{"when": {"res": "ad"},
        "steps": [{"blocked": "untranslated ad"}]}]}
    nav = NativeNavigator(raw, "home")
    nav.step(matching("home"), 0)
    assert nav.step(matching("home"), .1).arrived
    nav = NativeNavigator(raw, "home")
    nav.step(matching("home", "ad"), 0)
    assert nav.step(matching("home", "ad"), .1).blocked == "untranslated ad"


def test_conditional_sequence_latches_predicate_but_rechecks_each_leaf_target():
    raw = graph()
    raw["pages"]["home"]["hooks"] = {"enter_success": [{"when": {"res": "ad"}, "steps": [{
        "steps": [{"when": {"res": "ad"}, "action": {"click": [1, 1, 2, 2]}},
                  {"when": {"res": "next"}, "action": {"click": [3, 3, 4, 4]}}]}]}]}
    nav = NativeNavigator(raw, "home")
    nav.step(matching("home", "ad"), 0)
    assert nav.step(matching("home", "ad"), .1).action["click"] == [1, 1, 2, 2]
    nav.acknowledge(True)
    decision = nav.step(matching("next"), .2)
    assert decision.action["click"] == [3, 3, 4, 4]
    assert decision.guard == {"res": "next"}
    nav.acknowledge(True)
    assert nav.step(matching("home"), .3).arrived
