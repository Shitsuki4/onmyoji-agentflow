"""No emulator inputs: calendar, dependency and side-effect recovery contracts."""
import copy
import datetime as dt
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from onmyoji_agentflow.app import App
from onmyoji_agentflow.ledger import _zone
from onmyoji_agentflow.marathon import Marathon, load_plan
from onmyoji_agentflow.orchestration import Checkpoints, schedule_gate
from onmyoji_agentflow.store import Store
from onmyoji_agentflow.workflow.engine import RunResult


def stamp(value):
    return dt.datetime.fromisoformat(value).replace(tzinfo=_zone("Asia/Shanghai")).timestamp()


def test_overnight_window_belongs_to_start_day_and_end_is_exclusive():
    schedule = {"weekdays": [1], "windows": [["23:00", "01:00"]]}
    assert schedule_gate(schedule, stamp("2026-11-23T23:30"))[0]
    assert schedule_gate(schedule, stamp("2026-11-24T00:30"))[0]
    opened, next_at = schedule_gate(schedule, stamp("2026-11-24T01:00"))
    assert not opened and next_at == stamp("2026-11-30T23:00")
    assert not schedule_gate(schedule, stamp("2026-11-24T23:30"))[0]


def test_date_bounds_future_start_and_expired_overnight():
    schedule = {"starts_on": "2027-01-04", "ends_on": "2027-01-04", "windows": [["23:00", "01:00"]]}
    assert schedule_gate(schedule, stamp("2026-11-21T09:00")) == (False, stamp("2027-01-04T23:00"))
    assert schedule_gate(schedule, stamp("2027-01-05T00:30"))[0]
    assert schedule_gate(schedule, stamp("2027-01-05T01:00")) == (False, None)


def test_yaml_dates_are_persisted_as_iso_strings(tmp_path):
    path = tmp_path / "dated.yaml"
    path.write_text("items:\n  - workflow: home\n    schedule:\n      starts_on: 2026-11-21\n      ends_on: 2026-11-22\n", encoding="utf-8")
    plan = load_plan(str(path))
    assert plan["items"][0]["schedule"]["starts_on"] == "2026-11-21"


@pytest.mark.parametrize("extra", [
    {"schedule": {"weekdays": [True]}}, {"schedule": {"windows": [["25:00", "01:00"]]}},
    {"schedule": {"ends_on": "2020-01-01", "starts_on": "2021-01-01"}},
    {"limit_per_period": True}, {"cooldown_min": float("nan")}, {"on_failure": "ignore"},
    {"scope": "monthly"}, {"after": "first"}, {"after": ["missing"]},
])
def test_invalid_plan_fails_before_any_execution(extra):
    with pytest.raises((ValueError, TypeError)):
        load_plan({"items": [{"workflow": "home", **extra}]})


def test_dependencies_are_ordered_without_mutating_input_and_cycles_rejected():
    raw = {"items": [{"id": "last", "workflow": "home", "after": ["first"]},
                      {"id": "first", "workflow": "home"}]}
    original = copy.deepcopy(raw)
    assert [it["id"] for it in load_plan(raw)["items"]] == ["first", "last"]
    assert raw == original
    raw["items"][1]["after"] = ["last"]
    with pytest.raises(ValueError, match="循环"):
        load_plan(raw)
    with pytest.raises(ValueError, match="唯一"):
        load_plan({"items": [{"id": "same", "workflow": "home"}] * 2})
    with pytest.raises(ValueError):
        load_plan({"items": []})


class Clock:
    def __init__(self):
        self.t = stamp("2026-11-21T00:00")

    def __call__(self):
        return self.t


def app_fixture(tmp_path, monkeypatch, *, verified=True, result="completed"):
    app = App(tmp_path / "home", device_factory=lambda _: pytest.fail("offline test opened a device"))
    calls = []

    def run(name, instance, params, **kwargs):
        calls.append(name)
        res = RunResult(name, "success", actions=1, business_result=result,
                        evidence={"verified": verified, "run_id": len(calls), "screenshot": "synthetic"})
        return SimpleNamespace(result=res, notes=[], level="none")

    monkeypatch.setattr(app.supervisor, "run", run)
    monkeypatch.setattr(app.supervisor, "execution", lambda *args: nullcontext())
    monkeypatch.setattr(app.supervisor, "stop", lambda *args: None)
    return app, calls


def run_plan(app, clock, folder, items, **extra):
    plan = load_plan({"home_between": False, "task_aware": False, "continuous": False, "items": items, **extra})
    runner = Marathon(app, "main", plan, folder, clock=clock, max_rounds=1)
    runner.run()
    return runner


def test_completed_step_survives_new_runner_and_another_plan(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch)
    clock = Clock()
    item = {"id": "one", "workflow": "home", "task_key": "once", "once_per_period": True}
    first = run_plan(app, clock, tmp_path / "one", [item])
    second = run_plan(app, clock, tmp_path / "two", [item], pause_s=99)
    assert calls == ["home"] and first._checkpoint(item)["completed"] == 1
    assert second._done_for_period(item)
    clock.t += 86400
    run_plan(app, clock, tmp_path / "tomorrow", [item])
    assert calls == ["home", "home"]


def test_uncertain_side_effect_pauses_and_resume_does_not_replay_it(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch, verified=False, result="unknown")
    clock = Clock()
    item = {"id": "one", "workflow": "home", "once_per_period": True}
    first = run_plan(app, clock, tmp_path / "one", [item, {"id": "two", "workflow": "daily_rewards"}])
    assert first._checkpoint(item)["status"] == "needs_review" and "检查点" in first.stop_reason
    run_plan(app, clock, tmp_path / "two", [item])
    assert calls == ["home"]


def test_interrupted_running_step_not_stolen_by_new_process(tmp_path):
    store = Store(tmp_path / "state.db")
    checkpoints = Checkpoints(store, "account", "plan")
    assert checkpoints.begin("purchase", "week", 1)
    restarted = Checkpoints(Store(tmp_path / "state.db"), "account", "plan")
    assert not restarted.begin("purchase", "week", 10000)


def test_four_fosters_are_spaced_persistent_and_stop_at_quota(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch)
    clock = Clock()
    item = {"id": "foster", "workflow": "foster", "task_key": "foster_started",
            "limit_per_period": 4, "min_interval_min": 360}
    first = run_plan(app, clock, tmp_path / "first", [item])
    run_plan(app, clock, tmp_path / "too-soon", [item], pause_s=5)
    assert calls == ["foster"]
    for number in range(3):
        clock.t += 6 * 3600
        run_plan(app, clock, tmp_path / f"later-{number}", [item])
    run_plan(app, clock, tmp_path / "fifth", [item])
    assert calls == ["foster"] * 4 and first._checkpoint(item)["completed"] == 4


def test_preexisting_foster_timer_is_not_another_foster_start(tmp_path, monkeypatch):
    app, _ = app_fixture(tmp_path, monkeypatch, result="already_done")
    item = {"workflow": "foster", "task_key": "foster_started", "limit_per_period": 4}
    runner = run_plan(app, Clock(), tmp_path / "run", [item])
    assert runner._checkpoint(item)["completed"] == 0
    assert runner._quota_count(item) == 0


def test_failed_dependency_and_closed_window_never_navigate(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch, verified=False, result="unknown")
    items = [{"id": "first", "workflow": "home", "once_per_period": True, "on_failure": "continue"},
             {"id": "child", "workflow": "daily_rewards", "after": ["first"]},
             {"id": "later", "workflow": "daily_quests", "schedule": {"windows": [["12:00", "13:00"]]}}]
    run_plan(app, Clock(), tmp_path / "run", items, home_between=True)
    # Only the first task and its navigation ran. Child/window gates ran before navigation.
    assert calls == ["home", "home"]


def test_goal_batches_do_not_turn_one_batch_into_daily_completion(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch)
    clock = Clock()
    item = {"workflow": "orochi", "goal": "battle_15", "once_per_period": True}
    runner = Marathon(app, "main", load_plan({"task_aware": False, "home_between": False, "items": [item]}),
                      tmp_path / "run", clock=clock)
    remaining = iter([6, 3, 3, 0])
    monkeypatch.setattr(runner, "item_params", lambda _: ({"max_runs": 3}, "ready"))
    monkeypatch.setattr(runner, "_goal_remaining", lambda _: next(remaining))
    monkeypatch.setattr(runner, "_scan", lambda: True)
    runner._run_item(0, item)
    assert calls == ["orochi", "orochi"] and runner._checkpoint(item)["status"] == "completed"


def test_builtin_presets_and_preview_are_read_only(tmp_path):
    assert len(load_plan("all")["items"]) == len(load_plan("daily")["items"]) + len(load_plan("weekly")["items"])
    app = App(tmp_path / "home", device_factory=lambda _: pytest.fail("preview opened device"))
    before = app.ws.head()
    preview = app.plans.preview(path="weekly")
    assert all(row["status"] == "blocked" for row in preview["items"])
    assert app.ws.head() == before and not (app.cfg.home / "marathon" / "preview").exists()


def test_plan_pulls_upstream_before_device_lease_and_holds_pending_updates(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch)
    operations = []

    def sync(**kwargs):
        operations.append("sync")
        return SimpleNamespace(status="waiting_user", details={})

    app.sync = SimpleNamespace(sync=sync, due=lambda: False)
    monkeypatch.setattr(app.supervisor, "execution", lambda *args: operations.append("device") or nullcontext())
    runner = run_plan(app, Clock(), tmp_path / "run", [{"workflow": "home"}], sync_before_start=True)
    assert operations == ["sync"] and not calls and "上游同步" in runner.stop_reason
    assert app.store.marathon_jobs()[0]["status"] == "stopped"


def test_unchanged_sync_still_holds_an_older_pending_resource_update(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch)
    app.sync = SimpleNamespace(sync=lambda **kwargs: SimpleNamespace(status="unchanged", details={}), due=lambda: False)
    app.store.execute("INSERT INTO changes(workflow,status) VALUES ('upstream-sync','waiting_user')")
    run_plan(app, Clock(), tmp_path / "run", [{"workflow": "home"}], sync_before_start=True)
    assert not calls


def test_goal_proven_complete_by_scan_unblocks_dependency_without_replaying_battles(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch)
    clock = Clock()
    app.ledger.record_task("daily", "battle_15", 15, 15, verified=True, evidence={"screenshot": "synthetic"},
                           now=dt.datetime.fromtimestamp(clock.t, dt.timezone.utc))
    run_plan(app, clock, tmp_path / "run", [
        {"id": "battles", "workflow": "orochi", "goal": "battle_15", "once_per_period": True},
        {"id": "reward", "workflow": "daily_quests", "after": ["battles"]}])
    assert calls == ["daily_quests"]


def test_expired_plan_deadline_never_starts_initial_task_scan(tmp_path, monkeypatch):
    app, calls = app_fixture(tmp_path, monkeypatch)
    clock = Clock()
    runner = Marathon(app, "main", load_plan({"items": [{"workflow": "home"}]}),
                      tmp_path / "expired", clock=clock, deadline=clock.t - 1)
    runner.run()
    assert not calls and "结束时间" in runner.stop_reason
