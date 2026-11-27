"""Native growth-panel stages for pinned OAS ReplaceShikigami (GPL-3.0)."""
from ..yamlio import load_yaml


ASSETS = "Component_ReplaceShikigami"
CLASSES = ("MATERIAL", "N", "R", "SR", "SSR", "SP", "UR")


def bind_growth(raw, resources, *, prefix="ku", done_phase="harvest_probe", done_transitions=None):
    """Bind OAS ReplaceShikigami.check_max_lv growth-panel stages onto a workflow."""
    docs = {name: load_yaml(resources / f"{name}.yaml")["resources"]
            for name in (ASSETS, "GlobalGame")}
    p = prefix
    position = [f"{p}_growth_x", f"{p}_growth_y", f"{p}_growth_w", f"{p}_growth_h"]
    raw["params"][f"{p}_shikigami_class"] = {"default": "N", "choices": list(CLASSES)}
    raw["vars"].update(dict.fromkeys(position, 0), **{
        f"{p}_growth_clock": -1,
        f"{p}_growth_stable_since": -1,
        f"{p}_growth_passes": 0,
        f"{p}_growth_picks": 0,
        f"{p}_growth_pending": False,
        f"{p}_growth_residual_empty": False,
    })

    def image(name, namespace=ASSETS, **guards):
        return {"res": f"{namespace}::{name}", **guards}

    def expr(text):
        return {"expr": text}

    def step(name, phase, guards, *actions):
        raw["states"].append({"id": f"{p}_growth_" + name,
                              "when": {"all": [expr(f"{p}_phase == {phase!r}"), *guards]},
                              "do": list(actions)})

    def advance(phase, **values):
        return {"set": {f"{p}_phase": repr(phase), **values}}

    def click(name, delay, namespace=ASSETS):
        return {"click": docs[namespace][name]["rect"], "delay": delay, "recheck": True}

    def match_click(delay):
        return {"click_found": True, "use_match_size": True, "recheck": True, "delay": delay}

    growth = image("I_RS_RECORDS_SHIKI")
    full_level = image("I_RS_LEVEL_MAX")
    empty = {"any": [image(f"I_DETECT_EMPTY_{slot}") for slot in range(1, 7)]}
    open_slot = image("I_RS_NO_ADD")
    realm = image("I_REALM_SHIN", "KekkaiUtilize")
    enter_growth = image("I_SHI_GROWN", "KekkaiUtilize", scale_range=[0.8, 1.2])

    step("need_unset", "growth_verify", [growth, full_level], advance("growth_unset"))
    step("need_fill", "growth_verify", [growth, empty], advance("growth_class", **{f"{p}_growth_clock": "elapsed_ms"}))
    step("already_full", "growth_verify", [growth, {"not": full_level}, {"not": empty}], advance("growth_leave"))
    step("remove_max", "growth_unset", [growth, full_level], match_click(500))
    step("all_unset", "growth_unset", [growth, {"not": full_level}],
         advance("growth_class", **{f"{p}_growth_clock": "elapsed_ms"}))

    class_timeout = expr(f"elapsed_ms - {p}_growth_clock >= 25000")
    observed_box = {"capture_region": {"rect": ["match_x", "match_y", "match_w", "match_h"], "vars": position}}
    no_target = []
    for rank in CLASSES:
        requested = expr(f"{p}_shikigami_class == {rank!r}")
        row = image("I_RS_" + rank)
        chosen = image(f"I_RS_{rank}_SELECTED")
        saved_row = image("I_RS_" + rank, region_vars=position)
        no_target.append({"all": [requested, {"not": row}, {"not": chosen}]})

        for phase in ("growth_class", "growth_stable"):
            step(f"class_selected_{rank.lower()}_{phase}", phase, [growth, requested, chosen],
                 advance("growth_fill", **{
                     f"{p}_growth_clock": "elapsed_ms",
                     f"{p}_growth_picks": 0,
                     f"{p}_growth_passes": f"{p}_growth_passes + 1",
                     f"{p}_growth_pending": False,
                 }))
        step(f"class_probe_{rank.lower()}", "growth_class", [growth, {"not": class_timeout}, requested, row],
             observed_box, advance("growth_stable", **{f"{p}_growth_stable_since": "elapsed_ms"}))
        step(f"class_moved_{rank.lower()}", "growth_stable", [growth, requested, {"not": saved_row}],
             advance("growth_class"))
        step(f"class_choose_{rank.lower()}", "growth_stable", [growth, requested, {"not": class_timeout},
             expr(f"elapsed_ms - {p}_growth_stable_since >= 1500"), saved_row], match_click(2000),
             advance("growth_class"))

    for phase in ("growth_class", "growth_stable"):
        step("class_timeout_" + phase, phase, [class_timeout], {"fail": "育成分类没有在时限内稳定显示"})
    step("class_open", "growth_class", [growth, {"any": no_target}], click("C_SHIKIGAMI_SWITCH_1", 3500))

    before_timeout = expr(f"elapsed_ms - {p}_growth_clock <= 120000")
    step("fill_timeout", "growth_fill", [{"not": before_timeout}], {"fail": "育成补位超时"})
    step("second_pass", "growth_fill", [growth, {"not": open_slot}, empty, expr(f"{p}_growth_passes < 2")],
         advance("growth_class", **{f"{p}_growth_clock": "elapsed_ms"}))
    step("residual_empty", "growth_fill", [growth, {"not": open_slot}, empty],
         advance("growth_leave", **{f"{p}_growth_residual_empty": True}))
    step("filled", "growth_fill", [growth, {"not": open_slot}, {"not": empty}], advance("growth_leave"))

    pending = expr(f"{p}_growth_pending")
    small = image("I_U_CONFIRM_SMALL")
    confirm = image("I_UI_CONFIRM", "GlobalGame")
    confirm_short = image("I_UI_CONFIRM_SAMLL", "GlobalGame")
    alternate_circle = image("I_U_CIRCLE_ALTERNATE")
    alternate_confirm = image("I_U_CONFIRM_ALTERNATE")
    for name, guard, delay in (("small", small, 500), ("large", confirm, 1000), ("short", confirm_short, 1000)):
        step("confirm_" + name, "growth_fill", [pending, open_slot, guard], match_click(delay))
    step("alternate_enabled", "growth_fill", [pending, open_slot, alternate_circle], match_click(2500),
         advance("growth_alternate"))
    step("alternate_confirm", "growth_alternate", [pending, open_slot, alternate_confirm], match_click(1500),
         advance("growth_fill"))
    step("alternate_timeout", "growth_alternate", [{"not": before_timeout}], {"fail": "育成候补确认超时"})
    overlays = {"any": [small, confirm, confirm_short, alternate_circle, alternate_confirm]}
    for slot, when, duration in ((7, f"{p}_growth_picks % 2 == 0", 1500), (6, f"{p}_growth_picks % 2 == 1", 4500)):
        step(f"pick_{slot}", "growth_fill", [growth, open_slot, {"not": overlays}, expr(when)],
             click(f"C_SHIKIGAMI_LEFT_{slot}", duration),
             {"set": {f"{p}_growth_picks": f"{p}_growth_picks + 1", f"{p}_growth_pending": True}})

    if done_transitions is None:
        step("left", "growth_leave", [realm, enter_growth], advance(done_phase))
    else:
        for tag, guards, target_phase, updates in done_transitions:
            step(f"left_{tag}", "growth_leave", [realm, enter_growth, *guards], advance(target_phase, **updates))
    step("back", "growth_leave", [growth, image("I_UI_BACK_BLUE", "GlobalGame")], match_click(2500))
