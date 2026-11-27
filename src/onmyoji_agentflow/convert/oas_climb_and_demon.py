"""Pinned OAS BudokaiTournament, ActivityShikigami, FrogBoss, and DemonEncounter workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_answer_bank import ANSWER_BANK, PINS as ANSWER_PINS, bind_answer_bank
from .oas_battle import compile_general_battle
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


BUDOKAI_ENTRY = "tasks/BudokaiTournament/script_task.py"
BUDOKAI_PINS = {
    BUDOKAI_ENTRY: "6432f0a5474afb1151f5e0b319a3865a4eb60d3078dd52fa7f2bcac610973ae4",
    "tasks/BudokaiTournament/config.py": "3074ee4c0263a49d97d509d5bf18694cfb1780276edce802090cb63ffedaefcd",
    "tasks/BudokaiTournament/assets.py": "8ab8620bfc82325f1ce2fce2909a3df815ab0066f39bc7d537d5a981a42cfe5e",
}

ACT_SHIKIGAMI_ENTRY = "tasks/ActivityShikigami/script_task.py"
ACT_SHIKIGAMI_PINS = {
    ACT_SHIKIGAMI_ENTRY: "179d1dded999168ee77219b75d81aea1a9097de3d15408f26af82f69c5b60926",
    "tasks/ActivityShikigami/config.py": "8cc61f08ce7b8e5496715d735a2abcf5039c23b75aa5686fb198b1b58276da4b",
    "tasks/ActivityShikigami/assets.py": "48c47db751e19244ca94e5171b1489be1d17e7a2fdaaf63dd9d2941a88ec0072",
    "tasks/ActivityShikigami/page.py": "31b1b345ce8ae5635a4cd65e5ed65ad3b4453f88b7e62e4be961e1266886d5fa",
}

FROG_BOSS_ENTRY = "tasks/FrogBoss/script_task.py"
FROG_BOSS_PINS = {
    FROG_BOSS_ENTRY: "a60ca60bc5ddfa4bcaec79c9b6ff2b0b632ca8ad1de6f6f18431e5098d6088f1",
    "tasks/FrogBoss/config.py": "2d675ef3e5575f3aa2e9e13b4e91e0ca17ce5bf6aa8e00d4077a6a48024f797a",
    "tasks/FrogBoss/assets.py": "ca8b638808445389880e54f4e6f749036d25edf07ae5a8a6cdc86ade386f4b88",
    "tasks/FrogBoss/frog_oas.py": "5c25ddfcdc813ea2cd8762b77ad320747c9301c6abf966bd0d6f79e28eef236f",
    "tasks/FrogBoss/record_reader.py": "e9a546d98b9ecf2bdf5d019cd8f708807d80b12b1d9f1956f8be48672fa8e7e9",
}

DEMON_ENCOUNTER_ENTRY = "tasks/DemonEncounter/script_task.py"
DEMON_ENCOUNTER_PINS = {
    DEMON_ENCOUNTER_ENTRY: "eaca3a38d11d8f8673902b5812be5508d0c74612e0181be4b527446b95ffce3d",
    "tasks/DemonEncounter/config.py": "cf629af117367dc30b7b4276f89aa8bd0b3553ae888f27f83f3d2ee63c3da126",
    "tasks/DemonEncounter/assets.py": "fc7ceef21986e3e2cebcd51e39d79a5b4f1f1e330ef1c233beedd12be63cd902",
    "tasks/DemonEncounter/data/answer.py": "0057f6bacb901f427847473483a20d085d178e82d31f39d4def5a4f2bb91af7d",
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


def compile_budokai_tournament_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS BudokaiTournament (武道会/爬塔活动) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, BUDOKAI_PINS, "BudokaiTournament")
    nav = compile_navigation_family(
        source, resources, prefix="bt_nav", destination="page_climb_act",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="bt_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_budokai_tournament_natively_staged", title="武道会爬塔", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        bt_mode={"default": "daily_training", "choices": ["daily_training", "cultivation_drills", "both"]},
        bt_run_drills_first={"default": False},
        bt_limit_count={"default": 50, "min": 0, "max": 999},
        bt_drills_limit={"default": 5, "min": 0, "max": 999},
        bt_limit_seconds={"default": 3600, "min": 0, "max": 7200},
        bt_battle_timeout_s={"default": 0, "min": 0, "max": 3600},
        bt_enable_boss_search={"default": False},
        bt_check_tickets_ocr={"default": False},
        bt_active_souls_clean={"default": False},
        bt_souls_tidy_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        bt_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        bt_phase="entry", bt_active_stage="", bt_battles=0, bt_wins=0, bt_scouts=0,
        bt_remain_ap=-1, bt_remain_boss=-1, bt_exit_reason="", bt_souls_tidy_woken=False,
        bt_battle_started_ms=-1, bt_battle_timeouts=0, bt_target_delay_s=0, bt_observed_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/BudokaiTournament.yaml",
        "upstream/oas/ActivityShikigami.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("BudokaiTournament", "ActivityShikigami", "Component_GeneralBattle", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"bt_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"bt_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"bt_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="BudokaiTournament"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="BudokaiTournament", delay=1000):
        return _click_from(docs, name, ns, delay)

    bind_task_presets(raw, source, resources, prefix="bt", resume="navigate", category="bt")
    _wire_nav(raw, "bt", phase, advance, "lock_check")

    state("lock_turn_on", "lock_check", [expr("lock_team_enable"), asset("I_UNLOCK", "ActivityShikigami")],
          click("I_UNLOCK", "ActivityShikigami", 1000))
    state("lock_turn_off", "lock_check", [expr("not lock_team_enable"), asset("I_LOCK", "ActivityShikigami")],
          click("I_LOCK", "ActivityShikigami", 1000))
    state("lock_ready_on", "lock_check", [expr("lock_team_enable"), asset("I_LOCK", "ActivityShikigami")],
          advance("fight_loop"))
    state("lock_ready_off", "lock_check", [expr("not lock_team_enable"), asset("I_UNLOCK", "ActivityShikigami")],
          advance("fight_loop"))

    state("battle_super_long_timeout", "in_battle", [
        expr("bt_battle_timeout_s > 0 and bt_battle_started_ms >= 0 and "
             "elapsed_ms - bt_battle_started_ms >= bt_battle_timeout_s * 1000"),
        asset("I_EXIT", "Component_GeneralBattle"),
    ], click("I_EXIT", "Component_GeneralBattle", 1000),
       advance("battle_retreat", bt_battle_timeouts="bt_battle_timeouts + 1"))
    state("battle_retreat_confirm", "battle_retreat", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("battle_retreat_false", "battle_retreat", [asset("I_FALSE", "Component_GeneralBattle")],
          click("C_WIN_1", "Component_GeneralBattle", 1000),
          advance("fight_loop", bt_battles="bt_battles + 1", bt_battle_started_ms=-1))
    state("battle_retreat_returned", "battle_retreat", [
        {"any": [asset("I_IMG3"), asset("I_IMG4"), asset("I_IMG1"),
                 asset("I_CHECK_BATTLE_BOSS", "ActivityShikigami")]},
    ], advance("fight_loop", bt_battles="bt_battles + 1", bt_battle_started_ms=-1))
    reset = _wire_battle(raw, body, contract, phase, advance, "bt_battles", "bt_wins", "fight_loop")
    state("init_stage_drills", "fight_loop",
          [expr("bt_active_stage == '' and (bt_mode == 'cultivation_drills' or (bt_mode == 'both' and bt_run_drills_first))")],
          {"set": {"bt_active_stage": "'cultivation_drills'"}})
    state("init_stage_daily", "fight_loop", [expr("bt_active_stage == ''")],
          {"set": {"bt_active_stage": "'daily_training'"}})
    state("time_limit_reached", "fight_loop", [expr("elapsed_ms >= bt_limit_seconds * 1000")],
          advance("exit", bt_exit_reason="'time_limit'"))
    state("limit_reached", "fight_loop", [expr("bt_battles >= bt_limit_count")],
          advance("exit", bt_exit_reason="'count_limit'"))
    state("daily_ap_empty_to_drills", "fight_loop",
          [expr("bt_check_tickets_ocr and bt_active_stage == 'daily_training' and bt_mode == 'both' and not bt_run_drills_first"),
           {"ocr": "ActivityShikigami::O_REMAIN_AP", "var": "bt_remain_ap"},
           expr("bt_remain_ap == 0")],
          advance("switch_to_drills", bt_active_stage="'cultivation_drills'"))
    state("daily_ap_empty_exit", "fight_loop",
          [expr("bt_check_tickets_ocr and bt_active_stage == 'daily_training' and (bt_mode != 'both' or bt_run_drills_first)"),
           {"ocr": "ActivityShikigami::O_REMAIN_AP", "var": "bt_remain_ap"},
           expr("bt_remain_ap == 0")],
          advance("exit", bt_exit_reason="'ap_tickets_empty'"))
    state("drills_boss_empty_close_to_daily", "fight_loop",
          [expr("bt_check_tickets_ocr and bt_active_stage == 'cultivation_drills' and bt_mode == 'both' and bt_run_drills_first"),
           {"any": [asset("I_IMG3"), asset("I_IMG4")]},
           {"ocr": "ActivityShikigami::O_REMAIN_BOSS", "var": "bt_remain_boss"},
           expr("bt_remain_boss == 0")],
          click("C_BOSS_DETAIL_CLOSE", delay=1000),
          advance("switch_to_daily", bt_active_stage="'daily_training'"))
    state("drills_boss_empty_to_daily", "fight_loop",
          [expr("bt_check_tickets_ocr and bt_active_stage == 'cultivation_drills' and bt_mode == 'both' and bt_run_drills_first"),
           {"ocr": "ActivityShikigami::O_REMAIN_BOSS", "var": "bt_remain_boss"},
           expr("bt_remain_boss == 0")],
          advance("switch_to_daily", bt_active_stage="'daily_training'"))
    state("drills_boss_empty_close", "fight_loop",
          [expr("bt_check_tickets_ocr and bt_active_stage == 'cultivation_drills'"),
           {"any": [asset("I_IMG3"), asset("I_IMG4")]},
           {"ocr": "ActivityShikigami::O_REMAIN_BOSS", "var": "bt_remain_boss"},
           expr("bt_remain_boss == 0")],
          click("C_BOSS_DETAIL_CLOSE", delay=1000), advance("exit", bt_exit_reason="'boss_tickets_empty'"))
    state("drills_boss_empty_exit", "fight_loop",
          [expr("bt_check_tickets_ocr and bt_active_stage == 'cultivation_drills'"),
           {"ocr": "ActivityShikigami::O_REMAIN_BOSS", "var": "bt_remain_boss"},
           expr("bt_remain_boss == 0")],
          advance("exit", bt_exit_reason="'boss_tickets_empty'"))
    state("switch_drills_arrived", "switch_to_drills", [asset("I_CHECK_BATTLE_BOSS", "ActivityShikigami")],
          advance("fight_loop"))
    state("switch_drills_enter_boss", "switch_to_drills", [asset("I_TO_BATTLE_BOSS", "ActivityShikigami")],
          click("I_TO_BATTLE_BOSS", "ActivityShikigami", 1200))
    state("switch_drills_circle", "switch_to_drills", [asset("I_UI_BACK_CIRCLE", "GlobalGame")],
          click("I_UI_BACK_CIRCLE", "GlobalGame", 1000))
    state("switch_drills_back", "switch_to_drills", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000))
    state("switch_daily_arrived", "switch_to_daily",
          [{"any": [asset("I_LOCK", "ActivityShikigami"), asset("I_UNLOCK", "ActivityShikigami")]}],
          advance("fight_loop"))
    state("switch_daily_enter_main", "switch_to_daily", [asset("I_TO_BATTLE_MAIN", "ActivityShikigami")],
          click("I_TO_BATTLE_MAIN", "ActivityShikigami", 1200))
    state("switch_daily_circle", "switch_to_daily", [asset("I_UI_BACK_CIRCLE", "GlobalGame")],
          click("I_UI_BACK_CIRCLE", "GlobalGame", 1000))
    state("switch_daily_back", "switch_to_daily", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000))
    state("confirm_small", "fight_loop", [asset("I_UI_CONFIRM_SAMLL", "GlobalGame")],
          click("I_UI_CONFIRM_SAMLL", "GlobalGame", 1000))
    state("confirm_dlg", "fight_loop", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("discover_self_boss", "fight_loop",
          [expr("bt_enable_boss_search or bt_active_stage == 'cultivation_drills'"), asset("I_IMG2")],
          click("I_IMG2", delay=1000))
    state("drills_scout_limit", "fight_loop",
          [expr("(bt_enable_boss_search or bt_active_stage == 'cultivation_drills') and bt_scouts >= bt_drills_limit"),
           asset("I_IMG1")],
          advance("exit", bt_exit_reason="'drills_scout_limit'"))
    state("fire_start", "fight_loop", [asset("I_IMG3")],
          click("I_IMG3", delay=1200), {"set": reset}, advance("in_battle", bt_battle_started_ms="elapsed_ms"))
    state("fire_continue", "fight_loop", [asset("I_IMG4")],
          click("I_IMG4", delay=1200), {"set": reset}, advance("in_battle", bt_battle_started_ms="elapsed_ms"))
    state("search_boss", "fight_loop",
          [expr("bt_enable_boss_search or bt_active_stage == 'cultivation_drills'"), asset("I_IMG1")],
          click("I_IMG1", delay=1200), {"inc": "bt_scouts"})

    state("exit_wake_souls_tidy", "exit", [
        asset("I_CHECK_MAIN", "GameUi"), expr("bt_active_souls_clean and not bt_souls_tidy_woken"),
    ], {"oas_wake": {"task": "SoulsTidy", "failure_seconds_param": "bt_souls_tidy_failure_seconds"}},
       {"set": {"bt_souls_tidy_woken": True}})
    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("bt_next_delay_s > 0")],
          advance("stop_target", bt_target_delay_s="bt_next_delay_s", bt_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "武道会爬塔已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "BudokaiTournament",
                "delay_seconds_var": "bt_target_delay_s",
                "observed_ms_var": "bt_observed_ms",
            },
            "evidence": {"scope": "budokai_tournament_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "武道会爬塔已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "BudokaiTournament",
            "evidence": {"scope": "budokai_tournament_bounded_loop"},
        }
    })
    state("exit_back_green", "exit", [asset("I_BACK_GREEN", "ActivityShikigami")],
          click("I_BACK_GREEN", "ActivityShikigami", 1200))
    state("exit_back_circle", "exit", [asset("I_UI_BACK_CIRCLE", "GlobalGame")],
          click("I_UI_BACK_CIRCLE", "GlobalGame", 1200))
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))

    raw["oas_budokai_tournament_contract"] = {
        "source": BUDOKAI_ENTRY,
        "source_pins": {**BUDOKAI_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "budokai_tournament_sequence_and_cultivation_drills",
            "blocking": True,
            "requirement": "Bind multi-phase run_sequence switching, cultivation drills boss search, and super-long battle timeout",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_activity_shikigami_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS ActivityShikigami (新式神大型活动爬塔) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, ACT_SHIKIGAMI_PINS, "ActivityShikigami")
    nav = compile_navigation_family(
        source, resources, prefix="act_nav", destination="page_climb_act",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="act_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_activity_shikigami_natively_staged", title="活动爬塔", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        act_mode={"default": "pass", "choices": ["pass", "ap", "ap100", "boss"]},
        act_limit_count={"default": 50, "min": 0, "max": 999},
        act_ap_limit={"default": 0, "min": 0, "max": 999},
        act_ap100_limit={"default": 0, "min": 0, "max": 999},
        act_boss_limit={"default": 0, "min": 0, "max": 999},
        act_run_ap_after_pass={"default": False},
        act_run_ap100_after_ap={"default": False},
        act_run_boss_after_ap={"default": False},
        act_check_resource_ocr={"default": False},
        act_buy_ap={"default": False},
        act_confirm_buy_ap={"default": False},
        act_buy_max_clicks={"default": 1, "min": 0, "max": 50},
        act_active_souls_clean={"default": False},
        act_souls_tidy_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        act_limit_seconds={"default": 3600, "min": 0, "max": 7200},
        act_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        act_phase="entry", act_active_mode="", act_battles=0, act_stage_battles=0, act_wins=0,
        act_remain_pass=-1, act_remain_ap=-1, act_remain_ap100=-1, act_remain_boss=-1,
        act_remain_buy=-1, act_buys=0, act_target_delay_s=0, act_observed_ms=0,
        act_exit_reason="", act_souls_tidy_woken=False,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/ActivityShikigami.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("ActivityShikigami", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"act_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"act_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"act_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="ActivityShikigami"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="ActivityShikigami", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("buy_ap_economic_gate", "entry", [expr("act_buy_ap and not act_confirm_buy_ap")],
          {"fail": "活动爬塔消耗勾玉购买活动体力需显式开启 act_confirm_buy_ap 经济确认参数"})
    bind_task_presets(raw, source, resources, prefix="act", resume="navigate", category="act")
    _wire_nav(raw, "act", phase, advance, "enter_stage")

    state("stage_main_ready", "enter_stage", [expr("act_mode != 'boss'"), asset("I_CHECK_BATTLE_MAIN")],
          advance("fight_loop"))
    state("stage_boss_ready", "enter_stage", [expr("act_mode == 'boss'"), asset("I_CHECK_BATTLE_BOSS")],
          advance("fight_loop"))
    state("stage_click_main", "enter_stage", [expr("act_mode != 'boss'"), asset("I_TO_BATTLE_MAIN")],
          click("I_TO_BATTLE_MAIN", delay=1000))
    state("stage_click_main2", "enter_stage", [expr("act_mode != 'boss'"), asset("I_TO_BATTLE_MAIN_2")],
          click("I_TO_BATTLE_MAIN_2", delay=1000))
    state("stage_click_boss", "enter_stage", [expr("act_mode == 'boss'"), asset("I_TO_BATTLE_BOSS")],
          click("I_TO_BATTLE_BOSS", delay=1000))

    reset = _wire_battle(raw, body, contract, phase, advance, "act_battles", "act_wins", "fight_loop")
    state("init_active_mode", "fight_loop", [expr("act_active_mode == ''")],
          {"set": {"act_active_mode": "act_mode", "act_stage_battles": 0}})
    state("time_limit_reached", "fight_loop", [expr("elapsed_ms >= act_limit_seconds * 1000")],
          advance("exit", act_exit_reason="'time_limit'"))
    # Resource OCR depletion & multi-phase sequence switching (pass -> ap -> boss)
    state("pass_depleted_to_ap", "fight_loop",
          [expr("act_active_mode == 'pass' and act_check_resource_ocr and act_run_ap_after_pass"),
           {"ocr": "ActivityShikigami::O_REMAIN_PASS", "var": "act_remain_pass", "test": "act_remain_pass <= 0"}],
          {"set": {"act_active_mode": "'ap'", "act_stage_battles": 0}})
    state("pass_depleted_exit", "fight_loop",
          [expr("act_active_mode == 'pass' and act_check_resource_ocr and not act_run_ap_after_pass"),
           {"ocr": "ActivityShikigami::O_REMAIN_PASS", "var": "act_remain_pass", "test": "act_remain_pass <= 0"}],
          advance("exit", act_exit_reason="'pass_empty'"))
    state("ap_depleted_to_ap100", "fight_loop",
          [expr("act_active_mode == 'ap' and act_check_resource_ocr and act_run_ap100_after_ap"),
           {"ocr": "ActivityShikigami::O_REMAIN_AP", "var": "act_remain_ap", "test": "act_remain_ap <= 0"}],
          {"set": {"act_active_mode": "'ap100'", "act_stage_battles": 0}})
    state("ap_depleted_to_boss", "fight_loop",
          [expr("act_active_mode == 'ap' and act_check_resource_ocr and act_run_boss_after_ap and not act_run_ap100_after_ap"),
           {"ocr": "ActivityShikigami::O_REMAIN_AP", "var": "act_remain_ap", "test": "act_remain_ap <= 0"}],
          advance("switch_to_boss", act_active_mode="'boss'", act_stage_battles=0))
    state("ap_depleted_exit", "fight_loop",
          [expr("act_active_mode == 'ap' and act_check_resource_ocr and not act_run_boss_after_ap and not act_run_ap100_after_ap"),
           {"ocr": "ActivityShikigami::O_REMAIN_AP", "var": "act_remain_ap", "test": "act_remain_ap <= 0"}],
          advance("exit", act_exit_reason="'ap_empty'"))
    state("ap100_depleted_to_boss", "fight_loop",
          [expr("act_active_mode == 'ap100' and act_check_resource_ocr and act_run_boss_after_ap"),
           {"ocr": "ActivityShikigami::O_REMAIN_AP100", "var": "act_remain_ap100", "test": "act_remain_ap100 <= 0"}],
          advance("switch_to_boss", act_active_mode="'boss'", act_stage_battles=0))
    state("ap100_depleted_exit", "fight_loop",
          [expr("act_active_mode == 'ap100' and act_check_resource_ocr and not act_run_boss_after_ap"),
           {"ocr": "ActivityShikigami::O_REMAIN_AP100", "var": "act_remain_ap100", "test": "act_remain_ap100 <= 0"}],
          advance("exit", act_exit_reason="'ap100_empty'"))
    state("ap100_limit_to_boss", "fight_loop",
          [expr("act_active_mode == 'ap100' and act_run_boss_after_ap and act_ap100_limit > 0 and act_stage_battles >= act_ap100_limit")],
          advance("switch_to_boss", act_active_mode="'boss'", act_stage_battles=0))
    state("ap100_limit_exit", "fight_loop",
          [expr("act_active_mode == 'ap100' and not act_run_boss_after_ap and act_ap100_limit > 0 and act_stage_battles >= act_ap100_limit")],
          advance("exit", act_exit_reason="'ap100_limit_reached'"))
    state("buy_ap_confirm_jade", "fight_loop",
          [expr("act_buy_ap and act_confirm_buy_ap and act_buys < act_buy_max_clicks"),
           {"ocr": "ActivityShikigami::O_REMAIN_BUY", "mode": "counter_current", "var": "act_remain_buy",
            "test": "act_remain_buy > 0"},
           asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", delay=1000), {"inc": "act_buys"})
    raw["states"][-1].update(
        sensitive="花勾玉",
        desc="活动爬塔消耗勾玉购买活动体力门票。",
    )
    state("boss_depleted_exit", "fight_loop",
          [expr("act_active_mode == 'boss' and act_check_resource_ocr"),
           {"ocr": "ActivityShikigami::O_REMAIN_BOSS", "var": "act_remain_boss", "test": "act_remain_boss <= 0"}],
          advance("exit", act_exit_reason="'boss_empty'"))
    state("pass_limit_to_ap", "fight_loop",
          [expr("act_active_mode == 'pass' and act_run_ap_after_pass and act_battles >= act_limit_count")],
          {"set": {"act_active_mode": "'ap'", "act_stage_battles": 0}})
    state("ap_limit_to_ap100", "fight_loop",
          [expr("act_active_mode == 'ap' and act_run_ap100_after_ap and act_ap_limit > 0 and act_stage_battles >= act_ap_limit")],
          {"set": {"act_active_mode": "'ap100'", "act_stage_battles": 0}})
    state("ap_limit_to_boss", "fight_loop",
          [expr("act_active_mode == 'ap' and act_run_boss_after_ap and not act_run_ap100_after_ap and act_ap_limit > 0 and act_stage_battles >= act_ap_limit")],
          advance("switch_to_boss", act_active_mode="'boss'", act_stage_battles=0))
    state("ap_limit_exit", "fight_loop",
          [expr("act_active_mode == 'ap' and not act_run_boss_after_ap and not act_run_ap100_after_ap and act_ap_limit > 0 and act_stage_battles >= act_ap_limit")],
          advance("exit", act_exit_reason="'ap_limit_reached'"))
    state("boss_limit_exit", "fight_loop",
          [expr("act_active_mode == 'boss' and act_boss_limit > 0 and act_stage_battles >= act_boss_limit")],
          advance("exit", act_exit_reason="'boss_limit_reached'"))
    state("limit_reached", "fight_loop",
          [expr("not (act_active_mode == 'pass' and act_run_ap_after_pass) and not (act_active_mode == 'ap' and act_ap_limit > 0) and not (act_active_mode == 'ap100' and act_ap100_limit > 0) and not (act_active_mode == 'boss' and act_boss_limit > 0) and act_battles >= act_limit_count")],
          advance("exit", act_exit_reason="'limit_count_reached'"))
    state("switch_to_boss_ready", "switch_to_boss", [asset("I_CHECK_BATTLE_BOSS")], advance("fight_loop"))
    state("switch_to_boss_enter", "switch_to_boss", [asset("I_TO_BATTLE_BOSS")], click("I_TO_BATTLE_BOSS", delay=1000))
    state("switch_to_boss_circle", "switch_to_boss", [asset("I_UI_BACK_CIRCLE", "GlobalGame")],
          click("I_UI_BACK_CIRCLE", "GlobalGame", delay=1000))
    state("switch_to_boss_back", "switch_to_boss", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", delay=1000))
    state("switch_to_pass", "fight_loop", [expr("act_active_mode == 'pass'"), asset("I_CLIMB_MODE_AP")],
          click("I_CLIMB_MODE_SWITCH", delay=1000))
    state("switch_to_ap", "fight_loop", [expr("act_active_mode == 'ap'"), asset("I_CLIMB_MODE_PASS")],
          click("I_CLIMB_MODE_SWITCH", delay=1000))
    state("lock_on", "fight_loop", [expr("lock_team_enable"), asset("I_UNLOCK")], click("I_UNLOCK", delay=1000))
    state("confirm_popup", "fight_loop", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", delay=600))
    state("confirm_small_popup", "fight_loop", [asset("I_UI_CONFIRM_SAMLL", "GlobalGame")],
          click("I_UI_CONFIRM_SAMLL", "GlobalGame", delay=600))
    state("reward_popup", "fight_loop", [asset("I_UI_REWARD", "GlobalGame")],
          click("C_UI_REWARD", "GlobalGame", delay=500))
    state("skip_story", "fight_loop", [asset("I_SKIP_BUTTON")], click("I_SKIP_BUTTON", delay=800))
    state("confirm_skip", "fight_loop", [asset("I_CONFIRM_SKIP")], click("I_CONFIRM_SKIP", delay=800))
    state("fire_boss_img", "fight_loop", [asset("I_PASS_13")],
          click("I_PASS_13", delay=1200), {"set": {**reset, "act_stage_battles": "act_stage_battles + 1"}},
          advance("in_battle"))
    state("fire_ocr_text", "fight_loop", [{"text": "挑战", "region": [1135, 599, 85, 49]}],
          {"click": [1135, 599, 1220, 648], "delay": 1200, "recheck": True},
          {"set": {**reset, "act_stage_battles": "act_stage_battles + 1"}}, advance("in_battle"))

    state("exit_wake_souls_tidy", "exit", [
        asset("I_CHECK_MAIN", "GameUi"),
        expr("act_active_souls_clean and not act_souls_tidy_woken"),
    ], {"oas_wake": {"task": "SoulsTidy", "failure_seconds_param": "act_souls_tidy_failure_seconds"}},
       {"set": {"act_souls_tidy_woken": True}})
    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("act_next_delay_s > 0")],
          advance("stop_target", act_target_delay_s="act_next_delay_s", act_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "活动爬塔已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "ActivityShikigami",
                "delay_seconds_var": "act_target_delay_s",
                "observed_ms_var": "act_observed_ms",
            },
            "evidence": {"scope": "activity_shikigami_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "活动爬塔已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "ActivityShikigami",
            "evidence": {"scope": "activity_shikigami_bounded_climb"},
        }
    })
    state("exit_back_green", "exit", [asset("I_BACK_GREEN")], click("I_BACK_GREEN", delay=1200))
    state("exit_red", "exit", [asset("I_RED_EXIT")], click("I_RED_EXIT", delay=1200))
    state("exit_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))

    raw["oas_activity_shikigami_contract"] = {
        "source": ACT_SHIKIGAMI_ENTRY,
        "source_pins": {**ACT_SHIKIGAMI_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "activity_shikigami_pass_ap_ocr_and_shop_buy",
            "blocking": True,
            "requirement": "Bind O_REMAIN_PASS/O_REMAIN_AP/O_REMAIN_AP100 preprocessing OCR, run_sequence_v, and jade ticket purchase",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_frog_boss_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS FrogBoss (对弈竞猜) workflow with strict gold-bet confirmation gate."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, FROG_BOSS_PINS, "FrogBoss")
    nav = compile_navigation_family(
        source, resources, prefix="fb_nav", destination="page_main",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_frog_boss_natively_staged", title="对弈竞猜", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update(
        fb_confirm_bet={"default": False},
        fb_bet_side={"default": "left", "choices": ["left", "right"]},
        fb_strategy={"default": "manual", "choices": ["manual", "oas"]},
        fb_limit_seconds={"default": 0, "min": 0, "max": 7200},
        fb_round_delay_s={"default": 0, "min": 0, "max": 86400},
    )
    raw["vars"].update(fb_phase="entry", fb_target_delay_s=0, fb_observed_ms=0, fb_exit_reason="")
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/FrogBoss.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("FrogBoss", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"fb_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"fb_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"fb_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="FrogBoss"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="FrogBoss", delay=1000):
        return _click_from(docs, name, ns, delay)

    _wire_nav(raw, "fb", phase, advance, "enter")
    state("entry_begin", "entry", [], advance("navigate"))

    state("enter_time_limit", "enter",
          [expr("fb_limit_seconds > 0 and elapsed_ms >= fb_limit_seconds * 1000")],
          advance("stop_time_limit", fb_exit_reason="'time_limit'"))
    state("enter_ready", "enter", [asset("I_FROG_CHECK")], advance("lobby"))
    state("enter_click", "enter", [asset("I_FROG_BOSS_ENTER")], click("I_FROG_BOSS_ENTER", delay=1500))

    state("lobby_time_limit", "lobby",
          [expr("fb_limit_seconds > 0 and elapsed_ms >= fb_limit_seconds * 1000")],
          advance("stop_time_limit", fb_exit_reason="'time_limit'"))
    state("time_limit_target", "stop_time_limit", [expr("fb_round_delay_s > 0")],
          advance("stop_target", fb_target_delay_s="fb_round_delay_s", fb_observed_ms="elapsed_ms"))
    state("time_limit_stop", "stop_time_limit", [], {
        "stop": {
            "reason": "对弈竞猜达到安全超时上限，已停止",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "FrogBoss",
            "evidence": {"scope": "frog_boss_time_limit"},
        }
    })
    state("already_betted_target", "lobby", [asset("I_BETTED"), expr("fb_round_delay_s > 0")],
          advance("stop_target", fb_target_delay_s="fb_round_delay_s",
                  fb_observed_ms="elapsed_ms", fb_exit_reason="'already_betted'"))
    state("already_betted", "lobby", [asset("I_BETTED")], {
        "stop": {
            "reason": "本轮对弈竞猜已下注",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "FrogBoss",
            "evidence": {"scope": "frog_boss_already_betted"},
        }
    })
    state("boss_rest_target", "lobby", [asset("I_FROG_BOSS_REST"), expr("fb_round_delay_s > 0")],
          advance("stop_target", fb_target_delay_s="fb_round_delay_s",
                  fb_observed_ms="elapsed_ms", fb_exit_reason="'boss_rest'"))
    state("boss_rest", "lobby", [asset("I_FROG_BOSS_REST")], {
        "stop": {
            "reason": "对弈竞猜当前休息中",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "FrogBoss",
            "evidence": {"scope": "frog_boss_resting"},
        }
    })
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "对弈竞猜已按 2 小时轮次预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "FrogBoss",
                "delay_seconds_var": "fb_target_delay_s",
                "observed_ms_var": "fb_observed_ms",
            },
            "evidence": {"scope": "frog_boss_round_target"},
        }
    })
    state("claim_win_box", "lobby", [asset("I_BET_SUCCESS_BOX")], click("I_BET_SUCCESS_BOX", delay=1000))
    state("claim_lose_next", "lobby", [asset("I_BET_FAILURE"), asset("I_NEXT_COMPETITION")],
          click("I_NEXT_COMPETITION", delay=1200))

    state("bet_oas_network_gate", "lobby",
          [asset("I_BET_LEFT"), asset("I_BET_RIGHT"), expr("fb_strategy == 'oas'")],
          {"fail": "对弈竞猜 OAS 外部网络胜率预测(fetch_predictions)与历史记录结算需外部网络契约"})
    state("bet_economic_confirm_gate", "lobby",
          [asset("I_BET_LEFT"), asset("I_BET_RIGHT"), expr("not fb_confirm_bet")],
          {"fail": "对弈竞猜单局下注消耗 30 万金币，需显式开启 fb_confirm_bet 确认参数"})
    state("bet_pick_left", "lobby",
          [asset("I_BET_LEFT"), asset("I_BET_RIGHT"), expr("fb_confirm_bet and fb_bet_side == 'left'")],
          click("I_BET_LEFT", delay=1000), advance("confirm_bet"))
    state("bet_pick_right", "lobby",
          [asset("I_BET_LEFT"), asset("I_BET_RIGHT"), expr("fb_confirm_bet and fb_bet_side == 'right'")],
          click("I_BET_RIGHT", delay=1000), advance("confirm_bet"))

    state("bet_select_30w", "confirm_bet", [asset("I_GOLD_30")], click("I_GOLD_30", delay=1000))
    state("bet_confirm_sure", "confirm_bet", [asset("I_BET_SURE")], click("I_BET_SURE", delay=1200), advance("lobby"))
    raw["states"][-1].update(
        sensitive="购买",
        desc="确认对弈竞猜下注，将消耗 30 万金币。",
    )

    raw["oas_frog_boss_contract"] = {
        "source": FROG_BOSS_ENTRY,
        "source_pins": {**FROG_BOSS_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "frog_boss_oas_predictions_and_record_settlement",
            "blocking": True,
            "requirement": "Bind frog_oas HTTP prediction fetch, record_reader history settlement, and 2-hour round schedule",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_demon_encounter_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS DemonEncounter (现世逢魔与逢魔首领) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, DEMON_ENCOUNTER_PINS, "DemonEncounter")
    nav = compile_navigation_family(
        source, resources, prefix="de_nav", destination="page_demon_encounter_realworld",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="de_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_demon_encounter_natively_staged", title="逢魔之时", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 2400
    bind_schedule(source, raw)
    bind_answer_bank(raw, source)
    raw["params"].update(
        de_is_open_window={"default": True},
        de_best_boss={"default": False},
        de_confirm_jade_box={"default": False},
        de_jade_box_buy_sushi={"default": False},
        de_jade_box_max_budget={"default": 0, "min": 0, "max": 200},
        de_check_challenge_count={"default": True},
        de_check_boss_people={"default": False},
        de_max_crowded_skips={"default": 5, "min": 1, "max": 10},
        de_wait_boss_gather={"default": False},
        de_battle_lanterns={"default": False},
        de_find_boss_lantern={"default": False},
        de_boss_search_max={"default": 3, "min": 1, "max": 9},
        de_limit_seconds={"default": 0, "min": 0, "max": 7200},
        de_next_open_delay_s={"default": 0, "min": 0, "max": 86400},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        de_phase="entry", de_battles=0, de_wins=0, de_find_clicks=0, de_exit_reason="",
        de_lantern=1, de_letter_question="", de_letter_last_question="", de_letter_pick=0,
        de_letter_taps=0, de_letter_started=0, de_letter_rewards=0,
        de_jade_box_started=0, de_jade_box_spent=0, de_jade_box_rewards=0,
        de_challenge_remain=-1, de_boss_people=-1, de_crowded_skips=0,
        de_search_left=-1, de_search_used=-1, de_search_previous=-1, de_search_started_ms=-1,
        de_search_claimed=False,
        de_gather_waits=0, de_in_lantern_battle=False, de_lantern_battles=0,
        de_lantern_balloon_hits=0, de_lantern_mystery_hits=0, de_boss_lantern_found=False,
        de_boss_searches=0, de_target_delay_s=0, de_observed_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/DemonEncounter.yaml",
        "upstream/oas/GlobalGame.yaml",
        "upstream/oas/Component_Buy.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("DemonEncounter", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"de_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"de_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"de_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="DemonEncounter"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="DemonEncounter", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("closed_window_target", "entry", [expr("not de_is_open_window and de_next_open_delay_s > 0")],
          advance("stop_target", de_target_delay_s="de_next_open_delay_s",
                  de_observed_ms="elapsed_ms", de_exit_reason="'closed_window'"))
    state("closed_window_clean", "entry", [expr("not de_is_open_window")], {
        "stop": {
            "reason": "当前不在逢魔之时开放时间(17:00-22:00)",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "DemonEncounter",
            "evidence": {"scope": "demon_encounter_closed_window"},
        }
    })
    bind_task_presets(raw, source, resources, prefix="de", resume="navigate", category="de")
    _wire_nav(raw, "de", phase, advance, "lanterns")

    # Never spend 50 jade on accidental map treasure box popups: dismiss with I_DE_FIND
    for ph in ("lanterns", "scan_letters", "boss"):
        state(f"dismiss_jade50_{ph}", ph, [asset("I_JADE_50")], click("I_DE_FIND", delay=1000))
    for ph in ("lanterns", "lantern_find_pending", "lantern_claim_pending", "scan_letters", "boss", "boss_confirm_gather"):
        state(f"time_limit_{ph}", ph,
              [expr("de_limit_seconds > 0 and elapsed_ms >= de_limit_seconds * 1000")],
              advance("exit", de_exit_reason="'time_limit'"))

    state("lantern_challenge_count_zero", "lanterns",
          [expr("de_check_challenge_count"),
           {"ocr": "DemonEncounter::O_DE_CHALLENGE_COUNT", "mode": "counter_current", "var": "de_challenge_remain"},
           expr("de_challenge_remain == 0")],
          advance("already_challenged", de_exit_reason="'already_challenged_ocr'",
                  de_target_delay_s="oas_success_seconds", de_observed_ms=0))
    state("already_challenged", "already_challenged", [], {"stop": {
        "reason": "今日逢魔挑战次数已用完", "result": "already_done", "verified": True,
        "oas_schedule": {"task": "DemonEncounter", "delay_seconds_var": "de_target_delay_s",
                         "observed_ms_var": "de_observed_ms"},
        "evidence": {"scope": "demon_encounter_zero_challenges"},
    }})
    state("lantern_already_done", "lanterns", [{"any": [asset("I_BOSS_DONE_CHECK"), asset("I_BOSS_KILLED")]}],
          advance("exit", de_exit_reason="'already_challenged'"))
    award = asset("I_DE_AWARD")
    reward = {**asset("I_UI_REWARD", "GlobalGame"), "threshold": .6}
    reward_click = click("C_UI_REWARD", "GlobalGame", 500)
    counter = "DemonEncounter::O_DE_COUNTER"
    has_search_count = [
        {"ocr": counter, "mode": "counter_current", "var": "de_search_left"},
        {"ocr": counter, "mode": "counter_remaining", "var": "de_search_used"},
        expr("de_search_left + de_search_used == 4"),
    ]
    exhausted = [*has_search_count, expr("de_search_left == 0")]
    state("lantern_award_claimed", "lanterns", [*exhausted, {"not": reward}, award],
          {"set": {"de_search_claimed": True}}, advance("scan_letters"))
    state("lantern_claim_dharma", "lanterns", [*exhausted, {"not": award}, asset("I_DE_RED_DHARMA")],
          {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1000},
          advance("lantern_claim_pending", de_search_started_ms="elapsed_ms"))
    state("lantern_find_cap", "lanterns", [*has_search_count, expr("de_search_left > 0 and de_find_clicks >= 4")],
          {"fail": "已达到逢魔搜索输入上限，搜索次数仍未用完"})
    state("lantern_click_find", "lanterns", [
        *has_search_count, expr("de_search_left > 0 and de_find_clicks < 4"), asset("I_DE_FIND"),
    ], {"click_found": True, "offset": [37, 29, 72, 62], "recheck": True, "delay": 1200}, {"inc": "de_find_clicks"},
          advance("lantern_find_pending", de_search_previous="de_search_left", de_search_started_ms="elapsed_ms"))
    state("lantern_search_observed", "lantern_find_pending",
          [*has_search_count, expr("de_search_left < de_search_previous")], advance("lanterns"))
    state("lantern_search_timeout", "lantern_find_pending", [expr("elapsed_ms - de_search_started_ms >= 10000")],
          {"fail": "逢魔搜索后没有读到次数减少"})
    state("lantern_close_reward", "lantern_claim_pending", [reward],
          {"click": [930, 190, 980, 220], "recheck": True, "recheck_retry": True, "delay": 1000})
    state("lantern_reward_returned", "lantern_claim_pending", [*exhausted, {"not": reward}, award],
          {"set": {"de_search_claimed": True}}, advance("scan_letters"))
    state("lantern_reward_timeout", "lantern_claim_pending", [expr("elapsed_ms - de_search_started_ms >= 10000")],
          {"fail": "逢魔搜索奖励领取后未能核对已领取状态"})

    dialog = asset("I_LETTER_CLOSE")
    jade_price = asset("I_JADE_50")
    jade_budget = expr("de_confirm_jade_box and de_jade_box_spent + 50 <= de_jade_box_max_budget")
    for slot in range(1, 5):
        x, y, right, bottom = docs["DemonEncounter"][f"C_DE_MATCH_{slot}"]["rect"]
        roi_vars = [f"de_lantern_{slot}_{axis}" for axis in ("x", "y", "w", "h")]
        raw["vars"].update(zip(roi_vars, (x, y, right - x, bottom - y)))
        letter = {**asset("I_DE_LETTER"), "region_vars": roi_vars}
        box = {**asset("I_DE_BOX"), "region_vars": roi_vars}
        realm_l = {**asset("I_DE_REALM"), "region_vars": roi_vars}
        find_boss_l = {**asset("I_DE_FIND_BOSS"), "region_vars": roi_vars}
        balloon_l = {**asset("I_DE_BALLOON"), "region_vars": roi_vars}
        mystery_l = {**asset("I_DE_MYSTERY"), "region_vars": roi_vars}
        defeated = asset(f"I_DE_DEFEAT_{slot}")
        slot_ready = [award, {"not": dialog}, {"not": reward}, {"not": jade_price}, expr(f"de_lantern == {slot}")]
        state(f"open_jade_box_{slot}", "scan_letters", [*slot_ready, jade_budget, box],
              click(f"C_DE_{slot}", delay=1000), advance("jade_box_quote", de_jade_box_started="elapsed_ms"))
        state(f"open_letter_{slot}", "scan_letters", [*slot_ready, {"not": box}, letter],
              click(f"C_DE_{slot}", delay=1000),
              advance("letter_open", de_letter_taps=0, de_letter_last_question="''", de_letter_started="elapsed_ms"))
        state(f"open_find_boss_lantern_{slot}", "scan_letters",
              [*slot_ready, expr("de_find_boss_lantern"), {"not": box}, {"not": letter}, find_boss_l],
              click(f"C_DE_{slot}", delay=1000), advance("boss", de_boss_lantern_found=True))
        state(f"open_realm_lantern_{slot}", "scan_letters",
              [*slot_ready, expr("de_battle_lanterns"), {"not": box}, {"not": letter}, {"not": defeated}, realm_l],
              click(f"C_DE_{slot}", delay=1000), advance("lantern_battle_enter"))
        state(f"skip_balloon_lantern_{slot}", "scan_letters",
              [*slot_ready, {"not": box}, {"not": letter}, balloon_l],
              {"inc": "de_lantern_balloon_hits"}, {"inc": "de_lantern"})
        state(f"skip_mystery_lantern_{slot}", "scan_letters",
              [*slot_ready, {"not": box}, {"not": letter}, mystery_l],
              {"inc": "de_lantern_mystery_hits"}, {"inc": "de_lantern"})
        state(f"next_slot_{slot}", "scan_letters", slot_ready, {"inc": "de_lantern"})
    state("letters_scanned", "scan_letters", [award, expr("de_lantern > 4")], advance("boss"))
    real_money = asset("I_BUY_RMB", "Component_Buy")
    amulet, sushi = asset("I_MYSTERY_AMULET"), asset("I_SUSHI")
    for name, allowed, title in (
        ("amulet", [amulet, {"not": sushi}], "神秘的符咒"),
        ("sushi", [sushi, {"not": amulet}, expr("de_jade_box_buy_sushi")], "100 点体力"),
    ):
        state(f"jade_box_buy_{name}", "jade_box_quote", [jade_price, {"not": real_money}, jade_budget, *allowed],
              click("I_JADE_50", delay=1000),
              advance("jade_box_settle", de_jade_box_spent="de_jade_box_spent + 50", de_jade_box_started="elapsed_ms"))
        raw["states"][-1].update(sensitive="花勾玉", desc=f"花费 50 勾玉购买逢魔宝箱中的{title}。")
    state("jade_box_cancel", "jade_box_quote", [jade_price, asset("I_DE_FIND")],
          click("I_DE_FIND", delay=1000), advance("jade_box_return", de_jade_box_started="elapsed_ms"))
    state("jade_box_quote_timeout", "jade_box_quote", [expr("elapsed_ms - de_jade_box_started >= 8000")],
          {"fail": "逢魔宝箱报价无法确认，未购买"})
    state("jade_box_reward", "jade_box_settle", [reward, {"not": jade_price}], reward_click,
          {"inc": "de_jade_box_rewards"}, advance("jade_box_return", de_jade_box_started="elapsed_ms"))
    state("jade_box_result_unknown", "jade_box_settle", [expr("elapsed_ms - de_jade_box_started >= 12000")],
          {"fail": "逢魔宝箱已提交购买，未识别奖励，停止后续购买"})
    state("jade_box_returned", "jade_box_return", [award, {"not": jade_price}, {"not": reward}, {"not": dialog}],
          {"inc": "de_lantern"}, advance("scan_letters"))
    state("jade_box_return_timeout", "jade_box_return", [expr("elapsed_ms - de_jade_box_started >= 8000")],
          {"fail": "逢魔宝箱弹窗关闭后未识别灯笼页面"})

    option_vars = [f"de_letter_option_{index}" for index in range(1, 4)]
    raw["vars"].update({name: "" for name in option_vars})
    question = {"quiz_answer": {"bank": ANSWER_BANK, "question": "DemonEncounter::O_LETTER_QUESTION",
        "options": [f"DemonEncounter::O_LETTER_ANSWER_{index}" for index in range(1, 4)],
        "option_vars": option_vars, "question_var": "de_letter_question", "answer_var": "de_letter_pick"}}
    state("letter_ready", "letter_open", [dialog], advance("letter_answer", de_letter_started="elapsed_ms"))
    state("letter_not_opened", "letter_open", [expr("elapsed_ms - de_letter_started >= 8000")],
          {"fail": "已点击逢魔密信灯笼，未识别答题界面"})
    state("letter_unknown_question", "letter_answer", [dialog, {"not": reward}, question,
          expr("de_letter_pick == 0")], {"fail": "逢魔密信题库缺少唯一匹配，未选答"})
    for index in range(1, 4):
        state(f"letter_pick_{index}", "letter_answer", [dialog, {"not": reward}, question,
              expr(f"de_letter_pick == {index} and de_letter_question != de_letter_last_question")],
              click(f"C_ANSWER_{index}", delay=750), {"inc": "de_letter_taps"},
              advance("letter_wait", de_letter_last_question="de_letter_question", de_letter_started="elapsed_ms"))
    state("letter_unreadable", "letter_answer", [expr("elapsed_ms - de_letter_started >= 8000")],
          {"fail": "逢魔密信题目或选项不可读"})
    state("letter_reward", "letter_wait", [reward], reward_click, {"inc": "de_letter_rewards"},
          advance("letter_after_reward"))
    state("letter_reward_still_open", "letter_after_reward", [reward], reward_click)
    state("letter_returned", "letter_after_reward", [award, {"not": dialog}], {"inc": "de_lantern"},
          advance("scan_letters"))
    state("letter_next_question", "letter_after_reward", [dialog, question,
          expr("de_letter_taps < 3 and de_letter_question != de_letter_last_question")],
          advance("letter_answer", de_letter_started="elapsed_ms"))
    state("letter_wait_incomplete", "letter_wait", [expr("elapsed_ms - de_letter_started >= 12000")],
          {"fail": "逢魔密信选答后缺少奖励反馈"})
    state("letter_followup_incomplete", "letter_after_reward", [expr("elapsed_ms - de_letter_started >= 18000")],
          {"fail": "逢魔密信奖励后缺少下一题或灯笼页面证据"})

    reset = _wire_battle(raw, body, contract, phase, advance, "de_battles", "de_wins", "after_battle")
    state("after_battle_lantern", "after_battle", [expr("de_in_lantern_battle")],
          advance("scan_letters", de_in_lantern_battle=False, de_lantern="de_lantern + 1"))
    state("after_battle_boss", "after_battle", [expr("not de_in_lantern_battle")], advance("exit"))

    state("lantern_battle_realm_fire", "lantern_battle_enter", [asset("I_DE_REALM_FIRE")],
          click("I_DE_REALM_FIRE", delay=1200), {"set": reset},
          advance("in_battle", de_in_lantern_battle=True, de_lantern_battles="de_lantern_battles + 1"))
    state("lantern_battle_small_fire", "lantern_battle_enter", [asset("I_DE_SMALL_FIRE")],
          click("I_DE_SMALL_FIRE", delay=1200), {"set": reset},
          advance("in_battle", de_in_lantern_battle=True, de_lantern_battles="de_lantern_battles + 1"))
    state("lantern_battle_back", "lantern_battle_enter", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", 1000), advance("scan_letters", de_lantern="de_lantern + 1"))

    state("boss_already_done", "boss", [{"any": [asset("I_BOSS_KILLED"), asset("I_BOSS_DONE_CHECK")]}],
          advance("exit", de_exit_reason="'boss_done'"))
    state("boss_clear_center_box", "boss", [asset("I_DE_BOX_CENTER")], click("I_DE_LOCATION", delay=1000))
    state("boss_crowded_cap", "boss", [expr("de_check_boss_people and de_crowded_skips >= de_max_crowded_skips")],
          advance("exit", de_exit_reason="'boss_crowded_exhausted'"))
    state("boss_crowded_normal", "boss",
          [expr("de_check_boss_people and not de_best_boss"), asset("I_BOSS_FIRE"), asset("I_UI_BACK_RED", "GlobalGame"),
           {"ocr": "DemonEncounter::O_DE_BOSS_PEOPLE", "mode": "counter_current", "var": "de_boss_people"},
           expr("de_boss_people >= 290")],
          click("I_UI_BACK_RED", "GlobalGame", 1000), {"inc": "de_crowded_skips"})
    state("boss_crowded_best", "boss",
          [expr("de_check_boss_people and de_best_boss"), asset("I_BEST_BOSS_FIRE"), asset("I_UI_BACK_RED", "GlobalGame"),
           {"ocr": "DemonEncounter::O_DE_BEST_BOSS_PEOPLE", "mode": "counter_current", "var": "de_boss_people"},
           expr("de_boss_people >= 290")],
          click("I_UI_BACK_RED", "GlobalGame", 1000), {"inc": "de_crowded_skips"})
    state("boss_fire_normal_gather", "boss",
          [expr("not de_best_boss and de_wait_boss_gather"), asset("I_BOSS_FIRE")],
          click("I_BOSS_FIRE", delay=1200), advance("boss_confirm_gather"))
    state("boss_fire_best_gather", "boss",
          [expr("de_best_boss and de_wait_boss_gather"), asset("I_BEST_BOSS_FIRE")],
          click("I_BEST_BOSS_FIRE", delay=1200), advance("boss_confirm_gather"))
    state("boss_fire_normal", "boss", [expr("not de_best_boss"), asset("I_BOSS_FIRE")],
          click("I_BOSS_FIRE", delay=1200), {"set": reset}, advance("in_battle"))
    state("boss_fire_best", "boss", [expr("de_best_boss"), asset("I_BEST_BOSS_FIRE")],
          click("I_BEST_BOSS_FIRE", delay=1200), {"set": reset}, advance("in_battle"))
    state("boss_search_exhausted", "boss", [expr("de_boss_searches >= de_boss_search_max")],
          advance("exit", de_exit_reason="'boss_not_found'"))
    state("boss_search_normal", "boss", [expr("not de_best_boss"), asset("I_DE_BOSS")],
          click("I_DE_BOSS", delay=1000), _click_from(docs, "C_DM_BOSS_CLICK", "DemonEncounter", 1000, recheck=False),
          {"inc": "de_boss_searches"})
    state("boss_search_best", "boss", [expr("de_best_boss"), asset("I_DE_BOSS_BEST")],
          click("I_DE_BOSS_BEST", delay=1000), _click_from(docs, "C_DM_BOSS_CLICK", "DemonEncounter", 1000, recheck=False),
          {"inc": "de_boss_searches"})

    # Boss confirm checkbox + gather / wait-respawn loop
    state("boss_gather_done", "boss_confirm_gather",
          [{"any": [asset("I_BOSS_DONE_CHECK"), asset("I_BOSS_KILLED")]}],
          advance("exit", de_exit_reason="'boss_done'"))
    state("boss_gather_battle_start", "boss_confirm_gather",
          [{"any": [asset("I_PREPARE_HIGHLIGHT", "Component_GeneralBattle"),
                    asset("I_BATTLE_INFO", "Component_GeneralBattle")]}],
          {"set": reset}, advance("in_battle"))
    state("boss_confirm_check_box", "boss_confirm_gather", [asset("I_BOSS_CONFIRM"), asset("I_BOSS_NO_SELECT")],
          click("I_BOSS_NO_SELECT", delay=800))
    state("boss_confirm_submit", "boss_confirm_gather", [asset("I_BOSS_CONFIRM")],
          click("I_BOSS_CONFIRM", delay=1000))
    state("boss_gather_wait", "boss_confirm_gather", [asset("I_BOSS_GATHER")],
          {"inc": "de_gather_waits"}, {"wait": 2000})
    state("boss_respawn_wait", "boss_confirm_gather", [asset("I_BOSS_WAIT")], {"wait": 2000})

    state("exit_done_target", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("de_next_open_delay_s > 0")],
          advance("stop_target", de_target_delay_s="de_next_open_delay_s", de_observed_ms="elapsed_ms"))
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "逢魔之时已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "DemonEncounter",
            "evidence": {"scope": "demon_encounter_bounded_flow"},
        }
    })
    state("exit_back_white", "exit", [asset("I_BOSS_BACK_WHITE")], click("I_BOSS_BACK_WHITE", delay=1200))
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))
    state("stop_target_done", "stop_target", [], {
        "stop": {
            "reason": "逢魔之时已按开放窗口预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "DemonEncounter",
                "delay_seconds_var": "de_target_delay_s",
                "observed_ms_var": "de_observed_ms",
            },
            "evidence": {"scope": "demon_encounter_window_schedule"},
        }
    })

    raw["oas_demon_encounter_contract"] = {
        "source": DEMON_ENCOUNTER_ENTRY,
        "source_pins": {**DEMON_ENCOUNTER_PINS, **ANSWER_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "demon_encounter_lantern_answer_and_boss_gather",
            "blocking": True,
            "requirement": "Verify letter positions, 50-jade box quotes and settlement on saved frames, and bind the "
                           "remaining lantern classes, O_DE_CHALLENGE_COUNT/O_DE_BOSS_PEOPLE OCR, and weekday boss preset",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
