"""Pinned OAS EvoZone, EternitySea, FallenSun, and Orochi zone-farming workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import BATTLE_WAIT, BATTLE_WAIT_PIN, bind_courtyard_buffs, compile_general_battle
from .oas_boss_and_zones import TRUE_OROCHI_PINS
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


EVO_ZONE_ENTRY = "tasks/EvoZone/script_task.py"
EVO_ZONE_PINS = {
    EVO_ZONE_ENTRY: "533e5cbb81ea6c6f5fa7e6f1f1800a7bcd9e30e21ee706eb5e71c186b2207e2e",
    "tasks/EvoZone/config.py": "8b67a88cc15a9f13cb48331cb144720d9cb48524195fb395133cf1b2d6a4dee4",
    "tasks/EvoZone/assets.py": "66e4b8b43c05202aee304db81dc465e5b8a2bc8394cbacd62b8075d9eacb5267",
}

ETERNITY_SEA_ENTRY = "tasks/EternitySea/script_task.py"
ETERNITY_SEA_PINS = {
    ETERNITY_SEA_ENTRY: "5c6767d51a24680f0e8317e2713efa9f6fee65f7bf02b8be6161d29bcba889db",
    "tasks/EternitySea/config.py": "bb5705da5999dc3c4e6dc6e02b88436ce8a266a078d30448ca8183d20fac72ee",
    "tasks/EternitySea/assets.py": "4069756633fc0ad85db4b5581bee7cee4eb55d5edabf691643c1c77ad852bfcb",
}

FALLEN_SUN_ENTRY = "tasks/FallenSun/script_task.py"
FALLEN_SUN_PINS = {
    FALLEN_SUN_ENTRY: "f78a02abaf242e72449c9f6b674a967336c045ff74debcc80e45d21e4e10e435",
    "tasks/FallenSun/config.py": "977425e2d0b1c13f2446f50278329bf5c06443a2f8082c451d5d1034fc7f4205",
    "tasks/FallenSun/assets.py": "d68bd824769f5261f9044ff7875f0641380c0a9633e5793aca1a02871dbb7e39",
}

OROCHI_ENTRY = "tasks/Orochi/script_task.py"
OROCHI_PINS = {
    OROCHI_ENTRY: "8f590a7d1fb83ccc42cb9eb40ce7c9c3ef9c5c35074c5c5abd5a8d2b268b35da",
    "tasks/Orochi/config.py": "c273b85aacac94ce321978caa7fa3b6aa7682c94ab98ab4b8bd4bce60bb15aaf",
    "tasks/Orochi/assets.py": "0d0ca408d973fa2b46987e38a635b1df067bb59432cabd34373483d7ebc5050b",
    "tasks/Orochi/page.py": "e67ec0f6f2819e6a06289f60613ed95dec3328955a85186a752d3714c6a9dd43",
}

USER_STATUSES = ("alone", "leader", "member", "wild")
LIST_PINS = {"module/atom/list.py": "ae518b520f26493cc26ef0bad9567c09e92e451c27ef283aa65ef7c9739741b0"}
KIRIN_TYPES = {
    "火麒麟": "I_FIRE_KIRIN",
    "风麒麟": "I_WIND_KIRIN",
    "水麒麟": "I_WATER_KIRIN",
    "雷麒麟": "I_LIGHTNING_KIRIN",
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


def _layer_list(source, task, converted, layers):
    path = source / "tasks" / task / "assets.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    rule = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == "L_LAYER_LIST" for target in node.targets))
    args = {arg.arg: ast.literal_eval(arg.value) for arg in rule.keywords}
    labels = args["array"]
    if (args["direction"] != "vertical" or args["mode"] != "ocr" or len(labels) != len(layers)
            or [entry["itemName"] for entry in converted["items"]] != labels
            or tuple(converted["roi"]) != args["roi_back"]):
        raise ValueError(f"{task} layer list disagrees with the pinned asset")
    return args["roi_back"], args["size"], [list(dict.fromkeys([layer, short])) for layer, short in zip(layers, labels)]


def _bind_layer_list(raw, state, advance, *, prefix, panel, roi, size, labels, confirm_phase):
    direction, count, started = (f"{prefix}_layer_{key}" for key in ("direction", "swipes", "started"))
    raw["vars"].update({direction: 2, count: 0, started: -1})
    state("layer_enter", "layer_probe", [panel], advance("layer_find", **{started: "elapsed_ms", count: 0}))
    state("layer_limit", "layer_find", [{"expr": f"{count} >= 10 or elapsed_ms - {started} >= 20000"}],
          {"fail": "未在层级列表内识别到指定层级"})
    x, y, width, height = roi
    row_width, row_height = size
    # Keep the one-row source gesture inside the list's XYWH bounds.
    center_x, center_y = x + width // 2, y + height // 2
    low_x, high_x = center_x + (-row_width // 4), center_x + row_width // 4
    top_y, bottom_y = center_y - row_height // 2, center_y + row_height // 2
    top, bottom = [low_x, top_y, high_x, top_y], [low_x, bottom_y, high_x, bottom_y]
    for index, group in enumerate(labels):
        target = group[0]
        match = {"ordered_list": {"region": list(roi), "labels": labels, "target": target, "direction_var": direction}}
        active = [panel, {"expr": f"{prefix}_layer == {target!r}"}, match]
        state(f"layer_click_{index}", "layer_find", [*active, {"expr": f"{direction} == 0"}],
              {"click_found": True, "offset": [0, 0, 0, 0], "delay": 500, "recheck": True},
              advance(confirm_phase, **{started: "elapsed_ms"}))
        for name, value, start, end in (("earlier", -1, top, bottom), ("later", 1, bottom, top)):
            state(f"layer_{name}_{index}", "layer_find", [*active, {"expr": f"{direction} == {value}"}],
                  {"swipe": {"from": start, "to": end}, "delay": 0, "recheck": True},
                  {"wait_random": [800, 1300]}, {"inc": count})


def _bind_wailing_overlays(raw):
    """Handle the two Wailing overlays identified in saved battle frames."""
    def expr(value):
        return {"expr": value}

    def guard(phase):
        return expr(f"or_phase == {phase!r} and or_layer == '悲鸣' and or_user_status == 'alone'")

    def title(region, text):
        return {"ocr_single": {"region": region, "equals": text, "score": .6}}

    def insert_before(target, steps):
        position = next(i for i, step in enumerate(raw["states"]) if step["id"] == target)
        raw["states"][position:position] = steps

    raw["vars"].update(or_wailing_info_dismissed=False, or_wailing_unlock_dismissed=False,
                       or_wailing_info_clicked_ms=-1)
    ready = {"res": "Component_GeneralBattle::I_PREPARE_HIGHLIGHT"}
    info = {"all": [guard("battle"), expr("or_battle_phase == 'prepare' or or_battle_phase == 'prepare_after_setup'"),
                    ready, title([271, 280, 205, 51], "巫女大蛇·现世")]}
    challenge_started = next(step for step in raw["states"] if step["id"] == "or_battle_started")
    challenge_started["do"][0]["set"].update(or_wailing_info_dismissed=False, or_wailing_info_clicked_ms=-1)
    insert_before("or_battle_prepare_timeout", [
        {"id": "or_wailing_info_dismiss", "when": {"all": [expr("not or_wailing_info_dismissed"), info]},
         "do": [{"click": [1146, 561, 1207, 612], "delay": 0, "recheck": True},
                {"set": {"or_wailing_info_dismissed": True, "or_wailing_info_clicked_ms": "elapsed_ms",
                         "or_battle_prep_started_ms": "elapsed_ms", "or_battle_phase": "'prepare'"}}]},
        {"id": "or_wailing_info_timeout",
         "when": {"all": [expr("or_wailing_info_dismissed and elapsed_ms - or_wailing_info_clicked_ms >= 2000"), info]},
         "do": [{"fail": "悲鸣说明层未消失"}]},
        {"id": "or_wailing_info_wait", "when": info, "do": [{"wait": 0}]},
    ])

    unlock = {"all": [guard("cycle"), expr("or_wins > 0"),
                      title([395, 85, 500, 95], "悲鸣挑战开启")]}
    insert_before("or_pet_present_dismiss", [
        {"id": "or_wailing_unlock_dismiss",
         "when": {"all": [expr("not or_wailing_unlock_dismissed"), unlock]},
         "do": [{"click": [564, 108, 716, 150], "delay": 0, "recheck": True},
                {"set": {"or_wailing_unlock_dismissed": True}}]},
        {"id": "or_wailing_unlock_stuck", "when": unlock, "do": [{"wait": 0}]},
    ])


def _compile_zone_farm(
    source_root, resource_dir, *, task_name: str, wf_name: str, title: str,
    prefix: str, entry: str, pins: dict[str, str], nav_page: str,
    enter_icon: str | None, enter_map: dict[str, str] | None,
    lock_icon: str, unlock_icon: str, fire_icon: str,
    default_count: int, layers: tuple[str, ...], default_layer: str,
    buff_method: str | None = None, require_lock_alone: bool = False,
    check_true_orochi: bool = False, calibrations=None,
):
    source, resources = Path(source_root), Path(resource_dir)
    strategy_pins = {BATTLE_WAIT: BATTLE_WAIT_PIN} if task_name in ("EvoZone", "FallenSun") else {}
    _verify_pins(source, {**pins, **LIST_PINS, **strategy_pins}, task_name)
    nav = compile_navigation_family(
        source, resources, prefix=f"{prefix}_nav", destination=nav_page,
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix=f"{prefix}_battle",
                                    strategy_wait=bool(strategy_pins))
    if not battle["guarded_executable"]:
        raise ValueError(f"{task_name} could not bind GeneralBattle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name=wf_name, title=title, loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3700
    bind_schedule(source, raw)
    raw["params"].update({
        f"{prefix}_user_status": {"default": "alone", "choices": list(USER_STATUSES)},
        f"{prefix}_layer": {"default": default_layer, "choices": list(layers)},
        f"{prefix}_limit_count": {"default": default_count, "min": 0, "max": 999},
        f"{prefix}_limit_seconds": {"default": 1800, "min": 0, "max": 7200},
        f"{prefix}_next_delay_s": {"default": 0, "min": 0, "max": 604800},
    })
    if enter_map:
        raw["params"][f"{prefix}_kirin_type"] = {"default": "雷麒麟", "choices": list(enter_map)}
    if buff_method:
        raw["params"][f"{prefix}_buff_enable"] = {"default": False}
    if check_true_orochi:
        raw["params"].update(or_check_true_orochi={"default": False},
                             or_true_orochi_failure_seconds={"default": 86400, "min": 0, "max": 3155760000})
    if set(raw["params"]) & set(body["params"]):
        raise ValueError(f"{task_name} navigation and battle configuration overlap")
    raw["params"].update(body["params"])

    ph_var = f"{prefix}_phase"
    raw["vars"].update(
        body["vars"],
        **{
            ph_var: "entry",
            f"{prefix}_attempts": 0,
            f"{prefix}_wins": 0,
            f"{prefix}_start_taps": 0,
            f"{prefix}_main_arrived": 0,
            f"{prefix}_target_delay_s": 0,
            f"{prefix}_observed_ms": 0,
            f"{prefix}_exit_reason": "",
        },
    )
    extra_res = [
        f"upstream/oas/{task_name}.yaml",
        "upstream/oas/Component_GeneralBattle.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]
    if check_true_orochi:
        extra_res.append("upstream/oas/TrueOrochi.yaml")
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + extra_res))
    doc_names = [task_name, "Component_GeneralBattle", "Component_GeneralInvite", "GlobalGame"]
    if check_true_orochi:
        doc_names.append("TrueOrochi")
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in doc_names}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"{ph_var} == {val!r}")

    def advance(val, **updates):
        return {"set": {ph_var: repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"{prefix}_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns=task_name):
        return {"res": f"{ns}::{name}"}

    def click(name, ns=task_name, delay=1000):
        return _click_from(docs, name, ns, delay)

    state("wild_unsupported", "entry", [expr(f"{prefix}_user_status == 'wild'")],
          {"fail": f"{title}野队模式(wild)在上游未实现"})
    if require_lock_alone:
        state("alone_requires_lock", "entry", [expr(f"{prefix}_user_status == 'alone' and not lock_team_enable")],
              {"fail": f"{title}单人模式仅支持锁定阵容(lock_team_enable=True)"})

    buff_calls = []
    if buff_method:
        for leg, opening, resume in (("before", True, "route_entry"), ("after", False, "finished")):
            buff_calls.append(bind_courtyard_buffs(raw, source, resources, prefix=f"{prefix}_buff_{leg}",
                phase_var=ph_var, entry_phase=f"buff_{leg}", resume=resume, operations=[(buff_method, None)],
                enable_param=f"{prefix}_buff_enable", opening=opening,
                skip_in_battle=task_name == "Orochi" and opening))
    after_presets = "buff_before" if buff_method else "route_entry"
    if task_name == "EternitySea":
        bind_task_presets(raw, source, resources, prefix=prefix, resume="team2_presets", category=prefix)
        bind_task_presets(raw, source, resources, prefix=f"{prefix}2", phase_var=ph_var,
                          phase_prefix="team2_", entry_phase="team2_presets", resume=after_presets, category=prefix)
    else:
        bind_task_presets(raw, source, resources, prefix=prefix, resume=after_presets, category=prefix)
    state("route_member", "route_entry", [expr(f"{prefix}_user_status == 'member'")], advance("member_accept"))
    state("route_nav", "route_entry", [expr(f"{prefix}_user_status != 'member'")], advance("navigate"))

    arrived = next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("open_zone" if (enter_icon or enter_map) else "layer_probe")]
    next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_drive")["when"] = phase("navigate")

    # Enter zone subpage when needed
    if enter_map:
        state("zone_opened", "open_zone", [asset("I_FORM_TEAM")], advance("layer_probe"))
        for k_label, icon in enter_map.items():
            state(f"enter_{icon.lower()}", "open_zone",
                  [expr(f"{prefix}_kirin_type == {k_label!r}"), asset(icon)],
                  click(icon, task_name, 1000))
    elif enter_icon:
        state("zone_opened", "open_zone", [asset("I_FORM_TEAM")], advance("layer_probe"))
        state("enter_zone_icon", "open_zone", [asset(enter_icon)], click(enter_icon, task_name, 1000))

    # Lock / unlock check
    locked, unlocked = asset(lock_icon), asset(unlock_icon)
    fire = asset(fire_icon)
    challenge_ready = fire
    fire_click = click(fire_icon, task_name, 1000)
    confirmation_phase = "check_lock"
    roi, size, labels = _layer_list(source, task_name, docs[task_name]["LIST_LAYER_LIST"], layers)
    if task_name == "Orochi":
        confirmation_phase = "verify_layer"
        layouts = {"悲鸣": "I_OROCHI_CHECK_11", "神罚": "I_OROCHI_CHECK_12", "虚无": "I_OROCHI_CHECK_13"}
        ordinary = " and ".join(f"{prefix}_layer != {label!r}" for label in layouts)
        expected = {label: [expr(f"{prefix}_layer == {label!r}"), asset(marker)] for label, marker in layouts.items()}
        selected_ordinary = {"all": [asset("I_OROCHI_CHECK_10"), {"any": [
            {"all": [expr(f"{prefix}_layer == {label!r}"), {"ordered_list": {
                "region": list(roi), "labels": labels, "target": label, "direction_var": f"{prefix}_layer_direction",
                "selected_row": {"x": 195, "width": 28, "height": 20, "rgb": [130, 45, 26],
                                 "tolerance": 32, "coverage": .65},
            }}]} for label in layers if label not in layouts
        ]}]}
        state("verify_ordinary_layout", "verify_layer", [selected_ordinary],
              advance("check_lock"))
        for index, guards in enumerate(expected.values(), 11):
            state(f"verify_layout_{index}", "verify_layer", guards, advance("check_lock"))
        state("verify_layer_timeout", "verify_layer", [expr("elapsed_ms - or_layer_started >= 6000")],
              {"fail": "未识别选中层级对应的大蛇界面"})
        region = [f"{prefix}_wailing_fire_{axis}" for axis in ("x", "y", "w", "h")]
        raw["vars"].update(zip(region, (995, 549, 227, 143)))
        base_fire = fire
        fire = {"any": [
            {"all": [expr(ordinary), base_fire]},
            {"all": [*expected["悲鸣"], {"any": [{**base_fire, "region_vars": region}, base_fire]}]},
            *({"all": [*expected[label], base_fire]} for label in ("神罚", "虚无")),
        ]}
        challenge_ready = {"all": [{"any": [selected_ordinary, *({"all": guards} for guards in expected.values())]}, fire]}
        fire_click = {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}
    _bind_layer_list(raw, state, advance, prefix=prefix, roi=roi, size=size, labels=labels,
                     panel={"any": [locked, unlocked, fire]}, confirm_phase=confirmation_phase)
    lock_ok = {"any": [
        {"all": [expr("lock_team_enable"), locked]},
        {"all": [expr("not lock_team_enable"), unlocked]},
    ]}
    state("lock_ready_alone", "check_lock", [expr(f"{prefix}_user_status == 'alone'"), lock_ok], advance("cycle"))
    state("lock_ready_leader", "check_lock", [expr(f"{prefix}_user_status == 'leader'"), lock_ok],
          advance("leader_open_team"))
    state("lock_turn_on", "check_lock", [expr("lock_team_enable"), unlocked], click(unlock_icon, task_name, 1000))
    state("lock_turn_off", "check_lock", [expr("not lock_team_enable"), locked], click(lock_icon, task_name, 1000))

    # Leader & Member shared GeneralRoom / GeneralInvite integration
    state("leader_team_opened", "leader_open_team", [asset("I_CREATE_ROOM", "Component_GeneralRoom")],
          advance("room_create"))
    state("leader_click_form_team", "leader_open_team", [asset("I_FORM_TEAM")],
          click("I_FORM_TEAM", task_name, 1000))
    bind_room_create(raw, source, resources, prefix=prefix, phase_var=ph_var,
                     entry_phase="room_create", ready_phase="leader_invite", fail_phase="room_create_fail")
    state("room_create_failed", "room_create_fail", [],
          {"fail": f"{title}创建组队房间失败(可能缺少挑战券或体力)"})

    state("leader_pet_present", "leader_invite", [asset("I_PET_PRESENT")],
          click("C_WIN_3", "Component_GeneralBattle", 1000))
    state("leader_count_stop", "leader_invite", [expr(f"{prefix}_attempts >= {prefix}_limit_count")],
          advance("room_exit", **{f"{prefix}_exit_reason": "'count'", f"{prefix}_main_arrived": 0}))
    state("leader_time_stop", "leader_invite", [expr(f"elapsed_ms >= {prefix}_limit_seconds * 1000")],
          advance("room_exit", **{f"{prefix}_exit_reason": "'time'", f"{prefix}_main_arrived": 0}))
    bind_leader_invite_and_fire(
        raw, source, resources, prefix=prefix, phase_var=ph_var,
        entry_phase="leader_invite", battle_phase="team_battle_init", exit_phase="room_exit",
        room_type="eternity_sea" if task_name == "EternitySea" else "normal_3",
    )
    state("member_pet_present", "member_accept", [asset("I_PET_PRESENT")],
          click("C_WIN_3", "Component_GeneralBattle", 1000))
    state("member_count_stop", "member_accept", [expr(f"{prefix}_attempts >= {prefix}_limit_count")],
          advance("room_exit", **{f"{prefix}_exit_reason": "'count'", f"{prefix}_main_arrived": 0}))
    state("member_time_stop", "member_accept", [expr(f"elapsed_ms >= {prefix}_limit_seconds * 1000")],
          advance("room_exit", **{f"{prefix}_exit_reason": "'time'", f"{prefix}_main_arrived": 0}))
    bind_member_accept_and_wait(
        raw, source, resources, prefix=prefix, phase_var=ph_var,
        entry_phase="member_accept", battle_phase="team_battle_init", exit_phase="room_exit",
    )
    bind_room_exit(
        raw, source, resources, prefix=prefix, phase_var=ph_var,
        entry_phase="room_exit", done_phase="post_check" if check_true_orochi else "exit_main",
    )

    # Solo farming cycle
    state("pet_present_dismiss", "cycle", [asset("I_PET_PRESENT")],
          click("C_WIN_3", "Component_GeneralBattle", 1000))
    state("count_stop", "cycle", [fire, expr(f"{prefix}_attempts >= {prefix}_limit_count")],
          advance("post_check" if check_true_orochi else "exit_main",
                  **{f"{prefix}_exit_reason": "'count'", f"{prefix}_main_arrived": 0}))
    state("time_stop", "cycle", [fire, expr(f"elapsed_ms >= {prefix}_limit_seconds * 1000")],
          advance("post_check" if check_true_orochi else "exit_main",
                  **{f"{prefix}_exit_reason": "'time'", f"{prefix}_main_arrived": 0}))
    state("start_challenge", "cycle", [challenge_ready],
          fire_click,
          advance("begin_battle", **{f"{prefix}_start_taps": 1}))
    state("retry_challenge", "begin_battle", [challenge_ready, expr(f"{prefix}_start_taps < 3")],
          fire_click, {"inc": f"{prefix}_start_taps"})
    state("challenge_stuck", "begin_battle", [fire],
          {"fail": f"挑战后未离开{title}入口界面"})

    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    reset[outputs["current_count"]] = f"{prefix}_attempts"
    state("battle_started", "begin_battle", [{"not": fire}], {"set": reset}, advance("battle"))
    state("team_battle_start", "team_battle_init", [], {"set": reset}, advance("battle"))

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("after_battle", **{
                f"{prefix}_attempts": outputs["current_count"],
                f"{prefix}_wins": f"{prefix}_wins + {outputs['win']}",
            })]
        raw["states"].append(step)

    state("after_battle_alone", "after_battle", [expr(f"{prefix}_user_status == 'alone'")], advance("cycle"))
    state("after_battle_leader", "after_battle", [expr(f"{prefix}_user_status == 'leader'")], advance("leader_invite"))
    state("after_battle_member", "after_battle", [expr(f"{prefix}_user_status == 'member'")], advance("member_accept"))

    if check_true_orochi:
        orochi_page = raw["navigation"]["pages"]["page_orochi"]["when"]
        check = expr("or_check_true_orochi")
        found = asset("I_FIND_TS", "TrueOrochi")
        leave = advance("exit_main", or_main_arrived=0)
        state("post_true_orochi_discovered", "post_check", [check, orochi_page, found],
              {"oas_wake": {"task": "TrueOrochi", "failure_seconds_param": "or_true_orochi_failure_seconds"}},
              leave)
        state("post_true_orochi_absent", "post_check", [check, orochi_page, {"not": found}], leave)
        state("post_true_orochi_navigate", "post_check", [check, {"not": orochi_page}],
              {"navigate": {"destination": "page_orochi", "done_var": "or_check_page_arrived"}})
        state("post_check_clear", "post_check", [{"not": check}], leave)
        raw["vars"]["or_check_page_arrived"] = 0

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("returned_main", "exit_main", [court, expr(f"{prefix}_main_arrived == 1")],
          advance("buff_after" if buff_method else "finished"))
    state("finished_target_prep", "finished", [court, expr(f"{prefix}_next_delay_s > 0")],
          advance("stop_target", **{
              f"{prefix}_target_delay_s": f"{prefix}_next_delay_s",
              f"{prefix}_observed_ms": "elapsed_ms",
          }))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": f"{title}已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": task_name,
                "delay_seconds_var": f"{prefix}_target_delay_s",
                "observed_ms_var": f"{prefix}_observed_ms",
            },
            "evidence": {"scope": f"{prefix}_target_schedule"},
        }
    })
    state("finished", "finished", [court], {
        "stop": {
            "reason": f"{title}已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": task_name,
            "evidence": {"scope": f"{prefix}_native_path"},
        }
    })
    if task_name == "EternitySea":
        state("exit_confirm", "exit_main", [{"not": court}, asset("I_UI_CONFIRM", "GlobalGame")],
              click("I_UI_CONFIRM", "GlobalGame", 1000))
        state("exit_back_yellow_sea", "exit_main", [{"not": court}, asset("I_BACK_YELLOW_SEA", "Component_GeneralInvite")],
              click("I_BACK_YELLOW_SEA", "Component_GeneralInvite", 1000))
        state("exit_back_bottom", "exit_main", [{"not": court}, asset("I_BACK_BOTTOM")],
              click("I_BACK_BOTTOM", task_name, 1000))
    if task_name == "FallenSun":
        state("exit_back_blue", "exit_main", [{"not": court}, asset("I_UI_BACK_BLUE", "GlobalGame")],
              click("I_UI_BACK_BLUE", "GlobalGame", 1000))
    state("exit_back_yellow", "exit_main", [{"not": court}, asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", "GlobalGame", 1000))
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": f"{prefix}_main_arrived"}})

    raw[f"oas_{prefix}_contract"] = {
        "source": entry,
        "source_pins": {**pins, **SCHEDULE_PINS, **SOUL_PINS, **ROOM_INVITE_PINS, **LIST_PINS, **strategy_pins},
        "battle_wait_dispatch": contract["dispatch"],
        "layer_list": {"source_asset": f"{task_name}::LIST_LAYER_LIST", "labels": labels,
                       "recognition": "OCR ordered viewport, short and full labels, fresh exact location before input",
                       "swipe_limit": 10},
        "buff_calls": buff_calls,
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"],
            *(obligation for invocation in buff_calls for obligation in invocation["source_obligations"]), {
            "id": f"{prefix}_remaining_zone_branches",
            "blocking": True,
            "requirement": f"Verify selected layer and ordinary paths on live {task_name} frames, "
                           "and bind remaining task branches such as multi-tab friend scrolling" +
                           (" and verify courtyard buff setup and cleanup on live frames" if buff_method else ""),
        }],
    }
    if task_name == "Orochi":
        _bind_wailing_overlays(raw)
        raw[f"oas_{prefix}_contract"]["wailing_layout"] = {
            "confirmation": "Orochi::I_OROCHI_CHECK_11",
            "shifted_challenge_search_region": [995, 549, 227, 143],
            "source": "Live frames before and after Wailing first clear. Search the original challenge template "
                      "in the shifted panel or its default region.",
            "overlays": "Recognize the exact preparation information and first-clear titles. "
                        "Dismiss each at most once and wait for fresh evidence before proceeding.",
        }
        raw[f"oas_{prefix}_contract"]["true_orochi_schedule"] = {
            "source_lines": [62, 67], "asset": "TrueOrochi::I_FIND_TS",
            "schedule": "earlier of source start plus failure interval and observation time, with server disabled",
        }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_evo_zone_candidate(source_root, resource_dir, *, calibrations=None):
    return _compile_zone_farm(
        source_root, resource_dir, task_name="EvoZone", wf_name="oas_evo_zone_natively_staged",
        title="觉醒副本", prefix="ez", entry=EVO_ZONE_ENTRY, pins=EVO_ZONE_PINS,
        nav_page="page_awake_zones", enter_icon=None, enter_map=KIRIN_TYPES,
        lock_icon="I_EVOZONE_LOCK", unlock_icon="I_EVOZONE_UNLOCK", fire_icon="I_EVOZONE_FIRE",
        default_count=30,
        layers=("壹层", "贰层", "叁层", "肆层", "伍层", "陆层", "柒层", "捌层", "玖层", "拾层"),
        default_layer="拾层", buff_method="awake", calibrations=calibrations,
    )


def compile_eternity_sea_candidate(source_root, resource_dir, *, calibrations=None):
    return _compile_zone_farm(
        source_root, resource_dir, task_name="EternitySea", wf_name="oas_eternity_sea_natively_staged",
        title="永生之海", prefix="es", entry=ETERNITY_SEA_ENTRY, pins=ETERNITY_SEA_PINS,
        nav_page="page_soul_zones", enter_icon="I_ETERNITY_SEA", enter_map=None,
        lock_icon="I_NEWETERNITYSEA_LOCK", unlock_icon="I_ETERNITYSEA_UNLOCK",
        fire_icon="I_ETERNITY_SEA_FIRE", default_count=30,
        layers=("壹层", "贰层", "叁层", "肆层"), default_layer="肆层",
        require_lock_alone=True, calibrations=calibrations,
    )


def compile_fallen_sun_candidate(source_root, resource_dir, *, calibrations=None):
    return _compile_zone_farm(
        source_root, resource_dir, task_name="FallenSun", wf_name="oas_fallen_sun_natively_staged",
        title="日轮之陨", prefix="fs", entry=FALLEN_SUN_ENTRY, pins=FALLEN_SUN_PINS,
        nav_page="page_soul_zones", enter_icon="I_FALLEN_SUN", enter_map=None,
        lock_icon="I_FALLEN_SUN_LOCK", unlock_icon="I_FALLEN_SUN_UNLOCK",
        fire_icon="I_FALLEN_SUN_FIRE", default_count=50,
        layers=("壹层", "贰层", "叁层", "日蚀"), default_layer="叁层",
        calibrations=calibrations,
    )


def compile_orochi_candidate(source_root, resource_dir, *, calibrations=None):
    return _compile_zone_farm(
        source_root, resource_dir, task_name="Orochi", wf_name="oas_orochi_natively_staged",
        title="八岐大蛇", prefix="or", entry=OROCHI_ENTRY, pins={**OROCHI_PINS, **TRUE_OROCHI_PINS},
        nav_page="page_orochi", enter_icon=None, enter_map=None,
        lock_icon="I_OROCHI_LOCK", unlock_icon="I_OROCHI_UNLOCK",
        fire_icon="I_OROCHI_FIRE", default_count=30,
        layers=("壹层", "贰层", "叁层", "肆层", "伍层", "陆层", "柒层", "捌层", "玖层", "拾层", "悲鸣", "神罚", "虚无"),
        default_layer="悲鸣", buff_method="soul", check_true_orochi=True, calibrations=calibrations,
    )
