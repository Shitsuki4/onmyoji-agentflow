import pytest

from onmyoji_agentflow.convert.handlers import UnsupportedHandler, compose_handlers, phase_workflow
from onmyoji_agentflow.convert.scheme_lifecycle import bind_named_schemes
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import MillisecondClock, frame, run_synthetic
from test_handlers import case, handler


RED = {"colors": [[40, 50, "#ff0000"]]}
GREEN = {"colors": [[60, 70, "#00ff00"]]}
RERUN = {"scheme_transition": {"mode": "rerun", "target": "返回庭院"}}


def compile_stage(label, branch, *, defaults, value):
    model = handler(7, [branch], variables=defaults, params={"value": {"default": 1}})
    program = compose_handlers(label, [model], config_overrides={"7": {"value": value}},
                               common_overrides={"afterClickDelayRandom": 0})
    return phase_workflow(program, supported_primitives={"handler_control", "scheme_transition"},
                          supported_builtins={"elapsed_ms"})["workflow"]


def stages(continuation=None):
    local = {"local_progress": 0, "super_next_scheme_name": "",
             "core0_run_start_ms": 0, "core0_current_date_ms": 0}
    source = case("finished", condition=RED, counter=7, actions=[
        {"click": [100, 100, 100, 100], "delay": 1000},
        {"set": {"local_progress": "value", "super_next_scheme_name": repr("保留")}},
        RERUN, *(continuation if continuation is not None else [{"wait": 1000}]),
    ])
    target = case("arrived", condition={"all": [GREEN, {"expr":
        "local_progress == 0 and value == 52 and super_next_scheme_name == '保留'"}]},
        counter=7, actions=[
            {"click": [200, 200, 200, 200], "delay": 0},
            {"stop": {"reason": "target checkpoint", "result": "unknown", "verified": False}},
        ])
    return {"战斗": compile_stage("battle", source, defaults=local, value=81),
            "返回庭院": compile_stage("yard", target, defaults=local, value=52)}


def test_named_rerun_uses_one_run_preserves_count_history_and_restarts_local_clocks():
    raw = bind_named_schemes("guild_rerun", "战斗", stages())
    old_branch = next(s for s in raw["states"] if s["id"].endswith("_finished"))
    assert old_branch["do"][-1] == RERUN
    assert old_branch["interrupted_after_rerun"][0] == {"wait": 1000}
    wf = load_workflow(raw)
    result, replay, clock = run_synthetic(wf, [frame(RED), frame(GREEN)])
    assert result.status == "success" and result.business_result == "unknown", result.summary()
    assert replay.inputs == [("tap", 100, 100), ("tap", 200, 200)]
    assert replay.screenshot_calls == 2 and clock.ms == 1510
    assert result.variables["source_active_scheme"] == "返回庭院"
    assert result.variables["run_times_7"] == 0  # Reset count, preserve last input id/time.
    assert result.variables["handler_last_id"] == 7
    switch = result.evidence["scheme_history"][1]["entered_ms"]
    assert abs(switch - 1510) <= 1
    assert result.variables["core0_run_start_ms"] == result.variables["core0_current_date_ms"] == switch
    assert [entry["scheme"] for entry in result.evidence["scheme_history"]] == ["战斗", "返回庭院"]


@pytest.mark.parametrize("transition", [{"mode": "rerun", "target": "战斗"}, {"mode": "previous"}])
def test_linked_reruns_keep_stage_coordinates_and_count_history_visits(transition):
    history = {"core0_history_available": False, "core0_history_count": 0}
    returned = case("returned", condition={"expr": "core0_history_available and core0_history_count == 2"},
                    actions=[{"stop": "visited initial scheme twice"}])
    initial = case("first", condition=RED, actions=[{"click": {"xy_param": "xy", "radius": 20}}, RERUN])
    second = case("second", condition=GREEN, actions=[{"click": {"xy_param": "xy"}},
        {"scheme_transition": transition}])

    def stage(label, branches, xy):
        model = handler(7, branches, variables=history, params={"xy": {"default": xy}})
        program = compose_handlers(label, [model], common_overrides={"afterClickDelayRandom": 0})
        return phase_workflow(program, supported_primitives={"handler_control", "scheme_transition"},
                              supported_builtins={"elapsed_ms"})["workflow"]

    raw = bind_named_schemes("revisited", "战斗", {
        "战斗": stage("battle", [returned, initial], "210,310"),
        "返回庭院": stage("yard", [second], "510，610"),
    })
    rectangles = [step["click"] for state in raw["states"] for step in state["do"] if "click" in step]
    assert rectangles == [[190, 290, 230, 330], [500, 600, 520, 620]]
    result, replay, _ = run_synthetic(load_workflow(raw), [frame(RED), frame(GREEN)])
    assert result.status == "success" and len(replay.inputs) == 2, result.summary()
    assert result.variables["core0_history_count"] == 2
    assert [entry["scheme"] for entry in result.evidence["scheme_history"]] == ["战斗", "返回庭院", "战斗"]


def test_previous_scheme_in_first_entry_stops_without_inputs_or_verified_receipt():
    branch = case("previous_from_first", actions=[{"scheme_transition": {"mode": "previous"}},
                                                  {"wait": 3000}])
    raw = bind_named_schemes("previous", "战斗", {"战斗": compile_stage("battle", branch, defaults={}, value=1)})
    result, replay, clock = run_synthetic(load_workflow(raw), [frame(RED)])
    assert result.status == "success" and "第一个方案" in result.reason and not result.business_ok
    assert not replay.inputs and clock.ms == 0 and len(result.evidence["scheme_history"]) == 1


@pytest.mark.parametrize("kwargs", [{"max_actions": 1}, {"max_seconds": 1.2}])
def test_rerun_respects_original_time_and_action_limits(kwargs):
    wf = load_workflow(bind_named_schemes("bounded", "战斗", stages()))
    result, replay, _ = run_synthetic(wf, [frame(RED), frame(GREEN)], **kwargs)
    assert result.status == "limit", result.summary()
    assert replay.inputs == [("tap", 100, 100)]
    assert len(result.evidence["scheme_history"]) == 1


def test_named_rerun_cancellation_does_not_enter_target():
    clock = MillisecondClock()
    replay = ReplayDevice([frame(RED), frame(GREEN)], advance_on_input=False)
    ctl = Controller(replay, HumanizeConfig(base_sleep_ms=0, random_sleep_ms=0), sleep=clock.sleep)
    wf = load_workflow(bind_named_schemes("cancelled", "战斗", stages()))
    result = Runner(wf, ctl, clock=clock, should_stop=lambda: clock.ms >= 1250).run()
    assert result.status == "stopped" and len(result.evidence["scheme_history"]) == 1, result.summary()
    assert replay.inputs == [("tap", 100, 100)]


def test_named_rerun_rejects_unbound_target_and_unimplemented_continuation():
    available = stages()
    available.pop("返回庭院")
    with pytest.raises(UnsupportedHandler, match="unbound rerun target"):
        bind_named_schemes("missing", "战斗", available)
    with pytest.raises(UnsupportedHandler, match="unsupported caller continuation"):
        bind_named_schemes("suffix", "战斗", stages([{"click": [1, 1, 1, 1]}]))


@pytest.mark.parametrize("defect", ["unscoped_state", "state_overwrites_scheme", "wrong_phase", "external_target"])
def test_lifecycle_schema_validates_entire_route(defect):
    raw = bind_named_schemes("invalid", "战斗", stages())
    switch = next(s for s in raw["states"] if s["id"].endswith("_finished"))
    if defect == "unscoped_state":
        switch["when"] = {"expr": "True"}
    elif defect == "state_overwrites_scheme":
        switch["do"].insert(0, {"set": {"source_active_scheme": "'返回庭院'"}})
    elif defect == "wrong_phase":
        raw["scheme_lifecycle"]["schemes"]["返回庭院"]["reset"]["handler_phase"] = 1
    else:
        switch["do"][-1] = {"scheme_transition": {"mode": "rerun", "target": "外部方案"}}
    with pytest.raises(WorkflowError):
        load_workflow(raw)


def test_rerun_rejects_untrusted_resume_at_a_target_without_history():
    wf = load_workflow(bind_named_schemes("resume", "战斗", stages()))
    result, replay, _ = run_synthetic(wf, [frame(GREEN)], initial_vars={"source_active_scheme": "返回庭院"})
    assert result.failure_kind == "scheme_lifecycle", result.summary()
    assert not replay.inputs and replay.screenshot_calls == 0
