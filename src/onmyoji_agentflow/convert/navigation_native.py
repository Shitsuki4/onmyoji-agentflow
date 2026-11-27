"""Compile inert OAS page descriptors to the closed native navigation model.

Untranslated callable hooks remain blocking nodes with source locations. The
result reports semantic gaps independently of structural extraction success.
It is never a claim that login/battle/host instrumentation has been converted.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

from ..yamlio import load_yaml
from ..workflow.schema import SUPPORTED_IMAGE_METHODS
from .astpins import source_node_hash

_HELPER_PINS = {
    "random_click": "ef3b4e97ac1ecbf5cb8c1005d136299436e532d10fbde9412db0d28cb6ba9a93",
    "exploration_to_six_gates": "e7c7005731915b13fb1f769ad780f54289d1e1b0563925c313b06dfcf8d77162",
    "handle_battle_reward_page": "0f09abeee0fd9b997b13f304f0d60e56484c85ff972217894f9fff8c663434a8",
    "handle_battle_page": "4e5e3920fda9c22b3bcc1651442d4c7a932eb27c91f68fb335a723e368511ac7",
    "handle_login_page": "797817673001ff0d0bc74298fd53a6d21e3cc31ddc6640fe6298c631c8557007",
}


class NavigationCompiler:
    def __init__(self, graph, resource_dir, *, battle_hook=None, login_hook=None, asset_overrides=None):
        self.graph = graph
        self.resource_dir = Path(resource_dir)
        self.documents, self.refs, self.diagnostics = {}, [], list(graph.get("diagnostics", []))
        self.asset_overrides = dict(asset_overrides or {})
        if battle_hook is not None and battle_hook is not False and (not isinstance(battle_hook, str) or not battle_hook):
            raise ValueError("battle_hook 必须绑定有限调用名或源码缺失配置分支")
        self.battle_hook = battle_hook
        if login_hook is not None and (not isinstance(login_hook, str) or not login_hook):
            raise ValueError("login_hook 必须绑定有限调用名")
        self.login_hook = login_hook

    def asset(self, item):
        task, name = item["task"], item["name"]
        task, name = self.asset_overrides.get((task, name), (task, name))
        if task not in self.documents:
            path = self.resource_dir / (task + ".yaml")
            self.documents[task] = (load_yaml(path) or {}).get("resources", {}) if path.is_file() else {}
            self.refs.append("upstream/oas/" + task + ".yaml")
        if name not in self.documents[task]:
            raise ValueError(f"缺少资源 {task}::{name}")
        return task + "::" + name, self.documents[task][name]

    def condition(self, item):
        if not isinstance(item, dict):
            raise ValueError("导航 matcher 不是静态对象")
        for key in ("all", "any", "alternatives"):
            if key in item:
                children = [self.condition(value) for value in item[key]]
                if not children:
                    raise ValueError("空组合 matcher")
                return {"any" if key == "alternatives" else key: children}
        if "not" in item:
            return {"not": self.condition(item["not"])}
        if "task" in item:
            name, spec = self.asset(item)
            if spec["type"] in ("image", "colors", "find_colors"):
                return {"res": name}
            if spec["type"] == "ocr" and isinstance(spec.get("keyword"), str) and spec["keyword"]:
                # OAS RuleOcr applies keyword regexes, not literal substring matching.
                return {"text": "", "pattern": spec["keyword"], "region": spec["roi"]}
            raise ValueError("matcher 资源类型尚未转换：" + name)
        if "callable" in item:
            callback = item["callable"]
            expression = ast.parse(callback.get("lambda", "None"), mode="eval").body
            if isinstance(expression, ast.Lambda):
                if len(expression.args.args) != 1:
                    raise ValueError("lambda matcher 参数不完整")
                return self._lambda_condition(expression.body, callback, expression.args.args[0].arg)
        raise ValueError("未转换 matcher：" + str(item))

    def _lambda_condition(self, node, callback, argument):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return {"not": self._lambda_condition(node.operand, callback, argument)}
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "appear"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == argument
                and len(node.args) == 1 and not node.keywords):
            asset = node.args[0]
            if isinstance(asset, ast.Attribute) and isinstance(asset.value, ast.Name):
                task = callback.get("assets", {}).get(asset.value.id)
                if task:
                    return self.condition({"task": task, "name": asset.attr})
        raise ValueError("尚未转换的 callable matcher：" + callback.get("file", "") + ":" + str(callback.get("line")))

    def _audited_helper(self, name):
        descriptor = self.graph.get("functions", {}).get("GameUi/default_pages.py:" + name, {})
        source = descriptor.get("source", "")
        if not source:
            raise ValueError("缺少完整导航 helper 源码：" + name)
        digest = source_node_hash(ast.parse(source).body[0], style="legacy-311")
        if digest != _HELPER_PINS.get(name):
            raise ValueError("导航 helper 指纹未核对：" + name)

    def _random(self, enabled=(True, False, True, False)):
        self._audited_helper("random_click")
        rects = []
        for side, use in zip(("LEFT", "TOP", "RIGHT", "BOTTOM"), enabled):
            if use:
                _, spec = self.asset({"task": "Component_GeneralBattle", "name": "C_RANDOM_" + side})
                rects.append(spec["rect"])
        if not rects:
            raise ValueError("随机导航点击没有允许区域")
        return {"action": {"click_random": rects, "delay": 800, "recheck": True}}

    def _callable(self, descriptor):
        name = descriptor.get("name")
        if name == "handle_login_page" and self.login_hook is not None:
            self._audited_helper(name)
            return {"invoke": self.login_hook}
        if name == "handle_battle_page":
            self._audited_helper(name)
            if self.battle_hook is False:
                return {"result": False}
            if self.battle_hook is not None:
                return {"invoke": self.battle_hook}
        if name in ("exploration_to_six_gates", "handle_battle_reward_page"):
            self._audited_helper(name)
            if name == "exploration_to_six_gates":
                return {"choice": [self.action({"task": "GameUi", "name": "I_EXPLORATION_TO_" + suffix})
                    for suffix in ("MOON_SEA", "INCENSE_REALM", "SEASONRIFT_FOREST", "PURE_BUDDHA_REALM",
                                   "MANTRA_TOWER", "PEACOCK_KINGDOM")]}
            return {"choice": [self.action({"task": "Component_GeneralBattle", "name": "I_OVER_GHOST"}), self._random()]}
        expression = descriptor.get("lambda")
        if expression:
            # Recognize these reviewed finite callback forms structurally.
            # No expression is evaluated and no name is imported/resolved.
            tree = ast.parse(expression, mode="eval").body
            if not isinstance(tree, ast.Lambda) or len(tree.args.args) != 1:
                raise ValueError("尚未转换 lambda 形式")
            body = tree.body
            if isinstance(body, ast.Call) and isinstance(body.func, ast.Name) and body.func.id == "random_click" and not body.args and not body.keywords:
                return self._random()
            expected = ast.parse("lambda task: task.ui_click(click=random_click(ltrb=(False, False, False, True)), stop=GlobalGameAssets.I_UI_BACK_YELLOW)", mode="eval").body
            if ast.dump(tree, include_attributes=False) == ast.dump(expected, include_attributes=False):
                return {"repeat": self._random((False, False, False, True)),
                        "until": self.condition({"task": "GlobalGame", "name": "I_UI_BACK_YELLOW"}), "timeout_s": 30}
        raise ValueError("原生回调尚未转换：" + descriptor.get("name", descriptor.get("lambda", "")) +
                         " @" + descriptor.get("file", "") + ":" + str(descriptor.get("line", "")))

    def blocked(self, item, reason):
        self.diagnostics.append({"reason": reason, "source": copy.deepcopy(item)})
        return {"blocked": reason}

    def action(self, item):
        try:
            if not isinstance(item, dict):
                raise ValueError("动作不是静态对象")
            if "condition" in item and "action" in item:
                action = self.action(item["action"])
                return {"when": self.condition(item["condition"]), "steps": [action]}
            if "sequence" in item or "alternatives" in item:
                items = item.get("sequence", item.get("alternatives"))
                if not items:
                    raise ValueError("空动作序列")
                return {"steps": [self.action(child) for child in items],
                        "success_index": item.get("success_index", 0)}
            if "task" in item:
                name, spec = self.asset(item)
                if spec["type"] == "image":
                    if spec.get("method", "Template matching") not in SUPPORTED_IMAGE_METHODS:
                        raise ValueError("图片匹配方法尚未转换：" + name)
                    return {"when": {"res": name}, "action": {"click_found": True,
                            "use_match_size": True, "delay": 800, "recheck": True}}
                if spec["type"] == "click":
                    return {"action": {"click": name, "delay": 800, "recheck": True}}
                if spec["type"] == "ocr":
                    return {"when": self.condition(item), "action": {"click_found": True,
                            "offset": [-5, -5, 5, 5], "delay": 800, "recheck": True}}
                raise ValueError("动作资源类型尚未转换：" + name)
            if "callable" in item:
                return self._callable(item["callable"])
            raise ValueError("动作工厂尚未转换：" + str(item))
        except (ValueError, KeyError, SyntaxError) as error:
            return self.blocked(item, str(error))

    def hooks(self, owner):
        return {stage: [self.action(item) for item in items]
                for stage, items in owner.get("hooks", {}).items()}

    def compile(self, *, calibrations=None):
        if self.graph.get("format") != 2:
            raise ValueError("必须先提取 format:2 完整导航图")
        result = {"format": 1, "pages": {}, "links": [], "unknown_closers": []}
        for key, page in self.graph["pages"].items():
            # Recognition gaps cannot safely be represented as always-false
            # pages. Reject rather than quietly discarding such a node.
            result["pages"][key] = {"when": self.condition(page["check"]),
                "priority": page.get("priority", 50), "cost": page.get("cost", 1),
                "category": page.get("category", "global"), "hooks": self.hooks(page)}
        repairs = []
        for key, calibration in (calibrations or {}).get("pages", {}).items():
            if key not in result["pages"]:
                raise ValueError("校准页面不存在：" + key)
            original = self.graph["pages"][key]["check"]
            fingerprint = hashlib.sha256(json.dumps(original, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if calibration.get("original_check_sha256") != fingerprint:
                raise ValueError("页面原识别条件已变化，必须复核校准：" + key)
            evidence = calibration.get("evidence", {})
            if (not isinstance(evidence, dict) or evidence.get("resolution") != [1280, 720]
                    or not isinstance(evidence.get("sha256"), str) or len(evidence["sha256"]) != 64):
                raise ValueError("校准缺少真实保存帧的分辨率与摘要：" + key)
            # Only add a separately reviewed recognition alternative; never
            # remove or weaken the source marker silently. Schema validation
            # subsequently checks this native condition before any execution.
            additional = copy.deepcopy(calibration["additional"])
            from ..workflow.navigation import _positive
            if not _positive(additional):
                raise ValueError("校准必须含必经的正向识别：" + key)
            result["pages"][key]["when"] = {"any": [result["pages"][key]["when"], additional]}
            repairs.append({"page": key, **copy.deepcopy(calibration), "approval": "unreviewed"})
        for edge in self.graph["links"]:
            hooks = {stage: edge.get("on_" + stage, {}).get("alternatives", [])
                     for stage in ("enter_success", "enter_failure", "leave_success", "leave_failure")}
            native_edge = {"key": edge["key"], "from": edge["from"], "to": edge["to"],
                "cost": edge.get("cost", 0), "action": self.action(edge["button"]),
                "hooks": self.hooks({"hooks": hooks})}
            if edge["from"] == "page_town" and "task" in edge["button"]:
                _, spec = self.asset(edge["button"])
                if spec["type"] == "image":
                    x, y, w, h = spec["front"]
                    cx, cy = x + w // 2, y + h // 2
                    native_edge["fallback"] = {"action": {"click": [cx, cy, cx, cy], "delay": 800}}
            result["links"].append(native_edge)
        for node in self.graph.get("unknown_closers", {}).get("alternatives", []):
            # A global affirmative dialog is not evidence of a harmless exit.
            # Keep this source branch visible and require an audited context.
            if node.get("name") in ("I_UI_CONFIRM", "I_UI_CONFIRM_SAMLL"):
                self.blocked(node, "通用确认关闭器需要具体弹窗上下文，不能直接发送肯定输入")
                continue
            result["unknown_closers"].append(self.action(node))
        return {"navigation": result, "resources": sorted(set(self.refs)), "resource_namespaces": True,
                "complete": not self.diagnostics, "unsupported": self.diagnostics,
                "source_files": copy.deepcopy(self.graph.get("source_files", [])), "recognition_repairs": repairs}
