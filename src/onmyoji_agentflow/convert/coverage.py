"""Source obligations and revision-bound coverage accounting, never code execution.

An obligation mapping is a translation claim, not a semantic proof. Completion
additionally requires an independent review record in the immutable source
workspace at ``translations/coverage/<workflow>.json``. The record must bind the
source inventory, candidate and mapping digests; a proposal cannot supply it.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from ..yamlio import load_yaml


MANIFEST_FORMAT = 1


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def candidate_digest(workflow):
    """Hash the complete candidate revision, excluding only its own manifest."""
    return _digest({key: value for key, value in workflow.items() if key != "coverage_manifest"})


def _scope(entry):
    return {"kind": "scoped" if entry.get("variant") else entry["kind"],
            "variant": entry.get("variant"), "description": entry.get("scope_description")}


@lru_cache(maxsize=256)
def _file_obligations(path, text):
    """Conservative static inventory, including imported/local framework files.

    Whole-file obligations retain constructs that the structural inventory does
    not understand. In particular the TS inventory is not advertised as a parser
    or as evidence of semantic equivalence.
    """
    lines = text.splitlines(keepends=True)
    obligations = []

    def add(kind, label, start, end, column=0):
        anchor = {"path": path, "kind": kind, "label": label, "line": start,
                  "end_line": end, "column": column,
                  "sha256": hashlib.sha256("".join(lines[start - 1:end]).encode("utf-8")).hexdigest()}
        obligations.append({"id": _digest(anchor), **anchor})

    add("file", "complete source file", 1, max(1, len(lines)))
    errors = []
    if path.endswith(".py"):
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError as error:
            return tuple(obligations), (f"{path}:{error.lineno} 语法错误",)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.stmt, ast.Call, ast.IfExp, ast.comprehension)):
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind, label = "method", node.name
            elif isinstance(node, ast.ClassDef):
                kind, label = "inheritance", node.name + ":" + ",".join(ast.unparse(base) for base in node.bases)
            elif isinstance(node, ast.Call):
                kind, label = "call", ast.unparse(node.func)
            elif isinstance(node, ast.IfExp):
                kind, label = "branch", "IfExp"
            elif isinstance(node, ast.comprehension):
                # Comprehension nodes have no source location of their own.
                for branch in [node.iter, *node.ifs]:
                    add("branch", "comprehension", branch.lineno, branch.end_lineno, branch.col_offset)
                continue
            else:
                kind, label = "statement", type(node).__name__
            add(kind, label, node.lineno, node.end_lineno, node.col_offset)
            # A whole If/Try node alone must not hide its alternative branches.
            for field in ("body", "orelse", "finalbody"):
                branch = getattr(node, field, None)
                if isinstance(branch, list) and branch and isinstance(branch[0], ast.stmt):
                    add("branch", type(node).__name__ + "." + field,
                        branch[0].lineno, branch[-1].end_lineno, branch[0].col_offset)
            if isinstance(node, ast.Match):
                for position, case in enumerate(node.cases):
                    if case.body:
                        add("branch", f"Match.case[{position}]", case.body[0].lineno,
                            case.body[-1].end_lineno, case.body[0].col_offset)
            if isinstance(node, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                for position, handler in enumerate(node.handlers):
                    add("branch", f"Try.handler[{position}]", handler.lineno,
                        handler.end_lineno, handler.col_offset)
    else:
        # Line anchors deliberately over-approximate TS/other source rather than
        # silently dropping dynamic code, configuration, or unfamiliar syntax.
        for number, line in enumerate(lines, 1):
            if line.strip():
                add("source_line", "source line", number, number)
    return tuple(obligations), tuple(errors)


def source_obligations(entry, root):
    """Derive obligations from source bytes, never from a translator's claims."""
    folder = Path(root) / "resources/upstream" / entry["source"] / "programs/src"
    files, obligations, errors = [], [], []
    paths = entry.get("files") or []
    if not paths:
        errors.append("源码清单为空")
    if len(paths) != len(set(paths)):
        errors.append("源码清单包含重复文件")
    required = set(entry.get("entry_files") or [])
    if entry.get("entrypoint"):
        required.add(entry["entrypoint"])
    for path in sorted(required - set(paths)):
        errors.append("入口未收录在源码清单：" + path)
    for path in sorted(set(paths)):
        target = (folder / (path + ".txt")).resolve()
        if not target.is_relative_to(folder.resolve()) or not target.is_file():
            errors.append("源码快照缺失：" + path)
            files.append({"path": path, "sha256": None})
            continue
        data = target.read_bytes()
        files.append({"path": path, "sha256": hashlib.sha256(data).hexdigest()})
        try:
            found, problems = _file_obligations(path, data.decode("utf-8-sig"))
        except UnicodeError:
            errors.append("源码不是 UTF-8：" + path)
            continue
        obligations.extend(dict(item) for item in found)
        errors.extend(problems)
    # Recognition assets are source data too. Do not let an unchanged catalog
    # fingerprint conceal altered resource documents or image bytes.
    resource_root = folder.parent.parent
    resources = []
    for relative in sorted(set(entry.get("resource_files") or [])):
        target = (resource_root / relative).resolve()
        if not target.is_relative_to(resource_root.resolve()) or not target.is_file():
            resources.append({"path": relative, "sha256": None})
            errors.append("识别资源缺失：" + relative)
            continue
        resources.append({"path": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        try:
            document = load_yaml(target) or {}
            specs = (document.get("resources") or {}).values()
            for spec in specs:
                for field in ("file", "mask_file"):
                    image = spec.get(field)
                    if not image:
                        continue
                    asset = (target.parent / image).resolve()
                    if not asset.is_relative_to(resource_root.resolve()) or not asset.is_file():
                        errors.append("识别图片缺失或越界：" + str(image))
                        resources.append({"path": relative + ":" + str(image), "sha256": None})
                    else:
                        resources.append({"path": asset.relative_to(resource_root).as_posix(),
                                          "sha256": hashlib.sha256(asset.read_bytes()).hexdigest()})
        except Exception as error:
            errors.append("识别资源解析失败：" + relative + "：" + type(error).__name__)
    if entry.get("errors"):
        errors.append("上游依赖解析错误：" + str(entry["errors"]))
    if entry.get("missing_funcs"):
        errors.append("方案引用缺失组件：" + str(entry["missing_funcs"]))
    identity = {key: entry.get(key) for key in ("id", "source", "fingerprint", "entry_files",
                "entrypoint", "scheme_definition", "func_ids", "resource_files", "variant", "scope_description")}
    if entry.get("source_dispatch"):
        identity["source_dispatch"] = entry["source_dispatch"]
    return {"source_digest": _digest({"entry": identity, "files": files, "resources": resources}),
            "obligations_digest": _digest(obligations), "obligations": obligations,
            "errors": errors}


def _header(entry, inventory, workflow):
    return {"format": MANIFEST_FORMAT, "entry_id": entry["id"], "fingerprint": entry["fingerprint"],
            "source_digest": inventory["source_digest"],
            "obligations_digest": inventory["obligations_digest"],
            "obligation_count": len(inventory["obligations"]), "scope": _scope(entry),
            "candidate_digest": candidate_digest(workflow)}


def _claims(manifest, inventory, workflow):
    claims = manifest.get("claims")
    if not isinstance(claims, list):
        raise ValueError("coverage_manifest.claims 必须是列表")
    ids = {item["id"] for item in inventory["obligations"]}
    states = {state["id"] for state in workflow.get("states", [])}
    seen, result = set(), []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) - {"id", "status", "states", "note"}:
            raise ValueError("coverage_manifest 含无效的义务映射字段")
        oid = claim.get("id")
        if not isinstance(oid, str) or oid not in ids or oid in seen:
            raise ValueError("coverage_manifest 包含未知或重复的源义务")
        seen.add(oid)
        status, targets, note = claim.get("status"), claim.get("states", []), claim.get("note", "")
        if status not in ("implemented", "blocked", "unmapped"):
            raise ValueError("coverage_manifest 义务状态必须是 implemented/blocked/unmapped")
        if (not isinstance(targets, list) or not all(isinstance(target, str) and target in states for target in targets)
                or len(targets) != len(set(targets))):
            raise ValueError("coverage_manifest 引用了不存在或重复的候选状态")
        if not isinstance(note, str) or (status != "unmapped" and not note.strip()):
            raise ValueError("coverage_manifest 已映射或阻塞的义务需要说明")
        if status == "implemented" and not targets:
            raise ValueError("coverage_manifest implemented 义务必须映射到候选状态")
        result.append({"id": oid, "status": status, "states": targets, "note": note})
    return sorted(result, key=lambda item: item["id"])


def bind_manifest(entry, inventory, workflow, submitted=None, submitted_workflow=None):
    """Seal claims to the normalized candidate; legacy proposals remain drafts.

    When supplying claims, callers use this same helper on their input workflow.
    Its digest is checked before compiler normalization, then rebound to the
    exact persisted candidate. Reusing a manifest after editing its workflow is
    rejected. Caller-provided completion/review flags are never accepted.
    """
    claims = []
    if submitted is not None:
        if not isinstance(submitted, dict):
            raise ValueError("coverage_manifest 必须是对象")
        expected = _header(entry, inventory, submitted_workflow if submitted_workflow is not None else workflow)
        if set(submitted) != set(expected) | {"claims"}:
            raise ValueError("coverage_manifest 字段不完整或包含自行声明的审核信息")
        for key, value in expected.items():
            if type(submitted.get(key)) is not type(value) or submitted[key] != value:
                raise ValueError("coverage_manifest 已过期或绑定不匹配：" + key)
        claims = _claims(submitted, inventory, workflow)
    return {**_header(entry, inventory, workflow), "claims": claims}


def manifest_status(entry, inventory, workflow, review_root=None):
    """Validate a persisted manifest and an optional independently stored review."""
    total = len(inventory["obligations"])
    result = {"status": "missing", "valid": False, "mapped": 0, "blocked": 0,
              "unmapped": total, "total": total, "mapping_complete": False,
              "semantic_complete": False, "candidate_revision": None,
              "gaps": list(inventory["errors"])}
    try:
        result["candidate_revision"] = candidate_digest(workflow)
    except (TypeError, ValueError) as error:
        result.update(status="invalid")
        result["gaps"].append("候选内容无法计算修订摘要：" + str(error))
        return result
    manifest = workflow.get("coverage_manifest")
    if manifest is None:
        result["gaps"].append("缺少源义务覆盖清单；草稿不能证明完整语义")
        return result
    try:
        checked = bind_manifest(entry, inventory, workflow, manifest)
    except (ValueError, TypeError, KeyError) as error:
        result.update(status="invalid")
        result["gaps"].append(str(error))
        return result
    claims = checked["claims"]
    mapped = sum(claim["status"] == "implemented" for claim in claims)
    blocked = sum(claim["status"] == "blocked" for claim in claims)
    complete = total > 0 and mapped == total and not inventory["errors"]
    result.update(status="mapped" if complete else "partial" if claims else "unmapped", valid=True,
                  mapped=mapped, blocked=blocked, unmapped=total - mapped - blocked, mapping_complete=complete)
    if not complete:
        result["gaps"].append(f"源义务尚未完整映射：{mapped}/{total}；阻塞 {blocked}")
        return result
    # This record is read only from the pinned source workspace, never from the
    # submitted YAML, proposal branch or mutable branch head.
    name = entry["workflow"]
    review_path = (Path(review_root) / "translations/coverage" / (name + ".json")) if (
        review_root is not None and re.fullmatch(r"[\w-]+", name)) else None
    if review_path is not None and not review_path.resolve().is_relative_to(Path(review_root).resolve()):
        result["gaps"].append("独立语义审核记录超出固定源码工作区")
        return result
    try:
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path else None
    except FileNotFoundError:
        review = None
    except (OSError, ValueError) as error:
        result["gaps"].append("独立语义审核记录不可读：" + str(error))
        return result
    expected = {**_header(entry, inventory, workflow), "claims_digest": _digest(claims)}
    if (not isinstance(review, dict) or review.get("semantic_complete") is not True
            or not isinstance(review.get("review_note"), str) or not review["review_note"].strip()
            or any(type(review.get(key)) is not type(value) or review[key] != value for key, value in expected.items())):
        result["gaps"].append("缺少匹配此源码、范围、候选修订及映射的独立语义审核")
        return result
    result.update(status="reviewed", semantic_complete=True, review_digest=_digest(review))
    return result


def inspect_entry(entry, root):
    folder = Path(root) / "resources/upstream" / entry["source"] / "programs/src"
    files, methods, calls, gaps, inherited = [], [], set(), [], set()
    missing = []
    seeds = set(entry.get("entry_files") or [])
    for path in entry.get("files", []):
        target = (folder / (path + ".txt")).resolve()
        if not target.is_relative_to(folder.resolve()) or not target.is_file():
            missing.append(path)
            continue
        data = target.read_bytes()
        text = data.decode("utf-8-sig")
        files.append({"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                      "entry_file": path in seeds})
        if path not in seeds:
            continue
        if path.endswith(".py"):
            try:
                tree = ast.parse(text, filename=path)
            except SyntaxError as error:
                gaps.append(f"{path}:{error.lineno} 语法错误")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    inherited.update(ast.unparse(base) for base in node.bases)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({"path": path, "name": node.name, "line": node.lineno,
                                    "end_line": node.end_lineno})
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func)
                    if name.startswith("self."):
                        calls.add(name)
        elif path.endswith(".ts"):
            for match in re.finditer(r"\b(operatorFunc)\s*\(", text):
                methods.append({"path": path, "name": match[1], "line": text[:match.start()].count("\n") + 1})
            calls.update("thisScript." + name for name in re.findall(r"thisScript\.([A-Za-z_]\w*)\s*\(", text))
    if missing:
        gaps.append("源码快照缺失：" + ", ".join(missing))
    if entry.get("errors"):
        gaps.append("上游依赖解析错误：" + str(entry["errors"]))
    if entry.get("missing_funcs"):
        gaps.append("方案引用缺失组件：" + str(entry["missing_funcs"]))
    source_gaps = list(gaps)
    if entry["id"].startswith("assttyys:scheme:"):
        effective_ids = (entry.get("source_dispatch") or {}).get("effective_func_ids", entry.get("func_ids", []))
        gaps.append("整段方案仍需组合顺序、全局计数、配置和切换规则：" +
                    ",".join(f"{fid:03d}" for fid in effective_ids))
    elif entry["source"] == "assttyys":
        if methods:
            gaps.append("需完整转换自定义 operatorFunc 及共享变量/配置分支")
        else:
            gaps.append("需核对声明式 operator 的重测、资源消耗与停止边界")
    else:
        gaps.append(f"需完整转换 {len(methods)} 个入口/本地方法及继承实现")
        if inherited:
            gaps.append("继承契约：" + ",".join(sorted(inherited)))
    return {"entry_id": entry["id"], "source": entry["source"], "title": entry["title"],
            "kind": entry["kind"], "variant": entry.get("variant"),
            "fingerprint": entry["fingerprint"], "commit": entry.get("commit"),
            "files": files, "source_snapshot_complete": not missing,
            "methods": methods, "calls": sorted(calls), "gaps": gaps, "source_gaps": source_gaps,
            "semantic_gaps": gaps[len(source_gaps):],
            "scheme_definition": entry.get("scheme_definition"), "source_dispatch": entry.get("source_dispatch")}
