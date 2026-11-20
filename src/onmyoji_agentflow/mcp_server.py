"""MCP server: lets an external agent (Codex, Claude Code, ...) drive onmyoji-agentflow.

``oaf mcp`` speaks MCP over stdio (the default) or Streamable HTTP on a loopback address
(``oaf mcp --http``). It is a thin layer over the same App the CLI and the web panel use.

Approvals stay with the person. An agent can list pending items and ask for approval, but a
sensitive action (spending jade, summoning, buying, selling, dismantling) or a change that edits
recognition data or a workflow is only approved when the person says so:

* over stdio, when the client supports MCP elicitation and ``mcp.elicitation_approval`` is on,
  the server asks the person directly in the client and acts on their answer;
* otherwise the tool returns ``needs_user`` and the person approves in the web panel or with
  ``oaf confirm`` / ``oaf approve`` in a terminal.

Refusing (reject) is always allowed, because it only keeps things as they are. Config settings
that loosen a safety rule (``supervisor.auto_merge``, ``mcp``, exposing the web panel, sending a
saved API key to a new address) go through the same approval.
"""
from __future__ import annotations

import base64
import ipaddress
import itertools
import json
import secrets
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, credentials
from .config import LOOPBACK_HOSTS, get_path, needs_approval, set_path, validate_setting
from .errors import AgentflowError
from .log import logger

SERVER_NAME = "onmyoji-agentflow"
# newest first; the first one is offered when the client asks for a version we do not know
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
ELICITATION_SINCE = "2025-06-18"
APPROVAL_TIMEOUT_S = 600
MAX_WAIT_S = 600
MAX_TEXT = 20000

INSTRUCTIONS = (
    "onmyoji-agentflow 控制 MuMu 12 上的阴阳师 YAML 工作流。先用 status 和 list_workflows 看现状，"
    "新工作流或改过的工作流先用 observe（只识别不点击）确认能认出画面，再 run_workflow。"
    "花勾玉、抽卡、购买、出售、分解这类敏感操作，以及改识别数据/工作流的修复，必须由用户本人批准："
    "approve 会在支持的客户端里直接问用户，否则返回 needs_user，请把待批准内容转告用户，"
    "让用户在网页面板或终端里自己批准。不要替用户批准，也不要在终端里替用户执行 oaf confirm / oaf approve。"
)


class ToolError(Exception):
    """A tool call that cannot be done; the message goes back to the agent as an error result."""


def _dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)


def _result(data, images=()) -> dict:
    content = [{"type": "text", "text": _dumps(data)}]
    for b64 in images:
        content.append({"type": "image", "data": b64, "mimeType": "image/png"})
    return {"content": content, "isError": False}


def _error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _clip(text: str, n: int = MAX_TEXT) -> str:
    return text if len(text) <= n else text[:n] + f"\n…（后面还有 {len(text) - n} 个字符）"


def _loopback(host: str) -> bool:
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


class Session:
    """One MCP connection: the negotiated version and, over stdio, a way to ask the client."""

    def __init__(self, requester=None):
        self.protocol = PROTOCOL_VERSIONS[0]
        self.client = {}
        self.capabilities = {}
        self.requester = requester        # (method, params, timeout) -> result dict
        self.id = secrets.token_hex(16)
        self.last_seen = time.time()

    def can_elicit(self) -> bool:
        return (self.requester is not None and "elicitation" in (self.capabilities or {})
                and self.protocol >= ELICITATION_SINCE)


# ------------------------------------------------------------------------------------ tools

def _schema(props: dict | None = None, required: tuple = ()) -> dict:
    s = {"type": "object", "properties": props or {}, "additionalProperties": False}
    if required:
        s["required"] = list(required)
    return s


_INSTANCE = {"type": "string", "description": "实例名（config.yaml 里 instances[].name），不填用第一个"}
_WORKFLOW = {"type": "string", "description": "工作流名，见 list_workflows"}

TOOLS = [
    {"name": "list_instances", "title": "列出设备和实例",
     "description": "列出 config.yaml 里配置的 MuMu 12 实例、本机找到的 MuMu 实例，以及哪些实例正在运行工作流。",
     "inputSchema": _schema(), "annotations": {"readOnlyHint": True}},
    {"name": "screenshot", "title": "截图",
     "description": "截取一个实例当前的游戏画面，返回图片，同时存一份到数据目录的 runs/mcp-screenshots。只读，不会点击。",
     "inputSchema": _schema({"instance": _INSTANCE,
                             "max_width": {"type": "integer", "minimum": 160, "maximum": 3840,
                                           "description": "图片最大宽度，默认 1280"}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "list_workflows", "title": "列出工作流",
     "description": "列出工作区里的工作流：名字、标题、状态数和可调参数的默认值。",
     "inputSchema": _schema(), "annotations": {"readOnlyHint": True}},
    {"name": "validate_workflow", "title": "校验工作流",
     "description": "检查工作流 YAML 格式，并用 tests/<工作流> 里的截图跑回放测试。",
     "inputSchema": _schema({"workflow": _WORKFLOW}, ("workflow",)), "annotations": {"readOnlyHint": True}},
    {"name": "run_workflow", "title": "运行工作流",
     "description": ("在一个实例上后台运行工作流。mode=run 正常运行（带监管和自动修复），observe 只识别不点击，"
                     "trial 最多执行 actions 次操作。运行中遇到敏感操作会停下来等用户批准（见 list_pending）。"
                     "wait_seconds>0 时最多等这么久并返回结果，否则马上返回，之后用 status 查看。"),
     "inputSchema": _schema({
         "workflow": _WORKFLOW, "instance": _INSTANCE,
         "mode": {"type": "string", "enum": ["run", "observe", "trial"], "default": "run"},
         "params": {"type": "object", "description": "工作流参数，如 {\"max_runs\": 10}，见 list_workflows"},
         "seconds": {"type": "number", "minimum": 1, "description": "observe 模式时长，默认 config 里的 observe_seconds"},
         "actions": {"type": "integer", "minimum": 1, "description": "trial 模式最多操作次数，默认 trial_actions"},
         "repair": {"type": "boolean", "default": True, "description": "run 模式失败时是否自动诊断修复"},
         "wait_seconds": {"type": "number", "minimum": 0, "maximum": MAX_WAIT_S, "default": 0}},
         ("workflow",)),
     "annotations": {"destructiveHint": False, "idempotentHint": False}},
    {"name": "stop_workflow", "title": "停止工作流",
     "description": "跨 CLI/面板/MCP 停止同一物理设备；立即停止输入或战斗结算后停。",
     "inputSchema": _schema({"instance": _INSTANCE, "mode": {"type": "string", "enum": ["immediate", "after_battle"]}}),
     "annotations": {"idempotentHint": True}},
    {"name": "marathon_start", "title": "启动日常计划",
     "description": "按计划预览或后台启动日活、周活、活动工作流；支持一轮后停、截止时间和小规模试跑。",
     "inputSchema": _schema({"instance": _INSTANCE, "plan": {"type": ["string", "object"], "description": "计划路径或内联计划对象；items 支持 program: oas:Duel"},
                              "out": {"type": "string"}, "rounds": {"type": "integer", "minimum": 1},
                              "hours": {"type": "number", "minimum": 0.01}, "preview": {"type": "boolean"}},
                             ()), "annotations": {"idempotentHint": False}},
    {"name": "marathon_status", "title": "查看日常计划",
     "description": "查看日常计划运行状态、任务账本、预算和最近样本。",
     "inputSchema": _schema(), "annotations": {"readOnlyHint": True}},
    {"name": "marathon_stop", "title": "停止日常计划",
     "description": "请求日常计划停止；子工作流在下一次动作边界停止。",
     "inputSchema": _schema({"instance": _INSTANCE}), "annotations": {"idempotentHint": True}},
    {"name": "observe", "title": "观察模式",
     "description": "观察模式跑一个工作流：只截图识别，从不点击。跑完返回认出了哪些状态，适合新工作流或改动后先确认。",
     "inputSchema": _schema({"workflow": _WORKFLOW, "instance": _INSTANCE,
                             "seconds": {"type": "number", "minimum": 1, "maximum": MAX_WAIT_S}},
                            ("workflow",)),
     "annotations": {"readOnlyHint": True}},
    {"name": "status", "title": "查看状态",
     "description": "正在运行的任务、最近的运行记录、待批准的确认项和改动、最近一次同步、大模型用量和上限。",
     "inputSchema": _schema({"n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "logs", "title": "查看日志",
     "description": "最近的事件日志（可按级别、来源过滤），或者用 run_id 看某次运行的完整摘要。",
     "inputSchema": _schema({"n": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                             "level": {"type": "string", "enum": ["info", "warn", "error"]},
                             "source": {"type": "string", "description": "如 supervisor、sync、confirm、mcp"},
                             "run_id": {"type": "integer"}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "diagnose", "title": "诊断画面",
     "description": "看当前画面（或一张截图文件）匹配工作流里的哪些状态，返回每个状态的匹配结果和分数。",
     "inputSchema": _schema({"workflow": _WORKFLOW, "instance": _INSTANCE,
                             "image_path": {"type": "string", "description": "本机截图文件路径；不填就截当前画面"}},
                            ("workflow",)),
     "annotations": {"readOnlyHint": True}},
    {"name": "sync", "title": "同步上游",
     "description": ("同步 assttyys / OAS 上游（等同 oaf sync）。action=run 拉取转换验证（后台进行，要几分钟），"
                     "force 上游没变也重新转换，check 只看有没有更新，status 同步记录，show 看某次同步的报告。"
                     "会改识别数据的结果照常等用户批准。"),
     "inputSchema": _schema({
         "action": {"type": "string", "enum": ["run", "force", "check", "status", "show"], "default": "run"},
         "id": {"type": "integer", "description": "show 的同步编号，默认最近一次"},
         "only": {"type": "array", "items": {"type": "string", "enum": ["assttyys", "oas"]}},
         "offline": {"type": "boolean", "description": "不联网，用上次拉下来的缓存"},
         "no_translate": {"type": "boolean", "description": "这次不让大模型翻译新方案"},
         "validate_on": {"type": "string", "description": "验证时也在这个实例上跑观察模式和限次试跑"},
         "n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}}),
     "annotations": {"openWorldHint": True}},
    {"name": "upstream_programs", "title": "统一上游脚本转换",
     "description": ("收录 OAS/ assttyys 全部任务与组件。list 查看队列，source 分页读取完整源码，compile 后台续传转换，"
                     "propose 提交外部 agent 的完整 format:1 转换结果；只创建待审候选，不批准、不运行。"),
     "inputSchema": _schema({
         "action": {"type": "string", "enum": ["list", "source", "compile", "propose"], "default": "list"},
         "id": {"type": "integer", "minimum": 1}, "source": {"type": "string", "enum": ["oas", "assttyys"]},
         "status": {"type": "string"}, "path": {"type": "string"},
         "offset": {"type": "integer", "minimum": 0}, "chars": {"type": "integer", "minimum": 1, "maximum": 40000},
         "limit": {"type": "integer", "minimum": 0}, "retry": {"type": "boolean"},
         "proposal": {"type": "object", "description": "{complete:true,unsupported:[],workflow:{...},notes:...}"}}),
     "annotations": {"idempotentHint": False}},
    {"name": "agent_handoffs", "title": "查看与处理故障接管",
     "description": ("list 查看超时/卡死/异常的持久队列，show 读取截图路径、日志、工作流与源码版本，"
                     "diagnose 让配置的 agent 诊断，propose 提交修复 ops。沿用审批门禁，计划保持暂停。"),
     "inputSchema": _schema({"action": {"type": "string", "enum": ["list", "show", "diagnose", "propose"], "default": "list"},
                             "id": {"type": "integer", "minimum": 1}, "proposal": {"type": "object"}}),
     "annotations": {"idempotentHint": False}},
    {"name": "list_pending", "title": "待批准事项",
     "description": "列出等用户批准的敏感操作确认项（kind=confirmation）和已通过验证、等用户批准的改动（kind=change）。",
     "inputSchema": _schema(), "annotations": {"readOnlyHint": True}},
    {"name": "approve", "title": "请求用户批准",
     "description": ("请用户批准一个待批准事项。不会直接批准：客户端支持时会弹出确认框问用户本人，用户选“批准”才生效；"
                     "否则返回 needs_user，请把内容转告用户，让用户在网页面板或终端（oaf confirm / oaf approve）里自己批准。"),
     "inputSchema": _schema({"kind": {"type": "string", "enum": ["confirmation", "change"]},
                             "id": {"type": "integer"}}, ("kind", "id")),
     "annotations": {"destructiveHint": False}},
    {"name": "reject", "title": "拒绝",
     "description": "拒绝一个待批准事项：敏感操作不执行，改动不合并。拒绝不需要用户确认。",
     "inputSchema": _schema({"kind": {"type": "string", "enum": ["confirmation", "change"]},
                             "id": {"type": "integer"}}, ("kind", "id")),
     "annotations": {"idempotentHint": True}},
    {"name": "rollback", "title": "回滚",
     "description": ("target=sync 把上游转换结果退回上一版（id 不填就是最近一次同步）；"
                     "target=change 撤销一个已合并的改动（id 必填）。回滚是新的提交，历史都保留。"),
     "inputSchema": _schema({"target": {"type": "string", "enum": ["sync", "change"]},
                             "id": {"type": "integer"}}, ("target",)),
     "annotations": {"destructiveHint": True}},
    {"name": "get_config", "title": "读取配置",
     "description": ("读取 config.yaml 的设置，path 用点分隔，如 llm.budget、llm.providers.0.model；不填返回全部。"
                     "API key 不在配置里，只返回各供应商有没有保存 key。"),
     "inputSchema": _schema({"path": {"type": "string"}}), "annotations": {"readOnlyHint": True}},
    {"name": "set_config", "title": "修改配置",
     "description": ("修改 config.yaml 的一项设置并立即生效，如 llm.budget.daily_tokens=200000（null 表示不限，默认就是不限）、"
                     "llm.providers.0.enabled=true、upstream.schedule.enabled=true。"
                     "放宽安全规则的设置（supervisor.auto_merge、mcp、把面板开到本机以外、改已存 key 的供应商地址）要用户本人批准。"
                     "API key 不能用这个工具设置，请用户在终端运行 oaf key set <供应商名>。"),
     "inputSchema": _schema({"path": {"type": "string"},
                             "value": {"description": "新的值（任意 JSON：数字、字符串、true/false、null、列表、对象）"}},
                            ("path", "value")),
     "annotations": {"idempotentHint": True}},
]


class AgentTools:
    """The MCP tools, on top of one App."""

    def __init__(self, app, panel_url: str | None = None):
        self.app = app
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}         # instance -> current / last job started from MCP
        self.sync_job: dict | None = None
        self.program_job: dict | None = None
        self.handoff_job: dict | None = None
        self.marathon_jobs: dict[str, dict] = {}
        self.panel_url = panel_url or "http://{host}:{port}/".format(**app.cfg["web"])
        self.by_name = {t["name"]: t for t in TOOLS}

    # -------------------------------------------------------------- helpers
    def list(self) -> list[dict]:
        return TOOLS

    def call(self, name: str, args: dict, session: Session | None = None) -> dict:
        if name not in self.by_name:
            raise KeyError(name)
        try:
            return getattr(self, "t_" + name)(args or {}, session)
        except (ToolError, AgentflowError, KeyError, ValueError, FileNotFoundError) as e:
            msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
            return _error(f"{name} 没有完成：{msg}")
        except Exception as e:  # noqa: BLE001
            logger.exception("MCP tool %s failed", name)
            return _error(f"{name} 出错：{type(e).__name__}: {e}")

    def _instance(self, args) -> str:
        name = args.get("instance") or None
        inst = self.app.cfg.instance(name)          # KeyError with a readable message when unknown
        return name or inst.get("name") or str(inst.get("mumu_id"))

    def _workflow(self, args):
        name = args.get("workflow")
        if not name:
            raise ToolError("要写工作流名（见 list_workflows）")
        if name not in self.app.workflows():
            raise ToolError(f"没有工作流 {name}，现有：{'、'.join(self.app.workflows()) or '无'}")
        return self.app.supervisor.load(name)

    def _how_to_approve(self, kind: str, cid: int) -> list[str]:
        cmd = f"oaf confirm {cid} yes" if kind == "confirmation" else f"oaf approve {cid}"
        return [f"网页面板：运行 oaf web，打开 {self.panel_url} ，在待确认 / 改动里批准",
                f"终端：{cmd}"]

    def _ask_person(self, session: Session | None, title: str, lines: list[str]) -> tuple[str, str]:
        """Ask the person (MCP elicitation). Returns (verdict, note); verdict is approved / denied /
        unanswered / unavailable. Only an explicit "approve" choice by the person approves."""
        if not (self.app.cfg.get("mcp") or {}).get("elicitation_approval", True):
            return "unavailable", "config.yaml 里 mcp.elicitation_approval 关掉了，只能在网页面板或终端批准"
        if session is None or not session.can_elicit():
            return "unavailable", "这个客户端（或 HTTP 连接）不支持 MCP elicitation，没法直接问你"
        message = (f"{title}\n\n" + "\n".join(lines) +
                   "\n\n这是 onmyoji-agentflow 请你本人确认，agent 不能替你选。看清楚再选「批准」或「拒绝」。")
        schema = {"type": "object", "properties": {
            "decision": {"type": "string", "title": "你的决定", "enum": ["approve", "deny"],
                         "enumNames": ["批准", "拒绝"]}}, "required": ["decision"]}
        try:
            res = session.requester("elicitation/create", {"message": message, "requestedSchema": schema},
                                    APPROVAL_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001
            return "unanswered", f"没有拿到你的回答：{e}"
        action = (res or {}).get("action")
        decision = ((res or {}).get("content") or {}).get("decision")
        if action == "accept" and decision == "approve":
            return "approved", "你在客户端里选了批准"
        if action == "accept" and decision == "deny":
            return "denied", "你在客户端里选了拒绝"
        return "unanswered", "你关掉了确认框，没有做决定"

    # -------------------------------------------------------------- devices
    def t_list_instances(self, args, session):
        app = self.app
        configured = []
        for i in app.cfg["instances"]:
            name = i.get("name") or str(i.get("mumu_id"))
            job = self.jobs.get(name)
            configured.append({**i, "name": name,
                               "running": job["workflow"] if job and job["status"] == "running" else None})
        found, note = [], None
        try:
            from .device import discover
            for m in discover(app.cfg.get("mumu_root")):
                found.append({"mumu_id": m.instance_id, "name": m.name, "serial": m.serial})
        except Exception as e:  # noqa: BLE001
            note = f"查找 MuMu 实例失败：{e}"
        out = {"configured": configured, "mumu_found": found}
        if note:
            out["note"] = note
        elif not found:
            out["note"] = "本机没找到 MuMu 12（只在 Windows 上自动查找；可以在 config.yaml 写 mumu_root）"
        return _result(out)

    def t_screenshot(self, args, session):
        import cv2
        instance = self._instance(args)
        img = self.app.controller(instance, observe=True).screenshot()
        h, w = img.shape[:2]
        folder = self.app.cfg.runs_dir / "mcp-screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{instance}.png"
        cv2.imencode(".png", img)[1].tofile(str(path))
        max_w = int(args.get("max_width") or 1280)
        if w > max_w:
            img = cv2.resize(img, (max_w, round(h * max_w / w)), interpolation=cv2.INTER_AREA)
        b64 = base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode("ascii")
        return _result({"instance": instance, "size": [w, h], "saved": str(path)}, images=[b64])

    # -------------------------------------------------------------- workflows
    def t_list_workflows(self, args, session):
        out = []
        for name in self.app.workflows():
            try:
                wf = self.app.supervisor.load(name)
                out.append({"name": name, "title": wf.title, "states": len(wf.states), "params": wf.param_defaults(),
                            "requires": wf.requires})
            except Exception as e:  # noqa: BLE001
                out.append({"name": name, "error": str(e)})
        return _result({"workflows": out})

    def t_marathon_start(self, args, session):
        instance = self._instance(args)
        if args.get("preview"):
            return _result(self.app.plans.preview(instance, args.get("plan")))
        return _result(self.app.plans.start(instance, args.get("plan"), args.get("rounds", 1),
                                            args.get("hours"), args.get("out")))

    def t_marathon_status(self, args, session):
        return _result(self.app.plans.status())

    def t_marathon_stop(self, args, session):
        return _result(self.app.plans.stop(self._instance(args), args.get("mode", "immediate")))

    def t_validate_workflow(self, args, session):
        from .supervisor.replay import load_cases, run_cases
        wf = self._workflow(args)
        results = run_cases(wf, load_cases(self.app.ws.path / "tests" / wf.name))
        bad = [r for r in results if not r.ok]
        return _result({"workflow": wf.name, "format": "ok", "states": len(wf.states), "resources": len(wf.resources),
                        "replay": {"passed": len(results) - len(bad), "total": len(results),
                                   "failed": [{"case": r.case, "expected": r.expected, "got": r.got} for r in bad]},
                        "coverage": "insufficient" if not results else "sampled",
                        "ok": bool(results) and not bad})

    def _start_job(self, wf, instance: str, mode: str, params: dict, seconds=None, actions=None,
                   repair: bool = True) -> dict:
        sup = self.app.supervisor
        try:
            validated = wf.validate_params(params)
        except Exception as e:
            raise ToolError(str(e)) from e
        scfg = self.app.cfg["supervisor"]
        seconds = float(seconds or scfg.get("observe_seconds", 60)) if mode == "observe" else None
        actions = int(actions or scfg.get("trial_actions", 30)) if mode == "trial" else None
        with self.lock:
            cur = self.jobs.get(instance)
            if cur and cur["status"] == "running":
                raise ToolError(f"实例 {instance} 正在运行 {cur['workflow']}，先 stop_workflow 或等它结束")
            job = {"workflow": wf.name, "instance": instance, "mode": mode, "params": validated,
                   "status": "running", "started": time.time(), "done": threading.Event()}
            self.jobs[instance] = job
        self.app.store.event("info", "mcp", f"MCP 启动 {wf.name}@{instance}（{mode}）")

        def work():
            try:
                if mode == "run":
                    out = sup.run(wf.name, instance, validated, repair=repair)
                    job.update(summary=out.result.summary(), notes=list(out.notes), level=out.level, ok=out.result.ok)
                else:
                    sup.stop_flags.setdefault(instance, threading.Event()).clear()
                    res = sup._run_once(wf, instance, validated, mode=mode,
                                        max_seconds=seconds, max_actions=actions, observe=mode == "observe")
                    job.update(summary=res.summary(), ok=res.ok)
                job["status"] = "finished"
            except Exception as e:  # noqa: BLE001
                logger.exception("MCP run failed")
                job.update(status="error", error=str(e), ok=False)
                self.app.store.event("error", "mcp", f"{wf.name}@{instance} 出错：{e}")
            finally:
                job["ended"] = time.time()
                job["done"].set()

        threading.Thread(target=work, daemon=True, name=f"mcp-run-{instance}").start()
        return job

    @staticmethod
    def _job_view(job: dict) -> dict:
        return {k: v for k, v in job.items() if k != "done"}

    def t_run_workflow(self, args, session):
        wf = self._workflow(args)
        instance = self._instance(args)
        mode = args.get("mode") or "run"
        if mode not in ("run", "observe", "trial"):
            raise ToolError("mode 只能是 run、observe 或 trial")
        job = self._start_job(wf, instance, mode, dict(args.get("params") or {}), args.get("seconds"),
                              args.get("actions"), bool(args.get("repair", True)))
        wait = min(float(args.get("wait_seconds") or 0), MAX_WAIT_S)
        if wait > 0:
            job["done"].wait(wait)
        view = self._job_view(job)
        if job["status"] == "running":
            view["hint"] = "还在运行。用 status 查看进度，遇到敏感操作会出现在 list_pending 里等用户批准。"
        return _result(view)

    def t_stop_workflow(self, args, session):
        return _result(self.app.plans.stop(self._instance(args), args.get("mode", "immediate")))

    def t_observe(self, args, session):
        wf = self._workflow(args)
        instance = self._instance(args)
        seconds = min(float(args.get("seconds") or self.app.cfg["supervisor"].get("observe_seconds", 60)), MAX_WAIT_S)
        job = self._start_job(wf, instance, "observe", {}, seconds=seconds)
        job["done"].wait(seconds + 60)
        return _result(self._job_view(job))

    # -------------------------------------------------------------- status / logs
    def _pending(self) -> dict:
        conf = [{"kind": "confirmation", "id": c["id"], "category": c["category"], "detail": c["detail"],
                 "instance": c["instance"], "created": c["created"]} for c in self.app.broker.pending()]
        changes = []
        for ch in self.app.store.query("SELECT * FROM changes WHERE status='waiting_user' ORDER BY id"):
            try:
                validation = json.loads(ch["validation"] or "null")
            except (TypeError, ValueError):
                validation = ch["validation"]
            changes.append({"kind": "change", "id": ch["id"], "workflow": ch["workflow"], "change_kind": ch["kind"],
                            "note": ch["note"], "branch": ch["branch"], "validation": validation,
                            "created": ch["created"]})
        return {"confirmations": conf, "changes": changes}

    def t_status(self, args, session):
        app = self.app
        n = int(args.get("n") or 10)
        last_sync = (app.sync.history(1) or [None])[0]
        out = {
            "version": __version__,
            "jobs": [self._job_view(j) for j in self.jobs.values()],
            "recent_runs": app.store.recent_runs(limit=n, mode=None),
            "pending": self._pending(),
            "recent_changes": app.store.query(
                "SELECT id, workflow, kind, status, note FROM changes ORDER BY id DESC LIMIT ?", (n,)),
            "sync": {"running": app.sync.lock.locked(), "last": last_sync,
                     "job": self.sync_job and {k: v for k, v in self.sync_job.items() if k != "thread"}},
            "llm": app.llm.budget.snapshot() if app.llm else "没有启用大模型供应商",
            "marathons": [{k: v for k, v in j.items() if k not in ("marathon", "plan")} for j in self.marathon_jobs.values()],
            "tasks": app.ledger.snapshot(),
            "devices": {name: app.supervisor.runtime_status(name) for name in app.instance_names()},
            "resources": app.store.resource_totals(app.ledger.account, app.ledger.periods()[0]),
            "agent_handoffs": app.handoffs.list(n),
        }
        return _result(out)

    def t_logs(self, args, session):
        if args.get("run_id"):
            rows = self.app.store.query("SELECT * FROM runs WHERE id=?", (int(args["run_id"]),))
            if not rows:
                raise ToolError(f"没有运行记录 #{args['run_id']}")
            row = dict(rows[0])
            try:
                row["summary"] = json.loads(row.get("summary") or "null")
            except (TypeError, ValueError):
                pass
            return _result(row)
        n = int(args.get("n") or 50)
        level, source = args.get("level"), args.get("source")
        sql, params = "SELECT * FROM events", []
        cond = []
        if level:
            cond.append("level=?")
            params.append(level)
        if source:
            cond.append("source=?")
            params.append(source)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(n)
        rows = self.app.store.query(sql, tuple(params))
        for r in rows:
            r["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"]))
        return _result({"events": rows})

    def t_diagnose(self, args, session):
        import cv2
        import numpy as np

        from .workflow.engine import Runner
        wf = self._workflow(args)
        if args.get("image_path"):
            p = Path(args["image_path"])
            if not p.is_file():
                raise ToolError(f"找不到截图文件 {p}")
            img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ToolError(f"{p} 不是能读的图片")
            source = str(p)
        else:
            instance = self._instance(args)
            img = self.app.controller(instance, observe=True).screenshot()
            source = f"实例 {instance} 当前画面"

        class _O:
            observe = True

            def sleep(self, s):
                pass
        rows = Runner(wf, _O()).diagnose_frame(img)
        return _result({"workflow": wf.name, "source": source,
                        "matched": [r["id"] for r in rows if r.get("match")], "states": rows})

    # -------------------------------------------------------------- sync
    def t_sync(self, args, session):
        app = self.app
        action = args.get("action") or "run"
        if action == "status":
            return _result({"running": app.sync.lock.locked(), "history": app.sync.history(int(args.get("n") or 10))})
        if action == "show":
            s = app.sync.get(int(args["id"])) if args.get("id") else (app.sync.history(1) or [None])[0]
            if not s or not s.get("report_path") or not Path(s["report_path"]).is_file():
                raise ToolError("没有这次同步的报告")
            return _result({"sync": s["id"], "status": s["status"],
                            "report": _clip(Path(s["report_path"]).read_text(encoding="utf-8"))})
        if action == "check":
            from .sync import remote_head
            prev = (app.sync.last_processed() or {}).get("upstream") or {}
            out = {}
            for name, spec in (app.cfg["upstream"].get("sources") or {}).items():
                head, url = remote_head(spec)
                old = (prev.get(name) or {}).get("commit")
                out[name] = {"state": "拉不到" if not head else ("没有更新" if head == old else "有更新"),
                             "upstream": head, "last": old, "url": url}
            return _result(out)
        if action not in ("run", "force"):
            raise ToolError("action 只能是 run、force、check、status 或 show")
        if app.sync.lock.locked():
            raise ToolError("已经有一次同步在进行，用 sync action=status 查看")
        job = {"action": action, "status": "running", "started": time.time()}
        only = args.get("only") or None
        validate_on = args.get("validate_on") or None
        if validate_on:
            app.cfg.instance(validate_on)

        def work():
            try:
                r = app.sync.sync(force=action == "force", only=only, instance=validate_on,
                                  translate=not args.get("no_translate"), fetch=not args.get("offline"),
                                  trigger="mcp")
                job.update(status="finished", sync_id=r.id, result=r.status, message=r.message,
                           report=r.report_path)
            except Exception as e:  # noqa: BLE001
                logger.exception("sync from MCP failed")
                job.update(status="error", error=str(e))
                app.store.event("error", "sync", f"同步出错：{e}")
            finally:
                job["ended"] = time.time()
        self.sync_job = job
        threading.Thread(target=work, daemon=True, name="mcp-sync").start()
        return _result({"message": "已开始同步，拉取和转换要几分钟。用 sync action=status 或 status 查看结果，"
                                   "要用户批准的改动会出现在 list_pending。", **job})

    def t_upstream_programs(self, args, session):
        action = args.get("action", "list")
        programs = self.app.programs
        if action == "list":
            rows = programs.list(args.get("source"), args.get("status"))
            offset, limit = args.get("offset", 0), args.get("limit", 30)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise ToolError("list 使用非负 offset 和 1–100 的 limit")
            end = min(len(rows), offset + limit)
            return _result({"programs": rows[offset:end], "total": len(rows), "complete": end >= len(rows),
                            "next_offset": end if end < len(rows) else None, "job": self.program_job})
        if action == "source":
            return _result(programs.source(args["id"], args.get("path"), args.get("offset", 0), args.get("chars", 12000)))
        if action == "propose":
            return _result(programs.propose(args["id"], args["proposal"]))
        if action != "compile":
            raise ToolError("未知的脚本转换操作")
        with self.lock:
            if self.program_job and self.program_job["status"] == "running":
                raise ToolError("脚本转换已在进行，使用 list 查看进度")
            job = self.program_job = {"status": "running", "started": time.time()}
        def work():
            try:
                job.update(result=programs.compile(args.get("id"), args.get("limit"), args.get("retry", False)), status="finished")
            except Exception as error:
                job.update(status="error", error=str(error))
            finally:
                job["ended"] = time.time()
        threading.Thread(target=work, daemon=True, name="program-compiler").start()
        return _result({"message": "已开始处理转换队列；候选等待用户审核", **job})

    def t_agent_handoffs(self, args, session):
        action = args.get("action", "list")
        if action == "list":
            return _result({"handoffs": self.app.handoffs.list(), "job": self.handoff_job})
        if action == "show":
            return _result(self.app.handoffs.get(args["id"]))
        if action not in ("diagnose", "propose"):
            raise ToolError("未知的 agent 接管操作")
        if action == "propose" and not args.get("proposal"):
            raise ToolError("propose 需要修复提案 proposal")
        with self.lock:
            if self.handoff_job and self.handoff_job["status"] == "running":
                raise ToolError("agent 正在处理接管任务")
            job = self.handoff_job = {"id": args["id"], "status": "running", "started": time.time()}
        def work():
            try:
                result = self.app.handoffs.diagnose(args["id"], args.get("proposal"))
                job.update(status="finished", result=result)
            except Exception as error:
                job.update(status="error", error=str(error))
            finally:
                job["ended"] = time.time()
        threading.Thread(target=work, daemon=True, name="agent-handoff").start()
        return _result({"message": "agent 已开始诊断，计划保持暂停", **job})

    # -------------------------------------------------------------- approvals
    def t_list_pending(self, args, session):
        p = self._pending()
        p["how_to_approve"] = ("用 approve 请用户批准（支持的客户端会直接问用户），或请用户在网页面板 / 终端里批准；"
                               "用 reject 拒绝。")
        return _result(p)

    def _item(self, kind: str, cid: int) -> tuple[dict, str, list[str]]:
        if kind == "confirmation":
            rows = self.app.store.query("SELECT * FROM confirmations WHERE id=?", (cid,))
            if not rows:
                raise ToolError(f"没有确认项 #{cid}")
            row = rows[0]
            if row["status"] != "pending":
                raise ToolError(f"确认项 #{cid} 已经是 {row['status']}，不用再处理")
            return row, f"敏感操作确认 #{cid}", [f"类别：{row['category']}", f"内容：{row['detail']}",
                                                  f"实例：{row['instance'] or '-'}"]
        if kind == "change":
            rows = self.app.store.query("SELECT * FROM changes WHERE id=?", (cid,))
            if not rows:
                raise ToolError(f"没有改动 #{cid}")
            row = rows[0]
            if row["status"] != "waiting_user":
                raise ToolError(f"改动 #{cid} 现在是 {row['status']}，不在等待批准")
            return row, f"合并改动 #{cid}（会改识别数据或工作流）", [
                f"工作流：{row['workflow']}", f"类型：{row['kind']}", f"说明：{row['note']}",
                f"分支：{row['branch']}", f"验证：{_clip(str(row['validation'] or '-'), 1500)}"]
        raise ToolError("kind 只能是 confirmation 或 change")

    def t_approve(self, args, session):
        kind, cid = args.get("kind"), int(args.get("id"))
        _row, title, lines = self._item(kind, cid)
        verdict, note = self._ask_person(session, title, lines)
        app = self.app
        if verdict == "approved":
            # the item may have been answered elsewhere while the person was looking at the question
            if kind == "confirmation":
                if not app.broker.decide(cid, True):
                    raise ToolError(f"确认项 #{cid} 在你回答前已经被处理了（{app.broker.status(cid)}）")
                app.store.event("info", "mcp", f"用户在 MCP 客户端里批准了确认项 #{cid}")
                return _result({"approved": True, "kind": kind, "id": cid, "note": note})
            commit = app.supervisor.approve_change(cid)
            app.store.event("info", "mcp", f"用户在 MCP 客户端里批准了改动 #{cid}")
            return _result({"approved": True, "kind": kind, "id": cid, "merged_commit": commit, "note": note})
        if verdict == "denied":
            if kind == "confirmation":
                app.broker.decide(cid, False)
            else:
                app.supervisor.reject_change(cid)
            app.store.event("info", "mcp", f"用户在 MCP 客户端里拒绝了 {kind} #{cid}")
            return _result({"approved": False, "denied": True, "kind": kind, "id": cid, "note": note})
        return _result({"approved": False, "needs_user": True, "kind": kind, "id": cid, "reason": note,
                        "what": [title, *lines], "user_can_approve_with": self._how_to_approve(kind, cid),
                        "message": "没有批准。请把上面的内容告诉用户，由用户自己决定，不要替用户执行批准命令。"})

    def t_reject(self, args, session):
        kind, cid = args.get("kind"), int(args.get("id"))
        self._item(kind, cid)
        if kind == "confirmation":
            self.app.broker.decide(cid, False)
        else:
            self.app.supervisor.reject_change(cid)
        self.app.store.event("info", "mcp", f"MCP 拒绝了 {kind} #{cid}")
        return _result({"rejected": True, "kind": kind, "id": cid})

    def t_rollback(self, args, session):
        target = args.get("target")
        if target == "sync":
            commit = self.app.sync.rollback(int(args["id"]) if args.get("id") else None)
            return _result({"rolled_back": "sync", "commit": commit,
                            "note": "同样的上游提交以后会跳过，要重新套用：sync action=force"})
        if target == "change":
            if not args.get("id"):
                raise ToolError("回滚改动要写 id")
            commit = self.app.supervisor.rollback_change(int(args["id"]))
            return _result({"rolled_back": "change", "id": int(args["id"]), "commit": commit})
        raise ToolError("target 只能是 sync 或 change")

    # -------------------------------------------------------------- config
    def t_get_config(self, args, session):
        path = (args.get("path") or "").strip()
        data = self.app.cfg.data
        value = get_path(data, path) if path else data
        out = {"path": path or "(全部)", "value": value, "file": str(self.app.cfg.path)}
        if not path or path.startswith("llm"):
            out["api_keys_saved"] = {p.get("name"): credentials.has_key(p.get("name"))
                                     for p in data["llm"].get("providers") or [] if isinstance(p, dict)}
        return _result(out)

    def t_set_config(self, args, session):
        path = (args.get("path") or "").strip()
        if "value" not in args:
            raise ToolError("要写 value（null 表示清空 / 不限）")
        value = args["value"]
        validate_setting(path, value)
        cfg = self.app.cfg
        why = needs_approval(path, value, cfg.data, has_key=credentials.has_key)
        if why:
            try:
                old = get_path(cfg.data, path)
            except KeyError:
                old = None
            lines = [f"设置：{path}", f"原来：{_dumps(old)}", f"改成：{_dumps(value)}", f"原因：{why}"]
            verdict, note = self._ask_person(session, "修改安全相关设置", lines)
            if verdict != "approved":
                return _result({"changed": False, "needs_user": verdict != "denied", "denied": verdict == "denied",
                                "reason": note, "what": lines,
                                "user_can_change_with": [f"终端：oaf config set {path} '{json.dumps(value, ensure_ascii=False)}'",
                                                         f"或者编辑 {cfg.path}"]})
        old = set_path(cfg.data, path, value)
        cfg.save()
        self.app.refresh_llm()
        self.app.store.event("info", "mcp", f"MCP 修改配置 {path}")
        return _result({"changed": True, "path": path, "old": old, "new": get_path(cfg.data, path),
                        "approved_by_user": bool(why)})


# ------------------------------------------------------------------------------------ protocol

class MCPServer:
    def __init__(self, app, panel_url: str | None = None):
        self.app = app
        self.tools = AgentTools(app, panel_url)

    def handle(self, msg: dict, session: Session) -> dict | None:
        """Handle one JSON-RPC request or notification; returns the response (None for notifications)."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            return {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                    "error": {"code": -32600, "message": "Invalid Request"}}
        method, mid = msg["method"], msg.get("id")
        params = msg.get("params") or {}
        if mid is None:                       # notification
            return None
        session.last_seen = time.time()
        try:
            result = self._dispatch(method, params, session)
        except _RpcError as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": e.code, "message": e.message}}
        except Exception as e:  # noqa: BLE001
            logger.exception("MCP %s failed", method)
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _dispatch(self, method: str, params: dict, session: Session) -> dict:
        if method == "initialize":
            want = str(params.get("protocolVersion") or "")
            session.protocol = want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            session.capabilities = params.get("capabilities") or {}
            session.client = params.get("clientInfo") or {}
            logger.info("MCP client %s %s (protocol %s, elicitation %s)", session.client.get("name"),
                        session.client.get("version"), session.protocol, session.can_elicit())
            return {"protocolVersion": session.protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "title": "阴阳师 Agent 工作流", "version": __version__},
                    "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools.list()}
        if method == "tools/call":
            name = params.get("name")
            if name not in self.tools.by_name:
                raise _RpcError(-32602, f"Unknown tool: {name}")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                raise _RpcError(-32602, "arguments must be an object")
            return self.tools.call(name, args, session)
        if method in ("resources/list", "resources/templates/list", "prompts/list"):
            key = {"resources/list": "resources", "resources/templates/list": "resourceTemplates",
                   "prompts/list": "prompts"}[method]
            return {key: []}
        raise _RpcError(-32601, f"Method not found: {method}")


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# ------------------------------------------------------------------------------------ stdio

def serve_stdio(server: MCPServer, inp=None, out=None, workers: int = 8) -> None:
    """MCP over stdio: one JSON-RPC message per line. Tool calls run on worker threads so the
    reader can deliver the client's answers to our own requests (elicitation) meanwhile."""
    inp = inp or sys.stdin.buffer
    out = out or sys.stdout.buffer
    write_lock = threading.Lock()
    pending: dict[str, dict] = {}
    counter = itertools.count(1)
    schedule_stop = threading.Event()
    schedule_thread = None
    if (server.tools.app.cfg["upstream"].get("schedule") or {}).get("enabled"):
        from .sync import schedule_loop
        schedule_thread = threading.Thread(target=schedule_loop, args=(server.tools.app.sync, schedule_stop),
                                           daemon=True, name="mcp-sync-schedule")
        schedule_thread.start()

    def send(obj):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8") + b"\n"
        with write_lock:
            out.write(data)
            out.flush()

    def request(method, params, timeout):
        rid = f"oaf-{next(counter)}"
        slot = {"event": threading.Event()}
        pending[rid] = slot
        send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        if not slot["event"].wait(timeout):
            pending.pop(rid, None)
            raise TimeoutError(f"{int(timeout)} 秒内没有回答")
        pending.pop(rid, None)
        if "error" in slot:
            raise RuntimeError((slot["error"] or {}).get("message") or "客户端返回错误")
        if slot.get("closed"):
            raise RuntimeError("连接已断开")
        return slot.get("result") or {}

    session = Session(requester=request)
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mcp")

    def run(m):
        try:
            resp = server.handle(m, session)
            if resp is not None:
                send(resp)
        except Exception:  # noqa: BLE001
            logger.exception("MCP message failed")

    try:
        for raw in inp:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                continue
            for m in msg if isinstance(msg, list) else [msg]:
                if isinstance(m, dict) and "method" not in m and "id" in m:      # answer to our request
                    slot = pending.get(str(m.get("id")))
                    if slot is not None:
                        if "error" in m:
                            slot["error"] = m["error"]
                        slot["result"] = m.get("result")
                        slot["event"].set()
                    continue
                if isinstance(m, dict) and m.get("method") in ("initialize", "ping") or (
                        isinstance(m, dict) and "id" not in m):
                    run(m)                    # quick; keeps initialize ordered before anything else
                else:
                    pool.submit(run, m)
    finally:
        schedule_stop.set()
        for slot in list(pending.values()):
            slot["closed"] = True
            slot["event"].set()
        pool.shutdown(wait=True)            # answer what was already asked before the client closed


# ------------------------------------------------------------------------------------ HTTP

def make_http_handler(server: MCPServer, token: str | None = None, path: str = "/mcp"):
    sessions: dict[str, Session] = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            logger.debug("mcp http: " + fmt, *args)

        def _send(self, code: int, body=None, headers: dict | None = None):
            data = b"" if body is None else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            if body is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if data:
                self.wfile.write(data)

        def _guard(self) -> bool:
            """Only local clients: Host and Origin must be loopback (DNS rebinding), token when set."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") \
                else (self.headers.get("Host") or "").split("]")[0] + "]"
            if host and not _loopback(host):
                self._send(403, {"error": "只接受本机访问"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "null" and not _loopback(urlparse(origin).hostname or ""):
                self._send(403, {"error": "不接受网页跨站访问"})
                return False
            if origin == "null":
                self._send(403, {"error": "不接受网页跨站访问"})
                return False
            if token and not secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}"):
                self._send(401, {"error": "需要 Authorization: Bearer <token>"})
                return False
            if urlparse(self.path).path != path:
                self._send(404, {"error": f"MCP 地址是 {path}"})
                return False
            return True

        def do_GET(self):
            if self._guard():
                self._send(405, {"error": "这个服务不提供 SSE 流，请用 POST"}, {"Allow": "POST, DELETE"})

        def do_DELETE(self):
            if self._guard():
                with lock:
                    sessions.pop(self.headers.get("Mcp-Session-Id", ""), None)
                self._send(200, {})

        def do_POST(self):
            if not self._guard():
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > 4 * 1024 * 1024:
                    self._send(413, {"error": "请求太大"})
                    return
                msg = json.loads(self.rfile.read(length) or b"null")
            except (ValueError, UnicodeDecodeError):
                self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                return
            msgs = msg if isinstance(msg, list) else [msg]
            sid = self.headers.get("Mcp-Session-Id")
            is_init = any(isinstance(m, dict) and m.get("method") == "initialize" for m in msgs)
            with lock:
                if is_init:
                    session = Session()
                    sessions[session.id] = session
                    if len(sessions) > 64:        # forget the oldest idle sessions
                        for old in sorted(sessions.values(), key=lambda s: s.last_seen)[:len(sessions) - 64]:
                            sessions.pop(old.id, None)
                elif sid:
                    session = sessions.get(sid)
                    if session is None:
                        self._send(404, {"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32001, "message": "Session not found, initialize again"}})
                        return
                else:
                    session = Session()           # client that does not keep sessions
            responses = [r for r in (server.handle(m, session) for m in msgs
                                     if isinstance(m, dict) and "method" in m) if r is not None]
            headers = {"Mcp-Session-Id": session.id} if is_init else {}
            if not responses:
                self._send(202, None, headers)
            else:
                self._send(200, responses if isinstance(msg, list) else responses[0], headers)

    return Handler


def make_http_server(server: MCPServer, host: str = "127.0.0.1", port: int = 8766, token: str | None = None):
    if not _loopback(host):
        raise AgentflowError(f"MCP 的 HTTP 服务只能监听本机地址（127.0.0.1、localhost、::1），不能用 {host}")
    import socket

    class _Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6 if ":" in host else socket.AF_INET

        def handle_error(self, request, client_address):
            if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError, TimeoutError)):
                return                     # the client hung up; nothing to report
            super().handle_error(request, client_address)
    cls = _Server
    httpd = cls((host.strip("[]"), port), make_http_handler(server, token))
    httpd.daemon_threads = True
    return httpd


def serve_http(server: MCPServer, host: str, port: int, token: str | None = None) -> None:
    httpd = make_http_server(server, host, port, token)
    schedule_stop = threading.Event()
    if (server.app.cfg["upstream"].get("schedule") or {}).get("enabled"):
        from .sync import schedule_loop
        threading.Thread(target=schedule_loop, args=(server.app.sync, schedule_stop),
                         daemon=True, name="mcp-http-sync-schedule").start()
    real_port = httpd.server_address[1]
    shown = f"[{host.strip('[]')}]" if ":" in host else host
    print(f"MCP 服务已启动：http://{shown}:{real_port}/mcp  （只接受本机访问，Ctrl+C 退出）", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        schedule_stop.set()
        httpd.server_close()
