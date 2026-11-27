"""Static translation of Func690, assttyys (MIT, Copyright (c) 2019 Chaos)."""
from .core_handlers import CURRENT_DATE_VAR, _rerun
from .handlers import _count
from .team_handlers import _all, _expr


def build_launch_handler(b):
    email = "launch690_email_switch_active"
    b.model["vars"] = {"launch690_email_initialized": False, email: False,
                       "open_only_once": False, "back": True, "checked_yard_count": 0,
                       "launch690_yard_hits": 0, "launch690_yard_matched": False,
                       "app_is_open_flag": True, "launch690_activity_ms": 0,
                       "game_area": "", CURRENT_DATE_VAR: 0, "core0_run_start_ms": 0}
    proof = b.model["proof"]
    proof["source_state_bindings"] = {f"global.{key}": key for key in (
        "open_only_once", "back", "checked_yard_count", "app_is_open_flag", "game_area")}
    proof["source_state_bindings"]["global.timestamp"] = "launch690_activity_ms"
    # The config and source global have the same name. Keep the global in a
    # separate namespace since config expressions are rewritten at composition.
    proof["source_state_bindings"]["global.email_switch_enabled"] = email
    refresh = {"handler_control": {"op": "refresh"}}
    count = [_count(690)]
    changed = {"set": {"game_area": "'findMultiColor_皮肤广告关闭按钮'"}}

    def add_operator(name, index, *, condition=None, actions=None, counts=count, **options):
        guard = b.when(index)
        if condition is not None:
            guard = _all(condition, guard)
        return b.add(name, guard, b.actions(index) if actions is None else actions, counts=counts, **options)

    def name_match(parameter, rect):
        left, top, right, bottom = rect
        return {"ocr_full": {"keyword_var": parameter, "region": [left, top, right - left, bottom - top],
                             "selection": "unique_contains", "evidence": "complete_keyword"}}

    b.add("disable_restart", _expr("not close_game_new"), [{"set": {"app_is_open_flag": False}}],
          outcome=None, internal=True)
    b.add("init_email", _expr("not launch690_email_initialized"), [{"set": {
        email: "email_switch_enabled", "launch690_email_initialized": True}}], outcome=None, internal=True)
    active_email = _expr(email)
    account_profile = _expr("next_email and next_email != '@163.com'")
    account_open = b.when(19)
    switch_screens = {"any": [b.when(index) for index in (9, 12, 15, 19)]}
    missing_email = b.gap("email_profile", (522, 575), {"email_switch_enabled": True},
                          [{"effect": "switch to an explicitly configured account"}], None,
                          ["verified account profile with a distinct visible email"])
    b.add("missing_email", _all(active_email, switch_screens, {"not": account_profile}),
          [missing_email], outcome=False, internal=True)
    for index in (9, 12):
        add_operator(f"account_menu_{index}", index, condition=active_email)
    chosen, dropdown = b.actions(15)
    add_operator("account_dropdown", 15, condition=active_email, actions=[dropdown])
    b.add("account_list_count", _all(active_email, account_open), counts=[_count(609)],
          outcome=None, internal=True)
    start, end, email_crop = b.actions(19)
    active_list = _all(active_email, account_open)
    add_operator("account_list_bottom_29", 29, condition=active_list)
    b.add("account_email_match", _all(active_list, name_match("next_email", email_crop["click"])),
          [{"click_found": True, "offset": [10, 0, 50, 65], "delay": 1000, "recheck": True},
           chosen, {"set": {email: False}}])
    add_operator("account_list_bottom_30", 30, condition=active_list)
    scroll_gate = b.gap("account_list_scroll", (563, 573), {"screen": "account list"},
                        [{"effect": "scroll for configured email at source speed"}], True,
                        ["native swipe timing and per-account visual calibration"], blocking=False)
    b.add("account_list_scroll", _all(active_email, account_open), [scroll_gate])
    proof["source_native_lowerings"] = {"account_list_scroll": {
        "gate_prefix": scroll_gate["fail"], "native_intent": {
            "swipe": {"from": start["click"], "to": end["click"]}, "delay": 1000, "duration_ms": [1500, 1700]}}}

    for index in (22, 33):
        for mode, choice in (("not apple", 0), ("apple", 1)):
            add_operator(f"platform_{index}_{choice}", index, condition=_expr(mode),
                         actions=[b.actions(index)[choice]], counts=[_count(609)])
    b.add("already_open", _expr("open_only_once"), outcome=False, internal=True)
    add_operator("expand_yard_menu", 7)
    hits, matched = "launch690_yard_hits", "launch690_yard_matched"
    b.add("yard_init", _expr("True"), [{"set": {hits: 0, matched: False}}], outcome=None, internal=True)
    for index in (8, 13, 16):
        add_operator(f"yard_probe_{index}", index, condition=_expr(f"not {matched}"),
                     actions=[*b.actions(index), {"set": {matched: True}}, {"inc": hits}, refresh],
                     outcome=None)
    b.add("yard_done_once", _expr(f"{matched} and {hits} >= 6 and not scheme_switch_enabled"),
          [{"set": {"open_only_once": True, "back": False, "checked_yard_count": 0}}], internal=True)
    rerun = b.gap("yard_rerun", (618, 628), {"yards_seen": 6}, [_rerun({"config": "next_scheme"})], None,
                  ["bind the configured successor at the scheme lifecycle boundary"])
    b.add("yard_done_rerun", _expr(f"{matched} and {hits} >= 6 and scheme_switch_enabled"),
          [{"set": {"checked_yard_count": 0}}, rerun], internal=True)
    edge = b.gap("yard_phase_binding", (610, 631), {"yards_seen": "< 6"},
                 [{"effect": "repeat six ordered cached-yard checks"}], None,
                 ["native bounded handler phase edge"], blocking=False)
    b.add("repeat_yard_probe", _expr(matched), [{"wait": 500}, {"set": {matched: False}}, edge],
          outcome=None, internal=True)
    proof["source_phase_edges"] = {"repeat_yard_probe": {"target_case": "yard_probe_8", "gate_prefix": edge["fail"]}}

    for index in (23, 24, 25):
        add_operator(f"intro_{index}", index, actions=[*b.actions(index), {"set": {"app_is_open_flag": False}}],
                     counts=[])
    add_operator("battle_clock", 28, actions=[{"set": {"launch690_activity_ms": "elapsed_ms"}}],
                 counts=[], outcome=None, internal=True)
    stale = "app_is_open_flag and " + " and ".join(
        f"elapsed_ms - {clock} > 30000" for clock in ("launch690_activity_ms", "handler_last_ms",
                                                    "handler_last_handled_ms", CURRENT_DATE_VAR, "core0_run_start_ms"))
    restart = b.gap("restart_related_apps", (648, 656), {"stagnant_ms": "> 30000"},
                    [{"effect": "stop source related apps"}, {"effect": "sleep", "ms": 2000},
                     {"effect": "launch source related apps"}], True,
                    ["source package list, device launch/stop settings and guarded app lifecycle"])
    b.add("stagnant_restart", _expr(stale), [restart], internal=True)

    start_login, area_crop = b.actions(0)
    correct_area = name_match("area", area_crop["click"])
    b.add("area_matches", _all(b.when(0), _expr("area and not game_area"), correct_area), [start_login], counts=count)
    area_text = {"text": "", "pattern": ".+", "region": correct_area["ocr_full"]["region"]}
    b.add("area_differs", _all(b.when(0), _expr("area and not game_area"), area_text),
          [b.actions(4)[0]], counts=count)
    b.add("area_ocr_unreadable", _all(b.when(0), _expr("area and not game_area")),
          counts=count, outcome=False, internal=True)
    add_operator("login", 0, actions=[changed, start_login])
    add_operator("anniversary_login", 35, actions=[changed, *b.actions(35)])
    for index in (1, 2, 3):
        add_operator(f"account_slot_{index}", 18, condition=_expr(f"account_index == {index}"),
                     actions=[b.actions(18)[index], start_login])
    choice_roi = b.actions(4)[1]["click"]
    b.add("area_name", _all(b.when(4), _expr("area"), name_match("area", choice_roi)),
          [{"click_found": True, "offset": [5, 0, 40, 20], "delay": 1000, "recheck": True},
           start_login, changed], counts=count)
    b.add("area_name_absent", b.when(4), counts=count, outcome=None, internal=True)

    for index in (1, 2, 3, 6, 9, 10, 11, 14, 17, 20, 21, 26, 27, 15, 31, 32, 34):
        actions = [chosen] if index == 15 else b.actions(index)
        add_operator(f"login_popup_{index}", index, actions=actions)
    b.add("close_skin_promotion", _all(_expr("game_area"), {"find": "皮肤广告关闭按钮"}),
          [{"click_found": True, "offset": [-10, -10, 0, 0], "delay": 1000}])
    proof["account_recognition"] = {"direct_index": "integer 1–3, 0 disables",
                                    "email_and_role_ocr": "unambiguous substring in the pinned crop"}
