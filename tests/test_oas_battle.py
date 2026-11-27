"""Native family lowering/Runner tests; never import or execute OAS Python.

Portable unit tests separate the audited AST frontend from a synthetic literal
asset catalog. Optional source-conformance tests additionally inspect the actual
inert checkout (OAF_OAS_SOURCE_ROOT), including every reviewed AST fingerprint.
Only pytest temporary directories are written. There is no device/network I/O.
"""
from __future__ import annotations

import copy
import os
import random
from pathlib import Path

import cv2
import numpy as np
import pytest

from onmyoji_agentflow.convert import oas_battle as battle
from onmyoji_agentflow.device.base import Controller
from onmyoji_agentflow.device.humanize import HumanizeConfig
from onmyoji_agentflow.device.replay import ReplayDevice
from onmyoji_agentflow.workflow.engine import Runner
from onmyoji_agentflow.workflow.expr import evaluate
from onmyoji_agentflow.workflow.schema import load_workflow, validate
from onmyoji_agentflow.vision.ocr import FullOcrArea
from onmyoji_agentflow.yamlio import dump_yaml


MARKS = {
    "GREEN_LEFT1": "green_left1", "GREEN_LEFT2": "green_left2", "GREEN_LEFT3": "green_left3",
    "GREEN_LEFT4": "green_left4", "GREEN_LEFT5": "green_left5", "GREEN_MAIN": "green_main",
}
BUFFS = {name: (i + 1) * 10 for i, name in enumerate((
    "AWAKE", "SOUL", "GOLD_50", "GOLD_100", "EXP_50", "EXP_100",
    "AWAKE_CLOSE", "SOUL_CLOSE", "GOLD_50_CLOSE", "GOLD_100_CLOSE", "EXP_50_CLOSE", "EXP_100_CLOSE"))}
CONFIG = {
    "lock_team_enable": {"default": False}, "preset_enable": {"default": False},
    "preset_group": {"default": 1, "min": 1, "max": 7},
    "preset_team": {"default": 1, "min": 1, "max": 5},
    "green_enable": {"default": False},
    "green_mark": {"default": "green_left1", "choices": list(MARKS.values())},
    "green_mark_type": {"default": "choose", "choices": ["choose", "name"]},
    "green_mark_name": {"default": ""}, "random_click_swipt_enable": {"default": False},
}
IMAGE_NAMES = (
    "I_BATTLE_INFO", "I_DISABLE_7DAYS_DIFF_SOUL", "I_CONFIRM_CLOSE_DIFF_SOUL", "I_BUFF",
    "I_PREPARE_HIGHLIGHT", "I_PREPARE_DARK", "I_PRESET", "I_PRESET_WIT_NUMBER",
    "I_PRESET_ENSURE", "I_PRESENT_LESS_THAN_5", "I_FRIENDS", "I_WIN", "I_FALSE", "I_REWARD",
    "I_LOCAL", "I_DE_WIN", "I_REWARD_GOLD", "I_STATISTICS", "I_OVER_GHOST", "I_CLOUD",
    "I_AWAKE", "I_SOUL", "I_OPEN_YELLOW", "I_CLOSE_RED", "I_I_REJECT_1", "I_I_REJECT_2", "I_I_REJECT_3",
    "I_BATTLE_STATE_INFO",
)
SWIPE_NAMES = ("S_BATTLE_RANDOM_LEFT", "S_BATTLE_RANDOM_RIGHT")


class LiteralSources:
    """Unit-test input model, not a bypass accepted by the public compiler API."""
    def __init__(self):
        self.files = {"fixture": {"path": "fixture", "sha256": "a" * 64}}
        self.verified = False

    def verify(self):
        self.verified = True

    def check_owner(self, owner):
        assert owner is None

    def config(self):
        return copy.deepcopy(CONFIG)

    def enum(self, path, name):
        return copy.deepcopy(BUFFS if name == "BuffClass" else MARKS)

    def asset(self, path, cls, name):
        ref = {"path": path, "start_line": 1, "end_line": 1}
        if name == "C_PRESET_TEAM_5":
            raise battle._Missing(battle._issue("missing_resource", ref, "upstream asset declaration " + name))
        if name in IMAGE_NAMES:
            index = IMAGE_NAMES.index(name)
            box = (10 + index * 20, 20, 10, 10)
            if name in ("I_AWAKE", "I_SOUL"):
                box = (381, 180, 10, 20)
            if name in ("I_OPEN_YELLOW", "I_CLOSE_RED"):
                box = (780, 183, 10, 10)
            if name.startswith("I_I_REJECT_"):
                box = (5, 100 + int(name[-1]) * 110, 10, 10)
            filename = "gi_i_reject.png" if name.startswith("I_I_REJECT_") else name + ".png"
            search = (360, 100, 80, 400) if name in ("I_AWAKE", "I_SOUL") else box
            return "RuleImage", {"roi_front": box, "roi_back": search, "threshold": .8,
                                 "method": "Template matching", "file": filename}, ref
        if name in SWIPE_NAMES:
            start, end = ((600, 400, 50, 60), (900, 400, 50, 60))
            if name.endswith("RIGHT"):
                start, end = end, start
            return "RuleSwipe", {"roi_front": start, "roi_back": end, "mode": "default"}, ref
        if name.startswith("C_"):
            # Distinct fixtures for source ROI-back and click-front semantics.
            number = int(name[-1]) if name[-1].isdigit() else 6
            x = 100 + number * 30
            if name.startswith("C_REWARD"):
                x += 300
            return "RuleClick", {"roi_front": (x, 500, 15, 15), "roi_back": (x + 1, 501, 25, 50)}, ref
        if name in ("O_PRESET", "O_PRESET_FULL"):
            return "RuleOcr", {"roi": (20, 620, 60, 80), "keyword": "preset", "mode": "Single"}, ref
        if name in ("O_GOLD_50", "O_GOLD_100", "O_EXP_50", "O_EXP_100"):
            return "RuleOcr", {"roi": (400, 100, 400, 400), "keyword": name, "mode": "Full"}, ref
        raise AssertionError(name)


@pytest.fixture
def compiler_fixture(tmp_path, monkeypatch):
    sources = LiteralSources()
    folder = tmp_path / "resources/upstream/oas"
    folder.mkdir(parents=True)
    resources = {}
    patches, file_patches = {}, {}
    rng = np.random.default_rng(2601)
    clicks = ([f"C_WIN_{i}" for i in range(1, 4)] + [f"C_REWARD_{i}" for i in range(1, 4)] +
              [f"C_PRESET_GROUP_{i}" for i in range(1, 8)] + [f"C_PRESET_TEAM_{i}" for i in range(1, 5)] +
              [f"C_GREEN_LEFT_{i}" for i in range(1, 6)] + ["C_GREEN_MAIN", "C_RANDOM_CLICK"])
    for name in [*IMAGE_NAMES, *clicks, *SWIPE_NAMES, "O_PRESET", "O_PRESET_FULL",
                 "O_GOLD_50", "O_GOLD_100", "O_EXP_50", "O_EXP_100"]:
        kind, lit, _ = sources.asset(battle.ASSETS, "GeneralBattleAssets", name)
        if kind == "RuleImage":
            width, height = lit["roi_front"][2:]
            patch = file_patches.setdefault(lit["file"], rng.integers(0, 255, (height, width, 3), dtype=np.uint8))
            path = folder / lit["file"]
            assert cv2.imwrite(str(path), patch)
            patches[name] = patch
            spec = {"type": "image", "file": path.name, "roi": list(lit["roi_back"]),
                    "front": list(lit["roi_front"]), "threshold": .8,
                    "method": "Template matching", "roi_expand": 2}
        elif kind == "RuleClick":
            x, y, w, h = lit["roi_front"]
            spec = {"type": "click", "rect": [x, y, x + w, y + h]}
        elif kind == "RuleSwipe":
            def rect(box):
                x, y, w, h = box
                return [x, y, x + w, y + h]
            spec = {"type": "swipe", "from": rect(lit["roi_front"]), "to": rect(lit["roi_back"])}
        else:
            spec = {"type": "ocr", "roi": list(lit["roi"]), "keyword": lit["keyword"], "mode": lit["mode"]}
        resources[name] = spec
    for namespace in ("Component_GeneralBattle", "Component_GeneralBuff", "Component_GeneralInvite"):
        (folder / (namespace + ".yaml")).write_text(dump_yaml({"resources": resources}), encoding="utf-8")
    monkeypatch.setattr(battle, "_Sources", lambda root: sources)

    def compile(**kwargs):
        packet = battle.compile_general_battle(tmp_path / "inert", folder, **kwargs)
        path = tmp_path / "native.yaml"
        path.write_text(dump_yaml(packet["workflow"]), encoding="utf-8")
        workflow = load_workflow(path, [tmp_path / "resources"])
        assert sources.verified
        return packet, workflow

    def frame(*names):
        image = np.full((720, 1280, 3), 40, dtype=np.uint8)
        for name in names:
            x, y, w, h = resources[name]["front"]
            image[y:y+h, x:x+w] = patches[name]
        return image

    return compile, frame, resources, sources


class Clock:
    def __init__(self):
        self.ms = 0

    def __call__(self):
        return self.ms / 1000

    def sleep(self, seconds):
        self.ms += seconds * 1000


class Scenario(ReplayDevice):
    """Inert synthetic GUI; real Runner recognition, rechecks and input dispatch."""
    def __init__(self, frame, clock, choose):
        super().__init__([frame()])
        self.frame, self.clock, self.choose = frame, clock, choose
        self.runner = None
        self.taps_by_phase = {}
        self.swipes_by_phase = {}
        self.input_times = []
        self.snapshots = []

    def screenshot(self):
        self.clock.ms += 100  # Model capture latency, including input rechecks.
        variables = self.runner.vars if self.runner else {}
        phase = variables.get("gb_phase", "entry")
        self.snapshots.append((phase, dict(variables), self.clock.ms))
        chosen = self.choose(phase, variables, self)
        return chosen.copy() if isinstance(chosen, np.ndarray) else self.frame(*chosen)

    def tap(self, x, y, press_ms=40):
        self.inputs.append(("tap", x, y))
        phase = self.runner.vars["gb_phase"]
        self.taps_by_phase[phase] = self.taps_by_phase.get(phase, 0) + 1
        self.input_times.append((phase, "tap", self.clock.ms))

    def swipe(self, p1, p2, duration_ms=400):
        self.inputs.append(("swipe", tuple(p1), tuple(p2)))
        phase = self.runner.vars["gb_phase"]
        self.swipes_by_phase[phase] = self.swipes_by_phase.get(phase, 0) + 1
        self.input_times.append((phase, "swipe", self.clock.ms))


def run(workflow, frame, choose, *, params=None, initial_vars=None, max_seconds=30, max_actions=None,
         single_ocr_reader=None, full_ocr_reader=None, should_stop=None, before_input=None):
    clock, events = Clock(), []
    device = Scenario(frame, clock, choose)
    def full_reader(*args):
        # A synthetic area in these scenarios represents complete keyword evidence.
        # Tests of partial OCR supply the provenance-bearing result explicitly.
        area = full_ocr_reader(*args)
        return area if isinstance(area, FullOcrArea) else FullOcrArea(area, keyword_complete=True)
    controller = Controller(device, HumanizeConfig(base_sleep_ms=0, random_sleep_ms=0), sleep=clock.sleep)
    runner = Runner(workflow, controller, params=params, clock=clock, initial_vars=initial_vars,
                    max_seconds=max_seconds, max_actions=max_actions, single_ocr_reader=single_ocr_reader,
                    full_ocr_reader=full_reader if full_ocr_reader else None, should_stop=should_stop, before_input=before_input,
                    on_event=lambda kind, event: events.append((kind, event)))
    device.runner = runner
    return runner.run(), device, clock, events


def normal(marker="I_WIN", *, reward=True, ghost=False):
    def choose(phase, variables, device):
        taps = device.taps_by_phase.get(phase, 0)
        if phase == "prepare":
            return ["I_BATTLE_INFO"] if taps else ["I_PREPARE_HIGHLIGHT"]
        if phase == "battle_wait":
            return [marker]
        if phase == "de_win":
            return [] if taps else ["I_DE_WIN"]
        if phase == "result_win":
            return ["I_WIN"] if marker == "I_WIN" and not taps else []
        if phase == "result_loss":
            return ["I_FALSE"] if not taps else []
        if phase == "reward_wait":
            return ["I_REWARD"] if reward else []
        if phase == "reward_collect":
            if ghost and not taps:
                return ["I_OVER_GHOST"]
            return ["I_REWARD_GOLD"] if taps < (2 if ghost else 1) else []
        return ["I_BATTLE_INFO"]
    return choose


@pytest.fixture
def native_draws(monkeypatch):
    """Control only the new native ranges; preserve controller humanization."""
    original, original_uniform = random.randint, random.uniform
    calls = []
    def fixed(*, trigger=4, kind=0, prep_wait=400):
        choices = {(0, 500): trigger, (0, 2): kind}
        def draw(lo, hi):
            bounds = (lo, hi)
            if bounds in choices:
                choice = choices[bounds]
                result = choice.pop(0) if isinstance(choice, list) else choice
                assert lo <= result <= hi
                calls.append((bounds, result))
                return result
            return original(lo, hi)
        monkeypatch.setattr(random, "randint", draw)
        def uniform(lo, hi):
            if (lo, hi) == (400, 800):
                assert lo <= prep_wait <= hi
                calls.append(((lo, hi), prep_wait))
                return prep_wait
            return original_uniform(lo, hi)
        monkeypatch.setattr(random, "uniform", uniform)
        return calls
    return fixed


def test_all_config_domains_and_unresolved_branches_survive_defaults(compiler_fixture):
    compile, _, _, _ = compiler_fixture
    packet, workflow = compile()
    assert workflow.raw["params"] == CONFIG
    assert not packet["complete"] and not packet["original_task_complete"]
    kinds = {o["kind"] for o in packet["source_obligations"]}
    assert {"missing_resource", "positive_evidence_required"} <= kinds
    assert "missing_primitive" not in kinds
    states = {s["id"] for s in workflow.states}
    assert {f"gb_preset_group_{i}" for i in range(1, 8)} <= states
    assert {f"gb_preset_team_{i}" for i in range(1, 6)} <= states
    missing_team = next(o for o in packet["source_obligations"] if "TEAM_5" in o["requirement"])
    assert missing_team["kind"] == "missing_resource"
    assert missing_team["call_site"]["start_line"] == 473
    assert workflow.raw["oas_battle_contract"]["source_behavior"]["preparation_return_ignored"]
    assert "coordinate helper" in workflow.raw["oas_battle_contract"]["source_behavior"]["green_mark_type_and_name"]


def test_concrete_win_flow_counts_before_setup_and_receipts_are_visual(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    result, device, _, events = run(workflow, frame, normal(ghost=True))
    assert result.status == "success", result.summary()
    assert result.business_result == "unknown"  # A helper return is not a task.
    assert result.variables["gb_returned"] and result.variables["gb_return"] is True
    assert result.variables["gb_current_count"] == 1
    assert all(v["gb_current_count"] == 1 for p, v, _ in device.snapshots if p != "entry")
    assert device.taps_by_phase["prepare"] == 1
    assert device.taps_by_phase["result_win"] == 1
    assert device.taps_by_phase["reward_collect"] == 2
    receipts = [e for k, e in events if k == "receipt"]
    assert len(receipts) == 1 and receipts[0]["outcome"] == "win"
    assert receipts[0]["source_marker"].endswith("I_WIN")
    assert receipts[0]["vars"]["gb_current_count"] == 1
    assert np.array_equal(receipts[0]["frame"], frame("I_WIN"))


def test_parent_task_can_reenter_the_family_without_stale_result_or_mark_flags(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile()
    terminal = next(s for s in workflow.states if s["id"] == "gb_returned_true")
    first_join = copy.deepcopy(terminal)
    first_join["id"] = "gb_first_call_join"
    first_join["when"]["all"].append({"expr": "gb_current_count == 1"})
    first_join["do"][-1] = {"set": {"gb_phase": "'entry'"}}
    workflow.states.insert(workflow.states.index(terminal), first_join)
    result, device, _, events = run(workflow, frame, normal(), params={"green_enable": True})
    assert result.status == "success", result.summary()
    assert result.variables["gb_current_count"] == 2
    assert device.taps_by_phase["green_coordinate"] == 2
    second_start = next(values for phase, values, _ in device.snapshots
                        if phase == "prepare" and values["gb_current_count"] == 2)
    assert not second_start["gb_returned"] and not second_start["gb_outcome_known"]
    assert second_start["gb_mark_attempted"] == 0
    assert second_start["gb_last_i_prepare_highlight"] >= 0
    assert result.variables["gb_last_i_prepare_highlight"] == second_start["gb_last_i_prepare_highlight"]
    receipts = [event for kind, event in events if kind == "receipt"]
    assert [event["vars"]["gb_current_count"] for event in receipts] == [1, 2]
    shared = packet["workflow"]["oas_battle_contract"]["composition"]["interval_vars"]
    assert {"gb_last_c_random_click", "gb_last_s_battle_random_left", "gb_last_s_battle_random_right"} <= set(shared)


@pytest.mark.parametrize("marker,expected", [("I_WIN", True), ("I_FALSE", False),
    ("I_REWARD", True), ("I_REWARD_GOLD", True), ("I_DE_WIN", True)])
def test_all_result_paths_use_source_boolean(compiler_fixture, marker, expected):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(current_count=6)
    result, device, _, events = run(workflow, frame, normal(marker, reward=expected))
    assert result.status == "success", result.summary()
    assert result.variables["gb_return"] is expected
    assert result.variables["gb_current_count"] == 7
    assert result.variables["gb_outcome_known"]
    assert len([e for k, e in events if k == "receipt"]) == 1
    if marker == "I_DE_WIN":
        assert device.taps_by_phase["de_win"] == 1
    if not expected:
        assert not any(p.startswith("reward") for p, _, _ in device.snapshots)


def test_source_result_priority_de_and_win_precede_loss(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal("I_DE_WIN")
    result, _, _, events = run(workflow, frame,
        lambda p, v, d: ["I_DE_WIN", "I_WIN", "I_FALSE", "I_REWARD"] if p == "battle_wait" else base(p, v, d))
    assert result.variables["gb_return"] is True
    assert next(e for k, e in events if k == "receipt")["source_marker"].endswith("I_DE_WIN")


def test_reward_disappearing_during_recheck_returns_without_extra_click(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()
    captures = 0

    def choose(phase, variables, device):
        nonlocal captures
        if phase == "reward_collect":
            captures += 1
            return ["I_REWARD_GOLD"] if captures == 1 else []
        return base(phase, variables, device)

    result, device, _, _ = run(workflow, frame, choose)
    assert result.status == "success", result.summary()
    assert result.variables["gb_return"] is True
    assert not device.taps_by_phase.get("reward_collect")
    assert result.variables["gb_last_i_reward_gold"] == -1000000000


def test_defeat_disappearing_during_recheck_preserves_observed_loss(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()
    captures = 0

    def choose(phase, variables, device):
        nonlocal captures
        if phase == "battle_wait":
            return ["I_FALSE"]
        if phase == "result_loss":
            captures += 1
            return ["I_FALSE"] if captures == 1 else []
        return base(phase, variables, device)

    result, device, _, _ = run(workflow, frame, choose)
    assert result.status == "success", result.summary()
    assert result.variables["gb_return"] is False and result.variables["gb_outcome_known"]
    assert not device.taps_by_phase.get("result_loss")


def test_no_result_timeout_or_count_never_fabricates_a_receipt(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(current_count=19)
    result, device, _, events = run(workflow, frame, lambda p, v, d: ["I_BATTLE_INFO"], max_seconds=2)
    assert result.status == "limit"
    assert result.variables["gb_current_count"] == 20
    assert not result.variables["gb_outcome_known"] and not result.variables["gb_returned"]
    assert not [e for k, e in events if k == "receipt"]
    assert not device.inputs


def test_loss_thresholds_and_positive_image_click_guards(compiler_fixture):
    compile, _, _, _ = compiler_fixture
    _, workflow = compile()
    by_id = {s["id"]: s for s in workflow.states}
    assert by_id["gb_observe_loss"]["when"]["all"][-1]["threshold"] == .8
    assert by_id["gb_result_loss_click_i_false"]["when"]["all"][-1]["threshold"] == .6
    assert by_id["gb_observe_reward"]["when"]["all"][-1]["threshold"] == .6

    def positive(c):
        if "res" in c or "mean_color" in c or "ocr_single" in c:
            return True
        return any(positive(child) for key in ("all", "any") for child in c.get(key, []))
    for st in workflow.states:
        inputs = [a for a in st["do"] if set(a) & {"click", "click_found", "click_random", "swipe"}]
        assert len(inputs) <= 1
        for action in inputs:
            assert positive(st["when"]) and action["recheck"] is True
            if "click_found" in action:
                assert action["use_match_size"] is True


def test_preparation_five_seconds_does_not_mean_success_or_cut_nested_preset(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    result, device, _, events = run(workflow, frame,
        lambda p, v, d: ["I_PREPARE_DARK"] if p == "prepare" else [],
        params={"lock_team_enable": True}, max_seconds=7)
    assert result.status == "limit"
    assert not result.variables["gb_prep_return"]
    assert result.variables["gb_phase"] == "battle_wait"
    assert not device.inputs and not [e for k, e in events if k == "receipt"]
    timeouts = [s for s in workflow.states if s["id"] == "gb_prepare_timeout"]
    assert len(timeouts) == 1
    condition = timeouts[0]["when"]["all"][0]["expr"]
    assert evaluate(condition, {"gb_phase": "preset_open"}) is False


def test_first_attempt_setup_only_and_existing_count_binding(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(current_count=1)
    result, device, _, _ = run(workflow, frame, normal(), params={"preset_enable": True})
    assert result.status == "success"
    assert result.variables["gb_current_count"] == 2
    assert not any(p.startswith("preset") for p, _, _ in device.snapshots)


def test_enabled_preset_reaches_explicit_missing_team_five_after_group_selection(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile()
    def choose(phase, variables, device):
        if phase == "preset_open":
            return ["I_PRESET_ENSURE"]
        return ["I_PREPARE_HIGHLIGHT"]
    result, device, _, events = run(workflow, frame, choose, params={"preset_enable": True, "preset_group": 7, "preset_team": 5})
    assert result.status == "failed" and result.failed_state == "gb_preset_team_5"
    assert not result.variables["gb_confed"]
    assert not device.inputs and not [e for k, e in events if k == "receipt"]
    group = next(s for s in workflow.states if s["id"] == "gb_preset_group_7")
    assert group["when"]["all"][-1]["mean_color"]["region"][2:] == [25, 50]
    assert group["when"]["all"][-1]["mean_color"]["rgb"] == [224.9, 208.3, 187.4]
    assert group["when"]["all"][-1]["mean_color"]["tolerance"] == 10
    missing = next(o for o in packet["source_obligations"] if o["kind"] == "missing_resource")
    assert "preset_team == 5" in missing["branch"]


def preset_scene(workflow, frame, group, team, opener):
    """Synthetic preset colour transitions driven only by native device inputs."""
    by_id = {s["id"]: s for s in workflow.states}
    group_mean = by_id[f"gb_preset_group_{group}"]["when"]["all"][-1]["mean_color"]
    team_mean = by_id[f"gb_preset_team_{team}"]["when"]["all"][-1]["mean_color"]
    base = normal()
    def scene(p, v, d):
        taps = d.taps_by_phase.get(p, 0)
        if p == "preset_open":
            return [opener] if not taps else ["I_PRESET_ENSURE"]
        if p in ("preset_group", "preset_team"):
            spec = group_mean if p == "preset_group" else team_mean
            image = frame("I_PRESET_ENSURE")
            x, y, w, h = spec["region"]
            rgb = [int(value) for value in spec["rgb"]] if not taps else [10, 20, 30]
            image[y:y+h, x:x+w] = rgb[::-1]
            return image
        if p in ("preset_team_commit", "preset_ensure_wait", "preset_ensure_check", "preset_ensure_scan"):
            return ["I_PRESET_ENSURE"] if not d.taps_by_phase.get("preset_ensure_scan", 0) else []
        if p == "prepare_after_setup":
            return ["I_PREPARE_HIGHLIGHT"]
        if p == "prepare" and v.get("gb_confed"):
            return ["I_BATTLE_INFO"]
        return base(p, v, d)
    return scene


@pytest.mark.parametrize("group,team", [(i, (i - 1) % 4 + 1) for i in range(1, 8)])
def test_all_preset_groups_and_existing_teams_have_real_mean_loops(compiler_fixture, group, team):
    compile, frame, resources, _ = compiler_fixture
    packet, workflow = compile()
    by_id = {state["id"]: state for state in workflow.states}
    for category, number, size in (("GROUP", group, [25, 50]), ("TEAM", team, [5, 5])):
        rect = resources[f"C_PRESET_{category}_{number}"]["rect"]
        condition = by_id[f"gb_preset_{category.lower()}_{number}"]["when"]["all"][-1]
        assert condition["mean_color"]["region"] == [rect[0] + 1, rect[1] + 1, *size]
    result, device, _, events = run(workflow, frame,
        preset_scene(workflow, frame, group, team, "I_PRESET" if group % 2 else "I_PRESET_WIT_NUMBER"),
        params={"preset_enable": True, "preset_group": group, "preset_team": team})
    assert result.status == "success", result.summary()
    assert result.variables["gb_return"] is True
    assert device.taps_by_phase["preset_open"] == 1
    assert device.taps_by_phase["preset_group"] == 1
    assert device.taps_by_phase["preset_team"] == 1
    assert device.taps_by_phase["preset_team_commit"] == 1  # Extra source click after the colour loop.
    assert result.variables["gb_preset_team_committed"] == 1
    assert device.taps_by_phase["preset_ensure_scan"] == 1
    assert device.taps_by_phase["prepare_after_setup"] == 1
    points = device.snapshots
    last_group = max(i for i, (p, _, _) in enumerate(points) if p == "preset_group")
    assert points[last_group + 1][0] == "preset_team"
    assert points[last_group + 1][2] - points[last_group][2] == pytest.approx(600)  # 500ms + capture.
    assert len([event for kind, event in events if kind == "receipt"]) == 1
    assert not packet["complete"]
    assert not any(o["kind"] == "missing_primitive" for o in packet["source_obligations"])


def test_preset_single_ocr_absence_waits_without_fabricating_a_match_or_input(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile()
    result, device, _, _ = run(workflow, frame, lambda p, v, d: ["I_PREPARE_HIGHLIGHT"],
                               params={"preset_enable": True}, max_seconds=2,
                               single_ocr_reader=lambda *_: "")
    assert result.status == "limit"
    assert not device.inputs
    assert not any("Single-OCR" in o["requirement"] for o in packet["source_obligations"])


def test_preset_single_ocr_fallback_clicks_the_resource_roi_after_exact_line_evidence(compiler_fixture):
    compile, frame, resources, _ = compiler_fixture
    packet, workflow = compile()
    result, device, _, _ = run(workflow, frame, lambda p, v, d: ["I_PREPARE_HIGHLIGHT"],
        initial_vars={"gb_phase": "preset_open"}, params={"preset_enable": True}, max_actions=1,
        single_ocr_reader=lambda *_: "preset")
    assert result.status == "limit" and len(device.inputs) == 1
    _, x, y = device.inputs[0]
    rx, ry, width, height = resources["O_PRESET"]["roi"]
    assert rx <= x <= rx + width and ry <= y <= ry + height
    assert device.input_times[0][0] == "preset_open"
    assert packet["workflow"]["oas_battle_contract"]["source_behavior"]["preset"]["single_ocr"]["interval_ms"] == 1000


def test_preset_single_ocr_interval_suppression_continues_before_the_second_arm(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    result, device, _, _ = run(workflow, frame, lambda p, v, d: ["I_PREPARE_HIGHLIGHT"],
        initial_vars={"gb_phase": "preset_open", "gb_last_o_preset": 0},
        params={"preset_enable": True}, max_seconds=.8, single_ocr_reader=lambda *_: "preset")
    assert result.status == "limit" and not device.inputs
    assert any(state == "gb_preset_ocr_o_preset_cooldown" for _, state in result.history)


def test_preset_negative_mean_needs_positive_ui_for_the_unconditional_commit(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile()
    result, device, _, _ = run(workflow, frame, lambda p, v, d: [],
        initial_vars={"gb_phase": "preset_team_commit", "gb_current_count": 1}, params={"preset_enable": True})
    assert result.status == "failed" and result.failed_state == "gb_preset_commit_positive_evidence_blocked"
    assert not device.inputs and not result.variables["gb_preset_team_committed"]
    assert any("unconditional team click is strengthened" in note
               for note in packet["workflow"]["oas_battle_contract"]["native_adaptations"])


def test_source_less_than_five_marker_still_selects_and_does_not_mean_skip(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile()
    base = preset_scene(workflow, frame, 1, 1, "I_PRESENT_LESS_THAN_5")
    def scene(p, v, d):
        chosen = base(p, v, d)
        if p in ("preset_team_commit", "preset_ensure_wait", "preset_ensure_check", "preset_ensure_scan"):
            return ["I_PRESENT_LESS_THAN_5"]
        return chosen
    result, device, _, events = run(workflow, frame, scene, params={"preset_enable": True})
    assert result.status == "success", result.summary()
    assert "preset_open" not in device.taps_by_phase
    assert device.taps_by_phase["preset_group"] == 1
    assert device.taps_by_phase["preset_team"] == 1 and device.taps_by_phase["preset_team_commit"] == 1
    assert "preset_ensure_scan" not in device.taps_by_phase
    assert len([event for kind, event in events if kind == "receipt"]) == 1
    behavior = packet["workflow"]["oas_battle_contract"]["source_behavior"]["preset"]
    assert "never a skip or success" in behavior["less_than_five_marker"]


def test_mean_color_recheck_cannot_send_a_stale_group_click(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    spec = next(s for s in workflow.states if s["id"] == "gb_preset_group_1")["when"]["all"][-1]["mean_color"]
    seen = 0
    def scene(p, v, d):
        nonlocal seen
        image = frame("I_PRESET_ENSURE")
        if p == "preset_group":
            seen += 1
            x, y, w, h = spec["region"]
            image[y:y+h, x:x+w] = [187, 208, 224] if seen == 1 else [10, 20, 30]
        return image
    result, device, _, _ = run(workflow, frame, scene,
        initial_vars={"gb_phase": "preset_group", "gb_current_count": 1}, params={"preset_enable": True})
    assert result.status == "failed" and result.failure_kind == "recognition"
    assert not device.inputs


def test_negated_bad_mean_crop_cannot_become_a_selection_or_input(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    selected = next(s for s in workflow.states if s["id"] == "gb_preset_group_1_selected")
    selected["when"]["all"][-1]["not"]["mean_color"]["region"] = [1279, 700, 25, 50]
    result, device, _, events = run(workflow, frame, lambda p, v, d: ["I_PRESET_ENSURE"],
        initial_vars={"gb_phase": "preset_group", "gb_current_count": 1}, params={"preset_enable": True})
    assert result.status == "failed"
    assert result.variables["gb_phase"] == "preset_group"
    assert not device.inputs and not [event for kind, event in events if kind == "receipt"]


def test_preset_ensure_timer_warns_repeatedly_without_exiting_or_claiming_completion(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    result, device, _, events = run(workflow, frame, lambda p, v, d: ["I_PRESET_ENSURE"],
        initial_vars={"gb_phase": "preset_ensure_check", "gb_current_count": 1}, max_seconds=12.5)
    assert result.status == "limit", result.summary()
    assert result.variables["gb_phase"] in ("preset_ensure_check", "preset_ensure_scan")
    warnings = [event for kind, event in events if kind == "log" and event["message"] == "Switch preset failure"]
    assert len(warnings) >= 2
    assert any(ms > 10000 for phase, _, ms in device.input_times if phase == "preset_ensure_scan")
    assert not result.variables["gb_returned"] and not result.variables["gb_confed"]
    assert not [event for kind, event in events if kind == "receipt"]


def test_preset_ensure_wait_times_out_after_one_second_then_continues(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    result, device, _, _ = run(workflow, frame, normal(),
        initial_vars={"gb_phase": "preset_ensure_wait", "gb_current_count": 1})
    assert result.status == "success", result.summary()
    assert result.variables["gb_preset_warn_started_ms"] > 1000
    assert "preset_ensure_scan" not in device.taps_by_phase


def test_nested_preset_setup_may_exceed_five_seconds_before_its_final_ready_attempt(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = preset_scene(workflow, frame, 1, 1, "I_PRESET")
    def slow_group(p, v, d):
        if p == "preset_group" and d.clock.ms < 6000:
            image = frame("I_PRESET_ENSURE")
            spec = next(s for s in workflow.states if s["id"] == "gb_preset_group_1")["when"]["all"][-1]["mean_color"]
            x, y, w, h = spec["region"]
            image[y:y+h, x:x+w] = [187, 208, 224]
            return image
        return base(p, v, d)
    result, device, _, _ = run(workflow, frame, slow_group, params={"preset_enable": True})
    assert result.status == "success", result.summary()
    ready = [ms for p, _, ms in device.input_times if p == "prepare_after_setup"]
    assert ready and ready[0] > 5000
    assert result.variables["gb_confed"] and not result.variables["gb_prep_return"]


def test_random_disabled_never_samples_and_remaining_gaps_are_independent(compiler_fixture, native_draws):
    compile, frame, _, _ = compiler_fixture
    calls = native_draws(trigger=0)
    packet, workflow = compile()
    result, device, _, events = run(workflow, frame, lambda p, v, d: ["I_BATTLE_INFO"], max_seconds=2)
    assert result.status == "limit"
    assert not device.inputs and not [e for k, e in events if k == "receipt"]
    assert not calls
    assert not any(o["kind"] == "missing_primitive" and o["source"]["start_line"] in (77, 508)
                   for o in packet["source_obligations"])
    assert not packet["complete"]  # Preset/source-defect and caller obligations remain.


def test_random_gate_has_exactly_four_of_501_outcomes(compiler_fixture):
    compile, _, _, _ = compiler_fixture
    _, workflow = compile()
    state = next(s for s in workflow.states if s["id"] == "gb_idle_sample_kind")
    predicate = state["when"]["all"][1]["expr"]
    assert [value for value in range(501) if evaluate(predicate,
        {"gb_idle_trigger": value})] == [0, 1, 2, 3]
    sample = next(s for s in workflow.states if s["id"] == "gb_idle_sample_trigger")["do"][0]
    assert sample == {"sample_int": {"var": "gb_idle_trigger", "min": 0, "max": 500}}


@pytest.mark.parametrize("trigger,kind", [(0, 0), (1, 1), (2, 2), (3, 0)])
def test_random_trigger_boundaries_and_all_three_inputs(compiler_fixture, native_draws, trigger, kind):
    compile, frame, resources, _ = compiler_fixture
    calls = native_draws(trigger=trigger, kind=kind)
    _, workflow = compile()
    base = normal()
    def choose(p, v, d):
        if p == "battle_wait" and not d.input_times:
            return ["I_BATTLE_INFO"]
        if p == "battle_idle_input":
            return ["I_BATTLE_INFO"]
        return base(p, v, d)
    result, device, _, events = run(workflow, frame, choose,
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1},
        params={"random_click_swipt_enable": True})
    assert result.status == "success", result.summary()
    assert calls == [((0, 500), trigger), ((0, 2), kind)]
    idle = [e for e in device.input_times if e[0] == "battle_idle_input"]
    assert len(idle) == 1 and idle[0][1] == ("tap" if kind == 0 else "swipe")
    if kind == 0:
        _, x, y = device.inputs[0]
        x1, y1, x2, y2 = resources["C_RANDOM_CLICK"]["rect"]
        assert x1 <= x <= x2 and y1 <= y <= y2
    else:
        _, start, end = device.inputs[0]
        spec = resources[SWIPE_NAMES[kind - 1]]
        for point, rect in ((start, spec["from"]), (end, spec["to"])):
            assert rect[0] <= point[0] <= rect[2] and rect[1] <= point[1] <= rect[3]
    assert result.variables["gb_return"] is True
    assert len([e for k, e in events if k == "receipt"]) == 1


@pytest.mark.parametrize("trigger", [4, 500])
def test_random_non_trigger_waits_400ms_without_sampling_kind(compiler_fixture, native_draws, trigger):
    compile, frame, _, _ = compiler_fixture
    calls = native_draws(trigger=trigger)
    _, workflow = compile()
    base = normal()
    def choose(p, v, d):
        if p == "battle_wait" and not calls:
            return ["I_BATTLE_INFO"]
        return base(p, v, d)
    result, device, _, _ = run(workflow, frame, choose,
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1}, params={"random_click_swipt_enable": True})
    assert result.status == "success", result.summary()
    assert calls == [((0, 500), trigger)]
    assert not [e for e in device.input_times if e[0] == "battle_idle_input"]
    points = device.snapshots
    decision_index = next(i for i, (p, _, _) in enumerate(points) if p == "battle_idle_decide")
    assert points[decision_index + 1][2] - points[decision_index][2] == 500  # 400ms wait + capture.


@pytest.mark.parametrize("kind,name", [(0, "c_random_click"), (1, "s_battle_random_left"), (2, "s_battle_random_right")])
def test_random_target_cooldowns_are_strict_and_independent(compiler_fixture, native_draws, kind, name):
    compile, frame, _, _ = compiler_fixture
    native_draws(trigger=0, kind=kind)
    _, workflow = compile()
    selected = next(s for s in workflow.states if s["id"] == "gb_idle_" + name)
    due = selected["when"]["all"][1]["expr"]
    env = {"gb_idle_kind": kind, "elapsed_ms": 20000, "gb_last_" + name: 0}
    assert not evaluate(due, env)
    assert evaluate(due, {**env, "elapsed_ms": 20001})
    result, device, _, events = run(workflow, frame, lambda p, v, d: ["I_BATTLE_INFO"],
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1},
        params={"random_click_swipt_enable": True}, max_seconds=22)
    assert result.status == "limit", result.summary()
    idle = [e for e in device.input_times if e[0] == "battle_idle_input"]
    assert len(idle) == 2
    assert idle[1][2] - idle[0][2] > 20000
    assert not [e for k, e in events if k == "receipt"]
    for other in ("c_random_click", "s_battle_random_left", "s_battle_random_right"):
        if other != name:
            assert result.variables["gb_last_" + other] == -1000000000


def test_distinct_idle_targets_are_not_suppressed_by_a_shared_timer(compiler_fixture, native_draws):
    compile, frame, _, _ = compiler_fixture
    calls = native_draws(trigger=0, kind=[0, 1, 2])
    _, workflow = compile()
    base = normal()
    def choose(p, v, d):
        idle_count = sum(phase == "battle_idle_input" for phase, _, _ in d.input_times)
        if p in ("battle_wait", "battle_idle_input") and idle_count < 3:
            return ["I_BATTLE_INFO"]
        return base(p, v, d)
    result, device, _, _ = run(workflow, frame, choose,
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1}, params={"random_click_swipt_enable": True})
    assert result.status == "success", result.summary()
    idle = [e for e in device.input_times if e[0] == "battle_idle_input"]
    assert [kind for _, kind, _ in idle] == ["tap", "swipe", "swipe"]
    assert idle[-1][2] - idle[0][2] < 20000
    assert calls == [((0, 500), 0), ((0, 2), 0), ((0, 500), 0), ((0, 2), 1), ((0, 500), 0), ((0, 2), 2)]
    for target in ("c_random_click", "s_battle_random_left", "s_battle_random_right"):
        assert result.variables["gb_last_" + target] >= 0


def test_native_sampling_and_non_trigger_wait_are_not_device_inputs(compiler_fixture, native_draws):
    compile, frame, _, _ = compiler_fixture
    calls = native_draws(trigger=500)
    _, workflow = compile()
    result, device, _, events = run(workflow, frame, lambda p, v, d: ["I_BATTLE_INFO"],
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1},
        params={"random_click_swipt_enable": True}, max_seconds=2)
    assert result.status == "limit" and calls
    assert result.variables["actions"] == 0 and not device.inputs
    assert not result.variables["gb_outcome_known"] and not result.variables["gb_returned"]
    assert not [event for kind, event in events if kind == "receipt"]


@pytest.mark.parametrize("mark", list(MARKS.values()))
def test_all_six_coordinate_green_marks_and_source_ignored_name_mode(compiler_fixture, mark):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()
    def choose(p, v, d):
        if p == "green_local":
            return ["I_BATTLE_INFO", "I_LOCAL"]
        return base(p, v, d)
    result, device, clock, _ = run(workflow, frame, choose, params={"green_enable": True,
        "green_mark": mark, "green_mark_type": "name", "green_mark_name": "ignored upstream"})
    assert result.status == "success", result.summary()
    assert device.taps_by_phase["green_local"] == 1
    assert device.taps_by_phase["green_coordinate"] == 1
    assert result.variables["gb_mark_attempted"] == 1
    assert clock.ms >= 300


def test_green_absence_cannot_authorize_coordinate_input(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()
    result, device, _, _ = run(workflow, frame,
        lambda p, v, d: [] if p == "green_coordinate" else base(p, v, d), params={"green_enable": True})
    assert result.status == "failed" and result.failed_state == "gb_green_positive_evidence_blocked"
    assert "green_coordinate" not in device.taps_by_phase


@pytest.mark.parametrize("late_ui", ["I_WIN", "I_REWARD", "I_BATTLE_STATE_INFO"])
def test_green_mark_cannot_reach_settlement_controls(compiler_fixture, late_ui):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()

    def choose(phase, variables, device):
        if phase == "green_coordinate":
            return ["I_BATTLE_INFO", late_ui]
        return base(phase, variables, device)

    result, device, _, _ = run(workflow, frame, choose, params={"green_enable": True})
    assert result.status == "success" and result.variables["gb_return"] is True
    assert not device.taps_by_phase.get("green_coordinate")


def test_green_fresh_recheck_refuses_stale_input_when_result_arrives(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()
    visuals = iter((["I_BATTLE_INFO"], ["I_WIN"]))

    def choose(phase, variables, device):
        if phase == "green_coordinate":
            return next(visuals, ["I_WIN"])
        return base(phase, variables, device)

    result, device, _, _ = run(workflow, frame, choose, params={"green_enable": True})
    assert result.status == "failed" and result.failure_kind == "recognition"
    assert not device.taps_by_phase.get("green_coordinate")


def test_win_title_disappearing_on_recheck_skips_title_tap_and_collects_reward(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()
    seen = 0
    def choose(p, v, d):
        nonlocal seen
        if p == "result_win":
            seen += 1
            return ["I_WIN"] if seen == 1 else ["I_REWARD"]
        return base(p, v, d)
    result, device, _, _ = run(workflow, frame, choose)
    assert result.status == "success" and result.variables["gb_return"] is True
    assert "result_win" not in device.taps_by_phase
    assert device.taps_by_phase["reward_collect"] == 1


def test_action_budget_does_not_become_boolean_completion(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    result, _, _, events = run(workflow, frame, normal(), max_actions=1)
    assert result.status == "limit"
    assert result.variables["gb_current_count"] == 1
    assert not result.variables["gb_returned"]
    assert not [e for k, e in events if k == "receipt"]


@pytest.mark.parametrize("broken", ["resources: [", "[one, two]", "resources: 4"])
def test_malformed_resource_document_is_a_typed_native_failure(compiler_fixture, broken, tmp_path):
    compile, _, _, _ = compiler_fixture
    (tmp_path / "resources/upstream/oas/Component_GeneralBattle.yaml").write_text(broken, encoding="utf-8")
    packet, workflow = compile()
    assert not packet["guarded_executable"] and not packet["complete"]
    assert packet["source_obligations"][-1]["kind"] == "missing_resource"
    assert len(workflow.states) == 1 and "fail" in workflow.states[0]["do"][0]


def test_converted_roi_drift_cannot_silently_keep_old_semantics(compiler_fixture, tmp_path):
    compile, _, resources, _ = compiler_fixture
    changed = copy.deepcopy(resources)
    changed["I_BATTLE_INFO"]["roi"] = [1, 2, 3, 4]
    (tmp_path / "resources/upstream/oas/Component_GeneralBattle.yaml").write_text(
        dump_yaml({"resources": changed}), encoding="utf-8")
    packet, _ = compile()
    assert packet["source_obligations"][-1]["kind"] == "resource_drift"
    assert not packet["guarded_executable"]


@pytest.mark.parametrize("buff", list(BUFFS))
def test_each_buff_arm_preserves_source_operation_and_native_switch(compiler_fixture, buff):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile(buff=buff)
    base = normal()
    is_open = not buff.endswith("_CLOSE")
    desired, inverse = ("I_OPEN_YELLOW", "I_CLOSE_RED") if is_open else ("I_CLOSE_RED", "I_OPEN_YELLOW")
    def choose(p, v, d):
        if p == "buff_open":
            return ["I_CLOUD"]
        if p.startswith("buff_0"):
            marker = desired if d.taps_by_phase.get("buff_0_switch") else inverse
            return ["I_CLOUD", "I_AWAKE" if buff.startswith("AWAKE") else "I_SOUL", marker]
        if p == "buff_close":
            return []
        if p == "buff_prepare":
            return []
        return base(p, v, d)
    result, device, _, _ = run(workflow, frame, choose, full_ocr_reader=lambda *_: (500, 180, 250, 10))
    assert result.status == "success", result.summary()
    assert device.taps_by_phase["buff_0_switch"] == 1
    assert result.variables["gb_buff_0_status"] == "observed"
    helper = packet["workflow"]["oas_battle_contract"]["buff_helpers"][0]
    assert helper["source"]["path"] == battle.BUFF
    assert helper["contract"]["is_open"] is is_open
    assert helper["contract"]["switch_timeout_ms"] == 10000
    assert not any(o["kind"] == "missing_helper" and "buff" in o["requirement"] for o in packet["source_obligations"])


def test_buff_list_order_and_duplicate_operations_survive(compiler_fixture):
    compile, _, _, _ = compiler_fixture
    packet, _ = compile(buff=[10, 20, 70, 10])
    ops = packet["workflow"]["oas_battle_contract"]["buff_helpers"]
    assert [o["contract"]["method"] for o in ops] == ["awake", "soul", "awake", "awake"]
    assert [o["contract"]["is_open"] for o in ops] == [True, True, False, True]
    assert [o["contract"]["order"] for o in ops] == [0, 1, 2, 3]


def test_native_buff_suffix_keeps_caller_preparation_after_the_helper_return(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile(buff=["AWAKE"])
    base = normal()
    def choose(p, v, d):
        taps = d.taps_by_phase.get(p, 0)
        if p == "buff_close":
            return ["I_CLOUD", "I_BUFF"] if not taps else []
        if p == "buff_prepare":
            return ["I_PREPARE_HIGHLIGHT"] if not taps else []
        return base(p, v, d)
    # The caller's return join is independently tested from switch recognition.
    result, device, _, _ = run(workflow, frame, choose,
        initial_vars={"gb_phase": "buff_0_returned", "gb_current_count": 1})
    assert result.status == "success", result.summary()
    assert device.taps_by_phase["buff_close"] == 1
    assert device.taps_by_phase["buff_prepare"] == 1
    assert result.variables["gb_confed"]
    assert not packet["complete"]
    issue = packet["workflow"]["oas_battle_contract"]["buff_helpers"][0]
    assert issue["contract"]["native_continuation_phase"] == "buff_0_returned"


def test_reward_wait_timeout_preserves_prior_win_without_claiming_reward(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    result, _, clock, events = run(workflow, frame, normal(reward=False))
    assert result.status == "success" and result.variables["gb_return"] is True
    assert clock.ms > 10000
    receipts = [e for k, e in events if k == "receipt"]
    assert len(receipts) == 1 and receipts[0]["kind"] == "battle_result"
    assert "reward" not in result.evidence


def test_statistics_timeout_enters_reward_processing(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal(reward=False)
    result, device, _, _ = run(workflow, frame,
        lambda p, v, d: ["I_STATISTICS"] if p == "reward_timeout" else base(p, v, d))
    assert result.status == "success"
    assert device.taps_by_phase["reward_collect"] == 1


@pytest.mark.parametrize("wait_ms", [400, 800, 400.125, 799.875])
def test_unknown_preparation_uses_bounded_wait_then_times_out_without_completion(compiler_fixture, native_draws, wait_ms):
    compile, frame, _, _ = compiler_fixture
    calls = native_draws(prep_wait=wait_ms)
    _, workflow = compile()
    state = next(s for s in workflow.states if s["id"] == "gb_prepare_random_wait")
    assert state["do"] == [{"wait_random": {"min_ms": 400, "max_ms": 800, "distribution": "uniform"}}]
    result, device, _, events = run(workflow, frame, lambda p, v, d: [], max_seconds=7)
    assert result.status == "limit", result.summary()
    assert result.variables["gb_current_count"] == 1
    assert result.variables["gb_phase"] == "battle_wait"
    assert not result.variables["gb_returned"] and not result.variables["gb_prep_return"]
    assert not device.inputs and not [e for k, e in events if k == "receipt"]
    assert calls and all(pair == ((400, 800), wait_ms) for pair in calls)
    assert len(calls) == sum(sid == "gb_prepare_random_wait" for _, sid in result.history)
    waits = [i for i, (phase, _, _) in enumerate(device.snapshots[:-1]) if phase == "prepare"
             and device.snapshots[i + 1][2] - device.snapshots[i][2] > 100]
    assert waits
    assert all(device.snapshots[i + 1][2] - device.snapshots[i][2] == pytest.approx(wait_ms + 100) for i in waits)


def test_pending_idle_result_preempts_a_sampled_input(compiler_fixture, native_draws):
    compile, frame, _, _ = compiler_fixture
    calls = native_draws(trigger=0, kind=2)
    _, workflow = compile()
    base = normal()
    def choose(p, v, d):
        if p == "battle_idle_input":
            return ["I_WIN"]
        if p == "battle_wait" and not calls:
            return ["I_BATTLE_INFO"]
        return base(p, v, d)
    result, device, _, events = run(workflow, frame, choose,
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1}, params={"random_click_swipt_enable": True})
    assert result.status == "success" and result.variables["gb_return"] is True
    assert not [e for e in device.input_times if e[0] == "battle_idle_input"]
    assert len([e for k, e in events if k == "receipt"]) == 1


def test_sampled_idle_requires_positive_visual_evidence(compiler_fixture, native_draws):
    compile, frame, _, _ = compiler_fixture
    native_draws(trigger=0, kind=0)
    _, workflow = compile()
    result, device, _, events = run(workflow, frame, lambda p, v, d: [],
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1}, params={"random_click_swipt_enable": True})
    assert result.status == "failed" and result.failed_state == "gb_idle_positive_evidence_blocked"
    assert not device.inputs and not [e for k, e in events if k == "receipt"]


def test_sampled_idle_rechecks_positive_evidence_immediately_before_input(compiler_fixture, native_draws):
    compile, frame, _, _ = compiler_fixture
    native_draws(trigger=0, kind=1)
    _, workflow = compile()
    seen = 0
    def choose(p, v, d):
        nonlocal seen
        if p == "battle_idle_input":
            seen += 1
            return ["I_BATTLE_INFO"] if seen == 1 else []
        return ["I_BATTLE_INFO"]
    result, device, _, _ = run(workflow, frame, choose,
        initial_vars={"gb_phase": "battle_wait", "gb_current_count": 1}, params={"random_click_swipt_enable": True})
    assert result.status == "failed" and result.failure_kind == "recognition"
    assert not device.inputs


def test_trigger_during_cooldown_returns_without_400ms_sleep(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile()
    base = normal()
    result, device, _, _ = run(workflow, frame, base,
        initial_vars={"gb_phase": "battle_idle_input", "gb_idle_kind": 0,
                      "gb_last_c_random_click": 0, "gb_current_count": 1},
        params={"random_click_swipt_enable": True})
    assert result.status == "success", result.summary()
    first, second = device.snapshots[:2]
    assert first[0] == "battle_idle_input" and second[0] == "battle_wait"
    assert second[2] - first[2] == 100  # Only capture latency, not the non-trigger 400ms sleep.
    assert not [e for e in device.input_times if e[0] == "battle_idle_input"]


@pytest.mark.parametrize("kwargs", [{"current_count": True}, {"current_count": -1}, {"prefix": "x.y"},
                                    {"buff": "arbitrary_callback"}, {"buff": [True]}])
def test_invalid_binding_cannot_enter_native_output(compiler_fixture, kwargs):
    compile, _, _, _ = compiler_fixture
    with pytest.raises(ValueError):
        compile(**kwargs)


def test_frontend_static_config_and_enum_extraction_never_runs_imports(tmp_path):
    source = """
raise RuntimeError('must not run')
from nowhere import executable
class GreenMarkType(str, Enum):
    LEFT = 'left'
class GreenMarkEnum(str, Enum):
    CHOOSE = 'choose'
class GeneralBattleConfig(BaseModel):
    enabled: bool = Field(default=False)
    team: int = Field(default=1, ge=1, le=5)
    mark: GreenMarkType = Field(default=GreenMarkType.LEFT)
"""
    target = tmp_path / (battle.CONFIG + ".txt")
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    reader = battle._Sources(tmp_path)
    assert reader.config() == {"enabled": {"default": False}, "team": {"default": 1, "min": 1, "max": 5},
                               "mark": {"default": "left", "choices": ["left"]}}
    with pytest.raises(battle._Missing) as e:
        reader.verify()
    assert e.value.obligation["kind"] == "missing_source"


def test_missing_source_produces_native_input_free_failure(tmp_path):
    packet = battle.compile_general_battle(tmp_path, tmp_path)
    assert not packet["complete"]
    assert packet["source_obligations"][0]["kind"] == "missing_source"
    raw = packet["workflow"]
    validate(raw, {})
    assert all(set(a) == {"fail"} for s in raw["states"] for a in s["do"])


@pytest.mark.parametrize("method", ["battle_wait", "_hook_special_reward", "awake", "screenshot"])
def test_task_overrides_do_not_silently_inherit_base_translation(tmp_path, method):
    p = tmp_path / "tasks/Custom/script_task.py"
    p.parent.mkdir(parents=True)
    p.write_text("from tasks.Component.GeneralBattle.general_battle import GeneralBattle as G\n"
                 f"class Custom(G):\n    def {method}(self):\n        return dangerous()\n", encoding="utf-8")
    with pytest.raises(battle._Missing) as e:
        battle._Sources(tmp_path).check_owner(("tasks/Custom/script_task.py", "Custom"))
    assert e.value.obligation["kind"] == "overridden_helper"
    assert e.value.obligation["source"]["start_line"] == 3


@pytest.mark.parametrize("body,kind", [
    ("class Custom(G, Other):\n    pass\n", "unresolved_inheritance"),
    ("@unknown_decorator\nclass Custom(G):\n    pass\n", "unresolved_inheritance"),
    ("class Custom(G):\n    I_WIN = different_asset()\n", "overridden_resource"),
])
def test_unproven_task_dispatch_is_an_explicit_dependency(tmp_path, body, kind):
    target = tmp_path / "tasks/Custom/script_task.py"
    target.parent.mkdir(parents=True)
    target.write_text("from tasks.Component.GeneralBattle.general_battle import GeneralBattle as G\n" + body, encoding="utf-8")
    with pytest.raises(battle._Missing) as error:
        battle._Sources(tmp_path).check_owner(("tasks/Custom/script_task.py", "Custom"))
    assert error.value.obligation["kind"] == kind


def test_source_drift_cannot_be_self_attested(tmp_path):
    target = tmp_path / battle.BATTLE
    target.parent.mkdir(parents=True)
    target.write_text("class GeneralBattle:\n    def run_general_battle(self):\n        return True\n", encoding="utf-8")
    packet = battle.compile_general_battle(tmp_path, tmp_path)
    issue = packet["source_obligations"][0]
    assert issue["kind"] == "source_drift"
    assert issue["source"]["symbol"] == "GeneralBattle"
    assert issue["expected_ast_sha256"] != issue["actual_ast_sha256"]
    assert not packet["complete"]


@pytest.fixture
def inert_checkout():
    root = Path(os.environ.get("OAF_OAS_SOURCE_ROOT", str(Path.home() / "AppData/Local/onmyoji-agentflow/upstream-src/oas")))
    if not (root / battle.BATTLE).is_file():
        pytest.skip("optional inert OAS source conformance checkout unavailable")
    return root


def test_actual_inert_source_pins_defaults_and_real_missing_team_five(inert_checkout):
    reader = battle._Sources(inert_checkout)
    reader.verify()
    assert reader.config() == CONFIG
    assert reader.enum(battle.BUFF_CONFIG, "BuffClass") == BUFFS
    with pytest.raises(battle._Missing) as e:
        reader.asset(battle.ASSETS, "GeneralBattleAssets", "C_PRESET_TEAM_5")
    assert e.value.obligation["kind"] == "missing_resource"


def test_actual_checkout_compiles_with_current_resource_converter(inert_checkout, tmp_path):
    # Resource conversion reads JSON/images, not upstream Python. Writes only tmp.
    from onmyoji_agentflow.convert.oas import convert_task
    folder = tmp_path / "resources/upstream/oas"
    convert_task(inert_checkout / "tasks/Component/GeneralBattle", folder, "Component_GeneralBattle")
    convert_task(inert_checkout / "tasks/Component/GeneralBuff", folder, "Component_GeneralBuff")
    convert_task(inert_checkout / "tasks/Component/GeneralInvite", folder, "Component_GeneralInvite")
    packet = battle.compile_general_battle(inert_checkout, folder)
    raw = packet["workflow"]
    path = tmp_path / "native.yaml"
    path.write_text(dump_yaml(raw), encoding="utf-8")
    load_workflow(path, [tmp_path / "resources"])
    states = {state["id"]: state for state in raw["states"]}
    for group, y in enumerate((240, 305, 365, 430, 495, 555, 615), 1):
        assert states[f"gb_preset_group_{group}"]["when"]["all"][-1]["mean_color"]["region"] == [35, y, 25, 50]
    for team, y in enumerate((235, 355, 475, 595), 1):
        assert states[f"gb_preset_team_{team}"]["when"]["all"][-1]["mean_color"]["region"] == [195, y, 5, 5]
    assert len(raw["states"]) >= 60
    assert not packet["complete"]
    assert all(o["kind"] != "resource_drift" for o in packet["source_obligations"])
    assert packet["source_files"] and all(len(s["sha256"]) == 64 for s in packet["source_files"])
    for buff in (None, [10, 20, 110]):
        bound = battle.compile_general_battle(inert_checkout, folder, buff=buff)
        assert bound["guarded_executable"] and not bound["complete"]
    # The inventory's .py.txt layout has the same inert frontend contract.
    snapshot = tmp_path / "programs/src"
    for item in packet["source_files"]:
        target = snapshot / (item["path"] + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((inert_checkout / item["path"]).read_bytes())
    from_snapshot = battle.compile_general_battle(snapshot, folder)
    assert from_snapshot["workflow"] == raw
