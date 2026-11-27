"""Stable serializations for the two already-audited OAS AST pin formats.

Python 3.14 changed ast.dump's default representation of empty list fields.
Choose the format that produced a pin explicitly; never reinterpret a failed
pin as approval to accept new source. Nonempty new fields stay in the digest.
"""
from __future__ import annotations

import ast
import hashlib
import re


def dump_source_node(node: ast.AST, *, style: str) -> str:
    if style not in ("compact-314", "legacy-311"):
        raise ValueError("unknown AST pin format: " + str(style))

    def format_node(value):
        if isinstance(value, ast.AST):
            cls = type(value)
            parts = []
            for name in value._fields:
                if not hasattr(value, name):
                    continue
                child = getattr(value, name)
                if child is None and getattr(cls, name, ...) is None:
                    continue
                if isinstance(child, list) and not child:
                    # Type parameter fields were absent before Python 3.12.
                    # Nonempty type parameters must still change the digest.
                    if style == "legacy-311" and name == "type_params":
                        continue
                    types = getattr(cls, "_field_types", {})
                    if name in types:
                        is_list = getattr(types[name], "__origin__", None) is list
                    else:
                        # Older supported Python versions expose the same ASDL
                        # list markers through trusted stdlib class docstrings.
                        is_list = bool(re.search(
                            r"\b\w+\*\s+" + re.escape(name) + r"(?:,|\))",
                            cls.__doc__ or "",
                        ))
                    if style == "compact-314" and is_list:
                        continue
                parts.append(name + "=" + format_node(child))
            return cls.__name__ + "(" + ", ".join(parts) + ")"
        if isinstance(value, list):
            return "[" + ", ".join(format_node(item) for item in value) + "]"
        return repr(value)

    return format_node(node)


def source_node_hash(node: ast.AST, *, style: str) -> str:
    return hashlib.sha256(dump_source_node(node, style=style).encode()).hexdigest()
