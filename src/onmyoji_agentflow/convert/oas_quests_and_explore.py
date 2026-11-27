"""Pinned OAS WantedQuests, BondlingFairyland, Dokan, and Exploration workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
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
from ..workflow.oas_schedule import SERVER_TIMING
from ..workflow.schema import load_workflow
from ..workflow.wanted_quests import SECRET_LAYERS
from ..yamlio import load_yaml


WANTED_ENTRY = "tasks/WantedQuests/script_task.py"
WANTED_PINS = {
    WANTED_ENTRY: "24a30e7884c97e152f66dd8930156e9f15ad3d544af52f289980ebbe200777a5",
    "tasks/WantedQuests/config.py": "3234619485f6368bab84936a7c415534b2eda53eee10e90cf6d42346468fef24",
    "tasks/WantedQuests/assets.py": "e8542ef6f4aff34b48541b91781e8fdcafb986e8297d0bc7f3a33fe33834536b",
    "tasks/WantedQuests/explore.py": "c714e5ebd681871c649799460ba0f23079491d1191f646026c1f38a4853aa31f",
}

BONDLING_ENTRY = "tasks/BondlingFairyland/script_task.py"
BONDLING_PINS = {
    BONDLING_ENTRY: "cc96b1da6acb35d6acdefbb726bc2df7e1529a9a88f981cc59cb44e7e43c329c",
    "tasks/BondlingFairyland/config.py": "f6fbf644703e067bce356690364a0d9957a6f97e87f75d308856746dda0c62b3",
    "tasks/BondlingFairyland/assets.py": "4efec505eb72d0ac2930efed5584c83ec30842c2bd63e041c9c498e62f5daefa",
    "tasks/BondlingFairyland/battle.py": "8181a6fec0bffab9ccaf862fd00e43fddcb95af5a40b31876ef44b9437d4bd4b",
    "tasks/BondlingFairyland/config_battle.py": "6293427aa9c1a0fd844d8ab8ec10220b6aeae46656475ad9a9599cb785ad86e0",
    "tasks/BondlingFairyland/general_invite.py": "70fdcf495ae1599905fcae26d40f5bdbba113ce36293f9d4b3a13a2fa56f447e",
}

DOKAN_ENTRY = "tasks/Dokan/script_task.py"
DOKAN_PINS = {
    DOKAN_ENTRY: "21ea1be1851eefafb0d38c955546768c502a266225135dfab60b11877294dd5c",
    "tasks/Dokan/config.py": "f541b88cb5595f90279ffe5b053099d37b4c3ab7b5fd5464b4163b1198a03dcb",
    "tasks/Dokan/assets.py": "d8b27c5d88f6b04e938aea107969ad08560fea4ccc6050849ae787ef9e3420b0",
    "tasks/Dokan/dokan_scene.py": "afa3f72aec7d1948900522f6c7f88574fb8b8441c05e1dbb7c0d3f9f17114296",
    "tasks/Dokan/ex_green_mark.py": "e0f214e75d9ccd97f9ccacb04d3ce70987db29f9d4988aef148bd934ad1d7cf3",
    "tasks/Dokan/utils.py": "7d5e2e733e95c17a931b2472644e13a84efc3cad90bdc0f87a7055e2621e01a1",
}

EXPLORATION_ENTRY = "tasks/Exploration/script_task.py"
EXPLORATION_PINS = {
    EXPLORATION_ENTRY: "b3156088a655319977a8659626cef59202a0dca38ffb3354919460f3244759b8",
    "tasks/Exploration/solo.py": "72e35ec6079ce5907efb698c07d2881775e70125c101b9bb86b1fb03ea8437a5",
    "tasks/Exploration/base.py": "d9a15d0d164157676a44949efa26fd5dabcb168cb9d494f84ed11e871f7b10bb",
    "tasks/Exploration/config.py": "847d07a3ba7bac744fa07c80a6e934269fe45c218c49afac04c1b0396cf47d15",
    "tasks/Exploration/assets.py": "825ec347343c1fbabbfb2a04b079b7b5de14795c4b452c0ae069290a91f36518",
    "tasks/Exploration/page.py": "69042a1d52a40d2df78915e36d9f29ed91a5ca9a70710985b8d447ecf5afcc30",
    "tasks/Exploration/version.py": "c0e9e1836c96bc7c84af0cba812dcf28d66a5181d56cb7ed6e72115a32021673",
    "tasks/Component/ReplaceShikigami/replace_shikigami.py":
        "4e3e418a934ad62ba70d3e019eb629ef3c32d0319b11e0f40665f16c29c08740",
    "tasks/Component/ReplaceShikigami/assets.py":
        "da9963214b83100d2ed789edf5c39ff524968a86a777fa5606c953c2a1ea0f2b",
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


def compile_wanted_quests_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS WantedQuests (悬赏封印) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, WANTED_PINS, "WantedQuests")
    nav = compile_navigation_family(
        source, resources, prefix="wq_nav", destination="page_main",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="wq_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_wanted_quests_natively_staged", title="悬赏封印", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        wq_cooperation_only={"default": False},
        wq_confirm_invite={"default": False},
        wq_coop_max_invites={"default": 3, "min": 1, "max": 5},
        wq_coop_cross_server={"default": False},
        wq_run_pre_work={"default": False},
        wq_wake_secret={"default": False},
        wq_secret_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        wq_max_battles={"default": 15, "min": 1, "max": 30},
        wq_limit_seconds={"default": 0, "min": 0, "max": 7200},
        wq_next_delay_s={"default": 0, "min": 0, "max": 604800},
        wq_location_preview={"default": False},
        wq_follow_tracked={"default": False},
        wq_battle_priority={"default": "挑战 > 秘闻 > 探索"},
        wq_secret_cutoff={"default": "柒", "choices": [*SECRET_LAYERS, "无限制"]},
        wq_excluded_monsters={"default": "酒吞童子,阎魔"},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        wq_phase="entry", wq_battles=0, wq_wins=0, wq_rewards=0, wq_exit_reason="",
        wq_pre_traced=False, wq_exp_arrived=0, wq_list_swipes=0, wq_secret_woken=False,
        wq_coop_invites=0, wq_coop_friend_picked=False,
        wq_tickets=-1, wq_location_slot=0, wq_location_kind="", wq_location_destination="",
        wq_location_runs=0, wq_location_signature="", wq_chosen_signature="",
        wq_map_progress="", wq_location_progress="",
        wq_target_delay_s=0, wq_observed_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/WantedQuests.yaml",
        "upstream/oas/Exploration.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("WantedQuests", "Exploration", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"wq_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"wq_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"wq_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="WantedQuests"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="WantedQuests", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("coop_invite_gate", "entry", [expr("wq_cooperation_only and not wq_confirm_invite")],
          {"fail": "悬赏封印仅协作模式(邀请好友)需显式开启 wq_confirm_invite 与好友列表绑定"})
    _wire_nav(raw, "wq", phase, advance, "dispatch_pre")
    court = raw["navigation"]["pages"]["page_main"]["when"]
    tap_detected = {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1000}

    state("dispatch_coop_invite", "dispatch_pre", [expr("wq_cooperation_only and wq_confirm_invite")],
          advance("coop_invite"))
    state("dispatch_pre_work", "dispatch_pre", [expr("wq_run_pre_work or wq_follow_tracked")], advance("pre_work"))
    state("dispatch_board_direct", "dispatch_pre", [], advance("board"))

    # Guarded cooperation invite flow (requires wq_cooperation_only and wq_confirm_invite)
    state("coop_limit_reached", "coop_invite", [expr("wq_coop_invites >= wq_coop_max_invites")], advance("exit"))
    state("coop_open_seal", "coop_invite", [court, asset("I_WQ_SEAL")], tap_detected)
    state("coop_switch_diff_svr", "coop_invite", [
        expr("wq_coop_cross_server"),
        asset("I_WQ_INVITE_DIFF_SVR"),
        {"not": asset("I_WQ_INVITE_DIFF_SVR_HIGHLIGHT")},
    ], click("I_WQ_INVITE_DIFF_SVR", delay=800))
    state("coop_confirm_send", "coop_invite", [
        expr("wq_coop_friend_picked"),
        asset("I_WQ_INVITE_SELECTED"),
        asset("I_WQ_INVITE_ENSURE"),
    ], click("I_WQ_INVITE_ENSURE", delay=1000), {"inc": "wq_coop_invites"},
       {"set": {"wq_coop_friend_picked": False}})
    state("coop_pick_friend", "coop_invite", [
        expr("not wq_coop_friend_picked"),
        asset("I_WQ_INVITE_FRIEND_LIST_APPEAR"),
        asset("I_WQ_FRIEND_1"),
    ], click("I_WQ_FRIEND_1", delay=800), {"set": {"wq_coop_friend_picked": True}})
    for slot in (1, 2, 3):
        state(f"coop_tap_invite_{slot}", "coop_invite", [asset(f"I_WQ_INVITE_{slot}")],
              click(f"I_WQ_INVITE_{slot}", delay=1000), {"set": {"wq_coop_friend_picked": False}})
    state("coop_close_seal", "coop_invite", [asset("I_UI_BACK_RED", "GlobalGame")],
          click("I_UI_BACK_RED", "GlobalGame", 1000), advance("exit"))
    state("coop_done", "coop_invite", [asset("I_WQ_DONE")], advance("exit"))

    # Pre-work: open seal -> trace all quests -> close -> navigate to page_exploration
    state("pre_traced_close", "pre_work", [asset("I_TRACE_DISABLE"), asset("I_UI_BACK_RED", "GlobalGame")],
          tap_detected,
          advance("goto_exploration", wq_pre_traced=True, wq_exp_arrived=0))
    state("pre_traced_ready", "pre_work", [asset("I_TRACE_DISABLE")],
          advance("goto_exploration", wq_pre_traced=True, wq_exp_arrived=0))
    state("pre_tap_trace", "pre_work", [asset("I_TRACE_ENABLE")], tap_detected)
    state("pre_tap_seal", "pre_work", [court, asset("I_WQ_SEAL")], tap_detected)
    state("pre_tap_done", "pre_work", [court, asset("I_WQ_DONE")], tap_detected)

    exp_page = raw["navigation"]["pages"]["page_exploration"]["when"]
    state("exp_arrived", "goto_exploration", [exp_page, expr("wq_exp_arrived == 1")], advance("board"))
    state("exp_drive", "goto_exploration", [],
          {"navigate": {"destination": "page_exploration", "done_var": "wq_exp_arrived"}})

    # The two opt-ins preview one destination, either from the map or from an opened detail panel.
    detail = [asset("I_TRACE_TRUE"), asset("I_GOTO_1")]
    tickets = {"ocr": "WantedQuests::O_WQ_NUMBER", "mode": "exact_quantity", "var": "wq_tickets"}
    location = {"wanted_location": {
        "priority": "wq_battle_priority",
        "secret_cutoff": "wq_secret_cutoff",
        "excluded": "wq_excluded_monsters",
        "tickets": "wq_tickets",
        "output": {field: f"wq_location_{field}"
                   for field in ("slot", "kind", "destination", "runs", "signature", "progress")},
    }}
    state("location_read", "entry", [expr("wq_location_preview"), *detail, tickets, location],
          advance("location_choose", wq_chosen_signature="wq_location_signature"))
    state("location_unknown", "entry", [expr("wq_location_preview")],
          {"fail": "悬赏详情、未完成进度、挑战券或可用前往行无法核对"})
    state("location_read_tracked", "location_panel", [
        *detail, tickets, location, expr("wq_location_progress == wq_map_progress"),
    ], advance("location_choose", wq_chosen_signature="wq_location_signature"))
    state("location_tracked_unverified", "location_panel", [asset("I_TRACE_TRUE")],
          {"fail": "打开后的悬赏任务进度、挑战券或可用前往行无法核对"})
    for slot in range(1, 5):
        state(f"location_goto_{slot}", "location_choose", [
            *detail, tickets, location,
            expr(f"wq_location_slot == {slot} and wq_location_signature == wq_chosen_signature"),
            asset(f"I_GOTO_{slot}"),
        ], {**tap_detected, "recheck_retry": True}, advance("location_arrival"))
    state("location_changed", "location_choose", [],
          {"fail": "悬赏路线或票数变化，需要重新核对"})
    chapter_heading = {"ocr_full": {
        "region": [145, 6, 115, 47], "keyword_var": "wq_location_destination", "selection": "unique_equals",
    }}
    preview_end = {"stop": {"reason": "已核对悬赏前往页面", "result": "unknown", "verified": False,
                            "evidence": {"scope": "wanted_location_preview"}}}
    state("location_challenge_arrived", "location_arrival", [
        expr("wq_location_kind == '挑战'"), asset("I_WQC_FIRE"), chapter_heading,
    ], preview_end)
    state("location_exploration_arrived", "location_arrival", [
        expr("wq_location_kind == '探索'"), exp_page, chapter_heading,
    ], preview_end)
    state("location_secret_arrived", "location_arrival", [
        expr("wq_location_kind == '秘闻'"), asset("I_WQSE_FIRE"),
        {"ocr_full": {"region": [0, 0, 1280, 140], "keyword_var": "wq_location_destination",
                      "selection": "unique_equals"}},
    ], preview_end)
    bind_task_presets(raw, source, resources, prefix="wq", resume="navigate", category="wq")

    reset = _wire_battle(raw, body, contract, phase, advance, "wq_battles", "wq_wins", "board")
    state("board_time_limit", "board",
          [expr("wq_limit_seconds > 0 and elapsed_ms >= wq_limit_seconds * 1000")],
          advance("exit", wq_exit_reason="'time_limit'"))
    state("board_limit_reached", "board", [expr("wq_battles >= wq_max_battles")],
          advance("exit", wq_exit_reason="'limit_count_reached'"))
    state("board_claim_box", "board", [asset("I_WQ_BOX")], click("I_WQ_BOX", delay=1000), {"inc": "wq_rewards"})
    state("board_claim_treasure", "board", [asset("I_TREASURE_BOX_CLICK", "Exploration")],
          click("I_TREASURE_BOX_CLICK", "Exploration", 1000), {"inc": "wq_rewards"})
    state("board_open_tracked", "board", [
        expr("wq_follow_tracked"), exp_page, {"not": asset("I_TRACE_TRUE")},
        {"wanted_badge": "wq_map_progress"},
    ], {"click_found": True, "recheck": True, "recheck_retry": True, "delay": 1000},
       advance("location_panel"))
    state("board_lock_team", "board", [expr("not wq_follow_tracked and lock_team_enable"), asset("I_WQC_UNLOCK")],
          click("I_WQC_UNLOCK", delay=1000))
    state("board_fire_challenge", "board", [expr("not wq_follow_tracked"), asset("I_WQC_FIRE")],
          click("I_WQC_FIRE", delay=1200), {"set": reset}, advance("in_battle"))
    state("board_fire_secret", "board", [expr("not wq_follow_tracked"), asset("I_WQSE_FIRE")],
          click("I_WQSE_FIRE", delay=1200), {"set": reset}, advance("in_battle"))
    state("board_done_check", "board", [asset("I_WQ_DONE")], advance("exit"))
    state("board_scroll_up", "board", [expr("wq_list_swipes < 3"), asset("I_CHECK_EXPLORATION", "GameUi")],
          {"swipe": "WantedQuests::S_WQ_LIST_UP", "delay": 1000, "recheck": True}, {"inc": "wq_list_swipes"})
    state("board_scroll_exhausted", "board", [expr("wq_list_swipes >= 3")], advance("exit"))

    state("exit_wake_secret", "exit", [
        court, expr("wq_wake_secret and not wq_secret_woken"),
    ], {"oas_wake": {"task": "Secret", "failure_seconds_param": "wq_secret_failure_seconds"}},
       {"set": {"wq_secret_woken": True}})
    state("exit_done_target_prep", "exit", [court, expr("wq_next_delay_s > 0")],
          advance("stop_target", wq_target_delay_s="wq_next_delay_s", wq_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "悬赏封印已完成并按目标调度返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "WantedQuests",
                "delay_seconds_var": "wq_target_delay_s",
                "observed_ms_var": "wq_observed_ms",
            },
            "evidence": {"scope": "wanted_quests_target_schedule"},
        }
    })
    state("exit_done", "exit", [court], {
        "stop": {
            "reason": "悬赏封印已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "WantedQuests",
            "evidence": {"scope": "wanted_quests_bounded_loop"},
        }
    })
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))

    raw["oas_wanted_quests_contract"] = {
        "source": WANTED_ENTRY,
        "source_pins": {**WANTED_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "wanted_quests_ocr_routing_and_cooperation",
            "blocking": True,
            "requirement": "Verify all O_WQ_TEXT_ALL layouts, complete selected routes and repeat/return semantics, "
                           "and verify cooperation options",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_bondling_fairyland_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS BondlingFairyland (契灵之境) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, BONDLING_PINS, "BondlingFairyland")
    nav = compile_navigation_family(
        source, resources, prefix="bf_nav", destination="page_bondling_fairyland",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="bf_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_bondling_fairyland_natively_staged", title="契灵之境", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3600
    bind_schedule(source, raw)
    raw["params"].update(
        bf_mode={"default": "search", "choices": ["search", "catch"]},
        bf_user_status={"default": "alone", "choices": ["alone", "leader", "member", "handoff1", "handoff2"]},
        bf_limit_count={"default": 20, "min": 0, "max": 500},
        bf_limit_seconds={"default": 1800, "min": 0, "max": 7200},
        bf_member_wait_seconds={"default": 120, "min": 0, "max": 3540},
        bf_confirm_buy_stone={"default": False},
        bf_confirm_stone_spend={"default": False},
        bf_stone_buy_clicks={"default": 1, "min": 1, "max": 5},
        bf_area_select={"default": "none", "choices": ["none", "area1", "area2"]},
        bf_config_catch_plates={"default": False},
        bf_catch_plate_tier={"default": "low", "choices": ["low", "medium", "high"]},
        bf_check_plate_count={"default": False},
        bf_check_ball_count={"default": False},
        bf_check_stone_count={"default": False},
        bf_check_memory_enable={"default": False},
        bf_memory_limit={"default": 999, "min": 0, "max": 99999},
        bf_ball_scan_enable={"default": False},
        bf_target_ball_slot={"default": 0, "min": 0, "max": 5},
        bf_cap_continue_on_fail={"default": False},
        bf_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(body["vars"], bf_phase="entry", bf_battles=0, bf_wins=0, bf_main_arrived=0,
                       bf_handoff_stage=0, bf_handoff_arrived=0, bf_first_leg_battles=0,
                       bf_first_leg_wins=0, bf_member_since=-1, bf_final_notify=False, bf_notified_at=-1,
                       bf_mall_arrived=0, bf_memory_count=-1, bf_memory_capped=False,
                       bf_area_selected=False, bf_capture_configured=False, bf_stone_bought=False,
                       bf_stone_exhausted=False, bf_stone_count=-1, bf_ball_count=-1,
                       bf_stone_buy_taps=0, bf_plate_count=-1,
                       bf_ball_selected=0, bf_cap_wins=0, bf_cap_fails=0,
                       bf_target_delay_s=0, bf_observed_ms=0, bf_exit_reason="")
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/BondlingFairyland.yaml",
        "upstream/oas/RichMan.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("BondlingFairyland", "RichMan", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"bf_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"bf_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"bf_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="BondlingFairyland"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="BondlingFairyland", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("buy_stone_economic_gate", "entry", [expr("bf_confirm_buy_stone and not bf_confirm_stone_spend")],
          {"fail": "契灵之境商店购买契灵石涉及勾玉/金币消耗，需显式确认(bf_confirm_stone_spend=True)"})
    state("search_requires_solo", "entry", [expr("bf_mode == 'search' and bf_user_status != 'alone'")],
          {"fail": "契灵之境探查模式只支持单人"})
    state("memory_check_start", "entry", [expr("bf_check_memory_enable and bf_memory_count < 0")],
          advance("goto_mall", bf_mall_arrived=0))
    mall_page = raw["navigation"]["pages"]["page_mall"]["when"]
    state("mall_arrived", "goto_mall", [mall_page, expr("bf_mall_arrived == 1")], advance("mall_scales"))
    state("mall_drive", "goto_mall", [], {"navigate": {"destination": "page_mall", "done_var": "bf_mall_arrived"}})
    state("mall_scales_opened", "mall_scales", [asset("I_MALL_SCCALES_CHECK", "RichMan")], advance("mall_bondlings"))
    state("mall_scales_tap", "mall_scales", [asset("I_MALL_SCCALES", "RichMan")],
          click("I_MALL_SCCALES", "RichMan", 1000))
    state("mall_bondlings_opened", "mall_bondlings", [asset("I_MALL_BONDLINGS_ON", "RichMan")], advance("mall_read_memory"))
    state("mall_bondlings_tap", "mall_bondlings", [asset("I_MALL_BONDLINGS_SURE", "RichMan")],
          click("I_MALL_BONDLINGS_SURE", "RichMan", 1000))
    state("mall_memory_capped", "mall_read_memory",
          [{"ocr": "RichMan::O_BL_CHECK_MONEY", "mode": "counter_current", "var": "bf_memory_count"},
           expr("bf_memory_count >= bf_memory_limit")],
          advance("exit", bf_memory_capped=True, bf_exit_reason="'memory_capped'"))
    state("mall_memory_ok", "mall_read_memory",
          [{"ocr": "RichMan::O_BL_CHECK_MONEY", "mode": "counter_current", "var": "bf_memory_count"},
           expr("bf_memory_count >= 0 and bf_memory_count < bf_memory_limit")],
          advance("entry"))
    first = "bf_handoff_stage == 0"
    handoff = "bf_user_status == 'handoff1' or bf_user_status == 'handoff2'"
    leader = expr(f"bf_user_status == 'leader' or (bf_user_status == 'handoff1' and {first}) or "
                  "(bf_user_status == 'handoff2' and bf_handoff_stage == 1)")
    member = expr(f"bf_user_status == 'member' or (bf_user_status == 'handoff2' and {first}) or "
                  "(bf_user_status == 'handoff1' and bf_handoff_stage == 1)")
    limited = expr(f"bf_battles >= bf_limit_count // (1 + ({handoff}))")
    timed_out = expr("elapsed_ms >= bf_limit_seconds * 1000")
    bind_task_presets(raw, source, resources, prefix="bf", resume="route_entry", category="bf")
    state("route_member", "route_entry", [expr("bf_user_status == 'member'")], advance("member_accept"))
    state("route_nav", "route_entry", [expr("bf_user_status != 'member'")], advance("navigate"))
    _wire_nav(raw, "bf", phase, advance, "role_ready")
    state("after_route_member", "role_ready", [member], advance("member_accept", bf_member_since="elapsed_ms"))
    state("after_route_other_role", "role_ready", [], advance("loop"))

    # Leader & Member shared GeneralRoom / GeneralInvite integration
    state("leader_time_before_room", "loop", [leader, timed_out], advance("after_room_exit"))
    state("leader_ball_zero", "loop",
          [leader, expr("bf_mode == 'catch' and bf_check_ball_count"), asset("I_BALL_HELP"),
           {"ocr": "BondlingFairyland::O_B_BALL_NUMBER", "mode": "counter_current", "var": "bf_ball_count"},
           expr("bf_ball_count == 0")],
          advance("after_room_exit", bf_exit_reason="'no_ball_number'"))
    state("leader_open_help", "loop", [leader, asset("I_BALL_HELP")],
          click("I_BALL_HELP", delay=1000), advance("leader_team_create"))
    state("leader_team_confirm_popup", "leader_team_create", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("leader_create_team_btn", "leader_team_create", [asset("I_CREATE_TEAM")],
          click("I_CREATE_TEAM", delay=1200), advance("leader_invite"))
    state("leader_create_room_entry", "leader_team_create", [asset("I_CREATE_ROOM", "Component_GeneralRoom")],
          advance("room_create"))
    bind_room_create(raw, source, resources, prefix="bf", phase_var="bf_phase",
                     entry_phase="room_create", ready_phase="leader_invite", fail_phase="room_create_fail")
    state("room_create_failed", "room_create_fail", [], {"fail": "契灵之境创建求援房间失败"})
    state("leader_time_stop", "leader_invite", [timed_out], advance("room_exit"))
    state("leader_count_stop_handoff", "leader_invite",
          [limited, expr(f"bf_user_status == 'handoff1' and {first} and not bf_final_notify")],
          advance("leader_invite", bf_final_notify=True))
    state("leader_count_stop", "leader_invite", [limited, expr("not bf_final_notify")], advance("room_exit"))
    bind_leader_invite_and_fire(raw, source, resources, prefix="bf", phase_var="bf_phase",
                                entry_phase="leader_invite", battle_phase="team_battle_init",
                                exit_phase="room_exit", room_type="normal_3",
                                notify_only=("bf_final_notify", "leader_notified"))
    state("leader_notify_wait_start", "leader_notified", [],
          advance("leader_notify_wait", bf_notified_at="elapsed_ms"))
    state("leader_notify_wait_done", "leader_notify_wait", [expr("elapsed_ms - bf_notified_at >= 3000")],
          advance("room_exit"))
    state("leader_notify_waiting", "leader_notify_wait", [], {"wait": 100})
    state("member_begin_timer", "member_accept", [expr("bf_member_since < 0")],
          advance("member_accept", bf_member_since="elapsed_ms"))
    for where in ("member_accept", "bf_mem_wait"):
        state(where + "_wait_limit", where, [{"any": [timed_out,
              expr("elapsed_ms - bf_member_since >= bf_member_wait_seconds * 1000")]}], advance("room_exit"))
    bind_member_accept_and_wait(raw, source, resources, prefix="bf", phase_var="bf_phase",
                                entry_phase="member_accept", battle_phase="team_battle_init", exit_phase="room_exit")
    state("member_idle", "member_accept", [], {"wait": 250})
    state("member_in_room_idle", "bf_mem_wait", [], {"wait": 250})
    bind_room_exit(raw, source, resources, prefix="bf", phase_var="bf_phase",
                   entry_phase="room_exit", done_phase="after_room_exit")
    state("handoff_switch_roles", "after_room_exit", [expr(f"({handoff}) and {first}")],
          advance("handoff_return", bf_handoff_stage=1, bf_handoff_arrived=0, bf_final_notify=False,
                  bf_first_leg_battles="bf_battles", bf_first_leg_wins="bf_wins",
                  bf_battles=0, bf_wins=0, bf_member_since=-1))
    state("room_exit_completed", "after_room_exit", [], advance("exit"))
    page = raw["navigation"]["pages"]["page_bondling_fairyland"]["when"]
    state("handoff_arrived", "handoff_return", [page, expr("bf_handoff_arrived == 1")], advance("role_ready"))
    state("handoff_return_to_area", "handoff_return", [], {"navigate": {
        "destination": "page_bondling_fairyland", "done_var": "bf_handoff_arrived"}})

    state("cap_success", "in_battle", [expr("bf_mode == 'catch'"), asset("I_CAP_SUCCESS")],
          click("C_CAP_SUCCESS", delay=1200),
          advance("after_battle", bf_cap_wins="bf_cap_wins + 1", bf_battles="bf_battles + 1", bf_wins="bf_wins + 1"))
    state("cap_battle_win", "in_battle", [expr("bf_mode == 'catch'"), asset("I_BATTLE_SUCCESS")],
          click("C_CAP_SUCCESS", delay=1000))
    state("cap_fail_retry", "in_battle",
          [expr("bf_mode == 'catch' and bf_cap_continue_on_fail"), asset("I_CAP_AGAIN")],
          click("I_CAP_AGAIN", delay=1200), {"inc": "bf_cap_fails"})
    state("cap_fail_abandon", "in_battle",
          [expr("bf_mode == 'catch' and not bf_cap_continue_on_fail"), asset("I_BATTLE_FAIL_ABANDON")],
          click("I_BATTLE_FAIL_ABANDON", delay=1200),
          advance("after_battle", bf_cap_fails="bf_cap_fails + 1", bf_battles="bf_battles + 1"))
    state("cap_failure_banner", "in_battle", [expr("bf_mode == 'catch'"), asset("I_CAP_FAILURE")],
          click("C_CAP_SUCCESS", delay=1200),
          advance("after_battle", bf_cap_fails="bf_cap_fails + 1", bf_battles="bf_battles + 1"))

    reset = _wire_battle(raw, body, contract, phase, advance, "bf_battles", "bf_wins", "after_battle")
    state("team_battle_start", "team_battle_init", [], {"set": reset}, advance("in_battle"))
    state("after_battle_alone", "after_battle", [expr("bf_user_status == 'alone'")], advance("loop"))
    state("after_battle_leader", "after_battle", [leader], advance("leader_invite"))
    state("after_battle_member", "after_battle", [member], advance("member_accept", bf_member_since="elapsed_ms"))

    state("limit_reached", "loop", [expr("bf_user_status == 'alone'"), {"any": [limited, timed_out]}],
          advance("exit"))
    # Region selection (平安京 / 逢魔之原)
    state("area_select_start", "loop",
          [expr("bf_area_select != 'none' and not bf_area_selected"), asset("I_BALL_AREA")],
          click("I_BALL_AREA", delay=1200), advance("select_area"))
    state("area_select_1", "select_area", [asset("I_CHECK_AREA"), expr("bf_area_select == 'area1'")],
          click("C_AREA_1", delay=800), advance("select_area_wait"))
    state("area_select_2", "select_area", [asset("I_CHECK_AREA"), expr("bf_area_select == 'area2'")],
          click("C_AREA_2", delay=800), advance("select_area_wait"))
    state("area_select_done", "select_area_wait", [asset("I_BALL_AREA")],
          advance("loop", bf_area_selected=True))

    # Guarded stone purchase / summon (requires both bf_confirm_buy_stone and bf_confirm_stone_spend + runtime sensitive)
    state("stone_buy_open", "loop",
          [expr("bf_confirm_buy_stone and bf_confirm_stone_spend and not bf_stone_bought and not bf_stone_exhausted"),
           asset("I_STONE_ENTER")],
          click("I_STONE_ENTER", delay=1000), advance("buy_stone", bf_stone_buy_taps=0))
    state("stone_zero_close", "buy_stone",
          [expr("bf_check_stone_count"), asset("I_STONE_SURE"),
           {"ocr": "BondlingFairyland::O_B_STONE_NUMBER", "mode": "counter_current", "var": "bf_stone_count"},
           expr("bf_stone_count == 0")],
          advance("buy_stone_close", bf_stone_exhausted=True, bf_exit_reason="'no_stone_number'"))
    state("stone_buy_plus", "buy_stone",
          [expr("bf_stone_buy_taps < bf_stone_buy_clicks"), asset("I_BUY_PLUS")],
          click("I_BUY_PLUS", delay=500), {"inc": "bf_stone_buy_taps"})
    state("stone_buy_sure", "buy_stone", [asset("I_STONE_SURE")],
          click("I_STONE_SURE", delay=1500), advance("buy_stone_close", bf_stone_bought=True))
    raw["states"][-1].update(sensitive="花勾玉", desc="契灵之境：购买/使用鸣契石进行契灵召唤。")
    state("stone_close_confirm", "buy_stone_close", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("stone_close_btn", "buy_stone_close", [asset("I_STONE_CLOSE")],
          click("I_STONE_CLOSE", delay=800), advance("loop"))
    state("stone_close_done", "buy_stone_close",
          [{"not": asset("I_STONE_CLOSE")}, {"not": asset("I_UI_CONFIRM", "GlobalGame")}],
          advance("loop"))

    # Capture setting modal (auto-catch, minimal mode, plate tier, continuous & bond toggles)
    state("catch_config_open", "loop",
          [expr("bf_mode == 'catch' and bf_config_catch_plates and not bf_capture_configured"),
           asset("I_CLICK_CAPTION")],
          click("I_CLICK_CAPTION", delay=1000), advance("capture_setting"))
    state("cap_cfg_auto_on", "capture_setting", [asset("I_CAPTION_ENSURE"), asset("I_C_AUTO_FALSE")],
          click("I_C_AUTO_FALSE", delay=800))
    state("cap_cfg_minimal_on", "capture_setting",
          [asset("I_CAPTION_ENSURE"), asset("I_C_MINIMAL_MODE_DISABLE")],
          click("I_C_MINIMAL_MODE_DISABLE", delay=800))
    for tier, false_asset in (("low", "I_C_LOW_FALSE"), ("medium", "I_C_MIDUM_FALSE"), ("high", "I_C_HIGH_FALSE")):
        state(f"cap_cfg_{tier}_on", "capture_setting",
              [asset("I_CAPTION_ENSURE"), expr(f"bf_catch_plate_tier == {tier!r}"), asset(false_asset)],
              click(false_asset, delay=800))
    state("cap_cfg_low_cont_off", "capture_setting",
          [asset("I_CAPTION_ENSURE"), expr("bf_catch_plate_tier == 'low'"), asset("I_C_CONTINUOUS_DISABLE")],
          click("I_C_CONTINUOUS_DISABLE", delay=800))
    state("cap_cfg_low_first_off", "capture_setting",
          [asset("I_CAPTION_ENSURE"), expr("bf_catch_plate_tier == 'low'"), asset("I_C_FIRST_DISABLE")],
          click("I_C_FIRST_DISABLE", delay=800))
    state("cap_cfg_med_cont_on", "capture_setting",
          [asset("I_CAPTION_ENSURE"), expr("bf_catch_plate_tier == 'medium'"), asset("I_C_CONTINUOUS_ENABLE")],
          click("I_C_CONTINUOUS_ENABLE", delay=800))
    state("cap_cfg_med_first_on", "capture_setting",
          [asset("I_CAPTION_ENSURE"), expr("bf_catch_plate_tier == 'medium'"), asset("I_C_FIRST_ENABLE")],
          click("I_C_FIRST_ENABLE", delay=800))
    state("cap_cfg_confirm", "capture_setting", [asset("I_CAPTION_ENSURE")],
          click("I_CAPTION_ENSURE", delay=1000), advance("loop", bf_capture_configured=True))

    not_in_catch_ui = {"not": {"any": [asset("I_BALL_FIRE"), asset("I_BALL_HELP")]}}
    need_ball = expr("bf_mode == 'catch' and bf_ball_scan_enable and bf_ball_selected == 0")
    for slot, icon, click_name in (
        (1, "I_BF_LOCAL_1_AZURE_BASAN", "C_STONE_1"),
        (2, "I_BF_LOCAL_2_SNOWBALL", "C_STONE_2"),
        (3, "I_BF_LOCAL_3_LITTLE_KURO", "C_STONE_3"),
        (5, "I_BF_LOCAL_5_TOMB_GUARD", "C_STONE_5"),
    ):
        state(f"pick_ball_slot_{slot}", "loop",
              [need_ball, not_in_catch_ui,
               expr(f"bf_target_ball_slot == 0 or bf_target_ball_slot == {slot}"),
               asset(icon)],
              click(click_name, delay=1000), {"set": {"bf_ball_selected": slot}})
    state("pick_ball_slot_4", "loop",
          [need_ball, not_in_catch_ui, expr("bf_target_ball_slot == 4"),
           {"not": asset("I_BF_LOCAL_4_NONE")}],
          click("C_STONE_4", delay=1000), {"set": {"bf_ball_selected": 4}})
    state("lock_search", "loop", [expr("lock_team_enable"), asset("I_BF_UNLOCK")], click("I_BF_UNLOCK", delay=1000))
    state("lock_catch", "loop", [expr("lock_team_enable"), asset("I_BALL_UNLOCK")], click("I_BALL_UNLOCK", delay=1000))
    for tier, plate_ocr in (
        ("low", "O_B_LOW_NUMBER"),
        ("medium", "O_B_MEDIUM_NUMBER"),
        ("high", "O_B_HIGH_NUMBER"),
    ):
        state(f"plate_zero_{tier}", "loop",
              [expr(f"bf_user_status == 'alone' and bf_mode == 'catch' and bf_check_plate_count "
                    f"and bf_catch_plate_tier == {tier!r}"),
               asset("I_BALL_FIRE"),
               {"ocr": f"BondlingFairyland::{plate_ocr}", "mode": "counter_current", "var": "bf_plate_count"},
               expr("bf_plate_count == 0")],
              advance("exit", bf_exit_reason="'no_plate_number'"))
    state("catch_ball_zero", "loop",
          [expr("bf_user_status == 'alone' and bf_mode == 'catch' and bf_check_ball_count"),
           asset("I_BALL_FIRE"),
           {"ocr": "BondlingFairyland::O_B_BALL_NUMBER", "mode": "counter_current", "var": "bf_ball_count"},
           expr("bf_ball_count == 0")],
          advance("exit", bf_exit_reason="'no_ball_number'"))
    state("fire_search", "loop", [expr("bf_user_status == 'alone' and bf_mode == 'search'"), asset("I_BF_SEARSH")],
          click("I_BF_SEARSH", delay=1200), {"set": reset}, advance("in_battle"))
    state("fire_catch", "loop", [expr("bf_user_status == 'alone' and bf_mode == 'catch'"), asset("I_BALL_FIRE")],
          click("I_BALL_FIRE", delay=1200), {"set": reset}, advance("in_battle"))

    state("exit_done_target_prep", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("bf_next_delay_s > 0")],
          advance("stop_target", bf_target_delay_s="bf_next_delay_s", bf_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "契灵之境已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "BondlingFairyland",
                "delay_seconds_var": "bf_target_delay_s",
                "observed_ms_var": "bf_observed_ms",
            },
            "evidence": {"scope": "bondling_fairyland_target_schedule"},
        }
    })
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "契灵之境已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "BondlingFairyland",
            "evidence": {"scope": "bondling_fairyland_native_loop"},
        }
    })
    state("exit_nav", "exit", [],
          {"navigate": {"destination": "page_main", "done_var": "bf_main_arrived"}})

    raw["oas_bondling_fairyland_contract"] = {
        "source": BONDLING_ENTRY,
        "source_pins": {**BONDLING_PINS, **SOUL_PINS, **SCHEDULE_PINS, **ROOM_INVITE_PINS},
        "handoff": {"handoff1": ["leader", "member"], "handoff2": ["member", "leader"],
                    "count": "Integer half of the configured count; reset between roles.",
                    "member_end": "Wait timer or overall time cap, with the wait clock reset after each battle."},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "bondling_fairyland_ball_selection_and_handoff",
            "blocking": True,
            "requirement": "Bind 5-slot bondling ball identification, mall bondling-memory check and stone purchase. "
                           "Verify handoff roles with two accounts, including terminal invitation and battle cancellation.",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_dokan_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Dokan (阴阳寮道馆突破) workflow with guild-admin start gate."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, DOKAN_PINS, "Dokan")
    nav = compile_navigation_family(
        source, resources, prefix="dk_nav", destination="page_guild",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="dk_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_dokan_natively_staged", title="道馆突破", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 2400
    bind_schedule(source, raw)
    raw["params"].update(
        dk_is_open_day={"default": True},
        dk_try_start_dokan={"default": False},
        dk_confirm_start_dokan={"default": False},
        dk_abandon_after_master={"default": False},
        dk_confirm_abandon={"default": False},
        dk_vote_mode={"default": "keep_bounty", "choices": ["keep_bounty", "battle_again"]},
        dk_abandon_vote_mode={"default": "continue", "choices": ["continue", "abandon"]},
        dk_attack_priority={"default": 0, "min": 0, "max": 4},
        dk_master_limit={"default": 2, "min": 0, "max": 2},
        dk_max_battles={"default": 20, "min": 1, "max": 60},
        dk_limit_seconds={"default": 2400, "min": 0, "max": 7200},
        dk_next_open_delay_s={"default": 0, "min": 0, "max": 604800},
        dk_cheering_enable={"default": False},
        dk_green_enable={"default": False},
        dk_green_mark={"default": "left1", "choices": ["left1", "left2", "left3", "left4", "left5", "main"]},
        dk_preset_group_1={"default": 0, "min": 0, "max": 7},
        dk_preset_team_1={"default": 0, "min": 0, "max": 5},
        dk_preset_group_2={"default": 0, "min": 0, "max": 7},
        dk_preset_team_2={"default": 0, "min": 0, "max": 5},
    )
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        dk_phase="entry", dk_battles=0, dk_wins=0, dk_master_battles=0, dk_master_stage=0,
        dk_priority_selected=False, dk_cd_waits=0, dk_abandoned=False, dk_created=False,
        dk_cheers=0, dk_green_mark_done=False, dk_green_marks=0,
        dk_active_preset_group=0, dk_active_preset_team=0,
        dk_target_delay_s=0, dk_observed_ms=0, dk_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/Dokan.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("Dokan", "Component_GeneralBattle", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"dk_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"dk_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"dk_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Dokan"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="Dokan", delay=1000):
        return _click_from(docs, name, ns, delay)

    state("closed_day_target", "entry", [expr("not dk_is_open_day and dk_next_open_delay_s > 0")],
          advance("stop_target", dk_target_delay_s="dk_next_open_delay_s",
                  dk_observed_ms="elapsed_ms", dk_exit_reason="'closed_day'"))
    state("closed_day_clean", "entry", [expr("not dk_is_open_day")], {
        "stop": {
            "reason": "今日非道馆开放日(周一至周四配置)",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Dokan",
            "evidence": {"scope": "dokan_closed_day"},
        }
    })
    state("start_dokan_confirm_gate", "entry", [expr("dk_try_start_dokan and not dk_confirm_start_dokan")],
          {"fail": "开启寮道馆属于寮管理操作，需显式开启 dk_confirm_start_dokan 确认参数"})
    state("abandon_dokan_gate", "entry", [expr("dk_abandon_after_master and not dk_confirm_abandon")],
          {"fail": "放弃道馆突破属于寮管理操作，需显式开启 dk_confirm_abandon 确认参数"})
    bind_task_presets(raw, source, resources, prefix="dk", resume="navigate", category="dk")
    _wire_nav(raw, "dk", phase, advance, "enter")

    state("enter_ready_check", "enter", [asset("I_RYOU_DOKAN_CHECK")], advance("loop"))
    state("enter_ready_field", "enter", [asset("I_RYOU_DOKAN_IN_FIELD")], advance("loop"))
    state("enter_ready_challenge", "enter", [asset("I_RYOU_DOKAN_START_CHALLENGE")], advance("loop"))
    state("enter_activated", "enter", [asset("I_RYOU_DOKAN_ACTIVATED")], click("I_RYOU_DOKAN_ACTIVATED", delay=1200))
    state("enter_dokan", "enter", [asset("I_RYOU_DOKAN")], click("I_RYOU_DOKAN", delay=1200))
    state("enter_shrine", "enter", [asset("I_RYOU_SHENSHE")], click("I_RYOU_SHENSHE", delay=1200))

    for mark_key, click_name in (
        ("left1", "C_GREEN_LEFT_1"), ("left2", "C_GREEN_LEFT_2"),
        ("left3", "C_GREEN_LEFT_3"), ("left4", "C_GREEN_LEFT_4"),
        ("left5", "C_GREEN_LEFT_5"), ("main", "C_GREEN_MAIN"),
    ):
        state(f"in_battle_green_{mark_key}", "in_battle", [
            expr(f"dk_green_enable and not dk_green_mark_done and dk_green_mark == {mark_key!r}"),
            {"any": [asset("I_RYOU_DOKAN_FIGHTING"), asset("I_BATTLE_INFO", "Component_GeneralBattle")]},
        ], click(click_name, "Component_GeneralBattle", delay=600),
           {"set": {"dk_green_mark_done": True}}, {"inc": "dk_green_marks"})
    reset = _wire_battle(raw, body, contract, phase, advance, "dk_battles", "dk_wins", "loop")
    state("loop_finished", "loop", [{"any": [asset("I_RYOU_DOKAN_FINISHED"), asset("I_RYOU_DOKAN_WIN")]}],
          advance("exit", dk_exit_reason="'dokan_finished'"))
    state("loop_remain_count_exhausted", "loop",
          [{"any": [asset("I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE"), asset("I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO")]}],
          advance("exit", dk_exit_reason="'no_remain_count'"))
    state("loop_create_dokan_confirm", "loop",
          [expr("dk_try_start_dokan and dk_confirm_start_dokan and not dk_created"),
           asset("I_RYOU_DOKAN_CREATE_DOKAN_ENSURE")],
          click("I_RYOU_DOKAN_CREATE_DOKAN_ENSURE", delay=1200), {"set": {"dk_created": True}})
    raw["states"][-1].update(
        sensitive="购买",
        desc="寮管理开启道馆突破，将消耗阴阳寮勋章。",
    )
    state("loop_create_dokan_tap", "loop",
          [expr("dk_try_start_dokan and dk_confirm_start_dokan and not dk_created"),
           asset("I_RYOU_DOKAN_CREATE_DOKAN")],
          click("I_RYOU_DOKAN_CREATE_DOKAN", delay=1200))
    state("loop_finding_not_activated", "loop",
          [expr("not dk_try_start_dokan"), asset("I_RYOU_DOKAN_FINDING_DOKAN")],
          advance("exit", dk_exit_reason="'dokan_not_activated'"))
    state("loop_vote_keep_bounty", "loop",
          [expr("dk_vote_mode == 'keep_bounty'"), asset("I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY")],
          click("I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY", delay=1000))
    state("loop_vote_battle_again", "loop",
          [expr("dk_vote_mode == 'battle_again'"), asset("I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN")],
          click("I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN", delay=1000))
    state("loop_abandon_vote_continue", "loop",
          [expr("dk_abandon_vote_mode == 'continue'"), asset("I_RYOU_DOKAN_ABANDONED_TOPPA_CONTINUE")],
          click("I_RYOU_DOKAN_ABANDONED_TOPPA_CONTINUE", delay=1000))
    state("loop_abandon_vote_abandon", "loop",
          [expr("dk_abandon_vote_mode == 'abandon'"), asset("I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED")],
          click("I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED", delay=1000))
    state("loop_quit_battle_ensure", "loop", [asset("I_RYOU_DOKAN_QUIT_BATTLE_ENSURE")],
          click("I_RYOU_DOKAN_QUIT_BATTLE_ENSURE", delay=1000))
    state("loop_exit_ensure", "loop", [asset("I_RYOU_DOKAN_EXIT_ENSURE")],
          click("I_RYOU_DOKAN_EXIT_ENSURE", delay=1000))
    state("loop_challenge_ensure", "loop", [asset("I_CHALLENGE_ENSURE")],
          click("I_CHALLENGE_ENSURE", delay=1000))
    state("loop_info_close", "loop", [asset("I_RYOU_DOKAN_DOKAN_INFO_CLOSE")],
          click("I_RYOU_DOKAN_DOKAN_INFO_CLOSE", delay=1000))
    state("loop_spoils_close", "loop", [asset("I_RYOU_DOKAN_SPOILS_OF_DOKAN")],
          click("C_DOKAN_TOPPA_RANK_CLOSE_AREA", delay=1000))
    state("loop_found_enter", "loop", [asset("I_RYOU_DOKAN_FOUND_DOKAN")],
          click("I_RYOU_DOKAN_FOUND_DOKAN", delay=1200))
    state("loop_close_rank", "loop", [asset("I_RYOU_DOKAN_TOPPA_RANK")],
          click("C_DOKAN_TOPPA_RANK_CLOSE_AREA", delay=1000))
    state("loop_battle_over", "loop", [asset("I_RYOU_DOKAN_BATTLE_OVER")],
          click("I_RYOU_DOKAN_BATTLE_OVER", delay=1000))
    state("loop_time_limit", "loop", [expr("elapsed_ms >= dk_limit_seconds * 1000")],
          advance("exit", dk_exit_reason="'time_limit'"))
    state("loop_limit", "loop", [expr("dk_battles >= dk_max_battles")],
          advance("exit", dk_exit_reason="'max_battles_reached'"))
    state("loop_cheering_tap", "loop",
          [expr("dk_cheering_enable"), asset("I_RYOU_DOKAN_CHEERING"), {"not": asset("I_RYOU_DOKAN_CHEERING_GRAY")}],
          click("I_RYOU_DOKAN_CHEERING", delay=1200), {"inc": "dk_cheers"})
    state("loop_cheering_goto", "loop",
          [expr("dk_cheering_enable"), asset("I_RYOU_DOKAN_CHEERING_ATTACKING_SAMA")],
          click("I_RYOU_DOKAN_CHEERING_ATTACKING_SAMA", delay=1200), {"inc": "dk_cheers"})
    # DokanScene dispatch: GATHERING (attack priority) / CD / BOSS_WAITING / MASTER_BATTLING
    for prio in range(5):
        state(f"loop_priority_pick_{prio}", "loop",
              [expr(f"not dk_priority_selected and dk_attack_priority == {prio}"),
               asset(f"I_RYOU_DOKAN_ATTACK_PRIORITY_{prio}")],
              click(f"I_RYOU_DOKAN_ATTACK_PRIORITY_{prio}", delay=800),
              {"set": {"dk_priority_selected": True}})
    state("loop_gathering_open_priority", "loop",
          [expr("not dk_priority_selected"), asset("I_RYOU_DOKAN_GATHERING"),
           asset("I_RYOU_DOKAN_ATTACK_PRIORITY")],
          click("I_RYOU_DOKAN_ATTACK_PRIORITY", delay=800))
    state("loop_gathering_wait", "loop", [asset("I_RYOU_DOKAN_GATHERING")], {"wait": 2000})
    state("loop_cd_wait", "loop",
          [{"any": [asset("I_RYOU_DOKAN_CD"), asset("I_RYOU_DOKAN_CD1")]}],
          {"inc": "dk_cd_waits"}, {"wait": 2000})
    state("loop_boss_waiting", "loop", [asset("I_DOKAN_BOSS_WAITING")], {"wait": 2000})
    state("loop_master_first_quit", "loop",
          [asset("I_RYOU_DOKAN_BATTLE_MASTER_FIRST"), expr("dk_master_battles >= dk_master_limit")],
          click("C_DOKAN_BATTLE_QUIT_AREA", delay=1000),
          advance("exit", dk_exit_reason="'master_limit_quit'"))
    state("loop_master_second_quit", "loop",
          [asset("I_RYOU_DOKAN_BATTLE_MASTER_SECOND"), expr("dk_master_limit < 2 or dk_master_battles >= dk_master_limit")],
          click("C_DOKAN_BATTLE_QUIT_AREA", delay=1000),
          advance("exit", dk_exit_reason="'master_second_quit'"))
    state("loop_master_first_fight", "loop",
          [asset("I_RYOU_DOKAN_BATTLE_MASTER_FIRST"), expr("dk_master_battles < dk_master_limit")],
          click("C_DOKAN_READY_FOR_BATTLE", delay=1200), {"set": reset},
          advance("in_battle", dk_master_stage=1, dk_master_battles="dk_master_battles + 1",
                  dk_green_mark_done=False, dk_active_preset_group="dk_preset_group_2",
                  dk_active_preset_team="dk_preset_team_2"))
    state("loop_master_second_fight", "loop",
          [asset("I_RYOU_DOKAN_BATTLE_MASTER_SECOND"), expr("dk_master_limit >= 2 and dk_master_battles < dk_master_limit")],
          click("C_DOKAN_READY_FOR_BATTLE", delay=1200), {"set": reset},
          advance("in_battle", dk_master_stage=2, dk_master_battles="dk_master_battles + 1",
                  dk_green_mark_done=False, dk_active_preset_group="dk_preset_group_2",
                  dk_active_preset_team="dk_preset_team_2"))
    state("loop_master_abandon_confirm", "loop",
          [expr("dk_abandon_after_master and dk_confirm_abandon"), asset("I_DOKAN_ABANDONED_TOPPA_ENSURE")],
          click("I_DOKAN_ABANDONED_TOPPA_ENSURE", delay=1000),
          advance("exit", dk_abandoned=True, dk_exit_reason="'dokan_abandoned'"))
    state("loop_master_abandon_tap", "loop",
          [expr("dk_abandon_after_master and dk_confirm_abandon and dk_master_battles >= dk_master_limit"),
           asset("I_DOKAN_ABANDONED_TOPPA")],
          click("I_DOKAN_ABANDONED_TOPPA", delay=1000))
    state("loop_master_limit_exit", "loop",
          [asset("I_RYOU_DOKAN_MASTER_BATTLE"), expr("dk_master_battles >= dk_master_limit")],
          advance("exit", dk_exit_reason="'master_limit_reached'"))
    state("loop_master_challenge", "loop",
          [asset("I_RYOU_DOKAN_MASTER_BATTLE"), asset("I_RYOU_DOKAN_START_CHALLENGE"),
           expr("dk_master_battles < dk_master_limit")],
          click("I_RYOU_DOKAN_START_CHALLENGE", delay=1200), {"set": reset},
          advance("in_battle", dk_master_battles="dk_master_battles + 1",
                  dk_green_mark_done=False, dk_active_preset_group="dk_preset_group_2",
                  dk_active_preset_team="dk_preset_team_2"))
    state("loop_start_challenge", "loop", [asset("I_RYOU_DOKAN_START_CHALLENGE")],
          click("I_RYOU_DOKAN_START_CHALLENGE", delay=1200), {"set": reset},
          advance("in_battle", dk_green_mark_done=False,
                  dk_active_preset_group="dk_preset_group_1", dk_active_preset_team="dk_preset_team_1"))
    state("loop_in_field", "loop", [asset("I_RYOU_DOKAN_IN_FIELD")],
          click("I_RYOU_DOKAN_IN_FIELD", delay=1200), {"set": reset},
          advance("in_battle", dk_green_mark_done=False,
                  dk_active_preset_group="dk_preset_group_1", dk_active_preset_team="dk_preset_team_1"))
    state("loop_in_field2", "loop", [asset("I_RYOU_DOKAN_IN_FIELD2")],
          click("I_RYOU_DOKAN_IN_FIELD2", delay=1200), {"set": reset},
          advance("in_battle", dk_green_mark_done=False,
                  dk_active_preset_group="dk_preset_group_1", dk_active_preset_team="dk_preset_team_1"))

    state("exit_done_target", "exit", [asset("I_CHECK_MAIN", "GameUi"), expr("dk_next_open_delay_s > 0")],
          advance("stop_target", dk_target_delay_s="dk_next_open_delay_s", dk_observed_ms="elapsed_ms"))
    state("exit_done", "exit", [asset("I_CHECK_MAIN", "GameUi")], {
        "stop": {
            "reason": "道馆突破已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Dokan",
            "evidence": {"scope": "dokan_bounded_loop"},
        }
    })
    state("exit_dokan_quit", "exit", [asset("I_RYOU_DOKAN_DOKAN_QUIT")],
          click("I_RYOU_DOKAN_DOKAN_QUIT", delay=1000))
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))
    state("stop_target_done", "stop_target", [], {
        "stop": {
            "reason": "道馆突破已按开放日程预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "Dokan",
                "delay_seconds_var": "dk_target_delay_s",
                "observed_ms_var": "dk_observed_ms",
            },
            "evidence": {"scope": "dokan_weekday_schedule"},
        }
    })

    raw["oas_dokan_contract"] = {
        "source": DOKAN_ENTRY,
        "source_pins": {**DOKAN_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *contract["source_obligations"], {
            "id": "dokan_scene_detector_master_and_green_mark",
            "blocking": True,
            "requirement": "Bind DokanSceneDetector full state machine, master 1st/2nd team swap, ExtendGreenMark, and guild-admin creat_dokan",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_exploration_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Exploration (探索章节狗粮) workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, EXPLORATION_PINS, "Exploration")
    nav = compile_navigation_family(
        source, resources, prefix="exp_nav", destination="page_mainline",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="exp_battle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]

    raw = nav["workflow"]
    raw.update(name="oas_exploration_natively_staged", title="探索副本", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 86580
    bind_schedule(source, raw)
    config = ast.parse((source / "tasks/Exploration/config.py").read_text(encoding="utf-8-sig"))
    levels = next(node for node in config.body if isinstance(node, ast.ClassDef) and node.name == "ExplorationLevel")
    chapters = [ast.literal_eval(node.value) for node in levels.body if isinstance(node, ast.Assign)]
    if len(chapters) != 28 or len(set(chapters)) != len(chapters):
        raise ValueError("Exploration chapter list no longer matches the pinned configuration")
    chapter_aliases = [[label, "名" + label[1:], "书" + label[1:]] for label in chapters]
    raw["params"].update(
        exp_limit_count={"default": 30, "min": 0, "max": 500},
        exp_limit_seconds={"default": 1800, "min": 0, "max": 86399},
        exp_chapter={"default": chapters[-1], "choices": chapters},
        exp_attack_number={"default": "all", "choices": ["all", "boss"]},
        exp_up_type={"default": "up_all", "choices": ["up_all", "up_exp", "up_coin", "up_daruma"]},
        exp_auto_rotate={"default": False},
        exp_fodder_rarity={"default": "N", "choices": ["N", "MATERIAL"]},
        exp_check_realm_raid={"default": False},
        exp_realm_raid_failure_seconds={"default": 1800, "min": 0, "max": 3155760000},
        exp_scrolls_mode={"default": False},
        exp_scrolls_threshold={"default": 25, "min": 1, "max": 30},
        exp_scrolls_cooldown_seconds={"default": 1800, "min": 0, "max": 3155760000},
        exp_scrolls_exploration_failure_seconds={"default": 86400, "min": 0, "max": 3155760000},
        exp_scrolls_realm_raid_failure_seconds={"default": 86400, "min": 0, "max": 3155760000},
        exp_scrolls_memory_failure_seconds={"default": 86400, "min": 0, "max": 3155760000},
        exp_buff_enable={"default": False},
        exp_buff_exp_50={"default": False},
        exp_buff_exp_100={"default": False},
        exp_buff_gold_50={"default": False},
        exp_buff_gold_100={"default": False},
    )
    raw["params"].update(body["params"])
    memory_server_params = {key: f"exp_scrolls_memory_{key.removeprefix('oas_')}" for key in SERVER_TIMING}
    raw["params"].update({param: dict(SERVER_TIMING[key]) for key, param in memory_server_params.items()})
    raw["vars"].update(
        body["vars"],
        exp_phase="entry", exp_battles=0, exp_wins=0,
        exp_rr_remain=-1, exp_rr_woken=False, exp_map_swipes=0, exp_exit_reason="",
        exp_chapter_direction=2, exp_chapter_swipes=0, exp_chapter_started=-1,
        exp_fodder_started=-1, exp_fodder_since=-1, exp_fodder_count=-1, exp_fodder_previous=-1,
        exp_auto_rotate_verified=False,
        exp_scrolls_tickets=-1, exp_scrolls_next_seconds=0, exp_scrolls_reference_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/Exploration.yaml",
        "upstream/oas/GlobalGame.yaml",
        "upstream/oas/Component_ReplaceShikigami.yaml",
    ]))
    rarity_assets = "Component_ReplaceShikigami"
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"]
            for ns in ("Exploration", "GlobalGame", rarity_assets)}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"exp_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"exp_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"exp_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Exploration", **options):
        return {"res": f"{ns}::{name}", **options}

    def click(name, ns="Exploration", delay=1000):
        return _click_from(docs, name, ns, delay)

    bind_task_presets(raw, source, resources, prefix="exp", resume="buff_before", category="exp")
    exp_buff_ops = [
        ("exp_50", "exp_buff_exp_50"), ("exp_100", "exp_buff_exp_100"),
        ("gold_50", "exp_buff_gold_50"), ("gold_100", "exp_buff_gold_100"),
    ]
    exp_buff_expr = "(exp_buff_enable and (exp_buff_exp_50 or exp_buff_exp_100 or exp_buff_gold_50 or exp_buff_gold_100))"
    buff_calls = [
        bind_courtyard_buffs(
            raw, source, resources, prefix=f"exp_buff_{leg}", phase_var="exp_phase",
            entry_phase=f"buff_{leg}", resume=resume, operations=exp_buff_ops,
            enable_param=exp_buff_expr, opening=opening,
        )
        for leg, opening, resume in (("before", True, "navigate"), ("after", False, "finished"))
    ]
    _wire_nav(raw, "exp", phase, advance, "enter_chapter")

    mainline = raw["navigation"]["pages"]["page_mainline"]["when"]
    enter_button = asset("I_E_EXPLORATION_CLICK")
    expiry = expr("elapsed_ms >= exp_limit_seconds * 1000")
    limit_reached = expr("exp_battles >= exp_limit_count")
    for where in ("enter_chapter", "chapter_find", "chapter_verify"):
        state(f"{where}_count_limit", where, [limit_reached],
              advance("exit", exp_exit_reason="'limit_count_reached'"))
        state(f"{where}_time_limit", where, [expiry], advance("exit", exp_exit_reason="'time_limit_reached'"))

    # Keep the earlier opt-in full-ticket trigger available alongside source scroll mode.
    state("realm_raid_full_wake", "enter_chapter",
          [expr("exp_check_realm_raid and not exp_scrolls_mode and not exp_rr_woken"),
           {"ocr": "Exploration::O_REALM_RAID_NUMBER", "mode": "counter_remaining", "var": "exp_rr_remain"},
           expr("exp_rr_remain == 0")],
          {"oas_wake": {"task": "RealmRaid", "failure_seconds_param": "exp_realm_raid_failure_seconds"}},
          advance("exit", exp_rr_woken=True, exp_exit_reason="'realm_raid_tickets_full'"))
    team_entrance = {"all": [enter_button, asset("I_EXP_CREATE_TEAM")]}
    for where, layouts in (
        ("enter_chapter", (("map", [mainline, {"not": enter_button}], "O_REALM_RAID_NUMBER"),)),
        ("chapter_verify", (
            ("team", [team_entrance], "O_REALM_RAID_NUMBER1"),
            ("solo", [enter_button, {"not": team_entrance}], "O_REALM_RAID_NUMBER"),
        )),
    ):
        for layout, guards, counter in layouts:
            state(f"scrolls_{layout}_threshold", where,
                  [expr("exp_scrolls_mode"), *guards,
                   {"ocr": f"Exploration::{counter}", "mode": "counter_current", "var": "exp_scrolls_tickets"},
                   expr("exp_scrolls_tickets >= exp_scrolls_threshold")],
                  advance("exit", exp_exit_reason="'scrolls_ticket_threshold'"))
    selected_chapter = {"ocr_single": {"region": [145, 3, 190, 56], "equals_var": "exp_chapter"}}
    inside = {"any": [asset("I_EXPLORATION_TITLE"), asset("I_E_SETTINGS_BUTTON"),
                      asset("I_NORMAL_BATTLE_BUTTON"), asset("I_BOSS_BATTLE_BUTTON")]}
    state("chapter_begin_search", "enter_chapter", [mainline, {"not": enter_button}],
          advance("chapter_find", exp_chapter_started="elapsed_ms", exp_chapter_swipes=0))
    state("chapter_resume_selection", "enter_chapter", [enter_button, selected_chapter],
          advance("chapter_verify", exp_chapter_started="elapsed_ms"))
    state("chapter_back_to_list", "enter_chapter",
          [enter_button, {"not": selected_chapter}, asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 900))
    chapter_region = docs["Exploration"]["O_E_EXPLORATION_LEVEL_NUMBER"]["roi"]
    for index, target in enumerate(chapters, 1):
        nearest = {"ordered_list": {"region": chapter_region, "labels": chapter_aliases, "target": target,
                                    "direction_var": "exp_chapter_direction"}}
        live_chapter = [mainline, {"not": enter_button}, expr(f"exp_chapter == {target!r}"), nearest]
        state(f"chapter_click_{index}", "chapter_find", [*live_chapter, expr("exp_chapter_direction == 0")],
              {"click_found": True, "offset": [0, 0, 0, 0], "delay": 800, "recheck": True},
              advance("chapter_verify", exp_chapter_started="elapsed_ms"))
        for name, direction in (("earlier", -1), ("later", 1)):
            gesture = "S_SWIPE_LEVEL_UP" if direction < 0 else "S_SWIPE_LEVEL_DOWN"
            state(f"chapter_{name}_{index}", "chapter_find", [*live_chapter,
                  expr(f"exp_chapter_direction == {direction} and exp_chapter_swipes < 15 "
                       "and elapsed_ms - exp_chapter_started < 35000")],
                  {"swipe": f"Exploration::{gesture}", "delay": 900, "recheck": True},
                  {"inc": "exp_chapter_swipes"})
    state("chapter_lookup_exhausted", "chapter_find",
          [expr("exp_chapter_swipes >= 15 or elapsed_ms - exp_chapter_started >= 35000")],
          {"fail": "主线列表未唯一识别到配置章节，未进入探索战斗"})
    state("chapter_click_explore", "chapter_verify", [enter_button, selected_chapter],
          click("I_E_EXPLORATION_CLICK", delay=1200), advance("chapter_opening", exp_chapter_started="elapsed_ms"))
    state("chapter_label_mismatch", "chapter_verify", [expr("elapsed_ms - exp_chapter_started >= 10000")],
          {"fail": "章节详情标题未匹配配置，未点击探索"})
    state("chapter_entered_with_fodder", "chapter_opening",
          [inside, {"not": enter_button}, expr("exp_auto_rotate")],
          advance("fodder_open", exp_fodder_started="elapsed_ms", exp_map_swipes=0))
    state("chapter_entered", "chapter_opening", [inside, {"not": enter_button}, expr("not exp_auto_rotate")],
          advance("inside", exp_map_swipes=0))
    state("chapter_not_entered", "chapter_opening", [expr("elapsed_ms - exp_chapter_started >= 12000")],
          {"fail": "已点击探索，但未识别到章节内场景"})

    settings = asset("I_E_OPEN_SETTINGS")
    settings_button = asset("I_E_SETTINGS_BUTTON")
    reserve_count = {"ocr": "Exploration::O_E_ALTERNATE_NUMBER", "mode": "counter_current", "var": "exp_fodder_count"}
    # The purple border has stable points on its left edge while the reserve tab is active.
    reserve_selected = {"colors": [[480, 171, "#50328e"], [480, 382, "#55288e"]], "similarity": 69}
    rarity_choices = {}
    for rarity in ("N", "MATERIAL"):
        spec = docs[rarity_assets][f"I_RS_{rarity}"]
        x, y, width, height = spec["front"]
        region_vars = [f"exp_fodder_{rarity.lower()}_{k}" for k in ("x", "y", "w", "h")]
        raw["vars"].update(zip(region_vars, (x - 20, y - 20, width + 40, height + 40)))
        rarity_choices[rarity] = asset(f"I_RS_{rarity}", rarity_assets, region_vars=region_vars)
    rarity_menu = rarity_choices["MATERIAL"]
    # The source strip shows seven reserved cards. Match one badge when only
    # some cards are reserved, irrespective of their horizontal scroll offset.
    badge_area = [f"exp_fodder_badge_{k}" for k in ("x", "y", "w", "h")]
    raw["vars"].update(zip(badge_area, (148, 562, 984, 66)))
    already_reserved = asset("I_E_RATATE_EXSIT", region_vars=badge_area, template_crop=[48, 0, 31, 32],
                             threshold=.9)
    rotate_on, rotate_off = asset("I_E_AUTO_ROTATE_ON"), asset("I_E_AUTO_ROTATE_OFF")
    fodder_timeout = expr("elapsed_ms - exp_fodder_started >= 120000")
    state("fodder_opened", "fodder_open", [settings], advance("fodder_inspect"))
    state("fodder_open_settings", "fodder_open", [settings_button, {"not": settings}, {"not": fodder_timeout}],
          click("C_CLICK_SETTINGS"), advance("fodder_inspect"))
    state("fodder_select_reserves", "fodder_inspect",
          [settings, {"not": reserve_selected}, {"not": rarity_menu},
           reserve_count, expr("exp_fodder_count < 40"), {"not": fodder_timeout}],
          click("C_CLICK_STANDBY_TEAM"), advance("fodder_reserves_pending"))
    for where in ("fodder_inspect", "fodder_reserves_pending"):
        state(f"{where}_selected", where,
              [settings, reserve_selected, reserve_count, expr("exp_fodder_count < 40")], advance("fodder_class"))

    chosen = {"any": [
        {"all": [expr(f"exp_fodder_rarity == {kind!r}"), asset(f"I_RS_{kind}_SELECTED", rarity_assets)]}
        for kind in ("N", "MATERIAL")
    ]}
    active_reserves = [settings, reserve_selected, {"not": fodder_timeout}]
    state("fodder_class_selected", "fodder_class", [*active_reserves, {"not": rarity_menu}, chosen],
          advance("fodder_search"))
    for rarity, choice in rarity_choices.items():
        state(f"fodder_select_{rarity.lower()}", "fodder_class",
              [settings, {"not": fodder_timeout}, rarity_menu, expr(f"exp_fodder_rarity == {rarity!r}"),
               choice],
              {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1200})
    state("fodder_open_class_menu", "fodder_class",
          [*active_reserves, {"not": rarity_menu}, {"not": chosen}],
          click("C_SHIKIGAMI_SWITCH_1", rarity_assets, 1300))

    fill_guards = [settings, {"not": fodder_timeout}, {"not": rarity_menu},
                   reserve_count, expr("exp_fodder_count < 40"), chosen]
    state("fodder_skip_existing", "fodder_search", [*fill_guards, already_reserved],
          {"swipe": "Exploration::S_SWIPE_SHIKI_TO_LEFT", "delay": 850, "recheck": True})
    state("fodder_swipe_one", "fodder_search", [*fill_guards, {"not": already_reserved}],
          {"swipe": "Exploration::S_SWIPE_SHIKI_TO_LEFT_ONE", "delay": 800, "recheck": True},
          advance("fodder_hold", exp_fodder_previous="exp_fodder_count"))
    press = docs["Exploration"]["L_ROTATE_1"]
    state("fodder_hold_one", "fodder_hold",
          [*fill_guards, reserve_selected, {"not": already_reserved}, expr("exp_fodder_count == exp_fodder_previous")],
          {**click("L_ROTATE_1", delay=1000), "press_ms": press["press_ms"], "recheck_retry": True},
          advance("fodder_verify", exp_fodder_since="elapsed_ms"))
    state("fodder_added", "fodder_verify",
          [settings, reserve_count, expr("exp_fodder_count > exp_fodder_previous")],
          advance("fodder_search"))
    state("fodder_count_unchanged", "fodder_verify",
          [expr("elapsed_ms - exp_fodder_since >= 4500")],
          {"fail": "候补数量未在长按后增加，已停止继续添加"})

    for where in ("fodder_inspect", "fodder_search"):
        state(f"{where}_confirm", where,
              [settings, {"not": rarity_menu}, reserve_count, expr("exp_fodder_count >= 40"), asset("I_E_SURE_BUTTON")],
              click("I_E_SURE_BUTTON"), advance("fodder_return", exp_fodder_since="elapsed_ms"))
    outside_settings = [settings_button, {"not": settings}]
    state("fodder_rotation_on", "fodder_return", [*outside_settings, rotate_on],
          advance("inside", exp_auto_rotate_verified=True))
    state("fodder_enable_rotation", "fodder_return",
          [*outside_settings, rotate_off, {"not": rotate_on}, expr("elapsed_ms - exp_fodder_since < 5000")],
          click("I_E_AUTO_ROTATE_OFF"))
    state("fodder_return_unverified", "fodder_return", [expr("elapsed_ms - exp_fodder_since >= 5000")],
          {"fail": "未复核候补确认后的章节界面及自动轮换开关"})
    for where in ("fodder_open", "fodder_inspect", "fodder_reserves_pending", "fodder_class", "fodder_search", "fodder_hold"):
        state(f"{where}_timeout", where, [fodder_timeout],
              {"fail": "候补界面、稀有度或数量在时限内未完成复核"})

    reset = _wire_battle(raw, body, contract, phase, advance, "exp_battles", "exp_wins", "inside")
    state("inside_reward", "inside", [asset("I_BATTLE_REWARD")], click("I_BATTLE_REWARD", delay=1000))
    state("inside_treasure", "inside", [asset("I_TREASURE_BOX_CLICK")], click("I_TREASURE_BOX_CLICK", delay=1000))
    state("inside_limit", "inside", [limit_reached],
          advance("exit", exp_exit_reason="'limit_count_reached'"))
    state("inside_time_limit", "inside", [expiry], advance("exit", exp_exit_reason="'time_limit_reached'"))
    tap_battle = {"click_found": True, "use_match_size": True, "delay": 1200, "recheck": True, "recheck_retry": True}
    start_battle = ({"set": reset}, advance("in_battle"))
    state("inside_boss", "inside", [asset("I_BOSS_BATTLE_BUTTON")],
          tap_battle, *start_battle)
    state("inside_normal", "inside",
          [expr("exp_attack_number == 'all' and exp_up_type == 'up_all'"), asset("I_NORMAL_BATTLE_BUTTON")],
          tap_battle, *start_battle)
    for up_type, marker in (("up_exp", "I_UP_EXP"), ("up_coin", "I_UP_COIN"), ("up_daruma", "I_UP_DARUMA")):
        match = {"find_image_above": {
            "target": "Exploration::I_NORMAL_BATTLE_BUTTON", "reference": f"Exploration::{marker}",
            "x_pad": 60, "max_above": 300, "min_gap": 20, "x_weight": 3, "threshold": .9,
        }}
        state(f"inside_{up_type}", "inside", [expr(f"exp_attack_number == 'all' and exp_up_type == {up_type!r}"), match],
              tap_battle, *start_battle)
    chapter_returned = {"any": [mainline, enter_button, asset("I_CHECK_EXPLORATION", "GameUi")]}
    state("inside_returned_to_world", "inside", [chapter_returned, {"not": inside}],
          advance("enter_chapter", exp_map_swipes=0))
    state("inside_swipe_end", "inside", [asset("I_SWIPE_END")], advance("chapter_leave"))
    state("inside_targeted_swipe_limit", "inside", [expr("exp_up_type != 'up_all' and exp_map_swipes >= 2")],
          advance("chapter_leave"))
    state("inside_swipe_limit", "inside", [expr("exp_map_swipes >= 12")],
          {"fail": "探索满屏模式达到单章巡怪保护上限，未能验证右端边界"})
    state("inside_swipe_right", "inside", [{"any": [asset("I_EXPLORATION_TITLE"), asset("I_E_SETTINGS_BUTTON")]}],
          {"swipe": "Exploration::S_SWIPE_BACKGROUND_RIGHT", "delay": 1200, "recheck": True},
          {"inc": "exp_map_swipes"})

    map_back = asset("I_UI_BACK_YELLOW", "GlobalGame")
    exit_confirm = asset("I_E_EXIT_CONFIRM")
    state("chapter_left", "chapter_leave", [chapter_returned, {"not": inside}],
          advance("enter_chapter", exp_map_swipes=0))
    state("chapter_leave_reward", "chapter_leave", [asset("I_BATTLE_REWARD")], click("I_BATTLE_REWARD"))
    state("chapter_leave_confirm", "chapter_leave", [exit_confirm], click("I_E_EXIT_CONFIRM"))
    state("chapter_leave_back", "chapter_leave", [settings_button, {"not": settings}, {"not": exit_confirm}, map_back],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000))
    courtyard = raw["navigation"]["pages"]["page_main"]["when"]
    state("exit_done", "exit", [courtyard], advance("buff_after"))
    scrolls_stop = {
        "stop": {
            "reason": "探索突破券达到绘卷阈值，返回庭院并设置下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {"task": "Exploration", "delay_seconds_var": "exp_scrolls_next_seconds",
                             "observed_ms_var": "exp_scrolls_reference_ms"},
            "evidence": {"scope": "exploration_scrolls_handoff"},
        }
    }
    scrolls_handoff = expr("exp_exit_reason == 'scrolls_ticket_threshold'")
    state("finished_scrolls", "finished", [scrolls_handoff],
          {"set": {"exp_scrolls_next_seconds": "exp_scrolls_cooldown_seconds + elapsed_ms // 1000"}},
          advance("scrolls_schedule"))
    choose_delay = expr("exp_scrolls_exploration_failure_seconds < exp_scrolls_next_seconds")
    for suffix, guard, delay in (
        ("failure_interval", choose_delay, "exp_scrolls_exploration_failure_seconds"),
        ("cooldown", {"not": choose_delay}, "exp_scrolls_next_seconds"),
    ):
        state(f"scrolls_schedule_{suffix}", "scrolls_schedule", [guard],
              {"set": {"exp_scrolls_next_seconds": delay}},
              {"oas_wake": {"task": "RealmRaid", "failure_seconds_param": "exp_scrolls_realm_raid_failure_seconds"}},
              {"oas_wake": {"task": "MemoryScrolls", "failure_seconds_param": "exp_scrolls_memory_failure_seconds",
                            "server_params": memory_server_params}},
              scrolls_stop)
    state("finished", "finished", [], {
        "stop": {
            "reason": "探索副本已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Exploration",
            "evidence": {"scope": "exploration_solo_bounded_loop"},
        }
    })
    state("exit_reward", "exit", [asset("I_BATTLE_REWARD")], click("I_BATTLE_REWARD"))
    state("exit_confirm", "exit", [exit_confirm], click("I_E_EXIT_CONFIRM", delay=1000))
    state("exit_red_close", "exit", [asset("I_RED_CLOSE")], click("I_RED_CLOSE", delay=1000))
    state("exit_back_yellow", "exit", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1200))

    raw["oas_exploration_contract"] = {
        "source": EXPLORATION_ENTRY,
        "source_pins": {**EXPLORATION_PINS, **SOUL_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "buff_calls": buff_calls,
        "source_obligations": [
            *nav["source_obligations"], *contract["source_obligations"],
            *(ob for call in buff_calls for ob in call["source_obligations"]),
            {
                "id": "exploration_fodder_rotate_and_live",
                "blocking": True,
                "requirement": "Verify the N and material reserve update and rotation toggle on live frames, targeted UP fights, and the Realm Raid wake.",
            },
        ],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
