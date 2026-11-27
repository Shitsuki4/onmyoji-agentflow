"""Guarded native Six Realms Shouzu handler (316), assttyys (MIT, Copyright (c) 2019 Chaos)."""
from __future__ import annotations

from .core_handlers import _push, _rerun
from .handlers import _count
from .team_handlers import _all, _expr


def build_six_realms_shouzu(b):
    """Build native model for 316_六道椒图."""
    roufeng = "d6RouFeng"
    loop_var = "d6Loop"
    times_var = "d6_times"

    b.model["vars"] = {
        roufeng: 0,
        loop_var: 0,
        times_var: 0,
    }
    counted = [_count(316)]

    def taps(idx):
        acts = b.actions(idx)
        return [{**acts[0], "recheck": True}, *acts[1:]]

    # Lines 547-558: event selection (op[0] or op[2], retest=200)
    event_screen = {"any": [b.when(0), b.when(2)]}
    b.add(
        "event_select_found",
        _all(event_screen, {"find": "六道椒图_事件"}),
        [{"click_found": True, "offset": [-40, 20, 40, 80], "delay": 200, "recheck": True}],
        counts=counted,
        retest_ms=200,
    )
    b.add(
        "event_select_miss",
        event_screen,
        [],
        counts=counted,
        retest_ms=200,
        outcome=False,
    )

    # Lines 560-604: buff choice screen (op[4])
    buff_screen = b.when(4)
    need_roufeng = _expr(f"{roufeng} < 5")
    b.add(
        "buff_upgrade",
        _all(buff_screen, need_roufeng, {"find": "六道椒图_升级buff"}),
        [{"click_found": True, "offset": [-40, 410, 70, 440], "delay": 500, "recheck": True}, {"inc": roufeng}],
        counts=counted,
    )
    b.add(
        "buff_low_skip",
        _all(buff_screen, need_roufeng, b.when(25)),
        taps(4),
        counts=counted,
    )
    for idx in (17, 18):
        b.add(
            f"buff_refresh_{idx}",
            _all(buff_screen, need_roufeng, b.when(idx)),
            taps(idx),
            counts=counted,
        )
    b.add("buff_skip_fallback", buff_screen, taps(4), counts=counted)

    # Lines 606-616: shop confirm buy (op[23])
    acts23 = b.actions(23)
    b.add(
        "shop_confirm_buy",
        b.when(23),
        [{**acts23[0], "recheck": True}, acts23[1], {"inc": roufeng}],
        counts=counted,
    )

    # Lines 617-644: shop buy buff (op[7])
    shop_exit = acts23[1]
    b.add(
        "shop_buy_buff",
        _all(b.when(7), need_roufeng, {"find": "六道椒图_购买buff"}),
        [{"click_found": True, "offset": [-10, 50, 10, 140], "delay": 500, "recheck": True}, shop_exit],
        counts=counted,
        outcome=None,
    )
    b.add(
        "shop_exit",
        b.when(7),
        [{**shop_exit, "recheck": True}],
        counts=counted,
    )

    # Lines 646-656: mystery forge (op[15])
    b.add(
        "mystery_forge",
        b.when(15),
        [*taps(15), {"inc": roufeng}],
        counts=counted,
    )

    # Lines 658-676: onlyDouble stop check (op[9] + op[33])
    double_stop_gap = b.gap(
        "only_double_exhausted_stop",
        (659, 676),
        {"config": "onlyDouble", "double_remaining": 0},
        [_rerun("__停止脚本__")],
        True,
        ["source stop lifecycle via __停止脚本__"],
    )
    b.add(
        "only_double_stop",
        _all(_expr("onlyDouble"), b.when(9), b.when(33)),
        [double_stop_gap],
        counts=counted,
    )

    # Lines 678-689: full roufeng detection (op[34])
    b.add(
        "roufeng_full_detect",
        _all(need_roufeng, b.when(34)),
        [{"set": {roufeng: 5}}],
        counts=counted,
        outcome=None,
        internal=True,
    )

    # Lines 691-703: individual event steps
    for idx in (3, 5, 6, 8, 9, 10, 12, 13, 14, 19, 20, 21, 22, 26, 27, 28, 29, 30, 31, 32):
        b.add(f"event_step_{idx}", b.when(idx), taps(idx), counts=counted)

    # Lines 704-722: start new run (op[11], 60 stamina)
    b.add(
        "start_reset_run",
        b.when(11),
        [*taps(11), {"set": {loop_var: 0, roufeng: 1}}, {"inc": times_var}],
        counts=counted,
    )

    # Lines 724-757: finish screen (op[16])
    reached_over = _expr(f"overTimes > 0 and {times_var} >= overTimes")
    push_and_rerun = b.gap(
        "finish_push_and_rerun",
        (742, 755),
        {"pushResult": True, "overTimes_reached": True},
        [_push("六道椒图通关汇总"), {"effect": "sleep", "ms": 2000}, _rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 3000}],
        None,
        ["source Push", "bind next_scheme rerun"],
    )
    push_only = b.gap(
        "finish_push_only",
        (742, 750),
        {"pushResult": True, "overTimes_reached": False},
        [_push("六道椒图通关汇总"), {"effect": "sleep", "ms": 2000}],
        True,
        ["source Push"],
    )
    rerun_only = b.gap(
        "finish_over_times_rerun",
        (751, 755),
        {"pushResult": False, "overTimes_reached": True},
        [_rerun({"config": "next_scheme"}), {"effect": "sleep", "ms": 3000}],
        None,
        ["bind next_scheme rerun"],
    )
    b.add(
        "finish_push_and_rerun",
        _all(b.when(16), _expr("pushResult"), reached_over),
        [*taps(16), push_and_rerun],
        counts=counted,
    )
    b.add(
        "finish_push_only",
        _all(b.when(16), _expr("pushResult")),
        [*taps(16), push_only],
        counts=counted,
    )
    b.add(
        "finish_rerun_only",
        _all(b.when(16), reached_over),
        [*taps(16), rerun_only],
        counts=counted,
    )
    b.add(
        "finish_continue",
        b.when(16),
        taps(16),
        counts=counted,
    )

    proof = b.model["proof"]
    proof["source_state_bindings"] = {
        "global.d6RouFeng": roufeng,
        "global.d6Loop": loop_var,
        "global.times": times_var,
    }
    proof["source_retest"] = {"event_select_retest_ms": 200}
