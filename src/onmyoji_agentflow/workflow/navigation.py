"""Bounded native navigation planner; emits guarded actions, never runs source.

This kernel knows pages, directed weighted edges and declarative hook steps.
It has no imports/callback/script escape hatch. The owning Runner remains the
only device-input authority and rechecks every returned guard on a fresh frame.
Source contracts not yet representable are explicit ``blocked`` hook nodes.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from ..errors import WorkflowError


@dataclass
class NavigationDecision:
    action: dict | None = None
    guard: dict | None = None
    page: str | None = None
    arrived: bool = False
    blocked: str | None = None
    progress: bool = False
    invocation: str | None = None


def _positive(condition):
    if not isinstance(condition, dict):
        return False
    if set(condition) & {"colors", "mean_color", "res", "find", "find_near", "find_column", "find_image_above", "image", "text",
                         "ocr", "ocr_single", "ocr_full", "text_param"}:
        return True
    if "all" in condition:
        return any(_positive(child) for child in condition["all"])
    if "any" in condition:
        return bool(condition["any"]) and all(_positive(child) for child in condition["any"])
    return False


def validate_navigation(graph, resources, variables):
    """Check the complete closed vocabulary before a runner can use a graph."""
    from .schema import validate_action, validate_condition
    if not isinstance(graph, dict) or graph.get("format") != 1:
        raise WorkflowError("navigation 需要 format: 1 原生图")
    pages = graph.get("pages")
    if not isinstance(pages, dict) or not pages or len(pages) > 256:
        raise WorkflowError("navigation.pages 需要 1–256 个页面")
    calls = graph.get("calls", {})
    if not isinstance(calls, dict) or len(calls) > 32:
        raise WorkflowError("navigation.calls 需要有限调用表")
    if calls and (not isinstance(graph.get("call_active_var"), str) or graph["call_active_var"] not in variables):
        raise WorkflowError("navigation.calls 需要已声明 call_active_var")
    owned, outputs = set(), set()
    for key, spec in calls.items():
        if (not isinstance(key, str) or not key or not isinstance(spec, dict)
                or set(spec) != {"states", "initial_vars", "result_var"}):
            raise WorkflowError("navigation.calls 的有限状态契约无效")
        states, initial, result = spec["states"], spec["initial_vars"], spec["result_var"]
        if (not isinstance(states, list) or not states or len(states) > 4096
                or any(not isinstance(s, str) for s in states) or len(states) != len(set(states))
                or owned.intersection(states)):
            raise WorkflowError("navigation.calls 需要不重叠的状态列表")
        if (not isinstance(initial, dict) or not initial or
                any(not isinstance(n, str) or n not in variables or n in {"elapsed_ms", "elapsed_s", "actions", graph["call_active_var"]}
                    for n in initial) or not isinstance(result, str) or result not in initial or
                outputs.intersection(initial)):
            raise WorkflowError("navigation.calls 需要不重叠的已声明局部变量与结果")
        if any(type(value) not in (bool, str, int, float) or
               (type(value) is float and not math.isfinite(value)) for value in initial.values()):
            raise WorkflowError("navigation.calls 初值只能是有限数字、布尔或文字")
        owned.update(states)
        outputs.update(initial)

    def cost(value):
        return type(value) in (float, int) and math.isfinite(value) and value >= 0

    def hook(node, where):
        if not isinstance(node, dict):
            raise WorkflowError(where + ": hook 需要对象")
        if "blocked" in node:
            if set(node) != {"blocked"} or not isinstance(node["blocked"], str) or not node["blocked"]:
                raise WorkflowError(where + ": 无效的阻断说明")
            return
        if set(node) - {"when", "action", "steps", "choice", "repeat", "until", "timeout_s", "success_index", "invoke", "result"}:
            raise WorkflowError(where + ": 未知原生 hook 字段")
        if "when" in node:
            validate_condition(node["when"], resources, variables, where)
        kinds = set(node) & {"action", "steps", "choice", "repeat", "invoke", "result"}
        if len(kinds) != 1:
            raise WorkflowError(where + ": hook 需要唯一执行类型")
        if "invoke" in node:
            if not isinstance(node["invoke"], str) or node["invoke"] not in calls:
                raise WorkflowError(where + ": invoke 未绑定到有限原生调用")
        elif "result" in node:
            if type(node["result"]) is not bool:
                raise WorkflowError(where + ": hook result 必须是布尔值")
        elif "repeat" in node:
            validate_condition(node.get("until"), resources, variables, where + ".until")
            timeout = node.get("timeout_s", 30)
            if type(timeout) not in (int, float) or not 0 < timeout <= 30:
                raise WorkflowError(where + ": repeat 需要有界时限")
            hook(node["repeat"], where + ".repeat")
        elif "steps" in node or "choice" in node:
            children = node.get("steps", node.get("choice"))
            if not isinstance(children, list) or not children:
                raise WorkflowError(where + ": steps 需要非空列表")
            index = node.get("success_index", 0)
            if type(index) is not int or index < 0:
                raise WorkflowError(where + ": 无效 success_index")
            for index, item in enumerate(children):
                hook(item, where + f".steps[{index}]")
        else:
            action = node.get("action")
            if not isinstance(action, dict) or not set(action) & {"click", "click_found", "click_random", "wait"}:
                raise WorkflowError(where + ": 导航只允许点击或等待")
            validate_action(action, resources, variables, where)
            if set(action) & {"confirm", "cost", "attempt_var"}:
                raise WorkflowError(where + ": 导航 hook 不能隐含经济操作")

    def hooks(owner, where):
        values = owner.get("hooks", {})
        if not isinstance(values, dict) or set(values) - {
                "enter_success", "enter_failure", "leave_success", "leave_failure"}:
            raise WorkflowError(where + ": 未知 hook 阶段")
        for stage, items in values.items():
            if not isinstance(items, list):
                raise WorkflowError(where + ": hook 阶段需要列表")
            for index, item in enumerate(items):
                hook(item, where + f".{stage}[{index}]")

    for key, page in pages.items():
        if not isinstance(key, str) or not isinstance(page, dict):
            raise WorkflowError("navigation.pages 无效")
        validate_condition(page.get("when"), resources, variables, "navigation." + key)
        if not _positive(page["when"]):
            raise WorkflowError("navigation 页面需要必经的正向画面识别")
        priority = page.get("priority", 50)
        if type(priority) is not int or not 1 <= priority <= 100 or not cost(page.get("cost", 1)):
            raise WorkflowError("navigation 页面优先级/代价无效")
        hooks(page, "navigation." + key)
    links = graph.get("links", [])
    if not isinstance(links, list) or len(links) > 2048:
        raise WorkflowError("navigation.links 无效")
    seen = set()
    for index, link in enumerate(links):
        where = f"navigation.links[{index}]"
        if not isinstance(link, dict) or link.get("from") not in pages or link.get("to") not in pages:
            raise WorkflowError(where + ": 页面不存在")
        key = link.get("key")
        if not isinstance(key, str) or not key or key in seen or not cost(link.get("cost", 0)):
            raise WorkflowError(where + ": 边标识重复或代价无效")
        seen.add(key)
        hook(link.get("action"), where)
        if "fallback" in link:
            hook(link["fallback"], where + ".fallback")
        hooks(link, where)
    for index, item in enumerate(graph.get("unknown_closers", [])):
        hook(item, f"navigation.unknown_closers[{index}]")


@dataclass
class _Sequence:
    node: dict
    index: int = 0
    results: list[bool] = field(default_factory=list)
    started: float | None = None
    entered: bool = False


class NativeNavigator:
    """Incremental session. One step observes a frame and emits at most one input.

    The caller must call ``acknowledge`` only after its guarded device action
    succeeds. Merely planning/observing an input never advances an edge.
    """

    def __init__(self, graph: dict, destination: str, *, category="global", timeout=30):
        if destination not in graph["pages"]:
            raise WorkflowError("未知导航目标 " + destination)
        self.graph, self.pages, self.destination = graph, graph["pages"], destination
        self.category, self.timeout = category, timeout
        self.current = self.entered = None
        self.penalties = {}
        self.candidates = None
        self.pending = None
        self.phase = "detect"
        self.edge = None
        self.stage_started = self.last_progress = None
        self.last_signature = None
        self.hooks = []
        self.hook_context = None
        self.hook_after = None
        self.stack = []
        self.result = None
        self.unknown_history = []
        self.failures = 0
        self.failed_key = None
        self._stable_destination = False
        self.fallback_attempted = False
        self.call_started = None
        self.call_finished = False

    def path(self, current):
        allowed = {"global", self.category, self.pages[self.destination].get("category", "global"),
                   self.pages[current].get("category", "global")}
        nodes = {key for key, page in self.pages.items() if page.get("category", "global") in allowed}
        nodes |= {current, self.destination}
        queue, best, previous, sequence = [(0, 0, current)], {current: 0}, {}, 0
        while queue:
            cost, _, key = heapq.heappop(queue)
            if cost > best[key]:
                continue
            if key == self.destination:
                break
            for edge in self.graph.get("links", []):
                if edge["from"] != key or edge["to"] not in nodes:
                    continue
                target = edge["to"]
                value = cost + self.pages[target].get("cost", 1) + edge.get("cost", 0) + self.penalties.get(edge["key"], 0)
                if value >= best.get(target, float("inf")):
                    continue
                best[target], previous[target] = value, edge
                sequence += 1
                heapq.heappush(queue, (value, sequence, target))
        if current == self.destination:
            return []
        if self.destination not in previous:
            return None
        route, key = [], self.destination
        while key != current:
            edge = previous[key]
            route.append(edge)
            key = edge["from"]
        return list(reversed(route))

    def _detect(self, match):
        # Candidate membership is frozen from the first frame. A page that
        # appears only in the second frame is not a two-frame confirmation.
        if self.candidates is None:
            if self.current and match(self.pages[self.current]["when"]):
                self.candidates = [self.current]
            else:
                scoped = {"global", self.category, self.pages[self.destination].get("category", "global")}
                found = [key for key, page in self.pages.items()
                         if page.get("category", "global") in scoped and match(page["when"])]
                if not found:
                    found = [key for key, page in self.pages.items() if match(page["when"])]
                self.candidates = sorted(found, key=lambda key: -self.pages[key].get("priority", 50))
            return None
        candidates, self.candidates = self.candidates, None
        return next((key for key in candidates if match(self.pages[key]["when"])), None)

    def _begin_hooks(self, nodes, guard, after):
        self.hooks = list(nodes)
        self.hook_context, self.hook_after = guard, after
        self.stack, self.result = [], None
        self.phase = "hooks"

    def _finish_node(self, result):
        self.stack.pop()
        if self.stack:
            self.stack[-1].results.append(result)
            self.stack[-1].index += 1
        else:
            self.result = result

    def _hook_step(self, match, now):
        while self.stack:
            frame = self.stack[-1]
            node = frame.node
            if "blocked" in node:
                return NavigationDecision(blocked=node["blocked"], page=self.current)
            if not frame.entered:
                if node.get("when") and not match(node["when"]):
                    self._finish_node(False)
                    continue
                frame.entered = True
            if "result" in node:
                self._finish_node(node["result"])
                continue
            if "invoke" in node:
                self.pending, self.call_started = "call", now
                return NavigationDecision(page=self.current, invocation=node["invoke"])
            if "repeat" in node:
                if match(node["until"]):
                    self._finish_node(True)
                    continue
                if frame.started is None:
                    frame.started = now
                if now - frame.started > node.get("timeout_s", 30):
                    return NavigationDecision(blocked="导航重复 hook 达到安全时限", page=self.current)
                if frame.results:
                    frame.results.clear()
                    frame.index = 0
                    return NavigationDecision(page=self.current)
                self.stack.append(_Sequence(node["repeat"]))
                continue
            if "steps" in node or "choice" in node:
                children = node.get("steps", node.get("choice"))
                if "choice" in node and frame.results and frame.results[-1]:
                    self._finish_node(True)
                    continue
                if frame.index < len(children):
                    self.stack.append(_Sequence(children[frame.index]))
                    continue
                index = node.get("success_index", 0)
                self._finish_node(False if "choice" in node else
                                  frame.results[index] if index < len(frame.results) else any(frame.results))
                continue
            # ConditionalAction's predicate is latched once; it must not be
            # silently re-evaluated after a sequence's first click changed UI.
            # A RuleImage/OCR leaf supplies its own fresh positive guard. Raw
            # RuleClick leaves still need a currently true positive ancestor or
            # page context before they can produce a native input.
            guards = [node["when"]] if node.get("when") else []
            if not any(_positive(guard) for guard in guards):
                guards.extend(parent.node["when"] for parent in self.stack[:-1]
                              if parent.node.get("when") and _positive(parent.node["when"])
                              and match(parent.node["when"]))
            if self.hook_context:
                # Image/OCR hook guards remain valid after page change; a raw
                # fixed-position RuleClick additionally needs a confirmed page.
                if not guards or not set(node["action"]) & {"click_found"}:
                    if not guards:
                        guards.append(self.hook_context)
            if not guards:
                return NavigationDecision(blocked="固定区域 hook 缺少当前画面守卫", page=self.current)
            guard = guards[0] if len(guards) == 1 else {"all": guards}
            if not _positive(guard):
                if self.hook_context and _positive(self.hook_context):
                    guard = {"all": [self.hook_context, guard]}
                else:
                    return NavigationDecision(blocked="导航 hook 缺少必经的正向画面守卫", page=self.current)
            if not match(guard):
                self._finish_node(False)
                continue
            self.pending = "hook"
            return NavigationDecision(action=node["action"], guard=guard, page=self.current)
        return None

    def acknowledge(self, sent: bool):
        if self.pending != "hook" or not self.stack:
            raise WorkflowError("没有待确认的导航输入")
        self.pending = None
        self._finish_node(bool(sent))

    def return_from_call(self, invocation: str, result: bool, now: float):
        if (self.pending != "call" or not self.stack or self.stack[-1].node.get("invoke") != invocation
                or type(result) is not bool or not math.isfinite(now) or now < self.call_started):
            raise WorkflowError("没有匹配的待返回导航调用")
        # Upstream callbacks block the outer navigation loop. Their own native
        # actions remain bounded by the same Runner; suspend only this planner's
        # no-progress/edge clock, never the run, trial or resource budget.
        duration = now - self.call_started
        self.last_progress += duration
        if self.stage_started is not None:
            self.stage_started += duration
        self.pending, self.call_started = None, None
        self.call_finished = True
        self._finish_node(result)

    def _edge_hooks(self, successful):
        edge = self.edge
        suffix = "success" if successful else "failure"
        nodes = []
        for owner, stage in ((self.pages[edge["from"]], "leave_" + suffix),
                             (edge, "leave_" + suffix),
                             (self.pages[edge["to"]], "enter_" + suffix),
                             (edge, "enter_" + suffix)):
            nodes.extend(owner.get("hooks", {}).get(stage, []))
        return nodes

    def _unknown(self, match, now):
        for index, node in enumerate(self.graph.get("unknown_closers", [])):
            if self.unknown_history[-3:] == [index] * 3:
                continue
            guard = node.get("when")
            if guard and match(guard):
                self.unknown_history.append(index)
                self.unknown_history = self.unknown_history[-20:]
                self._begin_hooks([node], guard, "unknown_done")
                return self.step(match, now)
        self.unknown_history.append(None)
        self.unknown_history = self.unknown_history[-20:]
        self.current = None
        return NavigationDecision(page=None)

    def step(self, match, now):
        if self.pending:
            raise WorkflowError("必须先确认导航动作结果")
        if self.last_progress is None:
            self.last_progress = now
        if now - self.last_progress > self.timeout:
            return NavigationDecision(blocked=f"页面导航 {self.timeout} 秒没有进展", page=self.current)
        for _ in range(512):
            if self.phase == "hooks":
                if not self.stack and self.hooks:
                    self.stack.append(_Sequence(self.hooks.pop(0)))
                    self.result = None
                decision = self._hook_step(match, now)
                if decision:
                    return decision
                if self.hooks:
                    continue
                after, result = self.hook_after, self.result
                self.hook_after = None
                if after == "entered":
                    self.entered = self.current
                    self.phase = "route"
                elif after == "edge_action":
                    if result:
                        self.phase, self.stage_started = "wait_arrival", now
                        self.candidates = None
                    elif now - self.stage_started >= 6:
                        if self.edge.get("fallback") and not self.fallback_attempted:
                            self.fallback_attempted = True
                            self._begin_hooks([self.edge["fallback"]], self.pages[self.edge["from"]]["when"], "edge_action")
                        else:
                            self._fail_edge(now)
                    else:
                        self.phase = "edge_action"
                        return NavigationDecision(page=self.current)
                elif after == "edge_success":
                    self.entered = self.current
                    self.failures, self.failed_key = 0, None
                    self.phase = "route"
                elif after == "edge_failure":
                    self.phase = "detect"
                    self.candidates = None
                    if self.failures % 3 == 0:
                        return self._unknown(match, now)
                elif after == "unknown_done":
                    # A planned or skipped closer is not progress.
                    if result:
                        self.last_progress = now
                    self.phase, self.candidates = "detect", None
                    return NavigationDecision(page=self.current, progress=bool(result))
                if self.call_finished:
                    # A callback may consume an entire battle. Reconfirm the
                    # page after it returns before any route or arrival claim.
                    self.call_finished = False
                    self.phase, self.candidates = "detect", None
                    return NavigationDecision(page=self.current)
                continue
            if self.phase == "wait_arrival":
                target = self.edge["to"]
                if self._stable_destination and match(self.pages[target]["when"]):
                    self.current = target
                    self.last_progress = now
                    self._stable_destination = False
                    self._begin_hooks(self._edge_hooks(True), self.pages[target]["when"], "edge_success")
                    continue
                self._stable_destination = match(self.pages[target]["when"])
                if now - self.stage_started >= 4:
                    self._fail_edge(now)
                    continue
                return NavigationDecision(page=self.current)
            if self.phase == "edge_action":
                self._begin_hooks([self.edge["action"]], self.pages[self.edge["from"]]["when"], "edge_action")
                continue
            if self.phase == "detect":
                confirming = self.candidates is not None
                found = self._detect(match)
                if not found:
                    if confirming:
                        return self._unknown(match, now)
                    return NavigationDecision(page=self.current)
                if self.current != found:
                    self.last_progress = now
                self.current = found
                if self.entered != found:
                    self._begin_hooks(self.pages[found].get("hooks", {}).get("enter_success", []),
                                      self.pages[found]["when"], "entered")
                else:
                    self.phase = "route"
                continue
            if self.phase == "route":
                if self.current == self.destination:
                    return NavigationDecision(page=self.current, arrived=True)
                route = self.path(self.current)
                if not route:
                    self.phase = "detect"
                    return self._unknown(match, now)
                signature = (self.current, tuple(edge["key"] for edge in route))
                if signature != self.last_signature:
                    self.last_progress, self.last_signature = now, signature
                self.edge, self.stage_started, self.phase = route[0], now, "edge_action"
                self.fallback_attempted = False
                continue
            raise WorkflowError("无效导航阶段 " + self.phase)
        raise WorkflowError("导航内部步骤超过上限")

    def _fail_edge(self, now):
        key = self.edge["key"]
        self.penalties[key] = self.penalties.get(key, 0) + 1
        self.failures = self.failures + 1 if self.failed_key == key else 1
        self.failed_key = key
        # Failure does not reset the no-progress clock. Hooks themselves still
        # need a fresh positive visual guard before any returned input.
        self._begin_hooks(self._edge_hooks(False), None, "edge_failure")
