"""MCP server: protocol, tools, approvals that stay with the person, config, HTTP loopback."""
import json
import queue
import threading
import time
import urllib.error
import urllib.request

import pytest
import yaml

from helpers import blank, frame_for
from onmyoji_agentflow.app import App
from onmyoji_agentflow.cli import main
from onmyoji_agentflow.config import Config, needs_approval, validate_setting
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import AgentflowError
from onmyoji_agentflow.mcp_server import TOOLS, MCPServer, Session, make_http_server, serve_stdio


@pytest.fixture
def app(tmp_path):
    holder = {"frames": [blank()]}
    a = App(tmp_path / "home", device_factory=lambda inst: ReplayDevice(holder["frames"]))
    a.holder = holder
    return a


def call(server, name, args=None, session=None):
    session = session or Session()
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": args or {}}}, session)
    res = resp["result"]
    data = json.loads(res["content"][0]["text"]) if not res["isError"] else res["content"][0]["text"]
    return res, data


def eliciting_session(answer):
    asked = []

    def requester(method, params, timeout):
        asked.append((method, params))
        return answer
    s = Session(requester=requester)
    s.protocol = "2025-06-18"
    s.capabilities = {"elicitation": {}}
    return s, asked


def add_change(app, status="waiting_user"):
    cur = app.store.execute("INSERT INTO changes(created, workflow, kind, branch, status, note, validation) "
                            "VALUES (?,?,?,?,?,?,?)", (time.time(), "orochi", "recognition", "repair/x", status,
                                                       "准备按钮颜色变了", "{}"))
    return cur.lastrowid


def test_initialize_and_tool_list(app):
    server = MCPServer(app)
    s = Session()
    r = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "t", "version": "1"}}}, s)
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert r["result"]["serverInfo"]["name"] == "onmyoji-agentflow"
    assert "tools" in r["result"]["capabilities"]
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, s) is None
    names = {t["name"] for t in server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, s)["result"]["tools"]}
    for want in ("list_instances", "screenshot", "list_workflows", "validate_workflow", "run_workflow",
                 "stop_workflow", "observe", "status", "logs", "diagnose", "sync", "list_pending", "approve",
                 "reject", "rollback", "get_config", "set_config"):
        assert want in names
    for t in TOOLS:
        assert t["inputSchema"]["type"] == "object"
    # unknown version -> newest we speak; unknown method / tool -> JSON-RPC errors
    r = server.handle({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {"protocolVersion": "1999"}}, s)
    assert r["result"]["protocolVersion"] == "2025-11-25"
    assert server.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"}, s)["error"]["code"] == -32601
    r = server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope"}}, s)
    assert r["error"]["code"] == -32602


def test_workflow_tools_screenshot_and_diagnose(app, tmp_path):
    server = MCPServer(app)
    res, data = call(server, "list_workflows")
    names = [w["name"] for w in data["workflows"]]
    assert "orochi" in names
    res, data = call(server, "validate_workflow", {"workflow": "orochi"})
    assert data["format"] == "ok" and not data["ok"] and data["coverage"] == "insufficient"
    res, data = call(server, "validate_workflow", {"workflow": "不存在"})
    assert res["isError"] and "没有工作流" in data

    wf = app.supervisor.load("orochi")
    app.holder["frames"] = [frame_for(wf, "prepare")]
    res, data = call(server, "screenshot", {"max_width": 640})
    assert res["content"][1]["type"] == "image" and res["content"][1]["mimeType"] == "image/png"
    assert data["size"] == [1280, 720]
    res, data = call(server, "diagnose", {"workflow": "orochi"})
    assert "prepare" in data["matched"]
    res, data = call(server, "screenshot", {"instance": "没有这个"})
    assert res["isError"] and "没有实例" in data
    res, data = call(server, "list_instances")
    assert data["configured"][0]["name"] == "main"


def test_observe_never_taps_and_status_logs(app):
    server = MCPServer(app)
    wf = app.supervisor.load("orochi")
    app.holder["frames"] = [frame_for(wf, "prepare")]
    taps = []
    real = ReplayDevice.tap
    ReplayDevice.tap = lambda self, x, y, *a, **k: taps.append((x, y))
    try:
        res, data = call(server, "observe", {"workflow": "orochi", "seconds": 1})
    finally:
        ReplayDevice.tap = real
    assert data["status"] == "finished" and data["mode"] == "observe", data
    assert taps == []
    assert "prepare" in json.dumps(data["summary"], ensure_ascii=False)
    res, data = call(server, "status")
    assert data["llm"] == "没有启用大模型供应商"
    assert data["jobs"][0]["workflow"] == "orochi"
    res, data = call(server, "logs", {"source": "mcp"})
    assert any("MCP 启动 orochi" in e["message"] for e in data["events"])
    res, data = call(server, "run_workflow", {"workflow": "orochi", "params": {"乱写": 1}})
    assert res["isError"] and "没有参数" in data


def test_run_and_stop(app):
    server = MCPServer(app)
    app.holder["frames"] = [blank()]          # unknown screen: the run waits until stuck or stopped
    res, data = call(server, "run_workflow", {"workflow": "orochi", "mode": "trial", "actions": 1000})
    assert data["status"] == "running"
    res, data = call(server, "run_workflow", {"workflow": "orochi"})
    assert res["isError"] and "正在运行" in data
    res, data = call(server, "stop_workflow", {})
    assert data["stopping"] is True
    job = server.tools.jobs["main"]
    assert job["done"].wait(30)
    assert job["status"] == "finished"


def test_sensitive_confirmation_needs_the_person(app):
    server = MCPServer(app)
    cid = app.broker.request("抽卡", "用勾玉抽一次", "main")
    res, data = call(server, "list_pending")
    assert data["confirmations"][0]["id"] == cid

    # a client without elicitation cannot approve: the item stays pending
    res, data = call(server, "approve", {"kind": "confirmation", "id": cid})
    assert data["approved"] is False and data["needs_user"] is True
    assert any("oaf confirm" in x for x in data["user_can_approve_with"])
    assert app.broker.status(cid) == "pending"

    # the person closes the question or the agent tries to answer for them in other ways -> still pending
    for answer in ({"action": "cancel"}, {"action": "decline"}, {"action": "accept", "content": {}},
                   {"action": "accept", "content": {"decision": "yes"}}):
        s, asked = eliciting_session(answer)
        res, data = call(server, "approve", {"kind": "confirmation", "id": cid}, s)
        assert data["approved"] is False and asked[0][0] == "elicitation/create"
        assert app.broker.status(cid) == "pending"

    # elicitation switched off in config: no question, no approval
    app.cfg["mcp"]["elicitation_approval"] = False
    s, asked = eliciting_session({"action": "accept", "content": {"decision": "approve"}})
    res, data = call(server, "approve", {"kind": "confirmation", "id": cid}, s)
    assert data["needs_user"] and asked == [] and app.broker.status(cid) == "pending"
    app.cfg["mcp"]["elicitation_approval"] = True

    # the person approves in the client
    s, asked = eliciting_session({"action": "accept", "content": {"decision": "approve"}})
    res, data = call(server, "approve", {"kind": "confirmation", "id": cid}, s)
    assert data["approved"] is True
    assert "抽卡" in asked[0][1]["message"]
    assert app.broker.status(cid) == "approved"
    res, data = call(server, "approve", {"kind": "confirmation", "id": cid}, s)
    assert res["isError"]

    # reject needs no approval
    cid2 = app.broker.request("出售", "卖掉御魂", "main")
    res, data = call(server, "reject", {"kind": "confirmation", "id": cid2})
    assert data["rejected"] and app.broker.status(cid2) == "denied"


def test_running_workflow_blocks_on_sensitive_step_until_person_answers(app, tmp_path):
    """A sensitive state in a run waits on the broker; the agent alone cannot get past it."""
    ws = app.ws.path
    wf_doc = yaml.safe_load((ws / "workflows" / "orochi.yaml").read_text(encoding="utf-8"))
    wf = app.supervisor.load("orochi")
    target = next(s for s in wf_doc["states"] if s["id"] == "prepare")
    target["sensitive"] = "购买"
    (ws / "workflows" / "buy.yaml").write_text(
        yaml.safe_dump({**wf_doc, "name": "buy"}, allow_unicode=True), encoding="utf-8")
    app.holder["frames"] = [frame_for(wf, "prepare")]
    app.broker.poll_s = 0.05
    server = MCPServer(app)
    taps = []
    real = ReplayDevice.tap
    ReplayDevice.tap = lambda self, x, y, *a, **k: taps.append((x, y))
    try:
        res, data = call(server, "run_workflow", {"workflow": "buy", "mode": "trial", "actions": 1, "repair": False})
        assert not res["isError"], data
        for _ in range(200):
            pend = app.broker.pending()
            if pend:
                break
            time.sleep(0.05)
        assert pend and pend[0]["category"] == "购买"
        res, data = call(server, "approve", {"kind": "confirmation", "id": pend[0]["id"]})
        assert data["needs_user"] and taps == []
        call(server, "reject", {"kind": "confirmation", "id": pend[0]["id"]})
        server.tools.jobs["main"]["done"].wait(30)
    finally:
        ReplayDevice.tap = real
    assert taps == []                        # refused: the sensitive tap never happened


def test_change_approval_reject_and_rollback(app, monkeypatch):
    server = MCPServer(app)
    cid = add_change(app)
    res, data = call(server, "approve", {"kind": "change", "id": cid})
    assert data["needs_user"] and any("oaf approve" in x for x in data["user_can_approve_with"])
    assert app.store.query("SELECT status FROM changes WHERE id=?", (cid,))[0]["status"] == "waiting_user"

    merged = []
    monkeypatch.setattr(app.supervisor, "approve_change", lambda i: merged.append(i) or "abc123")
    s, asked = eliciting_session({"action": "accept", "content": {"decision": "approve"}})
    res, data = call(server, "approve", {"kind": "change", "id": cid}, s)
    assert data["approved"] and merged == [cid] and data["merged_commit"] == "abc123"

    cid2 = add_change(app)
    s, asked = eliciting_session({"action": "accept", "content": {"decision": "deny"}})
    res, data = call(server, "approve", {"kind": "change", "id": cid2}, s)
    assert data["denied"] is True
    assert app.store.query("SELECT status FROM changes WHERE id=?", (cid2,))[0]["status"] == "rejected"

    res, data = call(server, "rollback", {"target": "change", "id": cid2})
    assert res["isError"] and "没有合并过" in data
    res, data = call(server, "rollback", {"target": "sync"})
    assert res["isError"]


def test_rollback_merged_change_with_git(tmp_path):
    """rollback_change reverts the merge commit of a real merged change."""
    app = App(tmp_path / "home", device_factory=lambda inst: ReplayDevice([blank()]))
    ws = app.ws
    text = ws.read("workflows/orochi.yaml").replace("title:", "title: 改过 #", 1)
    branch, commit = ws.propose("orochi", "params", {"workflows/orochi.yaml": text}, "test change")
    cur = app.store.execute("INSERT INTO changes(created, workflow, kind, branch, commit_id, status, note) "
                            "VALUES (?,?,?,?,?,?,?)", (time.time(), "orochi", "params", branch, commit,
                                                       "waiting_user", "t"))
    cid = cur.lastrowid
    app.supervisor.approve_change(cid)
    assert "改过" in (ws.path / "workflows" / "orochi.yaml").read_text(encoding="utf-8")
    res, data = call(MCPServer(app), "rollback", {"target": "change", "id": cid})
    assert not res["isError"], data
    assert "改过" not in (ws.path / "workflows" / "orochi.yaml").read_text(encoding="utf-8")
    assert app.store.query("SELECT status FROM changes WHERE id=?", (cid,))[0]["status"] == "rolled_back"


def test_config_tools_and_limits(app, monkeypatch):
    server = MCPServer(app)
    res, data = call(server, "get_config", {"path": "llm.budget"})
    assert data["value"] == {"monthly_tokens": None, "daily_tokens": None, "calls_per_hour": None, "daily_cost": None}
    res, data = call(server, "set_config", {"path": "llm.budget.daily_tokens", "value": 200000})
    assert data["changed"] and data["new"] == 200000
    assert Config(app.cfg.home).data["llm"]["budget"]["daily_tokens"] == 200000
    res, data = call(server, "set_config", {"path": "llm.budget.daily_tokens", "value": None})
    assert data["changed"] and Config(app.cfg.home).data["llm"]["budget"]["daily_tokens"] is None
    res, data = call(server, "set_config", {"path": "llm.budget.daily_tokens", "value": "很多"})
    assert res["isError"]
    res, data = call(server, "set_config", {"path": "nothing.here", "value": 1})
    assert res["isError"]

    # switching a provider on is applied at once
    monkeypatch.setattr("onmyoji_agentflow.credentials.has_key", lambda n: False)
    res, data = call(server, "set_config", {"path": "llm.providers.0.enabled", "value": True})
    assert data["changed"] and app.llm is not None and app.supervisor.llm is app.llm and app.sync.llm is app.llm
    res, data = call(server, "status")
    assert data["llm"]["limits"] == "不限"
    call(server, "set_config", {"path": "llm.budget.calls_per_hour", "value": 5})
    assert app.llm.budget.limits() == {"calls_per_hour": 5}

    # safety settings need the person
    res, data = call(server, "set_config", {"path": "supervisor.auto_merge.images", "value": True})
    assert data["changed"] is False and data["needs_user"]
    assert app.cfg["supervisor"]["auto_merge"] == {"params": True, "images": False, "workflow": False}
    res, data = call(server, "set_config", {"path": "mcp.elicitation_approval", "value": False})
    assert data["changed"] is False
    res, data = call(server, "set_config", {"path": "web.host", "value": "0.0.0.0"})
    assert data["changed"] is False
    res, data = call(server, "set_config", {"path": "supervisor", "value": {**app.cfg["supervisor"], "auto_merge": {"workflow": True}}})
    assert data["changed"] is False
    s, _ = eliciting_session({"action": "accept", "content": {"decision": "approve"}})
    res, data = call(server, "set_config", {"path": "supervisor.auto_merge.params", "value": False}, s)
    assert data["changed"] and data["approved_by_user"] and app.cfg["supervisor"]["auto_merge"]["params"] is False


def test_provider_address_change_needs_approval():
    data = {"llm": {"providers": [{"name": "a", "base_url": "https://x/v1"}]}, "supervisor": {"auto_merge": {}},
            "mcp": {}, "web": {"host": "127.0.0.1"}}
    assert needs_approval("llm.providers.0.base_url", "https://evil/v1", data)
    assert needs_approval("llm.providers.0.model", "m2", data) is None
    assert needs_approval("llm.providers", [{"name": "b", "base_url": "https://y"}], data,
                          has_key=lambda n: n == "b")
    assert needs_approval("web.host", "localhost", data) is None
    with pytest.raises(ValueError):
        validate_setting("mcp.http.host", "0.0.0.0")
    with pytest.raises(ValueError):
        validate_setting("upstream.translate.max_per_sync", -1)
    validate_setting("upstream.translate.max_per_sync", None)


class _Pipe:
    """stdin/stdout stand-ins for serve_stdio."""

    def __init__(self):
        self.inq = queue.Queue()
        self.outq = queue.Queue()

    def __iter__(self):
        while True:
            line = self.inq.get()
            if line is None:
                return
            yield line

    def write(self, data):
        for line in data.decode("utf-8").splitlines():
            self.outq.put(json.loads(line))

    def flush(self):
        pass

    def send(self, obj):
        self.inq.put(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")

    def recv(self, timeout=20):
        return self.outq.get(timeout=timeout)


def test_stdio_transport_with_elicitation(app):
    pipe = _Pipe()
    t = threading.Thread(target=serve_stdio, args=(MCPServer(app), pipe, pipe), daemon=True)
    t.start()
    pipe.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {"elicitation": {}},
                          "clientInfo": {"name": "test", "version": "0"}}})
    assert pipe.recv()["result"]["serverInfo"]["name"] == "onmyoji-agentflow"
    pipe.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    pipe.inq.put(b"not json\n")
    assert pipe.recv()["error"]["code"] == -32700
    cid = app.broker.request("分解", "分解御魂", "main")
    pipe.send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": "approve", "arguments": {"kind": "confirmation", "id": cid}}})
    ask = pipe.recv()
    assert ask["method"] == "elicitation/create" and "分解" in ask["params"]["message"]
    # while the question is open, other calls still work
    pipe.send({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert pipe.recv() == {"jsonrpc": "2.0", "id": 3, "result": {}}
    assert app.broker.status(cid) == "pending"
    pipe.send({"jsonrpc": "2.0", "id": ask["id"], "result": {"action": "accept", "content": {"decision": "approve"}}})
    resp = pipe.recv()
    assert resp["id"] == 2 and json.loads(resp["result"]["content"][0]["text"])["approved"] is True
    assert app.broker.status(cid) == "approved"
    pipe.inq.put(None)
    t.join(5)


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream", **(headers or {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, dict(r.headers), json.loads(r.read() or b"null")


def test_http_loopback_only_session_and_token(app):
    with pytest.raises(AgentflowError):
        make_http_server(MCPServer(app), "0.0.0.0", 0)
    httpd = make_http_server(MCPServer(app), "127.0.0.1", 0, token="s3cret")
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/mcp"
    auth = {"Authorization": "Bearer s3cret"}
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(url, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert e.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(url, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, {**auth, "Origin": "https://evil.example"})
        assert e.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(url, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, {**auth, "Host": "evil.example"})
        assert e.value.code == 403
        status, headers, body = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                            "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}, auth)
        sid = headers.get("Mcp-Session-Id")
        assert status == 200 and sid and body["result"]["protocolVersion"] == "2025-06-18"
        status, _, body = _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                {**auth, "Mcp-Session-Id": sid})
        assert status == 202
        cid = app.broker.request("花勾玉", "买体力", "main")
        status, _, body = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "approve", "arguments": {"kind": "confirmation", "id": cid}}},
                                {**auth, "Mcp-Session-Id": sid, "Origin": f"http://localhost:{port}"})
        data = json.loads(body["result"]["content"][0]["text"])
        assert data["needs_user"] and app.broker.status(cid) == "pending"   # HTTP never approves by itself
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(url, {"jsonrpc": "2.0", "id": 3, "method": "ping"}, {**auth, "Mcp-Session-Id": "stale"})
        assert e.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_cli_config_and_mcp_parser(tmp_path, capsys):
    home = str(tmp_path / "h")
    assert main(["--home", home, "init"]) == 0
    assert main(["--home", home, "config", "set", "llm.budget.monthly_tokens", "5000000"]) == 0
    assert Config(home).data["llm"]["budget"]["monthly_tokens"] == 5000000
    assert main(["--home", home, "config", "set", "llm.budget.monthly_tokens", "null"]) == 0
    assert Config(home).data["llm"]["budget"]["monthly_tokens"] is None
    capsys.readouterr()
    assert main(["--home", home, "config", "get", "llm.budget"]) == 0
    assert json.loads(capsys.readouterr().out)["daily_tokens"] is None
    assert main(["--home", home, "config", "set", "llm.budget.monthly_tokens", "-3"]) == 2
    assert main(["--home", home, "mcp", "--http", "--host", "0.0.0.0", "--port", "0"]) == 2


def test_skill_md_covers_every_tool():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "skills" / "onmyoji-agentflow" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: onmyoji-agentflow\ndescription: ")
    for t in TOOLS:
        assert f"`{t['name']}`" in text, t["name"]
