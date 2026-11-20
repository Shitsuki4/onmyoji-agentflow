"""Game-day task and resource accounting helpers."""
from __future__ import annotations

import datetime as dt
import math
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import BudgetExceeded


def _zone(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as error:
        if tz_name in ("Asia/Shanghai", "Asia/Chongqing", "Asia/Beijing"):
            return timezone(timedelta(hours=8), "CST")
        raise ValueError(f"未知服务器时区：{tz_name}") from error


def now_local(tz_name: str = "Asia/Shanghai", now: dt.datetime | None = None) -> dt.datetime:
    zone = _zone(tz_name)
    if now is None:
        return dt.datetime.now(zone)
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def period_keys(tz_name: str = "Asia/Shanghai", now: dt.datetime | None = None, reset_hour: int = 0) -> tuple[str, str]:
    if isinstance(reset_hour, bool) or not isinstance(reset_hour, int) or not 0 <= reset_hour <= 23:
        raise ValueError("游戏重置小时必须是 0–23 的整数")
    value = now_local(tz_name, now) - dt.timedelta(hours=reset_hour)
    iso = value.isocalendar()
    return value.date().isoformat(), f"{iso.year}-W{iso.week:02d}"


def _task_status(current, target, claimed=False) -> str:
    if claimed:
        return "claimed"
    if current is not None and target is not None and current >= target:
        return "ready_to_claim"
    if current is not None:
        return "in_progress"
    return "unknown"


class GameLedger:
    def __init__(self, store, account: str = "default", timezone: str = "Asia/Shanghai", reset_hour: int = 0):
        self.store = store
        self.account = account
        self.timezone = timezone
        self.reset_hour = reset_hour

    def periods(self, now=None):
        return period_keys(self.timezone, now, self.reset_hour)

    def record_task(self, scope: str, task_key: str, current=None, target=None, claimed=None,
                    verified: bool | None = None, evidence: dict | None = None, now=None):
        day, week = self.periods(now)
        if scope not in ("daily", "weekly"):
            raise ValueError("scope 必须是 daily 或 weekly")
        if (not task_key or (current is not None and (type(current) is not int or current < 0))
                or (target is not None and (type(target) is not int or target <= 0))
                or (current is not None and target is not None and current > target)):
            raise ValueError("任务名、进度或目标无效")
        period = day if scope == "daily" else week if scope == "weekly" else day
        status = _task_status(current, target, bool(claimed))
        return self.store.upsert_task(self.account, period, scope, task_key, current, target, claimed,
                                      status, verified, evidence)

    def snapshot(self, scope: str | None = None, now=None):
        day, week = self.periods(now)
        if scope is None:
            return self.store.tasks(self.account, day, "daily") + self.store.tasks(self.account, week, "weekly")
        if scope not in ("daily", "weekly"):
            raise ValueError("scope 必须是 daily 或 weekly")
        period = day if scope == "daily" else week
        return self.store.tasks(self.account, period=period, scope=scope)

    def unfinished(self, scope: str, now=None):
        return [r for r in self.snapshot(scope, now) if r.get("status") not in ("claimed", "completed")]


class ResourceBudget:
    """Atomic conservative accounting before each resource-consuming input attempt."""
    def __init__(self, store, account: str = "default", timezone: str = "Asia/Shanghai", limits: dict | None = None,
                 reset_hour: int = 0):
        self.store = store
        self.account = account
        self.timezone = timezone
        self.limits = limits or {}
        self.reset_hour = reset_hour

    def period(self, now=None):
        return period_keys(self.timezone, now, self.reset_hour)[0]

    def _limit(self, resource: str, default=None):
        spec = self.limits.get(resource) or {}
        return spec.get("daily_limit", default), spec.get("reserve", 0)

    def check(self, costs: dict[str, float], now=None):
        period = self.period(now)
        current = self.store.resource_totals(self.account, period)
        for resource, amount in costs.items():
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise ValueError("资源费用必须是非负有限数字")
            amount = float(amount)
            if amount <= 0:
                continue
            limit, reserve = self._limit(resource)
            row = current.get(resource) or {"used": 0, "reserved": 0}
            if limit is not None and row["used"] + row["reserved"] + amount > float(limit):
                raise BudgetExceeded(f"{resource} 预算不足：需要 {amount}，剩余上限 {float(limit) - row['used'] - row['reserved']}")

    def spend(self, costs: dict[str, float], note="", evidence=None, balances=None, now=None):
        return self.store.spend_resources(self.account, self.period(now), costs, self.limits,
                                          note=note, evidence=evidence or {}, balances=balances or {})

    def authorize(self, costs, note="", evidence=None, balances=None, now=None):
        ticket = self.store.authorize_resources(self.account, self.period(now), costs, self.limits,
                                                note, evidence or {}, balances or {})
        return lambda submitted: self.store.finalize_resources(ticket, submitted)
