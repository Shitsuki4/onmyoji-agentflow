"""Activity calendar and expiry guards; dates are metadata, never inferred from a button click."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from .ledger import _zone
from .errors import WorkflowError


@dataclass(frozen=True)
class ActivityWindow:
    name: str
    battle_start: str
    battle_end: str
    shop_end: str | None = None
    timezone: str = "Asia/Shanghai"

    def __post_init__(self):
        try:
            start, end = self._parse(self.battle_start), self._parse(self.battle_end)
            if start > end or (self.shop_end and self._parse(self.shop_end) < end):
                raise ValueError("活动日期顺序无效")
        except (ValueError, TypeError) as error:
            raise WorkflowError(f"活动「{self.name}」元数据无效：{error}") from error

    def _parse(self, value: str | dt.datetime) -> dt.datetime:
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=_zone(self.timezone))
            return value.astimezone(_zone(self.timezone))
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_zone(self.timezone))
        return parsed.astimezone(_zone(self.timezone))

    def battle_open(self, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now(_zone(self.timezone))
        if now.tzinfo is None:
            now = now.replace(tzinfo=_zone(self.timezone))
        now = now.astimezone(_zone(self.timezone))
        return self._parse(self.battle_start) <= now <= self._parse(self.battle_end)

    def shop_open(self, now: dt.datetime | None = None) -> bool:
        if not self.shop_end:
            return False
        now = now or dt.datetime.now(_zone(self.timezone))
        if now.tzinfo is None:
            now = now.replace(tzinfo=_zone(self.timezone))
        return self._parse(self.battle_start) <= now.astimezone(_zone(self.timezone)) <= self._parse(self.shop_end)

    def assert_battle_open(self, now=None):
        if not self.battle_open(now):
            raise WorkflowError(f"活动「{self.name}」已不在战斗期；只允许查看/兑换到期前商店，不会开打旧 Boss")


def workflow_activity(raw: dict) -> ActivityWindow | None:
    data = raw.get("activity")
    if not data:
        return None
    required = ("name", "battle_start", "battle_end")
    if any(k not in data for k in required):
        raise WorkflowError("activity 需要 name、battle_start、battle_end")
    return ActivityWindow(**{k: data[k] for k in ("name", "battle_start", "battle_end", "shop_end", "timezone")
                             if k in data})
