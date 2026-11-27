import pytest

from onmyoji_agentflow.programs import _requires_positive_visual
from test_program_pipeline import app, job, reply


@pytest.mark.parametrize("condition", [
    {"any": [{"expr": "True"}, {"text": "准备"}]},
    {"not": {"text": "购买"}},
    {"any": [{"text": "准备"}, {"all": [{"expr": "True"}, {"not": {"text": "购买"}}]}]},
    {"all": [{"expr": "True"}, {"any": [{"text": "准备"}, {"expr": "True"}]}]},
])
def test_visual_leaf_in_optional_or_negated_branch_is_not_a_guard(condition):
    assert not _requires_positive_visual(condition)


@pytest.mark.parametrize("condition", [
    {"text": "准备"},
    {"all": [{"expr": "True"}, {"text": "准备"}]},
    {"any": [{"text": "准备"}, {"colors": [[1, 1, "#ffffff"]]}]},
    {"all": [{"any": [{"expr": "True"}, {"text": "可选"}]}, {"text": "必须识别"}]},
])
def test_visual_requirement_is_checked_across_boolean_paths(condition):
    assert _requires_positive_visual(condition)


@pytest.mark.parametrize("action", [{"click": [1, 1, 2, 2]}, {"select_foster": {"max_pages": 1}},
    {"select_foster_unit": {"required_text": ["白达摩"]}}, {"scan_tasks": {"scope": "daily"}}])
def test_external_proposals_cannot_use_expression_branch_to_bypass_visual_gate(app, action):
    proposal = reply()
    proposal["workflow"]["states"][0].update({
        "when": {"any": [{"expr": "True"}, {"text": "准备"}]}, "do": [action]})
    result = app.programs.propose(job(app)["id"], proposal)
    assert result["status"] == "blocked" and "正向画面" in result["message"]
    assert not app.store.query("SELECT * FROM changes")
