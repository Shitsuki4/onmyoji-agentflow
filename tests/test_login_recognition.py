"""Login-specific caller overrides use bounded native recognition only."""
import copy

import cv2
import numpy as np
import pytest

from helpers import FakeClock, blank
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.vision.ocr import FullOcrArea
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow


def raw(condition, **extra):
    return {"format": 1, "name": "login-recognition", "states": [
        {"id": "hit", "when": condition, "do": [{"click_found": True, "use_match_size": True,
         "recheck": True, "delay": 0}, {"stop": "done"}]}], **extra}


def test_condition_scale_override_changes_only_one_matcher_and_keeps_scaled_click_box(tmp_path):
    template = np.random.default_rng(110).integers(0, 255, (40, 50, 3), dtype=np.uint8)
    path = tmp_path / "mail.png"
    cv2.imencode(".png", template)[1].tofile(str(path))
    frame = blank()
    frame[100:132, 200:240] = cv2.resize(template, (40, 32))
    resource = {"type": "image", "path": str(path), "roi": [180, 80, 100, 100], "threshold": .99,
                "method": "Template matching"}
    condition = {"res": "mail", "scale_range": [.8, .8]}
    wf = load_workflow(raw(condition, inline_resources={"mail": resource}))
    before = copy.deepcopy(wf.resources["mail"])
    device = ReplayDevice([frame])
    runner = Runner(wf, Controller(device, sleep=lambda _: None), clock=FakeClock())
    assert not runner._match({"res": "mail"}, frame)
    assert runner._match(condition, frame) and runner._found_box == (200, 100, 40, 32)
    result = runner.run()
    assert result.status == "success" and len(device.inputs) == 1
    _, x, y = device.inputs[0]
    assert 200 <= x <= 240 and 100 <= y <= 132
    assert wf.resources["mail"] == before


@pytest.mark.parametrize("value", [None, [], [.8], [1.2, .8], [0, 1], [.8, 1.2, 0],
                                    [True, 1.2], [.8, float("nan")], [.1, 10, .00001]])
def test_invalid_scale_ranges_are_rejected_before_input(value):
    with pytest.raises(WorkflowError, match="scale_range"):
        load_workflow(raw({"res": "mail", "scale_range": value}, inline_resources={
            "mail": {"type": "image", "path": "unused.png"}}))


@pytest.mark.parametrize("condition", [{"text": "mail"}, {"expr": "True"}, {"ocr": "number", "var": "n"}])
def test_scale_override_cannot_be_silently_ignored_by_other_conditions(condition):
    with pytest.raises(WorkflowError, match="scale_range"):
        load_workflow(raw({**condition, "scale_range": [.8, 1.1]}))


def test_dynamic_single_keyword_is_literal_and_tracks_variable_rebinding_per_frame():
    cond = {"ocr_single": {"region": [20, 20, 100, 30], "equals_var": "character"}}
    wf = load_workflow(raw(cond, vars={"character": "角色.*"}))
    seen = []
    runner = Runner(wf, Controller(ReplayDevice([blank()]), sleep=lambda _: None),
                    single_ocr_reader=lambda *args: seen.append(args) or "角色.*")
    runner.vars = {"character": "角色.*"}
    frame = blank()
    assert runner._match(cond, frame)
    runner.vars["character"] = "角色"
    assert not runner._match(cond, frame)
    assert len(seen) == 1  # Recognition is cached; current literal binding is not.


def test_dynamic_full_keyword_is_cached_by_value_and_can_bind_a_parameter():
    cond = {"ocr_full": {"region": [20, 20, 100, 30], "keyword_var": "character",
                          "evidence": "complete_keyword"}}
    wf = load_workflow(raw(cond, params={"character": {"default": "甲"}}))
    seen = []
    def read(image, region, keyword, score):
        seen.append(keyword)
        return FullOcrArea((25, 25, 30, 10), keyword_complete=True)
    runner = Runner(wf, Controller(ReplayDevice([blank()])), full_ocr_reader=read)
    frame = blank()
    assert runner._match(cond, frame) and runner._match(cond, frame)
    runner.params["character"] = "乙[.*]"
    assert runner._match(cond, frame) and seen == ["甲", "乙[.*]"]


@pytest.mark.parametrize("key", ["ocr_single", "ocr_full"])
@pytest.mark.parametrize("value", ["", None, 1, False, ["角色"]])
def test_empty_or_nonstring_dynamic_keyword_cannot_authorize_negated_input(key, value):
    text_key = "equals" if key == "ocr_single" else "keyword"
    cond = {key: {"region": [20, 20, 100, 30], text_key + "_var": "character"}}
    wf = load_workflow(raw({"not": cond}, vars={"character": value}))
    device = ReplayDevice([blank()])
    result = Runner(wf, Controller(device, sleep=lambda _: None), clock=FakeClock(),
                    single_ocr_reader=lambda *_: pytest.fail("must check binding first"),
                    full_ocr_reader=lambda *_: pytest.fail("must check binding first")).run()
    assert result.status == "failed" and result.failure_kind == "workflow_error" and not device.inputs
    assert "OCR literal keyword must be a nonempty string" in result.reason


@pytest.mark.parametrize("key,text_key", [("ocr_single", "equals"), ("ocr_full", "keyword")])
def test_dynamic_keyword_requires_one_declared_binding(key, text_key):
    for fields in ({text_key + "_var": "missing"}, {text_key: "甲", text_key + "_var": "character"}):
        with pytest.raises(WorkflowError, match=key):
            load_workflow(raw({key: {"region": [0, 0, 100, 30], **fields}}, vars={"character": "甲"}))
