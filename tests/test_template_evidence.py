import numpy as np
import pytest

from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.vision.template import match_template
from onmyoji_agentflow.workflow.schema import load_workflow


def test_per_channel_constant_template_is_not_visual_evidence():
    template = np.zeros((5, 6, 3), np.uint8)
    template[:] = (40, 80, 120)
    image = np.random.default_rng(5).integers(0, 255, (50, 60, 3), dtype=np.uint8)
    assert match_template(image, template)[0] is False


def test_nonfinite_scores_are_never_positive_matches(monkeypatch):
    template = np.arange(27, dtype=np.uint8).reshape(3, 3, 3)
    image = np.zeros((10, 10, 3), np.uint8)
    monkeypatch.setattr("onmyoji_agentflow.vision.template.cv2.matchTemplate",
                        lambda *args: np.array([[np.nan, np.inf, -.5]], dtype=np.float32))
    assert match_template(image, template)[0] is False


def test_supported_matching_still_finds_translated_image_box():
    template = np.random.default_rng(8).integers(0, 255, (8, 7, 3), dtype=np.uint8)
    image = np.zeros((50, 60, 3), np.uint8)
    image[15:23, 20:27] = template
    matched, score, box = match_template(image, template)
    assert matched and score > .99 and box == (20, 15, 7, 8)


def test_unimplemented_source_image_method_does_not_silently_use_plain_matching():
    raw = {"format": 1, "name": "wrong-method", "inline_resources": {
        "asset": {"type": "image", "method": "Custom untranslated matcher", "path": "unused.png"}},
        "states": [{"id": "match", "when": {"res": "asset"}, "do": [{"wait": 1}]}]}
    with pytest.raises(WorkflowError, match="匹配方法尚未转换"):
        load_workflow(raw)
