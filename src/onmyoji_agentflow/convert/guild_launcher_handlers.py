"""Guarded native handlers for 320 (百鬼棋局), 519 (寮管理攻打道馆), and 600 (进入寮活动).

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

from .core_handlers import _push, _rerun, _stop
from .handlers import UnsupportedHandler, _count
from .team_handlers import _all, _expr

WEEKDAY_MAP = {
    "星期日": 0,
    "星期一": 1,
    "星期二": 2,
    "星期三": 3,
    "星期四": 4,
    "星期五": 5,
    "星期六": 6,
}


def normalize_guild_launcher_config(config):
    """Lower 600's banquet weekday list into scalar day indices."""
    result = dict(config)
    if "a_ctivity_banquet_time" in result:
        days = result.pop("a_ctivity_banquet_time")
        if (not isinstance(days, list) or len(days) < 2
                or any(not isinstance(day, str) or day not in WEEKDAY_MAP for day in days[:2])):
            raise UnsupportedHandler("600 a_ctivity_banquet_time requires two valid Chinese weekday names")
        result["banquet_day_one"] = WEEKDAY_MAP[days[0]]
        result["banquet_day_two"] = WEEKDAY_MAP[days[1]]
    return result


def build_chess_idle(b):
    """Build guarded native model for 320_百鬼棋局挂机."""
    ini = "chess320_ini"
    cheak = "chess320_cheak"
    lv5 = "chess320_levelFive"
    cnt = "chess320_cnt"
    step = "chess320_step"
    b.model["vars"] = {ini: True, cheak: 5, lv5: False, cnt: 0, step: False}
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 349-365: battle start button (op[6]) + 600-coin stop check (op[28], op[19])
    coin_600 = {"any": [b.when(28), b.when(19)]}
    coin_rerun = b.gap(
        "chess_600_coin_rerun",
        (353, 360),
        {"screen": "chess_battle_start", "coins_600": True},
        [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 1000}],
        None,
        ["bind next_scheme rerun"],
    )
    b.add("battle_start_600_coins", _all(b.when(6), coin_600), [coin_rerun])
    b.add(
        "battle_start_enter",
        b.when(6),
        [*taps(6), {"set": {ini: True, cheak: 5, lv5: False}}],
    )

    # Lines 366-372: misc screens
    for idx in (4, 5, 15, 8, 9, 10, 24, 25, 26, 27):
        b.add(f"chess_misc_{idx}", b.when(idx), taps(idx))

    # Lines 373-387: initial lineup apply
    for idx in (11, 12):
        b.add(f"init_lineup_{idx}", _all(_expr(ini), b.when(idx)), taps(idx))
    b.add(
        "init_lineup_exit",
        _all(_expr(ini), b.when(13)),
        [*taps(13), {"set": {ini: False}}],
    )

    # Lines 388-394: level five detection (op[18])
    b.add("detect_level_five", _all(_expr(f"not {lv5}"), b.when(18)), [{"set": {lv5: True}}])

    # Lines 395-424: bounded 8-attempt shop buy loop on op[14]
    b.add("buy_loop_init", _expr("True"), [{"set": {cnt: 0, step: False}}], outcome=None, internal=True)
    b.add(
        "buy_loop_check",
        b.when(14),
        [{"set": {cheak: 5, step: True}}, {"inc": cnt}, refresh],
        outcome=None,
        internal=True,
    )
    up_tap = b.actions(18)[0]
    shop_refresh_tap, shop_close_tap = b.actions(14)[0], b.actions(14)[1]
    b.add(
        "buy_max_upgrade_shop",
        _all(_expr(f"{step} and {cnt} >= 8 and not {lv5}"), b.when(16)),
        [{**up_tap, "recheck": True}, {"set": {step: False}}],
    )
    b.add(
        "buy_max_refresh_shop",
        _all(_expr(f"{step} and {cnt} >= 8 and {lv5}"), b.when(16)),
        [{**shop_refresh_tap, "recheck": True}, {"set": {step: False}}],
    )
    b.add(
        "buy_max_close_shop",
        _expr(f"{step} and {cnt} >= 8"),
        [{**shop_close_tap, "recheck": True}, {"set": {step: False}}],
    )
    b.add(
        "buy_recommended_unit",
        _all(_expr(step), {"find": "百鬼棋局_荐"}),
        [{"click_found": True, "offset": [0, 0, 20, 20], "delay": 1000, "recheck": True}],
        outcome=None,
    )
    buy_edge = "unresolved_source_obligation:team320.buy_loop requires team_workflow"
    b.add(
        "buy_loop_retry",
        _expr(f"{step} and {cnt} < 8"),
        [{"set": {step: False}}, {"wait": 200}, {"fail": buy_edge}],
        outcome=None,
        internal=True,
    )
    edges["buy_loop_retry"] = {"target_case": "buy_loop_check", "gate_prefix": buy_edge}

    # Lines 425-474: board/bench management when shop closed (op[17])
    manage_cond = _all(_expr(f"not {ini} and {cheak} > 0"), b.when(17))
    b.add(
        "manage_stage_1_2_skip",
        _all(manage_cond, {"any": [b.when(20), b.when(21)]}),
        [{"set": {cheak: 0}}],
    )
    drag_discover = b.gap(
        "chess_drag_discover_soul",
        (436, 440),
        {"found": "百鬼棋局_发现御魂"},
        [{"effect": "dynamic_origin_regionSwipe", "target": b.ops[23]["oper"][0], "duration_ms": [700, 800], "delay": 500}],
        True,
        ["dynamic_origin_swipe_from_found_point"],
    )
    b.add("manage_discover_soul", _all(manage_cond, {"find": "百鬼棋局_发现御魂"}), [drag_discover])

    drag_soul = b.gap(
        "chess_drag_equip_soul",
        (441, 445),
        {"found": "百鬼棋局_御魂"},
        [{"effect": "dynamic_origin_regionSwipe", "target": b.ops[17]["oper"][0], "duration_ms": [700, 800], "delay": 500}],
        True,
        ["dynamic_origin_swipe_from_found_point"],
    )
    b.add("manage_equip_soul", _all(manage_cond, {"find": "百鬼棋局_御魂"}), [drag_soul])

    drag_board = b.gap(
        "chess_drag_board_one_star",
        (446, 458),
        {"stage": "3", "found": "百鬼棋局_棋盘一星"},
        [{"effect": "findMultiColorEx_and_dynamic_regionSwipe_to_bench", "target": b.ops[22]["oper"][0]}],
        True,
        ["findMultiColorEx_multi_match", "dynamic_origin_swipe_from_found_point"],
    )
    b.add("manage_stage3_board_one_star", _all(manage_cond, b.when(22), {"find": "百鬼棋局_棋盘一星"}), [drag_board])

    drag_bench = b.gap(
        "chess_drag_bench_one_star",
        (459, 471),
        {"found": "百鬼棋局_一星"},
        [{"effect": "findMultiColorEx_filter_not_recommended_and_swipe_sell", "target": b.ops[17]["oper"][0]}],
        True,
        ["findMultiColorEx_multi_match", "dynamic_subregion_find_colors", "dynamic_origin_swipe_from_found_point"],
    )
    b.add("manage_bench_one_star", _all(manage_cond, {"find": "百鬼棋局_一星"}), [drag_bench])

    b.add("manage_decrement_check", manage_cond, [{"set": {cheak: f"{cheak} - 1"}}])

    # Lines 475-488: courtyard -> click 庭院_町中竖牌
    yard = {"any": [b.when(i) for i in (0, 1, 2, 3)]}
    b.add(
        "yard_to_town",
        _all(yard, {"find": "庭院_町中竖牌"}),
        [{"click_found": True, "offset": [0, 0, 10, 10], "delay": 1000, "recheck": True}],
    )

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_state_bindings"] = {
        "global.chess.ini": ini,
        "global.chess.cheak": cheak,
        "global.chess.levelFive": lv5,
    }
    proof["source_retest"] = {"buy_max_attempts": 8, "buy_sleep_ms": 200}


def build_dojo_admin(b):
    """Build guarded native model for 519_寮管理攻打道馆."""
    leave = "daoGuan_exit"
    click_flag = "daoGuan_click"
    swip_flag = "daoGuan_swip"
    flash_cnt = "flash_time"
    weekend = "dojo519_is_fri_sat_sun"
    b.model["vars"] = {
        leave: False,
        click_flag: False,
        swip_flag: True,
        flash_cnt: 0,
        weekend: False,
    }
    counted = [_count(519)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 206-212: weekend stop (Fri/Sat/Sun when config.day is True)
    weekend_stop = b.gap(
        "dojo519_weekend_stop",
        (206, 212),
        {"config": "day", "weekday_in": [0, 5, 6]},
        [_push("星期567,关闭方案"), _stop(), {"effect": "sleep", "ms": 2000}],
        True,
        ["source Push", "source stop lifecycle"],
    )
    b.add("weekend_guard_stop", _expr(f"day and {weekend}"), [weekend_stop])
    b.gap(
        "dojo519_weekday_clock_input",
        (204, 206),
        {"config": "day"},
        [{"effect": "host_sets_dojo519_is_fri_sat_sun_from_wall_clock"}],
        "continue",
        ["wall_clock_weekday_binding"],
        blocking=False,
    )

    # Lines 213-222: zero chances left or succeeded today -> rerun('返回庭院') + sleep(2000)
    done_rerun = b.gap(
        "dojo519_done_rerun",
        (213, 222),
        {"screen": "dojo_zero_chances_or_done"},
        [_rerun("返回庭院"), {"effect": "sleep", "ms": 2000}],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    b.add(
        "zero_chances_return_yard",
        {"any": [b.when(8), b.when(9), b.when(11)]},
        [done_rerun],
        counts=counted,
    )

    # Lines 223-229: shrine/establish/my-dojo navigation (op[0], op[7], op[10])
    for idx in (0, 7, 10):
        b.add(f"shrine_nav_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 230-382: dojo target selection page (op[1])
    b.add(
        "attack_selected_dojo",
        _all(b.when(1), _expr(click_flag), {"find": "敌方道馆_挑战"}),
        [
            {"click_found": True, "offset": [0, 0, 60, 60], "delay": 1000, "recheck": True},
            {"set": {leave: False, click_flag: False, swip_flag: True}},
        ],
        counts=counted,
    )
    ocr_scan_gap = b.gap(
        "dojo519_ocr_target_selection",
        (248, 381),
        {"screen": "dojo_select_page", "daoGuan_click": False},
        [{"effect": "ocr_scan_8_guilds_gold_people_defense_and_rank"}],
        True,
        ["ocr_guild_metrics_scan_and_rank"],
    )
    b.add(
        "dojo_ocr_scan_gate",
        b.when(1),
        [{"set": {leave: False}}, ocr_scan_gap],
        counts=counted,
    )

    b.model["proof"]["source_state_bindings"] = {
        "global.daoGuan_exit": leave,
        "global.daoGuan_click": click_flag,
        "global.daoGuan_swip": swip_flag,
        "global.flash_time": flash_cnt,
        "wall_clock_fri_sat_sun": weekend,
    }


def build_guild_launcher(b):
    """Build guarded native model for 600_进入寮活动."""
    super_next = "super_next_scheme_name"
    cheak = "liao_cheak"
    inited = "act600_inited"
    now_day = "act600_now_day"
    now_hour = "act600_now_hour"
    sw_gate = "act600_sw_gate"
    sw_dojo = "act600_sw_dojo"
    sw_dojo2 = "act600_sw_dojo_again"
    sw_hunt = "act600_sw_hunt"
    sw_narrow = "act600_sw_narrow"
    sw_banquet = "act600_sw_banquet"
    sw_boss = "act600_sw_huntBoss"

    b.model["vars"] = {
        super_next: "",
        cheak: -1,
        inited: False,
        now_day: 1,
        now_hour: 19,
        sw_gate: False,
        sw_dojo: False,
        sw_dojo2: False,
        sw_hunt: False,
        sw_narrow: False,
        sw_banquet: False,
        sw_boss: False,
    }
    counted = [_count(600)]
    refresh = {"handler_control": {"op": "refresh"}}
    lowerings = {}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    b.gap(
        "launcher600_clock_input",
        (313, 314),
        {"scope": "guild_activity_schedule"},
        [{"effect": "host_sets_act600_now_day_and_act600_now_hour_from_wall_clock"}],
        "continue",
        ["wall_clock_weekday_and_hour_binding"],
        blocking=False,
    )

    # Lines 315-327: initialize switch table from config once + set superGlobal.next_scheme_name
    b.add(
        "init_switches",
        _expr(f"not {inited}"),
        [{
            "set": {
                inited: True,
                super_next: repr("寮活动启动器"),
                sw_gate: "a_ctivity_gateOfHades",
                sw_dojo: "a_ctivity_dojo",
                sw_dojo2: False,
                sw_hunt: "a_ctivity_hunt",
                sw_narrow: "a_ctivity_narrow",
                sw_banquet: "a_ctivity_banquet",
                sw_boss: "a_ctivity_huntBoss",
            }
        }],
        outcome=None,
        internal=True,
    )

    # Lines 329-337: all switches False -> push + rerun(next_scheme) + sleep(1000)
    all_false = (
        f"not {sw_gate} and not {sw_dojo} and not {sw_dojo2} and not {sw_hunt}"
        f" and not {sw_narrow} and not {sw_banquet} and not {sw_boss}"
    )
    all_done_gap = b.gap(
        "all_activities_done_push_rerun",
        (330, 337),
        {"all_switches_false": True},
        [_push("已结束，请查看。"), _rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 1000}],
        True,
        ["source Push", "bind next_scheme rerun"],
    )
    b.add("all_activities_done", _expr(all_false), [{"set": {super_next: repr("")}}, all_done_gap])

    # Lines 338-344: enter guild shrine (op[14], op[15], op[16] retest=1000)
    for idx, rt in ((14, None), (15, None), (16, 1000)):
        b.add(f"enter_shrine_{idx}", b.when(idx), taps(idx), counts=counted, retest_ms=rt)

    # Lines 346-354: first shrine visit backs out once to clear cache
    b.add(
        "first_shrine_reenter",
        _all(_expr(f"{cheak} == -1"), b.when(11)),
        [*taps(11), {"inc": cheak}],
        counts=counted,
    )

    # Lines 356-414: dojo branch
    dojo_on = f"({sw_dojo} or {sw_dojo2})"
    dojo_sched = f"(({now_day} >= 1 and {now_day} <= 4) or (({now_day} == 5 or {now_day} == 6 or {now_day} == 0) and not a_ctivity_narrow))"
    dojo_rerun = b.gap(
        "rerun_dojo_scheme",
        (365, 390),
        {"activity": "dojo"},
        [_rerun({"config": "a_ctivity_dojo_select"})],
        True,
        ["bind a_ctivity_dojo_select rerun"],
    )
    b.add(
        "dojo_admin_start",
        _all(_expr(f"{dojo_on} and {dojo_sched} and admin"), b.when(11)),
        [{"set": {sw_dojo: False, sw_dojo2: False, sw_narrow: False}}, dojo_rerun],
        counts=counted,
    )
    b.add("dojo_open_tap", _all(_expr(f"{dojo_on} and {dojo_sched}"), b.when(12)), taps(12))
    b.add(
        "dojo_inside_switch",
        _all(_expr(f"{dojo_on} and {dojo_sched}"), b.when(6)),
        [{"set": {sw_dojo: False, sw_dojo2: False, sw_narrow: False}}, dojo_rerun],
    )
    b.add(
        "dojo_map_gathering",
        _all(_expr(f"{dojo_on} and {dojo_sched}"), b.when(2), {"find": "道馆集结"}),
        [{"click_found": True, "offset": [70, -110, 120, -80], "delay": 1000, "recheck": True}],
        counts=counted,
    )
    b.add("dojo_map_wait", _all(_expr(f"{dojo_on} and {dojo_sched}"), b.when(2)), [], counts=counted)
    b.add(
        "dojo_out_of_schedule",
        _expr(f"{dojo_on} and not ({dojo_sched})"),
        [{"set": {sw_dojo: False, sw_dojo2: False}}],
        outcome=None,
        internal=True,
    )

    # Lines 416-438: Saturday huntBoss (10:00-23:00)
    boss_sched = f"({now_day} == 6 and {now_hour} >= 10 and {now_hour} < 23)"
    boss_rerun = b.gap(
        "rerun_hunt_boss_scheme",
        (428, 433),
        {"activity": "huntBoss"},
        [_rerun({"config": "a_ctivity_huntBoss_select"})],
        True,
        ["bind a_ctivity_huntBoss_select rerun"],
    )
    b.add("hunt_boss_open", _all(_expr(f"{sw_boss} and {boss_sched}"), b.when(0)), taps(0))
    b.add(
        "hunt_boss_switch",
        _all(_expr(f"{sw_boss} and {boss_sched}"), b.when(7)),
        [{"set": {sw_boss: False}}, boss_rerun],
    )
    b.add(
        "hunt_boss_out_of_schedule",
        _expr(f"{sw_boss} and not ({boss_sched})"),
        [{"set": {sw_boss: False}}],
        outcome=None,
        internal=True,
    )

    # Lines 440-524: banquet
    banq_sched = f"({now_day} == banquet_day_one or {now_day} == banquet_day_two)"
    banq_only = f"not {sw_dojo} and not {sw_dojo2} and not {sw_narrow} and not {sw_boss}"
    banq_rerun = b.gap(
        "rerun_banquet_scheme",
        (504, 519),
        {"activity": "banquet"},
        [_rerun({"config": "a_ctivity_banquet_select"})],
        True,
        ["bind a_ctivity_banquet_select rerun"],
    )
    b.add(
        "banquet_admin_start",
        _all(_expr(f"{sw_banquet} and {banq_sched} and admin and {banq_only}"), b.when(11)),
        [{"set": {sw_banquet: False}}, banq_rerun],
        counts=counted,
    )
    b.add(
        "banquet_open_switch",
        _all(_expr(f"{sw_banquet} and {banq_sched}"), b.when(1)),
        [*taps(1), {"set": {sw_banquet: False}}, banq_rerun],
    )
    b.add(
        "banquet_out_of_schedule",
        _expr(f"{sw_banquet} and not ({banq_sched})"),
        [{"set": {sw_banquet: False}}],
        outcome=None,
        internal=True,
    )

    # Lines 526-557: narrow realm (Fri/Sat/Sun)
    narrow_sched = f"({now_day} == 0 or {now_day} == 5 or {now_day} == 6)"
    swipe_ops = b.ops[13]["oper"]
    narrow_swipe = b.gap(
        "swipe_narrow_scroll",
        (528, 534),
        {"move": "regionBezierSwipe op[13]"},
        [{"effect": "source regionBezierSwipe", "duration_ms": [1200, 1500], "delay": 1000}],
        True,
        ["native swipe on original endpoints and duration"],
        blocking=False,
    )
    lowerings["narrow_scroll_shrine"] = {
        "gate_prefix": narrow_swipe["fail"],
        "native_intent": {
            "swipe": {"from": swipe_ops[1][3:7], "to": swipe_ops[0][3:7]},
            "duration_ms": [1200, 1500],
            "delay": 1000,
            "recheck": True,
        },
    }
    b.add(
        "narrow_scroll_shrine",
        _all(_expr(f"{sw_narrow} and {narrow_sched}"), b.when(13)),
        [narrow_swipe, refresh],
        outcome=None,
    )
    b.add("narrow_open_tap", _all(_expr(f"{sw_narrow} and {narrow_sched}"), b.when(9)), taps(9))
    narrow_rerun = b.gap(
        "rerun_narrow_scheme",
        (545, 551),
        {"activity": "narrow"},
        [_rerun({"config": "a_ctivity_narrow_select"})],
        True,
        ["bind a_ctivity_narrow_select rerun"],
    )
    b.add(
        "narrow_switch",
        _all(_expr(f"{sw_narrow} and {narrow_sched}"), b.when(10)),
        [{"set": {sw_narrow: False, sw_dojo: False}}, narrow_rerun],
    )
    b.add(
        "narrow_out_of_schedule",
        _expr(f"{sw_narrow} and not ({narrow_sched})"),
        [{"set": {sw_narrow: False}}],
        outcome=None,
        internal=True,
    )

    # Lines 559-586: hunt (Mon-Thu 6:00-23:00)
    hunt_sched = f"({now_day} >= 1 and {now_day} <= 4 and {now_hour} >= 6 and {now_hour} < 23)"
    hunt_only = f"not {sw_dojo} and not {sw_dojo2} and not {sw_narrow} and not {sw_banquet} and not {sw_boss}"
    hunt_rerun = b.gap(
        "rerun_hunt_scheme",
        (575, 580),
        {"activity": "hunt"},
        [_rerun({"config": "a_ctivity_hunt_select"})],
        True,
        ["bind a_ctivity_hunt_select rerun"],
    )
    b.add("hunt_enter_tap", _all(_expr(f"{sw_hunt} and {hunt_sched} and {hunt_only}"), b.when(3)), taps(3))
    b.add(
        "hunt_inside_switch",
        _all(_expr(f"{sw_hunt} and {hunt_sched} and {hunt_only}"), b.when(4)),
        [{"set": {sw_hunt: False}}, hunt_rerun],
    )
    b.add(
        "hunt_out_of_schedule",
        _expr(f"{sw_hunt} and not ({hunt_sched})"),
        [{"set": {sw_hunt: False}}],
        outcome=None,
        internal=True,
    )

    # Lines 588-610: gate of hades (Fri-Sun 17:00-23:00)
    gate_sched = f"(({now_day} == 0 or {now_day} == 5 or {now_day} == 6) and {now_hour} >= 17 and {now_hour} < 23)"
    gate_only = f"not {sw_dojo} and not {sw_dojo2} and not {sw_hunt} and not {sw_narrow} and not {sw_banquet} and not {sw_boss}"
    gate_rerun = b.gap(
        "rerun_gate_scheme",
        (598, 603),
        {"activity": "gateOfHades"},
        [_rerun({"config": "a_ctivity_gateOfHades_select"})],
        True,
        ["bind a_ctivity_gateOfHades_select rerun"],
    )
    b.add(
        "gate_start_switch",
        _all(_expr(f"{sw_gate} and {gate_sched} and {gate_only}"), b.when(11)),
        [{"set": {sw_gate: False}}, gate_rerun],
        counts=counted,
    )
    b.add(
        "gate_out_of_schedule",
        _expr(f"{sw_gate} and not ({gate_sched})"),
        [{"set": {sw_gate: False}}],
    )

    # Lines 611-663: shrine wait / retry / timeout fallback
    shrine_back = taps(11)
    b.add(
        "shrine_wait_retry",
        _all(b.when(11), _expr(f"{cheak} + 1 < count")),
        [*shrine_back, {"inc": cheak}, {"wait_random": [28000, 32000]}],
        counts=counted,
    )
    b.add(
        "shrine_timeout_prune_admin",
        _all(b.when(11), _expr(f"{cheak} + 1 == count and admin")),
        [*shrine_back, {"inc": cheak}, {"set": {sw_dojo: False, sw_dojo2: False, sw_narrow: False, sw_boss: False}}],
        counts=counted,
    )
    b.add(
        "shrine_timeout_prune_member",
        _all(b.when(11), _expr(f"{cheak} + 1 == count and not admin")),
        [
            *shrine_back,
            {"inc": cheak},
            {"set": {sw_dojo: False, sw_dojo2: False, sw_narrow: False, sw_banquet: False, sw_boss: False}},
        ],
        counts=counted,
    )
    timeout_rerun = b.gap(
        "shrine_timeout_return_yard",
        (650, 662),
        {"liao_cheak": ">= count + 1"},
        [_rerun("返回庭院"), {"effect": "sleep", "ms": 3000}],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    b.add(
        "shrine_timeout_exit",
        _all(b.when(11), _expr(f"{cheak} + 1 < count + 3")),
        [*shrine_back, *b.actions(11), {"inc": cheak}, {"set": {super_next: repr("")}}, timeout_rerun],
        counts=counted,
    )

    proof = b.model["proof"]
    proof["source_native_lowerings"] = lowerings
    proof["source_state_bindings"] = {
        "superGlobal.next_scheme_name": super_next,
        "global.liao_cheak": cheak,
        "wall_clock.getDay": now_day,
        "wall_clock.getHours": now_hour,
    }
