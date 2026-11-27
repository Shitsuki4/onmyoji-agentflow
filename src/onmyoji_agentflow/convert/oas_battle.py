"""Audited, inert-source lowering of GeneralBattle.run_general_battle.

``compile_general_battle(oas_root, resource_dir, ...)`` returns an ordinary
format:1 workflow and a source-obligation packet. ``oas_root`` may also be the
program inventory's ``programs/src`` snapshot directory (``*.py.txt`` files).
Nothing from that directory is imported, evaluated, or executed. ``resource_dir``
is the directory containing converted ``Component_GeneralBattle.yaml`` files.

This is a *single invocation* family fragment, not a task/dispatcher compiler.
Config fields remain runtime parameters, including non-default branches. A bound
``buff`` argument is an ordered literal sequence of BuffClass names/values.
Caller overrides must be supplied through ``owner=(relative_file, class_name)``;
unresolved inheritance and overridden helpers fail closed. Task callbacks are
never interpreted. The caller owns task/resource budgets, approvals, surrounding
navigation, current_count continuity, and integration of the returned boolean.

Missing native helpers are executable failure gates at their source position,
not no-ops. BUFF helpers use captured OCR/image-relative ROIs; the source's
unhandled all-zero OCR result retains an explicit safety obligation. Preset
Single-OCR retains exact whole-line equality and the source ROI click. Preset
decisions use the source region-mean RGB tolerance metric,
never point samples or fixed selection assumptions. Bounded samples preserve the battle-idle
4/501 trigger, conditional three-way selection, and independent target cooldowns.
``complete`` covers all runtime config choices, never just their defaults.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import re
from pathlib import Path

from yaml import YAMLError

from ..yamlio import load_yaml
from ..workflow.schema import SUPPORTED_IMAGE_METHODS
from .astpins import source_node_hash


BATTLE = "tasks/Component/GeneralBattle/general_battle.py"
BATTLE_WAIT = "tasks/Component/GeneralBattle/battle_wait.py"
BATTLE_WAIT_PIN = "4a19487626edfcc930bad368b95b168a4561482d27cf264057fead62c55fc971"
CONFIG = "tasks/Component/GeneralBattle/config_general_battle.py"
ASSETS = "tasks/Component/GeneralBattle/assets.py"
BUFF = "tasks/Component/GeneralBuff/general_buff.py"
BUFF_CONFIG = "tasks/Component/GeneralBuff/config_buff.py"
BASE = "tasks/base_task.py"
UTILS = "module/base/utils/utils.py"
BUFF_OPERATIONS = {"awake": (202, 220), "soul": (222, 240), "gold_50": (84, 102),
                   "gold_100": (104, 122), "exp_50": (124, 150), "exp_100": (152, 178)}

# Canonical AST fingerprints, not caller-provided attestations. A changed body,
# signature, class base, default, or config arm needs a new source review.
SOURCE_PINS = {
    (BATTLE, "GeneralBattle"): "008e4d8b628d91e78a8d2a95f2e3bee6e959e0d8d53834c6473a55308c5cc9e7",
    (BATTLE, "run_task_or_default_general_battle"): "5c1098e42b867e8982ee740c6d59ade5f0fe0b7ac63ba3c2e015d3778f70ef15",
    (CONFIG, "GreenMarkType"): "f0986c004cac4703e28aa6754c0db599a0bab753504ac69560eecf446e17d6a8",
    (CONFIG, "GreenMarkEnum"): "74af421e7660efe80aae7d32810456e469b0339e5414bf8a0d88885096beea66",
    (CONFIG, "GeneralBattleConfig"): "6872e0d109558427f836e488139f317467ed2a9feecab3b537f85144470709ba",
    (BUFF, "GeneralBuff"): "78d643ef726a848caad146d498ef5a89bd983a47556ba4b4a29662c665be7918",
    (BUFF_CONFIG, "BuffClass"): "73bc4df8b13103cf3c85c2c1e1e44deb40cf4f2becd119c04f68946cc378b339",
    # Includes __new__: it wraps only _bw_* methods, not this entry's battle_wait.
    (BATTLE_WAIT, "BattleWait"): "1e0230168da7f945ad78c562d1e91431884c7274a1323f2a7f25875c99096042",
    (BASE, "BaseTask.appear"): "f350504816e2e4b29b1004a63d67dd833066726c8a2f75f6e3a0c9e593108b52",
    (BASE, "BaseTask.appear_then_click"): "6423233e67e6ced3a735c094deeb6327e9e28adf36532e70267a3a21a8beaffd",
    (BASE, "BaseTask.wait_until_appear"): "7df1fd661f438e429b2c0c2e2e22e3868273a38decc37d090b4b2bdb363b21b7",
    (BASE, "BaseTask.ui_click"): "82895b45eaa4574dd75f65bc37b050b3fcd4af1a06a07d8e2d3ffff7ead4ced4",
    (BASE, "BaseTask.ui_click_until_disappear"): "df718484825bbc8dd8d89ee665625dab22d5dadc753ba0936b59ffac5610ad23",
    (BASE, "BaseTask.click"): "a3aa167fab247793e5ac2795008d3be9bff1d3adfb853c0e5c96ca8f0e09d299",
    (BASE, "BaseTask.swipe"): "ced83d6918382a062ef71d78065bb5c8fb40febc40b0a88525b8fbaad211f758",
    (BASE, "BaseTask.ocr_appear"): "a8b4579fbca1274dfdeba4dfe2dc012738be7d682c6631946c0d716b281d1cd5",
    ("module/base/timer.py", "Timer"): "5469429f0bca141b576bfcee426d577f14911023fcc32dc8d0c363c37b1b57cb",
    (UTILS, "get_color"): "143fb5f2a5511500bf85a0c62daaec292f9e475fb69e4c23d10543b521f60c9b",
    (UTILS, "color_similar"): "97e2f2254db74e58c6f770a65c611a40e34fac597856bc0f201ecfbed076a3e5",
    ("module/ocr/sub_ocr.py", "Single"): "1cd17db6ff03a7479d3671af8eece0730adac152389cc4c5cefecfb4a0ab4ad2",
    ("module/ocr/base_ocr.py", "BaseCor"): "8135824553b35f3f4052e71f642434ffcbcc71431cf0b85af53f2cc53752df7d",
    ("module/ocr/base_ocr.py", "enlarge_canvas"): "5a9dedf5b9e919d6a00bdba7973b749c32128acd7448d81c9ef4447b564a3981",
    ("module/atom/ocr.py", "RuleOcr"): "5c0d51a77a92d03f5700d01625ff5a71ce768a4ac7321a91a7f0f8dfa8a8a3e1",
    ("module/ocr/ppocr.py", "sorted_boxes"): "65fe302c9308f72f94b9bf828a4f2a82c23494b9a6f6d7afe2c2d48f8caeaa0d",
    ("module/ocr/sub_ocr.py", "Full"): "bd2724b2b1b884b0dc4bad8ef9e1bc232517830f160505fb0278f0b35fb06a92",
    ("module/ocr/utils.py", "_merge_area"): "cc2d5c43db5455a58d4f4dab5d767b8761bdb9a53ea16c665a8c8a98353449f3",
    ("module/ocr/utils.py", "merge_area"): "dcff3d0be628544948975db099cffd68dc17c0084b2346819a2bc7d325e53aae",
    ("module/atom/image.py", "RuleImage.front_center"): "c75de639593890d18fb6c7e83e138833c72d530f85f2fabb2bec1d4d39822b34",
    ("module/atom/image.py", "RuleImage.name"): "ed5af149e223e96f2a11ec9228ca1652e982e91d7819fe8e8147e7b08933e041",
}


def _hash(node):
    return source_node_hash(node, style="compact-314")


def _ref(path, node=None, *, lines=None, symbol=None):
    start, end = lines or (getattr(node, "lineno", 1), getattr(node, "end_lineno", 1))
    out = {"path": path, "start_line": start, "end_line": end}
    if symbol:
        out["symbol"] = symbol
    return out


def _issue(kind, source, requirement, *, branch="all", **details):
    key = repr((kind, source, branch, requirement))
    return {"id": "gb_" + hashlib.sha256(key.encode()).hexdigest()[:12], "kind": kind,
            "source": source, "branch": branch, "requirement": requirement,
            "blocking": True, **details}


class _Missing(ValueError):
    def __init__(self, obligation):
        super().__init__(obligation["requirement"])
        self.obligation = obligation


class _Sources:
    def __init__(self, root):
        self.root, self.trees, self.files = Path(root), {}, {}

    def tree(self, relative):
        # Resolve only plain, workspace-relative data paths. No import machinery.
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("source paths must be relative to the inert OAS root")
        if relative not in self.trees:
            path = self.root / relative
            if not path.is_file():
                path = self.root / (relative + ".txt")
            try:
                raw = path.read_bytes()
                self.trees[relative] = ast.parse(raw.decode("utf-8-sig"), filename=relative)
            except (OSError, UnicodeError, SyntaxError) as error:
                raise _Missing(_issue("missing_source", _ref(relative),
                    "readable, parseable inert source", error=str(error))) from error
            self.files[relative] = {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}
        return self.trees[relative]

    def node(self, relative, selector):
        node = self.tree(relative)
        for part in selector.split("."):
            matches = [n for n in node.body if getattr(n, "name", None) == part]
            if len(matches) != 1:
                raise _Missing(_issue("missing_helper", _ref(relative, symbol=selector),
                    "one statically declared helper: " + selector))
            node = matches[0]
        return node

    def verify(self):
        for (path, selector), expected in SOURCE_PINS.items():
            node = self.node(path, selector)
            if _hash(node) != expected:
                raise _Missing(_issue("source_drift", _ref(path, node, symbol=selector),
                    "review changed helper before lowering", expected_ast_sha256=expected,
                    actual_ast_sha256=_hash(node)))

    def enum(self, path, name):
        node = self.node(path, name)
        return {n.targets[0].id: ast.literal_eval(n.value) for n in node.body
                if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}

    def config(self):
        enums = {name: self.enum(CONFIG, name) for name in ("GreenMarkType", "GreenMarkEnum")}
        out = {}
        for item in self.node(CONFIG, "GeneralBattleConfig").body:
            if not isinstance(item, ast.AnnAssign):
                continue
            options = {k.arg: k.value for k in item.value.keywords}
            value = options["default"]
            default = (enums[value.value.id][value.attr] if isinstance(value, ast.Attribute)
                       else ast.literal_eval(value))
            spec = {"default": default}
            for key, native in (("ge", "min"), ("le", "max")):
                if key in options:
                    spec[native] = ast.literal_eval(options[key])
            if isinstance(item.annotation, ast.Name) and item.annotation.id in enums:
                spec["choices"] = list(enums[item.annotation.id].values())
            out[item.target.id] = spec
        return out

    def asset(self, path, cls, name):
        declarations = [item for item in self.node(path, cls).body if isinstance(item, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == name for t in item.targets)]
        if len(declarations) > 1:
            raise _Missing(_issue("unsupported_resource", _ref(path, declarations[-1]),
                "one unambiguous asset declaration for " + name))
        for item in declarations:
            if (isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name)
                    and not item.value.args and all(k.arg for k in item.value.keywords)):
                try:
                    literal = {k.arg: ast.literal_eval(k.value) for k in item.value.keywords}
                except (ValueError, TypeError) as error:
                    raise _Missing(_issue("unsupported_resource", _ref(path, item),
                        "literal asset constructor arguments for " + name)) from error
                return item.value.func.id, literal, _ref(path, item)
        raise _Missing(_issue("missing_resource", _ref(path, symbol=cls + "." + name),
            "upstream asset declaration " + name))

    def check_owner(self, owner):
        if owner is None:
            return
        path, cls = owner
        node = self.node(path, cls)
        if node.decorator_list:
            raise _Missing(_issue("unresolved_inheritance", _ref(path, node),
                "resolve decorated task class before assuming base helper dispatch"))
        reachable = {"run_general_battle", "battle_before", "battle_wait", "_hook_special_reward",
                     "green_mark", "green_mark_choose", "switch_preset_team", "check_and_open_buff",
                     "is_in_battle", "is_in_real_battle", "is_in_prepare", "random_click_swipt",
                     "awake", "soul", "gold_50", "gold_100", "exp_50", "exp_100", "get_area",
                     "get_area_image", "set_switch_area", "reject_invite", "appear", "appear_then_click",
                     "click", "swipe", "ocr_appear", "screenshot", "ui_click", "ui_click_until_disappear",
                     "wait_until_appear", "__init__", "__getattribute__", "__getattr__"}
        for method in node.body:
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name in reachable:
                raise _Missing(_issue("overridden_helper", _ref(path, method, symbol=cls + "." + method.name),
                    "native translation of the task override; base implementation is not equivalent"))
            targets = method.targets if isinstance(method, ast.Assign) else [method.target] if isinstance(method, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id.startswith(("I_", "C_", "S_", "O_")) for t in targets):
                raise _Missing(_issue("overridden_resource", _ref(path, method), "bind task-local resource override"))
        # A narrowly understood direct inheritance is enough; arbitrary MROs are
        # deliberately not resolved by importing the task or guessing base order.
        if len(node.bases) != 1 or not isinstance(node.bases[0], ast.Name):
            raise _Missing(_issue("unresolved_inheritance", _ref(path, node), "resolve complete task MRO"))
        alias = node.bases[0].id
        imports = [(n.module, a.name) for n in self.tree(path).body if isinstance(n, ast.ImportFrom)
                   for a in n.names if (a.asname or a.name) == alias and n.level == 0]
        if imports != [("tasks.Component.GeneralBattle.general_battle", "GeneralBattle")]:
            raise _Missing(_issue("unresolved_inheritance", _ref(path, node),
                "prove dispatch reaches the pinned GeneralBattle implementation"))


class _Builder:
    def __init__(self, sources, resource_dir, prefix, current_count, buffs):
        self.src, self.folder, self.prefix = sources, Path(resource_dir), prefix
        self.obligations, self.documents, self.asset_data, self.refs = [], {}, {}, []
        self.buffs = buffs
        self.buff_contracts = []
        self.raw = {"format": 1, "name": prefix + "_general_battle", "title": "GeneralBattle single invocation",
                    "resource_namespaces": True, "resources": [], "params": sources.config(),
                    "vars": {}, "states": [], "loop_delay_ms": 0, "default_result": "unknown",
                    "limits": {"timeout_s": 3600, "unknown_timeout_s": 60, "stuck_timeout_s": 3600,
                               "no_progress_timeout_s": 3600, "max_repeat": 1000000}}
        for key, value in {"phase": "entry", "current_count": current_count, "confed": False,
                           "prep_started_ms": 0, "prep_return": False, "reward_started_ms": 0,
                           "outcome_known": False, "win": False, "returned": False, "return": False,
                           "mark_attempted": 0, "result_marker": "", "idle_trigger": 0, "idle_kind": 0,
                           "preset_team_committed": 0, "preset_ensure_started_ms": 0,
                           "preset_warn_started_ms": 0}.items():
            self.raw["vars"][self.v(key)] = value

    def v(self, key):
        return self.prefix + "_" + key

    def expr(self, text):
        # Only compiler-owned identifier tokens, never source Python expressions.
        return re.sub(r"\$([A-Za-z_][A-Za-z_0-9]*)", lambda m: self.v(m[1]), text)

    def assign(self, **values):
        return {"set": {self.v(k): self.expr(v) if isinstance(v, str) else v for k, v in values.items()}}

    def goto(self, phase):
        return self.assign(phase=repr(phase))

    def state(self, name, phase, actions, *, condition=None, guard=None, lines=(29, 51)):
        conditions = [{"expr": f"{self.v('phase')} == {phase!r}"}]
        if guard:
            conditions.append({"expr": self.expr(guard)})
        if condition:
            conditions.append(condition)
        self.raw["states"].append({"id": self.v(name), "when": {"all": conditions}, "do": actions,
            "phase": "battle" if phase.startswith("battle_") or phase == "de_win" else
                     "settlement" if phase.startswith(("result", "reward", "return")) else "preparation",
            "source": _ref(BATTLE, lines=lines)})

    def obligation(self, kind, lines, requirement, *, branch="all", path=BATTLE, **details):
        item = _issue(kind, _ref(path, lines=lines), requirement, branch=branch, **details)
        self.obligations.append(item)
        return item

    def blocked(self, name, phase, item, *, condition=None, guard=None):
        self.state(name, phase, [{"fail": "untranslated source obligation " + item["id"] + ": " + item["requirement"]}],
                   condition=condition, guard=guard,
                   lines=(item["source"]["start_line"], item["source"]["end_line"]))
        self.raw["states"][-1]["source"] = copy.deepcopy(item["source"])
        self.raw["states"][-1]["source_obligation"] = item["id"]

    def asset(self, name, namespace="Component_GeneralBattle"):
        alias = namespace + "::" + name
        if alias in self.asset_data:
            return alias, self.asset_data[alias]
        path = "tasks/" + namespace.replace("Component_", "Component/", 1) + "/assets.py"
        cls = {"Component_GeneralBattle": "GeneralBattleAssets", "Component_GeneralBuff": "GeneralBuffAssets",
               "Component_GeneralInvite": "GeneralInviteAssets"}[namespace]
        kind, literal, source = self.src.asset(path, cls, name)
        if namespace not in self.documents:
            resource_file = self.folder / (namespace + ".yaml")
            try:
                document = load_yaml(resource_file)
                if not isinstance(document, dict) or not isinstance(document.get("resources"), dict):
                    raise ValueError("resource document must have a resources mapping")
                self.documents[namespace] = document["resources"]
            except (OSError, ValueError, YAMLError, UnicodeError) as error:
                raise _Missing(_issue("missing_resource", source, "converted resource document " + str(resource_file))) from error
            self.refs.append("upstream/oas/" + namespace + ".yaml")
        spec = self.documents[namespace].get(name)
        if not isinstance(spec, dict):
            raise _Missing(_issue("missing_resource", source, "converted resource " + alias))
        required = {"RuleImage": ("roi_front", "roi_back", "threshold", "method"),
                    "RuleClick": ("roi_front", "roi_back"), "RuleOcr": ("roi", "keyword", "mode"),
                    "RuleSwipe": ("roi_front", "roi_back", "mode")}
        if kind in required and any(k not in literal for k in required[kind]):
            raise _Missing(_issue("unsupported_resource", source, "explicit literal asset fields for " + alias))
        for field in ("roi_front", "roi_back", "roi"):
            if field in literal and (not isinstance(literal[field], (list, tuple)) or len(literal[field]) != 4
                    or any(type(v) not in (int, float) for v in literal[field])):
                raise _Missing(_issue("unsupported_resource", source, "literal numeric XYWH " + field + " for " + alias))
        expected = {}
        if kind == "RuleImage":
            expected = {"type": "image", "front": list(literal["roi_front"]), "roi": list(literal["roi_back"]),
                        "threshold": literal["threshold"], "method": literal["method"], "roi_expand": 2}
            if spec.get("method", "Template matching") not in SUPPORTED_IMAGE_METHODS:
                raise _Missing(_issue("unsupported_image_method", source, "native matcher for " + alias))
            if not isinstance(spec.get("file"), str) or not (self.folder / spec["file"]).is_file():
                raise _Missing(_issue("missing_image", source, "converted image bytes for " + alias))
        elif kind == "RuleClick":
            x, y, w, h = literal["roi_front"]
            expected = {"type": "click", "rect": [x, y, x + w, y + h]}
        elif kind == "RuleOcr":
            expected = {"type": "ocr", "roi": list(literal["roi"]), "keyword": literal["keyword"],
                        "mode": literal["mode"]}
        elif kind == "RuleSwipe" and literal["mode"] == "default":
            def rect(box):
                x, y, w, h = box
                return [x, y, x + w, y + h]
            expected = {"type": "swipe", "from": rect(literal["roi_front"]), "to": rect(literal["roi_back"])}
        else:
            raise _Missing(_issue("unsupported_resource", source, "lower asset type " + kind))
        if any(spec.get(k) != value for k, value in expected.items()):
            raise _Missing(_issue("resource_drift", source, "regenerate resource from source " + alias,
                expected=expected, actual=spec))
        self.asset_data[alias] = {**copy.deepcopy(spec), "_literal": literal, "_source_ref": source}
        return alias, self.asset_data[alias]

    def image(self, name, threshold=None, namespace="Component_GeneralBattle"):
        alias, spec = self.asset(name, namespace)
        if spec["type"] != "image":
            raise _Missing(_issue("unsupported_resource", spec["_source_ref"], "image evidence for " + alias))
        return {"res": alias, **({"threshold": threshold} if threshold is not None else {})}

    def any_image(self, names):
        return {"any": [self.image(n) for n in names]}

    def cooldown(self, name, interval):
        variable = self.v("last_" + name.lower())
        self.raw["vars"].setdefault(variable, -1000000000)
        return f"elapsed_ms - {variable} > {interval}"

    def click_image(self, name, phase, interval, *, threshold=None, guard=None, context=None, next_phase=None,
                    namespace="Component_GeneralBattle", region_vars=None, interval_key=None, recheck_retry=False,
                    lines=(53, 80)):
        interval_key = interval_key or name
        expr = self.cooldown(interval_key, interval) if interval else "True"
        if guard:
            expr = f"({guard}) and ({expr})"
        actions = [{"click_found": True, "use_match_size": True, "delay": 0, "recheck": True}]
        if recheck_retry:
            actions[0]["recheck_retry"] = True
        if interval:
            actions.append({"set": {self.v("last_" + interval_key.lower()): "elapsed_ms"}})
        if next_phase:
            actions.append(self.goto(next_phase))
        condition = self.image(name, threshold, namespace)
        if region_vars:
            condition["region_vars"] = list(region_vars)
        if context:
            condition = {"all": [context, condition]}
        self.state(phase + "_click_" + name.lower(), phase, actions, condition=condition,
                   guard=expr, lines=lines)

    def random_click(self, marker, phase, choices, interval, *, threshold=None, recheck_retry=False, lines):
        rects = [self.asset(n)[1]["rect"] for n in choices]
        click = {"click_random": rects, "delay": 0, "recheck": True}
        if recheck_retry:
            click["recheck_retry"] = True
        self.state(phase + "_click_" + marker.lower(), phase,
            [click,
             {"set": {self.v("last_" + marker.lower()): "elapsed_ms"}}],
            condition=self.image(marker, threshold), guard=self.cooldown(marker, interval), lines=lines)

    def in_battle(self):
        return self.any_image(("I_BATTLE_INFO", "I_FRIENDS", "I_WIN", "I_FALSE", "I_REWARD"))

    def preparing(self):
        return self.any_image(("I_BUFF", "I_PREPARE_HIGHLIGHT", "I_PREPARE_DARK", "I_PRESET", "I_PRESET_WIT_NUMBER"))

    def result_screen(self):
        return {"any": [self.image("I_WIN", .8), self.image("I_DE_WIN"), self.image("I_FALSE", .8),
                        self.image("I_REWARD", .6), self.image("I_REWARD_GOLD", .8),
                        self.image("I_BATTLE_STATE_INFO")]}

    def build(self, strategy_wait=False):
        self.state("attempt", "entry", [{"inc": self.v("current_count")},
            self.assign(prep_started_ms="elapsed_ms", confed=False, prep_return=False,
                        outcome_known=False, win=False, returned=False, **{"return": False},
                        mark_attempted=0, preset_team_committed=0, result_marker=repr("")),
            self.goto("prepare")], lines=(35, 47))
        # Source Timer.reached uses strict >. Nested setup is not checked here.
        self.state("prepare_timeout", "prepare", [self.assign(prep_return=False), self.goto("green_gate")],
            guard="elapsed_ms - $prep_started_ms > 5000", lines=(53, 80))
        self.state("prepare_real_battle", "prepare", [self.assign(prep_return=True), self.goto("green_gate")],
            condition=self.image("I_BATTLE_INFO"), lines=(60, 62))
        for name in ("I_DISABLE_7DAYS_DIFF_SOUL", "I_CONFIRM_CLOSE_DIFF_SOUL"):
            self.click_image(name, "prepare", 600, lines=(63, 66))
        self.state("prepare_first_setup", "prepare", [self.goto("preset_open")], condition=self.preparing(),
            guard="not lock_team_enable and $current_count == 1 and not $confed", lines=(67, 72))
        self.click_image("I_PREPARE_HIGHLIGHT", "prepare", 800, guard="not lock_team_enable", lines=(67, 76))
        self.state("prepare_known_wait", "prepare", [{"wait": 0}], condition=self.preparing(), lines=(67, 76))
        # Source random.uniform(.4,.8) seconds; preserve continuous sampling.
        # Timeout is rechecked on the next outer iteration, not during this sleep.
        self.state("prepare_random_wait", "prepare", [{"wait_random": {
            "min_ms": 400, "max_ms": 800, "distribution": "uniform"}}], lines=(77, 79))
        self.presets()
        self.buff_setup()
        self.state("setup_complete", "setup_done", [self.assign(confed=True), self.goto("prepare_after_setup")], lines=(69, 74))
        # The source tries ready in the *same* outer iteration after nested
        # setup. Even when setup exceeded five seconds, that input precedes the
        # next timer check. Do not jump directly to prepare_timeout here.
        self.click_image("I_PREPARE_HIGHLIGHT", "prepare_after_setup", 800, next_phase="prepare", lines=(69, 75))
        self.state("prepare_after_setup_done", "prepare_after_setup", [self.goto("prepare")], lines=(69, 76))
        self.green()
        if strategy_wait:
            self.strategy_results()
        else:
            self.results()
        self.return_states()
        self.raw["resources"] = sorted(set(self.refs))
        return self.raw

    def presets(self):
        self.state("preset_disabled", "preset_open", [self.goto("buff_open")], guard="not preset_enable", lines=(407, 409))
        self.state("preset_opened", "preset_open", [self.goto("preset_group")],
            condition=self.any_image(("I_PRESET_ENSURE", "I_PRESENT_LESS_THAN_5")), lines=(413, 420))
        for name in ("I_PRESET", "I_PRESET_WIT_NUMBER"):
            self.click_image(name, "preset_open", 1000, threshold=0.8, lines=(421, 424))
        for name in ("O_PRESET", "O_PRESET_FULL"):
            alias, spec = self.asset(name)
            if (spec["_literal"]["mode"] != "Single" or not isinstance(spec["keyword"], str)
                    or not spec["keyword"]):
                raise _Missing(_issue("unsupported_resource", spec["_source_ref"],
                    "literal Single-OCR keyword for " + alias))
            condition = {"ocr_single": {"region": list(spec["roi"]), "equals": spec["keyword"], "score": .6}}
            x, y, width, height = spec["roi"]
            due = self.cooldown(name, 1000)
            self.state("preset_ocr_" + name.lower(), "preset_open", [
                {"click": [x, y, x + width, y + height], "delay": 0, "recheck": True},
                {"set": {self.v("last_" + name.lower()): "elapsed_ms"}}],
                condition=condition, guard=due, lines=(425, 430))
            # Source continues its outer loop after OCR success even when
            # click's interval suppresses input; do not try the next OCR arm.
            self.state("preset_ocr_" + name.lower() + "_cooldown", "preset_open", [{"wait": 0}],
                condition=condition, lines=(425, 430))
        self.state("preset_open_wait", "preset_open", [{"wait": 0}], lines=(411, 430))
        # Every supported config choice gets an actual mean-colour loop. The
        # upstream missing team 5 is a gated source defect, not a fallback to 1.
        for category, size, rgb, count, phase, lines in (
                ("GROUP", [25, 50], [224.9, 208.3, 187.4], 7, "preset_group", (452, 469)),
                ("TEAM", [5, 5], [216.8, 185.0, 146.8], 5, "preset_team", (473, 491))):
            for number in range(1, count + 1):
                name = f"C_PRESET_{category}_{number}"
                branch = f"preset_enable and preset_{category.lower()} == {number} on first unlocked attempt"
                try:
                    alias, spec = self.asset(name)
                    x, y, _, _ = spec["_literal"]["roi_back"]
                    if category == "GROUP":
                        _, first = self.asset("C_PRESET_GROUP_1")
                        size = list(first["_literal"]["roi_back"])[2:]
                except _Missing as error:
                    issue = {**error.obligation, "branch": branch, "call_site": _ref(BATTLE, lines=lines),
                             "requires_enabled_param": "preset_enable"}
                    self.obligations.append(issue)
                    self.blocked("preset_" + category.lower() + "_" + str(number), phase, issue,
                                 guard=f"preset_{category.lower()} == {number}")
                    continue
                mean = {"mean_color": {"region": [x, y, *size], "rgb": rgb, "tolerance": 10}}
                chosen = f"preset_{category.lower()} == {number}"
                label = "preset_" + category.lower() + "_" + str(number)
                done = ([{"wait": 500}, self.goto("preset_team")] if category == "GROUP" else
                        [self.goto("preset_team_commit")])
                self.state(label + "_selected", phase, done, condition={"not": mean}, guard=chosen, lines=lines)
                due = self.cooldown(name, 200)
                self.state(label, phase, [{"click": alias, "delay": 0, "recheck": True},
                    {"set": {self.v("last_" + name.lower()): "elapsed_ms"}}],
                    condition=mean, guard=f"{chosen} and ({due})", lines=lines)
                self.state(label + "_cooldown", phase, [{"wait": 0}], condition=mean, guard=chosen, lines=lines)
                if category == "TEAM":
                    self.state(label + "_commit", "preset_team_commit", [
                        {"click": alias, "attempt_var": self.v("preset_team_committed"), "delay": 0, "recheck": True},
                        self.assign(preset_ensure_started_ms="elapsed_ms"), self.goto("preset_ensure_wait")],
                        condition=self.any_image(("I_PRESET_ENSURE", "I_PRESENT_LESS_THAN_5")), guard=chosen, lines=(491, 495))
        missing = self.obligation("positive_evidence_required", (491, 491),
            "fresh preset UI evidence before the source unconditional team click",
            branch="team colour loop exited but no preset ensure/less-than-five marker remains",
            requires_enabled_param="preset_enable")
        self.blocked("preset_commit_positive_evidence_blocked", "preset_team_commit", missing)
        # wait_until_appear checks its timeout before recognizing the target.
        for label, condition, guard in (
                ("timeout", None, "elapsed_ms - $preset_ensure_started_ms > 1000"),
                ("appeared", self.image("I_PRESET_ENSURE"), None)):
            self.state("preset_ensure_wait_" + label, "preset_ensure_wait", [
                self.assign(preset_warn_started_ms="elapsed_ms"), self.goto("preset_ensure_check")],
                condition=condition, guard=guard, lines=(494, 496))
        self.state("preset_ensure_wait", "preset_ensure_wait", [{"wait": 0}], lines=(494, 496))
        # Timer(10) only logs, on every subsequent source loop. It never exits
        # the dialog or marks the selection as successful/failed by itself.
        self.state("preset_ensure_warn", "preset_ensure_check", [
            {"log": "Switch preset failure"}, self.goto("preset_ensure_scan")],
            guard="elapsed_ms - $preset_warn_started_ms > 10000", lines=(496, 500))
        self.state("preset_ensure_check", "preset_ensure_check", [self.goto("preset_ensure_scan")], lines=(496, 500))
        self.state("preset_ensure_gone", "preset_ensure_scan", [self.goto("buff_open")],
                   condition={"not": self.image("I_PRESET_ENSURE")}, lines=(501, 502))
        self.click_image("I_PRESET_ENSURE", "preset_ensure_scan", 1000, threshold=.8,
                         next_phase="preset_ensure_check", lines=(503, 504))
        self.state("preset_ensure_cooldown", "preset_ensure_scan", [self.goto("preset_ensure_check")], lines=(497, 504))

    def buff_setup(self):
        if not self.buffs:
            self.state("buff_none", "buff_open", [self.goto("setup_done")], lines=(612, 613))
            return
        self.state("buff_opened", "buff_open", [self.goto("buff_0")],
                   condition=self.image("I_CLOUD", namespace="Component_GeneralBuff"), lines=(615, 617))
        self.click_image("I_BUFF", "buff_open", 2000, lines=(615, 617))
        for index, value in enumerate(self.buffs):
            phase = "buff_" + str(index)
            method = value.removesuffix("_CLOSE").lower()
            image_based = method in ("awake", "soul")
            is_open = not value.endswith("_CLOSE")
            lines = BUFF_OPERATIONS[method]
            contract = {"method": method, "is_open": is_open, "order": index,
                    "area": "matched front_center.x+364, front.y, 80, front.h" if image_based else
                            "OCR bbox.x+bbox.w+10, bbox.y-10, 80, bbox.h+20; sentinel (432,143,325,21) means absent",
                    "missing_area": "retry" if method.startswith("exp") else "return None; caller continues",
                    "switch_interval_ms": 1000, "switch_timeout_ms": 10000, "after_helper_wait_ms": 100,
                     "native_continuation_phase": phase + "_returned",
                    "exp_missing_both_switches": "swipe (580,320)->(530,240); wait 1000ms; retry" if method.startswith("exp") else None,
                     "reject_invite": "I_I_REJECT_3,2,1 priority; interval 6000ms keyed by source image filename (shared for identical names)"}
            self.buff_contracts.append({"source": _ref(BUFF, lines=lines), "branch": f"buff[{index}] == {value}",
                "contract": contract, "native_entry_phase": phase,
                "dependencies": [_ref(BUFF, lines=(52, 82)), _ref(BUFF, lines=(180, 200)),
                                 _ref(BUFF, lines=(242, 256)), _ref(BATTLE, lines=(618, 643))]})
            self.buff_helper(phase, method, is_open, lines, contract)
            self.state(phase + "_returned", phase + "_returned",
                [{"wait": 100}, self.goto("buff_" + str(index + 1) if index + 1 < len(self.buffs) else "buff_close")],
                lines=(632, 635))
        cloud = self.image("I_CLOUD", namespace="Component_GeneralBuff")
        self.state("buff_closed", "buff_close", [self.goto("buff_prepare")],
                   condition={"not": cloud}, lines=(637, 640))
        self.click_image("I_BUFF", "buff_close", 1000, context=cloud, lines=(637, 642))
        self.state("buff_close_wait", "buff_close", [{"wait": 0}], lines=(637, 642))
        self.state("buff_prepare_gone", "buff_prepare", [self.goto("setup_done")],
                   condition={"not": self.image("I_PREPARE_HIGHLIGHT")}, lines=(643, 643))
        self.click_image("I_PREPARE_HIGHLIGHT", "buff_prepare", 800, lines=(643, 643))
        self.state("buff_prepare_wait", "buff_prepare", [{"wait": 0}], lines=(643, 643))

    def buff_helper(self, phase, method, is_open, lines, contract):
        buff_ns, invite_ns = "Component_GeneralBuff", "Component_GeneralInvite"
        returned = phase + "_returned"
        roi_vars = [self.v(phase + "_" + axis) for axis in ("x", "y", "w", "h")]
        for name in roi_vars:
            self.raw["vars"][name] = 0
        started, status = phase + "_started_ms", phase + "_status"
        self.raw["vars"][self.v(started)], self.raw["vars"][self.v(status)] = 0, "unobserved"

        # A visible higher-priority invite suppresses lower arms even if its
        # own click is cooling down, as the source's unconditional continue does.
        rejects = ["I_I_REJECT_" + str(i) for i in (3, 2, 1)]
        for name in rejects:
            _, spec = self.asset(name, invite_ns)
            identity = "source_" + re.sub(r"[^A-Za-z_0-9]", "_", Path(spec["_literal"]["file"]).stem).lower()
            self.click_image(name, phase, 6000, namespace=invite_ns, interval_key=identity, lines=(242, 256))
            self.state(phase + "_cooling_" + name.lower(), phase, [{"wait": 0}],
                       condition=self.image(name, namespace=invite_ns), lines=(242, 256))
        self.state(phase + "_invites_clear", phase, [self.goto(phase + "_locate")], lines=(242, 256))

        locate = phase + "_locate"
        if method in ("awake", "soul"):
            anchor = self.image("I_" + method.upper(), namespace=buff_ns)
            projection = ["match_x + match_w // 2 + 364", "match_y", 80, "match_h"]
        else:
            _, asset = self.asset("O_" + method.upper(), buff_ns)
            if asset["mode"] != "Full":
                raise _Missing(_issue("unsupported_resource", asset["_source_ref"], "Full OCR buff anchor"))
            anchor = {"ocr_full": {"region": asset["roi"], "keyword": asset["keyword"], "score": .6}}
            sentinel = copy.deepcopy(anchor)
            sentinel["ocr_full"]["box_equals"] = [432, 143, 325, 21]
            self.state(phase + "_area_sentinel", locate,
                [self.assign(**{status: repr("missing")}), self.goto(phase if method.startswith("exp") else returned)],
                condition=sentinel, lines=lines)
            partial = copy.deepcopy(anchor)
            partial["ocr_full"]["evidence"] = "partial_keyword"
            issue = self.obligation("unsafe_source_keyword", (244, 261),
                "source partial-character OCR fallback is not evidence of the requested buff; retain a complete keyword before a switch",
                branch=next(b["branch"] for b in self.buff_contracts if b["native_entry_phase"] == phase),
                path="module/ocr/base_ocr.py", contract=copy.deepcopy(contract),
                call_site=_ref(BUFF, lines=lines))
            self.blocked(phase + "_partial_keyword_blocked", locate, issue, condition=partial)
            anchor["ocr_full"]["evidence"] = "complete_keyword"
            projection = ["match_x + match_w + 10", "match_y - 10", 80, "match_h + 20"]
        following = phase + ("_probe" if method.startswith("exp") else "_switch_start")
        self.state(phase + "_capture", locate,
            [{"capture_region": {"vars": roi_vars, "rect": projection}}, self.goto(following)],
            condition=anchor, lines=lines)
        if method in ("awake", "soul"):
            self.state(phase + "_area_missing", locate,
                [{"log": "No " + method + " buff"}, self.assign(**{status: repr("missing")}), self.goto(returned)], lines=lines)
        else:
            issue = self.obligation("unsafe_source_roi", (61, 72),
                "resolve source Full zero-box mismatch: computed (10,-10,80,20) has no safe visual anchor",
                branch=next(b["branch"] for b in self.buff_contracts if b["native_entry_phase"] == phase), path=BUFF,
                contract=copy.deepcopy(contract), dependencies=[_ref("module/ocr/sub_ocr.py", lines=(26, 45))])
            self.blocked(phase + "_zero_area_blocked", locate, issue)

        def switch(name):
            return {**self.image(name, namespace=buff_ns), "region_vars": list(roi_vars)}

        cloud = self.image("I_CLOUD", namespace=buff_ns)
        yellow, red = switch("I_OPEN_YELLOW"), switch("I_CLOSE_RED")
        if method.startswith("exp"):
            probe = phase + "_probe"
            self.state(phase + "_switch_visible", probe, [self.goto(phase + "_switch_start")],
                       condition={"any": [yellow, red]}, lines=lines)
            self.state(phase + "_scroll", probe,
                [{"swipe": {"from": [580, 320, 580, 320], "to": [530, 240, 530, 240]},
                  "delay": 0, "recheck": True}, {"wait": 1000}, self.goto(phase)],
                condition={"all": [cloud, {"not": yellow}, {"not": red}]}, lines=lines)
            self.state(phase + "_probe_wait", probe, [{"wait": 0}], lines=lines)
        self.state(phase + "_switch_start", phase + "_switch_start",
                   [self.assign(**{started: "elapsed_ms"}), self.goto(phase + "_switch")], lines=lines)
        desired = yellow if is_open else red
        self.state(phase + "_switch_done", phase + "_switch",
                   [self.assign(**{status: repr("observed")}), self.goto(returned)], condition=desired, lines=lines)
        self.state(phase + "_switch_timeout", phase + "_switch",
                   [{"log": ("Open " if is_open else "Close ") + method + " buff failed"},
                    self.assign(**{status: repr("timeout")}), self.goto(returned)],
                   guard=f"elapsed_ms - ${started} > 10000", lines=lines)
        self.click_image("I_CLOSE_RED" if is_open else "I_OPEN_YELLOW", phase + "_switch", 1000,
            namespace=buff_ns, region_vars=roi_vars, context={"all": [cloud, {"not": desired}]}, lines=lines)
        self.state(phase + "_switch_wait", phase + "_switch", [{"wait": 0}], lines=lines)
        # This helper's states originate in GeneralBuff, not the caller's file.
        for st in self.raw["states"]:
            if st["id"].startswith(self.v(phase + "_")) and st["source"]["path"] == BATTLE:
                st["source"]["path"] = BUFF

    def green(self):
        result = self.result_screen()
        active = {"all": [self.image("I_BATTLE_INFO"), {"not": self.preparing()}, {"not": result}]}
        self.state("green_disabled", "green_gate", [self.goto("battle_wait")], guard="not green_enable", lines=(44, 47))
        for phase in ("green_gate", "green_wait_prepare", "green_local", "green_coordinate"):
            self.state(phase + "_result_visible", phase, [self.goto("battle_wait")],
                       condition=result, lines=(44, 47))
        self.state("green_enter", "green_gate", [self.goto("green_wait_prepare")], condition=self.in_battle(), lines=(44, 45))
        self.state("green_not_in_battle", "green_gate", [self.goto("battle_wait")], lines=(44, 47))
        self.state("green_prepare_visible", "green_wait_prepare", [{"wait": 0}],
                   condition=self.preparing(), lines=(368, 371))
        self.state("green_prepare_gone", "green_wait_prepare", [self.goto("green_local")], lines=(368, 371))
        self.click_image("I_LOCAL", "green_local", 0, context=active, next_phase="green_local_pause",
                         recheck_retry=True, lines=(372, 373))
        self.state("green_local_absent", "green_local", [self.goto("green_coordinate")], lines=(372, 374))
        self.state("green_local_pause", "green_local_pause", [{"wait": 300}, self.goto("green_coordinate")], lines=(372, 374))
        self.state("green_done", "green_coordinate", [self.goto("battle_wait")], guard="$mark_attempted > 0", lines=(374, 374))
        choices = self.src.enum(CONFIG, "GreenMarkType")
        for enum, value in choices.items():
            name = "C_GREEN_" + ("MAIN" if enum == "GREEN_MAIN" else "LEFT_" + enum[-1])
            alias, _ = self.asset(name)
            self.state("mark_" + value, "green_coordinate",
                [{"click": alias, "attempt_var": self.v("mark_attempted"), "delay": 0, "recheck": True}],
                condition=active,
                guard=f"green_mark == {value!r}", lines=(347, 374))
        issue = self.obligation("positive_evidence_required", (368, 374),
            "fresh positive battle evidence for the coordinate mark; source only checks preparation absence",
            branch="green_enable and no battle marker remains at the coordinate input",
            requires_enabled_param="green_enable")
        self.blocked("green_positive_evidence_blocked", "green_coordinate", issue)

    def observation(self, name, marker, condition, win, phase, *, lines=(175, 200)):
        self.state(name, "battle_wait", [self.assign(win=win, outcome_known=True, result_marker=repr(marker)),
            {"receipt": {"kind": "battle_result", "outcome": "win" if win else "loss",
                         "source_marker": "Component_GeneralBattle::" + marker, "scope": "single_battle"}},
            self.goto(phase)], condition=condition, lines=lines)

    def random_idle(self):
        """Finite native port of random_click_swipt, never a callback runner.

        The source draws the action kind only for trigger values 0..3, and
        cooldown suppression returns immediately (no 400ms else-branch sleep).
        Device inputs additionally require fresh real-battle evidence, as all
        family inputs do; unknown screens are explicit evidence obligations.
        """
        self.state("idle_sample_trigger", "battle_wait", [
            {"sample_int": {"var": self.v("idle_trigger"), "min": 0, "max": 500}},
            self.goto("battle_idle_decide")], guard="random_click_swipt_enable", lines=(202, 203))
        for phase in ("battle_idle_decide", "battle_idle_input"):
            self.state(phase + "_disabled", phase, [self.goto("battle_wait")],
                       guard="not random_click_swipt_enable", lines=(202, 203))
        self.state("idle_not_triggered", "battle_idle_decide", [{"wait": 400}, self.goto("battle_wait")],
                   guard="$idle_trigger > 3", lines=(509, 521))
        self.state("idle_sample_kind", "battle_idle_decide", [
            {"sample_int": {"var": self.v("idle_kind"), "min": 0, "max": 2}},
            self.goto("battle_idle_input")], guard="0 <= $idle_trigger and $idle_trigger <= 3", lines=(509, 510))
        results = self.result_screen()
        # Sampling and native inputs occupy separate fresh-frame ticks. If a
        # result arrives in between, return to the existing result-priority
        # states instead of sending the pending idle click/swipe over it.
        self.state("idle_result_preempts_input", "battle_idle_input", [self.goto("battle_wait")],
                   condition=results, lines=(175, 203))
        positive = self.image("I_BATTLE_INFO")
        for kind, name, action, lines in (
                (0, "C_RANDOM_CLICK", "click", (511, 513)),
                (1, "S_BATTLE_RANDOM_LEFT", "swipe", (514, 515)),
                (2, "S_BATTLE_RANDOM_RIGHT", "swipe", (516, 517))):
            alias, _ = self.asset(name)
            due = self.cooldown(name, 20000)
            selected = f"$idle_kind == {kind}"
            self.state("idle_" + name.lower() + "_cooldown", "battle_idle_input", [self.goto("battle_wait")],
                       guard=f"{selected} and not ({due})", lines=lines)
            self.state("idle_" + name.lower(), "battle_idle_input", [
                {action: alias, "delay": 0, "recheck": True},
                {"set": {self.v("last_" + name.lower()): "elapsed_ms"}}, self.goto("battle_wait")],
                condition={"all": [positive, {"not": self.preparing()}, {"not": results}]},
                guard=f"{selected} and ({due})", lines=lines)
        missing = self.obligation("positive_evidence_required", (508, 517),
            "fresh real-battle evidence for the sampled idle input; source does not guard its coordinates",
            branch="idle trigger in 0..3, selected target cooldown elapsed, no result and no I_BATTLE_INFO",
            requires_enabled_param="random_click_swipt_enable")
        self.blocked("idle_positive_evidence_blocked", "battle_idle_input", missing)

    def results(self):
        # DE_WIN must be dismissed even when WIN is visible in the same frame.
        self.observation("observe_de_win", "I_DE_WIN", self.image("I_DE_WIN"), True, "de_win")
        self.observation("observe_win", "I_WIN", self.image("I_WIN", 0.8), True, "result_win")
        self.observation("observe_loss", "I_FALSE", self.image("I_FALSE", 0.8), False, "result_loss")
        self.observation("observe_reward", "I_REWARD", self.image("I_REWARD", 0.6), True, "result_win")
        self.observation("observe_gold", "I_REWARD_GOLD", self.image("I_REWARD_GOLD", 0.8), True, "result_win")
        self.random_idle()
        self.state("battle_wait", "battle_wait", [{"wait": 0}], lines=(175, 203))
        self.click_image("I_DE_WIN", "de_win", 1000, lines=(181, 184))
        self.state("de_win_gone", "de_win", [self.goto("result_win")],
                   condition={"not": self.image("I_DE_WIN")}, lines=(181, 184))
        self.state("de_win_cooldown", "de_win", [{"wait": 0}], lines=(181, 184))
        self.random_click("I_WIN", "result_win", ["C_WIN_1", "C_WIN_2", "C_WIN_3"], 500,
                          recheck_retry=True, lines=(207, 215))
        self.state("win_gone", "result_win", [self.assign(reward_started_ms="elapsed_ms"), self.goto("reward_wait")],
                   condition={"not": self.image("I_WIN")}, lines=(214, 224))
        self.state("win_cooldown", "result_win", [{"wait": 0}], lines=(211, 215))
        self.click_image("I_FALSE", "result_loss", 0, threshold=0.6, recheck_retry=True, lines=(216, 221))
        self.state("loss_gone", "result_loss", [self.goto("return_false")],
                   condition={"not": self.image("I_FALSE", 0.6)}, lines=(216, 221))
        # wait_until_appear checks its timer *before* its match. Gold alone does
        # not satisfy this wait. Statistics is inspected only after timeout.
        self.state("reward_wait_timeout", "reward_wait", [self.goto("reward_timeout")],
                   guard="elapsed_ms - $reward_started_ms > 10000", lines=(223, 227))
        self.state("reward_appeared", "reward_wait", [self.goto("reward_collect")],
                   condition=self.image("I_REWARD"), lines=(223, 229))
        self.state("reward_wait", "reward_wait", [{"wait": 0}], lines=(223, 227))
        self.state("reward_statistics", "reward_timeout", [self.goto("reward_collect")],
                   condition=self.image("I_STATISTICS"), lines=(223, 229))
        self.state("no_reward", "reward_timeout", [self.goto("return_true")], lines=(223, 227))
        self.click_image("I_OVER_GHOST", "reward_collect", 0, lines=(232, 234))
        for marker in ("I_REWARD", "I_REWARD_GOLD"):
            self.random_click(marker, "reward_collect", ["C_REWARD_1", "C_REWARD_2", "C_REWARD_3"], 1500,
                              recheck_retry=True, lines=(236, 247))
        self.state("reward_gone", "reward_collect", [self.goto("return_true")],
            condition={"all": [{"not": self.image("I_REWARD")}, {"not": self.image("I_REWARD_GOLD")}]}, lines=(248, 261))
        self.state("reward_cooldown", "reward_collect", [{"wait": 0}], lines=(248, 261))

    def strategy_results(self):
        """Lower the default BattleWait hooks used by the pinned zone overrides."""
        first = len(self.raw["states"])
        reward_names = ("I_GREED_GHOST", "I_REWARD", "I_REWARD_GOLD", "I_REWARD_GOLD_SNAKE_SKIN")
        rewards = self.any_image(reward_names)
        details = self.any_image(("I_END_FIX_1", "I_END_FIX_2"))
        overflow = self.image("I_OVER_GHOST")
        win_title = self.image("I_WIN")
        loss = self.image("I_FALSE", .8)

        self.click_image("I_OVER_GHOST", "battle_wait", 600, recheck_retry=True, lines=(1165, 1171))
        self.click_image("I_PREPARE_HIGHLIGHT", "battle_wait", 1000, recheck_retry=True,
                         context={"not": {"any": [self.image("I_BATTLE_INFO"), win_title, loss, rewards, overflow]}},
                         lines=(1247, 1290))
        self.click_image("I_WIN", "battle_wait", 800, recheck_retry=True, lines=(1185, 1188))
        for marker in reward_names:
            self.observation("observe_" + marker[2:].lower(), marker, self.image(marker), True,
                             "reward_collect", lines=(1189, 1201))
        self.observation("observe_loss", "I_FALSE", loss, False, "result_loss", lines=(1233, 1242))
        self.state("battle_wait", "battle_wait", [{"wait": 0}], lines=(1244, 1245))

        self.click_image("I_FALSE", "result_loss", 0, recheck_retry=True, lines=(1233, 1242))
        self.state("loss_gone", "result_loss", [self.goto("return_false")],
                   condition={"not": self.image("I_FALSE")}, lines=(1233, 1242))
        self.click_image("I_OVER_GHOST", "reward_collect", 600, recheck_retry=True, lines=(1205, 1207))
        # C_REWARD_2 is the source's details dismissal and is outside all
        # OptionSuccessDefault stage-two exclusions in the pinned layout.
        target = self.asset("C_REWARD_2")[1]["rect"]
        for name, matches in (("details", details), ("settlement", {"all": [rewards, {"not": details}]})):
            interval = self.cooldown("strategy_reward", 1500)
            self.state("reward_" + name, "reward_collect", [
                {"click": target, "delay": 0, "recheck": True, "recheck_retry": True},
                self.assign(last_strategy_reward="elapsed_ms"),
            ], condition={"all": [matches, {"not": overflow}]}, guard=interval, lines=(1209, 1228))
        self.state("reward_gone", "reward_collect", [self.goto("return_true")],
                   condition={"not": {"any": [rewards, details, overflow, win_title, loss]}}, lines=(1223, 1231))
        self.state("reward_cooldown", "reward_collect", [{"wait": 0}], lines=(1201, 1231))
        for step in self.raw["states"][first:]:
            step["source"]["path"] = BATTLE_WAIT

        self.obligation("untranslated_strategy", (218, 226),
                        "Bind the configured BattleWait randomclick hook",
                        path=BATTLE_WAIT, branch="random_click_swipt_enable",
                        requires_enabled_param="random_click_swipt_enable")

    def return_states(self):
        for win in (True, False):
            self.state("returned_" + str(win).lower(), "return_" + str(win).lower(),
                [self.assign(returned=True, **{"return": win}), {"stop": {
                    "reason": "GeneralBattle source returned " + str(win), "result": "unknown", "verified": False,
                    "evidence": {"scope": "single_battle", "source_return": win, "original_task_complete": False}}}],
                guard=f"$outcome_known and $win == {win}", lines=(47, 51))


def bind_courtyard_buffs(raw, source_root, resource_dir, *, prefix, phase_var, entry_phase,
                        resume, operations, enable_param, opening, skip_in_battle=False):
    """Bind GeneralBuff.open_buff/close_buff and its caller's ordered switches."""
    sources = _Sources(source_root)
    sources.verify()
    builder = _Builder(sources, resource_dir, prefix, 0, [])
    image, state, goto = builder.image, builder.state, builder.goto
    namespace = "Component_GeneralBuff"
    cloud = image("I_CLOUD", namespace=namespace)
    awake = image("I_AWAKE", namespace=namespace)
    court = raw["navigation"]["pages"]["page_main"]["when"]
    active = {"expr": f"{phase_var} == {entry_phase!r}"}
    done = {"set": {phase_var: repr(resume)}}
    raw["states"].append({"id": prefix + "_skip", "when": {"all": [active, {"expr": f"not {enable_param}"}]},
                          "do": [done]})
    if skip_in_battle:
        raw["states"].append({"id": prefix + "_skip_in_battle", "when": {
            "all": [active, builder.in_battle()]}, "do": [done]})
    builder.raw["vars"] = {builder.v("phase"): "entry", builder.v("started_ms"): -1, builder.v("arrived"): 0}
    state("start", "entry", [builder.assign(started_ms="elapsed_ms"), goto("open")], lines=(18, 40))
    state("panel_open", "open", [goto("align")], condition=cloud, lines=(25, 32))
    builder.click_image("I_BUFF_1", "open", 2000, namespace=namespace, context=court, lines=(25, 32))
    state("navigate_to_court", "open", [{"navigate": {"destination": "page_main", "done_var": builder.v("arrived")}}],
          condition={"not": court}, lines=(24, 33))
    state("panel_aligned", "align", [goto("select_0")], condition={"all": [cloud, awake]}, lines=(34, 40))
    _, swipe = builder.asset("S_BUFF_UP", namespace)
    condition = {"all": [cloud, {"not": awake}]}
    cooldown = builder.cooldown("align", 2000)
    state("scroll_to_first_buff", "align", [
        {"swipe": {"from": swipe["from"], "to": swipe["to"]}, "delay": 0, "recheck": True},
        builder.assign(last_align="elapsed_ms")], condition=condition, guard=cooldown, lines=(34, 40))
    for index, (method, param) in enumerate(operations):
        phase = f"select_{index}"
        following = f"select_{index + 1}" if index + 1 < len(operations) else "close"
        guard = param if param else "True"
        state(phase + "_dispatch", phase, [goto(phase + "_helper")], guard=guard)
        if param:
            state(phase + "_skip", phase, [goto(following)], guard=f"not {param}")
        helper = phase + "_helper"
        lines = BUFF_OPERATIONS[method]
        operation = {"method": method, "is_open": opening, "parameter": param}
        builder.buff_contracts.append({"branch": method, "native_entry_phase": helper, "contract": operation})
        builder.buff_helper(helper, method, opening, lines, operation)
        state(phase + "_continue", helper + "_returned", [goto(following)], lines=lines)
    state("panel_closed", "close", [done], condition={"all": [court, {"not": cloud}]}, lines=(42, 52))
    builder.click_image("I_BUFF_1", "close", 2000, namespace=namespace, context=cloud, lines=(42, 52))
    raw["states"].append({"id": prefix + "_timeout",
        "when": {"all": [active, {"expr": f"{builder.v('started_ms')} >= 0 and "
                                          f"elapsed_ms - {builder.v('started_ms')} >= 60000"}]},
        "do": [{"fail": "庭院加成面板未完成切换和关闭"}]})
    for step in builder.raw["states"]:
        phase = step["when"]["all"][0]["expr"]
        conditions = [active]
        if phase.startswith(f"{builder.v('phase')} == 'select_"):
            conditions.append(cloud)
        step["when"] = {"all": [*conditions, *step["when"]["all"]]}
        if step["source"]["path"] == BATTLE:
            step["source"]["path"] = BUFF
        raw["states"].append(step)
    raw["vars"].update(builder.raw["vars"])
    raw["resources"] = sorted(set(raw["resources"] + builder.refs))
    return {"source_files": sorted(sources.files.values(), key=lambda item: item["path"]),
            "entry": entry_phase, "resume": resume, "helpers": builder.buff_contracts,
            "source_obligations": builder.obligations}


def compile_general_battle(source_root, resource_dir, *, prefix="gb", current_count=0, buff=None, owner=None,
                           strategy_wait=False):
    """Build a guarded native family invocation, preserving the full config domain.

    ``current_count`` is the source count *before* this call. Binding a count or
    buff literal narrows the invocation, never the editable config domain.
    ``strategy_wait`` selects the default BattleWait hooks for callers with a
    separately fingerprinted default-strategy override. No
    candidate is approved, written, or run here. Source/resource faults return a
    valid, input-free failure workflow and typed obligations, not an exception or
    a successful empty template. Invalid API arguments do raise ValueError.
    """
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", prefix):
        raise ValueError("prefix must be a native identifier")
    if type(current_count) is not int or current_count < 0:
        raise ValueError("current_count must be a nonnegative integer")
    sources = _Sources(source_root)
    builder = None
    try:
        sources.verify()
        sources.check_owner(owner)
        enums = sources.enum(BUFF_CONFIG, "BuffClass")
        inverse = {v: k for k, v in enums.items()}
        values = [] if buff is None else list(buff) if isinstance(buff, (list, tuple)) else [buff]
        buffs = []
        for value in values:
            if type(value) is int and value in inverse:
                value = inverse[value]
            if not isinstance(value, str) or value not in enums:
                raise ValueError("buff must contain literal BuffClass names or integer enum values")
            buffs.append(value)
        builder = _Builder(sources, resource_dir, prefix, current_count, buffs)
        workflow = builder.build(strategy_wait=strategy_wait)
        obligations = builder.obligations
    except _Missing as error:
        obligations = (builder.obligations if builder else []) + [error.obligation]
        workflow = {"format": 1, "name": prefix + "_general_battle_blocked", "vars": {}, "params": {},
            "states": [{"id": prefix + "_dependency_blocked", "when": {"expr": "True"},
                        "do": [{"fail": error.obligation["requirement"]}], "source_obligation": error.obligation["id"]}]}
    contract = {"version": 1, "coverage": "GeneralBattle.run_general_battle family fragment",
        "original_task_complete": False, "source_entry": _ref(BATTLE, lines=(29, 51)),
        "config_domain": "all runtime choices, including enabled presets/random/green and team 5",
        "dispatch": ("pinned BattleWait default strategy hooks" if strategy_wait else
                     "pinned GeneralBattle.battle_wait; task overrides require separate translation"),
        "bindings": {"current_count_before": current_count, "buff": list(buff) if isinstance(buff, tuple) else buff,
                     "owner": list(owner) if owner else None},
        "outputs": {k: prefix + "_" + k for k in ("current_count", "returned", "return", "win", "outcome_known", "result_marker")},
        "composition": {"phase_var": prefix + "_phase", "entry_phase": "entry",
            "return_states": [prefix + "_returned_true", prefix + "_returned_false"],
            "join": "replace the terminal stop with the caller's native continuation; preserve result/receipt guards",
            "interval_vars": sorted(k for k in workflow.get("vars", {}) if k.startswith(prefix + "_last_")),
            "clock_domain": "parent elapsed_ms; retain per-target interval clocks across calls in the same task instance"},
        "caller_requirements": ["bind actual helper dispatch and preceding current_count", "retain workflow approvals and resource budgets",
            "retain shared interval variables and parent elapsed_ms clock domain; a fresh standalone Runner is not a task-loop continuation",
            "compose the source boolean return; an attempt, timeout, helper return or receipt is not task completion"],
        "buff_helpers": copy.deepcopy(builder.buff_contracts) if builder else [],
        "source_behavior": {"attempt_count_before_preparation": True, "preparation_timeout_ms": 5000,
            "preparation_unknown_wait_ms": [400, 800],
            "preparation_unknown_wait_distribution": "continuous uniform",
            "preset": {"group_color_rgb": [224.9, 208.3, 187.4], "team_color_rgb": [216.8, 185.0, 146.8],
                "single_ocr": {"equality": "whole-line exact, identity normalization", "score": .6,
                    "horizontal_threshold": ">=", "vertical_threshold": ">", "click": "resource ROI",
                    "order": ["O_PRESET", "O_PRESET_FULL"], "interval_ms": 1000},
                "tolerance": 10, "selection_interval_ms": 200, "before_team_wait_ms": 500,
                "team_click_after_color_loop": True, "ensure_wait_ms": 1000,
                "ensure_click_interval_ms": 1000, "ten_second_timer": "warning every loop, never an exit",
                "less_than_five_marker": "ends the opening loop, then still runs group/team selection; never a skip or success signal"},
            "random_idle": {"trigger_range_inclusive": [0, 500], "trigger_values": [0, 1, 2, 3],
                "kind_range_inclusive": [0, 2], "per_target_interval_ms": 20000, "otherwise_wait_ms": 400,
                "cooldown_suppression": "return immediately without the non-trigger sleep"},
            "preparation_return_ignored": True, "nested_setup_can_exceed_preparation_timeout": True,
            "green_mark_type_and_name": "config values not forwarded by run_general_battle; coordinate helper defaults apply",
            "unused_helpers": ["battle_wait_v2", "run_general_battle_back", "exit_battle", "check_lock", "boss_mark"],
            "special_reward_hook": "pinned base returns False; overriding it is blocked"},
        "native_adaptations": ["fresh positive visual evidence before every input; one input per state",
            "Single-OCR uses native RapidOCR models with source confidence, ordering and padding rules; pixel recognition may differ from upstream ppocr",
            "Full-OCR uses native RapidOCR with source score/filter/merge rules, including partial-character fallback and the source's non-union merge",
            "BUFF switch/scroll inputs additionally require the cloud panel; zero or invalid OCR-derived regions stop instead of permitting unanchored inputs",
            "BUFF Full-OCR partial-character fallbacks remain observable but block input unless the complete keyword was recognized; a one-pixel mismatch of the source missing-area sentinel cannot select another buff",
            "source unconditional team click is strengthened with fresh I_PRESET_ENSURE or I_PRESENT_LESS_THAN_5 evidence",
            "native screenshot scheduling, humanization and bounded cancellation/watchdogs replace source device instrumentation",
            "original source long-battle/click-record infrastructure is not a task completion signal"],
        "source_files": sorted(sources.files.values(), key=lambda v: v["path"]), "source_obligations": copy.deepcopy(obligations)}
    workflow["oas_battle_contract"] = contract
    if strategy_wait:
        contract["source_behavior"].pop("random_idle")
        contract["source_behavior"]["strategy_wait"] = {
            "source": _ref(BATTLE_WAIT, lines=(1633, 1683)),
            "completion": "after observed reward dismissal or loss dismissal",
            "prepare_fallback": "continue servicing a visible ready button after battle_before expires",
        }
        contract["native_adaptations"].append(
            "Require reward evidence before returning victory and use a fixed safe subset of the source reward dismissal area."
        )
    return {"workflow": workflow, "complete": not obligations, "original_task_complete": False,
            "guarded_executable": builder is not None and len(workflow["states"]) > 1,
            "coverage": "guarded-family-fragment", "unsupported": copy.deepcopy(obligations),
            "source_obligations": copy.deepcopy(obligations), "source_files": contract["source_files"]}
