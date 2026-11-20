"""Local daily report assembled from receipts, runs and resource accounting."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from .ledger import now_local


def daily_report(app, instance: str | None = None) -> dict:
    day, week = app.ledger.periods()
    tasks = app.ledger.snapshot()
    resources = app.store.resource_totals(app.ledger.account, day)
    foster = [row for name in ([instance] if instance else app.instance_names())
              for row in app.store.active_foster(app.ledger.account, name)]
    start = now_local(app.ledger.timezone, dt.datetime.fromisoformat(day)) + dt.timedelta(hours=app.ledger.reset_hour)
    runs = app.store.query("SELECT * FROM runs WHERE started>=? AND started<?" + (" AND instance=?" if instance else "") + " ORDER BY id DESC",
                          (start.timestamp(), (start + dt.timedelta(days=1)).timestamp(), *((instance,) if instance else ())))
    for row in runs:
        try:
            row["summary"] = json.loads(row["summary"] or "{}")
        except (TypeError, ValueError):
            pass
    return {"date": day, "week": week, "account": app.ledger.account,
            "tasks": tasks, "resources": resources, "foster": foster,
            "resource_events": app.store.resource_events(app.ledger.account, day),
            "balances": app.store.balances(app.ledger.account),
            "plans": app.plans.status()["jobs"],
            "unknown_samples": app.samples.list(),
            "runs": runs, "generated": now_local(app.ledger.timezone).isoformat(timespec="seconds")}


def write_daily_report(app, path: str | Path, instance: str | None = None) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = daily_report(app, instance)
    lines = [f"# 阴阳师日常报告 {data['date']}", "", f"- 周次：{data['week']}",
             f"- 账号：{data['account']}", "", "## 任务", "",
             "| 范围 | 任务 | 当前 | 目标 | 状态 | 已核验 |", "|---|---|---:|---:|---|---|"]
    for t in data["tasks"]:
        lines.append(f"| {t['scope']} | {t['task_key']} | {t['current'] if t.get('current') is not None else '-'} | {t.get('target') or '-'} | "
                     f"{t.get('status') or 'unknown'} | {'是' if t.get('verified') else '否'} |")
    lines += ["", "## 资源", "", "| 资源 | 预留 | 已用 | 备注 |", "|---|---:|---:|---|"]
    for name, value in data["resources"].items():
        lines.append(f"| {name} | {value.get('reserved', 0):g} | {value.get('used', 0):g} | {value.get('note') or ''} |")
    lines += ["", "## 寄养", ""]
    if data["foster"]:
        for f in data["foster"]:
            due = dt.datetime.fromtimestamp(f["due"]).isoformat(timespec="minutes") if f.get("due") else "未知"
            lines.append(f"- {f.get('status')}：{f.get('stars') or '?'} 星 {f.get('card_type') or '未知卡型'}，到期 {due}")
    else:
        lines.append("- 没有已记录的有效寄养")
    lines += ["", "## 执行记录与待办", "", "活跃奖励已领、每项日常完成、流程正常退出分别记录。", ""]
    for row in data["runs"]:
        summary = row.get("summary") or {}
        evidence = summary.get("evidence") or {}
        lines.append(f"- {row['workflow']}：执行 {row['status']}，业务 {summary.get('business_result', 'unknown')}；{row['reason']}")
        if evidence.get("screenshot"):
            lines.append(f"  证据：{evidence['screenshot']}")
    for row in data["plans"][:5]:
        lines.append(f"- 计划 #{row['id']}：{row['status']}；{row.get('stop_reason') or '待核对'}；记录目录 {row.get('output') or ''}")
    lines += ["", "## 未知画面", ""]
    for sample in data["unknown_samples"]:
        lines.append(f"- #{sample['id']} {sample['workflow']}：{sample['path']}（{'已标注' if sample['annotation'] else '待标注'}）")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
