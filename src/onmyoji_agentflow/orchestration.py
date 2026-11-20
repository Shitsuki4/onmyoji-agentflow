"""Calendar gates and durable, evidence-based checkpoints for task plans."""
from __future__ import annotations

import datetime as dt
import math
import re

from .ledger import _zone


def _date(value):
    return value if type(value) is dt.date else dt.date.fromisoformat(value)


def validate_schedule(value):
    if not isinstance(value, dict) or set(value) - {"weekdays", "windows", "starts_on", "ends_on"}:
        raise ValueError("schedule 只支持 weekdays/windows/starts_on/ends_on")
    days = value.get("weekdays", list(range(1, 8)))
    if not isinstance(days, list) or not days or any(type(d) is not int or not 1 <= d <= 7 for d in days):
        raise ValueError("weekdays 使用 1–7（星期一到星期日）")
    windows = value.get("windows", [["00:00", "00:00"]])
    if not isinstance(windows, list) or not windows:
        raise ValueError("windows 需要至少一个 [开始时间,结束时间]")
    for window in windows:
        if not isinstance(window, list) or len(window) != 2 or any(
                not isinstance(t, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in window):
            raise ValueError("时间窗口使用 HH:MM，结束时刻不包含在窗口内")
    dates = {}
    for key in ("starts_on", "ends_on"):
        if key in value:
            dates[key] = _date(value[key])
    if dates.get("starts_on", dt.date.min) > dates.get("ends_on", dt.date.max):
        raise ValueError("schedule 起止日期顺序无效")


def schedule_gate(schedule, now, timezone="Asia/Shanghai"):
    """Return (is_open, next_open_timestamp). Overnight windows belong to their start day."""
    validate_schedule(schedule)
    zone = _zone(timezone)
    local = dt.datetime.fromtimestamp(now, zone)
    first = _date(schedule.get("starts_on", "0001-01-01"))
    last = _date(schedule.get("ends_on", "9999-12-31"))
    if last < dt.date.max and local.date() > last + dt.timedelta(days=1):
        return False, None
    anchor = max(local.date() - dt.timedelta(days=1), first)
    days = schedule.get("weekdays", list(range(1, 8)))
    windows = schedule.get("windows", [["00:00", "00:00"]])
    upcoming = []
    for offset in range(9):
        date = anchor + dt.timedelta(days=offset)
        if date > last:
            break
        if date.isoweekday() not in days:
            continue
        for a, b in windows:
            start = dt.datetime.combine(date, dt.time.fromisoformat(a), zone)
            end = dt.datetime.combine(date, dt.time.fromisoformat(b), zone)
            if end <= start:
                end += dt.timedelta(days=1)
            if start <= local < end:
                return True, now
            if start > local:
                upcoming.append(start.timestamp())
    return False, min(upcoming) if upcoming else None


def validate_items(plan):
    items = plan["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("计划 items 必须是非空列表")
    ids = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("workflow"), str):
            raise ValueError("每个计划项必须指定 workflow 或 program")
        if item.get("scope", "daily") not in ("daily", "weekly"):
            raise ValueError("计划 scope 只支持 daily/weekly")
        if "id" in item:
            if not isinstance(item["id"], str) or not re.fullmatch(r"[\w-]+", item["id"]) or item["id"] in ids:
                raise ValueError("计划项 id 必须唯一且只含字母、数字、下划线或短横线")
            ids[item["id"]] = index
        for key in ("cooldown_min", "min_interval_min"):
            value = item.get(key, 0)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} 必须是非负有限数字")
        if "limit_per_period" in item and (type(item["limit_per_period"]) is not int or item["limit_per_period"] < 1):
            raise ValueError("limit_per_period 必须是正整数")
        if item.get("on_failure", "pause") not in ("pause", "continue"):
            raise ValueError("on_failure 只支持 pause/continue")
        if "schedule" in item:
            validate_schedule(item["schedule"])
        if item.get("schedule_profile") and not isinstance(item["schedule_profile"], str):
            raise ValueError("schedule_profile 必须是账号日程名称")
    visiting, visited = set(), set()

    def visit(index):
        if index in visiting:
            raise ValueError("计划依赖存在循环")
        if index in visited:
            return
        visiting.add(index)
        after = items[index].get("after", [])
        if not isinstance(after, list):
            raise ValueError("after 必须是计划项 id 列表")
        for name in after:
            if not isinstance(name, str) or name not in ids:
                raise ValueError(f"未知依赖：{name}")
            visit(ids[name])
        visiting.remove(index)
        visited.add(index)

    for i in range(len(items)):
        visit(i)
    # Stable topological order; legacy plans without dependencies keep their original order.
    ordered, added = [], set()

    def append(index):
        if index not in added:
            for name in items[index].get("after", []):
                append(ids[name])
            added.add(index)
            ordered.append(items[index])

    for i in range(len(items)):
        append(i)
    plan["items"] = ordered


class Checkpoints:
    def __init__(self, store, account, plan_key):
        self.store, self.account, self.key = store, account, plan_key

    def get(self, item, period):
        rows = self.store.query("SELECT * FROM plan_steps WHERE account=? AND plan_key=? AND item_key=? AND period=?",
                                (self.account, self.key, item, period))
        return rows[0] if rows else {"status": "pending", "completed": 0, "attempts": 0, "next_at": 0}

    def begin(self, item, period, now):
        # The account+plan checkpoint is shared by all devices and entry points.
        with self.store._lock:
            try:
                self.store._conn.execute("BEGIN IMMEDIATE")
                old = self.get(item, period)
                if old["status"] in ("running", "needs_review", "completed"):
                    self.store._conn.rollback()
                    return False
                self.store._conn.execute("""INSERT INTO plan_steps
                    (account,plan_key,item_key,period,status,attempts,completed,next_at,updated)
                    VALUES (?,?,?,?,?,1,0,0,?) ON CONFLICT(account,plan_key,item_key,period)
                    DO UPDATE SET status='running',attempts=plan_steps.attempts+1,updated=excluded.updated""",
                    (self.account, self.key, item, period, "running", now))
                self.store._conn.commit()
                return True
            except BaseException:
                self.store._conn.rollback()
                raise

    def finish(self, item, period, status, completed, next_at, record, now):
        import json
        self.store.execute("""UPDATE plan_steps SET status=?,completed=completed+?,next_at=?,record=?,updated=?
            WHERE account=? AND plan_key=? AND item_key=? AND period=?""",
            (status, completed, next_at, json.dumps(record, ensure_ascii=False, default=str), now,
             self.account, self.key, item, period))
