"""Convert assttyys_autojs (MIT, Copyright (c) 2019 Chaos) recognition data.

Reads ``src/common/multiDetectColors.ts``, ``multiFindColors.ts``,
``funcList/*.ts`` (the ``operator`` arrays only) and ``schemeList.ts``.
Upstream code is parsed as data, never executed.

Output (under ``out``):
* ``colors.yaml``      - every multiDetectColors / multiFindColors entry
* ``funcs/<id>.yaml``  - each func's operators turned into candidate states;
  ``needs_translation: true`` when the func has custom ``operatorFunc`` logic
* ``schemes.yaml``     - scheme name -> func id list
* ``report.json``      - counts and the funcs that need LLM translation
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..yamlio import dump_yaml
from .jsliteral import extract_literal_after, find_consts, parse

SOURCE = {"source": "assttyys_autojs", "source_url": "https://github.com/zzliux/assttyys_autojs",
          "license": "MIT", "copyright": "Copyright (c) 2019 Chaos"}


def _hex(v) -> str:
    return f"#{int(v) & 0xFFFFFF:06x}"


def points_from_desc(desc) -> list:
    """[1280, 720, [[anchor, x, y, color], ...]] -> [[x, y, '#rrggbb'], ...]."""
    pts = desc[2] if len(desc) >= 3 else desc
    return [[int(p[1]), int(p[2]), _hex(p[3])] for p in pts]


def rect_from_oper(o) -> dict:
    """[anchor, 1280, 720, x1, y1, x2, y2, delay(, press)] -> {rect, delay, press?}."""
    d = {"rect": [int(o[3]), int(o[4]), int(o[5]), int(o[6])], "delay": int(o[7]) if len(o) > 7 else 500}
    if len(o) > 8 and o[8]:
        d["press_ms"] = int(o[8])
    return d


def convert_colors(common: Path) -> dict:
    out = {}
    s = (common / "multiDetectColors.ts").read_text(encoding="utf-8")
    lit, _ = extract_literal_after(s, r"multiDetectColors\s*:\s*\w+\s*=")
    for name, v in parse(lit, find_consts(s)).items():
        out[name] = {"type": "colors", "points": points_from_desc(v["desc"])}
    s = (common / "multiFindColors.ts").read_text(encoding="utf-8")
    lit, _ = extract_literal_after(s, r"multiFindColors\s*:\s*\w+\s*=")
    for name, v in parse(lit, find_consts(s)).items():
        region = v.get("region")
        entry = {"type": "find_colors", "groups": [points_from_desc(g) for g in v["desc"]]}
        entry["region"] = [int(x) for x in region[3:7]] if region else [0, 0, 1280, 720]
        out[name] = entry
    return out


def convert_func(path: Path, colors: dict) -> dict | None:
    s = path.read_text(encoding="utf-8")
    m_id = re.search(r"\bid\s*=\s*(\d+)\s*;", s)
    if not m_id:
        return None
    fid = int(m_id.group(1))
    name = (re.search(r"\bname\s*=\s*'([^']*)'", s) or [None, path.stem])[1]
    desc = (re.search(r"\bdesc\s*=\s*'([^']*)'", s) or [None, ""])[1]
    lit, _ = extract_literal_after(s, r"operator\s*:\s*[\w\[\]]+\s*=")
    operators = []
    error = None
    if lit:
        try:
            raw = parse(lit, find_consts(s))
        except ValueError as e:
            raw, error = [], str(e)
        for k, op in enumerate(raw):
            item: dict = {"index": k}
            d = op.get("desc")
            if isinstance(d, str):
                item["detect"] = d if d in colors else None
                if d not in colors:
                    item["unknown_ref"] = d
            elif isinstance(d, list) and d:
                item["detect_points"] = points_from_desc(d)
            if op.get("oper"):
                item["oper"] = [rect_from_oper(o) for o in op["oper"] if isinstance(o, list) and len(o) >= 7]
            if op.get("operStepRandom"):
                item["oper_step_random"] = [[rect_from_oper(o) for o in step] for step in op["operStepRandom"]]
            if op.get("retest"):
                item["retest_ms"] = int(op["retest"])
            operators.append(item)
    has_func = "operatorFunc" in s
    return {"id": fid, "name": name, "desc": desc, "needs_translation": has_func, "parse_error": error,
            "operators": operators}


def convert_schemes(common: Path) -> dict:
    s = (common / "schemeList.ts").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"schemeName:\s*'([^']*)'.*?list:\s*\[([^\]]*)\]", s, re.S):
        ids = [int(x) for x in re.findall(r"\d+", m.group(2))]
        out[m.group(1)] = ids
    return out


def convert(ass_root: str | os.PathLike, out_dir: str | os.PathLike) -> dict:
    common = Path(ass_root) / "src" / "common"
    if not common.is_dir():
        raise FileNotFoundError(f"{common} 不存在：请指向 assttyys_autojs 仓库根目录")
    out = Path(out_dir)
    (out / "funcs").mkdir(parents=True, exist_ok=True)
    colors = convert_colors(common)
    def dump(p, d):
        p.write_text(dump_yaml(d), encoding="utf-8")
    dump(out / "colors.yaml", {**SOURCE, "similarity": 93, "resources": colors})
    report = {"colors": len(colors), "funcs": 0, "needs_translation": [], "parse_errors": []}
    for f in sorted((common / "funcList").glob("*.ts")):
        func = convert_func(f, colors)
        if not func:
            continue
        dump(out / "funcs" / f"{func['id']:03d}.yaml", {**SOURCE, **func})
        report["funcs"] += 1
        if func["needs_translation"]:
            report["needs_translation"].append(f"{func['id']:03d} {func['name']}")
        if func["parse_error"]:
            report["parse_errors"].append(f"{func['id']:03d}: {func['parse_error']}")
    schemes = convert_schemes(common)
    dump(out / "schemes.yaml", {**SOURCE, "schemes": schemes})
    report["schemes"] = len(schemes)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
