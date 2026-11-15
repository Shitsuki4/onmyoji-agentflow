"""User confirmations for sensitive operations and for changes that need approval.

A request is stored in SQLite as ``pending``; the web panel or ``oaf confirm``
answers it. In an interactive terminal the CLI can also ask directly. A
request that is not answered within ``timeout_s`` counts as a refusal.
"""
from __future__ import annotations

import sys
import time

from ..log import logger


class ConfirmationBroker:
    def __init__(self, store, interactive: bool = False, timeout_s: float = 600, poll_s: float = 1.0,
                 sleep=time.sleep, input_fn=input):
        self.store = store
        self.interactive = interactive
        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self.sleep = sleep
        self.input_fn = input_fn

    def request(self, category: str, detail: str, instance: str = "") -> int:
        cur = self.store.execute("INSERT INTO confirmations(created, category, detail, instance) VALUES (?,?,?,?)",
                                 (time.time(), category, detail, instance))
        self.store.event("warn", "confirm", f"等待确认 #{cur.lastrowid}：{category} - {detail}")
        return cur.lastrowid

    def decide(self, cid: int, approve: bool) -> bool:
        cur = self.store.execute("UPDATE confirmations SET status=?, decided=? WHERE id=? AND status='pending'",
                                 ("approved" if approve else "denied", time.time(), cid))
        return cur.rowcount == 1

    def status(self, cid: int) -> str:
        rows = self.store.query("SELECT status FROM confirmations WHERE id=?", (cid,))
        return rows[0]["status"] if rows else "missing"

    def pending(self) -> list[dict]:
        return self.store.query("SELECT * FROM confirmations WHERE status='pending' ORDER BY id")

    def wait(self, cid: int) -> bool:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            st = self.status(cid)
            if st != "pending":
                return st == "approved"
            self.sleep(self.poll_s)
        self.store.execute("UPDATE confirmations SET status='expired', decided=? WHERE id=? AND status='pending'",
                           (time.time(), cid))
        logger.warning("confirmation #%s expired", cid)
        return False

    def __call__(self, category: str, detail: str, instance: str = "") -> bool:
        cid = self.request(category, detail, instance)
        if self.interactive and sys.stdin and sys.stdin.isatty():
            answer = self.input_fn(f"\n需要你确认：{category} - {detail}\n输入 yes 同意，其他任意内容拒绝：")
            approve = answer.strip().lower() in ("y", "yes")
            self.decide(cid, approve)
            return approve
        return self.wait(cid)
