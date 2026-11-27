"""Guarded native demon encounter handlers (023 quiz, 508 boss).

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

from .core_handlers import _rerun
from .handlers import _count
from .team_handlers import _all, _expr


def build_demon_quiz(b):
    """Build guarded native model for 023_逢魔答题."""
    ops = b.ops[0]["oper"]
    quiz_gap = b.gap(
        "demon_quiz_ocr_lookup",
        (29, 96),
        {"screen": "demon_quiz_dialog"},
        [
            {
                "effect": "ocr_question_and_answer_bank_click",
                "question_rect": ops[0][3:7],
                "answer_rect": ops[1][3:7],
                "fallback_click": ops[2][3:8],
            }
        ],
        True,
        ["ocr_question_and_answer_boxes", "assttyys_question_bank_fuzzy_search"],
    )
    b.add("demon_quiz_dialog", b.when(0), [quiz_gap])


def build_demon_boss(b):
    """Build native model for 508_逢魔首领."""
    kiss = "fm_kiss_boss_flag"
    click_cnt = "fm_boss_btn_click_cnt"
    yard_cnt = "checked_yard_count"
    super_next = "super_next_scheme_name"
    switch_boss = "demon508_switch_boss"
    limit_var = "demon508_limit"
    use_ji = "demon508_use_ji"
    retry_mult = "demon508_retry_mult"
    searched = "demon508_search_clicked"

    b.model["vars"] = {
        kiss: False,
        click_cnt: 0,
        yard_cnt: 0,
        super_next: "",
        switch_boss: False,
        limit_var: 20,
        use_ji: False,
        retry_mult: 1,
        searched: False,
    }
    counted = [_count(508)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 226-245: gathering scene -> pick trash if found + mark fm_kiss_boss_flag
    gather = b.when(7)
    b.add(
        "gathering_pick_trash",
        _all(gather, {"find": "逢魔_捡垃圾"}),
        [
            {"click_found": True, "offset": [-2, -2, 2, 2], "delay": 1200, "recheck": True},
            {"set": {kiss: True}},
        ],
        outcome=None,
    )
    b.add(
        "gathering_mark_boss",
        _all(gather, _expr(f"not {kiss}")),
        [{"set": {kiss: True}}],
        outcome=None,
        internal=True,
    )

    # Lines 247-255: found demon boss icon (op[1], op[10])
    for idx in (1, 10):
        b.add(f"found_boss_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 257-307: boss challenge page (op[2] normal or op[8] ji)
    boss_page = {"any": [b.when(2), b.when(8)]}
    challenge_tap, close_tap = b.actions(2)[0], b.actions(2)[1]
    b.add(
        "boss_page_retry_limit",
        _all(boss_page, _expr(f"{yard_cnt} >= 5")),
        [
            {**challenge_tap, "recheck": True},
            {"set": {yard_cnt: 0, switch_boss: True}},
            close_tap,
            {"wait": 2000},
        ],
        counts=counted,
        outcome=None,
    )
    b.add(
        "boss_page_switch_ji",
        _all(_expr(f"{switch_boss} and switch_ji_enabled"), b.when(9)),
        [*taps(9), {"set": {switch_boss: False}}],
    )
    b.add(
        "boss_page_switch_normal",
        _all(_expr(f"{switch_boss} and not switch_ji_enabled"), b.when(0)),
        [*taps(0), {"set": {switch_boss: False}}],
    )
    b.add(
        "boss_page_switch_done",
        _expr(switch_boss),
        [{"set": {switch_boss: False}}],
        internal=True,
    )
    b.add(
        "boss_page_challenge",
        boss_page,
        [{**challenge_tap, "recheck": True}, {"wait": 1000}, {"inc": yard_cnt}],
        counts=counted,
    )

    # Lines 310-328: dialog confirm (op[3]) and enter battle (op[4])
    b.add("confirm_dialog", b.when(3), taps(3), counts=counted)
    b.add("enter_battle", b.when(4), taps(4), counts=counted)

    # Lines 330-345: settlement screens (op[5], op[6] using op[5].oper)
    settle_acts = b.actions(5)
    for idx in (5, 6):
        b.add(
            f"settlement_{idx}",
            b.when(idx),
            [{**settle_acts[0], "recheck": True}, *settle_acts[1:], {"set": {kiss: True}}],
        )

    # Lines 347-401: discovery reward claimed screen (op[0])
    done_rerun = b.gap(
        "demon_boss_done_rerun",
        (355, 358),
        {"screen": "demon_discovery_done", "fm_kiss_boss_flag": True},
        [_rerun("返回庭院")],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    b.add(
        "boss_done_return_yard",
        _all(b.when(0), _expr(kiss)),
        [{"set": {super_next: "next_scheme"}}, done_rerun],
    )

    not_done_0 = _all(b.when(0), _expr(f"not {kiss}"))
    b.add(
        "search_limit_configured",
        _all(not_done_0, _expr("times_for_search_boss > 0")),
        [{"set": {limit_var: "times_for_search_boss", searched: False}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "search_limit_default",
        _all(not_done_0, _expr("times_for_search_boss <= 0")),
        [{"set": {limit_var: 20, searched: False}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "search_mode_ji",
        _all(not_done_0, _expr(f"switch_ji_enabled and {click_cnt} < {limit_var}")),
        [{"set": {use_ji: True, retry_mult: 1}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "search_mode_fallback_normal",
        _all(not_done_0, _expr(f"switch_ji_enabled and {click_cnt} >= {limit_var}")),
        [{"set": {use_ji: False, retry_mult: 2}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "search_mode_normal",
        _all(not_done_0, _expr("not switch_ji_enabled")),
        [{"set": {use_ji: False, retry_mult: 1}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "search_click_ji",
        _all(not_done_0, _expr(use_ji), b.when(9)),
        [*taps(9), {"set": {searched: True}}],
        outcome=None,
    )
    b.add(
        "search_click_normal",
        _all(not_done_0, _expr(f"not {use_ji}")),
        [*taps(0), {"set": {searched: True}}],
        outcome=None,
    )
    b.add(
        "search_mark_limit_reached",
        _expr(f"{searched} and {click_cnt} >= {limit_var} * {retry_mult}"),
        [{"set": {kiss: True}}],
        outcome=None,
        internal=True,
    )
    skip_tap = b.actions(10)[0]
    b.add(
        "search_after_skip_click",
        _expr(f"{searched} and switch_skip_search_boss"),
        [{"inc": click_cnt}, {"set": {searched: False}}, {**skip_tap, "recheck": True}],
        counts=counted,
    )
    b.add(
        "search_after_wait",
        _expr(searched),
        [{"inc": click_cnt}, {"set": {searched: False}}, {"wait": 2000}],
    )

    # Lines 402-407: 歌姬胧车 (op[11])
    b.add("no_ji_boss_button", b.when(11), taps(11))

    proof = b.model["proof"]
    proof["source_state_bindings"] = {
        "global.fm_kiss_boss_flag": kiss,
        "global.fm_boss_btn_click_cnt": click_cnt,
        "global.checked_yard_count": yard_cnt,
        "superGlobal.next_scheme_name": super_next,
    }
