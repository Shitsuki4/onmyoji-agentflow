"""Workflow execution engine (state machine) with built-in failure detection.

Each tick: screenshot -> evaluate states in order -> the first matching state
runs its actions. Failure kinds raised as ``RunFailure.kind``:

* ``timeout``         whole run exceeded ``limits.timeout_s``
* ``unknown_screen``  no state matched for ``limits.unknown_timeout_s``
* ``stuck``           the screen did not change for ``limits.stuck_timeout_s`` although we kept acting
* ``loop``            one state matched more than ``max_repeat`` times in a row
* ``no_progress``     no state marked ``progress: true`` ran for ``limits.no_progress_timeout_s``
* ``device``          the device raised an error
* ``confirm_denied``  the user refused a sensitive operation
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..errors import ConfirmationDenied, DeviceError, RunFailure, WorkflowError
from ..log import logger
from ..vision.colors import color_score, compare_colors, find_multi_color
from ..vision.template import match_template
from .expr import evaluate
from .schema import SENSITIVE, Workflow


@dataclass
class RunResult:
    workflow: str
    status: str                    # success | stopped | failed | limit | observed
    reason: str = ""
    failure_kind: str | None = None
    failed_state: str | None = None
    variables: dict = field(default_factory=dict)
    history: list = field(default_factory=list)   # [(t, state_id)]
    ticks: int = 0
    actions: int = 0
    recognized_ticks: int = 0
    last_frame: np.ndarray | None = None
    started: float = 0.0
    ended: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in ("success", "stopped", "limit", "observed")

    def summary(self) -> dict:
        return {"workflow": self.workflow, "status": self.status, "reason": self.reason,
                "failure_kind": self.failure_kind, "failed_state": self.failed_state,
                "variables": self.variables, "ticks": self.ticks, "actions": self.actions,
                "recognized_ticks": self.recognized_ticks, "duration_s": round(self.ended - self.started, 1),
                "last_states": [s for _, s in self.history[-15:]]}


def _thumb(img: np.ndarray) -> np.ndarray:
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA).astype(np.int16)


class Runner:
    """Runs one workflow on one Controller.

    ``confirm(category, detail) -> bool`` is called before sensitive operations.
    ``max_actions`` limits a trial run; ``observe`` is taken from the controller.
    ``clock``/``sleep`` are injectable for tests.
    """

    def __init__(self, workflow: Workflow, controller, params: dict | None = None, confirm=None,
                 max_actions: int | None = None, max_seconds: float | None = None, clock=time.monotonic,
                 on_event=None, should_stop=None, ocr_reader=None, text_reader=None, initial_vars=None):
        self.wf = workflow
        self.ctl = controller
        self.params = {**workflow.param_defaults(), **(params or {})}
        self.confirm = confirm
        self.max_actions = max_actions
        self.max_seconds = max_seconds
        self.clock = clock
        self.on_event = on_event or (lambda kind, data: None)
        self.should_stop = should_stop or (lambda: False)
        self.ocr_reader = ocr_reader
        # text_reader(img, region) -> [(text, cx, cy)]; injectable for tests (default: rapidocr)
        self.text_reader = text_reader
        self.initial_vars = dict(initial_vars or {})   # e.g. counters carried over from an earlier run
        self._text_cache: dict = {}
        self._text_frame = None
        self._ocr_warned = False
        self.vars: dict = {}
        self._found: tuple[int, int] | None = None
        self._repeat_count = 0

    # ---------------------------------------------------------------- conditions
    def _match(self, cond: dict, img: np.ndarray) -> bool:
        sim = float(cond.get("similarity", self.wf.similarity))
        if "colors" in cond:
            return compare_colors(img, cond["colors"], sim)
        if "res" in cond or "find" in cond or "image" in cond:
            name = cond.get("res") or cond.get("find") or cond.get("image")
            spec = self.wf.resources[name]
            t = spec.get("type")
            if t == "colors":
                return compare_colors(img, spec["points"], float(spec.get("similarity", sim)))
            if t == "find_colors":
                region = cond.get("region", spec["region"])
                # pick: first (default) = first hit in scan order; last / bottom = the lowest hit on
                # screen (e.g. the newest chapter at the bottom of a list); top = the highest hit
                pick = cond.get("pick", spec.get("pick", "first"))
                many = pick in ("last", "bottom", "top")
                pts = find_multi_color(img, region, spec["groups"], float(spec.get("similarity", sim)),
                                       max_results=50 if many else 1)
                if pts:
                    if pick in ("last", "bottom"):
                        self._found = max(pts, key=lambda p: (p[1], p[0]))
                    elif pick == "top":
                        self._found = min(pts, key=lambda p: (p[1], p[0]))
                    else:
                        self._found = pts[0]
                    return True
                return False
            if t == "image":
                ok, score, box = match_template(img, spec["path"], spec.get("roi"),
                                                float(cond.get("threshold", spec.get("threshold", 0.8))))
                if ok:
                    self._found = (box[0], box[1])
                return ok
            raise WorkflowError(f"资源 {name} 的类型 {t} 不能用于判断")
        if "expr" in cond:
            return bool(evaluate(cond["expr"], self._env()))
        if "all" in cond:
            return all(self._match(c, img) for c in cond["all"])
        if "any" in cond:
            return any(self._match(c, img) for c in cond["any"])
        if "not" in cond:
            return not self._match(cond["not"], img)
        if "text" in cond:
            return self._match_text(cond, img)
        if "ocr" in cond:
            spec = self.wf.resources[cond["ocr"]]
            reader = self.ocr_reader
            if reader is None:
                from ..vision.ocr import read_number as reader
            value = reader(img, spec["roi"])
            self.vars[cond["var"]] = value if value is not None else -1
            if "test" in cond:
                return bool(evaluate(cond["test"], self._env()))
            return value is not None
        raise WorkflowError(f"未知条件 {cond}")

    def _match_text(self, cond: dict, img: np.ndarray) -> bool:
        """``{text: 一键领取 | [..], region: [x, y, w, h], pattern: regex, var: name}``: OCR the region and
        look for one of the words (or the regex). On a hit the centre of the text is remembered for
        ``click_found`` (offset is added as usual, default [0, 0, 20, 20] -> use [-10, -10, 10, 10]).
        Without the optional OCR package the condition is simply false (warned once)."""
        from ..vision.ocr import OcrUnavailable, find_text, read_boxes
        region = tuple(int(v) for v in cond.get("region", (0, 0, img.shape[1], img.shape[0])))
        # The cache only lives for one frame. It used to be keyed by id(img), but a freed screenshot's
        # id is reused by the next one, so a new screen could get the old screen's words.
        if self._text_frame is not img:
            self._text_cache.clear()
            self._text_frame = img
        key = region
        boxes = self._text_cache.get(key)
        if boxes is None:
            try:
                boxes = (self.text_reader or read_boxes)(img, region)
            except OcrUnavailable as e:
                if not self._ocr_warned:
                    self._ocr_warned = True
                    logger.warning("[%s] %s；文字条件一律当作没认出", self.wf.name, e)
                    self.on_event("log", {"state": "", "message": f"{e}；文字条件一律当作没认出"})
                boxes = []
            self._text_cache[key] = boxes
        words = cond.get("text")
        hit = find_text(boxes, words if words not in (None, "") else None, cond.get("pattern"))
        if hit is None:
            return False
        text, cx, cy = hit
        self._found = (cx, cy)
        if cond.get("var"):
            self.vars[cond["var"]] = text
        return True

    def _env(self) -> dict:
        return {**self.params, **self.vars}

    def diagnose_frame(self, img: np.ndarray) -> list[dict]:
        """Per state (and per blocker): does it match, and for colour conditions the fraction of
        matching points. Variables start at the workflow's initial values, as at the start of a
        run, so conditions such as ``runs < max_runs`` can be evaluated."""
        if not self.vars:
            self.vars = {**(self.wf.raw.get("vars") or {}), "elapsed_s": 0, "actions": 0}
        out = []
        items = [(st, False) for st in self.wf.states] + [(b, True) for b in self.wf.blockers]
        for st, is_blocker in items:
            cond = st["when"]
            info = {"id": ("blocker:" + st["id"]) if is_blocker else st["id"], "match": False}
            self._found = None
            try:
                info["match"] = self._match(cond, img)
            except Exception as e:  # noqa: BLE001
                info["error"] = str(e)
            if "colors" in cond:
                info["score"] = round(color_score(img, cond["colors"], self.wf.similarity), 2)
            out.append(info)
        return out

    # ---------------------------------------------------------------- actions
    def _rect(self, v):
        if isinstance(v, str):
            return self.wf.resources[v]["rect"]
        return v

    def _do(self, st: dict, action: dict) -> str | None:
        """Run one action. Returns 'stop' / 'fail:<reason>' to end the run."""
        delay = int(action.get("delay", 500))
        if action.get("first") and self._repeat_count > 1:
            return None  # ``first: true`` actions run only on the first tick of a visit
        if "click_random" in action:
            # assttyys operStepRandom: pick one of the alternatives at random
            import random
            self.ctl.click(random.choice(action["click_random"]), delay, action.get("press_ms"))
            self.vars["actions"] += 1
        elif "click" in action:
            self.ctl.click(self._rect(action["click"]), delay, action.get("press_ms"))
            self.vars["actions"] += 1
        elif "click_found" in action:
            if self._found is None:
                raise WorkflowError(f"state {st['id']}: click_found 前没有 find/image 条件命中")
            x, y = self._found
            ox1, oy1, ox2, oy2 = action.get("offset", [0, 0, 20, 20])
            self.ctl.click([x + ox1, y + oy1, x + ox2, y + oy2], delay, action.get("press_ms"))
            self.vars["actions"] += 1
        elif "swipe" in action:
            v = action["swipe"]
            if isinstance(v, str):
                v = self.wf.resources[v]
            self.ctl.swipe(v["from"], v["to"], delay, action.get("duration_ms"))
            self.vars["actions"] += 1
        elif "back" in action:
            self.ctl.back(delay)
            self.vars["actions"] += 1
        elif "start_app" in action:
            self.ctl.start_app(action["start_app"])
        elif "wait" in action:
            self.ctl.sleep(float(action["wait"]) / 1000)
        elif "set" in action:
            env = self._env()
            for k, expr in action["set"].items():
                self.vars[k] = evaluate(str(expr), env)
        elif "inc" in action:
            self.vars[action["inc"]] = self.vars.get(action["inc"], 0) + int(action.get("by", 1))
        elif "confirm" in action:
            self._confirm(action["confirm"], action.get("detail", st.get("desc", st["id"])))
        elif "log" in action:
            logger.info("[%s] %s", self.wf.name, action["log"])
            self.on_event("log", {"state": st["id"], "message": action["log"]})
        elif "stop" in action:
            return f"stop:{action['stop']}"
        elif "fail" in action:
            return f"fail:{action['fail']}"
        return None

    def _confirm(self, category: str, detail: str):
        if category not in SENSITIVE:
            raise WorkflowError(f"未知的确认类别 {category}")
        if self.ctl.observe:
            return
        if self.confirm is None or not self.confirm(category, f"{self.wf.title}: {detail}"):
            raise ConfirmationDenied(f"用户没有同意：{category}（{detail}）")

    # ---------------------------------------------------------------- main loop
    def run(self) -> RunResult:
        wf = self.wf
        limits = wf.limits
        self.vars = {**(wf.raw.get("vars") or {}), **self.initial_vars, "elapsed_s": 0, "actions": 0}
        res = RunResult(wf.name, "failed", started=self.clock())
        start = res.started
        last_known = start
        last_progress = start
        last_change = start
        prev_thumb = None
        repeat_state, repeat_count = None, 0
        unknown_reported = False
        observe = bool(getattr(self.ctl, "observe", False))
        loop_delay = float(wf.raw.get("loop_delay_ms", 300)) / 1000
        self.on_event("start", {"workflow": wf.name, "observe": observe, "params": self.params})
        try:
            while True:
                now = self.clock()
                self.vars["elapsed_s"] = int(now - start)
                if self.should_stop():
                    res.status, res.reason = "stopped", "用户停止"
                    break
                if wf.raw.get("stop_when") and evaluate(wf.raw["stop_when"], self._env()):
                    res.status, res.reason = "success", "达到结束条件"
                    break
                if self.max_seconds is not None and now - start >= self.max_seconds:
                    res.status, res.reason = ("observed" if observe else "limit"), "达到时间上限"
                    break
                if self.max_actions is not None and self.vars["actions"] >= self.max_actions:
                    res.status, res.reason = "limit", f"达到试跑动作上限 {self.max_actions}"
                    break
                if now - start > limits["timeout_s"]:
                    raise RunFailure("timeout", f"超过 {limits['timeout_s']} 秒没有结束")
                try:
                    img = self.ctl.screenshot()
                except DeviceError as e:
                    raise RunFailure("device", str(e)) from e
                res.last_frame = img
                res.ticks += 1
                thumb = _thumb(img)
                if prev_thumb is None or float(np.mean(np.abs(thumb - prev_thumb))) > 1.5:
                    last_change = now
                prev_thumb = thumb

                self._found = None
                matched = None
                for st in wf.states:
                    self._found = None
                    if self._match(st["when"], img):
                        matched = st
                        break
                if matched is None:
                    for b in wf.blockers:
                        self._found = None
                        if self._match(b["when"], img):
                            res.history.append((round(now - start, 2), "blocker:" + b["id"]))
                            raise RunFailure("prerequisite", "前置条件没满足：" + b["message"], b["id"])
                    if not unknown_reported and now - last_known >= float(limits.get("unknown_sample_s", 10)):
                        unknown_reported = True
                        self.on_event("unknown", {"frame": img, "after_state": repeat_state,
                                                  "seconds": round(now - last_known, 1)})
                    if not observe and now - last_known > limits["unknown_timeout_s"]:
                        msg = f"{limits['unknown_timeout_s']} 秒内认不出当前画面"
                        if wf.requires:
                            msg += "（先确认账号满足：" + "、".join(wf.requires) + "）"
                        raise RunFailure("unknown_screen", msg)
                    self.ctl.sleep(loop_delay)
                    continue
                last_known = now
                unknown_reported = False
                res.recognized_ticks += 1
                res.history.append((round(now - start, 2), matched["id"]))
                self.on_event("state", {"state": matched["id"], "vars": dict(self.vars)})
                if matched["id"] == repeat_state:
                    repeat_count += 1
                else:
                    repeat_state, repeat_count = matched["id"], 1
                self._repeat_count = repeat_count
                max_repeat = int(matched.get("max_repeat", limits["max_repeat"]))
                if not observe and repeat_count > max_repeat:
                    if matched.get("on_repeat", "fail") == "stop":
                        res.status = "success"
                        res.reason = matched.get("repeat_reason", f"{matched['id']} 连续出现 {repeat_count} 次，按设定结束")
                        break
                    raise RunFailure("loop", f"状态 {matched['id']} 连续出现 {repeat_count} 次", matched["id"])
                if not observe:
                    if now - last_change > limits["stuck_timeout_s"]:
                        raise RunFailure("stuck", f"画面 {limits['stuck_timeout_s']} 秒没有变化", matched["id"])
                    if now - last_progress > limits["no_progress_timeout_s"]:
                        raise RunFailure("no_progress", f"{limits['no_progress_timeout_s']} 秒没有进展", matched["id"])
                if matched.get("sensitive"):
                    self._confirm(matched["sensitive"], matched.get("desc", matched["id"]))
                end = None
                for action in matched.get("do", []) or []:
                    end = self._do(matched, action)
                    if end:
                        break
                if matched.get("progress"):
                    last_progress = self.clock()
                if end:
                    kind, _, reason = end.partition(":")
                    if kind == "stop":
                        res.status, res.reason = "success", reason or "工作流结束"
                        break
                    raise RunFailure("workflow_fail", reason, matched["id"])
                self.ctl.sleep(loop_delay)
        except RunFailure as f:
            res.status, res.reason, res.failure_kind, res.failed_state = "failed", f.message, f.kind, f.state
        except ConfirmationDenied as e:
            res.status, res.reason, res.failure_kind = "failed", str(e), "confirm_denied"
        except DeviceError as e:
            res.status, res.reason, res.failure_kind = "failed", str(e), "device"
        res.ended = self.clock()
        res.actions = self.vars.get("actions", 0)
        res.variables = {k: v for k, v in self.vars.items()}
        self.on_event("end", res.summary())
        logger.info("[%s] %s: %s", wf.name, res.status, res.reason)
        return res
