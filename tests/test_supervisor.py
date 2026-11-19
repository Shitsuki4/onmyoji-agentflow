import json
import shutil

import pytest

from helpers import FakeClock, blank, frame_for
from onmyoji_agentflow.config import DEFAULT_CONFIG
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.errors import BudgetExceeded, LLMError
from onmyoji_agentflow.llm import LLMClient
from onmyoji_agentflow.store import Store
from onmyoji_agentflow.supervisor import ConfirmationBroker, Supervisor, Workspace
from onmyoji_agentflow.supervisor.repair import apply_ops, classify
from onmyoji_agentflow.workflow.schema import load_workflow

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required")


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        return json.dumps(self.reply, ensure_ascii=False)


def make_sup(tmp_path, frames_by_mode, llm=None, confirm=None, cfg_over=None):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["supervisor"].update({"max_local_retries": 0, "observe_seconds": 3, "trial_actions": 3})
    cfg["supervisor"].update(cfg_over or {})
    store = Store(tmp_path / "state.db")
    ws = Workspace(tmp_path / "ws")
    ws.init()
    devices = {}

    def factory(instance, observe):
        frames = frames_by_mode()
        dev = ReplayDevice(frames, advance_on_input=not observe)
        devices.setdefault("all", []).append(dev)
        return Controller(dev, HumanizeConfig(), observe=observe, sleep=lambda s: None)

    sup = Supervisor(cfg, store, ws, factory, confirm=confirm, llm=llm, runs_dir=tmp_path / "runs",
                     sleep=lambda s: None, clock=FakeClock(step=1.0))
    return sup, store, ws, devices


def shifted_prepare(wf):
    """A prepare screen whose colours drifted (e.g. after a game update): no state matches it."""
    img = frame_for(wf, "prepare")
    img[img != 40] = (img[img != 40].astype(int) // 2).astype("uint8")
    return img


def test_repair_ops_classification():
    assert classify([{"op": "set", "path": "limits.stuck_timeout_s", "value": 1}]) == "params"
    assert classify([{"op": "recapture_colors", "state": "a", "points": []}]) == "recognition"
    assert classify([{"op": "set", "path": "states", "value": []}]) == "workflow"
    assert classify([{"op": "set_delay", "state": "a", "value": 1}, {"op": "remove_state", "id": "a"}]) == "workflow"


def test_recapture_samples_colours_from_frame():
    raw = {"format": 1, "name": "t", "states": [{"id": "a", "when": {"colors": [[1, 1, "#000000"]]}}]}
    img = blank()
    img[5, 6] = (1, 2, 3)
    out = apply_ops(raw, [{"op": "recapture_colors", "state": "a", "points": [[6, 5], [7, 7], [8, 8]]}], img)
    assert out["states"][0]["when"]["colors"][0] == [6, 5, "#030201"]
    assert raw["states"][0]["when"]["colors"] == [[1, 1, "#000000"]]  # original untouched


def _wf(ws):
    return load_workflow(ws.path / "workflows" / "orochi.yaml", [ws.path / "resources"])


def test_failure_repair_validate_and_wait_for_user(tmp_path):
    holder = {}

    def frames():
        return holder["frames"]

    asked = []
    llm = FakeLLM(None)
    sup, store, ws, _ = make_sup(tmp_path, frames, llm=llm, confirm=lambda c, d, i="": asked.append(c) or False)
    wf = _wf(ws)
    bad = shifted_prepare(wf)
    holder["frames"] = [bad]
    prepare = next(s for s in wf.states if s["id"] == "prepare")
    spec = wf.resources[prepare["when"]["res"]]
    pts = [[p[0], p[1]] for p in spec["points"]]
    llm.reply = {"diagnosis": "准备按钮颜色变了", "action": "patch", "expected_state": "prepare",
                 "ops": [{"op": "recapture_colors", "state": "prepare", "points": pts}]}
    main_before = ws.head("main")
    out = sup.run("orochi", "main")
    assert out.result.failure_kind == "unknown_screen"
    assert llm.calls == 1
    assert out.level == "proposed", out.notes
    assert asked == ["合并改动"]          # recognition change needs the user
    assert ws.head("main") == main_before   # main not replaced
    ch = store.query("SELECT * FROM changes")[0]
    assert ch["status"] == "waiting_user" and ch["kind"] == "recognition"
    report = json.loads(ch["validation"])
    assert report["replay"]["total"] == 1 and not report["replay"]["failed"]
    # the user approves -> merged, and the repaired workflow now recognises the screen
    sup.approve_change(ch["id"])
    assert ws.head("main") != main_before
    from onmyoji_agentflow.supervisor.replay import first_match
    assert first_match(_wf(ws), bad) == "prepare"
    assert (ws.path / "tests" / "orochi").exists()


def test_params_change_auto_merges_and_rolls_back(tmp_path):
    holder = {}
    llm = FakeLLM({"diagnosis": "放宽超时", "action": "patch", "expected_state": None,
                   "ops": [{"op": "set", "path": "limits.unknown_timeout_s", "value": 90}]})
    sup, store, ws, _ = make_sup(tmp_path, lambda: holder["frames"], llm=llm, confirm=lambda *a: True)
    wf = _wf(ws)
    good_cycle = [frame_for(wf, "challenge_0"), frame_for(wf, "prepare"), frame_for(wf, "settle_6")]
    # failing run: unknown screen. Validation (observe + trial) sees a good cycle.
    seq = iter([[blank()]] + [good_cycle * 20] * 50)
    holder_fn = lambda: next(seq)  # noqa: E731
    sup.controller_factory = lambda inst, obs: Controller(ReplayDevice(holder_fn(), advance_on_input=not obs),
                                                          HumanizeConfig(), observe=obs, sleep=lambda s: None)
    before = ws.head("main")
    out = sup.run("orochi", "main")
    assert out.level == "repaired", out.notes
    assert ws.head("main") != before
    assert _wf(ws).limits["unknown_timeout_s"] == 90
    # the new version now fails 3 times in a row -> automatic rollback
    seq2 = iter([[blank()]] * 10)
    sup.controller_factory = lambda inst, obs: Controller(ReplayDevice(next(seq2)), HumanizeConfig(), observe=obs,
                                                          sleep=lambda s: None)
    for _ in range(3):
        sup.run("orochi", "main", repair=False)
    ch = store.query("SELECT * FROM changes")[0]
    assert ch["status"] == "rolled_back"
    assert _wf(ws).limits["unknown_timeout_s"] == 60
    assert "自动回滚" in ws.log(1)[0]


def test_bad_patch_is_rejected_and_main_untouched(tmp_path):
    llm = FakeLLM({"diagnosis": "x", "action": "patch", "expected_state": "prepare",
                   "ops": [{"op": "set_similarity", "state": "prepare", "value": 93}]})
    holder = {}
    sup, store, ws, _ = make_sup(tmp_path, lambda: holder["frames"], llm=llm, confirm=lambda *a: True)
    wf = _wf(ws)
    holder["frames"] = [shifted_prepare(wf)]
    before = ws.head("main")
    out = sup.run("orochi", "main")
    assert out.level == "human" and "回放测试" in out.notes[-1]
    assert ws.head("main") == before
    assert store.query("SELECT status FROM changes")[0]["status"] == "rejected"


def test_patch_cannot_remove_confirmation(tmp_path):
    from onmyoji_agentflow.supervisor.repair import sensitive_preserved
    raw = {"format": 1, "name": "t", "states": [
        {"id": "buy", "sensitive": "购买", "when": {"colors": [[1, 1, "#000000"]]}, "do": [{"click": [0, 0, 5, 5]}]}]}
    a = load_workflow(raw)
    b = load_workflow(apply_ops(raw, [{"op": "replace_state", "state": {
        "id": "buy", "when": {"colors": [[1, 1, "#000000"]]}, "do": [{"click": [0, 0, 5, 5]}]}}]))
    assert not sensitive_preserved(a, b)


def test_confirmation_broker(tmp_path):
    store = Store(tmp_path / "s.db")
    b = ConfirmationBroker(store, timeout_s=0.05, poll_s=0.01)
    assert b("购买", "买体力") is False                 # nobody answered -> refused
    assert store.query("SELECT status FROM confirmations")[0]["status"] == "expired"
    cid = b.request("抽卡", "x")
    assert b.decide(cid, True) and b.wait(cid) is True


def test_llm_failover_and_budget(tmp_path):
    store = Store(tmp_path / "s.db")
    calls = []

    def transport(url, payload, key, timeout):
        calls.append(url)
        if "primary" in url:
            raise LLMError("HTTP 500")
        return {"choices": [{"message": {"content": "{\"ok\": 1}"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}}

    cfg = {"providers": [{"name": "a", "base_url": "https://primary/v1", "model": "m", "vision": True},
                         {"name": "b", "base_url": "https://backup/v1", "model": "m", "vision": True}],
           "budget": {"daily_tokens": 300, "calls_per_hour": 100}}
    c = LLMClient(cfg, store, transport=transport, key_getter=lambda n: "k")
    assert c.chat([{"role": "user", "content": "hi"}]) == '{"ok": 1}'
    assert calls == ["https://primary/v1/chat/completions", "https://backup/v1/chat/completions"]
    c.chat([{"role": "user", "content": "hi"}])      # 300 tokens used now
    with pytest.raises(BudgetExceeded):
        c.chat([{"role": "user", "content": "hi"}])


def test_llm_text_only_fallback_strips_images(tmp_path):
    store = Store(tmp_path / "s.db")
    seen = {}

    def transport(url, payload, key, timeout):
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    cfg = {"providers": [{"name": "ds", "base_url": "https://x/v1", "model": "deepseek-chat", "vision": False}]}
    c = LLMClient(cfg, store, transport=transport, key_getter=lambda n: "k")
    c.chat([{"role": "user", "content": [{"type": "text", "text": "t"},
                                          {"type": "image_url", "image_url": {"url": "data:x"}}]}], need_vision=True)
    assert isinstance(seen["payload"]["messages"][0]["content"], str)


def test_llm_has_no_limit_by_default(tmp_path):
    """No usage limit unless the user sets one (llm.budget defaults to null)."""
    assert all(v is None for v in DEFAULT_CONFIG["llm"]["budget"].values())
    assert DEFAULT_CONFIG["upstream"]["translate"]["max_per_sync"] is None
    store = Store(tmp_path / "s.db")

    def transport(url, payload, key, timeout):
        return {"choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 400_000, "completion_tokens": 400_000}}

    cfg = json.loads(json.dumps(DEFAULT_CONFIG["llm"]))
    cfg["providers"] = [{"name": "a", "base_url": "https://a/v1", "model": "m", "vision": True}]
    c = LLMClient(cfg, store, transport=transport, key_getter=lambda n: "k")
    for _ in range(40):                                  # 32M tokens and 40 calls in an hour: still fine
        assert c.chat([{"role": "user", "content": "hi"}]) == "ok"
    snap = c.budget.snapshot()
    assert snap["limits"] == "不限" and snap["day"]["calls"] == 40
    # 0 and empty values also mean "no limit"; a limit the user sets still works
    c.budget.cfg = {"daily_tokens": 0, "calls_per_hour": "", "monthly_tokens": None}
    c.chat([{"role": "user", "content": "hi"}])
    c.budget.cfg = {"calls_per_hour": 42}       # 41 calls so far
    c.chat([{"role": "user", "content": "hi"}])
    with pytest.raises(BudgetExceeded):
        c.chat([{"role": "user", "content": "hi"}])


def test_untouched_v010_limits_are_removed_but_user_limits_kept(tmp_path):
    from onmyoji_agentflow.config import Config
    from onmyoji_agentflow.yamlio import dump_yaml
    home = tmp_path / "h"
    home.mkdir()
    v010 = {"monthly_tokens": 10_000_000, "daily_tokens": 400_000, "calls_per_hour": 30, "daily_cost": None}
    (home / "config.yaml").write_text(dump_yaml({"llm": {"budget": dict(v010)},
                                                 "upstream": {"translate": {"schemes": [], "max_per_sync": 2}}}),
                                      encoding="utf-8")
    cfg = Config(home)
    assert all(v is None for v in cfg["llm"]["budget"].values())
    assert cfg["upstream"]["translate"]["max_per_sync"] is None
    assert Config(home)["llm"]["budget"]["daily_tokens"] is None          # written back to the file
    (home / "config.yaml").write_text(dump_yaml({"llm": {"budget": {**v010, "daily_tokens": 123}}}), encoding="utf-8")
    assert Config(home)["llm"]["budget"]["daily_tokens"] == 123          # edited by the user: kept as is
    assert Config(home)["llm"]["budget"]["monthly_tokens"] == 10_000_000


def test_prerequisite_goes_to_user_without_repair(tmp_path):
    from helpers import blank
    import yaml as _y
    llm = FakeLLM(None)
    img = blank()
    img[30, 30] = (0, 255, 0)
    sup, store, ws, devices = make_sup(tmp_path, lambda: [img], llm=llm, cfg_over={"max_local_retries": 2})
    p = ws.path / "workflows" / "orochi.yaml"
    raw = _y.safe_load(p.read_text(encoding="utf-8"))
    raw["requires"] = ["账号已加入阴阳寮"]
    raw["blockers"] = [{"id": "no_guild", "when": {"colors": [[30, 30, "#00ff00"]]}, "message": "账号还没加入阴阳寮"}]
    p.write_text(_y.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    out = sup.run("orochi", "main")
    assert out.result.failure_kind == "prerequisite"
    assert out.level == "human" and any("阴阳寮" in n for n in out.notes)
    assert llm.calls == 0                         # no LLM diagnosis, no patch
    assert not any(n.startswith("第 ") for n in out.notes)   # no local retries


def _ops(devices, kind):
    return [i for d in devices.get("all", []) for i in d.inputs if i and i[0] == kind]


def test_local_retry_does_not_press_back_by_default(tmp_path):
    """v0.1.4 pressed back before every local retry; on 庭院 that opens 「退出游戏」 (seen on the real device)."""
    img = blank()
    sup, store, ws, devices = make_sup(tmp_path, lambda: [img], cfg_over={"max_local_retries": 2})
    out = sup.run("orochi", "main", repair=False)
    assert out.result.failure_kind == "unknown_screen"
    assert sum(n.startswith("第 ") for n in out.notes) == 2          # two local retries happened
    assert _ops(devices, "back") == []                              # ...without any back key


def test_local_retry_presses_back_only_when_configured(tmp_path):
    img = blank()
    sup, store, ws, devices = make_sup(tmp_path, lambda: [img],
                                       cfg_over={"max_local_retries": 1, "recover_back_on": ["unknown_screen"]})
    out = sup.run("orochi", "main", repair=False)
    assert out.result.failure_kind == "unknown_screen"
    assert len(_ops(devices, "back")) == 1
    assert any("返回键" in n for n in out.notes)


def test_upgraded_workspace_gets_new_bundled_workflows_but_keeps_edits_and_deletions(tmp_path):
    from onmyoji_agentflow.supervisor.versioning import Workspace
    src = tmp_path / "bundled"
    (src / "workflows").mkdir(parents=True)
    (src / "resources").mkdir()
    (src / "workflows" / "orochi.yaml").write_text("name: orochi\n", encoding="utf-8")
    (src / "workflows" / "exploration.yaml").write_text("name: exploration\n", encoding="utf-8")
    ws = Workspace(tmp_path / "ws")
    ws.init(src)
    # the user edits one workflow and deletes the other
    (ws.path / "workflows" / "orochi.yaml").write_text("name: orochi\n# mine\n", encoding="utf-8")
    (ws.path / "workflows" / "exploration.yaml").unlink()
    ws.git("add", "-A"); ws.git("commit", "-q", "-m", "user edits")
    # a newer release ships two more workflows
    (src / "workflows" / "home.yaml").write_text("name: home\n", encoding="utf-8")
    (src / "workflows" / "event_boss.yaml").write_text("name: event_boss\n", encoding="utf-8")
    assert ws.add_new_bundled(src) == ["event_boss.yaml", "home.yaml"]
    assert (ws.path / "workflows" / "home.yaml").exists()
    assert "# mine" in (ws.path / "workflows" / "orochi.yaml").read_text(encoding="utf-8")
    assert not (ws.path / "workflows" / "exploration.yaml").exists()
    assert ws.git("status", "--porcelain") == ""
    # running again changes nothing, and a deleted new workflow is not brought back
    (ws.path / "workflows" / "home.yaml").unlink()
    ws.git("add", "-A"); ws.git("commit", "-q", "-m", "drop home")
    assert ws.add_new_bundled(src) == []
    assert not (ws.path / "workflows" / "home.yaml").exists()


def test_workspace_from_before_the_known_list_gets_only_missing_workflows(tmp_path):
    from onmyoji_agentflow.supervisor.versioning import Workspace
    src = tmp_path / "bundled"
    (src / "workflows").mkdir(parents=True)
    (src / "workflows" / "orochi.yaml").write_text("name: orochi\n", encoding="utf-8")
    ws = Workspace(tmp_path / "ws")
    ws.init(src)
    (ws.path / Workspace.KNOWN_FILE).unlink()   # a v0.1.6 workspace has no list
    ws.git("add", "-A"); ws.git("commit", "-q", "-m", "old layout")
    (src / "workflows" / "daily_rewards.yaml").write_text("name: daily_rewards\n", encoding="utf-8")
    assert ws.add_new_bundled(src) == ["daily_rewards.yaml"]
    assert ws.git("status", "--porcelain") == ""


def test_bundled_upgrade_does_not_commit_unrelated_staged_edits(tmp_path):
    from onmyoji_agentflow.supervisor.versioning import Workspace
    source = tmp_path / "bundled"
    (source / "workflows").mkdir(parents=True)
    (source / "workflows" / "orochi.yaml").write_text("name: orochi\n", encoding="utf-8")
    workspace = Workspace(tmp_path / "ws")
    workspace.init(source)
    rel = "workflows/orochi.yaml"
    (workspace.path / rel).write_text("name: orochi\ntitle: Local edit\n", encoding="utf-8")
    workspace.git("add", "--", rel)
    (source / "workflows" / "home.yaml").write_text("name: home\n", encoding="utf-8")

    assert workspace.add_new_bundled(source) == ["home.yaml"]
    assert workspace.read(rel) == "name: orochi"
    assert workspace.git("diff", "--cached", "--name-only") == rel
