import copy
import datetime as dt
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from helpers import FakeClock, blank
from onmyoji_agentflow.activity import ActivityWindow
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import BudgetExceeded, WorkflowError
from onmyoji_agentflow.foster import (
    FosterCandidate, FosterSelector, choose_foster, missing_cross_friend_rows, read_card,
    read_countdown, selected_friend,
)
from onmyoji_agentflow.ledger import GameLedger, ResourceBudget, period_keys
from onmyoji_agentflow.runtime import DeviceBusy, DeviceLease, FileMutex, normalize_device_identity
from onmyoji_agentflow.store import Store
from onmyoji_agentflow.supervisor.replay import run_cases
from onmyoji_agentflow.tasks import TaskScanner, parse_task_page
from onmyoji_agentflow.vision.ocr import OcrUnavailable
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import bundled_dir, load_workflow


def workflow(actions, condition=None):
    return load_workflow({"format": 1, "name": "bounded", "states": [
        {"id": "step", "when": condition or {"expr": "True"}, "do": actions}]})


def test_input_limit_does_not_charge_rejected_action(tmp_path):
    store = Store(tmp_path / "state.db")
    budget = ResourceBudget(store, limits={"stamina": {"daily_limit": 12}})
    target = workflow([{"click": [10, 10, 20, 20], "cost": {"stamina": 6}}] * 3)
    device = ReplayDevice([blank()])
    result = Runner(target, Controller(device, sleep=lambda seconds: None), max_actions=1,
                    before_input=lambda state, action, variables: budget.authorize(action["cost"])).run()
    assert result.actions == len(device.inputs) == 1
    totals = store.resource_totals("default", budget.period())["stamina"]
    assert totals["used"] == 6 and totals["reserved"] == 0


def test_cancellation_after_authorization_releases_budget(tmp_path):
    store = Store(tmp_path / "state.db")
    budget = ResourceBudget(store, limits={"stamina": {"daily_limit": 6}})
    stopped = threading.Event()

    def authorize(state, action, variables):
        finalize = budget.authorize({"stamina": 6})
        stopped.set()
        return finalize

    device = ReplayDevice([blank()])
    result = Runner(workflow([{"click": [10, 10, 20, 20]}]), Controller(device, sleep=lambda seconds: None),
                    before_input=authorize, should_stop=stopped.is_set).run()
    assert result.status == "stopped" and device.inputs == []
    totals = store.resource_totals("default", budget.period())["stamina"]
    assert totals["used"] == totals["reserved"] == 0


def test_wait_interrupts_before_next_input():
    stopped = threading.Event()
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        stopped.set()

    device = ReplayDevice([blank()])
    result = Runner(workflow([{"wait": 600000}, {"click": [10, 10, 20, 20]}]),
                    Controller(device, sleep=sleep), should_stop=stopped.is_set).run()
    assert result.status == "stopped" and not device.inputs and sum(sleeps) <= 0.25


def test_after_battle_never_clicks_prepare():
    target = workflow([{"click": [10, 10, 20, 20]}])
    target.raw["states"][0]["id"] = "prepare"
    device = ReplayDevice([blank()])
    result = Runner(target, Controller(device, sleep=lambda seconds: None), should_stop=lambda: "after_battle").run()
    assert result.status == "stopped" and not device.inputs


def test_missing_ocr_cannot_authorize_negative_condition():
    def missing(image, region):
        raise OcrUnavailable("missing")

    target = workflow([{"click": [10, 10, 20, 20]}], {"not": {"text": "购买"}})
    device = ReplayDevice([blank()])
    result = Runner(target, Controller(device, sleep=lambda seconds: None), text_reader=missing).run()
    assert result.failure_kind == "recognition" and not device.inputs


def test_replay_stops_at_unverified_priority_state(monkeypatch):
    def missing(image, region):
        raise OcrUnavailable("missing")

    monkeypatch.setattr("onmyoji_agentflow.vision.ocr.read_boxes", missing)
    target = load_workflow({"format": 1, "name": "priority", "states": [
        {"id": "ocr_first", "when": {"text": "购买"}},
        {"id": "fallback", "when": {"expr": "True"}}]})
    result = run_cases(target, [("frame", blank(), {"state": "fallback"})])[0]
    assert not result.ok and "OCR" in result.error


@pytest.mark.parametrize("alias", ["127.0.0.1:16384", "emulator-5554", "localhost:16384", {"name": "other", "mumu_id": 0}])
def test_same_physical_identity(alias):
    assert normalize_device_identity(alias) == "mumu:0"


def test_cross_process_mutex_and_recovery(tmp_path):
    path = tmp_path / "physical.lock"
    script = "from pathlib import Path; from onmyoji_agentflow.runtime import FileMutex; import sys; " \
             "lock=FileMutex(Path(sys.argv[1])); lock.__enter__(); print('locked',flush=True); sys.stdin.readline()"
    process = subprocess.Popen([sys.executable, "-c", script, str(path)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "locked"
        with pytest.raises(DeviceBusy):
            with FileMutex(path):
                pass
        process.terminate()
        process.wait(timeout=10)
        with FileMutex(path):
            pass
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def test_live_lease_not_stolen_for_stale_heartbeat():
    with DeviceLease("mumu:0") as lease:
        lease.update(heartbeat=0)
        status = DeviceLease("emulator-5554").snapshot()
        assert status["status"] == "running" and status["heartbeat_stale"]
        DeviceLease("localhost:16384").request_stop("after_battle")
        assert lease.stop_mode() == "after_battle"
    with DeviceLease("mumu:0") as replacement:
        assert replacement.stop_mode() is None


def test_open_failure_releases_thread_lock(tmp_path):
    path = tmp_path / "directory"
    path.mkdir()
    with pytest.raises(OSError):
        with FileMutex(path):
            pass
    outcome = []

    def probe():
        try:
            with FileMutex(path):
                pass
        except Exception as error:
            outcome.append(error)

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join(timeout=3)
    assert len(outcome) == 1 and not isinstance(outcome[0], DeviceBusy)


def test_atomic_resource_limit_across_connections(tmp_path):
    path = tmp_path / "shared.db"
    stores = [Store(path), Store(path)]
    gate = threading.Barrier(2)

    def spend(index):
        gate.wait()
        try:
            stores[index].spend_resources("account", "day", {"stamina": 6}, {"stamina": {"daily_limit": 6}})
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(spend, range(2)))
    assert sorted(results) == [False, True]
    totals = stores[0].resource_totals("account", "day")["stamina"]
    assert totals["used"] == 6 and totals["reserved"] == 0


def test_authorization_finalize_is_idempotent_and_reserve_requires_balance(tmp_path):
    store = Store(tmp_path / "state.db")
    limits = {"stamina": {"daily_limit": 12, "reserve": 20}}
    with pytest.raises(BudgetExceeded):
        store.authorize_resources("account", "day", {"stamina": 6}, limits)
    ticket = store.authorize_resources("account", "day", {"stamina": 6}, limits, balances={"stamina": 26})
    assert store.finalize_resources(ticket, True)
    assert not store.finalize_resources(ticket, True)
    assert store.resource_totals("account", "day")["stamina"]["used"] == 6


def test_task_scope_reset_and_old_evidence(tmp_path):
    assert period_keys(now=dt.datetime(2027, 1, 4, 3), reset_hour=5) == ("2027-01-03", "2026-W53")
    store = Store(tmp_path / "state.db")
    store.upsert_task("account", "day", "daily", "battle", 15, 15, True, "claimed", True,
                      {"screenshot": "new"}, observed_at=20)
    store.upsert_task("account", "day", "daily", "battle", 0, 15, False, "in_progress", True,
                      {"screenshot": "old"}, observed_at=10)
    store.upsert_task("account", "day", "daily", "battle", status="unknown", verified=False, observed_at=30)
    row = store.tasks("account", "day", "daily")[0]
    assert row["current"] == 15 and row["verified"] and row["updated"] == 20
    with pytest.raises(ValueError):
        period_keys(tz_name="Asia/Invalid")


def test_weekly_embedded_progress_overrides_reward_counter():
    rows = parse_task_page([("完成式神委派基础奖励0/6", 720, 250), ("已完成0/1次", 640, 290),
                            ("前往", 1030, 270)])
    assert rows[0]["key"] == "delegation" and rows[0]["target"] == 6
    assert not rows[0]["claimed"]


def test_scan_dedup_and_partial_coverage():
    scanner = TaskScanner("daily", 2)
    row = {"key": "battle", "current": 12, "target": 15, "claimed": False}
    for _ in range(2):
        action, record = scanner.step([row])
        assert "swipe" in action and not record
    scanner.step([row])
    scanner.step([row])
    assert scanner.complete and scanner.finished and len(scanner.rows) == 1
    scanner = TaskScanner("daily", 1)
    scanner.step([row])
    scanner.step([row])
    assert scanner.finished and not scanner.complete


def test_foster_ranking_star_before_type_and_duration():
    candidates = [FosterCandidate("taiko", 5, "太鼓", 36000), FosterCandidate("moon", 6, "太阴", 3600),
                  FosterCandidate("fish", 6, "斗鱼", 300), FosterCandidate("taiko6", 6, "太鼓", 100),
                  FosterCandidate("expired", 6, "太鼓", 0), FosterCandidate("unknown", None, "太鼓", 600)]
    assert choose_foster(candidates).friend == "taiko6"
    assert choose_foster(candidates[:2]).friend == "moon"
    assert read_countdown("剩余05：59：38") == 21578
    assert read_countdown("05:99:00") is None


def test_foster_checks_both_tabs_before_selection():
    selector = FosterSelector(4)
    rows = [("friend", 400, 220)]
    card = [("6星太阴 05:00:00", 880, 330)]
    terminal = None
    for _ in range(20):
        action = selector.step(rows, card)
        if "stop" in action:
            terminal = action["stop"]
            break
    assert {candidate.region for candidate in selector.candidates} == {"0", "1"}
    assert selector.best is not None and selector.phase == "previewed"
    assert terminal["result"] == "blocked"
    assert terminal["evidence"]["stars"] == 6


def test_foster_requires_highlight_for_the_clicked_friend():
    selector = FosterSelector(4, require_highlight=True)
    rows = [("最近寄养", 511, 192), ("friend", 359, 221), ("other", 369, 328)]
    card = [("6星太鼓", 880, 330)]
    wrong = blank()
    wrong[274:278, 320:600] = (255, 10, 140)
    wrong[375:379, 320:600] = (255, 10, 140)
    assert "click" in selector.step(rows, card, wrong, active_region=0)  # Reset at top.
    assert "click" in selector.step(rows, card, wrong, active_region=0)  # Select friend.
    for _ in range(3):
        assert "wait" in selector.step(rows, card, wrong, active_region=0)
    assert selector.step(rows, card, wrong, active_region=0)["stop"]["result"] == "blocked"
    assert selector.candidates == []


def test_ranked_foster_treats_ocr_punctuation_width_as_the_same_identity():
    selector = FosterSelector(4, require_highlight=True)
    image = blank()
    image[169:173, 320:600] = (255, 10, 140)
    image[270:274, 320:600] = (255, 10, 140)
    card = [("6星太鼓", 880, 330)]
    for name in ("同一位：(", "同一位：(", "同一位:("):
        step = selector.step([(name, 400, 221)], card, image, active_region=0)
    assert len(selector.seen) == len(selector.candidates) == 1
    assert "swipe" in step


def test_ranked_foster_stops_when_scroll_skips_an_entire_viewport():
    selector = FosterSelector(require_highlight=True)
    selector.phase = "scan"
    selector.previous_page = ("好友甲", "好友乙")
    step = selector.step([("好友丙", 400, 221)], [], active_region=0)
    assert step["stop"]["result"] == "blocked"
    assert "没有重叠" in step["stop"]["reason"]
    assert not selector.seen


@pytest.mark.parametrize("start", [504, 509])
def test_foster_clipped_bottom_row_demands_the_continuous_highlight_wall(start):
    image = blank()
    rows = [("上一行", 398, 456), ("最后一行", 388, 562)]
    image[start:start + 8, 320:600] = (255, 10, 140)
    assert selected_friend(image, rows) is None
    image[start:604, 209:215] = (255, 10, 140)
    assert selected_friend(image, rows) == "最后一行"
    assert selected_friend(image, [*rows, ("同一行内歧义", 440, 565)]) is None


def test_foster_cross_view_detects_an_unread_nickname_without_counting_server_text():
    image = blank(245)
    image[208:226, 345:385] = (50, 50, 60)
    image[240:259, 345:395] = (49, 68, 185)
    image[524:543, 350:385] = (50, 50, 60)
    assert missing_cross_friend_rows(image, [("第一行", 365, 217)]) == 1
    assert missing_cross_friend_rows(image, [("第一行", 365, 217), ("最后一行", 365, 534)]) == 0


def test_foster_verifies_the_active_tab_and_ranks_both_regions():
    selector = FosterSelector(4, require_highlight=True)
    rows = [("friend", 400, 221)]
    image = blank()
    image[169:173, 320:600] = (255, 10, 140)
    image[270:274, 320:600] = (255, 10, 140)
    region = 0
    terminal = None
    for _ in range(30):
        card = [("5星太鼓" if region == 0 else "6星斗鱼", 880, 330)]
        action = selector.step(rows, card, image, active_region=region)
        if action.get("click") == [370, 115, 405, 135]:
            region = 1
        if "stop" in action:
            terminal = action["stop"]
            break
    assert {candidate.region for candidate in selector.candidates} == {"0", "1"}
    assert terminal and terminal["evidence"] == {"stars": 6, "card_type": "斗鱼", "region": "1"}


def test_foster_card_reader_skips_occupied_and_rejects_ambiguous_stars(tmp_path):
    import cv2
    import numpy as np

    from onmyoji_agentflow.foster import _read_star_template

    assets = bundled_dir() / "resources" / "oas-foster"
    occupied = [("已占用", 993, 310), ("太鼓", 881, 371)]
    assert read_card(occupied)[1] == "occupied"
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    template = cv2.imread(str(assets / "utilize_u_big_6.png"))
    frame[320:347, 833:933] = template
    assert _read_star_template(frame, assets) == 6
    assert read_card([("太鼓", 880, 371)], frame, assets)[0].stars == 6
    assert read_card([("太鼓 5星", 880, 371)], frame, assets)[1] == "unknown"
    assert read_card([("太鼓", 880, 371)])[1] == "unknown"


def test_foster_slot_does_not_shadow_friend_list():
    workflow_path = bundled_dir() / "workflows" / "foster.yaml"
    target = load_workflow(workflow_path)
    frame = blank()
    boxes = [
        ("可寄养式神", 1100, 50),
        ("进入好友结界寄养式神", 900, 120),
        ("好友", 270, 120),
    ]

    def reader(_image, region):
        x, y, width, height = region
        return [(text, cx, cy) for text, cx, cy in boxes
                if x <= cx < x + width and y <= cy < y + height]

    runner = Runner(target, Controller(ReplayDevice([frame]), sleep=lambda seconds: None), text_reader=reader)
    matches = {item["id"]: item["match"] for item in runner.diagnose_frame(frame)}

    assert not matches["foster_slot"]
    assert matches["friend_list"]


def test_all_bundled_workflows_reload_without_duplicate_states():
    for path in (bundled_dir() / "workflows").glob("*.yaml"):
        target = load_workflow(path)
        reloaded = load_workflow(target.raw)
        assert target.raw == reloaded.raw
        assert len(target.states) == len({state["id"] for state in target.states})


def test_activity_guards_separate_battle_and_shop_windows():
    window = ActivityWindow("event", "2026-11-11T00:00", "2026-11-17T23:59:59", "2026-11-24T23:59:59")
    assert not window.battle_open(dt.datetime(2026, 11, 20))
    assert window.shop_open(dt.datetime(2026, 11, 20))
    assert not window.shop_open(dt.datetime(2026, 11, 1))
    with pytest.raises(WorkflowError):
        ActivityWindow("bad", "2026-11-11", "2026-11-01")
