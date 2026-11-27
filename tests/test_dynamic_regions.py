"""Full OCR and bounded observation geometry; no upstream execution or devices."""
import copy

import cv2
import numpy as np
import pytest

from helpers import FakeClock, blank
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.programs import _requires_positive_visual
from onmyoji_agentflow.vision import ocr
from onmyoji_agentflow.vision.regions import project_region
from onmyoji_agentflow.vision.template import match_template
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow


def row(text, score=.6, x=4, y=6, w=20, h=10):
    return [[[x, y], [x+w, y], [x+w, y+h], [x, y+h]], text, score]


class Backend:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def __call__(self, image, **options):
        self.calls.append((image.copy(), options))
        return self.rows, None


def test_full_ocr_keeps_substrings_identity_threshold_and_source_padding(monkeypatch):
    backend = Backend([row("前缀金币50%后缀"), row("金币50%", .599, y=0)])
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: backend)
    assert ocr.read_full(blank(), [100, 200, 160, 80], "金币50%") == (104, 206, 20, 10)
    image, options = backend.calls[0]
    assert image.shape == (192, 192, 3)
    assert options == {"use_det": True, "use_cls": False, "use_rec": True}
    assert np.all(image[80:] == 0) and np.all(image[:, 160:] == 0)


def test_full_ocr_preserves_source_filter_and_non_union_multi_area_merge(monkeypatch):
    backend = Backend([row("经验", .9, x=4, y=30, w=20), row("经验", .9, x=50, y=6, w=30, h=12)])
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: backend)
    # Source merges widths/heights as maxima, not right/bottom coordinates.
    assert ocr.read_full(blank(), [100, 200, 160, 80], "经验") == (104, 206, 30, 12)


@pytest.mark.parametrize("rows,expected", [
    ([row("御灵队伍")], (0, 0, 0, 0)),
    ([row("御灵"), row("御灵队伍", y=30)], (104, 206, 20, 10)),
    ([row("御灵"), row("御灵", y=30)], (0, 0, 0, 0)),
])
def test_full_unique_equals_keeps_one_exact_box(monkeypatch, rows, expected):
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: Backend(rows))
    assert ocr.read_full(blank(), [100, 200, 160, 80], "御灵", selection="unique_equals") == expected


def test_full_first_contains_returns_first_matching_box_without_merging(monkeypatch):
    rows = [row("完成", .9, x=4, y=30, w=20, h=10), row("任务完成", .9, x=50, y=6, w=30, h=12)]
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: Backend(rows))
    area = ocr.read_full(blank(), [100, 200, 160, 80], "完成", selection="first_contains")
    assert area == (150, 206, 30, 12) and area.keyword_complete


@pytest.mark.parametrize("rows,keyword,expected", [
    ([row("战"), row("斗", x=40)], "战斗", (0, 0, 0, 0)),
    ([row("战")], "战斗胜利", (104, 206, 20, 10)),  # source partial-character fallback
    ([row("unrelated")], "金币", (0, 0, 0, 0)),
    ([], "金币", (0, 0, 0, 0)),
])
def test_full_filter_does_not_invent_joined_words_or_fix_partial_fallback(monkeypatch, rows, keyword, expected):
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: Backend(rows))
    assert ocr.read_full(blank(), [100, 200, 160, 80], keyword) == expected


def test_full_provenance_distinguishes_source_partial_fallback_from_complete_keyword(monkeypatch):
    backend = Backend([row("战")])
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: backend)
    partial = ocr.read_full(blank(), [100, 200, 160, 80], "战斗胜利")
    assert partial != (0, 0, 0, 0) and not partial.keyword_complete
    backend.rows = [row("战斗胜利")]
    assert ocr.read_full(blank(), [100, 200, 160, 80], "战斗胜利").keyword_complete
    for result, expected in ((partial, False), (ocr.FullOcrArea(partial, keyword_complete=True), True)):
        condition = {"ocr_full": {**FULL["ocr_full"], "evidence": "complete_keyword"}}
        runner = Runner(load_workflow(raw_capture(condition)), Controller(ReplayDevice([blank()])), full_ocr_reader=lambda *_: result)
        assert runner._match(condition, blank()) is expected


def test_missing_provenance_cannot_be_negated_to_authorize_input():
    condition = {"ocr_full": {**FULL["ocr_full"], "evidence": "complete_keyword"}}
    raw = {"format": 1, "name": "untyped-full", "states": [
        {"id": "negative", "when": {"not": condition}, "do": [{"click": [1, 1, 2, 2]}]}]}
    device = ReplayDevice([blank()])
    result = Runner(load_workflow(raw), Controller(device), clock=FakeClock(), full_ocr_reader=lambda *_: (500, 180, 250, 10)).run()
    assert result.status == "failed" and not device.inputs


@pytest.mark.parametrize("rows", [[[[[1, 2]], "text", .9]], [row("x", float("nan"))],
                                 [row("x", True)], [row("x", "0.9")], [row(123)]])
def test_full_malformed_model_output_is_not_negative_evidence(monkeypatch, rows):
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: Backend(rows))
    with pytest.raises(ValueError):
        ocr.read_full(blank(), [100, 200, 160, 80], "text")


FULL = {"ocr_full": {"region": [400, 100, 400, 400], "keyword": "经验"}}
NAMES = ["bx", "by", "bw", "bh"]
CAPTURE = {"capture_region": {"vars": NAMES, "rect": ["match_x+match_w+10", "match_y-10", 80, "match_h+20"]}}


def raw_capture(condition=FULL):
    return {"format": 1, "name": "capture", "vars": dict.fromkeys(NAMES, 0),
            "states": [{"id": "capture", "when": condition, "do": [CAPTURE, {"stop": "captured"}]}]}


def test_full_ocr_caches_the_box_per_frame_including_sentinel_comparison():
    frame, calls = blank(), []
    workflow = load_workflow(raw_capture())
    runner = Runner(workflow, Controller(ReplayDevice([frame])), full_ocr_reader=lambda *_: calls.append(1) or (500, 180, 250, 10))
    sentinel = copy.deepcopy(FULL)
    sentinel["ocr_full"]["box_equals"] = [432, 143, 325, 21]
    assert not runner._match(sentinel, frame)
    assert runner._match(FULL, frame)
    assert runner._found_box == (500, 180, 250, 10)
    assert len(calls) == 1
    assert runner._match(FULL, frame.copy())
    assert len(calls) == 2
    assert _requires_positive_visual(FULL)
    assert not _requires_positive_visual({"not": FULL})


def test_capture_is_read_only_truncates_after_projection_and_has_no_business_receipt():
    device = ReplayDevice([blank()])
    result = Runner(load_workflow(raw_capture()), Controller(device, sleep=lambda _: None), clock=FakeClock(),
                    full_ocr_reader=lambda *_: (500.5, 180.6, 249.8, 10.6)).run()
    assert result.status == "success", result.summary()
    assert [result.variables[n] for n in NAMES] == [760, 170, 80, 30]
    assert not device.inputs and result.actions == 0 and not result.business_ok
    assert project_region((381, 180, 35, 45), ["match_x+match_w//2+364", "match_y", 80, "match_h"], blank()) == (762, 180, 80, 45)


def test_projected_click_uses_the_rechecked_anchor():
    raw = raw_capture()
    raw["states"][0]["do"] = [{"click_found": True, "projected_rect": [978, "match_y", 20, 2], "recheck": True},
                              {"stop": "done"}]
    first, second = blank(30), blank(31)
    device = ReplayDevice([first, second])
    controller = Controller(device, sleep=lambda _: None)
    result = Runner(load_workflow(raw), controller, clock=FakeClock(),
                    full_ocr_reader=lambda frame, *_: (500, 180 if frame[0, 0, 0] == 30 else 249, 80, 24)).run()
    assert result.status == "success", result.summary()
    assert controller.ops[0]["rect"] == [978, 249, 998, 251]


@pytest.mark.parametrize("condition", [{"expr": "True"}, {"not": FULL}, {"any": [FULL, {"expr": "True"}]}])
def test_capture_requires_a_box_on_every_successful_condition_path(condition):
    with pytest.raises(WorkflowError, match="capture_region"):
        load_workflow(raw_capture(condition))


@pytest.mark.parametrize("rect", [["__import__('os')", 0, 80, 20], ["match_x.attr", 0, 80, 20],
                                 ["elapsed_ms", 0, 80, 20], [True, 0, 80, 20]])
def test_capture_rejects_calls_attributes_external_variables_and_booleans(rect):
    raw = raw_capture()
    raw["states"][0]["do"] = [{"capture_region": {"vars": NAMES, "rect": rect}}]
    with pytest.raises(WorkflowError):
        load_workflow(raw)


@pytest.mark.parametrize("area", [(1200, 180, 50, 10), (500, 5, 250, 5), (500, 180, -1, 20), (True, 0, 0, 0)])
def test_invalid_observed_or_projected_area_fails_without_mutating_region(area):
    device = ReplayDevice([blank()])
    result = Runner(load_workflow(raw_capture()), Controller(device, sleep=lambda _: None), clock=FakeClock(),
                    full_ocr_reader=lambda *_: area).run()
    assert result.status == "failed" and not device.inputs
    assert [result.variables[n] for n in NAMES] == [0, 0, 0, 0]


def test_dynamic_roi_is_exact_and_rechecked_before_a_switch_click(tmp_path):
    patch = np.random.default_rng(812).integers(0, 255, (10, 10, 3), np.uint8)
    path = tmp_path / "switch.png"
    assert cv2.imwrite(str(path), patch)
    frame = blank()
    frame[183:193, 780:790] = patch
    raw = {"format": 1, "name": "switch", "vars": dict(zip(NAMES, [760, 170, 80, 30])),
        "inline_resources": {"switch": {"type": "image", "path": str(path), "roi": [0, 0, 10, 10], "roi_expand": 32}},
        "states": [{"id": "switch", "when": {"res": "switch", "region_vars": NAMES},
                    "do": [{"click_found": True, "use_match_size": True, "recheck": True}, {"stop": "done"}]}]}
    device = ReplayDevice([frame, blank()])
    result = Runner(load_workflow(raw), Controller(device, sleep=lambda _: None), clock=FakeClock()).run()
    assert result.failure_kind == "recognition" and not device.inputs
    # A too-small dynamic ROI cannot grow to discover a neighboring row.
    assert not match_template(frame, patch, (780, 183, 2, 2), strict_roi=True)[0]
    runner = Runner(load_workflow(raw), Controller(ReplayDevice([frame])))
    runner.vars = dict(zip(NAMES, [760, 170, 80, 30]))
    assert runner._match(raw["states"][0]["when"], frame)
    assert runner._found_box == (780, 183, 10, 10)
    runner.vars["bw"] = 5000
    with pytest.raises(WorkflowError, match="outside"):
        runner._match({"not": raw["states"][0]["when"]}, frame)


def test_unavailable_full_ocr_cannot_authorize_negated_input():
    def unavailable(*_):
        raise ocr.OcrUnavailable("missing OCR")
    raw = {"format": 1, "name": "full-unavailable", "states": [
        {"id": "negated", "when": {"not": FULL}, "do": [{"click": [1, 1, 2, 2]}]}]}
    device = ReplayDevice([blank()])
    result = Runner(load_workflow(raw), Controller(device), clock=FakeClock(), full_ocr_reader=unavailable).run()
    assert result.failure_kind == "recognition" and not device.inputs
