"""Safe expressions for workflow conditions: numbers, variables, comparisons, and/or/not, + - * //.

No function calls, attributes, subscripts or anything else: an LLM-generated
workflow can only count and compare, never run code.
"""
from __future__ import annotations

import ast
import operator

from ..errors import WorkflowError

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge}


def compile_expr(text: str) -> ast.Expression:
    try:
        tree = ast.parse(str(text), mode="eval")
    except SyntaxError as e:
        raise WorkflowError(f"表达式语法错误: {text!r}") from e
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub,
                             ast.BinOp, ast.Compare, ast.Name, ast.Load, ast.Constant)):
            continue
        if type(node) in _BIN or type(node) in _CMP:
            continue
        raise WorkflowError(f"表达式里不允许 {type(node).__name__}: {text!r}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool, str)):
            raise WorkflowError(f"不支持的常量: {text!r}")
    return tree


def evaluate(tree_or_text, variables: dict):
    tree = compile_expr(tree_or_text) if isinstance(tree_or_text, str) else tree_or_text

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in ("true", "True"):
                return True
            if n.id in ("false", "False"):
                return False
            if n.id not in variables:
                raise WorkflowError(f"未定义的变量: {n.id}")
            return variables[n.id]
        if isinstance(n, ast.BoolOp):
            vals = (ev(v) for v in n.values)
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return (not v) if isinstance(n.op, ast.Not) else -v
        if isinstance(n, ast.BinOp):
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = ev(comp)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        raise WorkflowError(f"bad node {n}")

    return ev(tree)


def names_in(text: str) -> set[str]:
    return {n.id for n in ast.walk(compile_expr(text)) if isinstance(n, ast.Name)} - {"true", "false", "True", "False"}
