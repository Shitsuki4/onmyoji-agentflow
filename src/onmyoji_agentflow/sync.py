"""Upstream sync: pull assttyys_autojs and OnmyojiAutoScript, convert them, validate, then merge or ask.

One sync (``oaf sync``) does::

    ls-remote (cheap "did upstream move?" check)
      -> shallow git fetch of each source (URLs tried in order: GitHub, then mirrors)
      -> converters: assttyys -> resources/upstream/assttyys/, OAS -> resources/upstream/oas/,
         assttyys -> built-in workflows -> resources/upstream/generated/
      -> 3-way merge of the generated workflows/resources into the user's own copies
         (base = the previous generated copy), so local repairs survive upstream updates
      -> candidate branch ``sync/...`` with every change, validated workflow by workflow
         (schema, sensitive confirmations, replay tests, optional observe + trial run on a device)
      -> merge rules: raw data nobody uses yet merges automatically; anything that changes what
         a workflow recognises or does waits for the user's approval (``oaf approve <id>``)
      -> broken workflows go to the LLM repair pipeline (same patch language and validation as
         ``supervisor.py``); without an LLM they are reported for the user
      -> optional: the LLM translates configured assttyys schemes into new workflows (always
         waits for approval, and the first real run asks again)

Every sync is recorded (upstream commits, conversion report, file-level and resource-level
diff) in the ``syncs`` table and a Markdown report under ``<home>/sync-reports/``.
``oaf sync rollback`` reverts the last merged sync on ``main``; the same upstream commits are
then skipped until upstream moves on (or ``--force``).

Licences: everything under ``resources/upstream/oas`` comes from OnmyojiAutoScript (GPL-3.0),
everything under ``resources/upstream/assttyys`` and the generated workflows from
assttyys_autojs (MIT, Copyright (c) 2019 Chaos). Each file keeps its ``source`` / ``license``
header and each source folder gets the upstream LICENSE file.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from .errors import AgentflowError, BudgetExceeded, LLMError, WorkflowError
from .llm import image_to_data_url, parse_json_reply
from .log import logger
from .supervisor.repair import apply_ops, classify
from .supervisor.replay import load_cases, run_cases
from .supervisor.supervisor import NEEDS_CONFIRM_MERGE, SYSTEM_PROMPT
from .workflow.schema import SENSITIVE, bundled_dir, load_workflow
from .yamlio import dump_yaml, load_yaml

def _converter_version() -> str:
    """Changes whenever the converters or the workflow builder change, so a package upgrade that
    fixes generated workflows (v0.1.3: realm_raid's 未入寮 blocker) is applied by the next
    ``oaf sync`` even when upstream has no new commits. Line endings are normalised because a
    Windows git checkout may turn them into CRLF."""
    h = hashlib.sha256()
    for f in sorted((Path(__file__).parent / "convert").glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    return "1+" + h.hexdigest()[:12]


CONVERTER_VERSION = _converter_version()
UP = "resources/upstream"
GEN = f"{UP}/generated"
MANIFEST = f"{UP}/upstream.yaml"
NOTICE = f"{UP}/NOTICE.md"
SYNC_WORKFLOW = "upstream-sync"
KIND_ORDER = {"data": 0, "params": 1, "recognition": 2, "workflow": 3}
SOURCE_INFO = {
    "assttyys": {"label": "assttyys_autojs", "license": "MIT", "copyright": "Copyright (c) 2019 Chaos",
                 "home": "https://github.com/zzliux/assttyys_autojs"},
    "oas": {"label": "OnmyojiAutoScript", "license": "GPL-3.0", "copyright": "OnmyojiAutoScript contributors",
            "home": "https://github.com/nearaura/OnmyojiAutoScript"},
}
LOCAL_DIR_NAMES = {"assttyys": ("assttyys_autojs", "assttyys"), "oas": ("OnmyojiAutoScript", "oas")}

SYNC_REPAIR_PROMPT = SYSTEM_PROMPT.replace(
    "一次运行失败了。请根据截图、失败信息和各状态的匹配情况，给出最小的修复。",
    "上游项目（assttyys_autojs / OnmyojiAutoScript）更新后，这个工作流在新的识别资源下通不过验证。"
    "请根据报错、回放测试结果、它用到的资源前后差异（以及截图，如果有），给出最小的修复。")

TRANSLATE_PROMPT = """你把 assttyys_autojs（auto.js 版阴阳师脚本）的一个方案翻译成本项目的 YAML 工作流（format: 1）。
格式要点：
- 顶层：format: 1, name, title, resources: [upstream/assttyys/colors.yaml], similarity: 93,
  params: {名字: {default: 值, min, max, desc}}, vars: {计数变量: 0}, limits: {timeout_s, unknown_timeout_s,
  stuck_timeout_s, no_progress_timeout_s, max_repeat}, stop_when: "表达式", states: [...]
- 每个状态：{id, desc, when: 条件, do: [动作...], progress: true/false, sensitive: 可选}
- 条件只能是以下之一：{colors: [[x, y, "#rrggbb"], ...]}（多点比色）、{res: 资源名}、{find: find_colors资源名}、
  {expr: "runs >= max_runs"}、{all: [...]}、{any: [...]}、{not: {...}}
- 动作只能是以下之一：{click: [x1,y1,x2,y2], delay: 毫秒}、{click_random: [[x1,y1,x2,y2], ...]}、{click_found: true}、
  {swipe: {from: [..4..], to: [..4..]}}、{back: true}、{wait: 毫秒}、{set: {变量: 表达式}}、{inc: 变量}、
  {stop: "原因"}、{fail: "原因"}、{confirm: 花勾玉|抽卡|购买|出售|分解}、{log: "文字"}
- 坐标是 1280x720；颜色、坐标照抄给你的转换结果（detect_points / oper.rect），不要编造。
- 不能写任何代码。auto.js 里的自定义逻辑（operatorFunc）只能用计数变量、表达式和状态顺序表达；
  表达不了的就省掉并在 notes 里说明。
- 涉及花勾玉、抽卡、购买、出售、分解的状态必须加 sensitive（值为对应词），点击前加 {confirm: 对应词}。
只输出 JSON：{"workflow": {...工作流...}, "notes": "中文说明：翻译了什么、省掉了什么"}"""


class SyncError(AgentflowError):
    pass


@dataclass
class Fetched:
    name: str
    path: Path
    commit: str
    url: str
    commit_time: str = ""


@dataclass
class SyncResult:
    id: int
    status: str
    message: str
    report_path: str | None = None
    change_ids: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


# ------------------------------------------------------------------ git helpers
def _git(args: list, cwd: Path | None = None, timeout: float = 900) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    return subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)


def _last_line(text: str) -> str:
    lines = [x for x in (text or "").strip().splitlines() if x.strip()]
    return lines[-1] if lines else ""


def remote_head(spec: dict, timeout: float = 60) -> tuple[str | None, str | None]:
    """(commit, url) of the configured branch, trying each URL; (None, None) when none answers."""
    for url in spec.get("urls") or []:
        try:
            r = _git(["ls-remote", url, f"refs/heads/{spec.get('branch', 'master')}"], timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.split()[0], url
    return None, None


def fetch_source(name: str, spec: dict, cache: Path, timeout: float = 900) -> Fetched:
    """Shallow-fetch ``spec['branch']`` into ``cache/name`` from the first URL that works."""
    if shutil.which("git") is None:
        raise SyncError("需要安装 git（https://git-scm.com/）才能同步上游")
    repo = cache / name
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        _git(["init", "-q"], repo)
    branch = spec.get("branch", "master")
    errors = []
    for url in spec.get("urls") or []:
        try:
            r = _git(["fetch", "-q", "--depth", "1", "--no-tags", "--force", url,
                      f"+refs/heads/{branch}:refs/remotes/upstream/{branch}"], repo, timeout)
        except subprocess.TimeoutExpired:
            errors.append(f"{url}：超过 {timeout:.0f} 秒没拉完")
            continue
        if r.returncode != 0:
            errors.append(f"{url}：{_last_line(r.stderr) or '拉取失败'}")
            continue
        co = _git(["checkout", "-q", "--force", "--detach", f"refs/remotes/upstream/{branch}"], repo, 300)
        if co.returncode != 0:
            errors.append(f"{url}：检出失败 {_last_line(co.stderr)}")
            continue
        _git(["clean", "-fdxq"], repo, 300)
        commit = _git(["rev-parse", "HEAD"], repo, 60).stdout.strip()
        ctime = _git(["log", "-1", "--format=%cI"], repo, 60).stdout.strip()
        return Fetched(name, repo, commit, url, ctime)
    raise SyncError(f"{SOURCE_INFO[name]['label']} 所有源都拉取失败：" + "；".join(errors or ["没有配置 urls"]))


def local_source(name: str, path: Path) -> Fetched:
    """Use an existing checkout (``--from``): no network."""
    path = Path(path)
    commit = "local"
    if shutil.which("git"):
        r = _git(["rev-parse", "HEAD"], path, 60)
        if r.returncode == 0 and r.stdout.strip():
            commit = r.stdout.strip()
    return Fetched(name, path, commit, str(path))


def find_local_sources(folder: Path) -> dict[str, Path]:
    """``folder`` holds the two checkouts (assttyys_autojs/ and OnmyojiAutoScript/), or is one of them."""
    folder = Path(folder)
    out = {}
    for name, names in LOCAL_DIR_NAMES.items():
        for n in names:
            if (folder / n).is_dir():
                out[name] = folder / n
                break
    if not out:
        if (folder / "src" / "common" / "funcList").is_dir():
            out["assttyys"] = folder
        elif (folder / "tasks").is_dir():
            out["oas"] = folder
    return out


# ------------------------------------------------------------------ conversion
def _copy_license(src_root: Path, dest: Path, name: str) -> None:
    for cand in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
        if (src_root / cand).is_file():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_root / cand, dest / "LICENSE")
            return
    info = SOURCE_INFO[name]
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "LICENSE").write_text(f"{info['label']} - {info['license']} - {info['copyright']}\n{info['home']}\n",
                                  encoding="utf-8")


def convert_sources(fetched: dict[str, Fetched], out: Path) -> tuple[dict, list[str], dict]:
    """Run the converters into ``out`` (a workspace-shaped folder).

    Returns (replaced prefixes -> source name, errors, report). A prefix is only replaced when its
    converter succeeded; everything else keeps the version on main."""
    from .convert import assttyys, oas
    from .convert.build_mvp import build_all
    prefixes: dict[str, str] = {}
    errors: list[str] = []
    report: dict = {}
    if "assttyys" in fetched:
        src = fetched["assttyys"].path
        dest = out / UP / "assttyys"
        try:
            r = assttyys.convert(src, dest)
            _copy_license(src, dest, "assttyys")
            report["assttyys"] = r
            prefixes[f"{UP}/assttyys/"] = "assttyys"
        except Exception as e:  # noqa: BLE001 - any converter bug is reported, never fatal
            errors.append(f"assttyys 转换失败：{type(e).__name__}: {e}")
            report["assttyys_traceback"] = traceback.format_exc()[-3000:]
        if f"{UP}/assttyys/" in prefixes:
            gen = out / GEN
            try:
                build_all(dest, gen / "workflows")
                (gen / "resources" / "assttyys").mkdir(parents=True, exist_ok=True)
                for fn in ("colors.yaml", "schemes.yaml"):
                    shutil.copyfile(dest / fn, gen / "resources" / "assttyys" / fn)
                prefixes[f"{GEN}/"] = "assttyys"
            except Exception as e:  # noqa: BLE001
                errors.append(f"根据 assttyys 生成内置工作流失败（上游的功能编号或结构变了）：{type(e).__name__}: {e}")
                report["build_traceback"] = traceback.format_exc()[-3000:]
    if "oas" in fetched:
        src = fetched["oas"].path
        dest = out / UP / "oas"
        try:
            r = oas.convert(src, dest)
            summary = {"tasks": len(r["tasks"]),
                       "resources": sum(t["resources"] for t in r["tasks"].values()),
                       "navigation": r.get("navigation")}
            (dest / "report.json").write_text(json.dumps({**summary, "by_task": r["tasks"]}, ensure_ascii=False,
                                                         indent=2, default=str), encoding="utf-8")
            _copy_license(src, dest, "oas")
            report["oas"] = summary
            prefixes[f"{UP}/oas/"] = "oas"
        except Exception as e:  # noqa: BLE001
            errors.append(f"OAS 转换失败：{type(e).__name__}: {e}")
            report["oas_traceback"] = traceback.format_exc()[-3000:]
    return prefixes, errors, report


def _tree_files(root: Path, prefix: str) -> dict[str, bytes]:
    base = root / prefix
    out = {}
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file():
                out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


def merge3(ours: bytes | None, base: bytes | None, theirs: bytes | None) -> tuple[bytes | None, bool]:
    """Three-way merge of one file. Returns (result, conflict). On conflict the local version wins."""
    if ours == base:
        return theirs, False
    if theirs == base or ours == theirs:
        return ours, False
    if ours is None or base is None or theirs is None:
        return ours, True
    with tempfile.TemporaryDirectory(prefix="oaf-merge-") as d:
        paths = []
        for n, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            p = Path(d) / n
            p.write_bytes(data)
            paths.append(str(p))
        r = subprocess.run(["git", "merge-file", "-p", "-q", *paths], capture_output=True)
        if r.returncode == 0:
            return r.stdout, False
    return ours, True


# ------------------------------------------------------------------ diffs
def _yaml_bytes(data: bytes | None):
    if data is None:
        return None
    try:
        import yaml
        return yaml.safe_load(data.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _res_key(item) -> str:
    if isinstance(item, (str, int, float, bool)) or item is None:
        return str(item)
    return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)


def _res_map(doc: dict) -> dict:
    """Name -> spec for everything a document declares as resources.

    Resource files carry a ``resources:`` *mapping*; workflows carry a ``resources:`` *list* of
    file references plus an optional ``inline_resources:`` mapping. Both shapes are handled.
    """
    out: dict = {}
    res = doc.get("resources")
    if isinstance(res, dict):
        out.update({str(k): v for k, v in res.items()})
    elif isinstance(res, (list, tuple)):
        for item in res:
            out[_res_key(item)] = item
    inline = doc.get("inline_resources")
    if isinstance(inline, dict):
        out.update({str(k): v for k, v in inline.items()})
    return out


def resource_diff(old: bytes | None, new: bytes | None) -> dict:
    """Name-level diff of the resources a document declares (resource file or workflow)."""
    o, n = _yaml_bytes(old), _yaml_bytes(new)
    if not (isinstance(o, dict) and isinstance(n, dict)):
        return {}
    keys = ("resources", "inline_resources")
    if not any(k in o or k in n for k in keys):
        return {}
    ro, rn = _res_map(o), _res_map(n)
    return {"added": sorted(set(rn) - set(ro)), "removed": sorted(set(ro) - set(rn)),
            "changed": sorted(k for k in set(ro) & set(rn) if ro[k] != rn[k])}


def summarize_changes(changes: dict[str, bytes | None], old: dict[str, bytes | None]) -> dict:
    out: dict = {"files": {"added": [], "removed": [], "modified": []}, "resources": {}, "funcs_changed": [],
                 "images": {"added": 0, "removed": 0, "modified": 0}}
    for rel in sorted(changes):
        new, before = changes[rel], old.get(rel)
        state = "added" if before is None else ("removed" if new is None else "modified")
        out["files"][state].append(rel)
        if rel.endswith(".png"):
            out["images"][state] += 1
        elif rel.startswith(f"{UP}/assttyys/funcs/"):
            out["funcs_changed"].append(Path(rel).stem)
        elif rel.endswith(".yaml"):
            d = resource_diff(before, new)
            if d and any(d.values()):
                out["resources"][rel] = d
    return out


def _resource_names_used(raw: dict) -> set[str]:
    names: set[str] = set()

    def cond(c):
        if not isinstance(c, dict):
            return
        for k in ("res", "find", "image", "ocr"):
            if isinstance(c.get(k), str):
                names.add(c[k])
        for k in ("all", "any"):
            for sub in c.get(k) or []:
                cond(sub)
        if "not" in c:
            cond(c["not"])
    for st in raw.get("states") or []:
        cond(st.get("when"))
        for a in st.get("do") or []:
            if isinstance(a, dict):
                for k in ("click", "swipe"):
                    if isinstance(a.get(k), str):
                        names.add(a[k])
    # resources defined inside the workflow itself do not come from a shared resource file
    return names - set(raw.get("inline_resources") or {})


def effective_digest(root: Path, name: str) -> str:
    """Digest of a workflow *and* everything it resolves (resources, image bytes)."""
    path = root / "workflows" / f"{name}.yaml"
    wf = load_workflow(path, [root / "resources"])
    used = _resource_names_used(load_yaml(path) or {})
    h = hashlib.sha256(wf.dump().encode("utf-8"))
    for key in sorted(k for k in wf.resources if k in used):
        spec = dict(wf.resources[key])
        spec.pop("_source", None)
        path = spec.pop("path", None)
        h.update(json.dumps([key, spec], sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
        if path and Path(path).is_file():
            h.update(Path(path).read_bytes())
    return h.hexdigest()[:16]


def _workflow_names(root: Path) -> set[str]:
    return {p.stem for p in (root / "workflows").glob("*.yaml")}


# ------------------------------------------------------------------ manager
class SyncManager:
    def __init__(self, cfg, store, workspace, supervisor, llm=None, home: Path | None = None):
        self.cfg = cfg                       # Config.data (dict)
        self.ucfg = cfg.get("upstream") or {}
        self.store = store
        self.ws = workspace
        self.sup = supervisor
        self.llm = llm
        self.home = Path(home) if home else Path(tempfile.gettempdir()) / "oaf-home"
        self.cache = self.home / "upstream-src"
        self.reports = self.home / "sync-reports"
        self.lock = threading.Lock()

    # .............................................................. records
    def history(self, limit: int = 20) -> list[dict]:
        self.refresh()
        rows = self.store.query("SELECT * FROM syncs ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["upstream"] = json.loads(r["upstream"] or "{}")
            r["change_ids"] = json.loads(r["change_ids"] or "[]")
        return rows

    def get(self, sync_id: int) -> dict | None:
        rows = [r for r in self.history(10_000) if r["id"] == sync_id]
        return rows[0] if rows else None

    def refresh(self) -> None:
        """A sync waiting for approval becomes 'merged' once one of its changes was approved and merged."""
        for s in self.store.query("SELECT * FROM syncs WHERE status IN ('waiting_user','broken','repair_waiting')"):
            for cid in json.loads(s["change_ids"] or "[]"):
                ch = self.store.query("SELECT * FROM changes WHERE id=?", (cid,))
                if ch and ch[0]["status"] == "merged":
                    self.store.execute("UPDATE syncs SET status='merged', merged_commit=? WHERE id=?",
                                       (ch[0]["merged_commit"], s["id"]))
                    break

    def last_processed(self) -> dict | None:
        rows = self.store.query("SELECT * FROM syncs WHERE upstream IS NOT NULL AND status NOT IN ('failed') "
                                "ORDER BY id DESC LIMIT 1")
        if not rows:
            return None
        r = rows[0]
        r["upstream"] = json.loads(r["upstream"] or "{}")
        return r

    def due(self, now: float | None = None) -> bool:
        sch = self.ucfg.get("schedule") or {}
        if not sch.get("enabled"):
            return False
        rows = self.store.query("SELECT started FROM syncs WHERE trigger='schedule' ORDER BY id DESC LIMIT 1")
        last = rows[0]["started"] if rows else 0
        return (now or time.time()) - last >= float(sch.get("interval_hours", 24)) * 3600

    # .............................................................. main entry
    def sync(self, force: bool = False, only: list[str] | None = None, local: Path | None = None,
             instance: str | None = None, translate: bool = True, trigger: str = "manual",
             fetch: bool = True) -> SyncResult:
        if not self.lock.acquire(blocking=False):
            raise SyncError("已经有一次同步在进行")
        try:
            return self._sync(force, only, local, instance, translate, trigger, fetch)
        finally:
            self.lock.release()

    def _record(self, sid: int, **cols) -> None:
        if not cols:
            return
        keys = ", ".join(f"{k}=?" for k in cols)
        vals = [json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in cols.values()]
        self.store.execute(f"UPDATE syncs SET {keys} WHERE id=?", (*vals, sid))

    def _finish(self, sid: int, status: str, message: str, report: dict, **cols) -> SyncResult:
        report.update(status=status, message=message, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        path = self._write_report(sid, report)
        self._record(sid, status=status, ended=time.time(), summary=message, report_path=str(path), **cols)
        level = {"failed": "error", "broken": "error", "repair_waiting": "warn", "waiting_user": "warn"}.get(status,
                                                                                                          "info")
        self.store.event(level, "sync", f"上游同步 #{sid}：{message}")
        logger.info("sync #%s %s: %s", sid, status, message)
        return SyncResult(sid, status, message, str(path), cols.get("change_ids") or report.get("change_ids", []),
                          report)

    def _sources(self, only: list[str] | None) -> dict[str, dict]:
        out = {}
        for name, spec in (self.ucfg.get("sources") or {}).items():
            if name not in SOURCE_INFO or not spec.get("enabled", True):
                continue
            if only and name not in only:
                continue
            out[name] = spec
        return out

    def _sync(self, force, only, local, instance, translate, trigger, fetch) -> SyncResult:
        sid = self.store.execute("INSERT INTO syncs(started, trigger, status) VALUES (?,?,?)",
                                 (time.time(), trigger, "running")).lastrowid
        report: dict = {"id": sid, "trigger": trigger, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "converter_version": CONVERTER_VERSION, "errors": [], "notes": []}
        try:
            return self._sync_inner(sid, report, force, only, local, instance, translate, fetch)
        except Exception as e:  # noqa: BLE001 - a sync must always leave a record
            report["errors"].append(f"{type(e).__name__}: {e}")
            report["traceback"] = traceback.format_exc()[-4000:]
            return self._finish(sid, "failed", f"同步失败：{e}", report)

    def _sync_inner(self, sid, report, force, only, local, instance, translate, fetch) -> SyncResult:
        sources = self._sources(only)
        if not sources and not local:
            return self._finish(sid, "failed", "没有启用的上游源（config.yaml 里 upstream.sources）", report)
        prev = self.last_processed()
        prev_up = (prev or {}).get("upstream") or {}
        # ---- 1. cheap check: did upstream move?
        if fetch and not local and not force and prev:
            heads = {n: remote_head(s, timeout=60)[0] for n, s in sources.items()}
            same = all(heads[n] and (prev_up.get(n) or {}).get("commit") == heads[n] for n in sources)
            if same and prev_up.get("converter_version") == CONVERTER_VERSION:
                up = {**prev_up}
                if prev["status"] == "rolled_back":
                    msg = f"上游没有新提交，这个版本你回滚过（同步 #{prev['id']}），跳过；要重新套用请加 --force"
                    return self._finish(sid, "skipped", msg, report, upstream=up)
                if prev["status"] in ("waiting_user", "broken", "repair_waiting"):
                    msg = f"上游没有新提交；同步 #{prev['id']} 还在等你处理（{prev['status']}）"
                    return self._finish(sid, "unchanged", msg, report, upstream=up)
                return self._finish(sid, "unchanged", "上游没有新提交，不用转换", report, upstream=up)
        # ---- 2. fetch
        fetched: dict[str, Fetched] = {}
        if local:
            for name, path in find_local_sources(Path(local)).items():
                if not only or name in only:
                    fetched[name] = local_source(name, path)
            if not fetched:
                return self._finish(sid, "failed", f"{local} 里没找到 assttyys_autojs 或 OnmyojiAutoScript", report)
        else:
            for name, spec in sources.items():
                if not fetch:
                    repo = self.cache / name
                    if (repo / ".git").exists():
                        fetched[name] = local_source(name, repo)
                    else:
                        report["errors"].append(f"{SOURCE_INFO[name]['label']} 还没有拉取过，先运行 oaf sync")
                    continue
                try:
                    fetched[name] = fetch_source(name, spec, self.cache, float(self.ucfg.get("fetch_timeout_s", 900)))
                except SyncError as e:
                    report["errors"].append(str(e))
        if not fetched:
            return self._finish(sid, "failed", "；".join(report["errors"]) or "没有拉到任何上游代码", report)
        upstream = {"converter_version": CONVERTER_VERSION}
        for name in SOURCE_INFO:
            if name in fetched:
                f = fetched[name]
                upstream[name] = {"commit": f.commit, "url": f.url, "commit_time": f.commit_time,
                                  "branch": (sources.get(name) or {}).get("branch", "")}
            elif name in prev_up:
                upstream[name] = {**prev_up[name], "kept": True}
        report["upstream"] = upstream
        self._record(sid, upstream=upstream)
        if not force and not local and prev and prev["status"] == "rolled_back" and all(
                (prev_up.get(n) or {}).get("commit") == fetched[n].commit for n in fetched):
            msg = f"上游没有新提交，这个版本你回滚过（同步 #{prev['id']}），跳过；要重新套用请加 --force"
            return self._finish(sid, "skipped", msg, report)
        # ---- 3. convert
        tmp_root = Path(tempfile.mkdtemp(prefix="oaf-sync-"))
        try:
            return self._convert_and_apply(sid, report, fetched, upstream, tmp_root, instance, translate)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    def _convert_and_apply(self, sid, report, fetched, upstream, tmp_root, instance, translate) -> SyncResult:
        out = tmp_root / "snapshot"
        prefixes, errors, conv_report = convert_sources(fetched, out)
        report["conversion"] = {k: v for k, v in conv_report.items() if not k.endswith("traceback")}
        report["conversion_tracebacks"] = {k: v for k, v in conv_report.items() if k.endswith("traceback")}
        report["errors"] += errors
        if errors:
            report["notes"].append("转换器出错的部分保留了上一版转换结果。转换器本身要改代码才能修，不会自动修。")
        ass = conv_report.get("assttyys") or {}
        if ass.get("needs_translation"):
            report["needs_translation"] = ass["needs_translation"]
        if ass.get("parse_errors"):
            report["parse_errors"] = ass["parse_errors"]
        if not prefixes:
            return self._finish(sid, "failed", "转换全部失败：" + "；".join(errors), report)
        for name in list(upstream):
            if name in SOURCE_INFO and name in fetched and not any(v == name for v in prefixes.values()):
                upstream[name]["conversion_failed"] = True
        # ---- 4. candidate file set
        changes: dict[str, bytes | None] = {}
        old: dict[str, bytes | None] = {}
        new_files: dict[str, bytes] = {}
        for prefix in prefixes:
            new_files.update(_tree_files(out, prefix.rstrip("/")))
            for rel in self.ws.list_files(prefix.rstrip("/")):
                if rel not in new_files:
                    changes[rel] = None
        for rel, data in new_files.items():
            changes[rel] = data
        # merged copies of the generated workflows/resources
        conflicts = []
        if f"{GEN}/" in prefixes:
            gen_rels = set(k[len(GEN) + 1:] for k in new_files if k.startswith(f"{GEN}/"))
            gen_rels |= set(k[len(GEN) + 1:] for k in self.ws.list_files(GEN))
            for rel in sorted(gen_rels):
                base = self.ws.read_bytes(f"{GEN}/{rel}")
                if base is None and (bundled_dir() / rel).is_file():
                    base = (bundled_dir() / rel).read_bytes()
                ours = self.ws.read_bytes(rel)
                theirs = new_files.get(f"{GEN}/{rel}")
                merged, conflict = merge3(ours, base, theirs)
                if conflict:
                    conflicts.append(rel)
                changes[rel] = merged
        # manifest + notice
        manifest = {"converter_version": CONVERTER_VERSION,
                    "sources": {n: {k: v for k, v in upstream[n].items() if k != "kept"}
                                for n in SOURCE_INFO if n in upstream}}
        changes[MANIFEST] = dump_yaml(manifest).encode("utf-8")
        changes[NOTICE] = self._notice(manifest).encode("utf-8")
        for rel in list(changes):
            before = self.ws.read_bytes(rel)
            old[rel] = before
            if before == changes[rel]:
                del changes[rel]
        report["conflicts"] = conflicts
        if conflicts:
            report["notes"].append("你本地改过、上游也改了的文件保留了你的版本（冲突）：" + "、".join(conflicts))
        meaningful = [r for r in changes if r not in (MANIFEST, NOTICE)]
        if not meaningful:
            if changes:
                with self.sup.git_lock:
                    branch, commit = self.ws.propose(SYNC_WORKFLOW, "data", changes,
                                                     f"[sync] 记录上游提交 {self._short(upstream)}",
                                                     prefix="sync")
                    merged = self.ws.merge(branch, f"上游同步 #{sid}：只更新了上游提交记录")
                    self.ws.delete_branch(branch)
                return self._finish(sid, "unchanged", f"上游有新提交（{self._short(upstream)}），转换结果没有变化",
                                    report, merged_commit=merged, kind="data")
            return self._finish(sid, "unchanged", f"转换结果没有变化（{self._short(upstream)}）", report)
        diff = summarize_changes(changes, old)
        report["diff"] = diff
        # ---- 5. candidate branch + validation
        msg = f"[sync] 上游同步 #{sid}：{self._short(upstream)}"
        with self.sup.git_lock:
            branch, commit = self.ws.propose(SYNC_WORKFLOW, "sync", changes, msg, prefix="sync")
            cand = self.ws.checkout_tmp(branch, tmp_root / "candidate")
        report["branch"] = branch
        self._record(sid, branch=branch, commit_id=commit)
        affected, broken, results = self._check_workflows(cand, branch, instance, set(changes))
        report["affected"] = affected
        report["validation"] = results
        wf_changed = any(r.startswith("workflows/") for r in changes)
        kind = "workflow" if wf_changed else ("recognition" if affected else "data")
        report["kind"] = kind
        change_ids: list[int] = []
        note = self._note(diff, affected, broken, conflicts)
        cid = self.store.execute(
            "INSERT INTO changes(created, workflow, kind, branch, commit_id, status, note, validation) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), SYNC_WORKFLOW, kind, branch, commit, "proposed", note,
             json.dumps(results, ensure_ascii=False, default=str))).lastrowid
        change_ids.append(cid)
        self._record(sid, kind=kind, change_ids=change_ids)
        status, message = self._decide(sid, cid, kind, branch, broken, conflicts, report)
        # ---- 6. broken workflows -> repair pipeline
        if broken:
            rstatus, rmsg, rcid = self._repair(sid, branch, cand, broken, results, diff, instance, kind)
            report["repair"] = {"status": rstatus, "message": rmsg, "change_id": rcid}
            if rcid:
                change_ids.append(rcid)
            if rstatus == "merged":
                status, message = "merged", f"上游改动让 {'、'.join(broken)} 失效，已自动修复并合并：{rmsg}"
            elif rstatus == "waiting_user":
                status = "repair_waiting"
                message = (f"上游改动让 {'、'.join(broken)} 失效；大模型给出的修复已通过验证，"
                           f"等你批准改动 #{rcid}（oaf approve {rcid}）")
            else:
                message += f"；{rmsg}"
        # ---- 7. LLM translation of configured schemes
        if translate and self.llm is not None and (self.ucfg.get("translate") or {}).get("schemes"):
            base = "main" if status == "merged" else branch
            for t in self._translate(cand, base, diff, instance):
                report.setdefault("translations", []).append(t)
                if t.get("change_id"):
                    change_ids.append(t["change_id"])
        report["change_ids"] = change_ids
        merged = None
        if status == "merged":
            row = self.store.query("SELECT merged_commit FROM changes WHERE id=?", (change_ids[-1] if broken else cid,))
            merged = row[0]["merged_commit"] if row else None
        return self._finish(sid, status, message, report, change_ids=change_ids, merged_commit=merged)

    # .............................................................. steps
    @staticmethod
    def _short(upstream: dict) -> str:
        parts = []
        for n in SOURCE_INFO:
            if n in upstream and isinstance(upstream[n], dict):
                c = upstream[n].get("commit", "")
                parts.append(f"{SOURCE_INFO[n]['label']} {c[:7] if c != 'local' else 'local'}")
        return "，".join(parts)

    @staticmethod
    def _notice(manifest: dict) -> str:
        lines = ["# 上游来源与许可", "",
                 "这个目录由 `oaf sync` 自动生成，不要手改（改了下次同步会被覆盖）。", ""]
        for n, info in SOURCE_INFO.items():
            src = (manifest.get("sources") or {}).get(n)
            if not src:
                continue
            folder = "assttyys/ 和 generated/" if n == "assttyys" else "oas/"
            lines += [f"## {info['label']}", "",
                      f"- 目录：{folder}", f"- 来源：{src.get('url') or info['home']}",
                      f"- 分支 / 提交：{src.get('branch', '')} / {src.get('commit', '')}",
                      f"- 许可：{info['license']}（{info['copyright']}），原文见该目录下的 LICENSE", ""]
        lines.append("OnmyojiAutoScript 来的图片和配置按 GPL-3.0 发布；assttyys_autojs 来的数据保留 MIT 版权声明。")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _note(diff, affected, broken, conflicts) -> str:
        f = diff["files"]
        s = f"上游同步：新增 {len(f['added'])}、删除 {len(f['removed'])}、修改 {len(f['modified'])} 个文件"
        if affected:
            s += f"；影响工作流 {'、'.join(affected)}"
        if broken:
            s += f"；失效 {'、'.join(broken)}"
        if conflicts:
            s += f"；冲突保留本地 {'、'.join(conflicts)}"
        return s

    def _check_workflows(self, cand: Path, branch: str, instance: str | None, changed: set):
        main_root = self.ws.path
        names = sorted(_workflow_names(cand) | _workflow_names(main_root))
        affected, broken, results = [], [], {}
        for name in names:
            if not (cand / "workflows" / f"{name}.yaml").exists():
                continue   # removed workflows are listed in the diff
            try:
                before = effective_digest(main_root, name)
            except (WorkflowError, OSError):
                before = None
            try:
                after = effective_digest(cand, name)
            except (WorkflowError, OSError) as e:
                affected.append(name)
                broken.append(name)
                results[name] = {"failed_step": "格式检查", "error": str(e), "steps": []}
                continue
            if before == after:
                continue
            affected.append(name)
            try:
                wf_before = self.sup.load(name)
            except (WorkflowError, OSError):
                wf_before = None
            vkind = "workflow" if f"workflows/{name}.yaml" in changed else "recognition"
            ok, rep = self.sup._validate_in(wf_before, name, cand, branch, instance, vkind)
            results[name] = rep
            if not ok:
                broken.append(name)
        return affected, broken, results

    def _decide(self, sid, cid, kind, branch, broken, conflicts, report) -> tuple[str, str]:
        if broken:
            self.store.execute("UPDATE changes SET status='rejected' WHERE id=?", (cid,))
            return "broken", (f"上游改动让 {'、'.join(broken)} 通不过验证，main 没有动（还在用旧版本），"
                              f"候选分支 {branch}")
        auto = (self.cfg.get("supervisor") or {}).get("auto_merge") or {}
        auto_ok = {"data": bool(self.ucfg.get("auto_merge_data", True)),
                   "recognition": bool(auto.get("images", False)),
                   "workflow": bool(auto.get("workflow", False))}[kind]
        if conflicts:
            auto_ok = False
        if auto_ok:
            merged = self.sup.merge_change(cid)
            return "merged", f"已合并（{kind}，提交 {merged[:8]}）：{self._short(report['upstream'])}"
        self.store.execute("UPDATE changes SET status='waiting_user' WHERE id=?", (cid,))
        what = {"recognition": "改了工作流用到的识别资源", "workflow": "改了工作流本身", "data": "只改了数据"}[kind]
        self.store.event("warn", "sync", f"{NEEDS_CONFIRM_MERGE}：上游同步 #{sid} {what}，已通过验证，等你批准改动 #{cid}")
        return "waiting_user", (f"上游同步{what}，已通过验证，等你批准：oaf approve {cid}（或在网页面板点批准）")

    def _repair(self, sid, branch, cand, broken, results, diff, instance, kind):
        if self.llm is None:
            return "human", "没有配置大模型，需要你处理（报告里有失效原因）", None
        files: dict = {}
        all_ops: list = []
        diagnoses = []
        for name in broken:
            path = cand / "workflows" / f"{name}.yaml"
            raw = load_yaml(path)
            rep = results.get(name) or {}
            frame = None
            failed = (rep.get("replay") or {}).get("failed") or []
            if failed:
                for case, img, _meta in load_cases(cand / "tests" / name):
                    if case == failed[0].get("case"):
                        frame = img
                        break
            used = _resource_names_used(raw)
            res_diff = {f: {k: [x for x in v if x in used] for k, v in d.items()}
                        for f, d in diff.get("resources", {}).items()}
            res_diff = {f: d for f, d in res_diff.items() if any(d.values())}
            current = {}
            try:
                from .workflow.schema import resolve_resources
                allres = resolve_resources(raw, path, [cand / "resources"])
                current = {k: {kk: vv for kk, vv in v.items() if kk not in ("path", "_source")}
                           for k, v in allres.items() if k in used}
            except (WorkflowError, OSError) as e:
                current = {"error": str(e)}
            text = {"workflow": name, "validation": rep, "resource_diff": res_diff,
                    "resources_now": current, "workflow_yaml": dump_yaml(raw)[:12000]}
            content = [{"type": "text", "text": json.dumps(text, ensure_ascii=False, default=str)[:30000]}]
            if frame is not None:
                content.append({"type": "image_url", "image_url": {"url": image_to_data_url(frame)}})
            try:
                reply = self.llm.chat([{"role": "system", "content": SYNC_REPAIR_PROMPT},
                                       {"role": "user", "content": content}],
                                      purpose="sync-repair", need_vision=frame is not None)
                proposal = parse_json_reply(reply)
            except (LLMError, BudgetExceeded, ValueError) as e:
                return "human", f"大模型修复没做成：{e}", None
            diagnoses.append(f"{name}：{proposal.get('diagnosis', '')}")
            if proposal.get("action") != "patch" or not proposal.get("ops"):
                return "human", f"大模型诊断：{proposal.get('diagnosis', '')}（没有给出可用的修改，需要你处理）", None
            try:
                new_raw = apply_ops(raw, proposal["ops"], frame)
            except Exception as e:  # noqa: BLE001
                return "human", f"大模型给的修改用不上（{e}），需要你处理", None
            files[f"workflows/{name}.yaml"] = dump_yaml(new_raw)
            all_ops += proposal["ops"]
        rkind = max(kind, classify(all_ops), key=lambda k: KIND_ORDER.get(k, 3))
        note = f"上游同步 #{sid} 后的修复：" + "；".join(diagnoses)
        with self.sup.git_lock:
            rbranch, rcommit = self.ws.propose(SYNC_WORKFLOW, f"repair-{rkind}", files, f"[sync] {note[:120]}",
                                               base=branch, prefix="sync")
        rcid = self.store.execute(
            "INSERT INTO changes(created, workflow, kind, branch, commit_id, status, note) VALUES (?,?,?,?,?,?,?)",
            (time.time(), SYNC_WORKFLOW, rkind, rbranch, rcommit, "proposed", note)).lastrowid
        reports = {}
        all_ok = True
        for name in broken:
            try:
                wf_before = self.sup.load(name)
            except (WorkflowError, OSError):
                wf_before = None
            ok, rep = self.sup.validate_branch(wf_before, rbranch, instance, rkind, name=name)
            reports[name] = rep
            all_ok = all_ok and ok
        self.store.execute("UPDATE changes SET validation=? WHERE id=?",
                           (json.dumps(reports, ensure_ascii=False, default=str), rcid))
        if not all_ok:
            self.store.execute("UPDATE changes SET status='rejected' WHERE id=?", (rcid,))
            bad = [f"{n}（{r.get('failed_step')}）" for n, r in reports.items() if r.get("failed_step")]
            return "human", f"大模型的修复没通过验证：{'、'.join(bad)}，保留在分支 {rbranch}，需要你处理", rcid
        auto = (self.cfg.get("supervisor") or {}).get("auto_merge") or {}
        auto_ok = {"params": auto.get("params", True), "data": auto.get("params", True),
                   "recognition": auto.get("images", False), "workflow": auto.get("workflow", False)}[rkind]
        if auto_ok:
            merged = self.sup.merge_change(rcid)
            return "merged", f"提交 {merged[:8]}", rcid
        self.store.execute("UPDATE changes SET status='waiting_user' WHERE id=?", (rcid,))
        return "waiting_user", note, rcid

    def _translate(self, cand: Path, base: str, diff: dict, instance: str | None) -> list[dict]:
        tcfg = self.ucfg.get("translate") or {}
        schemes_doc = load_yaml(cand / UP / "assttyys" / "schemes.yaml") if (
            cand / UP / "assttyys" / "schemes.yaml").exists() else {}
        schemes = (schemes_doc or {}).get("schemes") or {}
        changed_funcs = {int(x) for x in diff.get("funcs_changed", []) if x.isdigit()}
        out = []
        mps = tcfg.get("max_per_sync")
        budget = None if mps in (None, "") else int(mps)    # None: no limit (the default)
        for scheme in tcfg.get("schemes") or []:
            if budget is not None and budget <= 0:
                out.append({"scheme": scheme, "status": "skipped", "message": "超过每次同步的翻译上限 max_per_sync"})
                continue
            if scheme not in schemes:
                out.append({"scheme": scheme, "status": "skipped", "message": "上游 schemes.yaml 里没有这个方案"})
                continue
            name = "ass_" + hashlib.sha1(scheme.encode("utf-8")).hexdigest()[:8]
            exists = (cand / "workflows" / f"{name}.yaml").exists()
            if exists and not (set(schemes[scheme]) & changed_funcs):
                out.append({"scheme": scheme, "workflow": name, "status": "unchanged",
                            "message": "方案用到的功能这次没变，不用重新翻译"})
                continue
            if budget is not None:
                budget -= 1
            out.append(self._translate_one(cand, base, scheme, name, schemes[scheme], instance))
        return out

    def _translate_one(self, cand: Path, base: str, scheme: str, name: str, func_ids: list, instance) -> dict:
        item = {"scheme": scheme, "workflow": name}
        funcs = []
        for fid in func_ids:
            p = cand / UP / "assttyys" / "funcs" / f"{int(fid):03d}.yaml"
            if p.exists():
                funcs.append(p.read_text(encoding="utf-8")[:6000])
        src_dir = self.cache / "assttyys" / "src" / "common" / "funcList"
        sources = []
        for fid in func_ids:
            for f in sorted(src_dir.glob(f"{int(fid):03d}*.ts")) if src_dir.is_dir() else []:
                sources.append(f"// {f.name}\n" + f.read_text(encoding="utf-8", errors="replace")[:5000])
        example = ""
        ex = cand / "workflows" / "orochi.yaml"
        if ex.exists():
            example = ex.read_text(encoding="utf-8")[:5000]
        user = {"scheme": scheme, "workflow_name": name, "func_ids": func_ids,
                "converted_funcs": "\n---\n".join(funcs)[:40000],
                "autojs_sources": "\n".join(sources)[:30000], "example_workflow": example}
        try:
            reply = self.llm.chat([{"role": "system", "content": TRANSLATE_PROMPT},
                                   {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
                                  purpose="translate", need_vision=False)
            data = parse_json_reply(reply)
        except (LLMError, BudgetExceeded, ValueError) as e:
            return {**item, "status": "failed", "message": f"大模型翻译没做成：{e}"}
        wf = data.get("workflow")
        if not isinstance(wf, dict):
            return {**item, "status": "failed", "message": "大模型没有返回工作流"}
        wf.update(format=1, name=name, title=f"{scheme}（assttyys 翻译）")
        wf["source"] = {"from": "assttyys_autojs", "scheme": scheme, "license": "MIT",
                        "copyright": "Copyright (c) 2019 Chaos", "translated_by": "llm"}
        problem = _sensitive_problem(wf)
        if problem:
            return {**item, "status": "rejected", "message": problem}
        try:
            load_workflow(wf, [cand / "resources"])
        except WorkflowError as e:
            return {**item, "status": "rejected", "message": f"翻译结果格式不对：{e}"}
        note = f"大模型翻译 assttyys 方案「{scheme}」：{str(data.get('notes', ''))[:300]}"
        with self.sup.git_lock:
            branch, commit = self.ws.propose(name, "workflow", {f"workflows/{name}.yaml": dump_yaml(wf)},
                                             f"[sync] {note[:120]}", base=base, prefix="sync")
        cid = self.store.execute(
            "INSERT INTO changes(created, workflow, kind, branch, commit_id, status, note) VALUES (?,?,?,?,?,?,?)",
            (time.time(), name, "workflow", branch, commit, "proposed", note)).lastrowid
        ok, rep = self.sup.validate_branch(None, branch, instance, "workflow", name=name)
        self.store.execute("UPDATE changes SET validation=? WHERE id=?", (json.dumps(rep, ensure_ascii=False), cid))
        if not ok:
            self.store.execute("UPDATE changes SET status='rejected' WHERE id=?", (cid,))
            return {**item, "status": "rejected", "change_id": cid,
                    "message": f"没通过验证（{rep.get('failed_step')}）：{rep.get('error', '')}"}
        # new workflows always wait for the user (and ask again before their first real run)
        self.store.execute("UPDATE changes SET status='waiting_user' WHERE id=?", (cid,))
        return {**item, "status": "waiting_user", "change_id": cid,
                "message": f"已通过格式检查，等你批准：oaf approve {cid}" + (
                    "（基于本次同步的候选分支，批准会连同步一起合并）" if base != "main" else "")}

    # .............................................................. rollback
    def rollback(self, sync_id: int | None = None) -> str:
        self.refresh()
        if sync_id is None:
            rows = self.store.query("SELECT * FROM syncs WHERE status='merged' AND merged_commit IS NOT NULL "
                                    "ORDER BY id DESC LIMIT 1")
        else:
            rows = self.store.query("SELECT * FROM syncs WHERE id=?", (sync_id,))
        if not rows:
            raise SyncError("没有可以回滚的同步（只有已合并的同步能回滚）")
        s = rows[0]
        if s["status"] != "merged" or not s["merged_commit"]:
            raise SyncError(f"同步 #{s['id']} 的状态是 {s['status']}，只有已合并的同步能回滚")
        with self.sup.git_lock:
            commit = self.ws.revert(s["merged_commit"], f"[sync] 回滚上游同步 #{s['id']}，回到上一版转换结果")
        self.store.execute("UPDATE syncs SET status='rolled_back' WHERE id=?", (s["id"],))
        for cid in json.loads(s["change_ids"] or "[]"):
            self.store.execute("UPDATE changes SET status='rolled_back' WHERE id=? AND status='merged'", (cid,))
        self.store.event("warn", "sync", f"已回滚上游同步 #{s['id']}（提交 {commit[:8]}）")
        return commit

    # .............................................................. report
    def _write_report(self, sid: int, report: dict) -> Path:
        self.reports.mkdir(parents=True, exist_ok=True)
        (self.reports / f"sync-{sid:04d}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        path = self.reports / f"sync-{sid:04d}.md"
        path.write_text(render_report(report), encoding="utf-8")
        return path


def _sensitive_problem(wf: dict) -> str | None:
    for st in wf.get("states") or []:
        text = json.dumps({k: st.get(k) for k in ("id", "desc", "title")}, ensure_ascii=False)
        for word in SENSITIVE:
            if word in text and st.get("sensitive") != word:
                return f"状态 {st.get('id')} 涉及「{word}」但没有标 sensitive，拒绝"
    return None


def render_report(r: dict) -> str:
    L = [f"# 上游同步 #{r.get('id')}", "",
         f"- 结果：{r.get('status')} - {r.get('message', '')}",
         f"- 开始：{r.get('started')}，结束：{r.get('finished', '')}，触发：{r.get('trigger')}"]
    up = r.get("upstream") or {}
    for n, info in SOURCE_INFO.items():
        if isinstance(up.get(n), dict):
            u = up[n]
            extra = "（本次没拉到，沿用上一版）" if u.get("kept") else ("（转换失败，沿用上一版）" if u.get(
                "conversion_failed") else "")
            L.append(f"- {info['label']}：{u.get('commit', '')[:12]} {u.get('commit_time', '')} {u.get('url', '')}{extra}")
    if r.get("branch"):
        L.append(f"- 候选分支：{r['branch']}")
    if r.get("change_ids"):
        L.append(f"- 改动编号：{', '.join('#' + str(c) for c in r['change_ids'])}")
    if r.get("errors"):
        L += ["", "## 错误", ""] + [f"- {e}" for e in r["errors"]]
    if r.get("notes"):
        L += ["", "## 说明", ""] + [f"- {e}" for e in r["notes"]]
    conv = r.get("conversion") or {}
    if conv:
        L += ["", "## 转换结果", ""]
        a = conv.get("assttyys")
        if a:
            L.append(f"- assttyys：{a.get('colors')} 个比色资源，{a.get('funcs')} 个功能（{len(a.get('needs_translation', []))} 个含自定义逻辑，"
                     f"需要大模型翻译），{a.get('schemes')} 个方案，解析出错 {len(a.get('parse_errors', []))} 个")
        o = conv.get("oas")
        if o:
            L.append(f"- OAS：{o.get('tasks')} 个任务，{o.get('resources')} 个识别资源，导航 {o.get('navigation')}")
    d = r.get("diff")
    if d:
        f = d["files"]
        L += ["", "## 差异", "",
              f"- 文件：新增 {len(f['added'])}，删除 {len(f['removed'])}，修改 {len(f['modified'])}",
              f"- 图片：新增 {d['images']['added']}，删除 {d['images']['removed']}，修改 {d['images']['modified']}"]
        if d.get("funcs_changed"):
            L.append(f"- assttyys 功能变化：{', '.join(d['funcs_changed'][:60])}")
        for rel, rd in list(d.get("resources", {}).items())[:40]:
            L.append(f"- {rel}：新增 {len(rd['added'])} 删除 {len(rd['removed'])} 修改 {len(rd['changed'])}"
                     + (f"（修改：{', '.join(rd['changed'][:10])}）" if rd["changed"] else ""))
        wf_files = [x for k in ("added", "removed", "modified") for x in f[k] if x.startswith("workflows/")]
        if wf_files:
            L.append(f"- 工作流文件：{', '.join(wf_files)}")
    if r.get("affected") is not None:
        L += ["", "## 验证", ""]
        if not r["affected"]:
            L.append("- 没有工作流受影响")
        for name, rep in (r.get("validation") or {}).items():
            if rep.get("failed_step"):
                L.append(f"- {name}：没通过（{rep['failed_step']}）{rep.get('error', '')}")
            else:
                L.append(f"- {name}：" + "，".join(rep.get("steps", [])))
    if r.get("repair"):
        L += ["", "## 修复", "", f"- {r['repair']['status']}：{r['repair']['message']}"]
    for t in r.get("translations") or []:
        L.append(f"- 翻译「{t.get('scheme')}」→ {t.get('workflow', '')}：{t.get('status')} {t.get('message', '')}")
    if r.get("needs_translation"):
        L += ["", "## 含自定义逻辑、需要大模型翻译的功能", "", "、".join(r["needs_translation"])]
    if r.get("parse_errors"):
        L += ["", "## 解析出错", ""] + [f"- {e}" for e in r["parse_errors"]]
    tb = r.get("conversion_tracebacks") or {}
    if r.get("traceback"):
        tb = {**tb, "sync": r["traceback"]}
    if tb:
        L += ["", "## 出错位置", ""]
        for k, v in tb.items():
            L += [f"{k}:", "", "```", v.strip(), "```", ""]
    return "\n".join(L) + "\n"


def schedule_loop(manager: SyncManager, stop: threading.Event, poll_s: float = 60) -> None:
    """Background loop for ``oaf web`` / ``oaf sync --loop``: run a sync whenever one is due."""
    while not stop.is_set():
        try:
            if manager.due():
                manager.sync(trigger="schedule")
        except SyncError as e:
            logger.info("scheduled sync skipped: %s", e)
        except Exception:  # noqa: BLE001
            logger.exception("scheduled sync crashed")
        stop.wait(poll_s)
