"""Pinned assttyys apprentice guarding flow (MIT, Copyright 2019 Chaos)."""
from __future__ import annotations

from .core_handlers import _rerun
from .handlers import _count
from .team_handlers import _all, _expr


def _taps(b, index):
    steps = b.actions(index)
    return [{**steps[0], "recheck": True}, *steps[1:]] if steps else []


def build_apprentice_login(b):
    stage = "apprentice_login_stage"
    timer = "apprentice_story_timer"
    b.model["vars"] = {stage: "create", timer: 0}
    counts = [_count(691)]

    def active(value):
        return _expr(f"{stage} == {value!r}")

    def enter(value):
        return {"set": {stage: repr(value)}}

    def operator(value, index, *, target=None):
        predicate = b.when(index)
        actions = _taps(b, index)
        if target is not None:
            actions.append(enter(target))
        if value is not None:
            predicate = _all(active(value), predicate)
        b.add(f"apprentice_login_{value or 'misc'}_{index}", predicate, actions, counts=counts,
              retest_ms=b.ops[index].get("retest"))

    def operators(value, indices):
        for index in indices:
            operator(value, index)

    def fail_branch(name, value, index, lines, effect, requirements):
        condition = _all(active(value), b.when(index))
        gap = b.gap(name, lines, condition, [{"effect": effect}], True, requirements)
        b.add(name, condition, [gap], counts=counts)

    def find_click(name, predicate, resource, offset, delay):
        b.add(name, _all(predicate, {"find": resource}),
              [{"click_found": True, "offset": offset, "delay": delay, "recheck": True}])

    def rerun(name, value, index, lines, config, *, tap):
        condition = _all(active(value), b.when(index))
        gap = b.gap(name, lines, condition, [_rerun({"config": config}), {"effect": "sleep", "ms": 1000}],
                    True, ["bind configured next scheme"])
        b.add(name, condition, [*(_taps(b, index) if tap else []), gap], counts=counts)

    fail_branch("apprentice_nickname", "create", 1, (1159, 1184),
                "open and verify the text field, then type prefix plus last five base-36 timestamp digits",
                ["verified native Android text field and deterministic nickname construction"])
    fail_branch("apprentice_realm_selection", "create", 0, (1185, 1207),
                "select account region by OCR or fall back to the pinned platform and latest realm",
                ["verified account selection, OCR target, and refreshed entry page"])
    operators("create", (2, *range(3, 17)))
    scroll = _all(active("create"), b.when(19))
    start, end = b.actions(19)
    gap = b.gap("apprentice_story_scroll", (1219, 1226), scroll, [{"effect": "source regionSwipe"}], True,
                ["preserve bounded source swipe timing"], blocking=False)
    b.add("apprentice_story_scroll", scroll, [gap], counts=counts)
    b.model["proof"]["source_native_lowerings"] = {"apprentice_story_scroll": {
        "gate_prefix": gap["fail"], "native_intent": {"swipe": {"from": start["click"], "to": end["click"]},
        "duration_ms": [1000, 1300], "delay": 200, "recheck": True}}}
    operator("create", 20)
    find_click("apprentice_story_bubble", active("create"), "剧情三点", [0, 0, 3, 3], 1000)
    for index, target in ((21, "apply"), (22, "apply"), (17, "bird"), (82, "tutorial")):
        operator("create", index, target=target)

    b.add("apprentice_cutscene_pause", _all(active("tutorial"), b.when(84)), [{"wait": 5000}], counts=counts)
    operators("tutorial", (*range(58, 66), 13, 66, 67, 69, 72, 35, 73, 74, 75, 76, 83))
    operator("tutorial", 77, target="bird")
    dialogue = _all(active("tutorial"), b.when(68), {"not": b.when(71)})
    for index, resource in enumerate(("剧情三点_普", "剧情三点_战", "剧情黄眼", "剧情问号")):
        find_click(f"apprentice_tutorial_dialogue_{index}", dialogue, resource, [0, 0, 3, 3], 700)
    b.add("apprentice_advance_story", _all(dialogue, _expr(f"{timer} >= 4")),
          [{"set": {timer: 0}}, *_taps(b, 70)], counts=counts)
    # The source can still dismiss a skin ad when there is no dialogue target.
    b.add("apprentice_story_timer", dialogue, [{"inc": timer}], outcome=None, internal=True)
    find_click("apprentice_tutorial_close_ad", active("tutorial"), "皮肤广告关闭按钮", [0, 0, 3, 3], 700)

    operators("apply", (23, 86))
    fail_branch("apprentice_mentor_text", "apply", 24, (1350, 1371),
                "verify the mentor nickname field, type the configured full nickname and submit a lookup",
                ["verified native Android text field and mentor search receipt"])
    operators("apply", (22, 26, 27))
    operator("apply", 28, target="bird")
    operator("apply", 17, target="experience")

    operators("bird", (29, 30, 38, 39, 41))
    operator("bird", 42, target="trial")
    operators("trial", (45, 46, 47, 48, 35, 78, 85))
    operator("trial", 49, target="experience")
    rerun("apprentice_level_up", "experience", 78, (1443, 1452), "levelUP_scheme", tap=False)
    find_click("apprentice_open_town", _all(active("experience"), b.when(31)), "庭院_町中竖牌", [0, 0, 10, 10], 1000)
    operators("experience", (32, 33, 34, 35, 36, 37, 18, 55, 56))
    # The equivalent hall operation already returns in the preceding list.
    b.gap("apprentice_duplicate_create_team", (1477, 1493), _all(active("experience"), b.when(36)), [], False,
          [], blocking=False)
    find_click("apprentice_experience_close_ad", active("experience"), "皮肤广告关闭按钮", [-10, -10, 0, 0], 1000)

    operators("join", (50, 51, 52, 53))
    rerun("apprentice_stamina", "join", 54, (1507, 1515), "next_scheme", tap=True)
    operator(None, 40, target="join")
    operators(None, (7, 10, 16, 15, 43, 79))
    operator(None, 80, target="experience")
    operator(None, 81, target="apply")
    b.gap("apprentice_red_finger_popup", (1567, 1571), {"missing_asset": "红手指"},
          [{"effect": "dismiss emulator-specific popup"}], True, ["pinned 红手指 recognition resource"])


def build_apprentice_guard(b):
    stage = "apprentice_stage"
    attempts = "apprentice_challenge_attempts"
    waits = "apprentice_invite_waits"
    b.model["vars"] = {stage: "flower", attempts: 0, waits: -1}
    counts = [_count(692)]
    refresh = {"handler_control": {"op": "refresh"}}
    edges = b.model["proof"]["source_phase_edges"] = {}

    def active(value):
        return _expr(f"{stage} == {value!r}")

    def enter(value):
        return {"set": {stage: repr(value)}}

    def taps(index):
        return _taps(b, index)

    def menus(value, indices):
        for idx in indices:
            b.add(f"apprentice_{value}_{idx}", _all(active(value), b.when(idx)), taps(idx), counts=counts)

    def loop(case, target, condition, actions):
        gate = f"unresolved_source_obligation:team692.{case} requires team_workflow"
        b.add(case, condition, [*actions, {"fail": gate}], outcome=None, internal=True)
        edges[case] = {"target_case": target, "gate_prefix": gate}

    menus("flower", (0, 1, 4, 5, 6, 55))
    flower_tasks = _all(active("flower"), b.when(3))
    b.add("apprentice_flower_collect", _all(flower_tasks, b.when(2)), taps(2), counts=counts)
    b.add("apprentice_flower_checked", flower_tasks, [enter("check")])

    menus("check", (3, 14))
    b.add("apprentice_guard_required", _all(active("check"), b.when(15)), [*taps(15), enter("five")], counts=counts)
    b.add("apprentice_graduation_ready", _all(active("check"), b.when(27)), [*taps(27), enter("over")], counts=counts)

    five = active("five")
    b.add("apprentice_challenge_init", five, [{"set": {attempts: 0}}], outcome=None, internal=True)
    b.add("apprentice_challenge_tap", _all(five, b.when(21), _expr(f"{attempts} < 3")),
          [*taps(21), {"inc": attempts}, refresh], outcome=None, counts=counts)
    exhausted = _all(five, _expr(f"{attempts} >= 3"))
    rerun = b.gap("apprentice_challenge_retry_target", (797, 803), exhausted,
          [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 2000}],
          False, ["bind configured next scheme or close-application directive"])
    b.add("apprentice_challenge_exhausted", exhausted, [rerun], outcome=False)
    loop("apprentice_challenge_repeat", "apprentice_challenge_tap", _all(five, b.when(21)), [])
    menus("five", (16, 17, 22, 26, 33))

    invite = _all(five, b.when(23))
    b.add("apprentice_invite", invite, [*taps(23), {"set": {waits: 0}}, refresh], outcome=None, counts=counts)
    wait_guard = _all(five, b.when(24), _expr(f"0 <= {waits} and {waits} < 13"))
    loop("apprentice_invite_wait", "apprentice_invite_wait", wait_guard, [{"inc": waits}, {"wait": 1000}, refresh])
    b.add("apprentice_invite_done", _expr(f"{stage} == 'five' and {waits} >= 0"),
          [{"set": {waits: -1}}], internal=True)

    menus("over", (28, 29, 7, 8, 30, 31, 32))
    b.add("apprentice_graduation_battle", _all(active("over"), b.when(33)),
          [*taps(33), enter("finish")], counts=counts)

    menus("finish", (33, 34, 35, 36, 50, 56))
    cleanup = _all(active("finish"), b.when(37))
    stop = b.gap("apprentice_retirement", (863, 938), cleanup,
          [{"effect": "blocked source character deletion and identity submission"}], True,
          ["character deletion is prohibited by the workflow runtime"])
    b.add("apprentice_retirement_stop", cleanup, [stop])
    b.add("apprentice_yard_menu", b.when(53), taps(53), counts=counts)
