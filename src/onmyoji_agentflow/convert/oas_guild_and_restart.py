"""Pinned OAS AbyssShadows, CollectiveMissions, KekkaiActivation, and Restart workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import compile_general_battle
from .oas_kekkai_growth import bind_growth
from .oas_login import compile_android_login
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


ABYSS_ENTRY = "tasks/AbyssShadows/script_task.py"
ABYSS_PINS = {
    ABYSS_ENTRY: "103726e900a86f4c33ed7a6e4d0dc4d05b8a85b01a9c53f36b03ebefeea76f7a",
    "tasks/AbyssShadows/config.py": "a938503712984f9945f3cd62ce598316e85b07275df2aa2045370a96fb29ee94",
    "tasks/AbyssShadows/assets.py": "4f2acef2fee5eb81567dee60c0ad417724332546178689998b72f7f67a356a0a",
}

CM_ENTRY = "tasks/CollectiveMissions/script_task.py"
CM_PINS = {
    CM_ENTRY: "73a2ee5740cab07082f999ed0b1f37a13deba04c4fdcafa2f9b372f0aaf9c860",
    "tasks/CollectiveMissions/config.py": "08305ff95fb3cf92f11330c38111c147206c40f6ad8de204ffd319ba53def702",
    "tasks/CollectiveMissions/assets.py": "8160b98a6025331d97f8d1c5657d780bbc8a272fe4fc4be740467ac62d831e88",
}

KA_ENTRY = "tasks/KekkaiActivation/script_task.py"
KA_PINS = {
    KA_ENTRY: "5ec011ffcc309e2e6b34e8cf3a4dcfa27dd339a6860784ea7f367f458f88f389",
    "tasks/KekkaiActivation/config.py": "fb6725b2578740c7b7900c0e2aeca2afb31e7ef2ba985e912ce917599723da09",
    "tasks/KekkaiActivation/assets.py": "b41764ccef1bc5e5371e5573143c5186aec1ab615820267abab5254969cc2894",
    "tasks/KekkaiActivation/utils.py": "a63d4e927f103cf268faf7e831ae3e5ebc9fc69208dfc51ef8486f6d92d2c53b",
}

RESTART_ENTRY = "tasks/Restart/script_task.py"
RESTART_PINS = {
    RESTART_ENTRY: "6fc4837173e82fd0a09c9f0a51aa14bee88731375263660b9a6ea81b050bf71c",
    "tasks/Restart/config.py": "bc92434709551f962391d14d29266975c4ef695aad4190e7cb7462cce7fdbc44",
    "tasks/Restart/config_scheduler.py": "4d8e8f6af0c0dcee7126a4523e030da23876b3948579a8d4c5fa3b00ea007555",
    "tasks/Restart/login.py": "6b3c533e7e18af586c415bfad758316c5860d9cddb4b9f0d5b009629e27e4513",
    "tasks/Restart/assets.py": "e0f9345c7c4ff075d970dcf3916332801ff0ee07d222738de865363d302922ff",
}


def _verify_pins(source: Path, pins: dict[str, str], label: str) -> None:
    for rel, expected in pins.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"{label} source fingerprint mismatch: {rel}")


def _click_from(docs: dict, name: str, ns: str, delay: int = 1000, *,
                press_ms: int | None = None, recheck: bool = True) -> dict:
    spec = docs[ns][name]
    if spec["type"] in ("click", "long_click"):
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    out = {"click": target, "delay": delay, "recheck": recheck}
    hold = spec.get("press_ms") if press_ms is None else press_ms
    if hold is not None:
        out["press_ms"] = hold
    return out


def compile_abyss_shadows_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS AbyssShadows (Fri-Sun guild shadows) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, ABYSS_PINS, "AbyssShadows")
    nav = compile_navigation_family(
        source, resources, prefix="as_nav", destination="page_guild",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="as_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_abyss_shadows_natively_staged", title="狭间暗域", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1800
    bind_schedule(source, raw)
    raw["params"].update(
        as_is_open_day={"default": True},
        as_max_battles={"default": 12, "min": 1, "max": 24},
        as_limit_seconds={"default": 1800, "min": 0, "max": 3600},
        as_next_open_delay_s={"default": 0, "min": 0, "max": 604800},
        as_switch_areas={"default": True},
        as_combat_time_enable={"default": False},
        as_boss_combat_seconds={"default": 60, "min": 5, "max": 300},
        as_general_combat_seconds={"default": 45, "min": 5, "max": 300},
        as_elite_combat_seconds={"default": 30, "min": 5, "max": 300},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        as_phase="entry", as_battles=0, as_wins=0, as_target_idx=0, as_main_arrived=0, as_exit_reason="",
        as_area_idx=0, as_areas_switched=0, as_battle_started=0, as_current_combat_ms=60000, as_retreats=0,
        as_target_delay_s=0, as_observed_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/AbyssShadows.yaml", "upstream/oas/Component_GeneralBattle.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("AbyssShadows", "Component_GeneralBattle", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"as_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"as_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"as_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="AbyssShadows"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="AbyssShadows", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("not_open_day_target", "entry", [expr("not as_is_open_day and as_next_open_delay_s > 0")],
          advance("stop_target", as_target_delay_s="as_next_open_delay_s",
                  as_observed_ms="elapsed_ms", as_exit_reason="'closed_day'"))
    state("not_open_day", "entry", [expr("not as_is_open_day")], {
        "stop": {
            "reason": "今日非狭间暗域开放日(周五-周日)",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "AbyssShadows",
            "evidence": {"scope": "abyss_shadows_closed_day"},
        }
    })
    bind_task_presets(raw, source, resources, prefix="as", resume="navigate", category="abyss_shadows")

    arrived = next(step for step in raw["states"] if step["id"] == "as_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_abyss")]
    next(step for step in raw["states"] if step["id"] == "as_nav_drive")["when"] = phase("navigate")

    state("entered_dragon", "enter_abyss", [asset("I_ABYSS_MAP")], advance("wait_start"))
    state("enter_shrine", "enter_abyss", [asset("I_RYOU_SHENSHE")], click("I_RYOU_SHENSHE", "AbyssShadows", 1000))
    state("enter_abyss_btn", "enter_abyss", [asset("I_RYOU_ABYSS_SHADOWS")],
          click("I_RYOU_ABYSS_SHADOWS", "AbyssShadows", 1000))
    state("pick_dragon", "enter_abyss", [asset("I_ABYSS_DRAGON")], click("I_ABYSS_DRAGON", "AbyssShadows", 1000))
    state("open_abyss_confirm", "enter_abyss", [asset("I_OPEN_ABYSS_SHADOWS")],
          click("I_OPEN_ABYSS_SHADOWS", "AbyssShadows", 1000))

    state("wait_gather", "wait_start", [asset("I_WAIT_TO_START")], {"wait": 1000})
    state("gather_done", "wait_start", [{"not": asset("I_WAIT_TO_START")}], advance("fight_cycle"))

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    state("battles_done", "fight_cycle", [expr("as_battles >= as_max_battles")],
          advance("exit_main", as_exit_reason="'count'", as_main_arrived=0))
    state("time_limit_reached", "fight_cycle", [expr("elapsed_ms >= as_limit_seconds * 1000")],
          advance("exit_main", as_exit_reason="'time_limit'", as_main_arrived=0))
    state("fire_enemy", "fight_cycle", [asset("I_ABYSS_FIRE")],
          click("I_ABYSS_FIRE", "AbyssShadows", 1000), {"set": reset},
          advance("battle", as_battles="as_battles + 1", as_battle_started="elapsed_ms"))
    state("goto_enemy", "fight_cycle", [asset("I_ABYSS_GOTO_ENEMY")],
          click("I_ABYSS_GOTO_ENEMY", "AbyssShadows", 1000))
    state("open_map_report", "fight_cycle", [asset("I_ABYSS_MAP")],
          click("I_ABYSS_MAP", "AbyssShadows", 1000), advance("pick_target"))

    targets = (
        ("C_BOSS_CLICK_AREA", "as_boss_combat_seconds * 1000"),
        ("C_GENERAL_1_CLICK_AREA", "as_general_combat_seconds * 1000"),
        ("C_GENERAL_2_CLICK_AREA", "as_general_combat_seconds * 1000"),
        ("C_ELITE_1_CLICK_AREA", "as_elite_combat_seconds * 1000"),
        ("C_ELITE_2_CLICK_AREA", "as_elite_combat_seconds * 1000"),
        ("C_ELITE_3_CLICK_AREA", "as_elite_combat_seconds * 1000"),
    )
    state("target_next_area", "pick_target", [
        expr(f"as_target_idx >= {len(targets)}"), expr("as_switch_areas and as_area_idx < 3"),
    ], advance("change_area", as_area_idx="as_area_idx + 1", as_target_idx=0))
    state("target_wrap", "pick_target", [expr(f"as_target_idx >= {len(targets)}")],
          advance("exit_main", as_exit_reason="'targets_exhausted'", as_main_arrived=0))
    for i, (tgt, combat_expr) in enumerate(targets):
        state(f"pick_target_{i}", "pick_target", [expr(f"as_target_idx == {i}")],
              click(tgt, "AbyssShadows", 1000),
              advance("fight_cycle", as_target_idx=i + 1, as_current_combat_ms=combat_expr))

    # 4-area switching: Dragon(0) -> Peacock(1) -> Fox(2) -> Leopard(3)
    state("area_close_map", "change_area", [asset("I_ABYSS_MAP_EXIT")],
          click("I_ABYSS_MAP_EXIT", "AbyssShadows", 1000))
    for aidx, area_img, area_btn in (
        (1, "I_PEACOCK_AREA", "C_ABYSS_PEACOCK"),
        (2, "I_FOX_AREA", "C_ABYSS_FOX"),
        (3, "I_LEOPARD_AREA", "C_ABYSS_LEOPARD"),
    ):
        state(f"area_arrived_{aidx}", "change_area", [expr(f"as_area_idx == {aidx}"), asset(area_img)],
              advance("fight_cycle", as_areas_switched="as_areas_switched + 1"))
        state(f"area_select_{aidx}", "change_area", [expr(f"as_area_idx == {aidx}"), asset("I_ABYSS_DRAGON")],
              click(area_btn, "AbyssShadows", 1500))
    state("area_open_switch", "change_area", [asset("I_CHANGE_AREA")],
          click("I_CHANGE_AREA", "AbyssShadows", 1500))

    # Smart combat timer early retreat (mirrors run_general_battle_back)
    state("battle_combat_timeout_exit", "battle", [
        expr("as_combat_time_enable"),
        expr("elapsed_ms - as_battle_started >= as_current_combat_ms"),
        asset("I_EXIT", "Component_GeneralBattle"),
    ], click("I_EXIT", "Component_GeneralBattle", 1000), advance("combat_retreat"))

    state("retreat_returned", "combat_retreat", [
        {"any": [asset("I_ABYSS_NAVIGATION"), asset("I_ABYSS_MAP")]},
    ], advance("fight_cycle", as_retreats="as_retreats + 1"))
    state("retreat_confirm", "combat_retreat", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("retreat_early_win", "combat_retreat", [asset("I_WIN", "Component_GeneralBattle")],
          click("I_WIN", "Component_GeneralBattle", 1000),
          advance("fight_cycle", as_wins="as_wins + 1"))
    state("retreat_tap_exit", "combat_retreat", [asset("I_EXIT", "Component_GeneralBattle")],
          click("I_EXIT", "Component_GeneralBattle", 1000))

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("fight_cycle", as_wins=f"as_wins + {outputs['win']}")]
        raw["states"].append(step)

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("exit_close_map", "exit_main", [asset("I_ABYSS_MAP_EXIT")], click("I_ABYSS_MAP_EXIT", "AbyssShadows", 1000))
    state("returned_main_target", "exit_main", [court, expr("as_main_arrived == 1 and as_next_open_delay_s > 0")],
          advance("stop_target", as_target_delay_s="as_next_open_delay_s", as_observed_ms="elapsed_ms"))
    state("returned_main", "exit_main", [court, expr("as_main_arrived == 1")], {
        "stop": {
            "reason": "狭间暗域已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "AbyssShadows",
            "evidence": {"scope": "abyss_shadows_native_path"},
        }
    })
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": "as_main_arrived"}})
    state("stop_target_done", "stop_target", [], {
        "stop": {
            "reason": "狭间暗域已完成并按开放日程预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "AbyssShadows",
                "delay_seconds_var": "as_target_delay_s",
                "observed_ms_var": "as_observed_ms",
            },
            "evidence": {"scope": "abyss_shadows_weekday_schedule"},
        }
    })

    raw["oas_abyss_shadows_contract"] = {
        "source": ABYSS_ENTRY,
        "source_pins": {**ABYSS_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"], {
            "id": "abyss_shadows_area_switching_and_combat_time",
            "blocking": True,
            "requirement": "Bind 4-area switching (Dragon->Peacock->Fox->Leopard), smart combat timer, and live frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_collective_missions_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS CollectiveMissions (guild 30 daily quests) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, CM_PINS, "CollectiveMissions")
    nav = compile_navigation_family(
        source, resources, prefix="cm_nav", destination="page_guild",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_collective_missions_natively_staged", title="集体任务", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update(
        cm_confirm_donate={"default": False},
        cm_prefer_slot={"default": 1, "min": 1, "max": 3},
        cm_ocr_prefer_title={"default": ""},
        cm_switch_mission_enable={"default": False},
        cm_max_switches={"default": 5, "min": 0, "max": 20},
        cm_mission_mode={"default": "donate", "choices": ["donate", "soul", "feed", "bondling"]},
        cm_bondling_failure_seconds={"default": 7200, "min": 0, "max": 3155760000},
        cm_limit_seconds={"default": 0, "min": 0, "max": 7200},
        cm_next_delay_s={"default": 0, "min": 0, "max": 172800},
    )
    raw["vars"].update(
        cm_phase="navigate", cm_done_count=-1, cm_done_before=-1, cm_done_after=-1,
        cm_matter_slot=1, cm_selected_slot=0, cm_donated=False, cm_rewards_claimed=0, cm_exit_reason="",
        cm_bondling_woken=False, cm_bondling_delay_s=7200, cm_bondling_observed_ms=0,
        cm_target_delay_s=0, cm_observed_ms=0, cm_switches=0,
        cm_soul_submit_count=0, cm_soul_submitted=False, cm_feed_submitted=False,
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/CollectiveMissions.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("CollectiveMissions", "GlobalGame")}
    sl_level_roi = docs["CollectiveMissions"]["O_SL_LEVEL"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"cm_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"cm_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"cm_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="CollectiveMissions", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, ns="CollectiveMissions", delay=1000, **kw):
        return _click_from(docs, name, ns, delay, **kw)

    arrived = next(step for step in raw["states"] if step["id"] == "cm_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_cm")]
    next(step for step in raw["states"] if step["id"] == "cm_nav_drive")["when"] = phase("navigate")

    for ph in ("enter_cm", "check_count", "donate", "soul_donate", "feed_donate"):
        state(f"{ph}_time_limit", ph,
              [expr("cm_limit_seconds > 0 and elapsed_ms >= cm_limit_seconds * 1000")],
              advance("exit_cm", cm_exit_reason="'time_limit'"))
    state("entered_records", "enter_cm", [asset("I_CM_RECORDS")], advance("check_count"))
    state("tap_cm_btn", "enter_cm", [asset("I_CM_CM")], click("I_CM_CM", "CollectiveMissions", 1000))
    state("tap_shrine", "enter_cm", [asset("I_CM_SHRINE")], click("I_CM_SHRINE", "CollectiveMissions", 1000))

    state("already_30_done", "check_count",
          [{"ocr": "CollectiveMissions::O_CM_NUMBER", "mode": "counter_remaining", "var": "cm_done_count"},
           expr("cm_done_count == 0")],
          advance("exit_cm", cm_exit_reason="'already_30'"))
    state("claim_existing_rewards", "check_count", [asset("I_CM_REWARDS")],
          click("I_CM_REWARDS", "CollectiveMissions", 1000), advance("collect_reward"))
    state("bondling_wake_task", "check_count", [
        expr("cm_mission_mode == 'bondling'"), {"not": asset("I_CM_REWARDS")},
    ], {"oas_wake": {"task": "BondlingFairyland", "failure_seconds_param": "cm_bondling_failure_seconds"}},
       advance("exit_cm", cm_bondling_woken=True, cm_bondling_observed_ms="elapsed_ms",
               cm_exit_reason="'bondling_woken'"))
    state("donate_confirm_gate", "check_count", [expr("not cm_confirm_donate")],
          {"fail": "集体任务捐赠材料/御魂/喂N卡需要显式确认(cm_confirm_donate=True)"})
    for mode_key, target_phase in (("donate", "donate"), ("soul", "soul_donate"), ("feed", "feed_donate")):
        for slot, ocr_pair in ((1, ("O_CM_1", "O_CM_2")), (2, ("O_CM_3", "O_CM_4")), (3, ("O_CM_5", "O_CM_6"))):
            slot_title_hit = {"any": [
                {"ocr_single": {"region": docs["CollectiveMissions"][okey]["roi"], "equals_var": "cm_ocr_prefer_title"}}
                for okey in ocr_pair
            ]}
            state(f"open_ocr_slot_{mode_key}_{slot}", "check_count", [
                expr(f"cm_confirm_donate and cm_mission_mode == {mode_key!r} and cm_ocr_prefer_title != ''"),
                slot_title_hit,
                {"ocr": "CollectiveMissions::O_CM_NUMBER", "mode": "counter_remaining", "var": "cm_done_before"},
            ], click(f"C_CM_{slot}", "CollectiveMissions", 1500),
               advance(target_phase, cm_matter_slot=1, cm_selected_slot=slot, cm_donated=False))
            state(f"open_ocr_slot_{mode_key}_{slot}_fallback", "check_count", [
                expr(f"cm_confirm_donate and cm_mission_mode == {mode_key!r} and cm_ocr_prefer_title != ''"),
                slot_title_hit,
            ], click(f"C_CM_{slot}", "CollectiveMissions", 1500),
               advance(target_phase, cm_matter_slot=1, cm_selected_slot=slot, cm_donated=False))
        state(f"switch_mission_refresh_{mode_key}", "check_count", [
            expr(f"cm_confirm_donate and cm_mission_mode == {mode_key!r} "
                 "and cm_switch_mission_enable and cm_ocr_prefer_title != '' and cm_switches < cm_max_switches"),
            asset("I_CM_SWITCH"),
        ], click("I_CM_SWITCH", "CollectiveMissions", 2000), {"inc": "cm_switches"})
        for slot in (1, 2, 3):
            state(f"open_slot_{mode_key}_{slot}", "check_count", [
                expr(f"cm_confirm_donate and cm_mission_mode == {mode_key!r} and cm_prefer_slot == {slot}"),
                {"ocr": "CollectiveMissions::O_CM_NUMBER", "mode": "counter_remaining", "var": "cm_done_before"},
            ], click(f"C_CM_{slot}", "CollectiveMissions", 1500),
               advance(target_phase, cm_matter_slot=1, cm_selected_slot=slot, cm_donated=False))
            state(f"open_slot_{mode_key}_{slot}_fallback", "check_count",
                  [expr(f"cm_confirm_donate and cm_mission_mode == {mode_key!r} and cm_prefer_slot == {slot}")],
                  click(f"C_CM_{slot}", "CollectiveMissions", 1500),
                  advance(target_phase, cm_matter_slot=1, cm_selected_slot=slot, cm_donated=False))

    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    state("reward_popup_double", "collect_reward", [reward, expr("cm_rewards_claimed < 2")],
          click("C_UI_REWARD", "GlobalGame", 400), {"inc": "cm_rewards_claimed"})
    state("reward_to_verify", "collect_reward",
          [expr("cm_donated"), {"not": reward}, {"not": asset("I_CM_PRESENT")}],
          advance("verify_donate"))
    state("reward_none", "collect_reward", [{"not": asset("I_CM_REWARDS")}, {"not": reward}],
          advance("exit_cm"))

    state("donate_submit", "donate", [asset("I_CM_MATTER"), asset("I_CM_PRESENT")],
          click("I_CM_PRESENT", "CollectiveMissions", 1000),
          advance("collect_reward", cm_donated=True, cm_rewards_claimed=0))
    raw["states"][-1].update(
        sensitive="分解",
        desc="提交阴阳寮集体任务材料捐赠，将消耗背包觉醒/御灵材料。",
    )
    for mslot in (1, 2, 3, 4):
        state(f"donate_swipe_{mslot}", "donate",
              [asset("I_CM_PRESENT"), {"not": asset("I_CM_MATTER")}, expr(f"cm_matter_slot == {mslot}")],
              {"swipe": f"CollectiveMissions::S_CM_MATTER_{mslot}", "delay": 1500, "recheck": True},
              {"set": {"cm_matter_slot": mslot + 1}})
    state("donate_insufficient_matter", "donate",
          [asset("I_CM_PRESENT"), {"not": asset("I_CM_MATTER")}, expr("cm_matter_slot > 4")],
          {"fail": "集体任务四档材料均未能拉满，已停止捐赠"})
    state("donate_done", "donate", [{"not": asset("I_CM_PRESENT")}], advance("exit_cm"))

    # Soul donation branch (mirrors CollectiveMissions._soul)
    state("soul_none_available", "soul_donate", [
        asset("I_SL_SUBMIT"), {"ocr_single": {"region": sl_level_roi, "equals": "古"}},
    ], click("I_UI_BACK_RED", "GlobalGame", 1000), advance("exit_cm", cm_exit_reason="'no_soul_available'"))
    state("soul_submit", "soul_donate", [
        asset("I_SL_SUBMIT"),
        {"ocr": "CollectiveMissions::O_SL_NUMBER", "var": "cm_soul_submit_count", "test": "cm_soul_submit_count > 0"},
    ], click("I_SL_SUBMIT", "CollectiveMissions", 1000),
       advance("collect_reward", cm_donated=True, cm_soul_submitted=True, cm_rewards_claimed=0))
    raw["states"][-1].update(
        sensitive="分解",
        desc="提交阴阳寮集体任务御魂捐赠，将消耗背包御魂。",
    )
    state("soul_select_long", "soul_donate", [asset("I_SL_SUBMIT")],
          click("L_SL_LONG", "CollectiveMissions", 2500))

    # N-card feed branch (mirrors CollectiveMissions._feed)
    state("feed_submit", "feed_donate", [asset("I_FEED_SUBMIT")],
          click("I_FEED_SUBMIT", "CollectiveMissions", 1000),
          advance("collect_reward", cm_donated=True, cm_feed_submitted=True, cm_rewards_claimed=0))
    raw["states"][-1].update(
        sensitive="分解",
        desc="提交阴阳寮集体任务喂N卡，将消耗背包N卡。",
    )
    state("feed_select_cards", "feed_donate", [asset("I_FEED_HEAP")],
          click("L_FEED_CLICK_1", "CollectiveMissions", 800),
          click("L_FEED_CLICK_2", "CollectiveMissions", 800, recheck=False))

    state("verify_donate_ok", "verify_donate", [
        asset("I_CM_RECORDS"),
        {"ocr": "CollectiveMissions::O_CM_NUMBER", "mode": "counter_remaining", "var": "cm_done_after"},
        expr("cm_done_before < 0 or cm_done_after < cm_done_before"),
    ], advance("exit_cm", cm_exit_reason="'donated_verified'"))
    state("verify_donate_unchanged", "verify_donate", [
        asset("I_CM_RECORDS"),
        {"ocr": "CollectiveMissions::O_CM_NUMBER", "mode": "counter_remaining", "var": "cm_done_after"},
        expr("cm_done_before >= 0 and cm_done_after >= cm_done_before"),
    ], {"fail": "集体任务提交捐赠后剩余次数未减少，已停止继续操作"})
    state("verify_donate_back_red", "verify_donate", [{"not": asset("I_CM_RECORDS")}, asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", 1000))

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("exit_bondling_retry", "exit_cm", [
        expr("cm_bondling_woken"), {"any": [asset("I_CM_SHRINE"), court]},
    ], {
        "stop": {
            "reason": "集体任务已唤醒契灵之境并预约 2 小时后收取奖励",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "CollectiveMissions",
                "delay_seconds_var": "cm_bondling_delay_s",
                "observed_ms_var": "cm_bondling_observed_ms",
            },
            "evidence": {"scope": "collective_missions_bondling_wake"},
        }
    })
    state("exit_done_target_prep", "exit_cm", [{"any": [asset("I_CM_SHRINE"), court]}, expr("cm_next_delay_s > 0")],
          advance("stop_target", cm_target_delay_s="cm_next_delay_s", cm_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "集体任务已完成，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "CollectiveMissions",
                "delay_seconds_var": "cm_target_delay_s",
                "observed_ms_var": "cm_observed_ms",
            },
            "evidence": {"scope": "collective_missions_target_schedule"},
        }
    })
    state("exit_done", "exit_cm", [{"any": [asset("I_CM_SHRINE"), court]}], {
        "stop": {
            "reason": "集体任务已完成",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "CollectiveMissions",
            "evidence": {"scope": "collective_missions_native_path"},
        }
    })
    state("exit_back_red", "exit_cm", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", 1000))
    state("exit_back_yellow", "exit_cm", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000))

    raw["oas_collective_missions_contract"] = {
        "source": CM_ENTRY,
        "source_pins": {**CM_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "collective_missions_priority_ocr_and_bondling_dispatch",
            "blocking": True,
            "requirement": "Bind 3-slot mission OCR ranking, BondlingFairyland cross-task scheduling, and N-card/soul donation",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_kekkai_activation_candidate(source_root, resource_dir, *, calibrations=None, screen_hourly_rate=False):
    """Compile pinned OAS KekkaiActivation (realm card placement) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, KA_PINS, "KekkaiActivation")
    nav = compile_navigation_family(
        source, resources, prefix="ka_nav", destination="page_guild",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_kekkai_activation_natively_staged", title="结界挂卡", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update(
        ka_card_type={"default": "太鼓", "choices": ["太鼓", "斗鱼"]},
        ka_confirm_activate={"default": False},
        ka_harvest_before={"default": False},
        ka_exchange_before={"default": False},
        ka_exchange_max={"default": False},
        ka_max_swipes={"default": 3, "min": 0, "max": 10},
        ka_limit_seconds={"default": 0, "min": 0, "max": 7200},
        ka_not_found_delay_s={"default": 10800, "min": 0, "max": 86400},
    )
    raw["vars"].update(
        ka_phase="navigate", ka_remain_s=-1, ka_observed_ms=0, ka_swipes=0,
        ka_filter_selected=False, ka_harvested=0, ka_activated=False,
        ka_main_arrived=0, ka_exit_reason="", ka_growth_return="",
        ka_growth_exchanged_before=False, ka_growth_exchanged_max=False,
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/KekkaiActivation.yaml",
        "upstream/oas/KekkaiUtilize.yaml",
        "upstream/oas/Component_ReplaceShikigami.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("KekkaiActivation", "KekkaiUtilize", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"ka_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"ka_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"ka_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="KekkaiActivation"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="KekkaiActivation", delay=1000):
        return _click_from(docs, name, ns, delay)

    arrived = next(step for step in raw["states"] if step["id"] == "ka_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_realm")]
    next(step for step in raw["states"] if step["id"] == "ka_nav_drive")["when"] = phase("navigate")

    realm_ready = {"any": [asset("I_REALM_SHIN", "KekkaiUtilize"), asset("I_SHI_GROWN", "KekkaiUtilize")]}
    for ph in ("enter_realm", "open_cards"):
        state(f"{ph}_time_limit", ph,
              [expr("ka_limit_seconds > 0 and elapsed_ms >= ka_limit_seconds * 1000")],
              advance("exit_main", ka_main_arrived=0, ka_remain_s="ka_not_found_delay_s",
                      ka_observed_ms="elapsed_ms", ka_exit_reason="'time_limit'"))
    state("check_card_time_limit", "check_card",
          [expr("ka_limit_seconds > 0 and elapsed_ms >= ka_limit_seconds * 1000")],
          advance("close_cards", ka_remain_s="ka_not_found_delay_s",
                  ka_observed_ms="elapsed_ms", ka_exit_reason="'time_limit'"))
    harvest_icons = (
        "I_A_HARVEST_EXP", "I_A_HARVEST_FISH4", "I_A_HARVEST_KAIKO_4", "I_A_HARVEST_KAIKO_3",
        "I_A_HARVEST_KAIKO_6", "I_A_HARVEST_FISH_6", "I_A_HARVEST_MOON_3", "I_A_HARVEST_FISH_3",
    )
    for icon in harvest_icons:
        state(f"harvest_{icon.lower()}", "enter_realm",
              [expr("ka_harvest_before and ka_harvested == 0"), asset(icon)],
              click(icon, "KekkaiActivation", 1000), {"inc": "ka_harvested"})
    growth_reset = dict(ka_growth_passes=0, ka_growth_picks=0, ka_growth_pending=False, ka_growth_residual_empty=False)
    state("realm_entered_growth", "enter_realm",
          [realm_ready, expr("ka_exchange_before and not ka_growth_exchanged_before")],
          advance("enter_growth", ka_growth_return="'open_cards'", **growth_reset))
    state("realm_entered", "enter_realm", [realm_ready], advance("open_cards"))
    state("tap_guild_realm", "enter_realm", [asset("I_GUILD_REALM", "KekkaiUtilize")],
          click("I_GUILD_REALM", "KekkaiUtilize", 1000))

    state("growth_panel_open", "enter_growth", [asset("I_RS_RECORDS_SHIKI", "Component_ReplaceShikigami")],
          advance("growth_verify"))
    state("tap_shi_grown", "enter_growth", [{"res": "KekkaiUtilize::I_SHI_GROWN", "scale_range": [0.8, 1.2]}],
          {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1500})
    bind_growth(
        raw, resources, prefix="ka",
        done_transitions=[
            ("before", [expr("ka_growth_return == 'open_cards'")], "open_cards", {"ka_growth_exchanged_before": True}),
            ("max", [expr("ka_growth_return == 'exit_main'")], "exit_main",
             {"ka_growth_exchanged_max": True, "ka_main_arrived": 0}),
        ],
    )

    cards_page = {"any": [asset("I_A_CHECK_CARD"), asset("I_A_AUTO_INVITE")]}
    state("cards_entered", "open_cards", [cards_page], advance("check_card"))
    state("tap_shi_card", "open_cards", [asset("I_SHI_CARD", "KekkaiUtilize")],
          click("I_SHI_CARD", "KekkaiUtilize", 1000))

    # Card already active -> read remaining duration and schedule target
    state("card_already_active", "check_card",
          [{"not": asset("I_A_EMPTY")}, asset("I_A_INVITE"),
           {"ocr": "KekkaiActivation::O_CARD_ALL_TIME", "mode": "duration_seconds",
            "var": "ka_remain_s", "test": "ka_remain_s > 0"}],
          advance("close_cards", ka_observed_ms="elapsed_ms", ka_exit_reason="'already_active'"))
    # Selected but not active -> confirm gate then activate
    state("activate_gate", "check_card",
          [{"not": asset("I_A_EMPTY")}, asset("I_A_ACTIVATE_YELLOW"), expr("not ka_confirm_activate")],
          {"fail": "激活结界卡消耗结界卡需要显式确认(ka_confirm_activate=True)"})
    state("activate_selected", "check_card",
          [{"not": asset("I_A_EMPTY")}, asset("I_A_ACTIVATE_YELLOW"), expr("ka_confirm_activate")],
          click("I_A_ACTIVATE_YELLOW", "KekkaiActivation", 1000), advance("confirm_activate"))
    raw["states"][-1].update(
        sensitive="购买",
        desc="激活已选中的结界卡，将消耗背包中对应的结界卡。",
    )
    # Empty -> filter by card type and search the list up to the configured limit.
    state("empty_select_gate", "check_card", [asset("I_A_EMPTY"), expr("not ka_confirm_activate")],
          {"fail": "空结界槽挑选并激活结界卡需要显式确认(ka_confirm_activate=True)"})
    state("empty_filter_taiko", "check_card",
          [asset("I_A_EMPTY"), expr("ka_confirm_activate and not ka_filter_selected and ka_card_type == '太鼓'"),
           asset("I_A_CARD_KAIKO")],
          click("I_A_CARD_KAIKO", "KekkaiActivation", 1000), {"set": {"ka_filter_selected": True}})
    state("empty_filter_fish", "check_card",
          [asset("I_A_EMPTY"), expr("ka_confirm_activate and not ka_filter_selected and ka_card_type == '斗鱼'"),
           asset("I_A_CARD_FISH")],
          click("I_A_CARD_FISH", "KekkaiActivation", 1000), {"set": {"ka_filter_selected": True}})
    verified_filter = []
    if screen_hourly_rate:
        raw["vars"]["ka_hourly_rate"] = -1
        filters = []
        for name, selected, currency, minimum in (("taiko", "太鼓", "勾玉", 8), ("fish", "斗鱼", "体力", 16)):
            param = f"ka_min_{name}_rate"
            raw["params"][param] = {"default": minimum, "min": 0, "max": 99999}
            header = {"ocr_single": {"region": [388, 99, 81, 49], "equals": selected}}
            card_type = {"all": [expr(f"ka_card_type == {selected!r}"), header]}
            filters.append(card_type)
            rate = {"ocr": "KekkaiActivation::O_CHECK_CARD_NUMBER", "mode": "max_hourly_rate",
                    "hourly_label": currency, "var": "ka_hourly_rate", "test": f"ka_hourly_rate >= {param}"}
            state(f"empty_select_{name}_rate", "check_card",
                  [cards_page, asset("I_A_EMPTY"), expr("ka_confirm_activate and ka_filter_selected"),
                   card_type, rate],
                  {"click_found": True, "offset": [-6, -5, 6, 5], "delay": 1000, "recheck": True})
        verified_filter.append({"any": filters})
    else:
        for star in (6, 5, 4, 3):
            for name, choice, template in (("taiko", "太鼓", "KAIKO"), ("fish", "斗鱼", "FISH")):
                card_asset = f"I_CARDS_{template}_{star}"
                state(f"empty_select_{name}_{star}", "check_card",
                      [asset("I_A_EMPTY"), expr(f"ka_confirm_activate and ka_card_type == {choice!r}"),
                       asset(card_asset)], click(card_asset, "KekkaiActivation", 1000))
    state("empty_card_not_found_bottom", "check_card",
          [asset("I_A_EMPTY"), expr("ka_confirm_activate and ka_filter_selected"), *verified_filter,
           {"any": [asset("I_AA_SWIPE_BLOCK"), expr("ka_swipes >= ka_max_swipes")]}],
          advance("close_cards", ka_remain_s="ka_not_found_delay_s",
                  ka_observed_ms="elapsed_ms", ka_exit_reason="'card_not_found'"))
    state("empty_swipe_cards", "check_card",
          [asset("I_A_EMPTY"), expr("ka_confirm_activate and ka_filter_selected and ka_swipes < ka_max_swipes"),
           *verified_filter],
          {"swipe": "KekkaiActivation::S_CARDS_SWIPE", "delay": 1200, "recheck": True}, {"inc": "ka_swipes"})
    filter_request = "ka_confirm_activate and not ka_filter_selected" if screen_hourly_rate else "ka_confirm_activate"
    state("empty_open_list", "check_card", [asset("I_A_EMPTY"), expr(filter_request)],
          click("C_A_SELECT_CARD_LIST", "KekkaiActivation", 1500))

    state("confirm_activate_done", "confirm_activate",
          [asset("I_A_INVITE"),
           {"ocr": "KekkaiActivation::O_CARD_ALL_TIME", "mode": "duration_seconds",
            "var": "ka_remain_s", "test": "ka_remain_s > 0"}],
          advance("close_cards", ka_activated=True, ka_observed_ms="elapsed_ms", ka_exit_reason="'activated'"))
    state("confirm_popup", "confirm_activate", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 600))
    state("confirm_retry_yellow", "confirm_activate", [asset("I_A_ACTIVATE_YELLOW")],
          click("I_A_ACTIVATE_YELLOW", "KekkaiActivation", 1000))

    state("close_cards_growth", "close_cards",
          [realm_ready, expr("ka_exchange_max and not ka_growth_exchanged_max")],
          advance("enter_growth", ka_growth_return="'exit_main'", **growth_reset))
    state("close_cards_done", "close_cards", [realm_ready], advance("exit_main", ka_main_arrived=0))
    open_card_view = {"any": [cards_page, asset("I_A_INVITE"), asset("I_A_EMPTY")]}
    state("close_cards_red", "close_cards", [open_card_view, asset("I_UI_BACK_RED", "GlobalGame")],
          {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1000})

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main_target", "exit_main",
          [court, expr("ka_main_arrived == 1"), expr("ka_remain_s > 0")], {
              "stop": {
                  "reason": "结界挂卡已完成并返回庭院",
                  "result": "unknown",
                  "verified": False,
                  "oas_schedule": {
                      "task": "KekkaiActivation",
                      "delay_seconds_var": "ka_remain_s",
                      "observed_ms_var": "ka_observed_ms",
                  },
                  "evidence": {"scope": "kekkai_activation_native_path"},
              }
          })
    state("returned_main_default", "exit_main", [court, expr("ka_main_arrived == 1")], {
        "stop": {
            "reason": "结界挂卡已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "KekkaiActivation",
            "evidence": {"scope": "kekkai_activation_native_path"},
        }
    })
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": "ka_main_arrived"}})

    raw["oas_kekkai_activation_contract"] = {
        "source": KA_ENTRY,
        "source_pins": {**KA_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "kekkai_activation_growth_exchange_and_min_rate_filter",
            "blocking": True,
            "requirement": ("Verify live card activation, hourly-rate OCR, and growth replacement on real realm frames"
                            if screen_hourly_rate else
                            "Bind min hourly rate OCR and verify live card activation and growth replacement on real realm frames"),
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_restart_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Restart (app restart + Android login harvest) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, RESTART_PINS, "Restart")
    raw = compile_android_login(source, resources, prefix="rs_login")
    raw.update(name="oas_restart_natively_staged", title="重启与登录收菜", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 900
    bind_schedule(source, raw)
    raw["params"].update(
        rs_wednesday_maintenance={"default": False},
        rs_wednesday_delay_s={"default": 0, "min": 0, "max": 28800},
        rs_ap_delay_s={"default": 0, "min": 0, "max": 86400},
        rs_desktop_mode={"default": False},
        rs_limit_seconds={"default": 0, "min": 0, "max": 7200},
    )
    raw["vars"].update(rs_phase="entry", rs_target_delay_s=0, rs_observed_ms=0, rs_exit_reason="")

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"rs_phase == {val!r}")

    # Gate all login states behind rs_phase == 'login' (flatten 'all' so restart_app schema checks preserve top-level items)
    for st in raw["states"]:
        when = st.get("when")
        if isinstance(when, dict) and "all" in when:
            st["when"] = {"all": [phase("login"), *when["all"]]}
        elif when is not None:
            st["when"] = {"all": [phase("login"), when]}
        else:
            st["when"] = phase("login")
    # Prepend entry guards and completion stop when rs_login_returned becomes True
    entry_states = [
        {
            "id": "rs_wednesday_maintenance_target",
            "when": {"all": [phase("entry"), expr("rs_wednesday_maintenance and rs_wednesday_delay_s > 0")]},
            "do": [{"set": {
                "rs_phase": "'stop_target'", "rs_target_delay_s": "rs_wednesday_delay_s",
                "rs_observed_ms": "elapsed_ms", "rs_exit_reason": "'wednesday_maintenance'",
            }}],
        },
        {
            "id": "rs_wednesday_maintenance_delay",
            "when": {"all": [phase("entry"), expr("rs_wednesday_maintenance")]},
            "do": [{"fail": "周三6-8点维护延迟所有待运行任务至9:00需跨任务调度器契约"}],
        },
        {
            "id": "rs_desktop_mode_gate",
            "when": {"all": [phase("entry"), expr("rs_desktop_mode")]},
            "do": [{"fail": "桌面端客户端启停(_desktop_start_and_login)需桌面进程管理契约"}],
        },
        {
            "id": "rs_entry_to_login",
            "when": phase("entry"),
            "do": [{"set": {"rs_phase": "'login'"}}],
        },
        {
            "id": "rs_login_time_limit_target",
            "when": {"all": [
                phase("login"),
                expr("rs_limit_seconds > 0 and elapsed_ms >= rs_limit_seconds * 1000 and rs_ap_delay_s > 0"),
            ]},
            "do": [{"set": {
                "rs_phase": "'stop_target'", "rs_target_delay_s": "rs_ap_delay_s",
                "rs_observed_ms": "elapsed_ms", "rs_exit_reason": "'time_limit'",
            }}],
        },
        {
            "id": "rs_login_time_limit",
            "when": {"all": [
                phase("login"),
                expr("rs_limit_seconds > 0 and elapsed_ms >= rs_limit_seconds * 1000"),
            ]},
            "do": [{"set": {"rs_phase": "'stop_default'", "rs_exit_reason": "'time_limit'"}}],
        },
        {
            "id": "rs_stop_default",
            "when": phase("stop_default"),
            "do": [{
                "stop": {
                    "reason": "重启与登录收菜达到限时后安全退出",
                    "result": "unknown",
                    "verified": False,
                    "oas_schedule": "Restart",
                    "evidence": {"scope": "restart_time_limit"},
                }
            }],
        },
        {
            "id": "rs_login_complete_ap_target",
            "when": {"all": [phase("login"), expr("rs_login_returned and rs_ap_delay_s > 0")]},
            "do": [{"set": {
                "rs_phase": "'stop_target'", "rs_target_delay_s": "rs_ap_delay_s",
                "rs_observed_ms": "elapsed_ms", "rs_exit_reason": "'ap_scheduled'",
            }}],
        },
        {
            "id": "rs_stop_target",
            "when": phase("stop_target"),
            "do": [{
                "stop": {
                    "reason": "重启与登录收菜已按维护/体力时间窗预约下次运行",
                    "result": "unknown",
                    "verified": False,
                    "oas_schedule": {
                        "task": "Restart",
                        "delay_seconds_var": "rs_target_delay_s",
                        "observed_ms_var": "rs_observed_ms",
                    },
                    "evidence": {"scope": "restart_target_schedule"},
                }
            }],
        },
        {
            "id": "rs_login_complete",
            "when": {"all": [phase("login"), expr("rs_login_returned")]},
            "do": [{
                "stop": {
                    "reason": "重启与登录收菜已完成",
                    "result": "unknown",
                    "verified": False,
                    "oas_schedule": "Restart",
                    "evidence": {"scope": "restart_android_login_path"},
                }
            }],
        },
    ]
    raw["states"] = entry_states + raw["states"]
    raw["oas_restart_contract"] = {
        "source": RESTART_ENTRY,
        "source_pins": {**RESTART_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*raw.get("harvest_contract", {}).get("source_obligations", []), {
            "id": "restart_desktop_and_ap_schedule",
            "blocking": True,
            "requirement": "Bind desktop client lifecycle, Wednesday maintenance delay_pending_tasks, and 12/20h AP schedule",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
