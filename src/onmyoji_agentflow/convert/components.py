"""Pinned translations of complete AutoJS *components*, never whole schemes.

The input is an inert snapshot.  Unknown fingerprints and unsupported operator
fields fail closed rather than discarding code or guessing coordinates.  Shared
variables retain their upstream names; composing a scheme still requires its
ordering, defaults, counts, stop rules, and transitions to be translated.
"""
from __future__ import annotations

import re
from pathlib import Path

from .assttyys import convert_func
from ..workflow.schema import bundled_dir
from ..yamlio import load_yaml


class UnsupportedComponent(ValueError):
    pass


def matches_component_pin(entry, pins):
    fingerprint = entry.get("fingerprint")
    expected = pins.get(entry.get("id"))
    accepted = expected if isinstance(expected, list) else [expected]
    return bool(fingerprint) and fingerprint in accepted


class ComponentBuilder:
    def __init__(self, entry, root):
        self.entry = entry
        folder = Path(root) / "resources/upstream/assttyys"
        self.colors = (load_yaml(folder / "colors.yaml") or {})["resources"]
        scripts = [path for path in entry.get("entry_files", []) if "/funcList/" in path]
        if len(scripts) != 1:
            raise UnsupportedComponent("组件必须有且仅有一个 funcList 入口")
        self.path = folder / "programs/src" / (scripts[0] + ".txt")
        self.source = self.path.read_text(encoding="utf-8")
        self.func = convert_func(self.path, self.colors)
        if not self.func or self.func["parse_error"] or self.func["config_error"]:
            raise UnsupportedComponent("完整 operator/config 数据解析失败")
        self.ops = self.func["operators"]
        for op in self.func["raw_operators"]:
            if set(op) - {"desc", "oper", "operStepRandom", "retest", "notForCnt"}:
                raise UnsupportedComponent("出现尚未实现的 operator 字段")
        self.raw = {"format": 1, "name": entry["workflow"], "title": entry["title"],
                    "resources": ["upstream/assttyys/colors.yaml"], "params": {}, "vars": {},
                    "limits": {"timeout_s": 300, "unknown_timeout_s": 20, "stuck_timeout_s": 90,
                               "no_progress_timeout_s": 180, "max_repeat": 20}, "states": []}

    def when(self, index):
        op = self.ops[index]
        if op.get("unknown_ref"):
            raise UnsupportedComponent("未知识别资源：" + op["unknown_ref"])
        if op.get("detect"):
            return {"res": op["detect"]}
        if op.get("detect_points"):
            return {"colors": op["detect_points"]}
        raise UnsupportedComponent(f"operator {index} 缺少正向识别")

    @staticmethod
    def action(operation):
        rect = operation["rect"]
        if rect == [-1, -1, -1, -1]:
            return {"wait": operation["delay"]}
        if any(v < 0 for v in rect) or rect[0] > rect[2] or rect[1] > rect[3]:
            raise UnsupportedComponent("点击区域无效")
        out = {"click": rect, "delay": operation["delay"]}
        if operation.get("press_ms"):
            out["press_ms"] = operation["press_ms"]
        return out

    def actions(self, index):
        op = self.ops[index]
        if op.get("oper_step_random"):
            raise UnsupportedComponent("operStepRandom 依据设备哈希固定选择，不能替换成每次随机点击；请使用已核对的 handler 编译路径")
        return [self.action(op) for op in op.get("oper", [])] or [{"wait": 300}]

    def state(self, index, *, condition=None, guard=None, actions=None, suffix="", **extra):
        condition = self.when(index) if condition is None else condition
        if guard:
            condition = {"all": [{"expr": guard}, condition]}
        state = {"id": f"op_{index}" + suffix, "when": condition,
                 "do": self.actions(index) if actions is None else actions,
                 "from": f"assttyys {self.func['id']:03d} #{index}", **extra}
        if self.ops[index].get("retest_ms"):
            state["retest_ms"] = self.ops[index]["retest_ms"]
        self.raw["states"].append(state)

    def build(self):
        fid = self.func["id"]
        if fid in (11, 505):
            if self.func["needs_translation"]:
                raise UnsupportedComponent("原声明已新增自定义逻辑")
            for index in range(len(self.ops)):
                self.state(index)
        elif fid == 1:
            self.raw["params"] = {"exitBeforeReady": {"default": False}}
            self.raw["vars"] = {"redFlag": False}
            literal = re.search(r"const\s+themeDescList\s*=\s*(\[[\s\S]*?\]);", self.source)
            if not literal:
                raise UnsupportedComponent("缺少主题列表")
            from .jsliteral import parse
            themes = parse(literal[1])
            for index, theme in enumerate(themes):
                ready = {"res": "准备界面_未准备_" + theme}
                auto = {"res": "战斗界面_手动状态_" + theme}
                for resource in (ready["res"], auto["res"]):
                    if resource not in self.colors:
                        raise UnsupportedComponent("主题资源缺失：" + resource)
                ops = self.ops[0]["oper"]
                self.state(0, suffix=f"_exit_{index}", condition=ready, guard="exitBeforeReady",
                           actions=[self.action(op) for op in ops[1:]])
            for index, theme in enumerate(themes):
                ready = {"res": "准备界面_未准备_" + theme}
                self.state(0, suffix=f"_ready_{index}", condition=ready, guard="not exitBeforeReady",
                           actions=[self.action(ops[0]), {"set": {"redFlag": False}}])
            for index, theme in enumerate(themes):
                auto = {"res": "战斗界面_手动状态_" + theme}
                self.state(1, suffix=f"_auto_{index}", condition=auto, guard="not exitBeforeReady",
                           actions=self.actions(1) + [{"set": {"redFlag": False}}], retest_ms=1000)
        elif fid == 7:
            self.raw["params"] = {"switch_nineWin": {"default": False}}
            gate = {"all": [self.when(4), {"any": [{"expr": "not switch_nineWin"},
                {"all": [{"expr": "switch_nineWin"}, {"find": "突破失败", "similarity": 95}]}]}]}
            for index in range(4):
                self.state(index, condition={"all": [gate, self.when(index)]})
        elif fid == 25:
            self.state(0, condition={"all": [self.when(1), {"not": self.when(0)}]})
            self.state(3)
        elif fid == 29:
            operation = self.ops[0]["oper"][0]
            x1, y1, x2, y2 = operation["rect"]
            self.state(0, condition={"all": [{"any": [self.when(0), self.when(1)]},
                       {"find": "庭院_探索灯笼"}]}, actions=[{"click_found": True,
                       "offset": [x1, y1, x2, y2], "delay": operation["delay"]}])
        elif fid == 35:
            self.raw["vars"] = {"checked_yard_count": 0}
            for index in range(4):
                self.state(index, actions=self.actions(index) + [{"set": {"checked_yard_count": 1}}])
        elif fid == 38:
            empty = {"any": [self.when(index) for index in (1, 2, 3)]}
            self.state(0, condition={"all": [self.when(0), {"not": empty}]})
            self.state(1, condition={"all": [self.when(0), empty]}, actions=[{"stop": {
                "reason": "组队暂时没有队员；组件返回未处理，交回调用方继续扫描", "result": "skipped",
                "verified": False, "evidence": {"component_handled": False}}}], component_handled=False)
        elif fid == 501:
            self.raw["params"] = {"once": {"default": False}}
            self.raw["vars"] = {"run_times_40": 0, "run_times_50": 0}
            guard = "not once or (run_times_40 <= 0 and run_times_50 <= 0)"
            for index in range(len(self.ops)):
                self.state(index, guard=guard)
        elif fid == 509:
            self.raw["vars"] = {"change_shikigami_flag": True}
            # The original first recognises records and clears the flag, then
            # considers navigation in the same invocation.  No input follows
            # recognition of records; other visual states are disjoint.
            self.state(3, guard="change_shikigami_flag", actions=[
                {"set": {"change_shikigami_flag": False}}, {"wait": 300}])
            for index in (0, 1, 2, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16):
                self.state(index, guard="change_shikigami_flag", actions=self.actions(index) + [{"wait": 1000}])
        elif fid == 990:
            self.raw["vars"] = {"shaoTiao": False}
            for index in (0, 1, 2, 7):
                self.state(index, actions=[{"set": {"shaoTiao": True}}, {"wait": 1000}])
            for index in (3, 4):
                self.state(index, guard="shaoTiao")
            for index in (5, 6):
                self.state(index, guard="shaoTiao", actions=[{"set": {"shaoTiao": False}}, {"wait": 300}])
            self.raw["states"].append({"id": "active_wait", "when": {"expr": "shaoTiao"},
                                       "do": [{"wait": 300}]})
        else:
            raise UnsupportedComponent("尚无完整组件转换")
        self.raw["requires"] = ["组件片段：调用方必须提供共享变量、handled/unhandled 返回、全局计数和方案调度"]
        # Record the framework obligations explicitly. A standalone test does
        # not supply the original Script dispatcher/counting contract.
        self.raw["component_contract"] = {"id": fid, "standalone_equivalence": False,
            "requires_dispatcher": True, "shared_variables": sorted(self.raw["vars"]),
            "counter_id": {1: 1, 7: 7, 11: 11, 25: None, 29: None, 35: 38,
                           38: 38, 501: 501, 505: 505, 509: None, 990: None}[fid],
            "counting": "upstream Script.oper 7500ms suppression; not implemented by standalone runner",
            "unmatched_return": False}
        return self.raw


def known_component(entry, root):
    if entry.get("source") != "assttyys" or entry.get("kind") != "component":
        return None
    pins = load_yaml(bundled_dir() / "translations/component-pins.yaml") or {}
    if not matches_component_pin(entry, pins):
        return None
    builder = ComponentBuilder(entry, root)
    return {"complete": True, "unsupported": [], "coverage": "component_fragment",
            "notes": "组件片段分支已转换；不是独立等价程序。handled/yield、共享计数与方案切换仍须调用方实现，不计为原始任务完整转换。",
            "workflow": builder.build()}
