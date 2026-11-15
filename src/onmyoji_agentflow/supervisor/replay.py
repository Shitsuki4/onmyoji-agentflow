"""Replay tests: recorded screenshots with the state that must be recognised on each.

Layout inside the workspace::

    tests/<workflow>/<case>/frame.png
    tests/<workflow>/<case>/expect.yaml   # {state: <id> | null, note: ...}

A case passes when the first matching state of the workflow equals ``state``
(``null`` means "no state may match"). Failure screenshots that a repair was
built for are added as new cases, so every later change is checked against all
of them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..workflow.engine import Runner
from ..workflow.schema import Workflow
from ..yamlio import dump_yaml, load_yaml


@dataclass
class CaseResult:
    case: str
    expected: str | None
    got: str | None

    @property
    def ok(self) -> bool:
        return self.expected == self.got


class _NullCtl:
    observe = True

    def sleep(self, s):
        pass


def first_match(wf: Workflow, img: np.ndarray, variables: dict | None = None) -> str | None:
    r = Runner(wf, _NullCtl())
    r.vars = {**(wf.raw.get("vars") or {}), "elapsed_s": 0, "actions": 0, **(variables or {})}
    for st in wf.states:
        r._found = None
        try:
            if r._match(st["when"], img):
                return st["id"]
        except Exception:  # noqa: BLE001 - e.g. OCR unavailable: treat as no match
            continue
    return None


def load_cases(folder: Path) -> list[tuple[str, np.ndarray, dict]]:
    cases = []
    if not folder.exists():
        return cases
    for d in sorted(p for p in folder.iterdir() if p.is_dir()):
        frame, expect = d / "frame.png", d / "expect.yaml"
        if frame.exists() and expect.exists():
            img = cv2.imdecode(np.fromfile(str(frame), np.uint8), cv2.IMREAD_COLOR)
            cases.append((d.name, img, load_yaml(expect) or {}))
    return cases


def run_cases(wf: Workflow, cases) -> list[CaseResult]:
    out = []
    for name, img, exp in cases:
        got = first_match(wf, img, exp.get("vars"))
        out.append(CaseResult(name, exp.get("state"), got))
    return out


def case_files(name: str, workflow: str, img: np.ndarray, state: str | None, note: str = "") -> dict[str, bytes | str]:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("cannot encode frame")
    base = f"tests/{workflow}/{name}"
    return {f"{base}/frame.png": buf.tobytes(), f"{base}/expect.yaml": dump_yaml({"state": state, "note": note})}
