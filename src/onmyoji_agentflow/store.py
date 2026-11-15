"""SQLite state: run history, LLM usage, confirmations, proposed changes."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
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
