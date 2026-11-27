"""Scheduling rules for OAS task finish intervals and explicit targets."""
from datetime import datetime, time, timedelta
from random import randint

from ..errors import WorkflowError


TASKS = (
    "AbyssShadows", "ActivityShikigami", "AreaBoss", "AutoCheckinBigGod",
    "BondlingFairyland", "BudokaiTournament", "CollectiveMissions",
    "DailyTrifles", "Delegation", "DemonEncounter", "DemonRetreat", "Dokan",
    "Duel", "DyeTrials", "EternitySea", "EvoZone", "ExperienceYoukai",
    "Exploration", "FallenSun", "FindJade", "FloatParade", "FrogBoss",
    "GoldYoukai", "GoryouRealm", "GuildActivityMonitor", "GuildBanquet",
    "HeroTest", "Hunt", "Hyakkiyakou", "KekkaiActivation", "KekkaiUtilize",
    "KittyShop", "MemoryScrolls", "MetaDemon", "MysteryShop", "Nian",
    "Orochi", "OtherWorldTwilight", "Pets", "Quiz", "RealmRaid", "Restart",
    "RichMan", "RyouToppa", "Secret", "SixRealms", "Sougenbi", "SoulsTidy",
    "Tako", "TalismanPass", "TrueOrochi", "WantedQuests", "WeeklyTrifles",
)
WAKE_WORKFLOWS = {
    "TrueOrochi": "oas_true_orochi_natively_staged",
    "TalismanPass": "oas_talisman_pass_natively_staged",
    "RealmRaid": "oas_realm_raid_natively_staged",
    "Exploration": "oas_exploration_natively_staged",
    "MemoryScrolls": "oas_memory_scrolls_natively_staged",
    "Dokan": "oas_dokan_natively_staged",
    "AbyssShadows": "oas_abyss_shadows_natively_staged",
    "GuildBanquet": "oas_guild_banquet_natively_staged",
    "DemonRetreat": "oas_demon_retreat_natively_staged",
    "SoulsTidy": "oas_souls_tidy_natively_staged",
    "WantedQuests": "oas_wanted_quests_natively_staged",
    "BondlingFairyland": "oas_bondling_fairyland_natively_staged",
    "Secret": "oas_secret_natively_staged",
}
PARAMS = {
    "oas_success_seconds": {"default": 86400, "min": 0, "max": 3155760000},
    "oas_server_update_seconds": {"default": 32400, "min": 0, "max": 86399},
    "oas_delay_days": {"default": 1, "min": 1, "max": 31},
    "oas_float_seconds": {"default": 0, "min": 0, "max": 86399},
}
SERVER_TIMING = {name: spec for name, spec in PARAMS.items() if name != "oas_success_seconds"}


def validate_schedule(schedule, parameters, variables):
    task = schedule
    if isinstance(schedule, dict):
        if set(schedule) != {"task", "delay_seconds_var", "observed_ms_var"}:
            raise WorkflowError("OAS 目标调度需要 task、delay_seconds_var 和 observed_ms_var")
        for key in ("delay_seconds_var", "observed_ms_var"):
            name = schedule[key]
            if not isinstance(name, str) or type(variables.get(name)) is not int:
                raise WorkflowError(f"OAS 目标调度的 {key} 必须引用已声明的整数变量")
        task = schedule["task"]
    if task not in TASKS:
        raise WorkflowError("未知的 OAS 调度任务")
    for name, bounds in PARAMS.items():
        spec = parameters.get(name)
        if (not isinstance(spec, dict) or set(spec) != set(bounds)
                or spec["min"] != bounds["min"] or spec["max"] != bounds["max"]
                or type(spec["default"]) is not int or not bounds["min"] <= spec["default"] <= bounds["max"]):
            raise WorkflowError(f"OAS 调度需要有效的 {name} 整数参数")


def validate_wake(wake, parameters):
    if (not isinstance(wake, dict) or set(wake) - {"task", "failure_seconds_param", "server_params"}
            or not isinstance(wake.get("task"), str) or wake["task"] not in WAKE_WORKFLOWS):
        raise WorkflowError("OAS 任务接续需要已绑定的调度目标")
    if "failure_seconds_param" in wake:
        key = wake["failure_seconds_param"]
        spec = parameters.get(key) if isinstance(key, str) else None
        if (not isinstance(spec, dict) or set(spec) != {"default", "min", "max"}
                or any(type(spec[name]) is not int for name in spec)
                or not 0 <= spec["min"] <= spec["default"] <= spec["max"] <= 3155760000):
            raise WorkflowError("OAS 任务接续需要有效的失败间隔整数参数")
    if "server_params" in wake:
        binding = wake["server_params"]
        if not isinstance(binding, dict) or set(binding) != set(SERVER_TIMING):
            raise WorkflowError("OAS 任务接续需要完整的目标服务器调度参数")
        for name, bounds in SERVER_TIMING.items():
            key = binding[name]
            spec = parameters.get(key) if isinstance(key, str) else None
            if (not isinstance(spec, dict) or set(spec) != set(bounds)
                    or spec["min"] != bounds["min"] or spec["max"] != bounds["max"]
                    or type(spec["default"]) is not int or not bounds["min"] <= spec["default"] <= bounds["max"]):
                raise WorkflowError(f"OAS 任务接续需要目标任务的有效整数参数 {name}")


def wake_next_run(start_at, observed_at, failure_seconds, server_params=None):
    """Apply an explicit wake, optionally bounded by the configured failure interval."""
    due = observed_at if failure_seconds is None else min(start_at + failure_seconds, observed_at)
    due = float(int(due))
    if server_params is not None:
        return next_run(due, server_params, target_delay_seconds=0, calendar_at=observed_at)
    return due


def next_run(reference_at, params, *, target_delay_seconds=None, calendar_at=None):
    """Apply the pinned success/finish/server branch using host local time."""
    reference = datetime.fromtimestamp(reference_at).replace(microsecond=0)
    jitter = randint(0, params["oas_float_seconds"])
    seconds = params["oas_server_update_seconds"]
    if seconds == 32400:
        delay = params["oas_success_seconds"] if target_delay_seconds is None else target_delay_seconds
        return (reference + timedelta(seconds=delay + jitter)).timestamp()

    calendar_date = reference.date() if calendar_at is None else datetime.fromtimestamp(calendar_at).date()
    day = calendar_date + timedelta(days=params["oas_delay_days"])
    midnight = datetime.combine(day, time.min)
    target = midnight + timedelta(seconds=seconds + jitter)
    if jitter:
        target = min(target, datetime.combine(day, time(23, 50)))
    return target.timestamp()
