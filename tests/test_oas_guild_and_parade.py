"""Offline unit tests for OAS FloatParade, GuildBanquet, and GuildActivityMonitor."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_guild_and_parade import (
    compile_float_parade_candidate,
    compile_guild_activity_monitor_candidate,
    compile_guild_banquet_candidate,
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
    for task in ("FloatParade", "Component_RightActivity", "TalismanPass", "GuildBanquet", "GuildActivityMonitor"):
        convert_task(inert_source / "tasks" / task.replace("Component_", "Component/", 1), folder, task)
    return stage, inert_source, folder


def _run_synthetic(raw, resources_root, frames, *, params=None, initial_vars=None, ocr_entries=None):
    wf = load_workflow(raw, [resources_root])
    aliases = {}
    for name, spec in wf.resources.items():
        if spec["type"] == "image":
            aliases.setdefault(Path(spec["path"]).resolve(), set()).add(name.rsplit("::", 1)[-1])

    def match(image, path, *_args, **_kwargs):
        visible = frames[int(image[0, 0, 0]) - 20]
        hit = bool(set(visible) & aliases.get(Path(path).resolve(), set()))
        return hit, float(hit), (200, 120, 40, 32)

    def full_ocr(image, region, keyword, score=0.6, **_kw):
        idx = int(image[0, 0, 0]) - 20
        for kw, box in (ocr_entries or {}).get(idx, []):
            if kw == keyword:
                return box if isinstance(box, FullOcrArea) else FullOcrArea(box, keyword_complete=True)
        return FullOcrArea((0, 0, 0, 0), keyword_complete=False)

    device = ReplayDevice([blank(20 + i) for i in range(len(frames))], advance_on_input=True)
    clock = MillisecondClock()
    with patch.object(engine, "match_template", match):
        result = engine.Runner(
            wf, Controller(device, sleep=clock.sleep), clock=clock,
            max_seconds=40, params=params, full_ocr_reader=full_ocr, initial_vars=initial_vars,
        ).run()
    return result, device


def test_float_parade_mileage_flower_and_return(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_float_parade_candidate(src, folder)
    frames = [
        ("I_TOGGLE_BUTTON",),
        ("I_FP_ACCESS",),
        ("I_FP_UPGRADE", "I_ENTRY_MILEAGE"),
        ("I_CLAIM_MILEAGE",),
        ("I_UI_REWARD",),
        ("I_UI_BACK_RED",),
        ("I_FP_GIFT_FLAG1", "I_FP_SELECT_3"),
        ("I_UI_REWARD",),
        ("I_FP_UPGRADE", "I_UI_BACK_YELLOW"),
        ("I_CHECK_MAIN",),
    ]
    res, dev = _run_synthetic(raw, stage / "resources", frames, initial_vars={"fp_phase": "enter_toggle"})
    assert res.status == "success", res.summary()
    assert res.oas_schedule == "FloatParade"
    assert res.variables["fp_mileage_claimed"] is True
    assert res.variables["fp_reward_receipts"] == 2
    assert len(dev.inputs) >= 6

    res_fp_tl, _ = _run_synthetic(
        raw, stage / "resources",
        [("I_FP_GETALL0",), ("I_UI_BACK_YELLOW",), ("I_CHECK_MAIN",)],
        params={"fp_limit_seconds": 1, "fp_next_delay_s": 259200},
        initial_vars={"fp_phase": "flower"},
    )
    assert res_fp_tl.status == "success", res_fp_tl.summary()
    assert res_fp_tl.variables["fp_exit_reason"] == "time_limit" and res_fp_tl.oas_target[0] == 259200


def test_guild_banquet_ongoing_and_not_started_retry(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_guild_banquet_candidate(src, folder)

    # Not started before 22:00 -> 5-min target retry
    res, _ = _run_synthetic(
        raw, stage / "resources", [("I_CHECK_GUILD", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        initial_vars={"gb_phase": "check_start"},
    )
    assert res.status == "success", res.summary()
    assert res.oas_schedule == "GuildBanquet"
    assert res.oas_target is not None and res.oas_target[0] == 300

    # Banquet ongoing -> flag disappears -> return main
    res2, _ = _run_synthetic(
        raw, stage / "resources", [("I_FLAG", "I_CHECK_GUILD", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"gb_check_interval_ms": 500, "gb_max_wait_seconds": 1},
        initial_vars={"gb_phase": "check_start"},
    )
    assert res2.status == "success", res2.summary()
    assert res2.variables["gb_exit_reason"] in ("ended", "timeout")
    assert res2.oas_schedule == "GuildBanquet"

    res3, _ = _run_synthetic(
        raw, stage / "resources", [("I_FLAG", "I_CHECK_GUILD", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"gb_check_interval_ms": 500, "gb_max_wait_seconds": 1, "gb_next_banquet_delay_s": 259200},
        initial_vars={"gb_phase": "check_start"},
    )
    assert res3.status == "success" and res3.oas_target is not None and res3.oas_target[0] == 259200

    res_gb_tl, _ = _run_synthetic(
        raw, stage / "resources", [("I_FLAG", "I_CHECK_GUILD", "I_UI_BACK_YELLOW"), ("I_CHECK_MAIN",)],
        params={"gb_limit_seconds": 1, "gb_max_wait_seconds": 920, "gb_next_banquet_delay_s": 259200},
        initial_vars={"gb_phase": "wait_banquet"},
    )
    assert res_gb_tl.status == "success" and res_gb_tl.variables["gb_exit_reason"] == "time_limit"
    assert res_gb_tl.oas_target is not None and res_gb_tl.oas_target[0] == 259200


def test_guild_activity_monitor_adb_gate_and_ocr_trigger(oas_stage):
    stage, src, folder = oas_stage
    raw = compile_guild_activity_monitor_candidate(src, folder)

    # Default use_ocr=False explicitly gated
    res_adb, _ = _run_synthetic(raw, stage / "resources", [()])
    assert res_adb.status == "failed"
    assert "dumpsys" in res_adb.reason

    # OCR mode detects new keyword -> natively wakes Dokan via oas_wake
    res_ocr, _ = _run_synthetic(
        raw, stage / "resources", [()],
        params={"gam_use_ocr": True, "gam_monitor_seconds": 10},
        initial_vars={"gam_phase": "monitor", "gam_init_keyword": ""},
        ocr_entries={0: [("道馆", (100, 50, 80, 24))]},
    )
    assert res_ocr.status == "success", res_ocr.summary()
    assert res_ocr.variables["gam_detected_task"] == "Dokan"
    assert list(res_ocr.oas_wakes) == ["Dokan"]

    # Partial single-char fallback (e.g. "道" in unrelated banner) must NOT falsely wake Dokan
    res_partial, _ = _run_synthetic(
        raw, stage / "resources", [()],
        params={"gam_use_ocr": True, "gam_monitor_seconds": 1},
        initial_vars={"gam_phase": "monitor", "gam_init_keyword": "", "gam_start_ms": -5000},
        ocr_entries={0: [("道馆", FullOcrArea((100, 50, 80, 24), keyword_complete=False))]},
    )
    assert res_partial.status == "success"
    assert res_partial.variables["gam_detected_task"] == ""
    assert not res_partial.oas_wakes

    # Skip day exits cleanly (default & custom weekday target schedule)
    res_skip, _ = _run_synthetic(raw, stage / "resources", [()], params={"gam_in_run_days": False})
    assert res_skip.status == "success"
    assert res_skip.oas_schedule == "GuildActivityMonitor"

    res_skip_t, _ = _run_synthetic(
        raw, stage / "resources", [()],
        params={"gam_in_run_days": False, "gam_next_run_delay_s": 86400},
    )
    assert res_skip_t.status == "success" and res_skip_t.oas_target[0] == 86400

    res_recheck, _ = _run_synthetic(
        raw, stage / "resources", [()],
        params={"gam_use_ocr": True, "gam_monitor_seconds": 1, "gam_recheck_minutes": 7, "gam_recheck_on_timeout": True},
        initial_vars={"gam_phase": "monitor", "gam_init_keyword": "", "gam_start_ms": -5000},
    )
    assert res_recheck.status == "success" and res_recheck.oas_target[0] == 420
    assert res_recheck.variables["gam_exit_reason"] == "timeout_recheck"
