"""Synthetic frames prove control flow only; they are never installed as real replay coverage."""
from pathlib import Path

import pytest

from helpers import FakeClock, blank, fake_text_reader, frame_for, paint_condition, register_texts
from onmyoji_agentflow.convert.recipes import Builder, known_recipe
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.ledger import ResourceBudget
from onmyoji_agentflow.store import Store
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.workflow.schema import bundled_dir


class SyntheticBuilder(Builder):
    def asset(self, task, name):
        assets = self.raw.setdefault("inline_resources", {})
        if name not in assets:
            n = len(assets) + 1
            if name.startswith("S_"):
                spec = {"type": "swipe", "from": [100, 100, 120, 120], "to": [200, 200, 220, 220]}
            elif name.startswith("O_"):
                spec = {"type": "ocr", "roi": [10, 10, 20, 20]}
            elif name.startswith("C_"):
                spec = {"type": "click", "rect": [500, 500, 520, 520]}
            else:
                spec = {"type": "colors", "points": [[n * 5, 10, "#ff0000"]], "front": [500, 200, 50, 40]}
            assets[name] = spec
        return assets[name]


def build(kind):
    builder = SyntheticBuilder({"workflow": "recipe", "scope_description": "test scope"}, Path("unused"))
    return load_workflow(getattr(builder, kind)())


def run(wf, frames, **kwargs):
    device = ReplayDevice(frames)
    result = Runner(wf, Controller(device, sleep=lambda _: None), clock=FakeClock(step=0.5),
                    text_reader=fake_text_reader, **kwargs).run()
    return result, device


def test_source_fingerprint_drift_never_reuses_a_recipe():
    assert known_recipe({"id": "oas:RichMan#medal_blue", "fingerprint": "changed"}, Path("nonexistent")) is None


@pytest.mark.parametrize("kind,claim", [("store_sign", "claim_store_sign"),
    ("friend_love", "collect_friend_points"), ("task_rewards", "claim_task_rewards")])
def test_reward_task_requires_positive_receipt_and_never_claims_twice(kind, claim):
    wf = build(kind)
    # A static button after the first input is not a second authorisation or a receipt.
    result, device = run(wf, [frame_for(wf, claim), frame_for(wf, claim)])
    assert not result.business_ok and len(device.inputs) == 1
    result, device = run(wf, [frame_for(wf, claim), frame_for(wf, "reward_verified")])
    assert result.business_ok and len(device.inputs) == 1


def purchase_frame(wf, price="180", currency=None):
    image = blank()
    texts = []
    state = next(state for state in wf.states if state["id"] == "confirm_medal_purchase")
    paint_condition(image, state["when"], wf.resources, texts)
    if currency:
        paint_condition(image, {"res": currency}, wf.resources)
    return register_texts(image, [(price, 640, 520)])


@pytest.mark.parametrize("currency", ["I_BUY_RMB", "I_BUY_JADE"])
def test_foreign_currency_wins_even_when_product_and_price_also_match(currency):
    wf = build("medal_blue")
    confirmations = []
    result, device = run(wf, [purchase_frame(wf, currency=currency)], params={"enabled": True},
                         initial_vars={"selected": 1}, confirm=lambda *args: confirmations.append(args) or True)
    assert result.business_result == "blocked" and not device.inputs and not confirmations


def test_price_mismatch_and_refused_confirmation_do_not_purchase():
    wf = build("medal_blue")
    result, device = run(wf, [purchase_frame(wf, price="200")], params={"enabled": True},
                         initial_vars={"selected": 1}, confirm=lambda *args: True)
    assert not result.business_ok and not device.inputs
    result, device = run(wf, [purchase_frame(wf)], params={"enabled": True},
                         initial_vars={"selected": 1}, confirm=lambda *args: False)
    assert result.failure_kind == "confirm_denied" and not device.inputs


def test_purchase_budget_is_charged_once_and_requires_real_success_screen(tmp_path):
    wf = build("medal_blue")
    store = Store(tmp_path / "budget.db")
    budget = ResourceBudget(store, limits={"medal": {"daily_limit": 180}})

    def authorize(state, action, variables):
        return budget.authorize(action["cost"]) if action.get("cost") else None

    result, device = run(wf, [purchase_frame(wf), purchase_frame(wf), frame_for(wf, "purchase_receipt_verified")],
        params={"enabled": True}, initial_vars={"selected": 1}, confirm=lambda *args: True, before_input=authorize)
    assert result.business_ok and len(device.inputs) == 1
    assert store.resource_totals("default", budget.period())["medal"]["used"] == 180
    result, device = run(wf, [purchase_frame(wf)], params={"enabled": True},
        initial_vars={"selected": 1}, confirm=lambda *args: True, before_input=authorize)
    assert result.failure_kind == "budget" and not device.inputs


def test_screen_changed_while_waiting_for_purchase_confirmation_never_clicks_or_charges(tmp_path):
    wf = build("medal_blue")
    store = Store(tmp_path / "budget.db")
    budget = ResourceBudget(store, limits={"medal": {"daily_limit": 180}})
    result, device = run(wf, [purchase_frame(wf), purchase_frame(wf, currency="I_BUY_JADE")],
        params={"enabled": True}, initial_vars={"selected": 1}, confirm=lambda *args: True,
        before_input=lambda state, action, variables: budget.authorize(action["cost"]))
    assert result.failure_kind == "recognition" and not device.inputs
    assert not store.resource_totals("default", budget.period())


def test_weekly_purchase_is_disabled_until_account_profile_explicitly_enables_it():
    wf = build("medal_black")
    result, device = run(wf, [purchase_frame(wf, price="480")])
    assert result.business_result == "skipped" and not device.inputs


def test_blue_summon_draws_at_most_once_and_requires_a_result():
    wf = build("one_summon")
    canvas = frame_for(wf, "draw_stroke_1")
    # The original canvas repeating must not draw a second line or report success.
    result, device = run(wf, [canvas, canvas], params={"enabled": True},
                         initial_vars={"selected": 1}, confirm=lambda *args: True)
    assert not result.business_ok and len(device.inputs) == 1 and device.inputs[0][0] == "swipe"
    result, device = run(wf, [canvas, canvas, frame_for(wf, "single_draw_receipt")],
                         params={"enabled": True}, initial_vars={"selected": 1}, confirm=lambda *args: True)
    assert result.business_ok and len(device.inputs) == 1


def test_blue_summon_ticket_ocr_failure_stops_without_spending():
    wf = build("one_summon")
    frame = blank()
    paint_condition(frame, {"res": "I_BLUE_TICKET"}, wf.resources)
    result, device = run(wf, [frame], params={"enabled": True}, ocr_reader=lambda *args: None)
    assert result.business_result == "blocked" and not device.inputs


def test_single_blue_ticket_budget_covers_open_draw_and_result_once(tmp_path):
    wf = build("one_summon")
    blue = blank()
    paint_condition(blue, {"res": "I_BLUE_TICKET"}, wf.resources)
    canvas = frame_for(wf, "draw_stroke_1")
    store = Store(tmp_path / "budget.db")
    budget = ResourceBudget(store, limits={"mystery_amulet": {"daily_limit": 1}})

    def authorize(state, action, variables):
        return budget.authorize(action["cost"]) if action.get("cost") else None

    result, device = run(wf, [blue, blue, canvas, canvas, frame_for(wf, "single_draw_receipt")],
        params={"enabled": True}, ocr_reader=lambda *args: 5, confirm=lambda *args: True, before_input=authorize)
    assert result.business_ok and [row[0] for row in device.inputs] == ["tap", "swipe"]
    assert store.resource_totals("default", budget.period())["mystery_amulet"]["used"] == 1


def test_native_input_error_after_draw_is_never_replayed_by_retry():
    wf = build("one_summon")
    canvas = frame_for(wf, "draw_stroke_1")

    class DeliveredThenFailed(ReplayDevice):
        def swipe(self, *args, **kwargs):
            super().swipe(*args, **kwargs)
            raise RuntimeError("input was delivered but IPC response failed")

    device = DeliveredThenFailed([canvas])
    result = Runner(wf, Controller(device, sleep=lambda _: None), clock=FakeClock(step=0.5),
                    params={"enabled": True}, initial_vars={"selected": 1}, confirm=lambda *args: True).run()
    assert result.failure_kind == "workflow_error" and result.variables["drawn"] == 1
    retried, second = run(wf, [canvas], params={"enabled": True}, initial_vars=result.variables,
                          confirm=lambda *args: True)
    assert len(device.inputs) == 1 and not second.inputs and not retried.business_ok


def test_new_foster_timer_is_not_misclassified_as_preexisting():
    wf = load_workflow(bundled_dir() / "workflows/foster.yaml")
    frame = register_texts(blank(), [("式神育成", 150, 40), ("寄养", 1100, 40), ("03:00:00", 1130, 90)])
    result, device = run(wf, [frame], initial_vars={"selected": 2, "unit_selected": 1, "started": 1})
    assert result.business_result == "completed" and result.business_ok and not device.inputs
    result, device = run(wf, [frame])
    assert result.business_result == "already_done" and not device.inputs
