"""ADB backend.

The commands follow OnmyojiAutoScript ``module/device/method/adb.py``
(``screencap -p`` for screenshots, ``input tap`` for clicks,
``input swipe x1 y1 x2 y2 ms`` for swipes and for long presses), GPLv3.
OAS talks to adb through the ``adbutils`` package; this port calls the adb
executable directly so the only requirement is an adb binary (MuMu 12 ships one).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time

import cv2
import numpy as np

from ..errors import DeviceError
from ..log import logger
from .base import Device

ONMYOJI_PACKAGE = "com.netease.onmyoji"
ONMYOJI_PACKAGE_PATTERN = r"com\.netease\.onmyoji(?:\.[A-Za-z_]\w*)*"
ANDROID_PACKAGE_PATTERN = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+"


def find_adb(explicit: str | None = None, mumu_root: str | None = None) -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    if mumu_root:
        from .mumu import TOOL_DIRS
        for sub in TOOL_DIRS:                      # nx_main first: the new "MuMu\nx_main" install
            candidates.append(os.path.join(mumu_root, sub, "adb.exe"))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    found = shutil.which("adb")
    if found:
        return found
    raise DeviceError("找不到 adb：请在配置里填 adb_path，或确认 MuMu 12 安装目录下有 nx_main\\adb.exe 或 shell\\adb.exe")


def resolve_package(pm_list_output: str, package: str) -> str:
    """Pick the installed package for ``package``.

    Channel builds add a suffix (the user's MuMu has ``com.netease.onmyoji.wyzymnqsd_cps``), so
    ``com.netease.onmyoji`` itself is often not installed. Exact match wins, then the first
    installed ``package.<suffix>``; otherwise the name is returned unchanged.
    """
    names = [l.strip()[len("package:"):] for l in (pm_list_output or "").splitlines()
             if l.strip().startswith("package:")]
    if package in names:
        return package
    for n in sorted(names):
        if n.startswith(package + "."):
            return n
    return package


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

    def display(self) -> dict:
        """wm size / density, for doctor and diagnostics."""
        size = parse_wm_size(self.shell("wm", "size"))
        return {"wm_size": size, "landscape": landscape(size), "density": parse_wm_density(self.shell("wm", "density"))}

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
        package = resolve_package(self.shell("pm", "list", "packages", package), package)
        self._run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])

    def restart_app(self, package: str) -> None:
        if not re.fullmatch(ONMYOJI_PACKAGE_PATTERN, package, flags=re.ASCII):
            raise DeviceError("重启只允许阴阳师 Android 包名")
        focus = self.current_app()
        foreground = self._foreground_game(focus, package)
        if foreground is None:
            raise DeviceError("阴阳师安装包与当前前台窗口不符，未执行重启")
        package = foreground
        installed = {line.strip() for line in self.shell("pm", "list", "packages", package).splitlines()}
        if "package:" + package not in installed:
            raise DeviceError("当前阴阳师包未出现在安装列表，未执行重启")
        if self.current_app() != focus:
            raise DeviceError("核对安装包期间前台窗口已变化，未执行重启")
        self._run(["shell", "am", "force-stop", package])
        output = self._run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER",
                            "--pct-syskeys", "0", "1"])
        if "Events injected: 1" not in output:
            raise DeviceError("游戏已停止，ADB 未确认重新启动")

    def close_related_apps(self, packages: list[str], mode: str) -> None:
        if (mode not in ("shell", "android api") or not packages or
                any(not isinstance(package, str) or not re.fullmatch(ANDROID_PACKAGE_PATTERN, package, flags=re.ASCII)
                    for package in packages)):
            raise DeviceError("关闭关联应用需要有效的模式和 Android 包名")
        focus = self.current_app()
        if self._foreground_game(focus, ONMYOJI_PACKAGE) is None:
            raise DeviceError("当前前台不是阴阳师，未关闭关联应用")
        user = self.shell("am", "get-current-user").strip()
        if not re.fullmatch(r"[0-9]+", user, flags=re.ASCII):
            raise DeviceError("无法核对当前 Android 用户，未关闭关联应用")
        installed = self.shell("pm", "list", "packages", "--user", user).splitlines()
        missing = [package for package in packages if "package:" + package not in installed]
        if missing or self.current_app() != focus:
            raise DeviceError("关联应用未安装或前台已变化，未关闭关联应用")
        command = "force-stop"
        if mode == "android api":
            self._run(["shell", "input", "keyevent", "KEYCODE_HOME"])
            time.sleep(2)
            home_focus = self.current_app()
            if not home_focus or self._foreground_game(home_focus, ONMYOJI_PACKAGE) is not None:
                raise DeviceError("未能核对离开游戏前台，未发出后台进程关闭命令")
            command = "kill"
        for package in packages:
            self.shell("am", command, "--user", user, package)
            time.sleep(.1)
        time.sleep(.5)

    def app_in_foreground(self, package: str) -> bool:
        return self._foreground_game(self.current_app(), package) is not None

    @staticmethod
    def _foreground_game(focus: str, package: str) -> str | None:
        match = re.search(r"(?<![\w.])(" + ONMYOJI_PACKAGE_PATTERN + r")/", focus, flags=re.ASCII)
        if match and (package == ONMYOJI_PACKAGE or package == match[1]):
            return match[1]
        return None

    def current_app(self) -> str:
        # MuMu's Android window subcommand omits display focus records.
        lines = self.shell("dumpsys", "window").splitlines()
        for key in ("mCurrentFocus", "mFocusedApp"):
            for line in lines:
                if key in line:
                    return line.strip()
        return ""


def parse_adb_devices(text: str, keep_emulator: bool = False) -> list[str]:
    """Serials in the ``device`` state from ``adb devices`` output.

    MuMu shows each instance twice: ``127.0.0.1:16384`` and ``emulator-5554``. Only the IP:port
    serial is kept (``keep_emulator=False``) so ``adb -s`` never has two names for one instance.
    """
    serials = []
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device" or line.startswith("List of devices"):
            continue
        if parts[0].startswith("emulator-") and not keep_emulator:
            continue
        if parts[0] not in serials:
            serials.append(parts[0])
    return serials


def list_adb_devices(adb_path: str, keep_emulator: bool = False) -> list[str]:
    out = subprocess.run([adb_path, "devices"], capture_output=True, timeout=15).stdout.decode(errors="ignore")
    return parse_adb_devices(out, keep_emulator)


def parse_wm_size(text: str) -> tuple[int, int] | None:
    """``wm size`` -> (w, h) as the device reports it; Override size wins over Physical size.

    MuMu reports portrait (``Physical size: 720x1280``); with the game in landscape the screen is
    1280x720, which is what screenshots and taps use.
    """
    found = {}
    for kind, w, h in re.findall(r"(Physical|Override) size:\s*(\d+)x(\d+)", text or ""):
        found[kind] = (int(w), int(h))
    return found.get("Override") or found.get("Physical")


def parse_wm_density(text: str) -> int | None:
    found = dict(re.findall(r"(Physical|Override) density:\s*(\d+)", text or ""))
    v = found.get("Override") or found.get("Physical")
    return int(v) if v else None


def landscape(size: tuple[int, int] | None) -> tuple[int, int] | None:
    return None if not size else (max(size), min(size))
