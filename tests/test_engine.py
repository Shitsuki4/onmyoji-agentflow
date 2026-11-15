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


def _battle_frames(wf, n):
    # the real battle screen animates: alternate two backgrounds so "screen unchanged" never fires
    return [frame_for(wf, "in_battle", base=40 if i % 2 else 70) for i in range(n)]


def test_orochi_long_battle_without_victory_drum_counts_and_stops():
    """Win10 + MuMu 12 run 000029/000031: battle > 60 s, then 统计 -> 达摩 (no drum), back on the challenge
    screen with max_runs=1. It used to fail with "60 秒内认不出当前画面" and done=0."""
    wf = load_workflow(WF_DIR / "orochi.yaml")
    frames = ([frame_for(wf, "challenge_0")] * 2 + _battle_frames(wf, 200)
              + [frame_for(wf, "settle_11")] * 2 + [frame_for(wf, "settle_4")] * 2
              + [frame_for(wf, "challenge_done_0")])
    ctl, dev = ctl_for(frames, advance_on_input=False)
    clock = FakeClock()
    res = Runner(wf, ctl, params={"max_runs": 1}, clock=clock).run()
    assert res.status == "success", res.summary()
    assert res.variables["runs"] == 1 and res.variables["done"] == 1 and res.variables["pending"] == 0
    assert res.ended - res.started > 60  # the fight alone lasted longer than unknown_timeout_s
    states = [s for _, s in res.history]
    assert "in_battle" in states and "settle_6" not in states
    # one click on 挑战, then one per result screen visit; nothing after the run is used up
    taps = [i for i in dev.inputs if i[0] == "tap"]
    assert len(taps) == 3


def test_orochi_counts_each_battle_once_across_result_screens():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    one = ([frame_for(wf, "challenge_0")] + _battle_frames(wf, 4) + [frame_for(wf, "settle_6")]
           + [frame_for(wf, "settle_11")] + [frame_for(wf, "settle_4")])
    ctl, dev = ctl_for(one * 3 + [frame_for(wf, "challenge_0")], advance_on_input=False)
    res = Runner(wf, ctl, params={"max_runs": 5}, clock=FakeClock()).run()
    # 3 battles happened, each counted once even though it showed three result screens
    assert res.variables["runs"] == 4 and res.variables["done"] == 3, res.summary()


def test_orochi_challenge_screen_counts_a_battle_whose_result_was_missed():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    frames = [frame_for(wf, "challenge_0"), *_battle_frames(wf, 4), frame_for(wf, "challenge_0"),
              *_battle_frames(wf, 4), frame_for(wf, "challenge_done_0")]
    ctl, dev = ctl_for(frames, advance_on_input=False)
    res = Runner(wf, ctl, params={"max_runs": 2}, clock=FakeClock()).run()
    assert res.status == "success" and res.variables["done"] == 2, res.summary()


def test_realm_raid_stops_on_raid_screen_when_runs_used_up():
    wf = load_workflow(WF_DIR / "realm_raid.yaml")
    frames = [frame_for(wf, "medal_呱太"), frame_for(wf, "attack"), *_battle_frames(wf, 4),
              frame_for(wf, "settle_11"), frame_for(wf, "raid_done")]
    ctl, dev = ctl_for(frames, advance_on_input=False)
    res = Runner(wf, ctl, params={"max_runs": 1}, clock=FakeClock()).run()
    assert res.status == "success" and res.variables["done"] == 1, res.summary()


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


# --- account prerequisites (requires / blockers) -----------------------------------------------

def _guild_wf():
    return load_workflow({"format": 1, "name": "t", "requires": ["账号已加入阴阳寮"],
                          "blockers": [{"id": "no_guild", "when": {"colors": [[30, 30, "#00ff00"]]},
                                        "message": "账号还没加入阴阳寮，请先在游戏里加入一个阴阳寮"}],
                          "states": [{"id": "a", "when": {"colors": [[10, 10, "#ff0000"]]}, "do": [{"wait": 100}]}]})


def test_blocker_stops_with_prerequisite():
    wf = _guild_wf()
    img = blank()
    img[30, 30] = (0, 255, 0)
    ctl, dev = ctl_for([img])
    res = Runner(wf, ctl, clock=FakeClock()).run()
    assert res.status == "failed" and res.failure_kind == "prerequisite"
    assert "阴阳寮" in res.reason and dev.inputs == []


def test_unknown_screen_mentions_requires():
    wf = _guild_wf()
    ctl, _ = ctl_for([blank()])
    res = Runner(wf, ctl, clock=FakeClock(step=5)).run()
    assert res.failure_kind == "unknown_screen" and "账号已加入阴阳寮" in res.reason


def test_requires_and_blockers_validated():
    with pytest.raises(WorkflowError):
        load_workflow({"format": 1, "name": "t", "requires": "入寮", "states": [{"id": "a", "when": {"expr": "1"}}]})
    with pytest.raises(WorkflowError):
        load_workflow({"format": 1, "name": "t", "blockers": [{"id": "b", "when": {"expr": "1"}}],
                       "states": [{"id": "a", "when": {"expr": "1"}}]})
    assert load_workflow(WF_DIR / "realm_raid.yaml").requires
