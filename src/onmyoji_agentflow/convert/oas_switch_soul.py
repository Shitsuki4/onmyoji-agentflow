"""Pinned OAS SwitchSoul helpers (GPL-3.0)."""
import hashlib

from ..yamlio import load_yaml


ASSETS = "Component_SwitchSoul"
PINS = {
    "tasks/Component/SwitchSoul/switch_soul.py": "be5fd7ff6c306d090042e31f2d4d5c4a898f32316bac8a9f86c76b9862a08b1d",
    "tasks/Component/SwitchSoul/assets.py": "c82f172a4e42f6b997a2ffb4c4caabc347a47a688ab81ba956ace86fc6e70b5f",
    "tasks/Component/SwitchSoul/switch_soul_config.py": "6ebf245f01ae1e4fd28f27aa909b8ff75cf2dd4dd60750c5dbe533c98a162d61",
}


def bind_named_preset(raw, source, resources, *, prefix, phase_var, resume_phase):
    """Add the named preset flow. Callers enter the returned phase after configuration checks."""
    for path, pin in PINS.items():
        content = (source / path).read_text(encoding="utf-8-sig").encode()
        if hashlib.sha256(content).hexdigest() != pin:
            raise ValueError(f"SwitchSoul source fingerprint mismatch: {path}")
    document = load_yaml(resources / f"{ASSETS}.yaml")["resources"]
    raw["resources"] = sorted(set(raw["resources"] + [f"upstream/oas/{ASSETS}.yaml", "upstream/oas/GlobalGame.yaml"]))
    keys = {name: f"{prefix}_{name}" for name in
            ("group", "team", "arrived", "texts", "last_texts", "scrolls", "clicks", "started")}
    group, team, arrived, texts, last_texts, scrolls, clicks, started = keys.values()
    raw["params"].update({group: {"default": ""}, team: {"default": ""}})
    raw["vars"].update({arrived: 0, texts: "", last_texts: "", scrolls: 0, clicks: 0, started: -1})

    def expr(text):
        return {"expr": text}

    def phase(name):
        return f"{prefix}_{name}"

    def advance(name, **updates):
        return {"set": {phase_var: repr(phase(name)), **updates}}

    def state(name, where, guards, *actions):
        raw["states"].append({"id": phase(name), "when": {"all": [expr(f"{phase_var} == {phase(where)!r}"), *guards]},
                              "do": list(actions)})

    def image(name):
        return {"res": f"{ASSETS}::{name}"}

    def record(asset):
        return {"ocr": f"{ASSETS}::{asset}", "mode": "text_sequence", "var": texts}

    def exact(asset, parameter):
        return {"ocr_full": {"region": document[asset]["roi"], "keyword_var": parameter,
                             "selection": "unique_equals", "evidence": "complete_keyword"}}

    def swipe(asset, delay):
        return {"swipe": f"{ASSETS}::{asset}", "delay": delay, "recheck": True}

    def match_click(delay):
        return {"click_found": True, "use_match_size": True, "recheck": True, "delay": delay}

    records = raw["navigation"]["pages"]["page_shikigami_records"]["when"]
    panel = {"any": [image("I_SOU_TEAM_PRESENT"), *(image(f"I_SOU_SWITCH_{n}") for n in range(1, 5))]}
    open_preset = image("I_SOUL_PRESET")
    confirm = {"res": "GlobalGame::I_UI_CONFIRM"}
    group_row = exact("O_SS_GROUP_NAME", group)
    team_row = exact("O_SS_TEAM_NAME", team)
    state("missing_names", "records", [expr(f"{group} == '' or {team} == ''")],
          {"fail": "御魂预设按名称切换需要分组名和队伍名"})
    state("records_ready", "records", [records, expr(f"{arrived} == 1")], advance("panel"))
    state("records_drive", "records", [], {"navigate": {"destination": "page_shikigami_records", "done_var": arrived}})
    state("panel_ready", "panel", [panel], advance("top_group", **{last_texts: "''", scrolls: 0}))
    state("open_panel", "panel", [records, open_preset], match_click(3000))

    for kind, asset, row, to_top, search, duration in (
        ("group", "O_SS_GROUP_NAME", group_row, "S_SS_GROUP_SWIPE_UP", "S_SS_GROUP_SWIPE_DOWN", 2500),
        ("team", "O_SS_TEAM_NAME", team_row, "S_SS_TEAM_SWIPE_DOWN", "S_SS_TEAM_SWIPE_UP", 2000),
    ):
        top_phase, find_phase = "top_" + kind, "find_" + kind
        read = record(asset)
        stable = expr(f"{texts} == {last_texts}")
        retry = {"set": {scrolls: f"{scrolls} + 1", last_texts: texts}}
        state(top_phase + "_ready", top_phase, [panel, read, stable], advance(find_phase, **{scrolls: 0}))
        state(top_phase + "_limit", top_phase, [expr(f"{scrolls} >= 12")], {"fail": "无法确认御魂预设列表顶部"})
        state(top_phase + "_swipe", top_phase, [panel, read], swipe(to_top, duration), retry)
        next_phase = "top_team" if kind == "group" else "apply"
        state(find_phase + "_select", find_phase, [panel, row], match_click(800),
              advance(next_phase, **{last_texts: "''", scrolls: 0, started: "elapsed_ms"}))
        state(find_phase + "_limit", find_phase, [expr(f"{scrolls} >= 12")], {"fail": "未找到唯一匹配的御魂预设名称"})
        state(find_phase + "_swipe", find_phase, [panel, read], swipe(search, 1500 if kind == "group" else 300), retry)

    state("apply_timeout", "apply", [expr(f"elapsed_ms - {started} >= 20000")], {"fail": "未能完成御魂预设应用"})
    state("apply_confirm", "apply", [expr(f"{clicks} > 0"), confirm], match_click(800))
    state("apply_done", "apply", [expr(f"{clicks} == 4"), panel, {"not": confirm}], {"set": {phase_var: repr(resume_phase)}})
    button_x, _, button_width, _ = document["I_SOU_CLICK_PRESENT"]["front"]
    state("apply_named", "apply", [expr(f"{clicks} < 4"), panel, {"not": confirm}, image("I_SOU_CLICK_PRESENT"), team_row],
          {"click_found": True, "projected_rect": [button_x, "match_y", button_width, 2], "delay": 1500, "recheck": True},
          {"inc": clicks})
    return phase("records")


def bind_numbered_preset(raw, state, goto, click, asset, *, prefix, group, team, resume, category,
                         phase_prefix="", group_2=None, team_2=None):
    """Bind the numbered group and team selection used by task callers (supports optional 2nd pair)."""
    arrived = f"{prefix}_records_arrived"
    scrolls, texts, previous = (f"{prefix}_soul_{name}" for name in ("scrolls", "groups", "last_groups"))
    group_taps, team_taps, confirms, blocks = (
        f"{prefix}_soul_{name}_taps" for name in ("group", "team", "confirm", "block"))
    raw["vars"].update({arrived: 0, scrolls: 0, texts: "", previous: "", group_taps: 0, team_taps: 0,
                        confirms: 0, blocks: 0})
    pair_idx = f"{prefix}_soul_pair_idx"
    cur_group, cur_team = (f"{prefix}_soul_cur_group", f"{prefix}_soul_cur_team") if group_2 and team_2 else (group, team)
    if group_2 and team_2:
        raw["vars"].update({pair_idx: 1, cur_group: 0, cur_team: 0})

    def expr(text):
        return {"expr": text}

    def seen(name):
        return {"res": asset(name)}

    def tap(name, delay):
        return {**click(asset(name)), "delay": delay}

    def ph(name):
        return f"{phase_prefix}{name}"

    teams = [f"I_SOU_SWITCH_{n}" for n in range(1, 5)]
    preset = {"any": [seen(name) for name in (*teams, "I_SOU_TEAM_PRESENT")]}
    records = raw["navigation"]["pages"]["page_shikigami_records"]["when"]
    init_pair = ([{"set": {pair_idx: 1, cur_group: group, cur_team: team}}] if group_2 and team_2 else [])
    state("soul_records_arrived", ph("soul_records"), [*init_pair, goto(ph("soul_panel"))], expr(f"{arrived} == 1"), records)
    state("soul_records_drive", ph("soul_records"), [{"navigate": {"destination": "page_shikigami_records",
          "done_var": arrived, "category": category}}])
    state("soul_panel_ready", ph("soul_panel"), [*init_pair, goto(ph("soul_scroll"))], preset)
    state("soul_panel_open", ph("soul_panel"), [tap("I_SOUL_PRESET", 3000)], records, seen("I_SOUL_PRESET"))

    read_groups = {"ocr": asset("O_SS_GROUP_NAME"), "mode": "text_sequence", "var": texts}
    stable = expr(f"{texts} == {previous}")
    state("soul_group_top", ph("soul_scroll"), [goto(ph("soul_group"))], preset, read_groups, stable)
    state("soul_group_scroll_limit", ph("soul_scroll"), [{"fail": "未能确认预设分组列表已回到顶部"}],
          preset, read_groups, expr(f"{scrolls} >= 8"))
    state("soul_group_scroll", ph("soul_scroll"), [
        {"swipe": asset("S_SS_GROUP_SWIPE_UP"), "delay": 2000, "recheck": True},
        {"set": {previous: texts}}, {"inc": scrolls}], preset, read_groups, {"not": stable})

    selected_groups = []
    for number in range(1, 8):
        target = expr(f"{cur_group} == {number}")
        selected_groups.append({"all": [target, seen(f"I_SOU_CHECK_GROUP_{number}")]})
        state(f"soul_group_{number}", ph("soul_group"), [tap(f"C_SOU_GROUP_{number}", 500), {"inc": group_taps}],
              preset, target, expr(f"{group_taps} < 2"))
    selected = {"any": selected_groups}
    state("soul_group_selected", ph("soul_group"), [goto(ph("soul_team"))], preset, selected, expr(f"{group_taps} == 2"))

    confirm_asset = "GlobalGame::I_UI_CONFIRM"
    confirm = {"res": confirm_asset}
    block = seen("I_CHECK_BLOCK")
    for number, target in enumerate(teams, 1):
        state(f"soul_team_{number}", ph("soul_team"), [tap(target, 800), {"inc": team_taps}, goto(ph("soul_confirm"))],
              preset, selected, {"not": confirm}, seen(target), expr(f"{cur_team} == {number} and {team_taps} < 3"))
    state("soul_confirm_block", ph("soul_confirm"), [tap("I_CHECK_BLOCK", 3000), {"inc": blocks}],
          block, expr(f"{confirms} > 0 and {blocks} < 3"))
    state("soul_confirm_apply", ph("soul_confirm"), [{**click(confirm_asset), "delay": 3000}, {"inc": confirms}],
          confirm, preset, selected, {"not": block}, expr(f"{confirms} < 3"))
    state("soul_confirm_unresolved", ph("soul_confirm"), [{"fail": "御魂预设确认弹窗无法核对"}], {"any": [confirm, block]})
    if group_2 and team_2:
        state("soul_applied_next_pair", ph("soul_confirm"), [
            {"set": {
                pair_idx: 2, cur_group: group_2, cur_team: team_2,
                group_taps: 0, team_taps: 0, confirms: 0, blocks: 0, scrolls: 0, previous: "''",
            }},
            goto(ph("soul_scroll")),
        ], preset, selected, expr(f"{confirms} > 0 and {blocks} == 0 and {pair_idx} == 1 and {group_2} > 0 and {team_2} > 0"))
    state("soul_applied", ph("soul_confirm"), [goto(resume)], preset, selected, expr(f"{confirms} > 0 and {blocks} == 0"))
    state("soul_blocked", ph("soul_confirm"), [{"fail": "御魂预设更换遇到占用提示"}], preset, expr(f"{blocks} > 0"))
    state("soul_try_team_again", ph("soul_confirm"), [{"wait": 2200}, goto(ph("soul_team"))],
          preset, selected, expr(f"{team_taps} < 3"))
    state("soul_team_unverified", ph("soul_confirm"), [{"fail": "未识别到预设确认，无法核对更换结果"}],
          preset, expr(f"{team_taps} >= 3"))


def bind_task_presets(raw, source, resources, *, prefix, resume, category, entry_phase="entry",
                      phase_var=None, phase_prefix=""):
    """Bind consecutive numbered (1 or 2 pairs) and named modes for task entries that call both."""
    phase_var = phase_var or f"{prefix}_phase"
    enabled = f"{prefix}_switch_soul"
    named_enabled = f"{prefix}_switch_soul_by_name"
    group, team = f"{prefix}_numbered_group", f"{prefix}_numbered_team"
    group_2, team_2 = f"{prefix}_numbered_group_2", f"{prefix}_numbered_team_2"
    raw["params"].update({
        enabled: {"default": False}, named_enabled: {"default": False},
        group: {"default": 0, "min": 0, "max": 7}, team: {"default": 0, "min": 0, "max": 4},
        group_2: {"default": 0, "min": 0, "max": 7}, team_2: {"default": 0, "min": 0, "max": 4},
    })
    documents = {name: load_yaml(resources / f"{name}.yaml")["resources"] for name in (ASSETS, "GlobalGame")}

    def goto(phase):
        return {"set": {phase_var: repr(phase)}}

    def state(name, phase, actions, *guards):
        raw["states"].append({"id": f"{prefix}_{name}", "when": {"all": [{"expr": f"{phase_var} == {phase!r}"}, *guards]},
                              "do": actions})

    def click(ref):
        namespace, name = ref.split("::", 1)
        spec = documents[namespace][name]
        if spec["type"] == "click":
            target = spec["rect"]
        else:
            x, y, w, h = spec["front"]
            target = [x, y, x + w, y + h]
        return {"click": target, "delay": 1000, "recheck": True}

    after_num = f"{phase_prefix}after_numbered"
    named = bind_named_preset(raw, source, resources, prefix=f"{prefix}_named", phase_var=phase_var, resume_phase=resume)
    state("numbered_unconfigured", entry_phase, [{"fail": "编号预设需要有效的分组和队伍"}],
          {"expr": f"{enabled} and ({group} == 0 or {team} == 0)"})
    state("numbered_preset", entry_phase, [goto(f"{phase_prefix}soul_records")], {"expr": enabled})
    state("skip_numbered", entry_phase, [goto(after_num)])
    state("named_preset", after_num, [goto(named)], {"expr": named_enabled})
    state("navigate_begin", after_num, [goto(resume)])
    bind_numbered_preset(raw, state, goto, click, lambda name: f"{ASSETS}::{name}", prefix=prefix,
                        group=group, team=team, resume=after_num, category=category, phase_prefix=phase_prefix,
                        group_2=group_2, team_2=team_2)
