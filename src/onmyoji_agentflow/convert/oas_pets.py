"""Pinned OAS pet-feeding task (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_courtyard_costume import bind_courtyard_costume
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


PINS = {
    "tasks/Pets/script_task.py": "7a7cbb478b6731327d68806196a674350a81ec3f6adc084bc1bd98b7151bf50c",
    "tasks/Pets/config.py": "e1cbcc3b5365b245c4d693ee190977f94fd1bfe59f11cf024c63c6d527e4fba6",
    "tasks/Pets/assets.py": "5ffcab2253173ca065e0d6723f169caf1369b08b2c5312ab5bbee5d75c5ca49c",
    "tasks/base_task.py": "6d8849bcfdb368a012b9e19e37d446ed3022dad39974ab6eb237c959c43b4c20",
    "module/config/config.py": "938cd30134f8113f63fba7bd68f419b666ccce188789e09be6ea36b6efc46978",
    "module/config/config_model.py": "b7554ef255a7005a1a605edbfd22cfc691f5c01d166f4750b411bc724eb72324",
}


def compile_pets_candidate(source_root, resource_dir, *, calibrations=None, courtyard_costume=0):
    """Lower the reachable Pets.run/_feed path for an isolated Runner."""
    source_root, resource_dir = Path(source_root), Path(resource_dir)
    for filename, expected in PINS.items():
        text = (source_root / filename).read_text(encoding="utf-8-sig")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"Pets source fingerprint mismatch: {filename}")
    # BaseTask retains the Config facade. Its __getattr__ returns None for the
    # absent top-level GeneralBattle field, selecting the helper's default arm.
    packet = compile_navigation_family(source_root, resource_dir, prefix="pet_nav", destination="page_main",
                                       battle_config="default", android_login=True, calibrations=calibrations)
    raw = packet["workflow"]
    raw["name"], raw["title"] = "oas_pets_natively_staged", "宠物小屋"
    bind_schedule(source_root, raw)
    raw["params"]["pets_feast"] = {"default": True}
    raw["vars"].update(pet_phase="navigate", pet_ap_cost=-1, pet_outcome="unknown", pet_feed_attempted=False)
    raw["resources"] = sorted(set(raw["resources"] + ["upstream/oas/Pets.yaml"]))
    pets = load_yaml(resource_dir / "Pets.yaml")["resources"]

    def phase(value):
        return {"expr": f"pet_phase == {value!r}"}

    def change(value):
        return {"set": {"pet_phase": repr(value)}}

    def res(asset):
        return {"res": "Pets::" + asset}

    def click(asset, **extra):
        x, y, w, h = pets[asset]["front"]
        return {"click": [x, y, x + w, y + h], "delay": 1000, "recheck": True, **extra}

    def state(name, current, guards, *actions):
        raw["states"].append({"id": f"pet_{name}", "when": {"all": [phase(current), *guards]}, "do": list(actions)})

    courtyard = raw["navigation"]["pages"]["page_main"]["when"]
    arrived = next(st for st in raw["states"] if st["id"] == "pet_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [change("enter")]
    next(st for st in raw["states"] if st["id"] == "pet_nav_drive")["when"] = phase("navigate")

    feast, feed, skip, exit_ = map(res, ("I_PET_FEAST", "I_PET_FEED", "I_PET_SKIP", "I_PET_EXIT"))
    state("house_arrival", "enter", [feast], change("house"))
    for name, asset in (("enter_house", "I_PET_HOUSE"), ("open_pet_claw", "I_PET_CLAW")):
        state(name, "enter", [res(asset)], click(asset))
    state("feeding_disabled", "house", [feast, {"expr": "not pets_feast"}],
          {"set": {"pet_outcome": "'skipped'"}}, change("exit"))
    state("feed_dialog_open", "house", [feed], change("cost"))
    state("fast_feed", "house", [feast, {"expr": "pets_feast"}], click("I_PET_FEAST"))
    state("read_cost", "cost", [feed, {"ocr": "Pets::O_PET_FEED_AP", "var": "pet_ap_cost"}], change("decide"))
    state("already_fed", "decide", [feed, {"expr": "pet_ap_cost == 0"}],
          {"set": {"pet_outcome": "'already_done'"}}, change("exit"))
    state("feed_once", "decide", [feed, {"expr": "pet_ap_cost > 0"}],
          click("I_PET_FEED", attempt_var="pet_feed_attempted"), change("confirm_animation"))
    state("feed_animation_seen", "confirm_animation", [skip], change("animation"))
    state("feed_animation_finished", "animation", [{"not": skip}, {"any": [exit_, feast]}],
          {"set": {"pet_outcome": "'completed'"}}, change("exit"))
    for result in ("completed", "already_done", "skipped"):
        state("finished_" + result, "exit", [courtyard, {"expr": f"pet_outcome == {result!r}"}],
              {"stop": {"reason": "宠物流程已返回庭院", "result": result, "verified": True,
                        "oas_schedule": "Pets", "evidence": {"scope": "Pets native task"}}})
    state("leave_pet_house", "exit", [exit_, {"not": courtyard}], click("I_PET_EXIT"))
    obligations = packet["source_obligations"]
    raw["oas_pets_contract"] = {
        "source": "tasks/Pets/script_task.py", "source_pins": {**PINS, **SCHEDULE_PINS}, "original_task_complete": False,
        "unreachable": "ScriptTask.run comments out its invocation of _play",
        "incidental_battle_config": "pinned Config.__getattr__ returns None; navigation uses GeneralBattle defaults",
        "recognition_repairs": packet["recognition_repairs"],
        "source_obligations": obligations,
    }
    bind_courtyard_costume(source_root, resource_dir, raw, courtyard_costume, bind_pet_house=True)
    load_workflow(raw, [resource_dir.parent.parent])
    return {"workflow": raw, "complete": False, "original_task_complete": False, "source_obligations": obligations}
