"""Pinned OAS RichMan, SixRealms, Hyakkiyakou, and AutoCheckinBigGod workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import compile_general_battle
from .oas_rich_man_scales import bind_scales_demon, bind_scales_sea
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_resource_file, load_workflow
from ..yamlio import load_yaml


RICH_MAN_ENTRY = "tasks/RichMan/script_task.py"
RICH_MAN_PINS = {
    RICH_MAN_ENTRY: "411f263fd0a8f6f708baf102f812158cf2baf74565c2e057652dddde37a69a11",
    "tasks/RichMan/config.py": "701a8b1362a9a58fe032a1b149b9654fd0c3f7b6274cd97793a076df569aa242",
    "tasks/RichMan/assets.py": "f8fe31ed6779426125bdbd33d3a24219d806dc51b68a8d97d6a50a211d83fb21",
    "tasks/RichMan/guild.py": "e1e4aac8050546803247064231806d3fc0166e2920e35b6f5a868cf5e7bd6d21",
    "tasks/RichMan/shrine.py": "1eaaf1f21b5f76a038be68b0f421c6273ec68c35a03a18d67deba05f44465a12",
    "tasks/RichMan/thousand_things.py": "37589d6fe93cd94a8afe594358ed5d67caca2a6e9da3c64a0d9ccc5b3a971563",
    "tasks/RichMan/mall/mall.py": "2657f8e5c0c00fa47414a25c0c2617815841d72a444e0134a49d38beae095f57",
    "tasks/RichMan/mall/navbar.py": "6b3582f738424f324bfb1225653a1782ac4b243686898d6d395af34cfd2a248e",
    "tasks/RichMan/mall/scales.py": "3048573ab94e363e09ea7efc3c16c4856106482c2aacfaa3cb4bc75a816d023a",
    "tasks/RichMan/mall/bondlings.py": "d4743755cadfa7efec2b9ecf3afb1665661490c24b425c0da4db8b7064060010",
    "tasks/Component/Buy/buy.py": "ec3b1b01dc51fd63b084c5992c9dd2e1d04cb19645f9e79aaa22c19f415e3355",
}

SIX_REALMS_ENTRY = "tasks/SixRealms/script_task.py"
SIX_REALMS_PINS = {
    SIX_REALMS_ENTRY: "bfc070d9e4eb2ed07abffe8eea73c050555803840ab884eb43e1432c2bfb4940",
    "tasks/SixRealms/config.py": "ceac3e682c86ac6fe2d10a328d11113ebb9a7251b7c941d0f3bf47a29a33a789",
    "tasks/SixRealms/assets.py": "24360de96faa216b5ac41eadf888b90ac3a75ed7191e02af372f061d63e1498b",
    "tasks/SixRealms/common.py": "6b29dbb4d3927264687e58f9d57af45ac4e31d9df376d25fd16430b57253f7c7",
    "tasks/SixRealms/oas_ocr.py": "b357e3e2484f8d175600c7d705db4c941d945c16c1e241b81d52921da367046c",
    "tasks/SixRealms/moon_sea/moon_sea.py": "a0b912552e28c7e2d8640e7c060b3c778803be4239ac59d7cb69e7ca221c55d6",
    "tasks/SixRealms/moon_sea/map.py": "d97c5bf53b45cd2cd47e443a90cd6230fd4ee8222a1b838f61512b32c81458a7",
    "tasks/SixRealms/moon_sea/skills.py": "b539b87e9ef442f7dddb75671b1418d17d1f1b56e2a3ee832c027cc9212889fc",
}

HYA_ENTRY = "tasks/Hyakkiyakou/script_task.py"
HYA_PINS = {
    HYA_ENTRY: "2a6cdf16d377dfd3a51fa3fc39c866bb7b6dfcefd6cbdcc9a4547d5ff4825bb6",
    "tasks/Hyakkiyakou/config.py": "abcda5158010b97ddb42e86362a2534b60532765f93e0e8ddab35135c4ec9756",
    "tasks/Hyakkiyakou/assets.py": "a7b839b99e01f511f52c2d1d457af2a717f6dbb603056e12f07569c3a524e333",
    "tasks/Hyakkiyakou/agent/agent.py": "b12a882cc3372146371cd625e0e5c7678a37cc5456095b68a83819c83db15363",
    "tasks/Hyakkiyakou/slave/hya_slave.py": "e0950976d3a4431a127bcbb99455ed7f887e6ad4b9ce31545cd3d1448c20e4c0",
}

BIG_GOD_ENTRY = "tasks/AutoCheckinBigGod/script_task.py"
BIG_GOD_PINS = {
    BIG_GOD_ENTRY: "e0aea76002a6b8736686498b1e5a0d6db0ed461f056b0fcf84ab0a57fff9f913",
    "tasks/AutoCheckinBigGod/config.py": "63b6166dd34d6f2cc332496def0539abe722d4efa69361da39dededab9ceb268",
    "tasks/AutoCheckinBigGod/assets.py": "d26b93e2da691691aafe55a60168bb92c60a994c038fdbc5ea61e9be8989727a",
}


def _verify_pins(source: Path, pins: dict[str, str], label: str) -> None:
    for rel, expected in pins.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"{label} source fingerprint mismatch: {rel}")


def _click_from(docs: dict, name: str, ns: str, delay: int = 1000, recheck: bool = True) -> dict:
    spec = docs[ns][name]
    if spec["type"] in ("click", "long_click"):
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    return {"click": target, "delay": delay, "recheck": recheck}


def _wire_nav(raw: dict, prefix: str, phase_fn, advance_fn, next_phase: str) -> None:
    arrived = next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_returned")
    arrived["when"]["all"].append(phase_fn("navigate"))
    arrived["do"] = [advance_fn(next_phase)]
    next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_drive")["when"] = phase_fn("navigate")


def _wire_battle(raw: dict, body: dict, contract: dict, phase_fn, advance_fn,
                 attempts_var: str, wins_var: str, return_phase: str) -> dict:
    outputs = contract["outputs"]
    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    reset[outputs["current_count"]] = attempts_var
    for step in body["states"]:
        step["when"] = {"all": [phase_fn("in_battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance_fn(return_phase, **{
                attempts_var: outputs["current_count"],
                wins_var: f"{wins_var} + {outputs['win']}",
            })]
        raw["states"].append(step)
    return reset


def _bind_component_buy_shop(
    raw, docs, state, advance, click, asset, expr, *,
    shop_key: str, enter_phase: str, next_phase: str,
    screen_guard, balance_ocr: str, budget_param: str, reserve_param: str,
    sensitive_label: str, items: list[tuple[str, str, str | None, str, int]],
    exit_states_fn=None, stock_ocr=None, balance_mode="exact_quantity",
    buy_until_exhausted=False, extra_reward=None, quote_identity=None, confirm_rect=None,
):
    """Bind a Component_Buy-based shop with exact-quantity balance, reserve, budget, RMB guard, and debit check."""
    more = asset("I_BUY_PLUS", "Component_Buy")
    rmb = asset("I_BUY_RMB", "Component_Buy")
    reward = {"any": [asset("I_UI_REWARD", "GlobalGame", threshold=0.6),
                      asset("I_BUY_SUCCESS", "Component_Buy")]}
    bal_var = f"rm_{shop_key}_balance"
    bal_before_var = f"rm_{shop_key}_balance_before"
    spent_var = f"rm_{shop_key}_spent"
    offer_var = f"rm_{shop_key}_offer"
    balance = {"ocr": balance_ocr, "mode": balance_mode, "var": bal_var}
    price = {"ocr": "Component_Buy::O_BUY_PRICE", "mode": "exact_quantity", "var": "rm_price"}
    amount = {"ocr": "Component_Buy::O_BUY_NUMBER", "mode": "exact_quantity", "var": "rm_quantity",
              "test": "rm_quantity == 1"}
    raw["vars"].update({
        offer_var: 0, bal_var: -1, bal_before_var: -1, spent_var: 0,
    })
    bought_var = f"rm_{shop_key}_bought"
    stock_var = f"rm_{shop_key}_stock"
    stock_before_var = f"rm_{shop_key}_stock_before"
    stock_debits = []
    if stock_ocr is not None:
        raw["vars"].update({bought_var: 0, stock_var: -1, stock_before_var: -1})

    def time_limit(ms: int):
        return expr(f"elapsed_ms - rm_started >= {ms}")

    offer_phase = f"{shop_key}_offer"
    quote_phase = f"{shop_key}_quote"
    commit_phase = f"{shop_key}_commit"
    settle_phase = f"{shop_key}_settle"
    cancel_phase = f"{shop_key}_cancel"
    exit_phase = f"{shop_key}_exit" if exit_states_fn else next_phase

    for idx, (param_name, btn_asset, dialog_asset, title, unit_cost) in enumerate(items):
        tag = f"{shop_key}_{idx}"
        arm = expr(f"{offer_var} == {idx}")
        counters = {offer_var: idx + 1}
        if stock_ocr is not None:
            counters[bought_var] = 0
        following = advance(offer_phase, **counters)
        item_btn = asset(btn_asset)
        dialog = asset(dialog_asset) if dialog_asset else {"any": [more, asset("I_BUY_ADD", "Component_Buy"), price]}

        disabled = f"not {param_name}" if stock_ocr is None or buy_until_exhausted else f"{bought_var} >= {param_name}"
        state(f"{tag}_skip_disabled", offer_phase, [arm, expr(disabled)], following)
        state(f"{tag}_unavailable", offer_phase, [arm, screen_guard, {"not": item_btn}], following)
        state(f"{tag}_budget_depleted", offer_phase, [arm, screen_guard, expr(f"{spent_var} + {unit_cost} > {budget_param}")], following)
        stock_guard = []
        open_updates = {bal_before_var: bal_var}
        if stock_ocr is not None:
            stock = {"ocr": stock_ocr[param_name], "mode": "exact_quantity", "var": stock_var}
            state(f"{tag}_stock_depleted", offer_phase, [arm, screen_guard, item_btn, stock, expr(f"{stock_var} == 0")],
                  following)
            state(f"{tag}_unreadable_stock", offer_phase, [arm, screen_guard, item_btn, {"not": stock}],
                  {"fail": f"{title}缺少有效库存读数，停止采购"})
            stock_guard = [stock, expr(f"{stock_var} > 0")]
            stock_debits.append({"all": [arm, stock, expr(f"{stock_var} == {stock_before_var} - 1")]})
            open_updates[stock_before_var] = stock_var
            if not buy_until_exhausted:
                state(f"{tag}_balance_cannot_fulfil_minimum", offer_phase,
                      [arm, screen_guard, item_btn, *stock_guard, balance,
                       expr(f"{bought_var} == 0 and {param_name} > 1 and {stock_var} > 1 and {bal_var} < {2 * unit_cost}")],
                      following)
        state(f"{tag}_balance_low", offer_phase, [arm, screen_guard, item_btn, balance,
              expr(f"{bal_var} - {reserve_param} < {unit_cost}")], following)
        state(f"{tag}_open", offer_phase, [arm, screen_guard, item_btn, *stock_guard, balance,
              expr(f"{bal_var} - {reserve_param} >= {unit_cost} and {spent_var} + {unit_cost} <= {budget_param}")],
              click(btn_asset, "RichMan", 800),
              advance(quote_phase, rm_started="elapsed_ms", **open_updates))
        state(f"{tag}_unreadable_balance", offer_phase, [arm, screen_guard, item_btn],
              {"fail": f"{title}缺少有效货币余额读数，停止采购"})

        qty_one = {"all": [more, amount]} if stock_ocr is not None else {"any": [{"not": more}, {"all": [more, amount]}]}
        identity = [quote_identity] if quote_identity is not None else []
        quote_ok = [arm, dialog, {"not": rmb}, *identity, qty_one, price, balance,
                    expr(f"rm_price == {unit_cost} and {bal_var} == {bal_before_var} and "
                         f"rm_price <= {bal_var} - {reserve_param} and "
                         f"{spent_var} + rm_price <= {budget_param}")]
        state(f"{tag}_quote_ready", quote_phase, quote_ok,
              advance(commit_phase, rm_quoted_price="rm_price", rm_started="elapsed_ms"))
        state(f"{tag}_cancel_rmb", quote_phase, [arm, rmb],
              click("C_BUY_CANCEL", "Component_Buy", 600), advance(cancel_phase, rm_started="elapsed_ms"))
        state(f"{tag}_reject_quote", quote_phase, [arm, dialog, time_limit(3000)],
              click("C_BUY_CANCEL", "Component_Buy", 600), advance(cancel_phase, rm_started="elapsed_ms"))
        state(f"{tag}_dialog_missing", quote_phase, [arm, time_limit(9000)],
              {"fail": f"未确认{title}购买窗口"})

        buttons = [(True, "C_BUY_MORE")]
        if stock_ocr is None:
            buttons.append((False, "C_BUY_ONE"))
        for is_multi, button in buttons:
            dialog_kind = more if is_multi else {"not": more}
            commit_click = {"click": confirm_rect, "delay": 800, "recheck": True} if is_multi and confirm_rect else (
                click(button, "Component_Buy", 800))
            state(f"{tag}_buy_{'multi' if is_multi else 'single'}", commit_phase,
                  [*quote_ok, dialog_kind, expr("rm_price == rm_quoted_price")],
                  commit_click,
                  advance(settle_phase, **{spent_var: f"{spent_var} + rm_quoted_price", "rm_started": "elapsed_ms"}))
            raw["states"][-1].update(
                sensitive=sensitive_label,
                desc=f"购买一件{title}，本次花费 {unit_cost}，确认后重新核对价格、余额和剩余预算。",
            )
        state(f"{tag}_changed_quote", commit_phase, [arm, time_limit(9000)],
              {"fail": f"{title}报价变化，未提交购买"})
        state(f"{tag}_cancel_done", cancel_phase, [arm, screen_guard, {"not": more}], following)

    state(f"{shop_key}_all_done", offer_phase, [screen_guard, expr(f"{offer_var} >= {len(items)}")], advance(exit_phase))
    if extra_reward is not None:
        reward_guard, reward_dismiss = extra_reward
        state(f"{shop_key}_extra_reward", settle_phase, [reward_guard], reward_dismiss)
        reward = {"any": [reward, reward_guard]}
    state(f"{shop_key}_reward", settle_phase, [reward], click("C_UI_REWARD", "GlobalGame", 400))
    debit = {offer_var: f"{offer_var} + 1"} if stock_ocr is None else {bought_var: f"{bought_var} + 1"}
    verified_stock = [{"any": stock_debits}] if stock_debits else []
    state(f"{shop_key}_debit_ok", settle_phase, [screen_guard, {"not": reward}, balance,
          expr(f"{bal_var} == {bal_before_var} - rm_quoted_price"), *verified_stock],
          {"inc": "rm_transactions"}, advance(offer_phase, **debit))
    state(f"{shop_key}_debit_missing", settle_phase, [time_limit(12000)],
          {"fail": f"{shop_key} 购买动作已尝试，缺少{'余额扣款或库存变化' if stock_debits else '余额扣款'}验证，停止后续采购"})
    state(f"{shop_key}_cancel_unknown", cancel_phase, [time_limit(10000)],
          {"fail": f"{shop_key} 购买弹窗尚未确认关闭"})
    if exit_states_fn:
        exit_states_fn(exit_phase, next_phase)


def compile_rich_man_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS RichMan (大富翁/多商店采购) workflow with per-currency budget & confirmation guards."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, RICH_MAN_PINS, "RichMan")
    nav = compile_navigation_family(
        source, resources, prefix="rm_nav", destination="page_mall",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_rich_man_natively_staged", title="大富翁(多商店采购)", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 1200
    bind_schedule(source, raw)
    raw["params"].update(
        rm_enable_purchases={"default": False},
        rm_confirm_spend={"default": False},
        # ThousandThings (千物币, O_S_TOTAL)
        rm_tt_enable={"default": False},
        rm_tt_mystery_amulet={"default": False},
        rm_tt_black_daruma_scrap={"default": False},
        rm_tt_ap={"default": False},
        rm_tt_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_tt_reserve={"default": 0, "min": 0, "max": 99999999},
        # Shrine (御札, O_TT_TOTOL)
        rm_shrine_enable={"default": False},
        rm_shrine_black_daruma={"default": False},
        rm_shrine_white_five={"default": False},
        rm_shrine_white_four={"default": False},
        rm_shrine_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_shrine_reserve={"default": 0, "min": 0, "max": 99999999},
        # GuildStore (功勋, O_GUILD_TOTAL)
        rm_guild_enable={"default": False},
        rm_guild_mystery_amulet={"default": False},
        rm_guild_black_daruma_scrap={"default": False},
        rm_guild_skin_ticket={"default": False},
        rm_guild_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_guild_reserve={"default": 0, "min": 0, "max": 99999999},
        # Mall Medal (勋章, O_MALL_RESOURCE_3) & Honor (荣誉, O_MALL_RESOURCE_4)
        rm_medal_enable={"default": False},
        rm_medal_black_daruma={"default": False},
        rm_medal_mystery_amulet={"default": False},
        rm_medal_ap_100={"default": False},
        rm_medal_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_medal_reserve={"default": 0, "min": 0, "max": 99999999},
        rm_honor_enable={"default": False},
        rm_honor_mystery_amulet={"default": False},
        rm_honor_black_daruma_scrap={"default": False},
        rm_honor_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_honor_reserve={"default": 0, "min": 0, "max": 99999999},
        # Mall Consignment (勾玉, O_LEGACY_MALL_RESOURCE_1)
        rm_consignment_enable={"default": False},
        rm_consignment_sale_ticket={"default": False},
        rm_consignment_max_jade={"default": 0, "min": 0, "max": 99999},
        rm_consignment_jade_reserve={"default": 0, "min": 0, "max": 99999999},
        rm_bondlings_enable={"default": False},
        rm_bondlings_stone={"default": 0, "min": 0, "max": 999},
        rm_bondlings_random_soul={"default": 0, "min": 0, "max": 999},
        rm_bondlings_high_disc={"default": 0, "min": 0, "max": 999},
        rm_bondlings_medium_disc={"default": 0, "min": 0, "max": 999},
        rm_bondlings_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_bondlings_reserve={"default": 0, "min": 0, "max": 99999999},
        rm_scales_orochi={"default": 0, "min": 0, "max": 999, "desc": "朴素御魂原版数量配置，非零时买到库存或预算耗尽"},
        rm_scales_orochi_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_scales_orochi_reserve={"default": 0, "min": 0, "max": 99999999},
        # Mall Special (金币, O_MALL_RESOURCE_1), FriendshipPoints (友情点, O_MALL_RESOURCE_5), Charisma (魅力, O_MALL_RESOURCE_5)
        rm_special_enable={"default": False},
        rm_special_totem_pass={"default": False},
        rm_special_medium_disc={"default": False},
        rm_special_low_disc={"default": False},
        rm_special_max_budget={"default": 0, "min": 0, "max": 9999999},
        rm_special_reserve={"default": 0, "min": 0, "max": 99999999},
        rm_friends_enable={"default": False},
        rm_friends_white_daruma={"default": False},
        rm_friends_red_daruma={"default": False},
        rm_friends_broken_amulet={"default": False},
        rm_friends_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_friends_reserve={"default": 0, "min": 0, "max": 99999999},
        rm_charisma_enable={"default": False},
        rm_charisma_black_daruma_scrap={"default": False},
        rm_charisma_mystery_amulet={"default": False},
        rm_charisma_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_charisma_reserve={"default": 0, "min": 0, "max": 99999999},
        rm_limit_seconds={"default": 0, "min": 0, "max": 7200},
        rm_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        rm_phase="entry", rm_price=-1, rm_quoted_price=-1, rm_quantity=-1,
        rm_transactions=0, rm_started=-1, rm_exit_reason="",
        rm_tt_offer=0, rm_tt_balance=-1, rm_tt_balance_before=-1, rm_tt_spent=0,
        rm_shrine_offer=0, rm_shrine_balance=-1, rm_shrine_balance_before=-1, rm_shrine_spent=0,
        rm_travel_arrived=0, rm_summon_arrived=0, rm_guild_arrived=0, rm_mall_arrived=0, rm_main_arrived=0,
        rm_target_delay_s=0, rm_observed_ms=0,
    )
    res_names = ("RichMan", "GlobalGame", "Component_Buy")
    raw["resources"] = sorted(set(raw["resources"] + [f"upstream/oas/{n}.yaml" for n in res_names]))
    docs = {n: load_yaml(resources / f"{n}.yaml")["resources"] for n in res_names}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"rm_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"rm_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"rm_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="RichMan", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, ns="RichMan", delay=1000):
        return _click_from(docs, name, ns, delay)

    _wire_nav(raw, "rm", phase, advance, "unused_nav")
    any_mall_sundry = "rm_special_enable or rm_medal_enable or rm_honor_enable or rm_friends_enable or rm_charisma_enable"
    use_scales = "rm_scales_orochi > 0 or rm_scales_demon_count > 0 or rm_scales_sea_count > 0"
    any_mall = f"rm_consignment_enable or {use_scales} or rm_bondlings_enable or {any_mall_sundry}"
    any_bound_shop = f"rm_tt_enable or rm_shrine_enable or rm_guild_enable or {any_mall}"

    state("spend_confirm_gate", "entry", [expr("rm_enable_purchases and not rm_confirm_spend")],
          {"fail": "大富翁(千物宝箱/神龛/功勋/杂货铺/勋章/荣誉/友情点)会消耗货币，需显式开启 rm_confirm_spend"})
    state("spend_subflows_unbound", "entry",
          [expr(f"rm_enable_purchases and rm_confirm_spend and not ({any_bound_shop})")],
          {"fail": "大富翁已开启采购但未启用任何已绑定子商店(千物/神龛/功勋/勋章/荣誉)，其余商店仍需来源绑定"})
    state("skip_when_disabled", "entry", [expr("not rm_enable_purchases")], {
        "stop": {
            "reason": "大富翁未开启自动采购，未消耗任何货币，安全结束",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "RichMan",
            "evidence": {"scope": "rich_man_economic_safe_skip"},
        }
    })
    state("entry_dispatch", "entry", [expr(f"rm_enable_purchases and rm_confirm_spend and ({any_bound_shop})")],
          advance("tt_dispatch"))

    # 1. ThousandThings (千物宝箱)
    for ph in ("tt_dispatch", "tt_enter", "tt_offer", "shrine_dispatch", "shrine_enter", "shrine_offer", "guild_dispatch"):
        state(f"{ph}_time_limit", ph,
              [expr("rm_limit_seconds > 0 and elapsed_ms >= rm_limit_seconds * 1000")],
              advance("exit_main", rm_exit_reason="'time_limit'", rm_main_arrived=0))
    state("tt_skip", "tt_dispatch", [expr("not rm_tt_enable")], advance("shrine_dispatch"))
    state("tt_goto", "tt_dispatch", [expr("rm_tt_enable")], advance("tt_nav", rm_travel_arrived=0))
    state("tt_nav_arrived", "tt_nav", [raw["navigation"]["pages"]["page_travel"]["when"], expr("rm_travel_arrived == 1")],
          advance("tt_enter"))
    state("tt_nav_drive", "tt_nav", [], {"navigate": {"destination": "page_travel", "done_var": "rm_travel_arrived"}})
    state("tt_entered", "tt_enter", [asset("I_TT_CHECK")], advance("tt_offer"))
    state("tt_click_enter", "tt_enter", [asset("I_TT_ENTER")], click("I_TT_ENTER", delay=800))

    tt_bal = {"ocr": "RichMan::O_S_TOTAL", "mode": "exact_quantity", "var": "rm_tt_balance"}
    tt_reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    tt_items = [
        ("rm_tt_mystery_amulet", "I_TT_TICKET_BULE", "千物蓝票", 2000),
        ("rm_tt_black_daruma_scrap", "I_TT_BLACK", "千物黑蛋碎片", 350),
        ("rm_tt_ap", "I_TT_AP", "千物体力", 600),
    ]
    for idx, (param_name, item_img, title, cost) in enumerate(tt_items):
        arm = expr(f"rm_tt_offer == {idx}")
        nxt = advance("tt_offer", rm_tt_offer=idx + 1)
        state(f"tt_{idx}_skip", "tt_offer", [arm, expr(f"not {param_name}")], nxt)
        state(f"tt_{idx}_missing", "tt_offer", [arm, asset("I_TT_CHECK"), {"not": asset(item_img)}], nxt)
        state(f"tt_{idx}_budget", "tt_offer", [arm, asset("I_TT_CHECK"), expr(f"rm_tt_spent + {cost} > rm_tt_max_budget")], nxt)
        state(f"tt_{idx}_low", "tt_offer", [arm, asset("I_TT_CHECK"), asset(item_img), tt_bal,
              expr(f"rm_tt_balance - rm_tt_reserve < {cost}")], nxt)
        state(f"tt_{idx}_open", "tt_offer", [arm, asset("I_TT_CHECK"), asset(item_img), tt_bal,
              expr(f"rm_tt_balance - rm_tt_reserve >= {cost} and rm_tt_spent + {cost} <= rm_tt_max_budget")],
              click(item_img, delay=800),
              advance("tt_commit", rm_quoted_price=cost, rm_tt_balance_before="rm_tt_balance", rm_started="elapsed_ms"))
        state(f"tt_{idx}_unreadable", "tt_offer", [arm, asset("I_TT_CHECK"), asset(item_img)],
              {"fail": f"{title}缺少有效千物币余额读数，停止采购"})
        state(f"tt_{idx}_confirm", "tt_commit",
              [arm, asset("I_TT_BUY_CONFIRM"), {"not": asset("I_BUY_RMB", "Component_Buy")}, tt_bal,
               expr(f"rm_tt_balance == rm_tt_balance_before and rm_quoted_price == {cost} and rm_tt_spent + rm_quoted_price <= rm_tt_max_budget")],
              click("I_TT_BUY_CONFIRM", delay=800),
              advance("tt_settle", rm_tt_spent="rm_tt_spent + rm_quoted_price", rm_started="elapsed_ms"))
        raw["states"][-1].update(sensitive="购买", desc=f"在千物宝箱兑换{title}，花费 {cost} 千物币。")
        state(f"tt_{idx}_timeout", "tt_commit", [arm, expr("elapsed_ms - rm_started >= 9000")],
              {"fail": f"{title}未确认兑换弹窗"})
    state("tt_all_done", "tt_offer", [asset("I_TT_CHECK"), expr(f"rm_tt_offer >= {len(tt_items)}")], advance("tt_exit"))
    state("tt_reward", "tt_settle", [tt_reward], click("C_UI_REWARD", "GlobalGame", 400))
    state("tt_debit_ok", "tt_settle", [asset("I_TT_CHECK"), {"not": tt_reward}, tt_bal,
          expr("rm_tt_balance == rm_tt_balance_before - rm_quoted_price")],
          {"inc": "rm_transactions"}, advance("tt_offer", rm_tt_offer="rm_tt_offer + 1"))
    state("tt_debit_missing", "tt_settle", [expr("elapsed_ms - rm_started >= 12000")],
          {"fail": "千物宝箱兑换已尝试，缺少余额扣款验证，停止后续采购"})
    state("tt_exit_done", "tt_exit", [asset("I_TT_ENTER")], advance("shrine_dispatch"))
    state("tt_exit_back", "tt_exit", [asset("I_UI_BACK_RED", "GlobalGame")], click("I_UI_BACK_RED", "GlobalGame", 800))

    # 2. Shrine (神龛)
    state("shrine_skip", "shrine_dispatch", [expr("not rm_shrine_enable")], advance("guild_dispatch"))
    state("shrine_goto", "shrine_dispatch", [expr("rm_shrine_enable")], advance("shrine_nav", rm_summon_arrived=0))
    state("shrine_nav_arrived", "shrine_nav", [raw["navigation"]["pages"]["page_summon"]["when"], expr("rm_summon_arrived == 1")],
          advance("shrine_enter"))
    state("shrine_nav_drive", "shrine_nav", [], {"navigate": {"destination": "page_summon", "done_var": "rm_summon_arrived"}})
    state("shrine_entered", "shrine_enter", [asset("I_S_NEXT_PERIOD")], advance("shrine_offer"))
    state("shrine_click_enter", "shrine_enter", [], click("C_C_SHRINE", delay=800))

    sh_bal = {"ocr": "RichMan::O_TT_TOTOL", "mode": "exact_quantity", "var": "rm_shrine_balance"}
    sh_items = [
        ("rm_shrine_black_daruma", "I_S_BLACK", "I_S_BUY_BLACK", "I_S_CONFIRM_BLACK", "神龛黑蛋", 1500),
        ("rm_shrine_white_five", "I_S_WHITE_FIVE", "I_S_BUY_WHITE_FIVE", "I_S_CONFIRM_WHITE_FIVE", "神龛五星白蛋", 1200),
        ("rm_shrine_white_four", "I_S_WHITE_FOUR", "I_S_BUY_WHITE_FOUR", "I_S_CONFIRM_WHITE_FOUR", "神龛四星白蛋", 400),
    ]
    for idx, (param_name, item_img, buy_img, confirm_img, title, cost) in enumerate(sh_items):
        arm = expr(f"rm_shrine_offer == {idx}")
        nxt = advance("shrine_offer", rm_shrine_offer=idx + 1)
        state(f"sh_{idx}_skip", "shrine_offer", [arm, expr(f"not {param_name}")], nxt)
        state(f"sh_{idx}_missing", "shrine_offer", [arm, asset("I_S_NEXT_PERIOD"), {"not": asset(item_img)}], nxt)
        state(f"sh_{idx}_budget", "shrine_offer", [arm, asset("I_S_NEXT_PERIOD"), expr(f"rm_shrine_spent + {cost} > rm_shrine_max_budget")], nxt)
        state(f"sh_{idx}_low", "shrine_offer", [arm, asset("I_S_NEXT_PERIOD"), asset(item_img), sh_bal,
              expr(f"rm_shrine_balance - rm_shrine_reserve < {cost}")], nxt)
        state(f"sh_{idx}_open", "shrine_offer", [arm, asset("I_S_NEXT_PERIOD"), asset(item_img), sh_bal,
              expr(f"rm_shrine_balance - rm_shrine_reserve >= {cost} and rm_shrine_spent + {cost} <= rm_shrine_max_budget")],
              click(item_img, delay=800),
              advance("shrine_quote", rm_quoted_price=cost, rm_shrine_balance_before="rm_shrine_balance", rm_started="elapsed_ms"))
        state(f"sh_{idx}_unreadable", "shrine_offer", [arm, asset("I_S_NEXT_PERIOD"), asset(item_img)],
              {"fail": f"{title}缺少有效御札余额读数，停止采购"})
        state(f"sh_{idx}_to_confirm", "shrine_quote", [arm, asset(buy_img)],
              click(buy_img, delay=800), advance("shrine_commit", rm_started="elapsed_ms"))
        state(f"sh_{idx}_quote_timeout", "shrine_quote", [arm, expr("elapsed_ms - rm_started >= 9000")],
              {"fail": f"{title}未打开兑换详情"})
        state(f"sh_{idx}_confirm", "shrine_commit",
              [arm, asset(confirm_img), sh_bal,
               expr(f"rm_shrine_balance == rm_shrine_balance_before and rm_quoted_price == {cost} and rm_shrine_spent + rm_quoted_price <= rm_shrine_max_budget")],
              click(confirm_img, delay=800),
              advance("shrine_settle", rm_shrine_spent="rm_shrine_spent + rm_quoted_price", rm_started="elapsed_ms"))
        raw["states"][-1].update(sensitive="购买", desc=f"在神龛兑换{title}，花费 {cost} 御札。")
        state(f"sh_{idx}_commit_timeout", "shrine_commit", [arm, expr("elapsed_ms - rm_started >= 9000")],
              {"fail": f"{title}确认弹窗变化或超时"})
    state("shrine_all_done", "shrine_offer", [asset("I_S_NEXT_PERIOD"), expr(f"rm_shrine_offer >= {len(sh_items)}")],
          advance("guild_dispatch"))
    state("shrine_reward", "shrine_settle", [tt_reward], click("C_UI_REWARD", "GlobalGame", 400))
    state("shrine_close_detail", "shrine_settle", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", 600))
    state("shrine_debit_ok", "shrine_settle", [asset("I_S_NEXT_PERIOD"), {"not": tt_reward}, sh_bal,
          expr("rm_shrine_balance == rm_shrine_balance_before - rm_quoted_price")],
          {"inc": "rm_transactions"}, advance("shrine_offer", rm_shrine_offer="rm_shrine_offer + 1"))
    state("shrine_debit_missing", "shrine_settle", [expr("elapsed_ms - rm_started >= 12000")],
          {"fail": "神龛兑换已尝试，缺少御札余额扣款验证，停止后续采购"})

    # 3. GuildStore (功勋商店)
    state("guild_skip", "guild_dispatch", [expr("not rm_guild_enable")], advance("mall_dispatch"))
    state("guild_goto", "guild_dispatch", [expr("rm_guild_enable")], advance("guild_nav", rm_guild_arrived=0))
    state("guild_nav_arrived", "guild_nav", [raw["navigation"]["pages"]["page_guild"]["when"], expr("rm_guild_arrived == 1")],
          advance("guild_enter"))
    state("guild_nav_drive", "guild_nav", [], {"navigate": {"destination": "page_guild", "done_var": "rm_guild_arrived"}})
    state("guild_entered", "guild_enter", [asset("I_GUILD_CLOSE_RED")], advance("guild_offer"))
    state("guild_click_shrine", "guild_enter", [asset("I_GUILD_SHRINE")], click("I_GUILD_SHRINE", delay=800))
    state("guild_click_store", "guild_enter", [asset("I_GUILD_STORE")], click("I_GUILD_STORE", delay=800))

    def _guild_exit(exit_ph, nxt_ph):
        state("guild_exit_done", exit_ph, [asset("I_GUILD_SHRINE")], advance(nxt_ph))
        state("guild_exit_red", exit_ph, [asset("I_GUILD_CLOSE_RED")], click("I_GUILD_CLOSE_RED", delay=800))
        state("guild_exit_yellow", exit_ph, [asset("I_UI_BACK_YELLOW", "GlobalGame")],
              click("I_UI_BACK_YELLOW", "GlobalGame", 800))

    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="guild", enter_phase="guild_enter", next_phase="mall_dispatch",
        screen_guard=asset("I_GUILD_CLOSE_RED"), balance_ocr="RichMan::O_GUILD_TOTAL",
        budget_param="rm_guild_max_budget", reserve_param="rm_guild_reserve",
        sensitive_label="购买",
        items=[
            ("rm_guild_mystery_amulet", "I_GUILD_BLUE", None, "功勋蓝票", 240),
            ("rm_guild_black_daruma_scrap", "I_GUILD_SCRAP", "I_GUILD_CHECK_SCRAP", "功勋黑蛋碎片", 200),
            ("rm_guild_skin_ticket", "I_GUILD_SKIN", None, "功勋皮肤券", 50),
        ],
        exit_states_fn=_guild_exit,
    )

    # 4. Mall: Consignment (勾玉), Special (金币), Medal (勋章), Honor (荣誉), FriendshipPoints (友情点), Charisma (魅力)
    state("mall_skip", "mall_dispatch", [expr(f"not ({any_mall})")],
          advance("exit_main", rm_main_arrived=0))
    state("mall_goto", "mall_dispatch", [expr(any_mall)],
          advance("mall_nav", rm_mall_arrived=0))
    state("mall_nav_arrived", "mall_nav", [raw["navigation"]["pages"]["page_mall"]["when"], expr("rm_mall_arrived == 1")],
          advance("consignment_dispatch"))
    state("mall_nav_drive", "mall_nav", [], {"navigate": {"destination": "page_mall", "done_var": "rm_mall_arrived"}})

    state("consignment_skip", "consignment_dispatch", [expr("not rm_consignment_enable")], advance("scales_dispatch"))
    state("consignment_ready", "consignment_dispatch",
          [expr("rm_consignment_enable"), asset("I_CON_ENTER_CHECK")], advance("consignment_offer"))
    state("consignment_open_exchange", "consignment_dispatch",
          [expr("rm_consignment_enable"), asset("I_CON_ENTER")], click("I_CON_ENTER", delay=800))
    state("consignment_open_tab", "consignment_dispatch",
          [expr("rm_consignment_enable"), asset("I_MALL_CONSIGNMENT")], click("I_MALL_CONSIGNMENT", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="consignment", enter_phase="consignment_dispatch", next_phase="scales_dispatch",
        screen_guard=asset("I_CON_ENTER_CHECK"), balance_ocr="RichMan::O_LEGACY_MALL_RESOURCE_1",
        budget_param="rm_consignment_max_jade", reserve_param="rm_consignment_jade_reserve",
        sensitive_label="花勾玉",
        items=[("rm_consignment_sale_ticket", "I_CON_TICKET", None, "寄售屋寄售券", 100)],
    )

    scales = asset("I_MALL_SCCALES_CHECK")
    state("scales_skip", "scales_dispatch", [expr(f"not ({use_scales})")], advance("bondlings_dispatch"))
    state("scales_ready", "scales_dispatch", [expr(use_scales), scales], advance("scales_orochi_offer"))
    state("scales_open", "scales_dispatch",
          [expr(use_scales), {"not": scales}, asset("I_MALL_SCCALES")],
          click("I_MALL_SCCALES", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="scales_orochi", enter_phase="scales_dispatch", next_phase="scales_demon_offer",
        screen_guard=scales, balance_ocr="RichMan::O_SCA_RES_OROCHI", balance_mode="counter_current",
        budget_param="rm_scales_orochi_max_budget", reserve_param="rm_scales_orochi_reserve",
        sensitive_label="购买", items=[("rm_scales_orochi", "I_SCA_OROCHI_SCALES", None, "朴素御魂", 50)],
        stock_ocr={"rm_scales_orochi": "RichMan::O_SCA_NUMBER_OROCHI"}, buy_until_exhausted=True,
        quote_identity={"ocr_single": {"region": [510, 140, 260, 56], "equals": "朴素的御魂礼盒"}},
        confirm_rect=[565, 535, 712, 570],
        extra_reward=(
            {"any": [asset("I_SCA_SIX_STAR"), asset("I_SCA_REWARD")]},
            click("C_SCA_SOULS_BACK", delay=1000),
        ),
    )
    bind_scales_demon(raw, state, advance, asset, click, expr)
    bind_scales_sea(raw, state, advance, asset, click, expr)

    state("bondlings_skip", "bondlings_dispatch", [expr("not rm_bondlings_enable")], advance("mall_sundry"))
    bondlings = {"any": [asset("I_MALL_BONDLINGS_ON"), asset("I_MALL_BONDLINGS_CHECK")]}
    state("bondlings_ready", "bondlings_dispatch", [expr("rm_bondlings_enable"), bondlings],
          advance("bondlings_offer"))
    state("bondlings_open_tab", "bondlings_dispatch",
          [expr("rm_bondlings_enable"), asset("I_MALL_SCCALES_CHECK"), asset("I_MALL_BONDLINGS_SURE")],
          click("I_MALL_BONDLINGS_SURE", delay=800))
    state("bondlings_open_scales", "bondlings_dispatch", [expr("rm_bondlings_enable"),
          {"not": asset("I_MALL_SCCALES_CHECK")}, asset("I_MALL_SCCALES")], click("I_MALL_SCCALES", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="bondlings", enter_phase="bondlings_dispatch", next_phase="mall_sundry",
        screen_guard=bondlings, balance_ocr="RichMan::O_BL_CHECK_MONEY", balance_mode="counter_current",
        budget_param="rm_bondlings_max_budget", reserve_param="rm_bondlings_reserve", sensitive_label="购买",
        items=[
            ("rm_bondlings_stone", "I_BL_BUY_STONE", None, "契灵石头", 30),
            ("rm_bondlings_random_soul", "I_BL_BUY_SOULS", None, "随机契灵御魂", 20),
            ("rm_bondlings_high_disc", "I_BL_BUY_HIGH", None, "高级契灵盘", 50),
            ("rm_bondlings_medium_disc", "I_BL_BUY_MEDIUM", None, "中级契灵盘", 20),
        ],
        stock_ocr={
            "rm_bondlings_stone": "RichMan::O_BL_RES_STONE",
            "rm_bondlings_random_soul": "RichMan::O_BL_RES_SOULS",
            "rm_bondlings_high_disc": "RichMan::O_BL_RES_HIGH",
            "rm_bondlings_medium_disc": "RichMan::O_BL_RES_MEDIUM",
        },
    )

    state("mall_sundry_skip", "mall_sundry", [expr(f"not ({any_mall_sundry})")],
          advance("exit_main", rm_main_arrived=0))
    state("mall_sundry_ready", "mall_sundry", [asset("I_MALL_SUNDRY_CHECK")], advance("special_dispatch"))
    state("mall_sundry_click", "mall_sundry", [asset("I_MALL_SUNDRY")], click("I_MALL_SUNDRY", delay=800))

    state("special_skip", "special_dispatch", [expr("not rm_special_enable")], advance("medal_dispatch"))
    state("special_ready", "special_dispatch", [expr("rm_special_enable"), asset("I_SIDE_CHECK_SPECIAL")],
          advance("special_offer"))
    state("special_tab_click", "special_dispatch", [expr("rm_special_enable"), asset("I_SIDE_SURE_SPECIAL")],
          click("I_SIDE_SURE_SPECIAL", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="special", enter_phase="special_dispatch", next_phase="medal_dispatch",
        screen_guard=asset("I_SIDE_CHECK_SPECIAL"), balance_ocr="RichMan::O_MALL_RESOURCE_1",
        budget_param="rm_special_max_budget", reserve_param="rm_special_reserve",
        sensitive_label="购买",
        items=[
            ("rm_special_totem_pass", "I_SP_BUY_TOTEM", None, "御灵挑战券", 5000),
            ("rm_special_medium_disc", "I_SP_BUY_MEDIUM", None, "中级契灵盘", 15000),
            ("rm_special_low_disc", "I_SP_BUY_LOW", None, "低级契灵盘", 5000),
        ],
    )

    state("medal_skip", "medal_dispatch", [expr("not rm_medal_enable")], advance("honor_dispatch"))
    state("medal_ready", "medal_dispatch", [expr("rm_medal_enable"), asset("I_SIDE_CHECK_MEDAL")], advance("medal_offer"))
    state("medal_tab_click", "medal_dispatch", [expr("rm_medal_enable"), asset("I_SIDE_SURE_MEDAL")],
          click("I_SIDE_SURE_MEDAL", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="medal", enter_phase="medal_dispatch", next_phase="honor_dispatch",
        screen_guard=asset("I_SIDE_CHECK_MEDAL"), balance_ocr="RichMan::O_MALL_RESOURCE_3",
        budget_param="rm_medal_max_budget", reserve_param="rm_medal_reserve",
        sensitive_label="购买",
        items=[
            ("rm_medal_black_daruma", "I_ME_BLACK", "I_ME_CHECK_BLACK", "勋章黑蛋", 480),
            ("rm_medal_mystery_amulet", "I_ME_BLUE", "I_ME_CHECK_BLUE", "勋章蓝票", 180),
            ("rm_medal_ap_100", "I_ME_AP", "I_ME_CHECK_AP", "勋章体力100", 120),
        ],
    )

    state("honor_skip", "honor_dispatch", [expr("not rm_honor_enable")], advance("friends_dispatch"))
    state("honor_ready", "honor_dispatch", [expr("rm_honor_enable"), asset("I_SIDE_CHECK_HONOR")], advance("honor_offer"))
    state("honor_tab_click", "honor_dispatch", [expr("rm_honor_enable"), asset("I_SIDE_SUER_HONOR")],
          click("I_SIDE_SUER_HONOR", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="honor", enter_phase="honor_dispatch", next_phase="friends_dispatch",
        screen_guard=asset("I_SIDE_CHECK_HONOR"), balance_ocr="RichMan::O_MALL_RESOURCE_4",
        budget_param="rm_honor_max_budget", reserve_param="rm_honor_reserve",
        sensitive_label="购买",
        items=[
            ("rm_honor_mystery_amulet", "I_HONOR_BLUE", None, "荣誉蓝票", 1500),
            ("rm_honor_black_daruma_scrap", "I_HONOR_BLACK", None, "荣誉黑蛋碎片", 540),
        ],
    )

    state("friends_skip", "friends_dispatch", [expr("not rm_friends_enable")], advance("charisma_dispatch"))
    state("friends_ready", "friends_dispatch", [expr("rm_friends_enable"), asset("I_SIDE_CHECK_FRIENDS")],
          advance("friends_offer"))
    state("friends_tab_click", "friends_dispatch", [expr("rm_friends_enable"), asset("I_SIDE_SURE_FRIENDS")],
          click("I_SIDE_SURE_FRIENDS", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="friends", enter_phase="friends_dispatch", next_phase="charisma_dispatch",
        screen_guard=asset("I_SIDE_CHECK_FRIENDS"), balance_ocr="RichMan::O_MALL_RESOURCE_5",
        budget_param="rm_friends_max_budget", reserve_param="rm_friends_reserve",
        sensitive_label="购买",
        items=[
            ("rm_friends_white_daruma", "I_FS_WHITE_CLICK", "I_FS_WHITE_CHECK", "友情点白蛋", 1000),
            ("rm_friends_red_daruma", "I_FS_RED", None, "友情点红蛋", 150),
            ("rm_friends_broken_amulet", "I_FS_BROKEN", None, "友情点破碎符咒", 100),
        ],
    )

    state("charisma_skip", "charisma_dispatch", [expr("not rm_charisma_enable")],
          advance("exit_main", rm_main_arrived=0))
    state("charisma_ready", "charisma_dispatch", [expr("rm_charisma_enable"), asset("I_SIDE_CHECK_CHARISMA")],
          advance("charisma_offer"))
    state("charisma_tab_click", "charisma_dispatch", [expr("rm_charisma_enable"), asset("I_SIDE_SURE_CHARISMA")],
          click("I_SIDE_SURE_CHARISMA", delay=800))
    _bind_component_buy_shop(
        raw, docs, state, advance, click, asset, expr,
        shop_key="charisma", enter_phase="charisma_dispatch", next_phase="exit_main",
        screen_guard=asset("I_SIDE_CHECK_CHARISMA"), balance_ocr="RichMan::O_MALL_RESOURCE_5",
        budget_param="rm_charisma_max_budget", reserve_param="rm_charisma_reserve",
        sensitive_label="购买",
        items=[
            ("rm_charisma_black_daruma_scrap", "I_CH_BLACK", None, "魅力黑蛋碎片", 320),
            ("rm_charisma_mystery_amulet", "I_CH_BLUE", "I_CH_CHECK_BLUE", "魅力蓝票", 400),
        ],
    )

    # Return to courtyard and schedule
    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main_target_prep", "exit_main", [court, expr("rm_next_delay_s > 0")],
          advance("stop_target", rm_target_delay_s="rm_next_delay_s", rm_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "大富翁已绑定商店按预算与扣款校验完成采购并按目标调度返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "RichMan",
                "delay_seconds_var": "rm_target_delay_s",
                "observed_ms_var": "rm_observed_ms",
            },
            "evidence": {"scope": "rich_man_target_schedule"},
        }
    })
    state("returned_main", "exit_main", [court], {
        "stop": {
            "reason": "大富翁已绑定商店按预算与扣款校验完成采购并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "RichMan",
            "evidence": {"scope": "rich_man_guarded_budget_subshops"},
        }
    })
    state("exit_main_drive", "exit_main", [], {"navigate": {"destination": "page_main", "done_var": "rm_main_arrived"}})

    raw["oas_rich_man_contract"] = {
        "source": RICH_MAN_ENTRY,
        "source_pins": {**RICH_MAN_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "bound_subshops": [
            "thousand_things", "shrine", "guild_store",
            "mall_consignment", "mall_special", "mall_medal", "mall_honor",
            "mall_friendship_points", "mall_charisma", "mall_bondlings", "mall_scales_orochi", "mall_scales_sea_manual",
            "mall_scales_demon",
        ],
        "source_obligations": [*nav["source_obligations"], {
            "id": "rich_man_scales_bondlings_and_live",
            "blocking": True,
            "requirement": "Bind automatic Sea selection and verify actual store debits and rewards on live frames. "
                           "Scales Orochi, Scales Demon and Bondlings use individually confirmed units.",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_six_realms_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS SixRealms (六道之门·月之海) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, SIX_REALMS_PINS, "SixRealms")
    nav = compile_navigation_family(
        source, resources, prefix="sr_nav", destination="page_six_gates",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="sr_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_six_realms_natively_staged", title="六道之门", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        sr_limit_runs={"default": 1, "min": 0, "max": 20},
        sr_limit_seconds={"default": 1800, "min": 0, "max": 7200},
        sr_confirm_ap_cost={"default": False},
        sr_use_double_ticket={"default": False},
        sr_confirm_double_ticket={"default": False},
        sr_retry_boss={"default": False},
        sr_shop_refresh_enable={"default": False},
        sr_max_shop_refreshes={"default": 2, "min": 0, "max": 5},
        sr_shop_min_coins={"default": 50, "min": 0, "max": 9999},
        sr_max_skill_refreshes={"default": 2, "min": 0, "max": 5},
        sr_buy_soft_wind_in_store={"default": True},
        sr_imitate_enable={"default": True},
        sr_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        sr_phase="entry", sr_runs=0, sr_battles=0, sr_wins=0,
        sr_ap_started=0, sr_double_used=0, sr_skills_picked=0, sr_boss_retries=0,
        sr_shop_refreshes=0, sr_skill_refreshes=0, sr_coins=0,
        sr_skill_refresh_left=-1, sr_store_refresh_left=-1, sr_team_locked=False,
        sr_soft_wind_level=1, sr_store_buys=0, sr_imitate_tries=0, sr_island_kind="",
        sr_target_delay_s=0, sr_observed_ms=0, sr_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/SixRealms.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("SixRealms", "GlobalGame")}
    sr_loaded = load_resource_file(resources / "SixRealms.yaml")
    inline = raw.setdefault("inline_resources", {})
    for skill_name, col_rois in (
        ("I_SKILL101", ([139, 167, 240, 100], [340, 167, 320, 100], [620, 167, 241, 100])),
        ("I_SKILL105", ([112, 149, 268, 151], [340, 149, 320, 151], [620, 149, 271, 151])),
    ):
        for col, col_roi in enumerate(col_rois):
            spec = dict(sr_loaded[skill_name])
            spec["roi"] = list(col_roi)
            inline[f"SixRealmsSkill::{skill_name}_COL{col}"] = spec

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"sr_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"sr_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"sr_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="SixRealms"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="SixRealms", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("double_ticket_gate", "entry", [expr("sr_use_double_ticket and not sr_confirm_double_ticket")],
          {"fail": "六道之门双倍消耗御神道具/勾玉需显式开启 sr_confirm_double_ticket"})
    bind_task_presets(raw, source, resources, prefix="sr", resume="navigate", category="sr")
    _wire_nav(raw, "sr", phase, advance, "gate")

    state("gate_limit_reached", "gate", [expr("sr_runs >= sr_limit_runs")], advance("exit"))
    state("gate_ap_confirm_gate", "gate", [asset("I_MSTART"), expr("not sr_confirm_ap_cost")],
          {"fail": "开启新一轮六道之门(月之海)消耗 60 体力，需显式开启 sr_confirm_ap_cost"})
    state("gate_select_shouzu_open", "gate", [asset("I_MSTART"), expr("sr_confirm_ap_cost"), asset("I_MSHUTEN")],
          click("I_MSHUTEN", delay=1500))
    state("gate_select_shouzu_pick", "gate", [asset("I_MSHOUZU_SELECT")],
          click("I_MSHOUZU_SELECT", delay=1000))
    state("gate_start_uncheck", "gate", [asset("I_MSTART_UNCHECK")], click("I_MSTART_UNCHECK", delay=600))
    state("gate_start_new", "gate", [asset("I_MSTART"), expr("sr_confirm_ap_cost")],
          click("I_MSTART", delay=1200), {"inc": "sr_ap_started"})
    raw["states"][-1].update(
        sensitive="购买",
        desc="开启新一轮六道之门(月之海)，将消耗 60 体力。",
    )
    state("gate_start_confirm", "gate", [asset("I_MSTART_CONFIRM")], click("I_MSTART_CONFIRM", delay=1200))
    state("gate_start_confirm2", "gate", [asset("I_MSTART_CONFIRM2")], click("I_MSTART_CONFIRM2", delay=1200))
    state("gate_select_shiki_swipe", "gate", [asset("I_SELECT_SHIKIGAMI_AND_CONFIRM")],
          {"swipe": "SixRealms::S_TEAM_SWIPE_UP", "delay": 1000, "recheck": True})
    state("gate_select_shiki_coin", "gate", [asset("I_COIN2")], click("I_COIN2", delay=1000))
    state("gate_start_skip", "gate", [asset("I_MSKIP")], click("I_MSKIP", delay=1200))
    state("gate_first_skill", "gate", [asset("I_MFIRST_SKILL")],
          click("I_MFIRST_SKILL", delay=1000), {"inc": "sr_skills_picked"}, advance("inside"))
    state("gate_continue", "gate", [asset("I_MCONINUE")], click("I_MCONINUE", delay=1200), advance("inside"))
    state("gate_enter_moon", "gate", [asset("I_MENTER")], click("I_MENTER", delay=1200), advance("inside"))

    reset = _wire_battle(raw, body, contract, phase, advance, "sr_battles", "sr_wins", "inside")
    state("inside_boss_double", "inside", [
        expr("sr_use_double_ticket and sr_confirm_double_ticket"), asset("I_BOSS_USE_DOUBLE"),
    ], click("I_BOSS_USE_DOUBLE", delay=1000), {"inc": "sr_double_used"})
    raw["states"][-1].update(
        sensitive="花勾玉",
        desc="使用六道之门双倍结算，将消耗双倍道具或勾玉。",
    )
    state("inside_time_limit", "inside", [expr("elapsed_ms >= sr_limit_seconds * 1000")],
          advance("exit", sr_exit_reason="'time_limit'"))
    state("inside_boss_done", "inside", [{"any": [asset("I_BOSS_SHARE"), asset("I_BOSS_GET_EXP")]}],
          click("C_MAIN_ANIMATE_KEEP", delay=1000), {"inc": "sr_runs"}, advance("exit"))
    state("inside_boss_skip", "inside", [asset("I_BOSS_SKIP")], click("I_BOSS_SKIP", delay=1000))
    state("inside_boss_retry", "inside", [expr("sr_retry_boss"), asset("I_BOSS_BATTLE_AGAIN")],
          click("I_BOSS_BATTLE_AGAIN", delay=1200), {"inc": "sr_boss_retries"})
    state("inside_boss_giveup", "inside", [expr("not sr_retry_boss"), asset("I_BOSS_BATTLE_GIVEUP")],
          click("I_BOSS_BATTLE_GIVEUP", delay=1200))
    state("inside_boss_lock", "inside", [asset("I_BOSS_FIRE"), asset("I_BOSS_TEAM_UNLOCK")],
          click("I_BOSS_TEAM_UNLOCK", delay=1000))
    state("inside_boss_fire", "inside", [asset("I_BOSS_FIRE")],
          click("I_BOSS_FIRE", delay=1200), {"set": reset}, advance("in_battle"))
    read_coins = {"ocr": "SixRealms::O_COIN_NUM", "var": "sr_coins"}
    read_skill_refresh_left = {
        "ocr": "SixRealms::O_SKILL_REFRESH", "mode": "remaining_times",
        "var": "sr_skill_refresh_left", "test": "sr_skill_refresh_left > 0",
    }
    read_store_refresh_left = {
        "ocr": "SixRealms::O_STORE_REFRESH_TIME", "mode": "remaining_times",
        "var": "sr_store_refresh_left", "test": "sr_store_refresh_left > 0",
    }
    state("inside_skill_refresh_confirm", "inside", [asset("I_SKILL_REFRESH"), asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 800))
    for col in (0, 1, 2):
        state(f"inside_pick_soft_wind_col{col}", "inside",
              [asset(f"I_SKILL101_COL{col}", "SixRealmsSkill"), asset(f"I_SELECT_{col}")],
              click(f"I_SELECT_{col}", delay=1000), {"inc": "sr_skills_picked"}, {"inc": "sr_soft_wind_level"})
    state("inside_pick_first_skill", "inside", [asset("I_MFIRST_SKILL")],
          click("I_MFIRST_SKILL", delay=1000), {"inc": "sr_skills_picked"})
    for col in (0, 1, 2):
        state(f"inside_pick_insight_col{col}", "inside",
              [asset(f"I_SKILL105_COL{col}", "SixRealmsSkill"), asset(f"I_SELECT_{col}")],
              click(f"I_SELECT_{col}", delay=1000), {"inc": "sr_skills_picked"})
    state("inside_skill_refresh", "inside", [
        expr("sr_skill_refreshes < sr_max_skill_refreshes and sr_soft_wind_level < 5"),
        asset("I_SKILL_REFRESH"),
        {"not": asset("I_SKILL101")},
        {"not": asset("I_SKILL105")},
        read_coins, expr("sr_coins >= 50"),
        read_skill_refresh_left,
    ], click("I_SKILL_REFRESH", delay=1000), {"inc": "sr_skill_refreshes"})
    for idx in (3, 2, 1, 0):
        state(f"inside_pick_fallback_{idx}", "inside", [asset(f"I_SELECT_{idx}")],
              click(f"I_SELECT_{idx}", delay=1000), {"inc": "sr_skills_picked"})
    state("inside_npc_team_lock", "inside", [asset("I_NPC_FIRE"), asset("I_BATTLE_TEAM_UNLOCK")],
          click("I_BATTLE_TEAM_UNLOCK", delay=800), {"set": {"sr_team_locked": True}})
    state("inside_npc_fire", "inside", [asset("I_NPC_FIRE")],
          click("I_NPC_FIRE", delay=1200), {"set": reset}, advance("in_battle"))
    for marker in ("I_ISLAND_MARKER_104", "I_ISLAND_MARKER_105", "I_ISLAND_MARKER_101",
                   "I_ISLAND_MARKER_102", "I_ISLAND_MARKER_103"):
        state(f"inside_enter_{marker.lower()}", "inside", [asset(marker)],
              {"click_found": True, "delay": 1200, "recheck": True})
    # Island l101 (宁息商店): buy in-run soft-wind skill 101 using roguelike coins up to lv5
    state("inside_l101_confirm_small", "inside", [asset("I_STORE_EXIT"), asset("I_UI_CONFIRM_SAMLL", "GlobalGame")],
          click("I_UI_CONFIRM_SAMLL", "GlobalGame", 800))
    state("inside_l101_confirm_buy", "inside", [asset("I_STORE_EXIT"), asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 800))
    state("inside_l101_buy_soft_wind", "inside", [
        expr("sr_buy_soft_wind_in_store and sr_soft_wind_level < 5"),
        asset("I_STORE_EXIT"), asset("I_STORE_SKILL_101"), read_coins, expr("sr_coins >= 300"),
    ], {"click_found": True, "offset": [-60, 0, -60, 0], "delay": 1000, "recheck": True},
          {"inc": "sr_store_buys"}, {"inc": "sr_soft_wind_level"})
    state("inside_store_open_active", "inside", [expr("sr_shop_refresh_enable"), asset("I_M_STORE_ACTIVITY")],
          click("I_M_STORE_ACTIVITY", delay=1000))
    state("inside_store_refresh", "inside", [
        expr("sr_shop_refresh_enable and sr_shop_refreshes < sr_max_shop_refreshes and sr_soft_wind_level < 5"),
        asset("I_STORE_REFRESH"), read_coins, expr("sr_coins >= sr_shop_min_coins"),
        read_store_refresh_left,
    ], click("I_STORE_REFRESH", delay=1000), {"inc": "sr_shop_refreshes"})
    state("inside_store_exit", "inside", [asset("I_STORE_EXIT")], click("I_STORE_EXIT", delay=1000))
    # Island l102 (神秘仿造/转移跳过)
    state("inside_l102_imitate_done", "inside", [asset("I_IMITATE_SUCCESS")],
          click("I_IMITATE_SUCCESS", delay=1000), {"inc": "sr_soft_wind_level"}, {"set": {"sr_imitate_tries": 0}})
    state("inside_l102_imitate_pick", "inside", [expr("sr_imitate_enable"), asset("I_IMITATE_1")],
          click("I_IMITATE_1", delay=1200))
    state("inside_l102_imitate_tap", "inside", [expr("sr_imitate_enable and sr_imitate_tries < 3"), asset("I_IMITATE")],
          click("I_IMITATE", delay=1000), {"inc": "sr_imitate_tries"})
    state("inside_l102_imitate_giveup", "inside", [expr("sr_imitate_tries >= 3"), asset("I_IMITATE"), asset("I_BACK_EXIT")],
          click("I_BACK_EXIT", delay=1200), {"set": {"sr_imitate_tries": 0}})
    state("inside_l102_transfer_exit", "inside", [asset("I_COIN_RIGHT_TOP"), asset("I_BACK_EXIT")],
          click("I_BACK_EXIT", delay=1200))
    # Island l103/l104/l105 OCR-routed NPC engagement & coin reward dismiss
    state("inside_l103_exit", "inside", [asset("I_L103_EXIT")], click("I_L103_EXIT", delay=1000))
    state("inside_l105_coin_reward", "inside", [asset("I_COIN")], click("C_UI_REWARD", "GlobalGame", 800))
    island_roi = docs["SixRealms"]["O_ISLAND_NAME"]["roi"]
    for tag, keyword, target_click in (
        ("l103", "混", "C_NPC_FIRE_CENTER"),
        ("l104", "战", "C_NPC_FIRE_RIGHT"),
        ("l105", "星", "C_NPC_FIRE_LEFT"),
    ):
        state(f"inside_{tag}_npc_engage", "inside", [
            {"not": asset("I_NPC_FIRE")},
            {"not": asset("I_L103_EXIT")},
            {"ocr_full": {"region": island_roi, "keyword": keyword}},
        ], click(target_click, delay=1200), {"set": {"sr_island_kind": repr(tag)}})
    state("inside_cancel_blessing", "inside", [asset("I_UI_CANCEL", "GlobalGame")],
          click("I_UI_CANCEL", "GlobalGame", 800))

    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("sr_next_delay_s > 0")],
          advance("stop_target", sr_target_delay_s="sr_next_delay_s", sr_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "六道之门已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "SixRealms",
                "delay_seconds_var": "sr_target_delay_s",
                "observed_ms_var": "sr_observed_ms",
            },
            "evidence": {"scope": "six_realms_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "六道之门已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "SixRealms",
            "evidence": {"scope": "six_realms_moon_sea_bounded"},
        }
    })
    state("exit_boss_shutu", "exit", [asset("I_BOSS_SHUTU")], click("I_BOSS_SHUTU", delay=1200))
    state("exit_confirm_leave", "exit", [asset("I_EXIT_SIXREALMS")], click("I_EXIT_SIXREALMS", delay=1200))
    state("exit_back_exit", "exit", [asset("I_BACK_EXIT")], click("I_BACK_EXIT", delay=1000))
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))

    raw["oas_six_realms_contract"] = {
        "source": SIX_REALMS_ENTRY,
        "source_pins": {**SIX_REALMS_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "six_realms_island_map_and_skill_routing",
            "blocking": True,
            "requirement": "Bind MoonSea island map OCR (l101-l105), soft-wind skill prioritization, shop refresh, and boss retry",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_hyakkiyakou_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Hyakkiyakou (百鬼夜行) workflow with ticket & ONNX tracker gates."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, HYA_PINS, "Hyakkiyakou")
    nav = compile_navigation_family(
        source, resources, prefix="hya_nav", destination="page_hyakkiyakou",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_hyakkiyakou_natively_staged", title="百鬼夜行", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1800
    bind_schedule(source, raw)
    raw["params"].update(
        hya_limit_count={"default": 1, "min": 0, "max": 200},
        hya_limit_seconds={"default": 1200, "min": 0, "max": 7200},
        hya_confirm_tickets={"default": False},
        hya_use_oashya_tracker={"default": False},
        hya_invite_friend={"default": False},
        hya_friend_slot={"default": 1, "min": 1, "max": 6},
        hya_boss_slot={"default": 2, "min": 1, "max": 3},
        hya_require_boss_selected={"default": False},
        hya_freeze_enabled={"default": False},
        hya_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        hya_phase="entry", hya_runs=0, hya_friend_invited=False, hya_invite_started=-1,
        hya_boss_selected_count=0, hya_freezes_used=0,
        hya_target_delay_s=0, hya_observed_ms=0, hya_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/Hyakkiyakou.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("Hyakkiyakou", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"hya_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"hya_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"hya_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Hyakkiyakou"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="Hyakkiyakou", delay=1000):
        return _click_from(docs, name, ns, delay)

    _wire_nav(raw, "hya", phase, advance, "lobby")
    state("oashya_tracker_unbound", "entry", [expr("hya_use_oashya_tracker")],
          {"fail": "百鬼夜行实时式神检测与砸豆策略依赖外部 oashya ONNX 推理契约，仍需来源绑定"})
    state("ticket_confirm_gate", "entry", [expr("hya_limit_count > 0 and not hya_confirm_tickets")],
          {"fail": "百鬼夜行入场会消耗百鬼夜行门票，需显式开启 hya_confirm_tickets"})
    state("entry_zero_skip", "entry", [expr("hya_limit_count == 0")], {
        "stop": {
            "reason": "百鬼夜行次数上限为 0，未消耗门票，安全结束",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Hyakkiyakou",
            "evidence": {"scope": "hyakkiyakou_zero_limit_skip"},
        }
    })
    state("entry_begin", "entry", [], advance("navigate"))

    state("lobby_limit", "lobby", [expr("hya_runs >= hya_limit_count")],
          advance("exit", hya_exit_reason="'count_limit'"))
    state("lobby_time_limit", "lobby", [expr("elapsed_ms >= hya_limit_seconds * 1000")],
          advance("exit", hya_exit_reason="'time_limit'"))
    state("lobby_end_dismiss", "lobby", [asset("I_HEND")], click("I_HEND", delay=1000), {"inc": "hya_runs"})
    state("lobby_invite_open", "lobby",
          [expr("hya_invite_friend and not hya_friend_invited"), asset("I_HINVITE")],
          click("I_HINVITE", delay=1000), advance("invite_friend", hya_invite_started="elapsed_ms"))
    state("lobby_access", "lobby", [asset("I_HACCESS")], click("I_HACCESS", delay=1200), advance("select_boss"))
    raw["states"][-1].update(
        sensitive="购买",
        desc="进入百鬼夜行，将消耗 1 张百鬼夜行门票。",
    )

    state("invite_done", "invite_friend", [{"not": asset("I_HINVITE")}],
          advance("lobby", hya_friend_invited=True))
    state("invite_timeout", "invite_friend", [expr("elapsed_ms - hya_invite_started >= 8000")],
          advance("lobby", hya_friend_invited=True))
    for fslot in range(1, 7):
        state(f"invite_recall_{fslot}", "invite_friend",
              [expr(f"hya_friend_slot == {fslot}"), asset("I_ENSURE_RECALL")],
              click(f"C_FRIEND_{fslot}_RECALL", delay=1200), advance("lobby", hya_friend_invited=True))
        state(f"invite_normal_{fslot}", "invite_friend",
              [expr(f"hya_friend_slot == {fslot}"), {"not": asset("I_ENSURE_RECALL")}],
              click(f"C_FRIEND_{fslot}", delay=1200), advance("lobby", hya_friend_invited=True))

    state("boss_start_selected", "select_boss",
          [expr("hya_require_boss_selected"), asset("I_HSELECTED"), asset("I_HSTART")],
          click("I_HSTART", delay=1200),
          advance("in_game", hya_friend_invited=False, hya_boss_selected_count="hya_boss_selected_count + 1"))
    state("boss_start", "select_boss", [expr("not hya_require_boss_selected"), asset("I_HSTART")],
          click("I_HSTART", delay=1200), advance("in_game", hya_friend_invited=False))
    for bslot in (1, 2, 3):
        state(f"boss_pick_{bslot}", "select_boss", [expr(f"hya_boss_slot == {bslot}"), asset("I_HTITLE")],
              click(f"C_HSELECT_{bslot}", delay=1000))

    state("game_end", "in_game", [asset("I_HEND")], click("I_HEND", delay=1200), {"inc": "hya_runs"}, advance("lobby"))
    state("game_freeze", "in_game", [expr("hya_freeze_enabled"), asset("I_HFREEZE")],
          click("I_HFREEZE", delay=800), {"inc": "hya_freezes_used"})
    state("game_time_limit", "in_game", [expr("hya_limit_seconds > 0 and elapsed_ms >= hya_limit_seconds * 1000")],
          advance("exit", hya_exit_reason="'time_limit'"))

    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("hya_next_delay_s > 0")],
          advance("stop_target", hya_target_delay_s="hya_next_delay_s", hya_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "百鬼夜行已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "Hyakkiyakou",
                "delay_seconds_var": "hya_target_delay_s",
                "observed_ms_var": "hya_observed_ms",
            },
            "evidence": {"scope": "hyakkiyakou_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "百鬼夜行已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Hyakkiyakou",
            "evidence": {"scope": "hyakkiyakou_bounded_round"},
        }
    })
    state("exit_close_red", "exit", [asset("I_HCLOSE_RED")], click("I_HCLOSE_RED", delay=1000))
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))

    raw["oas_hyakkiyakou_contract"] = {
        "source": HYA_ENTRY,
        "source_pins": {**HYA_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "hyakkiyakou_oashya_onnx_tracker_and_bean_throwing",
            "blocking": True,
            "requirement": "Bind oashya ONNX detector/tracker, fast screenshot loop, friend invite, and auto-bean aiming",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_auto_checkin_big_god_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS AutoCheckinBigGod (网易大神签到) strictly gated against Frida/external credential extraction."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, BIG_GOD_PINS, "AutoCheckinBigGod")
    nav = compile_navigation_family(
        source, resources, prefix="bg_nav", destination="page_main",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_auto_checkin_big_god_natively_staged", title="大神签到(安全受限)", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 300
    bind_schedule(source, raw)
    raw["params"].update(
        bg_enable_external_checkin={"default": False},
    )
    raw["vars"].update(bg_phase="entry")

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"bg_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"bg_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"bg_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    _wire_nav(raw, "bg", phase, advance, "done")
    state("external_frida_blocked", "entry", [expr("bg_enable_external_checkin")], {
        "fail": "网易大神自动签到(AutoCheckinBigGod)在 OAS 原版依赖 frida-server 注入第三方应用 com.netease.gl 提取登录 Token 并调用外部 HTTP API，超出游戏内安全边界，禁止自动执行",
    })
    state("disabled_safe_skip", "entry", [expr("not bg_enable_external_checkin")], {
        "stop": {
            "reason": "网易大神外部签到默认关闭(不执行 Frida 注入或第三方凭证提取)，安全跳过",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "AutoCheckinBigGod",
            "evidence": {"scope": "auto_checkin_big_god_safety_gate"},
        }
    })
    raw["oas_auto_checkin_big_god_contract"] = {
        "source": BIG_GOD_ENTRY,
        "source_pins": {**BIG_GOD_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "auto_checkin_big_god_external_app_safety_boundary",
            "blocking": True,
            "requirement": "Upstream uses frida-server memory/auth-DB token extraction on com.netease.gl + external HTTP APIs; requires an explicit compliant non-Frida external contract",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
