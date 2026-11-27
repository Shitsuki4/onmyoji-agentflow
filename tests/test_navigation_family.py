"""Actual inert OAS callback source/resource conformance; no emulator inputs."""
import os
from pathlib import Path

import pytest

from onmyoji_agentflow.convert import navigation_family as family
from onmyoji_agentflow.convert.navigation import read_navigation
from onmyoji_agentflow.convert.oas import _asset_class_map, convert_task
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml


@pytest.fixture(scope="module")
def inert_source():
    root = Path(os.environ.get("OAF_OAS_SOURCE_ROOT", str(Path.home() / "AppData/Local/onmyoji-agentflow/upstream-src/oas")))
    if not (root / family.BATTLE).is_file():
        pytest.skip("optional inert OAS source checkout unavailable")
    return root


@pytest.fixture(scope="module")
def converted(inert_source, tmp_path_factory):
    stage = tmp_path_factory.mktemp("navigation-family")
    folder = stage / "resources/upstream/oas"
    graph = read_navigation(inert_source / "tasks", _asset_class_map(inert_source / "tasks"))
    tasks = set()
    def walk(value):
        if isinstance(value, dict):
            if "task" in value and "name" in value:
                tasks.add(value["task"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(graph)
    tasks.update(("Component_GeneralBattle", "Component_GeneralBuff", "Component_GeneralInvite", "Restart", "GlobalGame", "GameUi"))
    for task in sorted(tasks):
        relative = task.replace("Component_", "Component/", 1)
        convert_task(inert_source / "tasks" / relative, folder, task)
    return stage, folder


@pytest.mark.parametrize("binding", ["task", "default", "missing"])
def test_actual_navigation_keeps_bound_battle_body_and_remaining_source_obligations(inert_source, converted, binding):
    stage, folder = converted
    packet = family.compile_navigation_family(inert_source, folder, battle_config=binding)
    raw = packet["workflow"]
    path = stage / (binding + ".yaml")
    path.write_text(dump_yaml(raw), encoding="utf-8")
    load_workflow(path, [stage / "resources"])
    for key in ("page_battle_prepare", "page_battle"):
        assert raw["navigation"]["pages"][key]["hooks"]["enter_success"] == [
            {"result": False} if binding == "missing" else {"invoke": "nav_battle"}]
    if binding != "missing":
        call = raw["navigation"]["calls"]["nav_battle"]
        assert len(call["states"]) == 128
        assert {f"nav_battle_{stage}_result_visible" for stage in (
            "green_gate", "green_wait_prepare", "green_local", "green_coordinate",
        )} <= set(call["states"])
        assert call["initial_vars"]["nav_battle_current_count"] == 0
        assert call["result_var"] == "nav_battle_return"
        returns = [s for s in raw["states"] if any("navigation_return" in a for a in s["do"])]
        assert [s["id"] for s in returns] == ["nav_battle_returned_true", "nav_battle_returned_false"]
        assert all(s["do"][-1] == {"navigation_return": "nav_battle"} for s in returns)
        assert not any("stop" in a for s in raw["states"] if s["id"] in call["states"] for a in s["do"])
        assert len(packet["source_obligations"]) == (7 if binding == "task" else 3)
    else:
        assert not raw["navigation"].get("calls") and len(packet["source_obligations"]) == 3
    if binding == "default":
        assert all(spec["choices"] == [spec["default"]] for spec in raw["params"].values())
        contract = raw["navigation_family_contract"]
        disabled = contract["disabled_battle_obligations"]
        assert disabled == {
            item["id"]: {item["requires_enabled_param"]: False}
            for item in contract["battle_contract"]["source_obligations"]
        }
        assert set(disabled).isdisjoint(item.get("id") for item in packet["source_obligations"])
        with pytest.raises(WorkflowError, match="preset_enable"):
            load_workflow(path, [stage / "resources"]).validate_params({"preset_enable": True})
    if binding == "task":
        assert load_workflow(path, [stage / "resources"]).validate_params({"preset_enable": True})["preset_enable"]
        assert raw["navigation_family_contract"]["disabled_battle_obligations"] == {}
    assert not packet["complete"] and not packet["original_task_complete"]
    assert any("handle_login_page" in o.get("reason", "") for o in packet["source_obligations"])
    assert len(raw["navigation"]["pages"]) == 51 and len(raw["navigation"]["links"]) == 116
    assert raw["navigation_family_contract"]["construction"].startswith("fresh GeneralBattle")


def test_fallback_dispatch_drift_is_rejected_without_running_its_source(tmp_path):
    target = tmp_path / family.BATTLE
    target.parent.mkdir(parents=True)
    sentinel = tmp_path / "source-was-executed.txt"
    target.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"
                      "def run_task_or_default_general_battle(task):\n    return task.changed()\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fallback dispatch"):
        family.compile_navigation_family(tmp_path, tmp_path, battle_config="task")
    assert not sentinel.exists()


def test_android_login_opt_in_composes_with_battle_without_resetting_the_parent(inert_source, converted):
    stage, folder = converted
    packet = family.compile_navigation_family(inert_source, folder, battle_config="default", android_login=True)
    raw = packet["workflow"]
    loaded = load_workflow(raw, [stage / "resources"])
    navigation = raw["navigation"]
    assert navigation["pages"]["page_login"]["hooks"]["enter_success"] == [{"invoke": "nav_login"}]
    assert set(navigation["calls"]) == {"nav_battle", "nav_login"}
    assert navigation["calls"]["nav_login"]["initial_vars"]["nav_login_phase"] == "login_entry"
    assert loaded.validate_params({})["enable_harvest"]
    assert not packet["original_task_complete"]
    states = {state["id"]: state for state in loaded.states}
    stall = states["nav_login_restart_stalled_login"]
    assert stall["id"] in navigation["calls"]["nav_login"]["states"]
    assert stall["sensitive"] == "重启游戏"
    assert {"foreground_game": "com.netease.onmyoji"} in stall["when"]["all"]


@pytest.mark.parametrize("binding", [None, False, True, "has_config", "eval", []])
def test_config_binding_must_distinguish_none_from_attribute_error(tmp_path, binding):
    with pytest.raises(ValueError, match="battle_config"):
        family.compile_navigation_family(tmp_path, tmp_path, battle_config=binding)


def test_navigation_family_binds_courtyard_costume(inert_source, converted):
    stage, folder = converted
    convert_task(inert_source / "tasks/Component/Costume", folder, "Component_Costume")
    packet = family.compile_navigation_family(
        inert_source, folder, battle_config="default", courtyard_costume=17,
    )
    raw = packet["workflow"]
    load_workflow(raw, [stage / "resources"])
    assert raw["oas_courtyard_costume_contract"]["configured_costume"] == 17
    assets = raw["oas_courtyard_costume_contract"]["source_assets"]["GameUi::I_CHECK_MAIN"]
    assert assets == ["I_CHECK_MAIN_17_A", "I_CHECK_MAIN_17_B", "I_CHECK_MAIN_17_C"]
