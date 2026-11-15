"""nemu_ipc glue, checked without MuMu: colour order, which dll is loaded, dll stdout kept off stdout."""
import os

import numpy as np

from onmyoji_agentflow.device._oas import nemu_ipc as N


class FakeImpl:
    def __init__(self, rgba):
        self.rgba = rgba

    def screenshot(self):
        return self.rgba.copy()


def test_screenshot_rgba_to_bgr_and_flipped():
    # 2x1 image, upside down as the dll returns it: bottom row first
    rgba = np.array([[[10, 20, 30, 255]],     # bottom pixel: R=10 G=20 B=30
                     [[200, 100, 50, 255]]],  # top pixel:    R=200 G=100 B=50
                    dtype=np.uint8)
    ipc = N.NemuIpc("C:/MuMu", 0)
    ipc._impl = FakeImpl(rgba)
    img = ipc.screenshot_nemu_ipc()
    assert img.shape == (2, 1, 3)
    assert img[0, 0].tolist() == [50, 100, 200]   # top pixel, BGR
    assert img[1, 0].tolist() == [30, 20, 10]


def test_explicit_dll_loaded_first(tmp_path, monkeypatch):
    root = tmp_path / "MuMu"
    for rel in ("nx_main/sdk", "nx_device/12.0/shell/sdk"):
        (root / rel).mkdir(parents=True)
        (root / rel / "external_renderer_ipc.dll").write_bytes(b"")
    loaded = []
    monkeypatch.setattr(N.ctypes, "CDLL", lambda p: loaded.append(p) or object())
    want = str(root / "nx_main" / "sdk" / "external_renderer_ipc.dll")
    N.NemuIpcImpl(str(root), 0, ipc_dll=want)
    assert loaded == [os.path.abspath(want)]
    loaded.clear()
    N.NemuIpcImpl(str(root), 0)  # without a hint OAS's own order applies
    assert loaded == [os.path.abspath(str(root / "nx_device" / "12.0" / "shell" / "sdk" / "external_renderer_ipc.dll"))]


def test_device_passes_found_dll(tmp_path, monkeypatch):
    from onmyoji_agentflow.device import nemu
    root = tmp_path / "MuMu"
    (root / "nx_main" / "sdk").mkdir(parents=True)
    (root / "nx_main" / "sdk" / "external_renderer_ipc.dll").write_bytes(b"")
    d = nemu.NemuDevice(str(root), 0)
    assert d.ipc.ipc_dll == str(root / "nx_main" / "sdk" / "external_renderer_ipc.dll")


def test_stdout_to_stderr(capfd):
    os.write(1, b"before\n")
    with N.stdout_to_stderr():
        os.write(1, b"nemu_connect instance_name: x\n")
    os.write(1, b"after\n")
    out, err = capfd.readouterr()
    assert out == "before\nafter\n"
    assert "nemu_connect" in err
