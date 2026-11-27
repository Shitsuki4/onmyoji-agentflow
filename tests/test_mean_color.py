import numpy as np
import pytest

from helpers import FakeClock, blank
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import WorkflowError
from onmyoji_agentflow.vision.colors import mean_rgb_similar
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow


def test_mean_rgb_uses_source_truncation_and_native_bgr_channel_order():
    image = np.array([[[187, 208, 225], [188, 209, 224]]], dtype=np.uint8)
    assert mean_rgb_similar(image, [0, 0, 2, 1], [224.9, 208.3, 187.4], 0)


def test_tolerance_is_source_positive_plus_negative_metric_not_per_channel_max():
    image = np.zeros((10, 10, 3), np.uint8)
    image[:] = (187, 202, 230)
    assert not mean_rgb_similar(image, [0, 0, 10, 10], [224.9, 208.3, 187.4], 10)
    assert mean_rgb_similar(image, [0, 0, 10, 10], [224.9, 208.3, 187.4], 12)


def test_region_mean_can_differ_from_all_single_point_samples():
    image = np.zeros((2, 2, 3), np.uint8)
    image[0] = (100, 100, 100)
    image[1] = (200, 200, 200)
    assert mean_rgb_similar(image, [0, 0, 2, 2], [150, 150, 150], 0)


def test_invalid_region_cannot_be_negated_into_an_input_permission():
    raw = {"format": 1, "name": "invalid-mean", "states": [{"id": "never_click", "when": {"not": {
        "mean_color": {"region": [1279, 719, 5, 5], "rgb": [0, 0, 0]}}}, "do": [{"click": [10, 10, 20, 20]}]}]}
    device = ReplayDevice([blank()])
    result = Runner(load_workflow(raw), Controller(device, sleep=lambda _: None), clock=FakeClock()).run()
    assert result.status == "failed" and not device.inputs and result.actions == 0


@pytest.mark.parametrize("spec", [
    {"region": [0, 0, 0, 5], "rgb": [0, 0, 0]},
    {"region": [0, 0, 5, 5], "rgb": [256, 0, 0]},
    {"region": [0, 0, 5, 5], "rgb": [0, 0, 0], "tolerance": float("nan")},
    {"region": [0, 0, 5, 5], "rgb": [0, 0, 0], "callback": "hidden"},
])
def test_mean_observation_is_a_closed_bounded_data_contract(spec):
    with pytest.raises(WorkflowError):
        load_workflow({"format": 1, "name": "bad", "states": [{"id": "probe", "when": {"mean_color": spec}, "do": [{"wait": 1}]}]})
