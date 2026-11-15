"""OpenAI-compatible multi-provider client with failover and usage limits.

Every provider is ``{name, base_url, model, vision, enabled, price_per_mtok?}``;
the API key comes from the Windows Credential Manager (``credentials.get_key``).
Calls go to ``POST {base_url}/chat/completions``. Providers are tried in order;
a failing provider is skipped for ``cooldown_s``.

Limits (``llm.budget``): tokens per day / per 30 days, calls per hour and an
optional daily cost. When a limit is reached, ``BudgetExceeded`` is raised and
the supervisor falls back to handing the problem to the user.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

import cv2
import numpy as np

from . import credentials
from .errors import BudgetExceeded, LLMError
from .log import logger

DAY = 86400


class Budget:
    def __init__(self, store, cfg: dict):
        self.store = store
        self.cfg = cfg or {}

    def usage(self, since: float) -> dict:
        rows = self.store.query(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS tokens,"
            " COALESCE(SUM(cost), 0) AS cost FROM llm_usage WHERE ts >= ?", (since,))
        return rows[0]

    def snapshot(self, now: float | None = None) -> dict:
        now = now or time.time()
        return {"hour": self.usage(now - 3600), "day": self.usage(now - DAY), "month": self.usage(now - 30 * DAY),
                "limits": self.cfg}

    def check(self, now: float | None = None) -> None:
        now = now or time.time()
        c = self.cfg
        if c.get("calls_per_hour") and self.usage(now - 3600)["calls"] >= c["calls_per_hour"]:
            raise BudgetExceeded(f"大模型调用已达每小时上限 {c['calls_per_hour']} 次")
        day = self.usage(now - DAY)
        if c.get("daily_tokens") and day["tokens"] >= c["daily_tokens"]:
            raise BudgetExceeded(f"大模型用量已达每日上限 {c['daily_tokens']} token")
        if c.get("daily_cost") and day["cost"] >= c["daily_cost"]:
            raise BudgetExceeded(f"大模型费用已达每日上限 {c['daily_cost']}")
        if c.get("monthly_tokens") and self.usage(now - 30 * DAY)["tokens"] >= c["monthly_tokens"]:
            raise BudgetExceeded(f"大模型用量已达 30 天上限 {c['monthly_tokens']} token")

    def record(self, provider, model, purpose, prompt_tokens, completion_tokens, cost, ok):
        self.store.execute(
            "INSERT INTO llm_usage(ts, provider, model, purpose, prompt_tokens, completion_tokens, cost, ok)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), provider, model, purpose, int(prompt_tokens), int(completion_tokens), float(cost), int(ok)))


def image_to_data_url(img: np.ndarray, max_width: int = 960) -> str:
    h, w = img.shape[:2]
    if w > max_width:
        img = cv2.resize(img, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise LLMError("截图编码失败")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _http_post(url: str, payload: dict, key: str, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:300]
        raise LLMError(f"HTTP {e.code}: {body}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"网络错误: {e}") from e


class LLMClient:
    def __init__(self, cfg: dict, store, transport=None, key_getter=None, cooldown_s: float = 300):
        self.cfg = cfg or {}
        self.budget = Budget(store, self.cfg.get("budget"))
        self.transport = transport or _http_post
        self.key_getter = key_getter or credentials.get_key
        self.cooldown_s = cooldown_s
        self._bad_until: dict[str, float] = {}

    def providers(self, need_vision: bool = False) -> list[dict]:
        out = []
        for p in self.cfg.get("providers", []):
            if not p.get("enabled", True):
                continue
            if need_vision and not p.get("vision"):
                continue
            if self._bad_until.get(p["name"], 0) > time.time():
                continue
            out.append(p)
        return out

    def chat(self, messages: list[dict], purpose: str = "diagnose", need_vision: bool = False,
             json_mode: bool = True, max_tokens: int = 1200) -> str:
        candidates = self.providers(need_vision)
        if not candidates and need_vision:
            # fall back to a text-only provider, dropping the images
            candidates = self.providers(False)
            messages = [_strip_images(m) for m in messages]
        if not candidates:
            raise LLMError("没有可用的大模型供应商（检查 config.yaml 的 llm.providers 和密钥）")
        errors = []
        for p in candidates:
            self.budget.check()
            key = self.key_getter(p["name"])
            if not key:
                errors.append(f"{p['name']}: 没有密钥")
                continue
            payload = {"model": p["model"], "messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
            if json_mode and p.get("json_mode", True):
                payload["response_format"] = {"type": "json_object"}
            url = p["base_url"].rstrip("/") + "/chat/completions"
            try:
                data = self.transport(url, payload, key, float(self.cfg.get("timeout_s", 60)))
                text = data["choices"][0]["message"]["content"]
            except (LLMError, KeyError, IndexError, TypeError) as e:
                self._bad_until[p["name"]] = time.time() + self.cooldown_s
                self.budget.record(p["name"], p["model"], purpose, 0, 0, 0, False)
                errors.append(f"{p['name']}: {e}")
                logger.warning("LLM provider %s failed: %s", p["name"], e)
                continue
            usage = data.get("usage") or {}
            pt, ct = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
            cost = (pt + ct) / 1e6 * float(p.get("price_per_mtok", 0) or 0)
            self.budget.record(p["name"], p["model"], purpose, pt, ct, cost, True)
            return text
        raise LLMError("所有大模型供应商都失败了：" + "；".join(errors))


def _strip_images(msg: dict) -> dict:
    c = msg.get("content")
    if isinstance(c, list):
        texts = [part.get("text", "") for part in c if part.get("type") == "text"]
        return {**msg, "content": "\n".join(texts) + "\n（没有支持图片的模型可用，已省略截图）"}
    return msg


def parse_json_reply(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < 0:
        raise LLMError("大模型没有返回 JSON")
    try:
        return json.loads(t[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"大模型返回的 JSON 无法解析: {e}") from e
