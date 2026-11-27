"""Audited, scoped translations. Unknown source fingerprints always return to the agent queue.

These are independent task contracts, not claims that the owning monolithic script
has been translated. Upstream code is parsed/read as data and never executed.
"""
# OAS-derived mappings: OnmyojiAutoScript, GPL-3.0, upstream author runhey and contributors.
# assttyys mappings: assttyys_autojs, MIT, Copyright (c) 2019 Chaos.
from __future__ import annotations

import re
from pathlib import Path

from ..workflow.schema import bundled_dir
from ..yamlio import load_yaml
from .assttyys import convert_func

OAS_SCOPES = {
    "Restart": {"daily_sign": "庭院每日一签（不解签、不分享、不选择累计奖励）"},
    "DailyTrifles": {
        "store_sign": "商店免费签到（不含召唤、购买体力和吉闻）",
        "friend_love": "一键收取友情点（不含祝福或消息发送）",
        "one_summon": "每日蓝票单抽（硬上限一次，不含今忆或神秘图案）",
    },
    "TalismanPass": {"task_rewards": "花合战任务奖励（不含等级自选、1500签御魂）"},
    "RichMan": {
        "medal_blue": "勋章商店每周一张蓝票（只买一个，180勋章）",
        "medal_black": "勋章商店每周一颗黑蛋（只买一个，480勋章）",
    },
}
ASS_SCOPES = {700: {"food_boxes": "领取体力和经验食盒（不更换育成式神）"}}


def known_recipe(entry, root):
    pins_path = bundled_dir() / "translations" / "pins.yaml"
    pins = load_yaml(pins_path) if pins_path.is_file() else {}
    if (pins or {}).get(entry["id"]) != entry["fingerprint"]:
        return None
    variant = entry.get("variant")
    builder = Builder(entry, Path(root))
    if entry["id"] == "assttyys:func:022":
        raw = builder.paper_summon()
    elif entry["source"] == "oas" and variant in ("daily_sign", "store_sign", "friend_love", "one_summon", "task_rewards", "medal_blue", "medal_black"):
        raw = getattr(builder, variant)()
    elif entry["source"] == "assttyys" and variant == "food_boxes":
        raw = builder.food_boxes()
    else:
        return None
    return {"complete": True, "unsupported": [], "notes": "已审计源码指纹；仅覆盖目录声明的独立任务范围：" +
            entry.get("scope_description", "普通召唤画面处理组件；有界一抽，不含导航"), "workflow": raw}


class Builder:
    def __init__(self, entry, root):
        self.entry, self.root = entry, root
        self.raw = {"format": 1, "name": entry["workflow"], "params": {}, "vars": {}, "resources": [],
                    "limits": {"timeout_s": 300, "unknown_timeout_s": 20, "stuck_timeout_s": 60,
                               "no_progress_timeout_s": 120, "max_repeat": 12}, "states": []}
        self.docs = {}

    def asset(self, task, name):
        ref = f"upstream/oas/{task}.yaml"
        if ref not in self.raw["resources"]:
            self.raw["resources"].append(ref)
        if ref not in self.docs:
            self.docs[ref] = load_yaml(self.root / "resources" / ref)["resources"]
        return self.docs[ref][name]

    def res(self, task, name):
        self.asset(task, name)
        return {"res": name}

    def click(self, task, name, delay=1000):
        spec = self.asset(task, name)
        if "rect" in spec:
            rect = spec["rect"]
        else:
            x, y, w, h = spec["front"]
            rect = [x, y, x + w, y + h]
        return {"click": rect, "delay": delay}

    def state(self, sid, condition, actions, expr=None, **extra):
        when = {"all": [{"expr": expr}, condition]} if expr else condition
        self.raw["states"].append({"id": sid, "when": when, "do": actions, **extra})

    def stop(self, sid, condition, expr, result="completed", verified=True):
        self.state(sid, condition, [{"stop": {"reason": sid, "result": result, "verified": verified,
            "evidence": {"scope": self.entry.get("scope_description", "画面处理组件"), "terminal_state": sid}}}], expr)

    def courtyard(self, expr):
        # 2026-11-21 live capture: I_CHECK_MAIN misses the account's cherry-tree
        # courtyard. Keep two independent, region-bound labels as the fallback.
        expanded = {"all": [{"text": "式神录", "region": [1080, 640, 110, 55]},
                            {"text": "阴阳寮", "region": [515, 640, 120, 55]}]}
        clear = {"not": {"any": [
            {"text": "每日一签", "region": [450, 150, 380, 250]},
            {"text": "累计奖励", "region": [440, 470, 390, 100]},
            {"text": "获得奖励", "region": [400, 120, 480, 250]},
            {"text": "退出游戏", "region": [330, 300, 360, 100]}]}}
        self.state("expand_courtyard_menu", {"all": [
            {"text": "探索", "region": [610, 120, 130, 110]},
            {"text": "加成", "region": [335, 20, 95, 90]}, {"not": expanded}, clear]},
            [{"click": [1180, 610, 1220, 670], "delay": 1200}], expr, max_repeat=2)
        return {"all": [clear, {"any": [self.res("GameUi", "I_CHECK_MAIN"), expanded]}]}

    def mall(self):
        self.raw["states"].insert(0, {"id": "optional_download_prompt", "when": {"all": [
            {"text": "是否下载", "region": [330, 260, 620, 140]},
            {"text": "取消", "region": [400, 420, 200, 100]}]}, "do": [{"stop": {
                "reason": "商店被可选资源下载弹窗遮挡，暂停等待处理", "result": "blocked", "verified": False}}]})
        self.state("open_mall", self.courtyard("attempted == 0"),
                   [self.click("GameUi", "I_MAIN_GOTO_MALL", 2500)], "attempted == 0", max_repeat=3)
        self.state("close_mall_recommendation", self.res("GameUi", "I_CHECK_MALL_RECOMMEND"),
                   [self.click("GlobalGame", "I_UI_BACK_YELLOW")], "attempted == 0", max_repeat=3)

    def reward(self, expr="attempted == 1"):
        # Stop while the positive receipt frame is still present. Next task homes independently.
        self.stop("reward_verified", self.res("GlobalGame", "I_UI_REWARD"), expr)

    def daily_sign(self):
        self.raw["vars"] = {"attempted": 0}
        self.raw["requires"] = ["从庭院领取每日一签；新皮肤入口识别不明时暂停，不猜测已签到"]
        result = {"all": [
            {"text": "", "pattern": r"第\s*\d+\s*签", "region": [440, 90, 230, 85]},
            {"text": "累计奖励", "region": [440, 470, 390, 100]},
            {"text": "奖励", "region": [450, 320, 150, 65]}]}
        self.stop("daily_sign_receipt", result, "attempted == 1")
        self.stop("existing_sign_result", result, "attempted == 0", "unknown", False)
        self.state("draw_daily_sign", {"all": [
            {"any": [self.res("Restart", "I_HARVEST_SIGN_2"), self.res("Restart", "I_HARVEST_SIGN_4"),
                     {"text": "每日一签", "region": [450, 150, 380, 250]}]},
            {"text": "今日最佳奖励", "region": [450, 400, 380, 95]}]},
            [{"click": [620, 225, 660, 280], "delay": 1500, "recheck": True, "attempt_var": "attempted"}],
            "attempted == 0", max_repeat=1, progress=True)
        main = self.courtyard("attempted == 0")
        # These upstream markers move within a wide ROI. Their matched location,
        # rather than their original absolute front rectangle, is the input target.
        self.state("open_upstream_sign_marker", {"all": [main, {"any": [
            self.res("Restart", "I_HARVEST_SIGN"), self.res("Restart", "I_HARVEST_SIGN_3")]}]},
            [{"click_found": True, "offset": [5, 5, 15, 15], "delay": 1200}], "attempted == 0", max_repeat=2)
        # Real 1280x720 capture, 2026-11-21: this skin places the tag above the
        # upstream image search ROI. Narrow colour points identify the visible
        # tag; no match is deliberately NOT interpreted as already signed.
        self.state("open_live_sign_marker", {"all": [main, {"colors": [
            [302, 450, "#d5c6bf"], [313, 451, "#b38b5b"], [309, 466, "#e3c7bc"],
            [319, 473, "#d09287"], [303, 480, "#c3a99c"], [318, 450, "#7c6255"],
            [300, 470, "#8f613b"]], "similarity": 93}]},
            [{"click": [302, 457, 317, 477], "delay": 1200}], "attempted == 0", max_repeat=2)
        self.stop("sign_marker_not_recognized", main, "attempted == 0", "unknown", False)
        return self.raw

    def store_sign(self):
        self.raw["vars"] = {"attempted": 0, "recommend_clicks": 0}
        self.reward()
        self.state("claim_store_sign", self.res("DailyTrifles", "I_GIFT_SIGN"),
                   [self.click("DailyTrifles", "I_GIFT_SIGN", 2500), {"set": {"attempted": 1}}],
                   "attempted == 0", progress=True)
        self.state("gift_recommendation", self.res("DailyTrifles", "I_GIFT_RECOMMEND"),
                   [self.click("DailyTrifles", "I_GIFT_RECOMMEND"), {"inc": "recommend_clicks"}],
                   "attempted == 0 and recommend_clicks < 4")
        self.stop("sign_not_available", self.res("DailyTrifles", "I_GIFT_RECOMMEND"),
                  "attempted == 0 and recommend_clicks >= 4", "unknown", False)
        self.state("open_gift_room", self.res("DailyTrifles", "I_ROOM_GIFT"),
                   [self.click("DailyTrifles", "I_ROOM_GIFT")], "attempted == 0", max_repeat=3)
        self.mall()
        return self.raw

    def friend_love(self):
        self.raw["vars"] = {"attempted": 0}
        self.reward()
        self.state("collect_friend_points", self.res("DailyTrifles", "I_L_COLLECT"),
                   [self.click("DailyTrifles", "I_L_COLLECT"), {"set": {"attempted": 1}}], "attempted == 0", progress=True)
        for name in ("I_FRIENDSHIP_UP", "I_L_FRIENDS", "I_FRIEND_TAB"):
            self.state(name.lower(), self.res("DailyTrifles", name), [self.click("DailyTrifles", name)],
                       "attempted == 0", max_repeat=3)
        self.state("open_friends", self.courtyard("attempted == 0"),
                   [self.click("GameUi", "I_MAIN_GOTO_FRIENDS")], "attempted == 0", max_repeat=3)
        return self.raw

    def task_rewards(self):
        self.raw["vars"] = {"attempted": 0, "task_opened": 0}
        self.reward()
        task_page = {"any": [self.res("TalismanPass", "I_TP_GOTO"), self.res("TalismanPass", "I_TP_EXP"),
            {"all": [{"text": "花合战", "region": [90, 15, 150, 60]},
                     {"text": "今日", "region": [490, 165, 100, 60]},
                     {"text": "已完成", "region": [550, 260, 250, 330]}]}]}
        claim = {"any": [self.res("TalismanPass", "I_TP_GET_ALL"), {"all": [
            {"text": "全部", "region": [870, 590, 150, 55]},
            {"text": "领取", "region": [870, 625, 150, 55]}]}]}
        self.state("claim_task_rewards", {"all": [task_page, claim]},
                   [self.click("TalismanPass", "I_TP_GET_ALL"), {"set": {"attempted": 1}}], "attempted == 0", progress=True)
        self.stop("task_rewards_not_available", {"all": [task_page, {"not": claim}]},
                  "attempted == 0 and task_opened == 1", "unknown", False)
        self.state("task_tab", {"all": [{"any": [self.res("GameUi", "I_CHECK_DAILY"),
                   {"text": "花合战", "region": [90, 15, 150, 60]}]},
                   {"text": "任务", "region": [1180, 300, 90, 275]}]},
                   [{"click": [1198, 328, 1234, 401], "delay": 1200}, {"set": {"task_opened": 1}}],
                   "attempted == 0 and task_opened == 0", max_repeat=1)
        self.state("open_daily", self.courtyard("attempted == 0"),
                   [self.click("GameUi", "I_MAIN_GOTO_DAILY")], "attempted == 0", max_repeat=3)
        return self.raw

    def one_summon(self):
        self.raw["params"] = {"enabled": {"default": False}, "stroke": {"default": 1, "choices": [1, 2, 3, 4]}}
        self.raw["vars"] = {"selected": 0, "drawn": 0, "tickets": -1}
        self.raw["requires"] = ["账号已核对使用蓝票召唤池；只画一次普通线条，不执行今忆或神秘图案"]
        self.stop("single_draw_disabled", {"expr": "not enabled"}, None, "skipped", False)
        self.stop("single_draw_receipt", {"any": [self.res("Component_Summon", "I_SM_CONFIRM"),
                  self.res("Component_Summon", "I_SM_CONFIRM_2")]}, "selected == 1 and drawn == 1")
        self.state("close_voice_dialog", {"all": [self.res("Component_Summon", "I_ONE_TICKET"),
                   self.res("GlobalGame", "I_UI_CANCEL")]}, [self.click("GlobalGame", "I_UI_CANCEL")],
                   "selected == 1 and drawn == 0", max_repeat=3)
        for stroke in range(1, 5):
            name = f"S_RANDOM_SWIPE_{stroke}"
            self.asset("Component_Summon", name)
            self.state(f"draw_stroke_{stroke}", {"all": [self.res("Component_Summon", "I_ONE_TICKET"),
                       {"not": self.res("GlobalGame", "I_UI_CANCEL")}]},
                       [{"confirm": "抽卡", "detail": "只执行一次蓝票画符；不会重试或追加第二抽"},
                        {"swipe": name, "delay": 1000, "recheck": True, "attempt_var": "drawn"}],
                       f"enabled and selected == 1 and drawn == 0 and stroke == {stroke}", progress=True)
        self.asset("Component_Summon", "O_ONE_TICKET")
        self.stop("no_blue_ticket", {"all": [self.res("Component_Summon", "I_BLUE_TICKET"),
                  {"ocr": "O_ONE_TICKET", "var": "tickets", "test": "tickets <= 0"}]},
                  "enabled and selected == 0", "blocked", False)
        self.state("select_blue_ticket", {"all": [self.res("Component_Summon", "I_BLUE_TICKET"),
                   {"ocr": "O_ONE_TICKET", "var": "tickets", "test": "tickets > 0"}]},
                   [{"confirm": "抽卡", "detail": "每日蓝票单抽，最多消耗一张蓝票；票不足则停止"},
                    {**self.click("Component_Summon", "I_BLUE_TICKET"), "cost": {"mystery_amulet": 1},
                     "recheck": True, "attempt_var": "selected"}], "enabled and selected == 0", max_repeat=1)
        self.state("open_card_page", self.courtyard("enabled and selected == 0"),
                   [self.click("GameUi", "I_MAIN_GOTO_SUMMON")], "enabled and selected == 0", max_repeat=3)
        return self.raw

    def medal_blue(self):
        return self.medal("BLUE", 180)

    def medal_black(self):
        return self.medal("BLACK", 480)

    def medal(self, item, price):
        self.raw["vars"] = {"attempted": 0, "selected": 0, "balance": -1}
        self.raw["params"] = {"enabled": {"default": False, "desc": "用户启用本周单件购买；每次仍需购买确认"}}
        self.raw["blockers"] = [{"id": "currency_" + k.lower(), "when": self.res("Component_Buy", k),
                                 "message": "购买币种与勋章不一致，停止"} for k in ("I_BUY_RMB", "I_BUY_JADE")]
        for name in ("I_BUY_RMB", "I_BUY_JADE"):
            self.stop("blocked_" + name.lower(), self.res("Component_Buy", name), None, "blocked", False)
        self.stop("purchase_disabled", {"expr": "not enabled"}, None, "skipped", False)
        self.stop("purchase_receipt_verified", self.res("Component_Buy", "I_BUY_SUCCESS"), "attempted == 1")
        self.reward()
        x, y, w, h = self.asset("RichMan", "I_ME_" + item)["front"]
        width, height = self.asset("RichMan", "O_SP_RES_NUMBER")["roi"][2:]
        remain_region = [x + w // 2 - width // 2, y - height, width, height]
        self.state("confirm_medal_purchase", {"all": [self.res("RichMan", "I_ME_CHECK_" + item),
                   {"not": self.res("Component_Buy", "I_BUY_RMB")}, {"not": self.res("Component_Buy", "I_BUY_JADE")},
                   {"not": self.res("Component_Buy", "I_BUY_PLUS")},
                   {"text": "", "pattern": rf"(?<!\d){price}(?!\d)", "region": [548, 483, 178, 119]}]},
                   [{"confirm": "购买", "detail": f"勋章商店 {item}：只购买一个，预期 {price} 勋章"},
                    {**self.click("Component_Buy", "C_BUY_ONE", 2800), "cost": {"medal": price}, "recheck": True,
                     "attempt_var": "attempted"}], "enabled and selected == 1 and attempted == 0", progress=True)
        self.state("select_medal_item", {"all": [self.res("RichMan", "I_SIDE_CHECK_MEDAL"),
                   self.res("RichMan", "I_ME_" + item),
                   {"text": "", "pattern": r"(?:剩余)?(?:购买次数|本周剩余数量)[：:]?\s*1(?!\d)", "region": remain_region},
                   {"ocr": "O_MALL_RESOURCE_3", "var": "balance", "test": f"balance >= {price}"}]},
                   [{"confirm": "购买", "detail": f"核对本周商品和勋章余额后打开 {item} 购买框"},
                    self.click("RichMan", "I_ME_" + item), {"set": {"selected": 1}}],
                   "enabled and selected == 0 and attempted == 0", max_repeat=1)
        self.asset("RichMan", "O_MALL_RESOURCE_3")
        self.state("select_medal_tab", self.res("RichMan", "I_SIDE_SURE_MEDAL"),
                   [self.click("RichMan", "I_SIDE_SURE_MEDAL", 3000)], "enabled and selected == 0", max_repeat=3)
        self.state("open_sundry", self.res("RichMan", "I_MALL_SUNDRY"),
                   [self.click("RichMan", "I_MALL_SUNDRY")], "enabled and selected == 0", max_repeat=3)
        self.mall()
        return self.raw

    def ass(self, fid):
        path = next(path for path in self.entry["entry_files"] if re.search(rf"/{fid:03d}[^/]*\.ts$", path))
        snapshot = self.root / f"resources/upstream/assttyys/programs/src/{path}.txt"
        colors = load_yaml(self.root / "resources/upstream/assttyys/colors.yaml")["resources"]
        doc = convert_func(snapshot, colors)
        if doc.get("parse_error"):
            raise ValueError(doc["parse_error"])
        self.raw["resources"] = ["upstream/assttyys/colors.yaml"]
        return doc["operators"]

    @staticmethod
    def condition(op):
        return {"res": op["detect"]} if op.get("detect") else {"colors": op["detect_points"]}

    @staticmethod
    def actions(op, indices=None):
        ops = op["oper"] if indices is None else [op["oper"][i] for i in indices]
        return [{"click": part["rect"], "delay": part["delay"], **(
                 {"press_ms": part["press_ms"]} if part.get("press_ms") else {})} for part in ops]

    def food_boxes(self):
        ops = self.ass(700)
        self.raw["vars"] = {"phase": 0, "stamina_done": 0, "exp_done": 0, "collected": 0,
                            "stored": -1, "stamina_attempted": 0, "exp_attempted": 0}
        self.raw["requires"] = ["已加入阴阳寮且结界已开启", "经验食盒有可接收经验的育成式神；本任务不更换式神"]
        # The legacy colour signature also matches an EMPTY modern experience jar.
        # Never infer a full unit from a disabled button alone.
        self.raw["blockers"] = [{"id": "experience_full", "when": {"all": [self.condition(ops[14]),
                                 {"text": "", "pattern": "经验已满|式神.{0,8}已满|没有.{0,8}育成式神"}]},
                                 "message": "经验已满，保留食盒，不更换或喂养式神"}]
        self.stop("boxes_empty_verified", self.condition(ops[10]),
                  "stamina_done == 1 and exp_done == 1 and collected == 0", "already_done")
        self.stop("boxes_receipts_verified", self.condition(ops[10]),
                  "stamina_done == 1 and exp_done == 1 and collected > 0")
        for phase, key in ((2, "stamina_done"), (4, "exp_done")):
            self.state("receipt_" + key, {"any": [self.condition(ops[5]),
                       {"text": "获得奖励", "region": [430, 150, 430, 160]}]},
                       [{"set": {key: 1, "phase": 0, "collected": "collected + 1"}},
                        {"click": [580, 680, 720, 700], "delay": 800}], f"phase == {phase}", progress=True)
        # Live modern food box / experience jar. Empty is a positive numeric
        # observation, not an OCR miss, and never causes a withdrawal click.
        for phase, key, title, button, roi in (
                (1, "stamina_done", "体力食盒", "取出", [690, 177, 130, 46]),
                (3, "exp_done", "经验酒壶", "提取", [505, 188, 285, 46])):
            resource = "modern_" + key + "_stored"
            self.raw.setdefault("inline_resources", {})[resource] = {"type": "ocr", "roi": roi}
            identity = {"text": ["体力食盒", "体刀食盒"] if phase == 1 else title,
                        "region": [450, 85, 380, 80]}
            self.state("empty_" + key, {"all": [identity,
                       {"ocr": resource, "var": "stored", "test": "stored == 0"}]},
                       [{"set": {key: 1, "phase": 0}}], f"phase == {phase}", progress=True)
            attempt = "stamina_attempted" if phase == 1 else "exp_attempted"
            button_region = [560, 510, 180, 80] if phase == 1 else [560, 460, 180, 80]
            self.state("withdraw_" + key, {"all": [identity,
                       {"ocr": resource, "var": "stored", "test": "stored > 0"},
                       {"text": button, "region": button_region}]},
                       [{"click": [620, 538, 650, 568] if phase == 1 else [625, 485, 655, 510], "delay": 700,
                         "recheck": True, "attempt_var": attempt}, {"set": {"phase": phase + 1}}],
                       f"phase == {phase} and {attempt} == 0", max_repeat=1)
        for phase, word, op_index in ((1, "体力", 8), (3, "经验", 9)):
            rect = ops[op_index]["oper"][1]["rect"]
            region = [rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]]
            self.state("claim_" + str(phase), {"all": [{"text": word}, {"text": "领取", "region": region}]},
                       self.actions(ops[op_index], [1]) + [{"set": {"phase": phase + 1}}], f"phase == {phase}")
        for key, op_index, phase in (("stamina_done", 8, 1), ("exp_done", 9, 3)):
            self.state("open_" + key, {"all": [self.condition(ops[10]), self.condition(ops[op_index])]},
                       self.actions(ops[op_index], [0]) + [{"set": {"phase": phase}}], f"phase == 0 and {key} == 0")
        # Returning from a receipt is a separate positively recognised close button.
        close = ops[8]["oper"][2]
        self.state("close_box", {"text": "", "pattern": "体[力刀]食盒|经验食盒|经验酒壶",
                   "region": [450, 85, 380, 100]},
                   [{"click": close["rect"], "delay": close["delay"]}],
                   "phase == 0 and (stamina_done == 1 or exp_done == 1)", max_repeat=2)
        for i in (0, 1, 2, 3, 4):
            self.state("navigate_" + str(i), self.condition(ops[i]), self.actions(ops[i]),
                       "phase == 0", max_repeat=3)
        return self.raw

    def paper_summon(self):
        ops = self.ass(22)
        self.raw["vars"] = {"attempted": 0, "result_seen": 0}
        self.raw["params"] = {"enabled": {"default": False}}
        self.raw["requires"] = ["手动进入普通召唤画面；只用破碎咒符，不消费蓝票或勾玉"]
        self.stop("summon_disabled", {"expr": "not enabled"}, None, "skipped", False)
        self.stop("one_summon_result", self.condition(ops[0]), "attempted == 1 and result_seen == 1")
        self.state("summon_one", {"all": [self.condition(ops[0]), {"text": ["破碎的咒符", "普通召唤"]}]},
                   [{"confirm": "抽卡", "detail": "普通召唤一次；消耗一张破碎咒符"},
                   {**self.actions(ops[0])[0], "cost": {"broken_amulet": 1}, "recheck": True, "attempt_var": "attempted"}],
                   "enabled and attempted == 0", max_repeat=1)
        self.state("result_animation", self.condition(ops[1]), self.actions(ops[1]) + [{"set": {"result_seen": 1}}],
                   "attempted == 1", max_repeat=3)
        return self.raw
