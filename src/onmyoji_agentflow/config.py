"""Configuration (config.yaml in the data folder). Secrets are never stored here."""
from __future__ import annotations

import copy
import os
from pathlib import Path

from .yamlio import dump_yaml, load_yaml

DEFAULT_CONFIG = {
    "mumu_root": None,          # MuMu 12 install folder; auto-detected when empty
    "adb_path": None,           # auto: <mumu>/shell/adb.exe or adb on PATH
    "instances": [               # one entry per MuMu 12 instance (multi-instance supported)
        {"name": "main", "mumu_id": 0, "method": "auto"},
    ],
    "humanize": {"style": "oas", "base_sleep_ms": 0, "random_sleep_ms": 200},
    "web": {"host": "127.0.0.1", "port": 8765},
    "llm": {
        # OpenAI-compatible providers, tried in order (primary first). api keys live in the
        # Windows Credential Manager under service "onmyoji-agentflow", user "llm:<name>".
        "providers": [
            {"name": "deepseek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
             "vision": False, "enabled": False},
            {"name": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
             "vision": True, "enabled": False},
            {"name": "agy", "base_url": "https://example.invalid/v1", "model": "gemini-2.5-flash",
             "vision": True, "enabled": False},
        ],
        "timeout_s": 60,
        # Usage limits. null (the default) means no limit; set a number to cap usage.
        "budget": {
            "monthly_tokens": None,         # tokens per rolling 30 days
            "daily_tokens": None,           # tokens per rolling 24 hours
            "calls_per_hour": None,
            "daily_cost": None,             # in the currency of price_per_mtok
        },
    },
    "upstream": {
        # Where `oaf sync` pulls the two upstream projects from. URLs are tried in order;
        # GitCode / Gitee mirrors are fallbacks for networks where GitHub is slow.
        "sources": {
            "assttyys": {"enabled": True, "branch": "master",
                         "urls": ["https://github.com/zzliux/assttyys_autojs.git"]},
            "oas": {"enabled": True, "branch": "master",
                    "urls": ["https://github.com/nearaura/OnmyojiAutoScript.git",
                             "https://gitcode.com/OnmyojiAutoScript/OnmyojiAutoScript.git",
                             "https://gitee.com/runheng/OnmyojiAutoScript.git"]},
        },
        "fetch_timeout_s": 900,
        "auto_merge_data": True,        # raw upstream data that no workflow uses yet merges without asking
        "schedule": {"enabled": False, "interval_hours": 24},   # used by `oaf web` and `oaf sync --loop`
        # assttyys schemes the LLM should translate into new workflows (scheme names from schemes.yaml)
        # max_per_sync: schemes translated per sync; null (the default) means no limit
        "translate": {"schemes": [], "max_per_sync": None},
    },
    "supervisor": {
        "max_local_retries": 2,
        "auto_merge": {"params": True, "images": False, "workflow": False},
        "observe_seconds": 60,
        "trial_actions": 30,
        "rollback_window": 10,          # compare the last N runs after a change
        "rollback_failure_rate": 0.5,
    },
    "mcp": {
        # `oaf mcp --http` listens here; only loopback addresses are accepted.
        "http": {"host": "127.0.0.1", "port": 8766},
        # Let an MCP client ask the person at the keyboard to approve a pending change or a
        # sensitive action (MCP elicitation, stdio only). false: approve only in the web panel or CLI.
        "elicitation_approval": True,
    },
}

# v0.1.0 wrote these limits into config.yaml by default. A config that still holds exactly
# these values is treated as untouched and switched to "no limit" (see Config._migrate).
V010_DEFAULT_BUDGET = {"monthly_tokens": 10_000_000, "daily_tokens": 400_000, "calls_per_hour": 30,
                       "daily_cost": None}
V010_DEFAULT_MAX_PER_SYNC = 2


def data_dir() -> Path:
    env = os.environ.get("OAF_HOME")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "onmyoji-agentflow"
    return Path.home() / ".onmyoji-agentflow"


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, home: Path | None = None):
        self.home = Path(home) if home else data_dir()
        self.path = self.home / "config.yaml"
        self.data = copy.deepcopy(DEFAULT_CONFIG)
        self.migrated: list[str] = []
        if self.path.exists():
            self.data = _merge(DEFAULT_CONFIG, load_yaml(self.path) or {})
            self._migrate()

    def _migrate(self):
        """Drop the limits v0.1.0 wrote by default, but only when they were never edited."""
        llm = self.data.get("llm") or {}
        budget = llm.get("budget")
        if not isinstance(budget, dict) or budget != V010_DEFAULT_BUDGET:
            return
        for k in budget:
            budget[k] = None
        self.migrated.append("llm.budget")
        tr = (self.data.get("upstream") or {}).get("translate")
        if isinstance(tr, dict) and tr.get("max_per_sync") == V010_DEFAULT_MAX_PER_SYNC:
            tr["max_per_sync"] = None
            self.migrated.append("upstream.translate.max_per_sync")
        try:
            self.save()
        except OSError:
            pass

    def save(self):
        self.home.mkdir(parents=True, exist_ok=True)
        self.path.write_text(dump_yaml(self.data), encoding="utf-8")

    def __getitem__(self, k):
        return self.data[k]

    def get(self, k, default=None):
        return self.data.get(k, default)

    # Paths inside the data folder
    @property
    def workspace(self) -> Path:
        """git repo holding the user's working copy of workflows + resources (see supervisor.versioning)."""
        return self.home / "workspace"

    @property
    def runs_dir(self) -> Path:
        return self.home / "runs"

    @property
    def db_path(self) -> Path:
        return self.home / "state.db"

    def instance(self, name: str | None) -> dict:
        inst = self.data["instances"]
        if name is None:
            return inst[0]
        for i in inst:
            if i.get("name") == name or str(i.get("mumu_id")) == str(name) or i.get("serial") == name:
                return i
        raise KeyError(f"配置里没有实例 {name}")


# ---------------------------------------------------------------------------- dotted-path access
# Used by `oaf config get/set` and the MCP tools get_config / set_config.

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

# Settings that loosen a safety rule. Changing them from an agent (MCP) needs the person's approval.
PROTECTED_PATHS = ("supervisor.auto_merge", "mcp")


def _split(path: str) -> list[str]:
    parts = [p for p in str(path or "").strip().split(".") if p != ""]
    return parts


def get_path(data, path: str):
    cur = data
    for part in _split(path):
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(f"配置里没有 {path}")
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                raise KeyError(f"配置里没有 {path}") from None
        else:
            raise KeyError(f"配置里没有 {path}")
    return cur


def parse_value(text: str):
    """Command-line value: YAML (so 123, true, null, [1, 2] and {a: 1} work); plain text otherwise."""
    try:
        return load_yaml(text)
    except Exception:  # noqa: BLE001
        return text


def _check_limit(path: str, v):
    if v is None:
        return
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise ValueError(f"{path} 要填不小于 0 的数字，或 null 表示不限")


def validate_setting(path: str, value) -> None:
    """Reject values that would break the program. Raises ValueError with a readable message."""
    parts = _split(path)
    if not parts:
        raise ValueError("要写配置项的路径，比如 llm.budget.daily_tokens")
    if parts[0] not in DEFAULT_CONFIG:
        raise ValueError(f"没有这个配置项：{parts[0]}（可用：{'、'.join(DEFAULT_CONFIG)}）")
    dotted = ".".join(parts)
    if dotted == "llm.budget":
        if not isinstance(value, dict):
            raise ValueError("llm.budget 要是一个字典")
        for k, v in value.items():
            if k not in DEFAULT_CONFIG["llm"]["budget"]:
                raise ValueError(f"llm.budget 里没有 {k}")
            _check_limit(f"llm.budget.{k}", v)
    elif dotted.startswith("llm.budget."):
        if parts[2] not in DEFAULT_CONFIG["llm"]["budget"]:
            raise ValueError(f"llm.budget 里没有 {parts[2]}")
        _check_limit(dotted, value)
    elif dotted == "upstream.translate.max_per_sync":
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError("max_per_sync 要填不小于 0 的整数，或 null 表示不限")
    elif dotted == "llm.providers":
        if not isinstance(value, list) or not all(isinstance(p, dict) and p.get("name") for p in value):
            raise ValueError("llm.providers 要是列表，每一项都要有 name")
    elif dotted == "instances":
        if not isinstance(value, list) or not value or not all(isinstance(i, dict) for i in value):
            raise ValueError("instances 要是非空列表，每一项是一个实例")
    elif dotted == "mcp.http.host" and str(value) not in LOOPBACK_HOSTS:
        raise ValueError("mcp.http.host 只能是本机地址（127.0.0.1、localhost 或 ::1）")


def set_path(data: dict, path: str, value) -> object:
    """Set ``path`` to ``value`` in place and return the old value (None when the key is new).

    Dicts that already exist are updated in place, so parts of the program that hold a
    reference to them (the LLM budget, the sync settings) see the new values at once.
    """
    parts = _split(path)
    cur = data
    for i, part in enumerate(parts[:-1]):
        if isinstance(cur, dict):
            if part not in cur or cur[part] is None:
                cur[part] = {}
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                raise KeyError(f"配置里没有 {'.'.join(parts[:i + 1])}") from None
        else:
            raise KeyError(f"{'.'.join(parts[:i])} 不是一组设置，不能往下写")
    last = parts[-1]
    if isinstance(cur, list):
        try:
            idx = int(last)
            old = copy.deepcopy(cur[idx])
        except (ValueError, IndexError):
            raise KeyError(f"配置里没有 {path}") from None
        if isinstance(cur[idx], dict) and isinstance(value, dict):
            cur[idx].clear()
            cur[idx].update(copy.deepcopy(value))
        else:
            cur[idx] = copy.deepcopy(value)
        return old
    if not isinstance(cur, dict):
        raise KeyError(f"{'.'.join(parts[:-1])} 不是一组设置，不能往下写")
    old = copy.deepcopy(cur.get(last))
    if isinstance(cur.get(last), dict) and isinstance(value, dict):
        cur[last].clear()
        cur[last].update(copy.deepcopy(value))
    elif isinstance(cur.get(last), list) and isinstance(value, list):
        cur[last][:] = copy.deepcopy(value)
    else:
        cur[last] = copy.deepcopy(value)
    return old


def _get_or_none(data, path):
    try:
        return get_path(data, path)
    except KeyError:
        return None


def needs_approval(path: str, new, data_before: dict, has_key=None) -> str | None:
    """Why changing ``path`` to ``new`` from an agent needs the person's approval, or None if it does not."""
    after = copy.deepcopy(data_before)
    set_path(after, path, new)
    for p in PROTECTED_PATHS:
        if _get_or_none(data_before, p) != _get_or_none(after, p):
            return f"{p} 是安全设置（自动合并 / MCP 批准方式），改它要你本人同意"
    host = _get_or_none(after, "web.host")
    if host != _get_or_none(data_before, "web.host") and host is not None and str(host) not in LOOPBACK_HOSTS:
        return "把网页面板开到本机以外，局域网里的人也能批准改动，要你本人同意"
    before = {p.get("name"): p for p in (_get_or_none(data_before, "llm.providers") or []) if isinstance(p, dict)}
    for p in _get_or_none(after, "llm.providers") or []:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        old_p = before.get(name)
        if old_p is not None and old_p.get("base_url") != p.get("base_url"):
            return f"供应商 {name} 的地址改了，保存的 API key 会发到新地址，要你本人同意"
        if old_p is None and has_key is not None and has_key(name):
            return f"新供应商 {name} 会用到已经保存的 API key，要你本人同意"
    return None
