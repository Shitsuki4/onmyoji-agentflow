"""Guarded assttyys 602 guild battle and result routing (MIT, 2019 Chaos)."""
from .handlers import _count
from .preset_handler import BATTLE_GROUP, BATTLE_PENDING, BATTLE_PRESET
from .team_handlers import _all, _expr


def build_dojo_handler(b):
    leave, again, switch_team = "daoGuan_exit", "daoGuan_again", "daoguan_team"
    has_guild_handler = "dojo602_scheme_has_519"
    first_loss = "dojo602_super_daoguan_lose"
    activity_ready = "dojo602_super_liao_configured"
    activity_retry = "dojo602_super_activity_dojo_again"
    b.model["vars"] = {leave: False, again: True, switch_team: True, has_guild_handler: False,
                       first_loss: True, activity_ready: False, activity_retry: False,
                       BATTLE_PENDING: False, BATTLE_GROUP: "", BATTLE_PRESET: ""}
    counter = [_count(602)]

    def taps(index):
        return [{**action, "recheck": True} for action in b.actions(index)]

    def setting(**values):
        return {"set": values}

    def confirmation(name, guard, index, lines, *, retest=None, after=None):
        initial, confirm = taps(index)
        effects = [{"effect": "source_regionClick_confirmation", "action": confirm}]
        if after:
            effects.append({"effect": "source_global_write", "set": after["set"]})
        gate = b.gap(name, lines, guard, effects, True, ["verified recognition of the dojo confirmation dialog"])
        b.add(name, guard, [initial, gate], counts=counter, retest_ms=retest)

    confirmation("no_attempts", _all(_expr("fail_exit"), b.when(11)), 11, (263, 269),
                 after=setting(**{BATTLE_PENDING: True}))
    confirmation("leave_battle", _all(_expr(leave), b.when(8)), 8, (271, 277),
                 after=setting(**{leave: False}))

    preset = _all(_expr(f"switch_team_group > 0 and {switch_team}"), b.when(10))
    b.add("open_preset", preset, [*taps(10), setting(**{
        BATTLE_GROUP: f"{BATTLE_GROUP} or switch_team_group",
        BATTLE_PRESET: f"{BATTLE_PRESET} or switch_team_default",
        switch_team: False,
    })], counts=counter, retest_ms=2000)
    b.add("start_challenge", b.when(0), taps(0), retest_ms=1000)
    for index in (1, 3, 4):
        b.add(f"battle_result_{index}", b.when(index), taps(index), counts=counter)

    vote = _all(_expr("after_fail_operation"), b.when(5))
    b.add("init_failed_vote", vote, [setting(**{switch_team: True, BATTLE_PENDING: True,
        activity_retry: f"{activity_retry} or ({first_loss} and {activity_ready})", first_loss: False})],
        counts=counter, outcome=None, internal=True)
    for option, tap in zip(("保留赏金", "再战道馆"), taps(5)):
        b.add("vote_retain" if option == "保留赏金" else "vote_retry",
              _all(vote, _expr(f"after_fail_operation == {option!r}")), [tap])
    b.add("vote_skip", vote)

    second_group = _all(_expr(f"{again} and exit_second"), b.when(7))
    confirmation("exit_after_first_group", second_group, 7, (332, 345), retest=1000,
                 after=setting(**{leave: True, again: "exit_second_again"}))
    b.add("vote_give_up", b.when(12), [{"wait": 1500}, *taps(12)])

    yard = {"scheme_transition": {"mode": "rerun", "target": "返回庭院"}}
    for sibling in (False, True):
        condition = _all(b.when(2), _expr(has_guild_handler if sibling else f"not {has_guild_handler}"))
        b.add("finished_for_guild" if sibling else "finished_to_yard", condition,
              [] if sibling else [yard], counts=counter, outcome=None if sibling else True)
    for index in (9, 13):
        b.add(f"daily_limit_{index}", b.when(index), [yard], counts=counter)
    b.model["proof"]["source_state_bindings"] = {
        "scheme.list.includes(519)": has_guild_handler,
        "superGlobal.daoguan_lose": first_loss,
        "Boolean(superGlobal.liao_activity_Switch)": activity_ready,
        "superGlobal.liao_activity_Switch.a_ctivity_dojo_again": activity_retry,
    }
    b.gap("super_global_lifecycle", (319, 324), vote,
          [{"effect": "source_persist_super_global_across_switch_and_rerun"}], True,
          ["bind 311/519 and preserve dojo superGlobal lifecycle"], blocking=False)
