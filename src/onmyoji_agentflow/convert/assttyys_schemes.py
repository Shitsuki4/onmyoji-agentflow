"""Compose verified assttyys snapshot entries for offline native replay."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from . import core_handlers, preset_handler, team_handlers, yard_handler
from .assttyys import convert_colors, scheme_definitions
from .handlers import AUDITED_METHODS, UnsupportedHandler, component_handler, literal_handler
from .programs import ASSTTYYS_COMPONENT_REGISTRY, ASSTTYYS_REGISTRY_PINS, CATALOG_VERSION
from .scheme_lifecycle import bind_named_schemes
from ..workflow.schema import bundled_dir, load_workflow
from ..yamlio import load_yaml


_SCHEME_PATH = "src/common/schemeList.ts"
_SCHEME_PIN = "1edf03c377d01e3d7272d7a2f11be9d98706551f80209e0ca1c2f6d4cbdfe8f8"
_CATALOG_PIN = "96e2f2e71d851f0cb42b8738bc7084c056950d20ed5a56186d713ee5285487b5"
_LOCAL_TERMINAL_TARGETS = {"__返回上个方案__", "__停止脚本__"}
_LOCAL_RERUN_TARGETS = _LOCAL_TERMINAL_TARGETS | {"__不做动作__"}
_LOCAL_NOTIFICATION_EFFECTS = frozenset({"source_push", "source_toast", "source_stop", "sleep"})
_CONFIGURED_RERUNS = {
    (0, "next_scheme"): ("after_operation", "切换方案"),
    (2, "next_scheme"): ("no_sushi_switch_enabled", True),
    (4, "teammate_exit_next_scheme"): ("teammate_exit", True),
    (6, "next_scheme"): None,
    (8, "cdSwitchScheme"): ("cdSwitchSchemeEnable", True),
    (12, "next_scheme"): ("afterCountOper", "切换方案"),
    (18, "next_scheme"): None,
    (50, "next_scheme"): ("scheme_switch_enabled", True),
    (302, "next_scheme"): ("scheme_switch_enabled", True),
    (316, "next_scheme"): ("pushResult", False),
    (320, "next_scheme"): None,
    (600, "a_ctivity_hunt_select"): ("a_ctivity_hunt", True),
    (600, "a_ctivity_dojo_select"): ("a_ctivity_dojo", True),
    (600, "a_ctivity_narrow_select"): ("a_ctivity_narrow", True),
    (600, "a_ctivity_huntBoss_select"): ("a_ctivity_huntBoss", True),
    (600, "a_ctivity_banquet_select"): ("a_ctivity_banquet", True),
    (600, "a_ctivity_gateOfHades_select"): ("a_ctivity_gateOfHades", True),
    (600, "next_scheme"): None,
    (609, "next_scheme"): None,
    (690, "next_scheme"): ("scheme_switch_enabled", True),
    (691, "next_scheme"): None,
    (691, "levelUP_scheme"): None,
    (692, "next_scheme"): None,
    (702, "next_scheme"): None,
    (1106, "next_scheme"): None,
}


def _unambiguous_target(target, catalog):
    # The source uses substring matching against the ordered scheme list.
    return (isinstance(target, str) and not target.startswith("__") and target in catalog
            and sum(target in name for name in catalog) == 1)


def _rerun_actions(target):
    if target == "__返回上个方案__":
        return [{"scheme_transition": {"mode": "previous"}}]
    if target == "__停止脚本__":
        return [{"log": "上游方案要求停止脚本，请查看。"}, {"stop": "上游方案要求停止脚本"}]
    if target == "__不做动作__":
        return []
    return [{"scheme_transition": {"mode": "rerun", "target": target}}]


def _local_notification_actions(effects, label):
    """Lower pure source Push/toast/sleep/stop sequences for opt-in local_notifications."""
    if not effects or any(effect.get("effect") not in _LOCAL_NOTIFICATION_EFFECTS for effect in effects):
        return None
    actions, last_text, stopped = [], "", False
    for effect in effects:
        kind = effect["effect"]
        if kind in ("source_push", "source_toast"):
            text = effect.get("text")
            if not isinstance(text, str):
                return None
            rendered = text.replace("${schemeHistory names joined by 、}", label)
            if not stopped:
                actions.append(core_handlers._local_notice(rendered))
            last_text = rendered
        elif kind == "sleep":
            ms = effect.get("ms")
            if type(ms) is not int or ms < 0:
                return None
            if not stopped:
                actions.append({"wait": ms})
        elif kind == "source_stop":
            if not stopped:
                actions.append(core_handlers._local_stop(last_text or "上游方案要求停止脚本"))
                stopped = True
    return actions or None


def _source_local_notifications(packet, label):
    """Find blocking obligations whose entire effect is local notification/stop."""
    targets = {}
    for obligation in packet["source_obligations"]:
        if not obligation.get("blocking", True):
            continue
        actions = _local_notification_actions(obligation.get("ordered_effects", ()), label)
        if not actions:
            continue
        slot = obligation["slot"]
        targets[slot, f"unresolved_source_obligation:{obligation['id']}"] = (actions, obligation)
    if not targets:
        return
    for state in packet["workflow"]["states"]:
        slot = state.get("handler_step", {}).get("slot")
        for index in range(len(state["do"]) - 1, -1, -1):
            action = state["do"][index]
            failure, _, _ = action.get("fail", "").partition(" ")
            match = targets.get((slot, failure))
            if match:
                yield state, index, *match


def _source_reruns(packet, catalog, label, *, local_notifications):
    """Find audited reruns whose entire effect can be bound to a pinned scheme."""
    by_slot = {handler["slot"]: handler["id"] for handler in packet["program"]["handlers"]}
    defaults = {key: spec["default"] for key, spec in packet["program"]["params"].items()}
    targets = {}
    for obligation in packet["source_obligations"]:
        effects = obligation["ordered_effects"]
        kinds = tuple(effect["effect"] for effect in effects)
        prefix_actions = []
        if kinds in (("source_rerun",), ("source_rerun", "sleep")):
            rerun = effects[0]
            delay = effects[1]["ms"] if len(effects) == 2 else None
        elif (local_notifications and kinds in (("source_push", "source_rerun"),
                                              ("source_push", "source_rerun", "sleep"),
                                              ("source_push", "sleep", "source_rerun"),
                                              ("source_push", "sleep", "source_rerun", "sleep"),
                                              ("source_toast", "source_rerun"),
                                              ("source_toast", "source_rerun", "sleep"))):
            push_idx = 0
            rerun_idx = kinds.index("source_rerun")
            prefix_actions = _local_notification_actions(effects[push_idx:rerun_idx], label)
            if not prefix_actions:
                continue
            rerun = effects[rerun_idx]
            delay = effects[rerun_idx + 1]["ms"] if rerun_idx + 1 < len(effects) else None
        else:
            continue
        target = rerun["target"]
        slot = obligation["slot"]
        fid = by_slot[slot]
        current = target is None and fid == 0 and defaults.get("cfg_0_after_operation") == "随机等待"
        if current:
            target = label
        if isinstance(target, dict) and set(target) == {"config"}:
            key = target["config"]
            flag = _CONFIGURED_RERUNS.get((fid, key))
            if fid == 2 and key == "next_scheme" and obligation["condition"].get("config") == "fail":
                flag = ("fail", True)
            elif fid == 316 and key == "next_scheme" and obligation["condition"].get("pushResult") is True:
                flag = ("pushResult", True)
            if (fid, key) in _CONFIGURED_RERUNS and (flag is None or defaults.get(f"cfg_{fid}_{flag[0]}") == flag[1]):
                target = defaults.get(f"cfg_{fid}_{key}")
        local_target = local_notifications and isinstance(target, str) and target in _LOCAL_RERUN_TARGETS
        if ((not current and not local_target and not _unambiguous_target(target, catalog))
                or (delay is not None and type(delay) is not int)):
            continue
        targets[slot, f"unresolved_source_obligation:{obligation['id']}"] = (prefix_actions, target, delay, obligation)
    for state in packet["workflow"]["states"]:
        slot = state.get("handler_step", {}).get("slot")
        for index, action in enumerate(state["do"]):
            failure, _, _ = action.get("fail", "").partition(" ")
            match = targets.get((slot, failure))
            if match:
                yield state, index, *match


def compile_assttyys_scheme(stage_root, title, *, device_hash31=None,
                            config_overrides=None, common_overrides=None, local_notifications=False):
    """Return a guarded candidate and its remaining source obligations.

    Unknown components, mismatching catalogs and unbound targets raise an
    explicit error. The result is based on the supplied inert text, gated by
    pinned sources. This entry point does not submit approval proposals.
    """
    stage = Path(stage_root)
    resources = stage / "resources/upstream/assttyys"
    source = (resources / "programs/src").resolve()

    def raw_source(relative):
        path = (source / (relative + ".txt")).resolve()
        if not path.is_relative_to(source):
            raise UnsupportedHandler(f"snapshot path escapes source root: {relative}")
        return path.read_bytes()

    def verified_text(relative, pin):
        raw = raw_source(relative)
        normalized = raw.replace(b"\r\n", b"\n")
        if not any(hashlib.sha256(data).hexdigest() == pin for data in (raw, normalized)):
            raise UnsupportedHandler(f"snapshot fingerprint mismatch: {relative}")
        return normalized.decode("utf-8")

    verified_text(_SCHEME_PATH, _SCHEME_PIN)
    if local_notifications:
        verified_text(core_handlers.PUSH_SELECTION, core_handlers.PUSH_SELECTION_PIN)
        verified_text("src/system/script.ts", core_handlers.HELPER_PINS["src/system/script.ts"])
    for relative, pin in team_handlers.HELPER_PINS.items():
        verified_text(relative, pin)
    common = source / "src/common"
    schemes = {item["schemeName"]: item for item in scheme_definitions(common, source_suffix=".txt")}
    colors = convert_colors(common, source_suffix=".txt")
    color_file = resources / "colors.yaml"
    if load_yaml(color_file)["resources"] != colors:
        raise UnsupportedHandler("staged colors differ from pinned resource literals")
    colors_pin = hashlib.sha256(color_file.read_bytes()).hexdigest()
    catalog_data = (resources / "programs/index.yaml").read_bytes()
    if hashlib.sha256(catalog_data).hexdigest() != _CATALOG_PIN:
        raise UnsupportedHandler("assttyys catalog fingerprint mismatch")
    catalog = load_yaml(catalog_data)
    if catalog["format"] != CATALOG_VERSION:
        raise UnsupportedHandler("unsupported assttyys snapshot catalog format")
    entries = {entry["id"]: entry for entry in catalog["entries"]}
    pins = load_yaml(bundled_dir() / "translations/component-pins.yaml") or {}

    def check_component_entry(entry):
        material = {"version": CATALOG_VERSION, "id": entry["id"], "extra": {"func_ids": entry["func_ids"]},
                    "files": {relative: hashlib.sha256(raw_source(relative).replace(b"\r\n", b"\n")).hexdigest()
                              for relative in entry["files"]},
                    "resources": {"colors.yaml": colors_pin}}
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest != entry["fingerprint"]:
            raise UnsupportedHandler(f"component catalog fingerprint mismatch: {entry['id']}")

    definitions = {}

    def definition(fid, scheme_name):
        key = (fid, scheme_name if fid == 0 else None)
        if key in definitions:
            return definitions[key]
        entry = entries.get(f"assttyys:func:{fid:03d}")
        if entry is None:
            raise UnsupportedHandler(f"component {fid:03d} is absent from the snapshot")
        if fid in core_handlers.SOURCE_FILES:
            relative = core_handlers.SOURCE_FILES[fid]
            text = verified_text(relative, core_handlers.SOURCE_PINS[fid])
            model = core_handlers.compile_core_handler(text, colors, scheme_history=[scheme_name] if fid == 0 else None,
                device_hash31=device_hash31 if fid == 2 else None, local_notifications=local_notifications)["handler"]
        elif fid in team_handlers.SOURCE_FILES:
            relative = team_handlers.SOURCE_FILES[fid]
            raw = raw_source(relative)
            pin = team_handlers.SOURCE_PINS[fid]
            text = raw.decode("utf-8")
            if hashlib.sha256(raw).hexdigest() != pin:
                text = text.replace("\r\n", "\n")
            packet = team_handlers.compile_team_handler(text, colors)
            model = packet["handler"]
        elif fid == 503:
            relative = yard_handler.SOURCE_FILE
            text = verified_text(relative, yard_handler.SOURCE_PIN)
            model = yard_handler.compile_yard_handler(text, colors, local_notifications=local_notifications)["handler"]
        elif fid == 510:
            relative = preset_handler.SOURCE
            text = verified_text(relative, preset_handler.SOURCE_PIN)
            model = preset_handler._compile(text, colors)
        elif fid == 315:
            relative = preset_handler.BATTLE_SOURCE
            text = verified_text(relative, preset_handler.BATTLE_PIN)
            model = preset_handler.compile_battle_preset(text, colors)
        else:
            if len(entry["entry_files"]) != 1:
                raise UnsupportedHandler(f"component {fid:03d} requires one source entry")
            relative = entry["entry_files"][0]
            if fid in AUDITED_METHODS:
                model = literal_handler(verified_text(relative, AUDITED_METHODS[fid]), colors,
                                        expected_sha256=AUDITED_METHODS[fid])
            else:
                check_component_entry(entry)
                model = component_handler(entry, stage, pins=pins)
                if model is None:
                    raise UnsupportedHandler(f"component {fid:03d} has no pinned native model")
        if entry["entry_files"] != [relative] or model["id"] != fid:
            raise UnsupportedHandler(f"unexpected source entry for component {fid:03d}")
        if "helper_pins_verified" in model["proof"]:
            model["proof"]["helper_pins_verified"] = True
        # Component adapters inline the resources each case references.
        model["resources"] = []
        definitions[key] = model
        return model

    def lowered(label, overrides):
        entry = entries.get("assttyys:scheme:" + label)
        if label not in schemes or not entry or entry.get("scheme_definition") != schemes[label]:
            raise UnsupportedHandler(f"scheme {label!r} does not match the pinned declaration")
        scheme = copy.deepcopy(schemes[label])
        dispatch = entry.get("source_dispatch")
        if dispatch:
            for relative, pin in ASSTTYYS_REGISTRY_PINS.items():
                verified_text(relative, pin)
            declared, effective = scheme["list"], dispatch.get("effective_func_ids")
            skipped = dispatch.get("skipped_unregistered", [])
            if (dispatch.get("registry_sha256") != ASSTTYYS_COMPONENT_REGISTRY
                    or effective != [fid for fid in declared if fid not in skipped]
                    or any(f"assttyys:func:{fid:03d}" in entries for fid in skipped)):
                raise UnsupportedHandler(f"unverified original dispatch exclusions: {label}")
            scheme["list"] = effective
        if "config" in scheme:
            # Keep orphaned source settings in the provenance, but the source
            # dispatch never invokes an operator solely because it has settings.
            scheme["config"] = {key: value for key, value in scheme["config"].items() if int(key) in scheme["list"]}
        for config in (scheme.get("config", {}), overrides):
            if "34" in config:
                config["34"] = preset_handler.normalize_weekly_preset_config(config["34"])
            if "503" in config:
                config["503"] = yard_handler._normalize_config_aliases(config["503"], label=label)
            if "600" in config:
                from .guild_launcher_handlers import normalize_guild_launcher_config
                config["600"] = normalize_guild_launcher_config(config["600"])
            if "603" in config:
                from .narrow_realm_handlers import normalize_narrow_realm_config
                config["603"] = normalize_narrow_realm_config(config["603"])
            if "693" in config:
                from .bounty_mentor_handlers import normalize_master_config
                config["693"] = normalize_master_config(config["693"])
        models = [definition(fid, label) for fid in dict.fromkeys(scheme["list"])]
        realm_config = {**scheme.get("config", {}).get("9", {}), **overrides.get("9", {})}
        invitation_config = {**scheme.get("config", {}).get("8", {}), **overrides.get("8", {})}
        retreat_bound = realm_config.get("scheme_switch_enabled") is True and {0, 1, 2, 9} <= set(scheme["list"])
        invitation_bound = invitation_config.get("inv") is True and {0, 8} <= set(scheme["list"])
        if retreat_bound or invitation_bound:
            models = copy.deepcopy(models)
        if retreat_bound:
            from .realm_handlers import bind_nine_exit_four
            bind_nine_exit_four(models, label)
        if invitation_bound:
            from .realm_handlers import bind_realm_invitation
            attack = next(model for model in models if model["id"] == 8)
            bind_realm_invitation(attack, invitation_config.get("designated_scheme"))
        # AutoJS coerces text config for these typed numeric declarations.
        # Keep the upstream literal in provenance and lower only decimal inputs.
        for model in models:
            actual = scheme.get("config", {}).get(str(model["id"]), {})
            for key, value in actual.items():
                default = model["params"].get(key, {}).get("default")
                if (type(default) is int and isinstance(value, str)
                        and re.fullmatch(r"[0-9]{1,8}(?:\.[0-9]{1,6})?", value)):
                    actual[key] = float(value) if "." in value else int(value)
        result = team_handlers.team_workflow(
            entry["workflow"], models, scheme=scheme, config_overrides=overrides, common_overrides=common_overrides,
            supported_primitives=("handler_control", "scheme_transition"))
        if retreat_bound:
            # The dispatcher owns settlement counts. The pinned 009 cutover
            # resets that count atomically after the selected tile is clicked.
            for state in result["workflow"]["states"]:
                for action in state["do"]:
                    updates = action.get("set", {})
                    if "realm9_retreat_active" in updates:
                        updates["run_times_2"] = f"run_times_2 * (not ({updates['realm9_retreat_active']}))"
        result["workflow"]["team_handler_contract"]["scheme_source"] = {
            "path": _SCHEME_PATH, "sha256_lf": _SCHEME_PIN, "definition": schemes[label], "dispatch": dispatch,
            "catalog_fingerprint": entry["fingerprint"]}
        return result

    root = lowered(title, copy.deepcopy(config_overrides or {}))

    def required_stages(seeds, existing):
        added = dict(seeds)
        pending = list(seeds.values())
        while pending:
            packet = pending.pop()
            for state in packet["workflow"]["states"]:
                for action in state["do"]:
                    if "scheme_transition" not in action:
                        continue
                    target = action["scheme_transition"].get("target")
                    if target is None:
                        continue
                    if target not in existing and target not in added:
                        added[target] = lowered(target, {})
                        pending.append(added[target])
        return added

    def workflows(packets):
        return {label: packet["workflow"] for label, packet in packets.items()}

    stages = required_stages({title: root}, {})
    name = root["workflow"]["name"]
    rejected = set()

    def include(target):
        if target in stages:
            return {}
        if target in rejected:
            return None
        try:
            added = required_stages({target: lowered(target, {})}, stages)
            bind_named_schemes(name, title, workflows({**stages, **added}))
        except UnsupportedHandler:
            rejected.add(target)
            return None
        stages.update(added)
        return added

    pending = list(stages.items())
    while pending:
        label, packet = pending.pop(0)
        lowered_reruns = []
        for state, index, prefix_actions, target, delay, obligation in list(
                _source_reruns(packet, schemes, label, local_notifications=local_notifications)):
            if target not in _LOCAL_RERUN_TARGETS:
                added = include(target)
                if added is None:
                    continue
                pending.extend(added.items())
            replacement = copy.deepcopy(prefix_actions) + _rerun_actions(target)
            if delay is not None and target != "__停止脚本__":
                replacement.append({"wait": delay})
            state["do"][index:index + 1] = replacement
            lowered_reruns.append({**obligation, "bound_target": target, "source_scheme": label})
        if lowered_reruns:
            resolved = {(item["slot"], item["id"]) for item in lowered_reruns}
            packet["source_obligations"] = [o for o in packet["source_obligations"] if (o["slot"], o["id"]) not in resolved]
            for key in ("core_handler_contract", "team_handler_contract"):
                contract = packet["workflow"][key]
                contract["source_obligations"] = packet["source_obligations"]
                if "required_contracts" in contract:
                    contract["required_contracts"] = sorted({req for o in packet["source_obligations"]
                                                             for req in o["required_contracts"]})
            packet["workflow"]["team_handler_contract"]["bound_source_reruns"] = lowered_reruns
        if local_notifications:
            lowered_notices = []
            for state, index, actions, obligation in list(_source_local_notifications(packet, label)):
                state["do"][index:index + 1] = copy.deepcopy(actions)
                lowered_notices.append({**obligation, "lowered_actions": copy.deepcopy(actions), "source_scheme": label})
            if lowered_notices:
                resolved = {(item["slot"], item["id"]) for item in lowered_notices}
                packet["source_obligations"] = [
                    o for o in packet["source_obligations"] if (o["slot"], o["id"]) not in resolved
                ]
                for key in ("core_handler_contract", "team_handler_contract"):
                    contract = packet["workflow"][key]
                    contract["source_obligations"] = packet["source_obligations"]
                    if "required_contracts" in contract:
                        contract["required_contracts"] = sorted({
                            req for o in packet["source_obligations"] for req in o["required_contracts"]
                        })
                packet["workflow"]["team_handler_contract"]["bound_local_notifications"] = lowered_notices

    # These recipients resolve their configured target after consuming the caller's
    # superGlobal.next_scheme_name. Bind only source-backed values.
    receivers = {"返回庭院": ("yard503.target_rerun", "yard503_next_scheme", 3000),
                 "关闭BUFF": ("team40.target_rerun", "team40_next_scheme", None)}
    handoffs = set()
    for recipient, component in (("返回庭院", 503), ("关闭BUFF", 40)):
        if recipient not in stages:
            continue
        settings = stages[recipient]["workflow"]["params"]
        if settings.get(f"cfg_{component}_scheme_switch_enabled", {}).get("default") is not True:
            continue
        target = settings.get(f"cfg_{component}_next_scheme", {}).get("default")
        local = local_notifications and isinstance(target, str) and target in _LOCAL_TERMINAL_TARGETS
        if local or _unambiguous_target(target, schemes):
            handoffs.add((recipient, target))
    for packet in list(stages.values()):
        raw = packet["workflow"]
        for state in raw["states"]:
            forwarded = None
            for action in state["do"]:
                if "super_next_scheme_name" in action.get("set", {}):
                    parameter = action["set"]["super_next_scheme_name"]
                    forwarded = raw["params"].get(parameter, {}).get("default")
                recipient = action.get("scheme_transition", {}).get("target")
                local = local_notifications and isinstance(forwarded, str) and forwarded in _LOCAL_TERMINAL_TARGETS
                if recipient in receivers and (local or _unambiguous_target(forwarded, schemes)):
                    handoffs.add((recipient, forwarded))
    for recipient, target in sorted(handoffs):
        recipient_raw = stages[recipient]["workflow"]
        obligation, variable, delay = receivers[recipient]
        prefix = f"unresolved_source_obligation:{obligation}"
        for position, state in enumerate(recipient_raw["states"]):
            failure = next((index for index, action in enumerate(state["do"])
                            if action.get("fail", "").partition(" ")[0] == prefix), None)
            if failure is not None:
                break
        else:
            continue
        if target not in _LOCAL_TERMINAL_TARGETS and include(target) is None:
            continue
        branch = copy.deepcopy(state)
        branch["id"] += "_named_" + hashlib.sha256(target.encode()).hexdigest()[:12]
        branch["when"] = {"all": [state["when"], {"expr": f"{variable} == {target!r}"}]}
        transition = _rerun_actions(target)
        if delay is not None and target != "__停止脚本__":
            transition.append({"wait": delay})
        branch["do"][failure:failure + 1] = transition
        recipient_raw["states"].insert(position, branch)
        recipient_raw["team_handler_contract"].setdefault("bound_source_reruns", []).append({
            "id": obligation, "source_scheme": recipient, "bound_target": target,
            "condition": branch["when"]["all"][1]})
    if any("scheme_transition" in action for packet in stages.values() for state in packet["workflow"]["states"]
           for action in state["do"]):
        root["workflow"] = bind_named_schemes(name, title, workflows(stages))
        root["source_obligations"] = [{**obligation, "source_scheme": label} for label, packet in stages.items()
                                      for obligation in packet["source_obligations"]]
    load_workflow(root["workflow"])
    return root
