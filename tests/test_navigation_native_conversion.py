import ast
import hashlib
import json

import pytest

from onmyoji_agentflow.convert.navigation import read_navigation
from onmyoji_agentflow.convert.navigation_native import NavigationCompiler
from onmyoji_agentflow.workflow.navigation import NativeNavigator, validate_navigation
from onmyoji_agentflow.workflow.schema import resolve_resources
from onmyoji_agentflow.yamlio import dump_yaml


def test_native_graph_keeps_namespace_composites_hooks_and_town_fallback(tmp_path):
    tasks = tmp_path / "tasks"
    (tasks / "GameUi").mkdir(parents=True)
    (tasks / "GameUi/default_pages.py").write_text("""
from tasks.GameUi.assets import GameUiAssets as G
page_main = Page(G.I_MAIN)
page_town = Page(any_of(G.I_TOWN, G.I_TOWN_OTHER), priority=80)
page_town.add_enter_success_hooks(conditional_action(G.I_AD, G.C_CLOSE))
page_town.connect(page_main, G.I_BACK, key='town-home', cost=2)
""", encoding="utf-8")
    folder = tmp_path / "resources/upstream/oas"
    folder.mkdir(parents=True)
    (folder / "GameUi.yaml").write_text(dump_yaml({"resources": {
        **{name: {"type": "image", "front": [10, 20, 30, 40], "file": name + ".png"}
           for name in ("I_MAIN", "I_TOWN", "I_TOWN_OTHER", "I_AD", "I_BACK")},
        "C_CLOSE": {"type": "click", "rect": [10, 10, 20, 20]}}}), encoding="utf-8")
    graph = read_navigation(tasks, {"GameUiAssets": "GameUi"})
    result = NavigationCompiler(graph, folder).compile()
    assert result["complete"] and not result["unsupported"]
    native = result["navigation"]
    assert native["pages"]["page_town"]["when"] == {"any": [
        {"res": "GameUi::I_TOWN"}, {"res": "GameUi::I_TOWN_OTHER"}]}
    assert native["links"][0]["fallback"]["action"]["click"] == [25, 40, 25, 40]
    resources = resolve_resources(result, None, [tmp_path / "resources"])
    validate_navigation(native, resources, set())


def test_untranslated_callbacks_stay_explicit_and_inert(tmp_path):
    result = NavigationCompiler({"format": 2, "pages": {}, "links": []}, tmp_path)
    node = result.action({"callable": {"name": "shell", "file": "not-an-import.py"}})
    assert "blocked" in node
    assert len(result.diagnostics) == 1
    # Even a correctly named helper must match the reviewed complete body.
    node = result.action({"callable": {"name": "exploration_to_six_gates"}})
    assert "缺少完整" in node["blocked"]
    result.graph["functions"] = {"GameUi/default_pages.py:exploration_to_six_gates": {
        "source": "def exploration_to_six_gates(task):\n    return task.dangerous()"}}
    node = result.action({"callable": {"name": "exploration_to_six_gates"}})
    assert "指纹未核对" in node["blocked"]


def test_missing_page_matcher_resource_cannot_be_silently_dropped(tmp_path):
    with pytest.raises(ValueError, match="缺少资源"):
        NavigationCompiler({"format": 2, "pages": {"home": {"check": {"task": "GameUi", "name": "I_MISSING"}}},
                            "links": []}, tmp_path).compile()


def test_callable_condition_rejects_non_parameter_receiver(tmp_path):
    builder = NavigationCompiler({"format": 2}, tmp_path)
    with pytest.raises(ValueError, match="尚未转换"):
        builder.condition({"callable": {"lambda": "lambda task: elsewhere.appear(G.I_MAIN)",
                                        "assets": {"G": "GameUi"}}})


def test_global_affirmative_closers_are_accounted_for_without_input(tmp_path):
    builder = NavigationCompiler({"format": 2, "pages": {}, "links": [], "unknown_closers": {
        "alternatives": [{"task": "GlobalGame", "name": "I_UI_CONFIRM"}]}}, tmp_path)
    result = builder.compile()
    assert not result["complete"]
    assert "具体弹窗上下文" in result["unsupported"][0]["reason"]
    assert result["navigation"]["unknown_closers"] == []


def test_calibration_adds_a_bound_alternative_without_replacing_source(tmp_path):
    (tmp_path / "GameUi.yaml").write_text(dump_yaml({"resources": {
        "I_MAIN": {"type": "image", "file": "not-read.png", "front": [10, 20, 30, 40]}}}), encoding="utf-8")
    check = {"task": "GameUi", "name": "I_MAIN"}
    graph = {"format": 2, "pages": {"page_main": {"check": check}}, "links": []}
    calibration = {"pages": {"page_main": {
        "original_check_sha256": hashlib.sha256(json.dumps(check, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "additional": {"all": [{"text": "式神录", "region": [1080, 640, 110, 55]},
                                {"text": "阴阳寮", "region": [515, 640, 120, 55]}]},
        "evidence": {"resolution": [1280, 720], "sha256": "a" * 64}}}}
    result = NavigationCompiler(graph, tmp_path).compile(calibrations=calibration)
    assert result["navigation"]["pages"]["page_main"]["when"]["any"][0] == {"res": "GameUi::I_MAIN"}
    assert result["recognition_repairs"][0]["approval"] == "unreviewed"
    calibration["pages"]["page_main"]["original_check_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="原识别条件已变化"):
        NavigationCompiler(graph, tmp_path).compile(calibrations=calibration)
