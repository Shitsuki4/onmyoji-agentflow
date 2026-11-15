"""MuMu 12 fast path: screenshots and touches through MuMu's external_renderer_ipc.dll.

The heavy lifting is OAS's ``NemuIpc`` (see ``_oas/nemu_ipc.py``). Back key and
app start still go through adb, exactly like OAS does.
"""
from __future__ import annotations

import numpy as np

from .adb import AdbDevice
from .base import Device


class NemuDevice(Device):
    name = "nemu_ipc"
    supports_path = True

    def __init__(self, root: str, instance_id: int, adb: AdbDevice | None = None):
        from ._oas.nemu_ipc import NemuIpc  # Windows only (ctypes DLL)
        from .mumu import find_ipc_dll
        self.ipc = NemuIpc(root, instance_id, ipc_dll=find_ipc_dll(root))
        self.adb = adb

    def screenshot(self) -> np.ndarray:
        return self.ipc.screenshot_nemu_ipc()

    def tap(self, x: int, y: int, press_ms: int = 40) -> None:
        if press_ms and press_ms > 150:
            self.ipc.long_click_nemu_ipc(x, y, duration=press_ms / 1000)
        else:
            # OAS click_nemu_ipc: down, 50-110 ms, tiny jitter, up
            self.ipc.click_nemu_ipc(x, y)

    def swipe(self, p1, p2, duration_ms: int = 400) -> None:
        # OAS swipe_nemu_ipc: bezier path from insert_swipe streamed point by point
        self.ipc.swipe_nemu_ipc(p1, p2)

    def back(self) -> None:
        if self.adb is None:
            raise NotImplementedError("back requires adb")
        self.adb.back()

    def start_app(self, package: str) -> None:
        if self.adb is None:
            raise NotImplementedError("start_app requires adb")
        self.adb.start_app(package)

    def close(self) -> None:
        self.ipc.nemu_ipc_release()
