from pathlib import Path

import pytest

from helpers import FakeClock, blank, frame_for
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import bundled_dir, load_workflow

WF_DIR = bundled_dir() / "workflows"


def ctl_for(frames, observe=False, advance_on_input=True):
    dev = ReplayDevice(frames, advance_on_input=advance_on_input)
    return Controller(dev, HumanizeConfig(), observe=observe, sleep=lambda s: None), dev


@pytest.mark.parametrize("name", ["orochi", "realm_raid", "exploration"])
def test_bundled_workflows_load(name):
    wf = load_workflow(WF_DIR / f"{name}.yaml")
    assert wf.states and wf.resources
    # every state can be painted and is then recognised as itself or an earlier, more specific state
    for st in wf.states:
        if "expr" in str(st["when"]):
            continue
        img = frame_for(wf, st["id"])
        r = Runner(wf, Controller(ReplayDevice([img]), sleep=lambda s: None, observe=True))
        r.vars = {**(wf.raw.get("vars") or {}), "elapsed_s": 0, "actions": 0, **wf.param_defaults()}
        assert r._match(st["when"], img), st["id"]


def test_orochi_full_cycle():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    cycle = [frame_for(wf, "challenge_0"), frame_for(wf, "prepare"), frame_for(wf, "battle_manual"),
             frame_for(wf, "settle_6"), frame_for(wf, "settle_0")]
    frames = cycle * 3 + [frame_for(wf, "challenge_0")]
    ctl, dev = ctl_for(frames)
    res = Runner(wf, ctl, params={"max_runs": 3}, clock=FakeClock()).run()
    assert res.status == "success", res.summary()
    assert res.variables["runs"] == 3 and res.variables["done"] == 3
    taps = [i for i in dev.inputs if i[0] == "tap"]
    # 3 x (challenge, prepare, auto, win drum) + 2 reward screens; stops right after the 3rd result
    assert len(taps) == 14
    # clicks land inside the challenge button area
    x, y = taps[0][1], taps[0][2]
    assert 1148 <= x <= 1235 and 602 <= y <= 663


def test_orochi_stops_when_challenge_does_not_react():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    ctl, dev = ctl_for([frame_for(wf, "challenge_0")])
    res = Runner(wf, ctl, clock=FakeClock()).run()
    assert res.status == "success" and "挑战" in res.reason
    assert len(dev.inputs) == 3


def test_stamina_empty_stops():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    ctl, dev = ctl_for([frame_for(wf, "stamina_empty")])
    res = Runner(wf, ctl, clock=FakeClock()).run()
    assert res.status == "success" and res.reason == "体力不足" and not dev.inputs


def test_unknown_screen_fails():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    ctl, _ = ctl_for([blank()])
    res = Runner(wf, ctl, clock=FakeClock(step=5)).run()
    assert res.status == "failed" and res.failure_kind == "unknown_screen"


def test_loop_detection():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    ctl, _ = ctl_for([frame_for(wf, "prepare")])
    res = Runner(wf, ctl, clock=FakeClock(step=0.1)).run()
    assert res.failure_kind == "loop" and res.failed_state == "prepare"


def test_observe_mode_never_touches():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    ctl, dev = ctl_for([frame_for(wf, "challenge_0")], observe=True, advance_on_input=False)
    res = Runner(wf, ctl, clock=FakeClock(), max_seconds=20).run()
    assert res.status == "observed" and dev.inputs == [] and res.recognized_ticks > 5


def test_trial_action_limit():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    cycle = [frame_for(wf, "challenge_0"), frame_for(wf, "prepare"), frame_for(wf, "settle_6")]
    ctl, dev = ctl_for(cycle * 10)
    res = Runner(wf, ctl, clock=FakeClock(), max_actions=4).run()
    assert res.status == "limit" and len(dev.inputs) == 4


def _sensitive_wf(tmp_path: Path):
    raw = {"format": 1, "name": "t", "vars": {"n": 0}, "stop_when": "n >= 1", "states": [
        {"id": "buy", "sensitive": "购买", "when": {"colors": [[10, 10, "#ff0000"]]},
         "do": [{"click": [0, 0, 20, 20]}, {"inc": "n"}]}]}
    return load_workflow(raw)


def test_sensitive_requires_confirmation(tmp_path):
    wf = _sensitive_wf(tmp_path)
    img = blank()
    img[10, 10] = (0, 0, 255)
    asked = []
    ctl, dev = ctl_for([img])
    res = Runner(wf, ctl, clock=FakeClock(), confirm=lambda c, d: asked.append(c) or False).run()
    assert res.failure_kind == "confirm_denied" and dev.inputs == [] and asked == ["购买"]
    ctl, dev = ctl_for([img])
    res = Runner(wf, ctl, clock=FakeClock(), confirm=lambda c, d: True).run()
    assert res.status == "success" and len(dev.inputs) == 1


def test_schema_rejects_code_and_unknowns():
    base = {"format": 1, "name": "t", "states": [{"id": "a", "when": {"expr": "__import__('os')"}}]}
    with pytest.raises(WorkflowError):
        load_workflow(base)
    base["states"][0]["when"] = {"expr": "x > 1"}
    with pytest.raises(WorkflowError):
        load_workflow(base)
    base["states"][0]["when"] = {"colors": [[1, 1, "#000000"]]}
    base["states"][0]["do"] = [{"confirm": "随便"}]
    with pytest.raises(WorkflowError):
        load_workflow(base)
    base["states"][0]["do"] = [{"click": [1, 2, 3]}]
    with pytest.raises(WorkflowError):
        load_workflow(base)


def test_realm_raid_picks_medal_then_attacks():
    wf = load_workflow(WF_DIR / "realm_raid.yaml")
    frames = [frame_for(wf, "medal_呱太"), frame_for(wf, "attack"), frame_for(wf, "prepare"),
              frame_for(wf, "settle_6"), frame_for(wf, "medal_4")]
    ctl, dev = ctl_for(frames * 2)
    res = Runner(wf, ctl, params={"max_runs": 2}, clock=FakeClock()).run()
    assert res.status == "success" and res.variables["done"] == 2 and res.variables["runs"] == 2, res.summary()


def test_exploration_swipes_then_leaves():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    ctl, dev = ctl_for([frame_for(wf, "leave_map")] * 20, advance_on_input=False)
    res = Runner(wf, ctl, params={"max_rounds": 1, "max_swipes": 3}, clock=FakeClock(), max_actions=5).run()
    kinds = [i[0] for i in dev.inputs]
    assert kinds[:3] == ["swipe", "swipe", "swipe"] and kinds[3] == "tap"
