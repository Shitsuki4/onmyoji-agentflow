"""Command line interface: ``oaf <command>``."""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from . import __version__
from .log import setup_logging


def _app(args, interactive=False):
    from .app import App
    return App(args.home, interactive=interactive)


def cmd_init(args):
    from .config import Config
    from .supervisor import Workspace
    cfg = Config(args.home)
    if not cfg.path.exists():
        cfg.save()
        print(f"已生成配置：{cfg.path}")
    else:
        print(f"配置已存在：{cfg.path}")
    Workspace(cfg.workspace).ensure()
    print(f"工作区（git 仓库）：{cfg.workspace}")
    return 0


def cmd_devices(args):
    from .device import discover, find_mumu_roots
    roots = find_mumu_roots(args.mumu_root)
    if not roots:
        print("没找到 MuMu 12 安装目录，可以用 --mumu-root 指定")
    for r in roots:
        print(f"MuMu 12: {r}")
    for inst in discover(args.mumu_root):
        print(f"  实例 {inst.instance_id}: {inst.name}  {inst.serial}")
    return 0


def _parse_params(items):
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def cmd_list(args):
    app = _app(args)
    for name in app.workflows():
        wf = app.supervisor.load(name)
        params = ", ".join(f"{k}={v}" for k, v in wf.param_defaults().items())
        print(f"{name:14s} {wf.title}  ({params})")
    return 0


def cmd_validate(args):
    from .supervisor.replay import load_cases, run_cases
    from .workflow.schema import load_workflow
    p = Path(args.workflow)
    if p.exists():
        wf = load_workflow(p)
        cases_dir = p.parent.parent / "tests" / wf.name
    else:
        app = _app(args)
        wf = app.supervisor.load(args.workflow)
        cases_dir = app.ws.path / "tests" / wf.name
    print(f"格式正确：{wf.name}，{len(wf.states)} 个状态，{len(wf.resources)} 个资源")
    results = run_cases(wf, load_cases(cases_dir))
    bad = [r for r in results if not r.ok]
    print(f"回放测试：{len(results) - len(bad)}/{len(results)} 通过")
    for r in bad:
        print(f"  {r.case}: 期望 {r.expected}，实际 {r.got}")
    return 1 if bad else 0


def cmd_run(args):
    app = _app(args, interactive=True)
    params = _parse_params(args.param)
    if args.observe or args.trial:
        wf = app.supervisor.load(args.workflow)
        res = app.supervisor._run_once(
            wf, args.instance, {**wf.param_defaults(), **params}, mode="observe" if args.observe else "trial",
            max_seconds=args.seconds if args.observe else None,
            max_actions=args.trial if args.trial else None, observe=args.observe)
        print(json.dumps(res.summary(), ensure_ascii=False, indent=2, default=str))
        return 0 if res.ok else 1
    out = app.supervisor.run(args.workflow, args.instance, params, repair=not args.no_repair)
    print(json.dumps(out.result.summary(), ensure_ascii=False, indent=2, default=str))
    for n in out.notes:
        print("-", n)
    return 0 if out.result.ok else 1


def cmd_diagnose(args):
    import cv2
    import numpy as np

    from .workflow.engine import Runner
    app = _app(args)
    wf = app.supervisor.load(args.workflow)
    if args.image:
        img = cv2.imdecode(np.fromfile(args.image, np.uint8), cv2.IMREAD_COLOR)
    else:
        img = app.controller(args.instance, observe=True).screenshot()
    class _O:
        observe = True

        def sleep(self, s):
            pass
    for row in Runner(wf, _O()).diagnose_frame(img):
        mark = "✓" if row["match"] else " "
        extra = f" score={row['score']}" if "score" in row else ""
        extra += f" error={row['error']}" if "error" in row else ""
        print(f"[{mark}] {row['id']}{extra}")
    return 0


def cmd_screenshot(args):
    import cv2
    app = _app(args)
    img = app.controller(args.instance, observe=True).screenshot()
    cv2.imencode(".png", img)[1].tofile(args.output)
    print(f"已保存 {args.output}  {img.shape[1]}x{img.shape[0]}")
    return 0


def cmd_convert(args):
    if args.all:
        local = args.path or args.source
        return _run_sync(args, fetch=not local, local=local, force=True, only=None)
    if args.source not in ("oas", "assttyys", "mvp") or not args.path or not args.out:
        print("用法：oaf convert {oas,assttyys,mvp} <上游仓库目录> <输出目录>，或 oaf convert --all [本地目录]",
              file=sys.stderr)
        return 2
    if args.source == "oas":
        from .convert import oas
        r = oas.convert(args.path, args.out, args.task or None)
        n = sum(t["resources"] for t in r["tasks"].values())
        print(f"OAS：{len(r['tasks'])} 个任务，{n} 个资源，导航 {r['navigation']}")
    elif args.source == "assttyys":
        from .convert import assttyys
        r = assttyys.convert(args.path, args.out)
        print(f"assttyys：{r['colors']} 个比色资源，{r['funcs']} 个功能，"
              f"{len(r['needs_translation'])} 个含自定义逻辑（需要翻译），{r['schemes']} 个方案")
    elif args.source == "mvp":
        from .convert.build_mvp import build_all
        for p in build_all(args.path, args.out):
            print(f"已生成 {p}")
    return 0


def cmd_key(args):
    from . import credentials
    if args.action == "set":
        secret = getpass.getpass(f"输入 {args.name} 的 API key（不显示）：")
        if not secret.strip():
            print("没有输入，取消")
            return 1
        credentials.set_key(args.name, secret.strip())
        print(f"已保存到系统凭据管理器（{credentials.SERVICE} / llm:{args.name}）")
    elif args.action == "delete":
        print("已删除" if credentials.delete_key(args.name) else "没有找到")
    else:
        print("已保存" if credentials.has_key(args.name) else "未保存")
    return 0


def cmd_status(args):
    app = _app(args)
    for r in app.store.recent_runs(limit=args.n, mode=None):
        print(f"#{r['id']} {r['workflow']}@{r['instance']} {r['mode']} {r['status']} {r['failure_kind'] or ''} {r['reason']}")
    if app.llm:
        snap = app.llm.budget.snapshot()
        print(f"大模型今日 {snap['day']['tokens']} token / {snap['day']['calls']} 次，30 天 {snap['month']['tokens']} token")
    pend = app.broker.pending()
    for c in pend:
        print(f"待确认 #{c['id']}: {c['category']} - {c['detail']}")
    for ch in app.store.query("SELECT * FROM changes ORDER BY id DESC LIMIT 10"):
        print(f"改动 #{ch['id']} {ch['workflow']} {ch['kind']} {ch['status']} {ch['branch']}")
    return 0


def cmd_confirm(args):
    app = _app(args)
    ok = app.broker.decide(args.id, args.answer == "yes")
    print("已记录" if ok else "没有这个待确认项")
    return 0 if ok else 1


def cmd_approve(args):
    app = _app(args)
    commit = app.supervisor.approve_change(args.id)
    print(f"已合并，提交 {commit[:8]}")
    return 0


def _print_sync(r) -> None:
    print(f"同步 #{r.id}：{r.status} - {r.message}")
    d = r.details or {}
    for name, u in (d.get("upstream") or {}).items():
        if isinstance(u, dict):
            print(f"  {name}: {u.get('commit', '')[:12]} {u.get('url', '')}")
    diff = d.get("diff")
    if diff:
        f = diff["files"]
        print(f"  差异：新增 {len(f['added'])}，删除 {len(f['removed'])}，修改 {len(f['modified'])} 个文件")
    if d.get("affected"):
        print(f"  影响工作流：{'、'.join(d['affected'])}")
    for e in d.get("errors") or []:
        print(f"  错误：{e}")
    if r.report_path:
        print(f"  报告：{r.report_path}")


def _run_sync(args, fetch=True, local=None, force=False, only=None):
    app = _app(args)
    r = app.sync.sync(force=force, only=only, local=local, instance=getattr(args, "validate_on", None),
                      translate=not getattr(args, "no_translate", False), fetch=fetch)
    _print_sync(r)
    return 1 if r.status in ("failed", "broken") else 0


def cmd_sync(args):
    action = args.action or "run"
    if action == "run":
        if args.loop:
            import threading
            from .sync import schedule_loop
            app = _app(args)
            if not (app.cfg["upstream"].get("schedule") or {}).get("enabled"):
                print("config.yaml 里 upstream.schedule.enabled 没打开，--loop 按 interval_hours 定时同步", file=sys.stderr)
                app.cfg["upstream"].setdefault("schedule", {})["enabled"] = True
            print(f"定时同步：每 {app.cfg['upstream']['schedule'].get('interval_hours', 24)} 小时一次，Ctrl+C 退出")
            schedule_loop(app.sync, threading.Event())
            return 0
        return _run_sync(args, fetch=not args.offline, local=args.source_dir, force=args.force, only=args.only)
    app = _app(args)
    if action == "check":
        from .sync import remote_head
        last = app.sync.last_processed()
        prev = (last or {}).get("upstream") or {}
        for name, spec in (app.cfg["upstream"].get("sources") or {}).items():
            head, url = remote_head(spec)
            old = (prev.get(name) or {}).get("commit")
            state = "拉不到" if not head else ("没有更新" if head == old else "有更新")
            print(f"{name}: {state}  上游 {head[:12] if head else '-'}  上次 {old[:12] if old else '-'}  {url or ''}")
        return 0
    if action == "status":
        rows = app.sync.history(args.n)
        if not rows:
            print("还没有同步过，运行 oaf sync")
        import time as _t
        for s in rows:
            up = "，".join(f"{k} {v.get('commit', '')[:7]}" for k, v in (s["upstream"] or {}).items()
                          if isinstance(v, dict))
            print(f"#{s['id']} {_t.strftime('%m-%d %H:%M', _t.localtime(s['started']))} {s['status']:<14} "
                  f"{up}  改动 {s['change_ids']}  {s['summary'] or ''}")
        return 0
    if action == "show":
        s = app.sync.get(args.id) if args.id else (app.sync.history(1) or [None])[0]
        if not s or not s.get("report_path"):
            print("没有这次同步的报告")
            return 1
        print(Path(s["report_path"]).read_text(encoding="utf-8"))
        return 0
    if action == "rollback":
        commit = app.sync.rollback(args.id)
        print(f"已回滚到上一版转换结果，提交 {commit[:8]}。同样的上游提交以后会跳过，要重新套用：oaf sync --force")
        return 0
    return 2


def cmd_web(args):
    from .web import serve
    app = _app(args)
    host = args.host or app.cfg["web"]["host"]
    port = args.port or app.cfg["web"]["port"]
    serve(app, host, port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="oaf", description="阴阳师 YAML 工作流引擎 + Agent 自动监管")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--home", help="数据目录（默认 %%LOCALAPPDATA%%\\onmyoji-agentflow）")
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="生成配置和工作区").set_defaults(func=cmd_init)
    s = sub.add_parser("devices", help="查找 MuMu 12 和它的多开实例")
    s.add_argument("--mumu-root")
    s.set_defaults(func=cmd_devices)
    sub.add_parser("list", help="列出工作流").set_defaults(func=cmd_list)
    s = sub.add_parser("validate", help="检查工作流格式并跑回放测试")
    s.add_argument("workflow")
    s.set_defaults(func=cmd_validate)
    s = sub.add_parser("run", help="运行工作流（带监管）")
    s.add_argument("workflow")
    s.add_argument("-i", "--instance", default=None)
    s.add_argument("-p", "--param", action="append", help="参数，如 -p max_runs=10")
    s.add_argument("--observe", action="store_true", help="观察模式：只识别不点击")
    s.add_argument("--seconds", type=float, default=60, help="观察模式时长")
    s.add_argument("--trial", type=int, default=0, help="限次试跑：最多执行这么多次操作")
    s.add_argument("--no-repair", action="store_true", help="失败时不自动修复")
    s.set_defaults(func=cmd_run)
    s = sub.add_parser("diagnose", help="看当前画面（或一张截图）匹配哪些状态")
    s.add_argument("workflow")
    s.add_argument("-i", "--instance", default=None)
    s.add_argument("--image")
    s.set_defaults(func=cmd_diagnose)
    s = sub.add_parser("screenshot", help="保存一张截图")
    s.add_argument("output")
    s.add_argument("-i", "--instance", default=None)
    s.set_defaults(func=cmd_screenshot)
    s = sub.add_parser("convert", help="从 OAS / assttyys 仓库转换识别数据")
    s.add_argument("source", nargs="?", help="oas / assttyys / mvp（--all 时可以直接写放两个仓库的目录）")
    s.add_argument("path", nargs="?", help="上游仓库根目录（mvp: assttyys 转换结果目录；--all: 放两个仓库的目录）")
    s.add_argument("out", nargs="?")
    s.add_argument("--task", action="append", help="只转换这些 OAS 任务")
    s.add_argument("--all", action="store_true",
                   help="拉取（或用本地目录里的）两个上游，全部转换进工作区，等同 oaf sync --force")
    s.add_argument("--validate-on", metavar="INSTANCE", help="验证时也在这个实例上跑观察模式和限次试跑")
    s.add_argument("--no-translate", action="store_true", help="这次不让大模型翻译新方案")
    s.set_defaults(func=cmd_convert)
    s = sub.add_parser("sync", help="自动拉取 assttyys / OAS 最新代码，转换、验证、合并或等你批准")
    s.add_argument("action", nargs="?", choices=["run", "check", "status", "show", "rollback"],
                   help="run（默认）拉取并转换；check 只看上游有没有更新；status 同步记录；"
                        "show 看报告；rollback 回到上一版转换结果")
    s.add_argument("id", nargs="?", type=int, help="show / rollback 的同步编号（默认最近一次）")
    s.add_argument("--force", action="store_true", help="上游没变也重新转换（也会重新套用回滚过的版本）")
    s.add_argument("--only", action="append", choices=["assttyys", "oas"], help="只同步这个上游")
    s.add_argument("--from", dest="source_dir", metavar="DIR", help="不联网，用本地已有的上游仓库")
    s.add_argument("--offline", action="store_true", help="不联网，用上次拉下来的缓存")
    s.add_argument("--validate-on", metavar="INSTANCE", help="验证时也在这个实例上跑观察模式和限次试跑")
    s.add_argument("--no-translate", action="store_true", help="这次不让大模型翻译新方案")
    s.add_argument("--loop", action="store_true", help="一直运行，按 upstream.schedule.interval_hours 定时同步")
    s.add_argument("-n", type=int, default=15, help="status 显示几条")
    s.set_defaults(func=cmd_sync)
    s = sub.add_parser("key", help="管理大模型 API key（Windows 凭据管理器）")
    s.add_argument("action", choices=["set", "delete", "check"])
    s.add_argument("name", help="供应商名，对应 config.yaml 里 llm.providers[].name")
    s.set_defaults(func=cmd_key)
    s = sub.add_parser("status", help="最近运行、待确认项、改动")
    s.add_argument("-n", type=int, default=15)
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("confirm", help="回答待确认项")
    s.add_argument("id", type=int)
    s.add_argument("answer", choices=["yes", "no"])
    s.set_defaults(func=cmd_confirm)
    s = sub.add_parser("approve", help="批准一个已通过验证、等你确认的改动")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_approve)
    s = sub.add_parser("web", help="启动本机网页面板")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(func=cmd_web)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    if getattr(args, "instance", "x") is None:
        from .config import Config
        args.instance = Config(args.home).instance(None).get("name") or "main"
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        from .errors import AgentflowError
        if isinstance(e, AgentflowError) or isinstance(e, (FileNotFoundError, KeyError)):
            print(f"错误：{e}", file=sys.stderr)
            return 2
        raise
