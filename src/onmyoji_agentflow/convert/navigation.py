"""Parse the complete OAS page registry as inert data, never import its modules.

Composite matchers, module aliases, hooks, keyword actions and inherited tab
edges are part of navigation.  Anything not understood remains an explicit
diagnostic; a partial regex graph must not masquerade as the full registry.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import re
from pathlib import Path

from .astpins import source_node_hash

_INHERIT_IMPLEMENTATION = "39910ee94423d61bae6906645ea840388dc5b3490e4cdce7ed2d49a0daa3204e"


def read_navigation(tasks: Path, classes: dict[str, str]) -> dict:
    primary = tasks / "GameUi/default_pages.py"
    if not primary.is_file():
        primary = tasks / "GameUi/page.py"
    if not primary.is_file():
        raise FileNotFoundError(primary)
    files = [primary] + sorted(path for path in tasks.glob("*/page.py") if path.parent.name != "GameUi")
    runtime = tasks / "GameUi/navigator.py"
    if runtime.is_file():
        files.append(runtime)
    graph = {"format": 2, "source": "OnmyojiAutoScript tasks/*/page.py", "license": "GPL-3.0",
             "pages": {}, "links": [], "functions": {}, "source_files": [], "diagnostics": []}

    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        rel = path.relative_to(tasks).as_posix()
        tree = ast.parse(text, filename=rel)
        graph["source_files"].append({"path": "tasks/" + rel,
            "sha256": hashlib.sha256(text.encode()).hexdigest()})
        aliases = {}
        inheritance_audited = False
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    aliases[alias.asname or alias.name] = alias.name
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "inherit_transitions":
                    inheritance_audited = source_node_hash(node, style="legacy-311") == _INHERIT_IMPLEMENTATION
                graph["functions"][rel + ":" + node.name] = {
                    "file": "tasks/" + rel, "line": node.lineno,
                    "source": ast.get_source_segment(text, node)}

        def diagnostic(node, why):
            result = {"file": "tasks/" + rel, "line": node.lineno,
                      "reason": why, "expression": ast.unparse(node)}
            graph["diagnostics"].append(result)
            return {"unsupported": result}

        def name(node):
            return aliases.get(node.id, node.id) if isinstance(node, ast.Name) else None

        def value(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, (ast.List, ast.Tuple)):
                return {"alternatives": [value(item) for item in node.elts]}
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                cls = aliases.get(node.value.id, node.value.id)
                if cls in classes:
                    return {"task": classes[cls], "name": node.attr}
                return diagnostic(node, "unknown asset class")
            if isinstance(node, ast.Name):
                symbol = name(node)
                if symbol.startswith("page_"):
                    return {"page": symbol}
                return {"callable": {"file": "tasks/" + rel, "name": symbol}}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                callee = name(node.func)
                arguments = [value(arg) for arg in node.args]
                keywords = {kw.arg: value(kw.value) for kw in node.keywords if kw.arg}
                if any(kw.arg is None for kw in node.keywords):
                    return diagnostic(node, "keyword expansion needs review")
                if callee in ("any_of", "all_of", "not_"):
                    key = {"any_of": "any", "all_of": "all", "not_": "not"}[callee]
                    if callee == "not_" and len(arguments) != 1:
                        return diagnostic(node, "not_ requires one matcher")
                    return {key: arguments[0] if callee == "not_" else arguments}
                if callee == "conditional_action":
                    condition = keywords.get("condition", arguments[0] if arguments else None)
                    action = keywords.get("action", arguments[1] if len(arguments) > 1 else None)
                    if condition is None or action is None:
                        return diagnostic(node, "conditional_action incomplete")
                    return {"condition": condition, "action": action}
                if callee == "sequence":
                    return {"sequence": arguments, "success_index": keywords.get("success_index", 0)}
                if callee == "random_click":
                    # Native adapters may implement this finite safe palette.
                    # This is a description, never an instruction to eval it.
                    return {"safe_random_click": {"args": arguments, **keywords}}
                return diagnostic(node, "unsupported action factory")
            if isinstance(node, ast.Lambda):
                return {"callable": {"file": "tasks/" + rel, "line": node.lineno,
                                     "lambda": ast.unparse(node),
                                     "assets": {alias: classes[original] for alias, original in aliases.items()
                                                if original in classes}}}
            return diagnostic(node, "unsupported page expression")

        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "GameUi":
                for statement in node.body:
                    if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                            and isinstance(statement.targets[0], ast.Name)
                            and statement.targets[0].id == "DEFAULT_UNKNOWN_CLOSERS"):
                        graph["unknown_closers"] = value(statement.value)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else (
                    node.target if isinstance(node, ast.AnnAssign) else None)
                call = node.value
                if (isinstance(target, ast.Name) and isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name) and name(call.func) == "Page"):
                    kwargs = {kw.arg: value(kw.value) for kw in call.keywords if kw.arg}
                    key = kwargs.get("key", target.id)
                    if len(call.args) != 1 or not isinstance(key, str):
                        diagnostic(node, "Page requires one recognizer and a static key")
                        continue
                    priority = kwargs.get("priority", 50)
                    if type(priority) is not int:
                        diagnostic(node, "dynamic Page priority")
                        continue
                    page = {"check": value(call.args[0]), "priority": max(1, min(100, priority)),
                            "cost": kwargs.get("cost", 1), "category": kwargs.get("category",
                            "global" if path.parent.name == "GameUi" else
                            re.sub(r"(?<!^)(?=[A-Z])", "_", path.parent.name).lower()),
                            "file": "tasks/" + rel, "line": node.lineno, "hooks": {}}
                    if kwargs.get("register", True) is not False:
                        graph["pages"][key] = page
                    continue
                try:
                    ast.literal_eval(call)
                except (ValueError, TypeError):
                    diagnostic(node, "unsupported module assignment may affect page registration")
                continue
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    continue  # module documentation
                if (isinstance(node, ast.If) and not node.orelse and
                        ast.dump(node.test) == ast.dump(ast.parse("__name__ == '__main__'", mode="eval").body)):
                    continue  # demonstrably inactive during PageRegistry imports
                diagnostic(node, "unsupported module statement may affect page registration")
                continue
            call = node.value
            if isinstance(call.func, ast.Name) and name(call.func) == "inherit_transitions":
                if not inheritance_audited:
                    diagnostic(node, "transition inheritance implementation is not audited")
                    continue
                if not all(isinstance(arg, ast.Name) for arg in call.args):
                    diagnostic(node, "dynamic transition inheritance")
                    continue
                symbols = [name(arg) for arg in call.args]
                if len(symbols) < 2:
                    diagnostic(node, "transition inheritance needs targets")
                    continue
                source, targets = symbols[0], symbols[1:]
                source_links = [copy.deepcopy(link) for link in graph["links"] if link["from"] == source]
                for target in targets:
                    for link in source_links:
                        if link["to"] == target or any(old["from"] == target and old["to"] == link["to"] for old in graph["links"]):
                            continue
                        link = copy.deepcopy(link)
                        link.update({"from": target, "key": target + "->" + link["to"],
                                     "inherited_from": source})
                        graph["links"].append(link)
                continue
            if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
                diagnostic(node, "unsupported module call may affect page registration")
                continue
            source, method = name(call.func.value), call.func.attr
            if not source.startswith("page_"):
                diagnostic(node, "unsupported registry mutation or module call")
                continue
            if method == "connect":
                kwargs = {kw.arg: value(kw.value) for kw in call.keywords if kw.arg}
                destination = kwargs.pop("destination", value(call.args[0]) if call.args else None)
                action = kwargs.pop("action", value(call.args[1]) if len(call.args) > 1 else None)
                if not isinstance(destination, dict) or "page" not in destination or action is None:
                    diagnostic(node, "incomplete page connection")
                    continue
                edge = {"from": source, "to": destination["page"], "button": action,
                        "file": "tasks/" + rel, "line": node.lineno, **kwargs}
                edge.setdefault("key", source + "->" + edge["to"])
                graph["links"] = [old for old in graph["links"] if old["key"] != edge["key"]]
                graph["links"].append(edge)
            elif method in ("add_enter_success_hooks", "add_enter_failure_hooks", "add_leave_success_hooks", "add_leave_failure_hooks"):
                if source not in graph["pages"]:
                    diagnostic(node, "hook on unknown page")
                    continue
                stage = method.removeprefix("add_").removesuffix("_hooks")
                graph["pages"][source]["hooks"].setdefault(stage, []).extend(value(arg) for arg in call.args)
            else:
                diagnostic(node, "unsupported page mutation")
    for edge in graph["links"]:
        if edge["from"] not in graph["pages"] or edge["to"] not in graph["pages"]:
            graph["diagnostics"].append({"file": edge.get("file"), "line": edge.get("line"),
                "reason": "edge references unknown page", "expression": edge["key"]})
    return graph
