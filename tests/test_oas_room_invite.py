"""Offline unit tests for shared OAS GeneralRoom & GeneralInvite native builders."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_room_invite import (
    bind_leader_invite_and_fire,
    bind_member_accept_and_wait,
    bind_room_create,
    bind_room_exit,
)
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.vision.ocr import FullOcrArea
from onmyoji_agentflow.workflow import engine
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import MillisecondClock
from test_navigation_family import converted, inert_source


@pytest.fixture(scope="module")
def oas_stage(inert_source, converted):
    stage, folder = converted
    for task in ("Component_GeneralRoom", "Component_GeneralInvite", "Component_GeneralBattle", "GlobalGame"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _base_workflow(name: str, initial_phase: str) -> dict:
    return {
        "format": 1,
        "name": name,
        "resource_namespaces": True,
        "resources": [],
        "params": {},
        "vars": {"phase": initial_phase, "outcome": ""},
        "states": [],
        "loop_delay_ms": 100,
        "limits": {"timeout_s": 60, "unknown_timeout_s": 10, "stuck_timeout_s": 60, "no_progress_timeout_s": 60, "max_repeat": 100},
        "default_result": "unknown",
    }


def _run(raw, root, frames, *, params=None, full_ocr=None, advance_on_input=True, boxes=None):
    wf = load_workflow(raw, [root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, *_a, **_kw):
        vis = frames[int(image[0, 0, 0]) - 20]
        hits = set(vis) & aliases.get(Path(path).resolve(), set())
        if not hits:
            return False, 0.0, (0, 0, 0, 0)
        for h in hits:
            if boxes and h in boxes:
                return True, 1.0, boxes[h]
        return True, 1.0, (200, 120, 40, 32)

    def read_full(image, region, keyword, score=0.6, **_kw):
        return (full_ocr or {}).get((int(image[0, 0, 0]) - 20, keyword), (0, 0, 0, 0))

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=advance_on_input)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, full_ocr_reader=read_full,
        ).run()
    return res, device


def test_leader_create_invite_fire_and_exit(oas_stage):
    stage, src, folder = oas_stage
    raw = _base_workflow("test_leader_room_invite", "create")
    bind_room_create(raw, src, folder, prefix="ld", phase_var="phase",
                     entry_phase="create", ready_phase="invite", fail_phase="create_fail")
    bind_leader_invite_and_fire(raw, src, folder, prefix="ld", phase_var="phase",
                                entry_phase="invite", battle_phase="battled", exit_phase="exit_room",
                                room_type="normal_3")
    bind_room_exit(raw, src, folder, prefix="ld", phase_var="phase",
                   entry_phase="exit_room", done_phase="done")
    raw["states"].append({"id": "stop_battled", "when": {"expr": "phase == 'battled'"},
                          "do": [{"stop": {"reason": "leader_battled", "result": "unknown", "verified": False}}]})
    raw["states"].append({"id": "stop_done", "when": {"expr": "phase == 'done'"},
                          "do": [{"stop": {"reason": "leader_done", "result": "unknown", "verified": False}}]})
    raw["states"].append({"id": "stop_fail", "when": {"expr": "phase == 'create_fail'"},
                          "do": [{"fail": "no_tickets"}]})

    frames = [
        ("I_CREATE_ROOM",),
        ("I_CREATE_ENSURE", "I_ENSURE_PRIVATE_FALSE"),
        ("I_CREATE_ENSURE", "I_ENSURE_PRIVATE"),
        ("I_GI_EMOJI_1", "I_ADD_1", "I_ADD_2"),
        ("I_INVITE_ENSURE",),
        ("I_SELECTED", "I_INVITE_ENSURE"),
        ("I_GI_EMOJI_1", "I_FIRE"),
        (),
    ]
    res, dev = _run(
        raw, stage / "resources", frames,
        params={"ld_friend_1": "Alice"},
        full_ocr={(4, "Alice"): FullOcrArea((450, 220, 80, 28), keyword_complete=True)},
        boxes={"I_CREATE_ROOM": (450, 595, 177, 58)},
    )
    assert res.status == "success" and res.reason == "leader_battled", (res.summary(), dev.inputs)
    assert len(dev.inputs) == 7
    assert 450 <= dev.inputs[0][1] <= 627 and 595 <= dev.inputs[0][2] <= 653

    res_exit, dev_exit = _run(
        {**raw, "vars": {**raw["vars"], "phase": "exit_room"}},
        stage / "resources",
        [("I_GI_EMOJI_1", "I_BACK_YELLOW"), ("I_UI_CONFIRM",), ("I_GR_BACK_YELLOW",), ()],
        boxes={"I_UI_CONFIRM": (670, 560, 179, 66)},
    )
    assert res_exit.status == "success" and res_exit.reason == "leader_done", (res_exit.summary(), dev_exit.inputs)
    assert len(dev_exit.inputs) == 3
    assert 670 <= dev_exit.inputs[1][1] <= 849 and 560 <= dev_exit.inputs[1][2] <= 626

    # Multi-tab fallback (friend_1 on tab 2) + friend_2 invite in 2-friend room
    frames_2 = [
        ("I_GI_EMOJI_1", "I_ADD_1", "I_ADD_2"),
        ("I_INVITE_ENSURE", "I_FLAG_2_OFF"),
        ("I_INVITE_ENSURE", "I_FLAG_2_ON"),
        ("I_SELECTED", "I_INVITE_ENSURE"),
        ("I_GI_EMOJI_1", "I_ADD_2"),
        ("I_INVITE_ENSURE",),
        ("I_SELECTED", "I_INVITE_ENSURE"),
        ("I_GI_EMOJI_1", "I_FIRE"),
        (),
    ]
    res_2, dev_2 = _run(
        {**raw, "vars": {**raw["vars"], "phase": "invite"}},
        stage / "resources", frames_2,
        params={"ld_invite_number": 2, "ld_friend_1": "Alice", "ld_friend_2": "Bob"},
        full_ocr={
            (2, "Alice"): FullOcrArea((450, 220, 80, 28), keyword_complete=True),
            (5, "Bob"): FullOcrArea((450, 260, 80, 28), keyword_complete=True),
        },
    )
    assert res_2.status == "success" and res_2.reason == "leader_battled", (res_2.summary(), dev_2.inputs)
    assert len(dev_2.inputs) == 8

    # Leader wait timeout exits cleanly after invite
    res_to, _ = _run(
        {**raw, "vars": {**raw["vars"], "phase": "invite"}},
        stage / "resources",
        [
            ("I_GI_EMOJI_1", "I_ADD_1", "I_ADD_2"),
            ("I_INVITE_ENSURE",),
            ("I_GI_EMOJI_1", "I_ADD_1", "I_ADD_2", "I_BACK_YELLOW"),
            ("I_UI_CONFIRM",),
            (),
        ],
        params={"ld_friend_1": "MissingFriend", "ld_leader_wait_seconds": 0},
    )
    assert res_to.status == "success" and res_to.reason == "leader_done", res_to.summary()

    # Recent-friend mode switches directly to tab 2 + uncheck default_invite=False when I_UI_CHECK visible
    res_rec, dev_rec = _run(
        {**raw, "vars": {**raw["vars"], "phase": "invite"}},
        stage / "resources",
        [
            ("I_UI_CHECK", "I_UI_CONFIRM"),
            ("I_UI_CONFIRM",),
            ("I_GI_EMOJI_1", "I_ADD_1", "I_ADD_2"),
            ("I_INVITE_ENSURE", "I_FLAG_2_OFF"),
            ("I_INVITE_ENSURE", "I_FLAG_2_ON"),
            ("I_SELECTED", "I_INVITE_ENSURE"),
            ("I_GI_EMOJI_1", "I_FIRE"),
            (),
        ],
        params={"ld_default_invite": False, "ld_find_mode": "recent_friend", "ld_friend_1": "Carol"},
        full_ocr={(4, "Carol"): FullOcrArea((450, 220, 80, 28), keyword_complete=True)},
    )
    assert res_rec.status == "success" and res_rec.reason == "leader_battled", (res_rec.summary(), dev_rec.inputs)
    assert res_rec.variables["ld_invite_tab"] == 2 and len(dev_rec.inputs) == 7


def test_member_accept_wait_and_leader_fled(oas_stage):
    stage, src, folder = oas_stage
    raw = _base_workflow("test_member_invite", "accept")
    bind_member_accept_and_wait(raw, src, folder, prefix="mb", phase_var="phase",
                                entry_phase="accept", battle_phase="battled", exit_phase="exit_room")
    bind_room_exit(raw, src, folder, prefix="mb", phase_var="phase",
                   entry_phase="exit_room", done_phase="fled_done")
    raw["states"].append({"id": "stop_battled", "when": {"expr": "phase == 'battled'"},
                          "do": [{"stop": {"reason": "member_battled", "result": "unknown", "verified": False}}]})
    raw["states"].append({"id": "stop_fled", "when": {"expr": "phase == 'fled_done'"},
                          "do": [{"stop": {"reason": "member_exited_after_leader_fled", "result": "unknown", "verified": False}}]})

    res_battle, dev_battle = _run(
        raw, stage / "resources", [("I_I_ACCEPT",), ("I_I_ACCEPT",), ("I_GI_EMOJI_1",), ()],
        advance_on_input=False, boxes={"I_I_ACCEPT": (113, 410, 63, 72)},
    )
    assert res_battle.status == "success" and res_battle.reason == "member_battled"
    assert 113 <= dev_battle.inputs[0][1] <= 176 and 410 <= dev_battle.inputs[0][2] <= 482

    res_fled, dev_fled = _run(
        raw, stage / "resources",
        [("I_I_ACCEPT_DEFAULT",), ("I_GI_EMOJI_1", "I_FIRE", "I_BACK_YELLOW"), ("I_UI_CONFIRM",), ()],
        boxes={"I_I_ACCEPT_DEFAULT": (115, 360, 62, 65)},
    )
    assert res_fled.status == "success" and res_fled.reason == "member_exited_after_leader_fled"
    assert 115 <= dev_fled.inputs[0][1] <= 177 and 360 <= dev_fled.inputs[0][2] <= 425

    res_mto, _ = _run(
        raw, stage / "resources",
        [("I_I_ACCEPT",), ("I_GI_EMOJI_1", "I_BACK_YELLOW"), ("I_UI_CONFIRM",), ()],
        params={"mb_member_wait_seconds": 0},
    )
    assert res_mto.status == "success" and res_mto.reason == "member_exited_after_leader_fled"

    res_inst, _ = _run(raw, stage / "resources", [("I_PREPARE_HIGHLIGHT",)])
    assert res_inst.status == "success" and res_inst.reason == "member_battled"
