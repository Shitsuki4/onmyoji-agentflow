"""Pinned OAS ExperienceYoukai, GoldYoukai, Nian, and Tako team-room workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import bind_courtyard_buffs, compile_general_battle
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


ROOM_INVITE_PINS = {
    "tasks/Component/GeneralRoom/general_room.py":
        "66637fef102652be58145df4380e20b6d81d12801096d6ea336914aac2aeedc8",
    "tasks/Component/GeneralRoom/assets.py":
        "166e7706cacacdd3baf88bafda6455f5f574032b40ac5a85ab019b041344d87f",
    "tasks/Component/GeneralInvite/general_invite.py":
        "7f5ea9bd8690a184a26e132e8cf0580409589445859d5d14b8968d2a82eb5407",
    "tasks/Component/GeneralInvite/assets.py":
        "5fcda5ac864dcc20bcb1f4055c8df2174e10727325c2035aeb8679ea3f9ec1c8",
}

EXP_YOUKAI_ENTRY = "tasks/ExperienceYoukai/script_task.py"
EXP_YOUKAI_PINS = {
    EXP_YOUKAI_ENTRY: "ca48f6674a194bea6d9caa0cd199c0894caf290281dad0a145e122a723d7e2a4",
    "tasks/ExperienceYoukai/config.py": "56033565d08d27509af2e314b84238f81845a36667e458d088c85c4884f12865",
    "tasks/ExperienceYoukai/assets.py": "071682c5a37c7d34579bbe0f51e64360b6003c9d990cb2378eceeb4c526f75ef",
    **ROOM_INVITE_PINS,
}

GOLD_YOUKAI_ENTRY = "tasks/GoldYoukai/script_task.py"
GOLD_YOUKAI_PINS = {
    GOLD_YOUKAI_ENTRY: "86a16aaaeb4f28651b20af069f18bd2a009dbd69429d4f4f8b91ff7ef2a9cbd1",
    "tasks/GoldYoukai/config.py": "2d462f8d388ee095c43f65e17545229b7b3d1a896bf34728ecc246a8eedad397",
    "tasks/GoldYoukai/assets.py": "d3e3403badc0b201111cf266dca9543cd0a4919199a9e57e18580aa869484be1",
    **ROOM_INVITE_PINS,
}

NIAN_ENTRY = "tasks/Nian/script_task.py"
NIAN_PINS = {
    NIAN_ENTRY: "83e5f575c7be4337f1e33e77b074e36d946f85513a72c5b5f9f589dc5b25bd90",
    "tasks/Nian/config.py": "e316e949dc22e5a56c011ec137523e3e66a41a5dc608acce4bcf49505f8f5e62",
    "tasks/Nian/assets.py": "1e1058082fac38cc06d582bf2e7e3aaf527fce0c10216974f7ab676f3651f2b1",
    **ROOM_INVITE_PINS,
}

TAKO_ENTRY = "tasks/Tako/script_task.py"
TAKO_PINS = {
    TAKO_ENTRY: "991ad974df835f7b3cfa638ff20478a5aece997b354eda90f145aea01af945c3",
    "tasks/Tako/config.py": "c74835537c49a4d054d94048a634f5ec5c4002ce967f56cc19622dd0a140a9a9",
    "tasks/Tako/assets.py": "1ba6c4305fac8f5224533d8804525ea192209cfeb1c05d88014ffa68be4735fc",
    **ROOM_INVITE_PINS,
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


def _compile_public_room_youkai(
    source_root, resource_dir, *, task_name: str, wf_name: str, title: str,
    prefix: str, entry: str, pins: dict[str, str], zone_label: str,
    win_asset: tuple[str, str] | None, max_runs: int, wait_s: int,
    slot_asset: str, buff_params: tuple[str, ...], buff_ops: list[tuple[str, str]],
    buff_enable_expr: str, exit_on_wait_timeout: bool,
    weekend_zone_label: str | None = None, calibrations=None,
):
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, pins, task_name)
    nav = compile_navigation_family(
        source, resources, prefix=f"{prefix}_nav", destination="page_team",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix=f"{prefix}_battle")
    if not battle["guarded_executable"]:
        raise ValueError(f"{task_name} could not bind GeneralBattle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name=wf_name, title=title, loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1800
    bind_schedule(source, raw)
    raw["params"].update({p: {"default": False} for p in buff_params})
    raw["params"].update({
        f"{prefix}_max_runs": {"default": max_runs, "min": 1, "max": 10},
        f"{prefix}_room_wait_seconds": {"default": wait_s, "min": 1, "max": 300},
        f"{prefix}_limit_seconds": {"default": 0, "min": 0, "max": 3600},
        f"{prefix}_next_delay_s": {"default": 0, "min": 0, "max": 604800},
    })
    if weekend_zone_label:
        raw["params"][f"{prefix}_is_weekend"] = {"default": False}
    if set(raw["params"]) & set(body["params"]):
        raise ValueError(f"{task_name} navigation and battle configuration overlap")
    raw["params"].update(body["params"])

    ph_var = f"{prefix}_phase"
    raw["vars"].update(
        body["vars"],
        **{
            ph_var: "entry",
            f"{prefix}_runs": 0,
            f"{prefix}_wins": 0,
            f"{prefix}_create_taps": 0,
            f"{prefix}_wait_start": 0,
            f"{prefix}_team_arrived": 0,
            f"{prefix}_main_arrived": 0,
            f"{prefix}_target_delay_s": 0,
            f"{prefix}_observed_ms": 0,
            f"{prefix}_exit_reason": "",
        },
    )
    extra_res = [
        "upstream/oas/Component_GeneralRoom.yaml",
        "upstream/oas/Component_GeneralInvite.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]
    if win_asset is not None:
        extra_res.append(f"upstream/oas/{win_asset[0]}.yaml")
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + extra_res))
    doc_names = ["Component_GeneralRoom", "Component_GeneralInvite", "GlobalGame"]
    if win_asset is not None:
        doc_names.append(win_asset[0])
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in doc_names}
    zone_roi = docs["Component_GeneralRoom"]["O_GR_ZONES_NAME"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"{ph_var} == {val!r}")

    def advance(val, **updates):
        return {"set": {ph_var: repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"{prefix}_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns):
        return {"res": f"{ns}::{name}"}

    def click(name, ns, delay=1000):
        return _click_from(docs, name, ns, delay)

    # SwitchSoul + Courtyard GeneralBuff open/close binding
    bind_task_presets(raw, source, resources, prefix=prefix, resume="buff_before", category=prefix)
    buff_calls = [
        bind_courtyard_buffs(
            raw, source, resources, prefix=f"{prefix}_buff_{leg}", phase_var=ph_var,
            entry_phase=f"buff_{leg}", resume=resume, operations=buff_ops,
            enable_param=buff_enable_expr, opening=opening,
        )
        for leg, opening, resume in (("before", True, "goto_team"), ("after", False, "finished"))
    ]

    # Disable unused initial nav
    next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_returned")["when"]["all"].append(phase("unused_nav"))
    next(step for step in raw["states"] if step["id"] == f"{prefix}_nav_drive")["when"] = phase("unused_nav")

    team_page = raw["navigation"]["pages"]["page_team"]["when"]
    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("team_time_limit", "goto_team",
          [expr(f"{prefix}_limit_seconds > 0 and elapsed_ms >= {prefix}_limit_seconds * 1000")],
          advance("exit_main", **{f"{prefix}_main_arrived": 0, f"{prefix}_exit_reason": "'time_limit'"}))
    state("team_done_limit", "goto_team", [expr(f"{prefix}_runs >= {prefix}_max_runs")],
          advance("exit_main", **{f"{prefix}_main_arrived": 0, f"{prefix}_exit_reason": "'count'"}))
    state("team_arrived", "goto_team", [team_page, expr(f"{prefix}_team_arrived == 1")],
          advance("select_zone", **{f"{prefix}_create_taps": 0}))
    state("team_drive", "goto_team", [],
          {"navigate": {"destination": "page_team", "done_var": f"{prefix}_team_arrived"}})

    # Select zone via OCR in GeneralRoom
    if weekend_zone_label:
        state("zone_pick_weekend", "select_zone",
              [expr(f"{prefix}_is_weekend"),
               {"ocr_full": {"region": zone_roi, "keyword": weekend_zone_label, "evidence": "complete_keyword"}}],
              {"click_found": True, "delay": 1000, "recheck": True}, advance("create_room"))
        state("zone_pick_weekday", "select_zone",
              [expr(f"not {prefix}_is_weekend"),
               {"ocr_full": {"region": zone_roi, "keyword": zone_label, "evidence": "complete_keyword"}}],
              {"click_found": True, "delay": 1000, "recheck": True}, advance("create_room"))
    else:
        state("zone_pick", "select_zone",
              [{"ocr_full": {"region": zone_roi, "keyword": zone_label, "evidence": "complete_keyword"}}],
              {"click_found": True, "delay": 1000, "recheck": True}, advance("create_room"))
    state("zone_create_visible", "select_zone", [asset("I_CREATE_ROOM", "Component_GeneralRoom")],
          advance("create_room"))

    # GeneralRoom: create_room -> ensure_public -> create_ensure
    ensure_seen = {"any": [asset("I_CREATE_ENSURE", "Component_GeneralRoom"),
                           asset("I_CREATE_ENSURE_2", "Component_GeneralRoom")]}
    state("create_opened", "create_room", [ensure_seen], advance("ensure_public"))
    state("create_retry_limit", "create_room", [expr(f"{prefix}_create_taps > 3")],
          advance("exit_main", **{f"{prefix}_main_arrived": 0, f"{prefix}_exit_reason": "'no_room_tickets'"}))
    state("create_click", "create_room", [asset("I_CREATE_ROOM", "Component_GeneralRoom")],
          {"click_found": True, "use_match_size": True, "delay": 2000, "recheck": True},
          {"inc": f"{prefix}_create_taps"})
    state("create_missing_exit", "create_room", [{"not": asset("I_CREATE_ROOM", "Component_GeneralRoom")}],
          advance("exit_main", **{f"{prefix}_main_arrived": 0, f"{prefix}_exit_reason": "'no_create_btn'"}))

    public_on = {"any": [asset("I_ENSURE_PUBLIC", "Component_GeneralRoom"),
                         asset("I_ENSURE_PUBLIC_2", "Component_GeneralRoom")]}
    state("public_ok", "ensure_public", [public_on], advance("create_ensure"))
    state("public_tap_1", "ensure_public", [asset("I_ENSURE_PUBLIC_FALSE", "Component_GeneralRoom")],
          click("I_ENSURE_PUBLIC_FALSE", "Component_GeneralRoom", 1000))
    state("public_tap_2", "ensure_public", [asset("I_ENSURE_PUBLIC_FALSE_2", "Component_GeneralRoom")],
          click("I_ENSURE_PUBLIC_FALSE_2", "Component_GeneralRoom", 1000))

    state("ensure_tap_1", "create_ensure", [asset("I_CREATE_ENSURE", "Component_GeneralRoom")],
          click("I_CREATE_ENSURE", "Component_GeneralRoom", 1500))
    state("ensure_tap_2", "create_ensure", [asset("I_CREATE_ENSURE_2", "Component_GeneralRoom")],
          click("I_CREATE_ENSURE_2", "Component_GeneralRoom", 1500))
    state("ensure_done", "create_ensure", [{"not": ensure_seen}],
          advance("wait_room", **{f"{prefix}_wait_start": "elapsed_ms"}))

    # Room wait: detect teammate joined (not slot_asset) or timeout
    in_room = {"any": [
        asset("I_FIRE", "Component_GeneralInvite"),
        asset("I_LOCK", "Component_GeneralInvite"),
        asset("I_UNLOCK", "Component_GeneralInvite"),
    ]}
    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    reset[outputs["current_count"]] = f"{prefix}_runs"

    state("room_teammate_joined", "wait_room",
          [in_room, {"not": asset(slot_asset, "Component_GeneralInvite")},
           asset("I_FIRE", "Component_GeneralInvite")],
          click("I_FIRE", "Component_GeneralInvite", 1000),
          {"set": reset}, advance("battle", **{f"{prefix}_runs": f"{prefix}_runs + 1"}))
    if exit_on_wait_timeout:
        state("room_wait_timeout_exit", "wait_room",
              [in_room, expr(f"elapsed_ms - {prefix}_wait_start >= {prefix}_room_wait_seconds * 1000")],
              advance("exit_room"))
        state("exit_room_back", "exit_room", [asset("I_BACK_YELLOW", "Component_GeneralInvite")],
              click("I_BACK_YELLOW", "Component_GeneralInvite", 1000))
        state("exit_room_confirm", "exit_room", [asset("I_UI_CONFIRM", "GlobalGame")],
              click("I_UI_CONFIRM", "GlobalGame", 1000))
        state("exit_room_done", "exit_room", [{"not": in_room}],
              advance("exit_main", **{f"{prefix}_main_arrived": 0, f"{prefix}_exit_reason": "'room_wait_timeout'"}))
    else:
        state("room_wait_timeout_fire", "wait_room",
              [in_room, expr(f"elapsed_ms - {prefix}_wait_start >= {prefix}_room_wait_seconds * 1000"),
               asset("I_FIRE", "Component_GeneralInvite")],
              click("I_FIRE", "Component_GeneralInvite", 1000),
              {"set": reset}, advance("battle", **{f"{prefix}_runs": f"{prefix}_runs + 1"}))
    state("room_wait_tick", "wait_room", [], {"wait": 1000})

    # Optional task-specific win banner (I_EXP_WIN / I_GOLD_WIN) + GeneralBattle states
    if win_asset is not None:
        state("custom_win_banner", "battle", [asset(win_asset[1], win_asset[0])],
              click(win_asset[1], win_asset[0], 1000),
              advance("goto_team", **{f"{prefix}_wins": f"{prefix}_wins + 1", f"{prefix}_team_arrived": 0}))
    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("goto_team", **{
                f"{prefix}_wins": f"{prefix}_wins + {outputs['win']}",
                f"{prefix}_team_arrived": 0,
            })]
        raw["states"].append(step)

    # Return to courtyard, close optional buffs, and schedule
    state("returned_main", "exit_main", [court, expr(f"{prefix}_main_arrived == 1")], advance("buff_after"))
    state("finished_target_prep", "finished", [expr(f"{prefix}_next_delay_s > 0")],
          advance("stop_target", **{
              f"{prefix}_target_delay_s": f"{prefix}_next_delay_s",
              f"{prefix}_observed_ms": "elapsed_ms",
          }))
    state("finished_target", "stop_target", [], {
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
    state("finished", "finished", [], {
        "stop": {
            "reason": f"{title}已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": task_name,
            "evidence": {"scope": f"{prefix}_native_path"},
        }
    })
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": f"{prefix}_main_arrived"}})

    raw[f"oas_{prefix}_contract"] = {
        "source": entry,
        "source_pins": {**pins, **SCHEDULE_PINS, **SOUL_PINS},
        "original_task_complete": False,
        "buff_calls": buff_calls,
        "source_obligations": [
            *nav["source_obligations"], *battle["source_obligations"],
            *(ob for call in buff_calls for ob in call["source_obligations"]),
            {
                "id": f"{prefix}_live_room_and_buff",
                "blocking": True,
                "requirement": f"Verify {task_name} courtyard buff readback, public room creation, and battle on live frames",
            },
        ],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_experience_youkai_candidate(source_root, resource_dir, *, calibrations=None):
    return _compile_public_room_youkai(
        source_root, resource_dir, task_name="ExperienceYoukai",
        wf_name="oas_experience_youkai_natively_staged", title="经验妖怪",
        prefix="ey", entry=EXP_YOUKAI_ENTRY, pins=EXP_YOUKAI_PINS,
        zone_label="经验妖怪", win_asset=("ExperienceYoukai", "I_EXP_WIN"),
        max_runs=2, wait_s=50, slot_asset="I_ADD_5_1",
        buff_params=("ey_buff_exp_50", "ey_buff_exp_100"),
        buff_ops=[("exp_50", "ey_buff_exp_50"), ("exp_100", "ey_buff_exp_100")],
        buff_enable_expr="(ey_buff_exp_50 or ey_buff_exp_100)",
        exit_on_wait_timeout=False, calibrations=calibrations,
    )


def compile_gold_youkai_candidate(source_root, resource_dir, *, calibrations=None):
    return _compile_public_room_youkai(
        source_root, resource_dir, task_name="GoldYoukai",
        wf_name="oas_gold_youkai_natively_staged", title="金币妖怪",
        prefix="gy", entry=GOLD_YOUKAI_ENTRY, pins=GOLD_YOUKAI_PINS,
        zone_label="金币妖怪", win_asset=("GoldYoukai", "I_GOLD_WIN"),
        max_runs=2, wait_s=50, slot_asset="I_ADD_5_1",
        buff_params=("gy_buff_gold_50", "gy_buff_gold_100"),
        buff_ops=[("gold_50", "gy_buff_gold_50"), ("gold_100", "gy_buff_gold_100")],
        buff_enable_expr="(gy_buff_gold_50 or gy_buff_gold_100)",
        exit_on_wait_timeout=False, calibrations=calibrations,
    )


def compile_tako_candidate(source_root, resource_dir, *, calibrations=None):
    return _compile_public_room_youkai(
        source_root, resource_dir, task_name="Tako",
        wf_name="oas_tako_natively_staged", title="石距",
        prefix="tk", entry=TAKO_ENTRY, pins=TAKO_PINS,
        zone_label="石距", weekend_zone_label="喷怒的石距", win_asset=None,
        max_runs=1, wait_s=60, slot_asset="I_ADD_1",
        buff_params=("tk_buff_enable", "tk_buff_gold_50", "tk_buff_gold_100", "tk_buff_exp_50", "tk_buff_exp_100"),
        buff_ops=[("gold_50", "tk_buff_gold_50"), ("gold_100", "tk_buff_gold_100"),
                  ("exp_50", "tk_buff_exp_50"), ("exp_100", "tk_buff_exp_100")],
        buff_enable_expr="(tk_buff_enable and (tk_buff_gold_50 or tk_buff_gold_100 or tk_buff_exp_50 or tk_buff_exp_100))",
        exit_on_wait_timeout=True, calibrations=calibrations,
    )


def compile_nian_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Nian auto-match workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, NIAN_PINS, "Nian")
    nav = compile_navigation_family(
        source, resources, prefix="ni_nav", destination="page_team",
        battle_config="default", android_login=True, separate_battle_defaults=True,
        calibrations=calibrations,
    )
    battle = compile_general_battle(source, resources, prefix="ni_battle")
    if not battle["guarded_executable"]:
        raise ValueError("Nian could not bind GeneralBattle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]

    raw = nav["workflow"]
    raw.update(name="oas_nian_natively_staged", title="年兽", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 900
    bind_schedule(source, raw)
    raw["params"].update(
        ni_buff_gold_50={"default": False},
        ni_buff_gold_100={"default": False},
        ni_match_timeout_seconds={"default": 480, "min": 1, "max": 900},
        ni_limit_seconds={"default": 0, "min": 0, "max": 7200},
        ni_cd_delay_s={"default": 14400, "min": 0, "max": 86400},
    )
    if set(raw["params"]) & set(body["params"]):
        raise ValueError("Nian navigation and battle configuration overlap")
    raw["params"].update(body["params"])
    raw["vars"].update(
        body["vars"],
        ni_phase="entry", ni_cd_taps=0, ni_match_start=0, ni_safe_clicked=False,
        ni_wins=0, ni_cd_ocr_s=-1, ni_cd_target_s=0, ni_cd_observed_ms=0, ni_main_arrived=0, ni_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/Nian.yaml",
        "upstream/oas/Component_GeneralRoom.yaml",
        "upstream/oas/Component_GeneralInvite.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("Nian", "Component_GeneralRoom", "Component_GeneralInvite", "GlobalGame")
    }
    zone_roi = docs["Component_GeneralRoom"]["O_GR_ZONES_NAME"]["roi"]
    cd_label_roi = docs["Nian"]["O_N_BATTLE_AGAIN"]["roi"]
    cd_time_roi = docs["Nian"]["O_N_CD"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"ni_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"ni_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"ni_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Nian"):
        return {"res": f"{ns}::{name}"}

    def click(name, ns="Nian", delay=1000):
        return _click_from(docs, name, ns, delay)

    ni_buff_ops = [("gold_50", "ni_buff_gold_50"), ("gold_100", "ni_buff_gold_100")]
    ni_buff_expr = "(ni_buff_gold_50 or ni_buff_gold_100)"
    buff_calls = [
        bind_courtyard_buffs(
            raw, source, resources, prefix=f"ni_buff_{leg}", phase_var="ni_phase",
            entry_phase=f"buff_{leg}", resume=resume, operations=ni_buff_ops,
            enable_param=ni_buff_expr, opening=opening,
        )
        for leg, opening, resume in (("before", True, "navigate"), ("after", False, "finished"))
    ]
    state("entry_to_buff", "entry", [], advance("buff_before"))

    arrived = next(step for step in raw["states"] if step["id"] == "ni_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("select_zone")]
    next(step for step in raw["states"] if step["id"] == "ni_nav_drive")["when"] = phase("navigate")

    state("pick_nian_zone", "select_zone",
          [{"ocr_full": {"region": zone_roi, "keyword": "年兽", "evidence": "complete_keyword"}}],
          {"click_found": True, "delay": 1000, "recheck": True}, advance("check_cd", ni_cd_taps=0))
    state("zone_already_selected", "select_zone", [asset("I_GR_AUTO_MATCH", "Component_GeneralRoom")],
          advance("check_cd", ni_cd_taps=0))

    # Check CD banner (I_N_CHECK + O_N_BATTLE_AGAIN/O_N_CD) -> schedule target delay & exit cleanly on CD
    cd_ocr = {"any": [
        {"ocr_full": {"region": cd_label_roi, "keyword": "再次挑战", "evidence": "complete_keyword"}},
        {"ocr_full": {"region": cd_label_roi, "keyword": "后可", "evidence": "complete_keyword"}},
        {"ocr_full": {"region": cd_time_roi, "keyword": "后可", "evidence": "complete_keyword"}},
    ]}
    state("check_cd_time_limit", "check_cd",
          [expr("ni_limit_seconds > 0 and elapsed_ms >= ni_limit_seconds * 1000")],
          advance("done", ni_exit_reason="'time_limit'"))
    state("in_cooldown_banner_ocr", "check_cd",
          [asset("I_N_CHECK"), cd_ocr,
           {"ocr": "Nian::O_N_CD", "mode": "cn_hour_minute", "var": "ni_cd_ocr_s", "test": "ni_cd_ocr_s > 0"}],
          advance("done", ni_exit_reason="'cooldown_banner_ocr'",
                  ni_cd_target_s="ni_cd_ocr_s", ni_cd_observed_ms="elapsed_ms"))
    state("in_cooldown_banner", "check_cd",
          [asset("I_N_CHECK"), cd_ocr],
          advance("done", ni_exit_reason="'cooldown_banner'",
                  ni_cd_target_s="ni_cd_delay_s", ni_cd_observed_ms="elapsed_ms"))
    state("waiting_started", "check_cd", [asset("I_N_WAITING")],
          advance("matching", ni_match_start="elapsed_ms", ni_safe_clicked=False))
    state("auto_match_cd_limit", "check_cd", [expr("ni_cd_taps >= 4")],
          advance("done", ni_exit_reason="'cooldown_no_match'"))
    state("click_auto_match", "check_cd", [asset("I_GR_AUTO_MATCH", "Component_GeneralRoom")],
          click("I_GR_AUTO_MATCH", "Component_GeneralRoom", 1500), {"inc": "ni_cd_taps"})

    # Matching loop: take-over battle, in-room wait, 240s safe click, 480s timeout cancel
    persistent = set(contract["composition"]["interval_vars"])
    reset = {k: repr(v) if isinstance(v, str) else v for k, v in body["vars"].items() if k not in persistent}
    battle_seen = {"any": [
        asset("I_PREPARE_HIGHLIGHT", "Component_GeneralBattle"),
        asset("I_BATTLE_INFO", "Component_GeneralBattle"),
    ]}
    in_room = {"any": [
        asset("I_FIRE", "Component_GeneralInvite"),
        asset("I_LOCK", "Component_GeneralInvite"),
        asset("I_UNLOCK", "Component_GeneralInvite"),
    ]}
    state("match_time_limit", "matching",
          [expr("ni_limit_seconds > 0 and elapsed_ms >= ni_limit_seconds * 1000")],
          advance("cancel_match", ni_exit_reason="'time_limit'"))
    state("match_takeover_battle", "matching", [battle_seen], {"set": reset}, advance("battle"))
    state("match_entered_room", "matching", [in_room], {"set": reset}, advance("battle"))
    state("match_timeout_cancel", "matching",
          [expr("elapsed_ms - ni_match_start >= ni_match_timeout_seconds * 1000")],
          advance("cancel_match"))
    state("match_safe_click", "matching",
          [expr("not ni_safe_clicked"), expr("elapsed_ms - ni_match_start >= 240000")],
          click("C_CLIC_SAFE", "Nian", 500), {"set": {"ni_safe_clicked": True}})
    state("match_wait_tick", "matching", [asset("I_N_WAITING")], {"wait": 1000})

    state("cancel_done_time_limit", "cancel_match",
          [expr("ni_exit_reason == 'time_limit'"), {"not": asset("I_N_WAITING")}],
          advance("done"))
    state("cancel_done", "cancel_match", [{"not": asset("I_N_WAITING")}],
          advance("done", ni_exit_reason="'match_timeout'"))
    state("cancel_confirm", "cancel_match", [asset("I_UI_CONFIRM", "GlobalGame")],
          click("I_UI_CONFIRM", "GlobalGame", 1000))
    state("cancel_confirm_small", "cancel_match", [asset("I_UI_CONFIRM_SAMLL", "GlobalGame")],
          click("I_UI_CONFIRM_SAMLL", "GlobalGame", 1000))
    state("cancel_waiting_tap", "cancel_match", [asset("I_N_WAITING")], click("I_N_WAITING", "Nian", 1000))

    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("done", ni_wins=f"ni_wins + {outputs['win']}", ni_exit_reason="'battle_done'")]
        raw["states"].append(step)

    court = raw["navigation"]["pages"]["page_main"]["when"]
    state("done_skip_main", "done", [expr(f"not {ni_buff_expr}")], advance("buff_after"))
    state("done_goto_main", "done", [expr(ni_buff_expr)], advance("exit_main", ni_main_arrived=0))
    state("returned_main", "exit_main", [court, expr("ni_main_arrived == 1")], advance("buff_after"))
    state("exit_main_drive", "exit_main", [],
          {"navigate": {"destination": "page_main", "done_var": "ni_main_arrived"}})
    state("complete_cd_target", "finished", [expr("ni_cd_target_s > 0")], {
        "stop": {
            "reason": "年兽处于冷却中，已按冷却时长预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "Nian",
                "delay_seconds_var": "ni_cd_target_s",
                "observed_ms_var": "ni_cd_observed_ms",
            },
            "evidence": {"scope": "nian_cd_target_schedule"},
        }
    })
    state("complete", "finished", [], {
        "stop": {
            "reason": "年兽已完成",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Nian",
            "evidence": {"scope": "nian_native_path"},
        }
    })

    raw["oas_nian_contract"] = {
        "source": NIAN_ENTRY,
        "source_pins": {**NIAN_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "buff_calls": buff_calls,
        "source_obligations": [
            *nav["source_obligations"], *battle["source_obligations"],
            *(ob for call in buff_calls for ob in call["source_obligations"]),
            {
                "id": "nian_cd_ocr_target_and_live",
                "blocking": True,
                "requirement": "Bind Nian CD regex target scheduling and live auto-match/buff verification",
            },
        ],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
