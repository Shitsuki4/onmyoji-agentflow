import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from helpers import frame_for
from onmyoji_agentflow.cli import main
from onmyoji_agentflow.convert import assttyys as conv_ass
from onmyoji_agentflow.convert import oas as conv_oas
from onmyoji_agentflow.device.mumu import default_serial, list_instances, mumu12_id, root_from_path

UPSTREAM = os.environ.get("OAF_UPSTREAM")  # optional: folder with OnmyojiAutoScript/ and assttyys_autojs/


def test_mumu_helpers(tmp_path):
    assert mumu12_id("MuMuPlayer-12.0-3") == 3 and mumu12_id("foo") is None
    assert default_serial(0) == "127.0.0.1:16384" and default_serial(2) == "127.0.0.1:16448"
    root = tmp_path / "MuMuPlayer-12.0"
    (root / "shell").mkdir(parents=True)
    (root / "vms" / "MuMuPlayer-12.0-0").mkdir(parents=True)
    (root / "vms" / "MuMuPlayer-12.0-1").mkdir(parents=True)
    (root / "vms" / "MuMuPlayer-12.0-1" / "x.nemu").write_text(
        '<Forwarding name="adb" proto="1" hostip="127.0.0.1" hostport="16416" guestport="5555"/>')
    assert root_from_path(str(root / "shell")) == str(root)
    inst = list_instances(str(root))
    assert [(i.instance_id, i.serial) for i in inst] == [(0, "127.0.0.1:16384"), (1, "127.0.0.1:16416")]


def _mini_oas(tmp_path: Path) -> Path:
    t = tmp_path / "oas" / "tasks" / "Demo" / "res"
    t.mkdir(parents=True)
    import cv2
    import numpy as np
    cv2.imwrite(str(t / "btn.png"), np.zeros((10, 10, 3), np.uint8))
    (t / "image.json").write_text(json.dumps([{"itemName": "btn", "imageName": "btn.png", "roiFront": "1,2,10,10",
                                               "roiBack": "0,0,100,100", "method": "Template matching",
                                               "threshold": 0.8, "description": "按钮"}]))
    (t / "click.json").write_text(json.dumps([{"itemName": "go", "roiFront": "10,20,30,40", "roiBack": "0,0,1,1",
                                               "description": ""}]))
    (t / "swipe.json").write_text(json.dumps([{"itemName": "s", "roiFront": "0,0,10,10", "roiBack": "100,0,10,10",
                                               "mode": "default", "description": ""}]))
    g = tmp_path / "oas" / "tasks" / "GameUi"
    g.mkdir(parents=True)
    (g / "assets.py").write_text("class GameUiAssets:\n    pass\n")
    (g / "default_pages.py").write_text(
        "page_main = Page(GameUiAssets.I_CHECK_MAIN)\npage_x = Page(GameUiAssets.I_X)\n"
        "page_main.connect(page_x, GameUiAssets.I_GO_X)\n")
    return tmp_path / "oas"


def test_convert_oas_minimal(tmp_path):
    root = _mini_oas(tmp_path)
    r = conv_oas.convert(root, tmp_path / "out")
    assert r["tasks"]["Demo"]["resources"] == 3 and r["tasks"]["Demo"]["images"] == 1
    import yaml
    doc = yaml.safe_load((tmp_path / "out" / "Demo.yaml").read_text(encoding="utf-8"))
    assert doc["resources"]["C_GO"]["rect"] == [10, 20, 40, 60]
    assert doc["resources"]["S_S"]["to"] == [100, 0, 110, 10]
    assert (tmp_path / "out" / doc["resources"]["I_BTN"]["file"]).exists()
    assert r["navigation"] == {"pages": 2, "links": 1}


def test_convert_assttyys_minimal(tmp_path):
    c = tmp_path / "ass" / "src" / "common"
    (c / "funcList").mkdir(parents=True)
    (c / "multiDetectColors.ts").write_text(
        "const left = 0;\nexport const multiDetectColors: IMultiDetectColors = {\n"
        "  '界面A': { desc: [1280, 720, [[left, 1, 2, 0x112233], [left, 3, 4, 0xffffff]]] },\n};\n", encoding="utf-8")
    (c / "multiFindColors.ts").write_text(
        "export const multiFindColors: IMultiFindColors = {\n"
        "  '找色B': { region: [0, 1280, 720, 10, 20, 300, 400], desc: [[[0, 5, 5, 0x010203], [0, 6, 6, 0x040506]]] },\n};\n",
        encoding="utf-8")
    (c / "funcList" / "F001.ts").write_text(
        "export class Func001 implements IFuncOrigin {\n id = 1;\n name = '测试';\n desc = 'd';\n"
        " operator: IFuncOperatorOrigin[] = [{ desc: '界面A', oper: [[0, 1280, 720, 1, 2, 3, 4, 500]] }];\n"
        " operatorFunc(thisScript, thisOperator) { return false; }\n}\n", encoding="utf-8")
    (c / "schemeList.ts").write_text("[{ id: 1, schemeName: '方案', list: [0, 1, 2] }]", encoding="utf-8")
    r = conv_ass.convert(tmp_path / "ass", tmp_path / "out")
    assert r["colors"] == 2 and r["funcs"] == 1 and r["needs_translation"] == ["001 测试"]
    import yaml
    colors = yaml.safe_load((tmp_path / "out" / "colors.yaml").read_text(encoding="utf-8"))["resources"]
    assert colors["界面A"]["points"] == [[1, 2, "#112233"], [3, 4, "#ffffff"]]
    assert colors["找色B"]["region"] == [10, 20, 300, 400]
    f = yaml.safe_load((tmp_path / "out" / "funcs" / "001.yaml").read_text(encoding="utf-8"))
    assert f["operators"][0]["detect"] == "界面A" and f["operators"][0]["oper"][0]["rect"] == [1, 2, 3, 4]


@pytest.mark.skipif(not UPSTREAM, reason="set OAF_UPSTREAM to test against real upstream checkouts")
def test_convert_real_upstream(tmp_path):
    r = conv_ass.convert(Path(UPSTREAM) / "assttyys_autojs", tmp_path / "ass")
    assert r["colors"] > 100 and r["funcs"] > 100 and not r["parse_errors"]
    r = conv_oas.convert(Path(UPSTREAM) / "OnmyojiAutoScript", tmp_path / "oas")
    assert len(r["tasks"]) > 30


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_cli_init_list_validate(tmp_path, capsys):
    home = str(tmp_path / "home")
    assert main(["--home", home, "init"]) == 0
    assert main(["--home", home, "list"]) == 0
    out = capsys.readouterr().out
    assert "orochi" in out and "realm_raid" in out and "exploration" in out
    assert main(["--home", home, "validate", "orochi"]) == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_cli_diagnose_image(tmp_path, capsys):
    import cv2
    from onmyoji_agentflow.workflow.schema import bundled_dir, load_workflow
    home = str(tmp_path / "home")
    wf = load_workflow(bundled_dir() / "workflows" / "orochi.yaml")
    p = tmp_path / "f.png"
    cv2.imwrite(str(p), frame_for(wf, "prepare"))
    assert main(["--home", home, "diagnose", "orochi", "--image", str(p)]) == 0
    assert "[✓] prepare" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_web_panel_requires_token(tmp_path):
    from http.server import ThreadingHTTPServer

    from onmyoji_agentflow.app import App
    from onmyoji_agentflow.web import Panel, make_handler
    app = App(tmp_path / "home", device_factory=lambda inst: None)
    panel = Panel(app)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(panel))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        html = urllib.request.urlopen(base + "/").read().decode()
        assert panel.token in html
        meta = json.loads(urllib.request.urlopen(base + "/api/meta").read())
        assert "orochi" in meta["workflows"]
        req = urllib.request.Request(base + "/api/confirm", data=b'{"id": 1, "approve": true}', method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
        cid = app.broker.request("购买", "测试")
        req = urllib.request.Request(base + "/api/confirm", data=json.dumps({"id": cid, "approve": False}).encode(),
                                     method="POST", headers={"X-OAF-Token": panel.token})
        assert json.loads(urllib.request.urlopen(req).read())["ok"] is True
        assert app.broker.status(cid) == "denied"
    finally:
        httpd.shutdown()


def test_diagnose_frame_seeds_vars():
    """Real Win10 report: `oaf diagnose` showed "名字 'runs' 未定义" on every guarded state."""
    import numpy as np
    from onmyoji_agentflow.workflow.engine import Runner
    from onmyoji_agentflow.workflow.schema import bundled_dir, load_workflow

    class _O:
        def sleep(self, s):
            pass
    for name in ("orochi", "realm_raid", "exploration"):
        wf = load_workflow(bundled_dir() / "workflows" / f"{name}.yaml")
        rows = Runner(wf, _O()).diagnose_frame(np.zeros((720, 1280, 3), np.uint8))
        assert rows and not [r for r in rows if "error" in r], (name, rows)


def test_realm_raid_no_guild_blocker():
    """The 未入寮 prompt seen on a real Win10 + MuMu 12 stops realm_raid as a prerequisite."""
    import numpy as np
    from onmyoji_agentflow.vision.colors import compare_colors
    from onmyoji_agentflow.workflow.schema import bundled_dir, load_workflow
    wf = load_workflow(bundled_dir() / "workflows" / "realm_raid.yaml")
    b = [x for x in wf.blockers if x["id"] == "no_guild"][0]
    img = np.zeros((720, 1280, 3), np.uint8)
    for x, y, hx in b["when"]["colors"]:
        r, g, bl = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        img[y, x] = (bl, g, r)                                  # screenshots are BGR
    assert compare_colors(img, b["when"]["colors"], 93)
    assert not compare_colors(np.zeros((720, 1280, 3), np.uint8), b["when"]["colors"], 93)


def test_realm_raid_no_barrier_prompt_on_real_frame():
    """Real MuMu 12 screenshot (2026-11-16): joined a guild but no own 寮结界 yet ->「尚未创建阴阳寮结界，是否前往创建」.
    Same dialog layout as the 未入寮 prompt, so the same blocker stops the run instead of waiting for a timeout."""
    from pathlib import Path

    import cv2
    from onmyoji_agentflow.vision.colors import compare_colors
    from onmyoji_agentflow.workflow.schema import bundled_dir, load_workflow
    wf = load_workflow(bundled_dir() / "workflows" / "realm_raid.yaml")
    b = [x for x in wf.blockers if x["id"] == "no_guild"][0]
    img = cv2.imread(str(Path(__file__).parent / "data" / "frames" / "realm_raid_no_guild_barrier.jpg"))
    assert compare_colors(img, b["when"]["colors"], 93)
    other = cv2.imread(str(Path(__file__).parent / "data" / "frames" / "explore_map_mainline.jpg"))
    assert not compare_colors(other, b["when"]["colors"], 93)
