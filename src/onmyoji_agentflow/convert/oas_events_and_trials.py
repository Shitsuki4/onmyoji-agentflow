"""Pinned OAS FindJade, Quiz, OtherWorldTwilight, MetaDemon, and HeroTest workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_answer_bank import ANSWER_BANK, PINS as ANSWER_PINS, bind_answer_bank
from .oas_battle import bind_courtyard_buffs, compile_general_battle
from .oas_room_invite import (
    PINS as ROOM_INVITE_PINS,
    bind_leader_invite_and_fire,
    bind_member_accept_and_wait,
    bind_room_create,
    bind_room_exit,
)
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


FIND_JADE_ENTRY = "tasks/FindJade/script_task.py"
FIND_JADE_PINS = {
    FIND_JADE_ENTRY: "94c58c3b5236843d0f87f9d41128488681698d7b173914cb71fb0e5bfbc19739",
    "tasks/FindJade/config.py": "961bbface26ce45c0646941207d932f2a8e8ec2cc438fa12462a33048f9a6efa",
    "tasks/FindJade/assets.py": "c9cd837439f0700444ddf375968d650e0e63cecb16dfcbefcdafd3c18356fb5e",
    "tasks/FindJade/WantedQuestsEx.py": "a832ff977e8620360eb4aaca7c37da9776958803833d9d26200ba3a6c66292c1",
    "tasks/Component/SwitchAccount/switch_account.py":
        "4ae24b460cbaece3255be8f5699b4864f87c9b379a66300a43793f7392c027f3",
    "tasks/Component/SwitchAccount/exit_game.py":
        "6c15d610004878318574732886430679916655254229b7c37726b5b2b365cf36",
    "tasks/Component/SwitchAccount/login_account.py":
        "076d4daa4d287e4d6e4f04256a424d73e3dc86d8e427be92869555ac42ec4f95",
    "tasks/Component/SwitchAccount/assets.py":
        "7d0a1f5c567278c4412476f67927b6b44102e5747c59a74eb62e2128cb193323",
}

QUIZ_ENTRY = "tasks/Quiz/script_task.py"
QUIZ_PINS = {
    QUIZ_ENTRY: "d0a5b08fe1dc3572289631896b13f42848224e3c01a1ea563c4e35f6f6a06942",
    "tasks/Quiz/config.py": "fd5ebece3e24828349e1fdfd2722ccae28b4c77bdacfe2bd0123997403dfce7a",
    "tasks/Quiz/assets.py": "d6c168eb6dfc0c39b0962aca3450f273d309df09072e86c42718d727bc366e04",
    "tasks/Quiz/debug.py": "53cd8930212025dba4e9c40669707fd341285aa3f3f3fe895681bd0d2f039b99",
}

OWT_ENTRY = "tasks/OtherWorldTwilight/script_task.py"
OWT_PINS = {
    OWT_ENTRY: "b06a9d69e5b679992a908989054dcecf6b085ece601c07d9ffb966f0f5bee152",
    "tasks/OtherWorldTwilight/config.py": "0ff445713de6c3ce8d4f7c9df51295d917c412aebd4ee7ca9b18d6e86c68ee6d",
    "tasks/OtherWorldTwilight/assets.py": "46b5b2014f12ec42a33e3902131d7ca3e705c7d3e3920375aef0c635282a80e2",
    "tasks/OtherWorldTwilight/page.py": "57145d0b0377e1427a09f3abb6bf9af5cbc6d6cae2f84ae35ddeb1770fb25e05",
}

META_DEMON_ENTRY = "tasks/MetaDemon/script_task.py"
META_DEMON_PINS = {
    META_DEMON_ENTRY: "66490061244fb4189e045360d8eb4c911eca4e648f8508986d14c1fb54659a80",
    "tasks/MetaDemon/config.py": "d43cc47823a73dee8047838bae0ea0eb2c32af7eda54f20b12125417a6421b76",
    "tasks/MetaDemon/assets.py": "55f02ee50fd415733a98e8298f8db1e098fd1e841e73b0192a786045f752012b",
}

HERO_TEST_ENTRY = "tasks/HeroTest/script_task.py"
HERO_TEST_PINS = {
    HERO_TEST_ENTRY: "a0578b461e1ee1374141a81aa7a35c097d0302d6df928b758e3ef3af2dbab03a",
    "tasks/HeroTest/config.py": "b02501ce71dbc84a3673fbbe8e23681a8bd0583c3dc0548cd058866e0dc50902",
    "tasks/HeroTest/assets.py": "c6083f4ddb488a864f48a80f5bef441e3cb221ed5cd682baf9e1169463e6fcb1",
}


def _verify_pins(source: Path, pins: dict[str, str], label: str) -> None:
    for rel, expected in pins.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"{label} source fingerprint mismatch: {rel}")


def _click_from(docs: dict, name: str, ns: str, delay: int = 1000, recheck: bool = True) -> dict:
    spec = docs[ns][name]
    if spec["type"] in ("click", "long_click"):
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    return {"click": target, "delay": delay, "recheck": recheck}


def _wire_nav(raw: dict, prefix: str, phase_fn, advance_fn, next_phase: str) -> None:
    arrived = next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_returned")
    arrived["when"]["all"].append(phase_fn("navigate"))
    arrived["do"] = [advance_fn(next_phase)]
    next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_drive")["when"] = phase_fn("navigate")


def _wire_battle(raw: dict, body: dict, contract: dict, phase_fn, advance_fn,
                 attempts_var: str, wins_var: str, return_phase: str) -> dict:
    outputs = contract["outputs"]
    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    reset[outputs["current_count"]] = attempts_var
    for step in body["states"]:
        step["when"] = {"all": [phase_fn("in_battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance_fn(return_phase, **{
                attempts_var: outputs["current_count"],
                wins_var: f"{wins_var} + {outputs['win']}",
            })]
        raw["states"].append(step)
    return reset


def compile_find_jade_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS FindJade (multi-account jade wanted quest dispatcher) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, FIND_JADE_PINS, "FindJade")
    nav = compile_navigation_family(
        source, resources, prefix="fj_nav", destination="page_main",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_find_jade_natively_staged", title="寻勾(多号悬赏)", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update(
        fj_has_pending_account={"default": False},
        fj_confirm_switch_account={"default": False},
        fj_target_account={"default": ""},
        fj_target_character={"default": ""},
        fj_platform={"default": "android", "choices": ["android", "apple"]},
        fj_wake_wanted_quests={"default": True},
        fj_wq_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        fj_limit_seconds={"default": 0, "min": 0, "max": 7200},
        fj_next_window_delay_s={"default": 18000, "min": 60, "max": 86400},
    )
    raw["vars"].update(
        fj_phase="entry",
        fj_target_delay_s=18000,
        fj_observed_ms=0,
        fj_account_switched=False,
        fj_account_scrolls=0,
        fj_char_scrolls=0,
        fj_wq_woken=False,
        fj_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/Component_SwitchAccount.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("Component_SwitchAccount", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"fj_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"fj_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"fj_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Component_SwitchAccount"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="Component_SwitchAccount", delay=1500):
        return _click_from(docs, name, ns, delay)

    _wire_nav(raw, "fj", phase, advance, "done")
    state("switch_account_confirm_gate", "entry",
          [expr("fj_has_pending_account and not fj_confirm_switch_account")],
          {"fail": "寻勾多账号切换需显式开启 fj_confirm_switch_account 确认参数"})
    state("switch_account_missing_target", "entry",
          [expr("fj_has_pending_account and fj_confirm_switch_account and (fj_target_account == '' or fj_target_character == '')")],
          {"fail": "寻勾切换小号需要配置 fj_target_account 与 fj_target_character"})
    state("switch_account_begin", "entry",
          [expr("fj_has_pending_account and fj_confirm_switch_account")],
          advance("exit_current"))
    state("schedule_next_window", "entry", [expr("not fj_has_pending_account")],
          advance("done", fj_target_delay_s="fj_next_window_delay_s", fj_observed_ms="elapsed_ms",
                  fj_exit_reason="'no_pending_account'"))

    # Exit current character to login form (ExitGame.exitGame)
    for ph in ("exit_current", "select_account", "login_submit", "select_character", "enter_game"):
        state(f"{ph}_time_limit", ph,
              [expr("fj_limit_seconds > 0 and elapsed_ms >= fj_limit_seconds * 1000")],
              advance("done", fj_target_delay_s="fj_next_window_delay_s",
                      fj_observed_ms="elapsed_ms", fj_exit_reason="'time_limit'"))
    state("exit_at_login", "exit_current",
          [{"any": [asset("I_CHECK_LOGIN_FORM"), asset("I_SA_NETEASE_GAME_LOGO")]}],
          advance("select_account", fj_account_scrolls=0))
    state("exit_tap_switch_account", "exit_current", [asset("I_SA_SWITCH_ACCOUNT_BTN")],
          click("I_SA_SWITCH_ACCOUNT_BTN", delay=2000))
    raw["states"][-1].update(
        sensitive="重启游戏",
        desc="寻勾多账号切换将退出当前登录角色并跳转账号登录界面。",
    )
    state("exit_tap_user_center", "exit_current", [asset("I_SA_USER_CENTER")],
          click("I_SA_USER_CENTER", delay=2500))
    state("exit_tap_profile", "exit_current", [asset("I_CHECK_MAIN", "GameUi")],
          click("C_SA_EG_PROFILE_PHOTO", delay=2500))

    # Select target account in login dropdown (LoginAccount.selectAccount)
    acc_list_roi = docs["Component_SwitchAccount"]["O_SA_ACCOUNT_ACCOUNT_LIST"]["roi"]
    acc_sel_roi = docs["Component_SwitchAccount"]["O_SA_ACCOUNT_ACCOUNT_SELECTED"]["roi"]
    state("account_already_selected", "select_account", [
        asset("I_SA_ACCOUNT_DROP_DOWN_CLOSED"),
        {"ocr_full": {
            "region": acc_sel_roi,
            "keyword_var": "fj_target_account",
            "selection": "unique_equals",
            "evidence": "complete_keyword",
        }},
    ], advance("login_submit"))
    state("account_open_dropdown", "select_account", [asset("I_SA_ACCOUNT_DROP_DOWN_CLOSED")],
          click("I_SA_ACCOUNT_DROP_DOWN_CLOSED", delay=1500))
    state("account_pick_target", "select_account", [
        {"not": asset("I_SA_ACCOUNT_DROP_DOWN_CLOSED")},
        {"ocr_full": {
            "region": acc_list_roi,
            "keyword_var": "fj_target_account",
            "selection": "unique_equals",
            "evidence": "complete_keyword",
        }},
    ], {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}, advance("login_submit"))
    state("account_not_found", "select_account", [
        {"any": [asset("I_SA_ACCOUNT_DROP_DOWN_ADD_ACCOUNT"), expr("fj_account_scrolls >= 6")]},
    ], {"fail": "寻勾未在账号下拉列表中找到目标账号"})
    state("account_scroll_list", "select_account", [
        asset("I_SA_NETEASE_GAME_LOGO"),
        {"not": asset("I_SA_ACCOUNT_DROP_DOWN_CLOSED")},
    ], {"swipe": "Component_SwitchAccount::S_SA_ACCOUNT_LIST_UP", "delay": 1500, "recheck": True},
       {"inc": "fj_account_scrolls"})
    state("account_open_user_center", "select_account", [asset("I_CHECK_LOGIN_FORM")],
          click("C_SA_LOGIN_FORM_USER_CENTER", delay=1500))

    # Submit login and choose Android/Apple platform
    state("login_pick_android", "login_submit", [expr("fj_platform == 'android'"), asset("I_SA_LOGIN_FORM_ANDROID")],
          click("I_SA_LOGIN_FORM_ANDROID", delay=1000))
    state("login_pick_apple", "login_submit", [expr("fj_platform == 'apple'"), asset("I_SA_LOGIN_FORM_APPLE")],
          click("I_SA_LOGIN_FORM_APPLE", delay=1000))
    state("login_tap_btn", "login_submit", [asset("I_SA_ACCOUNT_LOGIN_BTN")],
          click("I_SA_ACCOUNT_LOGIN_BTN", delay=1500))
    state("login_form_ready", "login_submit", [asset("I_CHECK_LOGIN_FORM"), {"not": asset("I_SA_ACCOUNT_LOGIN_BTN")}],
          advance("select_character", fj_char_scrolls=0))

    # Select target character & enter game (LoginAccount.switch_character)
    char_roi = docs["Component_SwitchAccount"]["O_SA_SELECT_SVR_CHARACTER_LIST"]["roi"]
    state("char_already_in_main", "select_character", [asset("I_CHECK_MAIN", "GameUi")],
          advance("wake_wanted", fj_account_switched=True))
    state("char_expand_list", "select_character",
          [asset("I_SA_CHECK_SELECT_SVR_1"), {"not": asset("I_SA_CHECK_SELECT_SVR_2")}],
          click("C_SA_SELECT_SVR_CHARACTER_LIST", delay=1500))
    state("char_pick_target", "select_character", [
        asset("I_SA_CHECK_SELECT_SVR_2"),
        {"ocr_full": {
            "region": char_roi,
            "keyword_var": "fj_target_character",
            "selection": "unique_equals",
            "evidence": "complete_keyword",
        }},
    ], {"click_found": True, "offset": [0, -30, 0, -30], "delay": 2000, "recheck": True}, advance("enter_game"))
    state("char_not_found", "select_character",
          [asset("I_SA_CHECK_SELECT_SVR_2"), expr("fj_char_scrolls >= 8")],
          {"fail": "寻勾未在已有角色列表中找到目标角色"})
    state("char_scroll_list", "select_character", [asset("I_SA_CHECK_SELECT_SVR_2")],
          {"swipe": "Component_SwitchAccount::S_SA_ACCOUNT_LIST_UP", "delay": 1500, "recheck": True},
          {"inc": "fj_char_scrolls"})
    state("char_open_svr_select", "select_character", [asset("I_CHECK_LOGIN_FORM")],
          click("C_SA_LOGIN_FORM_SWITCH_SVR_BTN", delay=1500))

    state("enter_game_arrived", "enter_game", [asset("I_CHECK_MAIN", "GameUi")],
          advance("wake_wanted", fj_account_switched=True))
    state("enter_game_tap", "enter_game", [asset("I_CHECK_LOGIN_FORM")],
          click("C_SA_LOGIN_FORM_ENTER_GAME_BTN", delay=2000))

    # Wake WantedQuests for cooperation invite on switched account, then schedule next 05:05/18:05 window
    state("wake_wanted_quests", "wake_wanted", [expr("fj_wake_wanted_quests and not fj_wq_woken")],
          {"oas_wake": {"task": "WantedQuests", "failure_seconds_param": "fj_wq_failure_seconds"}},
          {"set": {"fj_wq_woken": True}})
    state("wake_done", "wake_wanted", [],
          advance("done", fj_target_delay_s="fj_next_window_delay_s", fj_observed_ms="elapsed_ms",
                  fj_exit_reason="'switched_and_woken'"))

    state("finish", "done", [], {
        "stop": {
            "reason": "寻勾多号流程已按 05:05/18:05 窗口完成调度",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "FindJade",
                "delay_seconds_var": "fj_target_delay_s",
                "observed_ms_var": "fj_observed_ms",
            },
            "evidence": {"scope": "find_jade_switch_account_and_window_schedule"},
        }
    })
    raw["oas_find_jade_contract"] = {
        "source": FIND_JADE_ENTRY,
        "source_pins": {**FIND_JADE_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "find_jade_switch_account_and_wanted_quests_ex",
            "blocking": True,
            "requirement": "Bind SwitchAccount character/server switching, login history persistence, and WantedQuestsEx VIP invite",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_quiz_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Quiz (event trivia quiz) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, QUIZ_PINS, "Quiz")
    nav = compile_navigation_family(
        source, resources, prefix="qz_nav", destination="page_main",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_quiz_natively_staged", title="活动答题", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1200
    bind_schedule(source, raw)
    bind_answer_bank(raw, source)
    raw["params"].update(
        qz_max_rounds={"default": 1, "min": 1, "max": 30},
        qz_answers_per_round={"default": 150, "min": 0, "max": 150},
        qz_default_answer={"default": 1, "min": 1, "max": 4},
        qz_enable_answer_bank={"default": True},
        qz_limit_seconds={"default": 0, "min": 0, "max": 3600},
        qz_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        qz_phase="entry", qz_rounds=0, qz_start_clicks=0, qz_answers_clicked=0, qz_countdown=0,
        qz_question="", qz_last_question="", qz_bank_answer=0, qz_chosen=0, qz_sample=0,
        qz_round_answers=0, qz_selected=0, qz_pending_at=-1, qz_rewards_dismissed=0,
        qz_target_delay_s=0, qz_observed_ms=0, qz_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/Quiz.yaml",
        "upstream/oas/ActivityShikigami.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("Quiz", "ActivityShikigami", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"qz_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"qz_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"qz_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Quiz"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="Quiz", delay=1000):
        return _click_from(docs, name, ns, delay)

    _wire_nav(raw, "qz", phase, advance, "enter")
    state("entry_begin", "entry", [], advance("navigate"))

    state("enter_time_limit", "enter",
          [expr("qz_limit_seconds > 0 and elapsed_ms >= qz_limit_seconds * 1000")],
          advance("exit", qz_exit_reason="'time_limit'"))
    state("enter_ready", "enter", [asset("I_START")], advance("lobby"))
    state("enter_click_entry", "enter", [asset("I_ENTRY")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("enter_click_shi", "enter", [asset("I_SHI", "ActivityShikigami")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})

    state("lobby_time_limit", "lobby",
          [expr("qz_limit_seconds > 0 and elapsed_ms >= qz_limit_seconds * 1000")],
          advance("exit", qz_exit_reason="'time_limit'"))
    state("lobby_rounds_done", "lobby", [expr("qz_rounds >= qz_max_rounds")],
          advance("exit", qz_exit_reason="'rounds_done'"))
    state("lobby_no_ticket", "lobby", [expr("qz_start_clicks >= 4")],
          advance("exit", qz_exit_reason="'no_ticket'"))
    current = [f"qz_option_{i}" for i in range(1, 5)]
    previous = [f"qz_last_option_{i}" for i in range(1, 5)]
    raw["vars"].update({name: "" for name in current + previous})
    state("lobby_entered", "lobby", [asset("I_MESSAGE")], advance("answering", qz_start_clicks=0,
          qz_round_answers=0, qz_last_question="''", **{name: "''" for name in previous}))
    state("lobby_start", "lobby", [asset("I_START")],
          click("I_START", delay=1500), {"inc": "qz_start_clicks"})

    for where in ("answering", "select", "confirm"):
        state(f"{where}_reward_dismiss", where, [{"res": "GlobalGame::I_UI_REWARD", "threshold": 0.6}],
              click("C_UI_REWARD", "GlobalGame", delay=400), {"inc": "qz_rewards_dismissed"})
        state(f"{where}_fail_quit", where, [asset("I_FAIL_QUIT")],
              {"click_found": True, "use_match_size": True, "delay": 1200, "recheck": True},
              {"inc": "qz_rounds"}, advance("lobby"))
        state(f"{where}_victory", where, [asset("I_SHARE"), asset("I_UI_BACK_RED", "GlobalGame")],
              click("I_UI_BACK_RED", "GlobalGame", delay=1200), {"inc": "qz_rounds"}, advance("lobby"))
    clock = {"ocr": "Quiz::O_COUNTDOWN", "var": "qz_countdown"}
    window = {**clock, "test": "(qz_countdown >= 2 and qz_countdown <= 5) or qz_countdown > 100"}
    question_read = {"quiz_answer": {"bank": ANSWER_BANK, "question": "Quiz::O_QUESTION",
        "options": [f"Quiz::O_ANSWER{i}" for i in range(1, 5)], "option_vars": current,
        "question_var": "qz_question", "answer_var": "qz_bank_answer"}}
    changes = " + ".join(f"({a} != {b})" for a, b in zip(current, previous))
    newer = expr(f"{changes} >= 3")
    same = expr(" and ".join(["qz_question == qz_last_question",
                             *(f"{a} == {b}" for a, b in zip(current, previous))]))
    screen = asset("I_MESSAGE")
    bank_mode = [screen, expr("qz_enable_answer_bank"), window, question_read]
    state("bank_unknown", "answering", [*bank_mode, newer, expr("qz_bank_answer == 0")],
          {"fail": "题库缺少唯一匹配，未选答"})
    state("bank_answer", "answering", [*bank_mode, newer],
          advance("select", qz_last_question="qz_question", qz_chosen="qz_bank_answer",
                  qz_pending_at="elapsed_ms", qz_selected=0, **dict(zip(previous, current))))
    state("solo_finish_answer", "answering", [*bank_mode, {"not": newer}, expr("qz_countdown > 100"),
          asset("I_ALONE_ENSURE")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("bank_limit", "select", [expr("elapsed_ms - qz_pending_at >= 5000")],
          {"fail": "题目或选项变化，未发送选答"})
    state("confirm_limit", "confirm", [expr("elapsed_ms - qz_pending_at >= 7000")],
          {"fail": "未核对待确认题目"})
    state("limited_correct_answers", "select", [*bank_mode, same, expr(
        "qz_selected == 0 and qz_answers_per_round < 150 and qz_round_answers >= qz_answers_per_round")],
        {"sample_int": {"var": "qz_sample", "min": 1, "max": 3}},
        {"set": {"qz_chosen": "qz_sample + (qz_sample >= qz_bank_answer)", "qz_selected": 1}})
    for idx in (1, 2, 3, 4):
        x, y, w, h = docs["Quiz"][f"O_ANSWER{idx}"]["roi"]
        state(f"bank_pick_{idx}", "select", [*bank_mode, same, expr(f"qz_chosen == {idx}")],
              {"click": [x, y, x + w, y + h], "delay": 500, "recheck": True}, advance("confirm"))
        state(f"bank_confirm_{idx}", "confirm", [screen, question_read, same, expr(f"qz_chosen == {idx}")],
              click(f"C_ANSWER_ENSURE_{idx}", delay=1000), {"inc": "qz_answers_clicked"},
              {"inc": "qz_round_answers"}, advance("answering"))
        state(f"ans_pick_{idx}", "answering", [
            asset("I_MESSAGE"),
            expr(f"not qz_enable_answer_bank and qz_default_answer == {idx}"),
            {**clock, "test": "qz_countdown >= 2 and qz_countdown <= 5"},
        ], click(f"C_ANSWER_ENSURE_{idx}", delay=1400), {"inc": "qz_answers_clicked"})

    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("qz_next_delay_s > 0")],
          advance("stop_target", qz_target_delay_s="qz_next_delay_s", qz_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "活动答题已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "Quiz",
                "delay_seconds_var": "qz_target_delay_s",
                "observed_ms_var": "qz_observed_ms",
            },
            "evidence": {"scope": "quiz_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "活动答题已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Quiz",
            "evidence": {"scope": "quiz_bounded_rounds"},
        }
    })
    state("exit_back", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", delay=1500))

    raw["oas_quiz_contract"] = {
        "source": QUIZ_ENTRY,
        "source_pins": {**QUIZ_PINS, **ANSWER_PINS, **SCHEDULE_PINS},
        "answer_bank": {"resource": ANSWER_BANK, "rows": len(raw["inline_resources"][ANSWER_BANK]["rows"]),
                        "unknown_and_ties": "Requires a unique answer; does not default to option 1."},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "quiz_answer_bank_live_and_notifier",
            "blocking": True,
            "requirement": "Verify the OCR deadline, selected option, single-player confirmation and outcome on live rounds. "
                           "Unknown questions require a locally reviewed reporting and notification policy.",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_other_world_twilight_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS OtherWorldTwilight (彼世逢魔) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, OWT_PINS, "OtherWorldTwilight")
    nav = compile_navigation_family(
        source, resources, prefix="owt_nav", destination="page_owt",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="owt_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_other_world_twilight_natively_staged", title="彼世逢魔", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        owt_user_status={"default": "alone", "choices": ["alone", "leader", "member"]},
        owt_limit_count={"default": 10, "min": 0, "max": 999},
        owt_limit_seconds={"default": 1800, "min": 0, "max": 7200},
        owt_member_wait_seconds={"default": 120, "min": 0, "max": 3540},
        owt_unknown_page_timeout_s={"default": 10, "min": 1, "max": 60},
        owt_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        owt_phase="entry", owt_battles=0, owt_wins=0, owt_main_arrived=0,
        owt_member_since=-1, owt_unknown_since=-1, owt_battle_recoveries=0, owt_page_recoveries=0,
        owt_target_delay_s=0, owt_observed_ms=0, owt_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/OtherWorldTwilight.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("OtherWorldTwilight", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"owt_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"owt_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"owt_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="OtherWorldTwilight"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="OtherWorldTwilight", delay=1000):
        return _click_from(docs, name, ns, delay)

    bind_task_presets(raw, source, resources, prefix="owt", resume="route_entry", category="owt")
    state("route_member", "route_entry", [expr("owt_user_status == 'member'")], advance("member_accept"))
    state("route_nav", "route_entry", [expr("owt_user_status != 'member'")], advance("navigate"))
    _wire_nav(raw, "owt", phase, advance, "lock_check")

    lock_ok = {"any": [
        {"all": [expr("lock_team_enable"), asset("I_OWT_LOCK")]},
        {"all": [expr("not lock_team_enable"), asset("I_OWT_UNLOCK")]},
    ]}
    state("lock_want_locked", "lock_check", [expr("lock_team_enable"), asset("I_OWT_UNLOCK")],
          click("I_OWT_UNLOCK", delay=1000))
    state("lock_want_unlocked", "lock_check", [expr("not lock_team_enable"), asset("I_OWT_LOCK")],
          click("I_OWT_LOCK", delay=1000))
    state("lock_ready_alone", "lock_check", [expr("owt_user_status == 'alone'"), lock_ok], advance("fire_loop"))
    state("lock_ready_leader", "lock_check", [expr("owt_user_status == 'leader'"), lock_ok], advance("leader_open_team"))

    # Leader & Member shared GeneralRoom / GeneralInvite integration
    state("leader_team_opened", "leader_open_team", [asset("I_CREATE_ROOM", "Component_GeneralRoom")],
          advance("room_create"))
    state("leader_click_team", "leader_open_team", [asset("I_OWT_TEAM")], click("I_OWT_TEAM", delay=1000))
    bind_room_create(raw, source, resources, prefix="owt", phase_var="owt_phase",
                     entry_phase="room_create", ready_phase="leader_invite", fail_phase="room_create_fail")
    state("room_create_failed", "room_create_fail", [], {"fail": "彼世逢魔创建组队房间失败"})
    timed_out = expr("elapsed_ms >= owt_limit_seconds * 1000")
    state("leader_time_stop", "leader_invite", [timed_out], advance("room_exit", owt_exit_reason="'time_limit'"))
    state("leader_count_stop", "leader_invite", [expr("owt_battles >= owt_limit_count")],
          advance("room_exit", owt_exit_reason="'count_limit'"))
    bind_leader_invite_and_fire(raw, source, resources, prefix="owt", phase_var="owt_phase",
                                entry_phase="leader_invite", battle_phase="team_battle_init",
                                exit_phase="room_exit", room_type="normal_3")
    state("member_begin_timer", "member_accept", [expr("owt_member_since < 0")],
          advance("member_accept", owt_member_since="elapsed_ms"))
    state("member_count_stop", "member_accept", [expr("owt_battles >= owt_limit_count")],
          advance("room_exit", owt_exit_reason="'count_limit'"))
    for where in ("member_accept", "owt_mem_wait"):
        state(where + "_time_stop", where, [timed_out], advance("room_exit", owt_exit_reason="'time_limit'"))
        state(where + "_wait_timeout", where,
              [expr("owt_member_since >= 0 and elapsed_ms - owt_member_since >= owt_member_wait_seconds * 1000")],
              advance("room_exit", owt_exit_reason="'member_wait_timeout'"))
    bind_member_accept_and_wait(raw, source, resources, prefix="owt", phase_var="owt_phase",
                                entry_phase="member_accept", battle_phase="team_battle_init", exit_phase="room_exit")
    state("member_idle", "member_accept", [], {"wait": 250})
    state("member_in_room_idle", "owt_mem_wait", [], {"wait": 250})
    bind_room_exit(raw, source, resources, prefix="owt", phase_var="owt_phase",
                   entry_phase="room_exit", done_phase="exit")

    reset = _wire_battle(raw, body, contract, phase, advance, "owt_battles", "owt_wins", "after_battle")
    state("team_battle_start", "team_battle_init", [], {"set": reset}, advance("in_battle"))
    state("after_battle_alone", "after_battle", [expr("owt_user_status == 'alone'")], advance("fire_loop"))
    state("after_battle_leader", "after_battle", [expr("owt_user_status == 'leader'")], advance("leader_invite"))
    state("after_battle_member", "after_battle", [expr("owt_user_status == 'member'")],
          advance("member_accept", owt_member_since="elapsed_ms"))

    state("fire_time_stop", "fire_loop", [timed_out], advance("exit", owt_exit_reason="'time_limit'"))
    state("fire_limit_reached", "fire_loop", [expr("owt_battles >= owt_limit_count")],
          advance("exit", owt_exit_reason="'count_limit'"))
    owt_battle_seen = {"any": [
        asset("I_PREPARE_HIGHLIGHT", "Component_GeneralBattle"),
        asset("I_BATTLE_INFO", "Component_GeneralBattle"),
        asset("I_WIN", "Component_GeneralBattle"),
        asset("I_FALSE", "Component_GeneralBattle"),
    ]}
    state("fire_takeover_battle", "fire_loop", [owt_battle_seen],
          {"set": reset},
          advance("in_battle", owt_unknown_since=-1, owt_battle_recoveries="owt_battle_recoveries + 1"))
    state("fire_click", "fire_loop", [asset("I_OWT_FIRE")],
          click("I_OWT_FIRE", delay=1200), {"set": reset}, advance("in_battle", owt_unknown_since=-1))
    state("fire_unknown_recover", "fire_loop", [
        {"not": asset("I_OWT_FIRE")},
        expr("owt_unknown_since >= 0 and elapsed_ms - owt_unknown_since >= owt_unknown_page_timeout_s * 1000"),
    ], advance("navigate", owt_unknown_since=-1, owt_page_recoveries="owt_page_recoveries + 1"))
    state("fire_unknown_start", "fire_loop", [{"not": asset("I_OWT_FIRE")}, expr("owt_unknown_since < 0")],
          {"set": {"owt_unknown_since": "elapsed_ms"}}, {"wait": 500})
    state("fire_unknown_wait", "fire_loop", [{"not": asset("I_OWT_FIRE")}], {"wait": 500})

    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("owt_next_delay_s > 0")],
          advance("stop_target", owt_target_delay_s="owt_next_delay_s", owt_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "彼世逢魔已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "OtherWorldTwilight",
                "delay_seconds_var": "owt_target_delay_s",
                "observed_ms_var": "owt_observed_ms",
            },
            "evidence": {"scope": "other_world_twilight_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "彼世逢魔已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "OtherWorldTwilight",
            "evidence": {"scope": "other_world_twilight_native_loop"},
        }
    })
    state("exit_nav", "exit", [],
          {"navigate": {"destination": "page_main", "done_var": "owt_main_arrived"}})

    raw["oas_other_world_twilight_contract"] = {
        "source": OWT_ENTRY,
        "source_pins": {**OWT_PINS, **SOUL_PINS, **SCHEDULE_PINS, **ROOM_INVITE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "other_world_twilight_time_limit_and_live",
            "blocking": True,
            "requirement": "Bind wall-clock limit_time_v, multi-tab friend scroll, and live OtherWorldTwilight frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_meta_demon_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS MetaDemon (超鬼王) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, META_DEMON_PINS, "MetaDemon")
    nav = compile_navigation_family(
        source, resources, prefix="md_nav", destination="page_main",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="md_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_meta_demon_natively_staged", title="超鬼王", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        md_limit_count={"default": 10, "min": 0, "max": 500},
        md_crafting_card={"default": False},
        md_confirm_craft={"default": False},
        md_max_crafts={"default": 3, "min": 1, "max": 20},
        md_auto_shared_boss={"default": False},
        md_confirm_tea={"default": False},
        md_use_strategy={"default": False},
        md_default_group={"default": 0, "min": 0, "max": 7},
        md_default_team={"default": 0, "min": 0, "max": 5},
        md_star56_high_hp_group={"default": 0, "min": 0, "max": 7},
        md_star56_high_hp_team={"default": 0, "min": 0, "max": 5},
        md_star56_low_hp_group={"default": 0, "min": 0, "max": 7},
        md_star56_low_hp_team={"default": 0, "min": 0, "max": 5},
        md_boss_idle_timeout_s={"default": 50, "min": 0, "max": 600},
        md_summon_exhaustion_cap={"default": 90, "min": 0, "max": 100},
        md_limit_seconds={"default": 0, "min": 0, "max": 7200},
        md_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        md_phase="entry", md_battles=0, md_wins=0, md_exhaustion_rem=100, md_exhaustion_cur=-1,
        md_crafted=0, md_craft_started=0, md_is_star56=False, md_hp_low=False,
        md_boss_name="", md_boss_idle_since=-1, md_self_boss_opens=0, md_first_easy_battle=True,
        md_target_delay_s=0, md_observed_ms=0, md_exit_reason="",
        md_preset_group=0, md_preset_team=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/MetaDemon.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("MetaDemon", "GlobalGame")}
    craft_card_roi = docs["MetaDemon"]["O_CRAFTING_CARD_1"]["roi"]
    shared_boss_roi = docs["MetaDemon"]["O_BOSS_EMPTY_1"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"md_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"md_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"md_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="MetaDemon", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, ns="MetaDemon", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("craft_confirm_gate", "entry", [expr("md_crafting_card and not md_confirm_craft")],
          {"fail": "超鬼王合成门票会消耗低星卡，需显式开启 md_confirm_craft"})
    bind_task_presets(raw, source, resources, prefix="md", resume="navigate", category="md")
    _wire_nav(raw, "md", phase, advance, "enter")

    state("enter_ready_craft", "enter", [
        expr("md_crafting_card and md_confirm_craft"),
        {"any": [asset("I_FIND_DEMON"), asset("I_BATTLE_DEMON")]},
    ], advance("craft_open", md_craft_started="elapsed_ms"))
    state("enter_ready_find", "enter", [asset("I_FIND_DEMON")], advance("loop"))
    state("enter_ready_battle", "enter", [asset("I_BATTLE_DEMON")], advance("loop"))
    state("enter_reward_popup", "enter", [asset("I_UI_REWARD", "GlobalGame", threshold=0.6)],
          click("C_UI_REWARD", "GlobalGame", delay=500))
    state("enter_back_red", "enter", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", delay=1200))
    state("enter_ensure", "enter", [asset("I_ENTER_ENSURE")], click("I_ENTER_ENSURE", delay=1000))
    state("enter_step2", "enter", [asset("I_ENTER2")], click("I_ENTER2", delay=1000))
    state("enter_right", "enter", [asset("I_RIGHT_ENTER")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})

    # Guarded 1-star -> 2-star card crafting (mirrors MetaDemon.crafting)
    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    state("craft_open_ready", "craft_open", [asset("I_CRAFTING_START")],
          advance("craft_loop", md_craft_started="elapsed_ms"))
    state("craft_open_tap", "craft_open", [asset("I_CRAFTING_1")],
          click("I_CRAFTING_1", delay=1500))
    state("craft_open_skip", "craft_open", [expr("elapsed_ms - md_craft_started >= 6000")],
          advance("loop"))

    state("craft_reward_popup", "craft_loop", [reward],
          click("C_UI_REWARD", "GlobalGame", delay=500), {"set": {"md_craft_started": "elapsed_ms"}})
    state("craft_limit_reached", "craft_loop", [expr("md_crafted >= md_max_crafts")],
          advance("craft_close"))
    state("craft_timeout", "craft_loop", [expr("elapsed_ms - md_craft_started >= 3000")],
          advance("craft_close"))
    state("craft_fill_slot", "craft_loop", [
        {"ocr_single": {"region": craft_card_roi, "equals": "一星梦告铃鼓"}},
        {"any": [asset("I_CRAFTING_EMPTY"), asset("I_CRAFTING_EMPTY_NEW")]},
        asset("I_CRAFTING_CARD_STAR_1"),
    ], click("I_CRAFTING_CARD_STAR_1", delay=1000), {"set": {"md_craft_started": "elapsed_ms"}})
    state("craft_start_commit", "craft_loop", [
        {"ocr_single": {"region": craft_card_roi, "equals": "一星梦告铃鼓"}},
        {"not": asset("I_CRAFTING_EMPTY")}, {"not": asset("I_CRAFTING_EMPTY_NEW")},
        asset("I_CRAFTING_START"),
    ], click("I_CRAFTING_START", delay=2000), {"inc": "md_crafted"}, {"set": {"md_craft_started": "elapsed_ms"}})
    raw["states"][-1].update(
        sensitive="分解",
        desc="将一星梦告铃鼓合成为二星超鬼王门票，将消耗背包一星卡片。",
    )
    state("craft_no_card_exit", "craft_loop", [], advance("craft_close"))

    state("craft_close_red", "craft_close", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", delay=1000))
    state("craft_close_done", "craft_close", [{"not": asset("I_UI_BACK_RED", "GlobalGame")}],
          advance("loop"))

    # MetaDemon custom settlement hooks + GeneralBattle fallback
    state("in_battle_md_win", "in_battle", [asset("I_MD_WIN")],
          click("I_MD_WIN", delay=800),
          advance("loop", md_battles="md_battles + 1", md_wins="md_wins + 1", md_boss_idle_since="elapsed_ms"))
    state("in_battle_md_fail", "in_battle", [asset("I_MD_BATTLE_FAILURE")],
          click("I_MD_BATTLE_FAILURE", delay=800),
          advance("loop", md_battles="md_battles + 1", md_boss_idle_since="elapsed_ms"))
    reset = _wire_battle(raw, body, contract, phase, advance, "md_battles", "md_wins", "loop")
    state("loop_init_idle", "loop", [expr("md_boss_idle_since < 0")],
          {"set": {"md_boss_idle_since": "elapsed_ms"}})
    state("loop_time_limit", "loop",
          [expr("md_limit_seconds > 0 and elapsed_ms >= md_limit_seconds * 1000")],
          advance("exit", md_exit_reason="'time_limit'"))
    state("loop_limit_reached", "loop", [expr("md_battles >= md_limit_count")],
          advance("exit", md_exit_reason="'limit_count_reached'"))
    state("loop_exhausted_tea_unbound", "loop", [
        expr("md_confirm_tea"),
        {"ocr": "MetaDemon::O_MD_EXHAUSTION", "mode": "counter_remaining", "var": "md_exhaustion_rem", "test": "md_exhaustion_rem <= 0"},
    ], {"fail": "超鬼王疲劳度饮茶恢复(上游 buy_tea 未实现，缺少资产)仍需来源绑定"})
    state("loop_exhausted_stop", "loop", [
        expr("not md_confirm_tea"),
        {"ocr": "MetaDemon::O_MD_EXHAUSTION", "mode": "counter_remaining", "var": "md_exhaustion_rem", "test": "md_exhaustion_rem <= 0"},
    ], advance("exit", md_exit_reason="'exhaustion_full'"))
    state("loop_idle_timeout", "loop", [
        expr("md_boss_idle_timeout_s > 0 and md_boss_idle_since >= 0 and "
             "elapsed_ms - md_boss_idle_since >= md_boss_idle_timeout_s * 1000"),
    ], advance("exit", md_exit_reason="'boss_idle_timeout'"))
    state("loop_open_self_boss", "loop", [
        {"not": asset("I_BOSS_EMPTY")},
        {"not": asset("I_BATTLE_DEMON")},
        {"any": [asset("I_BOSS_CONVENE"), asset("I_BOOS_PUBLIC")]},
    ], click("I_BOSS_EMPTY", delay=1500), {"inc": "md_self_boss_opens"})
    state("loop_pick_shared_1", "loop", [
        expr("md_auto_shared_boss"), asset("I_BOSS_EMPTY"), {"not": asset("I_BOSS_EMPTY_1")},
        {"ocr_single": {"region": shared_boss_roi, "equals": "剩余时间"}},
    ], click("I_BOSS_EMPTY_1", delay=1500), {"set": {"md_is_star56": True}})
    state("loop_pick_shared_2", "loop", [
        expr("md_auto_shared_boss"), asset("I_BOSS_EMPTY"), asset("I_BOSS_EMPTY_1"), {"not": asset("I_BOSS_EMPTY_2")},
    ], click("I_BOSS_EMPTY_2", delay=1500), {"set": {"md_is_star56": True}})
    # Star56 full-name OCR & HP-threshold preset routing (when md_use_strategy=True)
    state("loop_battle_star56_low_hp_strategy", "loop", [
        expr("md_use_strategy"),
        asset("I_BATTLE_DEMON"), {"not": asset("I_STAR56_POS_1")},
        asset("I_STAR56_HP_THRESHOLD_F"), {"not": asset("I_STAR56_HP_THRESHOLD_T")},
        {"ocr": "MetaDemon::O_MD_FULL_NAME", "mode": "text_sequence", "var": "md_boss_name"},
    ], {"log": "超鬼王高星低血量策略切队"}, click("I_BATTLE_DEMON", delay=1200), {"set": reset},
       advance("in_battle", md_is_star56=True, md_hp_low=True, md_first_easy_battle=True,
               md_preset_group="md_star56_low_hp_group", md_preset_team="md_star56_low_hp_team",
               md_boss_idle_since="elapsed_ms"))
    state("loop_battle_star56_high_hp_strategy", "loop", [
        expr("md_use_strategy"),
        asset("I_BATTLE_DEMON"), {"not": asset("I_STAR56_POS_1")},
        {"ocr": "MetaDemon::O_MD_FULL_NAME", "mode": "text_sequence", "var": "md_boss_name"},
    ], {"log": "超鬼王高星高血量策略切队"}, click("I_BATTLE_DEMON", delay=1200), {"set": reset},
       advance("in_battle", md_is_star56=True, md_hp_low=False, md_first_easy_battle=True,
               md_preset_group="md_star56_high_hp_group", md_preset_team="md_star56_high_hp_team",
               md_boss_idle_since="elapsed_ms"))
    state("loop_battle_star56_low_hp", "loop", [
        asset("I_BATTLE_DEMON"), {"not": asset("I_STAR56_POS_1")},
        asset("I_STAR56_HP_THRESHOLD_F"), {"not": asset("I_STAR56_HP_THRESHOLD_T")},
    ], click("I_BATTLE_DEMON", delay=1200), {"set": reset},
       advance("in_battle", md_is_star56=True, md_hp_low=True, md_first_easy_battle=True,
               md_boss_idle_since="elapsed_ms"))
    state("loop_battle_star56", "loop", [
        asset("I_BATTLE_DEMON"), {"not": asset("I_STAR56_POS_1")},
    ], click("I_BATTLE_DEMON", delay=1200), {"set": reset},
       advance("in_battle", md_is_star56=True, md_hp_low=False, md_first_easy_battle=True,
               md_boss_idle_since="elapsed_ms"))
    state("loop_battle_easy_default", "loop", [
        expr("md_use_strategy and md_first_easy_battle"),
        asset("I_BATTLE_DEMON"),
    ], click("I_BATTLE_DEMON", delay=1200), {"set": reset},
       advance("in_battle", md_is_star56=False, md_hp_low=False, md_first_easy_battle=False,
               md_preset_group="md_default_group", md_preset_team="md_default_team",
               md_boss_idle_since="elapsed_ms"))
    state("loop_battle", "loop", [asset("I_BATTLE_DEMON")],
          click("I_BATTLE_DEMON", delay=1200), {"set": reset},
          advance("in_battle", md_is_star56=False, md_hp_low=False, md_boss_idle_since="elapsed_ms"))
    state("loop_summon_exhaustion_cap", "loop", [
        asset("I_FIND_DEMON"),
        {"ocr": "MetaDemon::O_MD_EXHAUSTION", "mode": "counter_current", "var": "md_exhaustion_cur"},
        expr("md_exhaustion_cur >= md_summon_exhaustion_cap"),
    ], advance("exit", md_exit_reason="'summon_exhaustion_cap'"))
    state("loop_find", "loop", [asset("I_FIND_DEMON")],
          click("I_FIND_DEMON", delay=1500), {"set": {"md_boss_idle_since": "elapsed_ms"}})
    state("loop_wait_idle", "loop", [], {"wait": 250})

    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("md_next_delay_s > 0")],
          advance("stop_target", md_target_delay_s="md_next_delay_s", md_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "超鬼王已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "MetaDemon",
                "delay_seconds_var": "md_target_delay_s",
                "observed_ms_var": "md_observed_ms",
            },
            "evidence": {"scope": "meta_demon_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "超鬼王已完成或疲劳度到达安全上限，已返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "MetaDemon",
            "evidence": {"scope": "meta_demon_bounded_loop"},
        }
    })
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", delay=1400))
    state("exit_back", "exit", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", delay=1200))

    raw["oas_meta_demon_contract"] = {
        "source": META_DEMON_ENTRY,
        "source_pins": {**META_DEMON_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "meta_demon_star56_strategy_and_crafting",
            "blocking": True,
            "requirement": "Bind Star56 name OCR/HP threshold preset switching, friend boss list, tea recovery, and card crafting",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_hero_test_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS HeroTest (英杰试炼) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, HERO_TEST_PINS, "HeroTest")
    nav = compile_navigation_family(
        source, resources, prefix="ht_nav", destination="page_hero_test",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="ht_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_hero_test_natively_staged", title="英杰试炼", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        ht_hero={"default": "hero1", "choices": ["hero1", "hero2"]},
        ht_mode={"default": "exp", "choices": ["exp", "skill"]},
        ht_limit_count={"default": 10, "min": 0, "max": 500},
        ht_limit_seconds={"default": 0, "min": 0, "max": 7200},
        ht_exp_buff={"default": False},
        ht_buff_exp_50={"default": True},
        ht_buff_exp_100={"default": False},
        ht_check_ticket_ocr={"default": False},
        ht_check_ap_ocr={"default": False},
        ht_ap_min={"default": 12, "min": 0, "max": 999},
        ht_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        ht_phase="entry", ht_battles=0, ht_wins=0, ht_exit_reason="",
        ht_art_war_card=-1, ht_art_war_card_plus=-1, ht_remain_ap=-1,
        ht_bless_picked=False, ht_bless_count=0,
        ht_target_delay_s=0, ht_observed_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/HeroTest.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("HeroTest", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"ht_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"ht_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"ht_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="HeroTest"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="HeroTest", delay=1000):
        return _click_from(docs, name, ns, delay)

    bind_task_presets(raw, source, resources, prefix="ht", resume="buff_before", category="ht")
    ht_buff_ops = [("exp_50", "ht_buff_exp_50"), ("exp_100", "ht_buff_exp_100")]
    ht_buff_expr = "(ht_exp_buff and (ht_buff_exp_50 or ht_buff_exp_100))"
    buff_calls = [
        bind_courtyard_buffs(
            raw, source, resources, prefix=f"ht_buff_{leg}", phase_var="ht_phase",
            entry_phase=f"buff_{leg}", resume=resume, operations=ht_buff_ops,
            enable_param=ht_buff_expr, opening=opening,
        )
        for leg, opening, resume in (("before", True, "navigate"), ("after", False, "finished"))
    ]
    _wire_nav(raw, "ht", phase, advance, "select_mode")

    state("switch_to_hero1_btn", "select_mode", [expr("ht_hero == 'hero1'"), asset("I_CHECK_HERO2")],
          click("C_SWITCH_HERO_BTN", delay=1000))
    state("switch_to_hero1_pick", "select_mode", [expr("ht_hero == 'hero1'"), asset("I_SWITCH_HERO1")],
          click("I_SWITCH_HERO1", delay=1000))
    state("switch_to_hero2_btn", "select_mode", [expr("ht_hero == 'hero2'"), asset("I_CHECK_HERO1")],
          click("C_SWITCH_HERO_BTN", delay=1000))
    state("switch_to_hero2_pick", "select_mode", [expr("ht_hero == 'hero2'"), asset("I_SWITCH_HERO2")],
          click("I_SWITCH_HERO2", delay=1000))

    state("enter_hero1_exp", "select_mode", [expr("ht_hero == 'hero1' and ht_mode == 'exp'"), asset("I_GBB")],
          click("I_GBB", delay=1000))
    state("enter_hero1_skill", "select_mode", [expr("ht_hero == 'hero1' and ht_mode == 'skill'"), asset("I_BCMJ")],
          click("I_BCMJ", delay=1000))
    state("enter_hero2_exp", "select_mode", [expr("ht_hero == 'hero2' and ht_mode == 'exp'"), asset("I_ENTER_CCSL")],
          click("I_ENTER_CCSL", delay=1000))
    state("enter_hero2_skill", "select_mode", [expr("ht_hero == 'hero2' and ht_mode == 'skill'"), asset("I_ENTER_MXMJ")],
          click("I_ENTER_MXMJ", delay=1000))

    for check_img in ("I_CHECK_HERO1_EXP", "I_CHECK_HERO1_SKILL", "I_CHECK_HERO2_EXP", "I_CHECK_HERO2_SKILL"):
        state(f"ready_{check_img.lower()}", "select_mode", [asset(check_img)], advance("fight_loop"))

    reset = _wire_battle(raw, body, contract, phase, advance, "ht_battles", "ht_wins", "fight_loop")
    # Hero1 & Hero2 priority skill/blessing selection (mirrors hero1_skill_wait / hero2_skill_wait)
    hero1_skills = [
        "I_BCMJ_SKILL_ADD1", "I_BCMJ_SKILL_ADD2", "I_BCMJ_BLESS",
        "I_BCMJ_PROPERTY_ADD_CRITICAL", "I_BCMJ__DEFALUT_ATTRIBUTE",
    ]
    hero2_skills = [
        "I_HERO2_SKILL1", "I_HERO2_SKILL2", "I_HERO2_SKILL3",
        "I_HERO2_SKILL4", "I_HERO2_SKILL5", "I_HERO2_SKILL6",
    ]
    for skill_img in hero1_skills:
        state(f"pick_h1_{skill_img.lower()}", "fight_loop",
              [expr("ht_hero == 'hero1' and not ht_bless_picked"), asset("I_BCMJ_SKILL_ADD_CONFIRM"), asset(skill_img)],
              {"click_found": True, "use_match_size": True, "delay": 800, "recheck": True},
              {"set": {"ht_bless_picked": True, "ht_bless_count": "ht_bless_count + 1"}})
    for skill_img in hero2_skills:
        state(f"pick_h2_{skill_img.lower()}", "fight_loop",
              [expr("ht_hero == 'hero2' and not ht_bless_picked"), asset("I_BCMJ_SKILL_ADD_CONFIRM"), asset(skill_img)],
              {"click_found": True, "use_match_size": True, "delay": 800, "recheck": True},
              {"set": {"ht_bless_picked": True, "ht_bless_count": "ht_bless_count + 1"}})
    state("confirm_skill_bless", "fight_loop", [asset("I_BCMJ_SKILL_ADD_CONFIRM")],
          click("I_BCMJ_SKILL_ADD_CONFIRM", delay=1000), {"set": {"ht_bless_picked": False}})
    state("stop_real_money", "fight_loop", [asset("I_REAL_MONEY")],
          advance("exit", ht_exit_reason="'ticket_empty_real_money_popup'"))
    state("stop_exp_max", "fight_loop", [expr("ht_mode == 'exp'"), asset("I_HERO_EXP_MAX")],
          advance("exit", ht_exit_reason="'hero_exp_max'"))
    state("stop_art_war_card_empty", "fight_loop",
          [expr("ht_mode == 'skill' and ht_check_ticket_ocr"),
           {"ocr": "HeroTest::O_ART_WAR_CARD", "var": "ht_art_war_card", "test": "ht_art_war_card <= 0"},
           {"ocr": "HeroTest::O_ART_WAR_CARD_PLUS", "var": "ht_art_war_card_plus", "test": "ht_art_war_card_plus <= 0"}],
          advance("exit", ht_exit_reason="'art_war_card_empty'"))
    state("stop_ap_insufficient", "fight_loop",
          [expr("ht_mode == 'exp' and ht_check_ap_ocr"),
           {"ocr": "HeroTest::O_REMAIN_AP", "mode": "counter_current", "var": "ht_remain_ap",
            "test": "ht_remain_ap < ht_ap_min"}],
          advance("exit", ht_exit_reason="'ap_insufficient'"))
    state("time_limit_reached", "fight_loop",
          [expr("ht_limit_seconds > 0 and elapsed_ms >= ht_limit_seconds * 1000")],
          advance("exit", ht_exit_reason="'time_limit'"))
    state("limit_reached", "fight_loop", [expr("ht_battles >= ht_limit_count")],
          advance("exit", ht_exit_reason="'limit_count_reached'"))
    state("lock_exp_team", "fight_loop", [expr("lock_team_enable"), asset("I_UNLOCK")], click("I_UNLOCK", delay=1000))
    state("lock_skill_team", "fight_loop", [expr("lock_team_enable"), asset("I_BCMJ_UNLOCK")],
          click("I_BCMJ_UNLOCK", delay=1000))
    state("confirm_start_challenge", "fight_loop", [asset("I_START_CHALLENGE")],
          click("I_START_CHALLENGE", delay=1000))
    state("confirm_reset_challenge", "fight_loop", [asset("I_BCMJ_RESET_CONFIRM")],
          click("I_BCMJ_RESET_CONFIRM", delay=1000))
    state("fire_exp", "fight_loop", [asset("I_BATTLE")],
          click("I_BATTLE", delay=1200), {"set": reset}, advance("in_battle"))
    state("fire_skill", "fight_loop", [asset("I_BCMJ_BATTLE")],
          click("I_BCMJ_BATTLE", delay=1200), {"set": reset}, advance("in_battle"))

    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], advance("buff_after"))
    state("finished_target_prep", "finished", [expr("ht_next_delay_s > 0")],
          advance("stop_target", ht_target_delay_s="ht_next_delay_s", ht_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "英杰试炼已完成并按目标调度返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "HeroTest",
                "delay_seconds_var": "ht_target_delay_s",
                "observed_ms_var": "ht_observed_ms",
            },
            "evidence": {"scope": "hero_test_target_schedule"},
        }
    })
    state("finished", "finished", [], {
        "stop": {
            "reason": "英杰试炼已完成或触发门票/满级安全停止，已返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "HeroTest",
            "evidence": {"scope": "hero_test_bounded_loop"},
        }
    })
    state("exit_gbb_back", "exit", [asset("I_GBB_BACK")], click("I_GBB_BACK", delay=1200))
    state("exit_back", "exit", [asset("I_BACK")], click("I_BACK", delay=1200))
    state("exit_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", delay=1200))

    raw["oas_hero_test_contract"] = {
        "source": HERO_TEST_ENTRY,
        "source_pins": {**HERO_TEST_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "buff_calls": buff_calls,
        "source_obligations": [
            *nav["source_obligations"], *contract["source_obligations"],
            *(ob for call in buff_calls for ob in call["source_obligations"]),
            {
                "id": "hero_test_skill_bless_selection_and_live",
                "blocking": True,
                "requirement": "Bind hero1/hero2 skill blessing preference selection, AP/ticket OCR checks, and live buff frames",
            },
        ],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
