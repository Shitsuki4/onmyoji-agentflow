"""Guarded weekly shop handlers from the pinned assttyys snapshot (MIT, Chaos)."""
from .core_handlers import _push
from .handlers import _count
from .team_handlers import _all, _expr


def _taps(b, index):
    actions = b.actions(index)
    return [{**actions[0], "recheck": True}, *actions[1:]] if actions else []


def _purchase_gate(b, name, index, guard, lines, *, counts=()):
    when = _all(guard, b.when(index))
    pending = b.gap(name, lines, when,
        [{"effect": "source_purchase_sequence", "operator": index, "actions": b.actions(index)}], True,
        ["bind item, currency and quantity before individual purchase approval", "fresh dialog evidence after quantity changes"])
    b.add(name, when, [pending], counts=counts)


def _shop_menus(b, prefix, guard, indices, *, counts=()):
    for index in indices:
        b.add(f"{prefix}_{index}", _all(guard, b.when(index)), _taps(b, index), counts=counts)


def _guild_merit_shop(b):
    stage = "MT_liaoShop"
    start = _expr(f"{stage} == 'start'")
    back = _expr(f"{stage} == 'back'")
    b.model["vars"] = {stage: "start"}
    counts = [_count(1101)]
    _shop_menus(b, "merit_enter", start, (0, 1, 2, 3), counts=counts)
    for index in (15, 16, 17, 18):
        _purchase_gate(b, f"merit_confirm_{index}", index, _expr(f"{stage} != 'end'"), (362, 371), counts=counts)
    selection = _expr(" or ".join(b.model["params"]))
    shop = {"any": [b.when(4), b.when(20)]}
    b.add("merit_no_products", _all(start, shop, {"not": selection}), [{"set": {stage: repr("back")}}], counts=counts)
    pending = _all(start, shop, selection)
    check = b.gap("merit_select_products", (344, 427), pending,
        [{"effect": "source_ordered_ocr_selection", "parameters": list(b.model["params"]),
          "ocr_geometry": b.ops[14]["oper"][2], "swipe_geometry": b.ops[14]["oper"][:2]}], True,
        ["identify configured item names and distinguish similarly named inventory", "preserve source three-scan and three-swipe limits"])
    b.add("merit_select_products", pending, [check], counts=counts)
    _shop_menus(b, "merit_return", back, (4,), counts=counts)
    b.add("merit_returned_to_courtyard", _all(back, b.when(19)), [{"set": {stage: repr("end")}}], counts=counts)


def _weekly_market(b):
    stage = "MT_shop"
    live_back = "zhiBoBack"
    loading = "weekly_shop_load_checks"
    b.model["vars"] = {stage: "zhiBo", live_back: False, loading: 0}
    counts = [_count(1102)]

    def at(value):
        return _expr(f"{stage} == {value!r}")

    def move(value):
        return {"set": {stage: repr(value)}}

    def skip(name, destination, configured):
        enabled = _expr(" or ".join(configured))
        b.add(f"market_skip_{name}", _all(at(name), {"not": enabled}), [move(destination)], internal=True)

    charm_options = ("meiLi_lanPiao", "meiLi_heiSui")
    honor_options = tuple(key for key in b.model["params"] if key.startswith("rongYu_"))
    medal_options = tuple(key for key in b.model["params"] if key.startswith("oper_"))
    special_options = ("teSu_yuling", "teSu_qiling")
    live = at("zhiBo")
    before = _all(live, _expr(f"not {live_back}"))
    after = _all(live, _expr(live_back))
    skip("zhiBo", "jiShouWu", charm_options)
    _shop_menus(b, "market_stream_open", before, (38, 39, 40, 41, 42), counts=counts)
    _purchase_gate(b, "market_stream_gift", 43, before, (801, 808), counts=counts)
    _shop_menus(b, "market_stream_exit", after, (40, 44, 45), counts=counts)
    b.add("market_stream_returned", _all(after, b.when(46)), [*_taps(b, 46), move("jiShouWu")], counts=counts)
    loading_screen = _all(live, b.when(48))
    b.add("market_stream_loading_timeout", _all(loading_screen, _expr(f"{loading} == 4")),
          [*_taps(b, 48), move("jiShouWu")], counts=counts, outcome=False)
    b.add("market_stream_loading", loading_screen, [{"inc": loading}, {"wait": 1000}], counts=counts)

    consign = at("jiShouWu")
    skip("jiShouWu", "miJuanWu", ("jiShouWu",))
    _shop_menus(b, "market_consign", consign, (2, 3, 4), counts=counts)
    _purchase_gate(b, "market_consign_confirm", 5, consign, (836, 841), counts=counts)
    b.add("market_consign_done", _all(consign, b.when(6)), [*_taps(b, 6), move("miJuanWu")], counts=counts)

    scroll = at("miJuanWu")
    skip("miJuanWu", "zaHuoPu_teSu", ("miJuanWu",))
    _shop_menus(b, "market_scroll", scroll, (7, 8), counts=counts)
    _purchase_gate(b, "market_scroll_purchase", 9, scroll, (880, 886), counts=counts)
    # A recognized post-purchase shop state remains necessary before moving between shops.
    _shop_menus(b, "market_entry", _expr(f"{stage} != 'done'"), (0, 1, 10, 47), counts=counts)

    special = at("zaHuoPu_teSu")
    _purchase_gate(b, "market_special_purchase", 12, special, (894, 901), counts=counts)
    skip("zaHuoPu_teSu", "zaHuoPu_rongYu", special_options)
    b.add("market_special_overflow", _all(special, b.when(13)),
          [*_taps(b, 13), move("zaHuoPu_rongYu")], counts=counts)
    for option, asset in zip(special_options, ("御灵票", "契灵盘"), strict=True):
        b.add(f"market_select_{option}", _all(special, b.when(11), _expr(option), {"find": asset}),
              [{"click_found": True, "offset": [-15, -15, 15, 15], "delay": 200, "recheck": True}], counts=counts)

    honor = at("zaHuoPu_rongYu")
    skip("zaHuoPu_rongYu", "zaHuoPu_youQing", honor_options)
    _shop_menus(b, "market_open_honor", honor, (14,), counts=counts)
    for index in (12, 16, 17, 18):
        _purchase_gate(b, f"market_honor_confirm_{index}", index, honor, (945, 951), counts=counts)
    for option in honor_options:
        # The source mutates its requested-list order before buying multiple distinct products.
        found = _all(honor, b.when(15), _expr(option), {"find": option})
        pending = b.gap(f"market_honor_item_{option}", (952, 981), found,
            [{"effect": "source_select_honor_product", "source_key": option}], True,
            ["preserve ordered product selection and verify the pending purchase"])
        b.add(f"market_honor_item_{option}", found, [pending], counts=counts)

    friend = at("zaHuoPu_youQing")
    skip("zaHuoPu_youQing", "zaHuoPu_xunZhang", ("youQing_baiDan",))
    b.add("market_friend_done", _all(friend, b.when(22)), [*_taps(b, 22), move("zaHuoPu_xunZhang")], counts=counts)
    _shop_menus(b, "market_friend", friend, (19, 20), counts=counts)
    _purchase_gate(b, "market_friend_purchase", 21, friend, (996, 1001), counts=counts)

    medal = at("zaHuoPu_xunZhang")
    skip("zaHuoPu_xunZhang", "zaHuoPu_meiLi", medal_options)
    _shop_menus(b, "market_medal", medal, (23, 32), counts=counts)
    for index in (16, 31):
        _purchase_gate(b, f"market_medal_confirm_{index}", index, medal, (1017, 1034), counts=counts)
    for option in reversed(medal_options):
        index = int(option.removeprefix("oper_"))
        _shop_menus(b, "market_medal_product", _all(medal, b.when(24), _expr(option)), (index,), counts=counts)

    charm = at("zaHuoPu_meiLi")
    skip("zaHuoPu_meiLi", "done", charm_options)
    _shop_menus(b, "market_charm", charm, (33,), counts=counts)
    for index in (16, 37):
        _purchase_gate(b, f"market_charm_confirm_{index}", index, charm, (1080, 1086), counts=counts)
    for option, index in (("meiLi_heiSui", 35), ("meiLi_lanPiao", 34)):
        _shop_menus(b, "market_charm_product", _all(charm, b.when(36), _expr(option)), (index,), counts=counts)

    # The source mixes separate retry loops with operator-index transitions between stores.
    for name, index, lines in (("zaHuoPu_teSu", 11, (913, 936)), ("zaHuoPu_rongYu", 15, (952, 981)),
                               ("zaHuoPu_xunZhang", 24, (1038, 1063)), ("zaHuoPu_meiLi", 36, (1087, 1115))):
        condition = _all(at(name), b.when(index))
        pending = b.gap(f"market_{name}_scan", lines, condition,
                      [{"effect": "source_controlled_scan", "phase": name, "recognition": index}], False,
                      ["verified scroll/retry and transition for exhausted configured stock"])
        b.add(f"market_{name}_scan", condition, [pending], counts=counts)


def _curio_exchange(b):
    active = _expr("zhenLvJu")
    b.model["vars"] = {"zhenLvJu": True, "curio_checks": 0}
    counts = [_count(1104)]
    _shop_menus(b, "curio_open", active, (0, 1, 19), counts=counts)
    page = _all(active, b.when(2))
    refresh = {"handler_control": {"op": "refresh"}}
    b.add("curio_init", active, [{"set": {"curio_checks": 0}}], outcome=None, internal=True)
    b.add("curio_read_page", page, [*_taps(b, 2), {"inc": "curio_checks"}], counts=counts, outcome=None)
    for index in range(3, 14):
        _shop_menus(b, "curio_product", _all(page, _expr(f"oper_{index}")), (index,), counts=counts)
    b.add("curio_leave", _all(page, _expr("curio_checks >= 10")),
          [*_taps(b, 17), {"set": {"zhenLvJu": False}}], outcome=False)
    start, end = b.actions(18)
    at_five = _all(page, _expr("curio_checks == 5"))
    motion = b.gap("curio_scroll_timing", (373, 374), at_five, [{"effect": "source regionSwipe"}], None,
        ["preserve explicit source swipe delay"], blocking=False)
    b.add("curio_scroll", at_five, [motion], outcome=None)
    edge = "unresolved_source_obligation:team1104.curio_scan requires team_workflow"
    b.add("curio_recheck", page, [refresh, {"wait": 1000}, {"fail": edge}], outcome=None, internal=True)
    for index in (14, 15, 16):
        _purchase_gate(b, f"curio_confirm_{index}", index, active, (383, 395), counts=counts)
    b.model["proof"]["source_phase_edges"] = {"curio_recheck": {"target_case": "curio_read_page", "gate_prefix": edge}}
    b.model["proof"]["source_native_lowerings"] = {"curio_scroll": {"gate_prefix": motion["fail"],
        "native_intent": {"swipe": {"from": start["click"], "to": end["click"]},
                          "duration_ms": [400, 450], "delay": 500}}}


def _style_tickets(b):
    active = _expr("fengZi")
    done = {"set": {"fengZi": False}}
    counts = [_count(1103)]
    b.model["vars"] = {"fengZi": True}
    b.add("style_gold_daruma", _all(active, b.when(7)), [*_taps(b, 7), done], counts=counts)
    for index in (0, 1, 4):
        b.add(f"style_open_{index}", _all(active, b.when(index)), _taps(b, index), counts=counts)
    _purchase_gate(b, "style_purchase", 5, active, (154, 160), counts=counts)
    start, end = b.actions(3)
    condition = _all(active, b.when(2))
    motion = b.gap("style_scroll_timing", (161, 169), condition,
        [{"effect": "source regionSwipe", "duration_ms": [200, 300], "after_ms": 1500}], True,
        ["preserve explicit source swipe delay"], blocking=False)
    b.add("style_redeem_tab", condition, [*_taps(b, 2), motion, start], counts=counts)
    b.model["proof"]["source_native_lowerings"] = {"style_redeem_tab": {"gate_prefix": motion["fail"],
        "native_intent": {"swipe": {"from": start["click"], "to": end["click"]},
                          "duration_ms": [200, 300], "delay": 1500}}}
    b.add("style_next_group", _all(active, b.when(6)), _taps(b, 6), counts=counts)
    b.add("style_finished", _all(active, b.when(8)), [*_taps(b, 8), done], counts=counts)


def _shrine_daruma(b):
    active = _expr("shenKan")
    inactive = _expr("not shenKan")
    done = {"set": {"shenKan": False}}
    counts = [_count(1105)]
    b.model["vars"] = {"shenKan": True}
    for index in (0, 1, 4):
        b.add(f"daruma_enter_{index}", _all(active, b.when(index)), _taps(b, index), counts=counts)
    _purchase_gate(b, "daruma_exchange", 5, active, (140, 146), counts=counts)
    _purchase_gate(b, "daruma_confirm_exchange", 6, active, (147, 154), counts=counts)
    b.add("daruma_already_exchanged", _all(active, b.when(8)), [done], counts=counts)
    b.add("daruma_leave_shrine", _all(inactive, b.when(2)), _taps(b, 2), counts=counts)
    failed = _all(inactive, b.when(7))
    b.gap("daruma_insufficient_notice", (164, 169), failed, [_push("无御札,兑换失败")], True,
          ["authorized source notification or local ringtone"], blocking=False)
    b.add("daruma_close_failed", failed, [*_taps(b, 7), {"log": "无御札，兑换失败"}], counts=counts)


def _qiling_shop(b):
    active = _expr("qiling_shop")
    done = {"set": {"qiling_shop": False}}
    counts = [_count(1107)]
    b.model["vars"] = {"qiling_shop": True}
    for index in (0, 1, 6, 7):
        b.add(f"qiling_shop_enter_{index}", _all(active, b.when(index)), _taps(b, index), counts=counts)
    _purchase_gate(b, "qiling_shop_purchase", 3, active, (113, 132))
    for index in (2, 4, 5):
        finished = _all(active, b.when(index))
        b.add(f"qiling_shop_sold_out_{index}", finished, [done, {"log": "契灵商店御魂已兑换"}], counts=counts)
    b.gap("qiling_shop_notice", (134, 141), {"source_operators": [2, 4, 5]},
          [_push("兑换完毕")], True, ["authorized source notification or local ringtone"], blocking=False)


def _chess_shop(b):
    active = _expr("chessShop")
    done = {"set": {"chessShop": False}}
    b.model["vars"] = {"chessShop": True, "chessShopNum": 0}
    courtyard = {"any": [b.when(index) for index in range(4)]}
    b.add("chess_shop_town", _all(active, courtyard, {"find": "庭院_町中竖牌"}), [
          {"click_found": True, "offset": [0, 0, 10, 10], "delay": 1000, "recheck": True}])
    for index in (4, 5, 6, 9):
        b.add(f"chess_shop_enter_{index}", _all(active, b.when(index)), _taps(b, index))
    _purchase_gate(b, "chess_shop_purchase", 7, active, (117, 128))
    b.add("chess_shop_purchase_complete", b.when(8), [*_taps(b, 8), done])


def build_weekly_shop(b):
    builders = {1101: _guild_merit_shop, 1102: _weekly_market, 1103: _style_tickets, 1104: _curio_exchange,
                1105: _shrine_daruma, 1107: _qiling_shop, 1111: _chess_shop}
    builders[b.fid](b)
    b.model["proof"]["source_state_bindings"] = {f"global.{key}": key for key in b.model["vars"]}
    b.model["proof"]["resource_costs"] = "Purchase dialogs require verified item, currency and quantity before approval."
