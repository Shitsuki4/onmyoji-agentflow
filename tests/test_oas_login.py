"""Fixed upstream harvest and deterministic ReplayDevice state transitions."""
import copy
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from helpers import FakeClock, blank, fake_text_reader, register_texts
from onmyoji_agentflow.convert.navigation_family import _bind_body
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_login import LOGIN, compile_android_login, compile_login_harvest
from onmyoji_agentflow.device.adb import AdbDevice, ONMYOJI_PACKAGE
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import DeviceError, WorkflowError
from onmyoji_agentflow.vision.ocr import FullOcrArea
from onmyoji_agentflow.workflow import engine
from onmyoji_agentflow.workflow.schema import load_workflow


@pytest.fixture(scope="module")
def fixed_assets(tmp_path_factory):
    default = Path.home() / "AppData/Local/onmyoji-agentflow/upstream-src/oas"
    upstream = Path(os.environ.get("OAF_OAS_SOURCE_ROOT", default))
    if not (upstream / LOGIN).is_file():
        pytest.skip("optional fixed OAS source checkout unavailable")
    resources = tmp_path_factory.mktemp("harvest") / "resources"
    folder = resources / "upstream/oas"
    for task in ("Restart", "GlobalGame", "GameUi", "Component_GeneralBuff", "Component_GeneralInvite"):
        convert_task(upstream / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return upstream, resources


@pytest.fixture(scope="module")
def harvest(fixed_assets):
    upstream, resources = fixed_assets
    folder = resources / "upstream/oas"
    return load_workflow(compile_login_harvest(upstream, folder), [resources])


@pytest.fixture(scope="module")
def login(fixed_assets):
    upstream, resources = fixed_assets
    return load_workflow(compile_android_login(upstream, resources / "upstream/oas"), [resources])


@pytest.fixture
def screen(login, monkeypatch):
    """Replay named template matches without overlap between unrelated OAS templates."""
    presets = {}
    names = {Path(spec["path"]).name: alias.rsplit("::", 1)[1]
             for alias, spec in login.resources.items() if "::" in alias and spec["type"] == "image"}

    def match(image, path, *_args, **_kwargs):
        name = names[Path(path).name]
        present = name in presets.get(int(image[0, 0, 0]), ())
        return present, 1.0 if present else 0.0, (200, 100, 40, 32)

    def frame(*contains):
        key = len(presets) + 30
        presets[key] = contains
        return blank(key)

    monkeypatch.setattr(engine, "match_template", match)
    return frame


def run(wf, frames, *, params=None, initial=None, use_inputs=False, clock=None, full_ocr_reader=None,
        confirm=None, should_stop=None, text_reader=None):
    device = ReplayDevice(frames, advance_on_input=use_inputs)
    runner = engine.Runner(wf, Controller(device, sleep=lambda _: None), params,
                           clock=clock or FakeClock(.05), initial_vars=initial, full_ocr_reader=full_ocr_reader,
                           confirm=confirm, should_stop=should_stop, text_reader=text_reader)
    return runner.run(), device.inputs


def visited(result):
    return [name.removeprefix("oas_harvest_").removeprefix("oas_login_") for _, name in result.history]


def test_mail_opens_marks_read_and_requires_bulk_claim_confirmation(harvest, screen):
    modal = register_texts(screen("I_UI_CONFIRM"), [("全部领取", 628, 84), ("确定", 763, 573)])
    frames = [screen("I_HARVEST_MAIL"), screen("I_READ_ALL_MAIL"), screen("I_HARVEST_MAIL_ALL"),
              modal, screen("I_LOGIN_RED_CLOSE"), screen()]
    result, inputs = run(harvest, frames, use_inputs=True, params={"enable_courtyard_affairs": False},
                         text_reader=fake_text_reader)
    assert result.status == "success" and result.business_result == "unknown"
    assert len(inputs) == 5
    assert [name for name in visited(result) if not name.endswith("_wait")] == [
        "visit_mail", "open_mail_icon", "mail_opened", "mail_mark", "mail_claim_all", "mail_confirm",
        "mail_close_input", "mail_closed", "idle_complete", "returned"]


def test_unrelated_confirmation_after_mark_read_stops_with_no_affirmative_input(harvest, screen):
    result, inputs = run(harvest, [screen("I_READ_ALL_MAIL"), screen("I_UI_CONFIRM")], use_inputs=True,
                         params={"enable_courtyard_affairs": False})
    assert result.status == "failed"
    assert visited(result)[-1] == "mail_confirmation_context"
    assert len(inputs) == 1


@pytest.mark.parametrize(("policy", "choice", "reward"), [
    ("reject", "reject", "I_G_JADE"),
    ("ignore", "ignore", "I_G_DOG_FOOD"),
    ("only_jade", "ignore", "I_G_DOG_FOOD"),
    ("jade_and_food", "ignore", None),
    ("jade_and_food", "accept", "I_G_CAT_FOOD"),
    ("only_jade", "accept", "I_G_JADE"),
    ("accept", "accept", None),
])
def test_harvest_invitation_dispositions_and_scheduling_follow_policy(harvest, screen, policy, choice, reward):
    markers = ["I_G_ACCEPT", "I_G_REJECT", "I_G_IGNORE"]
    if reward:
        markers.append(reward)
    result, inputs = run(harvest, [screen(*markers), screen()], use_inputs=True, params={
        "friend_invitation": policy, "enable_courtyard_affairs": False, "enable_mail": False})
    assert result.status == "success" and len(inputs) == 1
    assert f"harvest_invite_{choice}_input" in visited(result)
    assert list(result.oas_wakes) == (["WantedQuests"] if choice == "accept" else [])


def test_harvest_invitation_unchanged_or_unidentified_does_not_wake(harvest, screen):
    for policy, inputs_expected, markers in (
        ("accept", 1, ("I_G_ACCEPT", "I_G_REJECT")),
        ("accept", 0, ("I_G_ACCEPT",)),
        ("reject", 0, ("I_G_ACCEPT",)),
        ("ignore", 0, ("I_G_ACCEPT",)),
    ):
        result, inputs = run(harvest, [screen(*markers)], use_inputs=True, params={
            "friend_invitation": policy, "enable_courtyard_affairs": False, "enable_mail": False,
        })
        assert result.status == "failed" and len(inputs) == inputs_expected
        assert not result.oas_wakes


def test_scaled_match_and_recheck_on_real_mail_template(harvest):
    spec = harvest.resources["Restart::I_HARVEST_MAIL"]
    image = cv2.imdecode(np.fromfile(spec["path"], dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = image.shape[:2]
    target = cv2.resize(image, (int(width * .8), int(height * .8)))
    height, width = target.shape[:2]
    frame = blank()
    frame[490:490 + height, 260:260 + width] = target
    device = ReplayDevice([frame])
    runner = engine.Runner(harvest, Controller(device, sleep=lambda _: None),
                           {"enable_courtyard_affairs": False}, clock=FakeClock(.05),
                           max_actions=1)
    result = runner.run()
    assert result.status == "limit" and "open_mail_icon" in visited(result)
    [(_, x, y)] = device.inputs
    assert 260 <= x <= 260 + width and 490 <= y <= 490 + height


def test_courtyard_stops_after_three_completions_and_runs_only_once(harvest, screen):
    board = screen("I_PAGE", "I_COMPLETE_TASKS")
    frames = [screen("I_NOTE"), board, board, board, screen()]
    approvals = []
    result, inputs = run(harvest, frames, use_inputs=True, params={"enable_mail": False},
                         clock=FakeClock(.25), confirm=lambda category, _: approvals.append(category) or True)
    assert result.status == "success"
    names = visited(result)
    assert names.count("visit_courtyard") == 1
    assert names.count("courtyard_complete_tasks") == 3
    assert "courtyard_claim_cap" in names
    assert len(inputs) == 4
    assert approvals == ["购买", "分解"] * 3


def test_courtyard_bulk_completion_declined_before_any_input(harvest, screen):
    initial = {"oas_harvest_phase": "courtyard_claim"}
    result, inputs = run(harvest, [screen("I_PAGE", "I_COMPLETE_TASKS")], initial=initial,
                         confirm=lambda _category, _message: False)
    assert visited(result)[-1] == "courtyard_complete_tasks"
    assert not inputs and result.variables["oas_harvest_courtyard_claims"] == 0


def test_courtyard_bulk_completion_blocks_visible_soul_donation(harvest, screen):
    frame = register_texts(screen("I_PAGE", "I_DAILY", "I_COMPLETE_TASKS"),
                           [("任务类型:提交5星御魂2个", 720, 418)])
    initial = {"oas_harvest_phase": "courtyard_claim"}
    result, inputs = run(harvest, [frame], initial=initial, confirm=lambda *_: pytest.fail("must block first"))
    assert result.status == "failed" and visited(result)[-1] == "courtyard_soul_donation"
    assert not inputs


def test_noncanonical_resolution_cannot_authorize_input(harvest, screen):
    frame = cv2.resize(screen("I_READ_ALL_MAIL"), (640, 360))
    result, inputs = run(harvest, [frame], params={"enable_courtyard_affairs": False}, clock=FakeClock(1))
    assert result.failure_kind == "unknown_screen"
    assert not inputs


def test_harvest_stops_at_ambiguous_courtyard_accept(harvest, screen):
    result, inputs = run(harvest, [screen("I_PAGE", "I_CONFIRM", "I_COMPLETE_TASKS")])
    assert result.status == "failed"
    assert visited(result)[-1] == "courtyard_experience_context"
    assert not inputs


def test_login_requires_third_confirmed_courtyard_sample_and_defaults_to_harvest(login, screen):
    courtyard = screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")
    result, inputs = run(login, [courtyard],
                         params={"enable_mail": False, "enable_courtyard_affairs": False})
    assert result.status == "success" and not inputs
    names = visited(result)
    assert names.count("sample_courtyard") >= 2
    assert names.index("confirm_courtyard") < names.index("start_harvest") < names.index("idle_complete")
    recorded = dict((name, time) for time, name in result.history)
    assert recorded["oas_login_confirm_courtyard"] - recorded["oas_login_start_login"] > 1.5


def test_selected_character_is_literal_and_clicks_only_a_complete_box(login, screen):
    chooser = screen("I_LOGIN_SPECIFIC_SERVE")
    courtyard = screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")
    seen = []

    def read(_image, _region, keyword, _score):
        seen.append(keyword)
        return FullOcrArea((150, 160, 50, 25), keyword_complete=True)

    result, inputs = run(login, [chooser, chooser, courtyard], use_inputs=True,
                         params={"login_character": "角色[.*]", "enable_harvest": False}, full_ocr_reader=read)
    assert result.status == "success"
    assert seen == ["角色[.*]", "角色[.*]"]
    assert "confirm_same_server" in visited(result)
    (_, x, y), _ = inputs
    assert 150 <= x <= 200 and 160 <= y <= 185


def test_empty_character_and_create_account_are_blocked_without_input(login, screen):
    for image, state in (("I_LOGIN_SPECIFIC_SERVE", "missing_login_character"),
                         ("I_CREATE_ACCOUNT", "restart_disabled")):
        result, inputs = run(login, [screen(image)], params={"allow_login_restart": False})
        assert result.status == "failed" and not inputs
        assert visited(result)[-1] == state


def test_two_distinct_restarts_require_two_approvals_then_handoff(login, screen):
    approvals = []
    frame = screen("I_CREATE_ACCOUNT")
    result, inputs = run(login, [frame], confirm=lambda category, _: approvals.append(category) or True)
    assert result.status == "failed" and visited(result)[-1] == "retry_exhausted"
    assert inputs == [("restart_app", ONMYOJI_PACKAGE)] * 2
    assert approvals == ["重启游戏"] * 2
    assert result.actions == result.variables["oas_login_restart_count"] == 2
    assert result.variables["oas_login_login_attempt"] == 2


def test_restart_success_retries_login_and_can_finish_without_additional_input(login, screen):
    frames = [screen("I_CREATE_ACCOUNT"), screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")]
    result, inputs = run(login, frames, use_inputs=True, params={"enable_harvest": False}, confirm=lambda *_: True)
    assert result.status == "success"
    assert result.variables["oas_login_restart_pending"] == 0 and "retry_login" in visited(result)
    assert inputs == [("restart_app", ONMYOJI_PACKAGE)]


@pytest.mark.parametrize(("long_wait", "seconds", "captures", "expected"), [
    (False, 60, 61, False),
    (False, 61, 60, False),
    (False, 61, 61, True),
    (True, 300, 301, False),
    (True, 301, 300, False),
    (True, 301, 301, True),
])
def test_no_input_stall_requires_time_and_capture_count(login, screen, long_wait, seconds, captures, expected):
    frame = screen()
    runner = engine.Runner(login, Controller(ReplayDevice([frame])))
    runner.vars = {**login.raw["vars"], "oas_login_phase": "login", "oas_login_stall_long": long_wait,
                   "oas_login_stall_ms": 1000, "oas_login_stall_captures": 7,
                   "elapsed_ms": 1000 + seconds * 1000}
    runner._screen_captures = 7 + captures
    state = next(st for st in login.states if st["id"] == "oas_login_stalled_login_handoff")
    assert runner._match(state["when"], frame) is expected


@pytest.mark.parametrize("outcome", [
    "success", "not_foreground", "blank_frame", "denied", "focus_changed", "court_appeared", "exhausted",
])
def test_no_input_restart_requires_foreground_and_fresh_approval(login, screen, outcome):
    stalled = screen()
    if outcome != "blank_frame":
        stalled[24, 24] = (0, 255, 0)
    courtyard = screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")

    class TimedReplay(ReplayDevice):
        seconds = 0
        foreground = outcome != "not_foreground"

        def screenshot(self):
            self.seconds += 1
            return super().screenshot()

        def app_in_foreground(self, package):
            assert package == ONMYOJI_PACKAGE
            return self.foreground

    frames = [stalled] if outcome == "exhausted" else [stalled, courtyard]
    device = TimedReplay(frames, advance_on_input=True)
    approvals = []

    def confirm(category, _):
        approvals.append((category, device.seconds))
        if outcome == "focus_changed":
            device.foreground = False
        if outcome == "court_appeared":
            device.index = 1
        return outcome != "denied"

    result = engine.Runner(login, Controller(device, sleep=lambda _: None),
                           params={"enable_harvest": False}, clock=lambda: device.seconds,
                           confirm=confirm).run()
    if outcome == "success":
        assert result.status == "success", result.summary()
        assert {"restart_stalled_login", "retry_login", "confirm_courtyard"} <= set(visited(result))
        assert device.inputs == [("restart_app", ONMYOJI_PACKAGE)]
    elif outcome == "exhausted":
        assert result.status == "failed" and visited(result)[-1] == "retry_exhausted"
        assert device.inputs == [("restart_app", ONMYOJI_PACKAGE)] * 2
        assert approvals == [("重启游戏", 303), ("重启游戏", 607)]
        return
    else:
        assert not device.inputs
        assert result.failure_kind == {"not_foreground": "workflow_fail", "blank_frame": "workflow_fail",
                                       "denied": "confirm_denied", "focus_changed": "recognition",
                                       "court_appeared": "recognition"}[outcome]
        if outcome in ("not_foreground", "blank_frame"):
            assert visited(result)[-1] == "stalled_login_handoff"
    assert approvals == ([] if outcome in ("not_foreground", "blank_frame") else [("重启游戏", 303)])


def test_login_control_resets_short_window_and_excludes_recheck_from_capture_count(login, screen):
    stalled = screen()
    stalled[24, 24] = (0, 255, 0)

    class TapThenWait(ReplayDevice):
        seconds = 0

        def screenshot(self):
            self.seconds += 1
            return super().screenshot()

        def app_in_foreground(self, package):
            return package == ONMYOJI_PACKAGE

    frames = [screen("I_LOGIN_LOGIN_ONMYOJI_GENIE"), stalled, screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")]
    device = TapThenWait(frames, advance_on_input=True)
    approvals = []
    result = engine.Runner(login, Controller(device, sleep=lambda _: None), clock=lambda: device.seconds,
                           params={"enable_harvest": False},
                           confirm=lambda *_: approvals.append(device.seconds) or True).run()
    assert result.status == "success", result.summary()
    assert [entry[0] for entry in device.inputs] == ["tap", "restart_app"]
    assert approvals == [65]  # On the capture starting strictly more than 60 seconds after the tap.


@pytest.mark.parametrize(("targets", "taps_before_recovery"), [
    (["I_LOGIN_LOGIN_ONMYOJI_GENIE"] * 10, 9),
    (["I_LOGIN_LOAD_DOWN", "I_LOGIN_YELLOW_CLOSE"] * 6, 11),
])
def test_repeated_tap_that_would_cross_source_threshold_is_replaced_by_recovery(login, screen, targets, taps_before_recovery):
    frames = [screen(target) for target in targets]
    frames.append(screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS"))
    result, inputs = run(login, frames, use_inputs=True, params={"enable_harvest": False},
                         confirm=lambda *_: True, clock=FakeClock(.15))
    assert result.status == "success", result.reason
    assert [op[0] for op in inputs] == ["tap"] * taps_before_recovery + ["restart_app"]
    assert any(name.endswith("_recover_loop") for name in visited(result))


def test_restart_denial_cancel_and_stale_frame_are_nonmutating(login, screen):
    create = screen("I_CREATE_ACCOUNT")
    denied, inputs = run(login, [create], confirm=lambda *_: False)
    assert denied.failure_kind == "confirm_denied" and not inputs
    stopped = False

    def allow_then_stop(*_):
        nonlocal stopped
        stopped = True
        return True

    cancelled, inputs = run(login, [create], confirm=allow_then_stop, should_stop=lambda: stopped)
    assert cancelled.status == "stopped" and not inputs
    stale, inputs = run(login, [create, create, screen()], confirm=lambda *_: True)
    assert stale.failure_kind == "recognition" and not inputs


def test_restart_uncertainty_prevents_replay_of_the_operation(login, screen):
    create = screen("I_CREATE_ACCOUNT")

    class LostLaunch(ReplayDevice):
        def restart_app(self, package):
            super().restart_app(package)
            raise DeviceError("lifecycle connection lost")

    device = LostLaunch([create])
    result = engine.Runner(login, Controller(device, sleep=lambda _: None), clock=FakeClock(.05),
                           confirm=lambda *_: True).run()
    assert result.failure_kind == "restart_uncertain"
    assert result.actions == 1 and result.variables["oas_login_restart_pending"] == 1
    replay, inputs = run(login, [create], initial=result.variables, confirm=lambda *_: True)
    assert replay.failure_kind == "restart_uncertain" and not inputs


def test_restart_requires_and_targets_an_identical_foreground_package(monkeypatch):
    device = AdbDevice("serial", "adb", connect=False)
    channel = ONMYOJI_PACKAGE + ".channel"
    calls = []
    monkeypatch.setattr(device, "shell", lambda *_: f"package:{channel}\npackage:{ONMYOJI_PACKAGE}\n")
    monkeypatch.setattr(device, "_run", lambda args: calls.append(args) or "Events injected: 1")
    monkeypatch.setattr(device, "current_app", lambda: f"mCurrentFocus=Window{{abc {channel}/.Activity}}")
    assert device.app_in_foreground(ONMYOJI_PACKAGE)
    assert device.app_in_foreground(channel)
    assert not device.app_in_foreground(ONMYOJI_PACKAGE + ".unrelated")
    device.restart_app(ONMYOJI_PACKAGE)
    assert calls[0] == ["shell", "am", "force-stop", channel]
    assert calls[1][:4] == ["shell", "monkey", "-p", channel]
    calls.clear()
    monkeypatch.setattr(device, "current_app", lambda: "mCurrentFocus=Window{abc com.other.game/.Activity}")
    assert not device.app_in_foreground(ONMYOJI_PACKAGE)
    with pytest.raises(DeviceError, match="前台窗口"):
        device.restart_app(ONMYOJI_PACKAGE)
    assert not calls


def test_adb_reads_mumu_focus_from_the_full_window_dump(monkeypatch):
    device = AdbDevice("serial", "adb", connect=False)
    current = f"mCurrentFocus=Window{{abc {ONMYOJI_PACKAGE}/.Client}}"
    focused = "mFocusedApp=ActivityRecord{xyz com.other.game/.Activity}"

    def dump(*args):
        assert args == ("dumpsys", "window")
        return f"  {focused}\n  {current}\n"

    monkeypatch.setattr(device, "shell", dump)
    assert device.current_app() == current


@pytest.mark.parametrize("remove", ["sensitive", "recheck", "evidence", "marker"])
def test_unprotected_restart_is_rejected_by_schema(login, remove):
    raw = copy.deepcopy(login.raw)
    raw["resources"] = []
    raw["inline_resources"] = login.resources
    state = next(st for st in raw["states"] if st["id"] == "oas_login_restart_create_account")
    if remove == "sensitive":
        state.pop("sensitive")
    elif remove == "recheck":
        state["do"][0].pop("recheck")
    elif remove == "evidence":
        state["when"] = {"expr": "True"}
    else:
        state["do"][0].pop("attempt_var")
    with pytest.raises(WorkflowError, match="restart_app"):
        load_workflow(raw)


def test_login_returns_through_navigation_and_parent_reconfirms_destination(login, screen):
    body = copy.deepcopy(login.raw)
    raw = {
        "format": 1, "name": "login-parent", "resources": [], "vars": {"active": "", "done": 0},
        "inline_resources": login.resources,
        "navigation": {"format": 1, "call_active_var": "active", "links": [], "pages": {
            "login": {"when": {"colors": [[3, 3, "#ff0000"]]},
                      "hooks": {"enter_success": [{"invoke": "login"}]}},
            "main": {"when": {"colors": [[3, 3, "#ffffff"]]}},
        }},
        "states": [
            {"id": "parent_done", "when": {"expr": "done == 1"}, "do": [{"stop": "arrived"}]},
            {"id": "drive", "when": {"expr": "True"},
             "do": [{"navigate": {"destination": "main", "done_var": "done"}}]},
        ],
        "loop_delay_ms": 0,
    }
    returned = body["harvest_contract"]["result_var"]
    _bind_body(raw, body, "login", returned)
    raw["resources"] = []
    entry = screen()
    entry[3, 3] = (0, 0, 255)
    courtyard = screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")
    courtyard[3, 3] = (255, 255, 255)

    class NavigationReplay(ReplayDevice):
        def screenshot(self):
            if runner.vars.get("active") or runner.vars.get(returned):
                self.index = 1
            return super().screenshot()

    device = NavigationReplay([entry, courtyard], advance_on_input=True)
    runner = engine.Runner(load_workflow(raw), Controller(device, sleep=lambda _: None),
                           {"enable_harvest": False}, clock=FakeClock(.05), max_seconds=30)
    result = runner.run()
    assert result.status == "success", result.summary()
    assert result.variables[returned] and result.variables["active"] == "" and result.variables["done"] == 1
    assert result.history[-1][1] == "parent_done"
    assert not device.inputs
