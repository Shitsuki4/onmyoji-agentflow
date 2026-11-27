"""Guarded native guild banquet handler (605), assttyys (MIT, Copyright (c) 2019 Chaos)."""
from .core_handlers import _push, _rerun, _stop
from .team_handlers import _all, _expr


def build_guild_banquet(b):
    collect_var = "liao_banquet_collect"
    ongoing_var = "liao_banquet_onGoing"
    change_var = "banquet_change_flag"
    open_cnt, open_step = "banquet605_open_cnt", "banquet605_open_step"
    b.model["vars"] = {
        collect_var: False,
        ongoing_var: True,
        change_var: False,
        "run_times_2": 0,
        open_cnt: 0,
        open_step: False,
    }
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}
    lowerings = {}

    def make_swipe(name, op_index, duration, delay, lines):
        ops = b.ops[op_index]["oper"]
        gate = b.gap(
            f"swipe_{name}", lines, {"move": f"regionSwipe op[{op_index}]"},
            [{"effect": "source regionSwipe", "duration_ms": duration, "delay": delay}],
            True, ["native swipe on original endpoints and duration"], blocking=False,
        )
        lowerings[name] = {
            "gate_prefix": gate["fail"],
            "native_intent": {
                "swipe": {"from": ops[0][3:7], "to": ops[1][3:7]},
                "duration_ms": duration,
                "delay": delay,
                "recheck": True,
            },
        }
        return gate

    # Part 1: liao_banquet_collect == True (lines 360-456)
    collect = _expr(collect_var)
    prep_fail_gap = b.gap(
        "banquet_prepare_failed", (361, 369), {"screen": "chapter_1"},
        [_push("宴会筹备失败，请查看。"), _stop(), {"effect": "sleep", "ms": 3000}],
        None, ["source Push", "source stop lifecycle"],
    )
    b.add("collect_chapter1_fail", _all(collect, b.when(17)), [prep_fail_gap], outcome=False)

    explore_map = b.when(11)
    for name, expr_cond, key in (
        ("collect_find_tanuki", "run_times_2 < 1", "宴会筹备_狸猫"),
        ("collect_find_hungry", "run_times_2 >= 1 and run_times_2 < 2", "宴会筹备_饿鬼"),
        ("collect_find_kappa", "run_times_2 >= 2 and run_times_2 < 3", "宴会筹备_河童"),
    ):
        b.add(
            name,
            _all(collect, explore_map, _expr(expr_cond), {"find": key}),
            [{"click_found": True, "offset": [5, 5, 10, 10], "delay": 2500, "recheck": True}],
        )

    secret_entry = b.actions(19)[0]
    secret_swipe = make_swipe("collect_explore_to_secret", 11, [2000, 2050], 200, (381, 396))
    b.add(
        "collect_explore_to_secret",
        _all(collect, explore_map, _expr("run_times_2 >= 3 and run_times_2 < 6")),
        [{**secret_entry, "recheck": True}, secret_swipe],
    )
    prep_done_gap = b.gap(
        "banquet_prepare_done", (383, 388), {"screen": "explore_map", "run_times_2": ">= 6"},
        [_push("宴会筹备已完成，请查看。"), _stop(), {"effect": "sleep", "ms": 3000}],
        None, ["source Push", "source stop lifecycle"],
    )
    b.add("collect_explore_done", _all(collect, explore_map, _expr("run_times_2 >= 6")),
          [prep_done_gap], outcome=False)
    miss_swipe = make_swipe("collect_explore_scroll", 11, [2000, 2050], 200, (393, 396))
    b.add("collect_explore_scroll", _all(collect, explore_map, _expr("run_times_2 < 3")), [miss_swipe])

    for name, expr_cond, idx in (
        ("collect_tanuki_fight", "run_times_2 < 1", 13),
        ("collect_hungry_fight", "run_times_2 >= 1 and run_times_2 < 2", 14),
        ("collect_kappa_fight", "run_times_2 >= 2 and run_times_2 < 3", 15),
    ):
        acts = b.actions(idx)
        b.add(name, _all(collect, _expr(expr_cond), b.when(idx)),
              [{**acts[0], "recheck": True}, *acts[1:]])

    for idx in (12, 16, 18, 21, 22, 25, 26):
        acts = b.actions(idx)
        b.add(f"collect_screen_{idx}", _all(collect, b.when(idx)),
              [{**acts[0], "recheck": True}, *acts[1:]])

    b.add("collect_switch_to_ongoing", _all(collect, _expr("run_times_2 == 6")),
          [{"set": {collect_var: False, ongoing_var: True}}], internal=True)
    arakawa_acts = b.actions(24)
    b.add("collect_arakawa_fight", _all(collect, b.when(24)),
          [{**arakawa_acts[0], "recheck": True}, *arakawa_acts[1:]])

    arakawa_swipe = make_swipe("collect_arakawa_scroll", 23, [400, 510], 1000, (442, 448))
    b.add("collect_arakawa_scroll", _all(collect, b.when(23)), [arakawa_swipe])
    secret_list_swipe = make_swipe("collect_secret_scroll", 20, [400, 510], 1000, (449, 455))
    b.add("collect_secret_scroll", _all(collect, b.when(20)), [secret_list_swipe])

    # Part 2: liao_banquet_onGoing == True (lines 457-546)
    ongoing = _expr(ongoing_var)
    end_rerun = b.gap(
        "banquet_end_rerun", (458, 464), {"screen": "banquet_end_or_weekly_limit"},
        [_rerun("返回庭院")], True, ["bind 返回庭院 scheme rerun"],
    )
    b.add("banquet_end_1", _all(ongoing, b.when(1)), [end_rerun])
    end10_acts = b.actions(10)
    b.add("banquet_end_10", _all(ongoing, b.when(10)),
          [{**end10_acts[0], "recheck": True}, end_rerun])

    # Admin open & prep loop (lines 465-501)
    admin_on = _all(ongoing, _expr("admin"))
    eating = b.when(0)
    for idx, retest in ((4, None), (9, 1000)):
        acts = b.actions(idx)
        b.add(f"admin_open_{idx}", _all(admin_on, {"not": eating}, b.when(idx)),
              [{**acts[0], "recheck": True}, *acts[1:]], retest_ms=retest)

    b.add("admin_prep_init", _expr("True"), [{"set": {open_cnt: 0, open_step: False}}],
          outcome=None, internal=True)
    prep_screen = b.when(5)
    prep_ready = b.when(6)
    prep_acts = b.actions(6)
    b.add("admin_prep_ready", _all(admin_on, prep_screen, prep_ready),
          [{**prep_acts[0], "recheck": True}, *prep_acts[1:],
           {"inc": open_cnt}, {"set": {open_step: True}}], outcome=None)
    b.add("admin_prep_not_ready", _all(admin_on, prep_screen, {"not": prep_ready}),
          [{"set": {collect_var: True, ongoing_var: False}}])
    open_timeout_gap = b.gap(
        "admin_open_timeout", (492, 497), {"attempts": 3},
        [_push("开启超时,请查看"), _stop(), {"effect": "sleep", "ms": 2000}],
        False, ["source Push", "source stop lifecycle"],
    )
    b.add("admin_prep_timeout", _expr(f"{open_step} and {open_cnt} >= 3"),
          [open_timeout_gap], outcome=False, internal=True)
    open_edge = "unresolved_source_obligation:team605.admin_prep_loop requires team_workflow"
    b.add("admin_prep_retry", _expr(f"{open_step} and {open_cnt} < 3"),
          [{"set": {open_step: False}}, {"wait": 1000}, refresh, {"fail": open_edge}],
          outcome=None, internal=True)
    edges["admin_prep_retry"] = {"target_case": "admin_prep_ready", "gate_prefix": open_edge}

    # Regular ongoing banquet screens (lines 502-545)
    shrine_acts = b.actions(8)
    b.add("enter_guild_shrine", _all(ongoing, b.when(8)),
          [{**shrine_acts[0], "recheck": True}, *shrine_acts[1:]])
    b.add("eating_lift_up", _all(ongoing, eating, {"find": "宴会_举高高"}),
          [{"click_found": True, "offset": [0, 0, 0, 0], "delay": 120, "recheck": True}])
    eat_acts = b.actions(0)
    b.add("eating_open_rotate", _all(ongoing, eating, _expr(f"not {change_var}")),
          [{**eat_acts[0], "recheck": True}, *eat_acts[1:]])
    b.add("eating_wait", _all(ongoing, eating), [])

    rot_on = b.actions(3)
    b.add("rotate_already_on", _all(ongoing, b.when(3)),
          [{**rot_on[0], "recheck": True}, {"set": {change_var: True}}])
    rot_off = b.actions(2)
    b.add("rotate_turn_on", _all(ongoing, b.when(2)), [{**rot_off[0], "recheck": True}])
    put_acts = b.actions(7)
    b.add("banquet_quick_put", _all(ongoing, b.when(7)),
          [{**put_acts[0], "recheck": True}, *put_acts[1:]])

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_native_lowerings"] = lowerings
    proof["source_state_bindings"] = {
        "global.liao_banquet_collect": collect_var,
        "global.liao_banquet_onGoing": ongoing_var,
        "global.banquet_change_flag": change_var,
        "runTimes.2": "run_times_2",
    }
    proof["source_retest"] = {"admin_prep_max_attempts": 3, "admin_prep_sleep_ms": 1000}
