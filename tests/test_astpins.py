import ast

import pytest

from onmyoji_agentflow.convert.astpins import dump_source_node, source_node_hash


def test_legacy_and_compact_formats_are_explicit_and_keep_existing_layouts():
    node = ast.parse("def f(a): pass").body[0]
    assert dump_source_node(node, style="compact-314") == (
        "FunctionDef(name='f', args=arguments(args=[arg(arg='a')]), body=[Pass()])"
    )
    assert dump_source_node(node, style="legacy-311") == (
        "FunctionDef(name='f', args=arguments(posonlyargs=[], args=[arg(arg='a')], "
        "kwonlyargs=[], kw_defaults=[], defaults=[]), body=[Pass()], decorator_list=[])"
    )


@pytest.mark.parametrize("style", ["compact-314", "legacy-311"])
def test_source_changes_still_invalidate_the_pin_but_locations_do_not(style):
    first = ast.parse("def f(a): return []").body[0]
    relocated = ast.parse("\n\ndef f(a): return []").body[0]
    changed = ast.parse("def f(a): return None").body[0]
    assert source_node_hash(first, style=style) == source_node_hash(relocated, style=style)
    assert source_node_hash(first, style=style) != source_node_hash(changed, style=style)


@pytest.mark.parametrize("style", ["compact-314", "legacy-311"])
def test_literal_empty_list_is_never_removed_from_constant_payload(style):
    assert dump_source_node(ast.Constant(value=[]), style=style) == "Constant(value=[])"


def test_empty_new_type_parameters_do_not_change_legacy_pin_but_nonempty_do():
    node = ast.parse("class Example: pass").body[0]
    original = source_node_hash(node, style="legacy-311")
    if "type_params" not in node._fields:
        node._fields = (*node._fields, "type_params")
    node.type_params = []
    assert source_node_hash(node, style="legacy-311") == original
    node.type_params = [ast.Name(id="T", ctx=ast.Load())]
    assert source_node_hash(node, style="legacy-311") != original


def test_unknown_format_cannot_silently_choose_another_pin_representation():
    with pytest.raises(ValueError, match="unknown AST pin format"):
        source_node_hash(ast.parse("pass"), style="current-python-default")
