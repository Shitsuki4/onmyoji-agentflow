"""Guarded native realm branches, assttyys (MIT, Copyright (c) 2019 Chaos)."""
import re

from .core_handlers import _case, _push, _rerun, _stop
from .handlers import _count
from .team_handlers import _all, _expr


def build_area_boss(b):
    slot, phase, deadline = "dgCurNum", "area16_phase", "area16_deadline_ms"
    b.model["vars"] = {slot: -1, phase: "", deadline: 0, "super_next_scheme_name": ""}
    counted = [_count(16)]
    refresh = {"handler_control": {"op": "refresh"}}
    always = _expr("True")
    for index in (3, 1, 5):
        b.add(f"screen_{index}", b.when(index), b.actions(index), counts=counted)
    today, close = b.actions(2)
    home = b.when(0)
    b.add("home_required", {"not": home}, outcome=False, internal=True, group="open_today")
    b.add("open_today", home, [today, refresh, {"set": {slot: -1}}],
          retest_ms=2000, outcome=None, counts=counted)

    for index, point in enumerate(b.when(2)["colors"]):
        b.add(f"unplayed_{index}", _all(_expr(f"{slot} == -1"), {"colors": [point]}),
              [{"set": {slot: index}}], outcome=None, counts=counted)
    empty = _expr(f"{slot} == -1")
    rerun = b.gap("today_complete", (158, 163), empty, [_rerun("返回庭院")], "undefined",
                  ["bind the source scheme and forwarded next_scheme"])
    b.add("today_complete", empty, [close, {"set": {"super_next_scheme_name": "next_scheme"}}, rerun],
          outcome=False)

    actions = b.actions(0)
    for index, target in enumerate(actions[2:5]):
        for mode, tab in (("热门", 1), ("收藏", 8)):
            b.add(f"select_{index}_{tab}", _expr(f"{slot} == {index} and hot_star_type == {mode!r}"),
                  [actions[0], actions[tab], target, refresh], outcome=None)

    b.add("begin_extreme_probe", always, [{"set": {phase: repr("extreme"), deadline: "elapsed_ms + 3000"}}],
          outcome=None, internal=True)
    edges = {}

    def compare_loop(name, operator, on_match, next_phase):
        guard = _expr(f"{phase} == {name!r} and elapsed_ms <= {deadline}")
        on_match = [*on_match, {"set": {phase: repr(next_phase), deadline: "elapsed_ms + 3000"}}, refresh]
        b.add(f"match_{name}", _all(guard, b.when(operator)), on_match, outcome=None)
        failure = f"unresolved_source_obligation:team16.{name}_probe requires team_workflow"
        b.add(f"wait_{name}", _expr(f"{phase} == {name!r} and elapsed_ms < {deadline}"),
              [{"wait": 200}, refresh, {"fail": failure}], outcome=None, internal=True)
        edges[f"wait_{name}"] = {"target_case": f"match_{name}", "gate_prefix": failure}

    compare_loop("extreme", 4, b.actions(4), "normal")
    b.add("extreme_timeout", _expr(f"{phase} == 'extreme'"),
          [{"set": {phase: repr("normal"), deadline: "elapsed_ms + 3000"}}, refresh], outcome=None, internal=True)
    compare_loop("normal", 1, [{"wait": 1500}], "challenge")
    b.add("normal_timeout", _expr(f"{phase} == 'normal'"), internal=True)

    popup, handle = b.when(1), {"find": "地鬼_难度把手"}
    swipe = {"swipe": {"from_found": actions[5]["click"], "to": actions[6]["click"]},
             "duration_ms": [100, 300], "delay": 200, "recheck": True}
    base_delay = b.gap("swipe_delay", (193, 193), {"difficulty_handle_found": True},
                       [{"effect": "source regionSwipe with explicit 200ms base delay"}], True,
                       ["preserve explicit swipe delay with this common base"], blocking=False)
    b.add("adjust_difficulty", _all(popup, handle), [base_delay], outcome=None)
    b.add("challenge", popup, [{**actions[7], "recheck": True}, {"wait": 1500}])
    b.add("dialog_changed", always, internal=True)
    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_native_lowerings"] = {"adjust_difficulty": {"native_intent": swipe, "gate_prefix": base_delay["fail"]}}
    proof["source_state_bindings"] = {"global.dgCurNum": slot, "superGlobal.next_scheme_name": "super_next_scheme_name"}
    proof["source_retest"] = {"home_ms": 2000, "difficulty_and_challenge_ms_each": 3000,
                              "minimum_native_poll_ms": 200, "requires_current_challenge_dialog": True}


def build_realm_attack(b):
    attempts, limit = "realm8_attempts", "realm8_limit"
    b.model["vars"] = {attempts: 0, limit: 2}
    refresh = {"handler_control": {"op": "refresh"}}
    personal, encounter = b.when(1), b.when(2)
    overlay = {"any": [personal, encounter]}
    source_rects = b.ops[0]["oper"]
    attack = {"click_found": True, "offset": source_rects[0][3:7], "delay": source_rects[0][7], "recheck": True}
    close = {"click": source_rects[1][3:7], "delay": source_rects[1][7], "recheck": True}

    def find(key, indices):
        terms = [{"find": key, "region": source_rects[index][3:7]} for index in indices]
        return terms[0] if len(terms) == 1 else {"any": terms}

    invitation = b.gap("invite_history", (136, 155), {"invite": True},
        [{"effect": "use the latest history target when 000 settlement limit is disabled"}], True,
        ["bind 000 configuration and original scheme history"])
    b.add("offer_invite", _all(_expr("inv"), {"any": [b.when(3), b.when(4)]}), [invitation])
    b.model["proof"]["history_invite_close"] = source_rects[1][3:7]
    b.add("enter_personal", b.when(5), b.actions(5), counts=[_count(8)])
    b.add("enter_guild", _all(_expr("type == '寮突破'"), b.when(6)), b.actions(6), counts=[_count(8)])
    b.add("overlay_required", {"not": overlay}, outcome=False, internal=True)
    b.add("init", overlay, [{"set": {attempts: 0,
         limit: "2 + (count == '3') + 2 * (count == '4') + 3 * (count == '5')"}}],
          outcome=None, internal=True)
    guild = _expr("type == '寮突破'")
    guild_grey = _all(guild, overlay, find("结界_进攻_灰", (3, 4)))
    cooldown_route = b.gap("cooldown_rerun", (192, 196), {"grey": True, "configured_switch": True},
                           [_rerun({"config": "cdSwitchScheme"})], True,
                           ["bind the actual cooldown target"])
    b.add("cooldown_rerun", _all(guild_grey, _expr("cdSwitchSchemeEnable")), [cooldown_route])
    b.add("cooldown_wait", _all(guild_grey, _expr("cdWaitTime == '30,60'")),
          [close, {"wait_random": {"min_ms": 30000, "max_ms": 60000, "step_ms": 1000}}])
    cooldown_other = b.gap("cooldown_other", (197, 209), {"configured_range": "non-default"},
                          [{"effect": "close overlay then wait a configured inclusive second range"}], True,
                          ["bind source seconds and second-granularity sampling"])
    b.add("cooldown_other", guild_grey, [cooldown_other])

    attempts_guard = _expr(f"{attempts} < {limit}")
    starts = (
        ("guild", _all(guild, overlay), (3, 4)),
        ("encounter", _all(_expr("type == '个人突破'"), encounter), (5,)),
        ("personal", _all(_expr("type == '个人突破'"), personal, {"not": encounter}), (2,)),
    )
    edge = b.gap("attack_phase_binding", (214, 262), {"attempt": "< configured count"},
                 [{"effect": "retest attack icon on a fresh frame"}], None,
                 ["native bounded handler phase edge"], blocking=False)
    edges = {}
    for name, scene, regions in starts:
        case = "attack_" + name
        b.add(case, _all(attempts_guard, scene, find("结界_进攻", regions)),
              [attack, refresh, {"inc": attempts}, edge], outcome=None)
        edges[case] = {"target_case": "attack_guild", "gate_prefix": edge["fail"]}
    b.model["proof"]["source_phase_edges"] = edges
    exhausted = _expr(f"{attempts} >= {limit}")
    b.add("connected", _all(exhausted, {"not": overlay}), internal=True)
    b.add("close_overlay", _all(overlay, exhausted, _expr("afterCountOper == '关闭界面'")),
          [close, close])
    terminal = b.gap("attempt_limit_lifecycle", (219, 260), {"count_reached": True},
                     [{"effect": "source stop, named rerun or history-selected rerun"}], True,
                     ["preserve source legacy config, notification and rerun lifecycle"])
    b.add("attempts_exhausted", exhausted, [terminal], internal=True)
    b.add("attempted", _expr(f"{attempts} > 0"), internal=True)
    b.model["proof"]["limitations_extra"] = [
        "Fresh overlay evidence required before repeating attack or fallback exit.",
        "Source-compatible custom delay jitter and non-default cooldowns require an audited host binding.",
    ]


def build_realm_medals(b):
    for index in (2, 3):
        b.add(f"popup_{index}", b.when(index), b.actions(index))
    page = b.when(0)
    switch = b.gap("nine_exit_four_switch", (98, 151), {"scheme_switch_enabled": True},
                   [{"effect": "set 000/001/002 configuration and reset run_times_2"}], True,
                   ["atomic source config/counter mutation and previous-scheme history"])
    b.add("switch_gate", _all(page, _expr("scheme_switch_enabled")), [switch])
    raw_offset = b.ops[0]["oper"][0]
    adjustment = b.ops[0]["oper"][3]
    offset = [original + delta for original, delta in zip(raw_offset[3:7], adjustment[3:7], strict=True)]
    offset_click = {"click_found": True, "offset": offset, "delay": raw_offset[7], "recheck": True}
    b.model["proof"]["nine_exit_four"] = {
        "first_tile": b.ops[1]["oper"][0][3:7],
        "fallback": _case("retreat_first_slot", b.when(4), b.actions(4)),
    }
    priorities = b.model["params"]["priority"]["choices"]
    for order, priority in enumerate(priorities):
        for position, badge in enumerate(priority.split("->")):
            b.add(f"priority_{order}_{position}", _all(page, _expr(f"priority == {priority!r}"),
                    {"find": f"结界_{badge}勋章"}), [offset_click])


def bind_nine_exit_four(models, scheme_name):
    """Bind 009's transient mutations to the current run's 000/001/002 handlers."""
    handlers = {model["id"]: model for model in models}
    ending, preparation, settlement, medals = [handlers[fid] for fid in (0, 1, 2, 9)]
    proof = medals["proof"]
    plan = proof["nine_exit_four"]
    active, x, y = "realm9_retreat_active", "realm9_medal_x", "realm9_medal_y"
    medals["vars"].update({active: False, x: -1, y: -1})
    fallback = plan["fallback"]
    fallback["when"] = _all(_expr(active), fallback["when"])
    before_retreat = _expr(f"not {active}")
    medals["cases"] = [fallback, *(branch for branch in medals["cases"] if branch["id"] != "switch_gate")]
    left, top, right, bottom = plan["first_tile"]
    for branch in medals["cases"][1:]:
        branch["when"] = _all(before_retreat, branch["when"])
        if not branch["id"].startswith("priority_"):
            continue
        click = branch["do"][0]
        click["point_vars"] = [x, y]
        x1, y1, x2, y2 = click["offset"]
        branch["do"].append({"set": {active: (
            f"scheme_switch_enabled and {x} + ({x1}) > {left} and {y} + ({y1}) > {top} "
            f"and {x} + ({x2}) < {right} and {y} + ({y2}) < {bottom}")}})

    def add_override(condition, parameter):
        if "expr" in condition:
            condition["expr"] = re.sub(rf"\b{parameter}\b", f"({parameter} or {active})", condition["expr"])
        for key in ("all", "any", "not"):
            value = condition.get(key, [])
            for child in value if isinstance(value, list) else [value]:
                add_override(child, parameter)

    for model, parameter in ((preparation, "exitBeforeReady"), (settlement, "rechallenge")):
        for branch in model["cases"]:
            add_override(branch["when"], parameter)

    if 8 in handlers:
        for branch in handlers[8]["cases"]:
            if branch["id"] == "offer_invite":
                branch["when"] = _all(_expr(f"not cfg_0_jspd_enabled_2 and not {active}"), branch["when"])

    terminal_groups = {"inactivity", "total_duration", "count_1", "count_2"}
    for branch in ending["cases"]:
        if branch.get("retest_group") in terminal_groups:
            branch["when"] = _all(before_retreat, branch["when"])
    completed = _expr(
        "run_times_2 >= 4 or (jspd_enabled_1 and run_times_1 > 0 and run_times_1 >= jspd_times_1) or "
        "(jspd_enabled_longtime_nodo and elapsed_ms - core0_current_date_ms > jspd_times_longtime_nodo * 60000) or "
        "(jspd_enabled_zjsj and core0_run_start_ms + jspd_times_zjsj * 60000 < elapsed_ms)")
    ending["cases"].insert(0, _case("realm9_rerun_after_retreat", _all(_expr(active), completed),
        [{"scheme_transition": {"mode": "rerun", "target": scheme_name}}, {"wait": 3000}]))
    proof["unresolved_source_obligations"] = [
        issue for issue in proof["unresolved_source_obligations"] if not issue["id"].endswith(".nine_exit_four_switch")]


def bind_realm_invitation(model, configured_keywords):
    terms = [word.strip() for word in str(configured_keywords or "").replace("，", ",").split(",") if word.strip()]
    proof = model["proof"]
    index, source = next((i, case) for i, case in enumerate(model["cases"]) if case["id"] == "offer_invite")
    banner = _all(_expr("not cfg_0_jspd_enabled_2"), source["when"])
    branches = []
    if terms:
        history = {"scheme_history": terms}
        rect = proof["history_invite_close"]
        branches.append(_case("offer_invite_return_to_history", _all(banner, history), [
            {"click": rect, "delay": 500, "recheck": True},
            {"click": rect, "delay": 500},
            {"scheme_transition": {"mode": "latest_matching", "contains": terms}},
        ], counts=[_count(8)]))
        banner = _all(banner, {"not": history})
    branches.append(_case("offer_invite_no_matching_history", banner, counts=[_count(8)]))
    model["cases"][index:index + 1] = branches
    proof["unresolved_source_obligations"] = [
        issue for issue in proof["unresolved_source_obligations"] if not issue["id"].endswith(".invite_history")]


def build_guild_realm_paging(b):
    counter = "tp_swipe_times"
    b.model["vars"] = {counter: 0}
    page = b.when(0)
    rects = b.ops[0]["oper"]
    swipe = {"swipe": {"from": rects[0][3:7], "to": rects[1][3:7]},
             "duration_ms": [800, 1600], "delay": 200, "recheck": True}
    motion = b.gap("page_swipe", (51, 51), page, [{"effect": "source regionBezierSwipe"}], True,
                   ["native swipe on the original endpoints and duration, with device-specific source curve"],
                   blocking=False)
    b.add("guild_page_required", {"not": page}, outcome=False, internal=True)
    b.add("page", page, [motion, {"inc": counter}, {"handler_control": {"op": "refresh"}}], outcome=None)
    reached = _expr(" or ".join(f"(count == {n!r} and {counter} >= {n})"
                                for n in b.model["params"]["count"]["choices"]))
    reset = {"set": {counter: 0}}
    switch = _all(reached, _expr("afterCountOper == '切换方案'"))
    rerun = b.gap("page_switch", (61, 64), switch, [_rerun({"config": "next_scheme"})],
                  True, ["bind the configured next scheme"])
    click = {"click": rects[2][3:7], "delay": rects[2][7], "recheck": True}
    # A swipe may change the page contents. The exit control still needs the
    # guild screen signature, and an unrecognised exit remains a source gap.
    b.add("page_and_switch", _all(page, switch), [click, reset, rerun])
    unable = b.gap("exit_control_not_recognized", (61, 64), switch,
                   [{"effect": "click source guild exit before rerun"}], True,
                   ["fresh guild realm signature"])
    b.add("switch_without_page", switch, [reset, unable], internal=True)
    stopped = _all(reached, _expr("afterCountOper == '停止脚本'"))
    stop = b.gap("page_stop", (58, 60), stopped, [
        _push("[${schemeHistory names joined by 、}]已停止，请查看。"), _stop()],
        True, ["source Push", "source stop lifecycle"])
    b.add("page_and_stop", stopped, [reset, stop], internal=True)
    b.add("page_done", _expr(f"{counter} > 0"), internal=True)
    proof = b.model["proof"]
    proof["source_native_lowerings"] = {"page": {"gate_prefix": motion["fail"], "native_intent": swipe}}
    proof["source_state_bindings"] = {"global.tp_swipe_times": counter}


def build_guild_realm_food(b):
    home_cnt, home_step = "guild700_home_cnt", "guild700_home_step"
    in_change, change_cnt = "guild700_in_change", "guild700_change_cnt"
    exp_full = "shiHe_jingYan"
    b.model["vars"] = {
        exp_full: False,
        home_cnt: 0,
        home_step: False,
        in_change: False,
        change_cnt: 0,
    }
    counted = [_count(700)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}

    # Lines 189-194: enter guild / dismiss reward popups (no id -> uncounted)
    for index in (0, 1, 2, 4, 5, 6):
        acts = b.actions(index)
        b.add(f"enter_{index}", b.when(index), [{**acts[0], "recheck": True}, *acts[1:]])

    # Lines 195-238: while on guild homepage (op[3].desc), collect AP/Gold or enter realm after 3 misses
    guild_home = b.when(3)
    b.add("home_init", _expr("True"), [{"set": {home_cnt: 0, home_step: False}}],
          outcome=None, internal=True)
    b.add("home_ap", _all(guild_home, {"find": "阴阳寮_奖励体力"}),
          [{"click_found": True, "offset": [0, 0, 0, 0], "delay": 1200, "recheck": True}])
    b.add("home_gold", _all(guild_home, {"find": "阴阳寮_奖励金币"}),
          [{"click_found": True, "offset": [0, 0, 0, 0], "delay": 1200, "recheck": True}])
    b.add("home_miss", guild_home, [{"inc": home_cnt}, {"set": {home_step: True}}, refresh], outcome=None)
    b.add("home_open_realm", _expr(f"{home_step} and {home_cnt} >= 3"), b.actions(3))
    home_edge = "unresolved_source_obligation:team700.home_loop requires team_workflow"
    b.add("home_retry", _expr(f"{home_step} and {home_cnt} < 3"),
          [{"set": {home_step: False}}, {"wait": 500}, {"fail": home_edge}], outcome=None, internal=True)
    edges["home_retry"] = {"target_case": "home_ap", "gate_prefix": home_edge}

    # Lines 239-263: own guild realm -> claim AP box or EXP box (entering change())
    own_realm = b.when(10)
    ap_acts = b.actions(8)
    b.add("realm_ap", _all(own_realm, b.when(8)),
          [{**ap_acts[0], "recheck": True}, *ap_acts[1:]], counts=counted)
    b.add("realm_exp_capped", _all(own_realm, _expr(exp_full)), outcome=False, counts=counted)
    exp_acts = b.actions(9)
    b.add("realm_exp_claim", _all(own_realm, _expr(f"not {exp_full}"), b.when(9)),
          [{**exp_acts[0], "recheck": True}, *exp_acts[1:],
           {"set": {in_change: True, change_cnt: 0}}, refresh],
          outcome=None, counts=counted)
    b.add("realm_idle", _all(own_realm, _expr(f"not {in_change}")), outcome=False, counts=counted)

    # Lines 264-352: change() bounded loop (maxCount = 10)
    change_guard = _expr(in_change)
    change_edge = "unresolved_source_obligation:team700.change_loop requires team_workflow"
    for index in (10, 11, 12):
        acts = b.actions(index)
        name = f"change_enter_{index}"
        b.add(name, _all(change_guard, b.when(index)),
              [{**acts[0], "recheck": True}, *acts[1:], {"set": {change_cnt: 0}},
               refresh, {"fail": change_edge}],
              outcome=None, counts=counted)
        edges[name] = {"target_case": "change_enter_10", "gate_prefix": change_edge}

    fodder_page = b.when(7)
    fodder_acts = b.actions(7)
    empty_slot = {"find": "寄养狗粮_空"}
    n_full_bottom = {"find": "寄养狗粮_满级标识", "region": [910, 473, 1138, 568]}
    full_top = {"find": "寄养狗粮_满级标识", "region": [28, 214, 1254, 349]}
    full_any = {"find": "寄养狗粮_满级标识"}

    b.add("change_fodder_switch_n", _all(change_guard, fodder_page, empty_slot, b.when(13)),
          [{**fodder_acts[0], "recheck": True}, fodder_acts[1]], outcome=None, counts=counted)
    b.add("change_fodder_empty_refresh", _all(change_guard, fodder_page, empty_slot),
          [refresh], outcome=None, internal=True)
    push_n_full = b.gap(
        "all_n_cards_max_level", (296, 302),
        {"screen": "fodder_page", "empty_slot": True, "bottom_n_max_level": True},
        [_push("全部N卡已满级")], None,
        ["source Push"],
    )
    all_acts = b.actions(13)
    b.add("change_fodder_all_n_full", _all(change_guard, fodder_page, empty_slot, n_full_bottom),
          [{**all_acts[0], "recheck": True}, *all_acts[1:], push_n_full], outcome=False)
    b.gap(
        "multi_empty_slot_batch", (283, 307),
        {"screen": "fodder_page", "empty_slot_count": "> 1"},
        [{"effect": "place one N card per refreshed change() iteration instead of unrefreshed batch count"}],
        None, ["findMultiColorEx multi-match count"], blocking=False,
    )
    b.add("change_fodder_add_n", _all(change_guard, fodder_page, empty_slot),
          [{**fodder_acts[2], "recheck": True}, {"set": {change_cnt: 0}}, refresh, {"fail": change_edge}],
          outcome=None)
    edges["change_fodder_add_n"] = {"target_case": "change_enter_10", "gate_prefix": change_edge}

    b.add("change_fodder_clear_full", _all(change_guard, fodder_page, full_top),
          [{"click_found": True, "offset": [0, 0, 20, 20], "delay": 500, "recheck": True},
           {"set": {change_cnt: 0}}, refresh, {"fail": change_edge}],
          outcome=None)
    edges["change_fodder_clear_full"] = {"target_case": "change_enter_10", "gate_prefix": change_edge}

    below_350_gap = b.gap(
        "full_level_below_350_loop", (311, 330),
        {"screen": "fodder_page", "empty_slot": False, "max_level_only_y_ge_350": True},
        [{"effect": "source resets curCnt=0 and continues without clicking when max-level marker has y>=350"}],
        None, ["bounded handling for non-upper max-level markers"],
    )
    b.add("change_fodder_full_below_350", _all(change_guard, fodder_page, full_any),
          [below_350_gap], outcome=False)
    b.add("change_fodder_done", _all(change_guard, fodder_page),
          [{**fodder_acts[3], "recheck": True}, {"set": {in_change: False}}])

    exp_full_acts = b.actions(14)
    b.add("change_exp_full", _all(change_guard, b.when(14)),
          [{**exp_full_acts[0], "recheck": True}, {"set": {exp_full: True, in_change: False}}],
          counts=counted)
    b.add("change_miss_advance", change_guard, [{"inc": change_cnt}], outcome=None, internal=True)
    b.add("change_timeout", _expr(f"{in_change} and {change_cnt} >= 10"),
          [{"set": {in_change: False}}], internal=True)
    b.add("change_retry", _expr(f"{in_change} and {change_cnt} < 10"),
          [{"wait": 300}, refresh, {"fail": change_edge}], outcome=None, internal=True)
    edges["change_retry"] = {"target_case": "change_enter_10", "gate_prefix": change_edge}

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_state_bindings"] = {"global.shiHe_jingYan": exp_full}
    proof["source_retest"] = {
        "guild_home_max_probes": 3,
        "guild_home_sleep_ms": 500,
        "change_max_misses": 10,
        "change_sleep_ms": 300,
    }


def build_realm_card_replace(b):
    in_change, change_cnt = "card701_in_change", "card701_change_cnt"
    b.model["vars"] = {in_change: False, change_cnt: 0}
    counted = [_count(701)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}

    # Lines 259-267: card expiring within minutes -> close and wait 60s
    exp_soon = b.actions(10)
    b.add("expiring_soon", b.when(10),
          [{**exp_soon[0], "recheck": True}, {"wait": 60000}], counts=counted)

    # Lines 268-282: own guild realm -> optional reward claim (+ change()), then open card panel (op[0].oper[1])
    own_realm = b.when(0)
    open_card_action = b.actions(0)[1]
    reward_acts = b.actions(1)
    b.add("realm_reward_claim", _all(own_realm, b.when(1)),
          [{**reward_acts[0], "recheck": True}, *reward_acts[1:],
           {"set": {in_change: True, change_cnt: 0}}, refresh],
          outcome=None, counts=counted)
    b.add("realm_open_card", _all(own_realm, _expr(f"not {in_change}")),
          [{**open_card_action, "recheck": True}], counts=counted)

    # Lines 347-427: change() bounded loop (maxCount = 10), then line 280 open_card_action
    change_guard = _expr(in_change)
    change_edge = "unresolved_source_obligation:team701.change_loop requires team_workflow"
    for index in (12, 13, 14):
        acts = b.actions(index)
        name = f"change_enter_{index}"
        b.add(name, _all(change_guard, b.when(index)),
              [{**acts[0], "recheck": True}, *acts[1:], {"set": {change_cnt: 0}},
               refresh, {"fail": change_edge}],
              outcome=None, counts=counted)
        edges[name] = {"target_case": "change_enter_12", "gate_prefix": change_edge}

    fodder_page = b.when(7)
    fodder_acts = b.actions(7)
    empty_slot = {"find": "寄养狗粮_空"}
    n_full_bottom = {"find": "寄养狗粮_满级标识", "region": [910, 473, 1138, 568]}
    full_top = {"find": "寄养狗粮_满级标识", "region": [28, 214, 1254, 349]}
    full_any = {"find": "寄养狗粮_满级标识"}

    b.add("change_fodder_switch_n", _all(change_guard, fodder_page, empty_slot, b.when(15)),
          [{**fodder_acts[0], "recheck": True}, fodder_acts[1]], outcome=None, counts=counted)
    b.add("change_fodder_empty_refresh", _all(change_guard, fodder_page, empty_slot),
          [refresh], outcome=None, internal=True)
    push_n_full = b.gap(
        "all_n_cards_max_level", (379, 385),
        {"screen": "fodder_page", "empty_slot": True, "bottom_n_max_level": True},
        [_push("全部N卡已满级")], None,
        ["source Push"],
    )
    all_acts = b.actions(15)
    b.add("change_fodder_all_n_full", _all(change_guard, fodder_page, empty_slot, n_full_bottom),
          [{**all_acts[0], "recheck": True}, *all_acts[1:], push_n_full], outcome=False)
    b.gap(
        "multi_empty_slot_batch", (366, 390),
        {"screen": "fodder_page", "empty_slot_count": "> 1"},
        [{"effect": "place one N card per refreshed change() iteration instead of unrefreshed batch count"}],
        None, ["findMultiColorEx multi-match count"], blocking=False,
    )
    b.add("change_fodder_add_n", _all(change_guard, fodder_page, empty_slot),
          [{**fodder_acts[2], "recheck": True}, {"set": {change_cnt: 0}}, refresh, {"fail": change_edge}],
          outcome=None)
    edges["change_fodder_add_n"] = {"target_case": "change_enter_12", "gate_prefix": change_edge}

    b.add("change_fodder_clear_full", _all(change_guard, fodder_page, full_top),
          [{"click_found": True, "offset": [0, 0, 20, 20], "delay": 500, "recheck": True},
           {"set": {change_cnt: 0}}, refresh, {"fail": change_edge}],
          outcome=None)
    edges["change_fodder_clear_full"] = {"target_case": "change_enter_12", "gate_prefix": change_edge}

    below_350_gap = b.gap(
        "full_level_below_350_loop", (394, 413),
        {"screen": "fodder_page", "empty_slot": False, "max_level_only_y_ge_350": True},
        [{"effect": "source resets curCnt=0 and continues without clicking when max-level marker has y>=350"}],
        None, ["bounded handling for non-upper max-level markers"],
    )
    b.add("change_fodder_full_below_350", _all(change_guard, fodder_page, full_any),
          [below_350_gap], outcome=False)
    b.add("change_fodder_done", _all(change_guard, fodder_page),
          [{**fodder_acts[3], "recheck": True}, open_card_action, {"set": {in_change: False}}])
    b.add("change_miss_advance", change_guard, [{"inc": change_cnt}], outcome=None, internal=True)
    b.add("change_timeout", _expr(f"{in_change} and {change_cnt} >= 10"),
          [open_card_action, {"set": {in_change: False}}], internal=True)
    b.add("change_retry", _expr(f"{in_change} and {change_cnt} < 10"),
          [{"wait": 300}, refresh, {"fail": change_edge}], outcome=None, internal=True)
    edges["change_retry"] = {"target_case": "change_enter_12", "gate_prefix": change_edge}

    # Lines 283-345: realm card screen (op[3].desc)
    card_page = b.when(3)
    dropdown = b.when(5)
    drop_acts = b.actions(5)
    for label, idx in (("太鼓", 0), ("斗鱼", 1)):
        b.add(
            f"select_card_{idx}",
            _all(card_page, dropdown, _expr(f"change_enchantment_type == {label!r}")),
            [{**drop_acts[idx], "recheck": True}, drop_acts[2]],
            counts=counted,
        )
    for idx in (2, 4, 6):
        acts = b.actions(idx)
        b.add(f"card_misc_{idx}", _all(card_page, b.when(idx)),
              [{**acts[0], "recheck": True}, *acts[1:]], counts=counted)

    activated = _all(card_page, {"any": [b.when(8), b.when(9)]})
    finish_gap = b.gap(
        "card_activated_finish", (315, 344),
        {"screen": "realm_card_activated"},
        [
            {"effect": "optional_ocr_superGlobal_runTime", "region": b.ops[11]["oper"][0][3:7]},
            _push("更换完毕，请查看。"),
            _rerun({"config": "next_scheme"}),
            {"effect": "sleep", "ms": 3000},
        ],
        True,
        ["optional OCR runTime persistence", "source Push", "source rerun lifecycle"],
    )
    close_card = b.actions(3)[0]
    b.add("card_activated_finish", activated, [{**close_card, "recheck": True}, finish_gap], counts=counted)
    b.add("card_page_idle", card_page, outcome=False, counts=counted)

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_retest"] = {"change_max_misses": 10, "change_sleep_ms": 300, "expiring_sleep_ms": 60000}


def build_foster_shikigami(b):
    idx_var = "jy_enchantment_index"
    n_cnt, n_matched = "foster702_n_cnt", "foster702_n_matched"
    b.model["vars"] = {idx_var: 0, n_cnt: 0, n_matched: False}
    counted = [_count(702)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = {}
    lowerings = {}

    # Lines 224-239: in foster fodder screen (op[13]) -> tap empty foster slot (op[1]), else wait 10s + back
    in_foster = b.when(13)
    slot_acts = b.actions(1)
    b.add("foster_open_slot", _all(in_foster, b.when(1)),
          [{**slot_acts[0], "recheck": True}], counts=counted)
    back_from_foster = b.actions(12)[0]
    b.add("foster_wait_and_back", in_foster,
          [{"wait": 10000}, back_from_foster], counts=counted)

    # Lines 240-246: own realm -> enter fodder screen (op[0])
    enter_acts = b.actions(0)
    b.add("enter_foster_fodder", b.when(0), [{**enter_acts[0], "recheck": True}], counts=counted)

    # Lines 247-272: when jy_enchantment_index == 0, refresh friends/cross list
    idx_zero = _expr(f"{idx_var} == 0")
    list_ops = b.ops[2]["oper"]
    refresh_swipe = {
        "swipe": {"from": list_ops[0][3:7], "to": list_ops[1][3:7]},
        "duration_ms": [700, 800],
        "delay": 3000,
        "recheck": True,
    }
    refresh_gate = b.gap(
        "list_refresh_swipe", (248, 255), {"screen": "foster_list_top", "index": 0},
        [{"effect": "source regionSwipe to bottom of foster list"}], True,
        ["native swipe on original endpoints and duration"], blocking=False,
    )
    b.add("list_top_refresh", _all(idx_zero, b.when(3)), [refresh_gate], counts=counted)
    lowerings["list_top_refresh"] = {"gate_prefix": refresh_gate["fail"], "native_intent": refresh_swipe}

    tab_cross = b.actions(4)
    b.add("friends_bottom_to_cross", _all(idx_zero, b.when(4)),
          [{**tab_cross[0], "recheck": True}], counts=counted)
    tab_friends = b.actions(5)
    b.add("cross_bottom_to_friends", _all(idx_zero, b.when(5)),
          [{**tab_friends[0], "recheck": True}, {"set": {idx_var: 1}}, {"wait": 1000}], counts=counted)

    # Lines 273-282: already fostered (op[12]) -> exit clicks + rerun next_scheme
    done_rerun = b.gap(
        "foster_complete_rerun", (273, 282), {"screen": "already_fostered"},
        [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 3000}], True,
        ["source rerun lifecycle"],
    )
    done_acts = b.actions(12)
    b.add("foster_done_exit", b.when(12),
          [{**done_acts[0], "recheck": True}, *done_acts[1:], done_rerun], counts=counted)

    # Lines 283-312: bounded place N-card loop (op[8], op[9], op[10], maxCount=3)
    b.add("place_n_init", _expr("True"), [{"set": {n_cnt: 0, n_matched: False}}],
          outcome=None, internal=True)
    for idx in (8, 9, 10):
        acts = b.actions(idx)
        b.add(f"place_n_{idx}", _all(_expr(f"not {n_matched}"), b.when(idx)),
              [{**acts[0], "recheck": True}, *acts[1:], {"inc": n_cnt}, {"set": {n_matched: True}}, refresh],
              outcome=None, counts=counted)
    b.add("place_n_done_exit", _all(_expr(n_matched), b.when(12)),
          [{**done_acts[0], "recheck": True}, *done_acts[1:], done_rerun], counts=counted)
    n_max_push = b.gap(
        "foster_n_cards_max_level", (302, 311), {"attempts": 3, "screen": "n_cards_max_level"},
        [_push("寄养的N卡已满级")], True, ["source Push"],
    )
    n_max_acts = b.actions(11)
    b.add("place_n_all_max", _all(_expr(f"{n_matched} and {n_cnt} >= 3"), b.when(11)),
          [{**n_max_acts[0], "recheck": True}, *n_max_acts[1:], n_max_push], counts=counted)
    n_edge = "unresolved_source_obligation:team702.place_n_loop requires team_workflow"
    b.add("place_n_retry", _expr(f"{n_matched} and {n_cnt} < 3"),
          [{"set": {n_matched: False}}, {"fail": n_edge}], outcome=None, internal=True)
    edges["place_n_retry"] = {"target_case": "place_n_8", "gate_prefix": n_edge}
    b.add("place_n_bounded_exit", _expr(n_matched), internal=True)

    # Lines 313-379: filter realm cards by priority on foster list (op[2])
    foster_list = b.when(2)
    close_list = b.actions(2)[4]
    enter_realm_btn = b.actions(2)[5]
    not_found_gap = b.gap(
        "foster_card_not_found", (321, 330), {"screen": "foster_list", "priority_exhausted": True},
        [
            {"effect": "set_superGlobal_runTime", "seconds": 300},
            _push("找不到指定结界卡，5分钟后再试"),
            _rerun({"config": "next_scheme"}),
            {"effect": "sleep", "ms": 3000},
        ],
        True,
        ["superGlobal.runTime persistence", "source Push", "source rerun lifecycle"],
    )
    priorities = b.model["params"]["priority"]["choices"]
    for order, prio_str in enumerate(priorities):
        items = prio_str.split("->")
        b.add(
            f"priority_exhausted_{order}",
            _all(
                foster_list,
                _expr(f"priority == {prio_str!r} and ({idx_var} <= 0 or {idx_var} > {len(items)})"),
            ),
            [{**close_list, "recheck": True}, close_list, not_found_gap],
        )
        for pos, item in enumerate(items, start=1):
            key = f"结界卡_{item}星"
            b.add(
                f"priority_{order}_{pos}",
                _all(foster_list, _expr(f"priority == {prio_str!r} and {idx_var} == {pos}"), {"find": key}),
                [
                    {"click_found": True, "offset": [-20, -20, 0, 0], "delay": 1200, "recheck": True},
                    enter_realm_btn,
                ],
                counts=counted,
            )

    card_empty = {"find": "结界卡_无"}
    b.add("empty_friends_to_cross", _all(foster_list, card_empty, b.when(6)),
          [{**tab_cross[0], "recheck": True}], counts=counted)
    b.add("empty_cross_to_friends", _all(foster_list, card_empty, b.when(7)),
          [{**tab_friends[0], "recheck": True}, {"inc": idx_var}], counts=counted)

    scroll_swipe = {
        "swipe": {"from": list_ops[2][3:7], "to": list_ops[3][3:7]},
        "duration_ms": [350, 360],
        "delay": 1000,
        "recheck": True,
    }
    scroll_gate = b.gap(
        "list_scroll_swipe", (374, 377), {"screen": "foster_list", "card_empty": False},
        [{"effect": "source regionSwipe down foster list"}], True,
        ["native swipe on original endpoints and duration"], blocking=False,
    )
    b.add("list_scroll_down", _all(foster_list, {"not": card_empty}), [scroll_gate])
    lowerings["list_scroll_down"] = {"gate_prefix": scroll_gate["fail"], "native_intent": scroll_swipe}
    b.add("foster_list_idle", foster_list, outcome=False)

    proof = b.model["proof"]
    proof["source_phase_edges"] = edges
    proof["source_native_lowerings"] = lowerings
    proof["source_state_bindings"] = {"global.jy_enchantment_index": idx_var}
    proof["source_retest"] = {"place_n_max_attempts": 3, "wait_not_ready_ms": 10000}
