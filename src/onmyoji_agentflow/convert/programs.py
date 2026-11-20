"""Inventory executable upstream entries and snapshot their code as inert text.

This is deliberately separate from resource conversion: an indexed Python/AutoJS
program is not yet an executable format:1 workflow. Never import upstream code.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

from ..yamlio import dump_yaml, load_yaml

CATALOG_VERSION = 1


def _inside(root: Path, path: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve()) and path.is_file()


def _python_imports(root: Path, path: Path, text: str):
    tree = ast.parse(text, filename=path.relative_to(root).as_posix())
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            parent = root
        elif isinstance(node, ast.ImportFrom):
            parent = path.parent
            if node.level:
                for _ in range(node.level - 1):
                    parent = parent.parent
            else:
                parent = root
            prefix = node.module or ""
            names = [prefix] + [f"{prefix}.{a.name}".strip(".") for a in node.names if a.name != "*"]
        else:
            continue
        for name in names:
            target = parent.joinpath(*name.split("."))
            for candidate in (target.with_suffix(".py"), target / "__init__.py"):
                if _inside(root, candidate):
                    yield candidate


def _typescript_imports(root: Path, path: Path, text: str):
    for name in re.findall(r"(?:from\s*|require\(\s*)['\"]([^'\"]+)['\"]", text):
        if name.startswith("@/"):
            target = root / "src" / name[2:]
        elif name.startswith("."):
            target = path.parent / name
        else:
            continue
        for candidate in (target.with_suffix(".ts"), target / "index.ts"):
            if _inside(root, candidate):
                yield candidate


def build_catalog(source: str, root: Path, converted: Path, commit: str = "") -> dict:
    """Write programs/index.yaml and one shared, complete source snapshot.

    OAS entries are all script_task.py files. assttyys entries are every scheme
    and every funcList component, including ones not referenced by a scheme.
    Fingerprints cover transitive local imports, config and recognition assets;
    an unrelated upstream commit alone does not invalidate an entry.
    """
    root, converted = Path(root).resolve(), Path(converted).resolve()
    dest = converted / "programs"
    entries = []
    snapshots = {}
    dependency_cache = {}

    def dependencies(seeds):
        todo, found, errors = list(seeds), set(), []
        while todo:
            path = todo.pop().resolve()
            if path in found or not _inside(root, path):
                continue
            found.add(path)
            if path not in dependency_cache:
                text = path.read_text(encoding="utf-8-sig")
                parser = _python_imports if path.suffix == ".py" else _typescript_imports
                try:
                    refs = list(parser(root, path, text))
                    dependency_cache[path] = (text, refs, None)
                except (SyntaxError, ValueError) as error:
                    dependency_cache[path] = (text, [], str(error))
            text, refs, error = dependency_cache[path]
            snapshots[path.relative_to(root).as_posix()] = text
            if error:
                errors.append(f"{path.relative_to(root).as_posix()}: {error}")
            todo.extend(refs)
        return sorted(p.relative_to(root).as_posix() for p in found), errors

    resource_hashes = {}

    def add(identifier, title, kind, seeds, resource_files, **extra):
        files, errors = dependencies(seeds)
        resource_files = sorted(set(resource_files))
        assets = {}
        for rel in resource_files:
            if rel not in resource_hashes:
                path = converted / rel
                h = hashlib.sha256(path.read_bytes())
                doc = load_yaml(path) or {}
                for spec in (doc.get("resources") or {}).values():
                    image = spec.get("file")
                    if image:
                        img = path.parent / image
                        h.update(img.read_bytes() if _inside(converted, img) else b"MISSING")
                resource_hashes[rel] = h.hexdigest()
            assets[rel] = resource_hashes[rel]
        material = {"version": CATALOG_VERSION, "id": identifier, "extra": extra,
                    "files": {f: hashlib.sha256(snapshots[f].encode()).hexdigest() for f in files},
                    "resources": assets}
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        entries.append({"id": identifier, "source": source, "title": title, "kind": kind,
                        "workflow": f"{source}_" + hashlib.sha256(identifier.encode()).hexdigest()[:12],
                        "fingerprint": digest, "commit": commit, "files": files,
                        "entry_files": sorted(p.relative_to(root).as_posix() for p in seeds),
                        "resource_files": resource_files, "errors": errors, **extra})

    if source == "oas":
        if not (root / "tasks").is_dir():
            raise ValueError("OAS 缺少 tasks 目录")
        for script in sorted((root / "tasks").rglob("script_task.py")):
            if any(part.startswith((".", "__")) for part in script.relative_to(root).parts):
                continue
            task = script.parent.relative_to(root / "tasks").as_posix()
            # Include task-local helpers/config even when OAS loads them dynamically.
            seeds = list(script.parent.rglob("*.py"))
            files, _ = dependencies(seeds)
            task_names = {task.replace("/", "_")}
            for rel in files:
                parts = Path(rel).parts
                if len(parts) >= 3 and parts[0] == "tasks":
                    task_names.add("_".join(parts[1:3]) if parts[1] == "Component" else parts[1])
            refs = [f"{name}.yaml" for name in sorted(task_names) if (converted / f"{name}.yaml").is_file()]
            if (converted / "navigation.yaml").is_file():
                refs.append("navigation.yaml")
            add(f"oas:{task}", task, "task", seeds, refs, entrypoint=script.relative_to(root).as_posix())
            from .recipes import OAS_SCOPES
            for variant, description in OAS_SCOPES.get(task, {}).items():
                add(f"oas:{task}#{variant}", description, "task", seeds, refs,
                    entrypoint=script.relative_to(root).as_posix(), variant=variant, scope_description=description)
    elif source == "assttyys":
        folder = root / "src" / "common" / "funcList"
        funcs = {}
        for script in sorted(folder.glob("*.ts")):
            text = script.read_text(encoding="utf-8-sig")
            match = re.search(r"\bid\s*=\s*(\d+)\s*;", text)
            if match:
                funcs[int(match[1])] = script
                add(f"assttyys:func:{int(match[1]):03d}", script.stem, "component", [script],
                    ["colors.yaml"], func_ids=[int(match[1])])
                from .recipes import ASS_SCOPES
                for variant, description in ASS_SCOPES.get(int(match[1]), {}).items():
                    add(f"assttyys:func:{int(match[1]):03d}#{variant}", description, "task", [script],
                        ["colors.yaml"], func_ids=[int(match[1])], variant=variant, scope_description=description)
        schemes = (load_yaml(converted / "schemes.yaml") or {}).get("schemes") or {}
        scheme_file = root / "src" / "common" / "schemeList.ts"
        for title, ids in sorted(schemes.items()):
            seeds = [funcs[fid] for fid in ids if fid in funcs]
            # Keep the full scheme declaration as source evidence, never evaluate it.
            if scheme_file.is_file():
                seeds.append(scheme_file)
            add("assttyys:scheme:" + title, title, "task", seeds, ["colors.yaml"], func_ids=ids,
                missing_funcs=[fid for fid in ids if fid not in funcs])
    else:
        raise ValueError("source 必须是 assttyys 或 oas")
    for rel, text in snapshots.items():
        path = dest / "src" / (rel + ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    dest.mkdir(parents=True, exist_ok=True)
    doc = {"format": CATALOG_VERSION, "source": source, "commit": commit, "entries": entries}
    (dest / "index.yaml").write_text(dump_yaml(doc), encoding="utf-8")
    return {"tasks": sum(e["kind"] == "task" for e in entries),
            "components": sum(e["kind"] == "component" for e in entries),
            "source_files": len(snapshots), "errors": sum(bool(e["errors"]) for e in entries)}
