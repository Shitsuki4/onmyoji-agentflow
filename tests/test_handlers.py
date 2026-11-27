"""Offline compiler/dispatcher contracts. No upstream execution or device access."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from onmyoji_agentflow.convert.handlers import (
    AUDITED_METHODS, DispatchState, UnsupportedHandler, component_handler,
    compose_handlers, literal_handler, native_workflow, phase_workflow, trace_cycle,
)
from onmyoji_agentflow.workflow.expr import evaluate
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml, load_yaml


def handler(fid, cases=None, *, params=None, variables=None, guard=None):
    out = {"id": fid, "name": str(fid), "proof": {"source_sha256": "a" * 64},
           "params": params or {}, "vars": variables or {}, "resources": [],
           "resource_specs": {}, "unmatched_return": False,
           "cases": cases or [case("default")]}
    if guard:
        out["guard"] = guard
    return out


def case(name, *, condition=None, handled=True, actions=None, counter=None, **extra):
    return {"id": name, "when": condition or {"expr": "True"}, "do": actions or [],
            "return": handled, "count_events": [] if counter is None else [
                {"counter_id": counter, "not_for_count": False}], **extra}


def compile_literal(source, colors=None):
    return literal_handler(source, colors or {}, expected_sha256=hashlib.sha256(source.encode()).hexdigest())


DATA_SOURCE = """
import { IFuncOrigin, IFuncOperatorOrigin } from '@/interface/IFunc';
const center = 1;
export class Func11 implements IFuncOrigin {
  id = 11; name = 'refresh';
  config = [{config: [{name: 'once', default: false}]}];
  operator: IFuncOperatorOrigin[] = [
    {desc: [1280,720,[[center,10,20,0xff0000]]], retest: 1000, notForCnt: true,
     oper: [[center,1280,720,100,100,110,110,500]]},
    {desc: [1280,720,[[center,30,40,0x00ff00]]],
     oper: [[center,1280,720,-1,-1,-1,-1,3000]]}
  ];
}
export default new Func11();
"""


def test_priority_and_false_yield_use_same_frame_with_shared_effects():
    first = handler(38, [case("empty", handled=False, counter=38,
                             actions=[{"set": {"seen": "seen + 1"}}])], variables={"seen": 0})
    second = handler(2, [case("after", condition={"expr": "seen == 1"}, actions=[{"click": [1, 2, 3, 4]}])])
    result = trace_cycle(compose_handlers("ordered", [first, second, handler(3)]), [], now_ms=100)
    assert result["handled"]
    assert result["actions"] == [{"click": [1, 2, 3, 4]}]
    assert [(r["id"], r["handled"]) for r in result["returns"]] == [(38, False), (2, True)]
    assert result["state"].run_times == {38: 1}
    assert result["state"].variables["seen"] == 1


def test_false_return_ends_handler_but_null_continues_latched_guard():
    false = handler(1, [case("one", handled=False), case("must_not_run", actions=[{"fail": "bad"}])])
    latch = handler(2, [case("clear", handled=None, actions=[{"set": {"flag": False}}]),
                        case("still_entered", actions=[{"inc": "hits"}])],
                    variables={"flag": True, "hits": 0}, guard={"expr": "flag"})
    program = compose_handlers("latch", [false, latch])
    result = trace_cycle(program, [], now_ms=0)
    assert result["state"].variables == {"flag": False, "hits": 1}
    assert [r["handled"] for r in result["returns"]] == [False, True]
    again = trace_cycle(program, [], now_ms=1, state=result["state"])
    assert not again["handled"] and not again["actions"]


def test_scheme_order_duplicates_and_config_precedence_are_preserved():
    a = handler(1, [case("yield", handled=False)], params={"once": {"default": True}, "zero": {"default": 7}})
    b = handler(2, params={"once": {"default": True}, "nullable": {"default": "x"}})
    scheme = {"list": [2, 1, 2], "config": {"1": {"once": False, "zero": 0}, "2": {"nullable": None}},
              "commonConfig": {"loopDelay": 0, "afterClickDelayRandom": 0}}
    original = copy.deepcopy((a, b, scheme))
    program = compose_handlers("source_order", [a, b], scheme=scheme,
                               config_overrides={"2": {"once": False}}, common_overrides={"colorSimilar": 95})
    assert [h["id"] for h in program["handlers"]] == [2, 1, 2]
    assert [h["slot"] for h in program["handlers"]] == [0, 1, 2]
    assert {k: v["default"] for k, v in program["params"].items()} == {
        "cfg_1_once": False, "cfg_1_zero": 0, "cfg_2_once": False, "cfg_2_nullable": None}
    assert program["common_config"]["loopDelay"] == program["common_config"]["afterClickDelayRandom"] == 0
    assert program["common_config"]["colorSimilar"] == 95
    assert (a, b, scheme) == original


def test_config_names_are_namespaced_in_nested_guards_and_assignments():
    a = handler(1, [case("off", condition={"not": {"expr": "once"}},
                         actions=[{"set": {"observed": "once"}}])],
                params={"once": {"default": True}}, variables={"observed": True})
    b = handler(2, params={"once": {"default": True}})
    program = compose_handlers("namespace", [a, b], scheme={"config": {"1": {"once": False}}})
    assert program["handlers"][0]["cases"][0]["when"] == {"not": {"expr": "cfg_1_once"}}
    result = trace_cycle(program, [], now_ms=0)
    assert result["state"].variables["observed"] is False
    assert len(result["returns"]) == 1


def test_conflicting_shared_defaults_require_authority_and_resume_preserves_values():
    a, b = handler(1, variables={"flag": False}), handler(2, variables={"flag": True})
    with pytest.raises(UnsupportedHandler, match="conflicting shared"):
        compose_handlers("conflict", [a, b])
    program = compose_handlers("explicit", [a, b], shared_defaults={"flag": True})
    resumed = DispatchState(variables={"flag": False})
    assert trace_cycle(program, [], now_ms=1, state=resumed)["state"].variables["flag"] is False
    assert trace_cycle(program, [], now_ms=1)["state"].variables["flag"] is True


def test_counter_strict_7500_boundary_and_suppressed_timestamp_refresh():
    state = DispatchState()
    assert state.count(1, 0)
    assert not state.count(1, 7500)
    assert not state.count(1, 15000)  # Gap from suppressed match, NOT original counted event.
    assert state.count(1, 22501)
    assert state.run_times == {1: 2}
    assert state.last_func_ms == 22501
    assert state.count(2, 22501)  # Different id counts immediately.
    assert state.count(1, 22501)
    assert state.run_times == {1: 3, 2: 1}


def test_not_for_count_and_zero_id_do_not_touch_last_function_fields():
    state = DispatchState()
    state.count(1, 0)
    assert not state.count(2, 6000, not_for_count=True)
    assert not state.count(0, 6500)
    assert not state.count(None, 7000)
    assert (state.last_func, state.last_func_ms) == (1, 0)
    assert state.count(1, 7501)
    with pytest.raises(UnsupportedHandler, match="backwards"):
        state.count(1, 7499)


def test_count_precedes_input_and_false_does_not_refresh_inactivity():
    source = handler(1, [case("matched", handled=False, counter=1,
                              actions=[{"set": {"count_seen": "run_times_1"}}])], variables={"count_seen": 0})
    state = DispatchState(last_handled_ms=100)
    result = trace_cycle(compose_handlers("counts", [source]), [], now_ms=200, state=state)
    assert not result["handled"]
    assert state.variables["count_seen"] == 1
    assert state.last_handled_ms == 100
    assert result["counts"][0]["at_ms"] == 200


def test_retest_rescans_operator_group_not_earlier_handlers():
    earlier = handler(1, [case("early", condition={"res": "early"})])
    later = handler(2, [case("candidate", condition={"res": "old"}, retest_ms=1000,
                            actions=[{"click": [1, 1, 2, 2]}]),
                         case("changed", condition={"res": "new"}, counter=2,
                              actions=[{"click": [3, 3, 4, 4]}])])
    for h in (earlier, later):
        h["resource_specs"] = {k: {"type": "colors", "points": [[0, 0, "#ffffff"]]} for k in ("early", "old", "new")}
    program = compose_handlers("retest", [earlier, later])
    result = trace_cycle(program, [{"res": "old"}], now_ms=10,
                         refreshed_facts=[[{"res": "early"}, {"res": "new"}]])
    assert result["returns"][0]["handled"] is False
    assert result["actions"] == [{"click": [3, 3, 4, 4]}]
    assert result["counts"][0]["at_ms"] == 1010


def test_retest_without_fresh_frame_fails_closed_and_disappearance_yields():
    source = handler(1, [case("old", condition={"colors": [[1, 2, "#abcdef"]]}, retest_ms=1000, counter=1)])
    program = compose_handlers("fresh", [source, handler(2)])
    with pytest.raises(UnsupportedHandler, match="fresh supplied"):
        trace_cycle(program, [source["cases"][0]["when"]], now_ms=0)
    result = trace_cycle(program, [source["cases"][0]["when"]], now_ms=0, refreshed_facts=[[]])
    assert [r["handled"] for r in result["returns"]] == [False, True]
    assert not result["counts"]


def test_strict_literal_compiler_preserves_raw_anchor_retest_count_and_wait():
    compiled = compile_literal(DATA_SOURCE)
    assert compiled["params"] == {"once": {"default": False}}
    assert compiled["cases"][0]["source_operator"]["oper"][0][:3] == [1, 1280, 720]
    assert compiled["cases"][0]["retest_ms"] == 1000
    assert compiled["cases"][0]["count_events"] == [{"counter_id": 11, "not_for_count": True}]
    assert compiled["cases"][1]["do"] == [{"wait": 3000}]
    program = compose_handlers("literal", [compiled])
    assert load_yaml(dump_yaml(program)) == program


@pytest.mark.parametrize("change", [
    lambda s: s.replace("id = 11", "id = process.exit()"),
    lambda s: s.replace("  id = 11;", "  constructor() { throw new Error('never execute'); } id = 11;"),
    lambda s: s.replace("  id = 11;", "  operatorFunc() { return true; } id = 11;"),
    lambda s: s + " process.exit();",
    lambda s: "process.exit(); " + s,
    lambda s: s.replace("notForCnt: true", "notForCnt: true, hiddenCallback: 'drop-me'"),
    lambda s: s.replace("100,100,110,110,500", "100,100,110,110"),
    lambda s: s.replace("100,100,110,110,500", "-1,100,110,110,500"),
    lambda s: s + " callback();",
])
def test_unknown_code_and_malformed_operators_are_never_silently_dropped(change):
    with pytest.raises((UnsupportedHandler, ValueError)):
        compile_literal(change(DATA_SOURCE))


def test_fingerprint_mismatch_and_correctly_pinned_arbitrary_method_are_rejected():
    with pytest.raises(UnsupportedHandler, match="fingerprint mismatch"):
        literal_handler(DATA_SOURCE, {}, expected_sha256="0" * 64)
    custom = DATA_SOURCE.replace("  id = 11;", "  operatorFunc() { return true; } id = 11;")
    with pytest.raises(UnsupportedHandler, match="custom methods"):
        compile_literal(custom)


@pytest.mark.parametrize("raw", [
    "{desc: 'missing'}", "{desc: [640,360,[[1,1,1,0xffffff]]]}",
    "{desc: [1280,720,[[1,1,1,0xffffff]]], operStepRandom: []}",
    "{notForCnt: 1}", "{retest: true}", "{retest: -2}",
])
def test_literal_unknown_resources_geometry_and_count_metadata_fail_closed(raw):
    source = "export class F { id = 11; operator: IFuncOperatorOrigin[] = [" + raw + "]; }"
    with pytest.raises((UnsupportedHandler, ValueError)):
        compile_literal(source)


def component_fixture(tmp_path, fid, size, *, not_for_count=None):
    root = tmp_path / "resources/upstream/assttyys"
    snapshot = root / "programs/src/src/common/funcList/demo.ts.txt"
    snapshot.parent.mkdir(parents=True)
    operators = [{"desc": [1280, 720, [[1, i + 10, 20, 0xff0000]]],
                  "oper": [[1, 1280, 720, 100, 100, 110, 110, 0]]} for i in range(size)]
    for i in not_for_count or []:
        operators[i]["notForCnt"] = True
    snapshot.write_text(f"id = {fid}; name = 'demo'; operator: IFuncOperatorOrigin[] = " + json.dumps(operators) + ";", encoding="utf-8")
    (root / "colors.yaml").write_text(dump_yaml({"resources": {}}), encoding="utf-8")
    entry = {"id": f"assttyys:func:{fid:03d}", "source": "assttyys", "kind": "component",
             "title": "demo", "workflow": "demo", "fingerprint": "f" * 64,
             "entry_files": ["src/common/funcList/demo.ts"]}
    return component_handler(entry, tmp_path, pins={entry["id"]: entry["fingerprint"]})


def test_component_038_counts_unhandled_empty_room_and_yields_to_later_handler(tmp_path):
    source = component_fixture(tmp_path, 38, 4, not_for_count=[2])
    program = compose_handlers("empty_room", [source, handler(2)])
    facts = [{"colors": [[10, 20, "#ff0000"]]}, {"colors": [[12, 20, "#ff0000"]]}]
    result = trace_cycle(program, facts, now_ms=0)
    assert [r["handled"] for r in result["returns"]] == [False, True]
    assert not result["actions"]
    assert result["state"].run_times == {38: 1}
    assert [e["not_for_count"] for e in result["counts"]] == [False, True]


def test_component_035_preserves_counter_alias_38(tmp_path):
    source = component_fixture(tmp_path, 35, 4)
    result = trace_cycle(compose_handlers("alias", [source]), [{"colors": [[10, 20, "#ff0000"]]}], now_ms=0)
    assert result["state"].run_times == {38: 1}
    assert result["state"].variables["checked_yard_count"] == 1


def test_component_509_clear_is_not_return_true_and_guard_is_latched(tmp_path):
    source = component_fixture(tmp_path, 509, 17)
    program = compose_handlers("records", [source, handler(2)])
    records = {"colors": [[13, 20, "#ff0000"]]}
    result = trace_cycle(program, [records], now_ms=0)
    assert [r["handled"] for r in result["returns"]] == [False, True]
    assert result["state"].variables["change_shikigami_flag"] is False
    assert not result["actions"]
    both = trace_cycle(program, [records, {"colors": [[10, 20, "#ff0000"]]}], now_ms=0)
    assert both["handled"] and len(both["returns"]) == 1
    assert both["actions"][0] == {"click": [100, 100, 110, 110], "delay": 0}


def test_component_501_once_reads_real_shared_counters(tmp_path):
    source = component_fixture(tmp_path, 501, 1)
    program = compose_handlers("buff_once", [source, handler(2)], config_overrides={"501": {"once": True}})
    resumed = DispatchState(run_times={40: 1})
    result = trace_cycle(program, [{"colors": [[10, 20, "#ff0000"]]}], now_ms=0, state=resumed)
    assert [r["handled"] for r in result["returns"]] == [False, True]
    assert not result["actions"]
    assert result["state"].variables["run_times_40"] == 1


def test_component_pin_miss_does_not_read_source(tmp_path):
    assert component_handler({"id": "assttyys:func:011", "source": "assttyys", "kind": "component",
                              "fingerprint": "wrong"}, tmp_path / "nonexistent", pins={}) is None


def test_native_workflow_reports_missing_host_primitives_and_never_claims_task_completion(monkeypatch):
    import onmyoji_agentflow.workflow.schema as schema
    monkeypatch.setattr(schema, "ACTION_KEYS", schema.ACTION_KEYS - {"handler_control"})
    program = compose_handlers("proposal", [compile_literal(DATA_SOURCE)])
    result = native_workflow(program)
    assert not result["original_task_complete"]
    assert result["coverage"] == "handler_model"
    assert not result["executable"] and "handler_control" in result["missing_primitives"]
    with pytest.raises(Exception, match="动作"):
        load_workflow(result["workflow"])


@pytest.mark.parametrize(("fid", "rerun_index"), [(601, 1), (604, 1), (606, 3)])
def test_actual_audited_small_methods_translate_without_running_source(fid, rerun_index):
    default = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    root = Path(os.environ.get("OAF_ASSTTYYS_SOURCE_ROOT", default / "onmyoji-agentflow/upstream-src/assttyys"))
    folder = root / "src/common/funcList"
    sources = list(folder.glob(f"{fid}_*.ts"))
    if not sources:
        pytest.skip("optional local inert upstream fixture is unavailable")
    source = sources[0].read_text(encoding="utf-8")
    compiled = literal_handler(source, {"寮信息界面": {"type": "colors", "points": [[1, 1, "#ffffff"]]}},
                               expected_sha256=AUDITED_METHODS[fid])
    assert all(not case["count_events"] for case in compiled["cases"])
    program = compose_handlers(f"small_{fid}", [compiled])
    branch = next(case for case in compiled["cases"] if case["id"] == f"op_{rerun_index}")
    result = trace_cycle(program, [branch["when"]], now_ms=0)
    transitions = [a["scheme_transition"] for a in result["actions"] if "scheme_transition" in a]
    assert transitions == [{"mode": "rerun", "target": "返回庭院"}]
    assert program["required_schemes"] == ["返回庭院"]
    assert native_workflow(program)["missing_primitives"] == ["handler_control", "scheme_transition"]
    assert result["returns"][0]["handled"]
    if fid == 604:
        assert result["actions"][-1] == {"wait": 1000}
    if fid == 606:
        assert [case["id"] for case in compiled["cases"]] == ["op_0", "op_1", "op_4", "op_5", "op_2", "op_3"]
        popup = compiled["cases"][-2]
        entrance = compiled["cases"][2]
        grouped = trace_cycle(program, [entrance["when"], popup["when"], branch["when"]], now_ms=0)
        assert grouped["actions"] == entrance["do"]
        assert trace_cycle(program, [popup["when"], branch["when"]], now_ms=0)["actions"] == popup["do"]


@pytest.mark.parametrize("alter", [
    lambda h: h["cases"][0].update({"return": "true"}),
    lambda h: h["cases"][0].update({"do": [{"python": "print(1)"}]}),
    lambda h: h["cases"][0].update({"count_events": [{"counter_id": -1}]}),
    lambda h: h["cases"][0].update({"count_events": [{"counter_id": 1, "not_for_count": 1}]}),
])
def test_invalid_return_code_and_counter_contracts_are_rejected(alter):
    source = handler(1)
    alter(source)
    with pytest.raises((UnsupportedHandler, ValueError)):
        compose_handlers("invalid", [source])


def test_missing_components_unknown_config_and_shared_config_shadowing_fail_closed():
    with pytest.raises(UnsupportedHandler, match="missing"):
        compose_handlers("missing", [handler(1)], scheme={"list": [1, 2]})
    with pytest.raises(UnsupportedHandler, match="config"):
        compose_handlers("unknown", [handler(1)], scheme={"config": {"1": {"once": True}}})
    with pytest.raises(UnsupportedHandler, match="shadow"):
        compose_handlers("shadow", [handler(1, params={"once": {"default": True}}, variables={"cfg_1_once": False})])


def run_lowered_cycle(workflow, facts):
    """Walk ordinary generated guards/actions offline; no source callback or device."""
    variables = copy.deepcopy(workflow["vars"])
    variables.update({k: spec["default"] for k, spec in workflow["params"].items()})
    variables.update(elapsed_s=0, elapsed_ms=0, actions=0)
    state = DispatchState(variables=variables)
    observed = {json.dumps(f, sort_keys=True) for f in facts}
    actions = []
    now = 0

    def matches(cond):
        if "expr" in cond:
            return bool(evaluate(cond["expr"], variables))
        if "all" in cond:
            return all(matches(c) for c in cond["all"])
        if "any" in cond:
            return any(matches(c) for c in cond["any"])
        if "not" in cond:
            return not matches(cond["not"])
        return json.dumps(cond, sort_keys=True) in observed

    visited = []
    for _ in range(100):
        variables["elapsed_ms"] = now
        selected = next(s for s in workflow["states"] if matches(s["when"]))
        assert not selected.get("retest_ms"), "this test walker deliberately does not supply refresh frames"
        visited.append(selected["id"])
        for action in selected["do"]:
            if "handler_control" in action:
                control = action["handler_control"]
                assert control["op"] in {"begin", "end"}
                if control["op"] == "end":
                    return {"handled": control["handled"], "state": state, "actions": actions, "visited": visited}
            elif "set" in action:
                before = dict(variables)
                variables.update({k: evaluate(str(v), before) for k, v in action["set"].items()})
                for key in action["set"]:
                    if key.startswith("run_times_"):
                        state.run_times[int(key.removeprefix("run_times_"))] = variables[key]
            elif "inc" in action:
                variables[action["inc"]] += action.get("by", 1)
            else:
                actions.append(action)
                now += action.get("wait", action.get("delay", 0))
    pytest.fail("generated phases did not terminate one dispatcher cycle")


def test_phase_lowering_false_yield_matches_contract_oracle():
    first = handler(1, [case("yield", handled=False, counter=1,
                            actions=[{"set": {"seen": "run_times_1"}}])], variables={"seen": 0})
    second = handler(2, [case("handled", condition={"expr": "seen == 1"}, actions=[{"click": [1, 1, 2, 2]}])])
    program = compose_handlers("phases", [first, second, handler(3)])
    result = phase_workflow(program)
    assert result["missing_primitives"] == ["handler_control"]
    assert not result["executable"] and not result["original_task_complete"]
    assert all("dispatch_handlers" not in a for s in result["workflow"]["states"] for a in s["do"])
    lowered = run_lowered_cycle(result["workflow"], [])
    oracle = trace_cycle(program, [], now_ms=0)
    assert lowered["handled"] == oracle["handled"]
    assert lowered["actions"] == oracle["actions"]
    assert lowered["state"].run_times == oracle["state"].run_times
    assert not any(name.startswith("handler_2_") for name in lowered["visited"])


def test_phase_lowering_038_yield_and_509_latched_guard(tmp_path):
    empty = component_fixture(tmp_path / "empty", 38, 4)
    program = compose_handlers("empty", [empty, handler(2)])
    facts = [{"colors": [[10, 20, "#ff0000"]]}, {"colors": [[11, 20, "#ff0000"]]}]
    result = run_lowered_cycle(phase_workflow(program)["workflow"], facts)
    assert result["handled"] and result["state"].run_times == {38: 1}
    assert not result["actions"]
    records = component_fixture(tmp_path / "records", 509, 17)
    program = compose_handlers("records", [records, handler(2)])
    facts = [{"colors": [[13, 20, "#ff0000"]]}, {"colors": [[10, 20, "#ff0000"]]}]
    result = run_lowered_cycle(phase_workflow(program)["workflow"], facts)
    assert result["state"].variables["change_shikigami_flag"] is False
    assert result["actions"][0] == {"click": [100, 100, 110, 110], "delay": 0}
    assert "handler_1_enter" not in result["visited"]


def test_phase_lowering_all_unhandled_reaches_false_end():
    program = compose_handlers("false", [handler(1, [case("one", condition={"expr": "False"})]),
                                          handler(2, [case("two", handled=False)])])
    result = run_lowered_cycle(phase_workflow(program)["workflow"], [])
    assert not result["handled"] and not result["actions"]
    assert result["visited"][-1] == "handler_end_false"


def test_phase_retest_groups_use_same_phase_and_different_handlers_cannot_preempt():
    source = compile_literal(DATA_SOURCE)
    workflow = phase_workflow(compose_handlers("retest_phase", [handler(1), source]))["workflow"]
    candidates = [s for s in workflow["states"] if s.get("handler_step", {}).get("slot") == 1
                  and s["handler_step"]["kind"] == "case"]
    assert candidates[0]["retest_ms"] == 1000
    assert candidates[0]["when"]["all"][0] == candidates[1]["when"]["all"][0]
    first = next(s for s in workflow["states"] if s["id"] == "h0_default")
    assert first["when"]["all"][0] != candidates[0]["when"]["all"][0]
    contract = workflow["handler_dispatch"]
    assert contract["cached_frame_until_end"] and contract["skip_internal_loop_delay"]
    assert contract["count_preserves_found_anchor"]
    assert contract["comparison"] == ">" and contract["suppression_ms"] == 7500


def test_phase_inline_named_colours_need_no_new_data_file():
    compiled = compile_literal("export class F {id=11; operator: IFuncOperatorOrigin[]=[{desc:'page'}];}",
                               {"page": {"type": "colors", "points": [[1, 2, "#abcdef"]]},
                                "unused": {"type": "colors", "points": [[3, 4, "#123456"]]}})
    assert set(compiled["resource_specs"]) == {"page"}
    result = phase_workflow(compose_handlers("inline", [compiled]))
    assert result["workflow"]["resources"] == []
    branch = next(s for s in result["workflow"]["states"] if s["id"] == "h0_op_0")
    assert branch["when"]["all"][1] == {"colors": [[1, 2, "#abcdef"]]}
    assert run_lowered_cycle(result["workflow"], [{"colors": [[1, 2, "#abcdef"]]}])["handled"]


def test_old_host_rejects_phase_proposal_instead_of_running_ignored_metadata(monkeypatch):
    import onmyoji_agentflow.workflow.schema as schema
    monkeypatch.setattr(schema, "ACTION_KEYS", schema.ACTION_KEYS - {"handler_control"})
    result = phase_workflow(compose_handlers("gate", [handler(1)]))
    with pytest.raises(Exception, match="动作"):
        load_workflow(result["workflow"])


@pytest.mark.parametrize("change", [
    lambda h: h.update(unmatched_return=True),
    lambda h: h["cases"][0].pop("return"),
    lambda h: h["cases"][0].update(hidden_branch=True),
    lambda h: h["cases"][0].update(count_events=[{"counter_id": 1, "hidden": True}]),
])
def test_silent_contract_loss_is_rejected(change):
    source = handler(1)
    change(source)
    with pytest.raises(UnsupportedHandler):
        compose_handlers("bad", [source])


def test_phase_counter_lowering_uses_elapsed_ms_atomic_sets_and_strict_suppression():
    program = compose_handlers("clock", [handler(1, [case("matched", counter=1)])])
    result = phase_workflow(program)
    assert result["missing_builtins"] == ["elapsed_ms"]
    branch = next(s for s in result["workflow"]["states"] if s["id"] == "h0_matched")
    counter_set = branch["do"][0]["set"]
    assert "elapsed_ms - handler_last_ms > 7500" in counter_set["run_times_1"]
    assert not any(a.get("handler_control", {}).get("op") == "count" for a in branch["do"])
    values = dict(result["workflow"]["vars"])
    expected = DispatchState()
    for now in (0, 7500, 15000, 22501):
        values["elapsed_ms"] = now
        before = dict(values)
        values.update({k: evaluate(str(v), before) for k, v in counter_set.items()})
        expected.count(1, now)
        assert values["run_times_1"] == expected.run_times[1]
        assert values["handler_last_ms"] == expected.last_func_ms


def test_phase_not_for_count_retains_metadata_without_emitting_mutations():
    source = handler(1, [case("not_counted")])
    source["cases"][0]["count_events"] = [{"counter_id": 1, "not_for_count": True},
                                            {"counter_id": 0, "not_for_count": False}]
    workflow = phase_workflow(compose_handlers("skip_counts", [source]))["workflow"]
    branch = next(s for s in workflow["states"] if s["id"] == "h0_not_counted")
    assert len(branch["do"]) == 1
    assert set(branch["do"][0]["set"]) == {"handler_phase"}
    assert branch["handler_step"]["count_events"] == source["cases"][0]["count_events"]


def test_source_clock_references_are_read_only_and_consistent_with_relative_trace_origin():
    branch = case("clock_guard", counter=9)
    branch["when"] = {"expr": "handler_last_ms < 0 or elapsed_ms - handler_last_ms > 7500"}
    program = compose_handlers("clock_reference", [handler(9, [branch])])
    first = trace_cycle(program, [], now_ms=10000)
    assert first["handled"] and first["state"].run_times[9] == 1
    second = trace_cycle(program, [], now_ms=17500, state=first["state"])
    assert not second["handled"]
    third = trace_cycle(program, [], now_ms=17501, state=second["state"])
    assert third["handled"] and third["state"].run_times[9] == 2
    with pytest.raises(UnsupportedHandler, match="read-only"):
        compose_handlers("cannot_assign_clock", [handler(1, [case("bad", actions=[{"set": {"handler_last_ms": 0}}])])])


@pytest.mark.parametrize("action", [{"set": {"elapsed_ms": 100}}, {"inc": "elapsed_ms"}])
def test_elapsed_ms_is_read_only(action):
    with pytest.raises(UnsupportedHandler, match="read-only"):
        compose_handlers("readonly", [handler(1, [case("bad", actions=[action])])])
    with pytest.raises(UnsupportedHandler, match="read-only"):
        compose_handlers("readonly_default", [handler(1, variables={"elapsed_ms": 1})])


@pytest.mark.parametrize("source", [
    "export class F {id=11; name=`${sideEffect()}`; operator: IFuncOperatorOrigin[]=[{}];}",
    r"export class F {id=11; name='\u0078'; operator: IFuncOperatorOrigin[]=[{}];}",
    "export class F {id=11 name='missing separator'; operator: IFuncOperatorOrigin[]=[{}];}",
])
def test_literal_initializers_cannot_hide_code_or_unimplemented_string_semantics(source):
    with pytest.raises(UnsupportedHandler):
        compile_literal(source)
