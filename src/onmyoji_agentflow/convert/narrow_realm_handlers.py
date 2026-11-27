"""Guarded native battle-options (318) and narrow-realm (603) handlers.

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

import copy
import re

from .core_handlers import _rerun
from .handlers import UnsupportedHandler, _count
from .preset_handler import BATTLE_GROUP, BATTLE_PENDING, BATTLE_PRESET, ONCE_GROUP, ONCE_PRESET, STATE
from .team_handlers import _all, _expr

BOSS_ZONES = {"神龙": 0, "孔雀": 1, "狐狸": 2, "豹子": 3}
NARROW_PRESET_PAIRS = (
    ("preset_pair_小蛇", "preset_group_xiaoshe", "preset_slot_xiaoshe"),
    ("preset_pair_精英", "preset_group_jingying", "preset_slot_jingying"),
    ("preset_pair_副将", "preset_group_fujiang", "preset_slot_fujiang"),
    ("preset_pair_首领", "preset_group_shouling", "preset_slot_shouling"),
)


def normalize_narrow_realm_config(config):
    """Lower 603's list/string settings into typed scalar parameters."""
    result = dict(config)
    if "boss_select" in result:
        selected = result.pop("boss_select")
        if (not isinstance(selected, list) or len(selected) < 2
                or any(not isinstance(name, str) or name not in BOSS_ZONES for name in selected[:2])):
            raise UnsupportedHandler("603 boss_select requires at least two valid zone names")
        result["boss_select_one"] = BOSS_ZONES[selected[0]]
        result["boss_select_two"] = BOSS_ZONES[selected[1]]
    if "sneak" in result:
        raw_sneak = result["sneak"]
        if isinstance(raw_sneak, str) and re.fullmatch(r"\s*[0-9]{1,3}\s*", raw_sneak):
            result["sneak"] = int(raw_sneak.strip())
        elif type(raw_sneak) is int and raw_sneak >= 0:
            result["sneak"] = raw_sneak
        else:
            raise UnsupportedHandler(f"603 sneak must be a nonnegative integer, got {raw_sneak!r}")
    for source_key, group_key, slot_key in NARROW_PRESET_PAIRS:
        if source_key in result:
            configured = result.pop(source_key)
            match = re.fullmatch(r"\s*([0-7])\s*[,，]\s*([0-4])\s*", configured) if isinstance(configured, str) else None
            if not match:
                raise UnsupportedHandler(f"603 {source_key} needs a preset group 0-7 and a slot 0-4")
            result[group_key], result[slot_key] = map(int, match.groups())
    return result


def build_battle_options(b):
    """Build native model for 318_战斗内操作选项."""
    inited = "fight318_inited"
    xing_mie = "fight318_xingMie"
    di_si_tian = "fight318_diSiTian"
    deadline = "fight318_deadline_ms"
    skill_open = "fight318_skill_box_open"
    b.model["vars"] = {
        inited: False,
        xing_mie: False,
        di_si_tian: False,
        deadline: -1,
        skill_open: False,
    }
    refresh = {"handler_control": {"op": "refresh"}}

    # Split 帝释天 find region cleanly on anchor x < 1090 vs x >= 1090.
    base_dst = b.colors.get("帝释天")
    if base_dst is None:
        raise UnsupportedHandler("318 requires color resource 帝释天")
    x1, y1, x2, y2 = base_dst["region"]
    b.colors["帝释天_left"] = {**copy.deepcopy(base_dst), "region": [x1, y1, min(x2, 1089), y2]}
    b.colors["帝释天_right"] = {**copy.deepcopy(base_dst), "region": [max(x1, 1090), y1, x2, y2]}

    # Lines 156-162: lazy init of global.fight_Switch
    b.add(
        "init_state",
        _expr(f"not {inited}"),
        [{"set": {inited: True, xing_mie: "xingMie", di_si_tian: "diSiTian", deadline: -1}}],
        outcome=None,
        internal=True,
    )

    # Lines 163-197: 战字 (op[6]) / 一回目 (op[9]) start banner
    start_banner = {"any": [b.when(6), b.when(9)]}
    count_320 = [_count(320)]
    count_318 = [_count(318)]
    b.add(
        "start_init_timed",
        _all(start_banner, _expr("time > 0")),
        [{"set": {xing_mie: "xingMie", di_si_tian: "diSiTian", deadline: "elapsed_ms + time * 1000"}}],
        counts=count_320,
        outcome=None,
        internal=True,
    )
    b.add(
        "start_init_untimed",
        _all(start_banner, _expr("time <= 0")),
        [{"set": {xing_mie: "xingMie", di_si_tian: "diSiTian", deadline: -1}}],
        counts=count_320,
        outcome=None,
        internal=True,
    )
    qingming_tap = b.actions(0)[0]
    skill2_tap, skill3_tap = b.actions(4)[0], b.actions(4)[1]
    b.add(
        "start_xingmie",
        _all(start_banner, _expr(xing_mie)),
        [{**qingming_tap, "recheck": True}, skill3_tap],
        outcome=None,
        internal=True,
    )
    b.add(
        "start_disitian_left",
        _all(start_banner, _expr(di_si_tian), {"find": "帝释天_left"}),
        [
            {"click_found": True, "offset": [0, 0, 10, 10], "delay": 500, "recheck": True},
            {"click_found": True, "offset": [-30, -130, -20, -120], "delay": 250},
        ],
    )
    b.add(
        "start_disitian_right",
        _all(start_banner, _expr(di_si_tian), {"find": "帝释天_right"}),
        [
            {"click_found": True, "offset": [0, 0, 10, 10], "delay": 500, "recheck": True},
            {"click_found": True, "offset": [-80, -130, -70, -120], "delay": 250},
        ],
    )

    # Lines 198-217: timed battle exit
    battle_screen = b.when(8)
    b.add(
        "timer_arm",
        _all(_expr(f"time > 0 and {deadline} < 0"), battle_screen),
        [{"set": {deadline: "elapsed_ms + time * 1000"}}],
        outcome=None,
        internal=True,
    )
    exit_acts = b.actions(8)
    b.add(
        "timer_exit",
        _all(_expr(f"time > 0 and {deadline} >= 0 and elapsed_ms > {deadline}"), battle_screen),
        [{**exit_acts[0], "recheck": True}, *exit_acts[1:], {"set": {deadline: -1}}],
        counts=count_320,
    )

    # Lines 218-261: xingMie in-battle toggle
    xm_on = _expr(xing_mie)
    b.add(
        "xingmie_onmyoji",
        _all(xm_on, b.when(1), b.when(0)),
        [{**qingming_tap, "recheck": True}, refresh],
        counts=count_318,
        retest_ms=500,
        outcome=None,
    )
    b.add(
        "xingmie_skill_box_wait",
        _all(xm_on, b.when(3)),
        [{"wait": 250}, {"set": {skill_open: True}}],
        counts=count_318,
        outcome=None,
        internal=True,
    )
    b.add(
        "xingmie_skill_to_3",
        _all(_expr(skill_open), b.when(2)),
        [{**skill3_tap, "recheck": True}, {"set": {skill_open: False}}, refresh],
        counts=count_318,
        outcome=None,
    )
    b.add(
        "xingmie_skill_to_2",
        _all(_expr(skill_open), b.when(3)),
        [{**skill2_tap, "recheck": True}, {"set": {skill_open: False}}, refresh],
        outcome=None,
    )
    b.add(
        "xingmie_skill_box_clear",
        _expr(skill_open),
        [{"set": {skill_open: False}}],
        outcome=None,
        internal=True,
    )
    single_tap = b.actions(5)[0]
    b.add(
        "xingmie_single_skill",
        _all(xm_on, b.when(5)),
        [{**single_tap, "recheck": True}, refresh],
        counts=count_318,
        outcome=None,
    )
    b.add(
        "xingmie_unpopped_box",
        _all(xm_on, b.when(4)),
        [{**qingming_tap, "recheck": True}, refresh],
        counts=count_318,
        outcome=None,
    )

    # Lines 262-285: diSiTian action-bar switch to normal attack
    dst_on = _all(_expr(di_si_tian), b.when(7))
    b.add(
        "disitian_action_left",
        _all(dst_on, {"find": "帝释天_left"}),
        [
            {"wait": 2000},
            {"click_found": True, "offset": [0, 0, 10, 10], "delay": 500},
            {"click_found": True, "offset": [-120, -130, -110, -120], "delay": 250},
            {"set": {di_si_tian: False}},
        ],
        counts=count_318,
    )
    b.add(
        "disitian_action_right",
        _all(dst_on, {"find": "帝释天_right"}),
        [
            {"wait": 2000},
            {"click_found": True, "offset": [0, 0, 10, 10], "delay": 500},
            {"click_found": True, "offset": [-170, -130, -160, -120], "delay": 250},
            {"set": {di_si_tian: False}},
        ],
        counts=count_318,
    )
    b.add(
        "disitian_action_miss",
        dst_on,
        [],
        counts=count_318,
        outcome=None,
        internal=True,
    )

    proof = b.model["proof"]
    proof["source_state_bindings"] = {
        "global.fight_Switch.xingMie": xing_mie,
        "global.fight_Switch.diSiTian": di_si_tian,
        "global.fight_Switch.time": deadline,
    }
    proof["source_retest"] = {"op0_retest_ms": 500}


def build_narrow_realm(b):
    """Build native model for 603_狭间暗域."""
    base_init = "xiajian603_base_inited"
    base_rt2 = "xiajian603_runTime_2"
    fenzu = "xiajian603_fenZu"
    zhenrong = "xiajian603_zhenRong"
    real_var = "xiajian603_real"
    has_stage = "xiajian603_has_stage"
    p_var, q_var = "xiajian603_p", "xiajian603_q"
    zone_var, monster_var = "xiajian603_zone", "xiajian603_monster"
    in_report = "xiajian603_in_report"
    cur_cnt = "xiajian603_cur_cnt"
    loop_step = "xiajian603_loop_step"

    b.model["vars"] = {
        "run_times_2": 0,
        base_init: False,
        base_rt2: 0,
        fenzu: 0,
        zhenrong: 0,
        real_var: 0,
        has_stage: False,
        p_var: 0,
        q_var: 0,
        zone_var: 0,
        monster_var: 0,
        in_report: False,
        cur_cnt: 0,
        loop_step: False,
        ONCE_GROUP: "",
        ONCE_PRESET: "",
        BATTLE_GROUP: "",
        BATTLE_PRESET: "",
        STATE: "flushed",
        BATTLE_PENDING: False,
    }
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}

    # Lines 220-226: capture initial runTimes['2'] baseline
    b.add(
        "init_baseline",
        _expr(f"not {base_init}"),
        [{"set": {base_rt2: "run_times_2", base_init: True}}],
        outcome=None,
        internal=True,
    )

    # Line 282: Real = runTimes['2'] - global.runTime_2 - sneak
    b.add(
        "compute_real",
        _expr("True"),
        [{"set": {
            real_var: f"run_times_2 - {base_rt2} - sneak",
            has_stage: False,
            p_var: 0,
            q_var: 0,
            cur_cnt: 0,
            in_report: False,
            loop_step: False,
        }}],
        outcome=None,
        internal=True,
    )

    # Lines 283-306: finished checks -> rerun('返回庭院') + sleep(1000)
    done_rerun = b.gap(
        "narrow_realm_done_rerun",
        (283, 306),
        {"screen": "guild_home", "finished": True},
        [_rerun("返回庭院"), {"effect": "sleep", "ms": 1000}],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    done_cond = _expr(f"(boss_order == '大到小' and {real_var} >= 12) or {real_var} >= 14")
    b.add("done_return_yard", _all(done_cond, b.when(9)), [{"log": "已完成狭间"}, done_rerun])
    b.add("done_wait_guild_screen", done_cond, [], outcome=False, internal=True)

    # Lines 307-350: stage preset selection & sync with 510 / 315 globals
    b.add(
        "stage_preset_xiaoshe",
        _expr(f"sneak > 0 and run_times_2 == {base_rt2}"),
        [{"set": {has_stage: True, p_var: "preset_group_xiaoshe", q_var: "preset_slot_xiaoshe"}}],
        outcome=None,
        internal=True,
    )
    not_xiaoshe = f"not (sneak > 0 and run_times_2 == {base_rt2})"
    for label, cond_expr, grp, slt in (
        ("s2b_jingying", f"boss_order == '小到大' and {real_var} == 0", "preset_group_jingying", "preset_slot_jingying"),
        ("s2b_fujiang", f"boss_order == '小到大' and {real_var} == 6", "preset_group_fujiang", "preset_slot_fujiang"),
        ("s2b_shouling", f"boss_order == '小到大' and {real_var} == 10", "preset_group_shouling", "preset_slot_shouling"),
        ("b2s_shouling", f"boss_order == '大到小' and {real_var} == 0", "preset_group_shouling", "preset_slot_shouling"),
        ("b2s_fujiang", f"boss_order == '大到小' and {real_var} == 2", "preset_group_fujiang", "preset_slot_fujiang"),
        ("b2s_jingying", f"boss_order == '大到小' and {real_var} == 6", "preset_group_jingying", "preset_slot_jingying"),
    ):
        b.add(
            f"stage_preset_{label}",
            _expr(f"{not_xiaoshe} and {cond_expr}"),
            [{"set": {has_stage: True, p_var: grp, q_var: slt}}],
            outcome=None,
            internal=True,
        )

    b.add(
        "preset_write_override",
        _expr(f"{has_stage} and {p_var} != 0 and {q_var} != 0"),
        [{"set": {ONCE_GROUP: p_var, ONCE_PRESET: q_var, BATTLE_GROUP: p_var, BATTLE_PRESET: q_var}}],
        outcome=None,
        internal=True,
    )
    once_active = f"{ONCE_GROUP} != '' and {ONCE_GROUP} != 0"
    b.add(
        "preset_arm_switch",
        _expr(f"{has_stage} and {once_active} and ({ONCE_GROUP} != {fenzu} or {ONCE_PRESET} != {zhenrong})"),
        [{"set": {fenzu: ONCE_GROUP, zhenrong: ONCE_PRESET, BATTLE_PENDING: True, STATE: repr("flushed")}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "preset_clear_when_inactive",
        _expr(f"(not {has_stage}) or (not ({once_active}))"),
        [{"set": {BATTLE_PENDING: False, STATE: repr("finish")}}],
        outcome=None,
        internal=True,
    )

    # Lines 352-360: 检测_寮进入狭间 -> click first selected zone (op[0].oper[0..3])
    enter_acts = b.actions(0)
    for zone_idx in range(4):
        b.add(
            f"enter_zone_{zone_idx}",
            _all(b.when(0), _expr(f"boss_select_one == {zone_idx}")),
            [{**enter_acts[zone_idx], "recheck": True}],
        )

    # Lines 361-368: preset pending -> enter shikigami records (op[5]) or exit report (op[6])
    need_preset = _expr(f"{STATE} != 'finish'")
    for idx in (5, 6):
        acts = b.actions(idx)
        b.add(f"preset_nav_{idx}", _all(need_preset, b.when(idx)), [{**acts[0], "recheck": True}, *acts[1:]])

    # Lines 369-375: 集结中 (op[7]) -> sleep(1000)
    b.add("gathering_wait", b.when(7), [{"wait": 1000}])

    # Lines 376-381: 进入战报 (op[1]) or 前往 (op[2])
    for idx in (1, 2):
        acts = b.actions(idx)
        b.add(f"select_attack_{idx}", b.when(idx), [{**acts[0], "recheck": True}, *acts[1:]])

    # Lines 382-387: clamp Real 12->11, 13->10 and compute zone/monster indices
    b.add("clamp_real_12", _expr(f"{real_var} == 12"), [{"set": {real_var: 11}}], outcome=None, internal=True)
    b.add("clamp_real_13", _expr(f"{real_var} == 13"), [{"set": {real_var: 10}}], outcome=None, internal=True)

    b.add(
        "pick_zone_one",
        _expr(
            f"(boss_order == '小到大' and (({real_var} >= 0 and {real_var} <= 2) or ({real_var} >= 8 and {real_var} <= 10)))"
            f" or (boss_order == '大到小' and ({real_var} == 0 or ({real_var} >= 4 and {real_var} <= 8)))"
        ),
        [{"set": {zone_var: "boss_select_one"}}],
        outcome=None,
        internal=True,
    )
    b.add(
        "pick_zone_two",
        _expr(
            f"(boss_order == '小到大' and (({real_var} >= 3 and {real_var} <= 7) or {real_var} == 11))"
            f" or (boss_order == '大到小' and (({real_var} >= 1 and {real_var} <= 3) or ({real_var} >= 9 and {real_var} <= 11)))"
        ),
        [{"set": {zone_var: "boss_select_two"}}],
        outcome=None,
        internal=True,
    )

    monster_rules = (
        (0, f"(boss_order == '小到大' and ({real_var} == 10 or {real_var} == 11)) or (boss_order == '大到小' and ({real_var} == 0 or {real_var} == 1))"),
        (1, f"(boss_order == '小到大' and ({real_var} == 7 or {real_var} == 9)) or (boss_order == '大到小' and ({real_var} == 3 or {real_var} == 5))"),
        (2, f"(boss_order == '小到大' and ({real_var} == 6 or {real_var} == 8)) or (boss_order == '大到小' and ({real_var} == 2 or {real_var} == 4))"),
        (3, f"(boss_order == '小到大' and ({real_var} == 0 or {real_var} == 3)) or (boss_order == '大到小' and ({real_var} == 6 or {real_var} == 9))"),
        (4, f"(boss_order == '小到大' and ({real_var} == 1 or {real_var} == 4)) or (boss_order == '大到小' and ({real_var} == 7 or {real_var} == 10))"),
        (5, f"(boss_order == '小到大' and ({real_var} == 2 or {real_var} == 5)) or (boss_order == '大到小' and ({real_var} == 8 or {real_var} == 11))"),
    )
    for m_idx, expr_text in monster_rules:
        b.add(f"pick_monster_{m_idx}", _expr(expr_text), [{"set": {monster_var: m_idx}}], outcome=None, internal=True)

    # Lines 388-424: bounded while loop on 战报页内 (op[3], maxCount=3)
    report_screen = b.when(3)
    b.add("report_loop_check", report_screen, [{"set": {in_report: True}}], outcome=None, internal=True)

    covered_acts = b.actions(8)
    b.add(
        "report_covered",
        _all(_expr(in_report), b.when(8)),
        [{**covered_acts[0], "recheck": True}, {"set": {in_report: False}}],
    )
    snake_acts = b.actions(4)
    b.add(
        "report_small_snake",
        _all(_expr(f"{in_report} and run_times_2 - {base_rt2} < sneak"), b.when(4)),
        [{**snake_acts[0], "recheck": True}, {"set": {in_report: False}}],
    )

    report_acts = b.actions(3)
    for z_idx in range(4):
        b.add(
            f"report_click_zone_{z_idx}",
            _all(_expr(f"{in_report} and {real_var} >= 0 and {zone_var} == {z_idx}"), report_screen),
            [{**report_acts[z_idx + 6], "recheck": True}],
            outcome=None,
        )
    for m_idx in range(6):
        b.add(
            f"report_click_monster_{m_idx}",
            _all(_expr(f"{in_report} and {real_var} >= 0 and {monster_var} == {m_idx}"), report_screen),
            [report_acts[m_idx]],
            outcome=None,
        )
    b.add(
        "report_after_clicks",
        _expr(in_report),
        [{"inc": cur_cnt}, {"set": {in_report: False, loop_step: True}}, refresh],
        outcome=None,
        internal=True,
    )
    b.add(
        "report_loop_max",
        _expr(f"{loop_step} and {cur_cnt} >= 3"),
        [{"set": {base_rt2: f"{base_rt2} - 1", loop_step: False}}],
        outcome=False,
        internal=True,
    )
    loop_edge = "unresolved_source_obligation:team603.report_loop requires team_workflow"
    b.add(
        "report_loop_retry",
        _expr(f"{loop_step} and {cur_cnt} < 3"),
        [{"set": {loop_step: False}}, {"wait": 500}, {"fail": loop_edge}],
        outcome=None,
        internal=True,
    )
    edges["report_loop_retry"] = {"target_case": "report_loop_check", "gate_prefix": loop_edge}

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_state_bindings"] = {
        "runTimes.2": "run_times_2",
        "global.runTime_2": base_rt2,
        "global.xiaJian.fenZu": fenzu,
        "global.xiaJian.zhenRong": zhenrong,
        "global.preset_once_groupNum": ONCE_GROUP,
        "global.preset_once_defaultNum": ONCE_PRESET,
        "global.preset_once_team_groupNum": BATTLE_GROUP,
        "global.preset_once_team_defaultNum": BATTLE_PRESET,
        "global.shangyushe": BATTLE_PENDING,
        "global.change_shikigami_state": STATE,
    }
    proof["source_retest"] = {"report_max_attempts": 3, "report_sleep_ms": 500}
