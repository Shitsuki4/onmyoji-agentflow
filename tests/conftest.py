import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import pytest


@pytest.fixture(autouse=True)
def isolate_optional_ocr_and_device_locks(request, monkeypatch, tmp_path):
    import onmyoji_agentflow.runtime as runtime
    monkeypatch.setattr(runtime, "_lock_root", lambda: tmp_path)
    if request.node.get_closest_marker("real_ocr") is None:
        from helpers import FRAME_TEXTS, fake_text_reader
        FRAME_TEXTS.clear()
        monkeypatch.setattr("onmyoji_agentflow.vision.ocr.read_boxes", fake_text_reader)
