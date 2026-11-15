"""YAML helpers: compact flow style for short scalar lists (coordinates, colours)."""
from __future__ import annotations

import yaml


class _Dumper(yaml.SafeDumper):
    pass


def _list_repr(dumper, data):
    flow = all(not isinstance(v, (dict, list)) for v in data) or (
        all(isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v) for v in data) and len(data) <= 40)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(list, _list_repr)
_Dumper.add_representer(tuple, _list_repr)


def dump_yaml(data) -> str:
    return yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=200)


def load_yaml(text_or_path):
    if hasattr(text_or_path, "read_text"):
        text_or_path = text_or_path.read_text(encoding="utf-8")
    return yaml.safe_load(text_or_path)
