"""Device layer against the user's real Win10 + MuMu (nx_main) machine: samples in tests/data/mumu_win10."""
import os
from pathlib import Path

import numpy as np
import pytest

from onmyoji_agentflow.device import mumu
from onmyoji_agentflow.device.adb import (ONMYOJI_PACKAGE, find_adb, landscape, parse_adb_devices,
                                          parse_wm_density, parse_wm_size, resolve_package)
from onmyoji_agentflow.device.base import Controller, Device

DATA = Path(__file__).parent / "data" / "mumu_win10"


def _read(name):
    return (DATA / name).read_text(encoding="utf-8")


# --- MuMuManager.exe info -v all ---------------------------------------------------------------

def test_manager_info_all_sample():
    infos = mumu.parse_manager_info(_read("manager_info_all.json"))
    assert len(infos) == 1
    i = infos[0]
    assert i.index == 0
    assert i.serial == "127.0.0.1:16384"
    assert i.started is True
    assert i.state == "start_finished"


def test_manager_info_single_instance_sample():
    infos = mumu.parse_manager_info(_read("manager_info_0.json"))
    assert [(i.index, i.serial, i.started) for i in infos] == [(0, "127.0.0.1:16384", True)]


def test_channel_package_resolved():
    pm = _read("pm_list_packages.txt")
    assert resolve_package(pm, ONMYOJI_PACKAGE) == "com.netease.onmyoji.wyzymnqsd_cps"
    assert resolve_package("package:com.netease.onmyoji\npackage:com.netease.onmyoji.x\n", ONMYOJI_PACKAGE) \
        == "com.netease.onmyoji"
    assert resolve_package("", ONMYOJI_PACKAGE) == ONMYOJI_PACKAGE


def test_manager_info_bare_object_and_noise():
    text = 'some banner\r\n{"index": "2", "adb_host_ip": "127.0.0.1", "adb_port": "16448", ' \
           '"is_android_started": "false", "player_state": "starting", "name": "x"}\r\n'
    infos = mumu.parse_manager_info(text)
    assert [(i.index, i.serial, i.started) for i in infos] == [(2, "127.0.0.1:16448", False)]


def test_manager_info_stopped_instance_has_no_serial():
    text = '{"0": {"index": "0", "is_process_started": false, "name": "a"}, ' \
           '"1": {"index": "1", "adb_host_ip": "127.0.0.1", "adb_port": 16416, "player_state": "start_finished"}}'
    infos = mumu.parse_manager_info(text)
    assert [(i.index, i.serial) for i in infos] == [(0, None), (1, "127.0.0.1:16416")]


def test_manager_info_empty_or_garbage():
    assert mumu.parse_manager_info("") == []
    assert mumu.parse_manager_info("error: not running") == []


# --- adb devices / wm ---------------------------------------------------------------------------

def test_adb_devices_drops_emulator_alias():
    text = _read("adb_devices.txt")
    assert parse_adb_devices(text) == ["127.0.0.1:16384"]
    assert parse_adb_devices(text, keep_emulator=True) == ["127.0.0.1:16384", "emulator-5554"]
    assert parse_adb_devices("List of devices attached\n127.0.0.1:16384\toffline\n") == []


def test_wm_size_and_density_sample():
    size = parse_wm_size(_read("wm_size.txt"))
    assert size == (720, 1280)
    assert landscape(size) == (1280, 720)
    assert parse_wm_density(_read("wm_density.txt")) == 240


def test_wm_override_wins():
    assert parse_wm_size("Physical size: 720x1280\nOverride size: 1080x1920\n") == (1080, 1920)
    assert parse_wm_density("Physical density: 240\nOverride density: 320\n") == 320
    assert parse_wm_size("") is None and landscape(None) is None


# --- install layouts ----------------------------------------------------------------------------

def _touch(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")


def test_nx_main_layout(tmp_path, monkeypatch):
    root = tmp_path / "Netease" / "MuMu"
    _touch(root / "nx_main" / "MuMuManager.exe")
    _touch(root / "nx_main" / "adb.exe")
    _touch(root / "nx_device" / "12.0" / "shell" / "sdk" / "external_renderer_ipc.dll")
    r = str(root)
    assert mumu.is_mumu_root(r)
    assert mumu.root_from_path(str(root / "nx_main" / "MuMuManager.exe")) == r
    assert mumu.root_from_path(str(root / "nx_device" / "12.0" / "shell")) == r
    assert mumu.find_manager(r) == str(root / "nx_main" / "MuMuManager.exe")
    assert mumu.find_ipc_dll(r) == str(root / "nx_device" / "12.0" / "shell" / "sdk" / "external_renderer_ipc.dll")
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert find_adb(None, r) == str(root / "nx_main" / "adb.exe")
    # keep a real MuMu install on the test machine (registry / Program Files) out of the result
    monkeypatch.setattr(mumu, "GUESS_ROOTS", [])
    monkeypatch.setattr(mumu, "iter_registry_roots", lambda: [])
    assert mumu.find_mumu_roots(r) == [r]


def test_find_mumu_roots_merges_and_dedups(tmp_path, monkeypatch):
    new = tmp_path / "Netease" / "MuMu"
    old = tmp_path / "Netease" / "MuMuPlayer-12.0"
    _touch(new / "nx_main" / "MuMuManager.exe")
    (old / "shell").mkdir(parents=True)
    junk = tmp_path / "NotMuMu"
    junk.mkdir()
    monkeypatch.setattr(mumu, "iter_registry_roots", lambda: [str(old), str(junk)])
    monkeypatch.setattr(mumu, "GUESS_ROOTS", [str(new), str(old), str(tmp_path / "missing")])
    assert mumu.find_mumu_roots() == [str(old), str(new)]
    assert mumu.find_mumu_roots(str(new / "nx_main" / "MuMuManager.exe")) == [str(new), str(old)]


def test_nx_main_dll_preferred(tmp_path):
    root = tmp_path / "MuMu"
    _touch(root / "nx_main" / "sdk" / "external_renderer_ipc.dll")
    _touch(root / "nx_device" / "12.0" / "shell" / "sdk" / "external_renderer_ipc.dll")
    assert mumu.find_ipc_dll(str(root)) == str(root / "nx_main" / "sdk" / "external_renderer_ipc.dll")
    assert mumu.find_ipc_dll(str(tmp_path / "none")) is None and mumu.find_ipc_dll(None) is None


def test_list_instances_prefers_manager(tmp_path, monkeypatch):
    root = tmp_path / "MuMu"
    (root / "nx_main").mkdir(parents=True)
    infos = mumu.parse_manager_info(_read("manager_info_all.json"))
    monkeypatch.setattr(mumu, "manager_instances", lambda r, timeout=15.0: infos)
    inst = mumu.list_instances(str(root))
    assert [(i.instance_id, i.serial) for i in inst] == [(0, "127.0.0.1:16384")]


def test_list_instances_nx_device_vms_fallback(tmp_path, monkeypatch):
    root = tmp_path / "MuMu"
    vms = root / "nx_device" / "12.0" / "vms"
    (vms / "MuMuPlayer-12.0-0").mkdir(parents=True)
    monkeypatch.setattr(mumu, "manager_instances", lambda r, timeout=15.0: [])
    assert [(i.instance_id, i.serial) for i in mumu.list_instances(str(root))] == [(0, "127.0.0.1:16384")]


# --- open_device serial handling ----------------------------------------------------------------

def test_open_device_replaces_emulator_serial(tmp_path, monkeypatch):
    import onmyoji_agentflow.device as dev
    from onmyoji_agentflow.device.adb import AdbDevice
    _touch(tmp_path / "adb")
    monkeypatch.setattr(dev, "find_mumu_roots", lambda r=None: [])
    monkeypatch.setattr(AdbDevice, "connect", lambda self: None)
    d = dev.open_device({"serial": "emulator-5554", "mumu_id": 0, "method": "adb"}, adb_path=str(tmp_path / "adb"))
    assert d.serial == "127.0.0.1:16384"
    d2 = dev.open_device({"serial": "127.0.0.1:16384", "method": "adb"}, adb_path=str(tmp_path / "adb"))
    assert d2.serial == "127.0.0.1:16384"


# --- landscape handling in the Controller -------------------------------------------------------

class FakeDevice(Device):
    def __init__(self, w, h):
        self.img = np.full((h, w, 3), 50, np.uint8)
        self.taps, self.swipes = [], []

    def screenshot(self):
        return self.img

    def tap(self, x, y, press_ms=40):
        self.taps.append((x, y))

    def swipe(self, p1, p2, duration_ms=400):
        self.swipes.append((p1, p2))


def _ctrl(dev):
    return Controller(dev, sleep=lambda s: None)


def test_landscape_1280x720_untouched():
    d = FakeDevice(1280, 720)
    c = _ctrl(d)
    img = c.screenshot()
    assert img.shape == (720, 1280, 3) and img is d.img
    x, y = c.click((100, 100, 110, 110))
    assert d.taps == [(x, y)]


def test_landscape_1920x1080_scaled_back():
    d = FakeDevice(1920, 1080)
    c = _ctrl(d)
    assert c.screenshot().shape == (720, 1280, 3)
    x, y = c.click((640, 360, 641, 361))
    tx, ty = d.taps[0]
    assert abs(tx - x * 1.5) <= 1 and abs(ty - y * 1.5) <= 1
    c.swipe((100, 100, 101, 101), (200, 200, 201, 201))
    (sx, sy), (ex, ey) = d.swipes[0]
    assert 145 <= sx <= 155 and 295 <= ex <= 305


def test_portrait_screenshot_letterboxed_and_warned(caplog):
    d = FakeDevice(720, 1280)
    c = _ctrl(d)
    img = c.screenshot()
    assert img.shape == (720, 1280, 3)
    assert img[:, :200].max() == 0 and img[:, 640].max() == 50   # black bars left/right, picture in the middle
    c.screenshot()
    assert sum("竖屏" in r.getMessage() for r in caplog.records) <= 1
    c.click((10, 10, 11, 11))
    assert d.taps and d.taps[0][0] <= 12


def test_observe_mode_never_taps():
    d = FakeDevice(1920, 1080)
    c = Controller(d, observe=True, sleep=lambda s: None)
    c.screenshot()
    c.click((1, 1, 5, 5))
    c.swipe((1, 1, 2, 2), (5, 5, 6, 6))
    assert d.taps == [] and d.swipes == [] and len(c.ops) == 2
