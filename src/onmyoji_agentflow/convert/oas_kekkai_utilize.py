"""Pinned OAS KekkaiUtilize entry and existing foster check (GPL-3.0)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_kekkai_growth import CLASSES, bind_growth
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


ENTRY = "tasks/KekkaiUtilize/script_task.py"
GROWTH_ASSETS = "Component_ReplaceShikigami"
REWARD_SOURCE = "tasks/base_task.py"
PINS = {
    ENTRY: "6cce0ca52f95b46442e4a93ef8729ff1bfce4ed3c2d8d4ee9aea385ccdc71358",
    "tasks/KekkaiUtilize/config.py": "691ecd07fafaf3614bc9fd411102a27a974c5d410597d821311e86cef9f15a5e",
    "tasks/KekkaiUtilize/assets.py": "5535d95b6dcf206fb3ad62991e92d54024273a96140b263c9d948c2fc5dba2bd",
    "tasks/Component/ReplaceShikigami/replace_shikigami.py":
        "4e3e418a934ad62ba70d3e019eb629ef3c32d0319b11e0f40665f16c29c08740",
    "tasks/Component/ReplaceShikigami/assets.py":
        "da9963214b83100d2ed789edf5c39ff524968a86a777fa5606c953c2a1ea0f2b",
    "tasks/Utils/config_enum.py": "448f57caa1a19aa70ec61ae72f7f6a4754df9d17881ef05cc7e838db63f8d71e",
    "module/ocr/sub_ocr.py": "33344898ce3e638bc2d8c3a90bc85cd0586458871c352631416dca02361d994d",
}


def _verify_sources(source, pins):
    for path, expected in pins.items():
        data = (source / path).read_text(encoding="utf-8-sig").encode()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"KekkaiUtilize source fingerprint mismatch: {path}")


def compile_kekkai_foster_check(source_root, resource_dir, *, calibrations=None):
    """Extract the foster branch up to the selection or scheduling boundary."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_sources(source, PINS)

    packet = compile_navigation_family(source, resources, prefix="ku_nav", destination="page_guild",
                                        battle_config="default", android_login=True, calibrations=calibrations)
    raw = packet["workflow"]
    raw.update(name="oas_kekkai_foster_check_staged", title="结界寄养检查", loop_delay_ms=250)
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/KekkaiUtilize.yaml", f"upstream/oas/{GROWTH_ASSETS}.yaml",
    ]))
    raw["vars"].update(ku_phase="navigate", ku_seconds=-1, ku_next_delay_seconds=-1, ku_checked_at_ms=-1)
    raw["params"].update(ku_utilize_enable={"default": True}, ku_min_interval_seconds={"default": 0, "min": 0})
    assets = load_yaml(resources / "KekkaiUtilize.yaml")["resources"]

    def marker(name, **options):
        return {"res": "KekkaiUtilize::" + name, **options}

    def expr(value):
        return {"expr": value}

    def phase(value):
        return expr(f"ku_phase == {value!r}")

    def state(name, current, predicates, *actions):
        raw["states"].append({"id": "ku_" + name, "when": {"all": [phase(current), *predicates]}, "do": list(actions)})

    def advance(value, **values):
        return {"set": {"ku_phase": repr(value), **values}}

    def click(name, delay=1000):
        x, y, w, h = assets[name]["front"]
        return {"click": [x, y, x + w, y + h], "delay": delay, "recheck": True}

    guild = raw["navigation"]["pages"]["page_guild"]["when"]
    arrived = next(step for step in raw["states"] if step["id"] == "ku_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("realm")]
    next(step for step in raw["states"] if step["id"] == "ku_nav_drive")["when"] = phase("navigate")

    realm = {"any": [marker("I_REALM_SHIN"), marker("I_SHI_DEFENSE", scale_range=[0.8, 1.2])]}
    growth = {"res": f"{GROWTH_ASSETS}::I_RS_RECORDS_SHIKI"}
    add = marker("I_UTILIZE_ADD")
    state("realm_ready", "realm", [realm], advance("growth"))
    state("tree_close", "realm", [guild, marker("I_PLANT_TREE_CLOSE")], click("I_PLANT_TREE_CLOSE"))
    state("guild_realm", "realm", [guild, marker("I_GUILD_REALM")], click("I_GUILD_REALM"))
    state("growth_ready", "growth", [growth], advance("foster"))
    state("enter_growth", "growth", [realm, marker("I_SHI_GROWN", scale_range=[0.8, 1.2])], click("I_SHI_GROWN"))
    state("foster_disabled", "foster", [growth, expr("not ku_utilize_enable")], {"stop": {
        "reason": "寄养检查已按配置跳过", "result": "unknown", "verified": False,
        "evidence": {"scope": "foster_check_fragment"}}})
    state("foster_available", "foster", [growth, add], advance("friends"))
    read_timer = {"ocr": "KekkaiUtilize::O_UTILIZE_RES_TIME", "mode": "duration_seconds", "var": "ku_seconds"}
    state("active_timer", "foster", [growth, {"not": add}, read_timer, expr("ku_seconds >= ku_min_interval_seconds")],
          advance("timed", ku_next_delay_seconds="ku_seconds", ku_checked_at_ms="elapsed_ms"))
    state("active_timer_min", "foster", [growth, {"not": add}, read_timer],
          advance("timed", ku_next_delay_seconds="ku_min_interval_seconds", ku_checked_at_ms="elapsed_ms"))
    state("active_timer_unknown", "foster", [growth, {"not": add}], {"fail": "寄养剩余时间缺少有效读数"})
    state("active_timer_return", "timed", [], {"stop": {
        "reason": "寄养剩余时间已读取", "result": "unknown", "verified": False,
        "evidence": {"scope": "foster_check_fragment"}}})
    state("friend_list_ready", "friends", [marker("I_U_ENTER_REALM")], {"stop": {
        "reason": "已打开寄养好友选择，待核对同区和跨区列表", "result": "unknown", "verified": False,
        "evidence": {"scope": "foster_check_fragment"}}})
    state("friend_list_open", "friends", [growth, add], click("I_UTILIZE_ADD", 2000))

    obligations = [*packet["source_obligations"], {
        "id": "ku_friend_scan", "requirement": "Bind both friend lists, card ranking and unit selection", "blocking": True,
    }, {
        "id": "ku_followups", "requirement": "Bind growth replacement, harvest, guild receipt and computed scheduling",
        "blocking": True,
    }]
    raw["oas_kekkai_foster_contract"] = {"source": ENTRY, "source_pins": PINS,
        "outputs": {"seconds": "ku_seconds", "schedule_delay": "ku_next_delay_seconds",
                    "observed_elapsed_ms": "ku_checked_at_ms"},
        "original_task_complete": False, "source_obligations": obligations}
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_kekkai_realm_harvest(source_root, resource_dir):
    """Compile the realm portion between growth replacement and guild collection."""
    source, resources = Path(source_root), Path(resource_dir)
    pins = {**PINS, REWARD_SOURCE: "6d8849bcfdb368a012b9e19e37d446ed3022dad39974ab6eb237c959c43b4c20"}
    _verify_sources(source, pins)
    documents = {name: load_yaml(resources / f"{name}.yaml")["resources"] for name in ("KekkaiUtilize", "GlobalGame")}
    raw = {
        "format": 1, "name": "oas_kekkai_realm_harvest_staged", "title": "结界收取",
        "resource_namespaces": True, "resources": [f"upstream/oas/{name}.yaml" for name in documents],
        "default_result": "unknown", "loop_delay_ms": 250,
        "limits": {"timeout_s": 65, "unknown_timeout_s": 25, "stuck_timeout_s": 40, "no_progress_timeout_s": 40},
        "vars": {"ku_phase": "harvest_probe", "ku_timer": -1, "ku_foster_receipt": False, "ku_ap_receipt": False,
                 "ku_exp_remaining": -1, "ku_exp_attempted": False, "ku_exp_choice": "", "ku_exp_outcome": "",
                 "ku_foster_timeout": False, "ku_ap_timeout": False, "ku_foster_attempted": False,
                 "ku_ap_opened": False, "ku_ap_attempted": False, "ku_exp_opened": False},
        "params": {name: {"default": True} for name in ("ku_box_ap_enable", "ku_box_exp_enable", "ku_box_exp_waste")},
        "states": [],
    }

    def marker(name, namespace="KekkaiUtilize", **options):
        return {"res": f"{namespace}::{name}", **options}

    def click(name, delay=1000, namespace="KekkaiUtilize"):
        asset = documents[namespace][name]
        if "rect" in asset:
            rect = asset["rect"]
        else:
            x, y, w, h = asset["front"]
            rect = [x, y, x + w, y + h]
        return {"click": rect, "delay": delay, "recheck": True}

    def expr(value):
        return {"expr": value}

    def advance(value, **vars_):
        return {"set": {"ku_phase": repr(value), **vars_}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": "ku_" + name, "when": {"all": [expr(f"ku_phase == {where!r}"), *guards]},
                              "do": list(actions)})

    realm = marker("I_REALM_SHIN")
    reward = marker("I_UI_REWARD", "GlobalGame", threshold=0.6)
    dismiss = click("C_UI_REWARD", 400, "GlobalGame")
    red_back = marker("I_UI_BACK_RED", "GlobalGame")
    close = {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}
    foster = marker("I_UTILIZE_EXP")
    ap_box, ap_extract = marker("I_BOX_AP"), marker("I_AP_EXTRACT")
    exp_box = marker("I_BOX_EXP", threshold=0.6)
    exp_box_full = marker("I_BOX_EXP_MAX", threshold=0.6)
    exp_available = {"any": [exp_box, exp_box_full]}
    exp_extract = marker("I_EXP_EXTRACT")
    confirm = marker("I_UI_CONFIRM", "GlobalGame")
    cancel = marker("I_UI_CANCEL", "GlobalGame")
    exp_prompt = {"all": [confirm, cancel]}
    exp_ocr = {"ocr": "KekkaiUtilize::O_BOX_EXP", "mode": "counter_remaining", "var": "ku_exp_remaining"}

    state("foster_present", "harvest_probe", [realm, foster], advance("harvest_claim", ku_timer="elapsed_ms"))
    state("foster_absent", "harvest_probe", [realm, {"not": foster}], advance("ap_probe"))
    state("foster_reward", "harvest_claim", [reward, expr("ku_foster_attempted")],
          dismiss, {"wait": 500}, advance("harvest_receipt", ku_foster_receipt=True))
    state("foster_timeout", "harvest_claim", [expr("elapsed_ms - ku_timer >= 10000")],
          advance("ap_probe", ku_foster_timeout=True))
    state("foster_claim", "harvest_claim", [realm, foster, {"not": reward}],
          click("I_UTILIZE_EXP"), {"set": {"ku_foster_attempted": True}})
    state("foster_reward_again", "harvest_receipt", [reward], dismiss)
    state("foster_reward_closed", "harvest_receipt", [realm, {"not": reward}], advance("ap_probe"))

    state("ap_prepared", "ap_probe", [realm, ap_box, expr("ku_box_ap_enable")], advance("ap_claim", ku_timer="elapsed_ms"))
    state("ap_skipped", "ap_probe", [realm], advance("exp_probe"))
    state("ap_reward", "ap_claim", [reward, expr("ku_ap_attempted")], dismiss, advance("ap_close", ku_ap_receipt=True))
    state("ap_timeout", "ap_claim", [expr("elapsed_ms - ku_timer >= 6000")], advance("ap_close", ku_ap_timeout=True))
    state("ap_extract", "ap_claim", [ap_extract, {"not": reward}], click("I_AP_EXTRACT", 2000),
          {"set": {"ku_ap_attempted": True}})
    state("ap_open", "ap_claim", [realm, ap_box, {"not": reward}], click("I_BOX_AP"),
          {"set": {"ku_ap_opened": True}})
    state("ap_reward_again", "ap_close", [reward, expr("ku_ap_receipt")], dismiss)
    state("ap_back", "ap_close", [{"not": reward}, expr("ku_ap_opened or ku_ap_attempted"), red_back], close)
    state("ap_closed", "ap_close", [realm, {"not": exp_prompt}, {"not": reward}], advance("exp_probe"))

    state("exp_prepared", "exp_probe", [realm, expr("ku_box_exp_enable"), exp_available],
          advance("exp_claim", ku_timer="elapsed_ms"))
    state("exp_skipped", "exp_probe", [realm], advance("finished", ku_exp_outcome=repr("skip")))
    state("exp_done", "exp_claim", [realm, {"not": exp_available}, {"not": exp_extract}, {"not": confirm}, expr("ku_exp_attempted")],
          advance("finished", ku_exp_outcome=repr("extracted")))
    for choice, enabled, button in (("confirm", "ku_box_exp_waste", "I_UI_CONFIRM"),
                                   ("cancel", "not ku_box_exp_waste", "I_UI_CANCEL")):
        state("exp_overflow_" + choice, "exp_claim", [exp_prompt, expr("ku_exp_attempted"), expr(enabled)],
              click(button, namespace="GlobalGame"), advance("exp_prompt_close", ku_exp_choice=repr(choice)))
        state("exp_overflow_repeat_" + choice, "exp_prompt_close", [exp_prompt, expr(f"ku_exp_choice == {choice!r}")],
              click(button, namespace="GlobalGame"))
    state("exp_overflow_closed", "exp_prompt_close", [{"not": confirm}, {"any": [realm, exp_extract]}],
          advance("exp_close", ku_exp_outcome="ku_exp_choice"))
    state("exp_timeout", "exp_claim", [expr("elapsed_ms - ku_timer >= 12000")],
          advance("exp_close", ku_exp_outcome=repr("timeout")))
    state("exp_cap", "exp_claim", [exp_extract, exp_ocr, expr("ku_exp_remaining == 0")],
          advance("exp_close", ku_exp_outcome=repr("daily_cap")))
    state("exp_extract", "exp_claim", [exp_extract, exp_ocr, expr("ku_exp_remaining > 0"), {"not": confirm}],
          click("I_EXP_EXTRACT"), {"set": {"ku_exp_attempted": True}})
    state("exp_open", "exp_claim", [realm, {"not": exp_extract}, {"not": confirm}, exp_available], close,
          {"set": {"ku_exp_opened": True}})
    state("exp_back", "exp_close", [{"not": confirm}, expr("ku_exp_opened or ku_exp_attempted"), red_back], close)
    state("exp_closed", "exp_close", [realm, {"not": confirm}], advance("finished"))
    state("harvest_complete", "finished", [realm], {"stop": {
        "reason": "已返回寮结界，收取阶段已结束", "result": "unknown", "verified": False,
        "evidence": {"scope": "kekkai_realm_harvest_fragment"}}})

    raw["oas_kekkai_harvest_contract"] = {
        "source": ENTRY, "source_pins": pins, "original_task_complete": False,
        "functions": ["check_utilize_harvest", "check_box_ap_or_exp"],
        "source_obligations": [{"id": "ku_followup_composition", "blocking": True,
            "requirement": "Compose with foster selection, growth replacement, guild receipts and durable scheduling"}],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_kekkai_guild_harvest(source_root, resource_dir, *, calibrations=None):
    """Bind each guild collection attempt and its return to the courtyard."""
    source, resources = Path(source_root), Path(resource_dir)
    pins = {**PINS, REWARD_SOURCE: "6d8849bcfdb368a012b9e19e37d446ed3022dad39974ab6eb237c959c43b4c20"}
    _verify_sources(source, pins)
    packet = compile_navigation_family(source, resources, prefix="kg_nav", destination="page_guild",
                                        battle_config="default", android_login=True, calibrations=calibrations)
    raw = packet["workflow"]
    raw.update(name="oas_kekkai_guild_harvest_staged", title="寮资金与体力收取", loop_delay_ms=250)
    raw["states"] = [state for state in raw["states"] if state["id"] not in {"kg_nav_returned", "kg_nav_drive"}]
    raw["resources"] = sorted(set(raw["resources"] + ["upstream/oas/KekkaiUtilize.yaml", "upstream/oas/GlobalGame.yaml"]))
    raw["vars"].update(kg_phase="route_guild", kg_attempts=0, kg_timer=-1, kg_ap_pending=False,
                       kg_ap_receipt=False, kg_assets_pending=False, kg_assets_receipts=0, kg_court_arrived=0)
    raw["params"]["kg_max_tries"] = {"default": 3, "min": 0}
    documents = {name: load_yaml(resources / f"{name}.yaml")["resources"] for name in ("KekkaiUtilize", "GlobalGame")}

    def marker(name, namespace="KekkaiUtilize", **options):
        return {"res": f"{namespace}::{name}", **options}

    def click(name, delay=1000, namespace="KekkaiUtilize"):
        asset = documents[namespace][name]
        if "rect" in asset:
            rect = asset["rect"]
        else:
            x, y, w, h = asset["front"]
            rect = [x, y, x + w, y + h]
        return {"click": rect, "delay": delay, "recheck": True}

    def expr(value):
        return {"expr": value}

    def advance(value, **vars_):
        return {"set": {"kg_phase": repr(value), **vars_}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": "kg_" + name, "when": {"all": [expr(f"kg_phase == {where!r}"), *guards]},
                              "do": list(actions)})

    def stop(reason):
        return {"stop": {"reason": reason, "result": "unknown", "verified": False,
                         "evidence": {"scope": "kekkai_guild_harvest_fragment"}}}

    guild = raw["navigation"]["pages"]["page_guild"]["when"]
    courtyard = raw["navigation"]["pages"]["page_main"]["when"]
    realm = {"any": [marker("I_REALM_SHIN"), marker("I_SHI_DEFENSE", scale_range=[0.8, 1.2])]}
    reward = marker("I_UI_REWARD", "GlobalGame", threshold=0.6)
    dismiss = click("C_UI_REWARD", 400, "GlobalGame")
    tap = {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}
    ap = marker("I_GUILD_AP")
    assets = marker("I_GUILD_ASSETS", threshold=0.6)
    receive = marker("I_GUILD_ASSETS_RECEIVE")
    tree = marker("I_PLANT_TREE_CLOSE")
    expired = expr("elapsed_ms - kg_timer >= 2000")
    reset = {"set": {"kg_timer": "elapsed_ms"}}
    leave = advance("route_courtyard", kg_court_arrived=0)

    state("no_attempts", "route_guild", [expr("kg_max_tries == 0")], stop("配置的寮收取尝试次数为零"))
    state("guild_ready", "route_guild", [guild, expr("kg_nav_arrived == 1")],
          advance("collect", kg_attempts="kg_attempts + 1", kg_timer="elapsed_ms", kg_ap_pending=False,
                  kg_assets_pending=False))
    for color in ("RED", "BLUE", "YELLOW"):
        asset = f"I_UI_BACK_{color}"
        state("leave_realm_" + color.lower(), "route_guild", [realm, marker(asset, "GlobalGame")],
              tap)
    state("guild_drive", "route_guild", [], {"navigate": {"destination": "page_guild", "done_var": "kg_nav_arrived"}})

    state("reward", "collect", [reward], dismiss, {"set": {
        "kg_ap_receipt": "kg_ap_receipt or kg_ap_pending",
        "kg_assets_receipts": "kg_assets_receipts + kg_assets_pending",
        "kg_ap_pending": False, "kg_assets_pending": False, "kg_timer": "elapsed_ms",
    }})
    state("ap_received", "collect", [guild, expr("kg_ap_receipt"), {"not": ap}], leave)
    state("check_expired", "collect", [expired], leave)
    state("tree_close", "collect", [guild, tree], tap, reset)
    state("banner", "collect", [guild, marker("I_GUILD_EXPAND")], tap, reset)
    state("assets_receive", "collect", [expr("kg_assets_pending and not kg_ap_pending"), receive], tap, reset)
    state("assets_open", "collect", [guild, {"not": receive}, expr("not kg_ap_pending"), assets],
          {**tap, "delay": 1500}, {"set": {"kg_assets_pending": True, "kg_timer": "elapsed_ms"}})
    state("ap_collect", "collect", [guild, {"not": receive}, expr("not kg_assets_pending"), ap], tap,
          {"set": {"kg_ap_pending": True, "kg_timer": "elapsed_ms"}})

    state("return_retry", "route_courtyard", [courtyard, expr("kg_court_arrived == 1"),
          expr("not kg_ap_receipt and kg_attempts < kg_max_tries")], advance("route_guild", kg_nav_arrived=0))
    state("return_done", "route_courtyard", [courtyard, expr("kg_court_arrived == 1")], stop("已返回庭院，寮收取检查结束"))
    state("courtyard_drive", "route_courtyard", [], {"navigate": {"destination": "page_main", "done_var": "kg_court_arrived"}})

    raw["oas_kekkai_guild_contract"] = {
        "source": ENTRY, "source_pins": pins, "original_task_complete": False,
        "functions": ["recive_guild_ap_or_assets", "check_guild_ap_or_assets"],
        "source_obligations": packet["source_obligations"], "source_notes": [
            "Both guild claim switches are unused in the pinned caller and method.",
            "Guild asset claims are tracked separately because the original retry loop stops only on an AP receipt.",
        ],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_kekkai_occupied_candidate(source_root, resource_dir, *, calibrations=None,
                                     scan_friends=False, retry_empty_friends=False, inspect_friend_realm=False,
                                     place_friend_unit=False):
    """Compose the occupied or disabled foster path through the scheduled exit."""
    source, resources = Path(source_root), Path(resource_dir)
    raw = compile_kekkai_foster_check(source, resources, calibrations=calibrations)
    realm_harvest = compile_kekkai_realm_harvest(source, resources)
    guild_harvest = compile_kekkai_guild_harvest(source, resources, calibrations=calibrations)
    raw.update(name="oas_kekkai_utilize_occupied_staged", title="结界寄养与收取")
    raw["resources"] = sorted(set(raw["resources"] + realm_harvest["resources"] + guild_harvest["resources"]))
    guild_callbacks = guild_harvest["navigation"]["calls"].values()
    callback_states = {name for call in guild_callbacks for name in call["states"]}
    callback_vars = {name for call in guild_callbacks for name in call["initial_vars"]}
    raw["vars"].update({key: value for key, value in realm_harvest["vars"].items() if key != "ku_phase"})
    raw["vars"].update({key: value for key, value in guild_harvest["vars"].items() if key not in callback_vars})
    raw["vars"]["kg_phase"] = "idle"
    raw["params"].update(realm_harvest["params"], kg_max_tries=guild_harvest["params"]["kg_max_tries"])
    bind_schedule(source, raw)
    raw["params"]["oas_success_seconds"]["default"] = 21600
    if (retry_empty_friends or inspect_friend_realm) and not scan_friends:
        raise ValueError("foster retries and realm inspection require the ranked dual-tab scan")
    if place_friend_unit and not inspect_friend_realm:
        raise ValueError("foster placement requires ranked friend realm inspection")

    bind_growth(raw, resources)
    for state in raw["states"]:
        if state["id"] in ("ku_foster_disabled", "ku_active_timer_return"):
            state["do"] = [{"set": {"ku_phase": "'growth_verify'"}}]
        if scan_friends and state["id"] == "ku_friend_list_ready":
            state["do"] = [{"select_foster": {"max_pages": 30, "selected_tabs": [
                "KekkaiUtilize::I_UTILIZE_FRIEND_GROUP", "KekkaiUtilize::I_UTILIZE_ZONES_GROUP"]}}]
            if retry_empty_friends:
                state["when"]["all"].append({"expr": "not ku_foster_exhausted"})
                state["do"][0]["select_foster"]["exhausted_var"] = "ku_foster_exhausted"

    target = {"task": "KekkaiUtilize", "delay_seconds_var": "ku_next_delay_seconds", "observed_ms_var": "ku_checked_at_ms"}
    for state in realm_harvest["states"]:
        if state["id"] == "ku_harvest_complete":
            state["do"] = [{"set": {"ku_phase": "'guild'", "kg_phase": "'route_guild'"}}]
        raw["states"].append(state)
    for state in guild_harvest["states"]:
        if state["id"] in callback_states:
            continue
        if state["id"] in ("kg_no_attempts", "kg_return_done"):
            disabled = {**state, "id": state["id"] + "_disabled",
                        "when": {"all": [state["when"], {"expr": "not ku_utilize_enable"}]}}
            terminal = state["do"][0]["stop"]
            disabled["do"] = [{"stop": {**terminal, "oas_schedule": "KekkaiUtilize"}}]
            state["do"] = [{"stop": {**terminal, "oas_schedule": target}}]
            raw["states"].append(disabled)
        raw["states"].append(state)

    raw["oas_kekkai_candidate_contract"] = {
        "source": ENTRY, "source_pins": {**guild_harvest["oas_kekkai_guild_contract"]["source_pins"], **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*raw["oas_kekkai_foster_contract"]["source_obligations"][:-1], {
            "id": "ku_growth_replacement_live", "blocking": True,
            "requirement": "Verify class tabs, max-level removal and normal, alternate and fallback filling on retained frames",
        }, {
            "id": "ku_live_schedule", "blocking": True,
            "requirement": "Verify real receipts and explicit scheduling after placement or while already occupied",
        }],
        "native_adaptations": [
            "Persist the timer due at successful completion using the earlier observation time.",
            "Try slot seven first and then alternate with slot six if the same vacancy remains.",
        ],
    }
    if scan_friends:
        raw["name"] = "oas_kekkai_utilize_ranked_preview_staged"
        raw["oas_kekkai_candidate_contract"]["native_adaptations"].append(
            "Compare both friend tabs using the user's star-first ordering and verify the highlighted nickname.")
    if retry_empty_friends:
        _bind_empty_foster_retry(raw)
    if inspect_friend_realm:
        _bind_friend_realm_inspection(raw)
    if place_friend_unit:
        _bind_friend_placement(raw, resources)
    load_workflow(raw, [resources.parent.parent])
    return raw


def _bind_friend_realm_inspection(raw):
    """Inspect the selected friend's vacancies before permitting any placement."""
    raw["name"] = "oas_kekkai_utilize_friend_realm_staged"
    raw["vars"].update(ku_foster_entered=False, ku_friend_entered_ms=-1)
    entry = next(state for state in raw["states"] if state["id"] == "ku_friend_list_ready")
    entry["do"][0]["select_foster"]["enter_realm"] = {
        "button": "KekkaiUtilize::I_U_ENTER_REALM", "entered_var": "ku_foster_entered",
    }
    raw["states"].insert(raw["states"].index(entry), {"id": "ku_foster_entered_realm",
        "when": {"expr": "ku_phase == 'friends' and ku_foster_entered"},
        "do": [{"set": {"ku_phase": "'foster_inspect_realm'", "ku_friend_entered_ms": "elapsed_ms"}}]})
    phase = {"expr": "ku_phase == 'foster_inspect_realm'"}
    realm = {"all": [
        {"not": {"res": "KekkaiUtilize::I_U_ENTER_REALM"}},
        {"any": [{"res": f"KekkaiUtilize::I_CHECK_FRIEND_REALM_{i}"} for i in (1, 3)]},
    ]}
    primary, secondary = ({"res": f"KekkaiUtilize::I_U_ADD_{i}"} for i in (1, 2))
    for slot, guards in ((1, [primary]), (2, [{"not": primary}, secondary])):
        raw["states"].append({"id": f"ku_foster_inspected_slot_{slot}", "when": {"all": [phase, realm, *guards]},
            "do": [{"stop": {"result": "blocked", "verified": False, "reason": "已识别好友结界和空位，待核对式神放置",
                             "evidence": {"scope": "friend_realm_inspection", "vacant_slot": slot}}}]})
    raw["states"].append({"id": "ku_foster_realm_inspection_timeout", "when": {"all": [
        phase, {"expr": "elapsed_ms - ku_friend_entered_ms >= 20000"},
    ]}, "do": [{"stop": {"result": "blocked", "verified": False, "reason": "进入后未能核对好友结界与空位"}}]})
    for goal in raw["oas_kekkai_candidate_contract"]["source_obligations"]:
        if goal.get("id") == "ku_friend_scan":
            goal["requirement"] = "Verify friend realm and vacancy on live frames and bind unit selection and placement"


def _bind_friend_placement(raw, resources):
    """Stage unit placement and require a timer readback before resuming harvest."""
    friend = "KekkaiUtilize"
    growth = GROWTH_ASSETS
    unit_resources = load_yaml(resources / f"{growth}.yaml")["resources"]
    raw["name"] = "oas_kekkai_utilize_friend_placement_staged"
    raw["params"]["ku_shikigami_order"] = {"default": 7, "min": 1, "max": 7, "choices": list(range(1, 8))}
    raw["vars"].update(ku_foster_slot=0, ku_place_started_ms=-1, ku_place_pick_count=0,
                       ku_place_return_ms=-1, ku_place_class_since=-1)
    position = ["ku_place_x", "ku_place_y", "ku_place_w", "ku_place_h"]
    raw["vars"].update(dict.fromkeys(position, 0))
    tap = {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1100}

    def asset(name, namespace=friend, **kwargs):
        return {"res": f"{namespace}::{name}", **kwargs}

    def expr(value):
        return {"expr": value}

    def step(name, phase, predicates, *actions):
        raw["states"].append({"id": "ku_place_" + name,
            "when": {"all": [expr(f"ku_phase == {phase!r}"), *predicates]}, "do": list(actions)})

    def advance(phase, **extra):
        return {"set": {"ku_phase": repr(phase), **extra}}

    scout = {state["id"]: state for state in raw["states"]}
    realm = scout["ku_foster_inspected_slot_1"]["when"]["all"][1]
    slots = [asset(f"I_U_ADD_{slot}") for slot in (1, 2)]
    vacancy = {"any": [{"all": [expr(f"ku_foster_slot == {i}"), slot]}
                       for i, slot in enumerate(slots, 1)]}
    for i in (1, 2):
        scout[f"ku_foster_inspected_slot_{i}"]["do"] = [advance(
            "foster_class", ku_foster_slot=i, ku_place_started_ms="elapsed_ms")]

    available = [realm, vacancy]
    before_selection_timeout = expr("elapsed_ms - ku_place_started_ms < 25000")
    row_capture = {"capture_region": {"rect": ["match_x", "match_y", "match_w", "match_h"], "vars": position}}
    no_target, selected_class = [], []
    for rank in CLASSES:
        requested = expr(f"ku_shikigami_class == {rank!r}")
        chosen = asset(f"I_RS_{rank}_SELECTED", growth)
        row = asset("I_RS_" + rank, growth)
        saved_row = asset("I_RS_" + rank, growth, region_vars=position)
        no_target.append({"all": [requested, {"not": row}, {"not": chosen}]})
        selected_class.append({"all": [requested, chosen]})
        for phase in ("foster_class", "foster_class_stable"):
            step(f"class_chosen_{rank.lower()}_{phase}", phase,
                 [*available, before_selection_timeout, requested, chosen],
                 advance("foster_place", ku_place_started_ms="elapsed_ms"))
        step(f"class_probe_{rank.lower()}", "foster_class",
             [*available, before_selection_timeout, requested, row],
             row_capture, advance("foster_class_stable", ku_place_class_since="elapsed_ms"))
        step(f"class_moved_{rank.lower()}", "foster_class_stable",
             [*available, before_selection_timeout, requested, {"not": saved_row}], advance("foster_class"))
        step(f"class_choose_{rank.lower()}", "foster_class_stable",
             [*available, before_selection_timeout, requested, expr("elapsed_ms - ku_place_class_since >= 1500"), saved_row],
             {**tap, "delay": 2000}, advance("foster_class"))

    step("class_open", "foster_class", [*available, before_selection_timeout, {"any": no_target}],
         {"click": unit_resources["C_SHIKIGAMI_SWITCH_1"]["rect"], "delay": 3500, "recheck": True})
    for phase in ("foster_class", "foster_class_stable"):
        step("class_timeout_" + phase, phase,
             [{"not": before_selection_timeout}], {"fail": "好友结界的寄养空位或式神分类未核对成功"})

    before_timeout = expr("elapsed_ms - ku_place_started_ms <= 120000")
    pending = expr("ku_place_pick_count > 0")
    confirm = asset("I_U_CONFIRM_SMALL", growth)
    alternate = asset("I_U_CIRCLE_ALTERNATE", growth)
    alternate_confirm = asset("I_U_CONFIRM_ALTERNATE", growth)
    general = {"any": [asset(name, "GlobalGame") for name in ("I_UI_CONFIRM", "I_UI_CONFIRM_SAMLL")]}
    overlays = {"any": [confirm, alternate, alternate_confirm, general]}
    step("confirm", "foster_place", [*available, pending, before_timeout, confirm], {**tap, "delay": 500})
    step("alternate", "foster_place", [*available, pending, before_timeout, alternate],
         {**tap, "delay": 2500}, advance("foster_alternate"))
    step("alternate_confirm", "foster_alternate", [*available, pending, before_timeout, alternate_confirm],
         {**tap, "delay": 1500}, advance("foster_place"))
    step("unverified_confirmation", "foster_place", [pending, before_timeout, {"not": confirm}, general],
         {"fail": "寄养后出现通用确认框，待核对其来源和内容"})

    for i in range(1, 8):
        preferred_pick = f"ku_shikigami_order == {i} and ku_place_pick_count % 2 == 0"
        pick = expr(f"({preferred_pick}) or ku_place_pick_count % 2 == 1") if i == 6 else expr(preferred_pick)
        action = {"click": unit_resources[f"C_SHIKIGAMI_LEFT_{i}"]["rect"],
                  "delay": 4500 if i == 6 else 1500, "recheck": True}
        step(f"pick_{i}", "foster_place", [*available, before_timeout, {"not": overlays}, pick, {"any": selected_class}],
             action, {"inc": "ku_place_pick_count"})

    step("slot_filled", "foster_place", [realm, {"not": vacancy}, {"not": overlays}, pending, before_timeout],
         advance("foster_return", ku_place_return_ms="elapsed_ms"))
    for phase in ("foster_place", "foster_alternate"):
        step("timeout_" + phase, phase, [{"not": before_timeout}], {"fail": "好友结界寄养放置超时"})

    own_realm = {"any": [asset("I_REALM_SHIN"), asset("I_SHI_DEFENSE", scale_range=[.8, 1.2])]}
    guild = raw["navigation"]["pages"]["page_guild"]["when"]
    growth_panel = asset("I_RS_RECORDS_SHIKI", growth)
    enter_growth = asset("I_SHI_GROWN", scale_range=[.8, 1.2])
    panel = asset("I_U_ENTER_REALM")
    step("return_timeout", "foster_return", [expr("elapsed_ms - ku_place_return_ms >= 45000")],
         {"fail": "寄养放置后未核对到本方育成界面的有效倒计时"})
    for color in ("RED", "BLUE"):
        back = asset(f"I_UI_BACK_{color}", "GlobalGame")
        step("exit_friend_" + color.lower(), "foster_return", [{"not": overlays}, realm, back], tap)
        step("exit_list_" + color.lower(), "foster_return", [panel, back], tap)
    step("reenter_realm", "foster_return", [guild, asset("I_GUILD_REALM")], tap)
    step("reenter_growth", "foster_return", [own_realm, {"not": realm}, enter_growth], tap)
    read_timer = {"ocr": f"{friend}::O_UTILIZE_RES_TIME", "mode": "duration_seconds", "var": "ku_seconds"}
    timed_growth = [growth_panel, {"not": realm}, {"not": asset("I_UTILIZE_ADD")}, read_timer]
    for label, comparison, interval in (
        ("timer_verified", "ku_seconds >= ku_min_interval_seconds", "ku_seconds"),
        ("timer_minimum", "ku_seconds < ku_min_interval_seconds", "ku_min_interval_seconds"),
    ):
        step(label, "foster_return", [*timed_growth, expr(f"ku_seconds > 0 and {comparison}")],
             advance("timed", ku_next_delay_seconds=interval, ku_checked_at_ms="elapsed_ms"))

    for goal in raw["oas_kekkai_candidate_contract"]["source_obligations"]:
        if goal.get("id") == "ku_friend_scan":
            goal["requirement"] = (
                "Verify friend realm, vacancy, class and placement live, including a fresh positive timer. "
                "Identify the generic growth-candidate confirmation before binding it."
            )


def _bind_empty_foster_retry(raw):
    """Return to the realm after an empty scan and defer after four attempts."""
    raw["name"] = "oas_kekkai_utilize_ranked_retry_staged"
    raw["vars"].update(ku_foster_exhausted=False, ku_foster_search_attempts=0, ku_friend_list_opened_ms=-1)
    show_list = {"res": "KekkaiUtilize::I_U_ENTER_REALM"}
    growth = {"res": f"{GROWTH_ASSETS}::I_RS_RECORDS_SHIKI"}
    growth_entry = {"res": "KekkaiUtilize::I_SHI_GROWN", "scale_range": [.8, 1.2]}
    realm = {"any": [{"res": "KekkaiUtilize::I_REALM_SHIN"},
                     {"res": "KekkaiUtilize::I_SHI_DEFENSE", "scale_range": [.8, 1.2]}]}
    ready = {"expr": "ku_phase == 'foster_retry'"}
    found_back = {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1100}
    opening = next(state for state in raw["states"] if state["id"] == "ku_friend_list_open")
    opening["when"]["all"].append({"not": show_list})
    opening["do"].append({"set": {"ku_phase": "'foster_wait_for_friends'", "ku_friend_list_opened_ms": "elapsed_ms"}})
    raw["states"].extend([
        {"id": "ku_retry_friend_list_opened", "when": {"all": [
            {"expr": "ku_phase == 'foster_wait_for_friends'"}, show_list,
        ]}, "do": [{"set": {"ku_phase": "'friends'"}}]},
        {"id": "ku_retry_friend_list_timeout", "when": {
            "expr": "ku_phase == 'foster_wait_for_friends' and elapsed_ms - ku_friend_list_opened_ms >= 10000",
        }, "do": [{"fail": "空闲寄养槽点击后未识别到好友列表"}]},
        {"id": "ku_no_card_found", "when": {"all": [
            {"expr": "ku_phase == 'friends' and ku_foster_exhausted"}, show_list,
        ]}, "do": [
            {"inc": "ku_foster_search_attempts"},
            {"set": {"ku_phase": "'foster_retry'", "ku_foster_exhausted": False}},
        ]},
        {"id": "ku_retry_close_list", "when": {"all": [
            ready, show_list, {"res": "GlobalGame::I_UI_BACK_BLUE"},
        ]}, "do": [found_back]},
        {"id": "ku_retry_exit_growth", "when": {"all": [
            ready, growth, {"not": show_list}, {"res": "GlobalGame::I_UI_BACK_BLUE"},
        ]}, "do": [found_back]},
        {"id": "ku_retry_reenter_growth", "when": {"all": [
            ready, realm, {"not": show_list}, {"expr": "ku_foster_search_attempts < 4"},
        ]}, "do": [{"set": {"ku_phase": "'growth'"}}]},
        {"id": "ku_schedule_no_card_retry", "when": {"all": [
            ready, realm, {"not": show_list}, {"expr": "ku_foster_search_attempts >= 4"},
        ]}, "do": [
            {"log": "没有合适的寄养卡，安排五分钟后再试。"},
            {"set": {"ku_phase": "'retry_harvest_growth'", "ku_next_delay_seconds": 300,
                     "ku_checked_at_ms": "elapsed_ms"}},
        ]},
        {"id": "ku_retry_open_growth_for_harvest", "when": {"all": [
            {"expr": "ku_phase == 'retry_harvest_growth'"}, realm, growth_entry,
        ]}, "do": [found_back]},
        {"id": "ku_retry_continue_harvest", "when": {"all": [
            {"expr": "ku_phase == 'retry_harvest_growth'"}, growth, {"not": show_list},
        ]}, "do": [
            {"set": {"ku_phase": "'growth_verify'"}},
        ]},
    ])
    raw["oas_kekkai_candidate_contract"]["native_adaptations"].append(
        "Only a fully recognized and empty two-tab scan can advance the four-attempt retry counter.")
