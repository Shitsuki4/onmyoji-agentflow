"""Compile navigation callbacks into visible native states, never nested runners.

This is a navigation invocation family, not a complete original OAS task. The
caller must resolve actual Config.general_battle_config behavior (including
None versus AttributeError), constructor/costume asset binding and surrounding
task lifecycle. No model, upstream import, eval or source callback is executed.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from .astpins import source_node_hash
from .handlers import _condition, _expr
from .navigation import read_navigation
from .navigation_native import NavigationCompiler
from .oas import _asset_class_map
from .oas_battle import BATTLE, SOURCE_PINS, _Sources, compile_general_battle
from .oas_courtyard_costume import bind_courtyard_costume
from .oas_login import compile_android_login


def _bind_battle_body(raw, packet, call, config_binding, *, separate_defaults=False):
    body = copy.deepcopy(packet["workflow"])
    if separate_defaults:
        aliases = {key: call + "_config_" + key for key in body["params"]}
        body["vars"].update({alias: body["params"][key]["default"] for key, alias in aliases.items()})
        body["params"] = {}
        for state in body["states"]:
            state["when"] = _condition(state["when"], aliases)
            for action in state["do"]:
                if "set" in action:
                    action["set"] = {key: _expr(value, aliases) for key, value in action["set"].items()}
    elif config_binding == "default":
        body["params"] = {k: {**v, "choices": [v["default"]]} for k, v in body["params"].items()}
    _bind_body(raw, body, call, body["oas_battle_contract"]["outputs"]["return"])


def _bind_body(raw, body, call, result_var):
    params = raw.setdefault("params", {})
    if set(params) & set(body["params"]) or set(raw["vars"]) & set(body["vars"]):
        raise ValueError("navigation callback bindings overlap")
    params.update(body["params"])
    raw["vars"].update(body["vars"])
    for state in body["states"]:
        state["do"] = [{"navigation_return": call} if "stop" in action else action for action in state["do"]]
    raw["states"].extend(body["states"])
    raw["navigation"].setdefault("calls", {})[call] = {
        "states": [state["id"] for state in body["states"]],
        "initial_vars": copy.deepcopy(body["vars"]), "result_var": result_var}
    raw["resources"] = sorted(set(raw["resources"] + body["resources"]))


def compile_navigation_family(source_root, resource_dir, *, prefix="nav", destination="page_main",
                              battle_config, calibrations=None, android_login=False, separate_battle_defaults=False,
                              asset_overrides=None, courtyard_costume=0):
    """Bind native navigation helpers and the source's freshly constructed fallback.

    battle_config='task' retains every runtime GeneralBattle config arm;
    'default' is the source's config=None arm and freezes those default values;
    'missing' is the exact AttributeError arm, returning False without a battle.
    This required binding is a caller contract, not evidence that a task's
    dynamic Config facade has been audited. Remaining obligations are retained.
    """
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", prefix):
        raise ValueError("prefix must be a native identifier")
    if battle_config not in ("task", "default", "missing"):
        raise ValueError("battle_config must bind task/default/missing explicitly")
    if type(separate_battle_defaults) is not bool or (separate_battle_defaults and battle_config != "default"):
        raise ValueError("separate battle defaults require the default battle binding")
    if type(android_login) is not bool:
        raise ValueError("android_login must explicitly bind an Android caller")
    source_root, resource_dir = Path(source_root), Path(resource_dir)
    sources = _Sources(source_root)
    selector = "run_task_or_default_general_battle"
    node = sources.node(BATTLE, selector)
    if source_node_hash(node, style="compact-314") != SOURCE_PINS[(BATTLE, selector)]:
        raise ValueError("review changed fallback dispatch before composing navigation")
    graph = read_navigation(source_root / "tasks", _asset_class_map(source_root / "tasks"))
    call = prefix + "_battle"
    login_call = prefix + "_login"
    compiled = NavigationCompiler(graph, resource_dir, battle_hook=False if battle_config == "missing" else call,
                                  login_hook=login_call if android_login else None,
                                  asset_overrides=asset_overrides).compile(calibrations=calibrations)
    navigation = compiled["navigation"]
    if destination not in navigation["pages"]:
        raise ValueError("destination must be a statically declared page")
    active, done = prefix + "_call_active", prefix + "_arrived"
    raw = {"format": 1, "name": prefix + "_navigation_family", "resource_namespaces": True,
           "resources": compiled["resources"], "navigation": navigation, "params": {},
           "vars": {active: "", done: 0}, "states": [], "default_result": "unknown", "loop_delay_ms": 0,
           "limits": {"timeout_s": 3600, "unknown_timeout_s": 30, "stuck_timeout_s": 3600,
                      "no_progress_timeout_s": 3600, "max_repeat": 1000000}}
    obligations = copy.deepcopy(compiled["unsupported"])
    battle_packet = None
    login_contract = None
    disabled_battle_obligations = {}
    source_files = {item["path"]: item for item in [*compiled["source_files"], *sources.files.values()]}
    if battle_config != "missing":
        battle_packet = compile_general_battle(source_root, resource_dir, prefix=call, current_count=0)
        if not battle_packet["guarded_executable"]:
            raise ValueError("cannot bind unavailable battle family: " + str(battle_packet["unsupported"]))
        navigation["call_active_var"] = active
        _bind_battle_body(raw, battle_packet, call, battle_config, separate_defaults=separate_battle_defaults)
        battle_params = battle_packet["workflow"]["params"]
        for obligation in battle_packet["source_obligations"]:
            required = obligation.get("requires_enabled_param")
            if battle_config == "default" and battle_params.get(required, {}).get("default") is False:
                disabled_battle_obligations[obligation["id"]] = {required: False}
            else:
                obligations.append(obligation)
        source_files.update({item["path"]: item for item in battle_packet["source_files"]})
    if android_login:
        login = compile_android_login(source_root, resource_dir, prefix=login_call)
        login_contract = login["harvest_contract"]
        navigation["call_active_var"] = active
        _bind_body(raw, login, login_call, login_contract["result_var"])
        obligations.extend(login_contract["source_obligations"])
        source_files.update({item["path"]: item for item in login_contract["source_files"]})
    target = copy.deepcopy(navigation["pages"][destination]["when"])
    raw["states"].extend([
        {"id": prefix + "_returned", "when": {"all": [{"expr": done + " == 1"}, target]},
         "do": [{"stop": {"reason": "Native navigation family arrived", "result": "unknown", "verified": False,
                          "evidence": {"scope": "navigation_invocation", "original_task_complete": False}}}]},
        {"id": prefix + "_drive", "when": {"expr": "True"},
         "do": [{"navigate": {"destination": destination, "done_var": done}}]}])
    contract = {"version": 1, "original_task_complete": False, "destination": destination,
        "battle_config_binding": battle_config,
        "battle_defaults_in_callback_locals": separate_battle_defaults,
        "fallback_dispatch": {"path": BATTLE, "start_line": node.lineno, "end_line": node.end_lineno,
                              "ast_sha256": SOURCE_PINS[(BATTLE, selector)]},
        "callbacks": {"handle_battle_page": "AttributeError returns False" if battle_config == "missing" else call},
        "construction": "fresh GeneralBattle on every callback; local count and intervals reset, parent elapsed_ms preserved",
        "battle_contract": battle_packet["workflow"]["oas_battle_contract"] if battle_packet else None,
        "disabled_battle_obligations": disabled_battle_obligations,
        "caller_requirements": ["prove actual Config facade binding, including None versus AttributeError",
            "bind the effective assets after constructor/check_costume; source declarations alone do not prove every skin",
            "compose task lifecycle, resource budgets and scheduling before claiming original-task coverage"],
        "native_adaptations": ["callback bodies are ordinary states executed by the owning Runner with its budgets/approvals",
            "only the outer navigation progress clock is suspended while a callback runs; run/trial/resource limits remain active",
            "reconfirm page after callback return before routing or reporting arrival",
            "interrupted callback cannot be resumed without its planner return context"],
        "source_files": sorted(source_files.values(), key=lambda item: item["path"]),
        "source_obligations": copy.deepcopy(obligations)}
    if login_contract:
        contract["callbacks"]["handle_login_page"] = login_call
        contract["login_contract"] = login_contract
    raw["navigation_family_contract"] = contract
    if courtyard_costume:
        bind_courtyard_costume(source_root, resource_dir, raw, courtyard_costume)
    return {"workflow": raw, "complete": False, "original_task_complete": False,
            "coverage": "navigation-family-fragment", "source_files": contract["source_files"],
            "source_obligations": obligations, "unsupported": copy.deepcopy(obligations),
            "recognition_repairs": compiled["recognition_repairs"]}
