"""Pinned OAS return-to-courtyard entry (GPL-3.0, runhey et al.)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..workflow.schema import load_workflow
from .navigation_family import compile_navigation_family
from .oas_courtyard_costume import bind_courtyard_costume


ENTRY = "tasks/GotoMain/script_task.py"
PINS = {
    ENTRY: "c890c3b5ca4e62ef8bc40d23fc52076f8e131ab17b563ccd77380f3c32b7cb11",
    "tasks/GameUi/game_ui.py": "c8427823b3c7cbb485c521743484c9b6887c024d37413f8e6a51d0027b1738f5",
    "tasks/GameUi/navigator.py": "f850b90fbe4dccddbe16d34effa69a17dcae3ac17e783f35254bce04ec8a175a",
    "tasks/base_task.py": "6d8849bcfdb368a012b9e19e37d446ed3022dad39974ab6eb237c959c43b4c20",
    "module/config/config.py": "938cd30134f8113f63fba7bd68f419b666ccce188789e09be6ea36b6efc46978",
    "module/config/config_model.py": "b7554ef255a7005a1a605edbfd22cfc691f5c01d166f4750b411bc724eb72324",
    "tasks/Component/Costume/costume_base.py": "4467807636bec23d24994091a3f39497e88aa3a66d5d197f94471d1d70021865",
}


def compile_goto_main_candidate(source_root, resource_dir, *, calibrations=None, courtyard_costume=0):
    """Lower GotoMain's entry and retain unresolved navigation branches."""
    source_root, resource_dir = Path(source_root), Path(resource_dir)
    for path, expected in PINS.items():
        content = (source_root / path).read_text(encoding="utf-8-sig")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"GotoMain source fingerprint mismatch: {path}")

    # GameUi uses BaseTask's unchanged Config facade. A missing top-level
    # GeneralBattle field is None, which takes the fresh default-config arm.
    packet = compile_navigation_family(source_root, resource_dir, prefix="gm_nav",
        destination="page_main", battle_config="default", android_login=True, calibrations=calibrations)
    raw = packet["workflow"]
    raw["name"], raw["title"] = "oas_goto_main_natively_staged", "返回庭院"
    drive = next(state for state in raw["states"] if state["id"] == "gm_nav_drive")
    drive["do"][0]["navigate"]["category"] = "goto_main"
    returned = next(state for state in raw["states"] if state["id"] == "gm_nav_returned")
    returned["do"] = [{"stop": {"reason": "已确认返回庭院", "result": "completed", "verified": True,
                                "evidence": {"source_entry": "oas:GotoMain", "destination": "page_main"}}}]
    obligations = [*packet["source_obligations"], {
        "id": "goto_main_costume", "source": "tasks/Component/Costume/costume_base.py",
        "requirement": "Verify real frames for configured courtyard and other navigation costume variants",
        "blocking": True,
    }]
    raw["oas_goto_main_contract"] = {"source": ENTRY, "source_pins": PINS,
        "original_task_complete": False, "source_obligations": obligations,
        "recognition_repairs": packet["recognition_repairs"]}
    bind_courtyard_costume(source_root, resource_dir, raw, courtyard_costume)
    load_workflow(raw, [resource_dir.parent.parent])
    return {"workflow": raw, "complete": False, "original_task_complete": False, "source_obligations": obligations}
