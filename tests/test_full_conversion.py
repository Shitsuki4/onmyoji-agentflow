"""Complete inventories and fail-closed source-to-workflow conversion."""
from pathlib import Path

import pytest

from helpers import FakeClock, blank, paint_points
from onmyoji_agentflow.convert.assttyys import convert_func, convert_schemes, scheme_definitions
from onmyoji_agentflow.convert.components import ComponentBuilder, known_component, UnsupportedComponent
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml


def test_real_scheme_declaration_excludes_examples_preserves_config(tmp_path):
    (tmp_path / "schemeList.ts").write_text("""
    const SchemeList: IScheme[] = [
      {schemeName: 'real', list: [1, 2], config: {'1': {exit: true}},
       commonConfig: {delay: 10 + 2 * 3}},
      // {schemeName: 'commented', list: [999]},
      /* {schemeName: 'block-commented', list: [998]}, */
    ];
    const defaults = {schemeName: 'not a declaration item', list: []};
    """, encoding="utf-8")
    assert convert_schemes(tmp_path) == {"real": [1, 2]}
    declaration, = scheme_definitions(tmp_path)
    assert declaration["config"] == {"1": {"exit": True}}
    assert declaration["commonConfig"] == {"delay": 16}


def test_duplicate_scheme_names_fail_closed(tmp_path):
    (tmp_path / "schemeList.ts").write_text(
        "const SchemeList: IScheme[] = [{schemeName: 'x', list: [1]},"
        "{schemeName: 'x', list: [2]}];", encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        scheme_definitions(tmp_path)


def test_func_resource_conversion_keeps_raw_anchors_and_config(tmp_path):
    path = tmp_path / "example.ts"
    path.write_text("""
    export class Func {
      id = 11; name = 'refresh';
      config = [{desc: '', config: [{name: 'once', default: false}]}];
      operator: IFuncOperatorOrigin[] = [{desc: 'page', retest: 1000, notForCnt: true,
        oper: [[2, 1280, 720, -1, -1, -1, -1, 3000]]}];
    }
    """, encoding="utf-8")
    doc = convert_func(path, {"page": {}})
    assert doc["config"][0]["config"][0]["default"] is False
    assert doc["raw_operators"][0]["oper"][0][:3] == [2, 1280, 720]
    assert doc["operators"][0]["not_for_count"] is True
    assert doc["operators"][0]["retest_ms"] == 1000


def retest_workflow():
    return load_workflow({"format": 1, "name": "retest", "states": [
        {"id": "first", "when": {"colors": [[10, 10, "#ff0000"]]},
         "do": [{"click": [100, 100, 110, 110]}]},
        {"id": "candidate", "when": {"colors": [[20, 20, "#00ff00"]]},
         "retest_ms": 1000, "do": [{"click": [200, 200, 210, 210]}]},
    ]})


def test_retest_uses_new_frame_and_preserves_priority():
    wf = retest_workflow()
    candidate, changed = blank(), blank()
    paint_points(candidate, [[20, 20, "#00ff00"]])
    paint_points(changed, [[10, 10, "#ff0000"]])
    device = ReplayDevice([candidate, changed])
    result = Runner(wf, Controller(device, sleep=lambda _: None), clock=FakeClock(),
                    max_actions=1).run()
    assert result.actions == 1 and result.history[0][1] == "first"
    assert (result.last_frame == changed).all()


def test_retest_disappeared_screen_and_cancellation_send_no_input():
    wf = retest_workflow()
    candidate = blank()
    paint_points(candidate, [[20, 20, "#00ff00"]])
    device = ReplayDevice([candidate, blank()])
    result = Runner(wf, Controller(device, sleep=lambda _: None), clock=FakeClock(step=1),
                    max_seconds=3).run()
    assert result.actions == 0 and not device.inputs
    stopped = [False]
    device = ReplayDevice([candidate])
    ctl = Controller(device, sleep=lambda _: stopped.__setitem__(0, True))
    result = Runner(wf, ctl, clock=FakeClock(step=0.1), should_stop=lambda: stopped[0]).run()
    assert result.status == "stopped" and not device.inputs


@pytest.mark.parametrize("value", [-1, True, "1000", float("inf"), 60001])
def test_retest_invalid_values_are_rejected(value):
    raw = retest_workflow().raw
    raw["states"][1]["retest_ms"] = value
    with pytest.raises(Exception, match="retest_ms"):
        load_workflow(raw)


def component(tmp_path, fid, operators, resources=None):
    import json
    root = tmp_path / "resources/upstream/assttyys"
    snapshot = root / "programs/src/src/common/funcList/demo.ts.txt"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(f"id = {fid}; name = 'demo'; operator: IFuncOperatorOrigin[] = " +
                        json.dumps(operators) + ";", encoding="utf-8")
    (root / "colors.yaml").write_text(dump_yaml({"resources": resources or {}}), encoding="utf-8")
    entry = {"id": f"assttyys:func:{fid:03d}", "source": "assttyys", "kind": "component",
             "title": "demo", "workflow": "demo", "entry_files": ["src/common/funcList/demo.ts"]}
    raw = ComponentBuilder(entry, tmp_path).build()
    return load_workflow(raw, [tmp_path / "resources"])


def test_component_friend_count_gate_and_wait_sentinel(tmp_path):
    operators = [{"desc": [1280, 720, [[1, i + 10, 20, 0xff0000]]],
                  **({"oper": [[1, 1280, 720, 100, 100, 110, 110, 500]]} if i == 0 else {})}
                 for i in range(4)]
    wf = component(tmp_path, 38, operators)
    team = blank()
    paint_points(team, [[10, 20, "#ff0000"]])
    empty = team.copy()
    paint_points(empty, [[11, 20, "#ff0000"]])
    dev = ReplayDevice([empty])
    result = Runner(wf, Controller(dev, sleep=lambda _: None), clock=FakeClock(), max_seconds=3).run()
    assert not dev.inputs and not result.business_ok
    assert result.business_result == "skipped" and result.evidence["component_handled"] is False
    dev = ReplayDevice([team])
    result = Runner(wf, Controller(dev, sleep=lambda _: None), clock=FakeClock(), max_actions=1).run()
    assert result.actions == 1
    assert ComponentBuilder.action({"rect": [-1, -1, -1, -1], "delay": 3000}) == {"wait": 3000}


def test_component_unknown_fields_and_unpinned_source_are_not_silently_dropped(tmp_path):
    assert known_component({"source": "assttyys", "kind": "component", "id": "assttyys:func:011",
                            "fingerprint": "changed"}, tmp_path) is None
    with pytest.raises(UnsupportedComponent, match="字段"):
        component(tmp_path, 11, [{"desc": "p", "unexpected": True}])
    with pytest.raises(UnsupportedComponent, match="设备哈希"):
        component(tmp_path / "device-choice", 11, [{"desc": [1280, 720, [[1, 10, 20, 0xff0000]]],
            "operStepRandom": [[[1, 1280, 720, 10, 10, 20, 20, 500], [1, 1280, 720, 30, 30, 40, 40, 500]]]}])


def test_component_global_defaults_and_counter_aliases_are_explicit(tmp_path):
    operators = [{"desc": [1280, 720, [[1, i + 10, 20, 0xff0000]]],
                  "oper": [[1, 1280, 720, 100, 100, 110, 110, 500]]} for i in range(17)]
    wf = component(tmp_path / "records", 509, operators)
    assert wf.raw["vars"]["change_shikigami_flag"] is True
    assert wf.raw["component_contract"]["requires_dispatcher"]
    assert not wf.raw["component_contract"]["standalone_equivalence"]
    wf = component(tmp_path / "team", 35, operators[:4])
    assert wf.raw["component_contract"]["counter_id"] == 38
