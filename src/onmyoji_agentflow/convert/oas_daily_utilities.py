"""Pinned OAS Delegation, MemoryScrolls, and SoulsTidy workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


DELEGATION_ENTRY = "tasks/Delegation/script_task.py"
DELEGATION_PINS = {
    DELEGATION_ENTRY: "1e02524eff47969b6a6c3f53a1f25dbee6d684bd046b2c8da6f3b6883d065c15",
    "tasks/Delegation/config.py": "5ad11a5033ae0b37341bbeda6ba9272f5cf2125b01973799df9bd68ce85593e8",
    "tasks/Delegation/assets.py": "33d8bc45ecbf202d8e56972f09cfada8847b3814b978348e5c246578368ae748",
}
DELEGATION_ITEMS = (
    (0, "del_miyoshino_painting", "画"),
    (1, "del_bird_feather", "鸟羽"),
    (2, "del_find_earring", "寻找耳环"),
    (3, "del_cat_boss", "猫老大"),
    (4, "del_miyoshino", "接送"),
    (5, "del_strange_trace", "痕迹"),
)

MEMORY_SCROLLS_ENTRY = "tasks/MemoryScrolls/script_task.py"
MEMORY_SCROLLS_PINS = {
    MEMORY_SCROLLS_ENTRY: "ba0dbec6bb8ec23d54763db1e61286fc2929f448d3e545ff733153cee474cb6e",
    "tasks/MemoryScrolls/config.py": "0a0226b89faa8a844d8edd43f984d50d8c4668e58e086cbaf5e4fe4ade2e8386",
    "tasks/MemoryScrolls/assets.py": "92bb3faaae6573d7198ec3b8be3eb8a01d04fe25f7276e037a707b26b3467b5d",
}
DOUBLE_SCROLLS = ("默认绘卷一", "双绘卷之二")
SCROLL_NUMBERS = ("卷一", "卷二", "卷三", "卷四", "卷五", "卷六")

SOULS_TIDY_ENTRY = "tasks/SoulsTidy/script_task.py"
SOULS_TIDY_PINS = {
    SOULS_TIDY_ENTRY: "886de6677de47171cfce9d8dbf6987e596cc00ed31797fc4b76a8589417da6fb",
    "tasks/SoulsTidy/config.py": "48ded5df338cfb5e01669ee1914eb7759f0265e8ad5a6e8d1184abeebeaa62b2",
    "tasks/SoulsTidy/assets.py": "b110e6ea59a082b14f67601563649b659193fb0782027da6e35f634d2cc53df4",
}


def _verify_pins(source: Path, pins: dict[str, str], label: str) -> None:
    for rel, expected in pins.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"{label} source fingerprint mismatch: {rel}")


def _click_from(docs: dict, name: str, ns: str, delay: int = 1000, *,
                press_ms: int | None = None, recheck: bool = True) -> dict:
    spec = docs[ns][name]
    if spec["type"] in ("click", "long_click"):
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    out = {"click": target, "delay": delay, "recheck": recheck}
    if press_ms is not None:
        out["press_ms"] = press_ms
    return out


def compile_delegation_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS Delegation workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, DELEGATION_PINS, "Delegation")
    nav = compile_navigation_family(
        source, resources, prefix="del_nav", destination="page_delegation",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_delegation_natively_staged", title="式神委派", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update({key: {"default": False} for _, key, _ in DELEGATION_ITEMS})
    raw["params"].update(
        del_limit_seconds={"default": 0, "min": 0, "max": 1800},
        del_next_delay_s={"default": 0, "min": 0, "max": 86400},
    )
    raw["vars"].update(
        del_phase="navigate", del_timer=0, del_idx=0, del_started_ms=0,
        del_started_count=0, del_rewards_claimed=0,
        del_target_delay_s=0, del_observed_ms=0, del_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/Delegation.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("Delegation", "GlobalGame")}
    name_roi = docs["Delegation"]["O_D_NAME"]["roi"]
    done_roi = docs["Delegation"]["O_D_DONE"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"del_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"del_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"del_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="Delegation"):
        return {"res": f"{ns}::{name}"}

    def click(name, delay=1000, ns="Delegation", **kw):
        return _click_from(docs, name, ns, delay, **kw)

    arrived = next(step for step in raw["states"] if step["id"] == "del_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("check_reward", del_timer="elapsed_ms")]
    next(step for step in raw["states"] if step["id"] == "del_nav_drive")["when"] = phase("navigate")

    # check_reward(): collect finished delegations with 3s quiet timer
    state("check_reward_time_limit", "check_reward",
          [expr("del_limit_seconds > 0 and elapsed_ms >= del_limit_seconds * 1000")],
          advance("done_exit", del_exit_reason="'time_limit'"))
    reset_timer = {"set": {"del_timer": "elapsed_ms"}}
    for btn in ("I_REWARDS_GET", "I_REWARDS_CHAT", "I_CHAT_1", "I_CHAT_2", "I_REWARDS_DONE", "I_REWARDS_FALSE"):
        extra = ({"inc": "del_rewards_claimed"},) if btn == "I_REWARDS_GET" else ()
        state(f"reward_{btn.lower()}", "check_reward", [asset(btn)], click(btn, 1000), *extra, reset_timer)
    state("reward_done_break", "check_reward", [asset("I_REWARDS_MIN"), expr("elapsed_ms - del_timer >= 3000")],
          advance("dispatch", del_idx=0))
    state("reward_done_card", "check_reward",
          [asset("I_REWARDS_MIN"), {"ocr_full": {"region": done_roi, "keyword": "完成", "selection": "first_contains"}}],
          {"click_found": True, "projected_rect": ["match_x", "match_y + match_h", "match_w", "match_h"],
           "delay": 1000, "recheck": True}, reset_timer)

    # Dispatch through the 6 configurable delegations
    state("dispatch_time_limit", "dispatch",
          [expr("del_limit_seconds > 0 and elapsed_ms >= del_limit_seconds * 1000")],
          advance("done_exit", del_exit_reason="'time_limit'"))
    state("all_done", "dispatch", [expr("del_idx >= 6")],
          advance("done_exit", del_exit_reason="'all_done'"))
    state("done_exit_target_prep", "done_exit", [expr("del_next_delay_s > 0")],
          advance("stop_target", del_target_delay_s="del_next_delay_s", del_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "式神委派已完成，已按委派时长预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "Delegation",
                "delay_seconds_var": "del_target_delay_s",
                "observed_ms_var": "del_observed_ms",
            },
            "evidence": {"scope": "delegation_target_schedule"},
        }
    })
    state("done_exit_default", "done_exit", [], {
        "stop": {
            "reason": "式神委派已完成",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "Delegation",
            "evidence": {"scope": "delegation_native_path"},
        }
    })
    for idx, param_key, kw in DELEGATION_ITEMS:
        state(f"skip_disabled_{idx}", "dispatch", [expr(f"del_idx == {idx}"), expr(f"not {param_key}")],
              {"set": {"del_idx": idx + 1}})
        state(f"open_found_{idx}", "dispatch",
              [expr(f"del_idx == {idx}"), expr(param_key),
               {"ocr_full": {"region": name_roi, "keyword": kw, "evidence": "complete_keyword"}}],
              {"click_found": True, "delay": 3000, "recheck": True},
              advance("enter_detail", del_started_ms="elapsed_ms"))
        state(f"not_found_{idx}", "dispatch", [expr(f"del_idx == {idx}"), expr(param_key)],
              {"set": {"del_idx": idx + 1}})

    # enter_detail(): jade-safe cancel priority -> I_D_START / I_D_BACK / I_D_SKIP / I_D_CONFIRM
    cancel = asset("I_UI_CANCEL", "GlobalGame")
    state("enter_ready", "enter_detail", [asset("I_D_START")], advance("select_1"))
    state("enter_timeout", "enter_detail", [expr("elapsed_ms - del_started_ms >= 15000")],
          advance("dispatch", del_idx="del_idx + 1"))
    state("enter_cancel_jade", "enter_detail", [cancel],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("enter_already_running", "enter_detail", [asset("I_D_BACK")],
          advance("exit_detail", del_started_ms="elapsed_ms"))
    state("enter_skip", "enter_detail", [asset("I_D_SKIP")], click("I_D_SKIP", 800))
    state("enter_confirm", "enter_detail", [asset("I_D_CONFIRM")], click("I_D_CONFIRM", 800))
    for idx, _, kw in DELEGATION_ITEMS:
        state(f"enter_reclick_{idx}", "enter_detail",
              [expr(f"del_idx == {idx}"), {"ocr_full": {"region": name_roi, "keyword": kw, "evidence": "complete_keyword"}}],
              {"click_found": True, "delay": 3000, "recheck": True})

    state("exit_detail_done", "exit_detail", [{"not": asset("I_D_BACK")}],
          advance("dispatch", del_idx="del_idx + 1"))
    state("exit_detail_timeout", "exit_detail", [expr("elapsed_ms - del_started_ms >= 6000")],
          advance("dispatch", del_idx="del_idx + 1"))
    state("exit_detail_cancel", "exit_detail", [cancel],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("exit_detail_back", "exit_detail", [asset("I_D_BACK")], click("I_D_BACK", 1200))

    # Select 4 shikigami + click C_D_5 & I_D_START
    for slot in range(1, 5):
        next_phase = f"select_{slot + 1}" if slot < 4 else "start_delegation"
        extra = {"del_started_ms": "elapsed_ms"} if slot == 4 else {}
        state(f"slot_{slot}_selected", f"select_{slot}", [asset(f"I_D_SELECT_{slot}")],
              advance(next_phase, **extra))
        state(f"slot_{slot}_click", f"select_{slot}", [asset("I_D_START")], click(f"C_D_{slot}", 1500))

    state("start_done", "start_delegation", [{"not": asset("I_D_START")}],
          advance("dispatch", del_idx="del_idx + 1", del_started_count="del_started_count + 1"))
    state("start_timeout", "start_delegation", [expr("elapsed_ms - del_started_ms >= 10000")],
          advance("dispatch", del_idx="del_idx + 1"))
    state("start_slot5_and_go", "start_delegation", [asset("I_D_START")],
          click("C_D_5", 800), click("I_D_START", 1800, recheck=False))

    raw["oas_delegation_contract"] = {
        "source": DELEGATION_ENTRY,
        "source_pins": {**DELEGATION_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "delegation_live_ocr_and_ribbon_offset",
            "blocking": True,
            "requirement": "Verify O_D_DONE below-ribbon tap offset and jade-cancel protection on live frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_memory_scrolls_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS MemoryScrolls workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, MEMORY_SCROLLS_PINS, "MemoryScrolls")
    nav = compile_navigation_family(
        source, resources, prefix="ms_nav", destination="page_summon",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_memory_scrolls_natively_staged", title="追忆绘卷", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"].update(
        ms_auto_contribute={"default": True},
        ms_double_scrolls={"default": DOUBLE_SCROLLS[0], "choices": list(DOUBLE_SCROLLS)},
        ms_scroll_number={"default": SCROLL_NUMBERS[0], "choices": list(SCROLL_NUMBERS)},
        ms_auto_close_exploration={"default": False},
        ms_allow_local_close_log={"default": False},
        ms_notification_95={"default": False},
        ms_auto_finish_exploration={"default": False},
        ms_exploration_failure_seconds={"default": 86400, "min": 0, "max": 3155760000},
        ms_limit_seconds={"default": 0, "min": 0, "max": 7200},
        ms_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        ms_phase="navigate", ms_wait_start=0, ms_rounds=0, ms_notified_95=False,
        ms_exit_reason="", ms_scroll_completed=False, ms_exploration_woken=False,
        ms_exploration_closed=False, ms_target_delay_s=0, ms_observed_ms=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/MemoryScrolls.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("MemoryScrolls", "GlobalGame")}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"ms_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"ms_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"ms_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="MemoryScrolls"):
        return {"res": f"{ns}::{name}"}

    def click(name, delay=1000, ns="MemoryScrolls", **kw):
        return _click_from(docs, name, ns, delay, **kw)

    arrived = next(step for step in raw["states"] if step["id"] == "ms_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_main", ms_wait_start="elapsed_ms")]
    next(step for step in raw["states"] if step["id"] == "ms_nav_drive")["when"] = phase("navigate")

    # enter_main: wait up to 30s for I_MS_ENTER / handle double scrolls until I_MS_FRAGMENT_S
    state("entered_main", "enter_main", [asset("I_MS_FRAGMENT_S")], advance("check_50"))
    state("double_scroll_2", "enter_main",
          [asset("I_MS_DOUBLE_SCROLLS_ENTER"), expr(f"ms_double_scrolls == {DOUBLE_SCROLLS[1]!r}")],
          click("C_MS_DOUBLE_SCROLLS_2", 1000), click("I_MS_DOUBLE_SCROLLS_ENTER", 1000, recheck=False))
    state("double_scroll_1", "enter_main", [asset("I_MS_DOUBLE_SCROLLS_ENTER")],
          click("I_MS_DOUBLE_SCROLLS_ENTER", 1000))
    state("click_enter", "enter_main", [asset("I_MS_ENTER")], click("I_MS_ENTER", 1000))
    state("enter_timeout", "enter_main", [expr("elapsed_ms - ms_wait_start >= 30000")],
          {"fail": "未在30秒内找到追忆绘卷入口"})

    # Optional small fragment 50 check + cross-task Exploration wake
    state("skip_50_check", "check_50", [expr("not ms_auto_finish_exploration")], advance("enter_scroll"))
    state("reached_50_proceed", "check_50",
          [expr("ms_auto_finish_exploration and ms_exploration_woken"), {"not": asset("I_MS_FRAGMENT_S_VERIFICATION")}],
          advance("enter_scroll"))
    state("reached_50_close_popup", "check_50",
          [expr("ms_auto_finish_exploration and ms_exploration_woken"), asset("I_MS_FRAGMENT_S_VERIFICATION")],
          click("I_MS_FRAGMENT_S", 1500))
    state("open_50_verify", "check_50",
          [expr("ms_auto_finish_exploration and not ms_exploration_woken"),
           {"not": asset("I_MS_FRAGMENT_S_VERIFICATION")}, asset("I_MS_FRAGMENT_S")],
          click("I_MS_FRAGMENT_S", 1500))
    state("reached_50_wake_exploration", "check_50",
          [expr("ms_auto_finish_exploration and not ms_exploration_woken"),
           asset("I_MS_FRAGMENT_S_VERIFICATION"), asset("I_MS_FRAGMENT_S_50")],
          {"oas_wake": {"task": "Exploration", "failure_seconds_param": "ms_exploration_failure_seconds"}},
          {"set": {"ms_exploration_woken": True}})
    state("below_50_fail", "check_50",
          [expr("ms_auto_finish_exploration and not ms_exploration_woken"),
           asset("I_MS_FRAGMENT_S_VERIFICATION"), {"not": asset("I_MS_FRAGMENT_S_50")}],
          {"fail": "小绘卷碎片未达50，按来源失败退出"})

    # Enter target scroll 1..6
    back_red = asset("I_UI_BACK_RED", "GlobalGame")
    back_yellow = asset("I_UI_BACK_YELLOW", "GlobalGame")
    for ph in ("enter_scroll", "inspect_scroll", "contribute"):
        state(f"{ph}_time_limit", ph,
              [expr("ms_limit_seconds > 0 and elapsed_ms >= ms_limit_seconds * 1000")],
              advance("exit_scroll", ms_exit_reason="'time_limit'"))
    state("scroll_entered", "enter_scroll", [back_red], advance("inspect_scroll"))
    for idx, label in enumerate(SCROLL_NUMBERS, start=1):
        state(f"pick_scroll_{idx}", "enter_scroll", [expr(f"ms_scroll_number == {label!r}")],
              click(f"C_MS_SCROLL_{idx}", 1000))

    # Inspect scroll progress & decide contribute vs complete
    state("notify_95_mark", "inspect_scroll",
          [expr("ms_notification_95"), expr("not ms_notified_95"), {"not": asset("I_MS_COMPLETE_95")}],
          {"log": "追忆绘卷进度已达 95%"}, {"set": {"ms_notified_95": True}})
    state("start_contribute", "inspect_scroll",
          [{"any": [asset("I_MS_CONTRIBUTE"), {"not": asset("I_MS_COMPLETE")}]}, expr("ms_auto_contribute")],
          advance("contribute", ms_rounds=0))
    state("skip_contribute", "inspect_scroll",
          [{"any": [asset("I_MS_CONTRIBUTE"), {"not": asset("I_MS_COMPLETE")}]}, expr("not ms_auto_contribute")],
          advance("exit_scroll", ms_exit_reason="'checked_no_contribute'"))
    state("complete_close_exploration_gate", "inspect_scroll",
          [asset("I_MS_COMPLETE"), {"not": asset("I_MS_CONTRIBUTE")},
           expr("ms_auto_close_exploration and not ms_allow_local_close_log")],
          {"fail": "绘卷已完成，自动关闭探索任务需跨任务配置修改契约"})
    state("complete_close_exploration_local", "inspect_scroll",
          [asset("I_MS_COMPLETE"), {"not": asset("I_MS_CONTRIBUTE")},
           expr("ms_auto_close_exploration and ms_allow_local_close_log")],
          {"log": "绘卷已完成，本地标记关闭探索任务"},
          advance("exit_scroll", ms_scroll_completed=True, ms_exploration_closed=True,
                  ms_exit_reason="'scroll_complete_close_exploration'"))
    state("scroll_already_complete", "inspect_scroll",
          [asset("I_MS_COMPLETE"), {"not": asset("I_MS_CONTRIBUTE")}],
          advance("exit_scroll", ms_scroll_completed=True, ms_exit_reason="'scroll_complete'"))

    # Bounded 10-round contribution
    all_zero = {"all": [asset("I_MS_ZERO_S"), asset("I_MS_ZERO_M"), asset("I_MS_ZERO_L")]}
    state("contribute_zero_done", "contribute", [all_zero],
          advance("exit_scroll", ms_exit_reason="'fragments_exhausted'"))
    state("contribute_round_limit", "contribute", [expr("ms_rounds >= 10")],
          advance("exit_scroll", ms_exit_reason="'round_limit'"))
    state("contribute_dismiss_popup", "contribute", [asset("I_MS_CONTRIBUTED")],
          click("C_MS_CONTRIBUTED", 1000))
    state("contribute_round", "contribute", [asset("I_MS_CONTRIBUTE")],
          click("C_MS_MAX_S", 300), click("C_MS_MAX_S", 300, recheck=False),
          click("C_MS_MAX_M", 300, recheck=False), click("C_MS_MAX_M", 300, recheck=False),
          click("C_MS_MAX_L", 300, recheck=False), click("C_MS_MAX_L", 300, recheck=False),
          click("I_MS_CONTRIBUTE", 3000, recheck=False), {"inc": "ms_rounds"})

    # Exit scroll -> exit main -> stop
    state("exit_scroll_red", "exit_scroll", [back_red],
          {"click_found": True, "use_match_size": True, "delay": 1000, "recheck": True})
    state("exit_scroll_done", "exit_scroll", [{"not": back_red}], advance("exit_main"))
    state("exit_main_yellow", "exit_main", [back_yellow], click("I_UI_BACK_YELLOW", 1000, "GlobalGame"))
    state("exit_main_done_target_prep", "exit_main", [{"not": back_yellow}, expr("ms_next_delay_s > 0")],
          advance("stop_target", ms_target_delay_s="ms_next_delay_s", ms_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "追忆绘卷已返回召唤界面并按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "MemoryScrolls",
                "delay_seconds_var": "ms_target_delay_s",
                "observed_ms_var": "ms_observed_ms",
            },
            "evidence": {"scope": "memory_scrolls_target_schedule"},
        }
    })
    state("exit_main_done", "exit_main", [{"not": back_yellow}], {
        "stop": {
            "reason": "追忆绘卷已返回召唤界面",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "MemoryScrolls",
            "evidence": {"scope": "memory_scrolls_native_path"},
        }
    })

    raw["oas_memory_scrolls_contract"] = {
        "source": MEMORY_SCROLLS_ENTRY,
        "source_pins": {**MEMORY_SCROLLS_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "memory_scrolls_notifier_and_cross_task_exploration",
            "blocking": True,
            "requirement": "Bind 95% push notifier and cross-task Exploration schedule/disable mutations",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_souls_tidy_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS SoulsTidy workflow with explicit soul-consumption confirmation."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, SOULS_TIDY_PINS, "SoulsTidy")
    nav = compile_navigation_family(
        source, resources, prefix="st_nav", destination="page_shikigami_records",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_souls_tidy_natively_staged", title="御魂整理", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 900
    bind_schedule(source, raw)
    raw["params"].update(
        st_enable_greed={"default": True},
        st_enable_maneki={"default": True},
        st_confirm_consume={"default": False},
        st_max_donate_rounds={"default": 20, "min": 1, "max": 200},
        st_greed_timeout_s={"default": 15, "min": 0, "max": 120},
        st_sort_mode={"default": "level", "choices": ["level", "time", "type", "location"]},
        st_limit_seconds={"default": 0, "min": 0, "max": 7200},
        st_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        st_phase="navigate", st_feed_count=0, st_donate_rounds=0, st_gold_amount=-1,
        st_first_level="", st_greed_started=-1, st_target_delay_s=0, st_observed_ms=0, st_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/SoulsTidy.yaml", "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {ns: load_yaml(resources / f"{ns}.yaml")["resources"] for ns in ("SoulsTidy", "GlobalGame")}
    overflow_roi = docs["SoulsTidy"]["O_ST_OVERFLOW"]["roi"]
    first_level_roi = docs["SoulsTidy"]["O_ST_FIRSET_LEVEL"]["roi"]
    sort_rois = {k: docs["SoulsTidy"][k]["roi"] for k in (
        "O_ST_SORT_LEVEL_1", "O_ST_SORT_LEVEL_2", "O_ST_SORT_TIME", "O_ST_SORT_TYPE", "O_ST_SORT_LOCATION"
    )}

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"st_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"st_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"st_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="SoulsTidy", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, delay=1000, ns="SoulsTidy", **kw):
        return _click_from(docs, name, ns, delay, **kw)

    arrived = next(step for step in raw["states"] if step["id"] == "st_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("check_enabled")]
    next(step for step in raw["states"] if step["id"] == "st_nav_drive")["when"] = phase("navigate")

    state("both_disabled", "check_enabled", [expr("not st_enable_greed and not st_enable_maneki")], {
        "stop": {
            "reason": "御魂整理未启用贪吃鬼或奉纳，直接结束",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "SoulsTidy",
            "evidence": {"scope": "souls_tidy_disabled"},
        }
    })
    state("enter_souls_start", "check_enabled", [], advance("goto_souls"))

    # goto_souls()
    state("souls_ready", "goto_souls", [asset("I_ST_GREED"), asset("I_ST_TIDY")],
          advance("dismiss_overflow"))
    for btn in ("I_ST_REPLACE", "I_ST_SOULS", "I_ST_SOULS_CLOSE"):
        state(f"goto_{btn.lower()}", "goto_souls", [asset(btn)], click(btn, 1000))
    state("goto_detail", "goto_souls", [], click("C_ST_DETAIL", 2000))

    state("overflow_click", "dismiss_overflow",
          [{"ocr_full": {"region": overflow_roi, "keyword": "确定", "evidence": "complete_keyword"}}],
          {"click_found": True, "delay": 800, "recheck": True}, advance("greed_open"))
    state("overflow_none", "dismiss_overflow", [], advance("greed_open"))

    # Greed ghost phase (up to 3 feeds, gated unless st_confirm_consume=True, with idle timeout exit)
    confirm = asset("I_UI_CONFIRM", "GlobalGame")
    state("greed_skip", "greed_open", [expr("not st_enable_greed")], advance("to_cat"))
    state("greed_habit_ready", "greed_open", [asset("I_ST_GREED_HABIT")],
          click("I_ST_GREED_HABIT", 1000), advance("greed_feed", st_feed_count=0, st_greed_started="elapsed_ms"))
    state("greed_tap_icon", "greed_open", [asset("I_ST_GREED")], click("I_ST_GREED", 1000))

    for ph in ("greed_feed", "maneki_sort", "maneki_select"):
        state(f"{ph}_time_limit", ph,
              [expr("st_limit_seconds > 0 and elapsed_ms >= st_limit_seconds * 1000")],
              advance("back_records", st_exit_reason="'time_limit'"))
    state("greed_init_timer", "greed_feed", [expr("st_greed_started < 0")],
          {"set": {"st_greed_started": "elapsed_ms"}})
    state("greed_unselected", "greed_feed", [asset("I_ST_UNSELECTED")], click("I_ST_UNSELECTED", 800))
    state("greed_confirm_popup", "greed_feed", [confirm],
          {"click_found": True, "use_match_size": True, "delay": 500, "recheck": True})
    state("greed_done_3", "greed_feed", [expr("st_feed_count >= 3")], advance("to_cat"))
    state("greed_consume_gate", "greed_feed", [asset("I_ST_FEED_NOW"), expr("not st_confirm_consume")],
          {"fail": "贪吃鬼吞噬御魂需要显式确认(st_confirm_consume=True)"})
    state("greed_feed_tap", "greed_feed", [asset("I_ST_FEED_NOW"), expr("st_confirm_consume")],
          click("I_ST_FEED_NOW", 3500), {"inc": "st_feed_count"})
    raw["states"][-1].update(sensitive="分解", desc="御魂整理：贪吃鬼吞噬弃置御魂。")
    state("greed_open_habit_retry", "greed_feed", [asset("I_ST_GREED_HABIT")], click("I_ST_GREED_HABIT", 1000))
    state("greed_timeout_exit", "greed_feed",
          [expr("st_greed_started >= 0 and elapsed_ms - st_greed_started >= st_greed_timeout_s * 1000")],
          advance("to_cat", st_exit_reason="'greed_timeout'"))
    state("greed_wait_idle", "greed_feed", [], {"wait": 250})

    # Close greed -> open bongna until I_ST_CAT
    state("cat_ready", "to_cat", [asset("I_ST_CAT")], advance("maneki_abandoned"))
    state("to_cat_unselected", "to_cat", [asset("I_ST_UNSELECTED")], click("I_ST_UNSELECTED", 800))
    state("to_cat_confirm", "to_cat", [confirm],
          {"click_found": True, "use_match_size": True, "delay": 500, "recheck": True})
    state("to_cat_greed_close", "to_cat", [asset("I_ST_GREED_CLOSE")], click("I_ST_GREED_CLOSE", 700))
    state("to_cat_bongna", "to_cat", [asset("I_ST_BONGNA", threshold=0.6)], click("I_ST_BONGNA", 1000))

    # Maneki / bongna phase
    state("maneki_skip", "maneki_abandoned", [expr("not st_enable_maneki")], advance("back_records"))
    state("maneki_abandoned_ok", "maneki_abandoned", [asset("I_ST_ABANDONED_SELECTED")], advance("maneki_sort"))
    state("maneki_abandoned_tap", "maneki_abandoned", [], click("I_ST_ABANDONED_SELECTED", 1500))

    for mode_val, key, kw in (
        ("level", "O_ST_SORT_LEVEL_1", "等级"),
        ("time", "O_ST_SORT_TIME", "时间"),
        ("type", "O_ST_SORT_TYPE", "类型"),
        ("location", "O_ST_SORT_LOCATION", "位置"),
    ):
        state(f"sort_ready_{mode_val}", "maneki_sort",
              [expr(f"st_sort_mode == {mode_val!r}"),
               {"ocr_full": {"region": sort_rois[key], "keyword": kw, "evidence": "complete_keyword"}}],
              advance("maneki_select"))
    state("sort_o_st_sort_level_1_cycle", "maneki_sort",
          [expr("st_sort_mode != 'level'"),
           {"ocr_full": {"region": sort_rois["O_ST_SORT_LEVEL_1"], "keyword": "等级", "evidence": "complete_keyword"}}],
          {"click_found": True, "delay": 1000, "recheck": True})
    for key, kw, dly in (
        ("O_ST_SORT_LEVEL_2", "等级", 600),
        ("O_ST_SORT_TIME", "时间", 2000),
        ("O_ST_SORT_TYPE", "类型", 2000),
        ("O_ST_SORT_LOCATION", "位置", 2000),
    ):
        state(f"sort_{key.lower()}", "maneki_sort",
              [{"ocr_full": {"region": sort_rois[key], "keyword": kw, "evidence": "complete_keyword"}}],
              {"click_found": True, "delay": dly, "recheck": True})

    state("maneki_round_limit", "maneki_select", [expr("st_donate_rounds >= st_max_donate_rounds")],
          advance("back_records", st_exit_reason="'round_limit'"))
    stack_seen = {"any": [asset("I_ST_SOUL_STACK"), asset("I_ST_SOUL_STACK_1")]}
    state("maneki_stack_consume_gate", "maneki_select", [stack_seen, expr("not st_confirm_consume")],
          {"fail": "御魂奉纳消耗需要显式确认(st_confirm_consume=True)"})
    state("maneki_stack_long_press", "maneki_select", [stack_seen, expr("st_confirm_consume")],
          click("L_ONE", 2500, press_ms=1000), advance("maneki_check_gold"))
    state("maneki_lvl0_consume_gate", "maneki_select",
          [{"not": stack_seen}, asset("I_ST_LEVEL_0"), expr("not st_confirm_consume")],
          {"fail": "御魂奉纳消耗需要显式确认(st_confirm_consume=True)"})
    lvl0_ocr = {"any": [
        {"ocr_full": {"region": first_level_roi, "keyword": "+0", "selection": "unique_equals",
                      "evidence": "complete_keyword"}},
        {"ocr_full": {"region": first_level_roi, "keyword": "古", "evidence": "complete_keyword"}},
    ]}
    state("maneki_lvl0_long_press", "maneki_select",
          [{"not": stack_seen}, asset("I_ST_LEVEL_0"), expr("st_confirm_consume"), lvl0_ocr],
          click("L_ONE", 2500, press_ms=1000), advance("maneki_check_gold"))
    state("maneki_no_lvl0_done", "maneki_select", [{"not": stack_seen}, {"not": asset("I_ST_LEVEL_0")}],
          advance("back_records", st_exit_reason="'no_level_0'"))
    state("maneki_non_zero_ocr_done", "maneki_select",
          [{"not": stack_seen}, asset("I_ST_LEVEL_0"), expr("st_confirm_consume"), {"not": lvl0_ocr}],
          advance("back_records", st_exit_reason="'non_zero_level'"))

    state("gold_positive_donate", "maneki_check_gold",
          [{"ocr": "SoulsTidy::O_ST_GOLD", "var": "st_gold_amount", "test": "st_gold_amount > 0"},
           asset("I_ST_DONATE")],
          click("I_ST_DONATE", 5500), advance("maneki_collect"))
    raw["states"][-1].update(sensitive="分解", desc="御魂整理：将已选弃置 +0 御魂进行奉纳分解。")
    state("gold_zero_skip", "maneki_check_gold", [], advance("maneki_select"))

    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    state("collect_confirm", "maneki_collect", [confirm],
          {"click_found": True, "use_match_size": True, "delay": 500, "recheck": True})
    state("collect_reward", "maneki_collect", [reward], click("C_UI_REWARD", 400, "GlobalGame"))
    state("collect_god", "maneki_collect", [asset("I_ST_GOD_PRESENT")], click("C_ST_GOD_PRSENT", 2000))
    state("collect_luck", "maneki_collect", [asset("I_ST_LUCK")], click("C_ST_SOUL_OFFERING_REWARD", 2000))
    state("collect_small_luck", "maneki_collect", [asset("I_ST_SMALL_LUCK")], click("C_ST_SOUL_OFFERING_REWARD", 2000))
    state("collect_redonate", "maneki_collect", [asset("I_ST_DONATE")], click("I_ST_DONATE", 5500))
    state("collect_done", "maneki_collect", [{"not": asset("I_ST_GOLD")}],
          advance("maneki_select", st_donate_rounds="st_donate_rounds + 1"))

    # back_records()
    records = raw["navigation"]["pages"]["page_shikigami_records"]["when"]
    state("returned_records_target_prep", "back_records", [records, expr("st_next_delay_s > 0")],
          advance("stop_target", st_target_delay_s="st_next_delay_s", st_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "御魂整理已完成并返回式神录，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "SoulsTidy",
                "delay_seconds_var": "st_target_delay_s",
                "observed_ms_var": "st_observed_ms",
            },
            "evidence": {"scope": "souls_tidy_target_schedule"},
        }
    })
    state("returned_records", "back_records", [records], {
        "stop": {
            "reason": "御魂整理已完成并返回式神录",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "SoulsTidy",
            "evidence": {"scope": "souls_tidy_native_path"},
        }
    })
    state("back_yellow", "back_records", [asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", 1000, "GlobalGame"))

    raw["oas_souls_tidy_contract"] = {
        "source": SOULS_TIDY_ENTRY,
        "source_pins": {**SOULS_TIDY_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "souls_tidy_consumption_confirmation_and_live",
            "blocking": True,
            "requirement": "Require explicit st_confirm_consume before soul feed/donate and verify +0 OCR on live frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
