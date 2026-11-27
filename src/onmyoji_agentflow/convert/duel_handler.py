"""Guarded native duel misc handler (030), assttyys (MIT, Copyright (c) 2019 Chaos)."""
from .core_handlers import _push, _stop
from .handlers import _count
from .team_handlers import _all, _expr

BAN_CHARS = ("面", "龙", "辉", "犬", "狐", "言", "追", "桃", "平", "驴")


def build_duel_misc(b):
    b.model["vars"] = {"redFlag": False}
    counted = [_count(30)]

    # Lines 243-254: ledgeProPvP stop when on 大名士 screen (op[14], op[15])
    pro_stop = b.gap(
        "ledge_pro_pvp_stop", (243, 254), {"config": "ledgeProPvP", "screen": "da_ming_shi"},
        [_push("已大名士，停止斗技。"), _stop(), {"effect": "sleep", "ms": 3000}],
        True, ["source Push", "source stop lifecycle"],
    )
    for idx in (14, 15):
        acts = b.actions(idx)
        b.add(f"ledge_pro_stop_{idx}", _all(_expr("ledgeProPvP"), b.when(idx)),
              [{**acts[0], "recheck": True}, *acts[1:], pro_stop], counts=counted)

    # Lines 255-264: auto-deploy (op[4]) resets global.redFlag
    auto_acts = b.actions(4)
    b.add("auto_deploy", b.when(4),
          [{**auto_acts[0], "recheck": True}, *auto_acts[1:], {"set": {"redFlag": False}}],
          counts=counted)

    # Lines 265-275: standard duel screens
    for idx in (0, 1, 2, 3, 6, 7, 8, 9, 12, 13, 20):
        acts = b.actions(idx)
        b.add(f"duel_screen_{idx}", b.when(idx),
              [{**acts[0], "recheck": True}, *acts[1:]], counts=counted)

    # Lines 276-311: isKnowledgePvP branches
    knowledge = _expr("isKnowledgePvP")
    two_losses_gap = b.gap(
        "knockout_two_losses_check", (277, 289),
        {"config": "isKnowledgePvP", "screen": "knockout", "loss_marker_found": True},
        [{"effect": "findMultiColorEx('淘汰赛_败').length > 1 -> Push + stop + sleep(3000)"}],
        True, ["findMultiColorEx multi-match count >= 2", "source Push", "source stop lifecycle"],
    )
    b.add("knockout_loss_marker", _all(knowledge, b.when(19), {"find": "淘汰赛_败"}),
          [two_losses_gap], counts=counted)
    b.add("knockout_recognized", _all(knowledge, b.when(19)), outcome=None, counts=counted)

    for idx in (5, 10):
        acts = b.actions(idx)
        b.add(f"knowledge_screen_{idx}", _all(knowledge, b.when(idx)),
              [{**acts[0], "recheck": True}, *acts[1:]], counts=counted)

    # Lines 297-310: banList exit on op[11]
    ban_screen = b.when(11)
    ban_exit_acts = b.actions(11)
    configured_ban = str(b.model["params"]["banList"]["default"])
    seen_chars: list[str] = []
    for ch in configured_ban:
        if ch in BAN_CHARS and ch not in seen_chars:
            seen_chars.append(ch)
    for pos, ch in enumerate(seen_chars):
        b.add(
            f"ban_exit_{pos}",
            _all(knowledge, _expr(f"banList == {configured_ban!r}"), ban_screen, {"find": f"斗技ban选_{ch}"}),
            [{**ban_exit_acts[0], "recheck": True}, *ban_exit_acts[1:]],
            counts=counted,
        )
    dynamic_ban_gap = b.gap(
        "ban_list_runtime_parse", (297, 310),
        {"config": "isKnowledgePvP", "banList": "differs_from_compiled_literal"},
        [{"effect": "iterate runtime banList characters and exit on match"}],
        True, ["compile-time banList binding"],
    )
    b.add(
        "ban_list_dynamic_guard",
        _all(knowledge, _expr(f"banList != '' and banList != {configured_ban!r}"), ban_screen),
        [dynamic_ban_gap],
    )

    # Lines 312-329: courtyard -> click 庭院_町中竖牌 + sleep(2000) (uncounted)
    courtyard = {"any": [b.when(16), b.when(17)]}
    b.add("courtyard_to_town", _all(courtyard, {"find": "庭院_町中竖牌"}),
          [{"click_found": True, "offset": [0, 0, 5, 5], "delay": 1000, "recheck": True}, {"wait": 2000}])

    # Lines 330-335: town -> click duel lantern (op[18], uncounted)
    town_acts = b.actions(18)
    b.add("town_to_duel", b.when(18), [{**town_acts[0], "recheck": True}, *town_acts[1:]])

    proof = b.model["proof"]
    proof["source_state_bindings"] = {"global.redFlag": "redFlag"}
    proof["ban_list_compiled"] = {"literal": configured_ban, "matched_supported_chars": seen_chars}
