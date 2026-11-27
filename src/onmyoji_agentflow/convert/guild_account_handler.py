"""Pinned 609 account rotation and guild dailies (MIT, Copyright 2019 Chaos)."""
from __future__ import annotations

from .core_handlers import _rerun
from .handlers import _count
from .team_handlers import _all, _expr


def build_guild_account_flow(b):
    stage = "guild609_stage"
    index = "guild609_account_index"
    valid = "guild609_valid_accounts"
    double = "guild609_dual_platform"
    select = "guild609_switch_account"
    checks = "guild609_checks"
    features = ("juanGouYu", "shouLieZhan", "liaoSanshi", "agency", "regionBoos", "card",
                "qiLin_Fifty", "yuHun_Fifty", "buy_Petal", "add_Petal", "xuanShang")
    pending = {name: f"guild609_{name}" for name in features}
    b.model["vars"] = {stage: "login", index: 0, valid: 0, double: False, select: True, checks: 0, "run_times_2": 0,
                      **dict.fromkeys(pending.values(), False)}
    b.model["proof"]["source_phase_edges"] = edges = {}
    b.model["proof"]["source_native_lowerings"] = native = {}
    counts = [_count(609)]
    refresh = {"handler_control": {"op": "refresh"}}
    login = _expr(f"{stage} == 'login'")
    functions = _expr(f"{stage} == 'functions'")
    logout = _expr(f"{stage} == 'logout'")
    court = b.when(5)

    def tap(*actions):
        return [{**actions[0], "recheck": True}, *actions[1:]]

    def operators(name, guard, indices, tail=()):
        for op in indices:
            b.add(f"guild609_{name}_{op}", _all(guard, b.when(op)), [*tap(*b.actions(op)), *tail],
                  counts=counts, retest_ms=b.ops[op].get("retest"))

    def repeat(name, target, condition, actions=()):
        gate = f"unresolved_source_obligation:team609.{name} requires team_workflow"
        b.add(name, condition, [*actions, {"fail": gate}], outcome=None, internal=True)
        edges[name] = {"target_case": target, "gate_prefix": gate}

    def block(name, lines, condition, effect, *requirements):
        gap = b.gap(name, lines, condition, [{"effect": effect}], True, requirements)
        b.add(name, condition, [gap])

    true = _expr("True")
    block("guild609_account_suspended", (1578, 1590), b.when(99), "account suspension screen",
          "account holder review before continuing")
    operators("dismiss", true, (59, 61, 64, 78))
    operators("agency_limit", true, (63,), [{"set": {pending["agency"]: False}}])
    account_cap = _all(login, _expr(f"{valid} >= account_count"))
    gap = b.gap("guild609_complete_accounts", (1607, 1612), account_cap, [_rerun({"config": "next_scheme"})],
                True, ["bind next scheme or close-application command"])
    b.add("guild609_complete_accounts", account_cap, [gap])
    operators("login_open", _all(login, _expr(select)), (0, 1))
    choose = _all(login, b.when(2))
    direct = f"{index} == 0 or ({double} and {index} % 2 == 1)"
    for test, step, label in ((direct, 0, "enter"), (f"not ({direct})", 1, "expand")):
        b.add(f"guild609_account_{label}", _all(choose, _expr(test)),
              [*tap(b.actions(2)[step]), {"set": {select: False}}], counts=counts)
    for op in (4, 53):
        for platform in (0, 1):
            b.add(f"guild609_platform_{op}_{platform}", _all(login, b.when(op), _expr(f"{index} % 2 == {platform}")),
                  [*tap(b.actions(op)[platform]), {"set": {double: True}}], counts=counts)
    picker = _all(login, b.when(3))
    start, end, select_last = b.actions(3)
    bottom = _all(picker, b.when(97))
    b.add("guild609_select_last", bottom, [*tap(select_last), b.actions(2)[0]], counts=[*counts, *counts])
    scroll = _all(picker, {"not": b.when(97)})
    gap = b.gap("guild609_account_scroll", (1660, 1672), scroll, [{"effect": "source regionSwipe"}], True,
                ["preserve source picker scroll duration"], blocking=False)
    b.add("guild609_account_scroll", scroll, [gap], counts=counts)
    native["guild609_account_scroll"] = {"gate_prefix": gap["fail"], "native_intent": {
        "swipe": {"from": start["click"], "to": end["click"]}, "duration_ms": [500, 700], "delay": 500,
        "recheck": True}}
    operators("missing_character", login, (62,), [{"inc": index}, {"set": {select: True}}])

    b.add("guild609_court_init", login, [{"set": {checks: 0}}], outcome=None, internal=True)
    b.add("guild609_court_check", _all(login, court), [{"inc": checks}, refresh], outcome=None, counts=counts)
    feature_defaults = {pending[name]: "card != '关闭'" if name == "card" else name for name in features}
    b.add("guild609_court_ready", _all(login, _expr(f"{checks} == 6")),
          [{"wait": 500}, {"set": {stage: "'functions'", **feature_defaults}}])
    repeat("guild609_court_retry", "guild609_court_check", _all(login, court))
    b.add("guild609_skin_ad", _all(login, {"find": "皮肤广告关闭按钮"}),
          [{"click_found": True, "offset": [-10, -10, 0, 0], "delay": 1000, "recheck": True}])
    operators("login_continue", login, (100, 101, 108))

    def feature(name):
        return _all(functions, _expr(pending[name]))

    def clear(name):
        return {"set": {pending[name]: False}}

    def retries(name, op, limit, delay):
        flag = feature(name)
        prefix = f"guild609_{name}"
        b.add(f"{prefix}_init", flag, [{"set": {checks: 0}}], outcome=None, internal=True)
        step = _all(flag, b.when(op))
        b.add(f"{prefix}_try", step, [*tap(*b.actions(op)), {"inc": checks}, refresh], outcome=None, counts=counts)
        b.add(f"{prefix}_limit", _all(flag, _expr(f"{checks} == {limit}")), [clear(name)])
        repeat(f"{prefix}_again", f"{prefix}_try", step, [{"wait": delay}])

    jade = feature("juanGouYu")
    operators("guild_info", jade, (7, 8))
    retries("juanGouYu", 9, 2, 500)
    block("guild609_jade_donation", (1739, 1747), _all(jade, b.when(10)), "source 100-jade donation",
          "fresh donation amount and explicit user confirmation")

    block("guild609_hunt_clock", (1749, 1765), _all(feature("shouLieZhan"), court),
          "conditional guild hunt", "bind source weekday and hour to server clock")
    block("guild609_team_thirty", (1767, 1922), _all(feature("liaoSanshi"), court),
          "source guild team task", "verify team selection, prestorage and OCR counters")
    agency = feature("agency")
    retries("agency", 33, 2, 1000)
    operators("agency", agency, (36, 67, 37, 38, 39, 40, 41, 42, 32, 34, 54, 55, 56, 58))
    block("guild609_area_boss", (1951, 2014), _all(feature("regionBoos"), court),
          "source favourite boss and reward sequence", "verify three selection branches and stage counters")
    block("guild609_card", (2015, 2076), _all(feature("card"), court),
          "source realm card activation", "verify chosen card type and activation input")
    block("guild609_awaken_fifty", (2077, 2099), _all(feature("qiLin_Fifty"), court),
          "source fifty awakening runs", "verify reset and battle result counter")
    block("guild609_soul_fifty", (2100, 2122), _all(feature("yuHun_Fifty"), court),
          "source fifty soul runs", "verify reset and battle result counter")
    purchase = feature("buy_Petal")
    operators("open_merit", purchase, (7, 83, 84, 85, 87))
    block("guild609_purchase_petals", (2132, 2138), _all(purchase, b.when(88)),
          "source petal purchase", "verify displayed item, quantity, price and user confirmation")
    operators("petal_slot_changed", purchase, (89,), [clear("buy_Petal")])
    block("guild609_offer_petals", (2141, 2179), _all(feature("add_Petal"), court),
          "source seasonal offering", "verify seasonal banner and resource submission")
    bounty = feature("xuanShang")
    b.add("guild609_open_bounty", _all(bounty, court, {"find": "悬赏_庭院检测悬赏图标"}),
          [{"click_found": True, "offset": [0, 0, 20, 20], "delay": 1000, "recheck": True}])
    bounty_screen = _all(bounty, b.when(95))
    block("guild609_bounty_capture", (2190, 2213), _all(bounty_screen, {"find": "悬赏_勾玉协作"}),
          "source crops and stores the account-name region", "verify consent and private local capture destination")
    operators("bounty_close", bounty, (95,), [clear("xuanShang")])

    remaining = " or ".join(pending[name] for name in features if name != "xuanShang")
    b.add("guild609_start_logout", _all(functions, court, _expr(f"not ({remaining})")),
          [{"set": {stage: "'logout'"}}], counts=counts)
    operators("logout", logout, (5, 6))
    b.add("guild609_logout_seen", _all(logout, b.when(1)),
          [{"inc": index}, {"inc": valid}, {"set": {stage: "'login'", select: True}}], counts=counts)
    operators("close", true, (35, 43, 66, 72, 86, 93, 96, 97))
