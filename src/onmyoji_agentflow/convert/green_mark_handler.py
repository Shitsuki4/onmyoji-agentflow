"""Guarded native 051 green-mark handler (assttyys, MIT, 2019 Chaos)."""
from .handlers import _count
from .team_handlers import _all, _expr


def build_green_mark(b):
    pending, armed, fresh = "green51_pending", "green51_armed", "green51_new_round"
    seen, tick, waits = "green51_seen_count", "green51_poll_start_ms", "green51_waits"
    region_vars = ["green51_target_x", "green51_target_y", "green51_target_w", "green51_target_h"]
    b.model["vars"] = {pending: False, armed: False, fresh: False, "run_times_2": 0,
                       seen: 0, tick: 0, waits: 0, **{key: 0 for key in region_vars}}
    battle = b.when(0)
    ready = {"any": [b.when(1), b.when(2)]}
    marked = {"find": "绿标"}
    coord = _expr("greenType == '自定义坐标'")
    text = _expr("greenType == '自定义文本'")
    profile = _expr("greenTextMatchMode == '包含' and offset == '0,0' and greenText")
    x, y, right, bottom = b.ops[0]["oper"][3][3:7]
    recognized = {"ocr_full": {"keyword_var": "greenText", "region": [x, y, right - x, bottom - y],
                               "selection": "unique_contains", "evidence": "complete_keyword"}}
    capture = {"capture_region": {"vars": region_vars,
        "rect": ["match_x + match_w // 2 - 13", "match_y + match_h // 2 + 50", 26, 40]}}
    coordinate_click = {"click": {"xy_param": "greenPosition", "radius": 20}, "delay": 1000, "recheck": True}
    text_click = {"click": {"rect_vars": region_vars}, "delay": 1000, "recheck": True}
    clear = {"set": {pending: False}}
    b.add("reset_work", _expr("True"), [{"set": {armed: False, fresh: False, waits: 0}}],
          outcome=None, internal=True)
    b.add("manual_to_auto", b.when(3), b.actions(3), outcome=None)
    prep = _all(_expr("preSearch"), ready)
    b.add("pre_count", prep, counts=[_count(51)], outcome=None, internal=True)
    uncached = _all(prep, _expr(f"not {pending}"))
    b.add("pre_coordinates", _all(uncached, coord), [{"set": {pending: True}}])
    text_gap = b.gap("text_profile", (76, 108), {"mode": "text OCR"},
                     [{"effect": "resolve fuzzy OCR or configured target offset"}], None,
                     ["calibrate fuzzy discovery and translate bounded offsets"])
    b.add("pre_text_profile", _all(uncached, text, {"not": profile}), [text_gap])
    b.add("pre_text_capture", _all(uncached, text, profile, recognized),
          [capture, {"set": {pending: True}}])
    b.add("pre_text_miss", _all(uncached, text, profile), [{"wait": 3000}], internal=True)

    cached_battle = _all(battle, _expr(f"preSearch and {pending}"))
    b.add("cache_already_marked", _all(cached_battle, marked), [clear], internal=True)
    for name, mode, click in (("coord", coord, coordinate_click), ("text", text, text_click)):
        b.add(f"cache_{name}", _all(cached_battle, mode, {"not": marked}), [click, clear])
    b.add("skip_outside_battle", {"not": battle}, outcome=False, internal=True)
    first = _expr(f"not preSearch and ((run_times_2 != {seen} and run_times_2 != 0) "
                  f"or ({seen} == 0 and run_times_2 == 0))")
    b.add("new_round", first, [{"set": {seen: "run_times_2 - (run_times_2 == 0)", fresh: True}}],
          outcome=None, internal=True)
    b.add("existing_mark", _all(_expr(f"not {fresh}"), marked), outcome=False, internal=True)
    b.add("prepare_coords", _all(battle, coord), [{"set": {armed: True, tick: "elapsed_ms"}}],
          outcome=None, internal=True)
    b.add("battle_text_profile", _all(text, {"not": profile}), [text_gap])
    b.add("battle_text_capture", _all(battle, text, profile, recognized),
          [capture, {"set": {armed: True, tick: "elapsed_ms"}}], counts=[_count(51)],
          outcome=None, internal=True)
    b.add("battle_text_miss", _all(text, _expr(f"not {armed}")), [{"wait": 5000}],
          outcome=False, internal=True)
    b.add("lost_battle", {"not": battle}, outcome=False, internal=True)
    b.add("mark_appeared", _all(_expr(f"not {fresh}"), marked), outcome=False, internal=True)
    edge = b.gap("mark_poll", (242, 251), {"known_battle_and_mark_absent": True},
                 [{"effect": "refresh every 200ms up to 3 seconds"}], None,
                 ["native bounded handler phase edge"], blocking=False)
    b.add("watch_mark", _expr(f"{armed} and not {fresh} and elapsed_ms - {tick} < 3000 and {waits} < 15"),
          [{"wait": 200}, {"handler_control": {"op": "refresh"}}, {"inc": waits}, edge],
          outcome=None, internal=True)
    for name, mode, click in (("coord", coord, coordinate_click), ("text", text, text_click)):
        b.add(f"mark_{name}", _all(battle, _expr(armed), mode,
                                 {"any": [_expr(fresh), {"not": marked}]}), [click])
    proof = b.model["proof"]
    proof["source_phase_edges"] = {"watch_mark": {"target_case": "lost_battle", "gate_prefix": edge["fail"]}}
    proof["source_state_bindings"] = {"global.greenTagEnd": seen, "global.greenPosition": region_vars,
                                     "runTimes['2']": "run_times_2"}
    proof["text_adapter"] = "Unique substring and zero-offset OCR, with a frame-bounded derived target."
