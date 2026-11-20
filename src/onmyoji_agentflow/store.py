"""SQLite state: run history, LLM usage, confirmations, proposed changes."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import math
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workflow TEXT, instance TEXT, mode TEXT, status TEXT,
  failure_kind TEXT, reason TEXT, digest TEXT, started REAL, ended REAL, summary TEXT);
CREATE TABLE IF NOT EXISTS llm_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, provider TEXT, model TEXT, purpose TEXT,
  prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, ok INTEGER);
CREATE TABLE IF NOT EXISTS confirmations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, category TEXT, detail TEXT, instance TEXT,
  status TEXT DEFAULT 'pending', decided REAL);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, workflow TEXT, kind TEXT, branch TEXT, commit_id TEXT,
  status TEXT, note TEXT, validation TEXT, merged_commit TEXT, baseline_failure_rate REAL);
CREATE TABLE IF NOT EXISTS syncs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started REAL, ended REAL, trigger TEXT, status TEXT,
  upstream TEXT, kind TEXT, branch TEXT, commit_id TEXT, merged_commit TEXT, change_ids TEXT,
  summary TEXT, report_path TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, level TEXT, source TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS task_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, period TEXT, scope TEXT, task_key TEXT,
  current INTEGER, target INTEGER, claimed INTEGER DEFAULT 0, status TEXT, verified INTEGER DEFAULT 0,
  evidence TEXT, updated REAL, UNIQUE(account, period, scope, task_key));
CREATE TABLE IF NOT EXISTS resource_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, period TEXT, resource TEXT,
  reserved REAL DEFAULT 0, used REAL DEFAULT 0, note TEXT, updated REAL,
  UNIQUE(account, period, resource));
CREATE TABLE IF NOT EXISTS resource_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, period TEXT, resource TEXT, amount REAL,
  phase TEXT, note TEXT, evidence TEXT, created REAL);
CREATE TABLE IF NOT EXISTS resource_authorizations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, period TEXT, costs TEXT,
  status TEXT, note TEXT, evidence TEXT, created REAL, ended REAL);
CREATE TABLE IF NOT EXISTS resource_balances (
  account TEXT, resource TEXT, amount REAL, captured REAL, verified INTEGER, evidence TEXT,
  UNIQUE(account,resource));
CREATE TABLE IF NOT EXISTS task_receipts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, period TEXT, scope TEXT, task_key TEXT,
  identity TEXT, status TEXT, evidence TEXT, updated REAL,
  UNIQUE(account,period,scope,task_key,identity));
CREATE TABLE IF NOT EXISTS plan_cooldowns (
  account TEXT, device TEXT, plan_key TEXT, item_key TEXT, next_ok REAL,
  UNIQUE(account,device,plan_key,item_key));
CREATE TABLE IF NOT EXISTS foster_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, instance TEXT, status TEXT,
  card_type TEXT, stars INTEGER, friend TEXT, started REAL, due REAL, evidence TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS marathon_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, instance TEXT, status TEXT, plan TEXT,
  started REAL, heartbeat REAL, ended REAL, stop_reason TEXT, output TEXT);
CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, workflow TEXT, kind TEXT, path TEXT,
  context TEXT, annotation TEXT, created REAL);
CREATE TABLE IF NOT EXISTS account_stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, recorded REAL, source TEXT,
  team TEXT, member TEXT, speed REAL, crit REAL, order_index INTEGER, stat_values TEXT, evidence TEXT);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    # -- runs
    def add_run(self, workflow, instance, mode, result, digest) -> int:
        s = result.summary()
        cur = self.execute(
            "INSERT INTO runs(workflow, instance, mode, status, failure_kind, reason, digest, started, ended, summary)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (workflow, instance, mode, result.status, result.failure_kind, result.reason, digest,
             time.time() - (result.ended - result.started), time.time(), json.dumps(s, ensure_ascii=False, default=str)))
        return cur.lastrowid

    def recent_runs(self, workflow: str | None = None, limit: int = 50, mode: str | None = "run") -> list[dict]:
        sql, args = "SELECT * FROM runs WHERE 1=1", []
        if workflow:
            sql += " AND workflow=?"
            args.append(workflow)
        if mode:
            sql += " AND mode=?"
            args.append(mode)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return self.query(sql, tuple(args))

    def failure_rate(self, workflow: str, digest: str | None = None, limit: int = 10) -> tuple[float, int]:
        sql, args = "SELECT status FROM runs WHERE workflow=? AND mode='run'", [workflow]
        if digest:
            sql += " AND digest=?"
            args.append(digest)
        rows = self.query(sql + " ORDER BY id DESC LIMIT ?", (*args, limit))
        if not rows:
            return 0.0, 0
        return sum(1 for r in rows if r["status"] == "failed") / len(rows), len(rows)

    # -- events
    def event(self, level: str, source: str, message: str):
        self.execute("INSERT INTO events(ts, level, source, message) VALUES (?,?,?,?)",
                     (time.time(), level, source, message))

    def recent_events(self, limit: int = 100) -> list[dict]:
        return self.query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    # -- game task/resource ledger
    def upsert_task(self, account: str, period: str, scope: str, task_key: str,
                    current: int | None = None, target: int | None = None,
                    claimed: bool | None = None, status: str | None = None,
                    verified: bool | None = None, evidence: dict | None = None, observed_at=None):
        now = time.time() if observed_at is None else float(observed_at)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute("SELECT * FROM task_ledger WHERE account=? AND period=? AND scope=? AND task_key=?",
                                         (account, period, scope, task_key)).fetchone()
                if row and (now < row["updated"] or (row["verified"] and verified is False)):
                    self._conn.commit()
                    return row["id"]
                if row:
                    self._conn.execute("""UPDATE task_ledger SET current=?,target=?,claimed=?,status=?,verified=?,evidence=?,updated=?
                                          WHERE id=?""", (
                        row["current"] if current is None else current,
                        row["target"] if target is None else target,
                        row["claimed"] if claimed is None else int(bool(claimed)),
                        row["status"] if status is None else status,
                        row["verified"] if verified is None else int(bool(verified)),
                        json.dumps(evidence, ensure_ascii=False, default=str) if evidence is not None else row["evidence"],
                        now, row["id"]))
                    result = row["id"]
                else:
                    result = self._conn.execute("""INSERT INTO task_ledger(account,period,scope,task_key,current,target,claimed,status,verified,evidence,updated)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (account, period, scope, task_key, current, target,
                        int(bool(claimed)), status, int(bool(verified)), json.dumps(evidence or {}, ensure_ascii=False), now)).lastrowid
                self._conn.commit()
                return result
            except BaseException:
                self._conn.rollback()
                raise

    def tasks(self, account: str, period: str | None = None, scope: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM task_ledger WHERE account=?", [account]
        if period is not None:
            sql += " AND period=?"
            args.append(period)
        if scope is not None:
            sql += " AND scope=?"
            args.append(scope)
        rows = self.query(sql + " ORDER BY scope, task_key", tuple(args))
        for row in rows:
            try:
                row["evidence"] = json.loads(row["evidence"] or "{}")
            except (TypeError, ValueError):
                pass
        return rows

    def resource_totals(self, account: str, period: str) -> dict[str, dict]:
        return {r["resource"]: r for r in self.query(
            "SELECT * FROM resource_ledger WHERE account=? AND period=?", (account, period))}

    def record_resource(self, account: str, period: str, resource: str, reserved: float = 0,
                        used: float = 0, note: str = ""):
        self.execute("""INSERT INTO resource_ledger(account,period,resource,reserved,used,note,updated)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(account,period,resource) DO UPDATE SET
            reserved=resource_ledger.reserved+excluded.reserved,used=resource_ledger.used+excluded.used,
            note=excluded.note,updated=excluded.updated""", (account, period, resource, reserved, used, note, time.time()))

    def spend_resources(self, account, period, costs, limits, note="", evidence=None, balances=None):
        ticket = self.authorize_resources(account, period, costs, limits, note, evidence, balances)
        self.finalize_resources(ticket, True)
        return ticket

    def authorize_resources(self, account, period, costs, limits, note="", evidence=None, balances=None):
        from .errors import BudgetExceeded
        amounts = {}
        for resource, amount in costs.items():
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise ValueError("资源费用必须是非负有限数字")
            if amount:
                amounts[resource] = float(amount)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for resource, amount in amounts.items():
                    row = self._conn.execute("SELECT used,reserved FROM resource_ledger WHERE account=? AND period=? AND resource=?",
                                             (account, period, resource)).fetchone()
                    used = row["used"] + row["reserved"] if row else 0
                    spec = limits.get(resource) or {}
                    cap = spec.get("daily_limit")
                    if cap is not None and used + amount > cap:
                        raise BudgetExceeded(f"{resource} 超出每日额度：已用/预留 {used:g}，本次 {amount:g}，上限 {cap:g}")
                    reserve = float(spec.get("reserve") or 0)
                    balance = (balances or {}).get(resource)
                    if reserve > 0 and balance is None:
                        raise BudgetExceeded(f"{resource} 设置了最低保留量，需要先读取当前余额")
                    if balance is not None and balance - amount < reserve:
                        raise BudgetExceeded(f"{resource} 扣除后会低于最低保留量 {reserve:g}")
                    self._conn.execute("""INSERT INTO resource_ledger(account,period,resource,reserved,used,note,updated)
                        VALUES (?,?,?,?,?,?,?) ON CONFLICT(account,period,resource)
                        DO UPDATE SET reserved=resource_ledger.reserved+excluded.reserved,
                                      used=resource_ledger.used+excluded.used,note=excluded.note,updated=excluded.updated""",
                        (account, period, resource, amount, 0, note, time.time()))
                    self._conn.execute("INSERT INTO resource_events(account,period,resource,amount,phase,note,evidence,created) VALUES (?,?,?,?,?,?,?,?)",
                        (account, period, resource, amount, "authorized", note, json.dumps(evidence or {}, ensure_ascii=False), time.time()))
                ticket = self._conn.execute("""INSERT INTO resource_authorizations(account,period,costs,status,note,evidence,created)
                    VALUES (?,?,?,?,?,?,?)""", (account, period, json.dumps(amounts), "authorized", note,
                    json.dumps(evidence or {}, ensure_ascii=False), time.time())).lastrowid
                self._conn.commit()
                return ticket
            except BaseException:
                self._conn.rollback()
                raise

    def finalize_resources(self, ticket, submitted):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute("SELECT * FROM resource_authorizations WHERE id=?", (ticket,)).fetchone()
                if not row or row["status"] != "authorized":
                    self._conn.commit()
                    return False
                for resource, amount in json.loads(row["costs"]).items():
                    self._conn.execute("""UPDATE resource_ledger SET reserved=reserved-?,used=used+?,updated=?
                        WHERE account=? AND period=? AND resource=?""", (amount, amount if submitted else 0,
                        time.time(), row["account"], row["period"], resource))
                    self._conn.execute("""INSERT INTO resource_events(account,period,resource,amount,phase,note,evidence,created)
                        VALUES (?,?,?,?,?,?,?,?)""", (row["account"], row["period"], resource, amount,
                        "input_attempt" if submitted else "cancelled", row["note"], row["evidence"], time.time()))
                    if submitted:
                        self._conn.execute("UPDATE resource_balances SET amount=MAX(0,amount-?) WHERE account=? AND resource=?",
                                           (amount, row["account"], resource))
                self._conn.execute("UPDATE resource_authorizations SET status=?,ended=? WHERE id=?",
                                   ("submitted" if submitted else "cancelled", time.time(), ticket))
                self._conn.commit()
                return True
            except BaseException:
                self._conn.rollback()
                raise

    def record_balance(self, account, resource, amount, evidence, captured=None):
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            raise ValueError("余额必须是非负有限数字")
        self.execute("""INSERT INTO resource_balances(account,resource,amount,captured,verified,evidence) VALUES (?,?,?,?,?,?)
            ON CONFLICT(account,resource) DO UPDATE SET amount=excluded.amount,captured=excluded.captured,
            verified=excluded.verified,evidence=excluded.evidence WHERE excluded.captured>=resource_balances.captured""",
            (account, resource, amount, time.time() if captured is None else captured, 1, json.dumps(evidence, ensure_ascii=False)))

    def balances(self, account, max_age=120):
        return {row["resource"]: row for row in self.query("SELECT * FROM resource_balances WHERE account=? AND verified=1 AND captured>=?",
                                                         (account, time.time() - max_age))}

    def resource_events(self, account, period, limit=200):
        return self.query("SELECT * FROM resource_events WHERE account=? AND period=? ORDER BY id DESC LIMIT ?",
                          (account, period, limit))

    def record_task_receipt(self, account, period, scope, task_key, identity, status, evidence):
        if not identity:
            raise ValueError("任务回执需要可去重的实例身份")
        self.execute("""INSERT INTO task_receipts(account,period,scope,task_key,identity,status,evidence,updated)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(account,period,scope,task_key,identity)
            DO UPDATE SET status=excluded.status,evidence=excluded.evidence,updated=excluded.updated""",
            (account, period, scope, task_key, identity, status, json.dumps(evidence, ensure_ascii=False), time.time()))

    def task_receipts(self, account, period, task_key):
        return self.query("SELECT * FROM task_receipts WHERE account=? AND period=? AND task_key=?",
                          (account, period, task_key))

    def cooldowns(self, account, device, plan_key):
        return {row["item_key"]: row["next_ok"] for row in self.query(
            "SELECT * FROM plan_cooldowns WHERE account=? AND device=? AND plan_key=?", (account, device, plan_key))}

    def set_cooldown(self, account, device, plan_key, item_key, next_ok):
        self.execute("""INSERT INTO plan_cooldowns(account,device,plan_key,item_key,next_ok) VALUES (?,?,?,?,?)
            ON CONFLICT(account,device,plan_key,item_key) DO UPDATE SET next_ok=excluded.next_ok""",
            (account, device, plan_key, item_key, next_ok))

    def set_foster(self, account: str, instance: str, status: str, **values):
        allowed = {"card_type", "stars", "friend", "started", "due", "evidence"}
        if set(values) - allowed:
            raise ValueError("未知寄养字段")
        now = time.time()
        old = self.query("SELECT id FROM foster_ledger WHERE account=? AND instance=? AND status IN ('active','due') "
                         "ORDER BY id DESC LIMIT 1", (account, instance))
        fields = {"status": status, "updated": now, **values}
        if old:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.execute(f"UPDATE foster_ledger SET {sets} WHERE id=?", tuple(fields.values()) + (old[0]["id"],))
            return old[0]["id"]
        keys = ["account", "instance", *fields]
        vals = [account, instance, *fields.values()]
        cur = self.execute(f"INSERT INTO foster_ledger({','.join(keys)}) VALUES ({','.join('?' for _ in vals)})", tuple(vals))
        return cur.lastrowid

    def active_foster(self, account: str, instance: str) -> list[dict]:
        rows = self.query("SELECT * FROM foster_ledger WHERE account=? AND instance=? AND status IN ('active','due') ORDER BY id DESC",
                          (account, instance))
        for row in rows:
            if row["due"] and row["due"] <= time.time():
                row["status"] = "due"
            row["evidence"] = json.loads(row["evidence"] or "{}")
        return rows

    def add_account_stat(self, account: str, source: str, team: str, member: str,
                         speed=None, crit=None, order_index=None, values=None, evidence=None):
        cur = self.execute("""INSERT INTO account_stats(account,recorded,source,team,member,speed,crit,order_index,stat_values,evidence)
                             VALUES (?,?,?,?,?,?,?,?,?,?)""",
                           (account, time.time(), source, team, member, speed, crit, order_index,
                            json.dumps(values or {}, ensure_ascii=False, default=str),
                            json.dumps(evidence or {}, ensure_ascii=False, default=str)))
        return cur.lastrowid

    def account_stats(self, account: str, team: str | None = None, limit: int = 100):
        sql, args = "SELECT * FROM account_stats WHERE account=?", [account]
        if team:
            sql += " AND team=?"
            args.append(team)
        rows = self.query(sql + " ORDER BY recorded DESC LIMIT ?", (*args, limit))
        for row in rows:
            for key in ("stat_values", "evidence"):
                try:
                    row[key] = json.loads(row[key] or "{}")
                except (TypeError, ValueError):
                    pass
        return rows

    # -- marathon lifecycle (the OS device lease remains the source of truth for ownership)
    def add_marathon_job(self, account: str, instance: str, plan: dict, output: str = ""):
        cur = self.execute("""INSERT INTO marathon_jobs(account,instance,status,plan,started,heartbeat,output)
                             VALUES (?,?,?,?,?,?,?)""",
                           (account, instance, "running", json.dumps(plan, ensure_ascii=False), time.time(),
                            time.time(), output))
        return cur.lastrowid

    def update_marathon_job(self, job_id: int, status: str | None = None, stop_reason: str | None = None,
                            output: str | None = None):
        fields = {"heartbeat": time.time()}
        if status is not None:
            fields["status"] = status
        if stop_reason is not None:
            fields["stop_reason"] = stop_reason
        if output is not None:
            fields["output"] = output
        if status in ("finished", "error", "stopped"):
            fields["ended"] = time.time()
        self.execute("UPDATE marathon_jobs SET " + ", ".join(f"{key}=?" for key in fields) + " WHERE id=?",
                     tuple(fields.values()) + (job_id,))

    def marathon_jobs(self, account: str | None = None, limit: int = 20):
        if account is None:
            return self.query("SELECT * FROM marathon_jobs ORDER BY id DESC LIMIT ?", (limit,))
        return self.query("SELECT * FROM marathon_jobs WHERE account=? ORDER BY id DESC LIMIT ?", (account, limit))
