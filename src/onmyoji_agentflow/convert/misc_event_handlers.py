"""Guarded native event/shop handlers (304 emaki, 401 bet, 1110 mystery shop).

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

from .core_handlers import _push, _stop
from .handlers import _count
from .team_handlers import _all, _expr


def build_emaki_progress(b):
    """Build guarded native model for 304_检测绘卷进度."""
    rank_var = "paiMing"
    b.model["vars"] = {rank_var: 0}
    counted = [_count(304)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 175-189: OCR ranking on op[7] and click chosen emaki scroll op[0].oper[emaki]
    rank_gap = b.gap(
        "emaki_rank_ocr_and_enter",
        (175, 189),
        {"screen": "emaki_main_list"},
        [{"effect": "ocr_rank_region_into_paiMing_and_click_selected_emaki"}],
        True,
        ["ocr_numeric_rank_parse", "dynamic_emaki_index_click"],
    )
    b.add("emaki_rank_ocr", b.when(7), [rank_gap], counts=counted)

    # Lines 190-260: emaki progress dialog (op[1])
    progress_screen = b.when(1)
    osp_gap = b.gap(
        "emaki_progress_ocr_push",
        (196, 222),
        {"screen": "emaki_progress_dialog", "osp": True},
        [{"effect": "ocr_percentage_and_push_when_above_progress_threshold"}],
        True,
        ["ocr_percentage_parse", "source Push"],
    )
    b.add("progress_osp_check", _all(progress_screen, _expr("osp")), [osp_gap], counts=counted)

    need_donate = _all(progress_screen, _expr(f"not osp and {rank_var} > rankOpen"))
    donate_ops = b.actions(2)
    close_op = b.actions(1)[0]
    b.add(
        "donate_small",
        _all(need_donate, {"not": b.when(4)}),
        [{**donate_ops[1], "recheck": True}, donate_ops[4], donate_ops[5], close_op, {"wait": 61000}],
    )
    b.add(
        "donate_medium",
        _all(need_donate, b.when(4), {"not": b.when(5)}),
        [{**donate_ops[2], "recheck": True}, donate_ops[4], donate_ops[5], close_op, {"wait": 61000}],
    )
    b.add(
        "donate_large",
        _all(need_donate, b.when(4), b.when(5), {"not": b.when(6)}),
        [{**donate_ops[3], "recheck": True}, donate_ops[4], donate_ops[5], close_op, {"wait": 61000}],
    )
    b.add(
        "donate_all_insufficient",
        _all(need_donate, b.when(4), b.when(5), b.when(6)),
        [{"wait": 61000}],
    )
    b.add(
        "progress_rank_ok_close",
        _all(progress_screen, _expr("not osp")),
        [{**close_op, "recheck": True}, {"wait": 61000}],
    )

    # Lines 261-266: enter event / emaki (op[8], op[9])
    for idx in (8, 9):
        b.add(f"enter_emaki_{idx}", b.when(idx), taps(idx))

    b.model["proof"]["source_state_bindings"] = {"global.paiMing": rank_var}


def build_duel_bet(b):
    """Build guarded native model for 401_对弈竞猜."""
    cnt = "bet401_cnt"
    yard_active = "bet401_yard_active"
    b.model["vars"] = {cnt: 0, yard_active: False}
    counted = [_count(401)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 94-96: misc popups (op[4], op[3])
    for idx in (4, 3):
        b.add(f"bet_misc_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 98-113: courtyard -> bounded 3-attempt probe for 对弈竞猜 / 右边侧栏下一页图标
    yard = {"any": [b.when(0), b.when(1)]}
    b.add(
        "yard_probe_init",
        yard,
        [{"set": {cnt: 0, yard_active: True}}],
        counts=counted,
        outcome=None,
        internal=True,
    )
    b.add(
        "yard_probe_refresh",
        _expr(f"{yard_active} and {cnt} < 3"),
        [{"wait": 80}, refresh, {"inc": cnt}],
        outcome=None,
        internal=True,
    )
    b.add(
        "yard_click_bet",
        _all(_expr(yard_active), {"find": "对弈竞猜"}),
        [
            {"click_found": True, "offset": [-5, -5, 5, 5], "delay": 200, "recheck": True},
            {"wait": 1400},
            {"set": {yard_active: False}},
        ],
    )
    probe_edge = "unresolved_source_obligation:team401.yard_probe_loop requires team_workflow"
    b.add(
        "yard_probe_retry",
        _expr(f"{yard_active} and {cnt} < 3"),
        [{"fail": probe_edge}],
        outcome=None,
        internal=True,
    )
    edges["yard_probe_retry"] = {"target_case": "yard_probe_refresh", "gate_prefix": probe_edge}
    b.add(
        "yard_click_next_page",
        _all(_expr(yard_active), {"find": "右边侧栏下一页图标"}),
        [
            {"click_found": True, "offset": [-5, -5, 5, 5], "delay": 200, "recheck": True},
            {"wait": 1400},
            {"set": {yard_active: False}},
        ],
    )
    b.add(
        "yard_probe_clear",
        _expr(yard_active),
        [{"set": {yard_active: False}}],
        outcome=None,
        internal=True,
    )

    # Lines 115-131: external RSS/API fetch + wager confirmation on op[2]
    bet_ops = b.ops[2]["oper"]
    bet_gap = b.gap(
        "bet_external_feed_and_wager",
        (115, 423),
        {"screen": "bet_selection_page"},
        [
            {
                "effect": "fetch_external_rss_or_api_prediction_and_place_bet",
                "left_rect": bet_ops[0][3:7],
                "right_rect": bet_ops[1][3:7],
                "confirm_rects": [op[3:7] for op in bet_ops[2:5]],
                "exit_rect": bet_ops[5][3:7],
            }
        ],
        True,
        ["external_http_prediction_feed", "wall_clock_2h_slot", "economic_bet_confirmation"],
    )
    b.add("bet_select_side", b.when(2), [bet_gap], counts=counted)

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_retest"] = {"yard_probe_attempts": 3, "yard_probe_sleep_ms": 80}


def build_mystery_shop(b):
    """Build economically guarded native model for 1110_神秘商店."""
    share_var = "shopShare"
    cnt = "shop1110_cnt"
    step = "shop1110_step"
    b.model["vars"] = {share_var: False, cnt: 0, step: False}
    counted = [_count(1110)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}
    lowerings = {}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    def make_swipe(case_id, op_index, lines):
        ops = b.ops[op_index]["oper"]
        gate = b.gap(
            f"swipe_{case_id}",
            lines,
            {"move": f"regionSwipe op[{op_index}]"},
            [{"effect": "source regionSwipe", "duration_ms": [700, 800], "delay": 1000}],
            True,
            ["native swipe on original endpoints and duration"],
            blocking=False,
        )
        lowerings[case_id] = {
            "gate_prefix": gate["fail"],
            "native_intent": {
                "swipe": {"from": ops[0][3:7], "to": ops[1][3:7]},
                "duration_ms": [700, 800],
                "delay": 1000,
                "recheck": True,
            },
        }
        return gate

    # Lines 194-201: navigation to mystery shop (op[0..3]) + economic guard on buy dialog (op[11])
    for idx in (0, 1, 2, 3):
        b.add(f"shop_nav_{idx}", b.when(idx), taps(idx), counts=counted)

    buy_gap = b.gap(
        "mystery_shop_confirm_purchase",
        (194, 201),
        {"screen": "mystery_shop_buy_dialog"},
        [{"effect": "confirm_mystery_shop_purchase", "oper": b.ops[11]["oper"][0]}],
        True,
        ["economic_purchase_confirmation"],
    )
    b.add("shop_confirm_buy_dialog", b.when(11), [buy_gap], counts=counted)

    # Lines 202-240: friend share flow when shopShare is True
    share_on = _expr(share_var)
    for idx in (12, 7):
        b.add(f"share_nav_{idx}", _all(share_on, b.when(idx)), taps(idx), counts=counted)

    share_input_gap = b.gap(
        "mystery_shop_friend_share_input",
        (210, 231),
        {"shopShare": True, "screen": "share_nickname_input"},
        [{"effect": "android_edittext_setText_and_ocr_friend_invite_loop"}],
        True,
        ["android_edittext_input", "ocr_friend_invite_loop"],
    )
    b.add("share_nickname_input", _all(share_on, b.when(9)), [share_input_gap], counts=counted)

    share_swipe = make_swipe("share_swipe_search", 8, (232, 239))
    b.add("share_swipe_search", _all(share_on, b.when(8)), [share_swipe], counts=counted)

    # Lines 241-300: bounded 3-attempt shop scan loop on op[4]
    b.add("shop_loop_init", _expr("True"), [{"set": {cnt: 0, step: False}}], outcome=None, internal=True)
    b.add(
        "shop_loop_check",
        b.when(4),
        [{"inc": cnt}, {"set": {step: True}}, refresh],
        counts=counted,
        outcome=None,
        internal=True,
    )
    black_gap = b.gap(
        "mystery_shop_black_daruma_select",
        (250, 261),
        {"config": "black", "found": "神秘商店_黑碎"},
        [{"effect": "dynamic_subregion_verify_and_select_black_daruma_purchase"}],
        True,
        ["dynamic_subregion_find_colors", "economic_purchase_confirmation"],
    )
    b.add(
        "shop_find_black_daruma",
        _all(_expr(f"{step} and black"), {"find": "神秘商店_黑碎"}),
        [{"set": {step: False}}, black_gap],
    )
    amulet_gap = b.gap(
        "mystery_shop_amulet_select",
        (262, 276),
        {"found": "神秘商店_蓝票"},
        [{"effect": "select_mystery_amulet_purchase_and_arm_share"}],
        True,
        ["economic_purchase_confirmation"],
    )
    b.add(
        "shop_find_blue_amulet",
        _all(_expr(step), {"find": "神秘商店_蓝票"}),
        [{"set": {step: False}}, amulet_gap],
    )
    b.add(
        "shop_max_next_page",
        _all(_expr(f"{step} and {cnt} >= 3"), b.when(5), b.when(6)),
        [*taps(6), {"set": {step: False}}],
        counts=counted,
        outcome=False,
    )
    stop_gap = b.gap(
        "mystery_shop_done_stop",
        (287, 291),
        {"screen": "mystery_shop_scrolled_bottom", "next_page": False},
        [_stop()],
        False,
        ["source stop lifecycle"],
    )
    b.add(
        "shop_max_done_stop",
        _all(_expr(f"{step} and {cnt} >= 3"), b.when(5)),
        [*taps(5), {"set": {step: False}}, stop_gap],
        counts=counted,
        outcome=False,
    )
    scroll_swipe = make_swipe("shop_max_scroll_down", 4, (294, 297))
    b.add(
        "shop_max_scroll_down",
        _all(_expr(f"{step} and {cnt} >= 3"), b.when(4)),
        [scroll_swipe, {"set": {step: False}}],
        outcome=False,
    )
    loop_edge = "unresolved_source_obligation:team1110.shop_scan_loop requires team_workflow"
    b.add(
        "shop_loop_retry",
        _expr(f"{step} and {cnt} < 3"),
        [{"set": {step: False}}, {"wait": 200}, {"fail": loop_edge}],
        outcome=None,
        internal=True,
    )
    edges["shop_loop_retry"] = {"target_case": "shop_loop_check", "gate_prefix": loop_edge}

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_native_lowerings"] = lowerings
    proof["source_state_bindings"] = {"global.shopShare": share_var}
    proof["source_retest"] = {"shop_scan_max_attempts": 3, "shop_scan_sleep_ms": 200}
    proof["resource_costs"] = "All mystery shop item selections and purchase confirmations are gated pending explicit economic confirmation."
