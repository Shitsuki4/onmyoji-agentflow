"""Pinned OAS FloatParade, GuildBanquet, and GuildActivityMonitor workflows (GPL-3.0, runhey and contributors)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .navigation_family import compile_navigation_family
from .oas_schedule import PINS as SCHEDULE_PINS, bind_schedule
from ..workflow.schema import load_workflow
from ..yamlio import load_yaml


FLOAT_PARADE_ENTRY = "tasks/FloatParade/script_task.py"
FLOAT_PARADE_PINS = {
    FLOAT_PARADE_ENTRY: "d1e496ae8483dd8298700a31d87622e15ec5adedcb8023b39d9a9db8ffda3965",
    "tasks/FloatParade/config.py": "75de4b69506cac929d97791f6fb6e496f3a9519ee2c749b9764068f2442ad3b6",
    "tasks/FloatParade/assets.py": "ff31a8e47577430bc370df6d448c37bcf97cb6fbf825cb8801d991f3a744f54c",
    "tasks/Component/RightActivity/right_activity.py":
        "a31b6a09ee22d293b52f14b8ff6779347450b8f9bf244cd52b73706deae8c1b2",
    "tasks/Component/RightActivity/assets.py":
        "0abf16db8b9ff3ffb42c3b1ac4bda1078146bbec017d1f4738f852d461248085",
    "tasks/TalismanPass/assets.py": "01706f557af3ba25ea1eeedf7f12ed24f31f404e0878e1c24a9fc47e30e86690",
}
FP_REWARDS = ("蛇皮/青吉鬼", "金币/勾玉", "体力/樱饼")

GUILD_BANQUET_ENTRY = "tasks/GuildBanquet/script_task.py"
GUILD_BANQUET_PINS = {
    GUILD_BANQUET_ENTRY: "a064bfeb1b5a0486fa3771bd786c0277436d823e245d7416b351a729b95a48ca",
    "tasks/GuildBanquet/config.py": "ce17cf9d27b946c84d4f3161cb9f4a8356c0bf51b342e0f4cc6f5aa00cbaeda7",
    "tasks/GuildBanquet/assets.py": "107174ce834e62fff844cf823f7134ad3372a5df6a6c2a4728cfc13587827ecd",
}
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

GUILD_MONITOR_ENTRY = "tasks/GuildActivityMonitor/script_task.py"
GUILD_MONITOR_PINS = {
    GUILD_MONITOR_ENTRY: "d4a93d7a2fc6c6527db5ba722663af173da1b127afbbff2e17e730294cfb9cc1",
    "tasks/GuildActivityMonitor/config.py": "0d6553f3bd317f478c22f209b169e2be20c2738cf7cb519fc4a523917297e8ac",
    "tasks/GuildActivityMonitor/assets.py": "db6e4355f0135a2854919ba82523f225b61bdceaa46351f7e408f90ec7d0982d",
}
MONITOR_ACTIVITIES = (
    ("dokan", "道馆", "Dokan"),
    ("abyss", "狭间", "AbyssShadows"),
    ("banquet", "宴会", "GuildBanquet"),
    ("retreat", "退治", "DemonRetreat"),
)


def _verify_pins(source: Path, pins: dict[str, str], label: str) -> None:
    for rel, expected in pins.items():
        content = (source / rel).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"{label} source fingerprint mismatch: {rel}")


def _click_from(documents: dict, name: str, namespace: str, delay: int = 1000) -> dict:
    spec = documents[namespace][name]
    if spec["type"] == "click":
        target = spec["rect"]
    else:
        x, y, w, h = spec["front"]
        target = [x, y, x + w, y + h]
    return {"click": target, "delay": delay, "recheck": True}


def compile_float_parade_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS FloatParade workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, FLOAT_PARADE_PINS, "FloatParade")
    nav = compile_navigation_family(
        source, resources, prefix="fp_nav", destination="page_main",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_float_parade_natively_staged", title="花车巡游", loop_delay_ms=200)
    raw["limits"]["timeout_s"] = 600
    bind_schedule(source, raw)
    raw["params"]["oas_success_seconds"]["default"] = 259200
    raw["params"].update(
        fp_level_reward1={"default": FP_REWARDS[2], "choices": list(FP_REWARDS)},
        fp_level_reward2={"default": FP_REWARDS[0], "choices": list(FP_REWARDS)},
        fp_limit_seconds={"default": 0, "min": 0, "max": 1800},
        fp_next_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        fp_phase="navigate", fp_timer=0, fp_enter_taps=0, fp_mileage_claimed=False,
        fp_reward_receipts=0, fp_main_arrived=0, fp_target_delay_s=0, fp_observed_ms=0, fp_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + [
        "upstream/oas/FloatParade.yaml",
        "upstream/oas/Component_RightActivity.yaml",
        "upstream/oas/TalismanPass.yaml",
        "upstream/oas/GlobalGame.yaml",
    ]))
    docs = {
        ns: load_yaml(resources / f"{ns}.yaml")["resources"]
        for ns in ("FloatParade", "Component_RightActivity", "TalismanPass", "GlobalGame")
    }

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"fp_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"fp_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"fp_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def asset(name, ns="FloatParade", **opts):
        return {"res": f"{ns}::{name}", **opts}

    def click(name, delay=1000, ns="FloatParade"):
        return _click_from(docs, name, ns, delay)

    court = raw["navigation"]["pages"]["page_main"]["when"]
    arrived = next(step for step in raw["states"] if step["id"] == "fp_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("enter_toggle", fp_enter_taps=0)]
    next(step for step in raw["states"] if step["id"] == "fp_nav_drive")["when"] = phase("navigate")

    # RightActivity.enter(I_FP_ACCESS) + entry loop until I_FP_UPGRADE
    state("enter_access_visible", "enter_toggle", [asset("I_FP_ACCESS")], advance("enter_open"))
    state("enter_toggle_limit", "enter_toggle", [expr("fp_enter_taps >= 12")],
          {"fail": "未能展开右侧活动入口以找到花车巡游"})
    state("enter_toggle_click", "enter_toggle", [asset("I_TOGGLE_BUTTON", "Component_RightActivity")],
          click("I_TOGGLE_BUTTON", 2000, "Component_RightActivity"), {"inc": "fp_enter_taps"})

    state("entered", "enter_open", [asset("I_FP_UPGRADE")], advance("mileage"))
    state("open_access", "enter_open", [asset("I_FP_ACCESS")], click("I_FP_ACCESS", 800))
    state("open_red_close", "enter_open", [asset("I_FP_RED_CLOSE")], click("I_FP_RED_CLOSE", 1500))
    state("open_gift_close", "enter_open", [asset("I_FP_GIFT_CLOSE")], click("I_FP_GIFT_CLOSE", 3000))

    # get_mileage(): optional mileage entry -> claim -> reward -> back_red until gone
    reward = asset("I_UI_REWARD", "GlobalGame", threshold=0.6)
    back_red = asset("I_UI_BACK_RED", "GlobalGame")
    state("mileage_open", "mileage", [asset("I_ENTRY_MILEAGE")],
          click("I_ENTRY_MILEAGE", 1900), advance("mileage_claim"))
    state("mileage_skip", "mileage", [{"not": asset("I_ENTRY_MILEAGE")}],
          advance("flower", fp_timer="elapsed_ms"))
    state("mileage_claim_tap", "mileage_claim", [asset("I_CLAIM_MILEAGE")],
          click("I_CLAIM_MILEAGE", 1000), {"set": {"fp_mileage_claimed": True}})
    state("mileage_reward_dismiss", "mileage_claim", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"), {"inc": "fp_reward_receipts"}, advance("mileage_close"))
    state("mileage_open_retry", "mileage_claim", [asset("I_ENTRY_MILEAGE")], click("I_ENTRY_MILEAGE", 1900))
    state("mileage_close_back", "mileage_close", [back_red], click("I_UI_BACK_RED", 1800, "GlobalGame"))
    state("mileage_close_done", "mileage_close", [{"not": back_red}], advance("flower", fp_timer="elapsed_ms"))

    # get_flower(): 2-second quiet timer loop
    reset_timer = {"set": {"fp_timer": "elapsed_ms"}}
    state("flower_back_red", "flower", [back_red], click("I_UI_BACK_RED", 800, "GlobalGame"))
    state("flower_batch", "flower", [asset("I_BATCH_SELECTION")], click("I_BATCH_SELECTION", 1500))
    state("flower_batch_confirm", "flower", [asset("I_BATCH_SELECTION_CONFIRM")],
          click("I_BATCH_SELECTION_CONFIRM", 800))
    state("flower_overflow_confirm", "flower", [asset("I_OVERFLOW_CONFIRME", "TalismanPass")],
          click("I_OVERFLOW_CONFIRME", 800, "TalismanPass"), reset_timer)
    for idx, label in enumerate(FP_REWARDS, start=1):
        sel = f"I_FP_SELECT_{idx}"
        state(f"flower_gift1_{idx}", "flower",
              [expr(f"fp_level_reward1 == {label!r}"), asset("I_FP_GIFT_FLAG1"), asset(sel)],
              click(sel, 800), reset_timer)
        state(f"flower_gift2_{idx}", "flower",
              [expr(f"fp_level_reward2 == {label!r}"), asset("I_FP_GIFT_FLAG2"), asset(sel)],
              click(sel, 800), reset_timer)
    state("flower_reward", "flower", [reward],
          click("C_UI_REWARD", 400, "GlobalGame"), {"inc": "fp_reward_receipts"}, reset_timer)
    state("flower_time_limit", "flower",
          [expr("fp_limit_seconds > 0 and elapsed_ms >= fp_limit_seconds * 1000")],
          advance("return_main", fp_main_arrived=0, fp_exit_reason="'time_limit'"))
    state("flower_done", "flower", [expr("elapsed_ms - fp_timer >= 2000")],
          advance("return_main", fp_main_arrived=0))
    state("flower_get_all", "flower", [asset("I_FP_GETALL0")], click("I_FP_GETALL0", 2100), reset_timer)
    state("flower_tasks", "flower", [{"not": asset("I_FP_GETALL0")}, asset("I_FP_TASKS")],
          click("I_FP_TASKS", 2500), reset_timer)
    state("flower_red_point", "flower", [asset("I_RED_POINT_0")], click("I_RED_POINT_0", 1500))

    # Return to main and schedule
    state("returned_main_target_prep", "return_main",
          [court, expr("fp_main_arrived == 1 and fp_next_delay_s > 0")],
          advance("stop_target", fp_target_delay_s="fp_next_delay_s", fp_observed_ms="elapsed_ms"))
    state("stop_target", "stop_target", [], {
        "stop": {
            "reason": "花车巡游已完成并返回庭院，已按排班预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "FloatParade",
                "delay_seconds_var": "fp_target_delay_s",
                "observed_ms_var": "fp_observed_ms",
            },
            "evidence": {"scope": "float_parade_target_schedule"},
        }
    })
    state("returned_main", "return_main", [court, expr("fp_main_arrived == 1")], {
        "stop": {
            "reason": "花车巡游已完成并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "FloatParade",
            "evidence": {"scope": "float_parade_native_path"},
        }
    })
    state("return_back_yellow", "return_main", [{"not": court}, asset("I_UI_BACK_YELLOW", "GlobalGame")],
          click("I_UI_BACK_YELLOW", 1000, "GlobalGame"))
    state("return_main_drive", "return_main", [],
          {"navigate": {"destination": "page_main", "done_var": "fp_main_arrived"}})

    raw["oas_float_parade_contract"] = {
        "source": FLOAT_PARADE_ENTRY,
        "source_pins": {**FLOAT_PARADE_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "float_parade_live",
            "blocking": True,
            "requirement": "Verify RightActivity toggle, mileage claim, level reward selection, and return on live frames",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_guild_banquet_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS GuildBanquet workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, GUILD_BANQUET_PINS, "GuildBanquet")
    nav = compile_navigation_family(
        source, resources, prefix="gb_nav", destination="page_guild",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_guild_banquet_natively_staged", title="寮宴会", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1200
    bind_schedule(source, raw)
    raw["params"].update(
        gb_day_1={"default": "星期三", "choices": list(WEEKDAYS)},
        gb_day_2={"default": "星期六", "choices": list(WEEKDAYS)},
        gb_max_wait_seconds={"default": 920, "min": 1, "max": 1800},
        gb_check_interval_ms={"default": 10000, "min": 100, "max": 60000},
        gb_after_22h={"default": False},
        gb_limit_seconds={"default": 0, "min": 0, "max": 7200},
        gb_next_banquet_delay_s={"default": 0, "min": 0, "max": 604800},
    )
    raw["vars"].update(
        gb_phase="navigate", gb_wait_start=0, gb_last_check=0,
        gb_exit_reason="", gb_retry_delay_s=300, gb_next_delay_s=0, gb_observed_ms=0, gb_main_arrived=0,
    )
    raw["resources"] = sorted(set(raw["resources"] + ["upstream/oas/GuildBanquet.yaml"]))

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"gb_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"gb_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"gb_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    flag = {"res": "GuildBanquet::I_FLAG"}
    court = raw["navigation"]["pages"]["page_main"]["when"]
    arrived = next(step for step in raw["states"] if step["id"] == "gb_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("check_start")]
    next(step for step in raw["states"] if step["id"] == "gb_nav_drive")["when"] = phase("navigate")

    state("started", "check_start", [flag],
          advance("wait_banquet", gb_wait_start="elapsed_ms", gb_last_check="elapsed_ms"))
    state("not_started_late", "check_start", [{"not": flag}, expr("gb_after_22h")],
          advance("return_main", gb_exit_reason="'not_started_after_22h'", gb_main_arrived=0))
    state("not_started_retry", "check_start", [{"not": flag}],
          advance("return_main", gb_exit_reason="'not_started_retry_5m'",
                  gb_retry_delay_s=300, gb_observed_ms="elapsed_ms", gb_main_arrived=0))

    state("banquet_time_limit", "wait_banquet",
          [expr("gb_limit_seconds > 0 and elapsed_ms >= gb_limit_seconds * 1000")],
          advance("return_main", gb_exit_reason="'time_limit'",
                  gb_next_delay_s="gb_next_banquet_delay_s", gb_observed_ms="elapsed_ms", gb_main_arrived=0))
    state("banquet_timeout", "wait_banquet",
          [expr("elapsed_ms - gb_wait_start >= gb_max_wait_seconds * 1000")],
          advance("return_main", gb_exit_reason="'timeout'",
                  gb_next_delay_s="gb_next_banquet_delay_s", gb_observed_ms="elapsed_ms", gb_main_arrived=0))
    state("banquet_ended", "wait_banquet",
          [expr("elapsed_ms - gb_last_check >= gb_check_interval_ms"), {"not": flag}],
          advance("return_main", gb_exit_reason="'ended'",
                  gb_next_delay_s="gb_next_banquet_delay_s", gb_observed_ms="elapsed_ms", gb_main_arrived=0))
    state("banquet_ongoing_recheck", "wait_banquet",
          [expr("elapsed_ms - gb_last_check >= gb_check_interval_ms"), flag],
          {"set": {"gb_last_check": "elapsed_ms"}}, {"wait": 1000})
    state("banquet_wait_tick", "wait_banquet", [], {"wait": 1000})

    state("returned_retry_5m", "return_main",
          [court, expr("gb_main_arrived == 1"), expr("gb_exit_reason == 'not_started_retry_5m'")], {
              "stop": {
                  "reason": "未检测到寮宴会，5分钟后重试",
                  "result": "unknown",
                  "verified": False,
                  "oas_schedule": {
                      "task": "GuildBanquet",
                      "delay_seconds_var": "gb_retry_delay_s",
                      "observed_ms_var": "gb_observed_ms",
                  },
                  "evidence": {"scope": "guild_banquet_retry"},
              }
          })
    state("returned_after_22h", "return_main",
          [court, expr("gb_main_arrived == 1"), expr("gb_exit_reason == 'not_started_after_22h'")],
          {"fail": "超过22点未检测到寮宴会，需按失败调度策略处理"})
    state("returned_complete_target", "return_main",
          [court, expr("gb_main_arrived == 1"), expr("gb_next_delay_s > 0")], {
              "stop": {
                  "reason": "寮宴会结束并返回庭院，已按排班预约下次宴会",
                  "result": "unknown",
                  "verified": False,
                  "oas_schedule": {
                      "task": "GuildBanquet",
                      "delay_seconds_var": "gb_next_delay_s",
                      "observed_ms_var": "gb_observed_ms",
                  },
                  "evidence": {"scope": "guild_banquet_weekday_target"},
              }
          })
    state("returned_complete", "return_main", [court, expr("gb_main_arrived == 1")], {
        "stop": {
            "reason": "寮宴会结束并返回庭院",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "GuildBanquet",
            "evidence": {"scope": "guild_banquet_native_path"},
        }
    })
    state("return_main_drive", "return_main", [],
          {"navigate": {"destination": "page_main", "done_var": "gb_main_arrived"}})

    raw["oas_guild_banquet_contract"] = {
        "source": GUILD_BANQUET_ENTRY,
        "source_pins": {**GUILD_BANQUET_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "guild_banquet_weekday_schedule_rewrite",
            "blocking": True,
            "requirement": "Bind set_config/plan_next_run weekday schedule mutation and live banquet flag observation",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw


def compile_guild_activity_monitor_candidate(source_root, resource_dir, *, calibrations=None):
    """Compile pinned OAS GuildActivityMonitor workflow."""
    source, resources = Path(source_root), Path(resource_dir)
    _verify_pins(source, GUILD_MONITOR_PINS, "GuildActivityMonitor")
    nav = compile_navigation_family(
        source, resources, prefix="gam_nav", destination="page_main",
        battle_config="default", android_login=True, calibrations=calibrations,
    )
    raw = nav["workflow"]
    raw.update(name="oas_guild_activity_monitor_natively_staged", title="阴阳寮活动监控", loop_delay_ms=250)
    raw["limits"]["timeout_s"] = 1800
    bind_schedule(source, raw)
    raw["params"].update(
        gam_in_run_days={"default": True},
        gam_use_ocr={"default": False},
        gam_monitor_seconds={"default": 900, "min": 1, "max": 7200},
        gam_detection_interval_ms={"default": 30000, "min": 100, "max": 120000},
        gam_recheck_minutes={"default": 5, "min": 1, "max": 60},
        gam_recheck_on_timeout={"default": False},
        gam_next_run_delay_s={"default": 0, "min": 0, "max": 604800},
        gam_dokan={"default": True},
        gam_abyss={"default": True},
        gam_banquet={"default": True},
        gam_retreat={"default": True},
        gam_dokan_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        gam_abyss_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        gam_banquet_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
        gam_retreat_failure_seconds={"default": 21600, "min": 0, "max": 3155760000},
    )
    raw["vars"].update(
        gam_phase="entry", gam_start_ms=0, gam_init_keyword="", gam_detected_keyword="",
        gam_detected_task="", gam_target_delay_s=0, gam_observed_ms=0, gam_exit_reason="",
    )
    raw["resources"] = sorted(set(raw["resources"] + ["upstream/oas/GuildActivityMonitor.yaml"]))
    notify_roi = load_yaml(resources / "GuildActivityMonitor.yaml")["resources"]["O_GUILD_ACTIVITY_NOTIFY"]["roi"]

    def expr(val):
        return {"expr": val}

    def phase(val):
        return expr(f"gam_phase == {val!r}")

    def advance(val, **updates):
        return {"set": {"gam_phase": repr(val), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": f"gam_{name}", "when": {"all": [phase(where), *guards]}, "do": list(actions)})

    def notify_match(keyword):
        return {"ocr_full": {"region": notify_roi, "keyword": keyword, "evidence": "complete_keyword"}}

    state("skip_day_target", "entry", [expr("not gam_in_run_days and gam_next_run_delay_s > 0")],
          advance("stop_target", gam_target_delay_s="gam_next_run_delay_s",
                  gam_observed_ms="elapsed_ms", gam_exit_reason="'skip_day'"))
    state("skip_day", "entry", [expr("not gam_in_run_days")], {
        "stop": {
            "reason": "今日不在寮活动监控运行日期内",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "GuildActivityMonitor",
            "evidence": {"scope": "guild_activity_monitor_skip_day"},
        }
    })
    state("adb_mode_unbound", "entry", [expr("not gam_use_ocr")],
          {"fail": "adb dumpsys notification --noredact 系统通知读取需原生设备通知契约"})
    state("entry_to_nav", "entry", [expr("gam_use_ocr")], advance("navigate"))

    arrived = next(step for step in raw["states"] if step["id"] == "gam_nav_returned")
    arrived["when"]["all"].append(phase("navigate"))
    arrived["do"] = [advance("init_ocr", gam_start_ms="elapsed_ms")]
    next(step for step in raw["states"] if step["id"] == "gam_nav_drive")["when"] = phase("navigate")

    for key, kw, _ in MONITOR_ACTIVITIES:
        state(f"init_seen_{key}", "init_ocr", [expr(f"gam_{key}"), notify_match(kw)],
              advance("monitor", gam_init_keyword=repr(kw)))
    state("init_none", "init_ocr", [], advance("monitor", gam_init_keyword="''"))

    state("timeout_recheck", "monitor",
          [expr("gam_recheck_on_timeout and elapsed_ms - gam_start_ms >= gam_monitor_seconds * 1000")],
          advance("stop_target", gam_target_delay_s="gam_recheck_minutes * 60",
                  gam_observed_ms="elapsed_ms", gam_exit_reason="'timeout_recheck'"))
    state("timeout", "monitor", [expr("elapsed_ms - gam_start_ms >= gam_monitor_seconds * 1000")], {
        "stop": {
            "reason": "阴阳寮活动监控时间到",
            "result": "unknown",
            "verified": False,
            "oas_schedule": "GuildActivityMonitor",
            "evidence": {"scope": "guild_activity_monitor_timeout"},
        }
    })
    for key, kw, task_name in MONITOR_ACTIVITIES:
        state(
            f"trigger_{key}", "monitor",
            [expr(f"gam_{key}"), expr(f"gam_init_keyword != {kw!r}"), notify_match(kw)],
            {"set": {"gam_detected_keyword": repr(kw), "gam_detected_task": repr(task_name)}},
            {"oas_wake": {"task": task_name, "failure_seconds_param": f"gam_{key}_failure_seconds"}},
            {
                "stop": {
                    "reason": f"检测到寮活动通知({kw})，已通过原生调度唤醒 {task_name}",
                    "result": "unknown",
                    "verified": False,
                    "oas_schedule": "GuildActivityMonitor",
                    "evidence": {"scope": f"guild_activity_monitor_wake_{key}"},
                }
            },
        )
    state("poll_wait", "monitor", [], {"wait": 1000})
    state("stop_target_done", "stop_target", [], {
        "stop": {
            "reason": "阴阳寮活动监控已按排班/重检间隔预约下次运行",
            "result": "unknown",
            "verified": False,
            "oas_schedule": {
                "task": "GuildActivityMonitor",
                "delay_seconds_var": "gam_target_delay_s",
                "observed_ms_var": "gam_observed_ms",
            },
            "evidence": {"scope": "guild_activity_monitor_target_schedule"},
        }
    })

    raw["oas_guild_activity_monitor_contract"] = {
        "source": GUILD_MONITOR_ENTRY,
        "source_pins": {**GUILD_MONITOR_PINS, **SCHEDULE_PINS},
        "original_task_complete": False,
        "source_obligations": [*nav["source_obligations"], {
            "id": "guild_activity_monitor_adb_and_cross_task_dispatch",
            "blocking": True,
            "requirement": "Bind ADB dumpsys notification reader, weekday schedule calculation, and cross-task trigger dispatch",
        }],
    }
    load_workflow(raw, [resources.parent.parent])
    return raw
