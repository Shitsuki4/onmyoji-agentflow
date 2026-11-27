"""Pinned OAS KittyShop, MysteryShop, DailyTrifles, and WeeklyTrifles workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


KITTY_SHOP_ENTRY = "tasks/KittyShop/script_task.py"
KITTY_SHOP_PINS = {
    KITTY_SHOP_ENTRY: "7c54daeedae735d46f0b7fd0d4ba2acdd78a97f9123955d2046b1a659a1d1356",
    "tasks/KittyShop/config.py": "d2157f03f9074880df6da6a1161fc590815caa92cb67bd46f10f1482a5a3615b",
    "tasks/KittyShop/assets.py": "59bb1b31632047856685ae84e701e9df76c31c938976153429f8688982af55c6",
    "tasks/ActivityShikigami/assets.py": "48c47db751e19244ca94e5171b1489be1d17e7a2fdaaf63dd9d2941a88ec0072",
}

MYSTERY_SHOP_ENTRY = "tasks/MysteryShop/script_task.py"
MYSTERY_SHOP_PINS = {
    MYSTERY_SHOP_ENTRY: "871ca34ac994bd45bd22ae9344b947b4cbf74b81d8169bff0f522769b4c6070f",
    "tasks/MysteryShop/config.py": "2f8068cc8f69c6bbaafd7610425ce1a59578d48fdb5b8bb90c6b6929d493899b",
    "tasks/MysteryShop/assets.py": "cec25fd07d5a4bfee8db49ea258112b0b0762fdb9c7447d6dfd9c5d42530ee9c",
}
MYSTERY_PURCHASE_PINS = {
    "tasks/Component/Buy/buy.py": "ec3b1b01dc51fd63b084c5992c9dd2e1d04cb19645f9e79aaa22c19f415e3355",
    "tasks/Component/Buy/assets.py": "515f5ac2d72fb2fcdec77da93b9fa6f3bab0206431eb8c2cd19bae1b92706864",
    "tasks/RichMan/assets.py": "f8fe31ed6779426125bdbd33d3a24219d806dc51b68a8d97d6a50a211d83fb21",
    "tasks/RichMan/mall/friendship_points.py": "3c7ffce4f309fdd878ea49a4afa37a4ff19d711ac92a3427d9878cd631077f77",
    "tasks/RichMan/mall/special.py": "5d05920421880d1aae02ab7fa1f011f296bbc6d422a941b2969a17df0db443dd",
}
MYSTERY_OFFERS = (
    ("mshop_mystery_amulet", "BLUE", "神秘的符咒", 85),
    ("mshop_black_daruma_scrap", "BLACK", "御行达摩碎片", 60),
    ("mshop_kaiko_3", "TAIKO_3", "三星太鼓", 45),
    ("mshop_kaiko_4", "TAIKO_4", "四星太鼓", 80),
)

DAILY_TRIFLES_ENTRY = "tasks/DailyTrifles/script_task.py"
DAILY_TRIFLES_PINS = {
    DAILY_TRIFLES_ENTRY: "14f2765e6bcccf202aa2b31d1a4501cf025d055deee630ee4a92c0b38fde2192",
    "tasks/DailyTrifles/config.py": "32ea89dffe940d7d5b23d0a9ac105e7bcdce173dcf0ef5e8eaa72cf9b0657cda",
    "tasks/DailyTrifles/assets.py": "084d447a9802ba74cf9fc1403fe6e9593848d3e869adb5561fed0b1c5eaa4343",
    "tasks/DailyTrifles/page.py": "ac5416e71b029123e72e27a3c78f8a2fe94b396771ec6b0a8c0b809ff1079820",
    "tasks/RichMan/assets.py": MYSTERY_PURCHASE_PINS["tasks/RichMan/assets.py"],
    "tasks/Component/Buy/assets.py": MYSTERY_PURCHASE_PINS["tasks/Component/Buy/assets.py"],
}

WEEKLY_TRIFLES_ENTRY = "tasks/WeeklyTrifles/script_task.py"
WEEKLY_TRIFLES_PINS = {
    WEEKLY_TRIFLES_ENTRY: "e0b0fc649d0afe09003100d07ae8f5c8688c92720edc3b82197f6eb9c58da84e",
    "tasks/WeeklyTrifles/config.py": "3e4cd0bde275af34c97ea8e3a775712d2eac4a131aa6390cac36b366f3f8651a",
    "tasks/WeeklyTrifles/assets.py": "cc9585f4597e77559e5da2f4b1ef3026c9ba70869a277ddbecd84cdb37f3204f",
}


def _verify_pins(source: Path, pins: dict[str, str], label: str) -> None:
    for rel, expected in pins.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"{label} source fingerprint mismatch: {rel}")


def _click_from(docs: dict, name: str, ns: str, delay: int = 1000) -> dict:
    spec = docs[ns][name]
    if spec["type"] == "click":
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    return {"click": target, "delay": delay, "recheck": True}


def compile_kitty_shop_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS KittyShop workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, KITTY_SHOP_PINS, "KittyShop")
    nav = compile_navigation_family(
        source, resources, prefix="ks_nav", destination="page_main",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_kitty_shop_natively_staged", title="猫咪小店", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 900
    bind_schedule(source, raw)
    raw["params"].update(
        ks_attempts={"default": 1, "min": 0, "max": 50},
        ks_quit_when_finished={"default": False},
        ks_limit_seconds={"default": 0, "min": 0, "max": 3600},
        ks_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        ks_phase="navigate", ks_runs_done=0, ks_select_trials=0, ks_select_idx=0, ks_select_timer=0,
        ks_target_delay_s=0, ks_observed_ms=0, ks_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/KittyShop.yaml",
        "upstream/oas/ActivityShikigami.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("KittyShop", "ActivityShikigami", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"ks_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"ks_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"ks_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="KittyShop"):
        return {"res": f"{ns}::{name}"}

    def click(name, delay=1000, ns="KittyShop"):
        return _click_from(docs, name, ns, delay)

    court = raw["navigation"]["pages"]["page_main"]["when"]
    arrived = next(step for step in raw["states"] if step["id"] == "ks_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_shop")]
    next(step for step in raw["states"] if step["id"] == "ks_nav_drive")["when"] = phase("navigate")

    # Enter KittyShop from courtyard
    for ph in ("enter_shop", "farming"):
        state(f"{ph}_time_limit", ph,
              [expr("ks_limit_seconds > 0 and elapsed_ms >= ks_limit_seconds * 1000")],
              advance("exit_shop", ks_exit_reason="'time_limit'"))
    state("shop_ready", "enter_shop", [asset("I_START_FARMING")], advance("dispatch", ks_runs_done=0))
    state("enter_go1", "enter_shop", [asset("I_GO1")], click("I_GO1", 2000))
    state("enter_shi", "enter_shop", [asset("I_SHI", "ActivityShikigami")],
          {"click_found": True, "use_match_size": True, "delay": 2000, "recheck": True})

    # Loop attempts
    state("time_limit_dispatch", "dispatch",
          [expr("ks_limit_seconds > 0 and elapsed_ms >= ks_limit_seconds * 1000")],
          advance("exit_shop", ks_exit_reason="'time_limit'"))
    state("all_attempts_done", "dispatch", [expr("ks_runs_done >= ks_attempts")],
          advance("exit_shop", ks_exit_reason="'attempts_done'"))
    state("start_attempt", "dispatch", [asset("I_START_FARMING")],
          click("I_START_FARMING", 1000),
          advance("select_open", ks_select_trials=0, ks_select_idx=0, ks_select_timer="elapsed_ms"))

    # Select kitties (up to 3 trials; 12-step selection index matching source)
    state("select_ready", "select_open", [asset("I_START_ENSURE")],
          advance("select_kitties", ks_select_idx=0, ks_select_timer="elapsed_ms"))
    state("select_open_retry", "select_open", [asset("I_START_FARMING")], click("I_START_FARMING", 1000))

    state("select_all_picked", "select_kitties", [{"not": asset("I_UNSELECTED")}], advance("ensure_start"))
    state("select_trial_failed", "select_kitties", [expr("ks_select_idx >= 12"), expr("ks_select_trials < 2")],
          click("I_UI_BACK_YELLOW", 2200, "GlobalGame"),
          advance("select_open", ks_select_trials="ks_select_trials + 1"))
    state("select_give_up", "select_kitties", [expr("ks_select_idx >= 12")], advance("ensure_start"))
    for idx_list, btn in (([0], "C_SELECT_1"), ([1], "C_SELECT_2"), ([2], "C_SELECT_3"), ([3, 7, 11], "C_SELECT_4")):
        cond = {"any": [expr(f"ks_select_idx == {i}") for i in idx_list]} if len(idx_list) > 1 else expr(f"ks_select_idx == {idx_list[0]}")
        state(f"select_{btn.lower()}", "select_kitties", [asset("I_UNSELECTED"), cond],
              click(btn, 1200), {"inc": "ks_select_idx"})
    state("select_swipe", "select_kitties",
          [asset("I_UNSELECTED"), {"any": [expr("ks_select_idx == 5"), expr("ks_select_idx == 10")]}],
          {"swipe": "KittyShop::S_SELECTION", "delay": 1500, "recheck": True}, {"inc": "ks_select_idx"})
    state("select_advance_tick", "select_kitties", [asset("I_UNSELECTED")], {"inc": "ks_select_idx"}, {"wait": 200})

    # Start farming
    state("farming_started", "ensure_start", [asset("I_MAIN_FLAG")], advance("farming"))
    state("ensure_click", "ensure_start", [asset("I_START_ENSURE")], click("I_START_ENSURE", 1000))

    # Farming loop
    state("farming_share_done", "farming", [asset("I_MAIN_SHARE")], advance("close_result"))
    state("farming_quit_confirm", "farming", [expr("ks_quit_when_finished"), asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", 700, "GlobalGame"))
    state("farming_quit_confirm_small", "farming",
          [expr("ks_quit_when_finished"), asset("I_UI_CONFIRM_SAMLL", "GlobalGame")],
          click("I_UI_CONFIRM_SAMLL", 700, "GlobalGame"))
    state("farming_quit_finish", "farming", [expr("ks_quit_when_finished"), asset("I_MAIN_FINSH")],
          click("I_MAIN_FINSH", 1000))
    state("farming_gift", "farming", [asset("I_MAIN_FLAG"), asset("I_MAIN_GIFT")],
          {"click_found": True, "use_match_size": True, "delay": 700, "recheck": True})
    state("farming_add", "farming", [asset("I_MAIN_FLAG"), asset("I_MAIN_ADD")],
          {"click_found": True, "use_match_size": True, "delay": 600, "recheck": True})
    for slot in range(1, 6):
        busy = f"I_MAIN_BUSY_{slot}"
        state(f"farming_pick_kitty_{slot}", "farming",
              [asset("I_MAIN_FLAG"), asset("I_MAIN_FLAG1"), {"not": asset(busy)}],
              click(busy, 1300))

    # Close result back to I_START_FARMING
    state("result_closed", "close_result", [asset("I_START_FARMING")],
          advance("dispatch", ks_runs_done="ks_runs_done + 1"))
    state("result_dismiss", "close_result", [], click("I_MAIN_FLAG1", 2000))

    # Exit back to courtyard
    state("returned_main_target_prep", "exit_shop", [court, expr("ks_next_delay_s > 0")],
          advance("stop_target", ks_target_delay_s="ks_next_delay_s", ks_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "猫咪小店已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "KittyShop",
                "delay_seconds_var": "ks_target_delay_s",
                "observed_ms_var": "ks_observed_ms",
            },
            "evidence": {"scope": "kitty_shop_target_schedule"},
        }
    })
    state("returned_main", "exit_shop", [court], {
        "stop": {
            "reason": "猫咪小店已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "KittyShop",
            "evidence": {"scope": "kitty_shop_native_path"},
        }
    })
    state("exit_back_yellow", "exit_shop", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", 2400, "GlobalGame"))

    raw["oas_kitty_shop_contract"] = {
        "source": KITTY_SHOP_ENTRY,
        "source_pins": {**KITTY_SHOP_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "kitty_shop_live_event_frames",
            "blocking": True,
            "requirement": "Verify KittyShop entry, kitty selection swipe, and farming loop on live event frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def _bind_mystery_purchase(raw, docs, state, advance, click, asset, expr):
    shop = {"any": [asset("I_MS_SHARE"), asset("I_MS_BEFORE")]}
    more = asset("I_BUY_PLUS", "Component_Buy")
    rmb = asset("I_BUY_RMB", "Component_Buy")
    jade = asset("I_BUY_JADE", "Component_Buy")
    reward = {"any": [asset("I_UI_REWARD", "GlobalGame", threshold=.6),
                      asset("I_BUY_SUCCESS", "Component_Buy")]}
    balance = {"ocr": "RichMan::O_MALL_RESOURCE_5", "mode": "exact_quantity", "var": "mshop_balance"}
    price = {"ocr": "Component_Buy::O_BUY_PRICE", "mode": "exact_quantity", "var": "mshop_price"}
    amount_read = {"ocr": "Component_Buy::O_BUY_NUMBER", "mode": "exact_quantity", "var": "mshop_quantity"}
    stock_width, stock_height = docs["RichMan"]["O_SP_RES_NUMBER"]["roi"][2:]
    raw["vars"].update(mshop_offer=0, mshop_stock=-1, mshop_balance=-1, mshop_balance_before=-1,
                       mshop_price=-1, mshop_quoted_price=-1, mshop_quantity=-1, mshop_quoted_quantity=1,
                       mshop_spent=0, mshop_transactions=0, mshop_started=-1)

    def time_limit(milliseconds):
        return expr(f"elapsed_ms - mshop_started >= {milliseconds}")

    for index, (enabled, product, title, maximum) in enumerate(MYSTERY_OFFERS):
        name = product.lower()
        arm = expr(f"mshop_offer == {index}")
        following = advance("offer", mshop_offer=index + 1)
        offer = asset("I_MS_" + product)
        dialog = asset("I_MS_CHECK_" + product)
        x, y, width, _ = docs["MysteryShop"]["I_MS_" + product]["front"]
        stock_ref = "MS_STOCK_" + product
        raw.setdefault("inline_resources", {})[stock_ref] = {"type": "ocr", "mode": "Single",
            "roi": [x + width // 2 - stock_width // 2, y - stock_height, stock_width, stock_height]}
        stock = {"ocr": stock_ref, "mode": "shop_stock", "var": "mshop_stock"}
        state("skip_disabled_" + name, "offer", [arm, expr(f"not {enabled}")], following)
        state("unavailable_" + name, "offer", [arm, shop, {"not": offer}], following)
        state("sold_out_" + name, "offer", [arm, shop, offer, {**stock, "test": "mshop_stock == 0"}], following)
        state("budget_depleted_" + name, "offer", [arm, shop, expr("mshop_spent >= mshop_max_jade")], following)
        state("balance_low_" + name, "offer", [arm, shop, offer, balance,
              expr(f"mshop_balance - mshop_jade_reserve < {maximum}")], following)
        state("open_offer_" + name, "offer", [arm, shop, offer, balance, stock, expr(
              f"mshop_stock > 0 and mshop_balance - mshop_jade_reserve >= {maximum}")],
              click("I_MS_" + product), advance("quote", mshop_started="elapsed_ms",
                                               mshop_balance_before="mshop_balance"))
        state("unreadable_offer_" + name, "offer", [arm, shop, offer],
              {"fail": f"{title}缺少有效库存或勾玉余额"})

        supported = [arm, dialog, jade, {"not": rmb}]
        unit_price_1 = "40 <= mshop_price <= 85" if product == "BLUE" else f"mshop_price == {maximum}"
        unit_price_multi = (
            "40 * mshop_quantity <= mshop_price and mshop_price <= 85 * mshop_quantity"
            if product == "BLUE" else f"mshop_price == {maximum} * mshop_quantity"
        )
        state("increase_qty_" + name, "quote", [
            *supported, more, amount_read, price, balance,
            expr("mshop_buy_quantity > 1 and mshop_quantity >= 1 and mshop_quantity < mshop_buy_quantity "
                 "and (mshop_stock <= 0 or mshop_quantity < mshop_stock)"),
            expr(f"mshop_balance == mshop_balance_before and "
                 f"mshop_spent + (mshop_quantity + 1) * {maximum} <= mshop_max_jade and "
                 f"mshop_balance - mshop_jade_reserve >= (mshop_quantity + 1) * {maximum}"),
        ], click("I_BUY_ADD", delay=600, ns="Component_Buy"), {"set": {"mshop_started": "elapsed_ms"}})
        quote_ok_single = [
            *supported, {"not": more}, price, balance,
            expr(f"{unit_price_1} and mshop_balance == mshop_balance_before and "
                 "mshop_price <= mshop_balance - mshop_jade_reserve and "
                 "mshop_spent + mshop_price <= mshop_max_jade"),
        ]
        quote_ok_multi = [
            *supported, more, amount_read, price, balance,
            expr(f"1 <= mshop_quantity and mshop_quantity <= mshop_buy_quantity and "
                 f"(mshop_stock <= 0 or mshop_quantity <= mshop_stock) and {unit_price_multi} and "
                 "mshop_balance == mshop_balance_before and "
                 "mshop_price <= mshop_balance - mshop_jade_reserve and "
                 "mshop_spent + mshop_price <= mshop_max_jade"),
        ]
        state("quote_ready_" + name + "_multi", "quote", quote_ok_multi,
              advance("commit", mshop_quoted_price="mshop_price",
                      mshop_quoted_quantity="mshop_quantity", mshop_started="elapsed_ms"))
        state("quote_ready_" + name + "_single", "quote", quote_ok_single,
              advance("commit", mshop_quoted_price="mshop_price",
                      mshop_quoted_quantity=1, mshop_started="elapsed_ms"))
        state("cancel_rmb_" + name, "quote", [arm, dialog, rmb],
              click("C_BUY_CANCEL", ns="Component_Buy"), advance("cancel", mshop_started="elapsed_ms"))
        state("reject_quote_" + name, "quote", [arm, dialog, time_limit(3000)],
              click("C_BUY_CANCEL", ns="Component_Buy"), advance("cancel", mshop_started="elapsed_ms"))
        state("dialog_not_identified_" + name, "quote", [arm, time_limit(9000)],
              {"fail": f"未确认{title}购买窗口"})
        state("purchase_" + name + "_multi", "commit",
              [*quote_ok_multi, expr("mshop_price == mshop_quoted_price and mshop_quantity == mshop_quoted_quantity")],
              click("C_BUY_MORE", ns="Component_Buy"),
              advance("settle", mshop_spent="mshop_spent + mshop_quoted_price", mshop_started="elapsed_ms"))
        raw["states"][-1].update(
            sensitive="花勾玉", desc=f"购买{title}（单件至多 {maximum} 勾玉）。"
            "确认后重新核对货品、数量、总价、余额和剩余预算。")
        state("purchase_" + name + "_single", "commit",
              [*quote_ok_single, expr("mshop_price == mshop_quoted_price")],
              click("C_BUY_ONE", ns="Component_Buy"),
              advance("settle", mshop_spent="mshop_spent + mshop_quoted_price", mshop_started="elapsed_ms"))
        raw["states"][-1].update(
            sensitive="花勾玉", desc=f"购买一件{title}，本次至多花费 {maximum} 勾玉。"
            "确认后重新核对货品、数量、价格、余额和剩余预算。")
        state("changed_quote_" + name, "commit", [arm, time_limit(9000)],
              {"fail": f"{title}报价变化，未提交购买"})
        state("dialog_cancelled_" + name, "cancel", [arm, shop, {"not": dialog}, {"not": more}], following)

    raw.setdefault("inline_resources", {})["MS_FRIEND_FULL"] = {
        "type": "ocr", "mode": "Full", "roi": list(docs["MysteryShop"]["O_MS_FRIEND"]["roi"]),
    }
    state("next_friend_from_own", "offer", [
        asset("I_MS_SHARE"), expr(f"mshop_offer >= {len(MYSTERY_OFFERS)}"),
        expr("mshop_friends_visited < mshop_max_friends"), asset("I_MS_NEXT"),
    ], click("I_MS_NEXT", delay=1000), advance("switch_friend_own", mshop_started="elapsed_ms"))
    state("switch_friend_own_done", "switch_friend_own", [{"not": asset("I_MS_SHARE")}],
          {"inc": "mshop_friends_visited"}, advance("offer", mshop_offer=0))
    state("switch_friend_own_timeout", "switch_friend_own", [time_limit(10000)], advance("read_rewards"))
    state("switch_friend_own_retry", "switch_friend_own", [asset("I_MS_SHARE"), asset("I_MS_NEXT")],
          click("I_MS_NEXT", delay=1000))
    state("next_friend_from_friend_ocr", "offer", [
        {"not": asset("I_MS_SHARE")}, asset("I_MS_BEFORE"), expr(f"mshop_offer >= {len(MYSTERY_OFFERS)}"),
        expr("mshop_friends_visited < mshop_max_friends"), asset("I_MS_NEXT"),
        {"ocr": "MS_FRIEND_FULL", "mode": "text_sequence", "var": "mshop_prev_friend_name"},
    ], click("I_MS_NEXT", delay=2500), advance("switch_friend_name", mshop_started="elapsed_ms"))
    state("next_friend_from_friend_fallback", "offer", [
        {"not": asset("I_MS_SHARE")}, asset("I_MS_BEFORE"), expr(f"mshop_offer >= {len(MYSTERY_OFFERS)}"),
        expr("mshop_friends_visited < mshop_max_friends"), asset("I_MS_NEXT"),
    ], click("I_MS_NEXT", delay=1500), {"inc": "mshop_friends_visited"}, advance("offer", mshop_offer=0))
    state("switch_friend_name_changed", "switch_friend_name", [
        {"ocr": "MS_FRIEND_FULL", "mode": "text_sequence", "var": "mshop_cur_friend_name"},
        expr("mshop_cur_friend_name != mshop_prev_friend_name"),
    ], {"inc": "mshop_friends_visited"}, advance("offer", mshop_offer=0))
    state("switch_friend_name_timeout", "switch_friend_name", [time_limit(12000)], advance("read_rewards"))
    state("switch_friend_name_retry", "switch_friend_name", [asset("I_MS_NEXT")],
          click("I_MS_NEXT", delay=2500))
    state("all_offers_reviewed", "offer", [shop, expr(f"mshop_offer >= {len(MYSTERY_OFFERS)}")], advance("read_rewards"))
    state("purchase_reward", "settle", [reward], click("C_UI_REWARD", delay=400, ns="GlobalGame"))
    state("purchase_balance_verified", "settle", [shop, {"not": reward}, balance,
          expr("mshop_balance == mshop_balance_before - mshop_quoted_price")],
          {"inc": "mshop_transactions"}, advance("offer"))
    state("purchase_result_unknown", "settle", [time_limit(12000)],
          {"fail": "购买动作已尝试，缺少余额扣款验证，停止后续购买"})
    state("cancel_result_unknown", "cancel", [time_limit(10000)], {"fail": "购买弹窗尚未确认关闭"})


def compile_mystery_shop_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS MysteryShop workflow with explicit economic purchase guard."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, {**MYSTERY_SHOP_PINS, **MYSTERY_PURCHASE_PINS}, "MysteryShop")
    nav = compile_navigation_family(
        source, resources, prefix="mshop_nav", destination="page_mall",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_mystery_shop_natively_staged", title="神秘商店", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update(
        mshop_is_open_day={"default": True},
        mshop_mystery_amulet={"default": False},
        mshop_black_daruma_scrap={"default": False},
        mshop_kaiko_3={"default": False},
        mshop_kaiko_4={"default": False},
        mshop_share_enable={"default": False},
        mshop_confirm_share={"default": False},
        mshop_share_friend={"default": ""},
        mshop_share_friend_2={"default": ""},
        mshop_share_friend_3={"default": ""},
        mshop_share_friend_4={"default": ""},
        mshop_share_friend_5={"default": ""},
        mshop_max_friends={"default": 0, "min": 0, "max": 20},
        mshop_buy_quantity={"default": 1, "min": 1, "max": 10},
        mshop_limit_seconds={"default": 0, "min": 0, "max": 7200},
        mshop_next_open_delay_s={"default": 0, "min": 0, "max": 604800},
        mshop_max_jade={"default": 0, "min": 0, "max": 99999},
        mshop_jade_reserve={"default": 0, "min": 0, "max": 99999999},
    )
    raw["vars"].update(
        mshop_phase="entry", mshop_records=-1, mshop_rewards_claimed=0, mshop_exit_reason="",
        mshop_shared=False, mshop_share_tab=0, mshop_share_idx=0, mshop_shares_sent=0,
        mshop_current_share_friend="", mshop_friends_visited=0,
        mshop_prev_friend_name="", mshop_cur_friend_name="",
        mshop_target_delay_s=0, mshop_observed_ms=0,
    )
    names = ("MysteryShop", "GlobalGame", "RichMan", "Component_Buy", "Component_GeneralInvite")
    raw["resources"] = sorted(set(raw["resources"] + [f"upstream/oas/{name}.yaml" for name in names]))
    docs = {name: load_yaml(resources / f"{name}.yaml")["resources"] for name in names}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"mshop_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"mshop_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"mshop_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="MysteryShop", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, delay=1000, ns="MysteryShop"):
        return _click_from(docs, name, ns, delay)

    state("not_open_day_target", "entry", [expr("not mshop_is_open_day and mshop_next_open_delay_s > 0")],
          {"set": {"mshop_target_delay_s": "mshop_next_open_delay_s", "mshop_observed_ms": "elapsed_ms",
                   "mshop_exit_reason": "'closed_day'"}}, {
              "stop": {
                  "reason": "今日非神秘商店开放日(周三/周六)，已按开放日程预约下次运行",
                  "result": "unknown",
                  "verified": False,
                  "oas_schedule": {
                      "task": "MysteryShop",
                      "delay_seconds_var": "mshop_target_delay_s",
                      "observed_ms_var": "mshop_observed_ms",
                  },
                  "evidence": {"scope": "mystery_shop_closed_day_target"},
              }
          })
    state("not_open_day", "entry", [expr("not mshop_is_open_day")], {
        "stop": {
            "reason": "今日非神秘商店开放日(周三/周六)",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "MysteryShop",
            "evidence": {"scope": "mystery_shop_closed_day"},
        }
    })
    state("entry_to_nav", "entry", [expr("mshop_is_open_day")], advance("navigate"))

    arrived = next(step for step in raw["states"] if step["id"] == "mshop_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_shop")]
    next(step for step in raw["states"] if step["id"] == "mshop_nav_drive")["when"] = phase("navigate")

    for ph in ("enter_shop", "check_guards", "share_invite", "offer", "switch_friend_own", "switch_friend_name", "read_rewards"):
        state(f"{ph}_time_limit", ph,
              [expr("mshop_limit_seconds > 0 and elapsed_ms >= mshop_limit_seconds * 1000")],
              advance("exit_shop", mshop_exit_reason="'time_limit'"))
    state("entered_shop", "enter_shop", [asset("I_MS_SHARE")], advance("check_guards"))
    state("click_enter", "enter_shop", [asset("I_ME_ENTER")], click("I_ME_ENTER", 1000))

    state("share_gate", "check_guards", [expr("mshop_share_enable and not mshop_confirm_share")],
          {"fail": "神秘商店好友分享(GeneralInvite)需显式确认(mshop_confirm_share=True)"})
    share_friend_params = (
        "mshop_share_friend", "mshop_share_friend_2", "mshop_share_friend_3",
        "mshop_share_friend_4", "mshop_share_friend_5",
    )
    for fidx, fparam in enumerate(share_friend_params):
        state(f"share_open_{fidx}", "check_guards",
              [expr(f"mshop_share_enable and mshop_confirm_share and not mshop_shared "
                    f"and mshop_share_idx == {fidx} and {fparam} != ''"),
               asset("I_MS_SHARE")],
              click("I_MS_SHARE", 1000),
              advance("share_invite", mshop_share_tab=0, mshop_current_share_friend=fparam))
        state(f"share_skip_{fidx}", "check_guards",
              [expr(f"mshop_share_enable and mshop_confirm_share and not mshop_shared "
                    f"and mshop_share_idx == {fidx} and {fparam} == ''")],
              {"set": {"mshop_share_idx": fidx + 1, "mshop_shared": fidx == len(share_friend_params) - 1}})
    state("share_all_slots_done", "check_guards",
          [expr(f"mshop_share_enable and mshop_confirm_share and not mshop_shared "
                f"and mshop_share_idx >= {len(share_friend_params)}")],
          {"set": {"mshop_shared": True}})
    for col in (1, 2):
        name_roi = docs["Component_GeneralInvite"][f"O_FRIEND_NAME_{col}"]["roi"]
        state(f"share_pick_col{col}", "share_invite", [
            {"not": asset("I_SELECTED", "Component_GeneralInvite")},
            {"ocr_full": {
                "region": name_roi,
                "keyword_var": "mshop_current_share_friend",
                "selection": "unique_equals",
                "evidence": "complete_keyword",
            }},
        ], {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1000})
    state("share_confirm", "share_invite",
          [asset("I_SELECTED", "Component_GeneralInvite"), asset("I_INVITE_ENSURE")],
          click("I_INVITE_ENSURE", 1200),
          {"inc": "mshop_shares_sent"},
          advance("check_guards", mshop_share_idx="mshop_share_idx + 1"))
    for tab in (1, 2):
        state(f"share_tab_{tab}", "share_invite", [
            {"not": asset("I_SELECTED", "Component_GeneralInvite")},
            expr(f"mshop_share_tab < {tab}"),
            asset(f"I_FLAG_{tab}_OFF", "Component_GeneralInvite"),
        ], click(f"I_FLAG_{tab}_OFF", 1000, "Component_GeneralInvite"), {"set": {"mshop_share_tab": tab}})
    state("share_not_found_close", "share_invite",
          [{"not": asset("I_SELECTED", "Component_GeneralInvite")}, asset("I_INVITE_ENSURE")],
          click("I_INVITE_ENSURE", 1000),
          advance("check_guards", mshop_share_idx="mshop_share_idx + 1"))
    any_buy = expr(" or ".join(offer[0] for offer in MYSTERY_OFFERS))
    state("buy_economic_gate", "check_guards", [any_buy, expr("mshop_max_jade == 0")],
          {"fail": "神秘商店勾玉购买需设置勾玉预算并逐笔经济确认"})
    state("prepare_own_shop_purchase", "check_guards", [any_buy], advance("offer"))
    state("guards_clear", "check_guards", [], advance("read_rewards"))
    _bind_mystery_purchase(raw, docs, state, advance, click, asset, expr)

    # Claim free milestone rewards (3/5/10)
    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    state("read_records", "read_rewards", [{"ocr": "MysteryShop::O_MS_RECORDS", "var": "mshop_records"}],
          advance("claim_r3"))
    state("records_unreadable", "read_rewards", [], advance("exit_shop", mshop_exit_reason="'no_records'"))

    for threshold, cur, nxt, res_name in (
        (3, "claim_r3", "claim_r5", "I_MS_REWARD_3"),
        (5, "claim_r5", "claim_r10", "I_MS_REWARD_5"),
        (10, "claim_r10", "exit_shop", "I_MS_REWARD_10"),
    ):
        state(f"{cur}_reward_popup", cur, [reward],
              click("C_UI_REWARD", 500, "GlobalGame"), {"inc": "mshop_rewards_claimed"}, advance(nxt))
        state(f"{cur}_tap", cur, [expr(f"mshop_records >= {threshold}"), asset(res_name)], click(res_name, 800))
        state(f"{cur}_skip", cur, [], advance(nxt))

    mall = raw["navigation"]["pages"]["page_mall"]["when"]
    state("returned_mall_scheduled", "exit_shop", [mall, expr("mshop_next_open_delay_s > 0")],
          {"set": {"mshop_target_delay_s": "mshop_next_open_delay_s", "mshop_observed_ms": "elapsed_ms"}}, {
              "stop": {
                  "reason": "神秘商店检查与免费奖励领取完成并返回商店",
                  "result": "unknown",
                  "verified": False,
                  "oas_schedule": {
                      "task": "MysteryShop",
                      "delay_seconds_var": "mshop_target_delay_s",
                      "observed_ms_var": "mshop_observed_ms",
                  },
                  "evidence": {"scope": "mystery_shop_native_path"},
              }
          })
    state("returned_mall", "exit_shop", [mall], {
        "stop": {
            "reason": "神秘商店检查与免费奖励领取完成并返回商店",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "MysteryShop",
            "evidence": {"scope": "mystery_shop_native_path"},
        }
    })
    state("exit_back_yellow", "exit_shop", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", 1000, "GlobalGame"))

    raw["oas_mystery_shop_contract"] = {
        "source": MYSTERY_SHOP_ENTRY,
        "source_pins": {**MYSTERY_SHOP_PINS, **MYSTERY_PURCHASE_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "mystery_shop_economic_purchase_and_share",
            "blocking": True,
            "requirement": "Verify the own-shop quote and purchase receipt on live frames. "
                           "Bind amount selection beyond one item, friend storefront traversal and friend-share invite.",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_daily_trifles_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS DailyTrifles workflow with summon and jade-sushi economic guards."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, DAILY_TRIFLES_PINS, "DailyTrifles")
    nav = compile_navigation_family(
        source, resources, prefix="dt_nav", destination="page_main",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_daily_trifles_natively_staged", title="每日琐事", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update(
        dt_one_summon={"default": False},
        dt_confirm_summon={"default": False},
        dt_summon_type={"default": "普通召唤", "choices": ["普通召唤", "今忆召唤"]},
        dt_draw_mystery_pattern={"default": False},
        dt_friend_love={"default": False},
        dt_luck_msg={"default": False},
        dt_store_sign={"default": False},
        dt_buy_sushi_count={"default": -1, "min": -1, "max": 20},
        dt_confirm_sushi={"default": False},
        dt_sushi_max_jade={"default": 0, "min": 0, "max": 5000},
        dt_sushi_jade_reserve={"default": 0, "min": 0, "max": 99999999},
        dt_limit_seconds={"default": 0, "min": 0, "max": 7200},
        dt_next_delay_s={"default": 0, "min": 0, "max": 172800},
    )
    raw["vars"].update(
        dt_phase="dispatch_summon", dt_nav_arrived_sub=0, dt_timer=0, dt_gift_cnt=0,
        dt_summon_ticket=-1, dt_summon_submitted=False, dt_summon_done=False,
        dt_recall_tab=0, dt_recall_round=0,
        dt_friend_done=False, dt_luck_done=False, dt_sign_done=False,
        dt_sushi_jade=-1, dt_sushi_jade_before=-1, dt_sushi_price=-1, dt_sushi_quantity=-1,
        dt_sushi_quoted_price=0, dt_sushi_previous_price=0, dt_sushi_spent=0, dt_sushi_purchases=0,
        dt_target_delay_s=0, dt_observed_ms=0, dt_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/DailyTrifles.yaml", "upstream/oas/GlobalGame.yaml",
        "upstream/oas/RichMan.yaml", "upstream/oas/Component_Buy.yaml",
        "upstream/oas/Component_Summon.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("DailyTrifles", "GlobalGame", "RichMan", "Component_Buy", "Component_Summon")}
    luck_roi = docs["DailyTrifles"]["O_LUCK_MSG"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"dt_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"dt_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"dt_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="DailyTrifles", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, delay=1000, ns="DailyTrifles"):
        return _click_from(docs, name, ns, delay)

    # Unused initial nav disabled unless phase == 'navigate'
    next(step for step in raw["states"] if step["id"] == "dt_nav_returned")["when"]["all"].append(phase("navigate"))
    next(step for step in raw["states"] if step["id"] == "dt_nav_drive")["when"] = phase("navigate")

    court = raw["navigation"]["pages"]["page_main"]["when"]
    friends = raw["navigation"]["pages"]["page_friends"]["when"]
    mall = raw["navigation"]["pages"]["page_mall"]["when"]
    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    back_red = asset("I_UI_BACK_RED", "GlobalGame")

    # 1. One summon (normal or recall) with explicit dt_confirm_summon + sensitive="抽卡"
    summon_page = raw["navigation"]["pages"]["page_summon"]["when"]
    state("summon_gate", "dispatch_summon", [expr("dt_one_summon and not dt_confirm_summon")],
          {"fail": "每日一抽(普通/今忆召唤)需显式抽卡确认契约"})
    state("summon_skip", "dispatch_summon", [expr("not dt_one_summon")], advance("dispatch_love"))
    state("summon_goto", "dispatch_summon", [expr("dt_one_summon and dt_confirm_summon")],
          advance("summon_nav", dt_nav_arrived_sub=0, dt_summon_submitted=False))
    state("summon_arrived", "summon_nav", [summon_page, expr("dt_nav_arrived_sub == 1")], advance("summon_open"))
    state("summon_drive", "summon_nav", [], {"navigate": {"destination": "page_summon", "done_var": "dt_nav_arrived_sub"}})

    state("summon_open_time_limit", "summon_open",
          [expr("dt_limit_seconds > 0 and elapsed_ms >= dt_limit_seconds * 1000")],
          advance("summon_exit", dt_exit_reason="'time_limit'"))
    state("summon_draw_time_limit", "summon_draw",
          [expr("dt_limit_seconds > 0 and elapsed_ms >= dt_limit_seconds * 1000")],
          advance("summon_exit", dt_exit_reason="'time_limit'"))
    state("summon_default_no_ticket", "summon_open",
          [expr("dt_summon_type == '普通召唤'"), asset("I_BLUE_TICKET", "Component_Summon"),
           {"ocr": "Component_Summon::O_ONE_TICKET", "var": "dt_summon_ticket",
            "test": "dt_summon_ticket <= 0"}],
          advance("summon_exit", dt_summon_done=False))
    state("summon_default_enter", "summon_open",
          [expr("dt_summon_type == '普通召唤'"), asset("I_BLUE_TICKET", "Component_Summon"),
           {"ocr": "Component_Summon::O_ONE_TICKET", "var": "dt_summon_ticket",
            "test": "dt_summon_ticket > 0"}],
          click("I_BLUE_TICKET", 1000, "Component_Summon"), advance("summon_draw", dt_timer="elapsed_ms"))
    state("summon_recall_no_ticket", "summon_open",
          [expr("dt_summon_type == '今忆召唤'"), asset("I_RECALL_TICKET"),
           {"ocr": "DailyTrifles::O_RECALL_TICKET_AREA", "var": "dt_summon_ticket",
            "test": "dt_summon_ticket <= 0"}],
          advance("summon_exit", dt_summon_done=False))
    state("summon_recall_enter", "summon_open",
          [expr("dt_summon_type == '今忆召唤'"), asset("I_RECALL_TICKET"),
           {"ocr": "DailyTrifles::O_RECALL_TICKET_AREA", "var": "dt_summon_ticket",
            "test": "dt_summon_ticket > 0"}],
          click("I_RECALL_TICKET", 1000), advance("summon_draw", dt_timer="elapsed_ms"))
    state("summon_recall_close_popup", "summon_open",
          [expr("dt_summon_type == '今忆召唤'"), {"not": asset("I_RECALL_TICKET")}, back_red],
          click("I_UI_BACK_RED", 1000, "GlobalGame"))
    state("summon_recall_not_found", "summon_open",
          [expr("dt_summon_type == '今忆召唤' and dt_recall_round >= 3"), {"not": asset("I_RECALL_TICKET")}],
          {"log": "今忆召唤未找到召唤入口，安全跳过"},
          advance("summon_exit", dt_summon_done=False, dt_exit_reason="'recall_not_found'"))
    recall_anchor = {"any": [asset("I_BLUE_TICKET", "Component_Summon"), summon_page]}
    for tab_idx, sm_name in enumerate(("O_SELECT_SM2", "O_SELECT_SM3", "O_SELECT_SM4")):
        rx, ry, rw, rh = docs["DailyTrifles"][sm_name]["roi"]
        tab_update = ({"dt_recall_tab": tab_idx + 1} if tab_idx < 2
                      else {"dt_recall_tab": 0, "dt_recall_round": "dt_recall_round + 1"})
        state(f"summon_recall_tab_{tab_idx + 2}", "summon_open",
              [expr(f"dt_summon_type == '今忆召唤' and dt_recall_round < 3 and dt_recall_tab == {tab_idx}"),
               {"not": asset("I_RECALL_TICKET")}, recall_anchor],
              {"click": [rx, ry, rx + rw, ry + rh], "delay": 1000, "recheck": True},
              {"set": tab_update})

    state("summon_draw_cancel_voice", "summon_draw", [asset("I_UI_CANCEL", "GlobalGame")],
          click("I_UI_CANCEL", 800, "GlobalGame"))
    state("summon_draw_confirm_1", "summon_draw", [asset("I_SM_CONFIRM", "Component_Summon")],
          click("I_SM_CONFIRM", 800, "Component_Summon"), advance("summon_exit", dt_summon_done=True))
    state("summon_draw_confirm_2", "summon_draw", [asset("I_SM_CONFIRM_2", "Component_Summon")],
          click("I_SM_CONFIRM_2", 800, "Component_Summon"), advance("summon_exit", dt_summon_done=True))
    state("summon_draw_confirm_recall", "summon_draw", [asset("I_RECALL_SM_CONFIRM")],
          click("I_RECALL_SM_CONFIRM", 800), advance("summon_exit", dt_summon_done=True))
    state("summon_draw_confirm_recall_2", "summon_draw", [asset("I_SM_CONFIRM_2")],
          click("I_SM_CONFIRM_2", 800), advance("summon_exit", dt_summon_done=True))
    state("summon_draw_swipe_default", "summon_draw",
          [expr("dt_summon_type == '普通召唤' and not dt_summon_submitted"),
           asset("I_ONE_TICKET", "Component_Summon")],
          {"swipe": "Component_Summon::S_RANDOM_SWIPE_1", "delay": 1000, "recheck": True},
          {"set": {"dt_summon_submitted": True}})
    raw["states"][-1].update(sensitive="抽卡", desc="每日一抽：消耗 1 张神秘的符咒进行一次普通召唤。")
    state("summon_draw_swipe_recall", "summon_draw",
          [expr("dt_summon_type == '今忆召唤' and not dt_summon_submitted"),
           asset("I_RECALL_ONE_TICKET")],
          {"swipe": "Component_Summon::S_RANDOM_SWIPE_1", "delay": 1000, "recheck": True},
          {"set": {"dt_summon_submitted": True}})
    raw["states"][-1].update(sensitive="抽卡", desc="每日一抽：消耗 1 张今忆符咒进行一次今忆召唤。")
    state("summon_draw_timeout", "summon_draw", [expr("elapsed_ms - dt_timer >= 15000")],
          {"fail": "每日一抽未能在15秒内完成召唤确认"})
    state("summon_exit_done", "summon_exit",
          [{"any": [asset("I_BLUE_TICKET", "Component_Summon"), court]}], advance("dispatch_love"))
    state("summon_exit_back", "summon_exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", 1000, "GlobalGame"))

    # 2. Friend love
    for ph in ("dispatch_love", "dispatch_luck", "dispatch_store"):
        state(f"{ph}_time_limit", ph,
              [expr("dt_limit_seconds > 0 and elapsed_ms >= dt_limit_seconds * 1000")],
              advance("done", dt_exit_reason="'time_limit'"))
    state("love_open_time_limit", "love_open",
          [expr("dt_limit_seconds > 0 and elapsed_ms >= dt_limit_seconds * 1000")],
          advance("love_exit", dt_exit_reason="'time_limit'"))
    state("luck_open_time_limit", "luck_open",
          [expr("dt_limit_seconds > 0 and elapsed_ms >= dt_limit_seconds * 1000")],
          advance("luck_exit", dt_exit_reason="'time_limit'"))
    for ph in ("store_gift_room", "sushi_offer"):
        state(f"{ph}_time_limit", ph,
              [expr("dt_limit_seconds > 0 and elapsed_ms >= dt_limit_seconds * 1000")],
              advance("store_return_main", dt_nav_arrived_sub=0, dt_exit_reason="'time_limit'"))
    state("love_skip", "dispatch_love", [expr("not dt_friend_love")], advance("dispatch_luck"))
    state("love_goto_friends", "dispatch_love", [expr("dt_friend_love")],
          advance("love_nav", dt_nav_arrived_sub=0))
    state("love_arrived", "love_nav", [friends, expr("dt_nav_arrived_sub == 1")], advance("love_open"))
    state("love_drive", "love_nav", [], {"navigate": {"destination": "page_friends", "done_var": "dt_nav_arrived_sub"}})
    state("love_panel_ready", "love_open", [asset("I_L_LOVE")], advance("love_collect", dt_timer="elapsed_ms"))
    for btn, dly in (("I_FRIENDSHIP_UP", 1000), ("I_L_FRIENDS", 1000), ("I_FRIEND_TAB", 3000)):
        state(f"love_{btn.lower()}", "love_open", [asset(btn)], click(btn, dly))
    state("love_tap_collect", "love_collect", [asset("I_L_COLLECT")], click("I_L_COLLECT", 1000))
    state("love_reward", "love_collect", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"), advance("love_exit", dt_friend_done=True))
    state("love_timeout", "love_collect", [expr("elapsed_ms - dt_timer >= 2000")],
          advance("love_exit", dt_friend_done=True))
    state("love_exit_done", "love_exit", [court], advance("dispatch_luck"))
    state("love_exit_back", "love_exit", [back_red], click("I_UI_BACK_RED", 1000, "GlobalGame"))

    # 3. Luck msg
    state("luck_skip", "dispatch_luck", [expr("not dt_luck_msg")], advance("dispatch_store"))
    state("luck_goto_friends", "dispatch_luck", [expr("dt_luck_msg")], advance("luck_nav", dt_nav_arrived_sub=0))
    state("luck_arrived", "luck_nav", [friends, expr("dt_nav_arrived_sub == 1")], advance("luck_open"))
    state("luck_drive", "luck_nav", [], {"navigate": {"destination": "page_friends", "done_var": "dt_nav_arrived_sub"}})
    state("luck_panel_ready", "luck_open", [asset("I_LUCK_TITLE")], advance("luck_collect", dt_timer="elapsed_ms"))
    state("luck_friendship_up", "luck_open", [asset("I_FRIENDSHIP_UP")], click("I_FRIENDSHIP_UP", 1000))
    state("luck_ocr_enter", "luck_open",
          [{"ocr_full": {"region": luck_roi, "keyword": "吉闻", "evidence": "complete_keyword"}}],
          {"click_found": True, "delay": 1000, "recheck": True})
    state("luck_bless", "luck_collect", [asset("I_CLICK_BLESS")], click("I_CLICK_BLESS", 1000))
    state("luck_one_click", "luck_collect", [asset("I_ONE_CLICK_BLESS")], click("I_ONE_CLICK_BLESS", 1000))
    state("luck_reward", "luck_collect", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"), advance("luck_exit", dt_luck_done=True))
    state("luck_timeout", "luck_collect", [expr("elapsed_ms - dt_timer >= 2000")],
          advance("luck_exit", dt_luck_done=True))
    state("luck_exit_done", "luck_exit", [court], advance("dispatch_store"))
    state("luck_exit_back", "luck_exit", [back_red], click("I_UI_BACK_RED", 1000, "GlobalGame"))

    # 4. Store sign and the price-based daily AP allowance.
    state("sushi_economic_gate", "dispatch_store", [expr("dt_buy_sushi_count > 0 and not dt_confirm_sushi")],
          {"fail": "每日杂项勾玉购买体力(buy_sushi_count>0)需显式经济确认契约"})
    state("store_skip", "dispatch_store", [expr("not dt_store_sign and dt_buy_sushi_count <= 0")], advance("done"))
    state("store_goto_mall", "dispatch_store", [], advance("store_nav", dt_nav_arrived_sub=0))
    state("store_arrived", "store_nav", [mall, expr("dt_nav_arrived_sub == 1 and dt_store_sign")],
          advance("store_gift_room", dt_gift_cnt=0))
    state("store_arrived_sushi", "store_nav", [mall, expr("dt_nav_arrived_sub == 1 and not dt_store_sign")],
          advance("sushi_enter"))
    state("store_drive", "store_nav", [], {"navigate": {"destination": "page_mall", "done_var": "dt_nav_arrived_sub"}})
    state("store_open_gift_room", "store_gift_room", [asset("I_ROOM_GIFT")], click("I_ROOM_GIFT", 1000))
    state("store_sign_ready", "store_gift_room", [asset("I_GIFT_SIGN")],
          {"click_found": True, "use_match_size": True, "delay": 2500, "recheck": True}, advance("store_sign_reward"))
    state("store_gift_rec", "store_gift_room", [expr("dt_gift_cnt < 4"), asset("I_GIFT_RECOMMEND")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}, {"inc": "dt_gift_cnt"})
    state("store_gift_none", "store_gift_room", [expr("dt_gift_cnt >= 4")],
          advance("store_after_sign"))
    state("store_sign_reward_ok", "store_sign_reward", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"),
          advance("store_after_sign", dt_sign_done=True))
    state("store_sign_reward_skip", "store_sign_reward", [{"not": asset("I_GIFT_SIGN")}],
          advance("store_after_sign", dt_sign_done=True))
    finish_store = advance("store_return_main", dt_nav_arrived_sub=0)
    state("store_after_sign_sushi", "store_after_sign", [expr("dt_buy_sushi_count > 0")], advance("sushi_enter"))
    state("store_after_sign_return", "store_after_sign", [], finish_store)

    jade_region = [f"dt_sushi_currency_{axis}" for axis in ("x", "y", "w", "h")]
    raw["vars"].update(zip(jade_region, (585, 523, 66, 78)))
    raw.setdefault("inline_resources", {})["DailyTriflesSushi::O_JADE_BALANCE"] = {
        "type": "ocr", "mode": "Digit", "roi": [429, 11, 66, 36],
    }
    special = asset("I_SIDE_CHECK_SPECIAL", "RichMan")
    sundry = asset("I_MALL_SUNDRY_CHECK", "RichMan")
    sushi_offer = asset("I_SPECIAL_SUSHI")
    plus = asset("I_BUY_PLUS", "Component_Buy")
    quote = {"all": [plus, {"ocr_single": {"region": [520, 137, 238, 60], "equals": "100体力"}}]}
    jade_icon = asset("I_STORE_COST_TYPE_JADE", region_vars=jade_region, scale_range=[.65, 1.1])
    balance = {"ocr": "DailyTriflesSushi::O_JADE_BALANCE", "mode": "exact_quantity", "var": "dt_sushi_jade"}
    price = {"ocr": "Component_Buy::O_BUY_PRICE", "mode": "exact_quantity", "var": "dt_sushi_price"}
    quantity = {"ocr": "Component_Buy::O_BUY_NUMBER", "mode": "exact_quantity", "var": "dt_sushi_quantity"}
    tap_template = {"click_found": True, "use_match_size": True, "delay": 850, "recheck": True}

    state("sushi_ready", "sushi_enter", [special], advance("sushi_offer"))
    state("sushi_select_special", "sushi_enter", [sundry, asset("I_SIDE_SURE_SPECIAL", "RichMan")], tap_template)
    state("sushi_open_sundry", "sushi_enter", [{"not": sundry}, asset("I_MALL_SUNDRY", "RichMan")], tap_template)
    state("sushi_budget_exhausted", "sushi_offer", [special, expr("dt_sushi_spent + 60 > dt_sushi_max_jade")], finish_store)
    state("sushi_reserve", "sushi_offer", [special, sushi_offer, balance,
          expr("dt_sushi_jade - dt_sushi_jade_reserve < 60")], finish_store)
    state("sushi_quote_open", "sushi_offer", [special, {"not": reward}, {"not": plus}, balance, sushi_offer],
          tap_template, advance("sushi_quote", dt_sushi_jade_before="dt_sushi_jade", dt_timer="elapsed_ms"))
    state("sushi_balance_unreadable", "sushi_offer", [special, sushi_offer, {"not": plus}, {"not": balance}],
          {"fail": "无法核对商店勾玉余额，未购买体力"})
    valid_quote = [
        quote, jade_icon, {"not": asset("I_BUY_RMB", "Component_Buy")}, quantity, price, balance,
        expr("dt_sushi_quantity == 1 and dt_sushi_jade == dt_sushi_jade_before "
             "and dt_sushi_price >= 60 and (dt_sushi_price - 60) % 20 == 0"),
    ]
    cap = expr("(dt_sushi_price - 60) // 20 >= dt_buy_sushi_count "
               "or dt_sushi_spent + dt_sushi_price > dt_sushi_max_jade "
               "or dt_sushi_jade - dt_sushi_price < dt_sushi_jade_reserve")
    cancel_quote = click("C_BUY_CANCEL", 750, "Component_Buy")
    state("sushi_cap_reached", "sushi_quote", [*valid_quote, cap], cancel_quote,
          advance("sushi_closed", dt_timer="elapsed_ms"))
    state("sushi_ready_to_confirm", "sushi_quote",
          [*valid_quote, {"not": cap}, expr("dt_sushi_price > dt_sushi_previous_price")],
          advance("sushi_commit", dt_sushi_quoted_price="dt_sushi_price", dt_timer="elapsed_ms"))
    for index in range(20):
        cost = 60 + 20 * index
        state(f"sushi_purchase_{index}", "sushi_commit",
              [expr(f"dt_sushi_quoted_price == {cost}"), *valid_quote, {"not": cap}, expr(f"dt_sushi_price == {cost}")],
              {"click": [565, 549, 713, 584], "delay": 950, "recheck": True},
              advance("sushi_settle", dt_sushi_spent=f"dt_sushi_spent + {cost}", dt_sushi_previous_price=cost,
                      dt_timer="elapsed_ms"))
        raw["states"][-1].update(sensitive="花勾玉", desc=f"花费 {cost} 勾玉购买 100 点体力。")
    for quoting in ("sushi_quote", "sushi_commit"):
        state(f"{quoting}_invalid", quoting, [quote, expr("elapsed_ms - dt_timer >= 8500")],
              cancel_quote, advance("sushi_invalid_closed", dt_timer="elapsed_ms"))
        state(f"{quoting}_timeout", quoting, [expr("elapsed_ms - dt_timer >= 12000")],
              {"fail": "未识别 100 体力的勾玉报价"})
    state("sushi_closed_return", "sushi_closed", [special, {"not": plus}], finish_store)
    state("sushi_invalid_closed_fail", "sushi_invalid_closed", [special, {"not": plus}],
          {"fail": "100 体力的数量、勾玉报价或扣款前余额未通过核对，已取消"})
    for closing in ("sushi_closed", "sushi_invalid_closed"):
        state(f"{closing}_timeout", closing, [expr("elapsed_ms - dt_timer >= 8000")],
              {"fail": "体力购买报价尚未确认关闭"})
    state("sushi_reward", "sushi_settle", [reward, expr("elapsed_ms - dt_timer < 14000")],
          click("C_UI_REWARD", 400, "GlobalGame"))
    state("sushi_debit_verified", "sushi_settle", [special, {"not": plus}, {"not": reward}, balance,
          expr("dt_sushi_jade == dt_sushi_jade_before - dt_sushi_previous_price")],
          {"inc": "dt_sushi_purchases"}, advance("sushi_offer"))
    state("sushi_debit_missing", "sushi_settle", [expr("elapsed_ms - dt_timer >= 14000")],
          {"fail": "体力购买后缺少勾玉扣款记录，停止后续购买"})

    state("store_returned_main", "store_return_main", [court, expr("dt_nav_arrived_sub == 1")], advance("done"))
    state("store_return_drive", "store_return_main", [],
          {"navigate": {"destination": "page_main", "done_var": "dt_nav_arrived_sub"}})

    state("complete_target_prep", "done", [expr("dt_next_delay_s > 0")],
          advance("stop_target", dt_target_delay_s="dt_next_delay_s", dt_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "每日琐事已完成，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "DailyTrifles",
                "delay_seconds_var": "dt_target_delay_s",
                "observed_ms_var": "dt_observed_ms",
            },
            "evidence": {"scope": "daily_trifles_target_schedule"},
        }
    })
    state("complete", "done", [], {
        "stop": {
            "reason": "每日琐事已完成",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "DailyTrifles",
            "evidence": {"scope": "daily_trifles_native_path"},
        }
    })

    raw["oas_daily_trifles_contract"] = {
        "source": DAILY_TRIFLES_ENTRY,
        "source_pins": {**DAILY_TRIFLES_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "daily_trifles_summon_and_jade_sushi_live",
            "blocking": True,
            "requirement": "Bind normal and recall summon with explicit confirmation, and verify the live AP purchase debit.",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_weekly_trifles_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS WeeklyTrifles workflow with summon and touch-fish ticket guards."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, WEEKLY_TRIFLES_PINS, "WeeklyTrifles")
    nav = compile_navigation_family(
        source, resources, prefix="wt_nav", destination="page_main",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_weekly_trifles_natively_staged", title="每周琐事", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 900
    bind_schedule(source, raw)
    raw["params"]["oas_success_seconds"]["default"] = 604800
    raw["params"].update(
        wt_share_collect={"default": True},
        wt_share_area_boss={"default": True},
        wt_share_secret={"default": True},
        wt_save_touch_fish={"default": False},
        wt_confirm_touch_fish={"default": False},
        wt_touch_fish_max_tickets={"default": 0, "min": 0, "max": 999},
        wt_broken_amulet={"default": 100, "min": 0, "max": 2000},
        wt_confirm_broken_amulet={"default": False},
        wt_ba_batch_size={"default": 10, "choices": [10, 50]},
        wt_limit_seconds={"default": 0, "min": 0, "max": 7200},
        wt_next_monday_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        wt_phase="dispatch_collect", wt_nav_sub=0, wt_timer=0, wt_collect_done=False,
        wt_ab_done=False, wt_secret_done=False,
        wt_touch_tickets=-1, wt_touch_cost=-1, wt_touch_tickets_before=-1, wt_touch_quoted_cost=-1,
        wt_touch_submitted=False, wt_touch_saved=False,
        wt_ba_remain=-1, wt_ba_before=-1, wt_ba_summoned=0, wt_broken_done=False,
        wt_target_delay_s=0, wt_observed_ms=0, wt_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/WeeklyTrifles.yaml", "upstream/oas/GlobalGame.yaml",
        "upstream/oas/Component_GeneralBattle.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("WeeklyTrifles", "GlobalGame", "Component_GeneralBattle")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"wt_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"wt_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"wt_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="WeeklyTrifles", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, delay=1000, ns="WeeklyTrifles"):
        return _click_from(docs, name, ns, delay)

    next(step for step in raw["states"] if step["id"] == "wt_nav_returned")["when"]["all"].append(phase("navigate"))
    next(step for step in raw["states"] if step["id"] == "wt_nav_drive")["when"] = phase("navigate")

    collection = raw["navigation"]["pages"]["page_collection"]["when"]
    area_boss = raw["navigation"]["pages"]["page_area_boss"]["when"]
    secret_zones = raw["navigation"]["pages"]["page_secret_zones"]["when"]
    exploration = raw["navigation"]["pages"]["page_exploration"]["when"]
    court = raw["navigation"]["pages"]["page_main"]["when"]
    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    back_red = asset("I_UI_BACK_RED", "GlobalGame")
    back_yellow = asset("I_UI_BACK_YELLOW", "GlobalGame")
    back_blue = asset("I_UI_BACK_BLUE", "GlobalGame")

    # 1. Share collect
    for ph in ("dispatch_ab", "dispatch_secret", "dispatch_guarded", "dispatch_broken"):
        state(f"{ph}_time_limit", ph,
              [expr("wt_limit_seconds > 0 and elapsed_ms >= wt_limit_seconds * 1000")],
              advance("finished", wt_exit_reason="'time_limit'"))
    for ph, back_ph in (("collect_enter", "collect_back"), ("ab_enter", "ab_back"),
                        ("secret_enter", "secret_back"), ("broken_loop", "broken_exit")):
        state(f"{ph}_time_limit", ph,
              [expr("wt_limit_seconds > 0 and elapsed_ms >= wt_limit_seconds * 1000")],
              advance(back_ph, wt_exit_reason="'time_limit'"))
    state("collect_skip", "dispatch_collect", [expr("not wt_share_collect")], advance("dispatch_ab"))
    state("collect_go", "dispatch_collect", [expr("wt_share_collect")], advance("collect_nav", wt_nav_sub=0))
    state("collect_arrived", "collect_nav", [collection, expr("wt_nav_sub == 1")], advance("collect_enter"))
    state("collect_drive", "collect_nav", [],
          {"navigate": {"destination": "page_collection", "done_var": "wt_nav_sub"}})
    state("collect_logo_ready", "collect_enter", [asset("I_WT_LOGO")], advance("collect_share"))
    state("collect_shiki", "collect_enter", [asset("I_WT_SHIKIAGMI")], click("I_WT_SHIKIAGMI", 1000))
    state("collect_share_btn", "collect_enter", [asset("I_WT_SHARE")], click("I_WT_SHARE", 1000))
    state("collect_qr_seen", "collect_share", [asset("I_WT_QR_CODE")], advance("collect_wait", wt_timer="elapsed_ms"))
    state("collect_wechat_tap", "collect_share", [asset("I_WT_COLLECT_WECHAT")],
          {"click_found": True, "use_match_size": True, "delay": 4000, "recheck": True})
    state("collect_reward", "collect_wait", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"), advance("collect_back", wt_collect_done=True))
    state("collect_qr_click", "collect_wait", [asset("I_WT_QR_CODE")], click("C_WT_WECHAT", 2800))
    state("collect_timeout", "collect_wait", [expr("elapsed_ms - wt_timer >= 3000")],
          advance("collect_back", wt_collect_done=True))
    state("collect_back_done", "collect_back", [asset("I_WT_SHIKIAGMI")], advance("dispatch_ab"))
    state("collect_back_red", "collect_back", [back_red], click("I_UI_BACK_RED", 1000, "GlobalGame"))
    state("collect_back_yellow", "collect_back", [back_yellow], click("I_UI_BACK_YELLOW", 1000, "GlobalGame"))

    # 2. Share area boss
    state("ab_skip", "dispatch_ab", [expr("not wt_share_area_boss")], advance("dispatch_secret"))
    state("ab_go", "dispatch_ab", [expr("wt_share_area_boss")], advance("ab_nav", wt_nav_sub=0))
    state("ab_arrived", "ab_nav", [area_boss, expr("wt_nav_sub == 1")], advance("ab_enter"))
    state("ab_drive", "ab_nav", [], {"navigate": {"destination": "page_area_boss", "done_var": "wt_nav_sub"}})
    state("ab_no_day", "ab_enter", [asset("I_WT_NO_DAY")], advance("ab_back", wt_ab_done=True))
    state("ab_wechat_seen", "ab_enter", [asset("I_WT_AB_WECHAT")], advance("ab_check_jade"))
    state("ab_day_battle", "ab_enter", [asset("I_WT_DAY_BATTLE")], click("I_WT_DAY_BATTLE", 2000))
    state("ab_share_btn", "ab_enter", [asset("I_WT_SHARE_AB")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("ab_click", "ab_enter", [], click("C_WT_AB_CLICK", 2500))
    state("ab_already_got", "ab_check_jade", [{"not": asset("I_WT_AB_JADE")}], advance("ab_back", wt_ab_done=True))
    state("ab_need_share", "ab_check_jade", [asset("I_WT_AB_JADE")],
          click("I_WT_AB_WECHAT", 2500), advance("ab_qr_wait", wt_timer="elapsed_ms"))
    state("ab_reward", "ab_qr_wait", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"), advance("ab_back", wt_ab_done=True))
    state("ab_qr_click", "ab_qr_wait", [asset("I_WT_QR_CODE")], click("C_WT_WECHAT", 4800))
    state("ab_timeout", "ab_qr_wait", [expr("elapsed_ms - wt_timer >= 7000")], advance("ab_back", wt_ab_done=True))
    state("ab_back_done", "ab_back", [{"any": [asset("I_WT_DAY_BATTLE"), exploration]}], advance("dispatch_secret"))
    for name, b in (("red", "I_UI_BACK_RED"), ("blue", "I_UI_BACK_BLUE"), ("yellow", "I_UI_BACK_YELLOW")):
        state(f"ab_back_{name}", "ab_back", [asset(b, "GlobalGame")], click(b, 1000, "GlobalGame"))

    # 3. Share secret
    state("secret_skip", "dispatch_secret", [expr("not wt_share_secret")], advance("dispatch_guarded"))
    state("secret_go", "dispatch_secret", [expr("wt_share_secret")], advance("secret_nav", wt_nav_sub=0))
    state("secret_arrived", "secret_nav", [secret_zones, expr("wt_nav_sub == 1")], advance("secret_enter"))
    state("secret_drive", "secret_nav", [], {"navigate": {"destination": "page_secret_zones", "done_var": "wt_nav_sub"}})
    state("secret_wechat_seen", "secret_enter", [asset("I_WT_SE_WECHAT")], advance("secret_check_jade"))
    state("secret_enter_btn", "secret_enter", [asset("I_WT_ENTER_SE")], click("I_WT_ENTER_SE", 1000))
    state("secret_share_btn", "secret_enter", [asset("I_WT_SE_SHARE")], click("I_WT_SE_SHARE", 5000))
    state("secret_uncompleted_exit", "secret_enter", [asset("I_WT_SE_RANK"), {"not": asset("I_WT_SE_SHARE")}],
          advance("secret_back", wt_secret_done=True))
    state("secret_already_got", "secret_check_jade", [{"not": asset("I_WT_SE_JADE")}],
          advance("secret_back", wt_secret_done=True))
    state("secret_need_share", "secret_check_jade", [asset("I_WT_SE_JADE")],
          click("I_WT_SE_WECHAT", 2500), advance("secret_qr_wait", wt_timer="elapsed_ms"))
    state("secret_reward", "secret_qr_wait", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"), advance("secret_back", wt_secret_done=True))
    state("secret_qr_click", "secret_qr_wait", [asset("I_WT_QR_CODE")], click("C_WT_WECHAT", 4800))
    state("secret_timeout", "secret_qr_wait", [expr("elapsed_ms - wt_timer >= 7000")],
          advance("secret_back", wt_secret_done=True))
    state("secret_back_done", "secret_back", [court], advance("dispatch_guarded"))
    state("secret_back_blue", "secret_back", [back_blue], click("I_UI_BACK_BLUE", 1000, "GlobalGame"))
    state("secret_back_yellow", "secret_back", [back_yellow], click("I_UI_BACK_YELLOW", 1000, "GlobalGame"))

    # 4. Touch Fish ticket storage, after the three sharing paths.
    guild = raw["navigation"]["pages"]["page_guild"]["when"]
    touch_fish = raw["navigation"]["pages"]["page_touch_fish"]["when"]
    fold_open = asset("I_WT_FOLD_WINDOW")
    upcoming = asset("I_WT_SAVE_ALL")
    confirm_storage = asset("I_WT_TF_CONFIRM")
    storage_receipt = asset("I_WT_TF_SAVE_SUCCESS")
    last_week = asset("I_WT_LAST_SAVE")
    free_popup = asset("I_WT_HAPPY_GET")
    tickets = {"ocr": "WeeklyTrifles::O_WT_LUCKY_TICKETS", "mode": "counter_current", "var": "wt_touch_tickets"}
    cost = {"ocr": "WeeklyTrifles::O_WT_SAVE_COST", "mode": "exact_quantity", "var": "wt_touch_cost"}
    state("touch_fish_gate", "dispatch_guarded", [expr("wt_save_touch_fish and not wt_confirm_touch_fish")],
          {"fail": "惠比寿摸鱼消耗福运御守存储次数需显式确认契约"})
    state("touch_fish_skip", "dispatch_guarded", [expr("not wt_save_touch_fish")], advance("dispatch_broken"))
    state("touch_goto_guild", "dispatch_guarded", [], advance("touch_guild", wt_nav_sub=0))
    state("touch_guild_arrived", "touch_guild", [guild, expr("wt_nav_sub == 1")], advance("touch_unfold"))
    state("touch_guild_drive", "touch_guild", [], {"navigate": {"destination": "page_guild", "done_var": "wt_nav_sub"}})
    state("touch_fold_open", "touch_unfold", [guild, fold_open], advance("touch_nav", wt_nav_sub=0))
    state("touch_unfold_panel", "touch_unfold", [guild, asset("I_WT_OPEN_FOLD_WINDOW")],
          click("I_WT_OPEN_FOLD_WINDOW"))
    state("touch_activity_arrived", "touch_nav", [touch_fish, expr("wt_nav_sub == 1")],
          advance("touch_inbox", wt_timer="elapsed_ms"))
    state("touch_activity_drive", "touch_nav", [], {"navigate": {"destination": "page_touch_fish", "done_var": "wt_nav_sub"}})
    state("touch_close_last_week", "touch_inbox", [last_week], click("C_RANDOM_LEFT", 650, "Component_GeneralBattle"))
    state("touch_close_entry_notice", "touch_inbox", [free_popup], click("I_WT_HAPPY_GET", 700))
    state("touch_quote_available", "touch_inbox", [touch_fish, {"not": last_week}, {"not": free_popup}, upcoming],
          advance("touch_offer", wt_timer="elapsed_ms"))
    finish_touch = advance("touch_return", wt_nav_sub=0)
    state("touch_no_storage_available", "touch_inbox", [touch_fish, {"not": last_week}, {"not": free_popup},
          {"not": upcoming}, {"not": confirm_storage}, expr("elapsed_ms - wt_timer >= 3000")], finish_touch)

    quote = [touch_fish, upcoming, {"not": free_popup}, {"not": last_week}, {"not": confirm_storage}, tickets, cost]
    within_budget = expr("wt_touch_cost >= 0 and wt_touch_cost <= wt_touch_tickets "
                         "and wt_touch_cost <= wt_touch_fish_max_tickets")
    state("touch_storage_too_costly", "touch_offer", [*quote, {"not": within_budget}], finish_touch)
    state("touch_request_storage", "touch_offer", [*quote, within_budget],
          click("I_WT_SAVE_ALL", 850), advance("touch_confirm", wt_touch_tickets_before="wt_touch_tickets",
                                              wt_touch_quoted_cost="wt_touch_cost", wt_timer="elapsed_ms"))
    raw["states"][-1].update(sensitive="购买", desc="按画面已核对的票数消耗福运御守，存储本周全部摸鱼次数。")
    state("touch_offer_unreadable", "touch_offer", [expr("elapsed_ms - wt_timer >= 9000")],
          {"fail": "摸鱼储存缺少可核对的福运御守余额或报价"})
    state("touch_submit_same_storage", "touch_confirm", [confirm_storage, {"not": free_popup}, {"not": last_week},
          tickets, cost, expr("not wt_touch_submitted and wt_touch_tickets == wt_touch_tickets_before "
                             "and wt_touch_cost == wt_touch_quoted_cost")],
          click("I_WT_TF_CONFIRM", 850), {"set": {"wt_touch_submitted": True}})
    state("touch_verify_storage", "touch_confirm", [touch_fish, storage_receipt, {"not": upcoming}, {"not": confirm_storage},
          tickets, expr("wt_touch_tickets == wt_touch_tickets_before - wt_touch_quoted_cost")],
          {"set": {"wt_touch_saved": True}}, finish_touch)
    state("touch_storage_result_unknown", "touch_confirm", [expr("elapsed_ms - wt_timer >= 12000")],
          {"fail": "摸鱼存储缺少相同报价、成功标记或票数扣款记录，停止再次储存"})
    state("touch_returned", "touch_return", [court, expr("wt_nav_sub == 1")], advance("dispatch_broken"))
    state("touch_return_drive", "touch_return", [], {"navigate": {"destination": "page_main", "done_var": "wt_nav_sub"}})

    # 5. Broken-amulet batch summon with explicit confirmation & ticket-deduction verification
    summon_page = raw["navigation"]["pages"]["page_summon"]["when"]
    ba_remain = {"ocr": "WeeklyTrifles::O_BA_AMOUNT_1", "mode": "exact_quantity", "var": "wt_ba_remain"}
    state("broken_amulet_gate", "dispatch_broken", [expr("wt_broken_amulet > 0 and not wt_confirm_broken_amulet")],
          {"fail": "每周破碎符咒批量召唤需显式抽卡确认契约"})
    state("broken_amulet_goto", "dispatch_broken", [expr("wt_broken_amulet > 0 and wt_confirm_broken_amulet")],
          advance("broken_nav", wt_nav_sub=0, wt_ba_summoned=0))
    state("broken_nav_arrived", "broken_nav", [summon_page, expr("wt_nav_sub == 1")], advance("broken_loop"))
    state("broken_nav_drive", "broken_nav", [], {"navigate": {"destination": "page_summon", "done_var": "wt_nav_sub"}})

    state("broken_target_reached", "broken_loop", [expr("wt_ba_summoned >= wt_broken_amulet")],
          advance("broken_exit", wt_broken_done=True))
    state("broken_empty", "broken_loop", [ba_remain, expr("wt_ba_remain <= 0")],
          advance("broken_exit", wt_broken_done=True))
    state("broken_summon_enter", "broken_loop",
          [asset("I_BM_ENTER"), ba_remain, expr("wt_ba_remain > 0 and wt_ba_summoned < wt_broken_amulet")],
          click("I_BM_ENTER", 800),
          advance("broken_settle", wt_ba_before="wt_ba_remain", wt_timer="elapsed_ms"))
    raw["states"][-1].update(sensitive="抽卡", desc="破碎符咒批量召唤（首轮），确认后校验破碎符咒余量扣减。")
    state("broken_summon_again", "broken_loop",
          [asset("I_BM_AGAIN"), ba_remain, expr("wt_ba_remain > 0 and wt_ba_summoned < wt_broken_amulet")],
          click("I_BM_AGAIN", 800),
          advance("broken_settle", wt_ba_before="wt_ba_remain", wt_timer="elapsed_ms"))
    raw["states"][-1].update(sensitive="抽卡", desc="破碎符咒批量召唤（续抽），确认后校验破碎符咒余量扣减。")
    state("broken_settle_ok", "broken_settle",
          [asset("I_BM_AGAIN"), ba_remain, expr("wt_ba_remain < wt_ba_before")],
          advance("broken_loop", wt_ba_summoned="wt_ba_summoned + wt_ba_batch_size"))
    state("broken_settle_skip_anim", "broken_settle",
          [{"not": asset("I_BM_AGAIN")}, expr("elapsed_ms - wt_timer < 10000")],
          click("C_RANDOM_LEFT", 800, "Component_GeneralBattle"))
    state("broken_settle_timeout", "broken_settle", [expr("elapsed_ms - wt_timer >= 10000")],
          {"fail": "破碎符咒召唤后缺少余量扣减验证，停止后续召唤"})
    state("broken_exit_confirm", "broken_exit", [asset("I_BM_CONFIRM")], click("I_BM_CONFIRM", 800))
    state("broken_exit_done", "broken_exit", [{"not": asset("I_BM_CONFIRM")}], advance("finished"))

    state("complete_direct", "dispatch_broken", [expr("wt_broken_amulet <= 0")], advance("finished"))
    state("complete_target_prep", "finished", [expr("wt_next_monday_delay_s > 0")],
          advance("stop_target", wt_target_delay_s="wt_next_monday_delay_s", wt_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "每周琐事已完成，已按每周一排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "WeeklyTrifles",
                "delay_seconds_var": "wt_target_delay_s",
                "observed_ms_var": "wt_observed_ms",
            },
            "evidence": {"scope": "weekly_trifles_monday_target"},
        }
    })
    state("complete", "finished", [], {
        "stop": {
            "reason": "每周琐事已完成",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "WeeklyTrifles",
            "evidence": {"scope": "weekly_trifles_native_path"},
        }
    })

    raw["oas_weekly_trifles_contract"] = {
        "source": WEEKLY_TRIFLES_ENTRY,
        "source_pins": {**WEEKLY_TRIFLES_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "weekly_trifles_summon_and_touch_fish_live",
            "blocking": True,
            "requirement": "Bind broken-amulet batch summons with explicit confirmation, and verify Touch Fish charges and receipts on live frames.",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
