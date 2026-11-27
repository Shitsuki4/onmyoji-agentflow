"""A tiny parser for the JavaScript/TypeScript *data literals* used by assttyys.

It understands arrays, objects (quoted or bare keys), strings, numbers
(decimal / hex / negative), true/false/null/undefined, comments and trailing
commas. Bare identifiers are resolved through ``consts`` (e.g. ``left = 0``) or
returned as ``{"$ref": name}``. Anything else (function calls, arrow
functions) raises ``ValueError`` - we never execute upstream code.
"""
from __future__ import annotations

import re

_NUM = re.compile(r"-?(0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)")
_IDENT = re.compile(r"[A-Za-z_$\u4e00-\u9fff][\w$\u4e00-\u9fff]*")


class Parser:
    def __init__(self, text: str, consts: dict | None = None):
        self.s = text
        self.i = 0
        self.consts = consts or {}

    def error(self, msg):
        ctx = self.s[max(0, self.i - 30): self.i + 30].replace("\n", " ")
        raise ValueError(f"{msg} at {self.i}: ...{ctx}...")

    def ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif s.startswith("//", self.i):
                j = s.find("\n", self.i)
                self.i = len(s) if j < 0 else j + 1
            elif s.startswith("/*", self.i):
                j = s.find("*/", self.i)
                if j < 0:
                    self.error("unterminated comment")
                self.i = j + 2
            else:
                break

    def value(self):
        v = self.product()
        while isinstance(v, (int, float)) and not isinstance(v, bool):
            self.ws()
            if self.i < len(self.s) and self.s[self.i] in "+-":
                op = self.s[self.i]
                self.i += 1
                rhs = self.product()
                if type(rhs) not in (int, float):
                    self.error("non-numeric arithmetic")
                v = v + rhs if op == "+" else v - rhs
            else:
                break
        return v

    def product(self):
        v = self.atom()
        while type(v) in (int, float):
            self.ws()
            if self.i >= len(self.s) or self.s[self.i] != "*":
                break
            self.i += 1
            rhs = self.atom()
            if type(rhs) not in (int, float):
                self.error("non-numeric arithmetic")
            v *= rhs
        return v

    def atom(self):
        self.ws()
        if self.i >= len(self.s):
            self.error("unexpected end")
        c = self.s[self.i]
        if c == "[":
            return self.array()
        if c == "{":
            return self.obj()
        if c in "'\"`":
            return self.string()
        m = _NUM.match(self.s, self.i)
        if m and (c.isdigit() or c in "-."):
            self.i = m.end()
            t = m.group(0)
            neg = t.startswith("-")
            body = t[1:] if neg else t
            if body.lower().startswith("0x"):
                v = int(body, 16)
            elif any(ch in body for ch in ".eE"):
                v = float(body)
            else:
                v = int(body)
            return -v if neg else v
        m = _IDENT.match(self.s, self.i)
        if m:
            name = m.group(0)
            self.i = m.end()
            self.ws()
            if self.i < len(self.s) and self.s[self.i] in "(=":
                self.error(f"code is not data: {name}")
            lit = {"true": True, "false": False, "null": None, "undefined": None}
            if name in lit:
                return lit[name]
            if name in self.consts:
                return self.consts[name]
            return {"$ref": name}
        self.error(f"unexpected {c!r}")

    def string(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                if self.i + 1 >= len(self.s):
                    self.error("unterminated string escape")
                nxt = self.s[self.i + 1]
                out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                self.i += 2
                continue
            if c == q:
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1
        self.error("unterminated string")

    def array(self):
        self.i += 1
        out = []
        while True:
            self.ws()
            if self.i >= len(self.s):
                self.error("unterminated array")
            if self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.value())
            self.ws()
            if self.i >= len(self.s):
                self.error("unterminated array")
            if self.s[self.i] == ",":
                self.i += 1
            elif self.s[self.i] != "]":
                self.error("expected , or ]")

    def obj(self):
        self.i += 1
        out = {}
        while True:
            self.ws()
            if self.i >= len(self.s):
                self.error("unterminated object")
            if self.s[self.i] == "}":
                self.i += 1
                return out
            if self.s[self.i] in "'\"":
                key = self.string()
            else:
                m = _IDENT.match(self.s, self.i) or re.compile(r"\d+").match(self.s, self.i)
                if not m:
                    self.error("bad key")
                key = m.group(0)
                self.i = m.end()
            self.ws()
            if self.i >= len(self.s):
                self.error("unterminated object")
            if self.s[self.i] != ":":
                self.error("expected :")
            self.i += 1
            out[key] = self.value()
            self.ws()
            if self.i >= len(self.s):
                self.error("unterminated object")
            if self.s[self.i] == ",":
                self.i += 1
            elif self.s[self.i] != "}":
                self.error("expected , or }")


def parse(text: str, consts: dict | None = None):
    parser = Parser(text, consts)
    result = parser.value()
    parser.ws()
    if parser.i != len(text):
        parser.error("trailing code is not data")
    return result


def find_consts(src: str) -> dict:
    """Collect simple numeric constants such as ``const left = 0;`` (commented ones ignored)."""
    consts = {}
    for line in src.splitlines():
        m = re.match(r"\s*const\s+(\w+)\s*=\s*(-?\d+)\s*;", line)
        if m:
            consts[m.group(1)] = int(m.group(2))
    return consts


def extract_literal_after(src: str, marker_regex: str, start: int = 0):
    """Find ``marker_regex`` and return (literal_text, end_index) of the [ or { literal after it."""
    m = re.compile(marker_regex).search(src, start)
    if not m:
        return None, -1
    i = m.end()
    while i < len(src) and src[i] not in "[{":
        i += 1
    if i >= len(src):
        return None, -1
    depth = 0
    j = i
    in_str = None
    while j < len(src):
        c = src[j]
        if in_str:
            if c == "\\":
                j += 2
                continue
            if c == in_str:
                in_str = None
        elif src.startswith("//", j):
            k = src.find("\n", j)
            j = len(src) if k < 0 else k
            continue
        elif src.startswith("/*", j):
            k = src.find("*/", j)
            j = len(src) if k < 0 else k + 2
            continue
        elif c in "'\"`":
            in_str = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1], j + 1
        j += 1
    return None, -1
