"""Weekly sign-in and share-return handlers from assttyys (MIT, Chaos)."""
from .core_handlers import _push
from .handlers import _count
from .team_handlers import _all, _expr


def _navigate(b, label, guard, indices, counts=()):
    for index in indices:
        actions = b.actions(index)
        if actions:
            actions[0]["recheck"] = True
        b.add(f"{label}_{index}", _all(guard, b.when(index)), actions, counts=counts)


def _handoff_to_share_app(b, name, guard, index, lines, counts=()):
    condition = _all(guard, b.when(index))
    pending = b.gap(name, lines, condition,
        [{"effect": "source_external_share", "operator": index, "actions": b.actions(index)}], True,
        ["explicit scope for external share destination and content"])
    b.add(name, condition, [pending], counts=counts)


def _weekly_blue_ticket(b):
    b.model["vars"] = {"MT_share": "start", "MT_share_type": "mumu"}
    start = _expr("MT_share == 'start'")
    mumu = _expr("MT_share == 'start' and MT_share_type == 'mumu'")
    returning = _expr("MT_share == 'back'")
    counts = [_count(1100)]
    b.add("share_external_returned", _all(start, b.when(6)),
          [{**b.actions(6)[0], "recheck": True}, {"set": {"MT_share": repr("back")}}], counts=counts)
    _navigate(b, "share_gallery", start, (0, 1, 2, 11), counts)
    _navigate(b, "share_menu", mumu, (3,))
    _handoff_to_share_app(b, "share_wechat", mumu, 4, (181, 195))
    _navigate(b, "share_back", returning, (7, 8, 9), counts)
    b.add("share_gallery_finished", _all(returning, b.when(10)),
          [{"set": {"MT_share": repr("end")}}], counts=counts)


def _event_tickets(b):
    b.model["vars"] = {"day_chouKa": True, "event_ticket_checks": 0}
    active = _expr("day_chouKa")
    counts = [_count(518)]
    _navigate(b, "event_ticket_trial", active, (2, 3, 4, 5, 6, 7), counts)
    b.add("event_ticket_claimed", _all(active, b.when(8)), [], counts=counts)
    ad = _all(active, b.when(8), {"find": "皮肤广告关闭按钮", "region": [928, 99, 1225, 342]})
    # The pinned method returns at the preceding identical predicate.
    b.gap("event_ticket_unreachable_ad_cleanup", (222, 236), ad, [], False, [], blocking=False)
    _navigate(b, "event_ticket_prayer", active, (9, 10, 11, 12, 13), counts)
    purchase = _all(active, b.when(14))
    stop = b.gap("event_prayer_purchase", (238, 243), purchase,
          [{"effect": "source_purchase_sequence", "actions": b.actions(14)}], True,
          ["verify paid offer, price and account before purchase approval"])
    b.add("event_prayer_purchase", purchase, [stop], counts=counts)
    _navigate(b, "event_ticket_prayer", active, (15,), counts)

    summon = _all(active, b.when(0))
    checks = "event_ticket_checks"
    refresh = {"handler_control": {"op": "refresh"}}
    b.add("event_ticket_probe_start", {"not": summon}, outcome=False, internal=True, group="event_ticket_summon")
    b.add("event_ticket_probe", summon, [{"set": {checks: 0}}], outcome=None, internal=True, group="event_ticket_summon")
    b.add("event_ticket_collect", _all(summon, b.when(1)), [{**b.actions(1)[0], "recheck": True}],
          counts=[*counts, *counts])
    b.add("event_ticket_leave", _all(summon, _expr(f"{checks} == 2")),
          [refresh, {"set": {"day_chouKa": False}}], counts=counts, outcome=None)
    b.add("event_ticket_return", _all(_expr("not day_chouKa"), b.when(0)),
          [{**b.actions(0)[0], "recheck": True}], counts=counts)
    b.add("event_ticket_return_screen_changed", _expr("not day_chouKa"), outcome=False, internal=True)
    edge = "unresolved_source_obligation:team1108.retry_assembly requires team_workflow"
    b.add("event_ticket_retry", summon, [{"inc": checks}, refresh, {"wait": 2000}, {"fail": edge}],
          counts=counts, outcome=None, internal=True)
    b.model["proof"]["source_phase_edges"] = {"event_ticket_retry": {
        "target_case": "event_ticket_collect", "gate_prefix": edge}}


def _secret_and_area_share(b):
    b.model["vars"] = {"miWenshare": True, "diGuishare": False, "MT_share_type": "mumu"}
    secret = _expr("miWenshare")
    area = _expr("diGuishare")
    both = {"set": {"miWenshare": False, "diGuishare": True}}
    counts = [_count(1109)]
    _handoff_to_share_app(b, "secret_share_wechat", _expr("miWenshare and MT_share_type == 'mumu'"), 8, (231, 248))
    b.add("secret_share_receipt", _all(secret, b.when(9)),
          [{**b.actions(9)[0], "recheck": True}, both], counts=counts)
    _navigate(b, "secret_share_open", secret, (0, 2, 3, 4, 5), counts)
    _handoff_to_share_app(b, "secret_share_fallback_app", secret, 8, (289, 293), counts)
    ranking = _all(secret, b.when(6))
    b.add("secret_share_button", _all(ranking, b.when(7)), [{**b.actions(7)[0], "recheck": True}], counts=[*counts, *counts])
    b.gap("secret_no_completion_notice", (297, 313), ranking, [_push("你的秘闻似乎没有通关到十层")], True,
          ["authorized source notification or local ringtone"], blocking=False)
    b.add("secret_share_unavailable", ranking, [both, {"log": "未找到秘闻十层分享入口"}], counts=counts)
    b.add("area_share_receipt", _all(area, b.when(16)), [*b.actions(16), {"set": {"diGuishare": False}}], counts=counts)
    _navigate(b, "area_share_open", area, (0, 10, 11, 12, 13, 14), counts)
    _handoff_to_share_app(b, "area_share_wechat", area, 15, (325, 329), counts)
    _navigate(b, "completed_share_exit", _expr("True"), (10, 17, 18), counts)
    b.gap("share_android_close_id", (339, 347), {"idle_ms": 10000},
          [{"effect": "source viewId click", "id": "iv_close"}], True,
          ["bind Android view identity and verify the caller window"], blocking=False)


def build_weekly_reward(b):
    {1100: _weekly_blue_ticket, 1108: _event_tickets, 1109: _secret_and_area_share}[b.fid](b)
    b.model["proof"]["source_state_bindings"] = {f"global.{key}": key for key in b.model["vars"]
                                               if key != "event_ticket_checks"}
