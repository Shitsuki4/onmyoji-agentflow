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
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PLAN = {
    # 2026-11-17 起：只做日活 / 周活 / 活动，不再循环刷拾层（经验库第 7 节）
    "pause_s": 60,            # pause between rounds
    "home_between": True,     # bring the game back to the courtyard before every item
    "max_home_failures": 3,   # this many failed ``home`` runs in a row -> stop, a human is needed
    "items": [
        # 邮件 + 好友友情点
        {"workflow": "daily_rewards", "cooldown_min": 240},
        # 日活「结界突破胜利」：只挑最弱的，胜率低就停手留券
        {"workflow": "realm_raid", "params": {"max_runs": 12, "auto_refresh": 1, "max_refresh": 4,
                                              "weak_first": 1, "wins_per_page": 3, "min_win_pct": 50},
         "cooldown_min": 1440, "cooldown_on": {"突破券": 180, "胜率低": 240, "冷却": 6}},
        # 日活「挑战探索/御魂/觉醒 15 次」+ 活动门票：拾层每天 15 把就够
        {"workflow": "orochi", "params": {"max_runs": 15, "layer": 10},
         "cooldown_min": 1440, "cooldown_on": {"体力": 180}},
        # 花合战：把完成的今日 / 本周任务奖励领掉
        {"workflow": "daily_quests", "cooldown_min": 120},
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
        self._current = ""
        self._stop = threading.Event()

    # ------------------------------------------------------------------ control
    def stop(self, reason: str = "手动停止"):
        self.stop_reason = self.stop_reason or reason
        self._stop.set()
        self.app.supervisor.stop(self.instance)

    def _should_stop(self) -> bool:
        if self._stop.is_set():
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
    def _run(self, workflow: str, params: dict) -> dict:
        self._current = workflow
        t0 = self.clock()
        try:
            out = self.app.supervisor.run(workflow, self.instance, params, repair=self.repair)
            res = out.result
            rec = {"workflow": workflow, "status": res.status, "reason": res.reason,
                   "failure_kind": res.failure_kind, "failed_state": res.failed_state,
                   "vars": {k: res.variables.get(k) for k in COUNTERS if k in res.variables},
                   "notes": out.notes, "level": out.level, "ok": res.ok}
            if res.status == "failed":
                self._save_sample(res.last_frame, "failed",
                                  {"workflow": workflow, "reason": res.reason, "failure_kind": res.failure_kind,
                                   "last_states": [s for _, s in res.history[-15:]]})
        except Exception as e:  # noqa: BLE001 - keep the day going, record it
            rec = {"workflow": workflow, "status": "error", "reason": f"{type(e).__name__}: {e}", "ok": False,
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
        t.failed += 0 if rec["ok"] else 1
        t.seconds += rec["seconds"]
        for k, v in (rec.get("vars") or {}).items():
            if isinstance(v, (int, float)):
                t.counters[k] = t.counters.get(k, 0) + v
        t.last = f"{rec['status']}：{rec['reason']}"
        self.write_summary()

    def _cooldown(self, idx: int, item: dict, rec: dict):
        minutes = float(item.get("cooldown_min") or 0)
        for word, m in (item.get("cooldown_on") or {}).items():
            if word in (rec.get("reason") or ""):
                minutes = max(minutes, float(m))
        if not rec["ok"]:
            minutes = max(minutes, float(self.plan.get("failed_cooldown_min", 10)))
        self.next_ok[idx] = self.clock() + minutes * 60

    def run(self) -> str:
        sup = self.app.supervisor
        prev_sink = getattr(sup, "event_sink", None)
        sup.event_sink = self._on_event
        home_failures = 0
        try:
            while not self._should_stop():
                if self.max_rounds is not None and self.rounds >= self.max_rounds:
                    self.stop(f"跑满 {self.max_rounds} 轮")
                    break
                due = [(i, it) for i, it in enumerate(self.plan["items"]) if self.clock() >= self.next_ok.get(i, 0)]
                if not due:
                    wake = min(self.next_ok.values()) - self.clock()
                    self._wait(max(5.0, min(wake, 600.0)))
                    continue
                self.rounds += 1
                for idx, item in due:
                    if self._should_stop():
                        break
                    if self.plan.get("home_between", True):
                        h = self._run("home", {})
                        home_failures = 0 if h["ok"] else home_failures + 1
                        if home_failures >= int(self.plan.get("max_home_failures", 3)):
                            self.stop(f"连续 {home_failures} 次回不到庭院，需要人工看一下（最后一次：{h['reason']}）")
                            break
                        if not h["ok"]:
                            continue
                    rec = self._run(item["workflow"], dict(item.get("params") or {}))
                    self._cooldown(idx, item, rec)
                    if rec.get("failure_kind") == "device":
                        self.stop(f"模拟器连不上：{rec['reason']}")
                        break
                self._wait(float(self.plan.get("pause_s", 60)))
        except KeyboardInterrupt:
            self.stop("Ctrl+C")
        finally:
            sup.event_sink = prev_sink
            self.write_summary(final=True)
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
                 "| 工作流 | 次数 | 成功 | 失败 | 用时(分) | 计数 | 最后一次 |", "|---|---|---|---|---|---|---|"]
        for k, v in self.totals.items():
            cnt = "，".join(f"{names.get(c, c)} {n}" for c, n in v.counters.items())
            lines.append(f"| {k} | {v.runs} | {v.ok} | {v.failed} | {v.seconds / 60:.1f} | {cnt} | {v.last} |")
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
