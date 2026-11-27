"""Native Scales exchange states tied to the pinned RichMan shop contract."""


DEMON_SOULS = ("土蜘蛛", "胧车", "荒骷髅", "地震鲶", "蜃气楼", "鬼灵歌伎", "夜荒魂")
DEMON_POSITIONS = ("一号位", "二号位", "三号位", "四号位", "五号位", "六号位")


def bind_scales_demon(raw, state, advance, asset, click, expr):
    """Bind the boss catalogue, the chosen slot and one guarded exchange at a time."""
    raw["params"].update(
        rm_scales_demon_count={"default": 0, "min": 0, "max": 999},
        rm_scales_demon_kind={"default": DEMON_SOULS[0], "choices": list(DEMON_SOULS)},
        rm_scales_demon_position={"default": 1, "min": 1, "max": 6},
        rm_scales_demon_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_scales_demon_reserve={"default": 0, "min": 0, "max": 99999999},
    )
    raw["vars"].update(
        rm_scales_demon_balance=-1, rm_scales_demon_detail_balance=-1, rm_scales_demon_stock=-1,
        rm_scales_demon_balance_before=-1, rm_scales_demon_stock_before=-1,
        rm_scales_demon_spent=0, rm_scales_demon_bought=0, rm_scales_demon_swipes=0,
        rm_scales_demon_slot_reads=0, rm_scales_demon_detail_title="",
    )
    raw.setdefault("inline_resources", {})["RichManScales::O_DEMON_DETAIL_BALANCE"] = {
        "type": "ocr", "mode": "Digit", "roi": [1157, 25, 47, 23],
    }
    shop = asset("I_MALL_SCCALES_CHECK")
    offer = asset("I_SCA_DEMON_SOULS")
    close_region = [f"rm_scales_demon_close_{axis}" for axis in ("x", "y", "w", "h")]
    raw["vars"].update(zip(close_region, (1104, 92, 93, 86)))
    close = {**asset("I_UI_BACK_RED", "GlobalGame"), "region_vars": close_region}
    detail = asset("I_SCA_DEMON_BUY")
    plus = asset("I_BUY_PLUS", "Component_Buy")
    catalogue = {"all": [close, {"not": detail}, {"not": plus}]}
    balance = {"ocr": "RichMan::O_SCA_RES_DEMON", "mode": "exact_quantity", "var": "rm_scales_demon_balance"}
    modal_balance = {"ocr": "RichManScales::O_DEMON_DETAIL_BALANCE", "mode": "exact_quantity",
                     "var": "rm_scales_demon_detail_balance"}
    stock = {"ocr": "RichMan::O_SCA_NUMBER_DEMON", "mode": "exact_quantity", "var": "rm_scales_demon_stock"}
    quantity = {"ocr": "Component_Buy::O_BUY_NUMBER", "mode": "exact_quantity", "var": "rm_quantity"}
    price = {"ocr": "Component_Buy::O_BUY_PRICE", "mode": "exact_quantity", "var": "rm_price"}
    chosen = {"ocr_single": {"region": [835, 244, 235, 41], "equals_var": "rm_scales_demon_detail_title"}}
    rewarded = {"any": [asset("I_SCA_SIX_STAR"), asset("I_SCA_REWARD")]}

    def timeout(ms):
        return expr(f"elapsed_ms - rm_started >= {ms}")

    room_in_budget = "rm_scales_demon_spent + 50 <= rm_scales_demon_max_budget"
    room_in_balance = "rm_scales_demon_balance - rm_scales_demon_reserve >= 50"
    source_minimum = ("rm_scales_demon_bought == 0 and rm_scales_demon_count > 1 "
                      "and rm_scales_demon_stock > 1 and rm_scales_demon_balance < 100")
    state("scales_demon_disabled", "scales_demon_offer",
          [expr(f"rm_scales_demon_bought >= rm_scales_demon_count or not ({room_in_budget})")],
          advance("scales_sea_offer"))
    state("scales_demon_unavailable", "scales_demon_offer", [shop, {"not": offer}], advance("scales_sea_offer"))
    state("scales_demon_exhausted", "scales_demon_offer", [shop, offer, stock, balance,
          expr(f"rm_scales_demon_stock == 0 or not ({room_in_balance}) or ({source_minimum})")],
          advance("scales_sea_offer"))
    state("scales_demon_open_catalogue", "scales_demon_offer", [shop, offer, stock, balance,
          expr(f"rm_scales_demon_stock > 0 and ({room_in_balance}) and not ({source_minimum})")],
          click("I_SCA_DEMON_SOULS", delay=800),
          advance("scales_demon_catalogue", rm_started="elapsed_ms", rm_scales_demon_swipes=0,
                  rm_scales_demon_balance_before="rm_scales_demon_balance", rm_scales_demon_stock_before="rm_scales_demon_stock"))
    state("scales_demon_unreadable", "scales_demon_offer", [shop, offer],
          {"fail": "无法核对首领御魂库存或逢魔之魂余额"})

    boss_label = {"ocr_full": {"region": [158, 144, 960, 520], "selection": "unique_equals",
                               "keyword_var": "rm_scales_demon_kind"}}
    state("scales_demon_choose_boss", "scales_demon_catalogue", [catalogue, boss_label],
          {"click_found": True, "use_match_size": True, "recheck": True, "delay": 800},
          advance("scales_demon_position", rm_started="elapsed_ms", rm_scales_demon_slot_reads=0))
    for direction, bound, start_y, end_y in (("down", "rm_scales_demon_swipes < 4", 570, 265),
                                             ("up", "4 <= rm_scales_demon_swipes < 8", 265, 570)):
        state(f"scales_demon_scroll_{direction}", "scales_demon_catalogue", [catalogue, expr(bound), {"not": timeout(25000)}],
              {"swipe": {"from": [905, start_y, 918, start_y + 8], "to": [905, end_y, 918, end_y + 8]},
               "duration_ms": [500, 540], "delay": 750, "recheck": True},
              {"inc": "rm_scales_demon_swipes"})
    state("scales_demon_catalogue_unresolved", "scales_demon_catalogue",
          [{"any": [timeout(25000), expr("rm_scales_demon_swipes >= 8")]}],
          {"fail": "首领目录中未唯一识别配置的御魂，未兑换"})

    for position, slot in enumerate(DEMON_POSITIONS, 1):
        active = expr(f"rm_scales_demon_position == {position}")
        state(f"scales_demon_select_position_{position}", "scales_demon_position", [detail, {"not": plus}, active,
              expr("rm_scales_demon_slot_reads == 0")], click(f"C_SCA_DEMON_{position}", delay=800),
              advance("scales_demon_position", rm_scales_demon_slot_reads=1,
                      rm_scales_demon_detail_title=f"rm_scales_demon_kind + {'·' + slot!r}"))
        for index, name in enumerate(DEMON_SOULS, 1):
            quote_titles = {"any": [{"ocr_single": {"region": [510, 140, 260, 52], "equals": title}}
                           for title in (f"{name}·{slot}", f"{name}{slot}", f"  {name}{slot} ")]}
            state(f"scales_demon_confirm_{index}_{position}", "scales_demon_quote",
                  [active, expr(f"rm_scales_demon_kind == {name!r}"), plus, quote_titles,
                   {"not": asset("I_BUY_RMB", "Component_Buy")}, quantity, price, modal_balance,
                   expr(f"rm_quantity == 1 and rm_price == 50 and ({room_in_budget}) "
                        "and rm_scales_demon_detail_balance == rm_scales_demon_balance_before")],
                  click("C_BUY_MORE", "Component_Buy", 800),
                  advance("scales_demon_reward", rm_started="elapsed_ms",
                          rm_scales_demon_spent="rm_scales_demon_spent + 50"))
            raw["states"][-1].update(sensitive="购买", desc=f"兑换一件{name}·{slot}，消耗 50 逢魔之魂。")

    state("scales_demon_open_quote", "scales_demon_position", [expr("rm_scales_demon_slot_reads == 1"), detail,
          {"not": plus}, chosen, modal_balance,
          expr("rm_scales_demon_detail_balance == rm_scales_demon_balance_before")],
          click("I_SCA_DEMON_BUY", delay=800), advance("scales_demon_quote", rm_started="elapsed_ms"))
    state("scales_demon_position_unverified", "scales_demon_position", [timeout(14000)],
          {"fail": "首领御魂和位置未获得标题及余额验证，未兑换"})
    state("scales_demon_cancel_quote", "scales_demon_quote", [plus, timeout(10000)],
          click("C_BUY_CANCEL", "Component_Buy", 500), advance("scales_demon_cancelled", rm_started="elapsed_ms"))
    state("scales_demon_quote_missing", "scales_demon_quote", [timeout(15000)],
          {"fail": "未识别首领御魂兑换报价"})
    state("scales_demon_cancel_verified", "scales_demon_cancelled", [detail, {"not": plus}],
          {"fail": "首领御魂报价未通过核对，已取消"})
    state("scales_demon_cancel_missing", "scales_demon_cancelled", [timeout(8000)],
          {"fail": "首领御魂报价未确认关闭"})

    state("scales_demon_dismiss_reward", "scales_demon_reward", [rewarded],
          click("C_SCA_SOULS_BACK", delay=1000), advance("scales_demon_settle", rm_started="elapsed_ms"))
    state("scales_demon_reward_missing", "scales_demon_reward", [timeout(12000)],
          {"fail": "首领御魂提交后未识别奖励，停止后续兑换"})
    state("scales_demon_close_detail", "scales_demon_settle", [detail, chosen, {"not": plus}, {"not": rewarded}],
          click("C_SCA_SOULS_BACK", delay=800))
    state("scales_demon_close_catalogue", "scales_demon_settle", [catalogue, {"not": rewarded}],
          {"click_found": True, "use_match_size": True, "recheck": True, "delay": 800})
    state("scales_demon_debit_verified", "scales_demon_settle", [shop, offer, {"not": close}, {"not": plus},
          balance, stock, expr("rm_scales_demon_balance == rm_scales_demon_balance_before - 50 "
                               "and rm_scales_demon_stock == rm_scales_demon_stock_before - 1")],
          {"inc": "rm_transactions"}, advance("scales_demon_offer", rm_scales_demon_bought="rm_scales_demon_bought + 1"))
    state("scales_demon_debit_missing", "scales_demon_settle", [timeout(14000)],
          {"fail": "首领御魂兑换后未核对扣款及库存，停止后续兑换"})


def bind_scales_sea(raw, state, advance, asset, click, expr):
    """Bind the manual three-option exchange with the current Sea quote geometry."""
    raw["params"].update(
        rm_scales_sea_count={"default": 0, "min": 0, "max": 999},
        rm_scales_sea_auto={"default": False},
        rm_scales_sea_max_budget={"default": 0, "min": 0, "max": 999999},
        rm_scales_sea_reserve={"default": 0, "min": 0, "max": 99999999},
    )
    raw["vars"].update(
        rm_scales_sea_balance=-1, rm_scales_sea_stock=-1,
        rm_scales_sea_balance_before=-1, rm_scales_sea_stock_before=-1,
        rm_scales_sea_spent=0, rm_scales_sea_bought=0, rm_scales_sea_batch=0,
    )
    raw.setdefault("inline_resources", {})["RichManScales::O_SEA_QUOTE_PRICE"] = {
        "type": "ocr", "mode": "Digit", "roi": [637, 573, 65, 42],
    }
    shop = asset("I_MALL_SCCALES_CHECK")
    offer = asset("I_SCA_PICTURE_BOOK")
    plus = asset("I_BUY_PLUS", "Component_Buy")
    quote = {"all": [plus, {"ocr_single": {"region": [515, 140, 250, 56], "equals": "海汐的御魂礼盒"}}]}
    balance = {"ocr": "RichMan::O_SCA_RES_SEA", "mode": "exact_quantity", "var": "rm_scales_sea_balance"}
    stock = {"ocr": "RichMan::O_SCA_NUMBER_SEA", "mode": "exact_quantity", "var": "rm_scales_sea_stock"}
    quantity = {"ocr": "Component_Buy::O_BUY_NUMBER", "mode": "exact_quantity", "var": "rm_quantity"}
    price = {"ocr": "RichManScales::O_SEA_QUOTE_PRICE", "mode": "exact_quantity", "var": "rm_price"}
    # In the archived one- and two-unit offers the unchecked box has a plain brown interior.
    manual_toggle = {"mean_color": {"region": [551, 531, 9, 9], "rgb": [118, 99, 81], "tolerance": 5}}
    noncash = {"not": asset("I_BUY_RMB", "Component_Buy")}

    def timeout(ms):
        return expr(f"elapsed_ms - rm_started >= {ms}")

    def can_buy(count):
        cost = f"200 * ({count})"
        return expr(
            f"{count} <= rm_scales_sea_count - rm_scales_sea_bought and {count} <= rm_scales_sea_stock "
            f"and {cost} <= rm_scales_sea_balance - rm_scales_sea_reserve "
            f"and {cost} <= rm_scales_sea_max_budget - rm_scales_sea_spent"
        )

    state("scales_sea_disabled", "scales_sea_offer", [expr("rm_scales_sea_count == 0")], advance("bondlings_dispatch"))
    state("scales_sea_auto_unverified", "scales_sea_offer", [expr("rm_scales_sea_auto")],
          {"fail": "海汐礼盒的自动选择尚缺实机界面证据，未发起兑换"})
    state("scales_sea_unavailable", "scales_sea_offer", [shop, {"not": offer}], advance("bondlings_dispatch"))
    state("scales_sea_finished", "scales_sea_offer", [shop, offer, balance, stock, {"not": can_buy("2")}],
          advance("bondlings_dispatch"))
    state("scales_sea_open", "scales_sea_offer", [shop, offer, balance, stock, can_buy("2")],
          click("I_SCA_PICTURE_BOOK", delay=800),
          advance("scales_sea_quote", rm_started="elapsed_ms", rm_scales_sea_balance_before="rm_scales_sea_balance",
                  rm_scales_sea_stock_before="rm_scales_sea_stock"))
    state("scales_sea_unreadable", "scales_sea_offer", [shop, offer],
          {"fail": "无法核对海汐礼盒库存或被遗忘的绘本余额"})

    proved_quote = [
        quote, noncash, manual_toggle, quantity, price, balance, stock,
        expr("rm_price == 200 * rm_quantity and rm_scales_sea_balance == rm_scales_sea_balance_before "
             "and rm_scales_sea_stock == rm_scales_sea_stock_before"),
    ]
    state("scales_sea_add_one", "scales_sea_quote",
          [*proved_quote, expr("1 <= rm_quantity < 10"), can_buy("(rm_quantity + 1)"),
           asset("I_BUY_ADD", "Component_Buy"), {"not": timeout(15000)}],
          click("I_BUY_ADD", "Component_Buy", 650))
    for count in range(2, 11):
        final_size = [] if count == 10 else [{"not": can_buy(str(count + 1))}]
        state(f"scales_sea_confirm_{count}", "scales_sea_quote",
              [*proved_quote, expr(f"rm_quantity == {count}"), can_buy(str(count)), *final_size],
              {"click": [565, 579, 713, 606], "recheck": True, "delay": 900},
              advance("scales_sea_select", rm_scales_sea_batch=count,
                      rm_scales_sea_spent=f"rm_scales_sea_spent + {count * 200}", rm_started="elapsed_ms"))
        raw["states"][-1].update(sensitive="购买", desc=f"兑换 {count} 件海汐御魂礼盒，消耗 {count * 200} 被遗忘的绘本。")
    state("scales_sea_cancel_quote", "scales_sea_quote", [quote, timeout(15000)],
          click("C_BUY_CANCEL", "Component_Buy", 500), advance("scales_sea_cancelled", rm_started="elapsed_ms"))
    state("scales_sea_quote_timeout", "scales_sea_quote", [timeout(20000)],
          {"fail": "未识别海汐礼盒兑换窗口"})
    state("scales_sea_cancel_verified", "scales_sea_cancelled", [shop, {"not": plus}],
          {"fail": "海汐礼盒数量、报价或自动选择设置未通过校验，已取消兑换"})
    state("scales_sea_cancel_timeout", "scales_sea_cancelled", [timeout(7500)],
          {"fail": "海汐礼盒兑换窗口尚未确认关闭"})

    choices = [asset(f"I_SCA_SELECT_{index}") for index in range(1, 4)]
    state("scales_sea_choose_first", "scales_sea_select", choices,
          click("I_SCA_SELECT_1", delay=1600), advance("scales_sea_reward", rm_started="elapsed_ms"))
    reward = asset("I_SCA_SIX_STAR")
    state("scales_sea_claim", "scales_sea_reward", [reward],
          click("C_SCA_SOULS_GET", delay=1600), advance("scales_sea_debit", rm_started="elapsed_ms"))
    state("scales_sea_debit_verified", "scales_sea_debit", [shop, {"not": reward}, {"not": plus}, balance, stock,
          expr("rm_scales_sea_balance == rm_scales_sea_balance_before - 200 * rm_scales_sea_batch "
               "and rm_scales_sea_stock == rm_scales_sea_stock_before - rm_scales_sea_batch")],
          {"inc": "rm_transactions"},
          advance("scales_sea_offer", rm_scales_sea_bought="rm_scales_sea_bought + rm_scales_sea_batch"))
    for phase in ("select", "reward", "debit"):
        state(f"scales_sea_{phase}_timeout", "scales_sea_" + phase, [timeout(12000)],
              {"fail": "海汐礼盒兑换后的三选一、奖励或扣款库存缺少证据，停止后续兑换"})
