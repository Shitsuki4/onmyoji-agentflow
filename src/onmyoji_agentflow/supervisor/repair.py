"""Repair proposals: a small patch language the LLM (or a user) can use on a workflow.

Ops (JSON)::

    {"op": "set", "path": "limits.stuck_timeout_s", "value": 180}          # params
    {"op": "set", "path": "params.max_runs.default", "value": 10}           # params
    {"op": "set_delay", "state": "prepare", "action": 0, "value": 1500}     # params
    {"op": "set_similarity", "state": "prepare", "value": 90}               # params
    {"op": "recapture_colors", "state": "prepare", "points": [[x, y], ...]} # recognition
    {"op": "add_state", "state": {...}, "before": "id"}                     # workflow
    {"op": "replace_state", "state": {...}}                                  # workflow
    {"op": "remove_state", "id": "..."}                                      # workflow

``recapture_colors`` takes the colours from the failure screenshot itself, so
the model only chooses points and cannot invent colours. The change kind is
derived from the ops, never taken from the model.
"""
from __future__ import annotations

import copy

import numpy as np

from ..errors import WorkflowError

PARAM_PATH_PREFIXES = ("limits.", "params.", "similarity", "loop_delay_ms")
KIND_ORDER = {"params": 0, "recognition": 1, "workflow": 2}


def classify(ops: list[dict]) -> str:
    kind = "params"
    for op in ops:
        o = op.get("op")
        if o in ("set", "set_delay", "set_similarity"):
            k = "params"
            if o == "set" and not str(op.get("path", "")).startswith(PARAM_PATH_PREFIXES):
                k = "workflow"
        elif o == "recapture_colors":
            k = "recognition"
        elif o in ("add_state", "replace_state", "remove_state"):
            k = "workflow"
        else:
            raise WorkflowError(f"未知的修复操作 {o}")
        if KIND_ORDER[k] > KIND_ORDER[kind]:
            kind = k
    return kind


def _state(raw: dict, sid: str) -> dict:
    for st in raw["states"]:
        if st["id"] == sid:
            return st
    raise WorkflowError(f"没有状态 {sid}")


def _sample(img: np.ndarray, x: int, y: int) -> str:
    b, g, r = (int(v) for v in img[int(y), int(x)][:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def apply_ops(raw: dict, ops: list[dict], frame: np.ndarray | None = None) -> dict:
    out = copy.deepcopy(raw)
    for op in ops:
        o = op["op"]
        if o == "set":
            parts = str(op["path"]).split(".")
            cur = out
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
                if not isinstance(cur, dict):
                    raise WorkflowError(f"路径 {op['path']} 不是对象")
            cur[parts[-1]] = op["value"]
        elif o == "set_delay":
            st = _state(out, op["state"])
            st["do"][int(op.get("action", 0))]["delay"] = int(op["value"])
        elif o == "set_similarity":
            st = _state(out, op["state"])
            st["when"]["similarity"] = float(op["value"])
        elif o == "recapture_colors":
            if frame is None:
                raise WorkflowError("recapture_colors 需要失败时的截图")
            st = _state(out, op["state"])
            pts = op["points"]
            if not (3 <= len(pts) <= 30):
                raise WorkflowError("recapture_colors 需要 3 到 30 个点")
            h, w = frame.shape[:2]
            colors = []
            for x, y in pts:
                if not (0 <= int(x) < w and 0 <= int(y) < h):
                    raise WorkflowError(f"点 ({x},{y}) 超出画面")
                colors.append([int(x), int(y), _sample(frame, x, y)])
            st["when"] = {"colors": colors}
            st["recaptured"] = True
        elif o == "add_state":
            new = op["state"]
            ids = [s["id"] for s in out["states"]]
            if op.get("before") in ids:
                out["states"].insert(ids.index(op["before"]), new)
            else:
                out["states"].append(new)
        elif o == "replace_state":
            new = op["state"]
            ids = [s["id"] for s in out["states"]]
            if new.get("id") not in ids:
                raise WorkflowError(f"没有状态 {new.get('id')}")
            out["states"][ids.index(new["id"])] = new
        elif o == "remove_state":
            out["states"] = [s for s in out["states"] if s["id"] != op["id"]]
        else:
            raise WorkflowError(f"未知的修复操作 {o}")
    return out


def sensitive_preserved(before, after) -> bool:
    """A repair may never drop a confirmation that the original workflow had."""
    return before.sensitive_categories() <= after.sensitive_categories()
