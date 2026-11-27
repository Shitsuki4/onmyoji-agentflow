"""Device abstraction used by the engine.

Coordinates are always in the 1280x720 development resolution (both OAS and
assttyys use it). Backends scale if the emulator runs at another size, but
the README asks users to set MuMu 12 to 1280x720.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np

from ..log import logger
from .humanize import HumanizeConfig, after_delay_ms, pick_point, press_ms, swipe_points

DEV_W, DEV_H = 1280, 720


class Device(ABC):
    """Low level device. Subclasses implement raw input at exact coordinates."""

    name = "device"
    supports_path = False  # True when the backend can stream a swipe point by point

    @abstractmethod
    def screenshot(self) -> np.ndarray:
        """BGR image, ideally 1280x720."""

    @abstractmethod
    def tap(self, x: int, y: int, press_ms: int = 40) -> None: ...

    @abstractmethod
    def swipe(self, p1: tuple[int, int], p2: tuple[int, int], duration_ms: int = 400) -> None: ...

    def back(self) -> None:
        raise NotImplementedError

    def start_app(self, package: str) -> None:
        raise NotImplementedError

    def restart_app(self, package: str) -> None:
        raise NotImplementedError

    def app_in_foreground(self, package: str) -> bool:
        """Report whether the current window belongs to the requested game."""
        return False

    def close(self) -> None:
        pass


class Controller:
    """Humanized operations on top of a Device, used by the engine.

    ``observe=True`` turns every input into a no-op (observation mode: recognise only).
    """

    def __init__(self, device: Device, humanize: HumanizeConfig | None = None, observe: bool = False,
                 sleep=time.sleep):
        self.device = device
        self.hcfg = humanize or HumanizeConfig()
        self.observe = observe
        self.sleep = sleep
        self.ops: list[dict] = []  # every operation, for replay / audit
        self.raw_size: tuple[int, int] = (DEV_W, DEV_H)   # size of the last screenshot from the device
        self._warned: set[str] = set()

    def screenshot(self) -> np.ndarray:
        """The screen as landscape 1280x720, the size every workflow is written for.

        MuMu reports its display in portrait (``wm size`` 720x1280); with the game running the
        screenshot comes back landscape 1280x720 and is used as is. Another landscape size (such
        as 1920x1080) is scaled to 1280x720 and taps are scaled back. A portrait screenshot means
        the game is not on screen (home screen, or the emulator is set to portrait): it is fitted
        into 1280x720 without stretching, so nothing in it matches and the run reports it.
        """
        img = self.device.screenshot()
        h, w = img.shape[:2]
        self.raw_size = (w, h)
        if (w, h) == (DEV_W, DEV_H):
            return img
        import cv2
        if h > w:
            if "portrait" not in self._warned:
                self._warned.add("portrait")
                logger.warning("截图是竖屏 %dx%d：游戏没在前台，或者 MuMu 设成了竖屏。请把 MuMu 分辨率设成平板 1280x720", w, h)
            scale = DEV_H / h
            small = cv2.resize(img, (max(1, round(w * scale)), DEV_H), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((DEV_H, DEV_W, 3), dtype=img.dtype)
            x0 = (DEV_W - small.shape[1]) // 2
            canvas[:, x0:x0 + small.shape[1]] = small[:, :, :3] if small.ndim == 3 else small[:, :, None]
            return canvas
        if abs(w / h - DEV_W / DEV_H) > 0.02 and "ratio" not in self._warned:
            self._warned.add("ratio")
            logger.warning("截图是 %dx%d，不是 16:9，识别和点击可能不准。推荐 MuMu 分辨率 1280x720", w, h)
        return cv2.resize(img, (DEV_W, DEV_H), interpolation=cv2.INTER_AREA)

    def to_device(self, x: int, y: int) -> tuple[int, int]:
        """1280x720 workflow coordinates -> the device's landscape coordinates."""
        w, h = self.raw_size
        if (w, h) == (DEV_W, DEV_H) or h > w:
            return int(x), int(y)
        return round(x * w / DEV_W), round(y * h / DEV_H)

    def click(self, rect, delay_ms: int = 500, press_hint: int | None = None) -> tuple[int, int]:
        x, y = pick_point(rect, self.hcfg)
        pm = press_ms(self.hcfg, press_hint)
        self.ops.append({"op": "click", "rect": list(rect[:4]), "point": [x, y], "press_ms": pm,
                         "observe": self.observe})
        if not self.observe:
            self.device.tap(*self.to_device(x, y), pm)
        self.sleep(after_delay_ms(self.hcfg, delay_ms) / 1000)
        return x, y

    def swipe(self, start_rect, end_rect, delay_ms: int = 500, duration_ms: tuple[int, int] | None = None):
        cfg = self.hcfg
        if duration_ms:
            cfg = HumanizeConfig(**{**cfg.__dict__, "swipe_duration_ms": tuple(duration_ms)})
        p1, p2, dur = swipe_points(start_rect, end_rect, cfg)
        self.ops.append({"op": "swipe", "from": list(p1), "to": list(p2), "duration_ms": dur,
                         "observe": self.observe})
        if not self.observe:
            self.device.swipe(self.to_device(*p1), self.to_device(*p2), dur)
        self.sleep(after_delay_ms(self.hcfg, delay_ms) / 1000)
        return p1, p2

    def back(self, delay_ms: int = 800):
        self.ops.append({"op": "back", "observe": self.observe})
        if not self.observe:
            self.device.back()
        self.sleep(after_delay_ms(self.hcfg, delay_ms) / 1000)

    def start_app(self, package: str):
        self.ops.append({"op": "start_app", "package": package, "observe": self.observe})
        if not self.observe:
            self.device.start_app(package)

    def restart_app(self, package: str):
        self.ops.append({"op": "restart_app", "package": package, "observe": self.observe})
        if not self.observe:
            self.device.restart_app(package)
