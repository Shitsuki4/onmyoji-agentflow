"""Exercise pinned pet-feeding cost and receipt guards off device."""
from pathlib import Path

import pytest

from helpers import FakeClock, blank
from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.oas_pets import compile_pets_candidate
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.workflow import engine
from onmyoji_agentflow.workflow.schema import load_workflow
from test_navigation_family import converted, inert_source


@pytest.fixture(scope="module")
def workflow(inert_source, converted):
    stage, folder = converted
    convert_task(inert_source / "tasks/Pets", folder, "Pets")
    packet = compile_pets_candidate(inert_source, folder)
    return load_workflow(packet["workflow"], [stage / "resources"])


@pytest.fixture
def frames(workflow, monkeypatch):
    aliases = {Path(resource["path"]).name: key for key, resource in workflow.resources.items()
               if "::" in key and resource["type"] == "image"}
    contains = {}

    def frame(*visible):
        key = len(contains) + 20
        contains[key] = visible
        return blank(key)

    def match(image, path, *_args, **_kwargs):
        present = aliases[Path(path).name] in contains[int(image[0, 0, 0])]
        return present, float(present), (200, 100, 40, 32)

    monkeypatch.setattr(engine, "match_template", match)
    return frame


def run(workflow, frames, *, price, max_seconds=8, advance_on_input=True):
    device = ReplayDevice(frames, advance_on_input=advance_on_input)
    result = engine.Runner(workflow, Controller(device, sleep=lambda _: None), clock=FakeClock(.05),
                           initial_vars={"pet_phase": "cost"},
                           single_ocr_reader=price if callable(price) else lambda *_: str(price),
                           max_seconds=max_seconds).run()
    return result, device.inputs


def test_already_fed_is_verified_after_return_to_courtyard(workflow, frames):
    feed = frames("Pets::I_PET_FEED", "Pets::I_PET_EXIT")
    court = frames("GameUi::I_CHECK_MAIN")
    result, inputs = run(workflow, [feed, court], price=0)
    assert result.status == "success", result.summary()
    assert result.summary()["business_result"] == "already_done"
    assert result.summary()["business_ok"] and len(inputs) == 1
    _, x, y = inputs[0]
    assert 30 <= x <= 69 and 25 <= y <= 58


def test_positive_cost_never_repeats_feed_while_receipt_is_missing(workflow, frames):
    feed = frames("Pets::I_PET_FEED")
    result, inputs = run(workflow, [feed], price=6)
    assert not result.summary()["business_ok"] and len(inputs) == 1
    _, x, y = inputs[0]
    assert 899 <= x <= 978 and 511 <= y <= 579


def test_unknown_cost_keeps_feed_unattempted(workflow, frames):
    result, inputs = run(workflow, [frames("Pets::I_PET_FEED")], price=None)
    assert not result.summary()["business_ok"]
    assert not result.variables["pet_feed_attempted"] and inputs == []


@pytest.mark.parametrize("quotes", [("6", "12"), ("6", "6", "12"), ("0", "12"), ("6", "6", "12体力")])
def test_changing_or_ambiguous_quote_does_not_feed_or_report_already_done(workflow, frames, quotes):
    values = [frames("Pets::I_PET_FEED") for _ in quotes]
    by_frame = {int(frame[0, 0, 0]): quote for frame, quote in zip(values, quotes)}
    result, inputs = run(workflow, values, price=lambda image, *_: by_frame[int(image[0, 0, 0])],
                         advance_on_input=False)
    assert result.status == "failed" and not result.business_ok
    assert not result.variables["pet_feed_attempted"] and not inputs


def test_zero_then_twelve_quote_cannot_report_already_done(workflow, frames):
    """The live regression shape: a 0 AP preview followed by a 12 AP recheck."""
    values = [frames("Pets::I_PET_FEED") for _ in range(2)]
    by_frame = {int(frame[0, 0, 0]): quote for frame, quote in zip(values, ("0", "12"))}
    result, inputs = run(workflow, values, price=lambda image, *_: by_frame[int(image[0, 0, 0])],
                         advance_on_input=False)
    assert result.failed_state == "pet_quote_changed" and not result.business_ok
    assert result.variables["pet_ap_cost"] == 0 and result.variables["pet_ap_seen"] == 12
    assert not result.variables["pet_feed_attempted"] and inputs == []


def test_quote_roi_keeps_a_margin_around_the_digit(workflow):
    ap = workflow.resources["Pets::O_PET_FEED_AP"]["roi"]
    quote = workflow.resources["Pets::O_PET_FEED_AP_QUOTE"]["roi"]
    assert quote == [ap[0] - 2, ap[1] - 2, ap[2], ap[3] + 4]


def test_courtyard_costume_binding_for_goto_main_and_pets(inert_source, converted):
    from onmyoji_agentflow.convert.oas_goto_main import compile_goto_main_candidate

    stage, folder = converted
    convert_task(inert_source / "tasks/Pets", folder, "Pets")
    convert_task(inert_source / "tasks/Component/Costume", folder, "Component_Costume")
    for costume, expected_len in ((1, 1), (13, 1), (17, 3)):
        gm = compile_goto_main_candidate(inert_source, folder, courtyard_costume=costume)["workflow"]
        pet = compile_pets_candidate(inert_source, folder, courtyard_costume=costume)["workflow"]
        assert len(gm["oas_courtyard_costume_contract"]["source_assets"]["GameUi::I_CHECK_MAIN"]) == expected_len
        assert len(pet["oas_courtyard_costume_contract"]["source_assets"]["Pets::I_PET_HOUSE"]) == expected_len
        load_workflow(gm, [stage / "resources"])
        load_workflow(pet, [stage / "resources"])
    with pytest.raises(ValueError, match="0 to 17"):
        compile_pets_candidate(inert_source, folder, courtyard_costume=18)
