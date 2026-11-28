"""App shutdown is a terminal, user-confirmed action on the owning emulator."""
from unittest.mock import Mock

import pytest

from helpers import blank
from onmyoji_agentflow.device.adb import AdbDevice
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import DeviceError, WorkflowError
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import CLOSE_APPS_CONFIRMATION, load_workflow
from test_handler_runner import MillisecondClock


PACKAGES = ["com.netease.onmyoji", "com.example.companion"]


class ForegroundReplay(ReplayDevice):
    foreground = True

    def app_in_foreground(self, package):
        return self.foreground and package == "com.netease.onmyoji"


def candidate():
    return {"format": 1, "name": "related_apps", "vars": {"issued": 0}, "states": [{
        "id": "close", "when": {"expr": "issued == 0"}, "do": [
            {"close_related_apps": {"packages": PACKAGES, "mode": "shell"},
             "recheck": True, "attempt_var": "issued"},
            {"stop": "finished"},
        ],
    }]}


def run(raw, device, confirm, *, observe=False, initial_vars=None):
    clock = MillisecondClock()
    return Runner(load_workflow(raw), Controller(device, observe=observe, sleep=clock.sleep),
                  clock=clock, max_seconds=2, initial_vars=initial_vars, confirm=confirm).run()


def test_close_app_confirmation_names_exact_targets_and_rechecks_foreground():
    raw, device, confirm = candidate(), ForegroundReplay([blank()]), Mock(return_value=True)
    result = run(raw, device, confirm)
    assert result.status == "success" and result.variables["issued"] == 1
    assert device.inputs == [("close_related_apps", tuple(PACKAGES), "shell")]
    category, prompt = confirm.call_args.args
    assert category == CLOSE_APPS_CONFIRMATION and all(package in prompt for package in PACKAGES)

    device = ForegroundReplay([blank()])
    denied = run(raw, device, lambda *_: False)
    assert denied.failure_kind == "confirm_denied" and not device.inputs and denied.variables["issued"] == 0

    def change_foreground(*_):
        device.foreground = False
        return True

    changed = run(raw, device, change_foreground)
    assert changed.failure_kind == "prerequisite" and not device.inputs and changed.variables["issued"] == 0

    confirm.reset_mock()
    device = ForegroundReplay([blank()])
    observed = run(raw, device, confirm, observe=True)
    assert observed.actions == 0 and not device.inputs and not confirm.called


def test_uncertain_close_is_not_replayed():
    device = ForegroundReplay([blank()])
    device.close_related_apps = Mock(side_effect=DeviceError("ADB response was lost"))
    confirm = Mock(return_value=True)
    result = run(candidate(), device, confirm)
    assert result.failure_kind == "app_close_uncertain" and result.variables["issued"] == 1
    retried = run(candidate(), device, confirm, initial_vars={"issued": 1})
    assert retried.failure_kind == "app_close_uncertain"
    assert device.close_related_apps.call_count == confirm.call_count == 1


def test_invalid_close_target_cannot_be_loaded():
    raw = candidate()
    raw["states"][0]["do"][0]["close_related_apps"] = {"packages": ["com.example; invalid"], "mode": "shell"}
    with pytest.raises(WorkflowError, match="close_related_apps"):
        load_workflow(raw)


@pytest.mark.parametrize("mode,expected", [("shell", "force-stop"), ("android api", "kill")])
def test_adb_closes_exact_configured_packages_for_current_user(monkeypatch, mode, expected):
    device = AdbDevice("replay", "adb", connect=False)
    focus = "mCurrentFocus= Window{u10 com.netease.onmyoji/.GameActivity}"
    device.current_app = Mock(side_effect=[focus, focus, "mCurrentFocus= Window{u10 com.launcher/.Home}"])
    device.shell = Mock(side_effect=["10\n", "\r\n".join("package:" + package for package in PACKAGES), "", ""])
    device._run = Mock()
    monkeypatch.setattr("onmyoji_agentflow.device.adb.time.sleep", lambda _seconds: None)
    device.close_related_apps(PACKAGES, mode)
    assert [call.args for call in device.shell.call_args_list] == [
        ("am", "get-current-user"), ("pm", "list", "packages", "--user", "10"),
        *(("am", expected, "--user", "10", package) for package in PACKAGES),
    ]
    if mode == "android api":
        device._run.assert_called_once_with(["shell", "input", "keyevent", "KEYCODE_HOME"])
    else:
        device._run.assert_not_called()


def test_adb_missing_exact_target_has_no_side_effect():
    device = AdbDevice("replay", "adb", connect=False)
    device.current_app = Mock(return_value="mCurrentFocus= Window{u0 com.netease.onmyoji/.GameActivity}")
    device.shell = Mock(side_effect=["0", "package:com.netease.onmyoji\npackage:com.example.companion.clone"])
    device._run = Mock()
    with pytest.raises(DeviceError, match="未安装"):
        device.close_related_apps(PACKAGES, "android api")
    assert device.shell.call_count == 2
    device._run.assert_not_called()
