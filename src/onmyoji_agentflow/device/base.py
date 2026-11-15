"""Device abstraction used by the engine.

Coordinates are always in the 1280x720 development resolution (both OAS and
assttyys use it). Backends scale if the emulator runs at another size, but
the README asks users to set MuMu 12 to 1280x720.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np

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

    def screenshot(self) -> np.ndarray:
        img = self.device.screenshot()
        if img.shape[1] != DEV_W or img.shape[0] != DEV_H:
            import cv2
            img = cv2.resize(img, (DEV_W, DEV_H), interpolation=cv2.INTER_AREA)
        return img

    def click(self, rect, delay_ms: int = 500, press_hint: int | None = None) -> tuple[int, int]:
        x, y = pick_point(rect, self.hcfg)
        pm = press_ms(self.hcfg, press_hint)
        self.ops.append({"op": "click", "rect": list(rect[:4]), "point": [x, y], "press_ms": pm,
                         "observe": self.observe})
        if not self.observe:
            self.device.tap(x, y, pm)
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
            self.device.swipe(p1, p2, dur)
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
