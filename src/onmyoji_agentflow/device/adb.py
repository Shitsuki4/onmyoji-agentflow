"""ADB backend.

The commands follow OnmyojiAutoScript ``module/device/method/adb.py``
(``screencap -p`` for screenshots, ``input tap`` for clicks,
``input swipe x1 y1 x2 y2 ms`` for swipes and for long presses), GPLv3.
OAS talks to adb through the ``adbutils`` package; this port calls the adb
executable directly so the only requirement is an adb binary (MuMu 12 ships one).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time

import cv2
import numpy as np

from ..errors import DeviceError
from ..log import logger
from .base import Device

ONMYOJI_PACKAGE = "com.netease.onmyoji"


def find_adb(explicit: str | None = None, mumu_root: str | None = None) -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    if mumu_root:
        for sub in ("shell/adb.exe", "nx_main/adb.exe", "nx_device/12.0/shell/adb.exe"):
            candidates.append(os.path.join(mumu_root, sub))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    found = shutil.which("adb")
    if found:
        return found
    raise DeviceError("找不到 adb：请在配置里填 adb_path，或确认 MuMu 12 安装目录下有 shell/adb.exe")


class AdbDevice(Device):
    name = "adb"

    def __init__(self, serial: str, adb_path: str, connect: bool = True, timeout: float = 15.0):
        self.serial = serial
        self.adb = adb_path
        self.timeout = timeout
        if connect and ":" in serial:
            self.connect()

    # -- helpers
    def _run(self, args: list, binary: bool = False, timeout: float | None = None):
        cmd = [self.adb, "-s", self.serial, *[str(a) for a in args]]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=timeout or self.timeout)
        except subprocess.TimeoutExpired as e:
            raise DeviceError(f"adb 超时: {' '.join(map(str, args))}") from e
        if res.returncode != 0:
            raise DeviceError(f"adb 失败({res.returncode}): {res.stderr.decode(errors='ignore').strip()}")
        return res.stdout if binary else res.stdout.decode("utf-8", errors="ignore")

    def connect(self):
        out = subprocess.run([self.adb, "connect", self.serial], capture_output=True, timeout=self.timeout)
        text = out.stdout.decode(errors="ignore")
        logger.info("adb connect %s: %s", self.serial, text.strip())
        if "connected" not in text:
            raise DeviceError(f"adb connect {self.serial} 失败: {text.strip()}")

    def shell(self, *args) -> str:
        return self._run(["shell", *args])

    # -- Device API
    def screenshot(self) -> np.ndarray:
        data = self._run(["exec-out", "screencap", "-p"], binary=True)
        if len(data) < 500:
            raise DeviceError(f"Unexpected screenshot: {data[:100]!r}")
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            # Some systems return CRLF-converted data (OAS handles the same case)
            img = cv2.imdecode(np.frombuffer(data.replace(b"\r\n", b"\n"), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise DeviceError("cannot load screenshot")
        return img

    def tap(self, x: int, y: int, press_ms: int = 40) -> None:
        start = time.time()
        if press_ms and press_ms > 80:
            self._run(["shell", "input", "swipe", x, y, x, y, int(press_ms)])
        else:
            self._run(["shell", "input", "tap", x, y])
        if time.time() - start <= 0.05:
            time.sleep(0.05)

    def swipe(self, p1, p2, duration_ms: int = 400) -> None:
        self._run(["shell", "input", "swipe", *p1, *p2, int(duration_ms)])

    def back(self) -> None:
        self._run(["shell", "input", "keyevent", "4"])

    def start_app(self, package: str = ONMYOJI_PACKAGE) -> None:
        self._run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])

    def current_app(self) -> str:
        out = self.shell("dumpsys", "window", "windows")
        for line in out.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                return line.strip()
        return ""


def list_adb_devices(adb_path: str) -> list[str]:
    out = subprocess.run([adb_path, "devices"], capture_output=True, timeout=15).stdout.decode(errors="ignore")
    serials = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials
