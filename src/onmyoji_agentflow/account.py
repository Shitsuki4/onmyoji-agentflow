"""Read-only account measurements and one-change-at-a-time verification."""
from __future__ import annotations

import math
from pathlib import Path


def record(app, team, member, speed=None, crit=None, order=None, values=None, evidence=None, source="panel_read"):
    if not team or not member:
        raise ValueError("需要队伍和式神名称")
    evidence = evidence or {}
    screenshot = evidence.get("screenshot")
    if not screenshot or not Path(screenshot).is_file():
        raise ValueError("记录已核对数值需要存在的面板截图")
    for name, value in (("speed", speed), ("crit", crit)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError(f"{name} 必须是非负有限数值")
    return app.store.add_account_stat(app.ledger.account, source, team, member, speed, crit, order,
                                      values or {}, {**evidence, "verified": True})


def check_team(app, team):
    rows = app.store.account_stats(app.ledger.account, team)
    latest = {}
    for row in rows:
        latest.setdefault(row["member"], row)
    members = list(latest.values())
    errors = []
    for row in members:
        if row["speed"] is None or not row["evidence"].get("verified"):
            errors.append(f"{row['member']} 缺少实际速度或核对截图")
    order = sorted(members, key=lambda row: -(row["speed"] or 0))
    for before, after in zip(order, order[1:]):
        if before["speed"] == after["speed"]:
            errors.append(f"{before['member']} 与 {after['member']} 同速，需要战斗实测确认先后")
    expected = sorted((row for row in members if row["order_index"] is not None), key=lambda row: row["order_index"])
    if expected and [row["member"] for row in expected] != [row["member"] for row in order if row["order_index"] is not None]:
        errors.append("实读速度顺序与期望顺序不一致")
    return {"team": team, "verified": bool(members) and not errors, "speed_order": [row["member"] for row in order],
            "members": order, "issues": errors, "note": "顺序按面板速度；拉条、先机和技能效果仍需三把实测核对"}


def compare(app, team, member):
    rows = [row for row in app.store.account_stats(app.ledger.account, team) if row["member"] == member]
    if len(rows) < 2:
        return {"verified": False, "reason": "需要同一式神换装前后的两次面板记录"}
    after, before = rows[:2]
    return {"verified": all(row["evidence"].get("verified") for row in (before, after)),
            "before": before, "after": after,
            "delta": {key: after[key] - before[key] for key in ("speed", "crit") if before[key] is not None and after[key] is not None}}
