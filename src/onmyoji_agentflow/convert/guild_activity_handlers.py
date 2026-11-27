"""Guarded native guild activity handlers (601, 604, 606).

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

from .core_handlers import _rerun


def build_guild_hunt(b):
    """Build native model for 601_狩猎战."""
    challenge = b.actions(0)
    b.add("kirin_challenge", b.when(0), [{**challenge[0], "recheck": True}, *challenge[1:]])

    done_acts = b.actions(1)
    done_rerun = b.gap(
        "hunt_done_rerun",
        (50, 56),
        {"screen": "hunt_already_challenged"},
        [_rerun("返回庭院")],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    b.add("hunt_done_return_yard", b.when(1), [{**done_acts[0], "recheck": True}, *done_acts[1:], done_rerun])


def build_guild_boss_retreat(b):
    """Build native model for 604_首领退治."""
    challenge = b.actions(0)
    b.add("retreat_challenge", b.when(0), [{**challenge[0], "recheck": True}, *challenge[1:]])

    leave_acts = b.actions(1)
    done_rerun = b.gap(
        "retreat_done_rerun",
        (44, 52),
        {"screen": "guild_info"},
        [_rerun("返回庭院"), {"effect": "sleep", "ms": 1000}],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    b.add("retreat_done_return_yard", b.when(1), [{**leave_acts[0], "recheck": True}, *leave_acts[1:], done_rerun])


def build_gate_of_hades(b):
    """Build native model for 606_阴界之门."""
    for idx in (0, 1, 4, 5):
        acts = b.actions(idx)
        b.add(f"gate_entry_{idx}", b.when(idx), [{**acts[0], "recheck": True}, *acts[1:]])

    round36_acts = b.actions(2)
    b.add("gate_round36_confirm", b.when(2), [{**round36_acts[0], "recheck": True}, *round36_acts[1:]])

    done_acts = b.actions(3)
    done_rerun = b.gap(
        "gate_done_rerun",
        (122, 128),
        {"screen": "gate_completed_popup"},
        [_rerun("返回庭院")],
        True,
        ["bind 返回庭院 scheme rerun"],
    )
    b.add("gate_done_return_yard", b.when(3), [{**done_acts[0], "recheck": True}, *done_acts[1:], done_rerun])
