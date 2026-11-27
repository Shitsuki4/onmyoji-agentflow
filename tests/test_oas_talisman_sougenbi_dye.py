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


def _run(raw, root, frames, *, params=None, initial_vars=None, ocr_int=None, boxes=None):
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

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
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
