"""Pinned OAS TalismanPass workflow (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


ENTRY = "tasks/TalismanPass/script_task.py"
TAB_PNG = "tasks/TalismanPass/tp/tp_task_tab.png"
PINS = {
    ENTRY: "66bb7d56e7ac8e7046adff6fa2f807bd01553f2eae986e9a06f6c5978104cfca",
    "tasks/TalismanPass/config.py": "66d8e4f980f00c0c135ed2c6916c82250e64c455b87001a009f1129149dfcd30",
    "tasks/TalismanPass/assets.py": "01706f557af3ba25ea1eeedf7f12ed24f31f404e0878e1c24a9fc47e30e86690",
    "module/base/timer.py": "8b4c54c89e03c4588619e5650df85f49bbf94ad3b69bb1da8f9c0a6bba2f14af",
    TAB_PNG: "8c9208bcca4647c1066c85fbd59cfc966563b45d29d3122814217cbb29132ebd",
}
REWARDS = ("蛇皮/青吉鬼", "金币/勾玉", "体力/樱饼")


def compile_talisman_candidate(source_root, resource_dir, *, calibrations=None):
    source, resources = Path(source_root), Path(resource_dir)
    for path, expected in PINS.items():
        file = source / path
        data = file.read_bytes() if path == TAB_PNG else file.read_text(encoding="utf-8-sig").encode()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"TalismanPass source fingerprint mismatch: {path}")
    navigation = compile_navigation_family(source, resources, prefix="tp_nav", destination="page_daily",
                                           battle_config="default", android_login=True, calibrations=calibrations)
    raw = navigation["workflow"]
    raw["name"], raw["title"] = "oas_talisman_pass_natively_staged", "花合战"
    raw["limits"]["timeout_s"] = 600
    raw["loop_delay_ms"] = 200
    bind_schedule(source, raw)
    raw["params"]["oas_success_seconds"]["default"] = 21600
    raw["params"].update(tp_level_reward={"default": REWARDS[1], "choices": list(REWARDS)},
                         tp_harvest_soul={"default": False},
                         tp_next_delay_s={"default": 0, "min": 0, "max": 604800})
    raw["vars"].update(tp_phase="navigate", tp_timer=0, tp_reward_inputs=0, tp_reward_pending=False,
                       tp_unverified_claim=False, tp_level_picked=False, tp_nav_court_arrived=0, tp_reward_receipts=0,
                       tp_target_delay_s=0, tp_observed_ms=0)
    raw["resources"] = sorted(set(raw["resources"] + ["upstream/oas/TalismanPass.yaml"]))
    raw.setdefault("inline_resources", {})["tp_task_tab"] = {
        "type": "image", "path": str((source / TAB_PNG).resolve()), "roi": [1185, 307, 64, 117],
        "front": [1198, 328, 36, 73], "threshold": 0.8, "method": "Template matching", "roi_expand": 2}
    documents = {namespace: load_yaml(resources / f"{namespace}.yaml")["resources"]
                 for namespace in ("TalismanPass", "GlobalGame")}

    def expr(value):
        return {"expr": value}

    def phase(value):
        return expr(f"tp_phase == {value!r}")

    def advance(value, **values):
        return {"set": {"tp_phase": repr(value), **values}}

    def marker(name, **options):
        return {"res": f"TalismanPass::{name}", **options}

    def state(name, where, conditions, *actions):
        raw["states"].append({"id": f"tp_{name}", "when": {"all": [phase(where), *conditions]}, "do": list(actions)})

    def click(name, delay=1000, namespace="TalismanPass"):
        spec = documents[namespace][name]
        if spec["type"] == "click":
            rect = spec["rect"]
        else:
            x, y, width, height = spec["front"]
            rect = [x, y, x + width, y + height]
        return {"click": rect, "delay": delay, "recheck": True}

    daily = raw["navigation"]["pages"]["page_daily"]["when"]
    court = raw["navigation"]["pages"]["page_main"]["when"]
    arrived = next(step for step in raw["states"] if step["id"] == "tp_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("task_tab")]
    next(step for step in raw["states"] if step["id"] == "tp_nav_drive")["when"] = phase("navigate")
    task = {"any": [marker("I_TP_GOTO"), marker("I_TP_EXP")]}
    red_level = marker("I_RED_POINT_LEVEL")
    bulk = marker("I_TP_GET_ALL")
    pass_page = {"any": [daily, task, red_level, bulk, *(marker(f"I_TP_LEVEL_{n}") for n in range(1, 4))]}
    reward = {"res": "GlobalGame::I_UI_REWARD", "threshold": 0.6}
    dismiss_reward = click("C_UI_REWARD", 400, "GlobalGame")
    reset_timer = {"set": {"tp_timer": "elapsed_ms"}}
    count_claim = {"set": {"tp_reward_inputs": "tp_reward_inputs + 1", "tp_reward_pending": True}}
    receipt = {"set": {"tp_reward_receipts": "tp_reward_receipts + tp_reward_pending", "tp_reward_pending": False}}
    clear_unverified = {"set": {"tp_unverified_claim": "tp_unverified_claim or tp_reward_pending",
                                "tp_reward_pending": False}}

    state("switch_task_tab", "task_tab", [{"res": "tp_task_tab"}],
          {"click": [1198, 328, 1234, 401], "delay": 1000, "recheck": True}, advance("task_probe"))
    state("task_tab_absent", "task_tab", [pass_page], advance("task_probe"))
    state("task_enter", "task_probe", [task], advance("task_claim", tp_timer="elapsed_ms"))
    state("task_unavailable", "task_probe", [pass_page], advance("level_probe"))
    state("task_reward_seen", "task_claim", [reward], dismiss_reward, {"wait": 500}, advance("task_animation"))
    state("task_reward_timeout", "task_claim", [expr("elapsed_ms - tp_timer >= 10000")],
          {"wait": 500}, clear_unverified, advance("level_probe"))
    state("task_bulk_claim", "task_claim", [bulk], click("I_TP_GET_ALL"), count_claim)
    state("task_animation_dismiss", "task_animation", [reward], dismiss_reward)
    state("task_animation_done", "task_animation", [{"not": reward}, pass_page],
          receipt, {"wait": 500}, advance("level_probe"))

    state("level_available", "level_probe", [red_level], advance("level_open"))
    state("level_unavailable", "level_probe", [pass_page, {"not": red_level}], advance("optional_soul"))
    state("level_page", "level_open", [bulk], advance("level_claim", tp_timer="elapsed_ms"))
    state("open_level", "level_open", [red_level], click("I_RED_POINT_LEVEL"))
    overflow = marker("I_OVERFLOW_CONFIRME")
    state("level_overflow", "level_claim", [overflow, expr("tp_level_picked")],
          click("I_OVERFLOW_CONFIRME"), reset_timer, {"set": {"tp_level_picked": False}})
    state("unknown_overflow", "level_claim", [overflow], {"fail": "花合战溢出提示缺少已选等级奖励上下文"})
    for number, label in enumerate(REWARDS, 1):
        asset = f"I_TP_LEVEL_{number}"
        state(f"pick_level_{number}", "level_claim", [marker(asset), expr(f"tp_level_reward == {label!r}")],
              click(asset, 800), count_claim, reset_timer, {"set": {"tp_level_picked": True}})
    state("level_reward_seen", "level_claim", [reward], dismiss_reward, receipt, reset_timer,
          {"set": {"tp_level_picked": False}})
    state("level_idle", "level_claim", [pass_page, expr("elapsed_ms - tp_timer >= 2000")],
          clear_unverified, advance("optional_soul"))
    state("level_bulk_claim", "level_claim", [bulk], click("I_TP_GET_ALL", 2100), count_claim, reset_timer)

    state("soul_enabled", "optional_soul", [expr("tp_harvest_soul")], advance("navigate_court"))
    state("soul_disabled", "optional_soul", [expr("not tp_harvest_soul")], advance("finished"))
    state("courtyard_arrived", "navigate_court", [court, expr("tp_nav_court_arrived == 1")],
          advance("soul_search", tp_timer="elapsed_ms"))
    state("courtyard_drive", "navigate_court", [], {"navigate": {
        "destination": "page_main", "done_var": "tp_nav_court_arrived", "category": "talisman_pass"}})
    soul_card = marker("I_TP_SOUL_1", scale_range=[0.8, 1.1])
    soul_pick = marker("I_TP_SOUL_2")
    soul_done = marker("I_TP_SOUL_3")
    state("soul_found", "soul_search", [soul_card], advance("soul_open"))
    state("soul_timeout", "soul_search", [court, expr("elapsed_ms - tp_timer >= 5000")], advance("finished"))
    state("soul_picker", "soul_open", [soul_pick], advance("soul_select"))
    state("soul_open_card", "soul_open", [soul_card],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("soul_confirmed", "soul_select", [soul_done], advance("soul_receipt"))
    state("soul_select_reward", "soul_select", [soul_pick], click("I_TP_SOUL_2", 3000), count_claim)
    state("soul_dismiss_receipt", "soul_receipt", [soul_done], click("I_TP_SOUL_3"))
    state("soul_receipt_done", "soul_receipt", [{"not": soul_done}, court], receipt,
          advance("soul_search", tp_timer="elapsed_ms"))

    state("finished_target_prep", "finished", [expr("tp_next_delay_s > 0")],
          advance("stop_target", tp_target_delay_s="tp_next_delay_s", tp_observed_ms="elapsed_ms"))
    for name, predicate, verified in (
        ("unknown", "tp_unverified_claim or tp_reward_pending", False),
        ("completed", "tp_reward_receipts > 0", True),
        ("already_done", "tp_reward_inputs == 0", True),
    ):
        state("stop_target_" + name, "stop_target", [expr(predicate)], {"stop": {
            "reason": "花合战任务已退出领取循环并按排班预约下次运行", "result": name, "verified": verified,
            "oas_schedule": {"task": "TalismanPass", "delay_seconds_var": "tp_target_delay_s",
                             "observed_ms_var": "tp_observed_ms"},
            "evidence": {"scope": "talisman_target_schedule"}}})
        state("finished_" + name, "finished", [expr(predicate)], {"stop": {
            "reason": "花合战任务已退出领取循环", "result": name, "verified": verified,
            "oas_schedule": "TalismanPass", "evidence": {"scope": "native-task-path"}}})
    obligations = [*navigation["source_obligations"], {
        "id": "talisman_live_receipt", "requirement": "Verify task, level and 1500-day soul paths on retained real frames",
        "blocking": True,
    }]
    raw["oas_talisman_contract"] = {"source": ENTRY, "source_pins": {**PINS, **SCHEDULE_PINS},
                                    "original_task_complete": False, "source_obligations": obligations}
    load_workflow(raw, [resources.parent.parent])
    return {"workflow": raw, "complete": False, "source_obligations": obligations}
