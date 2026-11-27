"""Single-OCR source boundaries and guarded native input, without live devices."""
import numpy as np
import pytest

from helpers import FakeClock, blank
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.programs import _requires_positive_visual
from onmyoji_agentflow.vision import ocr
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow


class Backend:
    def __init__(self, *results):
        self.results = iter(results)
        self.calls = []

    def __call__(self, image, **options):
        self.calls.append((image.copy(), options))
        return next(self.results), None


def box(text, score, x=1, y=1):
    return [[[x, y], [x + 4, y], [x + 4, y + 4], [x, y + 4]], text, score]


@pytest.mark.parametrize("text", ["预设", " 预 设 ", "预设额外文字"])
def test_horizontal_single_preserves_the_whole_string_and_accepts_equal_confidence(monkeypatch, text):
    backend = Backend([[text, .6]])
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: backend)
    assert ocr.read_single(blank(), [20, 620, 60, 80]) == text
    assert len(backend.calls) == 1
    image, options = backend.calls[0]
    assert image.shape == (80, 60, 3)
    assert options == {"use_det": False, "use_cls": False, "use_rec": True}


@pytest.mark.parametrize("score,expected", [(.6, ""), (.600001, "预设")])
def test_vertical_fallback_uses_strict_confidence_and_source_square_padding(monkeypatch, score, expected):
    backend = Backend([["bad", .59]], [box("预设", score), box("later", .99, y=30)])
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: backend)
    assert ocr.read_single(blank(), [20, 620, 60, 80]) == expected
    padded, options = backend.calls[1]
    assert padded.shape == (96, 96, 3)
    assert np.all(padded[80:, :] == 0) and np.all(padded[:, 60:] == 0)
    assert options["use_det"] is True


def test_vertical_filters_low_scores_then_uses_only_first_eligible_box_in_source_order(monkeypatch):
    backend = Backend([], [box("second", .99, x=20), box("first", .9), box("low", .59, y=0)])
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: backend)
    assert ocr.read_single(blank(), [20, 620, 60, 80]) == "first"


@pytest.mark.parametrize("region", [[0, 0, 0, 20], [-1, 0, 20, 20], [1270, 0, 20, 20],
                                    [0, 710, 20, 20], [True, 0, 20, 20]])
def test_invalid_roi_raises_before_using_the_model(monkeypatch, region):
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: pytest.fail("model must not be used"))
    with pytest.raises(ValueError, match="region|crop"):
        ocr.read_single(blank(), region)


@pytest.mark.parametrize("result", [[["预设", float("nan")]], [["预设", -1]], [["预设", 2]],
                                    [["预设", True]], [["预设", .9], ["another", .9]]])
def test_malformed_results_fail_instead_of_becoming_negative_evidence(monkeypatch, result):
    monkeypatch.setattr(ocr, "_get_single_engine", lambda: Backend(result))
    with pytest.raises(ValueError):
        ocr.read_single(blank(), [20, 620, 60, 80])


def raw(condition):
    return {"format": 1, "name": "single-ocr", "states": [{"id": "single", "when": condition,
        "do": [{"click": [20, 620, 80, 700], "recheck": True}, {"stop": "done"}]}]}


SINGLE = {"ocr_single": {"region": [20, 620, 60, 80], "equals": "预设", "score": .6}}


def test_native_single_is_exact_caches_only_one_frame_and_rechecks_before_input():
    frame, seen = blank(), []
    workflow = load_workflow(raw(SINGLE))
    runner = Runner(workflow, Controller(ReplayDevice([frame]), sleep=lambda _: None),
                    single_ocr_reader=lambda image, region, score: seen.append((region, score)) or "预设")
    assert runner._match(SINGLE, frame)
    assert runner._match(SINGLE, frame)
    assert len(seen) == 1
    assert not runner._match({"ocr_single": {"region": [20, 620, 60, 80], "equals": "预"}}, frame)
    assert len(seen) == 1
    values = iter(["预设", "预设额外文字"])
    device = ReplayDevice([frame, frame])
    result = Runner(workflow, Controller(device, sleep=lambda _: None), clock=FakeClock(),
                    single_ocr_reader=lambda *_: next(values)).run()
    assert result.status == "failed" and result.failure_kind == "recognition"
    assert not device.inputs


def test_unavailable_single_ocr_cannot_be_negated_to_authorize_a_click():
    def unavailable(*_):
        raise ocr.OcrUnavailable("no OCR")
    device = ReplayDevice([blank()])
    result = Runner(load_workflow(raw({"not": SINGLE})), Controller(device, sleep=lambda _: None),
                    clock=FakeClock(), single_ocr_reader=unavailable).run()
    assert result.status == "failed" and result.failure_kind == "recognition"
    assert not device.inputs
    assert _requires_positive_visual(SINGLE)
    assert not _requires_positive_visual({"not": SINGLE})


@pytest.mark.parametrize("spec", [
    {"region": [0, 0, 10, 10], "equals": ""},
    {"region": [0, 0, -10, 10], "equals": "预设"},
    {"region": [0, 0, 10, 10], "equals": "预设", "score": float("nan")},
    {"region": [0, 0, 10, 10], "equals": "预设", "callback": "not allowed"},
])
def test_single_condition_rejects_empty_or_unbounded_contracts(spec):
    with pytest.raises(WorkflowError, match="ocr_single"):
        load_workflow(raw({"ocr_single": spec}))


@pytest.mark.parametrize("readout, expected", [
    ("D1.O2：3S", 3755), ("005959", 3599), ("0:00:00", 0),
    ("01:60:00", -1), ("寄养剩余001230", -1), ("", -1),
])
def test_duration_read_requires_complete_time_and_distinguishes_zero(readout, expected):
    condition = {"ocr": "remaining", "mode": "duration_seconds", "var": "seconds", "test": "seconds >= -1"}
    body = raw(condition)
    body["inline_resources"] = {"remaining": {"type": "ocr", "mode": "Duration", "roi": [1140, 117, 100, 30]}}
    frame = blank()
    runner = Runner(load_workflow(body), Controller(ReplayDevice([frame])),
                    single_ocr_reader=lambda *_: readout)
    assert runner._match(condition, frame) == (expected != -1)
    assert runner.vars["seconds"] == expected


@pytest.mark.parametrize("readout, expected", [
    ("I / B", 7), ("3/3", 0), ("4/3", -1), ("0/0", -1), ("3", -1), ("3/5 1/2", -1),
])
def test_counter_remaining_requires_one_valid_pair(readout, expected):
    condition = {"ocr": "box", "mode": "counter_remaining", "var": "remaining", "test": "remaining >= -1"}
    body = raw(condition)
    body["inline_resources"] = {"box": {"type": "ocr", "mode": "DigitCounter", "roi": [654, 538, 179, 39]}}
    frame = blank()
    runner = Runner(load_workflow(body), Controller(ReplayDevice([frame])),
                    single_ocr_reader=lambda *_: readout)
    assert runner._match(condition, frame) == (expected != -1)
    assert runner.vars["remaining"] == expected


@pytest.mark.parametrize("texts,target,expected", [
    (["壹", "贰层"], "肆层", (1, None)),
    (["叁", "肆"], "壹层", (-1, None)),
    (["壹", "叁"], "贰层", (None, None)),
    (["肆", "贰"], "叁层", (None, None)),
    (["叁", "叁层"], "叁层", (None, None)),
    (["贰", "叁 层"], "叁层", (0, (155, 350))),
    (["错误"], "壹层", (None, None)),
])
def test_ordered_list_shows_a_unique_target_or_a_scroll_direction(texts, target, expected):
    from onmyoji_agentflow.vision.ocr import ordered_list_position
    labels = [[item + "层", item] for item in "壹贰叁肆"]
    rows = [(text, 155, 250 + index * 100) for index, text in enumerate(texts)]
    assert ordered_list_position(rows, labels, target) == expected


@pytest.mark.parametrize("readout, expected", [
    ("3时25分后可再次挑战", 12300),
    (" 0 时 5 分 后 可 ", 300),
    ("0时0分后可", 0),
    ("24时0分后可", 86400),
    ("25时10分后可", -1),
    ("103时10分后可", -1),
    ("3时60分后可", -1),
    ("再次挑战", -1),
    ("", -1),
])
def test_cn_hour_minute_read_parses_exact_countdown_and_distinguishes_zero(readout, expected):
    condition = {"ocr": "cd", "mode": "cn_hour_minute", "var": "seconds", "test": "seconds >= 0"}
    body = raw(condition)
    body["inline_resources"] = {"cd": {"type": "ocr", "mode": "Single", "roi": [578, 218, 172, 41]}}
    frame = blank()
    runner = Runner(load_workflow(body), Controller(ReplayDevice([frame])),
                    single_ocr_reader=lambda *_: readout)
    assert runner._match(condition, frame) == (expected != -1)
    assert runner.vars["seconds"] == expected


@pytest.mark.parametrize("readout, expected", [
    ("剩2次", 2),
    ("剩余 10 次", 10),
    ("剩0次", 0),
    ("无次数", -1),
    ("", -1),
])
def test_remaining_times_read_parses_badge_and_distinguishes_zero(readout, expected):
    condition = {"ocr": "left", "mode": "remaining_times", "var": "left_count", "test": "left_count >= 0"}
    body = raw(condition)
    body["inline_resources"] = {"left": {"type": "ocr", "mode": "Single", "roi": [1172, 684, 100, 31]}}
    frame = blank()
    runner = Runner(load_workflow(body), Controller(ReplayDevice([frame])),
                    single_ocr_reader=lambda *_: readout)
    assert runner._match(condition, frame) == (expected != -1)
    assert runner.vars["left_count"] == expected
