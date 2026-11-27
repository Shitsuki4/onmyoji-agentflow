"""Pinned OAS Hunt, DemonRetreat, TrueOrochi, and Secret workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import bind_courtyard_buffs, compile_general_battle
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.oas_schedule import WAKE_WORKFLOWS
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


HUNT_ENTRY = "tasks/Hunt/script_task.py"
HUNT_PINS = {
    HUNT_ENTRY: "6082c0aa23294257de397175abb23c8b24a1bce45ec13e7234e4fadb5e7b0d6b",
    "tasks/Hunt/config.py": "f9fe289c74d834d6527a77f7c37d8b3ff49ae628524446b3a8f067a9aba495e6",
    "tasks/Hunt/assets.py": "522801b8905722743cc72b2c092936bfc714ed070aec4350084c1dab3e5e4692",
}

DEMON_RETREAT_ENTRY = "tasks/DemonRetreat/script_task.py"
DEMON_RETREAT_PINS = {
    DEMON_RETREAT_ENTRY: "19aa6fc3f841f583ad1fd6f9f99f886575fcccbb967dc05cb0caade2a1a37112",
    "tasks/DemonRetreat/config.py": "1ac7a38bd553ee512abe268b6177e6425b855ca6bae9014b8f1b092ecf071826",
    "tasks/DemonRetreat/assets.py": "edbae2307ad880a4ee605c453752494b27877aaa4825eb1ec7ce4ad95fa3b006",
}

TRUE_OROCHI_ENTRY = "tasks/TrueOrochi/script_task.py"
TRUE_OROCHI_PINS = {
    TRUE_OROCHI_ENTRY: "76020ae6163ec76b42977041b10062697f2ebfc54acf7d247a20c6661a04ea3f",
    "tasks/TrueOrochi/config.py": "8a2d242fbb5b9fb86ad660401cb9ab79e33c74827e21539f4830cd51bbd350ab",
    "tasks/TrueOrochi/assets.py": "92a49df34346a32831158961a5446c57f9b0d5037cb01209353f75aee4609f71",
}

SECRET_ENTRY = "tasks/Secret/script_task.py"
SECRET_PINS = {
    SECRET_ENTRY: "982f03dffe711ef58f9bda3b81fae4bf62f687abf85443edbde1d87ea76c8ba4",
    "tasks/Secret/config.py": "575e5985cb447a52c6729fb580d655c64c1d082aa98d433f445f047870536a37",
    "tasks/Secret/assets.py": "bfa64dfcc4d9d19c783fe3f22ee96c025ef72d5a472e24a2216894cf0c04be11",
}


def _verify_pins(source: Path, pins: dict[str, str], label: str) -> None:
    for rel, expected in pins.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"{label} source fingerprint mismatch: {rel}")


def _click_from(docs: dict, name: str, ns: str, delay: int = 1000) -> dict:
    spec = docs[ns][name]
    if spec["type"] == "click":
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    return {"click": target, "delay": delay, "recheck": True}


def compile_hunt_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Hunt (Kirin Mon-Thu / Netherworld Fri-Sun) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, HUNT_PINS, "Hunt")
    nav = compile_navigation_family(
        source, resources, prefix="hu_nav", destination="page_hunt",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="hu_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_hunt_natively_staged", title="狩猎战与阴界之门", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1800
    bind_schedule(source, raw)
    raw["params"].update(
        hu_in_window={"default": True},
        hu_kirin_day={"default": True},
        hu_limit_seconds={"default": 0, "min": 0, "max": 7200},
        hu_next_delay_s={"default": 0, "min": 0, "max": 172800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        hu_phase="entry", hu_nav_sub=0, hu_wins=0, hu_target_delay_s=0, hu_observed_ms=0, hu_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/Hunt.yaml",
        "upstream/oas/Component_GeneralInvite.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("Hunt", "Component_GeneralInvite", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"hu_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"hu_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"hu_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Hunt"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="Hunt", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("outside_window", "entry", [expr("not hu_in_window")],
          advance("done", hu_exit_reason="'outside_window'",
                  hu_target_delay_s="hu_next_delay_s", hu_observed_ms="elapsed_ms"))
    bind_task_presets(raw, source, resources, prefix="hu", resume="route_mode", category="hunt")
    next(step for step in raw["states"] if step["id"] == "hu_nav_returned")["when"]["all"].append(phase("unused"))
    next(step for step in raw["states"] if step["id"] == "hu_nav_drive")["when"] = phase("unused")

    state("route_kirin", "route_mode", [expr("hu_kirin_day")], advance("nav_kirin", hu_nav_sub=0))
    state("route_netherworld", "route_mode", [expr("not hu_kirin_day")], advance("nav_nw", hu_nav_sub=0))

    kirin_page = raw["navigation"]["pages"]["page_hunt_kirin"]["when"]
    hunt_page = raw["navigation"]["pages"]["page_hunt"]["when"]
    state("kirin_arrived", "nav_kirin", [kirin_page, expr("hu_nav_sub == 1")], advance("kirin_enter"))
    state("kirin_drive", "nav_kirin", [], {"navigate": {"destination": "page_hunt_kirin", "done_var": "hu_nav_sub"}})
    state("nw_arrived", "nav_nw", [hunt_page, expr("hu_nav_sub == 1")], advance("nw_enter"))
    state("nw_drive", "nav_nw", [], {"navigate": {"destination": "page_hunt", "done_var": "hu_nav_sub"}})

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}

    # Kirin entry
    state("kirin_time_limit", "kirin_enter",
          [expr("hu_limit_seconds > 0 and elapsed_ms >= hu_limit_seconds * 1000")],
          advance("done", hu_exit_reason="'time_limit'",
                  hu_target_delay_s="hu_next_delay_s", hu_observed_ms="elapsed_ms"))
    state("kirin_battle_ready", "kirin_enter", [asset("I_PREPARE_HIGHLIGHT", "Component_GeneralBattle")],
          {"set": reset}, advance("battle"))
    state("kirin_confirm", "kirin_enter", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 900))
    state("kirin_confirm_small", "kirin_enter", [asset("I_UI_CONFIRM_SAMLL", "GlobalGame")],
          click("I_UI_CONFIRM_SAMLL", "GlobalGame", 900))
    state("kirin_challenge", "kirin_enter", [asset("I_KIRIN_CHALLAGE")], click("I_KIRIN_CHALLAGE", "Hunt", 1500))
    state("kirin_start", "kirin_enter", [asset("I_KIRIN_START_CHALLAGE")],
          click("I_KIRIN_START_CHALLAGE", "Hunt", 2500))
    state("kirin_already_end", "kirin_enter", [asset("I_KIRIN_END")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000), advance("done", hu_exit_reason="'kirin_already_done'"))

    # Netherworld entry
    state("nw_time_limit", "nw_enter",
          [expr("hu_limit_seconds > 0 and elapsed_ms >= hu_limit_seconds * 1000")],
          advance("done", hu_exit_reason="'time_limit'",
                  hu_target_delay_s="hu_next_delay_s", hu_observed_ms="elapsed_ms"))
    state("nw_room_fire", "nw_enter", [asset("I_FIRE", "Component_GeneralInvite")],
          click("I_FIRE", "Component_GeneralInvite", 1000), {"set": reset}, advance("battle"))
    state("nw_icon", "nw_enter", [asset("I_NW")], click("I_NW", "Hunt", 900))
    state("nw_confirm", "nw_enter", [asset("I_UI_CONFIRM", "GlobalGame")], click("I_UI_CONFIRM", "GlobalGame", 900))
    state("nw_challenge", "nw_enter", [asset("I_NW_CHALLAGE")], click("I_NW_CHALLAGE", "Hunt", 1500))
    state("nw_already_done", "nw_enter", [asset("I_NW_DONE")],
          click("I_UI_BACK_RED", "GlobalGame", 1000), advance("done", hu_exit_reason="'nw_already_done'"))

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("done", hu_wins=f"hu_wins + {outputs['win']}",
                                       hu_target_delay_s="hu_next_delay_s", hu_observed_ms="elapsed_ms",
                                       hu_exit_reason="'battle_done'")]
        raw["states"].append(step)

    state("complete_target", "done", [expr("hu_target_delay_s > 0")], {
        "stop": {
            "reason": "狩猎战/阴界之门已完成并按麒麟/阴界日程预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "Hunt",
                "delay_seconds_var": "hu_target_delay_s",
                "observed_ms_var": "hu_observed_ms",
            },
            "evidence": {"scope": "hunt_weekday_target_schedule"},
        }
    })
    state("complete", "done", [], {
        "stop": {
            "reason": "狩猎战/阴界之门已完成",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Hunt",
            "evidence": {"scope": "hunt_native_path"},
        }
    })

    raw["oas_hunt_contract"] = {
        "source": HUNT_ENTRY,
        "source_pins": {**HUNT_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"], {
            "id": "hunt_schedule_and_live",
            "blocking": True,
            "requirement": "Bind Kirin/Netherworld weekday custom_next_run times and verify live battle entries",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_demon_retreat_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS DemonRetreat (Saturday boss retreat) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, DEMON_RETREAT_PINS, "DemonRetreat")
    nav = compile_navigation_family(
        source, resources, prefix="dr_nav", destination="page_guild",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="dr_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_demon_retreat_natively_staged", title="首领退治", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1800
    bind_schedule(source, raw)
    raw["params"].update(
        dr_is_saturday={"default": True},
        dr_max_rounds={"default": 1, "min": 1, "max": 3},
        dr_limit_seconds={"default": 0, "min": 0, "max": 7200},
        dr_next_saturday_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        dr_phase="entry", dr_hunt_taps=0, dr_rounds=0, dr_wins=0, dr_main_arrived=0,
        dr_target_delay_s=0, dr_observed_ms=0, dr_reward_claimed=False, dr_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/DemonRetreat.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("DemonRetreat", "GlobalGame")}
    later_roi = docs["DemonRetreat"]["O_LATER_ENTER_CHECK"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"dr_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"dr_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"dr_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="DemonRetreat", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, ns="DemonRetreat", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("not_saturday_target", "entry", [expr("not dr_is_saturday and dr_next_saturday_delay_s > 0")],
          advance("stop_target", dr_target_delay_s="dr_next_saturday_delay_s",
                  dr_observed_ms="elapsed_ms", dr_exit_reason="'not_saturday'"))
    state("not_saturday", "entry", [expr("not dr_is_saturday")], {
        "stop": {
            "reason": "今日非周六，跳过首领退治",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "DemonRetreat",
            "evidence": {"scope": "demon_retreat_not_saturday"},
        }
    })
    bind_task_presets(raw, source, resources, prefix="dr", resume="navigate", category="demon_retreat")

    arrived = next(step for step in raw["states"] if step["id"] == "dr_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_shrine", dr_hunt_taps=0)]
    next(step for step in raw["states"] if step["id"] == "dr_nav_drive")["when"] = phase("navigate")

    # Enter shrine -> hunt (max 5 attempts)
    ready_seen = {"any": [asset("I_HUNT_CHECK"), asset("I_DEMON_GATHER"),
                          asset("I_PREPARE_HIGHLIGHT", "Component_GeneralBattle")]}
    state("enter_time_limit", "enter_shrine",
          [expr("dr_limit_seconds > 0 and elapsed_ms >= dr_limit_seconds * 1000")],
          advance("exit_main", dr_exit_reason="'time_limit'", dr_main_arrived=0))
    state("entered_retreat", "enter_shrine", [ready_seen], advance("check_gather"))
    state("late_reward_only", "enter_shrine", [asset("I_REWARD_ALL")],
          click("I_REWARD_ALL", "DemonRetreat", 1000),
          advance("exit_main", dr_reward_claimed=True, dr_exit_reason="'already_challenged'", dr_main_arrived=0))
    state("enter_fail_limit", "enter_shrine", [expr("dr_hunt_taps >= 5")],
          advance("exit_main", dr_exit_reason="'enter_failed'", dr_main_arrived=0))
    state("enter_quit_back", "enter_shrine", [asset("I_QUIT_BACK")], click("I_QUIT_BACK", "DemonRetreat", 1000))
    state("enter_shrine_tap", "enter_shrine", [asset("I_SHRINE")], click("I_SHRINE", "DemonRetreat", 1000))
    state("enter_hunt_tap", "enter_shrine", [asset("I_HUNT")],
          click("I_HUNT", "DemonRetreat", 1500), {"inc": "dr_hunt_taps"})
    state("enter_rank_back", "enter_shrine", [asset("I_RANK_LSIT"), asset("I_DEMON_BACK_CHECK")],
          click("I_DEMON_BACK_CHECK", "DemonRetreat", 1000))

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    state("gather_time_limit", "check_gather",
          [expr("dr_limit_seconds > 0 and elapsed_ms >= dr_limit_seconds * 1000")],
          advance("exit_main", dr_exit_reason="'time_limit'", dr_main_arrived=0))
    state("gather_wait", "check_gather",
          [{"ocr_full": {"region": later_roi, "keyword": "集结", "evidence": "complete_keyword"}}, asset("I_DEMON_GATHER")], {"wait": 1000})
    state("gather_started", "check_gather",
          [{"ocr_full": {"region": later_roi, "keyword": "集结", "evidence": "complete_keyword"}}, {"not": asset("I_DEMON_GATHER")}],
          {"set": reset}, advance("battle"))
    state("late_enter_fire", "check_gather", [asset("I_ENTER_FIRE")],
          click("I_ENTER_FIRE", "DemonRetreat", 1000), {"set": reset}, advance("battle"))
    state("direct_to_battle", "check_gather", [], {"set": reset}, advance("battle"))

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("after_round", dr_rounds="dr_rounds + 1",
                                       dr_wins=f"dr_wins + {outputs['win']}")]
        raw["states"].append(step)

    state("after_round_time_limit", "after_round",
          [expr("dr_limit_seconds > 0 and elapsed_ms >= dr_limit_seconds * 1000")],
          advance("exit_main", dr_exit_reason="'time_limit'", dr_main_arrived=0))
    state("after_round_next", "after_round", [expr("dr_rounds < dr_max_rounds")], advance("check_gather"))
    state("after_round_done", "after_round", [expr("dr_rounds >= dr_max_rounds")], advance("claim_reward"))

    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    state("claim_reward_popup", "claim_reward", [reward],
          click("C_UI_REWARD", "GlobalGame", 400),
          advance("exit_main", dr_reward_claimed=True, dr_exit_reason="'claimed'", dr_main_arrived=0))
    state("claim_reward_all", "claim_reward", [asset("I_REWARD_ALL")],
          click("I_REWARD_ALL", "DemonRetreat", 1500),
          advance("exit_main", dr_reward_claimed=True, dr_exit_reason="'claimed'", dr_main_arrived=0))
    state("claim_no_reward_rank", "claim_reward", [asset("I_RANK_LSIT"), asset("I_DEMON_BACK_CHECK")],
          click("I_DEMON_BACK_CHECK", "DemonRetreat", 1000),
          advance("exit_main", dr_exit_reason="'no_reward'", dr_main_arrived=0))
    state("claim_pray", "claim_reward", [asset("I_PRAY")], click("I_PRAY", "DemonRetreat", 1000))
    state("claim_hunt", "claim_reward", [asset("I_HUNT")], click("I_HUNT", "DemonRetreat", 1000))

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main_target", "exit_main",
          [court, expr("dr_main_arrived == 1 and dr_next_saturday_delay_s > 0")],
          advance("stop_target", dr_target_delay_s="dr_next_saturday_delay_s", dr_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "首领退治已按周六排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "DemonRetreat",
                "delay_seconds_var": "dr_target_delay_s",
                "observed_ms_var": "dr_observed_ms",
            },
            "evidence": {"scope": "demon_retreat_saturday_target"},
        }
    })
    state("returned_main", "exit_main", [court, expr("dr_main_arrived == 1")], {
        "stop": {
            "reason": "首领退治已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "DemonRetreat",
            "evidence": {"scope": "demon_retreat_native_path"},
        }
    })
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": "dr_main_arrived"}})

    raw["oas_demon_retreat_contract"] = {
        "source": DEMON_RETREAT_ENTRY,
        "source_pins": {**DEMON_RETREAT_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"], {
            "id": "demon_retreat_saturday_schedule_and_live",
            "blocking": True,
            "requirement": "Bind Saturday custom_next_run calculation and verify 3-round prepare/reward live frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_true_orochi_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS TrueOrochi workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, TRUE_OROCHI_PINS, "TrueOrochi")
    nav = compile_navigation_family(
        source, resources, prefix="to_nav", destination="page_gameplay",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="to_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name=WAKE_WORKFLOWS["TrueOrochi"], title="真八岐大蛇", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"]["oas_success_seconds"]["default"] = 259200
    raw["params"].update(
        to_find_true_orochi={"default": True},
        to_select_layer_ten={"default": False},
        to_max_true_runs={"default": 1, "min": 1, "max": 2},
        to_limit_seconds={"default": 0, "min": 0, "max": 7200},
        to_next_monday_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        to_phase="check_gameplay", to_nav_sub=0, to_orochi_runs=0, to_true_runs=0,
        to_layer="拾层", to_layer_ready=False, to_target_delay_s=0, to_observed_ms=0, to_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/TrueOrochi.yaml",
        "upstream/oas/Orochi.yaml",
        "upstream/oas/Component_GeneralRoom.yaml",
        "upstream/oas/Component_GeneralInvite.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("TrueOrochi", "Orochi", "Component_GeneralBattle", "Component_GeneralRoom", "Component_GeneralInvite", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"to_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"to_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"to_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="TrueOrochi"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="TrueOrochi", delay=1000):
        return _click_from(docs, name, ns, delay)

    # Check page_gameplay for I_ST_MODULE (weekly attempts remaining)
    arrived = next(step for step in raw["states"] if step["id"] == "to_nav_returned")
    arrived["when"]["all"].append(phase("check_gameplay"))
    arrived["do"] = [advance("inspect_module")]
    next(step for step in raw["states"] if step["id"] == "to_nav_drive")["when"] = phase("check_gameplay")

    state("no_weekly_attempts", "inspect_module", [{"not": asset("I_ST_MODULE")}],
          advance("done", to_exit_reason="'weekly_done'"))
    state("module_present", "inspect_module", [asset("I_ST_MODULE")], advance("entry"))
    bind_task_presets(raw, source, resources, prefix="to", resume="goto_orochi", category="true_orochi")

    orochi_page = raw["navigation"]["pages"]["page_orochi"]["when"]
    state("orochi_arrived", "goto_orochi", [orochi_page, expr("to_nav_sub == 1")], advance("check_ts"))
    state("orochi_drive", "goto_orochi", [], {"navigate": {"destination": "page_orochi", "done_var": "to_nav_sub"}})

    # Check I_FIND_TS or select Layer.TEN + unlock team + farm up to 10 Orochi-10 runs
    from .oas_zone_farming import LIST_PINS, _bind_layer_list, _layer_list

    _verify_pins(source, LIST_PINS, "TrueOrochi")
    orochi_layers = ("壹层", "贰层", "叁层", "肆层", "伍层", "陆层", "柒层", "捌层", "玖层", "拾层", "悲鸣", "神罚", "虚无")
    roi, size, labels = _layer_list(source, "Orochi", docs["Orochi"]["LIST_LAYER_LIST"], orochi_layers)
    _bind_layer_list(
        raw, state, advance, prefix="to",
        panel={"any": [asset("I_OROCHI_FIRE", "Orochi"), asset("I_OROCHI_LOCK", "Orochi"), asset("I_OROCHI_UNLOCK", "Orochi")]},
        roi=roi, size=size, labels=labels, confirm_phase="unlock_layer_ten",
    )
    state("unlock_layer_ten_tap", "unlock_layer_ten", [asset("I_OROCHI_LOCK", "Orochi")],
          click("I_OROCHI_LOCK", "Orochi", 1000))
    state("unlock_layer_ten_done", "unlock_layer_ten", [{"not": asset("I_OROCHI_LOCK", "Orochi")}],
          advance("check_ts", to_layer_ready=True))

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    state("check_ts_time_limit", "check_ts",
          [expr("to_limit_seconds > 0 and elapsed_ms >= to_limit_seconds * 1000")],
          advance("done", to_exit_reason="'time_limit'"))
    state("ts_found", "check_ts", [asset("I_FIND_TS")], advance("open_ts_room"))
    state("ts_not_found_no_farm", "check_ts", [{"not": asset("I_FIND_TS")}, expr("not to_find_true_orochi")],
          advance("done", to_exit_reason="'not_found'"))
    state("ts_select_layer_ten", "check_ts", [
        {"not": asset("I_FIND_TS")}, expr("to_select_layer_ten and not to_layer_ready"),
    ], advance("layer_probe"))
    state("ts_farm_pet_present", "check_ts",
          [{"not": asset("I_FIND_TS")}, asset("I_PET_PRESENT", "Orochi")],
          click("C_WIN_3", "Component_GeneralBattle", 1000))
    state("ts_farm_limit", "check_ts", [{"not": asset("I_FIND_TS")}, expr("to_orochi_runs >= 10")],
          advance("done", to_exit_reason="'farm_10_not_found'"))
    state("ts_farm_orochi_fire", "check_ts",
          [{"not": asset("I_FIND_TS")}, asset("I_OROCHI_FIRE", "Orochi")],
          click("I_OROCHI_FIRE", "Orochi", 1000), {"set": reset},
          advance("orochi_battle", to_orochi_runs="to_orochi_runs + 1"))

    for step in body["states"]:
        step["when"] = {"all": [phase("orochi_battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("check_ts")]
        raw["states"].append(step)

    # True Orochi room creation -> ensure_private -> fire -> auto -> greed_ghost completion
    state("ts_room_opened", "open_ts_room", [asset("I_ST_CREATE_ROOM")], advance("ensure_private"))
    state("ts_open_confirm", "open_ts_room", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("ts_open_fire", "open_ts_room", [asset("I_ST_FIRE")], click("I_ST_FIRE", "TrueOrochi", 4000))
    state("ts_open_find", "open_ts_room", [asset("I_FIND_TS")], click("I_FIND_TS", "TrueOrochi", 1000))

    priv_on = {"any": [asset("I_ENSURE_PRIVATE", "Component_GeneralRoom"),
                       asset("I_ENSURE_PRIVATE_2", "Component_GeneralRoom")]}
    state("priv_ok", "ensure_private", [priv_on], advance("enter_ts_battle"))
    state("priv_tap_1", "ensure_private", [asset("I_ENSURE_PRIVATE_FALSE", "Component_GeneralRoom")],
          click("I_ENSURE_PRIVATE_FALSE", "Component_GeneralRoom", 1000))
    state("priv_tap_2", "ensure_private", [asset("I_ENSURE_PRIVATE_FALSE_2", "Component_GeneralRoom")],
          click("I_ENSURE_PRIVATE_FALSE_2", "Component_GeneralRoom", 1000))

    state("ts_prepare_seen", "enter_ts_battle", [asset("I_ST_FIRE_PREPARE")],
          click("I_ST_FIRE_PREPARE", "TrueOrochi", 1000), advance("ts_auto"))
    state("ts_fire_btn", "enter_ts_battle", [asset("I_FIRE", "Component_GeneralInvite")],
          click("I_FIRE", "Component_GeneralInvite", 3000))
    state("ts_enter_confirm", "enter_ts_battle", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("ts_create_room_tap", "enter_ts_battle", [asset("I_ST_CREATE_ROOM")],
          click("I_ST_CREATE_ROOM", "TrueOrochi", 1000))

    state("ts_auto_toggle", "ts_auto", [asset("I_BUFF", "Component_GeneralBattle"), asset("I_ST_AUTO_FALSE")],
          click("I_ST_AUTO_FALSE", "TrueOrochi", 1800))
    state("ts_auto_started", "ts_auto", [{"not": asset("I_BUFF", "Component_GeneralBattle")}],
          advance("ts_fight"))

    state("ts_fight_time_limit", "ts_fight",
          [expr("to_limit_seconds > 0 and elapsed_ms >= to_limit_seconds * 1000")],
          advance("done", to_exit_reason="'time_limit'"))
    state("ts_fight_greed_done", "ts_fight", [asset("I_GREED_GHOST", "Component_GeneralBattle")],
          click("I_GREED_GHOST", "Component_GeneralBattle", 1000),
          advance("ts_close_greed", to_true_runs="to_true_runs + 1"))
    state("ts_fight_frame", "ts_fight", [asset("I_ST_FRAME")], click("I_ST_FRAME", "TrueOrochi", 1000))
    state("ts_fight_wait", "ts_fight", [], {"wait": 500})

    state("ts_greed_closed_check_second", "ts_close_greed", [
        {"not": asset("I_GREED_GHOST", "Component_GeneralBattle")},
        expr("to_true_runs < to_max_true_runs"),
    ], advance("goto_orochi_second", to_nav_sub=0))
    state("ts_greed_closed", "ts_close_greed", [{"not": asset("I_GREED_GHOST", "Component_GeneralBattle")}],
          advance("done", to_exit_reason="'true_orochi_done'"))
    state("ts_greed_tap", "ts_close_greed", [asset("I_GREED_GHOST", "Component_GeneralBattle")],
          click("I_GREED_GHOST", "Component_GeneralBattle", 1000))

    # Optional second stored True Orochi entry check after returning to page_orochi
    state("second_orochi_arrived", "goto_orochi_second", [orochi_page, expr("to_nav_sub == 1")],
          advance("check_ts_second"))
    state("second_orochi_drive", "goto_orochi_second", [],
          {"navigate": {"destination": "page_orochi", "done_var": "to_nav_sub"}})
    state("ts_second_found", "check_ts_second", [asset("I_FIND_TS")], advance("open_ts_room"))
    state("ts_second_absent", "check_ts_second", [{"not": asset("I_FIND_TS")}],
          advance("done", to_exit_reason="'second_entry_absent'"))

    state("complete_target_prep", "done", [expr("to_next_monday_delay_s > 0")],
          advance("stop_target", to_target_delay_s="to_next_monday_delay_s", to_observed_ms="elapsed_ms"))
    state("complete_target", "stop_target", [], {
        "stop": {
            "reason": "真八岐大蛇已完成，已按每周一排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "TrueOrochi",
                "delay_seconds_var": "to_target_delay_s",
                "observed_ms_var": "to_observed_ms",
            },
            "evidence": {"scope": "true_orochi_monday_target"},
        }
    })
    state("complete", "done", [], {
        "stop": {
            "reason": "真八岐大蛇已完成",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "TrueOrochi",
            "evidence": {"scope": "true_orochi_native_path"},
        }
    })

    raw["oas_true_orochi_contract"] = {
        "source": TRUE_OROCHI_ENTRY,
        "source_pins": {**TRUE_OROCHI_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"], {
            "id": "true_orochi_layer10_select_and_second_stored_entry",
            "blocking": True,
            "requirement": "Bind Orochi Layer.TEN selection, second stored entry loop, and live 10-stage frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_secret_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Secret (weekly secret zone) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, SECRET_PINS, "Secret")
    nav = compile_navigation_family(
        source, resources, prefix="se_nav", destination="page_secret_zones",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="se_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_secret_natively_staged", title="秘闻副本", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"]["oas_success_seconds"]["default"] = 604800
    raw["params"].update(
        se_monday_before_8={"default": False},
        se_monday_open_delay_s={"default": 0, "min": 0, "max": 86400},
        se_next_monday_delay_s={"default": 0, "min": 0, "max": 604800},
        se_limit_seconds={"default": 0, "min": 0, "max": 3600},
        se_gold_50={"default": False},
        se_gold_100={"default": False},
        se_layer_9={"default": False},
        se_layer_10={"default": False},
        se_check_layer_ocr={"default": False},
        se_max_battles={"default": 10, "min": 1, "max": 20},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        se_phase="entry", se_battles=0, se_wins=0, se_swipes=0, se_main_arrived=0, se_exit_reason="",
        se_jade=0, se_gold=0, se_current_layer=0, se_total_time=-1, se_target_delay_s=0, se_observed_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/Secret.yaml",
        "upstream/oas/WeeklyTrifles.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("Secret", "WeeklyTrifles", "GlobalGame")}
    no_pass_roi = docs["Secret"]["O_SE_NO_PASS"]["roi"]
    no_pass_last_roi = docs["Secret"]["O_SE_NO_PASS_LAST"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"se_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"se_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"se_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Secret"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="Secret", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("monday_before_8_target", "entry", [expr("se_monday_before_8 and se_monday_open_delay_s > 0")],
          advance("stop_target", se_target_delay_s="se_monday_open_delay_s",
                  se_observed_ms="elapsed_ms", se_exit_reason="'monday_before_8'"))
    state("monday_before_8", "entry", [expr("se_monday_before_8")], {
        "stop": {
            "reason": "周一8点前暂不挑战秘闻",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Secret",
            "evidence": {"scope": "secret_monday_gate"},
        }
    })
    bind_task_presets(raw, source, resources, prefix="se", resume="buff_before", category="secret")
    se_buff_ops = [("gold_50", "se_gold_50"), ("gold_100", "se_gold_100")]
    se_buff_expr = "(se_gold_50 or se_gold_100)"
    buff_calls = [
        bind_courtyard_buffs(
            raw, source, resources, prefix=f"se_buff_{leg}", phase_var="se_phase",
            entry_phase=f"buff_{leg}", resume=resume, operations=se_buff_ops,
            enable_param=se_buff_expr, opening=opening,
        )
        for leg, opening, resume in (("before", True, "navigate"), ("after", False, "finished"))
    ]

    arrived = next(step for step in raw["states"] if step["id"] == "se_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_zone")]
    next(step for step in raw["states"] if step["id"] == "se_nav_drive")["when"] = phase("navigate")

    state("zone_entered", "enter_zone", [asset("I_SE_FIRE")], advance("check_placement"))
    state("zone_enter_tap", "enter_zone", [asset("I_SE_ENTER")], click("I_SE_ENTER", "Secret", 1000))
    state("placement_ok", "check_placement", [asset("I_SE_PLACEMENT")], advance("find_layer", se_swipes=0))
    state("placement_missing", "check_placement", [{"not": asset("I_SE_PLACEMENT")}],
          advance("exit_zone", se_exit_reason="'no_placement'"))

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    state("finished_marker", "find_layer", [asset("I_SE_FINISHED_1")],
          advance("exit_zone", se_exit_reason="'finished_1'"))
    state("finished_weekly_share", "find_layer", [asset("I_WT_SE_SHARE", "WeeklyTrifles")],
          advance("exit_zone", se_exit_reason="'weekly_share_visible'"))
    state("time_limit_exit", "find_layer", [expr("se_limit_seconds > 0 and elapsed_ms >= se_limit_seconds * 1000")],
          advance("exit_zone", se_exit_reason="'time_limit'"))
    state("battle_count_limit", "find_layer", [expr("se_battles >= se_max_battles")],
          advance("exit_zone", se_exit_reason="'max_battles'"))
    # Optional OCR layer-9 / layer-10 gating via O_SE_JADE (jade = layer * 7) and O_SE_GOLD (layer 1)
    state("layer_9_gated", "find_layer",
          [expr("se_check_layer_ocr and not se_layer_9"), asset("I_SE_FIRE"),
           {"ocr": "Secret::O_SE_JADE", "var": "se_jade", "test": "se_jade == 63"}],
          advance("exit_zone", se_current_layer=9, se_exit_reason="'layer_9_disabled'"))
    state("layer_10_gated", "find_layer",
          [expr("se_check_layer_ocr and not se_layer_10"), asset("I_SE_FIRE"),
           {"ocr": "Secret::O_SE_JADE", "var": "se_jade", "test": "se_jade == 70"}],
          advance("exit_zone", se_current_layer=10, se_exit_reason="'layer_10_disabled'"))
    state("pick_no_pass_layer1_gold", "find_layer",
          [expr("se_check_layer_ocr"), asset("I_SE_FIRE"),
           {"ocr_full": {"region": no_pass_roi, "keyword": "未通关", "evidence": "complete_keyword"}},
           {"ocr": "Secret::O_SE_GOLD", "var": "se_gold", "test": "se_gold == 10000 or se_gold == 18000"}],
          {"click_found": True, "delay": 1000, "recheck": True},
          advance("fire_battle", se_current_layer=1))
    state("pick_no_pass", "find_layer",
          [asset("I_SE_FIRE"), {"ocr_full": {"region": no_pass_roi, "keyword": "未通关", "evidence": "complete_keyword"}}],
          {"click_found": True, "delay": 1000, "recheck": True}, advance("fire_battle"))
    state("pick_no_pass_last", "find_layer",
          [asset("I_SE_FIRE"), {"ocr_full": {"region": no_pass_last_roi, "keyword": "未通关", "evidence": "complete_keyword"}}],
          {"click_found": True, "delay": 1000, "recheck": True}, advance("fire_battle"))
    state("weekly_total_time_cleared", "find_layer",
          [expr("se_check_layer_ocr"), asset("I_SE_FIRE"),
           {"ocr": "Secret::O_SE_TOTAL_TIME", "mode": "duration_seconds", "var": "se_total_time",
            "test": "se_total_time > 0"}],
          advance("exit_zone", se_exit_reason="'total_time_cleared'"))
    state("swipe_limit", "find_layer", [expr("se_swipes >= 8")],
          advance("exit_zone", se_exit_reason="'no_unpassed_layer'"))
    state("swipe_down", "find_layer", [asset("I_SE_FIRE")],
          {"swipe": "Secret::S_SE_DOWN_SEIPE", "delay": 2000, "recheck": True}, {"inc": "se_swipes"})

    state("fire_tap", "fire_battle", [asset("I_SE_FIRE")],
          click("I_SE_FIRE", "Secret", 1000), {"set": reset},
          advance("battle", se_battles="se_battles + 1"))
    state("fire_entered", "fire_battle", [{"not": asset("I_SE_FIRE")}],
          {"set": reset}, advance("battle", se_battles="se_battles + 1"))

    state("secret_battle_win", "battle", [asset("I_SE_BATTLE_WIN")],
          click("I_SE_BATTLE_WIN", "Secret", 2000),
          advance("find_layer", se_wins="se_wins + 1", se_swipes=0))
    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("find_layer", se_wins=f"se_wins + {outputs['win']}", se_swipes=0)]
        raw["states"].append(step)

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("exit_blue", "exit_zone", [asset("I_UI_BACK_BLUE", "GlobalGame")],
          click("I_UI_BACK_BLUE", "GlobalGame", 1000))
    state("exit_yellow", "exit_zone", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000))
    state("exit_returned_main", "exit_zone", [court], advance("buff_after"))
    state("finished_target_prep", "finished", [expr("se_next_monday_delay_s > 0")],
          advance("stop_target", se_target_delay_s="se_next_monday_delay_s", se_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "秘闻副本已按周一08:00排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "Secret",
                "delay_seconds_var": "se_target_delay_s",
                "observed_ms_var": "se_observed_ms",
            },
            "evidence": {"scope": "secret_monday_target"},
        }
    })
    state("finished", "finished", [], {
        "stop": {
            "reason": "秘闻副本已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Secret",
            "evidence": {"scope": "secret_native_path"},
        }
    })

    raw["oas_secret_contract"] = {
        "source": SECRET_ENTRY,
        "source_pins": {**SECRET_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "buff_calls": buff_calls,
        "source_obligations": [
            *nav["source_obligations"], *battle["source_obligations"],
            *(ob for call in buff_calls for ob in call["source_obligations"]),
            {
                "id": "secret_live_layer_ocr_and_buff",
                "blocking": True,
                "requirement": "Verify relative-ROI jade/gold/total-time OCR and courtyard gold buff toggles on live Secret frames",
            },
        ],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
