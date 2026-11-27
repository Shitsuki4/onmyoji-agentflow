"""Guarded native daily reward handler (518), assttyys (MIT, Copyright (c) 2019 Chaos)."""
from __future__ import annotations

from .core_handlers import _push
from .handlers import _count
from .team_handlers import _all, _expr


def build_daily_rewards(b):
    """Build native model for 518_领取日常奖励."""
    agency = "daily518_agency"
    shop = "daily518_shop"
    friend = "daily518_friend"
    flower = "daily518_flower"
    email = "daily518_email"
    godlike = "daily518_godlike"
    email_cnt = "email_yuHun"
    loop_cnt = "daily518_loop_cnt"
    loop_step = "daily518_loop_step"

    b.model["vars"] = {
        agency: True,
        shop: True,
        friend: True,
        flower: True,
        email: True,
        godlike: True,
        email_cnt: 0,
        loop_cnt: 0,
        loop_step: False,
    }
    counted = [_count(518)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 648-654: misc popups / yard expand
    for idx in (0, 16, 24, 41, 45):
        b.add(f"misc_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 655-683: email phase
    em_on = _expr(email)
    for idx in (12, 13, 14):
        b.add(f"email_reward_{idx}", _all(em_on, b.when(idx)), taps(idx), counts=counted)

    yuhun_full_gap = b.gap(
        "email_yuhun_full_push",
        (663, 666),
        {"email_active": True, "email_yuHun": ">= 8"},
        [_push("邮件里御魂已满")],
        "continue",
        ["source Push"],
    )
    b.add(
        "email_yuhun_full",
        _expr(f"{email} and {email_cnt} >= 8"),
        [{"set": {email: False}}, yuhun_full_gap],
        outcome=None,
        internal=True,
    )
    for idx in (8, 10):
        b.add(
            f"email_claim_{idx}",
            _all(em_on, b.when(idx)),
            [*taps(idx), {"inc": email_cnt}],
            counts=counted,
        )
    for idx in (17, 42):
        b.add(
            f"email_finish_{idx}",
            _all(em_on, b.when(idx)),
            [*taps(idx), {"set": {email: False}}],
            counts=counted,
        )

    # Lines 684-690: unconditional mail cleanup screens
    for idx in (15, 11, 17, 9, 48):
        b.add(f"mail_cleanup_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 691-724: agency (一键代办) phase
    ag_on = _expr(agency)
    b.add(
        "agency_already_done",
        _all(ag_on, b.when(40)),
        [{"set": {agency: False}}],
        counts=counted,
    )
    b.add(
        "agency_loop_init",
        ag_on,
        [{"set": {loop_cnt: 0, loop_step: False}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "agency_loop_tap",
        _all(ag_on, b.when(2)),
        [{"confirm": "购买", "detail": "庭院事务一键代办会按列表消耗金币或体力，请核对全部项目"},
         {"confirm": "分解", "detail": "庭院事务一键代办可能提交御魂或其他材料，请核对投入物品"},
         *taps(2), {"inc": loop_cnt}, {"set": {loop_step: True}}, refresh],
        counts=counted,
        outcome=None,
    )
    b.add(
        "agency_loop_max",
        _expr(f"{loop_step} and {loop_cnt} >= 2"),
        [{"set": {agency: False, loop_step: False}}],
        internal=True,
    )
    ag_edge = "unresolved_source_obligation:team518.agency_loop requires team_workflow"
    b.add(
        "agency_loop_retry",
        _expr(f"{loop_step} and {loop_cnt} < 2"),
        [{"set": {loop_step: False}}, {"wait": 1000}, {"fail": ag_edge}],
        outcome=None,
        internal=True,
    )
    edges["agency_loop_retry"] = {"target_case": "agency_loop_tap", "gate_prefix": ag_edge}

    for idx in (1, 43, 3, 5):
        b.add(f"agency_step_{idx}", _all(ag_on, b.when(idx)), taps(idx), counts=counted)

    # Lines 725-765: shop (商店黑蛋) phase
    sh_on = _expr(shop)
    for idx in (19, 20, 21, 5):
        b.add(f"shop_step_{idx}", _all(sh_on, b.when(idx)), taps(idx), counts=counted)

    b.add(
        "shop_loop_init",
        sh_on,
        [{"set": {loop_cnt: 0, loop_step: False}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "shop_loop_check",
        _all(sh_on, b.when(22)),
        [{"inc": loop_cnt}, {"set": {loop_step: True}}, refresh],
        counts=counted,
        outcome=None,
        internal=True,
    )
    exit_shop = b.actions(22)
    b.add(
        "shop_claim_daruma",
        _all(_expr(loop_step), b.when(23)),
        [*taps(23), *exit_shop, {"set": {shop: False, loop_step: False}}],
        counts=counted,
    )
    b.add(
        "shop_open_daily_tab",
        _all(_expr(loop_step), {"find": "商店_日常"}),
        [
            {"click_found": True, "offset": [-50, 20, -30, 40], "delay": 1000, "recheck": True},
            {"set": {loop_step: False}},
        ],
    )
    shop_timeout_gap = b.gap(
        "shop_daily_not_found_push",
        (756, 762),
        {"shop_active": True, "attempts": 10},
        [_push("连续差查找10次未找到，跳过领取"), {"effect": "exit_shop_and_disable_shop"}],
        True,
        ["source Push"],
    )
    b.add(
        "shop_loop_max",
        _expr(f"{loop_step} and {loop_cnt} >= 10"),
        [{"set": {loop_step: False}}, shop_timeout_gap],
        internal=True,
    )
    sh_edge = "unresolved_source_obligation:team518.shop_loop requires team_workflow"
    b.add(
        "shop_loop_retry",
        _expr(f"{loop_step} and {loop_cnt} < 10"),
        [{"set": {loop_step: False}}, {"wait": 500}, {"fail": sh_edge}],
        outcome=None,
        internal=True,
    )
    edges["shop_loop_retry"] = {"target_case": "shop_loop_check", "gate_prefix": sh_edge}

    # Lines 766-798: friend (好友吉闻) phase
    fr_on = _expr(friend)
    for idx in (25, 26, 27):
        b.add(f"friend_step_{idx}", _all(fr_on, b.when(idx)), taps(idx), counts=counted)

    b.add(
        "friend_loop_init",
        fr_on,
        [{"set": {loop_cnt: 0, loop_step: False}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "friend_bless_tap",
        _all(fr_on, b.when(29)),
        [*taps(29), {"inc": loop_cnt}, {"set": {loop_step: True}}, refresh],
        counts=counted,
        outcome=None,
    )
    bless_push_gap = b.gap(
        "friend_bless_empty_push",
        (783, 787),
        {"friend_active": True, "attempts": 3},
        [_push("无祝福语言,自行输入")],
        True,
        ["source Push"],
    )
    b.add(
        "friend_bless_max",
        _expr(f"{loop_step} and {loop_cnt} >= 3"),
        [{"set": {friend: False, loop_step: False}}, bless_push_gap],
        internal=True,
    )
    fr_edge = "unresolved_source_obligation:team518.friend_loop requires team_workflow"
    b.add(
        "friend_bless_retry",
        _expr(f"{loop_step} and {loop_cnt} < 3"),
        [{"set": {loop_step: False}}, {"wait": 1000}, {"fail": fr_edge}],
        outcome=None,
        internal=True,
    )
    edges["friend_bless_retry"] = {"target_case": "friend_bless_tap", "gate_prefix": fr_edge}

    b.add(
        "friend_no_bless_exit",
        _all(fr_on, b.when(28)),
        [*taps(28), {"set": {friend: False}}],
        counts=counted,
    )

    # Lines 799-825: flower (花合战) phase
    fl_on = _expr(flower)
    for idx in (35, 36, 39, 46, 47):
        b.add(f"flower_step_{idx}", _all(fl_on, b.when(idx)), taps(idx), counts=counted)

    b.add(
        "flower_claim_all",
        _all(fl_on, b.when(38), b.when(37)),
        taps(37),
        counts=counted,
    )
    b.add(
        "flower_exit",
        _all(fl_on, b.when(38)),
        [*taps(38), {"set": {flower: False}}],
        counts=counted,
    )

    # Lines 826-904: NetEase Dashen app (com.netease.gl) accessibility UI
    godlike_gap = b.gap(
        "godlike_dashen_app",
        (826, 904),
        {"godlike": True, "in_game_switches_finished": True},
        [{"effect": "launch_and_automate_com.netease.gl_via_accessibility_ui"}],
        True,
        ["android_package_switch:com.netease.gl", "android_accessibility_ui_selectors"],
    )
    b.add(
        "godlike_dashen_gate",
        _expr(f"{godlike} and not {agency} and not {shop} and not {friend} and not {flower} and not {email}"),
        [godlike_gap],
        internal=True,
    )

    # Lines 905-912: exit popups/screens
    for idx in (4, 6, 7, 30, 31, 32, 33, 34, 38, 44):
        b.add(f"exit_{idx}", b.when(idx), taps(idx), counts=counted)

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_state_bindings"] = {
        "global.function_Switch.agency": agency,
        "global.function_Switch.shop": shop,
        "global.function_Switch.friend": friend,
        "global.function_Switch.flower": flower,
        "global.function_Switch.email": email,
        "global.function_Switch.godlike": godlike,
        "global.email_yuHun": email_cnt,
    }
    proof["source_retest"] = {
        "agency_max_attempts": 2,
        "agency_sleep_ms": 1000,
        "shop_max_attempts": 10,
        "shop_sleep_ms": 500,
        "friend_bless_max_attempts": 3,
        "friend_bless_sleep_ms": 1000,
    }
