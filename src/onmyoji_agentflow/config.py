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
        "budget": {
            "monthly_tokens": 10_000_000,   # ~10M tokens a month by default
            "daily_tokens": 400_000,
            "calls_per_hour": 30,
            "daily_cost": None,             # optional, in the currency of price_per_mtok
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
        "translate": {"schemes": [], "max_per_sync": 2},
    },
    "supervisor": {
        "max_local_retries": 2,
        "auto_merge": {"params": True, "images": False, "workflow": False},
        "observe_seconds": 60,
        "trial_actions": 30,
        "rollback_window": 10,          # compare the last N runs after a change
        "rollback_failure_rate": 0.5,
    },
}


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
        if self.path.exists():
            self.data = _merge(DEFAULT_CONFIG, load_yaml(self.path) or {})

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
