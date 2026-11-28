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


def run_invitation(wf, frames, *, params=None, initial=None, on_state=None, should_stop=None):
    """Native Runner with time advanced by waits, not by the number of clock reads."""
    class Clock:
        ms = 0

        def __call__(self):
            return self.ms / 1000

        def sleep(self, seconds):
            self.ms += round(seconds * 1000)

    clock = Clock()

    class TimedReplay(ReplayDevice):
        def __init__(self):
            super().__init__(frames, advance_on_input=True)
            self.input_times = []

        def tap(self, x, y, press_ms=40):
            self.input_times.append(clock.ms)
            super().tap(x, y, press_ms)

    device = TimedReplay()
    snapshots = []

    def record(kind, data):
        if kind == "state":
            snapshots.append((data["state"], dict(data["vars"]), dict(runner._oas_wakes)))
            if on_state:
                on_state(runner, device, clock, data)

    runner = engine.Runner(wf, Controller(device, sleep=clock.sleep), params, clock=clock,
                           initial_vars=initial, on_event=record, should_stop=should_stop)
    return runner.run(), device, snapshots


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
    for policy, guarded, markers in (
        ("accept", True, ("I_G_ACCEPT", "I_G_REJECT")),
        ("accept", False, ("I_G_ACCEPT",)),
        ("reject", False, ("I_G_ACCEPT",)),
        ("ignore", False, ("I_G_ACCEPT",)),
    ):
        result, inputs = run(harvest, [screen(*markers)], use_inputs=True, params={
            "friend_invitation": policy, "enable_courtyard_affairs": False, "enable_mail": False,
        })
        assert result.status == "failed"
        if guarded:
            # Source retries an ineffective click; native retries remain bounded.
            assert 1 < len(inputs) <= 10
            assert visited(result)[-1] == "harvest_invite_accept_verify_timeout"
        else:
            assert not inputs
            assert visited(result)[-1] == "harvest_invitation_review"
        assert not result.oas_wakes


@pytest.mark.parametrize("parent", ["login", "harvest", "same_server"])
@pytest.mark.parametrize("choice", ["reject", "ignore"])
def test_invitation_selected_button_disappearance_restores_parent_and_stall(login, screen, parent, choice):
    initial = {"oas_login_phase": parent, "oas_login_since": 6543,
               "oas_login_stall_long": True, "oas_login_stall_ms": -500,
               "oas_login_stall_captures": -3, "oas_login_court_samples": 2}
    result, device, snapshots = run_invitation(
        login, [screen("I_G_ACCEPT", "I_G_REJECT", "I_G_IGNORE"), screen("I_G_ACCEPT")],
        initial=initial, params={"friend_invitation": choice, "enable_harvest": False})
    names = visited(result)
    assert names.count(f"{parent}_invite_{choice}_input") == 1
    assert f"{parent}_invite_{choice}_gone" in names
    # The remaining accept-only marker still blocks in the restored parent;
    # it must not strand us in reject/ignore or authorize a different input.
    assert result.status == "failed" and names[-1] == parent + "_invitation_review"
    assert len(device.inputs) == 1 and not result.oas_wakes
    assert result.variables["oas_login_phase"] == parent
    assert result.variables["oas_login_since"] == 6543
    assert result.variables["oas_login_court_samples"] == 2
    assert result.variables["oas_login_stall_long"] is True
    gone = next(variables for name, variables, _ in snapshots if name.endswith(f"_invite_{choice}_gone"))
    assert gone["oas_login_stall_long"] is False  # Successful input reset the short window.
    for key in ("oas_login_stall_ms", "oas_login_stall_captures"):
        assert result.variables[key] == gone[key]  # Completion must not reset that window again.


@pytest.mark.parametrize(("choice", "button"), [("reject", "I_G_REJECT"), ("ignore", "I_G_IGNORE")])
def test_invitation_accept_marker_loss_alone_does_not_complete_selected_disposition(harvest, screen, choice, button):
    def clear_after_wait(_runner, device, _clock, data):
        if data["state"].endswith(f"_invite_{choice}_wait"):
            device.index = 2

    result, device, _ = run_invitation(
        harvest, [screen("I_G_ACCEPT", button), screen(button), screen()],
        params={"friend_invitation": choice, "enable_mail": False, "enable_courtyard_affairs": False},
        on_state=clear_after_wait)
    assert result.status == "success"
    names = visited(result)
    assert names.index(f"harvest_invite_{choice}_wait") < names.index(f"harvest_invite_{choice}_gone")
    assert len(device.inputs) == 1 and not result.oas_wakes


@pytest.mark.parametrize("workflow", ["harvest", "login"])
def test_invitation_accept_retries_after_cooldown_and_wakes_only_after_ack(request, screen, workflow):
    wf = request.getfixturevalue(workflow)
    parent = "harvest" if workflow == "harvest" else "login"
    prefix = "oas_" + workflow + "_"
    panel = screen("I_G_ACCEPT", "I_G_REJECT")
    done = screen() if workflow == "harvest" else screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")
    params = {"enable_mail": False, "enable_courtyard_affairs": False}
    if workflow == "login":
        params["enable_harvest"] = False
    result, device, snapshots = run_invitation(wf, [panel, panel, done], params=params)
    names = visited(result)
    assert result.status == "success", result.summary()
    assert len(device.inputs) == 2 and device.input_times[1] - device.input_times[0] >= 800
    assert names.count(parent + "_invite_accept_input") == 1
    assert names.count(parent + "_invite_accept_retry") == 1
    assert names.count(parent + "_invite_accept_acknowledged") == 1
    assert list(result.oas_wakes) == ["WantedQuests"]
    ack = next(i for i, (name, _, _) in enumerate(snapshots) if name.endswith("_invite_accept_acknowledged"))
    assert all(not wakes for _, _, wakes in snapshots[:ack + 1])
    assert snapshots[ack + 1][2].keys() == {"WantedQuests"}
    if workflow == "login":
        assert snapshots[ack][1][prefix + "stall_long"] is False
        assert snapshots[ack + 1][1][prefix + "stall_long"] is True
    started = next(variables[prefix + "invite_started"] for name, variables, _ in snapshots
                   if name.endswith("_invite_accept_input"))
    assert result.variables[prefix + "invite_started"] == started  # Retry did not renew the budget.
    assert all(stamp - started < 8000 for stamp in device.input_times)
    ack_state = next(state for state in wf.states if state["id"].endswith(parent + "_invite_accept_acknowledged"))
    assert sum("oas_wake" in action for action in ack_state["do"]) == 1


@pytest.mark.parametrize("workflow", ["harvest", "login"])
def test_persistent_guarded_invitation_retries_only_within_original_deadline(request, screen, workflow):
    wf = request.getfixturevalue(workflow)
    params = {"enable_mail": False, "enable_courtyard_affairs": False}
    if workflow == "login":
        params["enable_harvest"] = False
    result, device, snapshots = run_invitation(wf, [screen("I_G_ACCEPT", "I_G_REJECT")], params=params)
    assert result.status == "failed"
    parent = "harvest" if workflow == "harvest" else "login"
    assert visited(result)[-1] == parent + "_invite_accept_verify_timeout"
    started = result.variables["oas_" + workflow + "_invite_started"]
    assert 1 < len(device.inputs) <= 10
    assert all(0 <= stamp - started < 8000 for stamp in device.input_times)
    assert all(later - earlier >= 800 for earlier, later in zip(device.input_times, device.input_times[1:]))
    assert result.variables["elapsed_ms"] - started >= 8000
    assert not result.oas_wakes and all(not wakes for _, _, wakes in snapshots)
    assert not any("recover_loop" in name for name in visited(result))


@pytest.mark.parametrize("pending", ["harvest_invite_accept", "harvest_invite_accept_verify"])
def test_invitation_deadline_precedes_initial_or_retry_input_at_exact_boundary(harvest, screen, pending):
    result, device, _ = run_invitation(harvest, [screen("I_G_ACCEPT", "I_G_REJECT")], initial={
        "oas_harvest_phase": pending, "oas_harvest_invite_started": -8000})
    assert result.status == "failed" and visited(result) == [pending + "_timeout"]
    assert not device.inputs and not result.oas_wakes


@pytest.mark.parametrize("dispatch", ["input", "retry"])
def test_invitation_deadline_is_rechecked_when_input_state_was_selected_earlier(harvest, screen, dispatch):
    def expire(runner, _device, clock, data):
        if data["state"] == "oas_harvest_harvest_invite_accept_" + dispatch:
            clock.ms = runner.vars["oas_harvest_invite_started"] + 8000

    panel = screen("I_G_ACCEPT", "I_G_REJECT")
    result, device, _ = run_invitation(harvest, [panel], on_state=expire)
    assert result.failure_kind == "recognition"
    assert visited(result)[-1] == "harvest_invite_accept_" + dispatch
    assert len(device.inputs) == (0 if dispatch == "input" else 1)
    assert not result.oas_wakes


def test_invitation_disappearing_before_first_input_expires_without_waking(harvest, screen):
    def disappear(_runner, device, _clock, data):
        if data["state"].endswith("_invite_accept_enter"):
            device.index = 1

    result, device, snapshots = run_invitation(
        harvest, [screen("I_G_ACCEPT", "I_G_REJECT"), screen()], on_state=disappear,
        params={"enable_mail": False, "enable_courtyard_affairs": False})
    assert result.status == "success"
    assert "harvest_invite_accept_expired" in visited(result)
    assert not any(name.endswith("_acknowledged") for name in visited(result))
    assert not device.inputs and not result.oas_wakes
    assert all(not wakes for _, _, wakes in snapshots)


@pytest.mark.parametrize(("policy", "remaining"), [
    ("accept", ("I_G_ACCEPT",)),
    ("only_jade", ("I_G_ACCEPT", "I_G_REJECT")),
])
def test_invitation_retry_withholds_input_when_companion_or_reward_is_lost(harvest, screen, policy, remaining):
    panel = screen("I_G_ACCEPT", "I_G_REJECT", "I_G_JADE")
    result, device, _ = run_invitation(harvest, [panel, screen(*remaining)],
                                        params={"friend_invitation": policy})
    assert result.status == "failed" and visited(result)[-1] == "harvest_invite_accept_verify_timeout"
    assert len(device.inputs) == 1 and "harvest_invite_accept_retry" not in visited(result)
    assert not result.oas_wakes


@pytest.mark.parametrize("changed", [(), ("I_G_ACCEPT", "I_G_JADE"), ("I_G_ACCEPT", "I_G_REJECT")])
def test_invitation_retry_rechecks_stale_accept_companion_and_reward(harvest, screen, changed):
    panel = screen("I_G_ACCEPT", "I_G_REJECT", "I_G_JADE")

    def change(_runner, device, _clock, data):
        if data["state"].endswith("_invite_accept_retry"):
            device.index = 2  # Change after selection but before Runner's fresh input recheck.

    result, device, _ = run_invitation(harvest, [panel, panel, screen(*changed)],
                                        params={"friend_invitation": "only_jade"}, on_state=change)
    assert result.failure_kind == "recognition"
    assert visited(result)[-1] == "harvest_invite_accept_retry"
    assert len(device.inputs) == 1 and not result.oas_wakes


def test_invitation_retry_cancellation_does_not_dispatch_or_wake(harvest, screen):
    stopped = False

    def stop(_runner, _device, _clock, data):
        nonlocal stopped
        if data["state"].endswith("_invite_accept_retry"):
            stopped = True

    panel = screen("I_G_ACCEPT", "I_G_REJECT")
    result, device, _ = run_invitation(harvest, [panel], on_state=stop, should_stop=lambda: stopped)
    assert result.status == "stopped" and len(device.inputs) == 1
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


@pytest.mark.parametrize("choice", ["accept", "reject", "ignore"])
def test_same_server_invitation_interrupt_resumes_character_confirmation(login, screen, choice):
    chooser = screen("I_LOGIN_SPECIFIC_SERVE")
    panel = screen("I_LOGIN_SPECIFIC_SERVE", "I_G_ACCEPT", "I_G_REJECT", "I_G_IGNORE")
    courtyard = screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")
    seen = []

    def read(_image, _region, keyword, _score):
        seen.append(keyword)
        return FullOcrArea((150, 160, 50, 25), keyword_complete=True)

    result, inputs = run(login, [chooser, panel, chooser, courtyard], use_inputs=True,
                         params={"login_character": "角色[.*]", "enable_harvest": False,
                                 "friend_invitation": choice}, full_ocr_reader=read)
    assert result.status == "success", result.summary()
    assert len(inputs) == 3 and seen == ["角色[.*]", "角色[.*]"]
    names = visited(result)
    completed = "same_server_invite_" + choice + ("_acknowledged" if choice == "accept" else "_gone")
    ordered = ["select_character", f"same_server_invite_{choice}_enter",
               f"same_server_invite_{choice}_input", completed, "confirm_same_server",
               "same_server_cleared", "confirm_courtyard", "skip_harvest"]
    assert [names.index(name) for name in ordered] == sorted(names.index(name) for name in ordered)
    assert names.count("confirm_same_server") == 1 and "start_harvest" not in names
    assert list(result.oas_wakes) == (["WantedQuests"] if choice == "accept" else [])
    if choice == "accept":
        assert names.count("same_server_invite_accept_acknowledged") == 1
    assert result.variables["oas_login_stall_long"] is False


def test_same_server_accept_only_evidence_blocks_before_chooser_input(login, screen):
    chooser = screen("I_LOGIN_SPECIFIC_SERVE")
    panel = screen("I_LOGIN_SPECIFIC_SERVE", "I_G_ACCEPT")
    result, inputs = run(login, [chooser, panel], use_inputs=True,
                         params={"login_character": "角色", "enable_harvest": False},
                         full_ocr_reader=lambda *_: FullOcrArea((150, 160, 50, 25), keyword_complete=True))
    assert result.status == "failed" and visited(result)[-1] == "same_server_invitation_review"
    assert len(inputs) == 1 and "confirm_same_server" not in visited(result)
    assert not result.oas_wakes


def test_bind_phone_prompt_opens_cancels_and_returns_without_consuming_shared_cooldown(login, screen):
    opener = screen("I_LOGIN_LOGIN_GOTO_BIND_PHONE")
    prompt = screen("I_UI_CANCEL_SAMLL")
    courtyard = screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")
    shared_cancel = "oas_login_interval_GlobalGame_i_ui_cancel_samll"
    # The interval-free source cancellation bypasses, and must not reset, the
    # existing cooldown used by other login callers of this same control.
    result, device, snapshots = run_invitation(
        login, [opener, prompt, courtyard], params={"enable_harvest": False},
        initial={shared_cancel: 1_000_000})
    assert result.status == "success", result.summary()
    assert [entry[0] for entry in device.inputs] == ["tap", "tap"]
    names = visited(result)
    ordered = ["open_bind_phone_prompt", "cancel_bind_phone_prompt", "confirm_courtyard", "skip_harvest"]
    assert [names.index(name) for name in ordered] == sorted(names.index(name) for name in ordered)
    assert names.count("open_bind_phone_prompt") == names.count("cancel_bind_phone_prompt") == 1
    before_cancel = next(values for state, values, _ in snapshots
                         if state == "oas_login_cancel_bind_phone_prompt")
    resumed_login = next(values for state, values, _ in snapshots
                         if state == "oas_login_confirm_courtyard")
    assert before_cancel["oas_login_phase"] == "bind_phone"
    assert resumed_login["oas_login_phase"] == "login"
    assert before_cancel[shared_cancel] == result.variables[shared_cancel] == 1_000_000
    assert not result.oas_wakes
    assert any(obligation["id"] == "oas_login_bind_phone"
               for obligation in login.raw["harvest_contract"]["source_obligations"])


@pytest.mark.parametrize(("selected", "expected_inputs", "phase"), [
    ("open_bind_phone_prompt", 0, "login"),
    ("cancel_bind_phone_prompt", 1, "bind_phone"),
])
def test_bind_phone_prompt_fresh_recheck_rejects_disappearing_controls(
        login, screen, selected, expected_inputs, phase):
    frames = [screen("I_LOGIN_LOGIN_GOTO_BIND_PHONE"), screen("I_UI_CANCEL_SAMLL"),
              screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")]

    def disappear(_runner, device, _clock, data):
        if data["state"] == "oas_login_" + selected:
            device.index = 2

    result, device, _ = run_invitation(login, frames, params={"enable_harvest": False}, on_state=disappear)
    assert result.status == "failed" and result.failure_kind == "recognition"
    assert selected in visited(result)
    # A stale opener dispatches nothing; a stale cancel adds nothing to the
    # already dispatched opener. Neither failed recheck executes its goto.
    assert len(device.inputs) == expected_inputs
    assert all(entry[0] == "tap" for entry in device.inputs)
    assert result.variables["oas_login_phase"] == phase
    assert not result.oas_wakes


@pytest.mark.parametrize("confirmation", ["I_UI_CONFIRM", "I_UI_CONFIRM_SAMLL"])
def test_bind_phone_prompt_unknown_confirmation_requires_review_without_affirmative_input(
        login, screen, confirmation):
    result, device, _ = run_invitation(
        login, [screen("I_LOGIN_LOGIN_GOTO_BIND_PHONE"), screen(confirmation)],
        params={"enable_harvest": False})
    assert result.status == "failed" and visited(result)[-1] == "bind_phone"
    assert result.variables["oas_login_phase"] == "bind_phone"
    assert [entry[0] for entry in device.inputs] == ["tap"]  # Only the known opener.
    assert "cancel_bind_phone_prompt" not in visited(result)
    assert not result.oas_wakes


@pytest.mark.parametrize("choice", ["accept", "reject", "ignore"])
def test_bind_phone_inner_burst_restores_prompt_before_cancel(login, screen, choice):
    opener = screen("I_LOGIN_LOGIN_GOTO_BIND_PHONE")
    panel = screen("I_UI_CANCEL_SAMLL", "I_G_ACCEPT", "I_G_REJECT", "I_G_IGNORE")
    prompt = screen("I_UI_CANCEL_SAMLL")
    courtyard = screen("I_BUFF_1", "I_MAIN_GOTO_SHIKIGAMI_RECORDS")
    result, device, snapshots = run_invitation(
        login, [opener, panel, prompt, courtyard],
        params={"enable_harvest": False, "friend_invitation": choice})
    assert result.status == "success", result.summary()
    assert [entry[0] for entry in device.inputs] == ["tap", "tap", "tap"]
    names = visited(result)
    completed = "bind_phone_invite_" + choice + ("_acknowledged" if choice == "accept" else "_gone")
    ordered = ["open_bind_phone_prompt", f"bind_phone_invite_{choice}_enter",
               f"bind_phone_invite_{choice}_input", completed, "cancel_bind_phone_prompt",
               "confirm_courtyard", "skip_harvest"]
    assert [names.index(name) for name in ordered] == sorted(names.index(name) for name in ordered)
    assert names.count("cancel_bind_phone_prompt") == 1
    before_cancel = next(values for state, values, _ in snapshots
                         if state == "oas_login_cancel_bind_phone_prompt")
    resumed_login = next(values for state, values, _ in snapshots
                         if state == "oas_login_confirm_courtyard")
    assert before_cancel["oas_login_phase"] == "bind_phone"
    assert resumed_login["oas_login_phase"] == "login"
    assert list(result.oas_wakes) == (["WantedQuests"] if choice == "accept" else [])
    if choice == "accept":
        assert names.count(completed) == 1


def test_bind_phone_inner_burst_accept_only_review_precedes_prompt_cancel(login, screen):
    result, device, _ = run_invitation(
        login, [screen("I_LOGIN_LOGIN_GOTO_BIND_PHONE"), screen("I_UI_CANCEL_SAMLL", "I_G_ACCEPT")],
        params={"enable_harvest": False})
    assert result.status == "failed" and visited(result)[-1] == "bind_phone_invitation_review"
    assert [entry[0] for entry in device.inputs] == ["tap"]
    assert "cancel_bind_phone_prompt" not in visited(result)
    assert not result.oas_wakes


def test_bind_phone_prompt_stop_before_cancel_sends_no_further_input(login, screen):
    stopped = False

    def stop_before_cancel(_runner, _device, _clock, data):
        nonlocal stopped
        if data["state"] == "oas_login_cancel_bind_phone_prompt":
            stopped = True

    result, device, _ = run_invitation(
        login, [screen("I_LOGIN_LOGIN_GOTO_BIND_PHONE"), screen("I_UI_CANCEL_SAMLL")],
        params={"enable_harvest": False}, on_state=stop_before_cancel, should_stop=lambda: stopped)
    assert stopped and result.status == "stopped"
    assert [entry[0] for entry in device.inputs] == ["tap"]
    assert result.variables["oas_login_phase"] == "bind_phone"
    assert not result.oas_wakes


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
