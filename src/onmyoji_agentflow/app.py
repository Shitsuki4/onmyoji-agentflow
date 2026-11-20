"""Wires config, store, workspace, devices, LLM and supervisor together (used by CLI and web)."""
from __future__ import annotations

import threading

from .config import Config
from .device import Controller, HumanizeConfig, open_device
from .llm import LLMClient
from .ledger import GameLedger, ResourceBudget
from .store import Store
from .supervisor import ConfirmationBroker, Supervisor, Workspace


class App:
    def __init__(self, home=None, interactive: bool = False, device_factory=None):
        self.cfg = Config(home)
        self.store = Store(self.cfg.db_path)
        game = self.cfg.get("game") or {}
        self.ledger = GameLedger(self.store, str(game.get("account") or "default"),
                                 str(game.get("timezone") or "Asia/Shanghai"), game.get("daily_reset_hour", 0))
        self.budget = ResourceBudget(self.store, self.ledger.account, self.ledger.timezone,
                                     game.get("budgets") or {}, reset_hour=game.get("daily_reset_hour", 0))
        self.ws = Workspace(self.cfg.workspace).ensure()
        self.broker = ConfirmationBroker(self.store, interactive=interactive)
        self._devices: dict[str, object] = {}
        self._lock = threading.RLock()
        self.device_factory = device_factory or self._open_device
        providers = [p for p in self.cfg["llm"]["providers"] if p.get("enabled")]
        self.llm = LLMClient(self.cfg["llm"], self.store) if providers else None
        self.supervisor = Supervisor(self.cfg.data, self.store, self.ws, self.controller, confirm=self.broker,
                                     llm=self.llm, runs_dir=self.cfg.runs_dir)
        from .sync import SyncManager
        self.sync = SyncManager(self.cfg.data, self.store, self.ws, self.supervisor, llm=self.llm, home=self.cfg.home)
        from .plans import Plans
        from .samples import Samples
        self.plans = Plans(self)
        self.samples = Samples(self.store, self.cfg.runs_dir / "samples")

    def refresh_llm(self):
        """Pick up changed llm settings (providers switched on/off, new limits) without a restart."""
        providers = [p for p in self.cfg["llm"].get("providers") or [] if p.get("enabled")]
        if not providers:
            self.llm = None
        elif self.llm is None:
            self.llm = LLMClient(self.cfg["llm"], self.store)
        else:
            self.llm.cfg = self.cfg["llm"]
            self.llm.budget.cfg = self.cfg["llm"].get("budget") or {}
        self.supervisor.llm = self.llm
        self.sync.llm = self.llm

    def _open_device(self, instance: str):
        return open_device(self.cfg.instance(instance), self.cfg.get("mumu_root"), self.cfg.get("adb_path"))

    def device(self, instance: str):
        with self._lock:
            if instance not in self._devices:
                self._devices[instance] = self.device_factory(instance)
            return self._devices[instance]

    def controller(self, instance: str, observe: bool = False) -> Controller:
        h = self.cfg["humanize"]
        inst = self.cfg.instance(instance)
        hcfg = HumanizeConfig(style=h.get("style", "oas"), device_id=str(inst.get("serial") or inst.get("mumu_id")),
                              base_sleep_ms=int(h.get("base_sleep_ms", 0)),
                              random_sleep_ms=int(h.get("random_sleep_ms", 200)))
        return Controller(self.device(instance), hcfg, observe=observe)

    def workflows(self) -> list[str]:
        return sorted(p.stem for p in (self.ws.path / "workflows").glob("*.yaml"))

    def instance_names(self) -> list[str]:
        return [i.get("name") or str(i.get("mumu_id")) for i in self.cfg["instances"]]
