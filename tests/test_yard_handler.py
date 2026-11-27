"""Data-only 503 conversion checks against the pinned upstream checkout."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from onmyoji_agentflow.convert.yard_handler import load_yard_handler, yard_workflow
from onmyoji_agentflow.workflow.schema import validate


@pytest.fixture
def pinned_assttyys():
    root = Path(os.environ.get(
        "OAF_ASSTTYYS_SOURCE_ROOT",
        str(Path.home() / "AppData/Local/onmyoji-agentflow/upstream-src/assttyys"),
    ))
    if not (root / "src/common/funcList/503_返回庭院界面.ts").is_file():
        pytest.skip("pinned assttyys checkout is not available")
    return root


def test_503_is_parsed_as_a_guarded_incomplete_handler(pinned_assttyys):
    packet = load_yard_handler(pinned_assttyys)
    handler = packet["handler"]

    assert packet["complete"] is False
    assert packet["original_task_complete"] is False
    assert len(handler["proof"]["source_operator_ranges"]) == 50
    assert len(handler["proof"]["enabled_operator_order"]) == 43
    assert [item["id"] for item in packet["source_obligations"]] == [
        "yard503.too_many_returns",
        "yard503.target_rerun",
        "yard503.arrived_stop",
        "yard503.arrived_close_app",
    ]
    assert all(item["blocking"] for item in packet["source_obligations"])
    assert not any(action.get("rerun") or action.get("source_push")
                   for branch in handler["cases"] for action in branch.get("do", []))


def test_503_composition_loads_only_with_explicit_native_contract(pinned_assttyys):
    handler = load_yard_handler(pinned_assttyys)["handler"]
    packet = yard_workflow("yard-probe", [handler])
    workflow = packet["workflow"]

    assert packet["guarded_executable"] is True
    assert packet["executable"] is False
    assert packet["coverage"] == "guarded-core-handler-partial"
    assert workflow["yard_handler_contract"]["source_complete"] is False
    assert len(workflow["core_handler_contract"]["source_obligations"]) == 4
    assert len(workflow["states"]) > 50
    validate(workflow, workflow.get("inline_resources", {}))


def test_503_runtime_and_super_targets_are_preserved_separately(pinned_assttyys):
    packet = load_yard_handler(
        pinned_assttyys,
        runtime_params={"next_scheme_name": "daily_target"},
        super_target="super_target",
    )
    bindings = packet["handler"]["proof"]["source_state_bindings"]

    assert packet["handler"]["vars"]["yard503_runtime_target"] == "daily_target"
    assert packet["handler"]["vars"]["super_next_scheme_name"] == "super_target"
    assert "runtimeParams.next_scheme_name" in bindings
    assert "superGlobal.next_scheme_name" in bindings


def test_503_rejects_code_and_unknown_config_instead_of_executing_it(pinned_assttyys):
    source = (pinned_assttyys / "src/common/funcList/503_返回庭院界面.ts").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="source fingerprint"):
        from onmyoji_agentflow.convert.yard_handler import compile_yard_handler
        compile_yard_handler(source + "\n", {}, config={})

    with pytest.raises(ValueError, match="undeclared"):
        load_yard_handler(pinned_assttyys, config={"unreviewed": "run arbitrary code"})


def test_503_rejects_conflicting_legacy_and_native_config_aliases(pinned_assttyys):
    with pytest.raises(ValueError, match="alias collision"):
        load_yard_handler(pinned_assttyys, config={
            "oper_find_-1": False,
            "oper_find_minus_1": True,
        })


def test_503_fallback_reports_the_missing_toast_as_source_behavior(pinned_assttyys):
    packet = load_yard_handler(pinned_assttyys)
    fallback = next(case for case in packet["handler"]["cases"] if case["id"] == "fallback_home_icon")
    assert fallback["do"] == [
        {"click_found": True, "offset": [0, 0, 15, 15], "delay": 1200},
        {"inc": "back_time"},
        {"log": "点击左上角返回庭院图标"},
    ]
    adaptation = packet["handler"]["proof"]["source_behavior_adaptations"][0]
    assert adaptation["source"] == "myToast('点击左上角返回庭院图标')"
    assert adaptation["native"] == "log event after the same click and back_time increment"
    assert "in-game toast" in adaptation["difference"]
