from pathlib import Path

import pytest

from helpers import FakeClock, blank, fake_text_reader, frame_for, paint_points, register_texts
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


@pytest.mark.parametrize("name", ["orochi", "realm_raid", "exploration", "daily_rewards", "home"])
def test_bundled_workflows_load(name):
    wf = load_workflow(WF_DIR / f"{name}.yaml")
    assert wf.states and wf.resources
    # every state can be painted and is then recognised as itself or an earlier, more specific state
    for st in wf.states:
        if "expr" in str(st["when"]):
            continue
        img = frame_for(wf, st["id"])
        r = Runner(wf, Controller(ReplayDevice([img]), sleep=lambda s: None, observe=True),
                   text_reader=fake_text_reader)
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
    # 3 x (challenge, prepare, auto, win drum, reward screen); after the 3rd run it clicks through the
    # result screens too and stops on the challenge screen without clicking 挑战 again
    assert len(taps) == 15
    assert [s for _, s in res.history][-1].startswith("challenge_done")
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
    clock = FakeClock(step=0.1)
    res = Runner(wf, ctl, params={"max_runs": 1}, clock=clock).run()
    assert res.status == "success", res.summary()
    assert res.variables["runs"] == 1 and res.variables["done"] == 1 and res.variables["pending"] == 0
    assert res.ended - res.started > 60  # the fight alone lasted longer than unknown_timeout_s
    states = [s for _, s in res.history]
    assert "in_battle" in states and "settle_6" not in states
    # 挑战 (twice: the screen had not changed yet), then one per result screen frame; it does not stop on a
    # result screen (live run 2026-11-16 stopped on 统计) but on the challenge screen, without clicking 挑战
    taps = [i for i in dev.inputs if i[0] == "tap"]
    assert len(taps) == 6
    assert states[-1] == "challenge_done_0"


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
    from test_handler_runner import MillisecondClock

    wf = load_workflow(WF_DIR / "orochi.yaml")
    ctl, dev = ctl_for([frame_for(wf, "challenge_0")], observe=True, advance_on_input=False)
    clock = MillisecondClock()
    ctl.sleep = clock.sleep
    res = Runner(wf, ctl, clock=clock, max_seconds=20).run()
    assert res.status == "observed" and dev.inputs == [] and res.recognized_ticks > 5
    assert 20000 <= clock.ms <= 20250


def test_trial_action_limit():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    cycle = [frame_for(wf, "challenge_0"), frame_for(wf, "prepare"), frame_for(wf, "settle_6")]
    ctl, dev = ctl_for(cycle * 10)
    res = Runner(wf, ctl, clock=FakeClock(), max_actions=4).run()
    assert res.status == "limit" and len(dev.inputs) == 4


def test_trial_action_limit_is_checked_between_actions_in_one_state():
    wf = load_workflow({
        "format": 1, "name": "three_clicks",
        "states": [{"id": "step", "when": {"expr": "True"}, "do": [
            {"click": [10, 10, 20, 20]}, {"click": [30, 30, 40, 40]},
            {"click": [50, 50, 60, 60]}, {"stop": "done"}]}],
    })
    ctl, dev = ctl_for([blank(74)])
    res = Runner(wf, ctl, clock=FakeClock(), max_actions=1).run()
    assert res.status == "limit" and res.actions == 1
    assert len([i for i in dev.inputs if i[0] == "tap"]) == 1


def test_business_result_distinguishes_blocked_stop():
    wf = load_workflow({
        "format": 1, "name": "blocked", "states": [{"id": "x", "when": {"expr": "True"},
            "do": [{"stop": {"reason": "页面没打开", "result": "blocked", "verified": False}}]}],
    })
    ctl, _ = ctl_for([blank(75)])
    res = Runner(wf, ctl, clock=FakeClock()).run()
    assert res.status == "success" and res.business_result == "blocked"
    assert not res.business_ok and res.evidence["verified"] is False


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
    assert kinds == ["swipe", "swipe", "swipe", "tap"]



DATA = Path(__file__).parent / "data" / "frames"


@pytest.mark.parametrize("name", ["explore_map_mainline.jpg", "explore_map_mainline.png"])
def test_exploration_picks_last_mainline_chapter_on_real_frame(name):
    """MuMu 12 1280x720 screenshot of the new big exploration map, 「主线」 tab open with chapters 26/27/28.
    The newest (lowest) chapter is clicked, not the old fixed 1156,501."""
    import cv2
    wf = load_workflow(WF_DIR / "exploration.yaml")
    img = cv2.imread(str(DATA / name))
    ctl, dev = ctl_for([img], advance_on_input=False)
    res = Runner(wf, ctl, params={"max_rounds": 1}, clock=FakeClock(), max_actions=1).run()
    assert [s for _, s in res.history][:1] == ["chapter_last"], res.summary()
    taps = [i for i in dev.inputs if i[0] == "tap"]
    assert taps, dev.inputs
    x, y = taps[0][1], taps[0][2]
    assert 1095 <= x <= 1150 and 455 <= y <= 490, taps[0]  # 第二十八章 row (chapter title around 1121,471)


def _paint_at(img, wf, resource, x, y):
    group = wf.resources[resource]["groups"][0]
    paint_points(img, group, x - group[0][0], y - group[0][1])


@pytest.mark.parametrize(("mode", "expected"), [
    ("无差别", (300, 380)), ("打经验", (800, 380)), ("打掉落", (300, 380)),
])
def test_exploration_challenge_modes_select_matching_targets(mode, expected):
    wf = load_workflow(WF_DIR / "exploration.yaml")
    img = frame_for(wf, "leave_map")
    _paint_at(img, wf, "探索_挑战", 300, 380)
    _paint_at(img, wf, "探索_挑战", 800, 380)
    _paint_at(img, wf, "探索_经验标识", 800, 450)
    _paint_at(img, wf, "探索_掉落标识", 300, 450)
    ctl, dev = ctl_for([img])
    Runner(wf, ctl, params={"challenge_type": mode}, clock=FakeClock(), max_actions=1).run()
    assert len(dev.inputs) == 1
    kind, x, y = dev.inputs[0]
    assert kind == "tap"
    assert expected[0] <= x <= expected[0] + 42 and expected[1] <= y <= expected[1] + 51


@pytest.mark.parametrize(("target_x", "target_y", "allowed"), [
    (600, 436, True), (600, 437, False), (939, 420, True), (940, 420, False),
])
def test_exploration_target_distance_and_height_limits(target_x, target_y, allowed):
    wf = load_workflow(WF_DIR / "exploration.yaml")
    img = frame_for(wf, "leave_map")
    _paint_at(img, wf, "探索_挑战", target_x, target_y)
    _paint_at(img, wf, "探索_经验标识", 600, 420)
    ctl, dev = ctl_for([img])
    Runner(wf, ctl, params={"challenge_type": "打经验"}, clock=FakeClock(), max_actions=1).run()
    assert len(dev.inputs) == 1
    assert dev.inputs[0][0] == ("tap" if allowed else "swipe")


def test_exploration_filtered_target_yields_to_boss():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    img = frame_for(wf, "leave_map")
    _paint_at(img, wf, "探索_挑战", 300, 380)
    _paint_at(img, wf, "探索_经验标识", 300, 460)
    _paint_at(img, wf, "探索_挑战BOSS", 850, 310)
    ctl, dev = ctl_for([img])
    res = Runner(wf, ctl, params={"challenge_type": "打经验"}, clock=FakeClock(), max_actions=1).run()
    assert res.history[0][1] == "challenge_boss"
    assert len(dev.inputs) == 1 and 850 <= dev.inputs[0][1] <= 892


def test_exploration_waits_for_label_and_rechecks_before_clicking():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    missing = frame_for(wf, "leave_map")
    _paint_at(missing, wf, "探索_挑战", 300, 380)
    ready = missing.copy()
    _paint_at(ready, wf, "探索_经验标识", 300, 460)
    ctl, dev = ctl_for([missing, ready, missing], advance_on_input=False)
    waits = []

    def on_event(kind, data):
        if kind == "state":
            waits.append(data["state"])

    Runner(wf, ctl, params={"challenge_type": "打经验"}, clock=FakeClock(step=.02), on_event=on_event,
           should_stop=lambda: len(waits) == 2).run()
    assert waits == ["wait_label_打经验", "wait_label_打经验"]
    assert not dev.inputs


def test_exploration_boss_appearing_during_retest_takes_precedence():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    before = frame_for(wf, "leave_map")
    _paint_at(before, wf, "探索_挑战", 300, 380)
    after = before.copy()
    _paint_at(after, wf, "探索_挑战BOSS", 850, 310)
    ctl, dev = ctl_for([before, after], advance_on_input=False)
    result = Runner(wf, ctl, clock=FakeClock(), max_actions=1).run()
    assert result.history[0][1] == "challenge_boss"
    assert len(dev.inputs) == 1 and 850 <= dev.inputs[0][1] <= 892


@pytest.mark.parametrize(("speed", "low", "high"), [("快", 200, 400), ("中", 500, 700), ("慢", 800, 1200)])
def test_exploration_swipe_speeds(speed, low, high):
    wf = load_workflow(WF_DIR / "exploration.yaml")
    ctl, dev = ctl_for([frame_for(wf, "leave_map")])
    Runner(wf, ctl, params={"swipe_speed": speed, "max_swipes": 1}, clock=FakeClock(), max_actions=1).run()
    assert len(dev.inputs) == 1 and dev.inputs[0][0] == "swipe"
    assert low <= ctl.ops[0]["duration_ms"] <= high


def test_exploration_prefers_configured_coordinates_when_selected():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    ctl, dev = ctl_for([frame_for(wf, "chapter_last")])
    result = Runner(wf, ctl, params={"chapter_selection": "坐标", "chapter_x": 1100, "chapter_y": 360},
                    clock=FakeClock(), max_actions=1).run()
    assert result.history[0][1] == "chapter_configured"
    assert len(dev.inputs) == 1 and ctl.ops[0]["rect"] == [1090, 350, 1110, 370]
    with pytest.raises(WorkflowError, match="chapter_x"):
        wf.validate_params({"chapter_x": 1})


@pytest.mark.parametrize("chapter", ["enter_normal", "enter_hard"])
def test_exploration_takes_chest_before_entering_either_chapter(chapter):
    wf = load_workflow(WF_DIR / "exploration.yaml")
    empty = frame_for(wf, chapter)
    with_chest = empty.copy()
    _paint_at(with_chest, wf, "探索_宝箱", 700, 636)
    ctl, dev = ctl_for([with_chest, empty])
    result = Runner(wf, ctl, clock=FakeClock(), max_actions=2).run()
    assert [state for _, state in result.history][:2] == ["chest", chapter]
    assert len(dev.inputs) == 2


def test_exploration_find_pick_last_chooses_lowest_hit():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    spec = wf.resources["探索_主线章节标题"]
    g = spec["groups"][0]
    img = blank(40)
    for dy in (-210, -105, 0):  # three chapter titles stacked like 26 / 27 / 28
        paint_points(img, g, 0, dy)
    r = Runner(wf, Controller(ReplayDevice([img]), sleep=lambda s: None, observe=True))
    assert r._match({"find": "探索_主线章节标题", "pick": "last"}, img)
    assert abs(r._found[1] - g[0][1]) <= 2
    assert r._match({"find": "探索_主线章节标题", "pick": "top"}, img)
    assert abs(r._found[1] - (g[0][1] - 210)) <= 2


def test_exploration_clicks_mainline_tab_when_chapter_list_hidden():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    img = blank(40)
    paint_points(img, wf.resources["探索地图界面"]["points"])
    ctl, dev = ctl_for([img] * 3, advance_on_input=False)
    res = Runner(wf, ctl, params={"max_rounds": 1}, clock=FakeClock(), max_actions=3).run()
    states = [s for _, s in res.history]
    assert states[:2] == ["chapter_tab", "chapter_tab"] and "chapter_map" in states, states


def test_exploration_rounds_done_leaves_map_and_stops_on_chapter_screen():
    """After the boss the run used to stop on the result screen (「点击屏幕继续」). Now it clicks through the
    result, leaves the chapter map, and stops once the big exploration map is back."""
    wf = load_workflow(WF_DIR / "exploration.yaml")
    big = blank(40)
    paint_points(big, wf.resources["探索地图界面"]["points"])
    dialog = frame_for(wf, "confirm_leave_map")
    frames = [frame_for(wf, "boss_appeared"), *_battle_frames(wf, 4), frame_for(wf, "settle_6"),
              frame_for(wf, "rounds_done_leave"), dialog, dialog, big]
    ctl, dev = ctl_for(frames, advance_on_input=False)
    res = Runner(wf, ctl, params={"max_rounds": 1}, clock=FakeClock()).run()
    states = [s for _, s in res.history]
    assert res.status == "success", res.summary()
    assert states[-3:] == ["rounds_done_leave", "confirm_leave_map", "rounds_done"], states
    assert res.variables["rounds"] >= 1


def test_exploration_boss_loss_does_not_finish_a_round():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    frames = [frame_for(wf, state) for state in ("boss_appeared", "settle_lose", "leave_map")]
    ctl, dev = ctl_for(frames)
    result = Runner(wf, ctl, params={"max_rounds": 1}, clock=FakeClock(), max_actions=3).run()
    assert result.variables["rounds"] == 0 and result.variables["losses"] == 1
    assert "rounds_done_leave" not in [state for _, state in result.history]
    assert len(dev.inputs) == 3


def test_exploration_leaves_when_swipes_are_exhausted_and_reenters():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    chapter_map = frame_for(wf, "leave_map")
    dialog = frame_for(wf, "confirm_leave_map")
    frames = [chapter_map, chapter_map, dialog, dialog, frame_for(wf, "enter_hard"), chapter_map]
    ctl, dev = ctl_for(frames, advance_on_input=False)
    result = Runner(wf, ctl, params={"max_swipes": 1}, clock=FakeClock(), max_actions=5).run()
    assert [state for _, state in result.history][:5] == [
        "swipe_map", "leave_map", "confirm_leave_map", "enter_hard", "swipe_map",
    ]
    assert [operation[0] for operation in dev.inputs] == ["swipe", "tap", "tap", "tap", "swipe"]


def test_exploration_sakura_courtyard_targets_explore_not_other_lanterns():
    wf = load_workflow(WF_DIR / "exploration.yaml")
    img = frame_for(wf, "nav_courtyard_sakura")
    ctl, dev = ctl_for([img])
    result = Runner(wf, ctl, clock=FakeClock(), max_actions=1).run()
    assert result.history[0][1] == "nav_courtyard_sakura"
    assert len(dev.inputs) == 1 and 663 <= dev.inputs[0][1] <= 687

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
