import pytest

from helpers import blank
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import Workflow, load_workflow


class Clock:
    def __init__(self):
        self.time, self.waits = 0, []

    def __call__(self):
        return self.time

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.time += seconds


def workflow(actions):
    return {"format": 1, "name": "bounded-sampling", "vars": {"draw": -1},
            "states": [{"id": "sample", "when": {"expr": "True"}, "do": actions}]}


def test_native_integer_sampling_and_random_wait_are_bounded_and_do_not_count_as_inputs(monkeypatch):
    calls = []
    values = iter([500, 650])
    def sample(low, high):
        calls.append((low, high))
        return next(values)
    monkeypatch.setattr("random.randint", sample)
    clock = Clock()
    device = ReplayDevice([blank()])
    wf = load_workflow(workflow([{"sample_int": {"var": "draw", "min": 0, "max": 500}},
                                 {"wait_random": [400, 800]}, {"stop": "done"}]))
    result = Runner(wf, Controller(device, sleep=clock.sleep), clock=clock).run()
    assert result.status == "success" and result.variables["draw"] == 500
    assert result.actions == 0 and not device.inputs
    assert calls == [(0, 500), (400, 800)]
    assert sum(clock.waits) == pytest.approx(.650)


def test_random_wait_remains_cancellable_between_native_wait_chunks(monkeypatch):
    monkeypatch.setattr("random.randint", lambda *args: 800)
    clock = Clock()
    ctl = Controller(ReplayDevice([blank()]), sleep=clock.sleep)
    result = Runner(load_workflow(workflow([{"wait_random": [400, 800]}])), ctl, clock=clock,
                    should_stop=lambda: clock.time >= .25).run()
    assert result.status == "stopped" and result.actions == 0
    assert clock.time == .25


def test_continuous_uniform_wait_preserves_fractional_milliseconds(monkeypatch):
    calls = []
    monkeypatch.setattr("random.uniform", lambda low, high: calls.append((low, high)) or 500.25)
    clock = Clock()
    raw = workflow([{"wait_random": {"min_ms": 400, "max_ms": 800, "distribution": "uniform"}}, {"stop": "done"}])
    result = Runner(load_workflow(raw), Controller(ReplayDevice([blank()]), sleep=clock.sleep), clock=clock).run()
    assert result.status == "success" and calls == [(400, 800)]
    assert clock.time == pytest.approx(.50025)


def test_persisted_random_enum_is_not_resampled_by_a_guarded_initialization(monkeypatch):
    monkeypatch.setattr("random.randint", lambda *args: (_ for _ in ()).throw(AssertionError("must retain prior draw")))
    raw = workflow([])
    raw["states"] = [
        {"id": "init", "when": {"expr": "draw < 0"}, "do": [{"sample_int": {"var": "draw", "min": 0, "max": 500}}]},
        {"id": "done", "when": {"expr": "draw >= 0"}, "do": [{"stop": "done"}]}]
    clock = Clock()
    result = Runner(load_workflow(raw), Controller(ReplayDevice([blank()]), sleep=clock.sleep),
                    clock=clock, initial_vars={"draw": 42}).run()
    assert result.status == "success" and result.variables["draw"] == 42


@pytest.mark.parametrize("action", [
    {"wait_random": [800, 400]}, {"wait_random": [0, 600001]}, {"wait_random": [False, 4]},
    {"sample_int": {"var": "draw", "min": 0, "max": 86400001}},
    {"sample_int": {"var": "draw", "min": 0.5, "max": 2}},
    {"sample_int": {"var": "draw", "min": 0, "max": 2, "callback": "hidden"}},
    {"sample_int": {"var": [], "min": 0, "max": 2}},
])
def test_unbounded_or_executable_sampling_descriptors_are_rejected(action):
    with pytest.raises(WorkflowError):
        load_workflow(workflow([action]))


@pytest.mark.parametrize("name", ["actions", "elapsed_s", "elapsed_ms"])
def test_workflow_cannot_mutate_native_runtime_metrics(name):
    for action in ({"set": {name: 0}}, {"inc": name}, {"sample_int": {"var": name, "min": 0, "max": 5}}):
        with pytest.raises(WorkflowError):
            load_workflow(workflow([action]))


def test_trial_limit_is_authoritative_even_if_raw_unvalidated_code_overwrites_display_counter():
    # Direct Workflow construction intentionally bypasses schema to ensure the
    # execution boundary itself owns the physical input limit.
    raw = workflow([{"click": [10, 10, 20, 20], "delay": 0}, {"set": {"actions": 0}}])
    device, clock = ReplayDevice([blank()]), Clock()
    result = Runner(Workflow(raw), Controller(device, sleep=clock.sleep), clock=clock, max_actions=2).run()
    assert result.status == "limit" and result.actions == 2
    assert result.variables["actions"] == 2 and len(device.inputs) == 2


@pytest.mark.parametrize("package", ["com.game;reboot", "com.game --option", "$(anything)", {"code": "hidden"}])
def test_start_app_cannot_be_used_as_a_shell_or_code_escape(package):
    with pytest.raises(WorkflowError, match="Android 包名"):
        load_workflow(workflow([{"start_app": package}]))
