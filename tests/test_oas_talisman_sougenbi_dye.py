"""Offline unit tests for OAS Sougenbi, TalismanPass, and DyeTrials schedule/reserve/limit upgrades."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_dye_trials import compile_dye_trials_candidate
from onmyoji_agentflow.convert.oas_sougenbi import compile_sougenbi_candidate
from onmyoji_agentflow.convert.oas_talisman import compile_talisman_candidate
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.workflow import engine
from onmyoji_agentflow.workflow.schema import load_workflow
from test_handler_runner import MillisecondClock
from test_navigation_family import converted, inert_source


@pytest.fixture(scope="module")
def oas_stage(inert_source, converted):
    stage, folder = converted
    for task in ("Sougenbi", "TalismanPass", "DyeTrials", "Component_GeneralBuff", "Component_SwitchSoul"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_int=None, boxes=None, advance_on_input=True):
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

    def read_int(image, region):
        return (ocr_int or {}).get(int(image[0, 0, 0]) - 20, 0)

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=advance_on_input)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        res = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock, max_seconds=60,
            params=params, ocr_reader=read_int, initial_vars=initial_vars,
            single_ocr_reader=lambda image, region, score: str(read_int(image, region)),
        ).run()
    return res, device


def test_sougenbi_talisman_dye_trials_reserve_limit_and_schedule(oas_stage):
    stage, src, folder = oas_stage

    # Sougenbi: ticket reserve stop + target schedule
    sg = compile_sougenbi_candidate(src, folder)
    res_sg, sg_device = _run(
        sg, stage / "resources",
        [("I_S_CHECK_SOUGENBI", "I_S_FIRE_FOOLERY", "I_UI_BACK_YELLOW", "I_CHECK_EXPLORATION"),
         ("I_CHECK_EXPLORATION",)],
        params={"sg_mode": "痴", "sg_ticket_reserve": 5, "sg_next_delay_s": 14400},
        initial_vars={"sg_phase": "cycle"},
        ocr_int={0: 5},
    )
    assert res_sg.status == "success", res_sg.summary()
    assert len(sg_device.inputs) == 1
    assert res_sg.variables["sg_exit_reason"] == "ticket_reserve"
    assert res_sg.oas_target is not None and res_sg.oas_target[0] == 14400

    # TalismanPass: target schedule preserving verified already_done status
    tp = compile_talisman_candidate(src, folder)["workflow"]
    res_tp, _ = _run(
        tp, stage / "resources", [()],
        params={"tp_harvest_soul": False, "tp_next_delay_s": 21600},
        initial_vars={"tp_phase": "optional_soul"},
    )
    assert res_tp.status == "success", res_tp.summary()
    assert res_tp.oas_target is not None and res_tp.oas_target[0] == 21600

    # TalismanPass: courtyard floating soul icon I_TP_SOUL_1 clicked dynamically inside 929px ROI
    res_tp_soul, dev_tp_soul = _run(
        {**tp, "stop_when": "tp_phase == 'soul_select'"},
        stage / "resources",
        [("I_TP_SOUL_1",), ("I_TP_SOUL_2",)],
        initial_vars={"tp_phase": "soul_open"},
        boxes={"I_TP_SOUL_1": (900, 420, 36, 38)},
    )
    assert res_tp_soul.status == "success"
    assert 900 <= dev_tp_soul.inputs[0][1] <= 936 and 420 <= dev_tp_soul.inputs[0][2] <= 458

    # DyeTrials: wall-clock time-limit + target schedule
    dye = compile_dye_trials_candidate(src, folder)["workflow"]
    res_dye, _ = _run(
        dye, stage / "resources",
        [("I_BATTLE_SUCCESS",), ("I_CHECK_MAIN",)],
        params={"dye_limit_seconds": 1, "dye_next_delay_s": 86400},
        initial_vars={"dye_phase": "challenge"},
    )
    assert res_dye.status == "success", res_dye.summary()
    assert res_dye.variables["dye_exit_reason"] == "time_limit"
    assert res_dye.oas_target is not None and res_dye.oas_target[0] == 86400


@pytest.mark.parametrize(
    ("phase", "threshold_ms", "marker", "timeout_state"),
    [
        ("task_claim", 10000, None, "task_reward_timeout"),
        ("level_claim", 2000, "I_CHECK_DAILY", "level_idle"),
        ("soul_search", 5000, "I_CHECK_MAIN", "soul_timeout"),
    ],
)
def test_talisman_timeout_is_strict_at_exact_boundary(oas_stage, phase, threshold_ms, marker, timeout_state):
    """At equality the established claim/search phase must still be active."""
    stage, src, folder = oas_stage
    workflow = compile_talisman_candidate(src, folder)["workflow"]
    raw = {**workflow}
    raw["blockers"] = [
        *workflow.get("blockers", []),
        {
            "id": "tp_exact_timeout_boundary",
            "when": {"all": [
                {"expr": f"tp_phase == {phase!r}"},
                {"expr": f"elapsed_ms - tp_timer == {threshold_ms}"},
            ]},
            "message": "Reached the exact TalismanPass timeout boundary",
        },
    ]
    blanks = threshold_ms // 200
    frames = [()] * (blanks + 4) if marker is None else [()] * blanks + [(marker,)] * 4
    result, _ = _run(
        raw, stage / "resources", frames,
        initial_vars={"tp_phase": phase, "tp_timer": 0},
        advance_on_input=False,
    )

    assert result.status == "failed", result.summary()
    assert result.failure_kind == "prerequisite"
    assert result.failed_state == "tp_exact_timeout_boundary"
    assert result.variables["tp_phase"] == phase
    assert result.variables["tp_reward_receipts"] == 0
    assert not any(state == f"tp_{timeout_state}" for _, state in result.history)


@pytest.mark.parametrize(
    ("phase", "threshold_ms", "timeout_state", "next_phase"),
    [
        ("task_claim", 10000, "task_reward_timeout", "level_probe"),
        ("level_claim", 2000, "level_idle", "optional_soul"),
        ("soul_search", 5000, "soul_timeout", "finished"),
    ],
)
def test_talisman_timeouts_need_no_page_marker_and_do_not_fabricate_receipt(
    oas_stage, phase, threshold_ms, timeout_state, next_phase,
):
    """Start in each established upstream phase on marker-free replay frames."""
    stage, src, folder = oas_stage
    workflow = compile_talisman_candidate(src, folder)["workflow"]
    raw = {**workflow, "stop_when": f"tp_phase == {next_phase!r}"}
    pending = phase in ("task_claim", "level_claim")
    initial = {
        "tp_phase": phase,
        "tp_timer": 0,
        "tp_reward_inputs": int(pending),
        "tp_reward_pending": pending,
        "tp_unverified_claim": False,
        "tp_reward_receipts": 0,
    }
    result, device = _run(
        raw, stage / "resources", [()] * (threshold_ms // 200 + 24),
        initial_vars=initial,
    )

    assert result.status == "success", result.summary()
    assert result.variables["tp_phase"] == next_phase
    assert result.variables["tp_reward_receipts"] == 0
    assert result.variables["tp_reward_pending"] is False
    assert result.variables["tp_unverified_claim"] is pending
    assert not device.inputs
    timed_out = [(at, state) for at, state in result.history if state == f"tp_{timeout_state}"]
    assert timed_out == [((threshold_ms + 200) / 1000, f"tp_{timeout_state}")]


@pytest.mark.parametrize(
    ("phase", "threshold_ms", "page_marker", "timeout_state", "next_phase"),
    [
        ("level_claim", 2000, "I_CHECK_DAILY", "level_idle", "optional_soul"),
        ("soul_search", 5000, "I_CHECK_MAIN", "soul_timeout", "finished"),
    ],
)
def test_talisman_timeout_still_fires_with_page_marker_present(
    oas_stage, phase, threshold_ms, page_marker, timeout_state, next_phase,
):
    stage, src, folder = oas_stage
    workflow = compile_talisman_candidate(src, folder)["workflow"]
    raw = {**workflow, "stop_when": f"tp_phase == {next_phase!r}"}
    frames = [()] * (threshold_ms // 200 + 1) + [(page_marker,)] * 8
    result, _ = _run(
        raw, stage / "resources", frames,
        initial_vars={"tp_phase": phase, "tp_timer": 0},
        advance_on_input=False,
    )

    assert result.status == "success", result.summary()
    assert result.variables["tp_phase"] == next_phase
    assert result.variables["tp_reward_receipts"] == 0
    assert (threshold_ms + 200) / 1000 in [at for at, state in result.history if state == f"tp_{timeout_state}"]


@pytest.mark.parametrize(
    ("phase", "threshold_ms", "tail", "stop_when", "priority_state", "timeout_state", "next_phase", "receipts"),
    [
        (
            "task_claim", 10000,
            [("I_UI_REWARD",), ("I_UI_REWARD",), ("I_CHECK_DAILY",), ("I_CHECK_DAILY",)],
            "tp_phase == 'level_probe'", "task_reward_seen", "task_reward_timeout", "level_probe", 1,
        ),
        (
            "level_claim", 2000,
            [("I_UI_REWARD",), ("I_UI_REWARD",)],
            "tp_reward_receipts > 0", "level_reward_seen", "level_idle", "level_claim", 1,
        ),
        (
            "soul_search", 5000,
            [("I_TP_SOUL_1",)],
            "tp_phase == 'soul_open'", "soul_found", "soul_timeout", "soul_open", 0,
        ),
    ],
)
def test_talisman_positive_reward_evidence_precedes_timeout(
    oas_stage, phase, threshold_ms, tail, stop_when, priority_state, timeout_state, next_phase, receipts,
):
    stage, src, folder = oas_stage
    workflow = compile_talisman_candidate(src, folder)["workflow"]
    raw = {**workflow, "stop_when": stop_when}
    claimed = phase in ("task_claim", "level_claim")
    initial = {
        "tp_phase": phase,
        "tp_timer": 0,
        "tp_reward_inputs": int(claimed),
        "tp_reward_pending": claimed,
        "tp_unverified_claim": False,
        "tp_reward_receipts": 0,
    }
    frames = [()] * (threshold_ms // 200 + 1) + tail + [()] * 8
    result, _ = _run(
        raw, stage / "resources", frames,
        initial_vars=initial,
        advance_on_input=False,
    )

    assert result.status == "success", result.summary()
    assert result.variables["tp_phase"] == next_phase
    assert result.variables["tp_reward_receipts"] == receipts
    assert result.variables["tp_reward_pending"] is (claimed and phase == "task_claim" and receipts == 0)
    assert result.variables["tp_unverified_claim"] is False
    states = [state for _, state in result.history]
    assert f"tp_{priority_state}" in states
    assert f"tp_{timeout_state}" not in states
