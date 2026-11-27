"""Pinned OAS Duel, RyouToppa, RealmRaid, and AreaBoss workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import compile_general_battle
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


DUEL_ENTRY = "tasks/Duel/script_task.py"
DUEL_PINS = {
    DUEL_ENTRY: "b464ef024d2b0b2e5f2f90f0f47b73ff18bee011d73c8ae255bbeafc33c6a06c",
    "tasks/Duel/config.py": "65b35eca071aa2a92a123441094dfc50b9110d355eb71e880e71dfdf545d92db",
    "tasks/Duel/assets.py": "e3136b4eed8671cb2f4ce45b12e5cf8231ef8371fb4f3d81138e7d3916ed26a9",
}

RYOU_TOPPA_ENTRY = "tasks/RyouToppa/script_task.py"
RYOU_TOPPA_PINS = {
    RYOU_TOPPA_ENTRY: "20329ce0d0dc34eee48518182408a0dc1a3bc67dbee3d5c21641fe2d5898ce38",
    "tasks/RyouToppa/config.py": "bede5927140c84333a146d1918675117df6cde922f0c9a7460ee645bc26de427",
    "tasks/RyouToppa/assets.py": "05f4153d68dcf650580152824eb4adb4765a0472d4a26fbcd8dbb8162e629f2f",
}

REALM_RAID_ENTRY = "tasks/RealmRaid/script_task.py"
REALM_RAID_PINS = {
    REALM_RAID_ENTRY: "53e55f8eb0cf996bfabeebf9b385911cc116b01c99e99a29e4b778e473379a21",
    "tasks/RealmRaid/config.py": "91bb6c6a9076fc25703458871373e1352e2755be0fcc24c07fc9722733f60e22",
    "tasks/RealmRaid/assets.py": "da2fc6ccce1547d20e64d1fdc0d5830eb82ef9d0e1953b521db9a9f780a27fc6",
}
REALM_RAID_MEDAL_PINS = {
    "module/atom/image_grid.py": "5980751381d390cb19603257d09ff9fe5127a360107e97930474132210d746d5",
    "tasks/RyouToppa/assets.py": RYOU_TOPPA_PINS["tasks/RyouToppa/assets.py"],
}

AREA_BOSS_ENTRY = "tasks/AreaBoss/script_task.py"
AREA_BOSS_PINS = {
    AREA_BOSS_ENTRY: "f69b3ca15cd1706a3b5e2539a6c76ddd1ed57979491bcccb185468c576c43030",
    "tasks/AreaBoss/config.py": "696a159002d49c3d62441843b05e5ff0f71efff0f13ef07765d67fbe9c4e1dbb",
    "tasks/AreaBoss/config_boss.py": "5103797173859342fd2141aa64b2706f9a3e7260c1069981689712cef0387a8e",
    "tasks/AreaBoss/assets.py": "502f65d34f898fd86fd31b825fefdc552c19cdd631fb6aae73ebbebcabd2a03a",
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


def compile_duel_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Duel workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, DUEL_PINS, "Duel")
    nav = compile_navigation_family(
        source, resources, prefix="du_nav", destination="page_duel",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_duel_natively_staged", title="斗技", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        du_in_window={"default": True},
        du_switch_onmyoji={"default": False},
        du_onmyoji={"default": "seimi", "choices": ["seimi", "kagura", "hiromasa", "yao_bikuni", "yorimitsu", "michinaga"]},
        du_limit_seconds={"default": 1800, "min": 0, "max": 7200},
        du_target_score={"default": 2000, "min": 0, "max": 9999},
        du_initial_score={"default": 3000, "min": 0, "max": 9999},
        du_celeb_battle={"default": False},
        du_ban_name={"default": ""},
        du_green_enable={"default": False},
        du_green_mark={"default": "left_1", "choices": ["left_1", "left_2", "left_3", "left_4", "left_5", "main"]},
        du_battle_timeout_s={"default": 900, "min": 0, "max": 3600},
        du_honor_full_exit={"default": False},
        du_trigger_talisman={"default": True},
        du_talisman_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        du_max_battles={"default": 30, "min": 0, "max": 200},
        du_next_window_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        du_phase="entry", du_battles=0, du_wins=0, du_losses=0,
        du_score=0, du_celeb_score=-1, du_honor_current=-1, du_honor_remain=-1, du_talisman_woken=False,
        du_honor_x=184, du_honor_y=629, du_honor_w=35, du_honor_h=30,
        du_is_celeb=False, du_ban_ocr="", du_ban_exits=0, du_battle_started_ms=-1,
        du_green_done=False, du_green_marks=0, du_battle_outcome="",
        du_onmyodo_arrived=0, du_onmyoji_started=0, du_onmyoji_switched=False,
        du_target_delay_s=0, du_observed_ms=0, du_main_arrived=0, du_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/Duel.yaml", "upstream/oas/Component_GeneralBattle.yaml",
        "upstream/oas/Component_SwitchOnmyoji.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("Duel", "Component_GeneralBattle", "Component_SwitchOnmyoji", "GlobalGame")}
    raw.setdefault("inline_resources", {})["Duel::O_D_HONOR_SHIFTED"] = {
        **docs["Duel"]["O_D_HONOR"], "roi": [204, 632, 67, 20],
    }
    hand_roi = docs["Duel"]["O_D_HAND"]["roi"]
    auto_roi = docs["Duel"]["O_D_AUTO"]["roi"]
    ban_roi = docs["Duel"]["O_D_BAN_NAME"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"du_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"du_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"du_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Duel", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, ns="Duel", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("outside_window_target", "entry", [expr("not du_in_window and du_next_window_delay_s > 0")],
          advance("stop_target", du_target_delay_s="du_next_window_delay_s",
                  du_observed_ms="elapsed_ms", du_exit_reason="'outside_window'"))
    state("outside_window", "entry", [expr("not du_in_window")], {
        "stop": {
            "reason": "当前不在斗技开放时间(12:00-23:00)",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Duel",
            "evidence": {"scope": "duel_outside_window"},
        }
    })
    bind_task_presets(raw, source, resources, prefix="du", resume="onmyoji_dispatch", category="duel")

    # Component_SwitchOnmyoji (mirrors tasks/Component/SwitchOnmyoji/switch_onmyoji.py)
    state("onmyoji_skip", "onmyoji_dispatch", [expr("not du_switch_onmyoji")], advance("navigate"))
    state("onmyoji_goto", "onmyoji_dispatch", [expr("du_switch_onmyoji")],
          advance("onmyoji_nav", du_onmyodo_arrived=0))
    onmyodo_page = raw["navigation"]["pages"]["page_onmyodo"]["when"]
    state("onmyoji_nav_arrived", "onmyoji_nav", [onmyodo_page, expr("du_onmyodo_arrived == 1")],
          advance("onmyoji_tab", du_onmyoji_started="elapsed_ms"))
    state("onmyoji_nav_drive", "onmyoji_nav", [],
          {"navigate": {"destination": "page_onmyodo", "done_var": "du_onmyodo_arrived"}})

    is_hero = expr("du_onmyoji == 'yorimitsu' or du_onmyoji == 'michinaga'")
    is_onmyoji = expr("du_onmyoji != 'yorimitsu' and du_onmyoji != 'michinaga'")
    hero_icons = [asset("I_YORIMITSU_BATTLE", "Component_SwitchOnmyoji"),
                  asset("I_MICHINAGA_BATTLE", "Component_SwitchOnmyoji")]
    onmyoji_icons = [asset(n, "Component_SwitchOnmyoji") for n in
                     ("I_SEIMI_BATTLE", "I_KAGURA_BATTLE", "I_HIROMASA_BATTLE", "I_YAO_BIKUNI_BATTLE")]
    state("onmyoji_tab_to_hero", "onmyoji_tab",
          [is_hero, asset("I_ONMYOJI_CHECK", "Component_SwitchOnmyoji")],
          click("I_ONMYOJI_CHECK", "Component_SwitchOnmyoji", 800))
    state("onmyoji_tab_to_onmyoji", "onmyoji_tab",
          [is_onmyoji, asset("I_HERO_CHECK", "Component_SwitchOnmyoji")],
          click("I_HERO_CHECK", "Component_SwitchOnmyoji", 800))
    state("onmyoji_list_open_hero", "onmyoji_tab", [is_hero, {"any": hero_icons}],
          advance("onmyoji_pick", du_onmyoji_started="elapsed_ms"))
    state("onmyoji_list_open_onmyoji", "onmyoji_tab", [is_onmyoji, {"any": onmyoji_icons}],
          advance("onmyoji_pick", du_onmyoji_started="elapsed_ms"))
    state("onmyoji_open_switch", "onmyoji_tab", [asset("I_ONMYOJI_SWITCH", "Component_SwitchOnmyoji")],
          click("I_ONMYOJI_SWITCH", "Component_SwitchOnmyoji", 800))
    state("onmyoji_tab_timeout", "onmyoji_tab", [expr("elapsed_ms - du_onmyoji_started >= 20000")],
          {"fail": "切换阴阳师未能在20秒内打开角色列表"})

    role_map = [
        ("seimi", "I_SEIMI_BATTLE", "I_ONMYOJI_CHECK"),
        ("kagura", "I_KAGURA_BATTLE", "I_ONMYOJI_CHECK"),
        ("hiromasa", "I_HIROMASA_BATTLE", "I_ONMYOJI_CHECK"),
        ("yao_bikuni", "I_YAO_BIKUNI_BATTLE", "I_ONMYOJI_CHECK"),
        ("yorimitsu", "I_YORIMITSU_BATTLE", "I_HERO_CHECK"),
        ("michinaga", "I_MICHINAGA_BATTLE", "I_HERO_CHECK"),
    ]
    for role_key, battle_icon, check_icon in role_map:
        role_guard = expr(f"du_onmyoji == {role_key!r}")
        state(f"onmyoji_done_{role_key}", "onmyoji_pick",
              [role_guard, asset(check_icon, "Component_SwitchOnmyoji")],
              advance("navigate", du_onmyoji_switched=True))
        state(f"onmyoji_back_{role_key}", "onmyoji_pick",
              [role_guard, asset(battle_icon, "Component_SwitchOnmyoji"), asset("I_UI_BACK_BLUE", "GlobalGame")],
              click("I_UI_BACK_BLUE", "GlobalGame", 1000))
        state(f"onmyoji_select_{role_key}", "onmyoji_pick",
              [role_guard, {"not": asset(battle_icon, "Component_SwitchOnmyoji")}],
              click(battle_icon, "Component_SwitchOnmyoji", 1000))
    state("onmyoji_pick_timeout", "onmyoji_pick", [expr("elapsed_ms - du_onmyoji_started >= 20000")],
          {"fail": "切换阴阳师未能在20秒内确认出战角色"})

    arrived = next(step for step in raw["states"] if step["id"] == "du_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("duel_main")]
    next(step for step in raw["states"] if step["id"] == "du_nav_drive")["when"] = phase("navigate")

    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    state("main_reward_popup", "duel_main", [reward], click("C_UI_REWARD", "GlobalGame", 400))
    state("main_time_stop", "duel_main", [expr("elapsed_ms >= du_limit_seconds * 1000")],
          advance("exit_main", du_exit_reason="'time'", du_main_arrived=0))
    round_reward = {"all": [
        asset("I_REWARD", "Component_GeneralBattle"),
        {"ocr_single": {"region": [536, 676, 213, 40], "equals": "点击屏幕继续", "score": .55}},
    ]}
    for phase_name in ("duel_main", "wait_battle", "exit_main"):
        state(f"collect_round_reward_{phase_name}", phase_name, [round_reward],
              {"click": [549, 681, 716, 708], "recheck": True, "recheck_retry": True, "delay": 1000})
    state("main_close_lineup_trial_intro", "duel_main", [
        raw["navigation"]["pages"]["page_duel"]["when"],
        {"ocr_single": {"region": [542, 459, 197, 33], "equals": "点击任意位置继续", "score": .55}},
        {"ocr_full": {"region": [450, 286, 397, 100], "keyword": "队伍试用功能"}},
    ], {"click": [434, 466, 480, 489], "recheck": True, "recheck_retry": True, "delay": 800})
    state("main_count_stop", "duel_main", [expr("du_battles >= du_max_battles")],
          advance("exit_main", du_exit_reason="'count'", du_main_arrived=0))
    state("main_train_stop", "duel_main",
          [{"any": [asset("I_BATTLE_WITH_TRAIN"), asset("I_BATTLE_WITH_TRAIN2")]}],
          advance("exit_main", du_exit_reason="'practice_mode'", du_main_arrived=0))
    state("main_init_celeb_score", "duel_main", [expr("du_celeb_score < 0")],
          {"set": {"du_celeb_score": "du_initial_score"}})
    state("main_celeb_stop", "duel_main",
          [expr("not du_celeb_battle"), {"any": [asset("I_D_CELEB_STAR"), asset("I_D_CELEB_HONOR")]}],
          advance("exit_main", du_exit_reason="'already_celeb'", du_main_arrived=0))
    state("main_celeb_score_stop", "duel_main",
          [expr("du_celeb_battle and du_celeb_score >= du_target_score"),
           {"any": [asset("I_D_CELEB_STAR"), asset("I_D_CELEB_HONOR")]}],
          advance("exit_main", du_is_celeb=True, du_score="du_celeb_score",
                  du_exit_reason="'celeb_target_score'", du_main_arrived=0))
    state("main_mark_celeb", "duel_main",
          [expr("du_celeb_battle and not du_is_celeb"),
           {"any": [asset("I_D_CELEB_STAR"), asset("I_D_CELEB_HONOR")]}],
          {"set": {"du_is_celeb": True}})
    honor = asset("I_DUEL_HONOR")
    shifted_honor = {**honor, "threshold": .77, "region_vars": ["du_honor_x", "du_honor_y", "du_honor_w", "du_honor_h"]}
    honor_reads = []
    for icon, counter in ((honor, "O_D_HONOR"), (shifted_honor, "O_D_HONOR_SHIFTED")):
        honor_reads.append({"all": [icon,
            {"ocr": f"Duel::{counter}", "mode": "counter_current", "var": "du_honor_current"},
            {"ocr": f"Duel::{counter}", "mode": "counter_remaining", "var": "du_honor_remain"},
        ]})
    state("main_honor_full_stop", "duel_main",
          [expr("du_honor_full_exit"), {"any": honor_reads}, expr("du_honor_remain == 0")],
          advance("exit_main", du_exit_reason="'honor_full'", du_main_arrived=0))
    state("main_score_stop", "duel_main",
          [{"ocr": "Duel::O_D_SCORE", "mode": "counter_current", "var": "du_score"},
           expr("du_score >= du_target_score and du_score < 10000")],
          advance("exit_main", du_exit_reason="'target_score'", du_main_arrived=0))
    for btn in ("I_D_BATTLE", "I_D_BATTLE2", "I_D_BATTLE_PROTECT"):
        state(f"start_{btn.lower()}", "duel_main", [asset(btn)],
              click(btn, "Duel", 1200), advance("prepare", du_battles="du_battles + 1", du_green_done=False,
                                                du_battle_outcome="''"))

    # Prepare & battle wait (including celebrity ban OCR exit & 15-min battle timeout)
    state("prep_ban", "prepare", [asset("I_BAN")], click("I_BAN", "Duel", 1200), {"set": {"du_is_celeb": True}})
    state("prep_celeb_ban_exit", "prepare", [
        expr("du_is_celeb and du_ban_name != ''"),
        {"not": asset("I_D_CHECK_BAN")},
        {"text": "", "region": ban_roi, "pattern": r".+"},
        {"not": {"ocr_single": {"region": ban_roi, "equals_var": "du_ban_name"}}},
    ], advance("duel_exit", du_ban_exits="du_ban_exits + 1"))
    state("prep_celeb_inspect_5", "prepare", [
        expr("du_is_celeb and du_ban_name != ''"),
        {"not": asset("I_D_CHECK_BAN")},
        {"not": asset("I_D_PREPARE")},
    ], click("C_DUEL_CLICK_5", "Duel", 1500))
    state("prep_auto_entry", "prepare", [asset("I_D_AUTO_ENTRY")], click("I_D_AUTO_ENTRY", "Duel", 1200))
    state("prep_ready_btn", "prepare", [asset("I_D_PREPARE")],
          click("I_D_PREPARE", "Duel", 1200), advance("wait_battle", du_battle_started_ms="elapsed_ms"))
    state("prep_already_fighting", "prepare",
          [{"any": [asset("I_D_VICTORY"), asset("I_D_FAIL"), asset("I_FALSE", "Component_GeneralBattle"),
                    {"ocr_full": {"region": hand_roi, "keyword": "手动"}}]}],
          advance("wait_battle", du_battle_started_ms="elapsed_ms"))

    # duel_exit_battle(): exit during ban/prepare or after battle timeout
    state("duel_exit_settled", "duel_exit",
          [{"any": [asset("I_D_FAIL"), asset("I_FALSE", "Component_GeneralBattle")]}],
          advance("wait_battle", du_battle_started_ms=-1))
    state("duel_exit_confirm", "duel_exit", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("duel_exit_duel_btn", "duel_exit", [asset("I_DUEL_EXIT")], click("I_DUEL_EXIT", "Duel", 1000))
    state("duel_exit_gen_btn", "duel_exit", [asset("I_EXIT", "Component_GeneralBattle")],
          click("I_EXIT", "Component_GeneralBattle", 1000))

    duel_page = raw["navigation"]["pages"]["page_duel"]["when"]
    state("battle_back_to_duel", "wait_battle", [duel_page, asset("I_D_HELP"), {"not": round_reward}],
          advance("duel_main", du_battle_started_ms=-1))
    state("battle_back_red", "wait_battle", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", 1200))
    for outcome, marker, count, score in (
        ("win", {"any": [asset("I_D_VICTORY"), asset("I_D_VICTORY_SHARE")]}, "du_wins", "+"),
        ("lose", {"any": [asset("I_D_FAIL"), asset("I_FALSE", "Component_GeneralBattle")]}, "du_losses", "-"),
    ):
        state(f"battle_{outcome}_observed", "wait_battle", [expr("du_battle_outcome == ''"), marker],
              {"inc": count}, {"set": {"du_battle_outcome": repr(outcome),
                                       "du_celeb_score": f"du_celeb_score {score} 100 * du_is_celeb"}})
        state(f"battle_{outcome}_dismiss", "wait_battle", [expr(f"du_battle_outcome == {outcome!r}"), marker],
              {**click("C_D_BATTLE_DATA", "Duel", 1200), "recheck_retry": True})
    state("battle_timeout_exit", "wait_battle",
          [expr("du_battle_started_ms >= 0 and elapsed_ms - du_battle_started_ms >= du_battle_timeout_s * 1000")],
          advance("duel_exit", du_battle_started_ms=-1))
    state("battle_hand_to_auto", "wait_battle",
          [expr("du_battle_outcome == ''"), {"ocr_full": {"region": hand_roi, "keyword": "手动",
                                                       "selection": "unique_equals"}}],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True, "recheck_retry": True})
    for slot_key, mark_asset in (
        ("left_1", "C_GREEN_LEFT_1"), ("left_2", "C_GREEN_LEFT_2"), ("left_3", "C_GREEN_LEFT_3"),
        ("left_4", "C_GREEN_LEFT_4"), ("left_5", "C_GREEN_LEFT_5"), ("main", "C_GREEN_MAIN"),
    ):
        state(f"battle_green_mark_{slot_key}", "wait_battle", [
            expr(f"du_green_enable and not du_green_done and du_green_mark == {slot_key!r}"),
            {"ocr_full": {"region": auto_roi, "keyword": "自动"}},
        ], click(mark_asset, "Component_GeneralBattle", 800),
              {"set": {"du_green_done": True}}, {"inc": "du_green_marks"})
    state("battle_wait_tick", "wait_battle", [], {"wait": 1000})

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main_wake_talisman", "exit_main",
          [court, expr("du_main_arrived == 1 and du_trigger_talisman and not du_talisman_woken")],
          {"oas_wake": {"task": "TalismanPass", "failure_seconds_param": "du_talisman_failure_seconds"}},
          {"set": {"du_talisman_woken": True}})
    state("returned_main_target_prep", "exit_main",
          [court, expr("du_main_arrived == 1 and du_next_window_delay_s > 0")],
          advance("stop_target", du_target_delay_s="du_next_window_delay_s", du_observed_ms="elapsed_ms"))
    target_schedule = {"task": "Duel", "delay_seconds_var": "du_target_delay_s", "observed_ms_var": "du_observed_ms"}
    settled_rounds = expr("du_battles > 0 and du_wins + du_losses == du_battles")
    for phase_name, schedule in (("exit_main", "Duel"), ("stop_target", target_schedule)):
        state(f"verified_return_{phase_name}", phase_name, [court, expr("du_main_arrived == 1"), settled_rounds],
              {"stop": {"reason": "斗技已核对全部场次的结算并返回庭院", "result": "completed", "verified": True,
                        "oas_schedule": schedule, "evidence": {"scope": "duel_settled_rounds_and_courtyard"}}})
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "斗技已完成或非开放时段，已按窗口排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": target_schedule,
            "evidence": {"scope": "duel_window_target_schedule"},
        }
    })
    state("returned_main", "exit_main", [court, expr("du_main_arrived == 1")], {
        "stop": {
            "reason": "斗技已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Duel",
            "evidence": {"scope": "duel_native_path"},
        }
    })
    state("exit_back_yellow", "exit_main", [{"not": court}, asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000))
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": "du_main_arrived"}})

    raw["oas_duel_contract"] = {
        "source": DUEL_ENTRY,
        "source_pins": {**DUEL_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "duel_onmyoji_ban_honor_and_talisman_trigger",
            "blocking": True,
            "requirement": "Bind SwitchOnmyoji, celeb ban OCR exit, dynamic honor ROI, and post-duel TalismanPass trigger",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_ryou_toppa_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS RyouToppa (guild realm raid) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, RYOU_TOPPA_PINS, "RyouToppa")
    nav = compile_navigation_family(
        source, resources, prefix="rt_nav", destination="page_kekkai_toppa",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="rt_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_ryou_toppa_natively_staged", title="寮突破", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        rt_limit_count={"default": 50, "min": 0, "max": 200},
        rt_limit_seconds={"default": 1800, "min": 0, "max": 7200},
        rt_ryou_access={"default": False},
        rt_confirm_admin_start={"default": False},
        rt_unlimited_hours={"default": False},
        rt_max_flushes={"default": 3, "min": 0, "max": 20},
        rt_tomorrow_delay_s={"default": 86400, "min": 0, "max": 172800},
        rt_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        rt_phase="entry", rt_area=1, rt_attempts=0, rt_wins=0,
        rt_tickets=-1, rt_flushes=0, rt_admin_started=False, rt_target_delay_s=0, rt_observed_ms=0,
        rt_main_arrived=0, rt_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/RyouToppa.yaml", "upstream/oas/RealmRaid.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("RyouToppa", "RealmRaid", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"rt_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"rt_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"rt_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="RyouToppa"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="RyouToppa", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("admin_start_confirm_gate", "entry", [expr("rt_ryou_access and not rt_confirm_admin_start")],
          {"fail": "寮突破寮管理开启新寮属于寮管理操作，需显式开启 rt_confirm_admin_start 确认参数"})
    bind_task_presets(raw, source, resources, prefix="rt", resume="navigate", category="ryou_toppa")

    arrived = next(step for step in raw["states"] if step["id"] == "rt_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_ryou")]
    next(step for step in raw["states"] if step["id"] == "rt_nav_drive")["when"] = phase("navigate")

    # Enter guild raid & detect status
    state("open_realm_raid_tab", "enter_ryou", [asset("I_REALM_RAID", "RealmRaid")],
          click("I_REALM_RAID", "RealmRaid", 1000))
    state("switch_to_ryou_tab", "enter_ryou", [asset("I_REAL_RAID_REFRESH"), asset("I_RYOU_TOPPA")],
          click("I_RYOU_TOPPA", "RyouToppa", 1000))
    state("penetration_100", "enter_ryou", [asset("I_SUCCESS_PENETRATION")],
          advance("exit_main", rt_exit_reason="'penetration_100'",
                  rt_target_delay_s="rt_tomorrow_delay_s", rt_observed_ms="elapsed_ms", rt_main_arrived=0))
    state("not_open_member", "enter_ryou", [asset("I_NO_SELECT_RYOU")],
          advance("exit_main", rt_exit_reason="'not_open'", rt_main_arrived=0))
    state("not_open_no_access", "enter_ryou", [asset("I_SELECT_RYOU_BUTTON"), expr("not rt_ryou_access")],
          advance("exit_main", rt_exit_reason="'not_open_no_admin'", rt_main_arrived=0))
    state("admin_open_ryou", "enter_ryou", [asset("I_SELECT_RYOU_BUTTON"), expr("rt_ryou_access")],
          click("I_SELECT_RYOU_BUTTON", "RyouToppa", 1000), advance("admin_start"))
    state("ryou_open_ready", "enter_ryou",
          [{"any": [asset("I_RYOU_REWARD"), asset("I_RYOU_REWARD_90")]}], advance("check_lock"))

    state("admin_pick_first", "admin_start", [asset("I_GUILD_ORDERS_REWARDS")],
          click("C_SELECT_FIRST_RYOU", "RyouToppa", 1000))
    state("admin_confirm_start", "admin_start", [asset("I_START_TOPPA_BUTTON")],
          click("I_START_TOPPA_BUTTON", "RyouToppa", 1000), {"set": {"rt_admin_started": True}})
    raw["states"][-1].update(
        sensitive="购买",
        desc="寮管理开启新的阴阳寮结界突破，将消耗阴阳寮突破次数或勋章。",
    )
    state("admin_started_ok", "admin_start", [asset("I_RYOU_REWARD")], advance("check_lock"))

    locked, unlocked = asset("I_TOPPA_LOCK_TEAM"), asset("I_TOPPA_UNLOCK_TEAM")
    state("lock_ready", "check_lock", [{"any": [
        {"all": [expr("lock_team_enable"), locked]},
        {"all": [expr("not lock_team_enable"), unlocked]},
    ]}], advance("cycle", rt_area=1))
    state("lock_on", "check_lock", [expr("lock_team_enable"), unlocked], click("I_TOPPA_UNLOCK_TEAM", "RyouToppa", 1000))
    state("lock_off", "check_lock", [expr("not lock_team_enable"), locked], click("I_TOPPA_LOCK_TEAM", "RyouToppa", 1000))

    # Attack cycle
    state("count_stop", "cycle", [asset("I_TOPPA_RECORD"), expr("rt_attempts >= rt_limit_count")],
          advance("exit_main", rt_exit_reason="'count'", rt_main_arrived=0))
    state("time_stop", "cycle", [asset("I_TOPPA_RECORD"), expr("elapsed_ms >= rt_limit_seconds * 1000")],
          advance("exit_main", rt_exit_reason="'time'", rt_main_arrived=0))
    state("no_tickets_stop", "cycle",
          [asset("I_TOPPA_RECORD"), expr("not rt_unlimited_hours"),
           {"ocr": "RyouToppa::O_NUMBER", "mode": "counter_remaining", "var": "rt_tickets"},
           expr("rt_tickets == 0")],
          advance("exit_main", rt_exit_reason="'no_tickets'", rt_main_arrived=0))
    state("area_flush_exhausted", "cycle",
          [asset("I_TOPPA_RECORD"), expr("rt_area > 8 and rt_flushes >= rt_max_flushes")],
          advance("exit_main", rt_exit_reason="'areas_exhausted'", rt_main_arrived=0))
    state("area_flush_scroll", "cycle",
          [asset("I_TOPPA_RECORD"), expr("rt_area > 8 and rt_flushes < rt_max_flushes")],
          {"swipe": {"from": [720, 480, 760, 500], "to": [720, 370, 760, 390]},
           "duration_ms": [320, 380], "delay": 1500, "recheck": True},
          {"set": {"rt_area": 1}}, {"inc": "rt_flushes"})
    for idx in range(1, 9):
        finished = {"any": [asset(f"I_AREA_{idx}_FINISHED"), asset(f"I_AREA_{idx}_FINISHED_NEW")]}
        failed = {"any": [asset(f"I_AREA_{idx}_IS_FAILURE"), asset(f"I_AREA_{idx}_IS_FAILURE_NEW")]}
        state(f"area_finished_{idx}", "cycle", [asset("I_TOPPA_RECORD"), expr(f"rt_area == {idx}"), finished],
              advance("exit_main", rt_exit_reason="'all_finished'",
                      rt_target_delay_s="rt_tomorrow_delay_s", rt_observed_ms="elapsed_ms", rt_main_arrived=0))
        state(f"skip_area_{idx}", "cycle", [asset("I_TOPPA_RECORD"), expr(f"rt_area == {idx}"), failed],
              {"set": {"rt_area": idx + 1}})
        state(f"tap_area_{idx}", "cycle", [asset("I_TOPPA_RECORD"), expr(f"rt_area == {idx}")],
              click(f"C_AREA_{idx}", "RyouToppa", 1000), advance("fire_area"))

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    reset[outputs["current_count"]] = "rt_attempts"
    state("fire_attack", "fire_area", [asset("I_FIRE", "RealmRaid")],
          click("I_FIRE", "RealmRaid", 1000), {"set": reset}, advance("battle"))
    state("fire_missing_next", "fire_area", [{"not": asset("I_FIRE", "RealmRaid")}],
          advance("cycle", rt_area="rt_area + 1"))

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("cycle", rt_attempts=outputs["current_count"],
                                       rt_wins=f"rt_wins + {outputs['win']}", rt_area="rt_area + 1")]
        raw["states"].append(step)

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main_tomorrow", "exit_main", [court, expr("rt_main_arrived == 1 and rt_target_delay_s > 0")], {
        "stop": {
            "reason": "寮突破已全部攻破并返回庭院，已预约次日运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "RyouToppa",
                "delay_seconds_var": "rt_target_delay_s",
                "observed_ms_var": "rt_observed_ms",
            },
            "evidence": {"scope": "ryou_toppa_tomorrow_schedule"},
        }
    })
    state("returned_main_next_prep", "exit_main",
          [court, expr("rt_main_arrived == 1 and rt_target_delay_s == 0 and rt_next_delay_s > 0")],
          advance("stop_target", rt_target_delay_s="rt_next_delay_s", rt_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "寮突破已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "RyouToppa",
                "delay_seconds_var": "rt_target_delay_s",
                "observed_ms_var": "rt_observed_ms",
            },
            "evidence": {"scope": "ryou_toppa_target_schedule"},
        }
    })
    state("returned_main", "exit_main", [court, expr("rt_main_arrived == 1")], {
        "stop": {
            "reason": "寮突破已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "RyouToppa",
            "evidence": {"scope": "ryou_toppa_native_path"},
        }
    })
    state("exit_back_red", "exit_main", [{"not": court}, asset("I_BACK_RED", "RealmRaid")],
          click("I_BACK_RED", "RealmRaid", 1000))
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": "rt_main_arrived"}})

    raw["oas_ryou_toppa_contract"] = {
        "source": RYOU_TOPPA_ENTRY,
        "source_pins": {**RYOU_TOPPA_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"], {
            "id": "ryou_toppa_flush_scroll_and_live",
            "blocking": True,
            "requirement": "Bind area list scroll flush, tomorrow custom_next_run, and live guild raid verification",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_realm_raid_candidate(source_root, resource_dir, *, calibrations=None, order_attack=None):
    """Compile pinned OAS RealmRaid (personal realm raid) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, REALM_RAID_PINS, "RealmRaid")
    if order_attack is not None:
        _verify_pins(source, REALM_RAID_MEDAL_PINS, "RealmRaid medal selection")
        parts = "".join(order_attack.split()).split(">") if isinstance(order_attack, str) else []
        if not parts or any(part not in "012345" or len(part) != 1 for part in parts):
            raise ValueError("RealmRaid order_attack requires medal counts 0–5 separated by >")
        medal_order = list(dict.fromkeys(map(int, parts)))
    nav = compile_navigation_family(
        source, resources, prefix="rr_nav", destination="page_realm_raid",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="rr_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_realm_raid_natively_staged", title="个人突破", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        rr_number_attack={"default": 30, "min": 1, "max": 30},
        rr_number_base={"default": 0, "min": 0, "max": 20},
        rr_exit_four={"default": False},
        rr_three_refresh={"default": False},
        rr_when_attack_fail={"default": "continue", "choices": ["continue", "refresh", "exit"]},
        rr_refresh_when_no_target={"default": False},
        rr_max_refreshes={"default": 3, "min": 0, "max": 20},
        rr_limit_seconds={"default": 0, "min": 0, "max": 7200},
        rr_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        rr_phase="entry", rr_attempts=0, rr_wins=0, rr_tickets=-1,
        rr_slot=1, rr_retreats=0, rr_last_win=1, rr_refreshes=0,
        rr_target_delay_s=0, rr_observed_ms=0, rr_main_arrived=0, rr_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/RealmRaid.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("RealmRaid", "Component_GeneralBattle", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"rr_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"rr_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"rr_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="RealmRaid"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="RealmRaid", delay=1000):
        return _click_from(docs, name, ns, delay)

    bind_task_presets(raw, source, resources, prefix="rr", resume="navigate", category="realm_raid")

    arrived = next(step for step in raw["states"] if step["id"] == "rr_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("check_lock")]
    next(step for step in raw["states"] if step["id"] == "rr_nav_drive")["when"] = phase("navigate")

    locked = {"any": [asset("I_LOCK"), asset("I_LOCK_2")]}
    unlocked = {"any": [asset("I_UNLOCK"), asset("I_UNLOCK_2")]}
    state("dismiss_frog_popup", "check_lock", [asset("I_FROG_RAID")], click("I_FROG_RAID", "RealmRaid", 1000))
    state("lock_ready", "check_lock", [{"any": [
        {"all": [expr("lock_team_enable"), locked]},
        {"all": [expr("not lock_team_enable"), unlocked]},
    ]}], advance("cycle", rr_slot=1))
    state("lock_on_1", "check_lock", [expr("lock_team_enable"), asset("I_UNLOCK")], click("I_UNLOCK", "RealmRaid", 1000))
    state("lock_on_2", "check_lock", [expr("lock_team_enable"), asset("I_UNLOCK_2")], click("I_UNLOCK_2", "RealmRaid", 1000))
    state("lock_off_1", "check_lock", [expr("not lock_team_enable"), asset("I_LOCK")], click("I_LOCK", "RealmRaid", 1000))
    state("lock_off_2", "check_lock", [expr("not lock_team_enable"), asset("I_LOCK_2")], click("I_LOCK_2", "RealmRaid", 1000))

    state("popup_confirm", "cycle", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1500))
    state("three_win_reward", "cycle", [asset("I_SOUL_RAID")], click("I_SOUL_RAID", "RealmRaid", 1500))
    state("time_limit_stop", "cycle",
          [expr("rr_limit_seconds > 0 and elapsed_ms >= rr_limit_seconds * 1000")],
          advance("exit_main", rr_exit_reason="'time_limit'", rr_main_arrived=0))
    board = {"all": [asset("I_BACK_RED"), asset("I_RR_PERSON")]}
    read_tickets = {"ocr": "RealmRaid::O_NUMBER", "mode": "counter_current", "var": "rr_tickets"}
    state("count_stop", "cycle", [board, expr("rr_attempts >= rr_number_attack")],
          advance("exit_main", rr_exit_reason="'count'", rr_main_arrived=0))
    state("ticket_stop", "cycle", [board, read_tickets, expr("rr_tickets == 0 or rr_tickets < rr_number_base")],
          advance("exit_main", rr_exit_reason="'tickets'", rr_main_arrived=0))
    state("ticket_unreadable", "cycle", [board, {"not": read_tickets}], {"fail": "无法读取个人突破券的当前数量"})
    state("fail_exit_stop", "cycle",
          [asset("I_BACK_RED"), expr("rr_last_win == 0 and rr_when_attack_fail == 'exit'")],
          advance("exit_main", rr_exit_reason="'battle_lost'", rr_main_arrived=0))
    state("fail_refresh_tap", "cycle",
          [asset("I_BACK_RED"), expr("rr_last_win == 0 and rr_when_attack_fail == 'refresh'"), asset("I_FRESH")],
          click("I_FRESH", "RealmRaid", 1500), {"set": {"rr_slot": 1, "rr_retreats": 0, "rr_last_win": 1}})
    state("three_refresh_tap", "cycle",
          [expr("rr_three_refresh"), asset("I_RR_THREE"), asset("I_FRESH")],
          click("I_FRESH", "RealmRaid", 1500), {"set": {"rr_slot": 1, "rr_retreats": 0}})
    may_select = [board, read_tickets, expr("rr_tickets > 0 and rr_tickets >= rr_number_base")]
    if order_attack is None:
        state("slot_wrap_refresh", "cycle", [expr("rr_slot > 9"), asset("I_FRESH")],
              click("I_FRESH", "RealmRaid", 1500), {"set": {"rr_slot": 1, "rr_retreats": 0}})
        state("slot_wrap_exit", "cycle", [expr("rr_slot > 9")],
              advance("exit_main", rr_exit_reason="'no_targets'", rr_main_arrived=0))
        for slot in range(1, 10):
            state(f"tap_partition_{slot}", "cycle", [*may_select, expr(f"rr_slot == {slot}")],
                  click(f"C_PARTITION_{slot}", "RealmRaid", 1000), advance("fire_slot"))
    else:
        raw["resources"] = sorted({*raw["resources"], "upstream/oas/RyouToppa.yaml"})
        raw["vars"]["rr_card_open_ms"] = -1
        cells = []
        for slot in range(1, 10):
            x, y, x2, y2 = docs["RealmRaid"][f"C_PARTITION_{slot}"]["rect"]
            cells.append([x, y, x2 - x, y2 - y])
        grid = {"templates": [f"RealmRaid::I_MEDAL_{count}" for count in medal_order],
                "cells": cells, "cell_var": "rr_slot"}
        misses = {"template": "RyouToppa::I_AREA_1_IS_FAILURE",
                  "regions": [[x, y, 86, 64] for y in (143, 277, 414) for x in (386, 714, 1047)]}
        opened = advance("fire_slot", rr_card_open_ms="elapsed_ms")
        state("continue_slot_one_retreats", "cycle", [*may_select, expr("rr_exit_four and rr_slot == 1 and rr_retreats > 0")],
              click("C_PARTITION_1", "RealmRaid", 1000), opened)
        for mode, guard, plan in (("omit_failed", "rr_when_attack_fail == 'continue'", {**grid, "exclude": misses}),
                                  ("all_cards", "rr_when_attack_fail != 'continue'", grid)):
            state("choose_medal_" + mode, "cycle", [*may_select, expr(guard), {"image_grid": plan}],
                  {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}, opened)
        state("no_ranked_target_refresh", "cycle", [
            *may_select,
            expr("rr_refresh_when_no_target and rr_refreshes < rr_max_refreshes"),
            asset("I_FRESH"),
        ], click("I_FRESH", "RealmRaid", 1500), {"set": {"rr_slot": 1, "rr_retreats": 0}}, {"inc": "rr_refreshes"})
        state("no_ranked_target", "cycle", may_select,
              advance("exit_main", rr_exit_reason="'no_targets'", rr_main_arrived=0))

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    reset[outputs["current_count"]] = "rr_attempts"
    fire = asset("I_FIRE")
    click_fire = {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}
    # Slot-1 four-retreat cycle (matches RealmRaid/script_task.py lines 190-201)
    state("fire_retreat_slot1", "fire_slot",
          [expr("rr_exit_four and rr_slot == 1 and rr_retreats < 4"), fire],
          click_fire, advance("retreat_battle"))
    state("retreat_back_to_board", "retreat_battle", [asset("I_BACK_RED")],
          advance("cycle", rr_retreats="rr_retreats + 1"))
    state("retreat_dismiss_false", "retreat_battle", [asset("I_FALSE", "Component_GeneralBattle")],
          click("C_WIN_1", "Component_GeneralBattle", 800))
    state("retreat_confirm", "retreat_battle", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 800))
    state("retreat_tap_exit", "retreat_battle", [asset("I_EXIT", "Component_GeneralBattle")],
          click("I_EXIT", "Component_GeneralBattle", 800))
    state("fire_attack", "fire_slot", [fire],
          click_fire, {"set": reset}, advance("battle"))
    if order_attack is None:
        state("fire_missing_next", "fire_slot", [{"not": fire}], advance("cycle", rr_slot="rr_slot + 1"))
    else:
        state("chosen_card_missing_attack", "fire_slot", [{"not": fire}, expr("elapsed_ms - rr_card_open_ms >= 6000")],
              {"fail": "勋章目标详情未显示进攻按钮"})

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("cycle", rr_attempts=outputs["current_count"],
                                       rr_wins=f"rr_wins + {outputs['win']}",
                                       rr_last_win=outputs["win"], rr_slot="rr_slot + 1")]
        raw["states"].append(step)

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main_target_prep", "exit_main",
          [court, expr("rr_main_arrived == 1 and rr_next_delay_s > 0")],
          advance("stop_target", rr_target_delay_s="rr_next_delay_s", rr_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "个人突破已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "RealmRaid",
                "delay_seconds_var": "rr_target_delay_s",
                "observed_ms_var": "rr_observed_ms",
            },
            "evidence": {"scope": "realm_raid_target_schedule"},
        }
    })
    state("returned_main", "exit_main", [court, expr("rr_main_arrived == 1")], {
        "stop": {
            "reason": "个人突破已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "RealmRaid",
            "evidence": {"scope": "realm_raid_native_path"},
        }
    })
    state("exit_back_red", "exit_main", [{"not": court}, asset("I_BACK_RED")],
          click("I_BACK_RED", "RealmRaid", 1000))
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": "rr_main_arrived"}})

    raw["oas_realm_raid_contract"] = {
        "source": REALM_RAID_ENTRY,
        "source_pins": {**REALM_RAID_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"], {
            "id": "realm_raid_exit_four_medal_order_and_live",
            "blocking": True,
            "requirement": "Bind exit_four 4-retreat cycle, medal priority ordering, frog raid unlock, and live verification",
        }],
    }
    if order_attack is not None:
        review = raw["oas_realm_raid_contract"]
        review["source_pins"].update(REALM_RAID_MEDAL_PINS)
        review["medal_order"] = medal_order
        review["source_obligations"][-1]["requirement"] = (
            "Verify four retreat and frog unlock behavior on live frames; bind a safe refresh for a board with no ranked target"
        )
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_area_boss_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS AreaBoss workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, AREA_BOSS_PINS, "AreaBoss")
    nav = compile_navigation_family(
        source, resources, prefix="ab_nav", destination="page_area_boss",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="ab_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_area_boss_natively_staged", title="地域鬼王", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1800
    bind_schedule(source, raw)
    raw["params"].update(
        ab_use_collect={"default": False},
        ab_boss_reward={"default": False},
        ab_dedup_reward_boss={"default": False},
        ab_reward_floor={"default": "default", "choices": ["default", "normal_lv1", "normal_lv60", "ji_1", "ji_10"]},
        ab_use_custom_count={"default": False},
        ab_boss_number={"default": 3, "min": 1, "max": 3},
        ab_limit_seconds={"default": 1800, "min": 0, "max": 3600},
        ab_next_delay_s={"default": 0, "min": 0, "max": 172800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        ab_phase="entry", ab_rep=-1, ab_target_count=1, ab_fought=0,
        ab_slot=1, ab_wins=0, ab_target_delay_s=0, ab_observed_ms=0, ab_exit_reason="",
        ab_reward_done=False, ab_reward_slot=1, ab_reward_swiped=False, ab_reward_challenges=0,
        ab_reward_boss_name="", ab_current_boss_name="", ab_skipped_dups=0,
        ab_in_reward_phase=False, ab_difficulty_set=False,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/AreaBoss.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("AreaBoss", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"ab_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"ab_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"ab_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="AreaBoss"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="AreaBoss", delay=1000):
        return _click_from(docs, name, ns, delay)

    bind_task_presets(raw, source, resources, prefix="ab", resume="navigate", category="area_boss")

    arrived = next(step for step in raw["states"] if step["id"] == "ab_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("dispatch_mode")]
    next(step for step in raw["states"] if step["id"] == "ab_nav_drive")["when"] = phase("navigate")

    state("dispatch_reward", "dispatch_mode", [expr("ab_boss_reward and not ab_reward_done")],
          advance("reward_filter", ab_reward_slot=1, ab_in_reward_phase=True))
    state("dispatch_regular", "dispatch_mode", [], advance("open_filter", ab_in_reward_phase=False))

    # Optional reward boss scan (mirrors fight_reward_boss / switch_to_reward)
    state("reward_tab_ready", "reward_filter", [asset("I_AB_FILTER_TITLE_REWARD")], advance("reward_pick"))
    state("reward_tab_click", "reward_filter", [asset("I_AB_FILTER_OPENED")],
          click("C_AB_REWARD_BTN", "AreaBoss", 1500))
    state("reward_filter_tap", "reward_filter", [asset("I_FILTER")], click("I_FILTER", "AreaBoss", 3000))

    state("reward_slots_exhausted", "reward_pick", [expr("ab_reward_slot > 5")],
          advance("open_filter", ab_reward_done=True, ab_in_reward_phase=False))
    state("reward_swipe_bottom", "reward_pick", [expr("ab_reward_slot == 4 and not ab_reward_swiped")],
          {"swipe": "AreaBoss::S_AB_FILTER_UP", "delay": 1200, "recheck": True},
          {"set": {"ab_reward_swiped": True}})
    for ridx, photo_name in (
        (1, "C_AB_BOSS_REWARD_PHOTO_1"),
        (2, "C_AB_BOSS_REWARD_PHOTO_2"),
        (3, "C_AB_BOSS_REWARD_PHOTO_3"),
        (4, "C_AB_BOSS_REWARD_PHOTO_MINUS_2"),
        (5, "C_AB_BOSS_REWARD_PHOTO_MINUS_1"),
    ):
        state(f"reward_open_{ridx}", "reward_pick", [expr(f"ab_reward_slot == {ridx}")],
              click(photo_name, "AreaBoss", 1500),
              advance("reward_check", ab_difficulty_set=False))
    state("reward_hot_enough_named", "reward_check", [
        expr("ab_dedup_reward_boss"),
        asset("I_AB_CLOSE_RED"), asset("I_FIRE"), {"not": asset("I_AB_NUM_CHALLENGE_RAIL")},
        {"ocr": "AreaBoss::O_AB_NUM_OF_CHALLENGE", "var": "ab_reward_challenges", "test": "ab_reward_challenges >= 20000"},
        {"ocr": "AreaBoss::O_AB_BOSS_NAME", "mode": "text_sequence", "var": "ab_reward_boss_name"},
    ], advance("setup_floor", ab_difficulty_set=False))
    state("reward_hot_enough", "reward_check", [
        asset("I_AB_CLOSE_RED"), asset("I_FIRE"), {"not": asset("I_AB_NUM_CHALLENGE_RAIL")},
        {"ocr": "AreaBoss::O_AB_NUM_OF_CHALLENGE", "var": "ab_reward_challenges", "test": "ab_reward_challenges >= 20000"},
    ], advance("setup_floor", ab_difficulty_set=False))
    state("reward_not_hot_close", "reward_check", [asset("I_AB_CLOSE_RED")],
          click("I_AB_CLOSE_RED", "AreaBoss", 1000),
          advance("reward_pick", ab_reward_slot="ab_reward_slot + 1"))
    state("reward_detail_unavailable", "reward_check", [{"not": asset("I_AB_CLOSE_RED")}],
          advance("reward_pick", ab_reward_slot="ab_reward_slot + 1"))

    state("filter_opened_collect", "open_filter", [asset("I_AB_FILTER_OPENED"), expr("ab_use_collect")],
          click("C_AB_COLLECTION_BTN", "AreaBoss", 1000), advance("read_rep"))
    state("filter_opened_famous", "open_filter", [asset("I_AB_FILTER_OPENED"), expr("not ab_use_collect")],
          click("C_AB_FAMOUS_BTN", "AreaBoss", 1000), advance("read_rep"))
    state("filter_tap", "open_filter", [asset("I_FILTER")], click("I_FILTER", "AreaBoss", 3000))

    # Dynamic boss count by reputation OCR (>=10000 -> 3, >=2000 -> 2, else 1) or explicit override
    state("rep_custom_count", "read_rep", [expr("ab_use_custom_count")],
          advance("pick_boss", ab_target_count="ab_boss_number", ab_slot=1))
    state("rep_tier_3", "read_rep",
          [{"ocr": "AreaBoss::O_AB_REPUTATION", "var": "ab_rep", "test": "ab_rep >= 10000"}],
          advance("pick_boss", ab_target_count=3, ab_slot=1))
    state("rep_tier_2", "read_rep",
          [{"ocr": "AreaBoss::O_AB_REPUTATION", "var": "ab_rep", "test": "ab_rep >= 2000"}],
          advance("pick_boss", ab_target_count=2, ab_slot=1))
    state("rep_tier_1", "read_rep", [], advance("pick_boss", ab_target_count=1, ab_slot=1))

    state("time_limit_reached", "pick_boss", [expr("elapsed_ms >= ab_limit_seconds * 1000")],
          advance("exit_main", ab_exit_reason="'time_limit'"))
    state("count_reached", "pick_boss", [expr("ab_fought >= ab_target_count or ab_slot > 3")],
          advance("exit_main", ab_exit_reason="'done'"))
    for idx in (1, 2, 3):
        btn = f"I_BATTLE_{idx}"
        state(f"open_boss_{idx}", "pick_boss", [expr(f"ab_slot == {idx}"), asset(btn)],
              click(btn, "AreaBoss", 1000), advance("setup_floor", ab_difficulty_set=False))
        state(f"skip_boss_{idx}", "pick_boss", [expr(f"ab_slot == {idx}"), {"not": asset(btn)}],
              {"set": {"ab_slot": idx + 1}})

    # Difficulty & floor setup (normal_lv1 / normal_lv60 / ji_1 / ji_10 / default) + defeated reward-boss dedup
    state("dedup_skip_reward_boss", "setup_floor", [
        expr("ab_dedup_reward_boss and not ab_in_reward_phase and ab_reward_boss_name != ''"),
        asset("I_AB_CLOSE_RED"),
        {"ocr": "AreaBoss::O_AB_BOSS_NAME", "mode": "text_sequence", "var": "ab_current_boss_name"},
        expr("ab_current_boss_name == ab_reward_boss_name"),
    ], click("I_AB_CLOSE_RED", "AreaBoss", 1000), {"inc": "ab_skipped_dups"},
       advance("pick_boss", ab_slot="ab_slot + 1"))
    state("floor_default", "setup_floor", [expr("ab_reward_floor == 'default'")], advance("fire_boss"))
    state("floor_to_normal", "setup_floor", [
        expr("ab_reward_floor == 'normal_lv1' or ab_reward_floor == 'normal_lv60'"),
        asset("I_AB_DIFFICULTY_JI"),
    ], click("I_AB_DIFFICULTY_JI", "AreaBoss", 1500))
    state("floor_normal_lv1_done", "setup_floor", [
        expr("ab_reward_floor == 'normal_lv1'"), {"not": asset("I_AB_DIFFICULTY_JI")},
    ], advance("fire_boss", ab_difficulty_set=True))
    state("floor_normal_lv60_done", "setup_floor", [
        expr("ab_reward_floor == 'normal_lv60'"), {"not": asset("I_AB_DIFFICULTY_JI")}, asset("I_AB_LEVEL_60"),
    ], advance("fire_boss", ab_difficulty_set=True))
    state("floor_normal_lv60_swipe", "setup_floor", [
        expr("ab_reward_floor == 'normal_lv60'"), {"not": asset("I_AB_DIFFICULTY_JI")}, asset("I_AB_LEVEL_HANDLE"),
    ], {"swipe": "AreaBoss::S_AB_LEVEL_RIGHT", "delay": 1500, "recheck": True})
    state("floor_to_ji", "setup_floor", [
        expr("ab_reward_floor == 'ji_1' or ab_reward_floor == 'ji_10'"),
        asset("I_AB_DIFFICULTY_NORMAL"),
    ], click("I_AB_DIFFICULTY_NORMAL", "AreaBoss", 1500))
    state("floor_ji_pick_1", "setup_floor", [
        expr("ab_reward_floor == 'ji_1'"), asset("I_AB_JI_FLOOR_LIST_CHECK"), asset("I_AB_JI_FLOOR_ONE"),
    ], click("I_AB_JI_FLOOR_ONE", "AreaBoss", 1000), advance("fire_boss", ab_difficulty_set=True))
    state("floor_ji_scroll_1", "setup_floor", [
        expr("ab_reward_floor == 'ji_1'"), asset("I_AB_JI_FLOOR_LIST_CHECK"), {"not": asset("I_AB_JI_FLOOR_ONE")},
    ], {"swipe": "AreaBoss::S_AB_FLOOR_DOWN", "delay": 1000, "recheck": True})
    state("floor_ji_pick_10", "setup_floor", [
        expr("ab_reward_floor == 'ji_10'"), asset("I_AB_JI_FLOOR_LIST_CHECK"), asset("I_AB_JI_FLOOR_TEN"),
    ], click("I_AB_JI_FLOOR_TEN", "AreaBoss", 1000), advance("fire_boss", ab_difficulty_set=True))
    state("floor_ji_open_list", "setup_floor", [
        expr("ab_reward_floor == 'ji_1' or ab_reward_floor == 'ji_10'"), asset("I_AB_DIFFICULTY_JI"),
    ], click("C_AB_JI_FLOOR_SELECTED", "AreaBoss", 1500))
    state("floor_fallback_fire", "setup_floor", [asset("I_FIRE")], advance("fire_boss"))

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    state("fire_boss_tap", "fire_boss", [asset("I_FIRE")],
          click("I_FIRE", "AreaBoss", 1000), {"set": reset}, advance("battle"))
    state("fire_boss_close_missing", "fire_boss", [{"not": asset("I_FIRE")}, asset("I_AB_CLOSE_RED")],
          click("I_AB_CLOSE_RED", "AreaBoss", 1000), advance("pick_boss", ab_slot="ab_slot + 1"))

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("close_detail", ab_fought="ab_fought + 1",
                                       ab_wins=f"ab_wins + {outputs['win']}")]
        raw["states"].append(step)

    state("detail_reward_popup", "close_detail", [asset("I_UI_REWARD", "GlobalGame")],
          click("C_UI_REWARD", "GlobalGame", 400))
    state("detail_close_red", "close_detail", [asset("I_AB_CLOSE_RED")],
          click("I_AB_CLOSE_RED", "AreaBoss", 1000))
    state("detail_closed_after_reward", "close_detail", [{"not": asset("I_AB_CLOSE_RED")}, expr("ab_in_reward_phase")],
          advance("open_filter", ab_reward_done=True, ab_in_reward_phase=False))
    state("detail_closed_next", "close_detail", [{"not": asset("I_AB_CLOSE_RED")}],
          advance("pick_boss", ab_slot="ab_slot + 1"))

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main_target_prep", "exit_main", [court, expr("ab_next_delay_s > 0")],
          advance("stop_target", ab_target_delay_s="ab_next_delay_s", ab_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "地域鬼王已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "AreaBoss",
                "delay_seconds_var": "ab_target_delay_s",
                "observed_ms_var": "ab_observed_ms",
            },
            "evidence": {"scope": "area_boss_target_schedule"},
        }
    })
    state("returned_main", "exit_main", [court], {
        "stop": {
            "reason": "地域鬼王已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "AreaBoss",
            "evidence": {"scope": "area_boss_native_path"},
        }
    })
    state("exit_back_yellow", "exit_main", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 2000))

    raw["oas_area_boss_contract"] = {
        "source": AREA_BOSS_ENTRY,
        "source_pins": {**AREA_BOSS_PINS, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"], {
            "id": "area_boss_ultra_floor_reward_boss_and_live",
            "blocking": True,
            "requirement": "Bind boss_reward, ultra/normal difficulty floor toggles, and live reputation OCR frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
