"""``oaf marathon``: run several dailies in a loop for hours, with per-run logs, totals and samples.

One round = every item of the plan whose cooldown has passed, in order. Before each item the game
is brought back to the courtyard with the ``home`` workflow, so a failed item does not leave the
next one on a strange screen. Everything lands in ``<home>/marathon/<YYYYmmdd-HHMMSS>/``:

* ``events.jsonl``  one line per item run (status, reason, counters, duration)
* ``summary.json`` / ``summary.md``  running totals per workflow, rewritten after every item
* ``samples/``  a screenshot for every screen nobody recognised (> ``unknown_sample_s``) and the
  last frame of every failed run, with a json next to it saying where it happened. These are the
  material to learn from afterwards: add a state or a blocker for them and replay them as tests.

Stop it with Ctrl+C, by creating a file named ``STOP`` in that folder, or with ``--hours`` / ``--until``.
"""
from __future__ import annotations

import datetime as _dt
import json
import hashlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .errors import BudgetExceeded
from .ledger import GameLedger, ResourceBudget
from .tasks import remaining_task
from .runtime import normalize_device_identity

DEFAULT_PLAN = {
    # 2026-11-17 起：只做日活 / 周活 / 活动，不再循环刷拾层（经验库第 7 节）
    "pause_s": 60,            # pause between rounds
    "home_between": True,     # bring the game back to the courtyard before every item
    "max_home_failures": 3,   # this many failed ``home`` runs in a row -> stop, a human is needed
    "continuous": False,
    "task_aware": True,
    "batch_limit": 3,
    "items": [
        {"workflow": "task_scan", "scope": "daily"},
        # 邮件 + 好友友情点
        {"workflow": "daily_rewards", "task_key": "mail_and_friend_points", "scope": "daily",
         "once_per_period": True, "cooldown_min": 240},
        # 寄养只在没有有效寄养时尝试；工作流先观察候选，无法识别卡型/星级就暂停留图
        {"workflow": "foster", "task_key": "foster_started", "scope": "daily",
         "cooldown_min": 15},
        # 日活「结界突破胜利」：只挑最弱的，胜率低就停手留券
        {"workflow": "realm_raid", "task_key": "realm_raid_wins", "scope": "daily", "once_per_period": True,
         "goal": "realm_raid_wins",
         "params": {"max_runs": 12, "auto_refresh": 1, "max_refresh": 4,
                                              "weak_first": 1, "wins_per_page": 3, "min_win_pct": 50},
         "cost": {"realm_ticket_per_run": 1},
         "cooldown_min": 1440, "cooldown_on": {"突破券": 180, "胜率低": 240, "冷却": 6}},
        # 日活「挑战探索/御魂/觉醒 15 次」+ 活动门票：拾层每天 15 把就够
        {"workflow": "orochi", "task_key": "battle_15", "scope": "daily", "once_per_period": True,
         "goal": "battle_15",
         "params": {"max_runs": 15, "layer": 10}, "cost": {"stamina_per_run": 6},
         "cooldown_min": 1440, "cooldown_on": {"体力": 180}},
        # 花合战：把完成的今日 / 本周任务奖励领掉
        {"workflow": "daily_quests", "task_key": "flower_battle_rewards", "scope": "daily",
         "once_per_period": True, "cooldown_min": 120},
        {"workflow": "regional_boss", "scope": "weekly", "goal": "regional_boss",
         "params": {"max_runs": 1}, "profile": "regional_boss"},
        {"workflow": "delegation", "scope": "weekly", "goal": "delegation", "profile": "delegation"},
    ],
}

# counters a workflow keeps in its variables (summed into the totals)
COUNTERS = ("done", "rounds", "losses", "refreshes", "claimed")


def load_plan(path: str | None) -> dict:
    plan = json.loads(json.dumps(DEFAULT_PLAN))
    if path:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        plan.update({k: v for k, v in raw.items() if k != "items"})
        if raw.get("items"):
            plan["items"] = raw["items"]
    for it in plan["items"]:
        it.setdefault("params", {})
        it.setdefault("cooldown_min", 0)
        it.setdefault("cooldown_on", {})
    return plan


def plan_yaml(plan: dict | None = None) -> str:
    return yaml.safe_dump(plan or DEFAULT_PLAN, allow_unicode=True, sort_keys=False)


@dataclass
class Totals:
    runs: int = 0
    ok: int = 0
    failed: int = 0
    business_ok: int = 0
    blocked: int = 0
    seconds: float = 0.0
    counters: dict = field(default_factory=dict)
    last: str = ""


class Marathon:
    def __init__(self, app, instance: str, plan: dict, out_dir: Path, *, deadline: float | None = None,
                 repair: bool = False, clock=time.time, sleep=time.sleep, max_rounds: int | None = None):
        self.app = app
        self.instance = instance
        self.plan = plan
        self.dir = Path(out_dir)
        (self.dir / "samples").mkdir(parents=True, exist_ok=True)
        self.deadline = deadline
        self.repair = repair
        self.clock = clock
        self.sleep = sleep
        self.max_rounds = max_rounds
        self.totals: dict[str, Totals] = {}
        self.next_ok: dict[int, float] = {}      # item index -> earliest next start
        self.started = clock()
        self.rounds = 0
        self.samples = 0
        self.unknown_contexts: dict[str, int] = {}
        self.stop_reason = ""
        self.job_id = None
        self.lease = None
        self._current = ""
        self._stop = threading.Event()
        cfg = getattr(app, "cfg", None)
        game = (cfg.get("game") if cfg else {}) or {}
        self.account = str(game.get("account") or "default")
        self.ledger = GameLedger(app.store, self.account, str(game.get("timezone") or "Asia/Shanghai"),
                                 game.get("daily_reset_hour", 0)) if getattr(app, "store", None) else None
        self.budget = ResourceBudget(app.store, self.account, str(game.get("timezone") or "Asia/Shanghai"),
                                     game.get("budgets") or {}, game.get("daily_reset_hour", 0)) if getattr(app, "store", None) else None
        self.device_key = normalize_device_identity(cfg.instance(instance) if hasattr(cfg, "instance") else instance)
        self.plan_key = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
        self._watch_stop = threading.Event()
        self._load_state()

    def _state_path(self) -> Path:
        return self.dir / "marathon-state.json"

    def _load_state(self):
        if self.ledger:
            rows = self.app.store.cooldowns(self.account, self.device_key, self.plan_key)
            self.next_ok.update({int(key): value for key, value in rows.items()})
            return
        try:
            data = json.loads(self._state_path().read_text(encoding="utf-8"))
            self.next_ok.update({int(k): float(v) for k, v in (data.get("next_ok") or {}).items()})
        except (FileNotFoundError, OSError, ValueError, TypeError):
            pass

    def _save_state(self):
        if self.ledger:
            for index, value in self.next_ok.items():
                self.app.store.set_cooldown(self.account, self.device_key, self.plan_key, str(index), value)
        self._state_path().write_text(json.dumps({"next_ok": self.next_ok}, ensure_ascii=False, indent=2),
                                      encoding="utf-8")

    def _period(self, scope: str):
        if not self.ledger:
            return None
        day, week = self.ledger.periods()
        return week if scope == "weekly" else day

    def _done_for_period(self, item: dict) -> bool:
        if not item.get("once_per_period") or not self.ledger:
            return False
        key = item.get("task_key") or item["workflow"]
        rows = self.ledger.store.tasks(self.account, self._period(item.get("scope", "daily")), item.get("scope", "daily"))
        return any(r["task_key"] == key and r.get("status") in ("completed", "claimed") and r.get("verified") for r in rows)

    def _mark_task(self, item: dict, rec: dict):
        if not self.ledger or not item.get("task_key") or item.get("goal"):
            return
        verified = bool(rec.get("business_ok"))
        self.ledger.store.upsert_task(self.account, self._period(item.get("scope", "daily")),
                                      item.get("scope", "daily"), item["task_key"],
                                      status="completed" if verified else "unknown", verified=verified,
                                      evidence=rec.get("evidence") or {"reason": rec.get("reason")})

    def item_params(self, item):
        params = dict(item.get("params") or {})
        if item.get("profile"):
            profile = (self.app.cfg.get("game", {}).get("profiles") or {}).get(item["profile"], {})
            if not profile.get("verified") or not profile.get("evidence"):
                return None, "缺少已核对的账号难度/队伍档案"
            params.update(profile.get("params") or {})
            options = profile.get("targets")
            if options:
                key = "boss_name" if item["workflow"] == "regional_boss" else "task_name"
                receipts = self.app.store.task_receipts(self.account, self._period(item.get("scope", "weekly")), item["goal"])
                identities = {row["identity"] for row in receipts if row["status"] in ("completed", "active")}
                choice = next((target for target in options if target.get(key) not in identities), None)
                if choice is None:
                    return None, "档案中的地域/委派实例已完成或正在进行"
                params.update(choice)
        if item.get("goal") and self.ledger:
            rows = self.ledger.snapshot(item.get("scope", "daily"))
            rows = [row for row in rows if self.clock() - row["updated"] < 900]
            remaining = remaining_task(rows, item["goal"])
            if remaining is None:
                return None, "未读取到近期游戏任务进度，保留资源"
            if remaining == 0:
                return None, "游戏目标已经达到"
            limit = min(remaining, int(self.plan.get("batch_limit", 3)))
            for key in ("max_runs", "max_rounds", "max_fights"):
                if key in params:
                    params[key] = min(params[key], limit)
            if item["workflow"] == "orochi" and params.get("layer", 0) < 10:
                return None, "未选择已验证的高收益御魂难度"
        if item["workflow"] == "foster" and self.ledger:
            active = self.app.store.active_foster(self.account, self.instance)
            if active and (active[0].get("due") or 0) > self.clock():
                return None, f"寄养尚未到期：{active[0]['due']}"
        return params, "待执行"

    # ------------------------------------------------------------------ control
    def stop(self, reason: str = "手动停止"):
        self.stop_reason = self.stop_reason or reason
        self._stop.set()
        self.app.supervisor.stop(self.instance)

    def _should_stop(self) -> bool:
        if self._stop.is_set():
            return True
        if self.lease and self.lease.stop_mode():
            self.stop_reason = self.stop_reason or "收到跨入口停止请求"
            return True
        if (self.dir / "STOP").exists():
            self.stop("发现 STOP 文件")
            return True
        if self.deadline is not None and self.clock() >= self.deadline:
            self.stop("到了设定的结束时间")
            return True
        return False

    def _wait(self, seconds: float):
        end = self.clock() + seconds
        while not self._should_stop() and self.clock() < end:
            self.sleep(min(5.0, max(0.0, end - self.clock())))

    # ------------------------------------------------------------------ samples
    def _save_sample(self, frame, kind: str, info: dict):
        if frame is None:
            return
        import cv2
        self.samples += 1
        name = f"{self.samples:04d}-{kind}-{info.get('workflow', '')}"
        cv2.imencode(".png", frame)[1].tofile(str(self.dir / "samples" / f"{name}.png"))
        (self.dir / "samples" / f"{name}.json").write_text(
            json.dumps({**info, "kind": kind, "time": _dt.datetime.now().isoformat(timespec="seconds")},
                       ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _on_event(self, instance, kind, data):
        if instance != self.instance or kind != "unknown":
            return
        ctx = f"{self._current} 在「{data.get('after_state') or '开始'}」之后"
        self.unknown_contexts[ctx] = self.unknown_contexts.get(ctx, 0) + 1
        if self.unknown_contexts[ctx] <= 5:   # enough to learn from, without filling the disk
            self._save_sample(data.get("frame"), "unknown",
                              {"workflow": self._current, "after_state": data.get("after_state"),
                               "seconds": data.get("seconds")})

    # ------------------------------------------------------------------ running
    def _run(self, workflow: str, params: dict, item: dict | None = None) -> dict:
        self._current = workflow
        t0 = self.clock()
        item = item or next((it for it in self.plan["items"] if it["workflow"] == workflow and
                             dict(it.get("params") or {}) == dict(params)), None)
        try:
            if item and self.budget:
                costs = {}
                n = float(params.get("max_runs") or params.get("max_rounds") or 1)
                for key, value in (item.get("cost") or {}).items():
                    if key.endswith("_per_run"):
                        costs[key[:-8]] = float(value) * n
                    else:
                        costs[key] = float(value)
                if costs:
                    self.budget.check(costs)
            out = self.app.supervisor.run(workflow, self.instance, params, repair=self.repair)
            res = out.result
            rec = {"workflow": workflow, "status": res.status, "reason": res.reason,
                   "failure_kind": res.failure_kind, "failed_state": res.failed_state,
                   "vars": {k: res.variables.get(k) for k in COUNTERS if k in res.variables},
                   "notes": out.notes, "level": out.level, "ok": res.ok,
                   "business_result": res.business_result, "business_ok": res.business_ok,
                   "evidence": res.evidence}
            if item:
                self._mark_task(item, rec)
            if res.status == "failed":
                self._save_sample(res.last_frame, "failed",
                                  {"workflow": workflow, "reason": res.reason, "failure_kind": res.failure_kind,
                                   "last_states": [s for _, s in res.history[-15:]]})
        except Exception as e:  # noqa: BLE001 - keep the day going, record it
            rec = {"workflow": workflow, "status": "error", "reason": f"{type(e).__name__}: {e}", "ok": False,
                   "business_result": "blocked", "business_ok": False, "evidence": {},
                   "vars": {}, "notes": [], "level": "human"}
        rec.update(seconds=round(self.clock() - t0, 1), round=self.rounds,
                   time=_dt.datetime.now().isoformat(timespec="seconds"), params=params)
        self._record(rec)
        return rec

    def _record(self, rec: dict):
        with open(self.dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        t = self.totals.setdefault(rec["workflow"], Totals())
        t.runs += 1
        t.ok += 1 if rec["ok"] else 0
        t.business_ok += 1 if rec.get("business_ok") else 0
        t.blocked += 1 if rec.get("business_result") in ("blocked", "skipped") else 0
        t.failed += 0 if rec["ok"] else 1
        t.seconds += rec["seconds"]
        for k, v in (rec.get("vars") or {}).items():
            if isinstance(v, (int, float)):
                t.counters[k] = t.counters.get(k, 0) + v
        t.last = f"{rec['status']}：{rec['reason']}"
        if self.job_id is not None:
            self.app.store.update_marathon_job(self.job_id, output=str(self.dir),
                                               stop_reason=self.stop_reason or None)
        self.write_summary()

    def _cooldown(self, idx: int, item: dict, rec: dict):
        minutes = float(item.get("cooldown_min") or 0)
        for word, m in (item.get("cooldown_on") or {}).items():
            if word in (rec.get("reason") or ""):
                minutes = max(minutes, float(m))
        if not rec["ok"]:
            minutes = max(minutes, float(self.plan.get("failed_cooldown_min", 10)))
        self.next_ok[idx] = self.clock() + minutes * 60
        self._save_state()

    def _watchdog(self):
        while not self._watch_stop.is_set():
            if self._should_stop():
                return
            self._watch_stop.wait(0.5)

    def run(self) -> str:
        with self.app.supervisor.execution(self.instance, f"marathon:{self.account}") as lease:
            self.lease = lease
            return self._run_locked()

    def _skip(self, item, reason):
        self._record({"workflow": item["workflow"], "status": "skipped", "reason": reason,
                      "ok": True, "business_ok": False, "business_result": "skipped",
                      "seconds": 0, "vars": {}, "evidence": {}})

    def _scan(self):
        if self._should_stop():
            return False
        home = self._run("home", {})
        if not home["ok"] or self._should_stop():
            self.stop_reason = self.stop_reason or "回庭院失败，未继续任务扫描"
            return False
        scan = self._run("task_scan", {})
        if scan.get("failure_kind") in ("unknown_screen", "device", "recognition"):
            self.stop(f"任务扫描未通过：{scan['reason']}")
        return scan["ok"] and not self._should_stop()

    def _goal_remaining(self, item):
        rows = self.ledger.snapshot(item.get("scope", "daily")) if self.ledger else []
        return remaining_task([row for row in rows if self.clock() - row["updated"] < 900], item["goal"])

    def _run_item(self, index, item):
        batches = int(self.plan.get("max_batches_per_task", 10)) if item.get("goal") else 1
        for batch in range(batches):
            if self._should_stop():
                return
            params, reason = self.item_params(item)
            if params is None:
                self._skip(item, reason)
                return
            if batch and self.plan.get("home_between", True):
                home = self._run("home", {})
                if not home["ok"] or self._should_stop():
                    return
            before = self._goal_remaining(item) if item.get("goal") else None
            rec = self._run(item["workflow"], params, item)
            self._cooldown(index, item, rec)
            if self._should_stop():
                return
            if rec.get("failure_kind") in ("unknown_screen", "device", "recognition"):
                self.stop(f"{item['workflow']} 未能可靠识别/连接，已留图暂停")
                return
            if not item.get("goal") or rec.get("status") != "success" or not rec.get("business_ok"):
                return
            if not self._scan():
                return
            after = self._goal_remaining(item)
            if after == 0:
                return
            if after is None or before is None or after >= before:
                self._skip(item, "执行后游戏进度没有可核验的增加，本轮不再消耗")
                return
        self._skip(item, "已达到本任务小批次上限，剩余目标保留待办")

    def _run_locked(self) -> str:
        sup = self.app.supervisor
        self.job_id = self.app.store.add_marathon_job(self.account, self.instance, self.plan, str(self.dir))
        prev_sink = getattr(sup, "event_sink", None)
        sup.event_sink = self._on_event
        home_failures = 0
        watchdog = threading.Thread(target=self._watchdog, name="oaf-marathon-watchdog", daemon=True)
        watchdog.start()
        job_status = "finished"
        try:
            if self.plan.get("task_aware") and not self._scan():
                self.stop_reason = self.stop_reason or "启动核对未完成，停止计划"
                return self.stop_reason
            while not self._should_stop():
                if self.max_rounds is not None and self.rounds >= self.max_rounds:
                    self.stop(f"跑满 {self.max_rounds} 轮")
                    break
                due = [(i, it) for i, it in enumerate(self.plan["items"])
                       if not self._done_for_period(it) and self.clock() >= self.next_ok.get(i, 0)
                       and not (self.plan.get("task_aware") and it["workflow"] == "task_scan")]
                if not due:
                    if not self.plan.get("continuous", False):
                        self.stop_reason = "本轮可执行目标已处理，冷却项与未验证项保留待办"
                        break
                    pending = [self.next_ok.get(i, self.clock() + 600) for i, it in enumerate(self.plan["items"])
                               if not self._done_for_period(it)]
                    if not pending and any(it.get("once_per_period") for it in self.plan["items"]):
                        self.stop("本周期已完成的任务都已核对，自动停止")
                        break
                    wake = min(pending or [self.clock() + 600]) - self.clock()
                    self._wait(max(5.0, min(wake, 600.0)))
                    continue
                self.rounds += 1
                for idx, item in due:
                    if self._should_stop():
                        break
                    params, reason = self.item_params(item)
                    if params is None:
                        self._skip(item, reason)
                        continue
                    if self.plan.get("home_between", True):
                        h = self._run("home", {})
                        home_failures = 0 if h["ok"] else home_failures + 1
                        if home_failures >= int(self.plan.get("max_home_failures", 3)):
                            self.stop(f"连续 {home_failures} 次回不到庭院，需要人工看一下（最后一次：{h['reason']}）")
                            break
                        if not h["ok"]:
                            continue
                    self._run_item(idx, item)
                if not self.plan.get("continuous", False):
                    self.stop_reason = self.stop_reason or "本轮计划结束，未确认的目标保留待办"
                    break
                self._wait(float(self.plan.get("pause_s", 60)))
        except KeyboardInterrupt:
            self.stop("Ctrl+C")
        except BaseException:
            job_status = "error"
            raise
        finally:
            self._watch_stop.set()
            watchdog.join(timeout=1)
            sup.event_sink = prev_sink
            self.write_summary(final=True)
            if self._stop.is_set() or (self.lease and self.lease.stop_mode()):
                job_status = "stopped"
            self.app.store.update_marathon_job(self.job_id, job_status, self.stop_reason, str(self.dir))
        return self.stop_reason

    # ------------------------------------------------------------------ report
    def write_summary(self, final: bool = False):
        data = {
            "started": _dt.datetime.fromtimestamp(self.started).isoformat(timespec="seconds"),
            "updated": _dt.datetime.now().isoformat(timespec="seconds"),
            "hours": round((self.clock() - self.started) / 3600, 2), "rounds": self.rounds,
            "finished": final, "stop_reason": self.stop_reason, "samples": self.samples,
            "unknown_screens": self.unknown_contexts,
            "workflows": {k: vars(v) for k, v in self.totals.items()},
        }
        (self.dir / "summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                                               encoding="utf-8")
        names = {"done": "打完", "rounds": "轮", "losses": "输", "refreshes": "刷新", "claimed": "领到"}
        lines = [f"# 连续日常 {data['started']}", "",
                 f"- 已运行 {data['hours']} 小时，{self.rounds} 轮；" + (
                     f"已停止：{self.stop_reason}" if final else "还在跑"),
                 f"- 留下的样本截图：{self.samples} 张（samples/）", "",
                 "| 工作流 | 执行 | 执行失败 | 业务完成 | 阻塞/跳过 | 用时(分) | 计数 | 最后一次 |",
                 "|---|---:|---:|---:|---:|---:|---|---|"]
        for k, v in self.totals.items():
            cnt = "，".join(f"{names.get(c, c)} {n}" for c, n in v.counters.items())
            lines.append(f"| {k} | {v.runs} | {v.failed} | {v.business_ok} | {v.blocked} | {v.seconds / 60:.1f} | {cnt} | {v.last} |")
        if self.unknown_contexts:
            lines += ["", "认不出的画面（按出现次数）：", ""]
            for ctx, n in sorted(self.unknown_contexts.items(), key=lambda x: -x[1]):
                lines.append(f"- {ctx}：{n} 次")
        (self.dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_deadline(hours: float | None, until: str | None, now: float | None = None) -> float | None:
    now = time.time() if now is None else now
    if hours:
        return now + float(hours) * 3600
    if until:
        hh, mm = (int(x) for x in until.replace("：", ":").split(":"))
        # wall-clock difference instead of datetime.timestamp(): on Windows that raises OSError for
        # moments near or before the epoch
        base = _dt.datetime.fromtimestamp(now)
        t = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta = (t - base).total_seconds()
        if delta <= 0:
            delta += 86400
        return now + delta
    return None
