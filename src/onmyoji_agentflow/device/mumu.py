"""MuMu 12 detection and multi-instance discovery.

Ported from OnmyojiAutoScript ``module/device/platform2/emulator_windows.py``,
``emulator_base.py`` (``MuMuPlayer12_id``) and ``method/nemu_ipc.py``
(``serial_to_id``), which derive from AzurLaneAutoScript. GPLv3.
Changes: reduced to MuMu 12 / MuMu 12 5.x only; returns plain dataclasses; also reads
``MuMuManager.exe info -v all`` (JSON) and knows the newer "MuMu\\nx_main" install layout.

Install layouts handled (root is the folder that holds them):

* ``<root>\\shell``                 MuMuPlayer-12.0 (MuMuManager.exe, adb.exe, sdk\\external_renderer_ipc.dll)
* ``<root>\\nx_main``               MuMu 12 5.x and the new "MuMu" install, e.g.
                                   ``C:\\Program Files\\Netease\\MuMu\\nx_main`` (MuMuManager.exe, adb.exe)
* ``<root>\\nx_device\\12.0\\shell``  device files of the 5.x layout (sdk\\external_renderer_ipc.dll, adb.exe)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

from ._oas.nemu_ipc import serial_to_id  # noqa: F401  (re-exported)

MUMU_UNINSTALL_NAMES = ["MuMuPlayer-12.0", "MuMu Player 12.0", "MuMuPlayer", "Nemu9", "MuMuPlayerGlobal-12.0",
                        "MuMu", "MuMuPlayer-12", "MuMu Player 12"]
# Where the tools live under the root, newest layout first.
TOOL_DIRS = ("nx_main", "shell", os.path.join("nx_device", "12.0", "shell"))
DLL_PATHS = (os.path.join("nx_main", "sdk", "external_renderer_ipc.dll"),
             os.path.join("nx_main", "external_renderer_ipc.dll"),
             os.path.join("nx_device", "12.0", "shell", "sdk", "external_renderer_ipc.dll"),
             os.path.join("shell", "sdk", "external_renderer_ipc.dll"))
VMS_DIRS = ("vms", os.path.join("nx_device", "12.0", "vms"))
GUESS_ROOTS = [rf"{d}:\Program Files\Netease\{name}" for d in "CDE"
               for name in ("MuMu", "MuMuPlayer-12.0", "MuMu Player 12", "MuMuPlayer")]
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
        if base in ("shell", "nx_main", "emulatorshell", "sdk"):
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
    roots.extend(GUESS_ROOTS)
    out = []
    for i, r in enumerate(roots):
        explicit_one = bool(explicit) and i == 0
        if r and os.path.isdir(r) and r not in out and (explicit_one or is_mumu_root(r)):
            out.append(r)
    return out


def is_mumu_root(root: str) -> bool:
    return any(os.path.isdir(os.path.join(root, d)) for d in TOOL_DIRS)


def find_tool(root: str | None, exe: str) -> str | None:
    """Path of MuMuManager.exe / adb.exe under a MuMu root, checking every known layout."""
    if not root:
        return None
    for d in TOOL_DIRS:
        p = os.path.join(root, d, exe)
        if os.path.isfile(p):
            return p
    return None


def find_manager(root: str | None) -> str | None:
    return find_tool(root, "MuMuManager.exe")


def find_ipc_dll(root: str | None) -> str | None:
    """external_renderer_ipc.dll (the nemu_ipc screenshot channel), or None: use adb then."""
    if not root:
        return None
    for rel in DLL_PATHS:
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            return p
    return None


@dataclass
class ManagerInfo:
    """One instance as reported by ``MuMuManager.exe info -v all``."""
    index: int
    name: str
    serial: str | None              # "127.0.0.1:16384" when adb is up, else None
    state: str                      # player_state, e.g. "start_finished"
    started: bool                   # Android has finished booting
    raw: dict = field(default_factory=dict, repr=False)


def _bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def parse_manager_info(text: str) -> list[ManagerInfo]:
    """Parse ``MuMuManager.exe info -v all``.

    With several instances (and on current MuMu, also with one) the top level is an object keyed
    by instance number: ``{"0": {"adb_host_ip": "127.0.0.1", "adb_port": 16384, ...}}``.
    A single instance can also come back as the bare object (``info -v 0``); both are accepted.
    """
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        return []
    data = json.loads(text[start:text.rfind("}") + 1])
    if not isinstance(data, dict):
        return []
    if "index" in data or "adb_port" in data or "player_state" in data:
        items = [(data.get("index", "0"), data)]
    else:
        items = [(k, v) for k, v in data.items() if isinstance(v, dict)]
    out = []
    for key, d in items:
        try:
            index = int(d.get("index", key))
        except (TypeError, ValueError):
            continue
        host, port = d.get("adb_host_ip"), d.get("adb_port")
        serial = f"{host or '127.0.0.1'}:{int(port)}" if port not in (None, "", 0, "0") else None
        state = str(d.get("player_state") or "")
        started = _bool(d.get("is_android_started")) or state == "start_finished"
        out.append(ManagerInfo(index, str(d.get("name") or f"MuMuPlayer-12.0-{index}"), serial, state, started, d))
    out.sort(key=lambda i: i.index)
    return out


def manager_instances(root: str | None, timeout: float = 15.0) -> list[ManagerInfo]:
    """Ask MuMuManager for the instances; empty list when it is missing or fails."""
    exe = find_manager(root)
    if not exe:
        return []
    try:
        res = subprocess.run([exe, "info", "-v", "all"], capture_output=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    for enc in ("utf-8", "gbk"):
        try:
            return parse_manager_info(res.stdout.decode(enc))
        except (UnicodeDecodeError, ValueError):
            continue
    return []


def list_instances(root: str) -> list[MuMuInstance]:
    """MuMuManager first (it reports the live adb port); then OAS's way: vms/MuMuPlayer-12.0-N/*.nemu
    holds the adb port forward; fall back to 16384+32*N."""
    out: list[MuMuInstance] = []
    for m in manager_instances(root):
        out.append(MuMuInstance(m.index, m.name, m.serial or default_serial(m.index), root))
    if out:
        return out
    vms = next((os.path.join(root, d) for d in VMS_DIRS if os.path.isdir(os.path.join(root, d))), None)
    if not vms:
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
