"""Semantic source coverage, resumability, approvals and durable agent handoff."""
import copy
import json
from pathlib import Path

import pytest

from helpers import FakeClock, blank, fake_text_reader, register_texts
from onmyoji_agentflow.app import App
from onmyoji_agentflow.cli import build_parser
from onmyoji_agentflow.convert.programs import build_catalog
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import BudgetExceeded, WorkflowError
from onmyoji_agentflow.marathon import Marathon, load_plan
from onmyoji_agentflow.mcp_server import MCPServer, Session
from onmyoji_agentflow.programs import assert_current
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml, load_yaml


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def upstream(tmp_path):
    root, converted = tmp_path / "oas", tmp_path / "converted"
    put(root / "tasks" / "Demo" / "script_task.py", "from tasks.Component.Shared.worker import x\nclass ScriptTask:\n    def run(self): return x\n")
    put(root / "tasks" / "Demo" / "config.py", "enabled = False\n")
    put(root / "tasks" / "Component" / "Shared" / "worker.py", "x = 1\n")
    put(root / "tasks" / "Other" / "script_task.py", "raise RuntimeError('must never execute upstream')\n")
    resource = {"resources": {"I_BUTTON": {"type": "click", "rect": [10, 10, 20, 20]}}}
    put(converted / "Demo.yaml", dump_yaml(resource))
    put(converted / "Component_Shared.yaml", "resources: {}\n")
    return root, converted


def entries(converted):
    return {entry["id"]: entry for entry in load_yaml(converted / "programs" / "index.yaml")["entries"]}


def test_catalog_all_entries_and_transitive_dependencies_are_inert(tmp_path, monkeypatch):
    root, converted = upstream(tmp_path)
    report = build_catalog("oas", root, converted, "a" * 40)
    assert report["tasks"] == 2 and not report["errors"]
    entry = entries(converted)["oas:Demo"]
    assert "tasks/Component/Shared/worker.py" in entry["files"]
    assert "tasks/Demo/config.py" in entry["files"]
    assert (converted / "programs/src/tasks/Other/script_task.py.txt").is_file()
    assert "must never execute" in (converted / "programs/src/tasks/Other/script_task.py.txt").read_text()
    monkeypatch.chdir(tmp_path)
    assert build_catalog("oas", Path("oas"), Path("converted"))["tasks"] == 2


def test_fingerprint_tracks_dependencies_and_config_not_unrelated_commits(tmp_path):
    root, converted = upstream(tmp_path)
    build_catalog("oas", root, converted, "a" * 40)
    before = entries(converted)
    build_catalog("oas", root, converted, "b" * 40)
    assert entries(converted)["oas:Demo"]["fingerprint"] == before["oas:Demo"]["fingerprint"]
    put(root / "tasks/Component/Shared/worker.py", "x = 2\n")
    build_catalog("oas", root, converted, "c" * 40)
    after = entries(converted)
    assert after["oas:Demo"]["fingerprint"] != before["oas:Demo"]["fingerprint"]
    assert after["oas:Other"]["fingerprint"] == before["oas:Other"]["fingerprint"]
    put(root / "tasks/Demo/config.py", "enabled = True\n")
    build_catalog("oas", root, converted)
    assert entries(converted)["oas:Demo"]["fingerprint"] != after["oas:Demo"]["fingerprint"]


def test_assttyys_schemes_and_unreferenced_components_all_indexed(tmp_path):
    root, out = tmp_path / "ass", tmp_path / "out"
    put(root / "src/common/funcList/001_a.ts", "id = 1; operatorFunc() { return false; }")
    put(root / "src/common/funcList/002_b.ts", "id = 2;")
    put(out / "schemes.yaml", dump_yaml({"schemes": {"日常": [1], "缺依赖": [9]}}))
    put(out / "colors.yaml", "resources: {}")
    result = build_catalog("assttyys", root, out)
    assert result["tasks"] == result["components"] == 2
    assert set(entries(out)) == {"assttyys:func:001", "assttyys:func:002", "assttyys:scheme:日常", "assttyys:scheme:缺依赖"}
    assert entries(out)["assttyys:scheme:缺依赖"]["missing_funcs"] == [9]


@pytest.fixture
def app(tmp_path):
    root, out = upstream(tmp_path)
    a = App(tmp_path / "home", device_factory=lambda _: pytest.fail("conversion must never open a device"))
    import shutil
    build_catalog("oas", root, out, "a" * 40)
    shutil.copytree(out, a.ws.path / "resources/upstream/oas")
    a.ws.git("add", "-A")
    a.ws.git("commit", "-qm", "fixture catalog")
    a.programs.index(a.ws.path, "main")
    return a


def job(app, identifier="oas:Demo"):
    return next(row for row in app.programs.list() if row["entry_id"] == identifier)


def reply():
    return {"complete": True, "unsupported": [], "notes": "完整转换", "workflow": {
        "format": 1, "name": "ignored", "resources": ["upstream/oas/Demo.yaml"],
        "states": [{"id": "prepare", "when": {"text": "准备"}, "do": [
            {"click": "I_BUTTON"}, {"stop": {"reason": "有界执行结束", "result": "unknown"}}]}]}}


class LLM:
    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls, self.contexts = data or reply(), error, 0, []

    def chat(self, messages, **kwargs):
        self.calls += 1
        self.contexts.append(json.loads(messages[1]["content"]))
        if self.error:
            raise self.error
        return json.dumps(self.data, ensure_ascii=False)


def test_queue_no_llm_source_pagination_and_path_boundary(app):
    result = app.programs.compile(job(app)["id"])
    assert result[0]["status"] == "waiting_agent"
    info = app.programs.source(job(app)["id"])
    name = info["entry"]["files"][0]
    first = app.programs.source(job(app)["id"], name, limit=2)
    second = app.programs.source(job(app)["id"], name, offset=first["next_offset"])
    assert not first["complete"] and second["complete"]
    full = app.programs.source(job(app)["id"], name)["text"]
    assert first["text"] + second["text"] == full
    with pytest.raises(ValueError):
        app.programs.source(job(app)["id"], "../../config.yaml")


def test_complete_translation_proposed_once_never_auto_activated(app):
    app.programs.llm = llm = LLM()
    before = app.ws.head()
    result = app.programs.compile(job(app)["id"])[0]
    assert result["status"] == "waiting_user"
    assert app.ws.head() == before
    assert not app.ws.workflow_path(job(app)["workflow"]).exists()
    change = app.store.query("SELECT * FROM changes WHERE id=?", (result["change_id"],))[0]
    assert change["status"] == "waiting_user"
    assert json.loads(change["validation"])["verification"] == "unverified"
    assert app.programs.compile(job(app)["id"]) == []
    assert llm.calls == 1
    assert llm.contexts[0]["sources"]["tasks/Component/Shared/worker.py"] == "x = 1\n"
    again = app.programs.propose(job(app)["id"], reply())
    assert again["change_id"] == result["change_id"]


@pytest.mark.parametrize("kind", ["partial", "unsafe", "unsafe_text", "foreign_resource", "no_input", "unconditional"])
def test_bad_translations_never_become_executable(app, kind):
    data = reply()
    if kind == "partial":
        data["unsupported"] = ["动态选队伍未翻译"]
    elif kind == "unsafe":
        data["workflow"]["states"][0]["desc"] = "购买蓝票"
    elif kind == "unsafe_text":
        data["workflow"]["states"][0]["when"] = {"text": "购买"}
    elif kind == "foreign_resource":
        data["workflow"]["resources"] = ["../../config.yaml"]
    elif kind == "no_input":
        data["workflow"]["states"][0]["do"] = [{"stop": "尚未实现"}]
    else:
        data["workflow"]["states"][0]["when"] = {"expr": "True"}
    app.programs.llm = LLM(data)
    assert app.programs.compile(job(app)["id"])[0]["status"] == "blocked"
    assert not app.store.query("SELECT * FROM changes")


def test_large_input_is_not_truncated_or_sent(app):
    app.cfg.data["upstream"]["translate"]["max_prompt_chars"] = 10
    app.programs.llm = llm = LLM()
    result = app.programs.compile(job(app)["id"])[0]
    assert result["status"] == "blocked" and "未截断" in result["message"]
    assert llm.calls == 0


def test_large_program_uses_bounded_retrieval_and_keeps_transcript(app):
    entry = app.programs.source(job(app)["id"])["entry"]
    shared = "tasks/Component/Shared/worker.py"
    put(app.ws.path / "resources/upstream/oas/programs/src" / (shared + ".txt"), "x = 1\n" + "# shared code\n" * 2000)
    app.ws.git("add", "-A")
    app.ws.git("commit", "-qm", "large source fixture")
    app.programs.index(app.ws.path, "main")
    app.cfg.data["upstream"]["translate"]["max_prompt_chars"] = 12000
    class RetrievalLLM:
        def __init__(self): self.calls = 0
        def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                initial = json.loads(messages[1]["content"])
                assert shared in initial["source_index"] and shared not in initial["sources"]
                return json.dumps({"action": "read", "requests": [{"kind": "source", "path": shared, "chars": 100}]})
            result = json.loads(messages[-1]["content"])["read_results"][0]
            assert not result["complete"] and result["next_offset"] == 100
            return json.dumps({"action": "finish", "complete": False, "unsupported": ["共享逻辑尚未读全"]})
    app.programs.llm = llm = RetrievalLLM()
    result = app.programs.compile(job(app)["id"])[0]
    assert result["status"] == "blocked" and llm.calls == 2
    assert list((app.cfg.home / "program-transcripts").glob("*.json"))


def test_converted_workflow_first_run_requires_person_before_device_access(app):
    result = app.programs.propose(job(app)["id"], reply())
    # Simulate a person's merge using the existing merge API. Execution still asks first-run approval.
    app.supervisor.merge_change(result["change_id"])
    asked = []
    app.supervisor.confirm = lambda category, detail, instance: asked.append(category) or False
    outcome = app.supervisor.run(job(app)["workflow"], repair=False)
    assert outcome.result.failure_kind == "confirm_denied"
    assert asked == ["新脚本首次运行"]
    assert not app.store.query("SELECT * FROM program_activations")


def test_budget_resumes_next_batch_without_resetting_completed_jobs(app):
    app.programs.llm = LLM(error=BudgetExceeded("预算已满"))
    assert app.programs.compile(limit=1)[0]["status"] == "budget"
    app.programs.llm = LLM()
    assert app.programs.compile(limit=1)[0]["status"] == "waiting_user"


def test_changed_source_supersedes_old_queue_and_stale_workflow(app):
    data = reply()
    app.programs.propose(job(app)["id"], data)
    old = job(app)
    meta = app.programs.source(old["id"])["entry"]
    doc_path = app.ws.path / "resources/upstream/oas/programs/index.yaml"
    doc = load_yaml(doc_path)
    next(entry for entry in doc["entries"] if entry["id"] == "oas:Demo")["fingerprint"] = "new"
    put(doc_path, dump_yaml(doc))
    app.ws.git("add", "-A")
    app.ws.git("commit", "-qm", "new source")
    app.programs.index(app.ws.path, "main")
    assert job(app)["id"] != old["id"]
    with pytest.raises(ValueError, match="源程序已更新"):
        app.programs.propose(old["id"], data)
    assert app.programs._set(old["id"], "failed", "late worker completion")["status"] == "superseded"
    raw = reply()["workflow"]
    raw["source"] = {"origin": "oas", "entry_id": "oas:Demo", "fingerprint": meta["fingerprint"]}
    wf = load_workflow(raw, [app.ws.path / "resources"])
    with pytest.raises(WorkflowError, match="上游脚本已变化"):
        assert_current(wf, app.ws.path)


def test_plan_accepts_namespaced_program_and_does_not_modify_input():
    raw = {"items": [{"program": "oas:Duel", "params": {}, "scope": "weekly"}]}
    before = copy.deepcopy(raw)
    plan = load_plan(raw)
    assert plan["items"][0]["workflow"].startswith("oas_")
    assert raw == before
    with pytest.raises(ValueError):
        load_plan({"items": [{"program": "oas:Duel", "workflow": "arbitrary"}]})


def test_pending_program_preview_and_runner_skip_without_navigation(app, tmp_path):
    plan = {"task_aware": False, "home_between": True, "items": [{"program": "oas:Demo"}]}
    preview = app.plans.preview(path=plan)
    assert preview["items"][0]["status"] == "blocked"
    assert preview["items"][0]["translation"]["status"] == "pending"
    runner = Marathon(app, "main", load_plan(plan), tmp_path / "plan", max_rounds=1)
    runner.run()
    assert "home" not in runner.totals
    assert next(iter(runner.totals.values())).blocked == 1


def failing_app(tmp_path, kind="error"):
    frame = register_texts(blank(), [("准备", 100, 100)])
    class BrokenDevice(ReplayDevice):
        def tap(self, *args, **kwargs):
            raise RuntimeError("test device input failed")
    a = App(tmp_path / "home", device_factory=lambda _: BrokenDevice([frame]))
    a.supervisor.scfg["max_local_retries"] = 0
    a.supervisor.clock = FakeClock(step=0.1)
    raw = {"format": 1, "name": "broken", "limits": {"timeout_s": 1 if kind == "timeout" else 60},
           "states": [{"id": "prepare", "when": {"text": "准备"}, "do":
                       [{"wait": 6000}] if kind == "timeout" else [{"click": [95, 95, 105, 105]}]}]}
    put(a.ws.workflow_path("broken"), dump_yaml(raw))
    a.ws.git("add", "-A")
    a.ws.git("commit", "-qm", "failing fixture")
    a.supervisor.controller_factory = lambda inst, observe: Controller(a.device(inst), observe=observe, sleep=lambda _: None)
    return a


@pytest.mark.parametrize("kind,expected", [("error", "workflow_error"), ("timeout", "timeout")])
def test_runtime_error_and_timeout_create_durable_handoff_without_repair(tmp_path, kind, expected):
    a = failing_app(tmp_path, kind)
    outcome = a.supervisor.run("broken", repair=False)
    assert outcome.result.failure_kind == expected
    handoff = a.handoffs.get(outcome.result.evidence["handoff_id"])
    assert handoff["status"] == "pending"
    assert Path(handoff["packet"]["screenshot"]).is_file()
    assert handoff["packet"]["workflow_yaml"]
    if kind == "error":
        assert handoff["packet"]["failure"]["failed_state"] == "prepare"
    assert len(a.handoffs.list()) == 1


def test_plan_stops_on_handoff_before_starting_next_workflow(tmp_path):
    a = failing_app(tmp_path)
    plan = load_plan({"home_between": False, "task_aware": False,
                      "items": [{"workflow": "broken"}, {"workflow": "home"}]})
    runner = Marathon(a, "main", plan, tmp_path / "run", max_rounds=1)
    reason = runner.run()
    assert "agent 接管" in reason
    assert "broken" in runner.totals and "home" not in runner.totals


def test_interrupted_handoff_can_be_claimed_again_without_blind_resume(tmp_path):
    a = failing_app(tmp_path)
    outcome = a.supervisor.run("broken", repair=False)
    handoff_id = outcome.result.evidence["handoff_id"]
    a.handoffs.update(handoff_id, "diagnosing", "prior process exited")
    a.supervisor.diagnose_and_repair = lambda *args: ("human", "需要补充实际界面样本")
    result = a.handoffs.diagnose(handoff_id)
    assert result["status"] == "needs_agent" and not result["resumed"]


def test_cli_and_mcp_expose_queue_without_approval_shortcuts(app):
    parser = build_parser()
    assert parser.parse_args(["programs", "compile", "--limit", "2"]).limit == 2
    assert parser.parse_args(["handoffs", "show", "--id", "1"]).id == 1
    assert parser.parse_args(["marathon"]).repair
    assert not parser.parse_args(["marathon", "--no-repair"]).repair
    server = MCPServer(app)
    names = {tool["name"] for tool in server.tools.list()}
    assert {"upstream_programs", "agent_handoffs"} <= names
    result = server.tools.call("upstream_programs", {"action": "list"}, Session())
    assert not result["isError"]
    assert len(json.loads(result["content"][0]["text"])["programs"]) == 2
