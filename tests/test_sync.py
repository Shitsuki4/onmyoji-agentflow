"""Upstream sync: fetch with mirror fallback, convert, 3-way merge, validate, approve, repair, rollback."""
import json
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest
import yaml

from onmyoji_agentflow import sync as syncmod
from onmyoji_agentflow.app import App
from onmyoji_agentflow.cli import main
from onmyoji_agentflow.workflow.schema import bundled_dir

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required")

GEN = syncmod.GEN
UP = syncmod.UP


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append(kw.get("purpose"))
        return json.dumps(self.reply, ensure_ascii=False)


def _colors():
    return yaml.safe_load((bundled_dir() / "resources" / "assttyys" / "colors.yaml").read_text(encoding="utf-8"))


def _dump(doc) -> str:
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


class FakeUpstream:
    """Replaces the converters: ``colors`` is what upstream's colour data converts to this time."""

    def __init__(self):
        self.colors = _colors()
        self.oas_doc = {"source": "OnmyojiAutoScript", "license": "GPL-3.0",
                        "resources": {"I_BTN": {"type": "click", "rect": [1, 2, 3, 4]}}}
        self.fail_assttyys = False
        self.commit = {"assttyys": "a" * 40, "oas": "b" * 40}

    def convert(self, fetched, out):
        prefixes, errors, report = {}, [], {}
        if "assttyys" in fetched:
            if self.fail_assttyys:
                errors.append("assttyys 转换失败：ValueError: boom")
            else:
                d = out / UP / "assttyys"
                d.mkdir(parents=True)
                (d / "colors.yaml").write_text(_dump(self.colors), encoding="utf-8")
                (d / "LICENSE").write_text("MIT License\nCopyright (c) 2019 Chaos\n")
                g = out / GEN
                shutil.copytree(bundled_dir() / "workflows", g / "workflows")
                (g / "resources" / "assttyys").mkdir(parents=True)
                (g / "resources" / "assttyys" / "colors.yaml").write_text(_dump(self.colors), encoding="utf-8")
                shutil.copyfile(bundled_dir() / "resources" / "assttyys" / "schemes.yaml",
                                g / "resources" / "assttyys" / "schemes.yaml")
                prefixes[f"{UP}/assttyys/"] = "assttyys"
                prefixes[f"{GEN}/"] = "assttyys"
                report["assttyys"] = {"colors": len(self.colors["resources"]), "funcs": 0, "schemes": 0,
                                      "needs_translation": [], "parse_errors": []}
        if "oas" in fetched:
            d = out / UP / "oas"
            d.mkdir(parents=True)
            (d / "Demo.yaml").write_text(_dump(self.oas_doc), encoding="utf-8")
            prefixes[f"{UP}/oas/"] = "oas"
            report["oas"] = {"tasks": 1, "resources": 1, "navigation": None}
        return prefixes, errors, report


@pytest.fixture
def env(tmp_path, monkeypatch):
    up = FakeUpstream()
    monkeypatch.setattr(syncmod, "convert_sources", up.convert)
    src = tmp_path / "src"
    for name in ("assttyys_autojs", "OnmyojiAutoScript"):
        (src / name).mkdir(parents=True)

    def local_source(name, path):
        return syncmod.Fetched(name, Path(path), up.commit[name], str(path))
    monkeypatch.setattr(syncmod, "local_source", local_source)
    app = App(tmp_path / "home", device_factory=lambda inst: None)
    return app, up, src


def _main_file(app, rel):
    data = app.ws.read_bytes(rel)
    return None if data is None else data.decode("utf-8")


def _used_resource(app):
    raw = yaml.safe_load(_main_file(app, "workflows/orochi.yaml"))
    return sorted(syncmod._resource_names_used(raw))[0]


def test_first_sync_merges_data_and_records_upstream(env):
    app, up, src = env
    r = app.sync.sync(local=src)
    assert r.status == "merged", r.message
    man = yaml.safe_load(_main_file(app, syncmod.MANIFEST))
    assert man["sources"]["assttyys"]["commit"] == "a" * 40 and man["sources"]["oas"]["commit"] == "b" * 40
    assert "GPL-3.0" in _main_file(app, syncmod.NOTICE) and "Copyright (c) 2019 Chaos" in _main_file(app, syncmod.NOTICE)
    assert "I_BTN" in _main_file(app, f"{UP}/oas/Demo.yaml")
    assert Path(r.report_path).is_file() and "上游同步 #1" in Path(r.report_path).read_text(encoding="utf-8")
    hist = app.sync.history()
    assert hist[0]["upstream"]["oas"]["commit"] == "b" * 40 and hist[0]["merged_commit"]
    # same upstream again: nothing to do
    r2 = app.sync.sync(local=src)
    assert r2.status == "unchanged"


def test_recognition_change_waits_for_approval_then_rollback(env):
    app, up, src = env
    assert app.sync.sync(local=src).status == "merged"
    used = _used_resource(app)
    spec = up.colors["resources"][used]
    pts = spec["points"]
    pts[0] = [pts[0][0] + 1, pts[0][1], pts[0][2]]
    up.commit["assttyys"] = "c" * 40
    r = app.sync.sync(local=src)
    assert r.status == "waiting_user", r.message
    assert "orochi" in r.details["affected"] and r.details["kind"] == "recognition"
    rd = r.details["diff"]["resources"]["resources/assttyys/colors.yaml"]
    assert used in rd["changed"]
    # main still has the old points
    main_colors = yaml.safe_load(_main_file(app, "resources/assttyys/colors.yaml"))
    assert main_colors["resources"][used]["points"][0][0] == pts[0][0] - 1
    cid = r.change_ids[0]
    app.supervisor.merge_change(cid)
    main_colors = yaml.safe_load(_main_file(app, "resources/assttyys/colors.yaml"))
    assert main_colors["resources"][used]["points"][0][0] == pts[0][0]
    assert app.sync.history()[0]["status"] == "merged"
    # roll back to the previous conversion
    app.sync.rollback()
    main_colors = yaml.safe_load(_main_file(app, "resources/assttyys/colors.yaml"))
    assert main_colors["resources"][used]["points"][0][0] == pts[0][0] - 1
    assert yaml.safe_load(_main_file(app, syncmod.MANIFEST))["sources"]["assttyys"]["commit"] == "a" * 40
    assert app.sync.get(r.id)["status"] == "rolled_back"
    # the rolled-back upstream version is skipped until --force
    assert app.sync.sync(local=src).status in ("skipped", "waiting_user")


def test_rolled_back_version_is_skipped_without_force(env, monkeypatch):
    app, up, src = env
    app.sync.sync(local=src)
    up.oas_doc["resources"]["I_NEW"] = {"type": "click", "rect": [0, 0, 1, 1]}
    up.commit["oas"] = "d" * 40
    r = app.sync.sync(local=src, only=["oas"])
    assert r.status == "merged" and r.details["kind"] == "data"
    app.sync.rollback()
    assert "I_NEW" not in _main_file(app, f"{UP}/oas/Demo.yaml")
    # remote check path (not --from): pretend ls-remote returns the rolled back commits
    monkeypatch.setattr(syncmod, "remote_head", lambda spec, timeout=60: (
        "d" * 40 if "Onmyoji" in spec["urls"][0] else "a" * 40, spec["urls"][0]))
    r = app.sync.sync()
    assert r.status == "skipped" and "--force" in r.message


def test_broken_workflow_reported_and_main_untouched(env):
    app, up, src = env
    app.sync.sync(local=src)
    used = _used_resource(app)
    del up.colors["resources"][used]
    up.commit["assttyys"] = "e" * 40
    r = app.sync.sync(local=src)
    assert r.status == "broken", r.message
    assert "orochi" in r.details["affected"]
    assert r.details["validation"]["orochi"]["failed_step"] == "格式检查"
    assert "没有配置大模型" in r.message
    assert used in _main_file(app, "resources/assttyys/colors.yaml")
    report = Path(r.report_path).read_text(encoding="utf-8")
    assert "没通过" in report and "orochi" in report


class RepairLLM:
    """Answers each sync-repair request by removing the states that use the deleted resource."""

    def __init__(self, res):
        self.res = res
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append(kw.get("purpose"))
        text = messages[1]["content"][0]["text"]
        data = json.loads(text)
        raw = yaml.safe_load(data["workflow_yaml"])
        ids = [st["id"] for st in raw["states"] if self.res in json.dumps(st.get("when"), ensure_ascii=False)]
        return json.dumps({"diagnosis": f"上游删了 {self.res}", "action": "patch",
                           "ops": [{"op": "remove_state", "id": i} for i in ids]}, ensure_ascii=False)


def test_broken_workflow_goes_to_llm_repair(env):
    app, up, src = env
    app.sync.sync(local=src)
    res = "退出结算_左上角贪吃鬼_mumu"
    assert res in up.colors["resources"]
    del up.colors["resources"][res]
    up.commit["assttyys"] = "f" * 40
    llm = RepairLLM(res)
    app.sync.llm = llm
    r = app.sync.sync(local=src)
    broken = r.details["affected"]
    assert "orochi" in broken and llm.calls == ["sync-repair"] * len(broken)
    assert r.status == "repair_waiting", r.message
    rcid = r.change_ids[-1]
    row = app.store.query("SELECT * FROM changes WHERE id=?", (rcid,))[0]
    assert row["status"] == "waiting_user" and row["kind"] == "workflow"
    app.supervisor.merge_change(rcid)
    for name in broken:
        assert res not in _main_file(app, f"workflows/{name}.yaml")
    assert res not in yaml.safe_load(_main_file(app, "resources/assttyys/colors.yaml"))["resources"]
    assert app.sync.get(r.id)["status"] == "merged"


def test_local_edits_survive_upstream_update(env):
    app, up, src = env
    app.sync.sync(local=src)
    # user (or an approved repair) edits a workflow parameter locally
    path = app.ws.path / "workflows" / "orochi.yaml"
    text = path.read_text(encoding="utf-8")
    assert "stuck_timeout_s: 120" in text
    path.write_text(text.replace("stuck_timeout_s: 120", "stuck_timeout_s: 300"), encoding="utf-8")
    app.ws.git("commit", "-qam", "local edit")
    # upstream changes a colour resource nobody uses
    used = set()
    for wf in (app.ws.path / "workflows").glob("*.yaml"):
        used |= syncmod._resource_names_used(yaml.safe_load(wf.read_text(encoding="utf-8")))
    unused = next(k for k in up.colors["resources"] if k not in used)
    up.colors["resources"][unused]["desc"] = "changed"
    up.commit["assttyys"] = "9" * 40
    r = app.sync.sync(local=src)
    assert r.status == "merged", r.message
    assert "stuck_timeout_s: 300" in _main_file(app, "workflows/orochi.yaml")
    assert yaml.safe_load(_main_file(app, "resources/assttyys/colors.yaml"))["resources"][unused]["desc"] == "changed"


def test_conversion_failure_keeps_previous_result(env):
    app, up, src = env
    app.sync.sync(local=src)
    before = _main_file(app, f"{UP}/assttyys/colors.yaml")
    up.fail_assttyys = True
    up.oas_doc["resources"]["I_X"] = {"type": "click", "rect": [0, 0, 2, 2]}
    up.commit = {"assttyys": "1" * 40, "oas": "2" * 40}
    r = app.sync.sync(local=src)
    assert r.status == "merged"
    assert any("assttyys 转换失败" in e for e in r.details["errors"])
    assert _main_file(app, f"{UP}/assttyys/colors.yaml") == before
    assert "I_X" in _main_file(app, f"{UP}/oas/Demo.yaml")
    assert "转换失败" in Path(r.report_path).read_text(encoding="utf-8")


def test_llm_translation_waits_for_approval_and_rejects_unmarked_sensitive(env):
    app, up, src = env
    used = sorted(_colors()["resources"])[0]
    good = {"workflow": {"format": 1, "name": "x", "resources": ["assttyys/colors.yaml"], "states": [
        {"id": "a", "desc": "点一下", "when": {"res": used}, "do": [{"click": [1, 1, 5, 5]}]}]}, "notes": "ok"}
    app.sync.llm = FakeLLM(good)
    schemes = yaml.safe_load((bundled_dir() / "resources" / "assttyys" / "schemes.yaml").read_text(encoding="utf-8"))
    scheme = next(iter(schemes["schemes"]))
    app.sync.ucfg["translate"] = {"schemes": [scheme, "不存在的方案"], "max_per_sync": 2}

    orig = FakeUpstream.convert

    def convert(self, fetched, out):
        res = orig(self, fetched, out)
        if (out / GEN).exists():
            shutil.copyfile(bundled_dir() / "resources" / "assttyys" / "schemes.yaml",
                            out / UP / "assttyys" / "schemes.yaml")
        return res
    syncmod.convert_sources = lambda f, o: convert(up, f, o)
    r = app.sync.sync(local=src)
    tr = {t["scheme"]: t for t in r.details["translations"]}
    assert tr[scheme]["status"] == "waiting_user", tr
    assert tr["不存在的方案"]["status"] == "skipped"
    cid = tr[scheme]["change_id"]
    name = tr[scheme]["workflow"]
    assert app.store.query("SELECT status FROM changes WHERE id=?", (cid,))[0]["status"] == "waiting_user"
    assert _main_file(app, f"workflows/{name}.yaml") is None
    app.supervisor.merge_change(cid)
    wf = yaml.safe_load(_main_file(app, f"workflows/{name}.yaml"))
    assert wf["source"]["license"] == "MIT" and wf["source"]["translated_by"] == "llm"
    # unmarked sensitive step is refused
    bad = json.loads(json.dumps(good))
    bad["workflow"]["states"][0]["desc"] = "花勾玉购买体力"
    app.sync.llm = FakeLLM(bad)
    item = app.sync._translate_one(app.ws.path, "main", "另一个", "ass_test", [], None)
    assert item["status"] == "rejected" and "sensitive" in item["message"]


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_fetch_source_falls_back_to_mirror(tmp_path):
    repo = tmp_path / "up"
    repo.mkdir()
    _git("init", "-q", "-b", "master", cwd=repo)
    (repo / "a.txt").write_text("1")
    _git("add", "-A", cwd=repo)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one", cwd=repo)
    spec = {"branch": "master", "urls": [str(tmp_path / "missing"), repo.as_uri()]}
    f = syncmod.fetch_source("oas", spec, tmp_path / "cache", timeout=60)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert f.commit == head and f.url == repo.as_uri() and (f.path / "a.txt").read_text() == "1"
    assert syncmod.remote_head(spec)[0] == head
    (repo / "a.txt").write_text("2")
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "two", cwd=repo)
    f2 = syncmod.fetch_source("oas", spec, tmp_path / "cache", timeout=60)
    assert f2.commit != head and (f2.path / "a.txt").read_text() == "2"
    with pytest.raises(syncmod.SyncError) as e:
        syncmod.fetch_source("oas", {"branch": "master", "urls": [str(tmp_path / "nope")]}, tmp_path / "c2", 30)
    assert "所有源都拉取失败" in str(e.value)


def test_merge3():
    assert syncmod.merge3(b"a", b"a", b"b") == (b"b", False)
    assert syncmod.merge3(b"x", b"a", b"a") == (b"x", False)
    m, c = syncmod.merge3(b"1\n2\n3x\n", b"1\n2\n3\n", b"1y\n2\n3\n")
    assert m == b"1y\n2\n3x\n" and not c
    assert syncmod.merge3(b"1z\n", b"1\n", b"1y\n") == (b"1z\n", True)


def test_cli_sync_from_real_mini_repos(tmp_path, capsys):
    """End to end with the real converters on tiny upstream checkouts (built-in workflow build fails: reported)."""
    from test_cli_web_convert import _mini_oas
    up = tmp_path / "up"
    oas_root = _mini_oas(up)
    oas_root.rename(up / "OnmyojiAutoScript")
    (up / "OnmyojiAutoScript" / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE Version 3\n")
    c = up / "assttyys_autojs" / "src" / "common"
    (c / "funcList").mkdir(parents=True)
    (c / "multiDetectColors.ts").write_text(
        "export const multiDetectColors: IMultiDetectColors = {\n"
        "  '界面A': { desc: [1280, 720, [[0, 1, 2, 0x112233], [0, 3, 4, 0xffffff]]] },\n};\n", encoding="utf-8")
    (c / "multiFindColors.ts").write_text("export const multiFindColors: IMultiFindColors = {\n};\n", encoding="utf-8")
    (c / "schemeList.ts").write_text("[{ id: 1, schemeName: '方案', list: [0] }]", encoding="utf-8")
    home = str(tmp_path / "home")
    assert main(["--home", home, "sync", "--from", str(up)]) == 0
    out = capsys.readouterr().out
    assert "同步 #1：merged" in out and "生成内置工作流失败" in out
    app = App(Path(home), device_factory=lambda inst: None)
    assert "GNU GENERAL PUBLIC LICENSE" in _main_file(app, f"{UP}/oas/LICENSE")
    assert "Copyright (c) 2019 Chaos" in _main_file(app, f"{UP}/assttyys/LICENSE")
    assert "界面A" in _main_file(app, f"{UP}/assttyys/colors.yaml")
    assert app.ws.read_bytes(f"{UP}/oas/images/Demo/btn.png") is not None or any(
        x.endswith(".png") for x in app.ws.list_files(f"{UP}/oas"))
    assert main(["--home", home, "sync", "status"]) == 0
    assert "#1" in capsys.readouterr().out
    assert main(["--home", home, "sync", "show"]) == 0
    assert "上游同步 #1" in capsys.readouterr().out
    # convert --all re-converts the same upstream (forced)
    assert main(["--home", home, "convert", "--all", str(up)]) == 0
    assert "同步 #2" in capsys.readouterr().out
    assert main(["--home", home, "sync", "rollback"]) == 0
    assert "已回滚" in capsys.readouterr().out


def test_web_panel_sync_endpoints(env):
    from http.server import ThreadingHTTPServer

    from onmyoji_agentflow.web import Panel, make_handler
    app, up, src = env
    app.sync.sync(local=src)
    panel = Panel(app)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(panel))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        st = json.loads(urllib.request.urlopen(base + "/api/status").read())
        assert st["sync"]["history"][0]["status"] == "merged"
        rep = json.loads(urllib.request.urlopen(base + "/api/sync/report?id=1").read())
        assert "上游同步 #1" in rep["report"]
        req = urllib.request.Request(base + "/api/sync", data=b'{"action": "run"}', method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
        req = urllib.request.Request(base + "/api/sync/rollback", data=b"{}", method="POST",
                                     headers={"X-OAF-Token": panel.token})
        assert json.loads(urllib.request.urlopen(req).read())["ok"] is True
        assert app.sync.history()[0]["status"] == "rolled_back"
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "上游同步" in html
    finally:
        httpd.shutdown()


def test_schedule_due(env):
    app, up, src = env
    assert app.sync.due() is False
    app.sync.ucfg["schedule"] = {"enabled": True, "interval_hours": 24}
    assert app.sync.due() is True
    app.store.execute("INSERT INTO syncs(started, trigger, status) VALUES (?,?,?)", (1000.0, "schedule", "merged"))
    assert app.sync.due(now=1000 + 3600) is False and app.sync.due(now=1000 + 25 * 3600) is True
