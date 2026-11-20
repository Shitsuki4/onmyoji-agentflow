"""v0.1.7: OCR text conditions, 补给领取, 回到庭院, 结界突破 refresh / losing streak, 御魂层数, oaf marathon."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from helpers import FakeClock, blank, fake_text_reader, frame_for, register_texts
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.marathon import Marathon, load_plan, parse_deadline
from onmyoji_agentflow.vision.ocr import OcrUnavailable, find_text
from onmyoji_agentflow.workflow.engine import RunResult, Runner
from onmyoji_agentflow.workflow.schema import bundled_dir, load_workflow

WF_DIR = bundled_dir() / "workflows"


def ctl_for(frames, advance_on_input=True):
    dev = ReplayDevice(frames, advance_on_input=advance_on_input)
    return Controller(dev, HumanizeConfig(), sleep=lambda s: None), dev


def run(wf, frames, params=None, advance=True, **kw):
    ctl, dev = ctl_for(frames, advance)
    res = Runner(wf, ctl, params=params or {}, clock=FakeClock(), text_reader=fake_text_reader, **kw).run()
    return res, dev


def taps(dev):
    return [i for i in dev.inputs if i[0] == "tap"]


# ------------------------------------------------------------------ text condition
def _text_wf(**cond):
    return load_workflow({
        "format": 1, "name": "t", "title": "t",
        "states": [{"id": "hit", "when": {"text": "一键领取", **cond},
                    "do": [{"click_found": True, "offset": [-2, -2, 2, 2]}, {"stop": "ok"}]}],
    })


def test_text_condition_clicks_the_found_word():
    wf = _text_wf(region=[0, 600, 400, 80])
    img = register_texts(blank(1), [("一键领取", 106, 619), ("一键领取", 900, 100)])
    res, dev = run(wf, [img])
    assert res.reason == "ok"
    (_, x, y, *_rest), = taps(dev)
    assert abs(x - 106) <= 3 and abs(y - 619) <= 3   # the one inside the region, not the other


def test_text_condition_outside_region_does_not_match():
    wf = _text_wf(region=[0, 600, 400, 80])
    img = register_texts(blank(2), [("一键领取", 900, 100)])
    res, dev = run(wf, [img])
    assert res.status == "failed" and not dev.inputs


def test_text_condition_without_ocr_is_false_and_warns_once():
    def no_ocr(img, region):
        raise OcrUnavailable("OCR 没装")
    wf = _text_wf()
    events = []
    ctl, dev = ctl_for([blank(3)])
    res = Runner(wf, ctl, clock=FakeClock(step=5), text_reader=no_ocr,
                 on_event=lambda k, d: events.append((k, d))).run()
    assert res.status == "failed" and not dev.inputs
    assert sum(1 for k, d in events if k == "log" and "OCR" in d.get("message", "")) == 1


def test_text_condition_schema():
    with pytest.raises(WorkflowError):
        _text_wf(pattern="(")
    with pytest.raises(WorkflowError):
        _text_wf(region=[1, 2, 3])
    assert find_text([("刷新 04:59", 1, 2)], None, r"刷新\d{1,2}[:：]\d{2}") == ("刷新 04:59", 1, 2)
    assert find_text([("刷新", 1, 2)], None, r"刷新\d{1,2}[:：]\d{2}") is None


def test_unknown_screen_event_carries_the_frame_once():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    events = []
    ctl, _ = ctl_for([blank(4)])
    Runner(wf, ctl, clock=FakeClock(step=5), on_event=lambda k, d: events.append((k, d))).run()
    unknown = [d for k, d in events if k == "unknown"]
    assert len(unknown) == 1 and isinstance(unknown[0]["frame"], np.ndarray)


# ------------------------------------------------------------------ daily rewards / home
def test_daily_rewards_claims_mail_and_friend_points_then_stops_in_courtyard():
    wf = load_workflow(WF_DIR / "daily_rewards.yaml")
    court = frame_for(wf, "open_mail", base=10)
    mail = frame_for(wf, "mail_claim", base=11)
    popup = frame_for(wf, "reward_popup", base=12)
    mail_empty = frame_for(wf, "mail_done", base=13)
    friends = frame_for(wf, "friend_collect", base=14)
    friends_done = frame_for(wf, "friend_done", base=15)
    frames = [court, mail, popup, mail_empty, court, friends, friends_done, court]
    res, dev = run(wf, frames)
    assert res.status == "success" and "补给领取流程结束" in res.reason, res.summary()
    assert not res.business_ok
    assert res.variables["claimed"] >= 1
    backs = [i for i in dev.inputs if i[0] == "back"]
    assert len(backs) == 2      # one per screen, never a third one in the courtyard


def test_text_cache_never_hands_a_new_screen_the_old_screens_words():
    # the OCR cache used to be keyed by id(frame); freed screenshots reuse ids, so a later screen
    # could read as the previous one. Run the same scenario many times so reused ids show up.
    for _ in range(30):
        test_daily_rewards_claims_mail_and_friend_points_then_stops_in_courtyard()


def test_daily_rewards_does_not_press_back_twice_while_mail_closes():
    wf = load_workflow(WF_DIR / "daily_rewards.yaml")
    mail_empty = frame_for(wf, "mail_done", base=16)
    court = frame_for(wf, "open_mail", base=17)
    ctl, dev = ctl_for([mail_empty, mail_empty, mail_empty, court], advance_on_input=False)
    seq = iter([mail_empty, mail_empty, mail_empty] + [court] * 50)
    dev.screenshot = lambda: next(seq)
    r = Runner(wf, ctl, clock=FakeClock(), text_reader=fake_text_reader)
    r.run()
    assert sum(1 for i in dev.inputs if i[0] == "back") == 1


def test_exit_dialog_is_cancelled():
    for name in ("home", "daily_rewards", "orochi", "realm_raid", "exploration"):
        wf = load_workflow(WF_DIR / f"{name}.yaml")
        img = frame_for(wf, "exit_dialog", base=20)
        ctl, dev = ctl_for([img], advance_on_input=False)
        r = Runner(wf, ctl, clock=FakeClock(), text_reader=fake_text_reader)
        r.vars = {**r.vars}
        r.run()
        assert taps(dev) and all(abs(t[1] - 805) < 40 and abs(t[2] - 440) < 30 for t in taps(dev)), name


def test_home_stops_in_courtyard_and_presses_back_elsewhere():
    wf = load_workflow(WF_DIR / "home.yaml")
    court = frame_for(wf, "courtyard", base=30)
    res, dev = run(wf, [blank(31), blank(32), court], advance=False)
    assert res.status == "success" and res.reason == "已回到庭院"
    assert not dev.inputs


def test_home_gives_up_after_eight_backs():
    wf = load_workflow(WF_DIR / "home.yaml")
    res, dev = run(wf, [blank(33)], advance=False)
    assert res.status == "failed" and res.failure_kind == "unknown_screen" and not dev.inputs


# ------------------------------------------------------------------ navigation / layer
@pytest.mark.parametrize("name,param", [("orochi", "max_runs"), ("realm_raid", "max_runs"),
                                        ("exploration", "max_rounds")])
def test_workflows_walk_in_from_the_courtyard(name, param):
    wf = load_workflow(WF_DIR / f"{name}.yaml")
    court = frame_for(wf, "nav_courtyard", base=40)
    ctl, dev = ctl_for([court], advance_on_input=False)
    Runner(wf, ctl, params={param: 1}, clock=FakeClock(), text_reader=fake_text_reader).run()
    assert taps(dev), name
    # done -> never walks back in
    ctl, dev = ctl_for([court], advance_on_input=False)
    Runner(wf, ctl, params={param: 1}, clock=FakeClock(step=5), text_reader=fake_text_reader,
           initial_vars={"runs" if param == "max_runs" else "rounds": 1}).run()
    assert not taps(dev), name


def test_orochi_selects_layer_once():
    wf = load_workflow(WF_DIR / "orochi.yaml")
    layer = frame_for(wf, "layer_3", base=50)
    ctl, dev = ctl_for([layer], advance_on_input=False)
    r = Runner(wf, ctl, params={"layer": 3, "max_runs": 1}, clock=FakeClock(step=5), text_reader=fake_text_reader)
    res = r.run()
    assert res.variables["layer_set"] == 1
    (_, x, y, *_r), = taps(dev)
    assert 110 <= x <= 170 and 323 <= y <= 347
    # layer 0 (default) never touches the list
    ctl, dev = ctl_for([layer], advance_on_input=False)
    Runner(wf, ctl, params={"max_runs": 1}, clock=FakeClock(step=5), text_reader=fake_text_reader).run()
    assert not taps(dev)


# ------------------------------------------------------------------ realm raid refresh / losing
def test_realm_raid_refreshes_when_page_is_done():
    wf = load_workflow(WF_DIR / "realm_raid.yaml")
    page = frame_for(wf, "refresh", base=60)
    confirm = frame_for(wf, "refresh_confirm", base=61)
    ctl, dev = ctl_for([page, confirm, blank(62)])
    res = Runner(wf, ctl, params={"max_runs": 5}, clock=FakeClock(step=5), text_reader=fake_text_reader).run()
    assert res.variables["refreshes"] == 1
    t = taps(dev)
    assert 990 <= t[0][1] <= 1120 and all(700 <= x <= 820 for _, x, *_r in t[1:]), t


def test_realm_raid_stops_when_refresh_is_cooling_down():
    wf = load_workflow(WF_DIR / "realm_raid.yaml")
    res, dev = run(wf, [frame_for(wf, "refresh_cooling", base=63)], params={"max_runs": 5}, advance=False)
    assert res.status == "success" and "冷却" in res.reason and not taps(dev), res.summary()


def test_realm_raid_without_auto_refresh_stops():
    wf = load_workflow(WF_DIR / "realm_raid.yaml")
    res, dev = run(wf, [frame_for(wf, "refresh", base=64)], params={"max_runs": 5, "auto_refresh": 0}, advance=False)
    assert res.status == "success" and "本页结界都打过了" in res.reason and not taps(dev)


def test_realm_raid_losing_streak_refreshes_then_stops():
    wf = load_workflow(WF_DIR / "realm_raid.yaml")
    lose = frame_for(wf, "settle_lose", base=65)
    page = frame_for(wf, "lose_refresh", base=66)
    # two lost battles, back on a page that still has the medal: refresh instead of attacking it again
    ctl, dev = ctl_for([page], advance_on_input=False)
    res = Runner(wf, ctl, params={"max_runs": 9}, clock=FakeClock(step=5), text_reader=fake_text_reader,
                 initial_vars={"streak": 2}).run()
    assert res.variables["refreshes"] >= 1 and res.variables["streak"] == 0
    # refreshes used up -> stop with the reason
    ctl, dev = ctl_for([page], advance_on_input=False)
    res = Runner(wf, ctl, params={"max_runs": 9, "max_refresh": 0}, clock=FakeClock(), text_reader=fake_text_reader,
                 initial_vars={"streak": 2}).run()
    assert res.status == "success" and "连续打输" in res.reason and not taps(dev)
    # the lose screen counts the streak, a win resets it
    ctl, dev = ctl_for([lose, frame_for(wf, "settle_11", base=67)])
    r = Runner(wf, ctl, params={"max_runs": 9}, clock=FakeClock(step=5), text_reader=fake_text_reader)
    seen = []
    r.on_event = lambda k, d: seen.append(dict(d["vars"])) if k == "state" else None
    r.run()
    assert any(v.get("streak") == 1 for v in seen), seen
    assert r.vars["streak"] == 0


# ------------------------------------------------------------------ marathon
class StepClock(FakeClock):
    def sleep(self, s):
        self.t += s


class FakeSupervisor:
    def __init__(self, script):
        self.script = script          # workflow -> list of (status, reason, vars)
        self.calls = []
        self.event_sink = None

    def run(self, workflow, instance, params, repair=False):
        self.calls.append((workflow, dict(params)))
        seq = self.script.get(workflow) or [("success", "ok", {})]
        status, reason, variables = seq.pop(0) if len(seq) > 1 else seq[0]
        if workflow == "orochi" and self.event_sink:
            self.event_sink(instance, "unknown", {"frame": blank(70), "after_state": "in_battle", "seconds": 11})
        res = RunResult(workflow, status, reason, variables=dict(variables))
        if status == "failed":
            res.last_frame = blank(71)
        return SimpleNamespace(result=res, notes=[], level="ok")

    def stop(self, instance):
        pass

    def execution(self, instance, owner):
        from contextlib import nullcontext
        return nullcontext()


# 2026-11-17 之前的刷本计划，测试按它写的
GRIND_PLAN = {
    "continuous": True,
    "pause_s": 60,            # pause between rounds
    "home_between": True,     # bring the game back to the courtyard before every item
    "max_home_failures": 3,   # this many failed ``home`` runs in a row -> stop, a human is needed
    "items": [
        {"workflow": "daily_rewards", "cooldown_min": 240},
        # only the 3 weakest per page, then refresh; stop and keep the tickets below 50 % wins
        {"workflow": "realm_raid", "params": {"max_runs": 30, "auto_refresh": 1, "max_refresh": 10,
                                              "weak_first": 1, "wins_per_page": 3, "min_win_pct": 50},
         "cooldown_min": 30, "cooldown_on": {"突破券": 120, "胜率低": 180, "冷却": 6}},
        # 魂十: 叁层 only drops low-star souls; 拾层 cleared 7/7 with the 2026-11-17 team
        {"workflow": "orochi", "params": {"max_runs": 20, "layer": 10},
         "cooldown_min": 0, "cooldown_on": {"体力": 120}},
        {"workflow": "exploration", "params": {"max_rounds": 5},
         "cooldown_min": 0, "cooldown_on": {"体力": 120}},
    ],
}


def _marathon(tmp_path, script, plan=None, **kw):
    clock = StepClock(step=1)
    sup = FakeSupervisor(script)
    from onmyoji_agentflow.store import Store
    app = SimpleNamespace(supervisor=sup, store=Store(tmp_path / "state.db"))
    m = Marathon(app, "mumu", plan or json.loads(json.dumps(GRIND_PLAN)), tmp_path / "m", clock=clock, sleep=clock.sleep, **kw)
    return m, sup


def test_marathon_runs_plan_with_home_between_and_totals(tmp_path):
    m, sup = _marathon(tmp_path, {
        "orochi": [("success", "挑战次数已打满", {"done": 20, "losses": 0})],
        "realm_raid": [("failed", "状态 x 连续出现 4 次", {"done": 3})],
    }, max_rounds=2)
    reason = m.run()
    assert "2 轮" in reason
    names = [c[0] for c in sup.calls]
    assert names[:8] == ["home", "daily_rewards", "home", "realm_raid", "home", "orochi", "home", "exploration"]
    # second round: daily_rewards (240 min) and the failed realm_raid (10 min) are still cooling down
    assert names[8:] == ["home", "orochi", "home", "exploration"]
    s = json.loads((tmp_path / "m" / "summary.json").read_text(encoding="utf-8"))
    assert s["workflows"]["orochi"]["counters"]["done"] == 40
    assert s["workflows"]["realm_raid"]["failed"] == 1
    assert s["finished"] and s["samples"] >= 2
    samples = sorted(p.name for p in (tmp_path / "m" / "samples").iterdir())
    assert any("failed-realm_raid" in n for n in samples) and any("unknown-orochi" in n for n in samples)
    lines = (tmp_path / "m" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(sup.calls)
    assert "orochi" in (tmp_path / "m" / "summary.md").read_text(encoding="utf-8")


def test_marathon_cooldown_on_stamina(tmp_path):
    plan = {"pause_s": 1, "home_between": False, "continuous": True,
            "items": [{"workflow": "orochi", "params": {}, "cooldown_min": 0, "cooldown_on": {"体力": 120}}]}
    m, sup = _marathon(tmp_path, {"orochi": [("success", "体力不足", {})]}, plan=plan,
                       deadline=None, max_rounds=None)
    m.deadline = m.clock() + 3 * 3600
    m.run()
    # 3 hours with a 2-hour cooldown after every 体力不足 -> 2 runs
    assert len(sup.calls) == 2 and "结束时间" in m.stop_reason


def test_marathon_stops_when_home_keeps_failing_and_on_stop_file(tmp_path):
    m, sup = _marathon(tmp_path, {"home": [("failed", "认不出", {})]})
    assert "回不到庭院" in m.run()
    assert [c[0] for c in sup.calls] == ["home"] * 3
    m2, sup2 = _marathon(tmp_path / "b", {})
    (m2.dir / "STOP").write_text("")
    assert "STOP" in m2.run() and not sup2.calls


def test_marathon_plan_and_deadline(tmp_path):
    p = tmp_path / "plan.yaml"
    p.write_text("pause_s: 5\nitems:\n  - workflow: orochi\n    params: {max_runs: 3}\n", encoding="utf-8")
    plan = load_plan(str(p))
    assert plan["pause_s"] == 5 and plan["items"] == [
        {"workflow": "orochi", "params": {"max_runs": 3}, "cooldown_min": 0, "cooldown_on": {}}]
    assert parse_deadline(2, None, now=1000.0) == 1000.0 + 7200
    d = parse_deadline(None, "00:00", now=1000.0)
    assert 1000.0 < d <= 1000.0 + 86400


# ------------------------------------------------------------------ realm raid: 3 weakest per page, win-rate floor
def _raid_states(params, init):
    wf = load_workflow(WF_DIR / "realm_raid.yaml")
    page = frame_for(wf, "page_quota_refresh", base=70)
    ctl, dev = ctl_for([page], advance_on_input=False)
    r = Runner(wf, ctl, params=params, clock=FakeClock(step=5), text_reader=fake_text_reader, initial_vars=init)
    seen = []
    r.on_event = lambda k, d: seen.append(d.get("state")) if k == "state" else None
    res = r.run()
    return res, seen, dev


def test_realm_raid_refreshes_after_three_wins_on_a_page():
    res, seen, dev = _raid_states({"max_runs": 9, "wins_per_page": 3, "max_refresh": 1}, {"done": 3, "losses": 0})
    assert seen[0] == "page_quota_refresh", seen
    assert res.variables["refreshes"] == 1 and res.variables["page_base"] == 3
    assert 990 <= taps(dev)[0][1] <= 1120
    # off by default (old params): the quota state never fires
    res, seen, dev = _raid_states({"max_runs": 9, "max_refresh": 1}, {"done": 3, "losses": 0})
    assert "page_quota_refresh" not in seen, seen


def test_realm_raid_quota_counts_wins_since_the_last_refresh():
    # 5 battles, 1 lost, 3 of the wins were on the previous page -> 1 win here: no quota refresh
    res, seen, dev = _raid_states({"max_runs": 9, "wins_per_page": 3, "max_refresh": 5},
                                  {"done": 5, "losses": 1, "page_base": 3})
    assert "page_quota_refresh" not in seen, seen
    # quota met but no refresh left -> stop with the reason
    res, seen, dev = _raid_states({"max_runs": 9, "wins_per_page": 3, "max_refresh": 0}, {"done": 3, "losses": 0})
    assert res.status == "success" and "够数" in res.reason, res.reason


def test_realm_raid_stops_below_win_rate_floor():
    res, seen, dev = _raid_states({"max_runs": 30, "min_win_pct": 50}, {"done": 4, "losses": 3})
    assert res.status == "success" and "胜率低" in res.reason and not taps(dev)
    # 2 of 4 won is exactly 50 %: no stop for the rate
    res, seen, dev = _raid_states({"max_runs": 30, "min_win_pct": 50}, {"done": 4, "losses": 2})
    assert "win_rate_stop" not in seen
    # fewer than min_rate_n battles: not judged yet
    res, seen, dev = _raid_states({"max_runs": 30, "min_win_pct": 50}, {"done": 3, "losses": 3})
    assert "win_rate_stop" not in seen


def test_marathon_default_plan_uses_tuned_raid_and_soul_ten():
    plan = load_plan(None)
    items = {it["workflow"]: it for it in plan["items"]}
    assert "event_boss" not in items
    rr = items["realm_raid"]
    assert rr["params"]["weak_first"] == 1 and rr["params"]["wins_per_page"] == 3 and rr["params"]["min_win_pct"] == 50
    assert "胜率低" in rr["cooldown_on"]
    assert items["orochi"]["params"]["layer"] == 10


def test_high_layer_result_panel_counts_once_and_taps_continue():
    # 御魂拾层 result panel (通关时间 + 裂变之眼 + 点击屏幕继续): no assttyys colour matches it
    for name in ("orochi", "home"):
        wf = load_workflow(WF_DIR / f"{name}.yaml")
        page = frame_for(wf, "settle_continue", base=73)
        ctl, dev = ctl_for([page], advance_on_input=False)
        r = Runner(wf, ctl, params={"max_runs": 5} if name == "orochi" else {}, clock=FakeClock(step=5),
                   text_reader=fake_text_reader, initial_vars={"pending": 1, "started": 1})
        seen = []
        r.on_event = lambda k, d: seen.append(d.get("state")) if k == "state" else None
        res = r.run()
        assert seen and seen[0] == "settle_continue", (name, seen)
        assert res.variables["done"] == 1, (name, res.variables)
        assert 540 <= taps(dev)[0][1] <= 740 and 600 <= taps(dev)[0][2] <= 690
