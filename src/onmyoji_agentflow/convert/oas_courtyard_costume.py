"""Bind the pinned OAS main-courtyard costume map to native image guards."""

from __future__ import annotations

import hashlib

from ..workflow.schema import load_resource_file


PINS = {
    "tasks/Component/Costume/costume_base.py": "4467807636bec23d24994091a3f39497e88aa3a66d5d197f94471d1d70021865",
    "tasks/Component/Costume/assets.py": "2e1229086f56f78848f20cd6bc4bdfc5164c9e1d5b4de2ff65aaa3fa5489ad01",
    "tasks/Component/Costume/config.py": "f1f86fa6019b673280a31b7442a4e1df0dbabcfcd11c50c05c7517ad8847dfc2",
    "module/atom/gif.py": "1e20c9cf61868c24b64d6b9269c27cd1e8168db0bb6cc10cc863d32d08991811",
}
CONTROLS = ("I_CHECK_MAIN", "I_MAIN_GOTO_EXPLORATION", "I_MAIN_GOTO_SUMMON", "I_MAIN_GOTO_TOWN")


def bind_courtyard_costume(source, resources, raw, costume, *, bind_pet_house=False):
    """Replace references to this caller's courtyard controls before validation."""
    if type(costume) is not int or not 0 <= costume <= 17:
        raise ValueError("OAS courtyard costume must be an integer from 0 to 17")
    if not costume:
        return
    for filename, expected in PINS.items():
        content = (source / filename).read_text(encoding="utf-8-sig")
        if hashlib.sha256(content.encode()).hexdigest() != expected:
            raise ValueError(f"OAS courtyard costume source fingerprint mismatch: {filename}")

    document = load_resource_file(resources / "Component_Costume.yaml")
    controls = [("GameUi", name) for name in CONTROLS]
    if bind_pet_house:
        controls.append(("Pets", "I_PET_HOUSE"))
    substitutions = {}
    inline = raw.setdefault("inline_resources", {})
    source_assets = {}
    for namespace, name in controls:
        old = f"{namespace}::{name}"
        variants = [f"{name}_17_{letter}" for letter in "ABC"] if costume == 17 else [f"{name}_{costume}"]
        template = document[variants[0]]
        aliases = []
        for variant in variants:
            spec = dict(document[variant])
            if spec["type"] != "image":
                raise ValueError(f"OAS courtyard costume asset is not an image: {variant}")
            # RuleGif uses the first target's search area and threshold for every target.
            if costume in (13, 17):
                for field in ("roi", "roi_expand", "threshold"):
                    if field in template:
                        spec[field] = template[field]
            alias = f"ConfiguredCourtyard::{variant}"
            inline[alias] = spec
            aliases.append(alias)
        substitutions[old] = aliases
        source_assets[old] = variants

    def replace_guards(value):
        if isinstance(value, list):
            return [replace_guards(child) for child in value]
        if not isinstance(value, dict):
            return value
        variants = substitutions.get(value.get("res"))
        if variants:
            guards = [{**value, "res": alias} for alias in variants]
            return guards[0] if len(guards) == 1 else {"any": guards}
        return {key: replace_guards(child) for key, child in value.items()}

    raw["navigation"] = replace_guards(raw["navigation"])
    for state in raw["states"]:
        state["when"] = replace_guards(state["when"])
    if bind_pet_house:
        entry = next(state for state in raw["states"] if state["id"] == "pet_enter_house")
        entry["do"] = [{"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}]
    raw["oas_courtyard_costume_contract"] = {
        "configured_costume": costume, "source_pins": PINS, "source_assets": source_assets,
    }
