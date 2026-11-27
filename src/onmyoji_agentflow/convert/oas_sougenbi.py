"""Pinned OAS Sougenbi workflow (GPL-3.0, runhey and contributors)."""
import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_battle import bind_courtyard_buffs, compile_general_battle
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from .oas_switch_soul import PINS as SOUL_PINS, bind_task_presets
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


ENTRY = "tasks/Sougenbi/script_task.py"
PINS = {
    ENTRY: "45a6f135f975e074e45c59cbc58cffcd7246449f7acd57065ad75c2babc5088e",
    "tasks/Sougenbi/config.py": "a9db493ee83c4820e419523f133302d626f887539ae45f3f7541f406080c51e5",
    "tasks/Sougenbi/assets.py": "e2c79265fee3b9e45be897c20e648f10aae70b1fdb567aa8cc3aaebd1caaf3df",
    "tasks/Component/GeneralBattle/general_battle.py":
        "40eee94e4a73717502a81e016968ae97fb289c838952b5ee4be519c9e3ca798a",
}
MODES = {"贪": "GREED", "嗔": "ANGER", "痴": "FOOLERY"}
BUFF_OPERATIONS = [(name, f"sg_buff_{name}_click") for name in ("gold_50", "gold_100", "exp_50", "exp_100")]


def compile_sougenbi_candidate(source_root, resource_dir, *, calibrations=None):
    source, resources = Path(source_root), Path(resource_dir)
    for path, pin in PINS.items():
        content = (source / path).read_text(encoding="utf-8-sig").encode()
        if hashlib.sha256(content).hexdigest() != pin:
            raise ValueError(f"Sougenbi source fingerprint mismatch: {path}")
    nav = compile_navigation_family(source, resources, prefix="sg_nav", destination="page_soul_zones",
                                    battle_config="default", android_login=True, separate_battle_defaults=True,
                                    calibrations=calibrations)
    battle = compile_general_battle(source, resources, prefix="sg_battle")
    if not battle["guarded_executable"]:
        raise ValueError("Sougenbi could not bind GeneralBattle")
    body = battle["workflow"]
    contract = body["oas_battle_contract"]
    outputs = contract["outputs"]
    raw = nav["workflow"]
    raw.update(name="oas_sougenbi_natively_staged", title="业原火", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 3700
    bind_schedule(source, raw)
    raw["params"].update(sg_mode={"default": "痴", "choices": list(MODES)}, sg_buff_enable={"default": False},
                         sg_max_count={"default": 30, "min": 0}, sg_limit_seconds={"default": 1800, "min": 0, "max": 3600},
                         sg_ticket_reserve={"default": 0, "min": 0, "max": 999},
                         sg_next_delay_s={"default": 0, "min": 0, "max": 604800})
    raw["params"].update({param: {"default": False} for _, param in BUFF_OPERATIONS})
    if set(raw["params"]) & set(body["params"]):
        raise ValueError("Sougenbi navigation and battle configuration overlap")
    raw["params"].update(body["params"])
    raw["vars"].update(body["vars"], sg_phase="entry", sg_tickets=-1, sg_attempts=0, sg_wins=0,
                       sg_live_tickets=-1, sg_post_tickets=-1, sg_ticket_receipts=0, sg_settled_ms=-1,
                       sg_start_taps=0, sg_target_delay_s=0, sg_observed_ms=0, sg_exit_reason="")
    raw["resources"] = sorted(set(raw["resources"] + body["resources"] + [
        "upstream/oas/Sougenbi.yaml", "upstream/oas/GlobalGame.yaml"]))
    documents = {name: load_yaml(resources / f"{name}.yaml")["resources"] for name in ("Sougenbi", "GlobalGame")}
    # The source labels Greed's ticket ROI as Single even though it compares the result to zero.
    raw.setdefault("inline_resources", {})["Sougenbi::O_S_GREED_TICKETS"] = {
        **documents["Sougenbi"]["O_S_GREED"], "mode": "Digit",
    }

    def expr(value):
        return {"expr": value}

    def phase(value):
        return expr(f"sg_phase == {value!r}")

    def advance(value, **updates):
        return {"set": {"sg_phase": repr(value), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"sg_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, namespace="Sougenbi"):
        return {"res": f"{namespace}::{name}"}

    def click(name, delay=1000, namespace="Sougenbi"):
        spec = documents[namespace][name]
        if spec["type"] == "click":
            target = spec["rect"]
        else:
            x, y, w, h = spec["front"]
            target = [x, y, x + w, y + h]
        return {"click": target, "delay": delay, "recheck": True}

    matched_click = {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True}

    buff_calls = [
        bind_courtyard_buffs(raw, source, resources, prefix=f"sg_buff_{leg}", phase_var="sg_phase",
            entry_phase=f"buff_{leg}", resume=resume, operations=BUFF_OPERATIONS,
            enable_param="sg_buff_enable", opening=opening)
        for leg, opening, resume in (("before", True, "presets"), ("after", False, "finished"))
    ]
    state("begin_task", "entry", [], advance("buff_before"))
    bind_task_presets(raw, source, resources, prefix="sg", entry_phase="presets", resume="navigate", category="sougenbi")
    zones = raw["navigation"]["pages"]["page_soul_zones"]["when"]
    exploration = raw["navigation"]["pages"]["page_exploration"]["when"]
    panel, fire = asset("I_S_CHECK_SOUGENBI"), asset("I_S_FIRE")
    locked, unlocked = asset("I_S_TEAM_LOCK"), asset("I_S_TEAM_UNLOCK")
    arrived = next(step for step in raw["states"] if step["id"] == "sg_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("open")]
    next(step for step in raw["states"] if step["id"] == "sg_nav_drive")["when"] = phase("navigate")
    state("panel_open", "open", [panel], {"wait": 500}, advance("lock"))
    state("panel_enter", "open", [zones, asset("I_S_SOUGENBI")], matched_click)
    state("lock_ready", "lock", [panel, {"any": [
        {"all": [expr("lock_team_enable"), locked]}, {"all": [expr("not lock_team_enable"), unlocked]}]}],
          advance("select"))
    state("lock_on", "lock", [panel, unlocked, expr("lock_team_enable")], click("I_S_TEAM_UNLOCK"))
    state("lock_off", "lock", [panel, locked, expr("not lock_team_enable")], click("I_S_TEAM_LOCK"))

    state("count_stop", "cycle", [panel, expr("sg_attempts >= sg_max_count")], advance("exit", sg_exit_reason="'count'"))
    state("time_stop", "cycle", [panel, expr("elapsed_ms >= sg_limit_seconds * 1000")],
          advance("exit", sg_exit_reason="'time'"))
    for name, suffix in MODES.items():
        label = suffix.lower()
        target = asset("I_S_FIRE_" + suffix)
        configured = expr(f"sg_mode == {name!r}")
        ticket = "O_S_GREED_TICKETS" if suffix == "GREED" else f"O_S_{suffix}"
        reads = {"ocr": f"Sougenbi::{ticket}", "mode": "exact_quantity", "var": "sg_tickets"}
        state("mode_ready_" + label, "select", [panel, configured, target], advance("cycle"))
        state("select_" + label, "select", [panel, configured, {"not": target}], click("C_C_" + suffix, 500))
        state("read_" + label, "cycle", [panel, configured, target, reads], advance("tickets"))
        state("unknown_ticket_" + label, "cycle", [panel, configured, target],
              {"fail": "票数无法识别，未发送挑战"})
        positive = {**reads, "var": "sg_live_tickets",
                    "test": "sg_live_tickets == sg_tickets and sg_tickets > sg_ticket_reserve"}
        state("start_" + label, "tickets", [panel, configured, target, positive, fire], matched_click,
              advance("begin_battle", sg_start_taps=1))
        state("retry_start_" + label, "begin_battle",
              [panel, configured, target, positive, expr("sg_start_taps < 3"), fire],
              matched_click, {"inc": "sg_start_taps"})
        state("verified_ticket_" + label, "settled", [
            panel, configured, target,
            {**reads, "var": "sg_post_tickets", "test": "sg_live_tickets - sg_post_tickets == 1"},
        ], {"inc": "sg_ticket_receipts"}, advance("cycle"))
    state("ticket_reserve_reached", "tickets",
          [panel, expr("sg_ticket_reserve > 0 and sg_tickets <= sg_ticket_reserve")],
          advance("exit", sg_exit_reason="'ticket_reserve'"))
    state("no_tickets", "tickets", [panel, expr("sg_tickets == 0")], advance("exit", sg_exit_reason="'no_tickets'"))
    state("start_limit", "begin_battle", [panel, fire], {"fail": "挑战后没有离开业原火入口"})

    persistent = set(contract["composition"]["interval_vars"])
    reset = {key: repr(value) if isinstance(value, str) else value for key, value in body["vars"].items()
             if key not in persistent}
    reset[outputs["current_count"]] = "sg_attempts"
    state("battle_started", "begin_battle", [{"not": fire}, {"not": panel}, {"not": exploration}],
          {"set": reset}, advance("battle"))
    for step in body["states"]:
        step["when"] = {"all": [phase("battle"), step["when"]]}
        if step["id"] in contract["composition"]["return_states"]:
            step["do"][-1:] = [advance("battle_returned", sg_attempts=outputs["current_count"],
                                      sg_wins=f"sg_wins + {outputs['win']}")]
        raw["states"].append(step)
    state("verify_winning_spend", "battle_returned", [expr(outputs["win"])],
          advance("settled", sg_settled_ms="elapsed_ms"))
    state("resume_after_loss", "battle_returned", [], advance("cycle"))
    state("unverified_spend", "settled", [expr("elapsed_ms - sg_settled_ms >= 12000")],
          {"fail": "业原火胜利后无法核对当前阵的一张挑战券扣减"})

    back = asset("I_UI_BACK_YELLOW", "GlobalGame")
    state("returned", "exit", [exploration, {"not": panel}, {"not": zones}], advance("buff_after"))
    state("finished_target_prep", "finished", [expr("sg_next_delay_s > 0")],
          advance("stop_target", sg_target_delay_s="sg_next_delay_s", sg_observed_ms="elapsed_ms"))
    victory = expr("sg_wins > 0 and sg_ticket_receipts == sg_wins")
    target_schedule = {"task": "Sougenbi", "delay_seconds_var": "sg_target_delay_s",
                       "observed_ms_var": "sg_observed_ms"}
    for terminal, schedule in (("stop_target", target_schedule), ("finished", "Sougenbi")):
        state("verified_victory_" + terminal, terminal, [victory], {"stop": {
            "reason": "业原火已核对胜场、挑战券扣减及返回探索", "result": "completed", "verified": True,
            "oas_schedule": schedule, "evidence": {"scope": "sougenbi_victory_ticket_readback_and_return"},
        }})
    state("stop_target", "stop_target", [], {"stop": {"reason": "业原火已退出副本并按排班预约下次运行", "result": "unknown",
          "verified": False,
          "oas_schedule": target_schedule,
          "evidence": {"scope": "sougenbi_target_schedule"}}})
    state("finished", "finished", [], {"stop": {"reason": "业原火已退出副本", "result": "unknown",
          "verified": False, "oas_schedule": "Sougenbi", "evidence": {"scope": "sougenbi_native_path"}}})
    state("exit_back", "exit", [{"any": [panel, zones]}, back], matched_click)
    raw["oas_sougenbi_contract"] = {
        "source": ENTRY, "source_pins": {**PINS, **SCHEDULE_PINS, **SOUL_PINS}, "original_task_complete": False,
        "buff_calls": buff_calls,
        "source_obligations": [*nav["source_obligations"], *battle["source_obligations"],
            *(obligation for invocation in buff_calls for obligation in invocation["source_obligations"]), {
            "id": "sougenbi_buff", "blocking": True,
            "requirement": "Verify the four optional buff setup and cleanup branches on live frames",
        }, {
            "id": "sougenbi_live", "blocking": True,
            "requirement": "Verify all three tickets, numbered and named presets, and battle settlement with real frames",
        }],
        "native_adaptations": ["The Greed source declares Single OCR and compares it to integer zero. "
                               "Require an exact numeric ticket in the pinned crop for every mode before challenge.",
                               "Require absence of the Sougenbi and soul-zones panels before confirming exploration."],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
