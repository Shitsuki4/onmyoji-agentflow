"""Closed callback composition in the same Runner, with budget/replay guards."""
import copy

import pytest

from helpers import blank, paint_points
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import BudgetExceeded, RunFailure, WorkflowError
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.navigation import NativeNavigator
from onmyoji_agentflow.workflow.schema import load_workflow


def packet():
    names = ("home", "battle", "other", "click", "win", "loss")
    resources = {n: {"type": "colors", "points": [[20 + i*10, 40, "#ffffff"]]} for i, n in enumerate(names)}
    body = [
        {"id": "body_entry", "when": {"expr": "phase == 'entry'"},
         "do": [{"inc": "count"}, {"set": {"phase": "'fight'"}}]},
        {"id": "body_win", "when": {"res": "win"},
         "do": [{"set": {"result": True}}, {"navigation_return": "battle"}]},
        {"id": "body_loss", "when": {"res": "loss"},
         "do": [{"set": {"result": False}}, {"navigation_return": "battle"}]},
        {"id": "body_click", "when": {"res": "click"}, "phase": "battle", "sensitive": "购买",
         "do": [{"click": [200, 200, 210, 210], "delay": 0, "recheck": True}, {"set": {"last_ms": "elapsed_ms"}}]},
        {"id": "body_wait", "when": {"expr": "True"}, "phase": "battle", "do": [{"wait": 100}]}]
    return {"format": 1, "name": "navigation-calls", "inline_resources": resources,
        "vars": {"active": "", "done": 0, "phase": "entry", "count": 0, "result": False, "last_ms": -1000000000},
        "navigation": {"format": 1, "pages": {
            "home": {"when": {"res": "home"}},
            "battle": {"when": {"res": "battle"}, "hooks": {"enter_success": [{"invoke": "battle"}]}},
            "other": {"when": {"res": "other"}, "hooks": {"enter_success": [{"invoke": "battle"}]}}},
            "links": [], "unknown_closers": [], "call_active_var": "active", "calls": {"battle": {
                "states": [s["id"] for s in body], "initial_vars": {"phase": "entry", "count": 0, "result": False,
                    "last_ms": -1000000000}, "result_var": "result"}}},
        "states": [
            {"id": "parent_done", "when": {"all": [{"expr": "done == 1"}, {"res": "home"}]},
             "do": [{"stop": {"reason": "parent returned", "result": "unknown", "verified": False}}]},
            # This deliberately precedes body states; it must never steal their ticks.
            {"id": "parent_drive", "when": {"expr": "True"}, "do": [{"navigate": {"destination": "home", "done_var": "done"}}]},
            *body],
        "loop_delay_ms": 0, "limits": {"timeout_s": 300, "no_progress_timeout_s": 300,
            "stuck_timeout_s": 300, "max_repeat": 100000}}


class Clock:
    def __init__(self):
        self.t = 0.

    def __call__(self):
        return self.t

    def sleep(self, value):
        self.t += value


class Scene(ReplayDevice):
    def __init__(self, raw, choose, clock):
        super().__init__([blank()])
        self.raw, self.choose, self.clock = raw, choose, clock
        self.runner, self.seen = None, []

    def screenshot(self):
        self.clock.t += .1
        variables = dict(self.runner.vars)
        names = self.choose(variables, self)
        self.seen.append((self.clock.t, variables, names))
        image = blank()
        for name in names:
            paint_points(image, self.raw["inline_resources"][name]["points"])
        return image


def run(raw, choose, **options):
    clock, events = Clock(), []
    device = Scene(raw, choose, clock)
    ctl = Controller(device, HumanizeConfig(base_sleep_ms=0, random_sleep_ms=0), sleep=clock.sleep)
    options.setdefault("max_seconds", 120)
    runner = Runner(load_workflow(raw), ctl, clock=clock,
        on_event=lambda k, e: events.append((k, e)), **options)
    device.runner = runner
    return runner.run(), device, events


@pytest.mark.parametrize("won", [True, False])
def test_both_returns_continue_parent_without_child_receipt_or_parent_state_interference(won):
    raw = packet()
    returns = []
    def choose(v, d):
        if v.get("active"):
            return ["win" if won else "loss"]
        if not returns and v.get("count"):
            returns.append(1)
        return ["home"] if returns else ["battle"]
    result, device, events = run(raw, choose)
    assert result.status == "success", result.summary()
    assert result.variables["result"] is won and result.variables["count"] == 1
    assert result.variables["active"] == "" and result.variables["done"] == 1
    assert not device.inputs and not result.business_ok
    assert [e["result"] for k, e in events if k == "navigation_call" and e["event"] == "returned"] == [won]
    states = [s for _, s in result.history]
    start, finish = states.index("body_entry"), states.index("body_win" if won else "body_loss")
    assert "parent_drive" not in states[start:finish+1]


def test_long_callback_suspends_only_navigation_clock_and_resets_locals_for_each_new_instance():
    raw = packet()
    calls, returned = [], []
    def choose(v, d):
        if v["active"]:
            if v["phase"] == "entry":
                calls.append((v["count"], v["last_ms"], d.clock.t))
            entered = calls[-1][2]
            return ["win"] if d.clock.t-entered > 35 else []
        if len(calls) > len(returned) and v["count"]:
            returned.append(len(calls))
        return ["home"] if len(returned) == 2 else ["other"] if returned else ["battle"]
    result, device, _ = run(raw, choose)
    assert result.status == "success", result.summary()
    assert len(calls) == 2 and all(c[:2] == (0, -1000000000) for c in calls)
    assert result.ended-result.started > 70 and result.variables["count"] == 1
    assert not device.inputs


def test_parent_count_stop_is_checked_after_callback_return_not_after_entry_count_increment():
    raw = packet()
    raw["stop_when"] = "count >= 1"
    result, device, events = run(raw, lambda v, _: ["win"] if v["active"] else ["battle"])
    assert result.status == "success" and result.variables["active"] == ""
    assert result.variables["result"] is True and result.variables["done"] == 0
    assert any(k == "navigation_call" and e["event"] == "returned" for k, e in events)
    assert not device.inputs and not result.business_ok


def test_parent_trial_resource_confirmation_and_fresh_guard_are_the_only_input_boundary():
    raw = packet()
    spent, confirmations = [], []
    def choose(v, d):
        return ["click"] if v["active"] else ["battle"]
    result, device, _ = run(raw, choose, max_actions=1,
        confirm=lambda category, detail: confirmations.append(category) or True,
        before_input=lambda st, action, v: spent.append((st["id"], action["recheck"], v["actions"])) )
    assert result.status == "limit" and result.actions == 1 and len(device.inputs) == 1
    assert confirmations == ["购买"] and spent == [("body_click", True, 0)]
    assert result.variables["active"] == "battle" and not result.business_ok
    result, device, _ = run(raw, choose, confirm=lambda *_: False)
    assert result.failure_kind == "confirm_denied" and not device.inputs


def test_callback_cannot_extend_parent_time_limit_or_bypass_resource_budget():
    result, device, _ = run(packet(), lambda v, _: [] if v["active"] else ["battle"], max_seconds=1)
    assert result.status == "limit" and result.ended-result.started < 2 and not device.inputs
    def insufficient(*_):
        raise BudgetExceeded("parent resource budget exhausted")
    result, device, _ = run(packet(), lambda v, _: ["click"] if v["active"] else ["battle"],
                            confirm=lambda *_: True, before_input=insufficient)
    assert result.failure_kind == "budget" and not device.inputs


def test_lost_fresh_child_evidence_cannot_send_input_after_confirmation():
    seen = []
    def choose(v, d):
        if v["active"]:
            return [] if seen else ["click"]
        return ["battle"]
    result, device, _ = run(packet(), choose, confirm=lambda *_: seen.append(1) or True)
    assert result.failure_kind == "recognition" and result.actions == 0 and not device.inputs


def test_interrupted_call_resume_is_rejected_before_recognition_or_input():
    result, device, _ = run(packet(), lambda *_: pytest.fail("must reject before capture"),
                            initial_vars={"active": "battle", "count": 1})
    assert result.failure_kind == "navigation_resume" and not device.inputs and not device.seen


def test_return_without_a_matching_planner_context_is_rejected():
    raw = packet()
    runner = Runner(load_workflow(raw), Controller(ReplayDevice([blank()])), clock=Clock())
    runner.vars = dict(raw["vars"])
    with pytest.raises(RunFailure, match="待返回"):
        runner._do(raw["states"][-4], {"navigation_return": "battle"})


@pytest.mark.parametrize("mutate", [
    lambda r: r["navigation"]["calls"]["battle"]["states"].append("not-a-state"),
    lambda r: r["navigation"]["calls"]["battle"].update(callback="arbitrary"),
    lambda r: r["navigation"]["calls"]["battle"]["initial_vars"].update(actions=0),
    lambda r: r["navigation"]["calls"]["battle"]["initial_vars"].update(active=""),
    lambda r: r["navigation"]["calls"]["battle"].update(result_var="missing"),
    lambda r: r["states"][-1]["do"].append({"stop": "parent must not stop"}),
    lambda r: r["states"][-1]["do"].append({"navigate": {"destination": "home", "done_var": "done"}}),
    lambda r: r["states"][-1]["do"].append({"set": {"active": "''"}}),
    lambda r: r["states"][-1].update(when={"text": "input", "var": "active"}),
    lambda r: r["states"][1]["do"][0]["navigate"].update(done_var="active"),
    lambda r: r["states"][-1]["do"].append({"sample_int": {"var": "active", "min": 0, "max": 1}}),
    lambda r: r["states"][1]["do"].append({"navigation_return": "battle"}),
    lambda r: r["states"][-4]["do"].append({"wait": 1}),
    lambda r: r["navigation"]["pages"]["battle"]["hooks"]["enter_success"][0].update(invoke="unbound"),
])
def test_invalid_or_nested_call_contracts_fail_before_execution(mutate):
    raw = packet()
    mutate(raw)
    with pytest.raises(WorkflowError):
        load_workflow(raw)


def test_same_call_cannot_own_other_invocation_states_or_variables():
    raw = packet()
    raw["navigation"]["calls"]["other"] = copy.deepcopy(raw["navigation"]["calls"]["battle"])
    with pytest.raises(WorkflowError, match="不重叠"):
        load_workflow(raw)


def test_declared_missing_config_branch_returns_false_without_a_body():
    raw = packet()
    raw["navigation"].pop("calls")
    raw["navigation"].pop("call_active_var")
    raw["states"] = raw["states"][:2]
    raw["navigation"]["pages"]["battle"]["hooks"]["enter_success"] = [{"result": False}]
    raw["navigation"]["pages"]["other"]["hooks"]["enter_success"] = []
    nav = NativeNavigator(raw["navigation"], "battle")
    match = lambda c: c.get("res") == "battle"
    assert not nav.step(match, 0).arrived
    assert nav.step(match, .1).arrived
    load_workflow(raw)
