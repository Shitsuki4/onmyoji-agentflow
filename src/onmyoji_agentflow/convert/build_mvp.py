"""Build the three MVP workflows (御魂 / 个人结界突破 / 探索) from converted assttyys data.

The states below are a hand translation of assttyys funcs (operator arrays
are taken verbatim from the converted ``funcs/*.yaml``; the ``operatorFunc``
logic of each func is re-expressed with conditions and counters). Each state
records the func/operator it comes from in ``from``. Running this module
regenerates ``data/workflows/*.yaml`` deterministically.

assttyys_autojs: MIT License, Copyright (c) 2019 Chaos.
"""
from __future__ import annotations

from pathlib import Path

from ..yamlio import dump_yaml, load_yaml

HEADER = ("# 由 onmyoji_agentflow.convert.build_mvp 从 assttyys_autojs 的识别数据生成，请勿手改坐标；\n"
          "# 需要调整时改 build_mvp.py 或交给 agent 监管修复（会在 git 分支上提交）。\n"
          "# 识别数据来源 https://github.com/zzliux/assttyys_autojs  MIT License, Copyright (c) 2019 Chaos\n")


class Funcs:
    def __init__(self, conv_dir: Path):
        self.dir = conv_dir
        self.colors = load_yaml(conv_dir / "colors.yaml")["resources"]
        self._cache: dict[int, dict] = {}

    def f(self, fid: int) -> dict:
        if fid not in self._cache:
            self._cache[fid] = load_yaml(self.dir / "funcs" / f"{fid:03d}.yaml")
        return self._cache[fid]

    def op(self, fid: int, idx: int) -> dict:
        return self.f(fid)["operators"][idx]

    def when(self, fid: int, idx: int) -> dict:
        o = self.op(fid, idx)
        if o.get("detect"):
            return {"res": o["detect"]}
        if o.get("detect_points"):
            return {"colors": o["detect_points"]}
        raise KeyError(f"func {fid} operator {idx} has no detection")

    def rect(self, fid: int, idx: int, k: int = 0) -> list:
        return self.op(fid, idx)["oper"][k]["rect"]

    def click(self, fid: int, idx: int, k: int = 0, **extra) -> dict:
        o = self.op(fid, idx)["oper"][k]
        d = {"click": o["rect"], "delay": o["delay"]}
        if o.get("press_ms"):
            d["press_ms"] = o["press_ms"]
        d.update(extra)
        return d

    def click_random(self, fid: int, idx: int, step: int = 0) -> dict:
        steps = self.op(fid, idx)["oper_step_random"][step]
        return {"click_random": [s["rect"] for s in steps], "delay": steps[0]["delay"]}


# A battle is "pending" from the click that starts it until any result screen (or the screen it was
# started from) shows up again. Counting on the first result screen of *any* kind matters: on real
# MuMu 12 devices the victory drum (002 #6) is often skipped or missed and the run goes straight
# to the 统计 / 达摩 screens, so counting only on the drum left ``done`` at 0 forever.
# ``started`` is set once the fight is actually seen (准备 / 战斗 screens), so the start screen still
# showing for a tick right after the click does not count as "back from the battle".
SETTLE_COUNT = {"done": "done + pending", "pending": 0, "started": 0}
BACK_COUNT = {"done": "done + started", "pending": "pending * (1 - started)", "started": 0}
CLICKED = {"pending": 1, "started": 0}
SEEN_FIGHT = {"started": "pending"}


def common_battle_states(F: Funcs, on_settle: dict | None = None) -> list[dict]:
    """assttyys 001 准备 / 002 退出结算 (the operators that matter for solo battles)."""
    count = on_settle or SETTLE_COUNT
    out = [
        {"id": "stamina_empty", "desc": "体力不足，停止", "from": "assttyys 002 #19",
         "when": F.when(2, 19), "do": [{"stop": "体力不足"}]},
    ]
    settle = [(6, "单人胜利太鼓"), (0, "左上角贪吃鬼"), (1, "左上角贪吃鬼(MuMu)"), (2, "已打开的达摩 1"),
              (3, "已打开的达摩 2"), (4, "已打开的达摩 3"), (11, "左上角统计图标"), (14, "掉落物金框")]
    for idx, label in settle:
        # a battle counts as done on the first result screen of any kind (first tick of the visit)
        out.append({"id": f"settle_{idx}", "desc": f"结算界面：{label}，点击退出", "from": f"assttyys 002 #{idx}",
                    "when": F.when(2, idx), "do": [{"set": dict(count), "first": True}, F.click_random(2, idx)],
                    "max_repeat": 10, "progress": True})
    lose_count = dict(count)
    if "pending" in lose_count:
        lose_count["losses"] = "losses + pending"
    else:
        lose_count["losses"] = "losses + 1"
    out += [
        {"id": "settle_lose", "desc": "单人失败太鼓，点击退出", "from": "assttyys 002 #9",
         "when": F.when(2, 9), "do": [{"set": lose_count, "first": True}, F.click_random(2, 9)],
         "max_repeat": 10, "progress": True},
        {"id": "settle_overflow", "desc": "御魂溢出确认框，点确认", "from": "assttyys 002 #13",
         "when": F.when(2, 13), "do": [F.click(2, 13)], "max_repeat": 5},
        {"id": "settle_cancel_box", "desc": "取消确认框，点确认", "from": "assttyys 002 #21",
         "when": F.when(2, 21), "do": [F.click(2, 21)], "max_repeat": 5},
        {"id": "battle_manual", "desc": "战斗中是手动状态，开启自动", "from": "assttyys 001 #1",
         "when": F.when(1, 1), "do": [{"set": SEEN_FIGHT, "first": True}, F.click(1, 1)], "max_repeat": 5},
        {"id": "prepare", "desc": "准备界面，点准备", "from": "assttyys 001 #0",
         "when": F.when(1, 0), "do": [{"set": SEEN_FIGHT, "first": True}, F.click(1, 0)], "max_repeat": 10},
        # A long fight (a weak team on 八岐大蛇 叁层 easily takes over a minute) must not trip the
        # 60 s unknown-screen limit: the in-battle screen is a known state that just waits.
        {"id": "in_battle", "desc": "战斗中（自动），等待", "from": "assttyys 资源 战斗界面",
         "when": {"res": "战斗界面"}, "do": [{"set": SEEN_FIGHT, "first": True}, {"wait": 1000}],
         "max_repeat": 3600},
    ]
    return out


LIMITS = {"timeout_s": 4 * 3600, "unknown_timeout_s": 60, "stuck_timeout_s": 120,
          "no_progress_timeout_s": 600, "max_repeat": 20}


def build_orochi(F: Funcs) -> dict:
    return {
        "format": 1, "name": "orochi", "title": "御魂（个人）",
        "desc": "在御魂挑战界面反复挑战，达到次数或体力不足时停止。对应 assttyys 方案「个人御魂」里的 001 准备、002 退出结算、006 御魂/御灵/秘闻挑战。",
        "resources": ["assttyys/colors.yaml"],
        "similarity": 93,
        "params": {"max_runs": {"default": 30, "min": 1, "max": 999, "desc": "挑战次数"}},
        "vars": {"runs": 0, "done": 0, "losses": 0, "pending": 0, "started": 0},
        "limits": dict(LIMITS),
        "stop_when": "done >= max_runs",
        "states": common_battle_states(F) + [
            # back on the challenge screen with every run used: the last battle is over, stop
            {"id": f"challenge_done_{k}", "desc": "挑战界面，次数已打满，结束", "from": f"assttyys 006 #{k}",
             "when": {"all": [F.when(6, k), {"expr": "runs >= max_runs and (pending == 0 or started == 1)"}]},
             "do": [{"set": BACK_COUNT, "first": True}, {"wait": 1500}],
             "max_repeat": 2, "on_repeat": "stop", "repeat_reason": "挑战次数已打满，停止"}
            for k in range(len(F.f(6)["operators"]))
        ] + [
            {"id": f"challenge_{k}", "desc": "挑战界面，点挑战", "from": f"assttyys 006 #{k}",
             # assttyys 006: if the challenge screen is still there after 3 clicks, stop
             # (the second half keeps retrying the last click while the battle has not started)
             "when": {"all": [F.when(6, k), {"expr": "runs < max_runs or (pending == 1 and started == 0)"}]},
             "do": [{"set": BACK_COUNT, "first": True}, F.click(6, k),
                    {"inc": "runs", "first": True}, {"set": CLICKED, "first": True}],
             "max_repeat": 3, "on_repeat": "stop", "repeat_reason": "连续 3 次点挑战没反应（可能体力不足），停止",
             "progress": True}
            for k in range(len(F.f(6)["operators"]))
        ],
    }


MEDAL_ORDER = ["呱太", "4", "5", "3", "2", "1", "0"]  # assttyys 009 default priority


def build_realm_raid(F: Funcs) -> dict:
    attack_off = F.rect(8, 0, 0)        # [0, 0, 119, 49]
    medal_off = F.rect(9, 0, 0)         # [30, 10, 160, 80]
    states = common_battle_states(F) + [
        {"id": "attack", "desc": "已选中结界（界面变暗），点进攻", "from": "assttyys 008 #1 + 结界_进攻",
         "when": {"all": [F.when(8, 1), {"find": "结界_进攻", "region": F.rect(8, 0, 2)},
                          {"expr": "runs < max_runs or (pending == 1 and started == 0)"}]},
         "do": [{"click_found": True, "offset": attack_off, "delay": F.op(8, 0)["oper"][0]["delay"]},
                {"inc": "runs", "first": True}, {"set": CLICKED, "first": True}],
         # assttyys 008 counts the clicks and stops the script when attacking keeps failing
         "max_repeat": 3, "on_repeat": "stop", "repeat_reason": "连续 3 次点进攻没反应（可能突破券用完），停止",
         "progress": True},
    ]
    for m in MEDAL_ORDER:
        states.append({
            "id": f"medal_{m}", "desc": f"突破界面，选 {m} 勋章的结界", "from": "assttyys 009 #0",
            "when": {"all": [F.when(9, 0), {"find": f"结界_{m}勋章"}, {"expr": "runs < max_runs"}]},
            "do": [{"set": BACK_COUNT, "first": True},
                   {"click_found": True, "offset": medal_off, "delay": F.op(9, 0)["oper"][0]["delay"]}],
            "max_repeat": 6})
    states.insert(len(states) - len(MEDAL_ORDER), {
        "id": "raid_done", "desc": "回到突破界面，次数已打满，结束", "from": "assttyys 009 #0",
        "when": {"all": [F.when(9, 0), {"expr": "runs >= max_runs and (pending == 0 or started == 1)"}]},
        "do": [{"set": BACK_COUNT, "first": True}, {"wait": 1500}],
        "max_repeat": 2, "on_repeat": "stop", "repeat_reason": "进攻次数已打满，停止"})
    states.append({"id": "all_broken", "desc": "突破界面上找不到可打的结界，停止", "from": "assttyys 009 #0",
                   "when": F.when(9, 0), "do": [{"wait": 1500}],
                   "max_repeat": 3, "on_repeat": "stop", "repeat_reason": "本页结界都打过了（刷新要等冷却，不自动刷新）"})
    return {
        "format": 1, "name": "realm_raid", "title": "个人结界突破",
        "desc": ("在个人结界突破界面按「呱太->4->5->3->2->1->0」勋章顺序选结界并进攻，"
                 "进攻连续无反应（突破券用完）或达到次数后停止。由 assttyys 008/009 翻译；"
                 "「打九退四」、自动刷新、锁定阵容没有做。"),
        "requires": ["账号已加入阴阳寮（没入寮时进不了结界突破，会提示先加入阴阳寮）"],
        "resources": ["assttyys/colors.yaml"],
        "similarity": 93,
        "params": {"max_runs": {"default": 30, "min": 1, "max": 300, "desc": "进攻次数上限"}},
        "vars": {"runs": 0, "done": 0, "losses": 0, "pending": 0, "started": 0},
        "limits": dict(LIMITS),
        "stop_when": "done >= max_runs",
        "states": states,
        # The 「暂未加入任何阴阳寮，是否前往申请加入？」 prompt (no counterpart in assttyys/OAS).
        # Points taken by the agent on a real Win10 + MuMu 12 screenshot (1280x720, RGB hex) and
        # checked there: all match the prompt, none match the 御魂 / 探索 / 庭院 screens.
        "blockers": [{
            "id": "no_guild",
            "desc": "点结界突破时弹出「暂未加入任何阴阳寮，是否前往申请加入？」",
            "when": {"colors": [
                [451, 428, "#da624a"], [481, 426, "#d9614a"],      # red 取消
                [679, 422, "#e9b05e"], [688, 452, "#e9b05e"],      # yellow 前往申请
                [450, 362, "#d9c5ae"], [490, 362, "#d9c5ae"], [530, 362, "#d9c5ae"],  # dialog
                [470, 240, "#c6b19c"], [700, 240, "#c6b29b"],      # title bar
                [1140, 627, "#4d472f"],                            # dimmed background
            ]},
            "message": "账号还没加入阴阳寮，进不了个人结界突破。请先在游戏里加入一个阴阳寮再运行",
        }],
    }


def build_exploration(F: Funcs) -> dict:
    op0 = F.op(14, 0)["oper"]
    icon_off = op0[0]["rect"]           # [0, 0, 42, 51] added to the found icon
    swipe_from, swipe_to = op0[1]["rect"], op0[2]["rect"]
    explore_map = F.when(14, 0)
    states = common_battle_states(F, {"rounds": "rounds + boss", "boss": 0}) + [
        {"id": "boss_appeared", "desc": "首领出现，点首领", "from": "assttyys 014 #2",
         "when": F.when(14, 2), "do": [{"wait": 1000}, F.click(14, 2), {"set": {"boss": 1, "swipes": 0}}], "max_repeat": 4, "progress": True},
        {"id": "challenge_boss", "desc": "地图里有首领挑战图标，点它", "from": "assttyys 014 探索_挑战BOSS",
         "when": {"all": [explore_map, {"find": "探索_挑战BOSS"}]},
         "do": [{"click_found": True, "offset": icon_off, "delay": op0[0]["delay"]}, {"set": {"boss": 1, "swipes": 0}}],
         "max_repeat": 4, "progress": True},
        {"id": "challenge", "desc": "地图里有小怪挑战图标（无差别），点它", "from": "assttyys 014 探索_挑战",
         "when": {"all": [explore_map, {"find": "探索_挑战"}]},
         "do": [{"click_found": True, "offset": icon_off, "delay": op0[0]["delay"]}, {"set": {"swipes": 0}}],
         "max_repeat": 4, "progress": True},
        {"id": "swipe_map", "desc": "当前屏幕没有挑战图标，向左划地图", "from": "assttyys 014 regionBezierSwipe",
         "when": {"all": [explore_map, {"expr": "swipes < max_swipes"}]},
         "do": [{"swipe": {"from": swipe_from, "to": swipe_to}, "duration_ms": [800, 1200], "delay": 200},
                {"inc": "swipes"}], "max_repeat": 40},
        {"id": "leave_map", "desc": "划了 max_swipes 次还没怪，点左上角返回并确认退出", "from": "assttyys 014 #0 oper[3]/[4]",
         "when": explore_map,
         "do": [{"click": op0[3]["rect"], "delay": op0[3]["delay"]}, {"click": op0[4]["rect"], "delay": op0[4]["delay"]},
                {"set": {"swipes": 0}}], "max_repeat": 3},
        {"id": "chest", "desc": "章节界面有宝箱，先领宝箱", "from": "assttyys 014 #4 + 探索_宝箱",
         "when": {"all": [F.when(14, 4), {"find": "探索_宝箱"}]},
         "do": [{"click_found": True, "offset": [0, 0, 10, 10], "delay": 500}], "max_repeat": 4},
        {"id": "enter_normal", "desc": "章节界面（普通），点探索进入", "from": "assttyys 014 #4",
         "when": F.when(14, 4), "do": [F.click(14, 4)], "max_repeat": 5},
        {"id": "enter_hard", "desc": "章节界面（困难），点探索进入", "from": "assttyys 014 #3",
         "when": F.when(14, 3), "do": [F.click(14, 3)], "max_repeat": 5},
        {"id": "misc_5", "desc": "探索界面杂项弹窗", "from": "assttyys 014 #5",
         "when": F.when(14, 5), "do": [F.click(14, 5)], "max_repeat": 5},
        {"id": "misc_6", "desc": "探索界面杂项弹窗", "from": "assttyys 014 #6",
         "when": F.when(14, 6), "do": [F.click(14, 6)], "max_repeat": 5},
        {"id": "chapter_map", "desc": "探索章节地图，点要打的章节（坐标可改 chapter_xy）", "from": "assttyys 014 #1",
         "when": {"res": "探索地图界面"},
         "do": [{"click": "chapter_xy", "delay": 1000}], "max_repeat": 5},
    ]
    return {
        "format": 1, "name": "exploration", "title": "探索（个人）",
        "desc": ("在探索地图里优先打首领，其次打小怪（无差别），没怪时划动地图，划满次数后退出重进。"
                 "由 assttyys 方案「个人探索」的 014 翻译；「打经验」「打掉落」模式没有做。"),
        "resources": ["assttyys/colors.yaml"],
        "inline_resources": {"chapter_xy": {"type": "click", "rect": [1146, 491, 1166, 511],
                                            "desc": "章节坐标，默认 1156,501 (assttyys 014 xy 默认值)"}},
        "similarity": 93,
        "params": {"max_rounds": {"default": 20, "min": 1, "max": 500, "desc": "探索轮数（打完首领算一轮）"},
                   "max_swipes": {"default": 4, "min": 1, "max": 30, "desc": "没怪时最多划几次再退出（assttyys 默认 4）"}},
        "vars": {"rounds": 0, "boss": 0, "losses": 0, "swipes": 0, "pending": 0, "started": 0},
        "limits": dict(LIMITS),
        "stop_when": "rounds >= max_rounds",
        "states": states,
    }


BUILDERS = {"orochi": build_orochi, "realm_raid": build_realm_raid, "exploration": build_exploration}


def build_all(conv_dir: str | Path, out_dir: str | Path) -> list[Path]:
    F = Funcs(Path(conv_dir))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, fn in BUILDERS.items():
        p = out / f"{name}.yaml"
        p.write_text(HEADER + dump_yaml(fn(F)), encoding="utf-8")
        written.append(p)
    return written
