"""Compose the actual native battle family through the parent navigation Runner."""
import copy

import pytest

from onmyoji_agentflow.convert.navigation_family import _bind_battle_body
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow
from test_oas_battle import Clock, Scenario, compiler_fixture, normal  # noqa: F401


@pytest.mark.parametrize("won", [True, False])
def test_general_battle_returns_through_navigation_with_original_outcome_and_no_task_receipt(compiler_fixture, won):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile()
    raw = {"format": 1, "name": "composed-navigation-battle", "resources": [], "vars": {"active": "", "done": 0},
        "navigation": {"format": 1, "call_active_var": "active", "pages": {
            "home": {"when": {"res": "home"}},
            "battle": {"when": {"res": "Component_GeneralBattle::I_PREPARE_HIGHLIGHT"},
                       "hooks": {"enter_success": [{"invoke": "battle"}]}}}, "links": [], "unknown_closers": []},
        "states": [{"id": "parent_done", "when": {"all": [{"expr": "done == 1"}, {"res": "home"}]},
            "do": [{"stop": {"reason": "family returned", "result": "unknown", "verified": False}}]},
            {"id": "parent", "when": {"expr": "True"}, "do": [{"navigate": {"destination": "home", "done_var": "done"}}]}],
        "loop_delay_ms": 0, "limits": copy.deepcopy(packet["workflow"]["limits"])}
    _bind_battle_body(raw, packet, "battle", "task")
    resources = {**workflow.resources, "home": {"type": "colors", "points": [[1, 1, "#ffffff"]]}}
    raw["inline_resources"] = resources
    raw["resources"] = []
    clock, events = Clock(), []
    base = normal("I_WIN" if won else "I_FALSE")
    def choose(p, v, d):
        if not v.get("active"):
            if v.get("gb_returned"):
                image = frame()
                image[1, 1] = 255
                return image
            return ["I_PREPARE_HIGHLIGHT"]
        return base(p, v, d)
    device = Scenario(frame, clock, choose)
    runner = Runner(load_workflow(raw), Controller(device, HumanizeConfig(random_sleep_ms=0), sleep=clock.sleep),
        clock=clock, max_seconds=40, on_event=lambda k, e: events.append((k, e)))
    device.runner = runner
    result = runner.run()
    assert result.status == "success", result.summary()
    assert result.variables["gb_return"] is won and result.variables["gb_current_count"] == 1
    assert result.variables["done"] == 1 and result.variables["active"] == ""
    assert result.business_result == "unknown" and not result.business_ok
    assert any(k == "navigation_call" and e.get("result") is won for k, e in events)
    assert len(device.inputs) > 0 and result.actions == len(device.inputs)
    assert "parent_done" == result.history[-1][1]
