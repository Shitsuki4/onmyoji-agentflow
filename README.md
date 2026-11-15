# onmyoji-agentflow

阴阳师（MuMu 12 模拟器）的 YAML 工作流引擎。把 [assttyys_autojs](https://github.com/zzliux/assttyys_autojs) 和
[OnmyojiAutoScript](https://github.com/nearaura/OnmyojiAutoScript)（OAS）的识别数据自动转成本项目的格式，
用状态机跑工作流，出错时由大模型看截图诊断、提出修复，修复要先通过验证才启用。

> **风险说明（请先读）**
>
> - 网易《阴阳师》的游戏服务协议禁止使用外挂和第三方自动化工具，处罚包括封停账号。用本工具就有被封号的风险。
> - 点击位置、滑动轨迹和延时的随机化**只是照搬 OAS 和 assttyys 两个项目的做法**，不能保证不被检测。
> - 花勾玉、抽卡、购买、出售、分解这些操作每次都要你确认，没人回答就当作拒绝；但工具仍可能误识别、误点。
> - 本项目和网易、assttyys、OAS 的作者都没有关系。按 GPL-3.0 "原样"提供，不带任何担保，后果自负。

当前版本 0.1.1 **还没有在真实的 Windows + MuMu 12 + 阴阳师上跑过**，测试用的都是程序合成的截图，见文末「已知限制」。

## 功能

- **工作流**：YAML 状态机。条件只有多点比色、区域找色、模板匹配、OCR 和计数表达式，不能写代码。
  内置御魂（`orochi`）、个人结界突破（`realm_raid`）、探索（`exploration`）三个，坐标和颜色由脚本从 assttyys 生成。
- **失败识别**：总超时、认不出画面、画面卡住、同一状态反复出现、长时间没进展、设备出错、你拒绝确认。
- **自动监管**：本地重试 → 大模型看截图诊断 → 改动放在 git 分支上 → 格式检查、回放测试、观察模式、限次试跑 →
  只改参数的自动合并，改识别或流程的等你批准 → 合并后失败率上升自动回滚。
- **上游自动同步**（`oaf sync`）：自动拉取 assttyys 和 OAS 的最新代码，转换、验证、合并或等你批准，可以回滚，见下文。
- **MuMu 12**：自动找安装目录和多开实例，优先用 `external_renderer_ipc.dll` 专用通道截图和点按，用不了就退回 adb。
- **命令行 `oaf`** 和 **本机网页面板**（只监听 127.0.0.1，改动类请求都要带令牌）。
- **给 agent 用的 MCP 服务**（`oaf mcp`）：Codex、Claude Code 等客户端可以直接列实例、截图、跑工作流、同步上游、
  改配置。敏感操作和改识别 / 流程的修复照样要你本人批准，agent 绕不过去，见「在 Codex / Claude Code 里用（MCP）」。

## 安装

需要 Windows 10/11、Python 3.10 或更新、[git](https://git-scm.com/)（同步上游和版本管理要用）和 MuMu 模拟器 12。

```powershell
git clone https://github.com/Shitsuki4/onmyoji-agentflow
cd onmyoji-agentflow
python -m venv .venv
.venv\Scripts\activate
pip install -e .
# 可选：OCR（PaddleOCR 的 ONNX 模型）
pip install -e .[ocr]

oaf init        # 生成配置和工作区
oaf devices     # 查找 MuMu 12 和多开实例
oaf list        # 列出工作流
```

数据目录默认是 `%LOCALAPPDATA%\onmyoji-agentflow`（Linux 为 `~/.onmyoji-agentflow`），可以用 `--home` 或环境变量
`OAF_HOME` 改。里面有：

- `config.yaml`：配置（不含任何密钥）
- `workspace/`：你的工作流和识别资源，是一个 git 仓库，每次修复、同步都是一次提交
- `runs/`：运行记录和失败截图；`sync-reports/`：同步报告；`upstream-src/`：拉下来的上游代码

## MuMu 12 设置

1. MuMu 设置 → 显示：**分辨率 1280×720（平板版），DPI 240**。两个上游项目都以 1280×720 为开发分辨率，
   工作流里的坐标和颜色也是按这个分辨率来的，其他分辨率不保证能认出画面。
2. MuMu 设置 → 其他：打开 **ADB 调试**（按本机连接）。
3. 游戏里建议关掉会改变画面颜色的特效，画面风格用默认。
4. 运行 `oaf devices`，应该能看到安装目录、实例编号和 adb 地址。找不到时在 `config.yaml` 里填 `mumu_root`。
5. `oaf screenshot shot.png` 截一张图，确认是 1280×720、画面正常。

### 多开

MuMu 12 的 adb 端口一般是 16384，每多一个实例加 32（16384、16416、16448……）。在 `config.yaml` 里每个实例写一条：

```yaml
instances:
  - {name: main, mumu_id: 0, method: auto}     # auto：先试专用通道，不行用 adb
  - {name: alt,  mumu_id: 1, method: auto}
  # - {name: other, serial: "127.0.0.1:16448", method: adb}   # 也可以直接写 adb 地址
```

运行时用 `-i` 选实例：`oaf run orochi -i alt -p max_runs=10`。每个实例开一个终端分别跑。

### 点击方式

```yaml
humanize: {style: oas, base_sleep_ms: 0, random_sleep_ms: 200}
```

- `oas`（默认）：点击区域内按正态分布取点，划动走贝塞尔曲线（照搬 OAS）。
- `assttyys`：每台设备一个固定偏移点，按压 10～60 毫秒，点完按正态分布随机等待（照搬 assttyys）。

再说一遍：这只是照搬两个项目的做法，不能保证不被检测。

## 运行工作流

```powershell
oaf validate orochi                      # 格式检查 + 回放测试
oaf diagnose orochi                      # 看当前画面匹配哪些状态（不点击）
oaf run orochi --observe --seconds 60    # 观察模式：只识别不点击
oaf run orochi --trial 5                 # 限次试跑：最多点 5 下
oaf run orochi -p max_runs=30            # 正式跑
oaf status                               # 最近运行、待确认项、改动
oaf confirm <编号> yes|no                # 回答花勾玉等敏感操作的确认
oaf approve <编号>                       # 批准一个等你确认的改动（修复、同步、翻译）
oaf web                                  # 网页面板，默认 http://127.0.0.1:8765
```

第一次在你的机器上跑，建议按 `diagnose` → `--observe` → `--trial` → 正式跑的顺序来。

内置工作流的参数：`orochi` 和 `realm_raid` 是 `max_runs`（默认 30），`exploration` 是 `max_rounds`（默认 20）和
`max_swipes`（默认 4）。打九退四、结界自动刷新、探索的打经验 / 打掉落模式还没做。

## 大模型 API 配置

支持任何 OpenAI 兼容接口，按顺序尝试，前一家失败自动换下一家。看截图诊断要用 `vision: true` 的模型。

```yaml
llm:
  providers:
    - {name: deepseek, base_url: "https://api.deepseek.com/v1", model: deepseek-chat, vision: false, enabled: true}
    - {name: openai, base_url: "https://api.openai.com/v1", model: gpt-4o-mini, vision: true, enabled: true,
       price_per_mtok: 1.0}        # 可选，配了才能用 daily_cost 限额
  timeout_s: 60
  budget:                      # 用量上限，默认全部 null = 不限
    monthly_tokens: null       # 30 天内最多用多少 token
    daily_tokens: null         # 每天 token 上限
    calls_per_hour: null       # 每小时调用次数上限
    daily_cost: null           # 每天费用上限（单位同 price_per_mtok）
```

密钥只存在 Windows 凭据管理器里，不进配置文件和日志：

```powershell
oaf key set deepseek      # 输入时不显示
oaf key check deepseek
oaf key delete deepseek
```

也可以用环境变量 `OAF_KEY_<名字大写>`（比如 `OAF_KEY_DEEPSEEK`）临时提供。

**用量上限**：默认不限制调用次数和 token 用量。想设上限就填数字，比如每天最多 100 万 token：
`oaf config set llm.budget.daily_tokens 1000000`；改回不限：`oaf config set llm.budget.daily_tokens null`
（写 `null`、`0` 或留空都是不限）。设了上限的话，到了就不再调用大模型，失败直接交给你处理。
用量和当前上限在网页面板和 `oaf status` 里看。

从 0.1.0 升级：0.1.0 会把「30 天 1000 万 / 每天 40 万 / 每小时 30 次」写进 config.yaml。0.1.1 第一次读配置时，
如果这几项还是 0.1.0 的原样，就自动改成不限（翻译的 `max_per_sync: 2` 一起改成不限）；你改过其中任何一项的，原样保留。

没配大模型也能用：工作流照常跑，只是出错和上游改动导致失效时只给报告，不会自动修。

## 同步上游（assttyys / OAS）

`oaf sync` 自动拉取两个上游项目的最新代码，转换成本项目的 YAML 和识别资源。

```powershell
oaf sync                 # 拉取 + 转换 + 验证 + 合并或等你批准（上游没变就直接跳过）
oaf sync check           # 只看上游有没有新提交，不下载
oaf sync status          # 同步记录：每次的上游提交号、结果、关联的改动编号
oaf sync show [编号]     # 看某次同步的报告（转换结果、差异、验证、修复）
oaf sync rollback [编号] # 回滚最近一次（或指定的）已合并同步，回到上一版转换结果
oaf sync --force         # 上游没变也重新转换（也会重新套用回滚过的版本）
oaf sync --only oas      # 只同步一个上游
oaf sync --from D:\src   # 不联网，用本地目录里的 assttyys_autojs/ 和 OnmyojiAutoScript/
oaf sync --offline       # 不联网，用上次拉下来的缓存
oaf sync --validate-on main   # 验证时也在实例 main 上跑观察模式和限次试跑（游戏要停在对应界面）
oaf sync --loop          # 一直运行，按设定间隔定时同步
oaf convert --all        # 等同 oaf sync --force
```

网页面板里「上游同步」一栏有同样的按钮（立即同步、强制重新转换、只检查更新、回滚），还能看同步记录和报告。

### 一次同步做了什么

1. **检查更新**：先用 `git ls-remote` 问上游最新提交，和上次转换时一样就什么都不做。
2. **拉取**：浅克隆（只拉最新一个提交）。OAS 约 230 MB，第一次要几分钟。按 `urls` 顺序试，GitHub 拉不动就换镜像。
3. **转换**：
   - assttyys → `resources/upstream/assttyys/`（多点比色、找色、每个功能的转换结果、方案列表）
   - OAS → `resources/upstream/oas/`（模板图、点击、滑动、OCR 区域、页面跳转图）
   - 用 assttyys 的新数据重新生成内置工作流，再和你本地的版本做三方合并：你或自动修复改过的地方保留，
     上游改的地方跟着更新；两边改了同一处时保留你的版本，并在报告里列出。
   - 某个转换器出错时，那部分保留上一版转换结果，报告里写明出错位置。
4. **验证**：所有改动先放在候选分支 `sync/...`。每个工作流按它实际用到的资源判断有没有受影响，受影响的跑
   格式检查、敏感确认检查、回放测试，加 `--validate-on` 时再跑观察模式和限次试跑。
5. **合并规则**（和自动修复用同一套权限）：
   - 只更新了还没有工作流用到的数据 → 自动合并（`upstream.auto_merge_data`）。
   - 改了工作流用到的识别资源、或改了工作流本身 → 通过验证后等你批准：`oaf approve <改动编号>`。
   - 和你本地改动冲突 → 一定等你批准。
6. **失效处理**：上游改动让某个工作流通不过验证时，main 不动（继续用旧版），把报错、回放结果、它用到的资源前后差异
   交给大模型修复。修复走和运行失败时一样的验证和权限，改流程的修复一定等你批准，批准时连同同步一起合并。
   没配大模型或修不好时，报告里写明原因，等你处理。
7. **记录**：每次同步记下两个上游的提交号、来源地址、转换结果、文件和资源级差异、验证结果，报告在
   `sync-reports/sync-NNNN.md`（和 `.json`）。当前用的上游提交写在工作区的 `resources/upstream/upstream.yaml`。
8. **回滚**：`oaf sync rollback` 在 main 上反向提交，回到上一版转换结果。之后同样的上游提交会跳过，等上游再更新
   或加 `--force` 才会重新套用。

### 大模型翻译新方案

assttyys 里有 100 多个功能带自定义代码，没法机械转换。想把某个 assttyys 方案变成工作流，在配置里写上方案名
（方案名见工作区 `resources/upstream/assttyys/schemes.yaml`）：

```yaml
upstream:
  translate:
    schemes: ["业原火", "斗技"]
    max_per_sync: null    # 每次同步最多翻译几个，默认 null = 不限；想控制用量就填数字
```

同步时大模型会按转换结果和 auto.js 源码写出工作流（不能写代码，只能用条件、计数和变量），有花勾玉等敏感操作却没标确认的
直接拒绝。通过格式检查后一定等你 `oaf approve`，工作流名字是 `ass_` 加一串编号。新工作流没有回放样本，
第一次请先用 `--observe` 和 `--trial` 试。方案用到的功能没变时不会重新翻译。

### 配置

```yaml
upstream:
  sources:
    assttyys:
      enabled: true
      branch: master
      urls: ["https://github.com/zzliux/assttyys_autojs.git"]
    oas:
      enabled: true
      branch: master
      urls:                                  # 按顺序尝试
        - "https://github.com/nearaura/OnmyojiAutoScript.git"     # 原作者账号被封，用备份仓库
        - "https://gitcode.com/OnmyojiAutoScript/OnmyojiAutoScript.git"
        - "https://gitee.com/runheng/OnmyojiAutoScript.git"
  fetch_timeout_s: 900
  auto_merge_data: true
  schedule: {enabled: false, interval_hours: 24}   # 打开后 oaf web 运行期间会定时同步
```

想换源、加自己的镜像，改 `urls` 就行。定时同步也可以用 Windows 任务计划程序每天跑一次 `oaf sync`。

## 在 Codex / Claude Code 里用（MCP）

`oaf mcp` 是一个 [MCP](https://modelcontextprotocol.io) 服务，让 Codex、Claude Code、Cursor 等 agent 直接操作本工具。
默认走 stdio（客户端自己启动它），也可以 `oaf mcp --http` 开一个只监听本机的 HTTP 服务。

**工具**：`list_instances`（设备 / 实例）、`screenshot`、`list_workflows`、`validate_workflow`、`run_workflow`
（`mode` 可选 run / observe / trial）、`stop_workflow`、`observe`、`status`、`logs`、`diagnose`、`sync`（等同 `oaf sync`，
还能 check / status / show）、`list_pending`、`approve`、`reject`、`rollback`、`get_config`、`set_config`。

**批准仍然由你来做**：花勾玉、抽卡、购买、出售、分解这类敏感操作，以及改识别数据 / 流程的修复，agent 调 `approve`
不会直接通过——

- 客户端支持 MCP elicitation（stdio）时，会在客户端里弹出确认框直接问你，你选「批准」才生效；关掉确认框不算批准；
- 不支持时（包括所有 HTTP 连接）返回 `needs_user`，你在网页面板或终端（`oaf confirm <编号> yes` / `oaf approve <编号>`）里批准。

不想让客户端弹框批准，把 `mcp.elicitation_approval` 设成 `false`，就只能在网页面板或终端批准。`reject` 随时可用。
放宽安全规则的设置（`supervisor.auto_merge`、`mcp`、把网页面板开到本机以外、改已存 key 的供应商地址）通过 `set_config`
修改也要你批准。API key 不能经 MCP 设置，请自己在终端 `oaf key set <名字>`。

下面的 `oaf` 要换成实际路径时（比如装在虚拟环境里），用 `where oaf`（Windows）或 `which oaf` 查。
不用默认工作区的，在 `mcp` 前面加 `--home <工作区>`。

**Codex**（命令行，写进 `~/.codex/config.toml`）：

```bash
codex mcp add onmyoji -- oaf mcp
```

或者手写 `~/.codex/config.toml`：

```toml
[mcp_servers.onmyoji]
command = "oaf"
args = ["mcp"]
tool_timeout_sec = 900   # run_workflow / observe 可能要等几分钟
```

**Claude Code**：

```bash
claude mcp add -s user onmyoji -- oaf mcp
```

或者在项目根目录放 `.mcp.json`：

```json
{
  "mcpServers": {
    "onmyoji": {"command": "oaf", "args": ["mcp"]}
  }
}
```

**HTTP 方式**（多个客户端共用一个服务；只能监听 127.0.0.1 / localhost / ::1，非本机的 Host、Origin 都会被拒）：

```powershell
$env:OAF_MCP_TOKEN = "换成一串随机字符"   # 可选，设了客户端就要带令牌
oaf mcp --http                            # 默认 http://127.0.0.1:8766/mcp，端口可用 --port 改
```

```bash
claude mcp add -s user --transport http onmyoji http://127.0.0.1:8766/mcp -H "Authorization: Bearer 换成一串随机字符"
```

Codex 用 HTTP：`codex mcp add onmyoji --url http://127.0.0.1:8766/mcp --bearer-token-env-var OAF_MCP_TOKEN`
（等于在 `config.toml` 里写 `url` 和 `bearer_token_env_var`，令牌从环境变量读）。
HTTP 连接没法弹框问你，敏感操作和修复都要到网页面板或终端里批准。

**Skill**：仓库里的 [`skills/onmyoji-agentflow/SKILL.md`](skills/onmyoji-agentflow/SKILL.md) 是给 agent 看的操作说明
（安装、配置 MCP、常见流程、注意事项）。Claude Code 复制到 `~/.claude/skills/onmyoji-agentflow/`，
Codex 复制到 `~/.codex/skills/onmyoji-agentflow/`（或项目里的 `.agents/skills/`）即可。

**命令行里改配置**：`oaf config get llm.budget`、`oaf config set llm.providers.0.enabled true`、
`oaf config set llm.budget.daily_tokens null`。另外新增 `oaf reject <编号>`（拒绝改动）和 `oaf revert <编号>`（撤销已合并的改动）。

## 工作流格式（简要）

```yaml
format: 1
name: orochi
title: 御魂（个人）
resources: [assttyys/colors.yaml]
similarity: 93
params: {max_runs: {default: 30, min: 1, max: 999}}
vars: {done: 0}
limits: {timeout_s: 14400, unknown_timeout_s: 60, stuck_timeout_s: 120, no_progress_timeout_s: 600, max_repeat: 20}
stop_when: "done >= max_runs"
states:
  - id: challenge
    when: {res: 御魂挑战界面}          # 或 colors / find / image / ocr / expr / all / any / not
    do: [{click: [1100, 560, 1180, 640]}, {inc: done}]
    progress: true
  - id: buy
    sensitive: 花勾玉                    # 敏感操作必须标出，并先确认
    when: {res: 体力购买弹窗}
    do: [{confirm: 花勾玉}, {click: [600, 400, 680, 440]}]
```

这里的资源名只是示意，完整写法看 `src/onmyoji_agentflow/data/workflows/` 里的三个内置工作流。

## 开发

```bash
pip install -e .[test]
python -m pytest -q
```

CI（GitHub Actions）在 Windows 和 Linux 上跑全部测试，还会拉取真实的两个上游仓库跑一次完整的 `oaf sync`。

## 已知限制

- 没在真实的 Windows 10/11 + MuMu 12 + 阴阳师上跑过：识别率、MuMu 专用通道、adb 实际能不能用都还不知道。
- 内置工作流的回放测试用的是程序合成的截图。
- OAS 的资源会转换进工作区，但内置工作流还没有用它们；OAS 的任务流程是 Python 代码，还没有翻译通道。
- 大模型修复和翻译只用模拟的大模型测试过，没接真实的 API 跑过。
- OCR 是可选组件，没测过。
- MCP：Claude Code 2.1.304 用 stdio 和 HTTP 都能连上并读到工具列表，Codex 0.163.0 能用 `codex mcp add` 加上配置；
  两个客户端都没有实际让 agent 调用工具跑过，客户端里弹框批准（elicitation）只用模拟客户端测过。

## 许可

GPL-3.0-or-later，见 [LICENSE](LICENSE)。来自 OAS 的代码和资源是 GPL-3.0，来自 assttyys 的部分保留 MIT 版权声明
（Copyright (c) 2019 Chaos），详见 [NOTICE.md](NOTICE.md)。
