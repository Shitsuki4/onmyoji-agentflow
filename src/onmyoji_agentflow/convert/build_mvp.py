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
    # 御魂 柒层 and up (seen on 拾层, 2026-11-17) and the 超鬼王 event put up a result panel of their own:
    # 「通关时间 00:35」 + 「今日已获得裂变之眼」 + 「点击屏幕继续」, none of the assttyys result colours match it.
    out.append({"id": "settle_continue", "desc": "结算界面：通关时间 / 活动结算面板（点击屏幕继续），点击继续",
                "from": "实机 MuMu 12 拾层截图",
                "when": {"text": "点击屏幕继续", "region": [480, 640, 320, 80]},
                "do": [{"set": dict(count), "first": True}, {"click": [540, 600, 740, 690], "delay": 1500}],
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


# ---------------------------------------------------------------- navigation (OCR text conditions)
# Taken on a real Win10 + MuMu 12 (1280x720, 新版界面) account; see docs/玩法说明.md.
COURTYARD = {"all": [{"text": "式神录", "region": [1080, 640, 110, 55]},
                     {"text": "阴阳寮", "region": [515, 640, 120, 55]}]}
COURTYARD_EXPLORE = {"text": "探索", "region": [250, 120, 900, 230]}   # the 探索 lantern (skips the chat ticker)
EXPLORE_MAP = {"res": "探索地图界面"}
# 「确定要退出游戏？」 (a back press too many in the courtyard): always answer 取消
EXIT_DIALOG_STATE = {
    "id": "exit_dialog", "desc": "「确定要退出游戏？」弹框，点取消",
    "when": {"all": [{"text": "退出游戏", "region": [330, 315, 330, 60]}, {"text": "取消", "region": [740, 415, 130, 50]}]},
    "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 1500}], "max_repeat": 3}


def nav_states(guard: str, target: str, target_rect: list, target_desc: str) -> list:
    """Courtyard -> 探索大地图 -> ``target`` (a bottom-bar entry of the big exploration map).

    Lowest priority: only used when no in-game state of the workflow matched, and only while
    ``guard`` (e.g. ``runs < max_runs``) holds, so a finished run never walks back in."""
    return [
        dict(EXIT_DIALOG_STATE),
        {"id": f"nav_{target}", "desc": f"探索大地图，点底部「{target_desc}」",
         "when": {"all": [{"expr": guard}, EXPLORE_MAP]},
         "do": [{"click": f"nav_{target}", "delay": 1500}], "max_repeat": 3},
        {"id": "nav_courtyard", "desc": "在庭院，点「探索」灯笼进探索大地图",
         "when": {"all": [{"expr": guard}, COURTYARD, COURTYARD_EXPLORE]},
         "do": [{"click_found": True, "offset": [-12, -8, 12, 8], "delay": 2500}], "max_repeat": 3},
    ], {f"nav_{target}": {"type": "click", "rect": target_rect,
                          "desc": f"探索大地图底部「{target_desc}」入口（新版界面实机坐标）"}}


# 八岐大蛇 challenge screen: layer list on the left (壹..陆), text centres measured by OCR on the real device
OROCHI_LAYER_Y = [126, 231, 335, 438, 542, 645]


def build_orochi(F: Funcs) -> dict:
    nav, nav_inline = nav_states("runs < max_runs", "soul", [165, 676, 195, 704], "御魂")
    nav_inline["nav_orochi_card"] = {"type": "click", "rect": [105, 440, 145, 500],
                                     "desc": "御魂选择界面最左边的八岐大蛇卡片（实机坐标）"}
    layer_states = [
        {"id": f"layer_{n}", "desc": f"八岐大蛇挑战界面，先选第 {n} 层",
         "when": {"all": [{"expr": f"layer == {n} and layer_set == 0 and runs == 0"},
                          {"text": "岐大", "region": [0, 90, 100, 150]}]},
         "do": [{"click": [110, y - 12, 170, y + 12], "delay": 1000}, {"set": {"layer_set": 1}}], "max_repeat": 2}
        for n, y in enumerate(OROCHI_LAYER_Y, start=1)] + [
        # 柒..拾 层 sit lower in the scrolled list: find the layer name by OCR and click it
        {"id": f"layer_{n}", "desc": f"八岐大蛇挑战界面，先选第 {n} 层（按文字找）",
         "when": {"all": [{"expr": f"layer == {n} and layer_set == 0 and runs == 0"},
                          {"text": "岐大", "region": [0, 90, 100, 150]},
                          {"text": f"{cn}层", "region": [95, 90, 140, 620]}]},
         "do": [{"click_found": True, "offset": [-20, -10, 20, 10], "delay": 1000}, {"set": {"layer_set": 1}}],
         "max_repeat": 2}
        for n, cn in ((7, "柒"), (8, "捌"), (9, "玖"), (10, "拾"))]
    return {
        "format": 1, "name": "orochi", "title": "御魂（个人）",
        "desc": "在御魂挑战界面反复挑战，达到次数或体力不足时停止。对应 assttyys 方案「个人御魂」里的 001 准备、002 退出结算、006 御魂/御灵/秘闻挑战。",
        "resources": ["assttyys/colors.yaml"],
        "similarity": 93,
        "params": {"max_runs": {"default": 30, "min": 1, "max": 999, "desc": "挑战次数"},
                   "layer": {"default": 0, "min": 0, "max": 10,
                             "desc": "八岐大蛇第几层（1-10；7-10 层按文字在列表里找；0 = 不动，用游戏里当前选中的层）"}},
        "vars": {"runs": 0, "done": 0, "losses": 0, "pending": 0, "started": 0, "layer_set": 0},
        "limits": dict(LIMITS),
        "inline_resources": nav_inline,
        # no stop_when: stop on the challenge / raid screen once the runs are used up, never on a result screen
        "counts": {"done": "max_runs"},
        "states": common_battle_states(F) + layer_states + [
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
        ] + [
            {"id": "nav_orochi", "desc": "御魂选择界面（右下角「掉落日历」），点最左边的「八岐大蛇」",
             "when": {"all": [{"expr": "runs < max_runs"}, {"text": "御魂", "region": [140, 15, 100, 45]},
                              {"text": "掉落日历", "region": [1140, 665, 135, 50]}]},
             "do": [{"click": "nav_orochi_card", "delay": 2500}], "max_repeat": 3},
        ] + nav,
    }


MEDAL_ORDER = ["呱太", "4", "5", "3", "2", "1", "0"]  # assttyys 009 default priority
MEDAL_ORDER_WEAK = ["呱太", "0", "1", "2", "3", "4", "5"]  # fewest medals first


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
    # weak_first=1: fewest medals first (fewer medals usually = weaker defence), the order the
    # 「挑最弱的 3 个打完就刷新」 strategy needs; weak_first=0 keeps the assttyys order.
    for order, flag in ((MEDAL_ORDER, 0), (MEDAL_ORDER_WEAK, 1)):
        for m in order:
            states.append({
                "id": f"medal_{m}" + ("_weak" if flag else ""), "desc": f"突破界面，选 {m} 勋章的结界",
                "from": "assttyys 009 #0",
                "when": {"all": [F.when(9, 0), {"find": f"结界_{m}勋章"},
                                 {"expr": f"runs < max_runs and weak_first == {flag}"}]},
                "do": [{"set": BACK_COUNT, "first": True},
                       {"click_found": True, "offset": medal_off, "delay": F.op(9, 0)["oper"][0]["delay"]}],
                "max_repeat": 6})
    states.insert(len(states) - 2 * len(MEDAL_ORDER), {
        "id": "raid_done", "desc": "回到突破界面，次数已打满，结束", "from": "assttyys 009 #0",
        "when": {"all": [F.when(9, 0), {"expr": "runs >= max_runs and (pending == 0 or started == 1)"}]},
        "do": [{"set": BACK_COUNT, "first": True}, {"wait": 1500}],
        "max_repeat": 2, "on_repeat": "stop", "repeat_reason": "进攻次数已打满，停止"})
    # every 结界 on the page broken (no medal left): refresh when allowed, or say the refresh is cooling down
    states += [
        {"id": "refresh_confirm", "desc": "「刷新后攻破记录进度将重置，确定吗？」点确定",
         "when": {"all": [{"text": "刷新后", "region": [400, 270, 480, 80]}, {"text": "确定", "region": [690, 410, 130, 55]}]},
         "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 2000}], "max_repeat": 2},
        {"id": "refresh_cooling", "desc": "本页都打过了，刷新按钮在冷却（显示倒计时），停止",
         "when": {"all": [F.when(9, 0), {"expr": "runs < max_runs"},
                          {"text": "", "pattern": r"刷新\d{1,2}[:：]\d{2}", "region": [990, 575, 130, 45]}]},
         "do": [{"wait": 1500}], "max_repeat": 2, "on_repeat": "stop",
         "repeat_reason": "本页结界都打过了，刷新还在冷却（5 分钟），停止"},
        {"id": "refresh", "desc": "本页都打过了，点「刷新」换一页（auto_refresh=1 时）",
         "when": {"all": [F.when(9, 0), {"expr": "runs < max_runs and auto_refresh == 1 and refreshes < max_refresh"},
                          {"text": "刷新", "region": [990, 575, 130, 45]}]},
         "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 1500}, {"inc": "refreshes"},
                {"set": {"page_base": "done - losses"}}],
         "max_repeat": 2},
    ]
    states.append({"id": "all_broken", "desc": "突破界面上找不到可打的结界，停止", "from": "assttyys 009 #0",
                   "when": F.when(9, 0), "do": [{"wait": 1500}],
                   "max_repeat": 3, "on_repeat": "stop", "repeat_reason": "本页结界都打过了（没有开自动刷新，或刷新次数已用完）"})
    # a lost 结界 keeps its medal, so the medal states would attack the same one again and again:
    # after ``lose_limit`` losses in a row refresh the page (if allowed and not cooling down) or stop
    for st in states:
        if st["id"].startswith("settle_") and st["id"] not in ("settle_overflow", "settle_cancel_box"):
            val = "streak + 1" if st["id"] == "settle_lose" else "0"
            st["do"].insert(0, {"set": {"streak": val}, "first": True})
    lose = "streak >= lose_limit and runs < max_runs"
    lose_states = [
        {"id": "lose_cooling", "desc": f"连续打输，刷新还在冷却，停止",
         "when": {"all": [F.when(9, 0), {"expr": lose},
                          {"text": "", "pattern": r"刷新\d{1,2}[:：]\d{2}", "region": [990, 575, 130, 45]}]},
         "do": [{"wait": 1000}], "max_repeat": 2, "on_repeat": "stop",
         "repeat_reason": "连续打输，打不过本页剩下的结界，刷新还在冷却（5 分钟），停止"},
        {"id": "lose_refresh", "desc": "连续打输，点「刷新」换一页",
         "when": {"all": [F.when(9, 0), {"expr": lose + " and auto_refresh == 1 and refreshes < max_refresh"},
                          {"text": "刷新", "region": [990, 575, 130, 45]}]},
         "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 1500}, {"inc": "refreshes"},
                {"set": {"streak": 0, "page_base": "done - losses"}}], "max_repeat": 2},
        {"id": "lose_stop", "desc": "连续打输，又不能刷新，停止",
         "when": {"all": [F.when(9, 0), {"expr": lose}]},
         "do": [{"stop": "连续打输，打不过本页剩下的结界（没开自动刷新，或刷新次数已用完），停止"}]},
    ]
    # 「挑最弱的 3 个，打完就刷新」: 3 breaks on a page already pay the 5 勾玉, so refresh instead of
    # fighting the harder rest (wins_per_page=0 turns it off). Low win rate this run -> stop and keep
    # the tickets (min_win_pct=0 turns it off; only judged after min_rate_n battles).
    quota = "wins_per_page > 0 and done - losses - page_base >= wins_per_page and runs < max_runs"
    rate = "min_win_pct > 0 and done >= min_rate_n and (done - losses) * 100 < min_win_pct * done"
    guard_states = [
        {"id": "win_rate_stop", "desc": "本轮胜率太低，停手留突破券",
         "when": {"all": [F.when(9, 0), {"expr": rate}]},
         "do": [{"stop": "本轮结界突破胜率低于下限，停手留券（胜率低）"}]},
        {"id": "page_quota_cooling", "desc": "本页已拿满 3 胜奖励，刷新还在冷却，停止",
         "when": {"all": [F.when(9, 0), {"expr": quota},
                          {"text": "", "pattern": r"刷新\d{1,2}[:：]\d{2}", "region": [990, 575, 130, 45]}]},
         "do": [{"wait": 1000}], "max_repeat": 2, "on_repeat": "stop",
         "repeat_reason": "本页已打下够数的结界，刷新还在冷却（5 分钟），停止"},
        {"id": "page_quota_refresh", "desc": "本页已打下够数的结界（拿到攻破 3 个的奖励），点「刷新」换一页",
         "when": {"all": [F.when(9, 0), {"expr": quota + " and auto_refresh == 1 and refreshes < max_refresh"},
                          {"text": "刷新", "region": [990, 575, 130, 45]}]},
         "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 1500}, {"inc": "refreshes"},
                {"set": {"streak": 0, "page_base": "done - losses"}}], "max_repeat": 2},
        {"id": "page_quota_stop", "desc": "本页已打下够数的结界，又不能刷新，停止",
         "when": {"all": [F.when(9, 0), {"expr": quota}]},
         "do": [{"stop": "本页已打下够数的结界，刷新次数已用完（或没开自动刷新），停止"}]},
    ]
    first_medal = next(i for i, st in enumerate(states) if st["id"].startswith("medal_"))
    states[first_medal:first_medal] = guard_states + lose_states
    nav, nav_inline = nav_states("runs < max_runs", "raid", [266, 676, 296, 704], "结界突破")
    states += nav
    return {
        "format": 1, "name": "realm_raid", "title": "个人结界突破",
        "desc": ("在个人结界突破界面按「呱太->4->5->3->2->1->0」勋章顺序选结界并进攻，"
                 "进攻连续无反应（突破券用完）或达到次数后停止；本页打完会自动刷新（冷却中就停止）。"
                 "由 assttyys 008/009 翻译；「打九退四」、锁定阵容没有做。"),
        "requires": ["账号已加入阴阳寮（没入寮时进不了结界突破，会提示先加入阴阳寮）"],
        "resources": ["assttyys/colors.yaml"],
        "similarity": 93,
        "params": {"max_runs": {"default": 30, "min": 1, "max": 300, "desc": "进攻次数上限"},
                   "auto_refresh": {"default": 1, "min": 0, "max": 1, "desc": "本页打完自动刷新（1 开 / 0 关）"},
                   "max_refresh": {"default": 3, "min": 0, "max": 50, "desc": "一次运行最多刷新几次"},
                   "lose_limit": {"default": 2, "min": 1, "max": 30, "desc": "连续打输几次就换一页（或停止）"},
                   "weak_first": {"default": 0, "min": 0, "max": 1,
                                  "desc": "1 = 先打勋章最少的结界（通常最弱）；0 = assttyys 默认顺序"},
                   "wins_per_page": {"default": 0, "min": 0, "max": 9,
                                     "desc": "每页打下几个就刷新（3 = 拿到攻破 3 个的 5 勾玉就换页；0 关）"},
                   "min_win_pct": {"default": 0, "min": 0, "max": 100,
                                   "desc": "本轮胜率低于这个百分比就停手留券（0 关）"},
                   "min_rate_n": {"default": 4, "min": 1, "max": 50,
                                  "desc": "打满几场之后才按胜率判断"}},
        "vars": {"runs": 0, "done": 0, "losses": 0, "pending": 0, "started": 0, "refreshes": 0, "streak": 0,
                 "page_base": 0},
        "limits": dict(LIMITS),
        "inline_resources": nav_inline,
        # no stop_when: stop on the challenge / raid screen once the runs are used up, never on a result screen
        "counts": {"done": "max_runs"},
        "states": states,
        # The 「暂未加入任何阴阳寮，是否前往申请加入？」 prompt (no counterpart in assttyys/OAS).
        # Points taken by the agent on a real Win10 + MuMu 12 screenshot (1280x720, RGB hex) and
        # checked there: all match the prompt, none match the 御魂 / 探索 / 庭院 screens.
        "blockers": [{
            "id": "no_guild",
            "desc": ("点结界突破时弹出「暂未加入任何阴阳寮，是否前往申请加入？」，或加入后还没建自己的结界时弹出"
                     "「尚未创建阴阳寮结界，是否前往创建？」（两种弹框版式一样，实机截图都能认出）"),
            "when": {"colors": [
                [451, 428, "#da624a"], [481, 426, "#d9614a"],      # red 取消
                [679, 422, "#e9b05e"], [688, 452, "#e9b05e"],      # yellow 前往申请
                [450, 362, "#d9c5ae"], [490, 362, "#d9c5ae"], [530, 362, "#d9c5ae"],  # dialog
                [470, 240, "#c6b19c"], [700, 240, "#c6b29b"],      # title bar
                [1140, 627, "#4d472f"],                            # dimmed background
            ]},
            "message": ("进不了个人结界突破：账号还没加入阴阳寮，或加入后还没创建自己的阴阳寮结界。"
                        "请先在游戏里加入阴阳寮，并在寮里点「结界」创建结界后再运行"),
        }],
    }


def build_exploration(F: Funcs) -> dict:
    op0 = F.op(14, 0)["oper"]
    icon_off = op0[0]["rect"]           # [0, 0, 42, 51] added to the found icon
    swipe_from, swipe_to = op0[1]["rect"], op0[2]["rect"]
    explore_map = F.when(14, 0)
    leave = [{"click": op0[3]["rect"], "delay": op0[3]["delay"]}, {"click": op0[4]["rect"], "delay": op0[4]["delay"]}]
    chapter_screen = {"any": [F.when(14, 4), F.when(14, 3), {"res": "探索地图界面"}]}
    states = common_battle_states(F, {"rounds": "rounds + boss", "boss": 0}) + [
        # Rounds used up: do not stop on the result screen (「点击屏幕继续」) but leave the chapter
        # map and stop once the chapter / big exploration map is on screen.
        {"id": "rounds_done_leave", "desc": "轮数已打满，还在章节地图里：点左上角返回并确认退出",
         "from": "assttyys 014 #0 oper[3]/[4]",
         "when": {"all": [explore_map, {"expr": "rounds >= max_rounds"}]},
         "do": leave + [{"set": {"swipes": 0}}], "max_repeat": 4},
        {"id": "rounds_done", "desc": "轮数已打满，已回到章节界面或探索大地图，结束",
         "when": {"all": [chapter_screen, {"expr": "rounds >= max_rounds"}]},
         "do": [{"stop": "探索轮数已打满，已回到章节界面"}]},
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
         "do": leave + [{"set": {"swipes": 0}}], "max_repeat": 3},
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
        # Big exploration map (新版界面): the chapters are listed on the right under the 「主线」 tab,
        # newest at the bottom. Pick the lowest chapter title found; if the list is not showing
        # (「玩法」 tab open), click 「主线」 first; the fixed chapter_xy is only the last resort.
        {"id": "chapter_last", "desc": "探索大地图，点「主线」列表里最下面（最新）的一章", "from": "assttyys 014 #1（按新版界面改写）",
         "when": {"all": [{"res": "探索地图界面"}, {"find": "探索_主线章节标题", "pick": "last"}]},
         "do": [{"click_found": True, "offset": [-12, 2, 10, 12], "delay": 1000}, {"set": {"tab_clicks": 0}}],
         "max_repeat": 5},
        {"id": "chapter_tab", "desc": "探索大地图，章节列表没显示：点右侧「主线」标签",
         "when": {"all": [{"res": "探索地图界面"}, {"expr": "tab_clicks < 2"}]},
         "do": [{"click": "main_tab", "delay": 1000}, {"inc": "tab_clicks"}], "max_repeat": 3},
        {"id": "chapter_map", "desc": "探索大地图，认不出章节列表时按固定坐标点章节（可改 chapter_xy）",
         "when": {"res": "探索地图界面"},
         "do": [{"click": "chapter_xy", "delay": 1000}, {"set": {"tab_clicks": 0}}], "max_repeat": 5},
        dict(EXIT_DIALOG_STATE),
        {"id": "nav_courtyard", "desc": "在庭院，点「探索」灯笼进探索大地图",
         "when": {"all": [{"expr": "rounds < max_rounds"}, COURTYARD, COURTYARD_EXPLORE]},
         "do": [{"click_found": True, "offset": [-12, -8, 12, 8], "delay": 2500}], "max_repeat": 3},
    ]
    return {
        "format": 1, "name": "exploration", "title": "探索（个人）",
        "desc": ("在探索地图里优先打首领，其次打小怪（无差别），没怪时划动地图，划满次数后退出重进。"
                 "由 assttyys 方案「个人探索」的 014 翻译；「打经验」「打掉落」模式没有做。"),
        "resources": ["assttyys/colors.yaml"],
        "inline_resources": {
            "chapter_xy": {"type": "click", "rect": [1111, 464, 1131, 478],
                           "desc": "认不出章节列表时点的章节坐标，默认 1121,471（新版界面「主线」列表第三行）"},
            "main_tab": {"type": "click", "rect": [1096, 178, 1120, 194], "desc": "探索大地图右侧「主线」标签"},
            "探索_主线章节标题": {
                "type": "find_colors", "region": [1040, 200, 1240, 600], "similarity": 88, "pick": "last",
                "desc": ("探索大地图「主线」列表里的章节标题（用「第二十X章」里「二十」两个字的笔画定位；"
                         "在 MuMu 12 1280x720 实机截图上取点）"),
                "groups": [[[1120, 464, "#e2dbc8"], [1120, 474, "#e2dbc8"], [1114, 470, "#e8e3d0"],
                            [1096, 476, "#e6e0ca"], [1106, 476, "#dcd5c2"], [1110, 474, "#2d2622"],
                            [1115, 465, "#2d2622"], [1125, 475, "#2d2622"]]]},
        },
        "similarity": 93,
        "params": {"max_rounds": {"default": 20, "min": 1, "max": 500, "desc": "探索轮数（打完首领算一轮）"},
                   "max_swipes": {"default": 4, "min": 1, "max": 30, "desc": "没怪时最多划几次再退出（assttyys 默认 4）"}},
        "vars": {"rounds": 0, "boss": 0, "losses": 0, "swipes": 0, "pending": 0, "started": 0, "tab_clicks": 0},
        "limits": dict(LIMITS),
        "counts": {"rounds": "max_rounds"},
        "states": states,
    }


MAIL_TITLE = {"text": "邮箱", "region": [580, 50, 120, 55]}
FRIEND_TITLE = {"text": "好友", "region": [580, 45, 120, 50]}
REWARD_POPUP = {"text": ["获得奖励", "获得物品"], "region": [440, 150, 400, 150]}


def build_daily_rewards(F: Funcs) -> dict:
    """Free daily supplies: claim all mail attachments and collect friendship points. OCR-driven
    (no counterpart colour script in assttyys for the new mail / friend screens)."""
    states = [
        dict(EXIT_DIALOG_STATE),
        {"id": "reward_popup", "desc": "「获得奖励」弹窗，点空白处关掉",
         "when": REWARD_POPUP, "do": [{"click": [540, 630, 740, 690], "delay": 1200}, {"inc": "claimed"}],
         "max_repeat": 5},
        {"id": "mail_confirm", "desc": "邮箱里领取时弹出的确认框，点确定",
         "when": {"all": [MAIL_TITLE, {"text": "确定", "region": [680, 540, 180, 70]}]},
         "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 1500}], "max_repeat": 3},
        {"id": "mail_claim", "desc": "邮箱，点左下「一键领取」/「全部领取」",
         "when": {"all": [{"expr": "mail_clicks < 3"}, MAIL_TITLE,
                          {"text": ["一键领取", "全部领取"], "region": [20, 590, 440, 65]}]},
         "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 1500}, {"inc": "mail_clicks"}],
         "max_repeat": 3},
        {"id": "mail_done", "desc": "邮箱里没有可领的了，返回庭院",
         "when": {"all": [{"expr": "mail_done == 0"}, MAIL_TITLE]},
         "do": [{"set": {"mail_done": 1}}, {"back": True, "delay": 2000}]},
        {"id": "mail_leaving", "desc": "已按过返回，邮箱还没关上，等一下（不再按返回，免得弹「退出游戏」）",
         "when": MAIL_TITLE, "do": [{"wait": 1500}], "max_repeat": 4},
        {"id": "friend_collect", "desc": "好友界面，点「一键收取」友情点",
         "when": {"all": [{"expr": "friend_clicks < 1"}, FRIEND_TITLE,
                          {"text": ["一键收取", "收取"], "region": [30, 530, 200, 65]}]},
         "do": [{"click_found": True, "offset": [-15, -8, 15, 8], "delay": 1500}, {"inc": "friend_clicks"}],
         "max_repeat": 2},
        {"id": "friend_done", "desc": "友情点收过了，返回庭院",
         "when": {"all": [{"expr": "friend_done == 0"}, FRIEND_TITLE]},
         "do": [{"set": {"friend_done": 1}}, {"back": True, "delay": 2000}]},
        {"id": "friend_leaving", "desc": "已按过返回，好友界面还没关上，等一下",
         "when": FRIEND_TITLE, "do": [{"wait": 1500}], "max_repeat": 4},
        {"id": "all_done", "desc": "庭院，邮件和友情点都领过了，结束",
         "when": {"all": [{"expr": "mail_done == 1 and friend_done == 1"}, COURTYARD]},
         "do": [{"stop": "补给领完了（邮件附件 + 好友友情点）"}]},
        {"id": "open_mail", "desc": "庭院，点右上角邮箱",
         "when": {"all": [{"expr": "mail_done == 0"}, COURTYARD]},
         "do": [{"click": "mail_icon", "delay": 2000}], "max_repeat": 3},
        {"id": "open_friends", "desc": "庭院，点底部「好友」",
         "when": {"all": [{"expr": "friend_done == 0"}, COURTYARD]},
         "do": [{"click": "friend_icon", "delay": 2000}], "max_repeat": 3},
        {"id": "leave_explore_map", "desc": "在探索大地图，返回庭院",
         "when": EXPLORE_MAP, "do": [{"back": True, "delay": 2000}], "max_repeat": 3},
    ]
    return {
        "format": 1, "name": "daily_rewards", "title": "补给领取（邮件 + 好友友情点）",
        "desc": ("从庭院（或探索大地图）出发：打开邮箱一键领取所有附件，再到好友界面一键收取友情点，回到庭院停止。"
                 "画面用 OCR 认字（需要可选依赖 rapidocr），没有 OCR 时认不出画面会停下。"),
        "resources": ["assttyys/colors.yaml"],
        "similarity": 93,
        "params": {},
        "vars": {"mail_done": 0, "friend_done": 0, "mail_clicks": 0, "friend_clicks": 0, "claimed": 0},
        "limits": {**LIMITS, "unknown_timeout_s": 30},
        "inline_resources": {
            "mail_icon": {"type": "click", "rect": [1144, 35, 1164, 55], "desc": "庭院右上角邮箱"},
            "friend_icon": {"type": "click", "rect": [897, 640, 917, 660], "desc": "庭院底部「好友」"},
        },
        "states": states,
    }


def build_home(F: Funcs) -> dict:
    """Back to the courtyard from wherever the game is (used between workflows by ``oaf marathon``)."""
    settle = [s for s in common_battle_states(F) if s["id"].startswith("settle") or s["id"] in ("battle_manual", "in_battle")]
    leave = [F.click(14, 0, 3), F.click(14, 0, 4)]
    states = [
        dict(EXIT_DIALOG_STATE),
        {"id": "courtyard", "desc": "已在庭院，结束", "when": COURTYARD, "do": [{"stop": "已回到庭院"}]},
        REWARD_HOME,
    ] + settle + [
        {"id": "explore_chapter", "desc": "在探索章节地图里，点左上返回并确认退出",
         "when": F.when(14, 0), "do": leave, "max_repeat": 3},
        {"id": "back", "desc": "认不出是哪，按返回键（最多 8 次）",
         "when": {"expr": "backs < 8"}, "do": [{"back": True, "delay": 2000}, {"inc": "backs"}], "max_repeat": 8},
    ]
    return {
        "format": 1, "name": "home", "title": "回到庭院",
        "desc": "从任意界面按返回键（最多 8 次，结算画面先点掉，探索地图先确认退出）回到庭院；连续日常 oaf marathon 在两项之间用它。",
        "resources": ["assttyys/colors.yaml"],
        "similarity": 93,
        "params": {},
        "vars": {"backs": 0, "runs": 0, "done": 0, "losses": 0, "pending": 0, "started": 0},
        "limits": {**LIMITS, "unknown_timeout_s": 20},
        "states": states,
    }


REWARD_HOME = {"id": "reward_popup", "desc": "「获得奖励」弹窗，点空白处关掉", "when": REWARD_POPUP,
               "do": [{"click": [540, 630, 740, 690], "delay": 1200}], "max_repeat": 5}

BUILDERS = {"orochi": build_orochi, "realm_raid": build_realm_raid, "exploration": build_exploration,
            "daily_rewards": build_daily_rewards, "home": build_home}


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
