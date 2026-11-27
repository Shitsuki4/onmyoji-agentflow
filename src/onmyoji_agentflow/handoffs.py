"""Durable failure packets for the built-in or an external supervisory agent."""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from .errors import AgentflowError
from .runtime import FileMutex
from .workflow.engine import RunResult

ACTIONABLE = {"timeout", "stuck", "loop", "no_progress", "unknown_screen", "recognition", "workflow_fail", "workflow_error"}


class Handoffs:
    def __init__(self, supervisor):
        self.sup = supervisor
        self.store = supervisor.store
        self.folder = supervisor.runs_dir / "handoffs"

    def create(self, workflow, instance, result):
        run_id = result.evidence.get("run_id")
        old = self.store.query("SELECT id FROM agent_handoffs WHERE run_id=?", (run_id,)) if run_id else []
        if old:
            return old[0]["id"]
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = str(run_id or time.time_ns())
        image = result.evidence.get("screenshot")
        if not image and result.last_frame is not None:
            image = str(self.folder / f"{stamp}.png")
            cv2.imencode(".png", result.last_frame)[1].tofile(image)
        path = self.folder / f"{stamp}.json"
        packet = {"format": 1, "workflow": workflow.name, "instance": instance,
                  "workflow_digest": workflow.digest(), "source": workflow.raw.get("source"),
                  "workflow_yaml": workflow.dump(), "failure": result.summary(), "screenshot": image,
                  "events": self.store.query("SELECT ts,level,source,message FROM events ORDER BY id DESC LIMIT 30"),
                  "policy": "设备已暂停；不能绕过预算、用户拒绝或工作流变更审批；修改后先验证再恢复任务"}
        path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "pending" if result.failure_kind in ACTIONABLE else "needs_user"
        now = time.time()
        cur = self.store.execute("""INSERT INTO agent_handoffs(workflow,instance,run_id,failure_kind,status,
            packet_path,note,created,updated) VALUES (?,?,?,?,?,?,?,?,?)""",
            (workflow.name, instance, run_id, result.failure_kind, status, str(path), result.reason, now, now))
        return cur.lastrowid

    def list(self, limit=30):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("limit 必须是 1–200 的整数")
        return self.store.query("SELECT * FROM agent_handoffs ORDER BY id DESC LIMIT ?", (limit,))

    def get(self, handoff_id):
        rows = self.store.query("SELECT * FROM agent_handoffs WHERE id=?", (handoff_id,))
        if not rows:
            raise ValueError("没有这个 agent 接管任务")
        row = rows[0]
        return {**row, "packet": json.loads(Path(row["packet_path"]).read_text(encoding="utf-8"))}

    def update(self, handoff_id, status, note):
        self.store.execute("UPDATE agent_handoffs SET status=?,note=?,updated=? WHERE id=?",
                           (status, note, time.time(), handoff_id))

    def diagnose(self, handoff_id, proposal=None):
        """One bounded diagnosis/patch attempt, never an unbounded tap loop or auto-resume."""
        row = self.get(handoff_id)
        if row["failure_kind"] not in ACTIONABLE:
            raise ValueError("账号前置条件、预算、设备或用户拒绝应由用户处理，不能自动修改绕过")
        if row["status"] in ("waiting_user", "repaired"):
            return {"id": handoff_id, "status": row["status"], "note": row["note"]}
        with FileMutex(self.folder / f"{handoff_id}.lock"):
            row = self.get(handoff_id)
            if row["status"] in ("waiting_user", "repaired"):
                return {"id": handoff_id, "status": row["status"], "note": row["note"]}
            with self.sup.execution(row["instance"], f"agent-handoff:{handoff_id}"):
                packet = row["packet"]
                workflow = self.sup.load(row["workflow"])
                if workflow.digest() != packet["workflow_digest"]:
                    raise ValueError("工作流已变化，这份故障截图属于旧版本；请先重新观察")
                self.update(handoff_id, "diagnosing", "agent 正在诊断；计划保持暂停")
                summary = packet["failure"]
                frame = None
                if packet.get("screenshot") and Path(packet["screenshot"]).is_file():
                    frame = cv2.imdecode(np.fromfile(packet["screenshot"], np.uint8), cv2.IMREAD_COLOR)
                result = RunResult(workflow.name, "failed", reason=summary["reason"],
                    failure_kind=summary["failure_kind"], failed_state=summary.get("failed_state"),
                    variables=summary.get("variables") or {}, last_frame=frame, evidence=summary.get("evidence") or {})
                try:
                    if proposal is None:
                        level, note = self.sup.diagnose_and_repair(workflow, row["instance"], result)
                    else:
                        if not isinstance(proposal, dict) or not proposal.get("ops"):
                            raise ValueError("修复提案需要 ops；这不会批准或直接合并工作流")
                        level, note = self.sup.apply_proposal(workflow, row["instance"], proposal, frame)
                    status = {"proposed": "waiting_user", "repaired": "repaired"}.get(level, "needs_agent")
                    self.update(handoff_id, status, note)
                    return {"id": handoff_id, "status": status, "note": note, "resumed": False}
                except Exception as error:
                    self.update(handoff_id, "needs_agent", f"{type(error).__name__}: {error}")
                    raise
