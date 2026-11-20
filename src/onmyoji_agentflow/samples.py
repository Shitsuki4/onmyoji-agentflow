"""Local sample catalogue, annotation and positive/negative replay."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np

from .errors import WorkflowError


class Samples:
    def __init__(self, store, directory):
        self.store = store
        self.directory = Path(directory)

    def add(self, frame, workflow, kind="unknown", context=None, run_id=None):
        if frame is None or frame.size == 0:
            raise ValueError("样本截图不可读")
        thumb = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (96, 54))
        digest = hashlib.sha256(thumb.tobytes()).hexdigest()
        small = cv2.resize(thumb, (17, 16))
        perceptual = np.packbits(small[:, 1:] > small[:, :-1]).tobytes().hex()
        old = self.store.query("SELECT * FROM samples WHERE workflow=? AND kind=? ORDER BY id DESC LIMIT 100",
                               (workflow, kind))
        for row in old:
            previous = json.loads(row["context"] or "{}")
            if previous.get("digest") == digest:
                return row
            old_hash = previous.get("perceptual")
            if old_hash and (int(old_hash, 16) ^ int(perceptual, 16)).bit_count() <= 4:
                old_frame = cv2.imdecode(np.fromfile(row["path"], np.uint8), cv2.IMREAD_GRAYSCALE)
                if old_frame is not None:
                    old_thumb = cv2.resize(old_frame, (96, 54)).astype(float)
                    if float(np.mean(np.abs(old_thumb - thumb))) <= 2:
                        return row
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{time.time_ns()}-{digest[:12]}.png"
        cv2.imencode(".png", frame)[1].tofile(str(path))
        cursor = self.store.execute("INSERT INTO samples(run_id,workflow,kind,path,context,created) VALUES (?,?,?,?,?,?)",
                                    (run_id, workflow, kind, str(path),
                                     json.dumps({**(context or {}), "digest": digest, "perceptual": perceptual}, ensure_ascii=False), time.time()))
        return self.get(cursor.lastrowid)

    def get(self, sample_id):
        rows = self.store.query("SELECT * FROM samples WHERE id=?", (sample_id,))
        if not rows:
            raise ValueError("没有该样本")
        return rows[0]

    def list(self, workflow=None):
        if workflow:
            return self.store.query("SELECT * FROM samples WHERE workflow=? ORDER BY id DESC LIMIT 200", (workflow,))
        return self.store.query("SELECT * FROM samples ORDER BY id DESC LIMIT 200")

    def annotate(self, sample_id, annotation):
        self.get(sample_id)
        if not isinstance(annotation, dict) or "state" not in annotation:
            raise ValueError("标注必须提供 state，反例使用 null")
        if set(annotation) - {"state", "vars", "note", "ocr_regions", "allowed_actions"}:
            raise ValueError("未知标注字段")
        if annotation["state"] is not None and not isinstance(annotation["state"], str):
            raise ValueError("state 需要状态名或 null")
        if not isinstance(annotation.get("vars", {}), dict):
            raise ValueError("vars 需要对象")
        if not isinstance(annotation.get("allowed_actions", []), list):
            raise ValueError("allowed_actions 需要动作名列表")
        for region in annotation.get("ocr_regions", []):
            if not isinstance(region, list) or len(region) != 4 or not all(isinstance(value, (int, float)) for value in region):
                raise ValueError("ocr_regions 使用 [x,y,w,h]")
        self.store.execute("UPDATE samples SET annotation=? WHERE id=?",
                           (json.dumps(annotation, ensure_ascii=False), sample_id))
        return self.get(sample_id)

    def replay(self, workflow):
        from .supervisor.replay import run_cases
        cases = []
        for row in self.list(workflow.name):
            if row["annotation"]:
                try:
                    image = cv2.imdecode(np.fromfile(row["path"], np.uint8), cv2.IMREAD_COLOR)
                except OSError:
                    image = None
                cases.append((str(row["id"]), image, json.loads(row["annotation"])))
        results = run_cases(workflow, cases)
        positive = sum(case[2].get("state") is not None for case in cases)
        negative = len(cases) - positive
        return {"ok": bool(positive and negative) and all(result.ok for result in results),
                "coverage": "sufficient" if positive and negative else "insufficient",
                "positive": positive, "negative": negative,
                "cases": [vars(result) for result in results]}
