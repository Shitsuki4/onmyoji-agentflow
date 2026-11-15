"""MuMu 12 detection and multi-instance discovery.

Ported from OnmyojiAutoScript ``module/device/platform2/emulator_windows.py``,
``emulator_base.py`` (``MuMuPlayer12_id``) and ``method/nemu_ipc.py``
(``serial_to_id``), which derive from AzurLaneAutoScript. GPLv3.
Changes: reduced to MuMu 12 / MuMu 12 5.x only; returns plain dataclasses.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass

from ._oas.nemu_ipc import serial_to_id  # noqa: F401  (re-exported)

MUMU_UNINSTALL_NAMES = ["MuMuPlayer-12.0", "MuMu Player 12.0", "MuMuPlayer", "Nemu9", "MuMuPlayerGlobal-12.0"]
UNINSTALL_PATHS = [
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
]


@dataclass
class MuMuInstance:
    instance_id: int
    name: str          # folder name, e.g. MuMuPlayer-12.0-1
    serial: str        # e.g. 127.0.0.1:16416
    root: str          # MuMu installation root, e.g. C:/Program Files/Netease/MuMuPlayer-12.0


def mumu12_id(name: str) -> int | None:
    """OAS ``MuMuPlayer12_id``: MuMuPlayer-12.0-3 -> 3."""
    res = re.search(r"MuMuPlayer(?:Global)?-(?:12|15)\.0-(\d+)", name)
    if res:
        return int(res.group(1))
    res = re.search(r"YXArkNights-12.0-(\d+)", name)
    if res:
        return int(res.group(1))
    return None


def default_serial(instance_id: int) -> str:
    """MuMu 12: 16384 for instance 0, +32 for each additional instance."""
    return f"127.0.0.1:{16384 + 32 * instance_id}"


def vbox_file_to_serial(path: str) -> str:
    regex = re.compile('<*?hostport="(.*?)".*?guestport="5555"/>')
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                res = regex.search(line)
                if res:
                    return f"127.0.0.1:{res.group(1)}"
    except FileNotFoundError:
        pass
    return ""


def root_from_path(path: str) -> str:
    """Accept the root, the shell/nx_main folder, or an exe inside them."""
    p = os.path.abspath(path)
    if os.path.isfile(p):
        p = os.path.dirname(p)
    while True:
        base = os.path.basename(p).lower()
        if base in ("shell", "nx_main", "emulatorshell"):
            p = os.path.dirname(p)
            continue
        if base in ("12.0", "15.0") and os.path.basename(os.path.dirname(p)).lower() == "nx_device":
            p = os.path.dirname(os.path.dirname(p))
            continue
        return p


def iter_registry_roots():
    if sys.platform != "win32":
        return
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in UNINSTALL_PATHS:
            for name in MUMU_UNINSTALL_NAMES:
                try:
                    with winreg.OpenKey(hive, f"{path}\\{name}") as reg:
                        uninstall = winreg.QueryValueEx(reg, "UninstallString")[0]
                except OSError:
                    continue
                if not uninstall:
                    continue
                res = re.search('"(.*?)"', uninstall)
                uninstall = res.group(1) if res else uninstall.split(" -")[0]
                yield root_from_path(os.path.dirname(uninstall))


def find_mumu_roots(explicit: str | None = None) -> list[str]:
    roots = []
    if explicit:
        roots.append(root_from_path(explicit))
    for r in iter_registry_roots() or []:
        roots.append(r)
    for guess in (r"C:\Program Files\Netease\MuMuPlayer-12.0", r"D:\Program Files\Netease\MuMuPlayer-12.0",
                  r"C:\Program Files\Netease\MuMu Player 12", r"D:\Program Files\Netease\MuMu Player 12"):
        roots.append(guess)
    out = []
    for r in roots:
        if r and os.path.isdir(r) and r not in out:
            out.append(r)
    return out


def list_instances(root: str) -> list[MuMuInstance]:
    """OAS: vms/MuMuPlayer-12.0-N/*.nemu holds the adb port forward; fall back to 16384+32*N."""
    vms = os.path.join(root, "vms")
    out: list[MuMuInstance] = []
    if not os.path.isdir(vms):
        return out
    for folder in sorted(os.listdir(vms)):
        full = os.path.join(vms, folder)
        if not os.path.isdir(full):
            continue
        iid = mumu12_id(folder)
        if iid is None:
            continue
        serial = ""
        for fn in os.listdir(full):
            if fn.endswith(".nemu"):
                serial = vbox_file_to_serial(os.path.join(full, fn))
                if serial:
                    break
        # Fix for MuMu12 v4.0.4, default instance of which has no forward record in vbox config
        out.append(MuMuInstance(iid, folder, serial or default_serial(iid), root))
    out.sort(key=lambda i: i.instance_id)
    return out


def discover(explicit_root: str | None = None) -> list[MuMuInstance]:
    result = []
    for root in find_mumu_roots(explicit_root):
        result.extend(list_instances(root))
    return result
