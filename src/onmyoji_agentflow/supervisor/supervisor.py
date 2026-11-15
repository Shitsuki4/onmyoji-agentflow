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
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from ..errors import AgentflowError, BudgetExceeded, LLMError, WorkflowError
from ..llm import image_to_data_url, parse_json_reply
from ..log import logger
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

    # ------------------------------------------------------------------ basics
    def load(self, name: str, root: Path | None = None):
        root = root or self.ws.path
        return load_workflow(root / "workflows" / f"{name}.yaml", [root / "resources"])

    def _confirm(self, category: str, detail: str, instance: str = "") -> bool:
        if self.confirm is None:
            return False
        try:
            return bool(self.confirm(category, detail, instance))
        except TypeError:
            return bool(self.confirm(category, detail))

    def _run_once(self, wf, instance: str, params: dict, mode: str = "run", max_actions=None, max_seconds=None,
                  observe: bool = False) -> RunResult:
        ctl = self.controller_factory(instance, observe)
        flag = self.stop_flags.setdefault(instance, threading.Event())
        runner = Runner(wf, ctl, params=params,
                        confirm=lambda c, d: self._confirm(c, d, instance),
                        max_actions=max_actions, max_seconds=max_seconds, should_stop=flag.is_set, clock=self.clock,
                        on_event=lambda k, d: self._on_event(instance, k, d))
        res = runner.run()
        run_id = self.store.add_run(wf.name, instance, mode, res, wf.digest())
        if res.status == "failed" and res.last_frame is not None:
            folder = self.runs_dir / f"{run_id:06d}"
            folder.mkdir(parents=True, exist_ok=True)
            cv2.imencode(".png", res.last_frame)[1].tofile(str(folder / "failure.png"))
            (folder / "summary.json").write_text(json.dumps(res.summary(), ensure_ascii=False, indent=2, default=str),
                                                 encoding="utf-8")
        return res

    def _on_event(self, instance, kind, data):
        if kind in ("start", "end"):
            msg = f"[{instance}] {kind}: " + json.dumps(data, ensure_ascii=False, default=str)[:400]
            self.store.event("info", "run", msg)

    def stop(self, instance: str):
        self.stop_flags.setdefault(instance, threading.Event()).set()

    # ------------------------------------------------------------------ main entry
    def run(self, name: str, instance: str = "main", params: dict | None = None, repair: bool = True) -> Outcome:
        self.stop_flags.setdefault(instance, threading.Event()).clear()
        wf = self.load(name)
        params = {**wf.param_defaults(), **(params or {})}
        res = self._run_once(wf, instance, params)
        outcome = Outcome(res)
        retries = 0
        while res.status == "failed" and res.failure_kind not in ("confirm_denied", "prerequisite") and retries < int(
                self.scfg.get("max_local_retries", 2)) and not self.stop_flags[instance].is_set():
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
            params = remaining_params(wf, params, res.variables)
            res = self._run_once(wf, instance, params)
            outcome.result = res
        self.check_rollback(name)
        if res.status != "failed" or not repair:
            if res.status == "failed":
                outcome.level = "human"
            return outcome
        if res.failure_kind in ("confirm_denied", "device", "prerequisite"):
            outcome.level = "human"
            outcome.notes.append("需要你处理：" + res.reason)
            self.store.event("error", "supervisor", f"{name}@{instance} 需要人工处理：{res.reason}")
            return outcome
        try:
            note = self.diagnose_and_repair(wf, instance, res)
            outcome.level = note[0]
            outcome.notes.append(note[1])
        except (LLMError, BudgetExceeded, WorkflowError, AgentflowError) as e:
            outcome.level = "human"
            outcome.notes.append(f"自动修复没做成：{e}")
            self.store.event("error", "supervisor", f"{name}@{instance} 自动修复没做成：{e}")
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
        if not auto_ok:
            detail = f"{wf.name}：{kind} 修改已通过验证（{proposal.get('diagnosis', '')}），分支 {branch}"
            if not self._confirm(NEEDS_CONFIRM_MERGE, detail, instance):
                self.store.execute("UPDATE changes SET status='waiting_user' WHERE id=?", (cid,))
                return "proposed", f"修改已通过验证，等你确认后才会替换（分支 {branch}）"
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
        report["steps"].append(f"回放测试 {len(results)} 个全部通过")
        if instance is None:
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
                               max_actions=int(self.scfg.get("trial_actions", 30)))
        report["trial"] = trial.summary()
        if trial.status == "failed":
            report["failed_step"] = "限次试跑"
            return False, report
        report["steps"].append(f"限次试跑通过（{trial.actions} 次操作）")
        return True, report

    def merge_change(self, change_id: int) -> str:
        row = self.store.query("SELECT * FROM changes WHERE id=?", (change_id,))[0]
        try:
            baseline, _ = self.store.failure_rate(row["workflow"], self.load(row["workflow"]).digest(),
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
        digest = self.load(name).digest()
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
            out[param] = max(1, out[param] - variables[var])
    return out
