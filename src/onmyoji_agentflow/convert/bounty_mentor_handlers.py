"""Guarded native handlers for 018 (每日悬赏) and 693 (师傅流程).

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

import re

from .core_handlers import _push, _rerun
from .handlers import UnsupportedHandler, _count
from .preset_handler import ONCE_GROUP, ONCE_PRESET, STATE
from .team_handlers import _all, _expr

MASTER_PRESET_PAIRS = (
    ("preset_pair_金币", "preset_group_coin", "preset_slot_coin"),
    ("preset_pair_经验", "preset_group_exp", "preset_slot_exp"),
    ("preset_pair_历练", "preset_group_trial", "preset_slot_trial"),
)


def normalize_master_config(config):
    """Lower 693's preset pairs and timer strings into typed scalars."""
    result = dict(config)
    for source_key, group_key, slot_key in MASTER_PRESET_PAIRS:
        if source_key in result:
            configured = result.pop(source_key)
            match = re.fullmatch(r"\s*([0-7])\s*[,，]\s*([0-4])\s*", configured) if isinstance(configured, str) else None
            if not match:
                raise UnsupportedHandler(f"693 {source_key} needs a preset group 0-7 and a slot 0-4")
            result[group_key], result[slot_key] = map(int, match.groups())
    for key in ("coin", "exp"):
        if key in result:
            raw = result[key]
            if isinstance(raw, str) and re.fullmatch(r"\s*[0-9]{1,5}\s*", raw):
                result[key] = int(raw.strip())
            elif type(raw) is int and raw >= 0:
                result[key] = raw
            else:
                raise UnsupportedHandler(f"693 {key} must be a nonnegative integer, got {raw!r}")
    return result


def build_daily_bounty(b):
    """Build guarded native model for 018_每日悬赏."""
    opened = "xsOpened"
    coop = "xsXieZuo"
    super_next = "super_next_scheme_name"
    cnt = "bounty18_cnt"
    step = "bounty18_step"
    b.model["vars"] = {opened: False, coop: False, super_next: "", cnt: 0, step: False}
    counted = [_count(18)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 277-317: bounty location dialog (op[3])
    loc_dialog = b.when(3)
    enter_confirm = {"click": [1082, 586, 1127, 625], "delay": 1000}
    b.add(
        "loc_challenge_copy",
        _all(loc_dialog, {"find": "悬赏_挑战字样"}),
        [{"click_found": True, "offset": [440, 0, 478, 21], "delay": 4000, "recheck": True}, enter_confirm],
    )
    # find_multi_color scans top-to-bottom so the first hit is minimum-y.
    b.add(
        "loc_secret_copy",
        _all(loc_dialog, {"find": "悬赏_秘闻字样"}),
        [{"click_found": True, "offset": [440, 0, 478, 21], "delay": 2000, "recheck": True}, enter_confirm],
    )
    b.add("loc_untrack_fallback", loc_dialog, taps(3), counts=counted)

    # Lines 319-372: bounded 5-attempt loop on exploration map (op[4], retest=500)
    b.add("explore_loop_init", _expr("True"), [{"set": {cnt: 0, step: False}}], outcome=None, internal=True)
    b.add(
        "explore_loop_check",
        b.when(4),
        [{"inc": cnt}, {"set": {step: True}}, refresh],
        retest_ms=500,
        outcome=None,
        internal=True,
    )
    mystery_push_gap = b.gap(
        "bounty_mystery_monster_push",
        (328, 340),
        {"attempts": 5, "found": "悬赏_神秘妖怪"},
        [_push("悬赏包含神秘妖怪，已停止，请查看。"), {"effect": "leave_explore_and_switch_or_coop"}],
        None,
        ["source Push"],
    )
    b.add(
        "explore_max_mystery_push",
        _all(_expr(f"{step} and {cnt} >= 5"), {"find": "悬赏_神秘妖怪"}),
        [{"set": {step: False}}, mystery_push_gap],
    )
    b.add(
        "explore_max_enter_coop",
        _all(_expr(f"{step} and {cnt} >= 5"), {"find": "悬赏_协作任务"}),
        [*taps(4), {"set": {coop: True, step: False}}],
    )
    done_next_gap = b.gap(
        "bounty_next_scheme_rerun",
        (338, 341),
        {"attempts": 5, "coop_found": False},
        [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 1000}],
        None,
        ["bind next_scheme rerun"],
    )
    b.add(
        "explore_max_done_rerun",
        _expr(f"{step} and {cnt} >= 5"),
        [*taps(4), {"set": {step: False}}, done_next_gap],
    )
    b.add(
        "explore_claim_chest",
        _all(_expr(step), {"find": "悬赏_宝箱"}),
        [{"click_found": True, "offset": [0, 0, 5, 5], "delay": 1000, "recheck": True}, {"set": {step: False}}],
    )
    b.add(
        "explore_tracked_task_clean",
        _all(_expr(step), {"find": "悬赏_已追踪任务"}, {"not": {"find": "悬赏_神秘妖怪"}}),
        [{"click_found": True, "offset": [20, 0, 35, 30], "delay": 1000, "recheck": True}, {"set": {step: False}}],
    )
    filter_mystery_gap = b.gap(
        "bounty_filter_mystery_tracked",
        (355, 370),
        {"found": "悬赏_已追踪任务", "mystery_present": True},
        [{"effect": "findMultiColorEx_filter_out_mystery_monster_subregion"}],
        True,
        ["findMultiColorEx_multi_match", "dynamic_subregion_find_colors"],
    )
    b.add(
        "explore_tracked_task_with_mystery",
        _all(_expr(step), {"find": "悬赏_已追踪任务"}, {"find": "悬赏_神秘妖怪"}),
        [{"set": {step: False}}, filter_mystery_gap],
    )
    exp_edge = "unresolved_source_obligation:team18.explore_loop requires team_workflow"
    b.add(
        "explore_loop_retry",
        _expr(f"{step} and {cnt} < 5"),
        [{"set": {step: False}}, {"wait": 500}, {"fail": exp_edge}],
        outcome=None,
        internal=True,
    )
    edges["explore_loop_retry"] = {"target_case": "explore_loop_check", "gate_prefix": exp_edge}

    # Lines 374-454: coop bounty phase (xsXieZuo == True)
    coop_on = _expr(coop)
    bounty_page = b.when(15)
    coop_subregion_gap = b.gap(
        "bounty_coop_subregion_check",
        (382, 442),
        {"xsXieZuo": True, "coop_complete_marker_present": True},
        [{"effect": "check_coop_complete_within_10px_subregion_of_found_icon"}],
        True,
        ["dynamic_subregion_find_colors"],
    )
    for label, cond_expr, icon in (
        ("jinbi", "not jinBi", "悬赏_金币协作"),
        ("gouliang", "not gouLiang", "悬赏_狗粮协作"),
        ("tili", "not tiLi", "悬赏_体力协作"),
        ("gouyu", "True", "悬赏_勾玉协作"),
        ("accepted", "True", "悬赏_已接受协作"),
    ):
        b.add(
            f"coop_fight_{label}",
            _all(coop_on, bounty_page, _expr(cond_expr), {"find": icon}, {"not": {"find": "悬赏_协作完成"}}),
            [{"click_found": True, "offset": [0, 0, 10, 10], "delay": 1000, "recheck": True}],
        )
        b.add(
            f"coop_fight_{label}_ambiguous",
            _all(coop_on, bounty_page, _expr(cond_expr), {"find": icon}, {"find": "悬赏_协作完成"}),
            [coop_subregion_gap],
        )

    coop_done_rerun = b.gap(
        "bounty_coop_done_rerun",
        (443, 448),
        {"xsXieZuo": True, "coop_remaining": False},
        [_rerun("返回庭院"), {"effect": "sleep", "ms": 1000}],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    b.add(
        "coop_done_return_yard",
        _all(coop_on, bounty_page),
        [*taps(1), {"set": {super_next: "next_scheme"}}, coop_done_rerun],
    )
    b.add(
        "coop_open_from_yard",
        _all(coop_on, {"find": "悬赏_庭院检测悬赏图标"}),
        [{"click_found": True, "offset": [0, 0, 20, 20], "delay": 1000, "recheck": True}],
    )

    # Lines 456-532: open bounty, collect untrack targets, close popup
    not_opened = _expr(f"not {opened}")
    yard = {"any": [b.when(i) for i in (16, 17, 18, 19)]}
    b.add(
        "open_bounty_from_yard",
        _all(not_opened, yard, {"find": "悬赏_庭院检测悬赏图标"}),
        [{"click_found": True, "offset": [0, 0, 20, 20], "delay": 3000, "recheck": True}],
    )
    b.add("open_bounty_one_click_track", _all(not_opened, b.when(0)), taps(0))

    jade_push_gap = b.gap(
        "bounty_jade_coop_push",
        (508, 512),
        {"found": "悬赏_勾玉协作"},
        [_push("发现有勾玉协作，及时邀请。")],
        True,
        ["source Push"],
    )
    b.add("open_bounty_jade_push", _all(not_opened, b.when(1), {"find": "悬赏_勾玉协作"}), [{"set": {opened: True}}, jade_push_gap])

    untrack_gap = b.gap(
        "bounty_untrack_coop_list",
        (478, 527),
        {"bounty_list_open": True, "filtered_coop_icons_present": True},
        [{"effect": "collect_allPoint_coop_icons_and_untrack_each"}],
        True,
        ["dynamic_point_queue_untrack"],
    )
    has_untrack_icon = {
        "any": [
            _all(_expr("jinBi"), {"find": "悬赏_金币协作"}),
            _all(_expr("gouLiang"), {"find": "悬赏_狗粮协作"}),
            _all(_expr("tiLi"), {"find": "悬赏_体力协作"}),
            _all(_expr("ranLiao"), {"find": "悬赏_胧车燃料"}),
            {"find": "悬赏_协作完成"},
        ]
    }
    b.add("open_bounty_filter_coop", _all(not_opened, b.when(1), has_untrack_icon), [{"set": {opened: True}}, untrack_gap])
    b.add("open_bounty_mark_opened", _all(not_opened, b.when(1)), [{"set": {opened: True}}])
    b.add("close_bounty_after_filter", bounty_page, taps(1))

    # Lines 548-553: misc screens (op[5..14])
    for idx in range(5, 15):
        b.add(f"bounty_misc_{idx}", b.when(idx), taps(idx))

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_state_bindings"] = {
        "global.xsOpened": opened,
        "global.xsXieZuo": coop,
        "superGlobal.next_scheme_name": super_next,
    }
    proof["source_retest"] = {"explore_max_attempts": 5, "explore_sleep_ms": 500, "op4_retest_ms": 500}


def build_master_flow(b):
    """Build guarded native model for 693_师傅流程."""
    dur_s = "master693_duration_s"
    deadline = "master693_deadline_ms"
    b.model["vars"] = {
        ONCE_GROUP: "",
        ONCE_PRESET: "",
        STATE: "flushed",
        dur_s: 0,
        deadline: -1,
    }
    counted = [_count(693)]
    count_691 = [_count(691)]
    count_320 = [_count(320)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    reset_preset = {"set": {ONCE_GROUP: repr(""), ONCE_PRESET: repr(""), STATE: repr("flushed")}}

    # Lines 226-235: kraken / leader exit / angry kraken (op[5], op[6], op[7])
    for idx in (5, 6, 7):
        b.add(f"master_exit_{idx}", b.when(idx), [*taps(idx), reset_preset], counts=counted)

    # Lines 236-242: apprentice letters / guard complete / already guarded (op[8], op[10], op[11])
    for idx in (8, 10, 11):
        b.add(f"apprentice_ui_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 243-270: apprentice application OCR matching (op[9])
    apply_gap = b.gap(
        "master_accept_apprentice_ocr",
        (243, 270),
        {"screen": "apprentice_application"},
        [{"effect": "ocr_match_apprentice_name_and_click_accept_or_reject", "region": b.ops[9]["oper"][0][3:7]}],
        True,
        ["ocr_name_substring_click"],
    )
    b.add("apprentice_application_ocr", b.when(9), [apply_gap], counts=counted)

    # Lines 271-279: accept invite when preset finished (op[4])
    b.add("accept_invite", _all(_expr(f"{STATE} == 'finish'"), b.when(4)), taps(4), counts=counted)

    # Lines 280-312: banner invite OCR -> select coin/exp/trial preset & timer (op[1])
    banner_gap = b.gap(
        "master_banner_ocr_preset",
        (280, 312),
        {"screen": "invite_banner"},
        [{"effect": "ocr_banner_type_select_preset_and_arm_timer", "region": b.ops[1]["oper"][0][3:7]}],
        True,
        ["ocr_banner_classification_and_preset_dispatch"],
    )
    b.add("banner_invite_ocr", b.when(1), [banner_gap], counts=count_691)

    # Lines 313-338: timed battle exit
    b.add(
        "timer_arm_on_battle_start",
        _all(_expr(f"{dur_s} > 0 and {dur_s} < 360 and {deadline} < 0"), b.when(2)),
        [{"set": {deadline: f"elapsed_ms + {dur_s} * 1000"}}],
        counts=count_320,
    )
    b.add(
        "timer_expire_timeout_reset",
        _expr(f"{deadline} >= 0 and elapsed_ms > {deadline} + 10000"),
        [{"set": {dur_s: 0, deadline: -1, ONCE_GROUP: repr(""), ONCE_PRESET: repr(""), STATE: repr("flushed")}}],
    )
    b.add(
        "timer_exit_battle",
        _all(_expr(f"{deadline} >= 0 and elapsed_ms > {deadline}"), b.when(3)),
        [*taps(3), {"set": {dur_s: 0, deadline: -1, ONCE_GROUP: repr(""), ONCE_PRESET: repr(""), STATE: repr("flushed")}}],
        counts=count_320,
    )

    b.model["proof"]["source_state_bindings"] = {
        "global.preset_once_groupNum": ONCE_GROUP,
        "global.preset_once_defaultNum": ONCE_PRESET,
        "global.change_shikigami_state": STATE,
        "global.timestamp_duration_s": dur_s,
        "global.timestamp_deadline_ms": deadline,
    }
