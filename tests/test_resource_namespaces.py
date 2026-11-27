from pathlib import Path

import pytest

from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.workflow.schema import load_workflow, resolve_resources
from onmyoji_agentflow.yamlio import dump_yaml


def resources(tmp_path):
    for task, x in (("First", 10), ("Second", 30)):
        (tmp_path / (task + ".yaml")).write_text(dump_yaml({"resources": {
            "I_SHARED": {"type": "colors", "points": [[x, 20, "#123456"]]},
            task.upper(): {"type": "click", "rect": [x, 10, x + 5, 15]}}}), encoding="utf-8")
    return {"resources": ["First.yaml", "Second.yaml"]}


def test_legacy_short_names_remain_unchanged(tmp_path):
    raw = resources(tmp_path)
    assert resolve_resources(raw, None, [tmp_path])["I_SHARED"]["points"][0][0] == 30


def test_explicit_namespaces_never_silently_overwrite_a_resource(tmp_path):
    raw = {**resources(tmp_path), "resource_namespaces": True}
    result = resolve_resources(raw, None, [tmp_path])
    assert "I_SHARED" not in result
    assert result["First::I_SHARED"]["points"][0][0] == 10
    assert result["Second::I_SHARED"]["points"][0][0] == 30
    assert result["FIRST"] == result["First::FIRST"]
    raw.update(format=1, name="namespaced", states=[{"id": "click", "when": {"res": "I_SHARED"},
        "do": [{"click": "First::FIRST"}]}])
    with pytest.raises(WorkflowError, match="未知资源"):
        load_workflow(raw, [tmp_path])
    raw["states"][0]["when"]["res"] = "First::I_SHARED"
    assert load_workflow(raw, [tmp_path]).states


def test_inline_resources_cannot_shadow_qualified_source(tmp_path):
    raw = {**resources(tmp_path), "resource_namespaces": True,
           "inline_resources": {"First::I_SHARED": {"type": "click", "rect": [0, 0, 1, 1]}}}
    with pytest.raises(WorkflowError, match="不能覆盖"):
        resolve_resources(raw, None, [tmp_path])
