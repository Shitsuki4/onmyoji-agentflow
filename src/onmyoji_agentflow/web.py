"""Local web panel (standard library only). Binds to 127.0.0.1 by default.

Every POST must carry the per-process token in the ``X-OAF-Token`` header; the
page receives it when it is loaded, so other websites cannot drive the panel.
API keys are never shown or accepted here (use ``oaf key set``).
"""
from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .log import logger

PAGE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>onmyoji-agentflow</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#f6f6f4;color:#222}
header{background:#2d2a26;color:#fff;padding:10px 16px}main{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px}
section{background:#fff;border-radius:8px;padding:12px;box-shadow:0 1px 2px #0002}h2{font-size:15px;margin:0 0 8px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #eee;padding:4px;text-align:left}
button{margin:2px;padding:4px 10px}.warn{color:#b45309}.err{color:#b91c1c}.ok{color:#15803d}pre{white-space:pre-wrap;font-size:12px}
@media(max-width:900px){main{grid-template-columns:1fr}}</style></head><body>
<header>onmyoji-agentflow 本机面板</header><main>
<section><h2>运行</h2><div>工作流 <select id=wf></select> 实例 <select id=inst></select>
次数 <input id=n type=number min=1 style=width:70px placeholder=默认></div>
<div><button onclick="run('run')">运行</button><button onclick="run('observe')">观察模式 60 秒</button>
<button onclick="run('trial')">试跑 30 步</button><button onclick=stopRun()>停止</button></div>
<div><button onclick="marathon('preview')">预览日常计划</button><button onclick="marathon('start')">启动一轮日常</button>
<button onclick="stopRun('after_battle')">当前战斗结束后停</button><button onclick="stopRun('immediate')">立即停输入</button></div><pre id=running></pre><pre id=plan></pre></section>
<section><h2>当前画面与寄养</h2><button onclick="snapshot()">刷新截图</button><img id=screen alt="点击刷新截图查看当前界面" style="width:100%;max-height:380px;object-fit:contain"><pre id=foster></pre></section>
<section><h2>今日 / 本周任务</h2><button onclick="scanTasks()">重新扫描进度</button><button onclick="showDailyReport()">本地完成报告</button><table id=tasks></table><pre id=report></pre></section>
<section><h2>游戏资源预算</h2><p>消耗按输入尝试保守计入；游戏实读余额和回执单独显示。</p><table id=resources></table><pre id=balances></pre></section>
<section><h2>界面样本与回放</h2><select id=sample onchange="selectSample()"></select><button onclick="replaySamples()">回放此工作流</button><img id=sampleimg alt="选择样本" style="width:100%"><textarea id=annotation rows=5 style="width:100%" placeholder='{"state":null,"note":"未知界面，不允许点击","allowed_actions":[]}'></textarea><button onclick="saveAnnotation()">保存标注</button><pre id=replay></pre></section>
<section><h2>账号档案</h2><p>只读面板值；改御魂后逐件记录新截图，核对最终出手顺序。</p><input id=team placeholder="队伍名"><input id=member placeholder="式神名"><input id=speed type=number step=.01 placeholder="实际面板速度"><input id=crit type=number step=.01 placeholder="暴击百分比"><input id=evidence placeholder="核对截图路径"><button onclick="recordStats()">记录已核对值</button><button onclick="checkTeam()">核对出手顺序</button><pre id=account></pre></section>
<section><h2>待确认</h2><div id=pending>无</div><h2>改动</h2><div id=changes></div></section>
<section><h2>最近运行</h2><table id=runs></table></section>
<section><h2>上游同步</h2><div><button onclick="sync('run')">立即同步</button><button onclick="sync('force')">强制重新转换</button>
<button onclick="sync('check')">只检查更新</button><button onclick="rollback()">回滚上一版转换</button>
<span id=syncsched></span></div><pre id=syncstate></pre><table id=syncs></table><pre id=syncreport></pre></section>
<section><h2>大模型用量</h2><pre id=budget></pre><h2>事件</h2><table id=events></table></section>
</main><script>
const T="__TOKEN__";const $=s=>document.querySelector(s);
let meta={},sampleRows=[];
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function api(p,b){const r=await fetch(p,b?{method:'POST',headers:{'Content-Type':'application/json','X-OAF-Token':T},body:JSON.stringify(b)}:{});return r.json()}
async function init(){const d=await api('/api/meta');meta=d;$('#wf').innerHTML=d.workflows.map(w=>`<option>${esc(w)}</option>`).join('');
$('#inst').innerHTML=d.instances.map(w=>`<option>${esc(w)}</option>`).join('');refresh();setInterval(refresh,3000)}
async function refresh(){const d=await api('/api/status');
$('#runs').innerHTML='<tr><th>#</th><th>工作流</th><th>实例</th><th>执行 / 业务</th><th>证据与原因</th></tr>'+d.runs.map(r=>{const s=JSON.parse(r.summary||'{}');return `<tr><td>${r.id}</td><td>${esc(r.workflow)}</td><td>${esc(r.instance)}</td><td class=${s.business_ok?'ok':r.status=='failed'?'err':'warn'}>${esc(r.status)} / ${esc(s.business_result||'unknown')}</td><td>${esc(r.reason)} <a target=_blank href="/api/image?run=${r.id}&token=${encodeURIComponent(T)}">截图</a></td></tr>`}).join('');
$('#pending').innerHTML=d.pending.length?d.pending.map(c=>`<div class=warn>#${c.id} ${esc(c.category)}：${esc(c.detail)} <button onclick="decide(${c.id},true)">同意</button><button onclick="decide(${c.id},false)">拒绝</button></div>`).join(''):'无';
$('#changes').innerHTML=d.changes.map(c=>`<div>#${c.id} ${esc(c.workflow)} ${esc(c.kind)} <b>${esc(c.status)}</b> ${esc(c.note)} ${c.status=='waiting_user'?`<button onclick="approve(${c.id})">批准合并</button>`:''}</div>`).join('')||'无';
$('#syncstate').textContent=d.sync.running?('正在同步…'+(d.sync.running_started||'')):(d.sync.last_check||'');
$('#syncsched').textContent=d.sync.schedule.enabled?`定时同步：每 ${d.sync.schedule.interval_hours} 小时`:'定时同步：关（config.yaml upstream.schedule）';
$('#syncs').innerHTML='<tr><th>#</th><th>时间</th><th>结果</th><th>上游提交</th><th>说明</th></tr>'+d.sync.history.map(s=>`<tr><td>${s.id}</td><td>${new Date(s.started*1000).toLocaleString()}</td><td class=${['failed','broken'].includes(s.status)?'err':['waiting_user','repair_waiting'].includes(s.status)?'warn':'ok'}>${esc(s.status)}</td><td>${Object.entries(s.upstream||{}).filter(([k,v])=>typeof v=='object').map(([k,v])=>esc(k+' '+String(v.commit||'').slice(0,7))).join('<br>')}</td><td>${esc(s.summary)} <a href=# onclick="showReport(${s.id});return false">报告</a></td></tr>`).join('');
$('#budget').textContent=JSON.stringify(d.budget,null,1);$('#running').textContent=JSON.stringify(d.running,null,1);
if(d.marathons?.length)$('#running').textContent+='\n日常计划：'+JSON.stringify(d.marathons,null,1);
$('#running').textContent+='\n设备：'+JSON.stringify(d.devices,null,1);
$('#tasks').innerHTML='<tr><th>范围</th><th>任务</th><th>进度</th><th>状态</th><th>证据</th></tr>'+d.tasks.map(row=>`<tr><td>${esc(row.scope)}</td><td>${esc(row.evidence?.label||row.task_key)}</td><td>${row.current??'?'} / ${row.target??'?'}</td><td>${esc(row.status)} ${row.verified?'已实读':'未核对'}</td><td>${row.evidence?.screenshot?`<a target=_blank href="/api/image?task=${row.id}&token=${encodeURIComponent(T)}">截图</a>`:''}</td></tr>`).join('');
$('#resources').innerHTML='<tr><th>资源</th><th>日限额</th><th>最低保留</th><th>已用估计 / 预留</th></tr>'+Object.entries(d.game_budgets||{}).map(([key,value])=>`<tr><td>${esc(key)}</td><td>${value.daily_limit??'不限'}</td><td>${value.reserve??0}</td><td>${d.resources[key]?.used??0} / ${d.resources[key]?.reserved??0}</td></tr>`).join('');
$('#balances').textContent=JSON.stringify(d.balances,null,1);
$('#foster').textContent=d.foster.length?d.foster.map(row=>`${row.status} ${row.stars??'?'}星 ${row.card_type??'卡型未核对'} 到期：${row.due?new Date(row.due*1000).toLocaleString():'未知'}`).join('\n'):'没有已核对的有效寄养；不代表游戏中一定为空';
const selected=$('#sample').value;sampleRows=d.samples;$('#sample').innerHTML='<option value="">选择样本</option>'+sampleRows.map(row=>`<option value="${row.id}">#${row.id} ${esc(row.workflow)} ${row.annotation?'已标注':'待标注'}</option>`).join('');$('#sample').value=selected;
$('#events').innerHTML=d.events.map(e=>`<tr><td>${new Date(e.ts*1000).toLocaleTimeString()}</td><td class=${e.level=='error'?'err':e.level=='warn'?'warn':''}>${esc(e.message)}</td></tr>`).join('')}
async function run(mode){const n=$('#n').value,wf=$('#wf').value,spec=meta.parameters[wf]||{},key=['max_runs','max_rounds','max_fights'].find(key=>key in spec);const r=await api('/api/run',{workflow:wf,instance:$('#inst').value,mode,params:n&&key?{[key]:+n}:{}});if(r.error)alert(r.error);refresh()}
async function stopRun(mode='immediate'){await api('/api/stop',{instance:$('#inst').value,mode});refresh()}
async function marathon(action){const r=await api('/api/marathon',{action,instance:$('#inst').value,rounds:action=='start'?1:undefined});if(r.error)alert(r.error);else $('#plan').textContent=JSON.stringify(r,null,2);refresh()}
function snapshot(){$('#screen').src='/api/screenshot?instance='+encodeURIComponent($('#inst').value)+'&token='+encodeURIComponent(T)+'&t='+Date.now()}
async function scanTasks(){const r=await api('/api/run',{workflow:'task_scan',instance:$('#inst').value,mode:'run',params:{}});if(r.error)alert(r.error);refresh()}
async function showDailyReport(){$('#report').textContent=JSON.stringify(await api('/api/report'),null,2)}
function selectSample(){const row=sampleRows.find(row=>row.id==$('#sample').value);if(!row)return;$('#sampleimg').src='/api/image?sample='+row.id+'&token='+encodeURIComponent(T);$('#annotation').value=row.annotation||JSON.stringify({state:null,note:'',allowed_actions:[]},null,2)}
async function saveAnnotation(){try{const r=await api('/api/samples/annotate',{id:+$('#sample').value,annotation:JSON.parse($('#annotation').value)});if(r.error)alert(r.error);refresh()}catch(error){alert(error.message)}}
async function replaySamples(){const row=sampleRows.find(row=>row.id==$('#sample').value);if(row)$('#replay').textContent=JSON.stringify(await api('/api/samples/replay',{workflow:row.workflow}),null,2)}
async function recordStats(){const r=await api('/api/account',{action:'record',team:$('#team').value,member:$('#member').value,speed:+$('#speed').value,crit:+$('#crit').value,evidence:{screenshot:$('#evidence').value,source:'panel_read'}});$('#account').textContent=JSON.stringify(r,null,2)}
async function checkTeam(){$('#account').textContent=JSON.stringify(await api('/api/account',{action:'check',team:$('#team').value}),null,2)}
async function decide(id,yes){await api('/api/confirm',{id,approve:yes});refresh()}
async function approve(id){const r=await api('/api/approve',{id});if(r.error)alert(r.error);refresh()}
async function sync(kind){const r=await api('/api/sync',{action:kind});if(r.error)alert(r.error);else if(r.message)alert(r.message);refresh()}
async function rollback(){if(!confirm('把上一次合并的上游同步回滚掉，回到上一版转换结果？'))return;const r=await api('/api/sync/rollback',{});alert(r.error||('已回滚，提交 '+r.commit.slice(0,8)));refresh()}
async function showReport(id){const r=await api('/api/sync/report?id='+id);$('#syncreport').textContent=r.report||r.error||''}
init()</script></body></html>"""


class Panel:
    def __init__(self, app):
        self.app = app
        self.token = secrets.token_urlsafe(24)
        self.running: dict[str, dict] = {}
        self.marathons: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.sync_started = None
        self.last_check = None

    def meta(self):
        return {"workflows": self.app.workflows(), "instances": self.app.instance_names(),
                "parameters": {name: self.app.supervisor.load(name).param_specs() for name in self.app.workflows()}}

    def status(self):
        a = self.app
        return {
            "runs": a.store.recent_runs(limit=20, mode=None),
            "pending": a.broker.pending(),
            "changes": a.store.query("SELECT id, workflow, kind, status, note, branch FROM changes ORDER BY id DESC LIMIT 10"),
            "events": a.store.recent_events(30),
            "budget": a.llm.budget.snapshot() if a.llm else "未配置大模型",
            "running": self.running,
            "marathons": a.plans.status()["jobs"],
            "foster": a.plans.status()["foster"],
            "samples": a.samples.list(),
            "tasks": a.ledger.snapshot(),
            "resources": a.store.resource_totals(a.ledger.account, a.ledger.periods()[0]),
            "balances": a.store.balances(a.ledger.account),
            "game_budgets": a.cfg.get("game", {}).get("budgets", {}),
            "devices": {name: a.supervisor.runtime_status(name) for name in a.instance_names()},
            "sync": self.sync_status(),
        }

    def sync_status(self):
        a = self.app
        return {"history": a.sync.history(10), "running": a.sync.lock.locked(),
                "running_started": self.sync_started, "last_check": self.last_check,
                "schedule": (a.cfg["upstream"].get("schedule") or {"enabled": False})}

    def start_sync(self, action: str) -> dict:
        a = self.app
        if action == "check":
            from .sync import remote_head
            last = a.sync.last_processed()
            prev = (last or {}).get("upstream") or {}
            lines = []
            for name, spec in (a.cfg["upstream"].get("sources") or {}).items():
                head, _url = remote_head(spec)
                old = (prev.get(name) or {}).get("commit")
                lines.append(f"{name}：" + ("拉不到" if not head else ("没有更新" if head == old else f"有更新 {head[:7]}")))
            self.last_check = "检查结果：" + "；".join(lines)
            return {"message": self.last_check}
        if a.sync.lock.locked():
            raise ValueError("已经有一次同步在进行")
        import time as _t
        self.sync_started = _t.strftime("%H:%M:%S")

        def work():
            try:
                a.sync.sync(force=action == "force", trigger="web")
            except Exception as e:  # noqa: BLE001
                logger.exception("sync from panel failed")
                a.store.event("error", "sync", f"同步出错：{e}")
        threading.Thread(target=work, daemon=True, name="sync").start()
        return {"message": "已开始同步，拉取和转换要几分钟，完成后看下面的记录和报告"}

    def start_run(self, workflow: str, instance: str, mode: str, params: dict):
        if workflow not in self.app.workflows():
            return {"error": f"没有工作流 {workflow}"}
        if mode not in ("run", "observe", "trial"):
            raise ValueError("未知运行模式")
        self.app.cfg.instance(instance)
        wf = self.app.supervisor.load(workflow)
        wf_params = wf.validate_params(params)
        with self.lock:
            if instance in self.running:
                return {"error": f"实例 {instance} 正在运行 {self.running[instance]['workflow']}"}
            self.running[instance] = {"workflow": workflow, "mode": mode}

        def work():
            sup = self.app.supervisor
            try:
                if mode == "run":
                    out = sup.run(workflow, instance, wf_params)
                    for n in out.notes:
                        self.app.store.event("info", "panel", f"{workflow}@{instance}: {n}")
                else:
                    sup._run_once(wf, instance, wf_params, mode=mode,
                                  max_seconds=60 if mode == "observe" else None,
                                  max_actions=30 if mode == "trial" else None, observe=mode == "observe")
            except Exception as e:  # noqa: BLE001
                logger.exception("run failed")
                self.app.store.event("error", "panel", f"{workflow}@{instance} 出错：{e}")
            finally:
                with self.lock:
                    self.running.pop(instance, None)

        threading.Thread(target=work, daemon=True, name=f"run-{instance}").start()
        return {"ok": True}

    def start_marathon(self, instance: str, plan_path: str | None = None, rounds: int | None = None,
                       hours: float | None = None, out: str | None = None, preview: bool = False):
        if preview:
            return self.app.plans.preview(instance, plan_path)
        return self.app.plans.start(instance, plan_path, rounds or 1, hours, out)

    def stop_marathon(self, instance: str, mode="immediate"):
        return self.app.plans.stop(instance, mode)


def make_handler(panel: Panel):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug("web: " + fmt, *args)

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self._send(200, PAGE.replace("__TOKEN__", panel.token).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/meta":
                self._send(200, panel.meta())
            elif path == "/api/status":
                self._send(200, panel.status())
            elif path == "/api/report":
                from .report import daily_report
                self._send(200, daily_report(panel.app))
            elif path in ("/api/screenshot", "/api/image"):
                query = parse_qs(urlparse(self.path).query)
                if not secrets.compare_digest((query.get("token") or [""])[0], panel.token):
                    self._send(403, {"error": "forbidden"})
                    return
                try:
                    if path == "/api/screenshot":
                        import cv2
                        instance = (query.get("instance") or panel.app.instance_names())[0]
                        panel.app.cfg.instance(instance)
                        image = panel.app.controller(instance, observe=True).screenshot()
                        data = cv2.imencode(".png", image)[1].tobytes()
                    else:
                        if query.get("sample"):
                            image_path = panel.app.samples.get(int(query["sample"][0]))["path"]
                        elif query.get("task"):
                            rows = panel.app.store.query("SELECT evidence FROM task_ledger WHERE id=? AND account=?",
                                (int(query["task"][0]), panel.app.ledger.account))
                            image_path = json.loads(rows[0]["evidence"])["screenshot"]
                        else:
                            rows = panel.app.store.query("SELECT summary FROM runs WHERE id=?", (int(query["run"][0]),))
                            image_path = json.loads(rows[0]["summary"])["evidence"]["screenshot"]
                        resolved = Path(image_path).resolve()
                        if not resolved.is_relative_to(panel.app.cfg.runs_dir.resolve()):
                            raise ValueError("只提供 oaf 运行目录内的证据图片")
                        data = resolved.read_bytes()
                    self._send(200, data, "image/png")
                except Exception as error:
                    self._send(400, {"error": str(error)})
            elif path == "/api/sync/report":
                try:
                    sid = int((parse_qs(urlparse(self.path).query).get("id") or ["0"])[0])
                except ValueError:
                    sid = 0
                s = panel.app.sync.get(sid)
                if s and s.get("report_path") and Path(s["report_path"]).is_file():
                    self._send(200, {"report": Path(s["report_path"]).read_text(encoding="utf-8")})
                else:
                    self._send(404, {"error": "没有这次同步的报告"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if not secrets.compare_digest(self.headers.get("X-OAF-Token", ""), panel.token):
                self._send(403, {"error": "forbidden"})
                return
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 65536)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._send(400, {"error": "bad json"})
                return
            path = urlparse(self.path).path
            app = panel.app
            try:
                if path == "/api/run":
                    mode = body.get("mode", "run")
                    if mode not in ("run", "observe", "trial"):
                        raise ValueError("bad mode")
                    self._send(200, panel.start_run(str(body["workflow"]), str(body["instance"]), mode,
                                                    dict(body.get("params") or {})))
                elif path == "/api/stop":
                    self._send(200, panel.stop_marathon(str(body["instance"]), body.get("mode", "immediate")))
                elif path == "/api/marathon":
                    action = str(body.get("action", "status"))
                    if action == "start":
                        self._send(200, panel.start_marathon(str(body["instance"]), body.get("plan"),
                                                             body.get("rounds"), body.get("hours"), body.get("out"),
                                                             bool(body.get("preview"))))
                    elif action == "stop":
                        self._send(200, panel.stop_marathon(str(body["instance"]), body.get("mode", "immediate")))
                    elif action == "preview":
                        self._send(200, app.plans.preview(body.get("instance"), body.get("plan")))
                    elif action == "status":
                        self._send(200, app.plans.status())
                    else:
                        raise ValueError("未知计划动作")
                elif path == "/api/samples/annotate":
                    self._send(200, app.samples.annotate(int(body["id"]), body["annotation"]))
                elif path == "/api/samples/replay":
                    self._send(200, app.samples.replay(app.supervisor.load(body["workflow"])))
                elif path == "/api/account":
                    from .account import record, check_team, compare
                    if body.get("action") == "record":
                        self._send(200, {"id": record(app, body.get("team"), body.get("member"), body.get("speed"),
                            body.get("crit"), body.get("order"), body.get("values"), body.get("evidence"))})
                    elif body.get("action") == "compare":
                        self._send(200, compare(app, body.get("team"), body.get("member")))
                    else:
                        self._send(200, check_team(app, body.get("team")))
                elif path == "/api/confirm":
                    self._send(200, {"ok": app.broker.decide(int(body["id"]), bool(body["approve"]))})
                elif path == "/api/sync":
                    action = str(body.get("action", "run"))
                    if action not in ("run", "force", "check"):
                        raise ValueError("bad action")
                    self._send(200, panel.start_sync(action))
                elif path == "/api/sync/rollback":
                    self._send(200, {"ok": True, "commit": app.sync.rollback(body.get("id"))})
                elif path == "/api/approve":
                    self._send(200, {"ok": True, "commit": app.supervisor.approve_change(int(body["id"]))})
                else:
                    self._send(404, {"error": "not found"})
            except Exception as e:  # noqa: BLE001
                self._send(400, {"error": str(e)})

    return Handler


def serve(app, host: str = "127.0.0.1", port: int = 8765):
    panel = Panel(app)
    stop = threading.Event()
    if (app.cfg["upstream"].get("schedule") or {}).get("enabled"):
        from .sync import schedule_loop
        threading.Thread(target=schedule_loop, args=(app.sync, stop), daemon=True, name="sync-schedule").start()
    httpd = ThreadingHTTPServer((host, port), make_handler(panel))
    if host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning("面板监听在 %s，局域网内的人也能打开它", host)
    print(f"面板已启动：http://{host}:{port}/  （Ctrl+C 退出）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()
