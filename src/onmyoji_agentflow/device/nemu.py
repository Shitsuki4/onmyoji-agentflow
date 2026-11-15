"""MuMu 12 fast path: screenshots and touches through MuMu's external_renderer_ipc.dll.

The heavy lifting is OAS's ``NemuIpc`` (see ``_oas/nemu_ipc.py``). Back key and
app start still go through adb, exactly like OAS does.
"""
from __future__ import annotations

import logging

import numpy as np

from .adb import AdbDevice
from .base import Device

logger = logging.getLogger(__name__)


class NemuDevice(Device):
    name = "nemu_ipc"
    supports_path = True

    def __init__(self, root: str, instance_id: int, adb: AdbDevice | None = None, touch: str = "auto"):
        from ._oas.nemu_ipc import NemuIpc  # Windows only (ctypes DLL)
        from .mumu import find_ipc_dll
        self.ipc = NemuIpc(root, instance_id, ipc_dll=find_ipc_dll(root))
        self.adb = adb
        self.touch = choose_touch(touch, adb)
        if self.touch == "adb":
            self.name = "nemu_ipc+adb_touch"

    def _touch_adb(self) -> bool:
        return self.touch == "adb" and self.adb is not None

    def screenshot(self) -> np.ndarray:
        return self.ipc.screenshot_nemu_ipc()

    def tap(self, x: int, y: int, press_ms: int = 40) -> None:
        if self._touch_adb():
            return self.adb.tap(x, y, press_ms)
        if press_ms and press_ms > 150:
            self.ipc.long_click_nemu_ipc(x, y, duration=press_ms / 1000)
        else:
            # OAS click_nemu_ipc: down, 50-110 ms, tiny jitter, up
            self.ipc.click_nemu_ipc(x, y)

    def swipe(self, p1, p2, duration_ms: int = 400) -> None:
        if self._touch_adb():
            return self.adb.swipe(p1, p2, duration_ms)
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


def choose_touch(touch: str, adb: AdbDevice | None) -> str:
    """Which channel sends taps and swipes: ``nemu`` (MuMu's dll) or ``adb``.

    OAS/ALAS's nemu touch path maps 1280x720 game coordinates into MuMu's frame assuming the
    emulator is set to the tablet layout (landscape 1280x720). On the phone layout (``wm size``
    720x1280, game rotated to landscape) the dll rotates again and taps land off-screen
    (seen on a real MuMu: (1010,175) -> x=-290). ``auto`` therefore uses nemu touch only when
    adb reports a landscape display; screenshots stay on nemu either way.
    """
    touch = (touch or "auto").lower()
    if touch in ("nemu", "adb"):
        return touch if (touch == "nemu" or adb is not None) else "nemu"
    if adb is None:
        return "nemu"
    try:
        size = adb.display().get("wm_size")
    except Exception as e:  # noqa: BLE001
        logger.warning("读不到 wm size（%s），点击改走 adb 更稳妥", e)
        return "adb"
    if size and size[0] < size[1]:
        logger.warning("MuMu 是竖屏手机版（wm size %sx%s），点击改走 adb；推荐在 MuMu 里改成平板版 1280x720", *size)
        return "adb"
    return "nemu"
