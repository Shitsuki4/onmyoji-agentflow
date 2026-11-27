"""Pinned OAS DyeTrials event workflow (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


ENTRY = "tasks/DyeTrials/script_task.py"
PINS = {
    ENTRY: "0e068d84643c5284177f253476870e46ad7ff969d4896599347df4a887fe3e58",
    "tasks/DyeTrials/config.py": "60fcce659acd1d44d03a9b377bdab33fe6325d5c6d9331ab1c64e26469e8ccc1",
    "tasks/DyeTrials/assets.py": "33c1914e7d84fb7ad6ee74f0a4171e5ff1d79869044fd324ff300a8db468752f",
    "tasks/Restart/assets.py": "e0f9345c7c4ff075d970dcf3916332801ff0ee07d222738de865363d302922ff",
    "module/ocr/sub_ocr.py": "33344898ce3e638bc2d8c3a90bc85cd0586458871c352631416dca02361d994d",
    "module/base/timer.py": "8b4c54c89e03c4588619e5650df85f49bbf94ad3b69bb1da8f9c0a6bba2f14af",
}


def compile_dye_trials_candidate(source_root, resource_dir, *, calibrations=None):
    source, resources = Path(source_root), Path(resource_dir)
    for path, expected in PINS.items():
        data = (source / path).read_text(encoding="utf-8-sig").encode()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"DyeTrials source fingerprint mismatch: {path}")
    packet = compile_navigation_family(source, resources, prefix="dye_nav", destination="page_main",
                                        battle_config="default", android_login=True, calibrations=calibrations)
    raw = packet["workflow"]
    raw.update(name="oas_dye_trials_natively_staged", title="灵染试炼", loop_delay_ms=200)
    raw["limits"]["unknown_timeout_s"] = 65
    bind_schedule(source, raw)
    raw["params"].update(
        dye_limit_seconds={"default": 0, "min": 0, "max": 3600},
        dye_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(dye_phase="entry", dye_timer=0, dye_started=0, dye_returned=0, dye_result="",
                       dye_challenge_taps=0, dye_target_delay_s=0, dye_observed_ms=0, dye_exit_reason="")
    raw["resources"] = sorted(set(raw["resources"] + ["upstream/oas/DyeTrials.yaml"]))
    assets = {name: load_yaml(resources / f"{name}.yaml")["resources"]
              for name in ("DyeTrials", "GlobalGame", "Restart")}

    def expr(value):
        return {"expr": value}

    def phase(value):
        return expr(f"dye_phase == {value!r}")

    def advance(value, **values):
        return {"set": {"dye_phase": repr(value), **values}}

    def asset(name, namespace="DyeTrials", **options):
        return {"res": f"{namespace}::{name}", **options}

    def click(name, delay=1000, namespace="DyeTrials"):
        spec = assets[namespace][name]
        if spec["type"] == "click":
            bounds = spec["rect"]
        else:
            x, y, w, h = spec["front"]
            bounds = [x, y, x + w, y + h]
        return {"click": bounds, "delay": delay, "recheck": True}

    def state(name, where, guards, *steps):
        raw["states"].append({"id": f"dye_{name}", "when": {"all": [phase(where), *guards]}, "do": list(steps)})

    bind_task_presets(raw, source, resources, prefix="dye", resume="navigate", category="dye_trials")
    returned = next(s for s in raw["states"] if s["id"] == "dye_nav_returned")
    returned["when"]["all"].append(phase("navigate"))
    returned["do"] = [advance("find_event")]
    next(s for s in raw["states"] if s["id"] == "dye_nav_drive")["when"] = phase("navigate")
    pages = raw["navigation"]["pages"]
    court = pages["page_main"]["when"]
    challenge = asset("I_FP_CHALLENGE")
    success = asset("I_BATTLE_SUCCESS")
    reward = asset("I_UI_REWARD", "GlobalGame", threshold=.6)
    reward_close = click("C_UI_REWARD", 400, "GlobalGame")
    notice = asset("I_HARVEST_CHAT_CLOSE", "Restart")
    reset_timer = {"set": {"dye_timer": "elapsed_ms"}}
    state("event_found", "find_event", [challenge], advance("challenge", dye_timer="elapsed_ms"))
    for name, delay, context in (("I_FP_ACCESS", 800, [court]),
                                 ("I_FP_ACCESS_1", 1500, []), ("I_TOGGLE_BUTTON", 3000, [court])):
        state(name.lower(), "find_event", [*context, asset(name)], click(name, delay))

    roi = assets["DyeTrials"]["O_BATTLE_NUM"]["roi"]
    reached_limit = {"text": "", "region": roi, "pattern": r"^\s*50\s*[/／]\s*50\s*$"}
    can_start = {"text": "", "region": roi, "pattern": r"^\s*(?:[0-4]?[0-9])\s*[/／]\s*50\s*$"}
    timeout = expr("elapsed_ms - dye_timer >= 60000")
    for where in ("challenge", "battle_pending"):
        state(f"{where}_timeout", where, [timeout], {"log": "灵染试炼识别超时，返回庭院"},
              advance("return", dye_result="'unknown'"))

    state("reward_overlay", "challenge", [reward], reward_close, reset_timer)
    state("chat_notice", "challenge", [notice], click("I_HARVEST_CHAT_CLOSE", 1000, "Restart"), reset_timer)
    state("time_limit_reached", "challenge",
          [expr("dye_limit_seconds > 0 and elapsed_ms >= dye_limit_seconds * 1000")],
          advance("return", dye_result="'limit'", dye_exit_reason="'time_limit'"))
    state("limit_reached", "challenge", [challenge, {"any": [reached_limit, expr("dye_started >= 50")]}],
          advance("return", dye_result="'limit'"))
    state("challenge_input", "challenge", [challenge, can_start], click("I_FP_CHALLENGE"),
          advance("battle_pending", dye_challenge_taps=1))
    state("success_overlay", "challenge", [success], click("I_BATTLE_SUCCESS"), reset_timer)
    battle_signal = {"any": [pages["page_battle"]["when"], success, reward]}
    state("challenge_departed", "battle_pending", [{"not": challenge}, battle_signal], {"inc": "dye_started"},
          advance("challenge", dye_timer="elapsed_ms"))
    state("challenge_retry", "battle_pending", [challenge, can_start, expr("dye_challenge_taps < 3")],
          click("I_FP_CHALLENGE"), {"inc": "dye_challenge_taps"})

    state("return_arrived", "return", [court, expr("dye_returned == 1")], advance("finished"))
    state("return_drive", "return", [], {"navigate": {"destination": "page_main", "done_var": "dye_returned",
                                                     "category": "dye_trials"}})
    state("finished_target_prep", "finished", [expr("dye_next_delay_s > 0")],
          advance("stop_target", dye_target_delay_s="dye_next_delay_s", dye_observed_ms="elapsed_ms"))
    for name, condition, verified in (
        ("already_done", "dye_result == 'limit' and dye_started == 0", True),
        ("completed", "dye_result == 'limit' and dye_started > 0", True),
        ("unknown", "dye_result == 'unknown'", False),
    ):
        state("stop_target_" + name, "stop_target", [expr(condition)], {"stop": {
            "reason": "灵染试炼已经返回庭院并按排班预约下次运行", "result": name, "verified": verified,
            "oas_schedule": {"task": "DyeTrials", "delay_seconds_var": "dye_target_delay_s",
                             "observed_ms_var": "dye_observed_ms"},
            "evidence": {"scope": "dye_trials_target_schedule"}}})
        state("finished_" + name, "finished", [expr(condition)], {"stop": {
            "reason": "灵染试炼已经返回庭院", "result": name, "verified": verified, "oas_schedule": "DyeTrials",
            "evidence": {"scope": "native-task-path"}}})
    obligations = [*packet["source_obligations"], {
        "id": "dye_trials_presets", "requirement": "Verify both preset modes and effective costume on real frames, and bind sequences of numbered pairs",
        "blocking": True,
    }, {
        "id": "dye_trials_counter", "requirement": "Verify recognized count, departure markers and event availability on real frames",
        "blocking": True,
    }, {
        "id": "dye_trials_timeout_push", "requirement": "Source timeout sends a notifier message. Native candidate records a local log.",
        "blocking": True,
    }]
    raw["oas_dye_trials_contract"] = {"source": ENTRY, "source_pins": {**PINS, **SCHEDULE_PINS, **SOUL_PINS},
                                     "original_task_complete": False, "source_obligations": obligations}
    load_workflow(raw, [resources.parent.parent])
    return {"workflow": raw, "complete": False, "source_obligations": obligations}
