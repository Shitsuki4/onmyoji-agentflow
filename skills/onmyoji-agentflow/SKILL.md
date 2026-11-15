---
name: onmyoji-agentflow
description: Operate onmyoji-agentflow (Onmyoji / 阴阳师 YAML workflows on the MuMu 12 emulator) through its MCP server — list instances, take screenshots, run, observe and stop workflows, read status and logs, diagnose a screen, sync upstream assttyys / OAS data, handle pending approvals, roll back, and read or change config such as LLM providers and usage limits. Use when the user asks to run or check 御魂 / 结界突破 / 探索 or other onmyoji-agentflow workflows, sync upstream, or change its settings.
---

# onmyoji-agentflow

onmyoji-agentflow runs 阴阳师 automation as YAML state-machine workflows on MuMu 12 (Windows). The
`oaf mcp` server exposes it to you as MCP tools. Talk to the user in Chinese unless they write in
another language.

## Install and connect

The user installs it on the Windows machine that runs MuMu 12 (needs Python 3.10+ and git):

```powershell
pip install git+https://github.com/Shitsuki4/onmyoji-agentflow
oaf init        # creates the workspace and config.yaml
oaf sync        # optional: pull and convert the latest assttyys / OAS data
```

Register the MCP server (stdio; the client starts it):

- Codex: `codex mcp add onmyoji -- oaf mcp`. In `~/.codex/config.toml` set
  `tool_timeout_sec = 900` under `[mcp_servers.onmyoji]`, because `observe` and `run_workflow`
  with `wait_seconds` can take minutes.
- Claude Code: `claude mcp add -s user onmyoji -- oaf mcp`
- Workspace other than the default: `oaf --home <dir> mcp`.
- Shared local HTTP server instead: the user runs `oaf mcp --http` (loopback only, default
  `http://127.0.0.1:8766/mcp`, optional bearer token from `OAF_MCP_TOKEN`); then
  `claude mcp add -s user --transport http onmyoji http://127.0.0.1:8766/mcp -H "Authorization: Bearer <token>"`
  or `codex mcp add onmyoji --url http://127.0.0.1:8766/mcp --bearer-token-env-var OAF_MCP_TOKEN`.

If the tools are missing, check `oaf --version` works in the same shell the client uses, or give
the full path from `where oaf`.

## Tools

| Tool | What it does |
|---|---|
| `status` | running jobs, recent runs, pending approvals, last sync, LLM usage and limits |
| `list_instances` | configured MuMu instances, instances found on the machine, which are busy |
| `screenshot` | current game screen of an instance (image); read-only |
| `list_workflows` / `validate_workflow` | workflows with params; format check + replay tests |
| `observe` | run a workflow recognising only, never tapping; returns which states it saw |
| `run_workflow` | `mode`: `run` (supervised, auto repair), `observe`, `trial` (at most `actions` taps); `params` e.g. `{"max_runs": 10}`; returns at once unless `wait_seconds` |
| `stop_workflow` | stop the run on an instance after the current step |
| `diagnose` | which states of a workflow match the current screen or an image file, with scores |
| `logs` | recent events (filter `level`, `source`), or one run's summary by `run_id` |
| `sync` | `run` / `force` / `check` / `status` / `show` — same as `oaf sync` |
| `list_pending` | sensitive-action confirmations and changes waiting for the user |
| `approve` / `reject` | ask the user to approve (see below) / refuse |
| `rollback` | `target=sync` (last sync or `id`) or `target=change` with `id` |
| `get_config` / `set_config` | dotted paths such as `llm.budget.daily_tokens`, `llm.providers.0.enabled` |

## Common flows

**Run a workflow**
1. `status` and `list_instances`: make sure the instance is free and MuMu is found.
2. `screenshot` to see where the game is. Workflows expect the screen they start from (for
   `orochi`, the 御魂 team screen); tell the user if the game is elsewhere.
3. New or changed workflow: `observe` first and check it recognised the expected states.
4. `run_workflow` with the user's params (`orochi` / `realm_raid`: `max_runs`; `exploration`:
   `max_rounds`, `max_swipes`). Poll `status` every minute or so; do not loop tightly.
5. When it ends, report the summary from `status` or `logs run_id=<id>`: runs done, why it stopped.

**It failed or got stuck**
`logs` (level `warn`/`error`) → `screenshot` → `diagnose` on that workflow. The supervisor may
have proposed a repair: it shows up in `list_pending` as a `change`. Explain what it changes
(`note`, `validation`) and let the user decide.

**Sync upstream**
`sync action=check` to see if assttyys / OAS changed; `sync action=run` to pull, convert and
validate (takes minutes; poll `sync action=status`); `sync action=show` for the report. Changes to
recognition data wait in `list_pending`. Undo with `rollback target=sync`.

**Settings**
`get_config path=llm` shows providers and limits; which providers have a saved key is in
`api_keys_saved`. LLM usage is unlimited by default (`llm.budget.*` are `null`). Set a limit only
when the user asks, e.g. `set_config path=llm.budget.daily_tokens value=1000000`; `null` removes
it. Enable a provider with `set_config path=llm.providers.<i>.enabled value=true`. Changes apply at
once and are saved to config.yaml.

## Approvals: never decide for the user

Sensitive actions (花勾玉 jade, 抽卡 summoning, 购买 buying, 出售 selling, 分解 dismantling) pause
the run and wait for a confirmation; repairs that change recognition data or a workflow wait as a
change. Unanswered confirmations count as refused after the timeout.

- `approve` does not approve by itself. If the client supports MCP elicitation, the user gets a
  dialog and only their "批准" counts. Otherwise it returns `needs_user`: tell the user what is
  waiting (category, detail, instance or the change note) and that they approve it in the web
  panel (`oaf web`) or a terminal (`oaf confirm <id> yes`, `oaf approve <id>`).
- Never run `oaf confirm`, `oaf approve`, or click approve in the web panel on the user's behalf,
  and never edit the database or config.yaml to get around a pending item.
- Ask before every `approve`; one yes covers one item. `reject` is fine when the user says no.
- `set_config` on safety settings (`supervisor.auto_merge`, `mcp.*`, a non-local `web.host`, a
  provider `base_url` that has a saved key) also needs the user's approval and returns
  `needs_user` otherwise.
- API keys are never set through MCP. Ask the user to run `oaf key set <provider>` themselves, and
  never ask them to paste a key into the chat.

## Cautions

- Tell the user once, before the first run, that NetEase's terms forbid third-party automation and
  the account can be banned; randomised taps only copy OAS / assttyys and are not a guarantee.
- Version 0.1.x has not run on real Windows + MuMu 12 + the game; recognition may be wrong. Prefer
  `observe` and `trial` before long `run`s, and watch the first runs with `screenshot`.
- One workflow per instance at a time. `stop_workflow` stops runs started by this MCP server and
  runs in the same process; runs started from the web panel or another terminal are stopped there.
- Screenshots are also saved under `runs/mcp-screenshots` in the oaf home directory.
