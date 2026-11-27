"""Convert OnmyojiAutoScript (GPLv3) recognition assets.

Input: an OAS checkout (``tasks/<Task>/**/{image,click,swipe,ocr,long_click,list}.json``
and ``tasks/GameUi/default_pages.py``). Output: ``<out>/<Task>.yaml`` plus the
template images copied to ``<out>/images/<Task>/``, and ``<out>/navigation.yaml``.

Resource names follow OAS's generated ``assets.py``: ``I_`` image, ``C_`` click,
``S_`` swipe, ``O_`` ocr, ``L_`` long click, ``LIST_`` list, all upper case.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path


from ..yamlio import dump_yaml

PREFIX = {"image": "I_", "click": "C_", "swipe": "S_", "ocr": "O_", "long_click": "L_", "list": "LIST_"}


def classify(item: dict) -> str | None:
    """Same rules as OAS dev_tools/assets_extract.py: decide the rule type from the keys."""
    if "imageName" in item:
        return "image"
    if "duration" in item:
        return "long_click"
    if "list" in item and "direction" in item:
        return "list"
    if "keyword" in item:
        return "ocr"
    if "mode" in item and "itemName" in item:
        return "swipe"
    if "itemName" in item and "roiFront" in item:
        return "click"
    return None


def _roi(text) -> list[int]:
    if isinstance(text, (list, tuple)):
        return [int(round(float(v))) for v in text]
    return [int(round(float(v))) for v in str(text).split(",")]


def _xywh_to_rect(r):
    x, y, w, h = r
    return [x, y, x + w, y + h]


def convert_task(task_dir: Path, out_dir: Path, task_name: str | None = None) -> dict:
    """Convert one OAS task folder. Returns {"resources": n, "images": n, "missing": [...]}."""
    task_name = task_name or task_dir.name
    resources: dict[str, dict] = {}
    missing: list[str] = []
    img_out = out_dir / "images" / task_name
    n_images = 0
    for jf in sorted(task_dir.rglob("*.json")):
        if any("temp" in part.lower() for part in jf.relative_to(task_dir).parts[:-1]):
            continue   # OAS keeps scratch files in temp/ folders; only look inside the task itself
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        items = data if isinstance(data, list) else [data]
        if not items or not isinstance(items[0], dict):
            continue
        kind = classify(items[0])
        if kind is None:
            continue
        if True:
            for it in items:
                name_src = it.get("itemName") or it.get("name")
                if not name_src:
                    continue
                name = PREFIX[kind] + name_src.upper()
                desc = it.get("description", "")
                if kind == "image":
                    src = jf.parent / it["imageName"]
                    rel = f"images/{task_name}/{jf.parent.relative_to(task_dir).as_posix()}/{it['imageName']}".replace("/./", "/")
                    if src.exists():
                        dst = out_dir / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(src, dst)
                        n_images += 1
                    else:
                        missing.append(str(src))
                    front = _roi(it["roiFront"])
                    resources[name] = {
                        "type": "image", "file": rel, "roi": _roi(it["roiBack"]), "front": front,
                        "threshold": float(it.get("threshold", 0.8)), "desc": desc,
                        "method": it.get("method", "Template matching"),
                        "roi_expand": 2,  # OAS RuleImage.ROI_BACK_EXPAND, before image matching.
                    }
                    if it.get("method") == "Masked template matching":
                        mask = src.with_name(src.stem + "_mask" + src.suffix)
                        if mask.is_file():
                            mask_rel = str(Path(rel).with_name(mask.name)).replace("\\", "/")
                            destination = out_dir / mask_rel
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(mask, destination)
                            resources[name]["mask_file"] = mask_rel
                            n_images += 1
                elif kind == "click":
                    # OAS RuleClick: the click area is roi_front (x, y, w, h)
                    resources[name] = {"type": "click", "rect": _xywh_to_rect(_roi(it["roiFront"])), "desc": desc}
                elif kind == "long_click":
                    resources[name] = {"type": "click", "rect": _xywh_to_rect(_roi(it["roiFront"])),
                                       "press_ms": int(it.get("duration", 1000)), "desc": desc}
                elif kind == "swipe":
                    # OAS RuleSwipe: roi_front = start area, roi_back = end area
                    resources[name] = {"type": "swipe", "from": _xywh_to_rect(_roi(it["roiFront"])),
                                       "to": _xywh_to_rect(_roi(it["roiBack"])), "desc": desc}
                elif kind == "ocr":
                    resources[name] = {"type": "ocr", "roi": _roi(it["roiFront"]), "mode": str(it.get("mode", "Full")),
                                       "keyword": it.get("keyword", ""), "desc": desc}
                elif kind == "list":
                    resources[name] = {"type": "list", "roi": _roi(it["roiBack"]), "direction": it.get("direction"),
                                       "items": it.get("list"), "desc": desc}
    doc = {
        "source": "OnmyojiAutoScript",
        "source_url": "https://github.com/nearaura/OnmyojiAutoScript",
        "license": "GPL-3.0",
        "task": task_name,
        "resources": resources,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{task_name}.yaml").write_text(
        dump_yaml(doc), encoding="utf-8")
    return {"resources": len(resources), "images": n_images, "missing": missing}


def _asset_class_map(tasks_dir: Path) -> dict[str, str]:
    """Map ``GameUiAssets`` -> ``GameUi`` by reading every tasks/*/assets.py."""
    out = {}
    for f in tasks_dir.glob("**/assets.py"):
        for m in re.finditer(r"^class\s+(\w+)\s*[:(]", f.read_text(encoding="utf-8", errors="ignore"), re.M):
            out[m.group(1)] = f.parent.relative_to(tasks_dir).as_posix().replace("/", "_")
    return out


def convert_navigation(tasks_dir: Path, out_dir: Path) -> dict:
    """Parse the complete registry including composites and task-local pages."""
    from .navigation import read_navigation
    doc = read_navigation(tasks_dir, _asset_class_map(tasks_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "navigation.yaml").write_text(dump_yaml(doc), encoding="utf-8")
    return {"pages": len(doc["pages"]), "links": len(doc["links"])}


def convert(oas_root: str | os.PathLike, out_dir: str | os.PathLike, tasks: list[str] | None = None) -> dict:
    root = Path(oas_root)
    tasks_dir = root / "tasks"
    if not tasks_dir.is_dir():
        raise FileNotFoundError(f"{tasks_dir} 不存在：请指向 OnmyojiAutoScript 仓库根目录")
    out = Path(out_dir)
    report = {"tasks": {}}
    candidates = []
    for d in sorted(tasks_dir.iterdir()):
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        if d.name == "Component":
            candidates += [(c, f"Component_{c.name}") for c in sorted(d.iterdir()) if c.is_dir()]
        else:
            candidates.append((d, d.name))
    for d, name in candidates:
        if tasks and name not in tasks:
            continue
        if not any(d.rglob("*.json")):
            continue
        r = convert_task(d, out, name)
        if r["resources"]:
            report["tasks"][name] = r
    try:
        report["navigation"] = convert_navigation(tasks_dir, out)
    except FileNotFoundError:
        report["navigation"] = None
    return report
