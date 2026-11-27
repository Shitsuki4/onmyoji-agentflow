"""Exercise the source-pinned 御灵 task loop without emulator inputs."""
from pathlib import Path

import pytest

from helpers import FakeClock, blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_goryou import compile_goryou_candidate
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.workflow import engine
from onmyoji_agentflow.workflow.schema import load_workflow
from test_navigation_family import converted, inert_source
from test_handler_runner import MillisecondClock


@pytest.fixture(scope="module")
def workflow(inert_source, converted):
    stage, folder = converted
    for task in ("GoryouRealm", "Restart", "Component_GeneralInvite", "Component_GeneralBuff", "Component_SwitchSoul"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    packet = compile_goryou_candidate(inert_source, folder)
    assert not packet["complete"]
    return load_workflow(packet["workflow"], [stage / "resources"])


@pytest.fixture
def frames(workflow, monkeypatch, request):
    aliases = {Path(resource["path"]).name: key for key, resource in workflow.resources.items()
               if "::" in key and resource["type"] == "image"}
    contains = {}

    def frame(*visible):
        key = len(contains) + 20
        contains[key] = visible
        return blank(key)

    def match(image, path, *_args, **_kwargs):
        key = aliases[Path(path).name]
        present = key in contains[int(image[0, 0, 0])]
        return present, float(present), tuple(workflow.resources[key]["front"])

    monkeypatch.setattr(engine, "match_template", match)
    challenge = ["GoryouRealm::I_GR_FIRE", "GoryouRealm::I_GR_UNLOCK", "GlobalGame::I_UI_BACK_YELLOW"]
    if getattr(request, "param", False):
        challenge.append("GameUi::I_CHECK_EXPLORATION")
    return frame(*challenge), frame("GameUi::I_CHECK_EXPLORATION")


@pytest.mark.parametrize("tickets", [0, None, 3])
def test_goryou_gates_ticket_use_and_only_finishes_after_return(workflow, frames, tickets):
    def read_single(_image, region, _threshold):
        if region == (1058, 630, 92, 49):
            return "×1"
        return str(tickets) if tickets is not None else ""

    device = ReplayDevice(list(frames), advance_on_input=True)
    result = engine.Runner(workflow, Controller(device, sleep=lambda _: None), clock=FakeClock(.05),
                           initial_vars={"gr_phase": "cycle"}, single_ocr_reader=read_single,
                           max_actions=1 if tickets == 3 else None, max_seconds=5).run()
    if tickets is None:
        assert device.inputs == []
    elif tickets == 0:
        assert result.status == "success", result.summary()
        assert result.variables["gr_exit_reason"] == "no_tickets"
        assert [s for _, s in result.history][-1] == "gr_returned_to_exploration"
        _, x, y = device.inputs[0]
        assert len(device.inputs) == 1 and 26 <= x <= 73 and 17 <= y <= 63
    else:
        assert result.status == "limit", result.summary()
        _, x, y = device.inputs[0]
        assert len(device.inputs) == 1 and 1051 <= x <= 1151 and 577 <= y <= 677
    assert not result.summary()["business_ok"]


def test_goryou_does_not_send_a_second_challenge_if_the_page_stays_open(workflow, frames):
    def read_single(_image, region, _threshold):
        return "×1" if region == (1058, 630, 92, 49) else "3"

    clock = MillisecondClock()
    device = ReplayDevice([frames[0]])
    result = engine.Runner(workflow, Controller(device, sleep=clock.sleep), clock=clock,
                           initial_vars={"gr_phase": "cycle"}, single_ocr_reader=read_single,
                           max_seconds=15).run()
    assert result.failed_state == "gr_challenge_unconfirmed", result.summary()
    assert len(device.inputs) == 1


@pytest.mark.parametrize("frames", [True], indirect=True)
def test_goryou_requires_leaving_the_boss_page_before_recording_victory(workflow, frames):
    clock = MillisecondClock()
    device = ReplayDevice(frames, advance_on_input=True)
    result = engine.Runner(
        workflow, Controller(device, sleep=clock.sleep), clock=clock,
        initial_vars={"gr_phase": "exit", "gr_wins": 1, "gr_attempts": 1, "gr_ticket_receipts": 1},
        max_seconds=15,
    ).run()
    assert result.business_ok and result.oas_schedule == "GoryouRealm", result.summary()
    assert [state for _, state in result.history] == ["gr_back_to_exploration", "gr_completed_with_victory"]
    assert len(device.inputs) == 1


def test_goryou_navigation_battle_uses_private_defaults(workflow):
    raw = workflow.raw
    callback = raw["navigation"]["calls"]["gr_nav_battle"]
    assert raw["navigation_family_contract"]["battle_config_binding"] == "default"
    assert callback["initial_vars"]["gr_nav_battle_config_lock_team_enable"] == workflow.param_defaults()["lock_team_enable"]
    callback_state = next(state for state in workflow.states if state["id"] == "gr_nav_battle_prepare_first_setup")
    assert "gr_nav_battle_config_lock_team_enable" in str(callback_state["when"])
    assert "gr_nav_battle_config_lock_team_enable" not in workflow.param_defaults()


@pytest.mark.parametrize("costume", [0, 1])
def test_goryou_numbered_soul_preset_applies_after_stable_ocr_and_group_check(
        workflow, inert_source, converted, monkeypatch, costume):
    stage, folder = converted
    raw = workflow.raw
    if costume:
        convert_task(inert_source / "tasks/Component/CostumeShikigami", folder, "Component_CostumeShikigami")
        raw = compile_goryou_candidate(inert_source, folder, shikigami_costume=costume)["workflow"]
    raw = {**raw, "stop_when": "gr_phase == 'navigation'"}
    wf = load_workflow(raw, [stage / "resources"])
    aliases = {Path(resource["path"]): key for key, resource in wf.resources.items()
               if "::" in key and resource["type"] == "image"}
    soul = "Component_SwitchSoul::"
    skin = "Component_CostumeShikigami::"
    suffix = f"_{costume}" if costume else ""
    panel = (skin if costume else soul) + "I_SOU_TEAM_PRESENT" + suffix
    group = (skin if costume else soul) + "I_SOU_CHECK_GROUP_3" + suffix
    team = (skin if costume else soul) + "I_SOU_SWITCH_2" + suffix
    if costume:
        page = raw["navigation"]["pages"]["page_shikigami_records"]["when"]
        assert page == {"res": f"{skin}I_CHECK_RECORDS{suffix}"}
    confirm = "GlobalGame::I_UI_CONFIRM"
    visible = [{panel}, {panel}, {panel}, {panel, group, team}, {panel, group, team, confirm}, {panel, group}]

    def match(image, path, *_args, **_kwargs):
        present = aliases[Path(path)] in visible[int(image[0, 0, 0]) - 20]
        return present, float(present), (200, 100, 40, 32)

    monkeypatch.setattr(engine, "match_template", match)
    clock = MillisecondClock()
    device = ReplayDevice([blank(value) for value in range(20, 26)], advance_on_input=True)
    result = engine.Runner(wf, Controller(device, sleep=clock.sleep), clock=clock,
        initial_vars={"gr_phase": "soul_scroll"}, text_reader=lambda *_: [("分组一", 1150, 130), ("分组三", 1150, 280)],
        params={"goryou_switch_soul_enabled": True, "goryou_soul_group": 3, "goryou_soul_team": 2}, max_seconds=25).run()
    assert result.status == "success", result.summary()
    assert [op[0] for op in device.inputs] == ["swipe", "tap", "tap", "tap", "tap"]
    assert result.variables["gr_soul_group_taps"] == 2 and result.variables["gr_soul_confirm_taps"] == 1
    assert result.variables["gr_soul_groups"] == '["分组一", "分组三"]'


def test_missing_goryou_soul_group_refuses_input(workflow):
    clock = MillisecondClock()
    device = ReplayDevice([blank()])
    result = engine.Runner(workflow, Controller(device, sleep=clock.sleep), clock=clock,
                           params={"goryou_switch_soul_enabled": True}).run()
    assert result.status == "failed" and result.failed_state == "gr_soul_unconfigured" and not device.inputs
