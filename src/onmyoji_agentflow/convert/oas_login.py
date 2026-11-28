"""Source-pinned native OAS login harvest, with explicit unresolved inputs."""
from __future__ import annotations

import re
from pathlib import Path

from .astpins import source_node_hash
from .navigation_native import NavigationCompiler
from .oas_battle import _Sources, _ref
from ..device.adb import ONMYOJI_PACKAGE
from ..workflow.oas_schedule import SERVER_TIMING
from ..workflow.schema import RESTART_CONFIRMATION

LOGIN = "tasks/Restart/login.py"
HARVEST_PINS = {
    ("tasks/GlobalGame/config_emergency.py", "FriendInvitation"): "32e0ac8d66f08fdedada0530155ede08c5b80779a16e4918e47b96b497c0e1f9",
    ("tasks/GlobalGame/config_emergency.py", "Emergency"): "770c972eeccbfa293dc7b9bdac9a39c78270589590f655587dc3991e03bcc6b0",
    ('tasks/Restart/login.py', 'LoginHandler.harvest'): "187fbfc8f9182f080a4e090e588b594cdb1631e967ab42d03f396be1274debb8",
    ('tasks/Restart/login.py', 'LoginHandler.harvest_mail'): "782c4d3f5880d133b54cf60fa269719bec8afa40da3bafe614e386446da22768",
    ('tasks/Restart/login.py', 'LoginHandler.harvest_courtyard_affairs'): "ad1f7186ea0756fe610b8f1a19fab7fb395c09e68ca795a21fd73164d0ab388a",
    ('tasks/Restart/config.py', 'HarvestConfig'): "395ee933040c311f900de18422046fcfe05b98f6e30e969b7d6d33dbab514f2a",
    ('tasks/Restart/assets.py', 'RestartAssets'): "7e52faf23b2009e5a3343946f26c5adbf7a645f183d3c68e2c23ec58767e36f3",
    ('tasks/GlobalGame/assets.py', 'GlobalGameAssets'): "2d1bec38e48768ce5d08a3bc8c64aa7d2e75bea78b9d8fb698a81d4b8cab7231",
    ('tasks/base_task.py', 'BaseTask._burst'): "7f16e876cd276719011a06166abce14ca0daa37848e5fd4f5532d8804a52d7e6",
    ('tasks/base_task.py', 'BaseTask.appear'): "f350504816e2e4b29b1004a63d67dd833066726c8a2f75f6e3a0c9e593108b52",
    ('tasks/base_task.py', 'BaseTask.appear_then_click'): "6423233e67e6ced3a735c094deeb6327e9e28adf36532e70267a3a21a8beaffd",
    ('tasks/base_task.py', 'BaseTask.appear_multi_scale'): "b1edb4c8a1ecb84fabdcc55a1ba495c9ba24087cf7109ec4a0ecca85c4ab0640",
    ('tasks/base_task.py', 'BaseTask.appear_then_click_multi_scale'): "2d4f125baa64e895f4f76f8263023fef73a7d29319593bb7a1a16bdd1a7935e1",
    ('tasks/base_task.py', 'BaseTask.ui_click'): "82895b45eaa4574dd75f65bc37b050b3fcd4af1a06a07d8e2d3ffff7ead4ced4",
    ('tasks/base_task.py', 'BaseTask.ui_click_until_disappear'): "df718484825bbc8dd8d89ee665625dab22d5dadc753ba0936b59ffac5610ad23",
    ('tasks/base_task.py', 'BaseTask.ui_click_multi_scale'): "8e94f871c024d8a9b3784106d6deaabb84fe5419e718abcd7f4b8778590118f4",
    ('tasks/base_task.py', 'BaseTask.ui_reward_appear_click'): "230a60d4533b701cc74d074d7a4f49886464994c7eb187e508958430f0045a7a",
    ('tasks/base_task.py', 'BaseTask.wait_until_appear'): "7df1fd661f438e429b2c0c2e2e22e3868273a38decc37d090b4b2bdb363b21b7",
    ('module/base/timer.py', 'Timer'): "5469429f0bca141b576bfcee426d577f14911023fcc32dc8d0c363c37b1b57cb",
    ('module/atom/image.py', 'RuleImage.match_multi_scale'): "d446053237da761b7a5c009b5c276e0fe48c77119c132436dfedcf63f3fcbb5c",
    ('module/atom/image.py', 'RuleImage.coord'): "6a6819efda5a68234667e4916f9a9bafaf6e834f1006b21b50f234d021ed68b6",
}

MAIL_ICON = ("I_HARVEST_MAIL", (0.8, 1.1))
MAIL_COPY = "I_HARVEST_MAIL_COPY"
READ_MAIL = "I_READ_ALL_MAIL"
RED_CLOSE = "I_LOGIN_RED_CLOSE"
COURTYARD_PAGE = "I_PAGE"
COURTYARD_INTRO = {"text": "", "pattern": "^点击任意位置继续$", "region": [500, 455, 280, 47]}
COURTYARD_SOUL_DONATION = {"text": "", "pattern": r"提交\s*\d+\s*星御魂", "region": [573, 126, 367, 526]}


LOGIN_PINS = {
    ("module/device/device.py", "Device"): "636829c8d9869a11eb736a84f2e5f67366e0e9dcb81d55f6015117647526f333",
    ("module/device/app_control.py", "AppControl.app_is_running"): "804ade027d902a612d0c7a3f80182d1d7e7f02f37759361cf7f6d75302b97338",
    ("tasks/Script/config_error.py", "Error"): "638cb0bb24585b97cb363223cf9a3a5748075106ae71efdb5ff2aedc7d600499",
('tasks/Restart/login.py', 'LoginHandler.__init__'): "7dc5d3383bacd930e95b08699863acabde39c09bee0205dfd4e07b6351df7822",
    ('tasks/Restart/login.py', 'LoginHandler._app_handle_login'): "4f4b302bdd45dc1d9a82c587ff843949161f40170e5e6f672685f4b7a0d26742",
    ('tasks/Restart/login.py', 'LoginHandler.app_handle_login'): "513c60e22fadc9d111cd7fa71b8e5ed42fb5d5a5a373f20b71c635fdbfe061f8",
    ('tasks/Restart/login.py', 'LoginHandler.set_specific_usr'): "b36a206712929730e6baa87f9a449aee71fd5cecb4fa5fd06767f420a73d9ee4",
    ('tasks/Restart/config.py', 'LoginCharacterConfig'): "cee195fbfd920e6f29cf95926c1fc263d484552bc4d4476faa6a4ffb07e6f9ed",
    ('tasks/base_task.py', 'BaseTask.click'): "a3aa167fab247793e5ac2795008d3be9bff1d3adfb853c0e5c96ca8f0e09d299",
    ('tasks/base_task.py', 'BaseTask.ocr_appear'): "a8b4579fbca1274dfdeba4dfe2dc012738be7d682c6631946c0d716b281d1cd5",
    ('tasks/base_task.py', 'BaseTask.ocr_appear_click'): "899b7ffb2045f42e893eb7e750f7959d416fc33514188fee298423764c8aee8b",
    ('module/atom/ocr.py', 'RuleOcr.coord'): "f766c4a32388b66ab7fa6cf9da8891b7621de01fc3e94337855e335d8ebe75eb",
    ('tasks/GameUi/default_pages.py', 'handle_login_page'): "0851c8acdd999f41d3eb6207dd8e663dd269419eb0de16ca56a319b06781f0e4",
    ('tasks/GameUi/assets.py', 'GameUiAssets'): "f18d3324416fcb59ab86ad2e9320762fdeefef138be6bd256dd619da88fa433f",
    ('tasks/Component/GeneralBuff/assets.py', 'GeneralBuffAssets'): "53b30d44c5023f21c3374808cf3c81bb7e99285166e2bb1483f3e26b01a8ec65",
    ('tasks/Component/GeneralInvite/assets.py', 'GeneralInviteAssets'): "441d5280e43a84a1f44a141e203cba058dea8e0b58b848735d61f99d5c479c33",
    ("module/device/device.py", "Device.stuck_record_add"): "8309f3fb4036ce55516979aba6bd27729f44c43f3923ab16f1b0cb9242c8dcd5",
    ("module/device/device.py", "Device.stuck_record_clear"): "46d740ef699eac268e1890fda1f321d4606cb56bda8b4867a542347505ea1b6e",
    ("module/device/device.py", "Device.stuck_record_check"): "66d4758ea51de11d98a9c1383ba418d3fdf1a7cb1596834326bdd3c0ddbb1e25",
    ("module/device/device.py", "Device.click_record_clear"): "c212a5fb940374d9a5495762c983f41d2ffd540750d59e28bec7a8794bba52b2",
    ("module/device/device.py", "Device.click_record_check"): "55782ea1a02fb31c13953e173a49c1841783ce634baeeadd51659298b62d6599",
}

LOGIN_CALLBACK_TIMEOUT_S = 720


class _LoginBuilder:
    def __init__(self, sources, resource_dir, prefix):
        self.sources = sources
        self.assets = NavigationCompiler({}, resource_dir)
        self.checked = set()
        self.prefix = prefix
        self.obligations = []
        self.track_taps = False
        self.raw = {
            "format": 1,
            "name": prefix,
            "resources": [],
            "resource_namespaces": True,
            "params": {"enable_mail": {"default": True}, "enable_courtyard_affairs": {"default": True},
                       "friend_invitation": {"default": "accept",
                                             "choices": ["accept", "reject", "only_jade", "jade_and_food", "ignore"]}},
            "vars": {self.var(name): value for name, value in {
                "phase": "harvest", "idle_since": -1, "since": 0, "courtyard_done": False,
                "courtyard_claims": 0, "mail_intent": "", "returned": False,
            }.items()},
            "states": [],
            "loop_delay_ms": 0,
            "limits": {"timeout_s": 120, "no_progress_timeout_s": 120, "stuck_timeout_s": 120,
                       "unknown_timeout_s": 15, "max_repeat": 10000},
            "default_result": "unknown",
        }

    def var(self, name):
        return self.prefix + "_" + name

    def set(self, **updates):
        return {"set": {self.var(name): value for name, value in updates.items()}}

    def goto(self, phase, **updates):
        return self.set(phase=repr(phase), **updates)

    def state(self, name, phase, lines, actions, *checks, guard=None):
        conditions = [{"expr": f"{self.var('phase')} == {phase!r}"}, {"screen_size": [1280, 720]}]
        if guard:
            conditions.append({"expr": guard})
        conditions.extend(checks)
        self.raw["states"].append({"id": self.var(name), "when": {"all": conditions},
                                   "do": actions, "source": _ref(LOGIN, lines=lines)})

    def asset(self, name, task):
        alias, spec = self.assets.asset({"task": task, "name": name})
        if alias in self.checked:
            return alias
        folder = task.replace("Component_", "Component/", 1)
        kind, fields, _ = self.sources.asset(f"tasks/{folder}/assets.py", folder.split("/")[-1] + "Assets", name)
        x, y, width, height = fields["roi_front"]
        if kind == "RuleClick":
            expected = {"type": "click", "rect": [x, y, x + width, y + height]}
        elif kind == "RuleImage":
            expected = {"type": "image", "front": list(fields["roi_front"]), "roi": list(fields["roi_back"]),
                        "threshold": fields["threshold"], "method": fields["method"], "roi_expand": 2}
            original = self.sources.root / fields["file"]
            converted = self.assets.resource_dir / spec["file"]
            if not original.is_file() or not converted.is_file() or original.read_bytes() != converted.read_bytes():
                raise ValueError("source image does not match converted resource " + alias)
        else:
            raise ValueError("unsupported harvest resource " + alias)
        if any(spec.get(key) != value for key, value in expected.items()):
            raise ValueError("source declaration does not match converted resource " + alias)
        self.checked.add(alias)
        return alias

    def image(self, name, *, task="Restart", threshold=None):
        options = {}
        if isinstance(name, tuple):
            name, scales = name
            options["scale_range"] = list(scales)
        if threshold is not None:
            options["threshold"] = threshold
        return {"res": self.asset(name, task), **options}

    def click(self, state, phase, lines, target, interval, *, task="Restart", button=None,
              context=(), threshold=None, afterwards=(), guard=None, clock_reset=False, rect=None):
        name = target[0] if isinstance(target, tuple) else target
        interval_key = self.var("interval_" + task + "_" + name.lower())
        end = []
        if interval:
            self.raw["vars"].setdefault(interval_key, -1_000_000)
            ready = f"elapsed_ms - {interval_key} > {interval}"
            guard = f"({guard}) and ({ready})" if guard else ready
            end.append({"set": {interval_key: "elapsed_ms"}})
        if clock_reset:
            end.append(self.set(idle_since="elapsed_ms"))
        if rect is not None:
            click = {"click": rect}
        elif button:
            click = {"click": self.asset(button, task)}
        else:
            click = {"click_found": True, "use_match_size": True}
        if self.track_taps:
            control = button if name in ("I_LOGIN_SCROOLL_CLOSE", "I_LOGIN_SPECIFIC_SERVE") and button else name
            click["tap_id"] = f"{task}::{control}"
            end.append(self.reset_stall_window(long_wait=False))
        self.state(state, phase, lines, [{**click, "recheck": True, "delay": 0}, *end, *afterwards],
                   *context, self.image(target, task=task, threshold=threshold), guard=guard)

    def block(self, name, phase, lines, requirement, *checks):
        self.obligations.append({"id": self.var(name), "source": _ref(LOGIN, lines=lines),
                                 "requirement": requirement, "blocking": True})
        self.state(name, phase, lines, [{"fail": requirement}], *checks)

    def reward(self, phase, lines, *, clock_reset=False):
        self.click(phase + "_reward", phase, lines, "I_UI_REWARD", 400, task="GlobalGame",
                   threshold=.6, button="C_UI_REWARD", clock_reset=clock_reset)
        self.click(phase + "_award", phase, lines, "I_UI_AWARD", 200, task="GlobalGame", clock_reset=clock_reset)

    def burst(self, phase, lines):
        task = "GlobalGame"
        accept = self.image("I_G_ACCEPT", task=task)
        jade = self.image("I_G_JADE", task=task)
        valued = {"any": [jade, self.image("I_G_CAT_FOOD", task=task), self.image("I_G_DOG_FOOD", task=task)]}
        ignore = {"any": [
            {"expr": "friend_invitation == 'ignore'"},
            {"all": [{"expr": "friend_invitation == 'only_jade'"}, {"not": jade}]},
            {"all": [{"expr": "friend_invitation == 'jade_and_food'"}, {"not": valued}]},
        ]}
        for choice, marker, policy in (
            ("reject", "I_G_REJECT", {"expr": "friend_invitation == 'reject'"}),
            ("ignore", "I_G_IGNORE", ignore),
        ):
            handling = phase + "_invite_" + choice
            button = self.image(marker, task=task)
            enter, leave = [self.goto(handling)], [self.goto(phase)]
            if self.track_taps:
                enter.append(self.set(stall_saved_long=self.var("stall_long")))
                leave.append(self.set(stall_long=self.var("stall_saved_long")))
            self.state(handling + "_enter", phase, lines, enter, accept, policy, button)
            self.state(handling + "_gone", handling, lines, leave, {"not": button})
            self.click(handling + "_input", handling, lines, marker, 800, task=task, context=[accept])
            self.await_frame(handling, lines)

        approved_policy = {"any": [
            {"expr": "friend_invitation == 'accept'"},
            {"all": [{"expr": "friend_invitation == 'only_jade'"}, jade]},
            {"all": [{"expr": "friend_invitation == 'jade_and_food'"}, valued]},
        ]}
        invitation_panel = {"any": [self.image("I_G_REJECT", task=task), self.image("I_G_IGNORE", task=task)]}
        timing = {name: f"wanted_invite_{name.removeprefix('oas_')}" for name in SERVER_TIMING}
        self.raw["params"].update({alias: dict(SERVER_TIMING[name]) for name, alias in timing.items()})
        clock = self.var("invite_started")
        self.raw["vars"].setdefault(clock, -1)
        accepting = phase + "_invite_accept"
        verifying = accepting + "_verify"
        enter = [self.goto(accepting, invite_started="elapsed_ms")]
        leave = [self.goto(phase)]
        if self.track_taps:
            enter.append(self.set(stall_saved_long=self.var("stall_long")))
            leave.append(self.set(stall_long=self.var("stall_saved_long")))
        self.state(accepting + "_enter", phase, lines, enter, invitation_panel, accept, approved_policy)
        self.state(accepting + "_expired", accepting, lines, leave, {"not": accept})
        self.state(accepting + "_acknowledged", verifying, lines, [
            {"oas_wake": {"task": "WantedQuests", "server_params": timing}},
            *leave,
        ], {"not": accept})
        # Completion is distinct from input eligibility: only a dispatched tap
        # enters verify. Persistent panels hit the original absolute deadline
        # before either initial input or retry, including tap-loop recovery.
        for pending in (accepting, verifying):
            self.state(pending + "_timeout", pending, lines, [{"fail": "协作邀请在时限内未确认处理完成"}],
                       guard=f"elapsed_ms - {clock} >= 8000")
        within_deadline = f"elapsed_ms - {clock} < 8000"
        for state, pending, afterwards in (
            (accepting + "_input", accepting, [self.goto(verifying)]),
            (accepting + "_retry", verifying, []),
        ):
            # Both states share the per-button 800 ms cooldown and recheck all
            # evidence and the deadline on the fresh pre-input frame. Retrying
            # never resets invite_started or relaxes the companion-button guard.
            self.click(state, pending, lines, "I_G_ACCEPT", 800, task=task,
                       context=[invitation_panel, approved_policy],
                       afterwards=afterwards, guard=within_deadline)
        for pending in (accepting, verifying):
            self.await_frame(pending, lines)

        self.block(phase + "_invitation_review", phase, lines,
                   "匹配到可能的协作邀请，但缺少与配置一致的弹窗按钮证据", accept)

    def login(self):
        self.track_taps = True
        started = self.var("login_started")
        phase_var = self.var("phase")
        self.raw["vars"].update({phase_var: "login_entry", started: 0, self.var("court_samples"): 0,
                                 self.var("court_started"): 0, self.var("court_last_sample"): -1_000_000,
                                 self.var("restart_count"): 0, self.var("restart_pending"): 0,
                                 self.var("login_attempt"): 0,
                                 self.var("stall_ms"): 0, self.var("stall_captures"): 0,
                                 self.var("stall_long"): False, self.var("stall_saved_long"): False})
        self.raw["params"].update({"login_character": {"default": ""}, "enable_harvest": {"default": True},
                                   "allow_login_restart": {"default": True}})
        # The source's two long login windows must have room to elapse before
        # the total callback timeout or generic workflow watchdogs fire.
        self.raw["limits"].update(timeout_s=LOGIN_CALLBACK_TIMEOUT_S + 15,
                                  stuck_timeout_s=LOGIN_CALLBACK_TIMEOUT_S + 15,
                                  no_progress_timeout_s=LOGIN_CALLBACK_TIMEOUT_S + 15)
        self.raw["states"].append({
            "id": self.var("login_deadline"),
            "when": {"expr": f"{phase_var} != 'login_entry' and {phase_var} != 'returned' and "
                             f"elapsed_ms - {started} > {LOGIN_CALLBACK_TIMEOUT_S * 1000}"},
            "do": [{"fail": "Login and harvest reached the Android callback time limit"}],
            "source": _ref(LOGIN, lines=(181, 201)),
        })
        self.state("start_login", "login_entry", (32, 36), [
            self.goto("login", court_started="elapsed_ms", login_started="elapsed_ms", login_attempt=1),
            self.reset_stall_window(long_wait=True),
        ])
        self.state("retry_exhausted", "after_restart", (198, 201), [
            {"fail": "两轮登录均触发重启，需要人工接管"},
        ], guard=f"{self.var('restart_count')} >= 2")
        self.state("retry_login", "after_restart", (181, 186), [
            self.goto("login", court_started="elapsed_ms", court_last_sample=-1_000_000,
                      court_samples=0, login_attempt=f"{self.var('login_attempt')} + 1"),
            self.reset_stall_window(long_wait=True),
        ])
        buff = self.image("I_BUFF_1", task="Component_GeneralBuff")
        record = self.image("I_MAIN_GOTO_SHIKIGAMI_RECORDS", task="GameUi")
        self.stall_recovery(buff, record)
        phase = "login"
        cancel = "I_UI_CANCEL_SAMLL"
        self.burst(phase, (76, 78))
        self.click("cancel_battle", phase, (80, 83), cancel, 800, task="GlobalGame")
        last = self.var("court_last_sample")
        samples = self.var("court_samples")
        ready = f"elapsed_ms - {last} > 200"
        elapsed = f"elapsed_ms - {self.var('court_started')} > 1500"
        self.state("confirm_courtyard", phase, (85, 92), [self.goto("after_login")],
                   buff, record, guard=f"{ready} and {samples} >= 2 and {elapsed}")
        self.state("sample_courtyard", phase, (85, 92),
                   [self.set(court_last_sample="elapsed_ms"), {"inc": samples}], buff, record, guard=ready)
        # Preserve the source position, with fresh positive evidence that the
        # scroll is collapsed before tapping its fixed region.
        self.click("expand_scroll", phase, (93, 98), "I_LOGIN_SCROOLL_CLOSE", 2000,
                   button="C_LOGIN_SCROLL_CLOSE_AREA", context=[buff, {"not": record}], guard=ready,
                   afterwards=[self.set(court_last_sample="elapsed_ms")])
        self.state("reset_courtyard", phase, (93, 99), [
            self.set(court_started="elapsed_ms", court_last_sample="elapsed_ms", court_samples=0)],
            buff, {"not": record}, guard=ready)

        self.click("download_illustrations", phase, (110, 112), "I_LOGIN_LOAD_DOWN", 1000)
        # The source switches the earlier cancel timer to a new interval.
        self.click("cancel_video", phase, (114, 116), cancel, 0, task="GlobalGame")
        self.click("login_red_close", phase, (118, 120), RED_CLOSE, 600)
        self.click("login_yellow_close", phase, (122, 124), "I_LOGIN_YELLOW_CLOSE", 600)
        # This source branch opens a prompt only to cancel it; it does not
        # enter a phone number or submit a binding. Enter only after dispatch.
        self.click("open_bind_phone_prompt", phase, (125, 127), "I_LOGIN_LOGIN_GOTO_BIND_PHONE", 0,
                   afterwards=[self.goto("bind_phone")])
        self.click("reject_foster_invite", phase, (133, 137), "I_I_REJECT", 800, task="Component_GeneralInvite")
        self.click("dismiss_genie", phase, (138, 141), "I_LOGIN_LOGIN_ONMYOJI_GENIE", 0)

        chooser = self.image("I_LOGIN_SPECIFIC_SERVE")
        self.block("missing_login_character", phase, (143, 152), "Bind an explicit character for the role selector",
                   chooser, {"expr": "login_character == ''"})
        self.login_ocr("select_character", "O_LOGIN_SPECIFIC_SERVE", 600, chooser,
                       (143, 152), "same_server", full=True)
        create_account = self.image("I_CREATE_ACCOUNT")
        self.state("restart_create_account", phase, (154, 157), self.restart_actions(),
                   create_account, guard=self.restart_guard())
        self.raw["states"][-1].update(sensitive=RESTART_CONFIRMATION, desc="登录误入角色创建页，重启当前阴阳师应用")
        self.state("restart_disabled", phase, (154, 157), [
            {"fail": "登录误入角色创建页，当前设置需要人工接管"},
        ], create_account)
        self.click("exit_server_settings", phase, (159, 164), "I_CHARACTARS", 1000, rect=[106, 535, 106, 535])
        login_form = self.image("I_LOGIN_8")
        early_server = self.image("I_EARLY_SERVER")
        self.click("stay_on_early_server", phase, (170, 174), "I_EARLY_SERVER_CANCEL", 0,
                   context=[login_form, early_server])
        self.state("wait_for_early_server_cancel", phase, (170, 174), [], login_form, early_server)
        for name in ("O_LOGIN_ENTER_GAME_ORIGIN", "O_LOGIN_ENTER_GAME"):
            self.login_ocr(name.lower(), name, 3000, login_form, (175, 177), "wait_for_role")
        self.await_frame(phase, (57, 179))

        # Source self.screenshot() at login.py:128 inherits _burst. Its
        # continuation belongs to this inner prompt, not the outer login loop.
        self.burst("bind_phone", (127, 129))
        self.block("bind_phone", "bind_phone", (125, 132),
                   "Phone prompt permits only the source cancel control; unrelated confirmation requires review",
                   {"any": [self.image("I_UI_CONFIRM", task="GlobalGame"),
                            self.image("I_UI_CONFIRM_SAMLL", task="GlobalGame")]})
        # Both source clicks omit interval. Reuse the existing cancel control
        # without allocating/resetting its shared per-target cooldown.
        self.click("cancel_bind_phone_prompt", "bind_phone", (128, 132), cancel, 0, task="GlobalGame",
                   afterwards=[self.goto(phase)])
        self.await_frame("bind_phone", (127, 132))

        self.state("role_page_timeout", "wait_for_role", (175, 177), [self.goto(phase)], guard=self.expired(5000))
        self.state("role_page_reached", "wait_for_role", (175, 177), [self.goto(phase)], chooser)
        self.await_frame("wait_for_role", (175, 177))
        # Source self.screenshot() here calls BaseTask.screenshot -> _burst.
        # Resume this inner chooser loop, not the outer login phase.
        self.burst("same_server", (145, 149))
        self.state("same_server_cleared", "same_server", (146, 152), [self.goto(phase)], {"not": chooser})
        self.click("confirm_same_server", "same_server", (146, 149), "I_LOGIN_SPECIFIC_SERVE", 2000,
                   button="C_LOGIN_ENSURE_LOGIN_CHARACTER_IN_SAME_SVR")
        self.await_frame("same_server", (145, 152))
        self.state("start_harvest", "after_login", (186, 192), [self.goto("harvest")], guard="enable_harvest")
        self.state("skip_harvest", "after_login", (186, 192), [self.goto("returned", returned=True)])

    def restart_guard(self):
        # OAS app_handle_login performs exactly two attempts. A restart may
        # follow only the first failed attempt. The second failure hands off.
        return f"allow_login_restart and {self.var('login_attempt')} <= 2 and {self.var('restart_count')} < 2"

    def reset_stall_window(self, *, long_wait):
        return self.set(stall_ms="elapsed_ms", stall_captures="screen_captures", stall_long=long_wait)

    def stall_recovery(self, buff, record):
        elapsed = f"elapsed_ms - {self.var('stall_ms')}"
        captures = f"screen_captures - {self.var('stall_captures')}"
        phase = self.var("phase")
        active = " and ".join(f"{phase} != {name!r}" for name in ("login_entry", "after_restart", "after_login", "returned"))
        overdue = {"expr": f"{active} and {elapsed} > 60000 and {captures} > 60 and "
                           f"(not {self.var('stall_long')} or ({elapsed} > 300000 and {captures} > 300))"}
        # A newly reached courtyard takes priority over restarting an otherwise
        # overdue login. The app check also rejects blank frames and stale focus.
        newly_arrived = {"all": [{"expr": f"{phase} == 'login' or {phase} == 'wait_for_role'"}, buff, record]}
        check = [overdue, {"not": newly_arrived}]
        source = _ref(LOGIN, lines=(181, 201))
        self.raw["states"].extend([
            {"id": self.var("restart_stalled_login"), "source": source,
             "when": {"all": [*check, {"expr": self.restart_guard()}, {"screen_size": [1280, 720]},
                              {"foreground_game": ONMYOJI_PACKAGE}]},
             "sensitive": RESTART_CONFIRMATION, "desc": "登录等待超时，重启当前前台阴阳师应用",
             "do": self.restart_actions()},
            {"id": self.var("stalled_login_handoff"), "source": source, "when": {"all": check},
             "do": [{"fail": "登录等待超时，需要核对客户端前台状态或重启设置"}]},
        ])

    def restart_actions(self):
        return [
            {"restart_app": ONMYOJI_PACKAGE, "recheck": True, "attempt_var": self.var("restart_pending")},
            {"inc": self.var("restart_count")},
            self.goto("after_restart", restart_pending=0),
        ]

    def add_tap_loop_recovery(self):
        # Insert before the matching tap, preserving the original state order
        # and requiring the same fresh frame to authorize either operation.
        states = []
        for state in self.raw["states"]:
            tap_id = next((action["tap_id"] for action in state["do"] if "tap_id" in action), None)
            if tap_id:
                loop = {"all": [{"tap_loop": tap_id}, state["when"]]}
                states.append({**state, "id": state["id"] + "_recover_loop",
                               "when": {"all": [{"expr": self.restart_guard()}, loop]},
                               "sensitive": RESTART_CONFIRMATION, "desc": "重复点击达到阈值，重启当前阴阳师应用",
                               "do": self.restart_actions()})
                states.append({**state, "id": state["id"] + "_block_loop", "when": loop,
                               "do": [{"fail": "重复点击达到阈值，需要人工接管"}]})
            states.append(state)
        self.raw["states"] = states

    def login_ocr(self, state, name, interval, context, lines, destination, *, full=False):
        _, fields, _ = self.sources.asset("tasks/Restart/assets.py", "RestartAssets", name)
        region = list(fields["roi"])
        stamp = self.var("interval_" + name.lower())
        self.raw["vars"][stamp] = -1_000_000
        ready = f"elapsed_ms - {stamp} > {interval}"
        if full:
            guard = f"login_character != '' and {ready}"
            condition = {"ocr_full": {"region": region, "keyword_var": "login_character",
                                      "evidence": "complete_keyword"}}
        else:
            guard = ready
            condition = {"ocr_single": {"region": region, "equals": fields["keyword"]}}
        self.state(state, "login", lines, [
            {"click_found": True, "use_match_size": True, "delay": 0, "recheck": True,
             "tap_id": "Restart::" + name},
            self.reset_stall_window(long_wait=False),
            {"set": {stamp: "elapsed_ms"}},
            self.goto(destination, since="elapsed_ms"),
        ], context, condition, guard=guard)

    def harvest(self):
        phase = "harvest"
        self.burst(phase, (213, 217))
        self.reward(phase, (219, 226), clock_reset=True)
        for name, target, interval, line in (
            ("chat", "I_HARVEST_CHAT_CLOSE", 1000, 228),
            ("yellow_close", "I_LOGIN_YELLOW_CLOSE", 600, 233),
            ("pet_house", "I_HARVEST_BACK_PET_HOUSE", 600, 238),
        ):
            self.click(name, phase, (line, line + 2), target, interval, clock_reset=True)
        self.block("soul_overflow", phase, (242, 247), "Soul overflow requires an identified dialog and an explicit disposition",
                   self.image("I_UI_CONFIRM_SAMLL", task="GlobalGame"))
        self.block("zidu_overlay", phase, (248, 255), "The shifted Zidu click needs fresh evidence for its destination",
                   self.image("I_HARVEST_ZIDU"))
        self.state("visit_courtyard", phase, (257, 262),
                   [self.goto("courtyard_enter", since="elapsed_ms", courtyard_claims=0)],
                   guard=f"enable_courtyard_affairs and not {self.var('courtyard_done')}")
        self.click("jade", phase, (263, 266), "I_HARVEST_JADE", 1500, clock_reset=True)
        self.click("sign", phase, (267, 271), "I_HARVEST_SIGN", 1500,
                   afterwards=[self.goto("wait_sign", since="elapsed_ms")])
        self.click("special_sign_3", phase, (272, 275), "I_HARVEST_SIGN_3", 700, clock_reset=True)
        self.click("special_sign_4", phase, (276, 278), "I_HARVEST_SIGN_4", 1000, clock_reset=True)
        self.click("sign_popup", phase, (279, 282), "I_HARVEST_SIGN_2", 1500,
                   afterwards=[self.goto("wait_sign_close", since="elapsed_ms")])
        self.click("sign_999", phase, (283, 286), "I_HARVEST_SIGN_999", 1500, clock_reset=True)
        self.state("visit_mail", phase, (287, 290), [self.goto("mail_enter", mail_intent="''")],
                   {"any": [self.image(MAIL_ICON), self.image(MAIL_COPY), self.image(READ_MAIL)]},
                   guard="enable_mail")
        for name, target, interval, line, threshold in (
            ("ap", "I_HARVEST_AP", 1000, 291, .7),
            ("soul_bonus", "I_HARVEST_SOUL", 1000, 295, None),
            ("guild_reward", "I_HARVEST_GUILD_REWARD", 2000, 299, None),
        ):
            self.click(name, phase, (line, line + 2), target, interval, threshold=threshold, clock_reset=True)
        self.state("select_soul", phase, (302, 308), [self.goto("soul_first")], self.image("I_HARVEST_SOUL_1"))
        self.harvest_red_close(phase)
        idle = self.var("idle_since")
        self.state("idle_start", phase, (316, 318), [self.set(idle_since="elapsed_ms")], guard=f"{idle} < 0")
        self.state("idle_complete", phase, (319, 322), [
            {"log": "No more reward"},
            self.goto("returned", returned=True),
        ], guard=f"elapsed_ms - {idle} > 5000")
        self.await_frame(phase, (312, 322))
        for name, target, lines in (
            ("wait_sign", "I_HARVEST_SIGN_2", (268, 271)),
            ("wait_sign_close", RED_CLOSE, (279, 282)),
        ):
            reset = [self.goto(phase, idle_since="elapsed_ms")]
            self.state(name + "_timeout", name, lines, reset, guard=self.expired(2000))
            self.state(name + "_seen", name, lines, reset, self.image(target))
            self.await_frame(name, lines)
        self.soul_sequence()

    def harvest_red_close(self, phase, *, resume_harvest=False):
        lines = (310, 314)
        advance = [self.goto("harvest")] if resume_harvest else []
        self.click(phase + "_red_close", phase, lines, RED_CLOSE, 2000, clock_reset=True, afterwards=advance)
        self.state(phase + "_red_cooling", phase, lines, [self.set(idle_since="elapsed_ms"), *advance],
                   self.image(RED_CLOSE))

    def soul_sequence(self):
        for phase, wanted, button, to, interval, line in (
            ("soul_first", "I_HARVEST_SOUL_2", "I_HARVEST_SOUL_1", "soul_second", 1000, 305),
            ("soul_second", "I_HARVEST_SOUL_3", "I_HARVEST_SOUL_2", "soul_dismiss", 3000, 306),
        ):
            self.state(phase + "_seen", phase, (line, line), [self.goto(to)], self.image(wanted))
            self.click(phase + "_input", phase, (line, line), button, interval)
            self.await_frame(phase, (line, line))
        self.state("soul_dismissed", "soul_dismiss", (307, 308),
                   [self.goto("soul_after", idle_since="elapsed_ms")], {"not": self.image("I_HARVEST_SOUL_3")})
        self.click("soul_dismiss_input", "soul_dismiss", (307, 307), "I_HARVEST_SOUL_3", 1000)
        self.await_frame("soul_dismiss", (307, 307))
        self.harvest_red_close("soul_after", resume_harvest=True)
        self.state("soul_resume", "soul_after", (310, 322), [self.goto("harvest")])

    def expired(self, duration):
        return f"elapsed_ms - {self.var('since')} > {duration}"

    def await_frame(self, phase, lines):
        self.state(phase + "_wait", phase, lines, [{"wait": 100}])

    def mail(self):
        self.state("mail_opened", "mail_enter", (334, 337), [self.goto("mail_claim", since="elapsed_ms")],
                   self.image(READ_MAIL))
        self.click("open_mail_icon", "mail_enter", (338, 339), MAIL_ICON, 1500)
        self.click("open_mail_copy", "mail_enter", (340, 341), MAIL_COPY, 1500)
        self.await_frame("mail_enter", (334, 341))

        self.state("mail_timeout", "mail_claim", (342, 347), [self.goto("mail_close")], guard=self.expired(6000))
        confirmed = self.image("I_UI_CONFIRM", task="GlobalGame")
        claim_title = {"text": "", "pattern": "^全部领取$", "region": [485, 30, 300, 95]}
        confirm_button = {"text": "", "pattern": "^确[认定]$", "region": [680, 515, 155, 110]}
        self.click("mail_confirm", "mail_claim", (348, 349), "I_UI_CONFIRM", 800, task="GlobalGame",
                   context=[confirmed, claim_title, confirm_button], guard=f"{self.var('mail_intent')} == 'claim_all'",
                   afterwards=[self.goto("mail_close")])
        self.block("mail_confirmation_context", "mail_claim", (348, 349),
                   "邮箱确认弹窗用途未核实，需要人工确认", confirmed)
        self.click("mail_mark", "mail_claim", (351, 352), READ_MAIL, 1500,
                   afterwards=[self.set(mail_intent="'mark_read'")])
        self.click("mail_claim_all", "mail_claim", (353, 354), "I_HARVEST_MAIL_ALL", 1500,
                   afterwards=[self.set(mail_intent="'claim_all'")])
        self.click("mail_red_point", "mail_claim", (355, 356), "I_MAIL_RED_POINT", 4000,
                   afterwards=[self.set(mail_intent="''")])
        self.await_frame("mail_claim", (344, 356))
        self.state("mail_closed", "mail_close", (357, 358), [self.goto("harvest", idle_since="elapsed_ms")],
                   {"not": self.image(RED_CLOSE)})
        self.click("mail_close_input", "mail_close", (357, 357), RED_CLOSE, 1000)
        self.await_frame("mail_close", (357, 357))

    def courtyard(self):
        finish = [self.goto("harvest", courtyard_done=True, idle_since="elapsed_ms")]
        self.state("courtyard_opened", "courtyard_enter", (360, 363), [self.goto("courtyard_claim")],
                   self.image(COURTYARD_PAGE))
        self.state("courtyard_open_timeout", "courtyard_enter", (361, 363),
                   [{"log": "courtyard affairs timeout!"}, *finish], guard=self.expired(3000))
        self.click("courtyard_open", "courtyard_enter", (360, 363), ("I_NOTE", (.8, 1.2)), 1000)
        self.await_frame("courtyard_enter", (360, 363))

        phase = "courtyard_claim"
        self.state("courtyard_intro", phase, (365, 400),
                   [{"click": [580, 464, 700, 486], "recheck": True, "delay": 600}],
                   self.image(COURTYARD_PAGE), COURTYARD_INTRO)
        self.state("courtyard_no_tasks", phase, (367, 369), [{"log": "courtyard affairs completed"}, *finish],
                   self.image("I_NO_TASKS"))
        self.click("courtyard_soul_two", phase, (370, 373), "I_HARVEST_SOUL_2", 1000)
        self.click("courtyard_soul_three", phase, (370, 373), "I_HARVEST_SOUL_3", 1000)
        self.reward(phase, (374, 379))
        self.block("courtyard_experience_context", phase, (380, 382),
                   "Verify the courtyard overflow-experience dialog before affirmative input", self.image("I_CONFIRM"))
        self.block("courtyard_soul_donation", phase, (397, 399),
                   "庭院事务包含提交御魂的项目，须单独核对投入物品，已停止一键完成",
                   self.image(COURTYARD_PAGE), self.image("I_COMPLETE_TASKS"), COURTYARD_SOUL_DONATION)
        for name, target, interval, line in (
            ("daily", "I_DAILY", 1000, 384), ("claimed", "I_SUCCESS_CLAIMED", 1000, 387),
            ("skip", "I_SKIP", 0, 389), ("close", RED_CLOSE, 1000, 391),
        ):
            self.click("courtyard_" + name, phase, (line, line + 1), target, interval)
        count = self.var("courtyard_claims")
        self.state("courtyard_claim_cap", phase, (393, 396), finish, guard=f"{count} >= 3")
        self.click("courtyard_complete_tasks", phase, (397, 399), "I_COMPLETE_TASKS", 2300,
                   context=[self.image(COURTYARD_PAGE), {"not": COURTYARD_INTRO}, {"not": COURTYARD_SOUL_DONATION}],
                   afterwards=[{"inc": count}])
        bulk = self.raw["states"][-1]
        bulk["do"].insert(0, {"confirm": "分解", "detail": "请核对庭院事务全部项目，未显示的项目也可能提交材料"})
        bulk.update(
            sensitive="购买", desc="庭院事务一键完成可能消耗金币、体力及提交材料，请核对全部项目",
        )
        self.await_frame(phase, (365, 400))


def _compile_fragment(source_root, resource_dir, prefix, *, android_login):
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", prefix):
        raise ValueError("prefix must be a native identifier")
    sources = _Sources(Path(source_root))
    pins = {**HARVEST_PINS, **(LOGIN_PINS if android_login else {})}
    for (path, symbol), fingerprint in pins.items():
        if source_node_hash(sources.node(path, symbol), style="compact-314") != fingerprint:
            raise ValueError(f"Review changed login/harvest source: {path}::{symbol}")
    builder = _LoginBuilder(sources, resource_dir, prefix)
    if android_login:
        builder.login()
    builder.harvest()
    builder.mail()
    builder.courtyard()
    if android_login:
        builder.add_tap_loop_recovery()
    builder.state("returned", "returned", (181, 192) if android_login else (316, 322), [
        {"stop": {"reason": "Login callback returned" if android_login else "Harvest callback returned",
                  "result": "unknown", "verified": False,
                  "evidence": {"scope": "login_fragment" if android_login else "harvest_fragment",
                               "original_task_complete": False}}},
    ])
    raw = builder.raw
    raw["resources"] = sorted(set(builder.assets.refs))
    raw["harvest_contract"] = {
        "complete": False,
        "original_task_complete": False,
        "source_files": sorted(sources.files.values(), key=lambda item: item["path"]),
        "source_obligations": builder.obligations,
        "result_var": builder.var("returned"),
        "caller_requirements": ["Invoke after verified login and bind the effective costume/asset set",
                                "Bind Restart.harvest_config.enable before entering this fragment"],
        "adaptations": ["Exact resolution required for every input, including during nested source loops",
                        "Fresh positive evidence before input and bounded native run",
                        "Per-target cooldown with current call's interval; source recreates timers on interval switches",
                        "Invitation reject/ignore requires both the invitation and selected button; acceptance needs a bound WantedQuests schedule",
                        "Mail bulk collection confirmation requires the preceding claim action, exact modal title and confirm-button evidence"],
    }
    if android_login:
        contract = raw["harvest_contract"]
        contract["caller_requirements"] = ["Explicit Android transport, effective costume/asset set and Restart config"]
        contract["platform_exclusions"] = [
            {"source": _ref(LOGIN, lines=(39, 65)), "branch": "Desktop MPay popup",
             "reason": "The pinned popup helper returns immediately when device.is_desktop is false."},
        ]
        contract["adaptations"].extend([
            "Every Android screenshot refreshes the controller's raw dimensions. The login states "
            "wait for a native 1280x720 screenshot before evaluating their controls.",
            "Courtyard confirmation requires three eligible frames and more than 1.5 seconds on the monotonic clock",
            "Role selection requires a complete literal OCR keyword and uses its current matched box",
            "Phone prompt cancellation follows LoginHandler._app_handle_login:125-132: dispatch the source opener, "
            "resume inherited screenshot/_burst in the prompt phase, then dispatch only I_UI_CANCEL_SAMLL and return to login; "
            "no phone entry or binding submission; unrelated confirmations retain the bind_phone review obligation",
            "Fixed scroll click requires the collapsed scroll marker",
            "Role creation enters the bounded two-attempt recovery with an explicit approval for each game restart",
            "The 15-control repeated-tap rule is enforced before the triggering tap, including across login and harvest",
            "No-input recovery uses the 60 s/60 capture and LOGIN_CHECK 300 s/300 capture windows; "
            "successful game controls reset both counters and a fresh foreground check is required before restarting",
        ])
    return raw


def compile_login_harvest(source_root, resource_dir, *, prefix="oas_harvest"):
    """Build an offline fragment for the harvest portion of LoginHandler."""
    return _compile_fragment(source_root, resource_dir, prefix, android_login=False)


def compile_android_login(source_root, resource_dir, *, prefix="oas_login"):
    """Build the source-pinned Android login and default harvest callback."""
    return _compile_fragment(source_root, resource_dir, prefix, android_login=True)
