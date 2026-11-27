"""Audited 311 targeting branches (assttyys, MIT, Copyright (c) 2019 Chaos)."""

from .handlers import _count
from .team_handlers import _all, _expr


def build_red_mark(b):
    b.model["vars"] = {"redFlag": False}
    b.model["proof"]["source_state_bindings"] = {"global.redFlag": "redFlag"}
    ready = _all(b.when(0), _expr("not redFlag"))
    marked = {"set": {"redFlag": True}}
    b.add("coordinates", _all(ready, _expr("redType == '自定义坐标'")), [
        {"wait": 1000}, {"click": {"xy_param": "redPosition", "radius": 20}, "delay": 1000, "recheck": True},
        marked])
    boss = _all(ready, _expr("redType == 'PVE顶部BOSS血条固定红标'"))
    b.add("boss_already_marked", _all(boss, b.when(2)), [marked], counts=[_count(311)])
    boss_click = {**b.actions(1)[0], "recheck": True}
    b.add("boss_mark", _all(boss, b.when(1), {"not": b.when(2)}), [boss_click, marked], counts=[_count(311)])

    icon_bar = {"any": [b.when(4), b.when(5)]}
    arakawa = _all(ready, _expr("redType == '神荒'"), icon_bar)
    bleed = {"find": "腐血"}
    for branch, marker, min_offset, priority in (
        ("bleed", "腐血", 1, bleed),
        ("arakawa", "神荒", -2, _all({"not": bleed}, {"find": "神荒"})),
    ):
        for row, offset in (("second_below", [35, 42, 40, 45]), ("lowest_else", [35, 60, 40, 80])):
            column = {"find_column": {"target": "红标_血条", "reference": marker,
                                      "x_offsets": [min_offset, 99], "row": row}}
            b.add(f"{branch}_{row}", _all(arakawa, priority, column), [
                {"click_found": True, "offset": offset, "delay": 1000, "recheck": True}, marked])
        b.add(branch + "_no_row", _all(arakawa, priority), [])
    b.add("no_marker", arakawa, [marked], outcome=False)

    duel = _all(ready, _expr("redType == '斗技式神'"))
    names = b.gap("duel_names", (284, 315), _all(duel, b.when(5)),
                  [{"effect": "toggle name display when present, then use ordered fuzzy OCR names"}], True,
                  ["source parseName and fuzzy OCR matching/geometry"])
    b.add("duel_find_names", _all(duel, b.when(5)), [names])
    b.add("duel_timeout", _all(duel, b.when(8)), [
        *({**action, "recheck": True} for action in b.actions(8)), marked])
    b.add("duel_waiting", duel, [])
