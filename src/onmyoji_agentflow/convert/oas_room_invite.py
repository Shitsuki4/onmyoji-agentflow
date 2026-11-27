"""Pinned reusable OAS Component/GeneralRoom & Component/GeneralInvite native builders (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..yamlio import load_yaml


ROOM_ASSETS = "Component_GeneralRoom"
INVITE_ASSETS = "Component_GeneralInvite"

PINS = {
    "tasks/Component/GeneralRoom/general_room.py": "66637fef102652be58145df4380e20b6d81d12801096d6ea336914aac2aeedc8",
    "tasks/Component/GeneralRoom/assets.py": "166e7706cacacdd3baf88bafda6455f5f574032b40ac5a85ab019b041344d87f",
    "tasks/Component/GeneralRoom/config_rom.py": "96ba5e35c22c1d305903dc9a167c346e70dd84cc8847993e2e2881d6a0fa448e",
    "tasks/Component/GeneralInvite/general_invite.py": "7f5ea9bd8690a184a26e132e8cf0580409589445859d5d14b8968d2a82eb5407",
    "tasks/Component/GeneralInvite/assets.py": "5fcda5ac864dcc20bcb1f4055c8df2174e10727325c2035aeb8679ea3f9ec1c8",
    "tasks/Component/GeneralInvite/config_invite.py": "c4634ba31f94f5c4ebd9b87b5e36b945e3fbf551adf245fa8cb169290f0ab673",
}


def verify_pins(source_root) -> None:
    source = Path(source_root)
    for rel, expected in PINS.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"GeneralRoom/GeneralInvite source fingerprint mismatch: {rel}")


def _click_from(docs: dict, name: str, ns: str, delay: int = 1000, recheck: bool = True) -> dict:
    spec = docs[ns][name]
    if spec["type"] in ("click", "long_click"):
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    return {"click": target, "delay": delay, "recheck": recheck}


def _load_docs(raw: dict, resources: Path) -> dict:
    raw["resources"] = sorted(set(raw["resources"] + [
        f"upstream/oas/{ROOM_ASSETS}.yaml",
        f"upstream/oas/{INVITE_ASSETS}.yaml",
        "upstream/oas/Component_GeneralBattle.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    return {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in (ROOM_ASSETS, INVITE_ASSETS, "Component_GeneralBattle", "GlobalGame")
    }


def _in_room_cond() -> dict:
    return {"any": [
        {"res": f"{INVITE_ASSETS}::I_GI_EMOJI_1"},
        {"res": f"{INVITE_ASSETS}::I_GI_EMOJI_2"},
        {"res": f"{INVITE_ASSETS}::I_GI_SPEAK"},
    ]}


def bind_room_create(
    raw: dict, source_root, resource_dir, *,
    prefix: str, phase_var: str, entry_phase: str, ready_phase: str, fail_phase: str,
    private_default: bool = True,
) -> None:
    """Bind GeneralRoom create_room -> ensure_private/public -> create_ensure phases."""
    verify_pins(source_root)
    docs = _load_docs(raw, Path(resource_dir))

    priv_param = f"{prefix}_room_private"
    clicks_var = f"{prefix}_room_create_clicks"
    raw["params"].setdefault(priv_param, {"default": private_default})
    raw["vars"].setdefault(clicks_var, 0)

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"{phase_var} == {val!r}")

    def advance(val, **updates):
        return {"set": {phase_var: repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"{prefix}_gr_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns=ROOM_ASSETS):
        return {"res": f"{ns}::{name}"}

    def click(name, ns=ROOM_ASSETS, delay=1000):
        return _click_from(docs, name, ns, delay)

    ensure_ph = f"{prefix}_gr_ensure_vis"
    confirm_ph = f"{prefix}_gr_confirm"

    state("create_ready_1", entry_phase, [asset("I_CREATE_ENSURE")], advance(ensure_ph))
    state("create_ready_2", entry_phase, [asset("I_CREATE_ENSURE_2")], advance(ensure_ph))
    state("create_retry_exceeded", entry_phase, [expr(f"{clicks_var} > 3")], advance(fail_phase))
    state("create_click", entry_phase, [asset("I_CREATE_ROOM")],
          {"click_found": True, "use_match_size": True, "delay": 1500, "recheck": True}, {"inc": clicks_var})

    # Visibility toggle (private vs public)
    state("private_ok", ensure_ph, [expr(priv_param), {"any": [asset("I_ENSURE_PRIVATE"), asset("I_ENSURE_PRIVATE_2")]}],
          advance(confirm_ph))
    state("private_toggle_1", ensure_ph, [expr(priv_param), asset("I_ENSURE_PRIVATE_FALSE")],
          click("I_ENSURE_PRIVATE_FALSE", delay=1000))
    state("private_toggle_2", ensure_ph, [expr(priv_param), asset("I_ENSURE_PRIVATE_FALSE_2")],
          click("I_ENSURE_PRIVATE_FALSE_2", delay=1000))
    state("public_ok", ensure_ph, [expr(f"not {priv_param}"), {"any": [asset("I_ENSURE_PUBLIC"), asset("I_ENSURE_PUBLIC_2")]}],
          advance(confirm_ph))
    state("public_toggle_1", ensure_ph, [expr(f"not {priv_param}"), asset("I_ENSURE_PUBLIC_FALSE")],
          click("I_ENSURE_PUBLIC_FALSE", delay=1000))
    state("public_toggle_2", ensure_ph, [expr(f"not {priv_param}"), asset("I_ENSURE_PUBLIC_FALSE_2")],
          click("I_ENSURE_PUBLIC_FALSE_2", delay=1000))

    # Confirm creation
    state("confirm_1", confirm_ph, [asset("I_CREATE_ENSURE")], click("I_CREATE_ENSURE", delay=1200))
    state("confirm_2", confirm_ph, [asset("I_CREATE_ENSURE_2")], click("I_CREATE_ENSURE_2", delay=1200))
    state("confirm_done", confirm_ph, [{"not": asset("I_CREATE_ENSURE")}, {"not": asset("I_CREATE_ENSURE_2")}],
          advance(ready_phase, **{clicks_var: 0}))


def bind_leader_invite_and_fire(
    raw: dict, source_root, resource_dir, *,
    prefix: str, phase_var: str, entry_phase: str, battle_phase: str, exit_phase: str,
    room_type: str = "normal_3",
    notify_only: tuple[str, str] | None = None,
) -> None:
    """Bind GeneralInvite leader flow: check_and_invite, friend OCR invite, slot-ready check, and click_fire."""
    verify_pins(source_root)
    docs = _load_docs(raw, Path(resource_dir))
    if room_type not in ("normal_2", "normal_3", "normal_5", "eternity_sea"):
        raise ValueError(f"Unsupported room_type: {room_type}")

    inv_num = f"{prefix}_invite_number"
    default_inv = f"{prefix}_default_invite"
    find_mode = f"{prefix}_find_mode"
    friend_name = f"{prefix}_friend_1"
    friend_name_2 = f"{prefix}_friend_2"
    wait_param = f"{prefix}_leader_wait_seconds"
    active_friend = f"{prefix}_active_friend"
    invited_cnt = f"{prefix}_invited_count"
    invite_tab = f"{prefix}_invite_tab"
    wait_started = f"{prefix}_ld_wait_started_ms"
    raw["params"].setdefault(inv_num, {"default": 1, "min": 1, "max": 2})
    raw["params"].setdefault(default_inv, {"default": True})
    raw["params"].setdefault(find_mode, {"default": "auto_find", "choices": ["auto_find", "recent_friend"]})
    raw["params"].setdefault(friend_name, {"default": ""})
    raw["params"].setdefault(friend_name_2, {"default": ""})
    raw["params"].setdefault(wait_param, {"default": 120, "min": 0, "max": 3540})
    raw["vars"].setdefault(active_friend, "")
    raw["vars"].setdefault(invited_cnt, 0)
    raw["vars"].setdefault(invite_tab, 0)
    raw["vars"].setdefault(wait_started, -1)

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"{phase_var} == {val!r}")

    def advance(val, **updates):
        return {"set": {phase_var: repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"{prefix}_gi_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns=INVITE_ASSETS):
        return {"res": f"{ns}::{name}"}

    def click(name, ns=INVITE_ASSETS, delay=1000):
        return _click_from(docs, name, ns, delay)

    invite_modal_ph = f"{prefix}_gi_invite_modal"
    fire_ph = f"{prefix}_gi_fire"
    in_room = _in_room_cond()

    # Post-battle default re-invite dialog (check_and_invite)
    state("default_invite_check", entry_phase, [expr(default_inv), asset("I_UI_UNCHECK", "GlobalGame")],
          click("I_UI_UNCHECK", "GlobalGame", 1000))
    state("default_invite_uncheck", entry_phase, [expr(f"not {default_inv}"), asset("I_UI_CHECK", "GlobalGame")],
          click("I_UI_CHECK", "GlobalGame", 1000))
    state("default_invite_confirm", entry_phase, [asset("I_UI_CONFIRM", "GlobalGame")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})

    # Room dead / kicked back to matching or leader wait timeout
    state("room_dead_matching", entry_phase, [asset("I_MATCHING")], advance(exit_phase))
    state("leader_wait_timeout", entry_phase, [
        in_room,
        expr(f"{wait_started} >= 0 and elapsed_ms - {wait_started} >= {wait_param} * 1000"),
    ], advance(exit_phase))

    # Slot-readiness triggers click_fire
    if room_type == "normal_2":
        ready_cond = {"all": [in_room, {"not": asset("I_ADD_2")}]}
        add_btn = "I_ADD_2"
    elif room_type == "normal_3":
        ready_cond = {"any": [
            {"all": [in_room, expr(f"{inv_num} == 1"), {"not": asset("I_ADD_1")}]},
            {"all": [in_room, expr(f"{inv_num} == 2"), {"not": asset("I_ADD_2")}]},
        ]}
        add_btn = "I_ADD_2"
    elif room_type == "normal_5":
        ready_cond = {"any": [
            {"all": [in_room, expr(f"{inv_num} == 1"), {"not": asset("I_ADD_5_1")}]},
            {"all": [in_room, expr(f"{inv_num} == 2"), {"not": asset("I_ADD_5_2")}]},
        ]}
        add_btn = "I_ADD_5_4"
    else:  # eternity_sea
        ready_cond = {"all": [in_room, {"not": asset("I_ADD_SEA")}]}
        add_btn = "I_ADD_SEA"

    if notify_only:
        flag, notified_phase = notify_only
        state("notify_without_fire", entry_phase, [expr(flag), ready_cond], advance(notified_phase))
    state("room_ready_to_fire", entry_phase, [ready_cond],
          advance(fire_ph, **{invited_cnt: 0, wait_started: -1}))

    # Open friend invite modal when named friend provided and slot still empty (supports friend_1 & friend_2)
    state("open_invite_modal_second", entry_phase, [
        in_room, expr(f"{inv_num} == 2 and {invited_cnt} == 1 and {friend_name_2} != ''"), asset(add_btn),
    ], click(add_btn, delay=1200),
       advance(invite_modal_ph, **{active_friend: friend_name_2, invite_tab: 0}))
    state("open_invite_modal", entry_phase, [in_room, expr(f"{friend_name} != ''"), asset(add_btn)],
          click(add_btn, delay=1200),
          advance(invite_modal_ph, **{active_friend: friend_name, invite_tab: 0}))

    # Invite modal: loading wait -> recent_friend direct tab 2 -> exact OCR on O_FRIEND_NAME_1/2 -> auto_find tabs 1..4 -> ensure
    state("wait_load_friend", invite_modal_ph, [asset("I_LOAD_FRIEND")], {"wait": 500})
    state("recent_friend_tab", invite_modal_ph, [
        expr(f"{find_mode} == 'recent_friend' and {invite_tab} < 2"),
        {"not": asset("I_SELECTED")},
        asset("I_FLAG_2_OFF"),
    ], click("I_FLAG_2_OFF", delay=1000), {"set": {invite_tab: 2}})
    for idx in (1, 2):
        ocr_spec = docs[INVITE_ASSETS][f"O_FRIEND_NAME_{idx}"]
        state(f"pick_friend_col{idx}", invite_modal_ph, [
            {"not": asset("I_SELECTED")},
            {"ocr_full": {
                "region": ocr_spec["roi"],
                "keyword_var": active_friend,
                "selection": "unique_equals",
                "evidence": "complete_keyword",
            }},
        ], {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1000})
    state("confirm_invite_send", invite_modal_ph, [asset("I_SELECTED"), asset("I_INVITE_ENSURE")],
          click("I_INVITE_ENSURE", delay=1200),
          {"inc": invited_cnt},
          advance(entry_phase, **{wait_started: "elapsed_ms"}))
    for tab in (1, 2, 3, 4):
        state(f"switch_friend_tab_{tab}", invite_modal_ph, [
            {"not": asset("I_SELECTED")},
            expr(f"{find_mode} == 'auto_find' and {invite_tab} < {tab}"),
            asset(f"I_FLAG_{tab}_OFF"),
        ], click(f"I_FLAG_{tab}_OFF", delay=1000), {"set": {invite_tab: tab}})
    state("invite_not_found_close", invite_modal_ph, [
        {"not": asset("I_SELECTED")},
        asset("I_INVITE_ENSURE"),
    ], click("I_INVITE_ENSURE", delay=1000), advance(entry_phase, **{wait_started: "elapsed_ms"}))

    # Fire battle until leaving room
    state("fire_normal", fire_ph, [in_room, asset("I_FIRE")], click("I_FIRE", delay=1000))
    state("fire_sea", fire_ph, [in_room, asset("I_FIRE_SEA")], click("I_FIRE_SEA", delay=1000))
    state("fire_entered_battle", fire_ph, [{"not": in_room}], advance(battle_phase))


def bind_member_accept_and_wait(
    raw: dict, source_root, resource_dir, *,
    prefix: str, phase_var: str, entry_phase: str, battle_phase: str, exit_phase: str,
) -> None:
    """Bind GeneralInvite member flow: check_then_accept + wait_battle (with leader-fled detection)."""
    verify_pins(source_root)
    docs = _load_docs(raw, Path(resource_dir))

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"{phase_var} == {val!r}")

    def advance(val, **updates):
        return {"set": {phase_var: repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"{prefix}_mem_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns=INVITE_ASSETS):
        return {"res": f"{ns}::{name}"}

    def click(name, ns=INVITE_ASSETS, delay=1000):
        return _click_from(docs, name, ns, delay)

    wait_ph = f"{prefix}_mem_wait"
    in_room = _in_room_cond()
    mem_wait_param = f"{prefix}_member_wait_seconds"
    mem_wait_started = f"{prefix}_mem_wait_started_ms"
    raw["params"].setdefault(mem_wait_param, {"default": 120, "min": 0, "max": 3540})
    raw["vars"].setdefault(mem_wait_started, -1)

    # Accept invitation -> enter room or directly into battle
    state("accept_in_room", entry_phase, [in_room], advance(wait_ph, **{mem_wait_started: "elapsed_ms"}))
    state("accept_instant_battle", entry_phase, [{
        "any": [
            asset("I_EXIT", "Component_GeneralBattle"),
            asset("I_PREPARE_HIGHLIGHT", "Component_GeneralBattle"),
            asset("I_BATTLE_INFO", "Component_GeneralBattle"),
        ]
    }], advance(battle_phase))
    state("accept_default_check", entry_phase, [asset("I_UI_UNCHECK", "GlobalGame")],
          click("I_UI_UNCHECK", "GlobalGame", 1000))
    state("accept_confirm", entry_phase, [asset("I_UI_CONFIRM", "GlobalGame")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("accept_default_btn", entry_phase, [asset("I_I_ACCEPT_DEFAULT")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("accept_btn", entry_phase, [asset("I_I_ACCEPT")],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})

    # Wait in room: leader fled (became leader -> I_FIRE/I_FIRE_SEA visible), wait timeout, or room destroyed -> exit_phase
    state("wait_room_destroyed", wait_ph, [{"any": [asset("I_GI_HOME"), asset("I_GI_EXPLORE")]}], advance(exit_phase))
    state("wait_leader_fled", wait_ph, [{"any": [asset("I_FIRE"), asset("I_FIRE_SEA")]}], advance(exit_phase))
    state("wait_timeout", wait_ph, [
        in_room,
        expr(f"{mem_wait_started} >= 0 and elapsed_ms - {mem_wait_started} >= {mem_wait_param} * 1000"),
    ], advance(exit_phase))
    state("wait_battle_started", wait_ph, [{"not": in_room}], advance(battle_phase))


def bind_room_exit(
    raw: dict, source_root, resource_dir, *,
    prefix: str, phase_var: str, entry_phase: str, done_phase: str,
) -> None:
    """Bind GeneralInvite.exit_room + GeneralRoom.exit_team back to caller's done_phase."""
    verify_pins(source_root)
    docs = _load_docs(raw, Path(resource_dir))

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"{phase_var} == {val!r}")

    def advance(val, **updates):
        return {"set": {phase_var: repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"{prefix}_exit_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns=INVITE_ASSETS):
        return {"res": f"{ns}::{name}"}

    def click(name, ns=INVITE_ASSETS, delay=1000):
        return _click_from(docs, name, ns, delay)

    in_room = _in_room_cond()
    state("confirm_leave", entry_phase, [asset("I_UI_CONFIRM", "GlobalGame")],
          {"click_found": True, "use_match_size": True, "delay": 800, "recheck": True})
    state("leave_room_back", entry_phase, [in_room, asset("I_BACK_YELLOW")], click("I_BACK_YELLOW", delay=800))
    state("leave_room_sea", entry_phase, [in_room, asset("I_BACK_YELLOW_SEA")], click("I_BACK_YELLOW_SEA", delay=800))
    state("leave_team_ui", entry_phase, [asset("I_GR_BACK_YELLOW", ROOM_ASSETS)],
          click("I_GR_BACK_YELLOW", ROOM_ASSETS, 800))
    state("exit_done", entry_phase, [
        {"not": in_room},
        {"not": asset("I_UI_CONFIRM", "GlobalGame")},
        {"not": asset("I_GR_BACK_YELLOW", ROOM_ASSETS)},
    ], advance(done_phase))
