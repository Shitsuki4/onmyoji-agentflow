"""The supervision loop: run -> detect failure -> escalate -> repair on a branch -> validate -> merge -> watch -> roll back.

Escalation ladder after a failed run:

1. **local**: retry with the remaining count (``max_local_retries``).
   Device errors reopen the device first. ``confirm_denied`` never retries.
   The back key is pressed before a retry only for the failure kinds listed in
   ``supervisor.recover_back_on`` (empty by default): on 庭院 the back key opens the
   game's 「退出游戏」 confirmation, so pressing it blindly is unsafe.
2. **diagnose**: compare the failure screenshot with every state (near misses) and,
   if an LLM is configured and the budget allows, ask it for a repair in the
   patch language of ``repair.py``.
3. **repair**: commit the patch on ``agent/...`` branch, add the failure screenshot
   as a replay case, then validate in order: schema -> replay tests -> observation
   mode on the device (no input) -> limited trial run (``trial_actions`` inputs).
   Only a change that passes everything can replace ``main``:
   params changes merge automatically; recognition and workflow changes wait for
   the user's approval (``auto_merge`` in config). A workflow change also asks
   before its first trial run ("新脚本首次运行").
4. **human**: anything else is recorded as an event for the user.

After a merge, the next runs of that workflow are watched; if the failure rate of
the new version reaches ``rollback_failure_rate`` over at least 3 runs and is
not better than before, the merge is reverted automatically.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from ..errors import AgentflowError, BudgetExceeded, LLMError, WorkflowError
from ..activity import workflow_activity
from ..llm import image_to_data_url, parse_json_reply
from ..log import logger
from ..runtime import DeviceLease, DeviceBusy, normalize_device_identity
from ..runtime import WorkspaceLease
from ..ledger import GameLedger, ResourceBudget
from ..workflow.engine import Runner, RunResult
from ..workflow.schema import load_workflow
from ..yamlio import dump_yaml
from .repair import apply_ops, classify, sensitive_preserved
from .replay import case_files, load_cases, run_cases

NEEDS_CONFIRM_MERGE = "合并改动"
FIRST_RUN = "新脚本首次运行"

SYSTEM_PROMPT = """你是阴阳师自动化工作流的监管助手。工作流是 YAML 状态机：每个状态有 when（多点比色/找色/表达式）和 do（点击、滑动等）。
一次运行失败了。请根据截图、失败信息和各状态的匹配情况，给出最小的修复。只输出 JSON：
{"diagnosis": "一两句中文说明原因",
 "action": "patch" | "retry" | "human",
 "expected_state": "这张截图应该被识别成的状态 id，或 null",
 "ops": [ ... ]}
可用 ops：
{"op":"set","path":"limits.stuck_timeout_s","value":180}
{"op":"set_delay","state":"<id>","action":0,"value":1500}
{"op":"set_similarity","state":"<id>","value":90}
{"op":"recapture_colors","state":"<id>","points":[[x,y],...]}   # 3-30 个点，颜色由程序从截图采样
{"op":"add_state","before":"<id>","state":{...}}  {"op":"replace_state","state":{...}}  {"op":"remove_state","id":"<id>"}
规则：坐标是 1280x720。永远不要去掉已有的 confirm/sensitive。
如果截图说明是账号条件不满足（account_requires 里列的条件，例如提示要先加入阴阳寮、等级不够、功能未解锁），
这不是脚本故障：action 用 "human"，diagnosis 里写清楚缺什么条件，不要给 ops。涉及花勾玉、抽卡、购买、出售、分解的新状态必须加 sensitive。
弄不清楚就返回 action=human。"""


@dataclass
class Outcome:
    result: RunResult
    level: str = "none"            # none | local | repaired | proposed | human
    notes: list = field(default_factory=list)
    attempts: list = field(default_factory=list)


class Supervisor:
    def __init__(self, cfg, store, workspace, controller_factory, confirm=None, llm=None, runs_dir: Path | None = None,
                 sleep=time.sleep, clock=time.monotonic):
        self.cfg = cfg
        self.clock = clock
        self.scfg = cfg["supervisor"]
        self.store = store
        self.ws = workspace
        self.controller_factory = controller_factory   # (instance_name, observe: bool) -> Controller
        self.confirm = confirm
        self.llm = llm
        self.runs_dir = Path(runs_dir) if runs_dir else Path(tempfile.gettempdir()) / "oaf-runs"
        self.sleep = sleep
        self.git_lock = threading.RLock()
        self.stop_flags: dict[str, threading.Event] = {}
        self.event_sink = None   # optional (instance, kind, data) callback, e.g. oaf marathon's sample saver
        self._runtime = threading.local()
        game = cfg.get("game") or {}
        self.ledger = GameLedger(store, str(game.get("account") or "default"),
                                 str(game.get("timezone") or "Asia/Shanghai"), game.get("daily_reset_hour", 0))
        self.budget = ResourceBudget(store, self.ledger.account, self.ledger.timezone, game.get("budgets") or {},
                                     reset_hour=game.get("daily_reset_hour", 0))
        from ..handoffs import Handoffs
        self.handoffs = Handoffs(self)

    def _device_identity(self, instance: str) -> str:
        for item in self.cfg.get("instances", []):
            if str(item.get("name") or item.get("mumu_id")) == str(instance) or str(item.get("serial")) == str(instance):
                return normalize_device_identity(item)
        return normalize_device_identity(instance)

    # ------------------------------------------------------------------ basics
    def load(self, name: str, root: Path | None = None):
        root = root or self.ws.path
        if not re.fullmatch(r"[\w-]+", name):
            raise WorkflowError("工作流名只能包含文字、数字、下划线或连字符")
        with WorkspaceLease(root):
            return load_workflow(root / "workflows" / f"{name}.yaml", [root / "resources"])

    @contextmanager
    def execution(self, instance: str, owner: str):
        identity = self._device_identity(instance)
        existing = getattr(self._runtime, "lease", None)
        if existing is not None:
            if existing.identity != identity:
                raise DeviceBusy("一个执行线程不能同时操作两台设备")
            yield existing
            return
        lease = DeviceLease(identity, owner=owner).acquire()
        self._runtime.lease = lease
        self.stop_flags.setdefault(instance, threading.Event()).clear()
        lease.start_heartbeat()
        lease.update(home=str(self.runs_dir.parent), instance=instance)
        try:
            yield lease
        finally:
            self._runtime.lease = None
            lease.release()

    def runtime_status(self, instance: str):
        return DeviceLease(self._device_identity(instance)).snapshot()

    def _confirm(self, category: str, detail: str, instance: str = "") -> bool:
        if self.confirm is None:
            return False
        try:
            return bool(self.confirm(category, detail, instance))
        except TypeError:
            return bool(self.confirm(category, detail))

    def _run_once(self, wf, instance: str, params: dict, mode: str = "run", max_actions=None, max_seconds=None,
                  observe: bool = False, initial_vars: dict | None = None,
                   validate_params: bool = True, first_run_approved: bool = False,
                   scheme_checkpoint=None, resume_from=None) -> RunResult:
        if not observe:
            from ..programs import assert_current
            assert_current(wf, wf.path.parent.parent if wf.path else self.ws.path)
            activity = workflow_activity(wf.raw)
            if activity is not None:
                activity.assert_battle_open()
        params = wf.validate_params(params) if validate_params else params
        with self.execution(instance, f"workflow:{wf.name}:{mode}") as lease:
            lease.update(workflow=wf.name, mode=mode, params=params)
            source = wf.raw.get("source") or {}
            if not observe and isinstance(source, dict) and source.get("entry_id"):
                digest = wf.digest()
                approved = self.store.query("SELECT approved FROM program_activations WHERE instance=? AND digest=?",
                                            (instance, digest))
                if not approved:
                    if not first_run_approved and not self._confirm(FIRST_RUN,
                            f"{wf.name}：上游统一转换后的首次运行；来源 {source['entry_id']}；敏感操作仍逐项确认", instance):
                        result = RunResult(wf.name, "failed", reason="用户未批准转换工作流的首次运行", failure_kind="confirm_denied")
                        result.evidence["run_id"] = self.store.add_run(wf.name, instance, mode, result, digest)
                        return result
                    self.store.execute("INSERT OR IGNORE INTO program_activations(instance,digest,approved) VALUES (?,?,?)",
                                       (instance, digest, time.time()))
            ctl = self.controller_factory(instance, observe)
            flag = self.stop_flags.setdefault(instance, threading.Event())
            charged = set()
            def before_input(state, action, variables):
                boundary_key = (state["id"], tuple((name, variables.get(name))
                                                     for name in ("runs", "rounds", "wins", "done")))
                cost = action.get("cost")
                if cost is None and state.get("cost"):
                    if boundary_key in charged:
                        return
                    cost = state["cost"]
                if cost:
                    activity = workflow_activity(wf.raw)
                    if activity:
                        activity.assert_battle_open()
                    balances = {name: row["amount"] for name, row in self.store.balances(self.ledger.account).items()}
                    finalize = self.budget.authorize(cost, note=f"{wf.name}/{state['id']}", balances=balances,
                                      evidence={"instance": instance, "basis": "input_attempt", "estimated": True})
                    def finish(submitted):
                        finalize(submitted)
                        if submitted and state.get("cost"):
                            charged.add(boundary_key)
                    return finish
            runner = Runner(wf, ctl, params=params,
                            confirm=lambda c, d: self._confirm(c, d, instance),
                            max_actions=max_actions, max_seconds=max_seconds,
                            should_stop=lambda: "immediate" if flag.is_set() else lease.stop_mode(), clock=self.clock,
                            on_event=lambda k, d: self._on_event(instance, k, d), initial_vars=initial_vars,
                            validate_params=validate_params, before_input=before_input, scheme_checkpoint=scheme_checkpoint)
            oas_started_at = time.time()
            if resume_from is not None and not self.store.claim_scheme_pause(resume_from):
                raise WorkflowError("方案暂停记录已被恢复")
            res = runner.run()
            restore_pause = None
            if resume_from is not None:
                res.evidence["resumed_from_run_id"] = resume_from
                if res.actions == 0 and res.status in ("failed", "stopped"):
                    restore_pause = resume_from
                    res.evidence["scheme_resume_retryable"] = True
            if mode == "run" and not observe and res.oas_wakes:
                from ..workflow.oas_schedule import WAKE_WORKFLOWS, wake_next_run
                res.evidence["oas_wakes"] = [
                    {"task": task, "workflow": WAKE_WORKFLOWS[task], "account": self.ledger.account,
                     "observed_at": oas_started_at + elapsed,
                     "next_run": wake_next_run(oas_started_at, oas_started_at + elapsed, delay, *server_params)}
                    for task, (delay, elapsed, *server_params) in res.oas_wakes.items()
                ]
            if mode == "run" and not observe and res.status == "success" and res.oas_schedule:
                from ..workflow.oas_schedule import calendar_next_run, next_run
                finished_at = time.time()
                reference_at, delay = finished_at, None
                if res.oas_target is not None:
                    delay, age = res.oas_target
                    reference_at -= age
                if res.oas_calendar_target is not None:
                    local_time_seconds, days_ahead = res.oas_calendar_target
                    due = calendar_next_run(finished_at, params, local_time_seconds=local_time_seconds,
                                            days_ahead=days_ahead)
                else:
                    due = next_run(reference_at, params, target_delay_seconds=delay, calendar_at=finished_at)
                res.evidence["oas_schedule"] = {"task": res.oas_schedule, "account": self.ledger.account,
                                                "finished_at": finished_at, "next_run": due}
            digest = self._run_digest(wf)
            pause_scope = None
            if (res.scheme_pause and mode == "run" and not observe and max_seconds is None and max_actions is None
                    and wf.path and wf.path.resolve().parent == (self.ws.path / "workflows").resolve()):
                pause_scope = (lease.identity, self.ledger.account, wf.path.stem)
                res.evidence["scheme_resume_available"] = True
            run_id = self.store.add_run(wf.name, instance, mode, res, digest, pause_scope=pause_scope,
                                        restore_pause=restore_pause)
        if res.last_frame is not None:
            folder = self.runs_dir / f"{run_id:06d}"
            folder.mkdir(parents=True, exist_ok=True)
            image_path = folder / ("failure.png" if res.status == "failed" else "final.png")
            cv2.imencode(".png", res.last_frame)[1].tofile(str(image_path))
            res.evidence["screenshot"] = str(image_path)
            res.evidence["run_id"] = run_id
            (folder / "summary.json").write_text(json.dumps(res.summary(), ensure_ascii=False, indent=2, default=str),
                                                 encoding="utf-8")
            self.store.execute("UPDATE runs SET summary=? WHERE id=?", (json.dumps(res.summary(), ensure_ascii=False), run_id))
        return res

    def _run_digest(self, wf):
        return wf.digest({"humanize": self.cfg.get("humanize"), "game": self.cfg.get("game")})

    def resume_scheme(self, run_id: int) -> RunResult:
        """Claim one stored pause and restart only that scheme on its original device."""
        from ..programs import assert_current
        from ..workflow.scheme_lifecycle import resume_elapsed_ms

        row = self.store.scheme_pause(run_id)
        if row is None or row["resumed"] is not None:
            raise WorkflowError("没有可恢复的方案暂停记录")
        instance = row["instance"]
        with self.execution(instance, f"scheme-resume:{run_id}") as lease:
            if row["device"] != lease.identity or row["account"] != self.ledger.account:
                raise WorkflowError("方案暂停记录与当前设备或账号不一致")
            wf = self.load(row["workflow_file"])
            if not wf.raw.get("scheme_lifecycle") or self._run_digest(wf) != row["digest"]:
                raise WorkflowError("工作流、资源或运行配置已变化，无法恢复旧方案")
            assert_current(wf, self.ws.path)
            checkpoint = json.loads(row["checkpoint"])
            resume_elapsed_ms(wf.raw, checkpoint, time.time())
            return self._run_once(wf, instance, {}, scheme_checkpoint=checkpoint, resume_from=run_id)

    def _on_event(self, instance, kind, data):
        lease = getattr(self._runtime, "lease", None)
        if kind == "state" and lease:
            lease.update(state=data.get("state"), variables=data.get("vars"))
        if kind == "task_scan":
            evidence = self._save_evidence(instance, data.get("frame"), "task-scan")
            for task in data.get("tasks", []) if data.get("verified") else []:
                self.ledger.record_task(data["scope"], task["key"], task.get("current"), task.get("target"),
                                        task.get("claimed"), verified=bool(data.get("verified")),
                                        evidence={**evidence, **task, "ocr_verified": bool(data.get("verified"))})
        if kind == "task_scan_complete" and data.get("verified"):
            evidence = self._save_evidence(instance, data.get("frame"), "task-coverage")
            self.ledger.record_task(data["scope"], "scan_coverage", verified=bool(data.get("complete")),
                                    evidence={**evidence, "pages": data["pages"], "task_keys": data["task_keys"],
                                              "complete": data.get("complete")})
        if kind == "receipt":
            self._record_receipt(instance, data)
        if kind == "unknown" and data.get("frame") is not None:
            from ..samples import Samples
            workflow = lease.snapshot().get("workflow", "unknown") if lease else "unknown"
            Samples(self.store, self.runs_dir / "samples").add(data["frame"], workflow,
                context={"after_state": data.get("after_state"), "instance": instance})
        if self.event_sink is not None:
            try:
                self.event_sink(instance, kind, data)
            except Exception:  # noqa: BLE001 - a broken sink must not stop the run
                pass
        if kind in ("start", "end"):
            msg = f"[{instance}] {kind}: " + json.dumps(data, ensure_ascii=False, default=str)[:400]
            self.store.event("info", "run", msg)

    def _save_evidence(self, instance, frame, kind):
        folder = self.runs_dir / "evidence"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{time.time_ns()}-{kind}.png"
        if frame is not None:
            cv2.imencode(".png", frame)[1].tofile(str(path))
        return {"screenshot": str(path), "instance": instance, "captured": time.time()}

    def _record_receipt(self, instance, data):
        evidence = self._save_evidence(instance, data.get("frame"), data["kind"])
        if data["kind"] == "foster":
            from ..foster import read_countdown
            seconds = read_countdown(data.get("vars", {}).get("foster_timer", ""))
            if seconds is not None and seconds > 0:
                candidate = data.get("candidate") or {}
                self.store.set_foster(self.ledger.account, instance, "active", due=time.time() + seconds,
                                      **{key: candidate[key] for key in ("card_type", "stars", "friend") if key in candidate},
                                      evidence=json.dumps(evidence, ensure_ascii=False))
        elif data["kind"] in ("regional_boss", "delegation"):
            from ..foster import read_countdown
            seconds = read_countdown(data.get("vars", {}).get("delegation_timer", ""))
            if data["kind"] == "delegation" and not seconds:
                return
            if seconds:
                evidence["due"] = time.time() + seconds
            self.store.record_task_receipt(self.ledger.account, self.ledger.periods()[1], "weekly", data["kind"],
                                           data.get("identity"), "active" if seconds else "completed", evidence)

    def stop(self, instance: str, mode: str = "immediate"):
        if mode == "immediate":
            self.stop_flags.setdefault(instance, threading.Event()).set()
        DeviceLease(self._device_identity(instance), owner="stop-request").request_stop(mode)

    # ------------------------------------------------------------------ main entry
    def run(self, name: str, instance: str = "main", params: dict | None = None, repair: bool = True) -> Outcome:
        with self.execution(instance, f"workflow:{name}:run"):
            return self._run(name, instance, params, repair)

    def _run(self, name, instance, params, repair):
        wf = self.load(name)
        from ..programs import assert_current
        assert_current(wf, self.ws.path)
        activity = workflow_activity(wf.raw)
        if activity is not None:
            activity.assert_battle_open()
        params = wf.validate_params(params or {})
        original_params = dict(params)
        res = self._run_once(wf, instance, params)
        outcome = Outcome(res, attempts=[res.summary()])
        retries = 0
        call_active_var = wf.raw.get("navigation", {}).get("call_active_var")
        lifecycle = wf.raw.get("scheme_lifecycle")
        while (res.status == "failed" and not lifecycle and not (call_active_var and res.variables.get(call_active_var))
                and res.failure_kind not in ("confirm_denied", "prerequisite", "budget", "unknown_screen",
                                             "navigation_resume", "restart_uncertain", "app_close_uncertain") and retries < int(
                self.scfg.get("max_local_retries", 2)) and not self.stop_flags[instance].is_set()):
            if getattr(self._runtime, "lease").stop_mode():
                break
            retries += 1
            outcome.level = "local"
            outcome.notes.append(f"第 {retries} 次本地重试（{res.failure_kind}: {res.reason}）")
            self.store.event("warn", "supervisor", f"{name}@{instance} 失败，本地重试 {retries}：{res.reason}")
            back_on = self.scfg.get("recover_back_on") or []
            if res.failure_kind in back_on:
                try:
                    ctl = self.controller_factory(instance, False)
                    ctl.back(800)
                    outcome.notes.append(f"重试前按了一次返回键（{res.failure_kind}）")
                except Exception as e:  # noqa: BLE001
                    outcome.notes.append(f"恢复操作失败：{e}")
            remaining = remaining_params(wf, original_params, res.variables)
            if _no_remaining_count(wf, remaining):
                outcome.notes.append("已达到工作流请求的次数，重试只会再次开战；停止重试并保留当前结算证据")
                outcome.level = "human"
                outcome.result.evidence = {**(outcome.result.evidence or {}),
                                           "attempts": outcome.attempts,
                                           "attempt_count": len(outcome.attempts),
                                           "retry_actions": sum(int(a.get("actions") or 0)
                                                                for a in outcome.attempts)}
                if outcome.result.evidence.get("run_id"):
                    self.store.execute("UPDATE runs SET summary=? WHERE id=?", (
                        json.dumps(outcome.result.summary(), ensure_ascii=False),
                        outcome.result.evidence["run_id"]))
                return outcome
            # Keep the original limit and carry forward counters.  Reducing the limit as well
            # would subtract completed battles twice and stop a resumed run early.
            res = self._run_once(wf, instance, original_params, initial_vars=res.variables)
            outcome.attempts.append(res.summary())
            outcome.result = res
        outcome.result.evidence = {**(outcome.result.evidence or {}),
                                   "attempts": outcome.attempts,
                                   "attempt_count": len(outcome.attempts),
                                   "retry_actions": sum(int(a.get("actions") or 0) for a in outcome.attempts)}
        if outcome.result.evidence.get("run_id"):
            self.store.execute("UPDATE runs SET summary=? WHERE id=?", (
                json.dumps(outcome.result.summary(), ensure_ascii=False), outcome.result.evidence["run_id"]))
        self.check_rollback(name)
        handoff_id = None
        if res.status == "failed":
            handoff_id = self.handoffs.create(wf, instance, res)
            res.evidence["handoff_id"] = handoff_id
            if res.evidence.get("run_id"):
                self.store.execute("UPDATE runs SET summary=? WHERE id=?", (
                    json.dumps(res.summary(), ensure_ascii=False), res.evidence["run_id"]))
            outcome.notes.append(f"已保存 agent 接管任务 #{handoff_id}，包含截图、状态、日志与源码版本")
        if res.status != "failed" or not repair:
            if res.status == "failed":
                outcome.level = "human"
            return outcome
        if (lifecycle or res.failure_kind in ("confirm_denied", "device", "prerequisite", "budget", "navigation_resume",
                                               "restart_uncertain", "app_close_uncertain")
                or (call_active_var and res.variables.get(call_active_var))):
            outcome.level = "human"
            outcome.notes.append("需要你处理：" + res.reason)
            self.store.event("error", "supervisor", f"{name}@{instance} 需要人工处理：{res.reason}")
            return outcome
        try:
            note = self.diagnose_and_repair(wf, instance, res)
            outcome.level = note[0]
            outcome.notes.append(note[1])
            self.handoffs.update(handoff_id, {"proposed": "waiting_user", "repaired": "repaired"}.get(note[0], "needs_agent"), note[1])
        except Exception as e:
            outcome.level = "human"
            outcome.notes.append(f"自动修复没做成：{e}")
            self.store.event("error", "supervisor", f"{name}@{instance} 自动修复没做成：{e}")
            self.handoffs.update(handoff_id, "needs_agent", str(e))
        return outcome

    # ------------------------------------------------------------------ diagnosis
    def diagnose_and_repair(self, wf, instance: str, res: RunResult) -> tuple[str, str]:
        if self.llm is None:
            raise AgentflowError("没有配置大模型，只能交给你处理")
        frame = res.last_frame
        diag = Runner(wf, _Observe()).diagnose_frame(frame) if frame is not None else []
        text = {
            "workflow": wf.name, "failure": res.summary(), "state_matches": diag,
            # account prerequisites: if the screenshot shows one is missing (e.g. 未加入阴阳寮), answer
            # action "human" and say so; never patch the workflow for it
            "account_requires": wf.requires,
            "workflow_yaml": wf.dump()[:12000],
        }
        content = [{"type": "text", "text": json.dumps(text, ensure_ascii=False, default=str)}]
        if frame is not None:
            content.append({"type": "image_url", "image_url": {"url": image_to_data_url(frame)}})
        reply = self.llm.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
                              purpose="diagnose", need_vision=True)
        proposal = parse_json_reply(reply)
        self.store.event("info", "llm", f"{wf.name} 诊断：{proposal.get('diagnosis', '')}")
        if proposal.get("action") != "patch" or not proposal.get("ops"):
            return "human", f"大模型诊断：{proposal.get('diagnosis', '')}（没有给出可用的修改，交给你处理）"
        return self.apply_proposal(wf, instance, proposal, frame)

    # ------------------------------------------------------------------ repair
    def apply_proposal(self, wf, instance: str, proposal: dict, frame) -> tuple[str, str]:
        ops = proposal["ops"]
        kind = classify(ops)
        new_raw = apply_ops(wf.raw, ops, frame)
        rel = f"workflows/{wf.name}.yaml"
        files: dict = {rel: dump_yaml(new_raw)}
        if frame is not None and "expected_state" in proposal:
            case = f"auto-{time.strftime('%Y%m%d-%H%M%S')}"
            files.update(case_files(case, wf.name, frame, proposal.get("expected_state"),
                                    proposal.get("diagnosis", "")))
        msg = f"[agent] {wf.name} {kind} 修复：{proposal.get('diagnosis', '')[:80]}"
        with self.git_lock:
            branch, commit = self.ws.propose(wf.name, kind, files, msg)
        cid = self.store.execute(
            "INSERT INTO changes(created, workflow, kind, branch, commit_id, status, note) VALUES (?,?,?,?,?,?,?)",
            (time.time(), wf.name, kind, branch, commit, "proposed", proposal.get("diagnosis", ""))).lastrowid
        ok, report = self.validate_branch(wf, branch, instance, kind)
        self.store.execute("UPDATE changes SET validation=? WHERE id=?", (json.dumps(report, ensure_ascii=False), cid))
        if not ok:
            self.store.execute("UPDATE changes SET status='rejected' WHERE id=?", (cid,))
            return "human", f"修改没通过验证（{report.get('failed_step')}），保留在分支 {branch}，没有替换"
        auto = self.scfg.get("auto_merge", {})
        auto_ok = {"params": auto.get("params", True), "recognition": auto.get("images", False),
                   "workflow": auto.get("workflow", False)}[kind]
        if report.get("verification") == "unverified":
            auto_ok = False
        if not auto_ok:
            verification = "格式检查通过但缺少回放样本，尚未验证" if report.get("verification") == "unverified" else "修改已通过验证"
            detail = f"{wf.name}：{kind} {verification}（{proposal.get('diagnosis', '')}），分支 {branch}"
            if not self._confirm(NEEDS_CONFIRM_MERGE, detail, instance):
                self.store.execute("UPDATE changes SET status='waiting_user' WHERE id=?", (cid,))
                return "proposed", f"{verification}，等你确认后才会替换（分支 {branch}）"
        merged = self.merge_change(cid)
        return "repaired", f"已自动修复并替换（{kind}，提交 {merged[:8]}）：{proposal.get('diagnosis', '')}"

    def validate_branch(self, wf_before, branch: str, instance: str | None, kind: str,
                        name: str | None = None) -> tuple[bool, dict]:
        """Validate workflow ``name`` (default: ``wf_before.name``) on ``branch``.

        ``wf_before`` is the version currently on main, or ``None`` for a brand-new workflow."""
        name = name or wf_before.name
        root = Path(tempfile.mkdtemp(prefix="oaf-validate-"))
        try:
            with self.git_lock:
                tmp = self.ws.checkout_tmp(branch, root / "ws")
            return self._validate_in(wf_before, name, tmp, branch, instance, kind)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _validate_in(self, wf_before, name: str, tmp: Path, branch: str, instance: str | None,
                     kind: str) -> tuple[bool, dict]:
        report: dict = {"branch": branch, "workflow": name, "steps": []}
        # 1. schema
        try:
            wf = self.load(name, tmp)
        except (WorkflowError, OSError) as e:
            report.update(failed_step="格式检查", error=str(e))
            return False, report
        if wf_before is not None and not sensitive_preserved(wf_before, wf):
            report.update(failed_step="确认项检查", error="修改去掉了需要确认的操作")
            return False, report
        report["steps"].append("格式检查通过")
        # 2. replay tests
        cases = load_cases(tmp / "tests" / wf.name)
        results = run_cases(wf, cases)
        bad = [r.__dict__ for r in results if not r.ok]
        report["replay"] = {"total": len(results), "failed": bad}
        if bad:
            report["failed_step"] = "回放测试"
            return False, report
        if not results:
            report.update(coverage="insufficient", verification="unverified")
            report["steps"].append("格式正确；缺少回放样本，未验证")
            return True, report
        report["steps"].append(f"回放测试 {len(results)} 个全部通过")
        if instance is None:
            if kind == "workflow":
                covered = {case[2].get("state") for case in cases if case[2].get("state") is not None}
                missing = [state["id"] for state in wf.states if state["id"] not in covered]
                report["replay"].update(covered_states=sorted(covered), uncovered_states=missing,
                    positive=sum(case[2].get("state") is not None for case in cases),
                    negative=sum(case[2].get("state") is None for case in cases))
                report.update(coverage="partial" if missing or not report["replay"]["negative"] else "recognition_only",
                              verification="unverified")
                report["steps"].append("仅验证静态识别；未批准实机输入，不能宣称执行闭环通过")
            return True, report
        # 3. observation mode (recognise only, no input)
        obs = self._run_once(wf, instance, wf.param_defaults(), mode="observe",
                             max_seconds=float(self.scfg.get("observe_seconds", 60)), observe=True)
        ratio = obs.recognized_ticks / max(obs.ticks, 1)
        report["observe"] = {"ticks": obs.ticks, "recognized": obs.recognized_ticks, "status": obs.status}
        if obs.status == "failed" or ratio < 0.3:
            report["failed_step"] = "观察模式"
            return False, report
        report["steps"].append(f"观察模式识别率 {ratio:.0%}")
        # 4. limited trial run
        if kind == "workflow" and not self._confirm(FIRST_RUN, f"{wf.name}：新版本第一次试跑（分支 {branch}）", instance):
            report["failed_step"] = "用户没有同意试跑"
            return False, report
        trial = self._run_once(wf, instance, wf.param_defaults(), mode="trial",
                               max_actions=int(self.scfg.get("trial_actions", 30)), first_run_approved=True)
        report["trial"] = trial.summary()
        if trial.status == "failed":
            report["failed_step"] = "限次试跑"
            return False, report
        report["steps"].append(f"限次试跑通过（{trial.actions} 次操作）")
        return True, report

    def merge_change(self, change_id: int) -> str:
        row = self.store.query("SELECT * FROM changes WHERE id=?", (change_id,))[0]
        try:
            baseline, _ = self.store.failure_rate(row["workflow"], self.load(row["workflow"]).digest(
                                                  {"humanize": self.cfg.get("humanize"), "game": self.cfg.get("game")}),
                                                  int(self.scfg.get("rollback_window", 10)))
        except (WorkflowError, OSError):
            baseline = None   # upstream sync changes or brand-new workflows have no baseline
        with self.git_lock:
            merged = self.ws.merge(row["branch"], f"合并 {row['branch']}：{row['note'][:60]}")
        self.store.execute("UPDATE changes SET status='merged', merged_commit=?, baseline_failure_rate=? WHERE id=?",
                           (merged, baseline, change_id))
        self.store.event("info", "supervisor", f"已合并改动 #{change_id}（{row['workflow']}, {row['kind']}）")
        return merged

    def approve_change(self, change_id: int, instance: str | None = None) -> str:
        """User approval of a change waiting for confirmation (validated already)."""
        row = self.store.query("SELECT * FROM changes WHERE id=?", (change_id,))
        if not row or row[0]["status"] not in ("waiting_user",):
            raise AgentflowError("这个改动不在等待确认的状态")
        return self.merge_change(change_id)

    def reject_change(self, change_id: int) -> None:
        """User refusal of a change waiting for confirmation; the branch stays for reference."""
        cur = self.store.execute("UPDATE changes SET status='rejected' WHERE id=? AND status='waiting_user'",
                                 (change_id,))
        if cur.rowcount != 1:
            raise AgentflowError("这个改动不在等待确认的状态")
        self.store.event("info", "supervisor", f"改动 #{change_id} 被拒绝，没有合并")

    def rollback_change(self, change_id: int) -> str:
        """Undo a merged change by reverting its merge commit (a new commit; history is kept)."""
        rows = self.store.query("SELECT * FROM changes WHERE id=?", (change_id,))
        if not rows or rows[0]["status"] != "merged" or not rows[0]["merged_commit"]:
            raise AgentflowError("这个改动没有合并过，不用回滚")
        ch = rows[0]
        with self.git_lock:
            commit = self.ws.revert(ch["merged_commit"], f"回滚改动 #{change_id}（{ch['workflow']}, {ch['kind']}）")
        self.store.execute("UPDATE changes SET status='rolled_back' WHERE id=?", (change_id,))
        self.store.event("warn", "supervisor", f"已回滚改动 #{change_id}（{ch['workflow']}）")
        return commit

    # ------------------------------------------------------------------ rollback
    def check_rollback(self, name: str) -> str | None:
        rows = self.store.query("SELECT * FROM changes WHERE workflow=? AND status='merged' ORDER BY id DESC LIMIT 1",
                                (name,))
        if not rows:
            return None
        ch = rows[0]
        digest = self.load(name).digest({"humanize": self.cfg.get("humanize"), "game": self.cfg.get("game")})
        rate, n = self.store.failure_rate(name, digest, int(self.scfg.get("rollback_window", 10)))
        threshold = float(self.scfg.get("rollback_failure_rate", 0.5))
        # roll back when the new version fails often and is not better than the old one
        if n >= 3 and rate >= threshold and rate >= (ch["baseline_failure_rate"] or 0):
            with self.git_lock:
                commit = self.ws.revert(ch["merged_commit"],
                                        f"[agent] 自动回滚 #{ch['id']}：新版本最近 {n} 次失败率 {rate:.0%}")
            self.store.execute("UPDATE changes SET status='rolled_back' WHERE id=?", (ch["id"],))
            self.store.event("warn", "supervisor", f"{name} 已自动回滚改动 #{ch['id']}（失败率 {rate:.0%}）")
            logger.warning("rolled back change #%s of %s", ch["id"], name)
            return commit
        return None


class _Observe:
    observe = True

    def sleep(self, s):
        pass


def remaining_params(wf, params: dict, variables: dict) -> dict:
    """Lower max_runs by what was already done before a retry.

    The counter comes from ``counts: {done: max_runs}`` (workflows that stop on a screen, not on an
    expression) or from ``stop_when: "runs >= max_runs"``."""
    out = dict(params)
    pairs = list((wf.raw.get("counts") or {}).items())
    expr = wf.raw.get("stop_when") or ""
    pairs += re.findall(r"(\w+)\s*>=\s*(\w+)", expr)
    seen = set()
    for var, param in pairs:
        if param in seen:
            continue
        seen.add(param)
        if param in out and isinstance(variables.get(var), int) and isinstance(out[param], int):
            # Zero means that a retry may only settle/return.  Clamping to one could open an
            # additional fight after the requested quota was already reached.
            out[param] = max(0, out[param] - variables[var])
    return out


def _no_remaining_count(wf, params: dict) -> bool:
    pairs = list((wf.raw.get("counts") or {}).items())
    expr = wf.raw.get("stop_when") or ""
    pairs += re.findall(r"(\w+)\s*>=\s*(\w+)", expr)
    return bool(pairs) and any(param in params and isinstance(params[param], int) and params[param] == 0
                               for _var, param in pairs)
