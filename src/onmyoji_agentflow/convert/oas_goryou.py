"""Pinned OAS 御灵 entry, challenge loop, and return (GPL-3.0, runhey et al.)."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import compile_general_battle
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import bind_numbered_preset
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


ENTRY = "tasks/GoryouRealm/script_task.py"
PINS = {
    ENTRY: "0ff3902daf3a4a3d3280cbb8e43ee0dd24b97fc8401ba46fc2abde9d10e6007d",
    "tasks/GoryouRealm/config.py": "78b097f503e28054ae4233f53a90d7f4eab644aad751597e27ad4f9d242e231a",
    "tasks/GoryouRealm/assets.py": "4b27cc83f42df4c23215f3dca547166e94955bd93cf4b99c4deac44d734b2c62",
    "module/config/config_model.py": "b7554ef255a7005a1a605edbfd22cfc691f5c01d166f4750b411bc724eb72324",
    "tasks/Component/SwitchSoul/switch_soul.py": "be5fd7ff6c306d090042e31f2d4d5c4a898f32316bac8a9f86c76b9862a08b1d",
    "tasks/Component/SwitchSoul/assets.py": "c82f172a4e42f6b997a2ffb4c4caabc347a47a688ab81ba956ace86fc6e70b5f",
    "tasks/Component/SwitchSoul/switch_soul_config.py": "6ebf245f01ae1e4fd28f27aa909b8ff75cf2dd4dd60750c5dbe533c98a162d61",
    "tasks/Component/GeneralBattle/general_battle.py":
        "40eee94e4a73717502a81e016968ae97fb289c838952b5ee4be519c9e3ca798a",
}
BOSSES = ("暗神龙", "暗白蔵主", "暗黑豹", "暗孔雀")
BOSS_TAB_TOP = (108, 264, 422, 578)
SKIN_TASK = "Component_CostumeShikigami"
SKIN_SOURCE = "tasks/Component/CostumeShikigami/assets.py"
SKIN_PINS = {
    SKIN_SOURCE: "a872256c0ad6bacae2c08fff9287e178441ae43c9d88645f6f17e1716b9fcf24",
    "tasks/Component/Costume/config.py": "f1f86fa6019b673280a31b7442a4e1df0dbabcfcd11c50c05c7517ad8847dfc2",
    "tasks/Component/Costume/costume_base.py": "4467807636bec23d24994091a3f39497e88aa3a66d5d197f94471d1d70021865",
    "tasks/GameUi/default_pages.py": "c6da4ba1904eb585fcc9fa7adc4d709d097a13fc324a4f37fe032629c47f066f",
}


def _shikigami_assets(source, resources, costume):
    """Lower check_costume_shikigami's replacement of declared RuleImages."""
    if type(costume) is not int or not 0 <= costume <= 13:
        raise ValueError("GoryouRealm shikigami costume must be an integer from 0 to 13")
    if not costume:
        return {}, {}
    for path, expected in SKIN_PINS.items():
        text = (source / path).read_text(encoding="utf-8-sig")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"GoryouRealm costume source fingerprint mismatch: {path}")

    tree = ast.parse((source / SKIN_SOURCE).read_text(encoding="utf-8-sig"))
    assets = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CostumeShikigamiAssets")
    declared = {target.id for node in assets.body if isinstance(node, ast.Assign)
                for target in node.targets if isinstance(target, ast.Name)}
    document = load_yaml(resources / f"{SKIN_TASK}.yaml")["resources"]
    preset_names = ("I_SOUL_PRESET", "I_SOU_TEAM_PRESENT", *(f"I_SOU_CHECK_GROUP_{n}" for n in range(1, 8)),
                    *(f"I_SOU_SWITCH_{n}" for n in range(1, 5)))
    targets = [("GameUi", "I_CHECK_RECORDS"), *(("Component_SwitchSoul", name) for name in preset_names)]
    aliases = {}
    for namespace, name in targets:
        variant = f"{name}_{costume}"
        if variant not in declared:
            continue  # BaseTask's hasattr check retains the base asset here.
        if document.get(variant, {}).get("type") != "image":
            raise ValueError(f"GoryouRealm missing converted costume asset: {variant}")
        aliases[namespace, name] = (SKIN_TASK, variant)
    return aliases, document


def goryou_selected_tab(index):
    tabs = [{"mean_color": {"region": [28, top, 6, 6], "rgb": [189, 163, 100], "tolerance": 24}}
            for top in BOSS_TAB_TOP]
    return {"all": [tabs[index - 1], {"not": {"any": tabs[:index - 1] + tabs[index:]}}]}


def compile_goryou_candidate(source_root, resource_dir, *, calibrations=None, shikigami_costume=0,
                             screen_boss_selection=False):
    """Build an isolated candidate with typed stop and business evidence."""
    source_root, resource_dir = Path(source_root), Path(resource_dir)
    for relative, expected in PINS.items():
        text = (source_root / relative).read_text(encoding="utf-8-sig")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"GoryouRealm source fingerprint mismatch: {relative}")

    costumes, costume_document = _shikigami_assets(source_root, resource_dir, shikigami_costume)
    navigation = compile_navigation_family(source_root, resource_dir, prefix="gr_nav",
                                           destination="page_goryou_realm", battle_config="default",
                                           android_login=True, calibrations=calibrations, separate_battle_defaults=True,
                                           asset_overrides=costumes)
    battle = compile_general_battle(source_root, resource_dir, prefix="gr_battle")
    if not battle["guarded_executable"]:
        raise ValueError("GoryouRealm cannot bind the pinned battle fragment")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]
    raw = navigation["workflow"]
    raw["name"] = "oas_goryou_realm_natively_staged"
    raw["title"] = "御灵之境"
    raw["loop_delay_ms"] = 250
    bind_schedule(source_root, raw)
    raw["params"].update({
        "goryou_class": {"default": "随机", "choices": ["随机", *BOSSES]},
        "goryou_limit_count": {"default": 30, "min": 0},
        "goryou_limit_seconds": {"default": 1800, "min": 0, "max": 3600},
        "goryou_switch_soul_enabled": {"default": False},
        "goryou_soul_group": {"default": 0, "min": 0, "max": 7},
        "goryou_soul_team": {"default": 0, "min": 0, "max": 4},
    })
    if set(raw["params"]) & set(body["params"]):
        raise ValueError("GoryouRealm navigation and battle config bindings overlap")
    raw["params"].update(body["params"])
    raw["vars"].update(body["vars"])
    raw["vars"].update(gr_phase="entry", gr_boss=0, gr_tickets=-1, gr_live_tickets=-1,
                       gr_post_tickets=-1, gr_ticket_receipts=0,
                       gr_challenge_since=-1, gr_settled_since=-1, gr_wins=0, gr_attempts=0, gr_exit_reason="")
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/GoryouRealm.yaml", "upstream/oas/Component_SwitchSoul.yaml"]))
    raw["limits"]["timeout_s"] = 3700

    def expr(value):
        return {"expr": value}

    def phase(value):
        return expr(f"gr_phase == {value!r}")

    def goto(value):
        return {"set": {"gr_phase": repr(value)}}

    def state(name, where, do, *guards):
        raw["states"].append({"id": f"gr_{name}", "when": {"all": [phase(where), *guards]}, "do": do})

    def click(resource):
        namespace, name = resource.split("::")
        spec = documents[namespace][name]
        if spec["type"] == "click":
            target = spec["rect"]
        else:
            x, y, width, height = spec["front"]
            target = [x, y, x + width, y + height]
        return {"click": target, "delay": 1000, "recheck": True}

    documents = {namespace: load_yaml(resource_dir / f"{namespace}.yaml")["resources"]
                 for namespace in ("GoryouRealm", "GlobalGame", "Component_SwitchSoul")}
    if costumes:
        documents[SKIN_TASK] = costume_document
        raw["resources"] = sorted(set(raw["resources"] + [f"upstream/oas/{SKIN_TASK}.yaml"]))

    def soul_asset(name):
        key = ("Component_SwitchSoul", name)
        return "::".join(costumes.get(key, key))
    fire = {"res": "GoryouRealm::I_GR_FIRE"}
    locked = {"res": "GoryouRealm::I_GR_LOCK"}
    unlocked = {"res": "GoryouRealm::I_GR_UNLOCK"}
    selector = {"res": "GameUi::I_CHECK_GORYOU"}
    exploration = {"all": [
        {"res": "GameUi::I_CHECK_EXPLORATION"}, {"not": fire}, {"not": selector},
    ]}
    back = {"res": "GlobalGame::I_UI_BACK_YELLOW"}
    returned = next(st for st in raw["states"] if st["id"] == "gr_nav_returned")
    returned["when"]["all"].append(phase("navigation"))
    returned["do"] = [{"sample_int": {"var": "gr_boss", "min": 1, "max": 4}}, goto("select")]
    drive = next(st for st in raw["states"] if st["id"] == "gr_nav_drive")
    drive["when"] = phase("navigation")
    drive["do"][0]["navigate"]["category"] = "goryou_realm"
    state("soul_skip", "entry", [goto("navigation")], expr("not goryou_switch_soul_enabled"))
    state("soul_unconfigured", "entry", [{"fail": "请设置有效的御灵御魂预设分组和队伍"}],
          expr("goryou_switch_soul_enabled and (goryou_soul_group == 0 or goryou_soul_team == 0)"))
    state("soul_begin", "entry", [goto("soul_records")], expr("goryou_switch_soul_enabled"))
    bind_numbered_preset(raw, state, goto, click, soul_asset, prefix="gr", group="goryou_soul_group",
                        team="goryou_soul_team", resume="navigation", category="goryou_realm")
    selected = []
    for index, name in enumerate(BOSSES, 1):
        desired = expr(f"goryou_class == {name!r} or (goryou_class == '随机' and gr_boss == {index})")
        selected.append({"all": [desired, goryou_selected_tab(index)]})
        state(f"select_{index}", "select", [click(f"GoryouRealm::C_GR_C_{index}")], selector, {"not": fire},
              desired)
    chosen_boss = {"any": selected} if screen_boss_selection else expr("True")
    if screen_boss_selection:
        for index, entry in enumerate(selected, 1):
            y = BOSS_TAB_TOP[index - 1]
            other_tabs = [goryou_selected_tab(slot) for slot in range(1, 5) if slot != index]
            state(f"select_tab_{index}", "select",
                  [{"click": [32, y + 7, 60, y + 89], "delay": 1000, "recheck": True}],
                  entry["all"][0], fire, {"any": other_tabs})
    state("enter_lock", "select", [goto("lock")], fire, chosen_boss)
    lock_matches = {"any": [{"all": [expr("lock_team_enable"), locked, {"not": unlocked}]},
                            {"all": [expr("not lock_team_enable"), unlocked, {"not": locked}]}]}
    state("lock_correct", "lock", [goto("cycle")], fire, chosen_boss, lock_matches)
    state("lock", "lock", [click("GoryouRealm::I_GR_UNLOCK")],
          fire, chosen_boss, unlocked, {"not": locked}, expr("lock_team_enable"))
    state("unlock", "lock", [click("GoryouRealm::I_GR_LOCK")],
          fire, chosen_boss, locked, {"not": unlocked}, expr("not lock_team_enable"))

    for reason, condition in (
        ("count_limit", "gr_attempts >= goryou_limit_count"),
        ("time_limit", "elapsed_ms >= goryou_limit_seconds * 1000"),
    ):
        state(reason, "cycle", [{"set": {"gr_exit_reason": repr(reason)}}, goto("exit")], fire, expr(condition))
    ticket_ocr = {"ocr": "GoryouRealm::O_GR_TICKET", "mode": "exact_quantity"}
    state("read_tickets", "cycle", [goto("ticket_result")], fire, chosen_boss,
          {**ticket_ocr, "var": "gr_tickets"})
    state("no_tickets", "ticket_result", [{"set": {"gr_exit_reason": repr("no_tickets")}}, goto("exit")],
          fire, expr("gr_tickets == 0"))
    one_ticket = {"any": [{"ocr_single": {"region": [1058, 630, 92, 49], "equals": label}}
                          for label in ("×1", "x1", "X1")]}
    state("challenge", "ticket_result", [
        {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True},
        {"set": {"gr_challenge_since": "elapsed_ms"}}, goto("enter_battle"),
    ], chosen_boss, lock_matches, one_ticket, {**ticket_ocr, "var": "gr_live_tickets"},
       expr("gr_live_tickets == gr_tickets and gr_tickets > 0"), fire)
    state("challenge_unverified", "ticket_result", [{"fail": "御灵挑战前的首领、阵容或一张券报价无法核对"}], fire)
    state("challenge_unconfirmed", "enter_battle", [{"fail": "御灵挑战后未在八秒内离开挑战页"}],
          fire, expr("elapsed_ms - gr_challenge_since >= 8000"))
    # GeneralBattle's source keeps per-target interval clocks across this
    # task's battles. Per-battle state is reset at each challenge.
    persistent = set(contract["composition"]["interval_vars"])
    reset = {key: repr(value) if isinstance(value, str) else value for key, value in body["vars"].items()
             if key not in persistent}
    reset[outputs["current_count"]] = "gr_attempts"
    state("begin_battle", "enter_battle", [{"set": reset}, goto("battle")], {"not": fire})
    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [{"set": {"gr_attempts": outputs["current_count"],
                                        "gr_wins": f"gr_wins + {outputs['win']}",
                                        "gr_settled_since": "elapsed_ms"}}, goto("settled")]
        raw["states"].append(step)

    state("ticket_spend_verified", "settled", [{"inc": "gr_ticket_receipts"}, goto("cycle")],
          fire, chosen_boss, {**ticket_ocr, "var": "gr_post_tickets"},
          expr("gr_live_tickets - gr_post_tickets == 1"))
    state("ticket_spend_unverified", "settled", [{"fail": "御灵结算后无法核对一张券扣减"}],
          expr("elapsed_ms - gr_settled_since >= 12000"))
    state("completed_with_victory", "exit", [{"stop": {
          "reason": "御灵已核对胜场、挑战券扣减及返回探索",
          "result": "completed", "verified": True, "oas_schedule": "GoryouRealm",
          "evidence": {"scope": "victory_ticket_readback_and_return"},
    }}], exploration, expr("gr_wins > 0 and gr_ticket_receipts == gr_attempts"))
    state("returned_to_exploration", "exit", [{"stop": {"reason": "御灵流程已返回探索地图", "result": "unknown",
          "verified": False, "oas_schedule": "GoryouRealm", "evidence": {"scope": "native_task_path"}}}],
          exploration)
    state("back_to_exploration", "exit",
          [{"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}],
          fire, {"not": exploration}, back)
    obligations = [*navigation["source_obligations"], *battle["source_obligations"],
                   {"id": "goryou_switch_soul_receipt", "requirement": "verify numbered preset and effective costume on real frames"},
                   {"id": "goryou_owner", "requirement": "verify constructor/MRO and final costume asset bindings"}]
    raw["oas_goryou_contract"] = {"source": ENTRY, "source_pins": {
                                       **PINS, **SCHEDULE_PINS, **(SKIN_PINS if costumes else {})},
                                   "incidental_battle_config": "Config.__getattr__ returns None; use fresh defaults",
                                   "task_battle_config": "use goryou_realm.general_battle_config",
                                   "switch_soul_config": "switch_group_team pair exposed as integer goryou_soul_group and goryou_soul_team",
                                   "switch_soul_scope": "only advance on a numbered group match and ordinary preset confirmation",
                                   "shikigami_costume": shikigami_costume,
                                   "screen_boss_selection": screen_boss_selection,
                                   "shikigami_asset_bindings": {"::".join(key): "::".join(value)
                                                                for key, value in costumes.items()},
                                   "original_task_complete": False,
                                   "source_obligations": obligations}
    load_workflow(raw, [resource_dir.parent.parent])
    return {"workflow": raw, "complete": False, "original_task_complete": False, "source_obligations": obligations}
