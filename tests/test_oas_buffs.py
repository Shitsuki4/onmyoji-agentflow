"""Source-level BUFF branching exercised through the native Runner."""
import pytest

from test_oas_battle import compiler_fixture, normal, run  # noqa: F401 -- shared portable source fixture
from onmyoji_agentflow.vision.ocr import FullOcrArea


def scene(base, phase, variables, device, *, marker="I_CLOSE_RED", icon="I_AWAKE"):
    if phase == "buff_open":
        return ["I_CLOUD"]
    if phase.startswith("buff_0"):
        return ["I_CLOUD", icon, marker]
    if phase in ("buff_close", "buff_prepare"):
        return []
    return base(phase, variables, device)


def test_icon_area_is_derived_from_the_current_match_not_asset_declaration(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff="AWAKE")
    base = normal()
    original = frame("I_AWAKE")
    patch = original[180:200, 381:391].copy()
    red = frame("I_CLOSE_RED")[183:193, 780:790].copy()
    yellow = frame("I_OPEN_YELLOW")[183:193, 780:790].copy()
    def choose(p, v, d):
        if p.startswith("buff_0"):
            image = frame("I_CLOUD")
            image[280:300, 381:391] = patch
            image[283:293, 780:790] = yellow if d.taps_by_phase.get("buff_0_switch") else red
            return image
        return scene(base, p, v, d)
    result, device, _, _ = run(workflow, frame, choose)
    assert result.status == "success", result.summary()
    assert [result.variables["gb_buff_0_" + n] for n in ("x", "y", "w", "h")] == [750, 280, 80, 20]
    tap = next(data for data in device.inputs if data[0] == "tap")
    assert 780 <= tap[1] <= 790 and 283 <= tap[2] <= 293


@pytest.mark.parametrize("buff", ["AWAKE", "SOUL", "AWAKE_CLOSE", "SOUL_CLOSE"])
def test_missing_icon_returns_to_caller_without_a_switch_attempt(compiler_fixture, buff):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile(buff=buff)
    base = normal()
    def choose(p, v, d):
        if p.startswith("buff_0"):
            return ["I_CLOUD"]
        return scene(base, p, v, d)
    result, device, _, _ = run(workflow, frame, choose)
    assert result.status == "success" and result.variables["gb_buff_0_status"] == "missing"
    assert not device.taps_by_phase.get("buff_0_switch")
    assert not any(o["branch"].startswith("buff[") for o in packet["source_obligations"])


@pytest.mark.parametrize("buff", ["GOLD_50", "GOLD_100", "EXP_50", "EXP_100"])
def test_ocr_zero_box_remains_a_typed_safety_obligation_without_input(compiler_fixture, buff):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile(buff=buff)
    result, device, _, _ = run(workflow, frame, lambda *_: ["I_CLOUD"],
        initial_vars={"gb_phase": "buff_0", "gb_current_count": 1}, full_ocr_reader=lambda *_: (0, 0, 0, 0))
    assert result.status == "failed" and result.failed_state == "gb_buff_0_zero_area_blocked"
    assert not device.inputs and not result.business_ok
    issue = next(o for o in packet["source_obligations"] if o["branch"] == "buff[0] == " + buff and o["kind"] == "unsafe_source_roi")
    assert issue["kind"] == "unsafe_source_roi" and issue["blocking"]


def test_partial_character_result_one_pixel_from_source_sentinel_cannot_toggle_awake_for_missing_gold(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile(buff="GOLD_50")
    area = FullOcrArea((432, 142, 325, 22), keyword_complete=False)
    result, device, _, _ = run(workflow, frame, lambda *_: ["I_CLOUD", "I_AWAKE", "I_CLOSE_RED"],
        initial_vars={"gb_phase": "buff_0", "gb_current_count": 1}, full_ocr_reader=lambda *_: area)
    assert result.failed_state == "gb_buff_0_partial_keyword_blocked"
    assert not device.inputs and not result.business_ok
    assert any(o["kind"] == "unsafe_source_keyword" for o in packet["source_obligations"])


@pytest.mark.parametrize("buff,returns", [("GOLD_50", True), ("GOLD_100_CLOSE", True), ("EXP_50", False), ("EXP_100_CLOSE", False)])
def test_source_exact_sentinel_returns_for_gold_but_retries_for_exp(compiler_fixture, buff, returns):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff=buff)
    result, device, _, _ = run(workflow, frame, lambda *_: ["I_CLOUD"], max_seconds=2,
        initial_vars={"gb_phase": "buff_0", "gb_current_count": 1}, full_ocr_reader=lambda *_: (432, 143, 325, 21))
    phases = [sid for _, sid in result.history]
    assert ("gb_buff_0_returned" in phases) is returns
    assert phases.count("gb_buff_0_area_sentinel") >= (1 if returns else 2)
    assert not device.inputs


@pytest.mark.parametrize("buff", ["EXP_50", "EXP_100_CLOSE"])
def test_exp_missing_markers_swipes_exact_source_points_then_waits_and_relocates(compiler_fixture, buff):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff=buff)
    base, ocr_times = normal(), []
    desired, inverse = ("I_CLOSE_RED", "I_OPEN_YELLOW") if buff.endswith("CLOSE") else ("I_OPEN_YELLOW", "I_CLOSE_RED")
    def choose(p, v, d):
        marker = desired if d.taps_by_phase.get("buff_0_switch") else inverse
        if p.startswith("buff_0") and not d.swipes_by_phase.get("buff_0_probe"):
            return ["I_CLOUD"]
        return scene(base, p, v, d, marker=marker)
    def reader(*_):
        ocr_times.append(True)
        return (500, 180, 250, 10)
    result, device, _, _ = run(workflow, frame, choose, full_ocr_reader=reader)
    assert result.status == "success", result.summary()
    assert ("swipe", (580, 320), (530, 240)) in device.inputs
    assert device.swipes_by_phase["buff_0_probe"] == 1 and len(ocr_times) == 2
    swipe_t = next(t for p, op, t in device.input_times if op == "swipe")
    reentry = [t for p, _, t in device.snapshots if p == "buff_0" and t > swipe_t]
    assert reentry and reentry[0] - swipe_t >= 1000
    assert result.variables["gb_buff_0_status"] == "observed"


def test_source_helper_timeout_warns_and_continues_with_distinct_status(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff="AWAKE")
    base = normal()
    def choose(p, v, d):
        if p.startswith("buff_0"):
            return ["I_CLOUD", "I_AWAKE"]
        return scene(base, p, v, d)
    result, device, _, events = run(workflow, frame, choose)
    assert result.status == "success" and result.variables["gb_buff_0_status"] == "timeout"
    assert not device.taps_by_phase.get("buff_0_switch")
    assert any("buff failed" in e.get("message", "") for k, e in events if k == "log")
    assert "gb_buff_0_returned" in [s for _, s in result.history]


def test_target_marker_precedes_timeout_and_never_requires_a_click(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff="AWAKE")
    base = normal()
    result, device, _, _ = run(workflow, frame,
        lambda p, v, d: scene(base, p, v, d, marker="I_OPEN_YELLOW"))
    assert result.variables["gb_buff_0_status"] == "observed"
    assert not device.taps_by_phase.get("buff_0_switch")


def test_switch_retries_have_a_strict_shared_target_cooldown(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff="AWAKE")
    base = normal()
    def choose(p, v, d):
        marker = "I_OPEN_YELLOW" if d.taps_by_phase.get("buff_0_switch", 0) >= 3 else "I_CLOSE_RED"
        return scene(base, p, v, d, marker=marker)
    result, device, _, _ = run(workflow, frame, choose)
    assert result.status == "success", result.summary()
    times = [t for p, op, t in device.input_times if p == "buff_0_switch"]
    assert len(times) == 3 and all(b-a > 1000 for a, b in zip(times, times[1:]))


def test_invite_rejection_order_and_filename_shared_six_second_cooldown(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    packet, workflow = compile(buff="AWAKE")
    base = normal()
    def choose(p, v, d):
        if p == "buff_0":
            remaining = ["I_I_REJECT_" + str(i) for i in (3, 2, 1)][d.taps_by_phase.get(p, 0):]
            return ["I_CLOUD", *remaining]
        if p.startswith("buff_0"):
            return ["I_CLOUD"]
        return scene(base, p, v, d)
    result, device, _, _ = run(workflow, frame, choose, max_seconds=25,
        initial_vars={"gb_phase": "buff_0", "gb_current_count": 1})
    assert result.status == "success", result.summary()
    times = [t for p, op, t in device.input_times if p == "buff_0"]
    assert len(times) == 3 and all(b-a > 6000 for a, b in zip(times, times[1:]))
    taps = [data for data in device.inputs if data[0] == "tap"][:3]
    assert [round(t[2] / 100) for t in taps] == [4, 3, 2]
    interval_vars = packet["workflow"]["oas_battle_contract"]["composition"]["interval_vars"]
    assert [n for n in interval_vars if "gi_i_reject" in n] == ["gb_last_source_gi_i_reject"]


def test_trial_limit_and_fresh_frame_loss_prevent_continuing_a_switch(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff="AWAKE")
    base = normal()
    result, device, _, _ = run(workflow, frame, lambda p, v, d: scene(base, p, v, d), max_actions=1,
        initial_vars={"gb_phase": "buff_0", "gb_current_count": 1})
    assert result.status == "limit" and len(device.inputs) == 1 and not result.business_ok
    assert result.variables["gb_buff_0_status"] == "unobserved"
    seen = []
    def stale(p, v, d):
        if p == "buff_0_switch":
            seen.append(1)
            return ["I_CLOUD", "I_AWAKE", "I_CLOSE_RED"] if len(seen) == 1 else ["I_CLOUD"]
        return scene(base, p, v, d)
    result, device, _, _ = run(workflow, frame, stale,
        initial_vars={"gb_phase": "buff_0", "gb_current_count": 1})
    assert result.failure_kind == "recognition" and not device.inputs


def test_cancel_during_exp_post_swipe_sleep_never_reenters_or_sends_more_input(compiler_fixture):
    compile, frame, _, _ = compiler_fixture
    _, workflow = compile(buff="EXP_50")
    cancelled = []
    def before_input(*_):
        return lambda sent: cancelled.append(True) if sent else None
    result, device, _, _ = run(workflow, frame, lambda *_: ["I_CLOUD"], full_ocr_reader=lambda *_: (500, 180, 250, 10),
        initial_vars={"gb_phase": "buff_0", "gb_current_count": 1}, should_stop=lambda: bool(cancelled), before_input=before_input)
    assert result.status == "stopped" and len(device.inputs) == 1
    assert device.inputs[0][0] == "swipe" and not result.business_ok
