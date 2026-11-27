"""Guarded assttyys 313 navigation and team branches (MIT, 2019 Chaos)."""
from .handlers import _count
from .team_handlers import _all, _expr, _push, _rerun


def build_qiling_handler(b):
    checks = "qiling313_plate_checks"
    matched = "qiling313_plate_matched"
    purchases = "qiling_ball"
    first_team = "team_up_Frist"
    b.model["vars"] = {checks: 0, matched: False, purchases: 0, first_team: True}
    counter = [_count(313)]
    types = b.model["params"]["type"]["choices"]

    def guarded_clicks(index):
        return [{**action, "recheck": True} for action in b.actions(index)]

    def guarded_gap(name, index, lines, condition, effects, contracts):
        b.add(name, condition, [b.gap(name, lines, condition, [
            {"effect": "source_operators", "index": index, "operations": b.ops[index]["oper"]}, *effects], True, contracts)],
            counts=counter)

    guarded_gap("purchase_stone", 13, (272, 280), _all(_expr("buy"), b.when(13)), [],
                ["positive identification of the purchase and user approval"])
    guarded_gap("purchase_ball", 14, (281, 290), _all(_expr(f"buy_ball and {purchases} < 3"), b.when(14)),
                [{"effect": "increment_global_after_purchase", "key": purchases}],
                ["positive identification of the purchase and user approval", "source purchase count"])
    for index, wanted in ((2, types[:4]), (11, types[4:])):
        condition = _all(b.when(index), {"any": [_expr(f"type == {name!r}") for name in wanted]})
        b.add(f"switch_region_{index}", condition, guarded_clicks(index), counts=counter)

    bosses = guarded_clicks(3)
    for i, action in enumerate(bosses):
        b.add(f"select_boss_{i}", _all(b.when(3), _expr("team != '队员'"),
              _expr(f"type == {types[i]!r} or type == {types[i+4]!r}")), [action], counts=counter)

    choose_solo, choose_team = guarded_clicks(5)
    b.add("start_as_captain", _all(b.when(5), _expr("team == '队长'")),
          [choose_team, {"set": {first_team: True}}], counts=counter)
    b.add("start_solo", _all(b.when(5), _expr("team == '单人'")), [choose_solo], counts=counter)
    b.add("member_on_selection", _all(b.when(5), _expr("team == '队员'")),
          outcome=None, counts=counter, internal=True)

    dialog = b.when(8)
    x1, y1, x2, y2 = b.ops[8]["oper"][1][3:7]
    lookup = {"ocr_full": {"keyword": "契", "region": [x1, y1, x2 - x1, y2 - y1],
                           "selection": "unique_contains", "evidence": "complete_keyword"}}
    b.add("read_dialog", dialog, counts=counter, outcome=None, internal=True)
    memory = _all(dialog, lookup)
    cancel = guarded_clicks(8)[2]
    b.add("cancel_memory_dialog", memory, [cancel, {"scheme_transition": {"mode": "rerun", "target": "返回庭院"}}])
    b.gap("memory_dialog_lifecycle", (371, 376), memory,
          [_rerun("返回庭院"), {"effect": "sleep", "ms": 3000}], True,
          ["verify source post-rerun timing"], blocking=False)
    b.add("unverified_dialog", dialog, [b.gap("dialog_confirmation", (371, 380), dialog,
        [{"effect": "source_findText_absence_branch", "ordered_intents": [guarded_clicks(8)[0]]}], True,
        ["positive identification of plate dialog and user approval if confirmation spends a resource"])])

    plates = b.when(9)
    b.add("reset_plate_checks", _expr("True"), [{"set": {checks: 0, matched: False}}], outcome=None, internal=True)
    refresh = {"handler_control": {"op": "refresh"}}
    b.add("read_plates", plates, [{"inc": checks}, {"set": {matched: True}}, refresh],
          counts=counter, outcome=None, internal=True)
    fallback = b.gap("no_plates_rerun", (383, 397), _expr(f"{checks} >= 4"),
        [{"effect": "source_selection_after_four_reads", "ordered_intents": [guarded_clicks(9)[1]]},
         _push("无盘子"), _rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 2000}], True,
        ["confirm the plate selection cost", "source Push", "named or sentinel source rerun"])
    b.add("no_plates_rerun", _expr(f"{checks} >= 4"), [fallback], internal=True)
    edge = "unresolved_source_obligation:team313.plate_loop requires team_workflow"
    b.add("retry_plate_read", _expr(f"{matched} and {checks} < 4"),
          [{"wait": 1000}, {"set": {matched: False}}, refresh, {"fail": edge}], outcome=None, internal=True)
    b.model["proof"]["source_phase_edges"] = {"retry_plate_read": {"target_case": "read_plates", "gate_prefix": edge}}

    b.add("enter_qiling", b.when(0), guarded_clicks(0), counts=counter)
    guarded_gap("summon", 4, (399, 405), b.when(4), [],
                ["verify the summon dialog and exact cost", "user approval for summoning"])
    for index in (6, 7, 10, 12):
        b.add(f"misc_{index}", b.when(index), guarded_clicks(index), counts=counter)
    b.model["proof"]["source_state_bindings"] = {"global.qiling_ball": purchases, "global.team_up_Frist": first_team}
    b.model["proof"]["resource_costs"] = "Purchase, summon and uncertain plate costs are explicit approval obligations."
