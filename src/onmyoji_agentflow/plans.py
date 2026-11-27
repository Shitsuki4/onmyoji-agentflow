"""Plan control shared by CLI, web and MCP."""
from __future__ import annotations

import copy
import math
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
        runner = Marathon(self.app, instance, plan, self.app.cfg.home / "marathon" / "preview",
                          prepare_output=False)
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
                params, reason = runner.item_params(item)
                row["checkpoint"] = runner._checkpoint(item)
                if runner._done_for_period(item):
                    row.update(status="done", reason="本周期已核验完成")
                    rows.append(row)
                    continue
                if params is None:
                    row.update(status="blocked", reason=reason)
                    rows.append(row)
                    continue
                row["params"] = workflow.validate_params(params)
                row["status"] = "ready"
                index = plan["items"].index(item)
                if runner.next_ok.get(index, 0) > time.time():
                    row.update(status="waiting", reason="计划项仍在持久冷却期", next_at=runner.next_ok[index])
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
        pending = self.app.store.query("SELECT id FROM changes WHERE workflow='upstream-sync' AND status IN ('proposed','waiting_user')")
        startup = {"sync_before_start": bool(plan.get("sync_before_start")),
                   "pending_upstream_changes": [row["id"] for row in pending],
                   "status": "blocked" if plan.get("sync_before_start") and pending else
                             "check_on_start" if plan.get("sync_before_start") else "ready"}
        return {"plan": plan, "items": rows, "instance": instance, "startup": startup,
                "runtime": self.app.supervisor.runtime_status(instance)}

    def start(self, instance=None, path=None, rounds=None, hours=None, out=None, background=True, repair=True):
        preview = self.preview(instance, path)
        instance = preview["instance"]
        if rounds is None and hours is None:
            rounds = 1
        if rounds is not None and (isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1):
            raise ValueError("rounds 必须是正整数")
        if hours is not None and (type(hours) not in (int, float) or not math.isfinite(hours) or hours <= 0):
            raise ValueError("hours 必须是正有限数字")
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
            finally:
                job["job_id"] = runner.job_id

        if background:
            threading.Thread(target=work, daemon=True, name=f"oaf-plan-{instance}").start()
        else:
            work()
        return job

    def resume(self, job_id, *, background=True, rounds=None, hours=None, repair=True):
        """Reopen the same plan. Evidence checkpoints, not list position, decide what can run."""
        import json
        jobs = self.app.store.query("SELECT * FROM marathon_jobs WHERE id=? AND account=?",
                                     (job_id, self.app.ledger.account))
        if not jobs:
            raise ValueError("没有本账号的计划记录")
        row = jobs[0]
        if self.app.supervisor.runtime_status(row["instance"]).get("status") == "running":
            raise ValueError("模拟器仍有任务运行")
        return self.start(row["instance"], json.loads(row["plan"]), rounds=rounds, hours=hours,
                          background=background, repair=repair)

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
