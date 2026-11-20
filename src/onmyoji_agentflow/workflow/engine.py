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

from ..errors import BudgetExceeded, ConfirmationDenied, DeviceError, RunFailure, WorkflowError
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
    business_result: str = "unknown"  # completed | already_done | blocked | skipped | unknown
    evidence: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ("success", "stopped", "limit", "observed")

    @property
    def execution_ok(self) -> bool:
        """Whether the state machine stopped without an execution failure.

        This deliberately does not imply that the game task was completed.  A
        limited trial, an observation run, and a manual stop are all valid
        executions but are not business receipts.
        """
        return self.status in ("success", "stopped", "limit", "observed")

    @property
    def business_ok(self) -> bool:
        return (self.status == "success" and self.business_result in ("completed", "already_done")
                and bool(self.evidence.get("verified")))

    def summary(self) -> dict:
        return {"workflow": self.workflow, "status": self.status, "reason": self.reason,
                "failure_kind": self.failure_kind, "failed_state": self.failed_state,
                "variables": self.variables, "ticks": self.ticks, "actions": self.actions,
                "recognized_ticks": self.recognized_ticks, "duration_s": round(self.ended - self.started, 1),
                "last_states": [s for _, s in self.history[-15:]],
                "execution_ok": self.execution_ok, "business_result": self.business_result,
                "business_ok": self.business_ok, "evidence": self.evidence}


def _thumb(img: np.ndarray) -> np.ndarray:
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA).astype(np.int16)


class _ControlStop(Exception):
    pass


class Runner:
    """Runs one workflow on one Controller.

    ``confirm(category, detail) -> bool`` is called before sensitive operations.
    ``max_actions`` limits a trial run; ``observe`` is taken from the controller.
    ``clock``/``sleep`` are injectable for tests.
    """

    def __init__(self, workflow: Workflow, controller, params: dict | None = None, confirm=None,
                 max_actions: int | None = None, max_seconds: float | None = None, clock=time.monotonic,
                 on_event=None, should_stop=None, ocr_reader=None, text_reader=None, initial_vars=None,
                 validate_params: bool = True, before_input=None, after_input=None, strict_ocr=False):
        self.wf = workflow
        self.ctl = controller
        self.params = workflow.validate_params(params or {}) if validate_params else {
            **workflow.param_defaults(), **(params or {})}
        self.confirm = confirm
        self.max_actions = max_actions
        self.max_seconds = max_seconds
        self.clock = clock
        self.on_event = on_event or (lambda kind, data: None)
        self.should_stop = should_stop or (lambda: False)
        self.before_input = before_input or (lambda state, action, variables: None)
        self.after_input = after_input or (lambda state, action, variables: None)
        self.strict_ocr = strict_ocr
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
        self._run_started = 0.0
        self._stop_evidence: dict = {}
        self._frame: np.ndarray | None = None
        self._stop_business_result = "unknown"
        self._current_state = {}
        self._base_sleep = controller.sleep

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
        if "text_param" in cond:
            value = self.params[cond["text_param"]]
            if not value:
                return False
            return self._match_text({**cond, "text": str(value)}, img)
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
                if self.text_reader:
                    boxes = self.text_reader(img, region)
                else:
                    full = self._text_cache.get("full")
                    if full is None:
                        full = read_boxes(img, None)
                        self._text_cache["full"] = full
                    region_x, region_y, width, height = region
                    boxes = [(text, coord_x, coord_y) for text, coord_x, coord_y in full
                             if region_x <= coord_x < region_x + width and region_y <= coord_y < region_y + height]
            except OcrUnavailable as e:
                if not self._ocr_warned:
                    self._ocr_warned = True
                    self.on_event("log", {"state": "", "message": f"{e}；暂停输入，不能以否定条件绕过 OCR"})
                raise
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

    def _action_boundary(self, input_action: bool = True) -> str | None:
        """Check cancellation/deadline immediately before every device input."""
        if getattr(self.ctl, "observe", False):
            return None
        mode = self.should_stop()
        if mode is True or mode == "immediate":
            return "stopped:收到停止请求，未继续输入"
        if mode == "after_battle":
            state_id = self._current_state.get("id", "")
            phase = self._current_state.get("phase")
            if phase is None:
                if state_id.startswith(("settle_", "result_")):
                    phase = "settlement"
                elif state_id in ("in_battle", "battle_manual", "battle_start"):
                    phase = "battle"
            if phase not in ("battle", "settlement"):
                return "stopped:当前战斗已结束，未开始下一场"
        elapsed = self.clock() - self._run_started
        if self.max_seconds is not None and elapsed >= self.max_seconds:
            return "limit:达到时间上限，未继续输入"
        if elapsed > self.wf.limits["timeout_s"]:
            raise RunFailure("timeout", "达到工作流时间上限，未继续输入")
        if input_action and self.max_actions is not None and self.vars.get("actions", 0) >= self.max_actions:
            return f"limit:达到试跑动作上限 {self.max_actions}"
        return None

    def _sleep(self, seconds):
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            boundary = self._action_boundary(input_action=False)
            if boundary:
                raise _ControlStop(boundary)
            duration = min(remaining, 0.25)
            self._base_sleep(duration)
            remaining -= duration

    def _input(self, state, action, operation):
        if self.ctl.observe:
            operation()
            return None
        boundary = self._action_boundary()
        if boundary:
            return boundary
        authorization = self.before_input({**state, "repeat_count": self._repeat_count}, action, self.vars)
        boundary = self._action_boundary()
        if boundary:
            if callable(authorization):
                authorization(False)
            return boundary
        self.vars["actions"] += 1
        try:
            operation()
        finally:
            if callable(authorization):
                authorization(True)
            self.after_input(state, action, self.vars)
        return None

    def _do(self, st: dict, action: dict) -> str | None:
        """Run one action. Returns 'stop' / 'fail:<reason>' to end the run."""
        delay = int(action.get("delay", 500))
        if action.get("first") and self._repeat_count > 1:
            return None  # ``first: true`` actions run only on the first tick of a visit
        boundary = self._action_boundary(input_action=False)
        if boundary:
            return boundary
        if "click_random" in action:
            import random
            return self._input(st, action, lambda: self.ctl.click(random.choice(action["click_random"]), delay,
                                                                 action.get("press_ms")))
        elif "click" in action:
            return self._input(st, action, lambda: self.ctl.click(self._rect(action["click"]), delay,
                                                                 action.get("press_ms")))
        elif "click_found" in action:
            if self._found is None:
                raise WorkflowError(f"state {st['id']}: click_found 前没有 find/image 条件命中")
            x, y = self._found
            ox1, oy1, ox2, oy2 = action.get("offset", [0, 0, 20, 20])
            return self._input(st, action, lambda: self.ctl.click([x + ox1, y + oy1, x + ox2, y + oy2], delay,
                                                                 action.get("press_ms")))
        elif "select_foster" in action:
            if self.ctl.observe:
                return None
            from ..foster import FosterSelector
            from ..vision.ocr import read_boxes
            from .schema import bundled_dir
            spec = action["select_foster"]
            if not hasattr(self, "_foster_selector"):
                self._foster_selector = FosterSelector(spec.get("max_pages", 30))
            reader = self.text_reader or read_boxes
            step = self._foster_selector.step(reader(self._frame, [200, 145, 430, 460]),
                reader(self._frame, [760, 175, 245, 340]), self._frame,
                bundled_dir() / "resources" / "oas-foster")
            result = self._do(st, step)
            if self._foster_selector.phase == "selected":
                self.vars["selected"] = 1
            return result
        elif "select_foster_unit" in action:
            if self._frame is None:
                return "stop:没有可用于寄养式神核对的当前画面"
            from ..vision.ocr import OcrUnavailable, find_text, read_boxes
            spec = action["select_foster_unit"]
            region = tuple(spec.get("region", [0, 450, 520, 230]))
            try:
                boxes = (self.text_reader or read_boxes)(self._frame, region)
            except OcrUnavailable:
                boxes = []
            hits = [find_text(boxes, word) for word in spec["required_text"]]
            hits = [h for h in hits if h is not None]
            if (len(hits) < len(spec["required_text"]) or
                    max((hit[1] for hit in hits), default=0) - min((hit[1] for hit in hits), default=0) > 70):
                self._stop_business_result = "blocked"
                self._stop_evidence = {"verified": False, "reason": "没有同时识别到明确的安全狗粮文字"}
                return "stop:没有识别到明确的可用白达摩，已暂停并保留截图"
            x = sum(h[1] for h in hits) / len(hits)
            y = sum(h[2] for h in hits) / len(hits)
            radius = int(spec.get("radius", 45))
            result = self._input(st, action, lambda: self.ctl.click([x - radius, y - radius, x + radius, y + radius],
                                                                   int(spec.get("delay", delay))))
            if result is None:
                self.vars["unit_selected"] = 1
            return result
        elif "swipe" in action:
            v = action["swipe"]
            if isinstance(v, str):
                v = self.wf.resources[v]
            return self._input(st, action, lambda: self.ctl.swipe(v["from"], v["to"], delay, action.get("duration_ms")))
        elif "back" in action:
            return self._input(st, action, lambda: self.ctl.back(delay))
        elif "start_app" in action:
            return self._input(st, action, lambda: self.ctl.start_app(action["start_app"]))
        elif "wait" in action:
            self._sleep(float(action["wait"]) / 1000)
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
        elif "scan_tasks" in action:
            from ..tasks import TaskScanner, parse_task_page
            spec = action["scan_tasks"]
            from ..vision.ocr import OcrUnavailable, read_boxes
            records = []
            step = None
            try:
                boxes = (self.text_reader or read_boxes)(self._frame, spec.get("region", [365, 225, 760, 370]))
                records = parse_task_page(boxes)
                scope = spec["scope"]
                if spec.get("paginate"):
                    scanners = getattr(self, "_task_scanners", None)
                    if scanners is None:
                        scanners = self._task_scanners = {}
                    scanner = scanners.setdefault(scope, TaskScanner(scope, self.params["max_pages"]))
                    step, record = scanner.step(records)
                    self.vars[f"{scope}_pages"] = scanner.pages
                    self.vars[f"{scope}_done"] = int(scanner.finished)
                    self.vars[f"{scope}_coverage"] = int(scanner.complete)
                    if not record:
                        records = []
                    if scanner.finished:
                        self.on_event("task_scan_complete", {"scope": scope, "pages": scanner.pages,
                            "complete": scanner.complete, "verified": not self.ctl.observe,
                            "frame": self._frame, "task_keys": sorted(scanner.rows)})
                self.on_event("task_scan", {"scope": scope, "tasks": records, "frame": self._frame,
                                              "verified": not self.ctl.observe})
            except OcrUnavailable as error:
                self.on_event("task_scan", {"scope": spec.get("scope") or "daily", "tasks": [],
                                              "frame": self._frame, "verified": False, "error": str(error)})
            self.vars["scanned"] = self.vars.get("scanned", 0) + len(records)
            if spec.get("paginate") and step:
                return self._do(st, step)
        elif "receipt" in action:
            spec = action["receipt"]
            receipt = {**spec, "vars": dict(self.vars), "frame": self._frame}
            if spec.get("key_param"):
                receipt["identity"] = self.params[spec["key_param"]]
            if spec["kind"] == "foster" and hasattr(self, "_foster_selector") and self._foster_selector.best:
                from dataclasses import asdict
                receipt["candidate"] = asdict(self._foster_selector.best)
            if spec.get("countdown_region") and self._frame is not None:
                from ..vision.ocr import OcrUnavailable, read_boxes
                try:
                    boxes = (self.text_reader or read_boxes)(self._frame, spec["countdown_region"])
                    text = " ".join(box[0] for box in boxes)
                    receipt["vars"][f"{spec['kind']}_timer"] = text
                except OcrUnavailable:
                    receipt["vars"][f"{spec['kind']}_timer"] = ""
            if not self.ctl.observe:
                self.on_event("receipt", receipt)
        elif "stop" in action:
            stop = action["stop"]
            if isinstance(stop, dict):
                reason = str(stop.get("reason") or "工作流结束")
                self._stop_business_result = str(stop.get("result") or "unknown")
                self._stop_evidence = dict(stop.get("evidence") or {})
                if "verified" in stop:
                    self._stop_evidence["verified"] = bool(stop["verified"])
            else:
                reason = str(stop)
                self._stop_business_result = str(action.get("result") or st.get("result") or "unknown")
                self._stop_evidence = dict(action.get("evidence") or {})
            return f"stop:{reason}"
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
        self._run_started = start
        self._stop_business_result = str(wf.raw.get("default_result") or "unknown")
        self._stop_evidence = {}
        last_known = start
        last_progress = start
        last_change = start
        prev_thumb = None
        repeat_state, repeat_count = None, 0
        unknown_reported = False
        observe = bool(getattr(self.ctl, "observe", False))
        loop_delay = float(wf.raw.get("loop_delay_ms", 300)) / 1000
        self.ctl.sleep = self._sleep
        self.on_event("start", {"workflow": wf.name, "observe": observe, "params": self.params})
        try:
            while True:
                now = self.clock()
                self.vars["elapsed_s"] = int(now - start)
                mode = self.should_stop()
                if mode is True or mode == "immediate":
                    res.status, res.reason = "stopped", "用户停止"
                    break
                if wf.raw.get("stop_when") and evaluate(wf.raw["stop_when"], self._env()):
                    res.status, res.reason = "success", "达到结束条件"
                    res.business_result = "completed"
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
                self._frame = img
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
                self._current_state = matched
                boundary = self._action_boundary(input_action=False)
                if boundary:
                    res.status, _, res.reason = boundary.partition(":")
                    break
                max_repeat = int(matched.get("max_repeat", limits["max_repeat"]))
                if not observe and repeat_count > max_repeat:
                    if matched.get("on_repeat", "fail") == "stop":
                        res.status = "success"
                        res.reason = matched.get("repeat_reason", f"{matched['id']} 连续出现 {repeat_count} 次，按设定结束")
                        res.business_result = matched.get("repeat_result", "blocked")
                        res.evidence = {"terminal_state": matched["id"], "verified": False}
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
                        res.business_result = self._stop_business_result
                        res.evidence = {"terminal_state": matched["id"], **self._stop_evidence}
                        break
                    if kind == "limit":
                        res.status, res.reason = "limit", reason or "达到限制"
                        break
                    if kind == "stopped":
                        res.status, res.reason = "stopped", reason or "用户停止"
                        break
                    raise RunFailure("workflow_fail", reason, matched["id"])
                self.ctl.sleep(loop_delay)
        except RunFailure as f:
            res.status, res.reason, res.failure_kind, res.failed_state = "failed", f.message, f.kind, f.state
        except ConfirmationDenied as e:
            res.status, res.reason, res.failure_kind = "failed", str(e), "confirm_denied"
        except DeviceError as e:
            res.status, res.reason, res.failure_kind = "failed", str(e), "device"
        except BudgetExceeded as e:
            res.status, res.reason, res.failure_kind = "failed", str(e), "budget"
        except _ControlStop as stopped:
            res.status, _, res.reason = str(stopped).partition(":")
        except Exception as error:
            from ..vision.ocr import OcrUnavailable
            res.status = "failed"
            res.reason = f"{type(error).__name__}: {error}"
            res.failure_kind = "recognition" if isinstance(error, OcrUnavailable) else "workflow_error"
            res.failed_state = self._current_state.get("id")
            if not isinstance(error, OcrUnavailable):
                import traceback
                res.evidence["traceback"] = traceback.format_exc()
            self.on_event("unknown", {"frame": res.last_frame, "after_state": repeat_state,
                                       "error": str(error), "seconds": 0})
        finally:
            self.ctl.sleep = self._base_sleep
        res.ended = self.clock()
        res.actions = self.vars.get("actions", 0)
        res.variables = {k: v for k, v in self.vars.items()}
        if res.status == "failed":
            res.business_result = "failed"
        elif res.status == "success" and res.business_result == "unknown":
            res.business_result = self._stop_business_result
        if observe:
            res.evidence["verified"] = False
        self.on_event("end", res.summary())
        logger.info("[%s] %s: %s", wf.name, res.status, res.reason)
        return res
