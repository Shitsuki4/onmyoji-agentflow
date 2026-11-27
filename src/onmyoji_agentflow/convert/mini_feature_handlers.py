"""Guarded native mini-feature handlers (017, 302, 309, 310, 319) for 小功能合集.

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

from .core_handlers import _push, _rerun, _stop
from .handlers import _count
from .team_handlers import _all, _expr


def _rect(raw_op):
    return [int(v) for v in raw_op[3:7]]


def _long_press(raw_op, press_ms=1000):
    return {"click": _rect(raw_op), "delay": int(raw_op[7]), "press_ms": press_ms, "recheck": True}


def build_normal_summon(b):
    """Build native model for 022_抽厕纸(普通召唤)."""
    counted = [_count(22)]
    for idx in (0, 1):
        acts = b.actions(idx)
        detail = ("再次召唤。请先在游戏画面确认召唤类型和消耗。"
                  if idx == 0 else "普通召唤界面中的操作。请先确认当前入口和消耗。")
        b.add(f"summon_step_{idx}", b.when(idx),
              [{"confirm": "抽卡", "detail": detail}, {**acts[0], "recheck": True}, *acts[1:]],
              counts=counted)


def build_realm_card_continue_synth(b):
    """Build native model for 031_结界卡_继续合成."""
    counted = [_count(31)]
    for idx in (0, 1, 2):
        acts = b.actions(idx)
        b.add(f"card_synth_step_{idx}", b.when(idx), [{**acts[0], "recheck": True}, *acts[1:]], counts=counted)


def build_demon_parade(b):
    """Build guarded native model for 017_百鬼夜行."""
    skill_var = "xxxskill"
    b.model["vars"] = {skill_var: 0}
    counted = [_count(17)]
    count_18 = [_count(18)]
    refresh = {"handler_control": {"op": "refresh"}}
    lowerings = {}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 177-183: freeze wait (op[8], oper [-1,-1,-1,-1,1000]) and town entry (op[10])
    b.add("parade_freeze_wait", b.when(8), [{"wait": 1000}], counts=counted)
    b.add("parade_town_entry", b.when(10), taps(10), counts=counted)

    # Lines 184-195: invite toggle (op[3])
    acts3 = b.actions(3)
    b.add("parade_invite_plus", _all(b.when(3), _expr("Inv")), [{**acts3[0], "recheck": True}], counts=counted)
    b.add("parade_no_invite", b.when(3), [{**acts3[1], "recheck": True}], counts=counted)

    # Lines 196-215: invite friend random pick (op[4], op[9]) + refresh
    for idx in (4, 9):
        ops = b.ops[idx]["oper"]
        b.add(
            f"parade_invite_friend_{idx}",
            b.when(idx),
            [{"click_random": [_rect(ops[0]), _rect(ops[1])], "delay": int(ops[0][7]), "recheck": True}, refresh],
            counts=counted,
            outcome=None,
        )

    # Lines 216-222: post-invite misc (op[6], op[7])
    for idx in (6, 7):
        b.add(f"parade_misc_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 223-238: choose boss king (op[5])
    ops5 = b.ops[5]["oper"]
    start5 = b.actions(5)[3]
    b.add(
        "parade_boss_random",
        _all(b.when(5), _expr("bossPosition == '随机'")),
        [{"click_random": [_rect(ops5[0]), _rect(ops5[1]), _rect(ops5[2])], "delay": 500, "recheck": True}, start5],
        counts=count_18,
    )
    for pos in ("1", "2", "3"):
        pick = b.actions(5)[int(pos) - 1]
        b.add(
            f"parade_boss_{pos}",
            _all(b.when(5), _expr(f"bossPosition == {pos!r}")),
            [{**pick, "recheck": True}, start5],
            counts=count_18,
        )

    # Lines 239-248: drag bean slider to 10 (op[0])
    ops0 = b.ops[0]["oper"]
    drag_gate = b.gap(
        "swipe_parade_10_beans",
        (239, 248),
        {"move": "regionSwipe op[0]"},
        [{"effect": "source regionSwipe", "duration_ms": [100, 300], "delay": 200}],
        True,
        ["native swipe on original endpoints and duration"],
        blocking=False,
    )
    lowerings["parade_drag_10_beans"] = {
        "gate_prefix": drag_gate["fail"],
        "native_intent": {
            "swipe": {"from": _rect(ops0[0]), "to": _rect(ops0[1])},
            "duration_ms": [100, 300],
            "delay": 200,
            "recheck": True,
        },
    }
    b.add("parade_drag_10_beans", b.when(0), [drag_gate], counts=counted)

    # Lines 249-263: throw beans (op[2]) with optional 百鬼夜行_BUFF priority
    b.add(
        "parade_throw_buff",
        _all(b.when(2), {"find": "百鬼夜行_BUFF"}),
        [{"set": {skill_var: 2}}, {"click_found": True, "offset": [0, 0, 15, 15], "delay": 500, "recheck": True}],
        counts=counted,
    )
    b.add("parade_throw_random", b.when(2), taps(2), counts=counted)

    proof = b.model["proof"]
    proof["source_native_lowerings"] = lowerings
    proof["source_state_bindings"] = {"global.xxxskill": skill_var}


def build_soul_shrine(b):
    """Build guarded native model for 302_奉纳御魂."""
    fengna = "fengNa"
    b.model["vars"] = {fengna: False}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 256-269: glutton feed phase (not fengNa)
    not_fn = _expr(f"not {fengna}")
    for idx in (9, 10, 11, 12):
        b.add(f"glutton_feed_{idx}", _all(not_fn, b.when(idx)), taps(idx))
    b.add("glutton_feed_done", _all(not_fn, b.when(13)), [*taps(13), {"set": {fengna: True}}])

    # Lines 270-329: shrine release phase (fengNa)
    fn_on = _expr(fengna)
    b.add("shrine_switch_sort", _all(fn_on, {"not": b.when(8)}, b.when(5)), taps(8))
    for idx in (0, 2, 3, 4, 7):
        b.add(f"shrine_step_{idx}", _all(fn_on, b.when(idx)), [*taps(idx), {"wait": 500}])

    first_row = {"any": [b.when(1), b.when(14)]}
    b.add(
        "shrine_select_row",
        _all(fn_on, first_row),
        [_long_press(b.ops[6]["oper"][0], 1000), *b.actions(2)],
    )

    done_empty = _all(fn_on, {"not": first_row}, b.when(5))
    rerun_gap = b.gap(
        "shrine_done_rerun",
        (318, 321),
        {"scheme_switch_enabled": True, "souls_empty": True},
        [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 3000}],
        None,
        ["bind next_scheme rerun"],
    )
    stop_gap = b.gap(
        "shrine_done_stop",
        (322, 327),
        {"scheme_switch_enabled": False, "souls_empty": True},
        [_push("奉纳结束或未正确使用，请查看。"), _stop(), {"effect": "sleep", "ms": 3000}],
        None,
        ["source Push", "source stop lifecycle"],
    )
    b.add("shrine_done_switch", _all(done_empty, _expr("scheme_switch_enabled")), [*taps(5), rerun_gap])
    b.add("shrine_done_stop", done_empty, [*taps(5), stop_gap])

    # Lines 330-336: enter shrine from yard/records (op[15..19])
    for idx in (15, 16, 17, 18, 19):
        b.add(f"shrine_enter_{idx}", b.when(idx), taps(idx))

    b.model["proof"]["source_state_bindings"] = {"global.fengNa": fengna}


def build_soul_enhance(b):
    """Build guarded native model for 309_强化御魂."""
    ini = "upYuHunIni"
    flag = "upYuHun"
    b.model["vars"] = {ini: True, flag: False}
    counted = [_count(309)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 250-293: attribute filter init
    ini_on = _expr(ini)
    b.add("enhance_init_open_attr", _all(ini_on, b.when(12)), taps(12), counts=counted)
    b.add("enhance_init_speed_switch", _all(ini_on, _expr("speed"), b.when(13)), [*taps(13), {"set": {ini: False}}], counts=counted)
    b.add(
        "enhance_init_speed_keep",
        _all(ini_on, _expr("speed"), b.when(14)),
        [{**b.actions(14)[4], "recheck": True}, {"set": {ini: False}}],
        counts=counted,
    )
    b.add("enhance_init_sub_switch", _all(ini_on, _expr("not speed"), b.when(14)), [*taps(14), {"set": {ini: False}}], counts=counted)
    b.add(
        "enhance_init_sub_keep",
        _all(ini_on, _expr("not speed"), b.when(13)),
        [{**b.actions(13)[4], "recheck": True}, {"set": {ini: False}}],
        counts=counted,
    )

    # Lines 294-302: long press select soul (op[0])
    b.add(
        "enhance_select_soul",
        b.when(0),
        [_long_press(b.ops[0]["oper"][0], 1000), {"set": {flag: False}}],
        counts=counted,
    )

    # Lines 303-310: calculate/enhance (+3, +6, +15, +9)
    for idx in (2, 5, 6, 8):
        b.add(f"enhance_tier_{idx}", b.when(idx), [*taps(idx), {"set": {flag: True}}], counts=counted)

    # Lines 311-330: speed vs normal branch
    for idx in (7, 1, 10, 11):
        b.add(f"enhance_speed_{idx}", _all(_expr("speed"), b.when(idx)), [*taps(idx), {"set": {flag: False}}], counts=counted)
    for idx in (7, 1, 3, 4):
        b.add(f"enhance_normal_{idx}", _all(_expr("not speed"), b.when(idx)), [*taps(idx), {"set": {flag: False}}], counts=counted)

    # Lines 340-348: finished (op[9])
    done_stop = b.gap(
        "enhance_finished_stop",
        (340, 348),
        {"screen": "soul_enhance_done"},
        [_push("强化御魂已停止，请查看。"), _stop()],
        True,
        ["source Push", "source stop lifecycle"],
    )
    b.add("enhance_finished", b.when(9), [done_stop], counts=counted)

    b.model["proof"]["source_state_bindings"] = {"global.upYuHunIni": ini, "global.upYuHun": flag}


def build_glutton_exp(b):
    """Build guarded native model for 310_暴食鬼."""
    counted = [_count(310)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    main = b.when(0)
    for idx in (4, 6):
        b.add(f"glutton_store_{idx}", _all(main, b.when(idx)), [*taps(idx), {"wait": 2000}], counts=counted)
    b.add(
        "glutton_pick_exp",
        _all(main, {"any": [b.when(1), b.when(2), b.when(3)]}),
        [_long_press(b.ops[0]["oper"][0], 1000)],
        counts=counted,
    )
    full_stop = b.gap(
        "glutton_exp_full_stop",
        (124, 134),
        {"screen": "glutton_exp_full"},
        [_push("经验已满，请查看。"), _stop()],
        False,
        ["source Push", "source stop lifecycle"],
    )
    b.add("glutton_exp_full", b.when(5), [full_stop], counts=counted, outcome=False)


def build_yuanjie_travel(b):
    """Build economically guarded native model for 319_缘结趣游."""
    ten_var = "youjiequyuan_ten"
    b.model["vars"] = {ten_var: True}
    counted = [_count(319)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 187-193: bell appeared (op[9]: wait 2000, click, wait 2000)
    bell_tap = {"click": _rect(b.ops[9]["oper"][1]), "delay": 1000, "recheck": True}
    b.add("yuanjie_bell_appear", b.when(9), [{"wait": 2000}, bell_tap, {"wait": 2000}], counts=counted)

    # Lines 194-211: < 10 tickets (op[2]) -> economic guard when buy=True; dismiss when buy=False
    buy_gap = b.gap(
        "yuanjie_buy_tickets_jade",
        (199, 206),
        {"config": "buy", "screen": "less_than_10_tickets"},
        [{"effect": "purchase_yuanjie_tickets_with_jade", "ops": b.ops[5]["oper"]}],
        True,
        ["economic_jade_purchase_confirmation"],
    )
    b.add("yuanjie_buy_tickets", _all(b.when(2), _expr("buy")), [buy_gap], counts=counted)
    b.add(
        "yuanjie_switch_single",
        b.when(2),
        [*taps(2), {"set": {ten_var: False}}],
        counts=counted,
    )

    # Lines 212-222: < 1 ticket (op[4]) -> push + stop + sleep(2000)
    no_ticket_stop = b.gap(
        "yuanjie_no_ticket_stop",
        (212, 222),
        {"screen": "less_than_1_ticket"},
        [_push("缘结趣游不足一抽，脚本自动停止"), _stop(), {"effect": "sleep", "ms": 2000}],
        False,
        ["source Push", "source stop lifecycle"],
    )
    b.add("yuanjie_no_ticket", b.when(4), [*taps(4), no_ticket_stop], counts=counted, outcome=False)

    # Lines 223-240: bells bonus popup (op[6]) and 10 bells reached stop (op[7] when not over)
    b.add("yuanjie_bells_popup", b.when(6), taps(6), counts=counted)
    bells_done_stop = b.gap(
        "yuanjie_bells_done_stop",
        (230, 240),
        {"config": "not over", "screen": "bells_reached_10"},
        [_push("缘结趣游抽足铃铛，脚本自动停止"), _stop(), {"effect": "sleep", "ms": 2000}],
        False,
        ["source Push", "source stop lifecycle"],
    )
    b.add("yuanjie_bells_done", _all(_expr("not over"), b.when(7)), [bells_done_stop], counts=counted, outcome=False)

    # Lines 241-261: main screen (op[0]) -> toggle 10x checkbox (op[1]/op[3]) then draw
    draw_tap = b.actions(0)[0]
    b.add("yuanjie_draw_check_ten", _all(b.when(0), _expr(ten_var), b.when(1)), [*taps(1), draw_tap], counts=counted)
    b.add("yuanjie_draw_uncheck_ten", _all(b.when(0), _expr(f"not {ten_var}"), b.when(3)), [*taps(3), draw_tap], counts=counted)
    b.add("yuanjie_draw_direct", b.when(0), [{**draw_tap, "recheck": True}], counts=counted)

    # Lines 262-268: bought all tickets popup (op[8]) -> clear ten flag, return False
    b.add("yuanjie_all_bought", b.when(8), [*taps(8), {"set": {ten_var: False}}], counts=counted, outcome=False)

    proof = b.model["proof"]
    proof["source_state_bindings"] = {"global.youjiequyuan_ten": ten_var}
    proof["resource_costs"] = "Ticket purchases with jade (buy=True) are gated pending explicit economic confirmation."
