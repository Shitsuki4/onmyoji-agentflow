"""Plan control shared by CLI, web and MCP."""
from __future__ import annotations

import copy
import threading
import time
from pathlib import Path

from .errors import WorkflowError
from .marathon import Marathon, load_plan, parse_deadline
from .tasks import remaining_task


class Plans:
    def __init__(self, app):
        self.app = app

    def preview(self, instance=None, path=None):
        instance = instance or self.app.instance_names()[0]
        self.app.cfg.instance(instance)
        plan = load_plan(path)
        rows = []
        programs = {row["entry_id"]: row for row in self.app.programs.list()}
        for item in plan["items"]:
            row = copy.deepcopy(item)
            if item.get("program"):
                entry = programs.get(item["program"])
                row["translation"] = {key: entry.get(key) for key in ("id", "status", "note", "change_id")} if entry else None
            try:
                workflow = self.app.supervisor.load(item["workflow"])
                from .programs import assert_current
                assert_current(workflow, self.app.ws.path)
                row["params"] = workflow.validate_params(item.get("params") or {})
                row["status"] = "ready"
                if item.get("goal"):
                    tasks = [task for task in self.app.ledger.snapshot(item.get("scope", "daily"))
                             if time.time() - task["updated"] < 900]
                    gap = remaining_task(tasks, item["goal"])
                    row.update(remaining=gap, status="unknown" if gap is None else "done" if gap == 0 else "ready")
                if item.get("profile"):
                    profile = self.app.cfg.get("game", {}).get("profiles", {}).get(item["profile"], {})
                    if not profile.get("verified") or not profile.get("evidence"):
                        row.update(status="blocked", reason="缺少已核对账号档案")
            except (WorkflowError, OSError, ValueError) as error:
                row.update(status="blocked", reason=str(error))
                if item.get("program") and row.get("translation"):
                    row["reason"] = "上游脚本尚未通过完整转换与审批：" + str(row["translation"])
            rows.append(row)
        return {"plan": plan, "items": rows, "instance": instance,
                "runtime": self.app.supervisor.runtime_status(instance)}

    def start(self, instance=None, path=None, rounds=1, hours=None, out=None, background=True, repair=True):
        preview = self.preview(instance, path)
        instance = preview["instance"]
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise ValueError("rounds 必须是正整数")
        if preview["runtime"].get("status") == "running":
            raise ValueError("模拟器已有任务运行")
        folder = Path(out) if out else self.app.cfg.home / "marathon" / str(time.time_ns())
        runner = Marathon(self.app, instance, preview["plan"], folder, max_rounds=rounds,
                          deadline=parse_deadline(hours, None), repair=repair)
        job = {"instance": instance, "out": str(folder), "status": "starting"}

        def work():
            try:
                job.update(status="finished", reason=runner.run())
            except Exception as error:
                job.update(status="error", reason=str(error))
                self.app.store.event("error", "marathon", str(error))

        if background:
            threading.Thread(target=work, daemon=True, name=f"oaf-plan-{instance}").start()
        else:
            work()
        return job

    def status(self):
        return {"jobs": self.app.store.marathon_jobs(self.app.ledger.account),
                "devices": {name: self.app.supervisor.runtime_status(name) for name in self.app.instance_names()},
                "tasks": self.app.ledger.snapshot(),
                "resources": self.app.store.resource_totals(self.app.ledger.account, self.app.ledger.periods()[0]),
                "foster": [row for name in self.app.instance_names()
                           for row in self.app.store.active_foster(self.app.ledger.account, name)]}

    def stop(self, instance=None, mode="immediate"):
        instance = instance or self.app.instance_names()[0]
        state = self.app.supervisor.runtime_status(instance)
        self.app.supervisor.stop(instance, mode)
        return {"instance": instance, "stopping": state.get("status") == "running", "mode": mode}
