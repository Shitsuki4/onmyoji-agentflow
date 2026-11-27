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
import math
import copy
import random
import json
from collections import Counter, deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..errors import BudgetExceeded, ConfirmationDenied, DeviceError, RunFailure, WorkflowError
from ..log import logger
from ..vision.colors import color_score, compare_colors, find_multi_color, mean_rgb_similar
from ..vision.template import match_template
from .expr import evaluate
from .schema import SENSITIVE, Workflow
from .scheme_lifecycle import ACTIVE_SCHEME, MAX_SWITCHES, SWITCH_DELAY_S


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
    oas_schedule: str | None = None
    oas_target: tuple[int, float] | None = None
    oas_wakes: dict[str, tuple[int | None, float] | tuple[int | None, float, dict]] = field(default_factory=dict)

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
                 validate_params: bool = True, before_input=None, after_input=None, strict_ocr=False,
                 single_ocr_reader=None, full_ocr_reader=None):
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
        self.single_ocr_reader = single_ocr_reader
        self.full_ocr_reader = full_ocr_reader
        # text_reader(img, region) -> [(text, cx, cy)]; injectable for tests (default: rapidocr)
        self.text_reader = text_reader
        self.initial_vars = dict(initial_vars or {})   # e.g. counters carried over from an earlier run
        self._text_cache: dict = {}
        self._answer_banks: dict = {}
        self._text_frame = None
        self._ocr_warned = False
        self.vars: dict = {}
        self._found: tuple[int, int] | None = None
        self._found_box = None
        self._repeat_count = 0
        self._run_started = 0.0
        self._stop_evidence: dict = {}
        self._frame: np.ndarray | None = None
        self._stop_business_result = "unknown"
        self._current_state = {}
        self._base_sleep = controller.sleep
        self._actions_taken = 0
        # Successful scans only. Input authorization rechecks and cached
        # handler steps are not workflow screenshot attempts.
        self._screen_captures = 0
        self._navigation_call = None
        self._navigation_call_states = {sid: name for name, spec in
            workflow.raw.get("navigation", {}).get("calls", {}).items() for sid in spec["states"]}
        self._restart_markers = {action["attempt_var"] for state in workflow.states
                                 for action in state.get("do", []) if "restart_app" in action}
        self._recent_taps = deque(maxlen=15)

    # ---------------------------------------------------------------- conditions
    def _match(self, cond: dict, img: np.ndarray) -> bool:
        if "foreground_game" in cond:
            # Only a live/fresh runner capture can accompany the foreground check.
            return (img is self._frame and img.ndim == 3 and img.shape[2] == 3
                    and bool(np.ptp(img[::24, ::24], axis=(0, 1)).any())
                    and self.ctl.device.app_in_foreground(cond["foreground_game"]))
        if "tap_loop" in cond:
            # OAS inspects the last 15 controls including the proposed tap,
            # before sending the tap which would cross its loop threshold.
            if len(self._recent_taps) < 9:
                return False
            counts = Counter([*self._recent_taps, cond["tap_loop"]][-15:])
            top = [n for _, n in counts.most_common(2)]
            return top[0] >= 10 or (len(top) == 2 and top[1] >= 6)
        if "screen_size" in cond:
            size = self.ctl.raw_size if img is self._frame else (img.shape[1], img.shape[0])
            return img.ndim == 3 and img.shape[2] == 3 and tuple(cond["screen_size"]) == size
        sim = float(cond.get("similarity", self.wf.similarity))
        if "colors" in cond:
            return compare_colors(img, cond["colors"], sim)
        if "mean_color" in cond:
            spec = cond["mean_color"]
            return mean_rgb_similar(img, spec["region"], spec["rgb"], spec.get("tolerance", 10))
        if "find_near" in cond:
            from ..vision.colors import nearest_color_match
            spec = cond["find_near"]
            self._found = nearest_color_match(img, self.wf.resources[spec["target"]],
                                              self.wf.resources[spec["reference"]], sim,
                                              spec["max_distance"], spec["max_below"])
            self._found_box = None
            return self._found is not None
        if "find_column" in cond:
            from ..vision.colors import column_color_match
            spec = cond["find_column"]
            self._found = column_color_match(img, self.wf.resources[spec["target"]],
                                             self.wf.resources[spec["reference"]], sim,
                                             spec["x_offsets"], spec["row"])
            self._found_box = None
            return self._found is not None
        if "find_image_above" in cond:
            from ..vision.template import match_template_above
            spec = cond["find_image_above"]
            if not self._match({"res": spec["reference"]}, img):
                return False
            target = self.wf.resources[spec["target"]]
            self._found_box = match_template_above(
                img, target["path"], self._found_box, x_pad=spec["x_pad"], max_above=spec["max_above"],
                min_gap=spec["min_gap"], x_weight=spec["x_weight"], threshold=spec["threshold"],
            )
            self._found = self._found_box[:2] if self._found_box else None
            return self._found is not None
        if "image_grid" in cond:
            return self._match_image_grid(cond["image_grid"], img)
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
                    self._found_box = None
                    if pick in ("last", "bottom"):
                        self._found = max(pts, key=lambda p: (p[1], p[0]))
                    elif pick == "top":
                        self._found = min(pts, key=lambda p: (p[1], p[0]))
                    else:
                        self._found = pts[0]
                    return True
                return False
            if t == "image":
                roi = spec.get("roi")
                if "region_vars" in cond:
                    from ..vision.regions import checked_box
                    roi = checked_box(tuple(self.vars[n] for n in cond["region_vars"]), img, integral=True)
                # An explicit mutated roi_back is NOT expanded again in OAS.
                padding = 0 if "region_vars" in cond else spec.get("roi_expand", 0)
                if roi is not None and padding:
                    x, y, width, height = roi
                    screen_h, screen_w = img.shape[:2]
                    x0, y0 = min(max(0, x - padding), screen_w), min(max(0, y - padding), screen_h)
                    x1, y1 = min(max(0, x + width + padding), screen_w), min(max(0, y + height + padding), screen_h)
                    roi = [x0, y0, max(0, x1 - x0), max(0, y1 - y0)]
                ok, score, box = match_template(img, spec["path"], roi,
                    float(cond.get("threshold", spec.get("threshold", 0.8))),
                    method="Multi-scale template matching" if "scale_range" in cond else spec.get("method", "Template matching"),
                    mask=spec.get("mask_path"),
                    **({"scale_range": cond["scale_range"]} if "scale_range" in cond else {}),
                    **({"template_crop": cond["template_crop"]} if "template_crop" in cond else {}),
                    **({"strict_roi": True} if "region_vars" in cond else {}))
                if ok:
                    self._found = (box[0], box[1])
                    self._found_box = box
                return ok
            raise WorkflowError(f"资源 {name} 的类型 {t} 不能用于判断")
        if "expr" in cond:
            return bool(evaluate(cond["expr"], self._env()))
        if "scheme_history" in cond:
            from .scheme_lifecycle import latest_scheme
            return latest_scheme(getattr(self, "_scheme_history", ()), cond["scheme_history"]) is not None
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
        if "quiz_answer" in cond:
            return self._match_quiz_answer(cond["quiz_answer"], img)
        if "wanted_badge" in cond:
            return self._match_wanted_badge(cond["wanted_badge"], img)
        if "wanted_location" in cond:
            return self._match_wanted_location(cond["wanted_location"], img)
        if "ordered_list" in cond:
            from ..vision.ocr import ordered_list_position, read_boxes
            spec = cond["ordered_list"]
            region = tuple(spec["region"])
            if self._text_frame is not img:
                self._text_cache.clear()
                self._text_frame = img
            key = ("ordered_list", region)
            if key not in self._text_cache:
                self._text_cache[key] = (self.text_reader(img, region) if self.text_reader else
                                         read_boxes(img, region, pad=0, min_score=.6))
            x, y, width, height = region
            rows = [row for row in self._text_cache[key] if x <= row[1] < x + width and y <= row[2] < y + height]
            direction, self._found = ordered_list_position(rows, spec["labels"], spec["target"])
            self._found_box = None
            self.vars[spec["direction_var"]] = direction if direction is not None else 2
            if "selected_row" in spec:
                marker = spec["selected_row"]
                if direction != 0 or self._found is None:
                    return False
                left = marker["x"]
                top = self._found[1] - marker["height"] // 2
                right, bottom = left + marker["width"], top + marker["height"]
                if not 0 <= top < bottom <= img.shape[0] or right > img.shape[1]:
                    return False
                pixels = img[top:bottom, left:right, :3].astype(np.int16)
                reference = np.asarray(marker["rgb"][::-1], dtype=np.int16)
                agreement = (np.abs(pixels - reference) <= marker["tolerance"]).all(axis=2)
                return float(agreement.mean()) >= marker["coverage"]
            return direction is not None
        if "ocr_single" in cond:
            spec = cond["ocr_single"]
            expected = self._literal_ocr_keyword(spec, "equals")
            region = tuple(spec["region"])
            if self._read_single_text(img, region, spec.get("score", .6)) != expected:
                return False
            self._found = region[:2]
            self._found_box = region
            return True
        if "ocr_full" in cond:
            from ..vision.ocr import FullOcrArea, read_full
            from ..vision.regions import checked_box
            spec = cond["ocr_full"]
            keyword = self._literal_ocr_keyword(spec, "keyword")
            if self._text_frame is not img:
                self._text_cache.clear()
                self._text_frame = img
            region, score = tuple(spec["region"]), spec.get("score", .6)
            selection = {key: spec[key] for key in ("selection",) if key in spec}
            key = ("full_area", region, keyword, score, spec.get("selection"))
            if key not in self._text_cache:
                area = (self.full_ocr_reader or read_full)(img, region, keyword, score, **selection)
                # The source's all-zero result is absence, not a usable anchor.
                if (not isinstance(area, (tuple, list)) or len(area) != 4 or
                        any(type(n) not in (int, float) or not math.isfinite(n) for n in area)):
                    raise WorkflowError("ocr_full reader must return a finite xywh box")
                if tuple(area) != (0, 0, 0, 0):
                    checked_box(area, img)
                self._text_cache[key] = area if isinstance(area, FullOcrArea) else tuple(area)
            area = self._text_cache[key]
            if area == (0, 0, 0, 0) or ("box_equals" in spec and area != tuple(spec["box_equals"])):
                return False
            if "evidence" in spec:
                if not isinstance(area, FullOcrArea):
                    raise WorkflowError("ocr_full.evidence requires typed Full OCR provenance")
                if area.keyword_complete != (spec["evidence"] == "complete_keyword"):
                    return False
            self._found, self._found_box = area[:2], area
            return True
        if "ocr" in cond:
            spec = self.wf.resources[cond["ocr"]]
            if cond.get("mode") == "max_hourly_rate":
                return self._match_hourly_rate(cond, img, spec)
            if cond.get("mode") == "text_sequence":
                from ..vision.ocr import read_boxes
                from ..vision.regions import checked_box
                roi = checked_box(spec["roi"], img, integral=True)
                if self._text_frame is not img:
                    self._text_cache.clear()
                    self._text_frame = img
                key = ("sequence", roi)
                if key not in self._text_cache:
                    boxes = (self.text_reader or read_boxes)(img, roi)
                    self._text_cache[key] = [text for text, _, _ in boxes if text and text.strip()]
                lines = self._text_cache[key]
                self.vars[cond["var"]] = json.dumps(lines, ensure_ascii=False) if lines else ""
                return bool(lines)
            mode = cond.get("mode")
            if mode in ("duration_seconds", "cn_hour_minute", "remaining_times", "counter_remaining",
                        "counter_current", "exact_quantity", "shop_stock"):
                from ..vision.ocr import (parse_exact_quantity, parse_oas_cn_hour_minute, parse_oas_counter_current,
                                          parse_oas_counter_remaining, parse_oas_duration, parse_oas_remaining_times,
                                          parse_shop_stock)
                parser = {"duration_seconds": parse_oas_duration, "cn_hour_minute": parse_oas_cn_hour_minute,
                          "remaining_times": parse_oas_remaining_times,
                          "counter_remaining": parse_oas_counter_remaining,
                          "counter_current": parse_oas_counter_current,
                          "exact_quantity": parse_exact_quantity, "shop_stock": parse_shop_stock}[mode]
                value = parser(self._read_single_text(img, tuple(spec["roi"]), .6))
                if value is None:
                    self.vars[cond["var"]] = -1
                    return False
            else:
                reader = self.ocr_reader
                if reader is None:
                    from ..vision.ocr import read_number as reader
                value = reader(img, spec["roi"])
            self.vars[cond["var"]] = value if value is not None else -1
            if "test" in cond:
                return bool(evaluate(cond["test"], self._env()))
            return value is not None
        raise WorkflowError(f"未知条件 {cond}")

    def _match_wanted_badge(self, output, img):
        from ..vision.ocr import read_boxes
        from .wanted_quests import first_tracked_badge

        if self._text_frame is not img:
            self._text_cache.clear()
            self._text_frame = img
        region = (0, 114, 123, 413)
        key = ("wanted_badge", region)
        if key not in self._text_cache:
            self._text_cache[key] = (self.text_reader(img, region) if self.text_reader else
                                     read_boxes(img, region, pad=0, min_score=.6))
        badge = first_tracked_badge(self._text_cache[key], lambda roi: self._read_single_text(img, roi, .6))
        self.vars[output] = ""
        if badge is None:
            return False
        self._found, self._found_box = badge[0], None
        self.vars[output] = badge[1]
        return True

    def _match_wanted_location(self, spec, img):
        from ..vision.ocr import read_boxes
        from .wanted_quests import choose_location

        if self._text_frame is not img:
            self._text_cache.clear()
            self._text_frame = img
        region = (622, 275, 421, 276)
        key = ("wanted_location", region)
        if key not in self._text_cache:
            self._text_cache[key] = (self.text_reader(img, region) if self.text_reader else
                                     read_boxes(img, region, pad=0, min_score=.6))
        env = self._env()
        plan = choose_location(
            self._text_cache[key],
            self._read_single_text(img, (859, 202, 84, 29), .6),
            self._read_single_text(img, (630, 145, 516, 62), .6),
            **{name: env[spec[name]] for name in ("priority", "secret_cutoff", "excluded", "tickets")},
        )
        for field, variable in spec["output"].items():
            self.vars[variable] = getattr(plan, field) if plan else (0 if field in ("slot", "runs") else "")
        return plan is not None

    def _match_hourly_rate(self, cond, img, spec):
        from ..vision.ocr import parse_hourly_rate, read_boxes
        from ..vision.regions import checked_box

        region = checked_box(spec["roi"], img, integral=True)
        if self._text_frame is not img:
            self._text_cache.clear()
            self._text_frame = img
        key = ("hourly_rates", region)
        if key not in self._text_cache:
            self._text_cache[key] = (self.text_reader(img, region) if self.text_reader else
                                     read_boxes(img, region, pad=0, min_score=.6))
        left, top, width, height = region
        matches = []
        for text, x, y in self._text_cache[key]:
            rate = parse_hourly_rate(text, cond["hourly_label"])
            if rate is not None and left <= x < left + width and top <= y < top + height:
                matches.append((-rate, y, x))
        self.vars[cond["var"]] = -1
        if not matches:
            return False
        negative_rate, y, x = min(matches)
        self.vars[cond["var"]] = -negative_rate
        if "test" in cond and not evaluate(cond["test"], self._env()):
            return False
        self._found, self._found_box = (x, y), None
        return True

    def _match_image_grid(self, spec, image):
        def match(ref, region):
            template = self.wf.resources[ref]
            return match_template(image, template["path"], region, template.get("threshold", .8),
                                  strict_roi=True, mask=template.get("mask_path"))

        cells = list(enumerate(spec["cells"], 1))
        exclude = spec.get("exclude")
        if exclude:
            cells = [(number, box) for (number, box), region in zip(cells, exclude["regions"])
                     if not match(exclude["template"], region)[0]]
        self._found = self._found_box = None
        self.vars[spec["cell_var"]] = 0
        for template in spec["templates"]:
            candidates = []
            for number, region in cells:
                ok, score, box = match(template, region)
                if ok:
                    candidates.append((score, number, box))
            if candidates:
                _, number, box = max(candidates, key=lambda item: item[0])
                self._found_box, self._found = box, box[:2]
                self.vars[spec["cell_var"]] = number
                return True
        return False

    def _match_quiz_answer(self, spec, img):
        from ..vision.ocr import read_boxes
        from .quiz import AnswerBank, normalize

        bank = spec["bank"]
        if bank not in self._answer_banks:
            self._answer_banks[bank] = AnswerBank(self.wf.resources[bank]["rows"])
        if self._text_frame is not img:
            self._text_cache.clear()
            self._text_frame = img
        key = ("quiz_answer", bank, spec["question"], *spec["options"])
        if key not in self._text_cache:
            resource = self.wf.resources[spec["question"]]
            roi = tuple(resource["roi"])
            if resource["mode"] == "Single":
                question = self._read_single_text(img, roi, .6)
            else:
                boxes = self.text_reader(img, roi) if self.text_reader else read_boxes(img, roi, pad=0, min_score=.6)
                question = "".join(word for word, _, _ in sorted(boxes, key=lambda row: (row[2], row[1])))
            question = normalize(question)
            options = [normalize(self._read_single_text(img, tuple(self.wf.resources[name]["roi"]), .6))
                       for name in spec["options"]]
            answer = self._answer_banks[bank].choose(question, options) if question and all(options) else 0
            self._text_cache[key] = question, options, answer
        question, options, answer = self._text_cache[key]
        self.vars.update(zip(spec["option_vars"], options))
        self.vars[spec["question_var"]] = question
        self.vars[spec["answer_var"]] = answer
        return bool(question and all(options))

    def _read_single_text(self, image, region, score):
        from ..vision.ocr import read_single
        if self._text_frame is not image:
            self._text_cache.clear()
            self._text_frame = image
        key = ("single", region, score)
        if key not in self._text_cache:
            self._text_cache[key] = (self.single_ocr_reader or read_single)(image, region, score)
        text = self._text_cache[key]
        if not isinstance(text, str):
            raise WorkflowError("ocr_single reader must return a whole-line string")
        return text

    def _literal_ocr_keyword(self, spec, key):
        value = self._env().get(spec[key + "_var"]) if key + "_var" in spec else spec[key]
        if not isinstance(value, str) or not value:
            # Empty Full keywords match every upstream box. That is an explicit
            # caller obligation, not negative evidence or permission to click.
            raise WorkflowError("OCR literal keyword must be a nonempty string")
        return value

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
        self._found_box = None
        if cond.get("var"):
            self.vars[cond["var"]] = text
        return True

    def _env(self) -> dict:
        return {**self.params, **self.vars, "actions": self._actions_taken, "screen_captures": self._screen_captures}

    def diagnose_frame(self, img: np.ndarray) -> list[dict]:
        """Per state (and per blocker): does it match, and for colour conditions the fraction of
        matching points. Variables start at the workflow's initial values, as at the start of a
        run, so conditions such as ``runs < max_runs`` can be evaluated."""
        if not self.vars:
            self.vars = {**(self.wf.raw.get("vars") or {}), "elapsed_s": 0, "elapsed_ms": 0, "actions": 0}
        out = []
        items = [(st, False) for st in self.wf.states] + [(b, True) for b in self.wf.blockers]
        for st, is_blocker in items:
            cond = st["when"]
            info = {"id": ("blocker:" + st["id"]) if is_blocker else st["id"], "match": False}
            self._found = None
            self._found_box = None
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
        if isinstance(v, dict):
            if "rect_vars" in v:
                from ..vision.regions import checked_box
                x, y, width, height = checked_box([self.vars[key] for key in v["rect_vars"]], self._frame,
                                                   integral=True)
                return [x, y, x + width, y + height]
            from ..vision.regions import parameter_click_rect
            return parameter_click_rect(v, self.params)
        return v

    def _action_boundary(self, input_action: bool = True) -> str | None:
        """Check cancellation/deadline immediately before every device input."""
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
        self.vars["elapsed_ms"] = getattr(self, "_elapsed_offset_ms", 0) + max(0, int(elapsed * 1000))
        if self.max_seconds is not None and elapsed >= self.max_seconds:
            if self.ctl.observe:
                return "observed:达到时间上限"
            return "limit:达到时间上限，未继续输入"
        if elapsed > self.wf.limits["timeout_s"]:
            raise RunFailure("timeout", "达到工作流时间上限，未继续输入")
        if input_action and self.max_actions is not None and self._actions_taken >= self.max_actions:
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

    def _input(self, state, action, operation, *, prepare=None):
        if self.ctl.observe:
            if prepare:
                prepare()
            operation()
            return None
        boundary = self._action_boundary()
        if boundary:
            return boundary
        marker = action.get("attempt_var")
        if marker and self.vars.get(marker):
            raise RunFailure("recognition", "该输入已尝试，结果未核对前不能重放", state["id"])
        if action.get("recheck"):
            # A user may spend minutes in a confirmation dialog. Never use that old frame to spend.
            image = self.ctl.screenshot()
            self._frame = image
            self._found = None
            self._found_box = None
            if not self._match(state["when"], image):
                if action.get("recheck_retry") and not state.get("sensitive") and not self._handler_active:
                    return "rescan"
                raise RunFailure("recognition", "确认后画面条件已变化，未发送点击", state["id"])
            boundary = self._action_boundary()
            if boundary:
                return boundary
        if prepare:
            prepare()
        authorization = self.before_input({**state, "repeat_count": self._repeat_count}, action, self.vars)
        boundary = self._action_boundary()
        if boundary:
            if callable(authorization):
                authorization(False)
            return boundary
        self._actions_taken += 1
        self.vars["actions"] = self._actions_taken
        if marker:
            # Write ahead in the retry variables: native input may succeed before raising an error.
            self.vars[marker] = 1
        try:
            operation()
            if action.get("tap_id"):
                self._recent_taps.append(action["tap_id"])
            elif "restart_app" in action:
                self._recent_taps.clear()
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
            return self._input(st, action, lambda: self.ctl.click(random.choice(action["click_random"]), delay,
                                                                 action.get("press_ms")))
        elif "click" in action:
            target = self._rect(action["click"])
            return self._input(st, action, lambda: self.ctl.click(target, delay,
                                                                 action.get("press_ms")))
        elif "click_found" in action:
            if self._found is None:
                raise WorkflowError(f"state {st['id']}: click_found 前没有 find/image 条件命中")
            ox1, oy1, ox2, oy2 = action.get("offset", [0, 0, 20, 20])
            target = None
            point = None
            def prepare_found():
                # Resolve after _input's fresh-frame recheck, not from the
                # position remembered before a confirmation/screenshot.
                nonlocal target, point
                if self._found is None:
                    raise WorkflowError("重新核对后缺少点击位置")
                point = self._found
                x, y = point
                if "projected_rect" in action:
                    from ..vision.regions import project_region
                    px, py, width, height = project_region(self._found_box, action["projected_rect"], self._frame)
                    target = [px, py, px + width, py + height]
                elif action.get("use_match_size"):
                    if self._found_box is None:
                        raise WorkflowError("use_match_size 需要当前命中的图片区域")
                    bx, by, width, height = self._found_box
                    frame_h, frame_w = self._frame.shape[:2]
                    if width <= 0 or height <= 0 or bx < 0 or by < 0 or bx + width > frame_w or by + height > frame_h:
                        raise RunFailure("recognition", "图片命中区域越过当前画面，未发送输入", st["id"])
                    target = [bx, by, bx + width, by + height]
                else:
                    target = [x + ox1, y + oy1, x + ox2, y + oy2]
            end = self._input(st, action, lambda: self.ctl.click(target, delay, action.get("press_ms")),
                              prepare=prepare_found)
            if end is None and "point_vars" in action:
                self.vars.update(zip(action["point_vars"], point))
            return end
        elif "capture_region" in action:
            from ..vision.regions import project_region
            if self._found_box is None or self._frame is None:
                raise WorkflowError("capture_region needs a current positive match box")
            spec = action["capture_region"]
            values = project_region(self._found_box, spec["rect"], self._frame)
            self.vars.update(zip(spec["vars"], values))
        elif "navigate" in action:
            from .navigation import NativeNavigator
            spec = action["navigate"]
            sessions = getattr(self, "_navigators", None)
            if sessions is None:
                sessions = self._navigators = {}
            key = (st["id"], spec["destination"], spec["done_var"])
            session = sessions.setdefault(key, NativeNavigator(self.wf.raw["navigation"], spec["destination"],
                category=spec.get("category", "global"), timeout=spec.get("timeout_s", 30)))
            decision = session.step(lambda condition: self._match(condition, self._frame), self.clock())
            self.on_event("navigation", {"state": st["id"], "page": decision.page,
                "arrived": decision.arrived, "blocked": decision.blocked, "phase": session.phase})
            if decision.blocked:
                raise RunFailure("navigation", decision.blocked, st["id"])
            if decision.arrived:
                self.vars[spec["done_var"]] = 1
                sessions.pop(key)
            if decision.invocation:
                if self._navigation_call is not None:
                    raise RunFailure("navigation", "原生导航调用不能重入", st["id"])
                graph = self.wf.raw["navigation"]
                body = graph["calls"][decision.invocation]
                self.vars.update(copy.deepcopy(body["initial_vars"]))
                self.vars[graph["call_active_var"]] = decision.invocation
                self._navigation_call = (session, decision.invocation)
                self._recent_taps.clear()
                self.on_event("navigation_call", {"name": decision.invocation, "state": st["id"], "event": "entered"})
            if decision.action:
                guarded = {**st, "when": decision.guard}
                # Route every native planner input through the same cancellation,
                # trial, confirmation, resource and fresh-frame input boundary.
                end = self._do(guarded, {**decision.action, "recheck": True})
                session.acknowledge(end is None and not self.ctl.observe)
                return end
        elif "navigation_return" in action:
            name = action["navigation_return"]
            if (not self._navigation_call or self._navigation_call[1] != name or
                    self._navigation_call_states.get(st["id"]) != name):
                raise RunFailure("navigation", "没有匹配的待返回原生调用", st["id"])
            session, _ = self._navigation_call
            graph = self.wf.raw["navigation"]
            result = self.vars[graph["calls"][name]["result_var"]]
            if type(result) is not bool:
                raise RunFailure("navigation", "导航回调返回值必须是布尔值", st["id"])
            session.return_from_call(name, result, self.clock())
            self.vars[graph["call_active_var"]] = ""
            self._navigation_call = None
            self.on_event("navigation_call", {"name": name, "state": st["id"], "event": "returned", "result": result})
        elif "scheme_transition" in action:
            return self._transition_scheme(st, action["scheme_transition"])
        elif "handler_control" in action:
            control = action["handler_control"]
            contract = self.wf.raw["handler_dispatch"]
            if control["op"] == "begin":
                if self._handler_active:
                    raise RunFailure("handler_dispatch", "重复开始组件扫描", st["id"])
                self._handler_active, self._handler_frame = True, self._frame
                self._handler_steps = 0
                self._handler_seen_case = False
            elif control["op"] == "refresh":
                if not self._handler_active:
                    raise RunFailure("handler_dispatch", "组件扫描尚未开始", st["id"])
                self._handler_frame = self._frame = self.ctl.screenshot()
                self._screen_captures += 1
                self._found = self._found_box = None
            else:
                if not self._handler_active:
                    raise RunFailure("handler_dispatch", "组件扫描尚未开始", st["id"])
                if control["handled"]:
                    lifecycle = self.wf.raw.get("scheme_lifecycle")
                    handled = (lifecycle["schemes"][self.vars[ACTIVE_SCHEME]]["handled_var"] if lifecycle
                               else contract["last_handled_ms_var"])
                    self.vars[handled] = self.vars["elapsed_ms"]
                self._handler_active, self._handler_frame = False, None
            return None
        elif "select_foster" in action:
            if self.ctl.observe:
                return None
            from ..foster import (FosterSelector, foster_friend_key, missing_cross_friend_rows, read_card,
                                  read_foster_friend_rows, selected_friend, supplement_cross_friend_rows)
            from ..vision.ocr import read_boxes
            from .schema import bundled_dir
            spec = action["select_foster"]
            tabs = spec.get("selected_tabs")
            if not hasattr(self, "_foster_selector"):
                self._foster_selector = FosterSelector(spec.get("max_pages", 30), require_highlight=tabs is not None)
            active = [i for i, tab in enumerate(tabs or ()) if self._match({"res": tab}, self._frame)]
            region = active[0] if len(active) == 1 else None
            reader = self.text_reader or read_boxes
            aliases = {name: self.wf.resources[ref]["path"]
                       for name, ref in spec.get("cross_nickname_templates", {}).items()}
            card_roi = [760, 175, 245, 340]
            card_templates = bundled_dir() / "resources" / "oas-foster"

            def friend_rows(frame):
                rows = read_foster_friend_rows(frame, reader, cross_region=region == 1)
                return supplement_cross_friend_rows(frame, rows, aliases) if region == 1 and aliases else rows

            rows = friend_rows(self._frame)
            if region == 1 and missing_cross_friend_rows(self._frame, rows):
                step = {"stop": {"reason": "跨区好友列表仍有可见昵称未识别，无法核对最优寄养结界卡",
                                 "result": "blocked"}}
            else:
                step = self._foster_selector.step(rows,
                    reader(self._frame, card_roi), self._frame, card_templates, active_region=region)
            enter = spec.get("enter_realm")
            if enter and self._foster_selector.phase == "previewed" and region is not None:
                best = self._foster_selector.best
                button = {"res": enter["button"]}
                guarded = {**st, "when": {"all": [
                    st["when"], {"res": tabs[region]}, {"not": {"res": tabs[1 - region]}}, button,
                ]}}
                tap = {"click_found": True, "use_match_size": True, "recheck": True, "delay": 1500}

                def recheck_selected_card():
                    fresh_rows = friend_rows(self._frame)
                    names = [(foster_friend_key(name), x, y) for name, x, y in fresh_rows
                             if 315 <= x <= 610 and 155 <= y <= 590 and "最近寄养" not in name.replace(" ", "")]
                    card, status = read_card(reader(self._frame, card_roi), self._frame, card_templates)
                    if (str(region) != best.region or sum(name == best.friend for name, _, _ in names) != 1
                            or selected_friend(self._frame, names) != best.friend
                            or (region == 1 and missing_cross_friend_rows(self._frame, fresh_rows))
                            or status != "known" or (card.card_type, card.stars) != (best.card_type, best.stars)
                            or self._found_box is None):
                        raise RunFailure("recognition", "好友或结界卡已变化，未进入好友结界", st["id"])

                def enter_realm():
                    x, y, width, height = self._found_box
                    self.ctl.click((x, y, x + width, y + height), tap["delay"])

                result = self._input(guarded, tap, enter_realm, prepare=recheck_selected_card)
                if result is None:
                    self.vars[enter["entered_var"]] = True
                    del self._foster_selector
                return result
            if spec.get("exhausted_var") and step.get("stop", {}).get("result") == "skipped":
                self.vars[spec["exhausted_var"]] = True
                del self._foster_selector
                return None
            if tabs and region is not None and ("click" in step or "swipe" in step):
                st = {**st, "when": {"all": [st["when"], {"res": tabs[region]}, {"not": {"res": tabs[1 - region]}}]}}
                step = {**step, "recheck": True}
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
            if "from_found" in v:
                start_rect = None

                def prepare_swipe():
                    nonlocal start_rect
                    if self._found is None:
                        raise RunFailure("recognition", "重新核对后缺少滑动起点", st["id"])
                    x, y = self._found
                    x1, y1, x2, y2 = v["from_found"]
                    start_rect = [x + x1, y + y1, x + x2, y + y2]
                    height, width = self._frame.shape[:2]
                    for left, top, right, bottom in (start_rect, v["to"]):
                        if not (0 <= left < right < width and 0 <= top < bottom < height):
                            raise RunFailure("recognition", "滑动区域越过当前画面，未发送输入", st["id"])

                return self._input(st, action, lambda: self.ctl.swipe(start_rect, v["to"], delay,
                    action.get("duration_ms")), prepare=prepare_swipe)
            return self._input(st, action, lambda: self.ctl.swipe(v["from"], v["to"], delay, action.get("duration_ms")))
        elif "back" in action:
            return self._input(st, action, lambda: self.ctl.back(delay))
        elif "start_app" in action:
            return self._input(st, action, lambda: self.ctl.start_app(action["start_app"]))
        elif "restart_app" in action:
            try:
                return self._input(st, action, lambda: self.ctl.restart_app(action["restart_app"]))
            except DeviceError as error:
                if not self.vars.get(action["attempt_var"]):
                    raise
                raise RunFailure("restart_uncertain", str(error), st["id"]) from error
        elif "wait" in action:
            wait = action["wait"]
            if isinstance(wait, dict):
                delay = self._env()[wait["var"]]
                if type(delay) not in (int, float) or not 0 <= delay <= 600000:
                    raise RunFailure("workflow_error", "等待时长需要在 0–600000 毫秒内", st["id"])
                wait = max(delay, wait.get("minimum_ms", 0))
            self._sleep(float(wait) / 1000)
        elif "wait_random" in action:
            spec = action["wait_random"]
            if isinstance(spec, list):
                delay = random.randint(*spec)
            elif "step_ms" in spec:
                delay = random.randrange(spec["min_ms"], spec["max_ms"] + 1, spec["step_ms"])
            else:
                delay = random.uniform(spec["min_ms"], spec["max_ms"])
            self._sleep(delay / 1000)
        elif "sample_int" in action:
            spec = action["sample_int"]
            self.vars[spec["var"]] = random.randint(spec["min"], spec["max"])
        elif "sample_duration" in action:
            spec = action["sample_duration"]
            name = spec["range_param"]
            configured = self._env()[name]
            minutes = spec["unit"] == "minutes"
            upper = 86400000 if minutes else 600000
            try:
                if not isinstance(configured, str) or len(configured) > 96 or "_" in configured:
                    raise ValueError
                lo, hi = [float(endpoint) * 1000 * (60 if minutes else 1) for endpoint in configured.split(",")]
                if not 0 <= lo <= hi <= upper:
                    raise ValueError
            except (ValueError, OverflowError) as error:
                raise RunFailure("workflow_error", f"{name} 需要升序的非负时长区间（{spec['unit']}）", st["id"]) from error
            sample = random.randint(int(lo), int(hi)) if lo.is_integer() and hi.is_integer() else random.uniform(lo, hi)
            self.vars[spec["var"]] = math.floor(sample) if minutes else sample
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
        elif "oas_wake" in action:
            wake = action["oas_wake"]
            if not self.ctl.observe:
                key = wake.get("failure_seconds_param")
                delay = self.params[key] if key is not None else None
                if key is not None and (type(delay) is not int or not 0 <= delay <= 3155760000):
                    raise RunFailure("workflow_fail", "OAS 任务接续的失败间隔无效", st["id"])
                elapsed = self.clock() - self._run_started
                timing = wake.get("server_params")
                self._oas_wakes[wake["task"]] = (
                    (delay, elapsed, {name: self.params[param] for name, param in timing.items()})
                    if timing else (delay, elapsed)
                )
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
    def _record_scheme_entry(self, target, entered_ms):
        self._scheme_history.append({"scheme": target, "entered_ms": entered_ms})
        if (type(self.vars.get("core0_history_available")) is bool
                and type(self.vars.get("core0_history_count")) is int):
            self.vars["core0_history_available"] = True
            self.vars["core0_history_count"] = sum(entry["scheme"] == target for entry in self._scheme_history)

    def _transition_scheme(self, state, transition):
        lifecycle = self.wf.raw.get("scheme_lifecycle") or {}
        if not lifecycle or not self._handler_active:
            raise RunFailure("scheme_lifecycle", "方案切换缺少有效的组件扫描", state["id"])
        target = transition.get("target")
        if transition["mode"] == "previous":
            if len(self._scheme_history) == 1:
                reason = "无法查询到上个方案，当前为第一个方案"
                self.on_event("log", {"state": state["id"], "message": reason})
                self._stop_business_result = "unknown"
                self._stop_evidence = {"verified": False}
                return "stop:" + reason
            target = self._scheme_history[-2]["scheme"]
        elif transition["mode"] == "latest_matching":
            from .scheme_lifecycle import latest_scheme
            target = latest_scheme(self._scheme_history, transition["contains"])
        binding = lifecycle.get("schemes", {}).get(target)
        if binding is None:
            raise RunFailure("scheme_lifecycle", "方案切换缺少明确目标", state["id"])
        if len(self._scheme_history) > MAX_SWITCHES:
            raise RunFailure("scheme_lifecycle", "方案切换已达到本次运行的上限", state["id"])
        boundary = self._action_boundary()
        if boundary:
            return boundary
        self.ctl.sleep(SWITCH_DELAY_S)
        boundary = self._action_boundary()
        if boundary:
            return boundary
        previous = self.vars[ACTIVE_SCHEME]
        self.vars.update(binding["reset"])
        self.vars.update(dict.fromkeys(binding["clocks"], self.vars["elapsed_ms"]))
        self.vars[ACTIVE_SCHEME] = target
        self._record_scheme_entry(target, self.vars["elapsed_ms"])
        self._handler_active, self._handler_frame, self._handler_steps = False, None, 0
        self._recent_taps.clear()
        self.on_event("scheme_transition", {"from": previous, "to": target, "state": state["id"]})
        return "scheme_transition"

    def run(self) -> RunResult:
        wf = self.wf
        limits = wf.limits
        self.vars = {**(wf.raw.get("vars") or {}), **self.initial_vars, "elapsed_s": 0, "elapsed_ms": 0, "actions": 0}
        self._actions_taken = 0
        self._screen_captures = 0
        self._recent_taps.clear()
        res = RunResult(wf.name, "failed", started=self.clock())
        start = res.started
        self._run_started = start
        self._oas_wakes = {}
        self._stop_business_result = str(wf.raw.get("default_result") or "unknown")
        self._stop_evidence = {}
        self._navigators = {}
        self._navigation_call = None
        self._handler_active, self._handler_frame, self._handler_steps = False, None, 0
        self._elapsed_offset_ms = 0
        dispatch = wf.raw.get("handler_dispatch")
        lifecycle = wf.raw.get("scheme_lifecycle")
        self._scheme_history = []
        prior_clock = self.initial_vars.get("elapsed_ms", 0)
        valid_handler_clock = type(prior_clock) in (int, float) and math.isfinite(prior_clock) and prior_clock >= 0
        if dispatch and valid_handler_clock:
            self._elapsed_offset_ms = prior_clock
        original_hcfg = getattr(self.ctl, "hcfg", None)
        if dispatch and original_hcfg is not None:
            from dataclasses import replace
            common = dispatch["common_config"]
            self.ctl.hcfg = replace(original_hcfg, style="assttyys",
                base_sleep_ms=int(common["afterClickDelayBase"]), random_sleep_ms=int(common["afterClickDelayRandom"]))
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
            if lifecycle:
                if self.initial_vars:
                    raise RunFailure("scheme_lifecycle", "方案生命周期缺少可验证的恢复记录")
                self._record_scheme_entry(self.vars[ACTIVE_SCHEME], 0)
            call_active_var = wf.raw.get("navigation", {}).get("call_active_var")
            if call_active_var and self.vars.get(call_active_var) != "":
                raise RunFailure("navigation_resume", "上次在导航回调中途停止；缺少原生返回上下文，不能自动重放")
            if any(self.vars.get(marker) for marker in self._restart_markers):
                raise RunFailure("restart_uncertain", "上一次游戏重启结果未核对，需要人工确认状态")
            if dispatch and not valid_handler_clock:
                raise RunFailure("handler_resume", "已保存的组件时钟不是有效的非负有限毫秒数")
            if dispatch and self.vars.get(dispatch["phase_var"], 0) != 0:
                raise RunFailure("handler_resume", "上次在组件扫描中途停止；缺少缓存帧，不能自动续放剩余输入")
            while True:
                now = self.clock()
                self.vars["elapsed_s"] = int(now - start)
                self.vars["elapsed_ms"] = self._elapsed_offset_ms + max(0, int((now - start) * 1000))
                mode = self.should_stop()
                if mode is True or mode == "immediate":
                    res.status, res.reason = "stopped", "用户停止"
                    break
                if self._navigation_call is None and wf.raw.get("stop_when") and evaluate(wf.raw["stop_when"], self._env()):
                    res.status, res.reason = "success", "达到结束条件"
                    res.business_result = "completed"
                    break
                if self.max_seconds is not None and now - start >= self.max_seconds:
                    res.status, res.reason = ("observed" if observe else "limit"), "达到时间上限"
                    break
                if self.max_actions is not None and self._actions_taken >= self.max_actions:
                    res.status, res.reason = "limit", f"达到试跑动作上限 {self.max_actions}"
                    break
                if now - start > limits["timeout_s"]:
                    raise RunFailure("timeout", f"超过 {limits['timeout_s']} 秒没有结束")
                try:
                    if self._handler_active:
                        self._handler_steps += 1
                        if self._handler_steps > min(10000, len(wf.states) * 3 + 8):
                            raise RunFailure("handler_dispatch", "组件扫描内部步骤超过有界上限")
                        img = self._handler_frame
                    else:
                        img = self.ctl.screenshot()
                        self._screen_captures += 1
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
                self._found_box = None
                matched = None
                for st in wf.states:
                    owner = self._navigation_call_states.get(st["id"])
                    active_call = self._navigation_call[1] if self._navigation_call else None
                    if owner != active_call:
                        continue
                    self._found = None
                    self._found_box = None
                    if self._match(st["when"], img):
                        matched = st
                        break
                if matched is not None and matched.get("retest_ms"):
                    # assttyys retest refreshes the screenshot and reruns the
                    # operator list once.  Never click using the earlier frame,
                    # and preserve priority if a different operator now matches.
                    self.ctl.sleep(float(matched["retest_ms"]) / 1000)
                    self.vars["elapsed_s"] = int(self.clock() - start)
                    boundary = self._action_boundary(input_action=False)
                    if boundary:
                        res.status, _, res.reason = boundary.partition(":")
                        break
                    try:
                        img = self.ctl.screenshot()
                        self._screen_captures += 1
                    except DeviceError as e:
                        raise RunFailure("device", str(e)) from e
                    res.last_frame = img
                    self._frame = img
                    if self._handler_active:
                        self._handler_frame = img
                    res.ticks += 1
                    matched = None
                    for st in wf.states:
                        owner = self._navigation_call_states.get(st["id"])
                        active_call = self._navigation_call[1] if self._navigation_call else None
                        if owner != active_call:
                            continue
                        self._found = None
                        self._found_box = None
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
                handler_step = matched.get("handler_step", {}) if dispatch else {}
                logical_match = not dispatch or handler_step.get("kind") == "case"
                if logical_match:
                    last_known = now
                    unknown_reported = False
                    res.recognized_ticks += 1
                    if dispatch:
                        self._handler_seen_case = True
                elif handler_step.get("kind") == "end" and not getattr(self, "_handler_seen_case", False):
                    # Phase/entry/fallthrough states are bookkeeping, not screen
                    # recognition. They must not keep an unknown UI alive.
                    if not unknown_reported and now - last_known >= float(limits.get("unknown_sample_s", 10)):
                        unknown_reported = True
                        self.on_event("unknown", {"frame": img, "after_state": repeat_state,
                                                  "seconds": round(now - last_known, 1)})
                    if not observe and now - last_known > limits["unknown_timeout_s"]:
                        raise RunFailure("unknown_screen", "组件扫描未识别画面，已达到未知画面时限", matched["id"])
                res.history.append((round(now - start, 2), matched["id"]))
                self.on_event("state", {"state": matched["id"], "vars": dict(self.vars)})
                if logical_match:
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
                idle_poll = any(isinstance(step.get("wait"), dict) and "minimum_ms" in step["wait"]
                                for step in matched["do"])
                max_repeat = int(matched.get("max_repeat", limits["max_repeat"]))
                if not observe and not idle_poll and logical_match and repeat_count > max_repeat:
                    if matched.get("on_repeat", "fail") == "stop":
                        res.status = "success"
                        res.reason = matched.get("repeat_reason", f"{matched['id']} 连续出现 {repeat_count} 次，按设定结束")
                        res.business_result = matched.get("repeat_result", "blocked")
                        res.evidence = {"terminal_state": matched["id"], "verified": False}
                        break
                    raise RunFailure("loop", f"状态 {matched['id']} 连续出现 {repeat_count} 次", matched["id"])
                if not observe and not idle_poll:
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
                if end == "rescan":
                    self.ctl.sleep(loop_delay)
                    continue
                if matched.get("progress"):
                    last_progress = self.clock()
                if idle_poll and end is None:
                    # A planned input-free pause can leave the screen unchanged for minutes.
                    last_change = last_progress = self.clock()
                    repeat_state, repeat_count = None, 0
                if end:
                    kind, _, reason = end.partition(":")
                    if kind == "scheme_transition":
                        last_known = last_change = last_progress = self.clock()
                        prev_thumb = repeat_state = None
                        repeat_count = 0
                        unknown_reported = False
                        continue
                    if kind == "stop":
                        res.status, res.reason = "success", reason or "工作流结束"
                        res.business_result = self._stop_business_result
                        res.evidence = {"terminal_state": matched["id"], **self._stop_evidence}
                        terminal = action.get("stop")
                        if isinstance(terminal, dict):
                            schedule = terminal.get("oas_schedule")
                            if isinstance(schedule, dict):
                                res.oas_schedule = schedule["task"]
                                delay = self.vars[schedule["delay_seconds_var"]]
                                observed = self.vars[schedule["observed_ms_var"]]
                                elapsed = self.vars["elapsed_ms"]
                                if (type(delay) is not int or not 0 <= delay <= 3155760000 or
                                        type(observed) is not int or not 0 <= observed <= elapsed):
                                    raise RunFailure("workflow_fail", "OAS 目标调度缺少有效的延迟或观察时间", matched["id"])
                                res.oas_target = (delay, (elapsed - observed) / 1000)
                            else:
                                res.oas_schedule = schedule
                        break
                    if kind in ("limit", "observed"):
                        res.status, res.reason = kind, reason or "达到限制"
                        break
                    if kind == "stopped":
                        res.status, res.reason = "stopped", reason or "用户停止"
                        break
                    raise RunFailure("workflow_fail", reason, matched["id"])
                if not self._handler_active:
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
            if original_hcfg is not None:
                self.ctl.hcfg = original_hcfg
            if self._frame is not None:
                res.last_frame = self._frame
        res.ended = self.clock()
        res.oas_wakes = self._oas_wakes
        res.actions = self._actions_taken
        self.vars["actions"] = self._actions_taken
        res.variables = {k: v for k, v in self.vars.items()}
        if res.status == "failed":
            res.business_result = "failed"
        elif res.status == "success" and res.business_result == "unknown":
            res.business_result = self._stop_business_result
        if observe:
            res.evidence["verified"] = False
        if lifecycle:
            res.evidence["scheme_history"] = self._scheme_history
        self.on_event("end", res.summary())
        logger.info("[%s] %s: %s", wf.name, res.status, res.reason)
        return res
