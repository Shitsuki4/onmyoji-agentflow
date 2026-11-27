"""Pinned native families for AutoJS team, exploration, realm and startup.

Use ``load_team_handler`` for full raw source/helper pin verification, or
``compile_team_handler`` with an audited source string/resource map. Compose with
``team_workflow`` (which reuses core_workflow/phase_workflow). This wrapper binds
source find thresholds, bookkeeping, and 050's per-input swipe base override.
All configurations remain in the model; compilation never specializes to only
the default arm. Unsupported source effects fail explicitly after the native
prefix, with ordered effects/returns/source locations retained as inert data.

006's local loop has a native phase backedge bounded to three attempts. Each click's fixed 1000ms delay moves
to an unconditional 1000ms native retest phase, refreshing the cached frame
before the next source test, without adding time or an outer loop delay. Common
base/jitter still applies once per click; its distribution is translation
invariant under this integer shift. After the THIRD refresh, source reruns even
if the refreshed frame no longer matches: preserve that ordering and false
return rather than silently declaring victory. No callbacks or new primitives.

040's runtimeParams and superGlobal inputs are distinct from scheme config.
Scalar empty strings represent their absent/null next-scheme names. Runtime
payloads are initial inert snapshots; transition gates retain the entire payload
for the future source lifecycle controller. No source lifecycle equivalence is
claimed. 1280x720 geometry/native humanization and vendor misaligned search have
the same verification limits as the existing handler compiler.

Source: assttyys_autojs, MIT, Copyright (c) 2019 Chaos. See NOTICE.md.
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

from .core_handlers import core_workflow, _push, _rerun, _stop
from .handlers import (
    COMMON_DEFAULTS, UnsupportedHandler, _count, _data, _defaults,
    _operator_case, _used_resources,
)
from .jsliteral import extract_literal_after, find_consts, parse


SOURCE_FILES = {
    4: "src/common/funcList/004_接受邀请.ts",
    5: "src/common/funcList/005_组队挑战.ts",
    6: "src/common/funcList/006_御魂御灵挑战.ts",
    8: "src/common/funcList/008_结界_进攻.ts",
    9: "src/common/funcList/009_结界_勋章点击.ts",
    12: "src/common/funcList/012_寮突破_翻页.ts",
    14: "src/common/funcList/014_探索_点击挑战图标.ts",
    16: "src/common/funcList/016_地鬼_热门收藏挑战.ts",
    17: "src/common/funcList/017_百鬼夜行.ts",
    18: "src/common/funcList/018_每日悬赏.ts",
    22: "src/common/funcList/022_抽厕纸(普通召唤).ts",
    23: "src/common/funcList/023_逢魔答题.ts",
    26: "src/common/funcList/026_现世逢魔.ts",
    27: "src/common/funcList/027_组队_创建或匹配.ts",
    28: "src/common/funcList/028_继续育成.ts",
    30: "src/common/funcList/030_斗技_杂项.ts",
    31: "src/common/funcList/031_结界卡_继续合成.ts",
    34: "src/common/funcList/034_秘闻_挑战.ts",
    40: "src/common/funcList/040_关闭BUFF.ts",
    50: "src/common/funcList/050_开启BUFF.ts",
    51: "src/common/funcList/051_绿标.ts",
    53: "src/common/funcList/053_探索地图进入挑战.ts",
    99: "src/common/funcList/099_伊吹之擂_匹配.ts",
    221: "src/common/funcList/221_夜行荒河_挑战.ts",
    302: "src/common/funcList/302_奉纳御魂.ts",
    304: "src/common/funcList/304_检测绘卷进度.ts",
    306: "src/common/funcList/306_组队内邀请好友.ts",
    309: "src/common/funcList/309_强化御魂.ts",
    310: "src/common/funcList/310_暴食鬼.ts",
    311: "src/common/funcList/311_红标.ts",
    312: "src/common/funcList/312_通用活动.ts",
    313: "src/common/funcList/313_契灵.ts",
    316: "src/common/funcList/316_六道椒图.ts",
    317: "src/common/funcList/317_清自己鬼王.ts",
    318: "src/common/funcList/318_战斗内操作选项.ts",
    319: "src/common/funcList/319_缘结趣游.ts",
    320: "src/common/funcList/320_百鬼棋局挂机.ts",
    401: "src/common/funcList/401_对弈竞猜.ts",
    508: "src/common/funcList/508_逢魔首领.ts",
    517: "src/common/funcList/517_宠物庭院.ts",
    518: "src/common/funcList/518_领取日常奖励.ts",
    519: "src/common/funcList/519_寮管理攻打道馆.ts",
    600: "src/common/funcList/600_进入寮活动.ts",
    601: "src/common/funcList/601_狩猎战.ts",
    602: "src/common/funcList/602_道馆.ts",
    603: "src/common/funcList/603_狭间暗域.ts",
    604: "src/common/funcList/604_首领退治.ts",
    605: "src/common/funcList/605_寮宴会.ts",
    606: "src/common/funcList/606_阴界之门.ts",
    609: "src/common/funcList/609_僵尸寮小号功能.ts",
    690: "src/common/funcList/690_启动游戏.ts",
    691: "src/common/funcList/691_新号流程.ts",
    692: "src/common/funcList/692_徒弟流程.ts",
    693: "src/common/funcList/693_师傅流程.ts",
    694: "src/common/funcList/694_上阵协战式神.ts",
    700: "src/common/funcList/700_进入结界并领取食盒.ts",
    701: "src/common/funcList/701_结界卡更换.ts",
    702: "src/common/funcList/702_式神寄养.ts",
    1100: "src/common/funcList/1100_每周分享蓝票.ts",
    1101: "src/common/funcList/1101_寮商店.ts",
    1102: "src/common/funcList/1102_每周商店购买.ts",
    1103: "src/common/funcList/1103_风姿皮肤券.ts",
    1104: "src/common/funcList/1104_珍旅居兑换.ts",
    1105: "src/common/funcList/1105_每两周神龛兑换黑蛋.ts",
    1106: "src/common/funcList/1106_每周两次真蛇.ts",
    1107: "src/common/funcList/1107.每周契灵商店.ts",
    1108: "src/common/funcList/1108.档期式神领取蓝票.ts",
    1109: "src/common/funcList/1109_秘闻地鬼的分享.ts",
    1110: "src/common/funcList/1110_神秘商店.ts",
    1111: "src/common/funcList/1111_百鬼棋局商店.ts",
}
SOURCE_PINS = {
    4: "ee90d9c874e0ee5554a2b5b1fc497e509b75368d53acc504241d6af52dba63b4",
    5: "8d29f7df0133bb4de5a16ce7acbcc6cdce185306f860baf8e5981d08cac07f2c",
    6: "7ba11c63e8dcc0fa748e907e1c3e0995a0973fe67247eb14ed025749cfee4825",
    8: "01cfd45408ce5ffb7685f5cb9afe7cd0afdda55fcdc938a3c85156928f15bb74",
    9: "aa3baad77d28c87274058b66eaafb0fea7287ce1b9d0cab868dc1fdf30023201",
    12: "3c6d958d9c86c22f16f285fd8668bcc0c72e93ab9008a268cc11f6909e939445",
    14: "8bbd6f975498612fca00f959fecfc96c40a44a299c51948b65c3c5ae7067e41f",
    16: "c809cb7b7151439ef66a931842dbe8f96ec07f0d0aaf3788b1b84366b018cf91",
    17: "5d43df2b7c3311edd69d766a1dcc65465d42d4b11c9e49d553e5febf4ca53620",
    18: "e77b6619a4875b96916334f7b4e69af5b829eb5a77cbd8048f5306ddbadb8182",
    22: "6228f1feca7965fc2bedd7f8a0939b9fe627731b3ba4a98c85df5878d09123b8",
    23: "09063b94dbfa875b1428968cadae8b1a01b98870c97c5cdbf8c853d086a0b414",
    26: "eb95a844bf636f1d16ec7a64269edc4312f8835a2f75352524e388ceab7d409f",
    27: "0c3fd4c188a9dfa56830c527d65cebc296db0201f6546f0b075e2c2dc60c430e",
    28: "9ab6aecf372b6f5cc85fb83af5f66ccefc1b89adc6320d6fd0e30925a0fdc0eb",
    30: "a8bd8501849fc8d3013da0d84916c37d7e821a0ac80038fda66eccf181fe7d6c",
    31: "7d8eaf3304ef7eb50f16ca5402351dcc7fdb19206eac642f9fadf23c2f640a28",
    34: "19226dd30fddd6503d98d1c9d03a1527ede766d0ce05a20a9221d2eb9dff8abf",
    40: "76c68cf329f77dbfb797e11b320045fddedc31066b0930108eca42744a89e459",
    50: "4abe1f0e5e60c146c5baa0169f950bbcbef4c5b41b5e01173190248b0245325d",
    51: "4206bf40eb0a37312af5eb5f7415b3e6782f5a17d5efdabf4c8846d0f2073251",
    53: "e5bebc7c0df67b581a097166bd1dcf5b3e5e7844f2e442bb8abd64250071a9a6",
    99: "0841a6d52d47bd28f6ef02ba9843c62cfde9222f68a1de6900311f7ecf2ced0f",
    221: "5534f6b7ef622b026b98d9ff93eff10a831c094e00a51ed0bdc3f50ad6da59af",
    302: "c96184e95414b7354b1c54c2d3b67ca23f51b140fbde649478b8b009a348c856",
    304: "1ca250173245713bb332115c414c6444f0dd84172010f20400726b6646b28c46",
    306: "e151f1602ce343f9ecaf58485ac9ce09858d336dea8437b787bbd2552a9fd102",
    309: "585dcd6378557e0bf274dc2c6f91f2a432ee2eb10fab65c696557df6cfdbe072",
    310: "d656c43d9398bc5305332e0774a883fe4be54cdf2ba323007ec4eeb707abf581",
    311: "f19513ca5faf273e699552c2a86a3b0f87007b43d63447ac46032584c5548849",
    312: "84a8ff0be7420bb1bb9c6d7fd61cb2276ccc580bc5d5fd8f90b50dbe45d8f82e",
    313: "d6179e49437ffc6d0ece94b62eca7fa62528144f83a717bcdd644d66532e362b",
    316: "4a15ac4bd3e1130cfe2db3adcf353de812b18c7286ba9ba94874703cf415fd50",
    317: "5cc976c5e256fa841e365cf4f615804240278e701ed8c4a5c93990f50e21fd12",
    318: "d2f82a36a87eb40d07b0745240bcc15af7624f10c9ccc37a434748bf9ae49e73",
    319: "75ab8d8803b82024eec2760fb1480fb988bb97ab971ff3b923accf19161b2f8b",
    320: "93ca7aeab5826b01d70ba8e66941131334c390718f2b8315b528b3b3663b672d",
    401: "05f5c40d1950ac111cb14044f98bb8da551c07d5793a2cc65779f1d4d8dfe67e",
    508: "d78ac9b259b365bfbf9be363a9d2f87da18950e758775fb15e01e7792e181d67",
    517: "f23c11dfd2dae4499e092107f9603bc137f8b81d86520229b320c9cd584e10fd",
    518: "23296efebff0e8a1176801b8e7c15056e0c5ca81f7e3d753b5c4c74f2dae049c",
    519: "4e29a6154efc4aafb2c22e1ddf640a29b95bbe8668952c5545759ae4fc062ebf",
    600: "a313417bce78aa42f3b56e62485e3dabfc0211b30be98a7ec010fd9c1872e049",
    601: "4d073142f3b7f2f299814ecd1af14fb5a673f01d50e43900f9d4dce052f11c76",
    602: "f462aeb354aee751e25c58e1f9ecdad8040a98d651fb17e1773bb654110fa425",
    603: "5980791254a49fd4b49e08ffc43254a49b2ebdfb7195079c0e110384b0b4c394",
    604: "a3832ae56285a98162dac7df9a7cbf37820d9219ad8bc471e2280b858c101c79",
    605: "e88e80ffcfbbf70e578073ee5312580098d249e35b3bb5f57a38a259d5587d6a",
    606: "06e2488c6b9a4cd51cc43619d095cae5652d52604bc813b25f6a6ad05ad3b884",
    609: "f3a8c6d07495e389fba1b4fe7a0ad7ab2905da31f89a66807a5eff6a25b2d89b",
    690: "b992a8ed04b99b889804312e1f35488b4586b60fb212cff31651767cb0bb9ee6",
    691: "70c84834ec7575329c8684771fcb7c3e77e97ec82eaad7b5e6155ba4b5947e3c",
    692: "d938261308bcfba2d51ee3081c44d2da1534c153f957d5406a873974f95102bf",
    693: "720e7c3a0bba6cd82778c7de8271138d27176e8cf7a2d68e1f4c4692869c2cef",
    694: "0b5eedba29ec935c8b5927b856e9d4039d0187b8e7719fa361c2326a64ecda36",
    700: "abccad89d01fc7a5501222f30c07f443eb97648390448355b689cbb6ff8c1660",
    701: "8107f882585b7501bea9490cc8464285d59f192d08ef7f3e649b527b8bd3a415",
    702: "13e57843c156e2c2f5fcb0092a98e8a9ea84f85850b6fe51ed5994da2bba996f",
    1100: "f26cda0a68dcb47018a70fb56d42e13b550292c620759b2416ec801bcc795ffe",
    1101: "d4493901cb261b449e16b1ffbf7c97819bac4942403cc19d63d4e0c05ace1538",
    1102: "e8fe66a02879512514fce35153577308d507b3f2c920fa5f56ed6fbd519373cc",
    1103: "9154dc0e075a57f54e1bc24e1845648c6a5964f9974d88b691cade487cc97a8a",
    1104: "630a68637ef8c1d5e3471d3da911d8a8a06c451ea528e540c0d74ba2804d2c88",
    1105: "786e38092963e74c50ab32156015d4d2e5f61a845949492e15cd12fa1bcc0f96",
    1106: "af75ce8458a5dff1b76ec3cf1a8ce81694d359ffcee6e51e54abad5956b218c0",
    1107: "5b40b28540c2f800361e1c83facfe3eb7fd5592ba0b969308444525a3fa63181",
    1108: "a39f5686eda7e1f1f994e9f33a2f5af5f4210cf337321018132a3087b1657c8d",
    1109: "e365ac8586571158a354ba1c74a6002e196dffe17beaaa3bfc34c01e37d9496a",
    1110: "3c216b8356d77417db2ad9b5eec9fbf3376237aa350593f3faa77b5a671fd1e8",
    1111: "3a180d0eea7ba7c293819354150a30f489c407af9c40c3ae2fd2a8908c71eca7",
}
_WEEKLY_SHOP_IDS = (1101, 1102, 1103, 1104, 1105, 1107, 1111)
_WEEKLY_REWARD_IDS = (1100, 1108, 1109)
_EXPLORATION_LF_PIN = "756867d1d3dbac35d8b9623c7213915f59a8159372b69abe86cea98b4bfe41f0"
# Full helper files, not a body substring or caller-generated approval pin.
HELPER_PINS = {
    "src/system/script.ts": "839c55ffb354cc307170fa55babdfa64a1f8c339f1a54f94c23231d8d7fed3bd",
    "src/system/helperBridge.ts": "f7a595ed7aba8a41ce8ab9c71507f379273d9d26a25191fd1f53f34217dc2dae",
    "src/common/toolAuto.ts": "d0cf56ab35ff69b3308e2c0750698f9e866264698de6d7d9c170c310268eb5b8",
    "src/common/multiFindColors.ts": "c4b8c97a6110fa36f87cedc4398c91fc8c813b2dc6ed0c47899cc4083e727091",
    "src/common/multiDetectColors.ts": "bbead5d49fe2307bb28c368ea5bb5e853e148946819ffc5fed2a14a2d117e18a",
    "src/system/GlobalStore/index.ts": "5887bb21ca8e97d7819563043a0979310ac6a86f0ac5c9edb372594ecc3966d5",
}
SWIPE_GATE = "unresolved_source_obligation:team50.swipe_timing_override"


def _expr(text):
    return {"expr": text}


def _all(*items):
    return {"all": list(items)}


def _case(name, condition, actions=(), *, outcome=True, counts=(), group=None):
    result = {"id": name, "when": condition, "do": list(actions), "return": outcome,
              "count_events": list(counts)}
    if group:
        result["retest_group"] = group
    return result


def _gap(packet, name, lines, condition, effects, source_return, required, *, blocking=True):
    fid = packet["handler"]["id"]
    obligation = {"id": f"team{fid}.{name}", "source": {"path": SOURCE_FILES[fid],
        "start_line": lines[0], "end_line": lines[1]}, "condition": copy.deepcopy(condition),
        "ordered_effects": copy.deepcopy(effects), "source_return": source_return,
        "required_contracts": list(required), "blocking": blocking}
    packet["source_obligations"].append(obligation)
    return {"fail": f"unresolved_source_obligation:{obligation['id']} "
                    f"{SOURCE_FILES[fid]}:{lines[0]}-{lines[1]}"}


def _validate_config(fid, params, configured):
    if not isinstance(configured, dict) or set(configured) - set(params):
        raise UnsupportedHandler(f"handler {fid}: unknown config key")
    for key, value in configured.items():
        default = params[key]["default"]
        if type(default) is bool and type(value) is not bool:
            raise UnsupportedHandler(f"{key} must be boolean")
        if isinstance(default, str) and not isinstance(value, str):
            raise UnsupportedHandler(f"{key} must be a literal string")
    enums = {key: spec["choices"] for key, spec in params.items() if "choices" in spec}
    enums.update({5: {"type": ("有人就开", "三人")},
                  50: {"buff_type": ("觉醒", "御魂", "金币", "经验")}}.get(fid, {}))
    for key, choices in enums.items():
        if key in configured and configured[key] not in choices:
            raise UnsupportedHandler(f"unsupported {key}: {configured[key]!r}")


def _target(value, label):
    if value is None or value is False or value == 0 or value == "":
        return ""
    if not isinstance(value, str):
        raise UnsupportedHandler(f"{label}: truthy non-string source target is unsupported")
    return value


def compile_team_handler(source, colors, *, expected_sha256=None, config=None,
                         runtime_params=None, super_next_scheme=None):
    """Compile exact audited source into the standard handler model + audit packet.

    Direct callers own the provenance of ``colors``. The loader additionally
    verifies the full helper/resource files. ``expected_sha256`` cannot authorize
    a new body. Context inputs are inert initial values, never generic callbacks.
    """
    if not isinstance(source, str):
        raise UnsupportedHandler("source must be an inert UTF-8 string")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    lf_digest = hashlib.sha256(source.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    fid = 14 if lf_digest == _EXPLORATION_LF_PIN else next(
        (fid for fid, pin in SOURCE_PINS.items()
         if pin == digest or (fid in (8, 9, 12, 16, 17, 18, 22, 23, 26, 27, 28, 30, 31, 34, 51, 53, 99, 221, 302, 304, 306, 309, 310, 311, 312, 313, 316, 317, 318, 319, 320, 401, 508, 517, 518, 519, 600, 601, 602, 603, 604, 605, 606, 609, 690, 691, 692, 693, 694, 700, 701, 702, 1106, 1110, *_WEEKLY_SHOP_IDS, *_WEEKLY_REWARD_IDS)
                              and pin == lf_digest)), None)
    if fid is None or (expected_sha256 is not None and expected_sha256 != digest):
        raise UnsupportedHandler("team handler source fingerprint mismatch")
    if runtime_params is not None and not isinstance(runtime_params, dict):
        raise UnsupportedHandler("runtime_params must be an inert object or null")
    _data(runtime_params)
    runtime_target = _target((runtime_params or {}).get("next_scheme_name"), "runtimeParams.next_scheme_name")
    super_target = _target(super_next_scheme, "superGlobal.next_scheme_name")
    if fid in (22, 23, 26, 31, 99, 221, 310, 317, 518, 601, 604, 606, 694, 700, 1103, 1105, 1107, 1111, *_WEEKLY_REWARD_IDS):
        declaration = []
    elif fid == 401:
        boss_lit, _ = extract_literal_after(source, r"\ballBosses\s*:\s*string\[\]\s*=")
        bosses = parse(boss_lit, find_consts(source))
        literal, _ = extract_literal_after(source, r"\bconfig\s*=")
        expanded = literal.replace("...allBosses", ", ".join(repr(name) for name in bosses))
        declaration = parse(expanded, find_consts(source))
    else:
        literal, _ = extract_literal_after(source, r"\bconfig\s*=")
        declaration = parse(literal, find_consts(source))
    params = _defaults(declaration)
    if fid == 34:
        from .preset_handler import WEEKLY_GROUPS, normalize_weekly_preset_config
        normalized = normalize_weekly_preset_config({key: spec["default"] for key, spec in params.items()})
        params = {key: {"default": value} for key, value in normalized.items()}
        for suffix in WEEKLY_GROUPS:
            params[f"preset_group_{suffix}"].update(min=0, max=7)
            params[f"preset_slot_{suffix}"].update(min=0, max=4)
        config = normalize_weekly_preset_config(config or {})
    if fid in (8, 9, 12, 14, 16, 17, 27, 28, 51, 53, 306, 311, 313, 401, 602, 603, 609, 701, 702):
        for item in (item for group in declaration for item in group["config"]):
            if item["type"] == "list":
                params[item["name"]]["choices"] = list(item["data"])
    if fid == 304:
        params["choiceEmaki"]["choices"] = ["1", "2", "3", "4", "5", "6"]
        params["rankOpen"] = {"default": int(params["rankOpen"]["default"]), "min": 0}
        if config and "rankOpen" in config and isinstance(config["rankOpen"], str) and re.fullmatch(r"\s*[0-9]{1,6}\s*", config["rankOpen"]):
            config = {**config, "rankOpen": int(config["rankOpen"].strip())}
    if fid == 316:
        params["overTimes"] = {"default": int(params["overTimes"]["default"]), "min": 0}
        if config and "overTimes" in config and isinstance(config["overTimes"], str) and re.fullmatch(r"\s*[0-9]{1,6}\s*", config["overTimes"]):
            config = {**config, "overTimes": int(config["overTimes"].strip())}
    if fid == 318:
        params["time"] = {"default": int(params["time"]["default"]), "min": 0}
        if config and "time" in config and isinstance(config["time"], str) and re.fullmatch(r"\s*[0-9]{1,8}\s*", config["time"]):
            config = {**config, "time": int(config["time"].strip())}
    if fid == 508:
        params["times_for_search_boss"] = {"default": int(params["times_for_search_boss"]["default"]), "min": 0}
        if (config and "times_for_search_boss" in config
                and isinstance(config["times_for_search_boss"], str)
                and re.fullmatch(r"\s*[0-9]{1,6}\s*", config["times_for_search_boss"])):
            config = {**config, "times_for_search_boss": int(config["times_for_search_boss"].strip())}
    if fid == 519:
        params["day"]["default"] = True
    if fid == 609:
        params["account_count"] = {"default": int(params["account_count"]["default"]), "min": 0}
    if fid == 600:
        from .guild_launcher_handlers import normalize_guild_launcher_config
        normalized = normalize_guild_launcher_config({key: spec["default"] for key, spec in params.items()})
        params = {key: {"default": value} for key, value in normalized.items()}
        params["banquet_day_one"]["choices"] = list(range(7))
        params["banquet_day_two"]["choices"] = list(range(7))
        params["count"]["min"] = 0
        config = normalize_guild_launcher_config(config or {})
    if fid == 603:
        from .narrow_realm_handlers import NARROW_PRESET_PAIRS, normalize_narrow_realm_config
        choices = params["boss_order"].get("choices")
        normalized = normalize_narrow_realm_config({key: spec["default"] for key, spec in params.items()})
        params = {key: {"default": value} for key, value in normalized.items()}
        if choices:
            params["boss_order"]["choices"] = choices
        params["boss_select_one"]["choices"] = [0, 1, 2, 3]
        params["boss_select_two"]["choices"] = [0, 1, 2, 3]
        params["sneak"]["min"] = 0
        for _, grp, slt in NARROW_PRESET_PAIRS:
            params[grp].update(min=0, max=7)
            params[slt].update(min=0, max=4)
        config = normalize_narrow_realm_config(config or {})
    if fid == 690:
        params["account_index"]["choices"] = [0, 1, 2, 3]
    if fid == 693:
        from .bounty_mentor_handlers import MASTER_PRESET_PAIRS, normalize_master_config
        normalized = normalize_master_config({key: spec["default"] for key, spec in params.items()})
        params = {key: {"default": value} for key, value in normalized.items()}
        for _, grp, slt in MASTER_PRESET_PAIRS:
            params[grp].update(min=0, max=7)
            params[slt].update(min=0, max=4)
        params["coin"]["min"] = 0
        params["exp"]["min"] = 0
        config = normalize_master_config(config or {})
    if fid == 602:
        # The upstream switch default is string 'true'; the body reads truthiness.
        params["fail_exit"]["default"] = True
        for name, maximum in (("switch_team_group", 7), ("switch_team_default", 4)):
            params[name] = {"default": int(params[name]["default"]), "min": 0, "max": maximum}
    if fid == 1106:
        for name, maximum in (("switch_group", 8), ("switch_default", 4)):
            params[name]["choices"] = [str(n) for n in range(maximum + 1)]
    if fid in (8, 40):
        # Read by the actual method although omitted from its UI declaration.
        params["afterCountOper"] = {"default": ""}
    _validate_config(fid, params, config or {})
    for key, value in (config or {}).items():
        params[key]["default"] = value
    literal, _ = extract_literal_after(source, r"operator\s*:\s*IFuncOperatorOrigin\[\]\s*=")
    ops = parse(literal, find_consts(source))
    expected_counts = {4: 5, 5: 9, 6: 3, 8: 7, 9: 5, 12: 1, 14: 7, 16: 6, 17: 11, 18: 20, 22: 2, 23: 1, 26: 13, 27: 17, 28: 3, 30: 21, 31: 3, 34: 9,
                       40: 2, 50: 5, 51: 4, 53: 7, 99: 8, 221: 6, 302: 21, 304: 10, 306: 16, 309: 15, 310: 7, 311: 9, 312: 2, 313: 16, 316: 35,
                       317: 3, 318: 10, 319: 10, 320: 29, 401: 6, 508: 12, 517: 12, 518: 49, 519: 12, 600: 17, 601: 2, 602: 14, 603: 10,
                       604: 2, 605: 27, 606: 6, 609: 109, 690: 36, 691: 87, 692: 57, 693: 14, 694: 9, 700: 15, 701: 16, 702: 14,
                       1100: 12, 1101: 21, 1102: 49, 1103: 9, 1104: 20, 1105: 9,
                       1106: 11, 1107: 9, 1108: 16, 1109: 20, 1110: 13, 1111: 10}
    if len(ops) != expected_counts[fid]:
        raise UnsupportedHandler("audited operator count mismatch")
    model = {"id": fid, "name": re.search(r"\bname\s*=\s*'([^']*)'", source)[1],
        "params": params, "vars": {}, "cases": [], "resources": [], "resource_specs": {},
        "unmatched_return": False, "proof": {"source_sha256": digest, "source_path": SOURCE_FILES[fid],
            "scope": "pinned-team-family-partial", "source_complete": False,
            "helper_pins": copy.deepcopy(HELPER_PINS), "helper_pins_verified": False,
            "config_declaration": declaration, "source_operator_count": len(ops)}}
    packet = {"handler": model, "source_obligations": [], "bookkeeping_cases": [],
              "complete": False, "original_task_complete": False, "coverage": "guarded-team-handler-partial"}
    builder = _Builder(packet, ops, dict(colors))
    if fid == 4:
        _accept(builder)
    elif fid == 5:
        _challenge(builder)
    elif fid == 6:
        _solo(builder)
    elif fid in (8, 9):
        from .realm_handlers import build_realm_attack, build_realm_medals
        (build_realm_attack if fid == 8 else build_realm_medals)(builder)
    elif fid == 12:
        from .realm_handlers import build_guild_realm_paging
        build_guild_realm_paging(builder)
    elif fid == 14:
        _exploration(builder)
    elif fid == 16:
        from .realm_handlers import build_area_boss
        build_area_boss(builder)
    elif fid == 17:
        from .mini_feature_handlers import build_demon_parade
        build_demon_parade(builder)
    elif fid == 18:
        from .bounty_mentor_handlers import build_daily_bounty
        build_daily_bounty(builder)
    elif fid == 22:
        from .mini_feature_handlers import build_normal_summon
        build_normal_summon(builder)
    elif fid == 23:
        from .demon_encounter_handlers import build_demon_quiz
        build_demon_quiz(builder)
    elif fid == 26:
        _demon_discovery(builder)
    elif fid == 27:
        _create_team(builder)
    elif fid == 28:
        _continue_upgrade(builder)
    elif fid == 30:
        from .duel_handler import build_duel_misc
        build_duel_misc(builder)
    elif fid == 31:
        from .mini_feature_handlers import build_realm_card_continue_synth
        build_realm_card_continue_synth(builder)
    elif fid == 34:
        from .preset_handler import build_weekly_preset
        build_weekly_preset(builder)
    elif fid == 40:
        _close_buff(builder, runtime_target, super_target, runtime_params)
    elif fid == 51:
        from .green_mark_handler import build_green_mark
        build_green_mark(builder)
    elif fid == 53:
        _challenge_entry(builder)
    elif fid in (99, 221):
        _bounded_event_clicks(builder)
    elif fid == 302:
        from .mini_feature_handlers import build_soul_shrine
        build_soul_shrine(builder)
    elif fid == 304:
        from .misc_event_handlers import build_emaki_progress
        build_emaki_progress(builder)
    elif fid == 306:
        _invite_friend(builder)
    elif fid == 309:
        from .mini_feature_handlers import build_soul_enhance
        build_soul_enhance(builder)
    elif fid == 310:
        from .mini_feature_handlers import build_glutton_exp
        build_glutton_exp(builder)
    elif fid == 311:
        from .red_mark_handler import build_red_mark
        build_red_mark(builder)
    elif fid == 312:
        _generic_event_challenge(builder)
    elif fid == 313:
        from .qiling_handler import build_qiling_handler
        build_qiling_handler(builder)
    elif fid == 316:
        from .six_realms_handler import build_six_realms_shouzu
        build_six_realms_shouzu(builder)
    elif fid == 317:
        _own_boss(builder)
    elif fid == 318:
        from .narrow_realm_handlers import build_battle_options
        build_battle_options(builder)
    elif fid == 319:
        from .mini_feature_handlers import build_yuanjie_travel
        build_yuanjie_travel(builder)
    elif fid == 320:
        from .guild_launcher_handlers import build_chess_idle
        build_chess_idle(builder)
    elif fid == 401:
        from .misc_event_handlers import build_duel_bet
        build_duel_bet(builder)
    elif fid == 508:
        from .demon_encounter_handlers import build_demon_boss
        build_demon_boss(builder)
    elif fid == 517:
        _pet_courtyard(builder)
    elif fid == 518:
        from .daily_reward_handler import build_daily_rewards
        build_daily_rewards(builder)
    elif fid == 519:
        from .guild_launcher_handlers import build_dojo_admin
        build_dojo_admin(builder)
    elif fid == 600:
        from .guild_launcher_handlers import build_guild_launcher
        build_guild_launcher(builder)
    elif fid == 601:
        from .guild_activity_handlers import build_guild_hunt
        build_guild_hunt(builder)
    elif fid == 602:
        from .dojo_handler import build_dojo_handler
        build_dojo_handler(builder)
    elif fid == 603:
        from .narrow_realm_handlers import build_narrow_realm
        build_narrow_realm(builder)
    elif fid == 604:
        from .guild_activity_handlers import build_guild_boss_retreat
        build_guild_boss_retreat(builder)
    elif fid == 605:
        from .banquet_handler import build_guild_banquet
        build_guild_banquet(builder)
    elif fid == 606:
        from .guild_activity_handlers import build_gate_of_hades
        build_gate_of_hades(builder)
    elif fid == 609:
        from .guild_account_handler import build_guild_account_flow
        build_guild_account_flow(builder)
    elif fid == 690:
        from .launch_handler import build_launch_handler
        build_launch_handler(builder)
    elif fid == 691:
        from .apprentice_handler import build_apprentice_login
        build_apprentice_login(builder)
    elif fid == 692:
        from .apprentice_handler import build_apprentice_guard
        build_apprentice_guard(builder)
    elif fid == 693:
        from .bounty_mentor_handlers import build_master_flow
        build_master_flow(builder)
    elif fid == 694:
        _assist_fighter(builder)
    elif fid == 700:
        from .realm_handlers import build_guild_realm_food
        build_guild_realm_food(builder)
    elif fid == 701:
        from .realm_handlers import build_realm_card_replace
        build_realm_card_replace(builder)
    elif fid == 702:
        from .realm_handlers import build_foster_shikigami
        build_foster_shikigami(builder)
    elif fid == 1106:
        from .preset_handler import build_weekly_orochi_preset
        build_weekly_orochi_preset(builder)
    elif fid == 1110:
        from .misc_event_handlers import build_mystery_shop
        build_mystery_shop(builder)
    elif fid in _WEEKLY_SHOP_IDS:
        from .weekly_shop_handlers import build_weekly_shop
        build_weekly_shop(builder)
    elif fid in _WEEKLY_REWARD_IDS:
        from .weekly_reward_handlers import build_weekly_reward
        build_weekly_reward(builder)
    else:
        _open_buff(builder)
    model["resource_specs"] = _used_resources(model["cases"], builder.colors)
    proof = model["proof"]
    proof["unresolved_source_obligations"] = copy.deepcopy(packet["source_obligations"])
    proof["bookkeeping_cases"] = list(packet["bookkeeping_cases"])
    proof["helper_dependencies"] = [
        "src/system/script.ts:260-299,331-364 coordinate/resource transforms",
        "src/system/script.ts:375-431 FindMultiColor similar fallback/misalignedMatch=true",
        "src/system/script.ts:788-851 ordered oper/retest/count-before-input/notForCnt",
        "src/system/script.ts:598-607 cached frame/source priority/true-only currentDate",
        "src/system/script.ts:218-225 KeepScreen(false) refresh (006)",
        "src/system/script.ts:971-980 direct regionClick/regionSwipe base/jitter fallback",
        "src/system/helperBridge.ts:57-97,107-135,164-175 geometry/input/after-delay/swipe timing",
        "src/common/toolAuto.ts:194-210,269-277 getNormalRandom/strHashToNum",
        "src/system/script.ts:118-122,549-570,682-776 Push suffix/start/stop/rerun/pause lifecycle",
        "src/common/toolAuto.ts:339-376 Push bitmap/client/ringtone fallback",
        "src/system/script.ts:921-963 stopRelatedApp API/root settings",
        "src/system/GlobalStore/index.ts:235-236,250,319-324 opened/closed/invite flags and superGlobal",
    ]
    proof["limitations"] = [
        "1280x720 geometry; non-16:9 vendor anchors require separate calibration",
        "Vendor misaligned search/device identifier and source lifecycle are not independently verified",
        "Only fresh starts/completed-phase-0 retries; no downtime-inclusive clock or mid-handler replay",
    ]
    proof.setdefault("resource_costs", "No explicit source resource debit; do not infer stamina/jade/buff-duration receipts.")
    proof.setdefault("source_retest", {"operator_retest_fields": "none in the pinned declaration",
        "explicit_zero": "005/006 pass0; Script.oper uses retest || item.retest, so no source retest is added",
        "native_refresh_retest": "006 moves the existing1000ms input delay to cached-frame refresh"})
    packet["required_contracts"] = sorted({contract for item in packet["source_obligations"] for contract in item["required_contracts"]})
    _data(packet)
    return packet


def _demon_discovery(b):
    discovered = "xianShiFengMo"
    b.model["vars"] = {discovered: 0}
    for index in (8, 12):
        b.add(f"discover_{index}", b.when(index), b.actions(index))

    home = b.when(0)
    for index, action in enumerate(b.actions(7)):
        b.add(f"event_{index}", _all(home, _expr(f"{discovered} == {index}")),
              [action, {"inc": discovered}])
    b.add("open_final_reward", _all(home, {"not": b.when(2)}), [*b.actions(2), {"wait": 5000}])
    b.add("final_reward_already_opened", home, [{"wait": 1500}], outcome=False)

    for index in (3, 4, 5, 6):
        b.add(f"event_dialog_{index}", b.when(index), b.actions(index))
    courtyard = {"any": [b.when(9), b.when(10)]}
    b.add("open_town", _all(courtyard, {"find": "庭院_町中竖牌"}), [
        {"click_found": True, "offset": [0, 0, 5, 5], "delay": 500}, {"wait": 2000}])
    b.add("open_demon_encounter", b.when(11), b.actions(11))
    b.model["proof"]["source_state_bindings"] = {"global.xianShiFengMo": discovered}
    b.model["proof"]["resource_costs"] = "Source dismisses the paid chest and mystery quest. No paid chest input."


def _pet_courtyard(b):
    checks = "checked_yard_count"
    counter = [_count(517)]
    b.model["vars"] = {checks: 0, "super_next_scheme_name": ""}
    b.add("finished", b.when(9), [{"set": {"super_next_scheme_name": "next_scheme"}},
          {"scheme_transition": {"mode": "rerun", "target": "返回庭院"}}], outcome=False, counts=counter)
    entry = {"any": [b.when(index) for index in (0, 1, 2)]}
    b.add("recognize_entry", entry, counts=counter, outcome=None, internal=True)
    b.add("open_pet_house", entry, [{**action, "recheck": True} for action in b.actions(0)], counts=counter)
    for index in (3, 5, 6, 7, 8, 10, 11):
        b.add(f"house_{index}", b.when(index), [{**action, "recheck": True} for action in b.actions(index)],
              counts=counter)

    rear = b.when(4)
    b.add("check_rear_yard", rear, counts=counter, outcome=None, internal=True)
    b.add("reset_rear_count", _all(rear, _expr(f"{checks} >= 6")), [{"set": {checks: 0}}], internal=True)
    for index, action in enumerate(b.actions(4)):
        condition = _all(rear, _expr(f"{checks} == {index}"))
        b.add(f"rear_yard_{index}", condition, [{"wait": 1500}, {**action, "recheck": True}, {"inc": checks}],
              counts=counter)
    b.model["proof"]["source_state_bindings"] = {"global.checked_yard_count": checks,
                                                 "superGlobal.next_scheme_name": "super_next_scheme_name"}
    b.gap("source_skin", (211, 229), entry, [], True,
          ["validate pinned default-courtyard markers across supported client skins"], blocking=False)


def _bounded_event_clicks(b):
    fid = b.fid
    counted = fid == 221
    maximum = 3 if counted else 5
    current, matched = f"event{fid}_attempts", f"event{fid}_matched"
    b.model["vars"] = {current: 0, matched: False}
    counts = [_count(fid)] if counted else []

    def taps(index):
        return [{**action, "recheck": True} for action in b.actions(index)]

    if counted:
        for index in range(2, len(b.ops)):
            b.add(f"terminal_or_battle_{index}", b.when(index), taps(index), counts=counts)

    b.add("reset_attempt_count", _expr("True"), [{"set": {current: 0, matched: False}}], outcome=None, internal=True)
    for index in range(2 if counted else len(b.ops)):
        b.add(f"attempt_{index}", _all(_expr(f"not {matched}"), b.when(index)), [
            *taps(index), {"inc": current}, {"set": {matched: True}}, {"handler_control": {"op": "refresh"}}],
            counts=counts, outcome=None)
    reached = _expr(f"{current} >= {maximum}")
    effects = [{"effect": "source_toast", "text": f"连续执行{maximum}次挑战后未开始，脚本自动停止"},
               _push("[${schemeHistory names joined by 、}]已停止，请查看。"), _stop()]
    if not counted:
        effects.append({"effect": "sleep", "ms": 2000})
    failure = b.gap("attempt_limit", (123, 127) if counted else (137, 142), reached, effects, False,
                    ["source toast", "source Push", "source stop lifecycle"])
    b.add("attempt_limit", reached, [failure], outcome=False, internal=True)
    edge = f"unresolved_source_obligation:team{fid}.phase_loop requires team_workflow"
    b.add("retry_attempt", _expr(matched), [{"set": {matched: False}}, {"fail": edge}], outcome=None, internal=True)
    b.add("attempt_screen_changed", _expr(f"{current} > 0"), internal=True)
    b.model["proof"]["source_phase_edges"] = {"retry_attempt": {"target_case": "attempt_0", "gate_prefix": edge}}
    b.model["proof"]["source_retest"] = {"recheck_after_input": True, "max_recognized_attempts": maximum,
                                         "counter_id": fid if counted else None}


def _generic_event_challenge(b):
    attempts, clicked = "event312_attempts", "event312_clicked"
    b.model["vars"] = {attempts: 0, clicked: False}
    target = {"any": [{"find": name} for name in (
        "活动右下角式神录", "活动说明的感叹号", "体力图标", "右下角锁定阵容")]}
    b.add("reset_attempts", _expr("True"), [{"set": {attempts: 0, clicked: False}}], outcome=None, internal=True)
    boundary = _all(target, _expr(f"{attempts} == 4"))
    failure = b.gap("attempt_limit", (53, 68), boundary, [
        {"effect": "source_toast", "text": "连续执行5次挑战后未开始，脚本自动停止"},
        _push("[${schemeHistory names joined by 、}]已停止，请查看。"), _stop(), {"effect": "sleep", "ms": 2000}],
        False, ["source toast", "source Push", "source stop lifecycle"])
    b.add("attempt_limit", boundary, [failure], outcome=False)
    b.add("tap_challenge", target, [{"click": {"rect_param": "xy"}, "delay": 1000, "recheck": True},
          {"inc": attempts}, {"set": {clicked: True}}, {"handler_control": {"op": "refresh"}}], outcome=None)
    edge = "unresolved_source_obligation:team312.phase_loop requires team_workflow"
    b.add("retry_challenge", _expr(clicked), [{"set": {clicked: False}}, {"fail": edge}], outcome=None, internal=True)
    b.add("challenge_disappeared", _expr(f"{attempts} > 0"), internal=True)
    b.model["proof"]["source_phase_edges"] = {"retry_challenge": {"target_case": "attempt_limit", "gate_prefix": edge}}
    b.model["proof"]["source_retest"] = {"max_inputs": 4, "stop_on_fifth_recognition": True,
                                         "stamina_check_requires_zero_attempts": True}
    stamina = b.when(1)
    blocked = b.gap("stamina_stop", (88, 99), stamina, [
        _push("体力不足，请查看。"), _stop(), {"effect": "sleep", "ms": 3000}], "undefined",
        ["source Push", "source stop lifecycle"])
    b.add("stamina_stop", stamina, [{**action, "recheck": True} for action in b.actions(1)] + [blocked],
          outcome=False, counts=[_count(312)])


def _continue_upgrade(b):
    b.add("level_up", b.when(0), [{**action, "recheck": True} for action in b.actions(0)])
    for index, empty in enumerate(b.when(2)["colors"], 1):
        condition = _all(_expr(f"count == {str(index)!r}"), b.when(1), {"not": {"colors": [empty]}})
        b.add(f"upgrade_with_{index}_materials", condition,
              [{**action, "recheck": True} for action in b.actions(1)])


def _own_boss(b):
    attempts = "cgwDetailCnt"
    b.model["vars"] = {attempts: 0}
    reset = {"set": {attempts: 0}}
    count = [_count(317)]
    detail = b.when(0)
    limit = _all(detail, _expr(f"{attempts} >= 8"))
    stop = b.gap("boss_attempt_limit", (76, 86), limit, [
        _push("多次点击挑战都没有进入战斗，可能已达疲劳度上限（>100）或挑战被拒，脚本停止。"),
        _stop(), {"effect": "sleep", "ms": 3000}], True, ["source Push", "source stop lifecycle"])
    challenge = [{**action, "recheck": True} for action in b.actions(0)]
    b.add("boss_attempt_limit", limit, [*challenge, reset, stop], counts=count)
    b.add("challenge_own_boss", detail, [*challenge, {"inc": attempts}], counts=count)
    for index, name in ((1, "boss_prepare"), (2, "boss_summon")):
        b.add(name, b.when(index), [{**action, "recheck": True} for action in b.actions(index)] + [reset],
              counts=count)
    b.model["proof"]["source_state_bindings"] = {"global.cgwDetailCnt": attempts}
    b.model["proof"]["resource_costs"] = "Source uses the star and ticket already selected in the summoning queue."


class _Builder:
    def __init__(self, packet, ops, colors):
        self.packet, self.ops, self.colors = packet, ops, colors
        self.model = packet["handler"]
        self.fid = self.model["id"]

    def when(self, index):
        raw = {"desc": self.ops[index].get("desc")}
        return _operator_case(self.fid, index, raw, self.colors)["when"]

    def actions(self, index):
        return _operator_case(self.fid, index, self.ops[index], self.colors)["do"]

    def add(self, name, condition, actions=(), *, outcome=True, counts=(), internal=False, retest_ms=None, group=None):
        branch = _case(name, condition, actions, outcome=outcome, counts=counts, group=group or name)
        if retest_ms:
            branch["retest_ms"] = retest_ms
        self.model["cases"].append(branch)
        if internal:
            self.packet["bookkeeping_cases"].append(name)
        return branch

    def gap(self, *args, **kwargs):
        return _gap(self.packet, *args, **kwargs)


def _exploration(b):
    from .build_mvp import EXPLORATION_EXIT_DIALOG

    left = "explore14_swipes_left"
    initialized = "explore14_swipes_initialized"
    attempts = "explore14_label_retries"
    explore_map = b.when(0)
    boss_icon = {"find": "探索_挑战BOSS"}
    monster_icon = "探索_挑战"
    tags = {"打经验": "探索_经验标识", "打掉落": "探索_掉落标识"}
    b.model["vars"] = {left: 0, initialized: False, attempts: 0}
    chapter = {"click": {"xy_param": "xy"}, "delay": 1000}
    b.add("chapter_xy", b.when(1), [chapter])
    for index in (5, 6, 4, 3):
        if index in (4, 3):
            chest = {"find": "探索_宝箱"}
            b.add(f"chest_{index}", _all(b.when(index), chest),
                  [{"click_found": True, "offset": [0, 0, 10, 10], "delay": 500}])
        b.add(f"page_{index}", b.when(index), b.actions(index))

    icon, start, end, back, confirm, contact, _ = b.actions(0)
    hit = {"click_found": True, "offset": icon["click"], "delay": icon["delay"]}
    countdown = "2 + (swipeTime == '3') + 2 * (swipeTime == '4') + 3 * (swipeTime == '5')"
    b.add("map_probe", explore_map, [{"set": {
        left: f"({countdown}) * (not {initialized}) + {left} * {initialized}",
        initialized: True, attempts: 0}}],
        outcome=None, retest_ms=500)
    # The source's while exits when its retest loses the map. The later gates
    # also check the map again after each explicit refresh.
    b.add("map_yield", {"not": explore_map}, outcome=False, internal=True)
    b.add("boss_overlay", _all(explore_map, b.when(2)),
          [{"wait": 1000}, *b.actions(2), {"set": {left: 1}}])
    b.add("boss_icon", _all(explore_map, boss_icon), [hit, {"set": {left: 1}}])
    b.add("monster_any", _all(_expr("type == '无差别'"), explore_map, {"find": monster_icon}), [hit])
    height = contact["click"][2]
    for mode, label in tags.items():
        match = {"find_near": {"target": monster_icon, "reference": label,
                               "max_below": height, "max_distance": height * 15 * 1.414}}
        b.add("monster_" + mode, _all(_expr(f"type == {mode!r}"), explore_map, match), [hit])
    missing_label = {"any": [_all(_expr(f"type == {mode!r}"), {"not": {"find": label}})
                             for mode, label in tags.items()]}
    refresh = {"handler_control": {"op": "refresh"}}
    retry_gate = b.gap("retry_phase_binding", (200, 240), {"search": "label missing"},
                       [{"effect": "resume cached scan after fresh capture"}], None,
                       ["native bounded handler phase edge"], blocking=False)
    b.add("retry_label", _all(explore_map, missing_label, _expr(f"{attempts} < 4")),
          [{"wait": 400}, refresh, {"inc": attempts}, retry_gate], outcome=None, internal=True)
    b.add("last_label_refresh", _all(explore_map, missing_label, _expr(f"{attempts} == 4")),
          [{"wait": 400}, refresh], outcome=None, internal=True)
    b.add("decrement", _expr("True"), [{"set": {left: f"{left} - 1"}}], outcome=None, internal=True)
    b.add("exit_if_view_changed", _all(_expr(f"{left} <= 0"), {"not": explore_map}), internal=True)
    b.add("exit_back", _all(_expr(f"{left} <= 0"), explore_map), [back, refresh], outcome=None)
    b.add("exit_confirm", _all(_expr(f"{left} <= 0"), EXPLORATION_EXIT_DIALOG),
          [{**confirm, "recheck": True}, {"set": {left: 0, initialized: False}}])
    b.add("exit_dialog_missing", _expr(f"{left} <= 0"),
          [{"fail": "未识别确认退出探索弹窗"}], internal=True)
    b.add("swipe_yield", {"not": explore_map}, outcome=False, internal=True)
    swipe_gate = b.gap("swipe_timing_override", (261, 266), {"move": "regionBezierSwipe"},
                       [{"effect": "swipe", "base_delay_ms": 200}], None,
                       ["native swipe timing override", "vendor path conformance"], blocking=False)
    loop_gate = b.gap("swipe_phase_binding", (174, 272), {"move": "after swipe"},
                      [{"effect": "retest chapter before continuing search"}], None,
                      ["native bounded handler phase edge"], blocking=False)
    proof = b.model["proof"]
    proof["source_phase_edges"] = {"retry_label": {
        "target_case": "boss_icon", "gate_prefix": retry_gate["fail"]}}
    proof["source_native_lowerings"] = {}
    for speed, duration in (("快", [200, 400]), ("中", [500, 700]), ("慢", [800, 1200])):
        case = f"swipe_{speed}"
        b.add(case, _all(explore_map, _expr(f"swipeSpeed == {speed!r}")),
              [swipe_gate, refresh, loop_gate], outcome=None)
        proof["source_phase_edges"][case] = {"target_case": "map_probe", "gate_prefix": loop_gate["fail"]}
        proof["source_native_lowerings"][case] = {"gate_prefix": swipe_gate["fail"],
            "native_intent": {"swipe": {"from": start["click"], "to": end["click"]},
                              "duration_ms": duration, "delay": 200}}
    proof["source_state_bindings"] = {"global.tsAttackSwhipeNum": left}
    proof["source_retest"] = {"chapter_outer_ms": 500,
        "chapter_selector": "operator 1 descriptor copied without its retest field",
        "label_search": "refresh after 400ms only for absent labels, at most five attempts"}
    b.gap("exit_confirmation_guard", (247, 254), {"move": "exit exploration"},
          [{"effect": "confirm using observed modal after back"}], True,
          ["recognize the exit confirmation before its native click"], blocking=False)


def _create_team(b):
    first = "first_create_team"
    attempts = "team27_create_attempts"
    matched = "team27_create_matched"
    b.model["vars"] = {first: False, "team_up_Frist": True, "super_next_scheme_name": "",
                       attempts: 0, matched: False}
    proof = b.model["proof"]
    proof["source_state_bindings"] = {"global.first_create_team": first,
                                     "global.team_up_Frist": "team_up_Frist",
                                     "superGlobal.next_scheme_name": "super_next_scheme_name"}
    lowerings = proof["source_native_lowerings"] = {}
    swipe_gate = b.gap("team_list_swipe", (216, 286), {"move": "regionBezierSwipe"},
                       [{"effect": "configured team list navigation"}], None,
                       ["native swipe timing and vendor curve"], blocking=False)

    def swipe(name, operator, start, end, duration, delay):
        steps = b.actions(operator)
        lowerings.setdefault(name, []).append({
            "gate_prefix": swipe_gate["fail"],
            "native_intent": {"swipe": {"from": steps[start]["click"], "to": steps[end]["click"]},
                              "duration_ms": duration, "delay": delay}})
        return swipe_gate

    first_visit = _expr(f"not {first}")
    top = {"any": [b.when(12), b.when(13)]}
    refresh = {"handler_control": {"op": "refresh"}}
    b.add("list_align", _all(first_visit, b.when(13)),
          [swipe("list_align", 13, 0, 1, [2000, 2050], 500)], outcome=None)
    options = b.actions(12)
    done = {"set": {first: True}}
    for index, level in enumerate(("魂十", "魂土", "魂王", "魂十三"), start=5):
        name = f"soul_layer_{index}"
        b.add(name, _all(first_visit, top, _expr(f"mission == '御魂' and level == {level!r}")),
              [options[0], swipe(name, 11, 4, 5, [200, 250], 500), options[index], done])
    b.add("hard_exploration", _all(first_visit, top, _expr("mission == '探索（困难）'")), [options[1], done])
    b.add("sun", _all(first_visit, top, _expr("mission == '日轮之陨'")), [options[2], options[3], done])
    b.add("sea", _all(first_visit, top, _expr("mission == '永生之海'")),
          [swipe("sea", 11, 2, 3, [1200, 1250], 500), options[2], options[4], done])
    for name, mission, option in (("experience", "经验妖怪", 9), ("gold", "金币妖怪", 9), ("ship", "石距", 10)):
        actions = [swipe(name, 11, 1, 0, [200, 250], 1500)]
        if name == "experience":
            actions.append(swipe(name, 13, 1, 0, [2000, 2050], 500))
        b.add(name, _all(first_visit, top, _expr(f"mission == {mission!r}")),
              [*actions, options[option], done])
    b.add("auto_match", _all(first_visit, top, _expr("mission == '妖气封印'"), b.when(5)),
          [*b.actions(5), done])
    b.add("source_first_visit_without_action", _all(first_visit, top), [done])
    b.add("lobby_scroll", _all(first_visit, b.when(4)),
          [swipe("lobby_scroll", 11, 0, 1, [200, 250], 500)])

    b.add("create_init", _expr("True"), [{"set": {attempts: 0, matched: False}}],
          outcome=None, internal=True)
    for index in (14, 4, 7):
        b.add(f"create_{index}", _all(_expr(f"not {matched}"), b.when(index)),
              [*b.actions(index), {"set": {"team_up_Frist": True, matched: True}}, {"inc": attempts}, refresh],
              outcome=None)
    fallback = b.gap("create_failed_rerun", (298, 305), {"attempts": 3},
                    [_rerun("关闭BUFF"), {"effect": "sleep", "ms": 2000}], True,
                    ["bind the original 关闭BUFF target and preserve superGlobal"])
    b.add("create_exhausted", _expr(f"{matched} and {attempts} >= 3"),
          [*b.actions(8), {"set": {"super_next_scheme_name": "next_scheme"}}, fallback])
    edge = b.gap("create_phase_binding", (289, 306), {"attempts": "< 3"},
                 [{"effect": "retry with a freshly captured team lobby"}], None,
                 ["native bounded handler phase edge"], blocking=False)
    b.add("retry_create", _expr(matched), [{"set": {matched: False}}, edge], outcome=None, internal=True)
    proof["source_phase_edges"] = {"retry_create": {"target_case": "create_14", "gate_prefix": edge["fail"]}}
    for index in (0, 10, 15, 1, 2, 16, 9, 3, 6):
        actions = b.actions(index)
        if index in (0, 10):
            actions.append({"set": {first: False}})
        b.add(f"match_{index}", b.when(index), actions, counts=[_count(27)])


def _challenge_entry(b):
    open_level = "sneak_level_open"
    b.model["vars"] = {open_level: True}
    b.model["proof"]["source_state_bindings"] = {"global.sneak_level_open": open_level}
    lowerings = b.model["proof"]["source_native_lowerings"] = {}
    counts = [_count(52)]
    soul = "御魂-八岐大蛇"
    levels = ("倒数第四", "倒数第三", "倒数第二", "倒数第一", "默认")
    start, end, *positions = b.actions(4)
    gate = b.gap("scroll_soul_tiers", (148, 165), {"panel": "八岐大蛇层数"},
                 [{"effect": "native swipe and optional tier selection"}], True,
                 ["vendor swipe curve conformance"], blocking=False)
    native = {"swipe": {"from": start["click"], "to": end["click"]}, "delay": 1500, "duration_ms": [400, 500]}
    for index, label in enumerate(levels):
        name = f"soul_tier_{index}"
        actions = [gate]
        if index < len(positions):
            actions.append({**positions[index], "recheck": True})
        actions.append({"set": {open_level: False}})
        b.add(name, _all(b.when(4), _expr(f"{open_level} and challenge_type == {soul!r} and sneak_level == {label!r}")),
              actions, counts=counts)
        lowerings[name] = {"gate_prefix": gate["fail"], "native_intent": native}
    types = b.model["params"]["challenge_type"]["choices"]
    for index, label in enumerate(types):
        mode = _expr(f"challenge_type == {label!r}")
        if label.startswith("御魂-"):
            routes = [(5, b.actions(5)[0]), (6, b.actions(6)[0]), (1, b.actions(1)[index])]
        elif label == "御灵":
            routes = [(0, b.actions(0)[1]), (3, b.actions(3)[0])]
        else:
            routes = [(0, b.actions(0)[2]), (2, b.actions(2)[index - 5])]
        for op, action in routes:
            b.add(f"challenge_{index}_{op}", _all(mode, b.when(op)), [action], counts=counts)


def _assist_fighter(b):
    b.model["vars"] = {"frist": True}
    proof = b.model["proof"]
    proof["source_state_bindings"] = {"global.frist": "frist"}
    lowerings = proof["source_native_lowerings"] = {}
    counts = [_count(692)]
    first = _expr("frist")
    no_assist = b.gap("no_assist_lifecycle", (135, 153), {"screen": "无协战式神"},
                      [{"effect": "guard the two back/confirm steps and use original 000 shutdown config"}], True,
                      ["original stop/Push/rerun lifecycle and positive confirmation evidence"])
    b.add("no_assist", _all(first, b.when(2)), [no_assist], counts=counts)
    motion = b.gap("drag_assist_unit", (154, 173), {"screen": "上阵协战式神"},
                   [{"effect": "drag source support slot onto lineup"}], True,
                   ["verify drag and post-drag UI confirmation"], blocking=False)
    for index in (0, 3):
        name = f"drag_unit_{index}"
        start, end, accept = b.actions(index)
        b.add(name, _all(first, b.when(index)), [motion, {**accept, "recheck": True}, {"set": {"frist": False}}],
              counts=counts)
        lowerings[name] = {"gate_prefix": motion["fail"], "native_intent": {
            "swipe": {"from": start["click"], "to": end["click"]}, "delay": 1000, "duration_ms": [800, 1000]}}
    for index in (1, 6, 4, 5, 7, 8):
        scene = _all(first, b.when(index)) if index in (1, 6) else b.when(index)
        b.add(f"support_{index}", scene, [{**action, "recheck": True} for action in b.actions(index)], counts=counts)


def _invite_friend(b):
    first, count = "team_up_Frist", "team_up_Time"
    lag, lag_known = "team306_lag_ms", "team306_lag_known"
    opened, tab, second = "team306_opened", "team306_tab_selected", "team306_second_selected"
    locals_ = {opened: False, tab: False, second: False}
    b.model["vars"] = {first: True, count: 0, lag: 0, lag_known: False, **locals_}
    proof = b.model["proof"]
    proof["source_state_bindings"] = {
        "global.team_up_Frist": first, "global.team_up_Time": count, "global.team_up_lagTime": lag}
    lobby = {"any": [b.when(2), b.when(10)]}
    modal = b.when(1)
    refresh = {"handler_control": {"op": "refresh"}}
    b.add("reset_locals", _expr("True"), [{"set": locals_}], outcome=None, internal=True)
    b.add("reset_lag", {"any": [_expr(f"not {lag_known}"), {"not": lobby}]},
          [{"set": {lag: "elapsed_ms", lag_known: True}}], outcome=None, internal=True)
    b.add("battle_reset", b.when(5), [{"set": {count: 0, first: False}}], outcome=False, internal=True)
    due = _expr(f"{first} or elapsed_ms - {lag} > 15000")
    b.add("unlock", _all(due, b.when(13)), b.actions(13), outcome=None)

    for name, index, actions in (("pair", 4, b.actions(4)[1:]), ("trio", 0, b.actions(0))):
        b.add(f"open_{name}", _all(due, _expr(f"not {opened}"), b.when(index)),
              [*actions, {"set": {opened: True}}], outcome=None)
    for index in (11, 12):
        b.add(f"open_sea_{index}", _all(due, _expr(f"not {opened}"), b.when(10), b.when(index)),
              b.actions(index), outcome=None)
    b.add("mark_open_sea", _all(due, _expr(f"not {opened}"), b.when(10)),
          [{"set": {opened: True}}], outcome=None, internal=True)
    b.add("open_gold_exp", _all(due, _expr(f"not {opened}"), b.when(14)),
          [*b.actions(14), {"set": {opened: True}}], outcome=None)
    b.add("record_open", _expr(opened), [{"set": {first: False, lag: "elapsed_ms"}}, {"inc": count}],
          outcome=None, internal=True)
    stop = b.gap("invite_timeout", (284, 342), {"opened_more_than": 10},
                 [_push("多次邀请未响应，或多次未识别到昵称，请查看。"), _stop(),
                  {"effect": "sleep", "ms": 3000}], None, ["source Push and stop lifecycle"])
    b.add("too_many_openings", _expr(f"{opened} and {count} > 10"), [stop], outcome=False, internal=True)
    b.add("return_opened", _expr(opened), internal=True)

    invalid = b.gap("invite_profile_guard", (349, 413), {"screen": "invite list"},
                    [{"effect": "require explicit distinct nicknames and supported OCR profile"}], None,
                    ["calibrate source fuzzy OCR discovery"], blocking=False)
    b.add("unsupported_nicknames", _all(modal, _expr(
        "not inviteName or (secondPlayer and (not inviteNameTwo or inviteName == inviteNameTwo)) "
        "or stringCompareMode != '包含'")), [invalid], outcome=False, internal=True)
    tabs = [(6, 0, "跨区"), (7, 0, "跨区"), (8, 0, "好友"), (8, 1, "跨区"),
            (15, 0, "跨区"), (15, 1, "好友")]
    for index, action_index, area in tabs:
        b.add(f"tab_one_{index}_{action_index}", _all(modal, _expr(f"not {tab} and selectArea == {area!r}"),
                                                     b.when(index)),
              [b.actions(index)[action_index], refresh, {"set": {tab: True}}], outcome=None)
    ocr_rect, invite = b.actions(1)
    x, y, right, bottom = ocr_rect["click"]

    def name_match(param):
        return {"ocr_full": {"keyword_var": param, "region": [x, y, right - x, bottom - y],
                             "selection": "unique_contains", "evidence": "complete_keyword"}}

    missed = [*b.actions(4)[:1], {"inc": count}, {"set": {lag: "elapsed_ms - 15001"}}]
    b.add("select_first", _all(modal, name_match("inviteName")),
          [{"click_found": True, "offset": [20, 0, 50, 65], "delay": 1000, "recheck": True},
           {"set": {opened: True}}], outcome=None)
    b.add("missing_first", _all(modal, _expr(f"not {opened}")), missed)
    b.add("invitation_lost", _all(_expr(opened), {"not": modal}), outcome=False, internal=True)
    different_tab = _expr(f"{opened} and secondPlayer and selectArea != selectAreaTwo")
    for action_index, area in ((0, "跨区"), (1, "好友")):
        b.add(f"tab_two_{action_index}", _all(modal, different_tab,
              _expr(f"selectAreaTwo == {area!r}"), b.when(7)), [b.actions(7)[action_index]], outcome=None)
    b.add("refresh_second_tab", _all(modal, different_tab), [refresh], outcome=None, internal=True)
    b.add("select_second", _all(modal, _expr(f"{opened} and secondPlayer"), name_match("inviteNameTwo")),
          [{"click_found": True, "offset": [10, 0, 50, 65], "delay": 1000, "recheck": True},
           {"set": {second: True}}], outcome=None)
    b.add("missing_second", _all(modal, _expr(f"{opened} and secondPlayer and not {second}")), missed)
    b.add("send_invitation", _all(modal, _expr(f"{opened} and (not secondPlayer or {second})")),
          [{**invite, "recheck": True}], counts=[_count(306)])
    b.add("mistouch", b.when(9), b.actions(9))
    proof["nickname_search"] = {"selection": "unique full substring in source list crop",
                               "ambiguity": "use source missing-name branch, with no send",
                               "fuzzy_search": "guarded until source OCR profile is calibrated"}


def _reward(b, index, lines):
    name = "组队探索_宝箱"
    if name not in b.colors or b.colors[name].get("type") != "find_colors":
        raise UnsupportedHandler("missing source exploration chest resource")
    b.add("exploration_reward", _all(b.when(index), {"find": name}),
          [{"click_found": True, "offset": [0, 0, 5, 5], "delay": 500}])
    b.model["proof"]["reward_contract"] = {"source_lines": lines, "counter_id": None,
        "on_search_miss": "continue same invocation on cached frame", "offset": [0, 0, 5, 5], "delay_ms": 500}


def _accept(b):
    b.model["vars"] = {"yaoqing_close": False}
    _reward(b, 4, [96, 106])
    for index in (2, 3):
        b.add(f"leader_no_action_{index}", _all(_expr("teammate_exit and teammate_exit_next_scheme == '__不做动作__'"), b.when(index)),
              [{"wait": 3000}], counts=[_count(4)])
        fail = b.gap(f"leader_exit_{index}", (107, 114),
            {"config": "teammate_exit and teammate_exit_next_scheme != '__不做动作__'", "operator": index},
            [_rerun({"config": "teammate_exit_next_scheme"}), {"effect": "sleep", "ms": 3000}], True,
            ["source_rerun/real named scheme and sentinel resolution", "source_lifecycle"])
        b.add(f"leader_exit_{index}", _all(_expr("teammate_exit and teammate_exit_next_scheme != '__不做动作__'"), b.when(index)),
              [fail], counts=[_count(4)])
    b.add("reward_then_auto_yield", _all(_expr("auto_team and yaoqing_close"), b.when(4)), outcome=False)
    b.add("auto_team_yield", _expr("auto_team and yaoqing_close"), outcome=False, internal=True)
    b.add("accept_automatic", b.when(0), b.actions(0) + [{"set": {"yaoqing_close": True}}], counts=[_count(4)])
    b.add("accept_once", b.when(1), b.actions(1), counts=[_count(4)])
    b.add("reward_search_missed", b.when(4), outcome=False)
    b.model["proof"]["source_state_bindings"] = {"global.yaoqing_close": "yaoqing_close; source default=false; set only after operator0 input"}
    b.model["proof"]["source_returns"] = {"auto_team_guard": False,
        "native_input_or_leader_exit": True, "fallthrough": "undefined; outer Script.oper yields false",
        "reward_marker_without_search_hit": "recognized source check; no true return/currentDate refresh"}


def _challenge(b):
    _reward(b, 8, [105, 115])
    b.add("eternal_sea", b.when(4), b.actions(4))
    ready, reward = b.when(0), b.when(8)
    anybody = _all(ready, _expr("type == '有人就开'"))
    gold = _all(anybody, b.when(7))
    b.add("gold_exp_start", _all(gold, {"not": b.when(5)}), b.actions(3))
    b.add("gold_exp_visual_exit", _all(gold, b.when(5), b.when(6)), b.actions(6))
    normal = _all(anybody, {"not": b.when(7)}, {"not": b.when(1)})
    b.add("normal_wait_for_reward", _all(normal, reward), [{"wait": 2000}] + b.actions(3))
    b.add("normal_start", normal, b.actions(3))
    three = _all(ready, _expr("type == '三人'"), {"not": b.when(1)}, {"not": b.when(2)})
    b.add("three_start", three, b.actions(3))
    # Positive detection can legitimately yield: preserve recognition without
    # inventing an input or refreshing Script.currentDate on a false return.
    b.add("known_team_waiting", {"any": [ready, reward]}, outcome=False)
    b.model["proof"]["source_counter_id"] = None
    b.model["proof"]["literal_branch_semantics"] = {
        "gold_exp_start": "operator7 AND NOT operator5 (preserve source negation despite comment)",
        "gold_exp_exit": "operator7 AND operator5 AND operator6; visual glyph, not an elapsed timer",
        "normal": "NOT operator7 AND NOT operator1; wait2000 only when operator8 matches",
        "three": "NOT operator1 AND NOT operator2; short-circuit source order",
        "returns": "true only on native input branches; otherwise false",
    }


def _solo(b):
    b.model["vars"] = {"team6_attempts": 0, "team6_matched": False}
    b.add("local_init", _expr("True"), [{"set": {"team6_attempts": 0, "team6_matched": False}}], outcome=None, internal=True)
    for index in range(3):
        actions = b.actions(index)
        if len(actions) != 1 or actions[0]["delay"] != 1000:
            raise UnsupportedHandler("006 audited delay split no longer applies")
        actions[0]["delay"] = 0
        actions.append({"set": {"team6_matched": True}})
        b.add(f"attempt_op_{index}", _all(_expr("not team6_matched"), b.when(index)),
              actions, outcome=None, counts=[_count(6)])
    b.add("unmatched_entry", _expr("not team6_matched and team6_attempts == 0"), outcome=False, internal=True)
    b.add("challenge_disappeared", _expr("not team6_matched and team6_attempts > 0"), outcome=True, internal=True)
    b.add("refresh_after_input", _expr("team6_matched"),
          [{"set": {"team6_attempts": "team6_attempts + 1", "team6_matched": False}}],
          outcome=None, internal=True, retest_ms=1000)
    fail = b.gap("three_attempts_rerun", (64, 83), {"local": "curCnt reaches 3 after keepScreen(false)"},
        [{"effect": "source_toast", "text": "连续执行3次挑战后未开始，脚本自动停止"},
         {**_rerun({"config": "next_scheme"}), "noop_target": "__不做动作__ returns false without broadcast"},
         {"effect": "sleep", "ms": 2000}], False,
        ["source_toast", "source_rerun unless __不做动作__ (default __停止脚本__, including Push/stop)", "source_lifecycle"])
    b.add("three_attempts_rerun", _expr("team6_attempts >= 3"),
          [fail], outcome=False, internal=True)
    b.add("retry_challenge", _expr("team6_attempts < 3"),
          [{"fail": "unresolved_source_obligation:team6.phase_loop_lowering requires team_workflow"}],
          outcome=None, internal=True)
    b.model["proof"]["source_phase_edges"] = {"retry_challenge": {
        "target_case": "attempt_op_0", "gate_prefix": "unresolved_source_obligation:team6.phase_loop_lowering",
        "bounded_by": "team6_attempts < 3; initialized0; incremented once per native refresh",
    }}
    b.model["proof"]["bounded_loop"] = {"max_attempts": 3, "locals_reset": "every handler invocation",
        "refresh_after_each_input": True, "fixed_delay_relocated_ms": 1000, "added_delay_ms": 0,
        "third_refresh_disappearance": "still reruns and returns false; source does not test success again",
        "counter": "id6 event before each input; strict7500ms suppression remains framework-owned"}


def _buff_probe(b, flag):
    b.model["vars"][flag] = False
    b.model["proof"].setdefault("source_state_bindings", {})["global." + flag] = flag
    b.add("buff_probe", b.when(0), [{"set": {flag: True}}], outcome=None, counts=[_count(b.fid)])


def _buff_offset(b):
    raw = b.ops[0]["oper"][0]
    # Source uses transformed oper[0][2:4], the end point, as delta extents.
    return [0, 0, raw[5], raw[6]]


def _close_buff(b, runtime_target, super_target, runtime_params):
    b.model["vars"] = {"team40_runtime_next_scheme": runtime_target,
        "super_next_scheme_name": super_target, "team40_next_scheme": ""}
    b.model["proof"]["source_state_bindings"] = {
        "runtimeParams.next_scheme_name": "team40_runtime_next_scheme (initial snapshot, distinct from config)",
        "superGlobal.next_scheme_name": "super_next_scheme_name (empty string denotes source null)",
        "global.closed_buff": "closed_buff", "runtime_payload": copy.deepcopy(runtime_params),
        "undeclared_config": {"afterCountOper": "停止脚本 / 关闭应用 / any other value => no source effect"}}
    _buff_probe(b, "closed_buff")
    active_buff = {"find": "开启的BUFF"}
    b.add("close_active_buff", _all(b.when(0), active_buff),
          [{"click_found": True, "offset": _buff_offset(b), "delay": 1000, "recheck": True}])
    b.add("close_panel", _all(b.when(0), {"not": active_buff}), [{**b.actions(0)[1], "recheck": True},
          {"set": {"team40_next_scheme": "team40_runtime_next_scheme"}}], outcome=None)
    b.add("consume_super_target", _expr("not team40_next_scheme"),
          [{"set": {"team40_next_scheme": "super_next_scheme_name", "super_next_scheme_name": repr("")}}],
          outcome=None, internal=True)
    b.add("configured_target", _expr("scheme_switch_enabled"),
          [{"set": {"team40_next_scheme": "next_scheme"}}, {"wait": 3000}], outcome=None, internal=True)
    stop = b.gap("after_count_stop", (75, 86), {"target": "falsy", "config": "afterCountOper == '停止脚本'"},
        [_push("[${schemeHistory names joined by 、}]已停止，请查看。"), _stop()], True,
        ["source_push", "source_lifecycle/stop"])
    b.add("after_count_stop", _expr("not team40_next_scheme and afterCountOper == '停止脚本'"), [stop], internal=True)
    close_app = b.gap("after_count_close_app", (79, 85), {"target": "falsy", "config": "afterCountOper == '关闭应用'"},
        [{"effect": "source_stop_related_apps", "settings": ["defaultLaunchAppList", "kill_related_app_mode"]},
         _push("[${schemeHistory}]已停止，应用[${packageNames}]已杀，请查看。"), {"effect": "sleep", "ms": 2000}, _stop()],
        True, ["source_stop_related_apps", "source_push", "source_lifecycle/stop"])
    b.add("after_count_close_app", _expr("not team40_next_scheme and afterCountOper == '关闭应用'"),
          [{"wait": 1000}, close_app], internal=True)
    b.add("target_no_action", _expr("team40_next_scheme == '__不做动作__'"), [{"wait": 1000}], internal=True)
    rerun = b.gap("target_rerun", (66, 93), {"target": "team40_next_scheme (truthy and not __不做动作__)"},
        [{**_rerun({"var": "team40_next_scheme"}), "params": copy.deepcopy(runtime_params or {}),
          "params_source": "{...thisScript.runtimeParams}; preserve all initial JSON keys, not scheme config"}],
        True, ["source_rerun/target resolution and runtime-parameter handoff", "source_lifecycle"])
    b.add("target_rerun", _expr("team40_next_scheme and team40_next_scheme != '__不做动作__'"), [{"wait": 1000}, rerun], internal=True)
    b.add("closed_without_target", _expr("True"), outcome=True, internal=True)
    # The above fallthrough belongs ONLY to a matched BUFF probe. Bound phase
    # cases must skip lifecycle statements when initial comparison did not match.
    _guard_buff_body(b, "buff_probe", "closed_without_target")
    b.add("ready_once", _all(_expr("ready_once_buff and not closed_buff"), b.when(1)),
          [{**action, "recheck": True} for action in b.actions(1)], counts=[_count(40)])


def _guard_buff_body(b, start, end):
    """Latch the original BUFF entry; local phases may not enter on a miss."""
    key = f"team{b.fid}_buff_entered"
    b.model["vars"][key] = False
    init = _case("buff_local_init", _expr("True"), [{"set": {key: False}}], outcome=None, group="buff_local_init")
    b.model["cases"].insert(0, init)
    b.packet["bookkeeping_cases"].append("buff_local_init")
    inside = False
    for branch in b.model["cases"]:
        if branch["id"] == start:
            branch["do"].append({"set": {key: True}})
            inside = True
            continue
        if inside:
            branch["when"] = _all(_expr(key), branch["when"])
        if branch["id"] == end:
            break


def _open_buff(b):
    native = {"swipe": {"from": b.ops[4]["oper"][0][3:7], "to": b.ops[4]["oper"][1][3:7]},
              "duration_ms": [1000, 1300], "delay": 200}
    fail = b.gap("swipe_timing_override", (95, 103),
        {"operator": 4, "host": "team_workflow required; common base >200 cannot be subtracted from native delay"},
        [{"effect": "source_swipe", "native_intent": native, "baseSleep": 200,
          "randomSleep": "scheme.commonConfig.afterClickDelayRandom", "input_delay_literals_ignored": [1000, 1000]}],
        True, ["per-input swipe base override when common afterClickDelayBase >200"])
    b.add("special_area_swipe", b.when(4), [fail], counts=[_count(50)])
    b.model["proof"]["source_native_lowerings"] = {"special_area_swipe": {"native_intent": native,
        "gate_prefix": SWIPE_GATE, "policy": "subtract integer common base from delay200 if <=200; otherwise retain gate"}}
    _buff_probe(b, "opened_buff")
    b.add("obstructed_soul_buff", _all(b.when(0), _expr("buff_type == '御魂'"), b.when(1)), b.actions(1))
    for buff in ("觉醒", "御魂", "金币", "经验"):
        b.add("enable_" + buff, _all(b.when(0), _expr(f"buff_type == {buff!r}"), {"find": "关闭的BUFF_" + buff}),
              [{"click_found": True, "offset": _buff_offset(b), "delay": 1000}])
    b.add("close_panel", b.when(0), [b.actions(0)[1]], outcome=None)
    b.add("configured_no_action", _expr("scheme_switch_enabled and next_scheme == '__不做动作__'"), internal=True)
    rerun = b.gap("configured_rerun", (126, 133), {"config": "scheme_switch_enabled and next_scheme != '__不做动作__'"},
        [_rerun({"config": "next_scheme"})], True, ["source_rerun", "source_lifecycle"])
    b.add("configured_rerun", _expr("scheme_switch_enabled and next_scheme != '__不做动作__'"), [rerun], internal=True)
    stop = b.gap("finished_stop", (129, 133), {"config": "not scheme_switch_enabled and not ready_once_buff"},
        [_push("[${schemeHistory names joined by 、}]已停止，请查看。"), _stop()], True,
        ["source_push", "source_lifecycle/stop"])
    b.add("finished_stop", _expr("not ready_once_buff"), [stop], internal=True)
    b.add("ready_mode_finished", _expr("True"), internal=True)
    _guard_buff_body(b, "buff_probe", "ready_mode_finished")
    # Preserve special-area priority over local BUFF bookkeeping/probes.
    local = b.model["cases"].pop(0)
    b.model["cases"].insert(1, local)
    for index in (2, 3):
        b.add(f"ready_once_{index}", _all(_expr("ready_once_buff and not opened_buff"), b.when(index)),
              b.actions(index), counts=[_count(50)])


def team_workflow(name, definitions, *, scheme=None, config_overrides=None,
                  common_overrides=None, shared_defaults=None,
                  supported_primitives=("handler_control",), supported_builtins=("elapsed_ms",)):
    """Return self-contained guarded native phase YAML, always complete=False.

    Accepts team/core packets and ordinary handler models. Config override order
    remains declaration -> source scheme -> explicit override. RuntimeParams is
    never merged into scheme config. This wrapper lowers bounded phases and
    native swipe timing in the audited families.
    """
    models = [copy.deepcopy(d.get("handler", d)) for d in definitions]
    active_ids = (scheme or {}).get("list", [model["id"] for model in models])
    for model in models:
        if model["id"] == 602 and model.get("proof", {}).get("source_path") == SOURCE_FILES[602]:
            model["vars"]["dojo602_scheme_has_519"] = 519 in active_ids
        if (model["id"] == 1106 and 510 in active_ids
                and model.get("proof", {}).get("source_path") == SOURCE_FILES[1106]):
            from .preset_handler import ONCE_GROUP, ONCE_PRESET
            restore = next(case for case in model["cases"] if case["id"] == "restore_record_preset")
            restore["do"][-1]["set"].update({ONCE_GROUP: "cfg_510_groupNum", ONCE_PRESET: "cfg_510_defaultNum"})
    scheme_norm = copy.deepcopy(scheme) if scheme is not None else None
    overrides_norm = copy.deepcopy(config_overrides) if config_overrides is not None else None
    for cfg_map in (scheme_norm.get("config") if isinstance(scheme_norm, dict) else None, overrides_norm):
        if not isinstance(cfg_map, dict):
            continue
        if "600" in cfg_map:
            from .guild_launcher_handlers import normalize_guild_launcher_config
            cfg_map["600"] = normalize_guild_launcher_config(cfg_map["600"])
        if "603" in cfg_map:
            from .narrow_realm_handlers import normalize_narrow_realm_config
            cfg_map["603"] = normalize_narrow_realm_config(cfg_map["603"])
        if "693" in cfg_map:
            from .bounty_mentor_handlers import normalize_master_config
            cfg_map["693"] = normalize_master_config(cfg_map["693"])
        if "304" in cfg_map and isinstance(cfg_map["304"], dict):
            raw_rank = cfg_map["304"].get("rankOpen")
            if isinstance(raw_rank, str) and re.fullmatch(r"\s*[0-9]{1,6}\s*", raw_rank):
                cfg_map["304"] = {**cfg_map["304"], "rankOpen": int(raw_rank.strip())}
        if "316" in cfg_map and isinstance(cfg_map["316"], dict):
            raw_over = cfg_map["316"].get("overTimes")
            if isinstance(raw_over, str) and re.fullmatch(r"\s*[0-9]{1,6}\s*", raw_over):
                cfg_map["316"] = {**cfg_map["316"], "overTimes": int(raw_over.strip())}
        if "318" in cfg_map and isinstance(cfg_map["318"], dict):
            raw_time = cfg_map["318"].get("time")
            if isinstance(raw_time, str) and re.fullmatch(r"\s*[0-9]{1,8}\s*", raw_time):
                cfg_map["318"] = {**cfg_map["318"], "time": int(raw_time.strip())}
    common = {**COMMON_DEFAULTS, **(scheme_norm or {}).get("commonConfig", {}), **(common_overrides or {})}
    for model in models:
        if model.get("proof", {}).get("scope") != "pinned-team-family-partial":
            continue
        fid = model["id"]
        values = {k: v["default"] for k, v in model["params"].items()}
        values.update((scheme_norm or {}).get("config", {}).get(str(fid), {}))
        values.update((overrides_norm or {}).get(str(fid), {}))
        _validate_config(fid, model["params"], values)
        for spec in model["resource_specs"].values():
            if spec.get("type") == "find_colors":
                spec.setdefault("similarity", common["multiColorSimilar"])
    result = core_workflow(name, models, scheme=scheme_norm, config_overrides=overrides_norm,
        common_overrides=common_overrides, shared_defaults=shared_defaults,
        supported_primitives=supported_primitives, supported_builtins=supported_builtins)
    by_slot = {h["slot"]: h for h in result["program"]["handlers"]}
    by_id = {state["id"]: state for state in result["workflow"]["states"]}
    phase_var = result["workflow"]["handler_dispatch"]["phase_var"]
    base = int(result["program"]["common_config"]["afterClickDelayBase"])
    for state in result["workflow"]["states"]:
        step = state.get("handler_step", {})
        model = by_slot.get(step.get("slot"))
        if model is None:
            continue
        for key, edge in model.get("proof", {}).get("source_phase_edges", {}).items():
            if state["id"] != f"h{model['slot']}_{key}":
                continue
            target = by_id[f"h{model['slot']}_{edge['target_case']}"]
            phase_test = target["when"]["all"][0]["expr"]
            match = re.fullmatch(re.escape(phase_var) + r" == (\d+)", phase_test)
            if not match or state["do"][-1].get("set", {}).get(phase_var) is None:
                raise UnsupportedHandler("handler phase layout changed; bounded loop lowering refused")
            state["do"] = [action for action in state["do"]
                           if not str(action.get("fail", "")).startswith(edge["gate_prefix"])]
            state["do"][-1]["set"][phase_var] = int(match[1])
        case = state["id"].removeprefix(f"h{model['slot']}_")
        if model["id"] == 16 and case in ("wait_extreme", "wait_normal"):
            delay = next(action for action in state["do"] if "wait" in action)
            delay["wait"] = min(3000, max(200, int(common["loopDelay"])))
        if model["id"] == 12 and case == "page_and_switch":
            click = next(action for action in state["do"] if "click" in action)
            click["delay"] += 500 + int(result["program"]["common_config"]["afterClickDelayRandom"]) - base
        if model["id"] == 609 and case == "guild609_logout_seen":
            # The source resets the dispatcher-owned battle counter after logout.
            state["do"].insert(-1, {"set": {"run_times_2": 0}})
        lowerings = model.get("proof", {}).get("source_native_lowerings", {}).get(case, [])
        if isinstance(lowerings, dict):
            lowerings = [lowerings]
        next_index = 0
        for spec in lowerings:
            native = copy.deepcopy(spec["native_intent"])
            for index in range(next_index, len(state["do"])):
                action = state["do"][index]
                if str(action.get("fail", "")).startswith(spec["gate_prefix"]):
                    next_index = index + 1
                    if base <= native["delay"]:
                        native["delay"] -= base
                        state["do"][index] = native
                    break
            else:
                raise UnsupportedHandler("native swipe placeholder is missing")
    contract = {"version": 1, "source_complete": False, "coverage": "guarded-team-handler-partial",
        "source_obligations": copy.deepcopy(result["source_obligations"]),
        "audited_handlers": [{"id": h["id"], "slot": h["slot"],
            "source_path": h["proof"]["source_path"], "source_sha256": h["proof"]["source_sha256"],
            "helper_pins": copy.deepcopy(h["proof"]["helper_pins"]),
            "helper_pins_verified": h["proof"]["helper_pins_verified"],
            "source_state_bindings": copy.deepcopy(h["proof"].get("source_state_bindings", {}))}
            for h in result["program"]["handlers"] if h.get("proof", {}).get("scope") == "pinned-team-family-partial"],
        "find_similarity": "per-resource source similar, else source common multiColorSimilar",
        "swipe_override": "native source delay minus common integer base when nonnegative; failure gate otherwise",
        "missing_effect_policy": "native prefix then workflow_fail; never fake click or successful source stop"}
    result["workflow"]["team_handler_contract"] = contract
    result.update(coverage="guarded-team-handler-partial", complete=False, original_task_complete=False)
    _data(result)
    return result


def load_team_handler(upstream_root, fid, **options):
    """Verify the full audited helper/source bytes and read inert resource data."""
    if type(fid) is not int or fid not in SOURCE_FILES:
        raise UnsupportedHandler("unsupported pinned team handler")
    root = Path(upstream_root)
    for relative, pin in HELPER_PINS.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != pin:
            raise UnsupportedHandler(f"team helper fingerprint mismatch: {relative}")
    from .assttyys import convert_colors
    packet = compile_team_handler((root / SOURCE_FILES[fid]).read_bytes().decode("utf-8"),
                                  convert_colors(root / "src/common"), **options)
    packet["handler"]["proof"]["helper_pins_verified"] = True
    return packet
