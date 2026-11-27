"""Bind pinned handler workflows to literal assttyys rerun targets."""
from __future__ import annotations

import copy

from ..errors import WorkflowError
from ..vision.regions import parameter_click_rect
from ..workflow.schema import Workflow
from ..workflow.scheme_lifecycle import ACTIVE_SCHEME, CLOCKS
from .handlers import UnsupportedHandler


def bind_named_schemes(name, initial, stages):
    """Keep all candidate actions, resources and budgets in one native run.

    Each stage has fixed source configuration. Explicit targets must be staged.
    A previous-scheme transition resolves against the current run's history.
    """
    if initial not in stages:
        raise UnsupportedHandler("initial scheme is missing")
    stages = copy.deepcopy(stages)
    base = stages[initial]
    dispatch_keys = ("phase_var", "last_id_var", "last_ms_var", "common_config")
    stage_keys = {"format", "name", "title", "vars", "params", "states",
                  "resources", "inline_resources", "resource_namespaces", "handler_dispatch",
                  "loop_delay_ms", "similarity", "limits", "core_handler_contract",
                  "yard_handler_contract", "team_handler_contract"}
    phase = base["handler_dispatch"]["phase_var"]
    preserve = {base["handler_dispatch"][key] for key in ("last_id_var", "last_ms_var")} | {"super_next_scheme_name"}
    states, resource_refs, inline_resources, stage_defaults, schemes = [], [], {}, {}, {}
    for index, (label, stage) in enumerate(stages.items()):
        dispatch = stage.get("handler_dispatch", {})
        if (stage.keys() - stage_keys
                or any(dispatch.get(key) != base["handler_dispatch"][key] for key in dispatch_keys)
                or any(stage.get(key) != base.get(key) for key in ("format", "loop_delay_ms", "similarity",
                                                                 "limits", "resource_namespaces"))):
            raise UnsupportedHandler(f"{label}: scheme requires incompatible native contracts")
        configs = Workflow(stage).validate_params()
        variables = stage["vars"]
        if set(configs) & set(variables) or ACTIVE_SCHEME in (set(configs) | set(variables)):
            raise UnsupportedHandler(f"{label}: conflicting scheme variables and configuration")
        defaults = {**variables, **configs}
        stage_defaults[label] = defaults
        handled_var = dispatch["last_handled_ms_var"]
        schemes[label] = {"clocks": sorted(CLOCKS & set(defaults)), "handled_var": handled_var}
        for ref in stage.get("resources", []):
            if ref not in resource_refs:
                resource_refs.append(ref)
        for alias, resource in stage.get("inline_resources", {}).items():
            if alias in inline_resources and inline_resources[alias] != resource:
                raise UnsupportedHandler(f"{label}: conflicting resource {alias}")
            inline_resources[alias] = resource
        for state in stage["states"]:
            state["id"] = f"scheme_{index}_{state['id']}"
            state["source_scheme"] = label
            state["when"] = {"all": [{"expr": f"{ACTIVE_SCHEME} == {label!r}"}, state["when"]]}
            actions = state.get("do", [])
            for position, action in enumerate(actions):
                click = action.get("click")
                if isinstance(click, dict) and set(click) & {"xy_param", "x_param", "y_param", "rect_param"}:
                    try:
                        action["click"] = parameter_click_rect(click, configs)
                    except (KeyError, WorkflowError) as error:
                        raise UnsupportedHandler(f"{label}: invalid fixed click coordinates in {state['id']}") from error
                if "scheme_transition" not in action:
                    continue
                transition = action["scheme_transition"]
                target = transition.get("target")
                if transition["mode"] == "rerun" and target not in stages:
                    raise UnsupportedHandler(f"{label}: unbound rerun target {target!r}")
                suffix = actions[position + 1:]
                if (not suffix or set(suffix[-1].get("set", {})) != {phase}
                        or any(set(step) != {"wait"} for step in suffix[:-1])):
                    raise UnsupportedHandler(f"{label}: rerun has unsupported caller continuation")
                # The old worker is interrupted; 604's trailing sleep cannot
                # delay the target worker. Retain the original suffix for review.
                state["interrupted_after_rerun"] = suffix
                state["do"] = actions[:position + 1]
                break
            states.append(state)
    all_local = set().union(*(d.keys() for d in stage_defaults.values())) - preserve
    for label, spec in schemes.items():
        spec["reset"] = {key: stage_defaults[label].get(key) for key in sorted(all_local)}
    persistent = {key: base["vars"][key] for key in sorted(preserve & base["vars"].keys())}
    # A shared slot introduced only by a target still needs its source default.
    if "super_next_scheme_name" not in persistent and any("super_next_scheme_name" in d for d in stage_defaults.values()):
        persistent["super_next_scheme_name"] = ""
    return {key: base[key] for key in ("format", "loop_delay_ms", "similarity", "limits", "resource_namespaces",
                                       "handler_dispatch") if key in base} | {
        "name": name, "vars": {**schemes[initial]["reset"], **persistent, ACTIVE_SCHEME: initial},
        "states": states, "resources": resource_refs, "inline_resources": inline_resources,
        "scheme_lifecycle": {"version": 1, "schemes": schemes},
        "scheme_source_contracts": {label: {key: stage[key] for key in (
            "handler_dispatch", "core_handler_contract", "yard_handler_contract", "team_handler_contract"
        ) if key in stage} for label, stage in stages.items()},
    }
