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


def test_cherry_courtyard_fallback_requires_two_labels_and_expands_once():
    wf = build("friend_love")
    collapsed = register_texts(blank(), [("探索", 673, 168), ("加成", 378, 56)])
    expanded = register_texts(blank(41), [("式神录", 1132, 671), ("阴阳寮", 571, 671)])
    result, device = run(wf, [collapsed, expanded], max_actions=2)
    assert len(device.inputs) == 2
    assert [row[1] for row in result.history][:2] == ["expand_courtyard_menu", "open_friends"]
    unrelated = register_texts(blank(42), [("探索", 673, 168)])
    result, device = run(wf, [unrelated])
    assert not device.inputs and not result.business_ok
    for modal, x, y in (("每日一签", 640, 261), ("累计奖励", 519, 508), ("获得奖励", 641, 244)):
        overlay = register_texts(blank(43), [("式神录", 1132, 671), ("阴阳寮", 571, 671), (modal, x, y)])
        result, device = run(wf, [overlay])
        assert not device.inputs and not result.business_ok


class SyntheticFoodBuilder(SyntheticBuilder):
    def ass(self, fid):
        operators = []
        for index in range(15):
            name = "food_" + str(index)
            self.asset("test", name)
            operators.append({"detect": name, "oper": [
                {"rect": [500, 300, 520, 320], "delay": 1},
                {"rect": [611, 476, 676, 519], "delay": 1},
                {"rect": [956, 151, 994, 179], "delay": 1}]})
        return operators


def food_workflow():
    return load_workflow(SyntheticFoodBuilder({"workflow": "food"}, Path("unused")).food_boxes())


def test_modern_empty_experience_is_not_a_full_unit_or_a_withdrawal():
    wf = food_workflow()
    image = register_texts(blank(), [("经验酒壶", 630, 126), ("当前存储0/20000", 612, 213),
                                    ("提取", 640, 499)])
    # The old full-unit colour points also appear on the modern empty jar.
    paint_condition(image, {"res": "food_14"}, wf.resources)
    register_texts(image, [("经验酒壶", 630, 126), ("当前存储0/20000", 612, 213), ("提取", 640, 499)])
    result, device = run(wf, [image], initial_vars={"phase": 3}, ocr_reader=lambda *args: 0,
                         max_actions=1)
    assert result.failure_kind != "prerequisite"
    assert result.variables["exp_done"] == 1
    assert not any(row[0] == "tap" and 460 <= row[2] <= 540 for row in device.inputs)


def test_modern_stamina_requires_receipt_and_empty_never_withdraws():
    wf = food_workflow()
    box = register_texts(blank(), [("体刀食盒！", 642, 120), ("取出", 635, 555)])
    reward = register_texts(blank(41), [("获得奖励", 641, 244)])
    result, device = run(wf, [box, box], initial_vars={"phase": 1}, ocr_reader=lambda *args: 39)
    assert len(device.inputs) == 1 and result.variables["stamina_attempted"] == 1
    assert not result.variables["stamina_done"] and not result.business_ok
    result, device = run(wf, [box, box, reward], initial_vars={"phase": 1}, ocr_reader=lambda *args: 39,
                         max_actions=2)
    assert result.variables["stamina_done"] == 1 and result.variables["collected"] == 1
    result, device = run(wf, [box], initial_vars={"phase": 1}, ocr_reader=lambda *args: None)
    assert not device.inputs and not result.variables["stamina_done"]


@pytest.mark.parametrize("name,expected", [("foster", "guild_barrier"), ("home", "guild_home")])
def test_guild_entry_uses_independent_live_labels(name, expected):
    wf = load_workflow(bundled_dir() / "workflows" / (name + ".yaml"))
    guild = register_texts(blank(), [("集体任务", 63, 175), ("寮信息", 1197, 689)])
    result, device = run(wf, [guild], max_actions=1)
    assert result.history[0][1] == expected and len(device.inputs) == 1
    unrelated = register_texts(blank(41), [("集体任务", 63, 175)])
    result, device = run(wf, [unrelated])
    assert not device.inputs


def test_flower_task_tab_is_not_repeated_and_missing_reward_is_not_completion():
    wf = build("task_rewards")
    reward_tab = register_texts(blank(), [("花合战", 148, 41), ("任务排行", 1216, 427)])
    task_tab = register_texts(blank(41), [("花合战", 148, 41), ("今日", 542, 192),
                                        ("已完成0/1次", 623, 290), ("任务", 1216, 364)])
    result, device = run(wf, [reward_tab, task_tab])
    assert len(device.inputs) == 1
    assert result.business_result == "unknown" and not result.business_ok
    assert [row[1] for row in result.history] == ["task_tab", "task_rewards_not_available"]


def test_food_withdrawal_native_error_keeps_attempt_marker_for_retry():
    wf = food_workflow()
    box = register_texts(blank(), [("体力食盒", 642, 120), ("取出", 635, 555)])

    class DeliveredThenFailed(ReplayDevice):
        def tap(self, *args, **kwargs):
            super().tap(*args, **kwargs)
            raise RuntimeError("delivered but response failed")

    device = DeliveredThenFailed([box])
    result = Runner(wf, Controller(device, sleep=lambda _: None), initial_vars={"phase": 1},
                    text_reader=fake_text_reader, ocr_reader=lambda *a: 39, clock=FakeClock()).run()
    assert result.variables["stamina_attempted"] == 1 and result.failure_kind == "workflow_error"
    retry, retried = run(wf, [box], initial_vars=result.variables, ocr_reader=lambda *a: 39)
    assert not retried.inputs and not retry.business_ok


def test_daily_sign_is_one_attempt_and_requires_the_sign_result():
    wf = build("daily_sign")
    prompt = register_texts(blank(), [("每日一签", 640, 261), ("今日最佳奖励", 639, 450)])
    receipt = register_texts(blank(41), [("第208签", 543, 135), ("累计奖励", 519, 508), ("奖励", 496, 352)])
    result, device = run(wf, [prompt, prompt, receipt])
    assert result.business_ok and len(device.inputs) == 1 and result.variables["attempted"] == 1
    result, device = run(wf, [prompt, prompt, prompt])
    assert not result.business_ok and len(device.inputs) == 1
    result, device = run(wf, [receipt])
    assert not result.business_ok and not device.inputs


def test_missing_sign_marker_never_counts_as_already_signed():
    wf = build("daily_sign")
    courtyard = register_texts(blank(), [("式神录", 1132, 671), ("阴阳寮", 571, 671)])
    result, device = run(wf, [courtyard])
    assert result.business_result == "unknown" and not result.business_ok and not device.inputs


def test_home_closes_reward_in_front_of_a_known_page_before_navigating():
    wf = load_workflow(bundled_dir() / "workflows/home.yaml")
    overlay = register_texts(blank(), [("花合战", 148, 41), ("获得奖励", 640, 244)])
    result, device = run(wf, [overlay], max_actions=1)
    assert result.history[0][1] == "reward_popup" and len(device.inputs) == 1
    assert device.inputs[0][2] >= 630


@pytest.mark.parametrize("kind", ["store_sign", "medal_blue", "medal_black"])
def test_optional_mall_download_blocks_clicks_on_the_background(kind):
    wf = build(kind)
    frame = register_texts(blank(), [("是否下载？", 526, 349), ("取消", 484, 471)])
    paint_condition(frame, {"res": "I_CHECK_MALL_RECOMMEND"}, wf.resources)
    register_texts(frame, [("是否下载？", 526, 349), ("取消", 484, 471)])
    kwargs = {"params": {"enabled": True}} if kind.startswith("medal") else {}
    result, device = run(wf, [frame], **kwargs)
    assert result.business_result == "blocked" and not device.inputs
