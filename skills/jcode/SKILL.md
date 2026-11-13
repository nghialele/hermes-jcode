---
name: jcode
description: Use when installing, configuring, or driving jcode CLI.
version: 1.0.0
author: nghialele
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, jcode, TUI, Daemon, MCP, Skills, Remote]
    related_skills: [claude-code, codex, opencode, hermes-agent]
    homepage: https://github.com/nghialele/hermes-jcode
---

# jcode

Rust TUI coding agent. Daemon owns sessions/tools/provider calls; the TUI is a
socket client — so one daemon can be driven from a laptop, a phone, or a script.

## When to Use

- Installing or uninstalling jcode, or debugging a failed install
- Logging in a provider (subscription OAuth or a custom OpenAI-compatible endpoint)
- Editing `~/.jcode/config.toml`, MCP servers, or jcode skills
- Driving a remote jcode daemon (socket forwarding, `--remote-working-dir`)
- Pairing phone/web clients through the gateway
- Looking up a slash command or keybinding

Anything else: verify against the live binary (`jcode --help`, `/help`, `/hotkeys`);
docs: https://jcode.sh/docs (snapshot 2026-11-13, v0.99.x).

## From Hermes

The `jcode` Hermes plugin (default profile) exposes two tools — use them instead of
hand-rolling a terminal call:

- `jcode_run(prompt, cwd?, model?, provider_profile?, timeout?)` — one-shot run
- `jcode_status(auth_test?)` — binary/version, config + mcp.json presence, skills,
  daemon socket, optional provider auth check

The same file is bundled as the plugin skill `jcode:jcode`.

## Install

| Platform | Command |
|---|---|
| macOS / Linux | `curl -fsSL https://jcode.sh/install \| bash` |
| Windows 11 (PS 5.1+) | `irm https://jcode.sh/install.ps1 \| iex` |
| macOS (brew) | `brew tap 1jehuang/jcode && brew install jcode` |
| Source | `git clone https://github.com/1jehuang/jcode.git && cd jcode && cargo build --release && scripts/install_release.sh` |
| Termux | `pkg install glibc patchelf` **first**, then the install script |

Uninstall keeps config/auth/sessions (reinstall resumes); `--purge` wipes them,
`--dry-run` previews:

```bash
curl -fsSL https://raw.githubusercontent.com/1jehuang/jcode/master/scripts/uninstall.sh | bash -s -- --yes
```

## First run

```bash
jcode                      # TUI
jcode run "say hello"      # one-shot, non-interactive
jcode --resume fox         # resume by memorable session name
jcode serve                # persistent background daemon
jcode connect              # attach a client to it
```

Instruction files, both loaded into every session in scope: `AGENTS.md` (repo
root) and `~/AGENTS.md` (machine-wide).

## Providers

```bash
jcode login --provider claude|openai|gemini|copilot|azure|ollama|lmstudio
```

Named OpenAI-compatible profiles ship for `openrouter`, `deepseek`, `moonshotai`,
`huggingface`, `nebius`. Switch model with `/model` in the TUI or `--model`.

Custom endpoint — key goes through stdin so it never lands in shell history:

```bash
printf '%s' "$MY_API_KEY" | jcode provider add my-api \
  --base-url https://llm.example.com/v1 \
  --model my-model-id \
  --api-key-stdin \
  --set-default

jcode --provider-profile my-api auth-test      # smoke test
jcode --provider-profile my-api run 'hello'
```

Local server with no auth: `--no-api-key` plus a `localhost` base URL.

Headless/remote login: `--no-browser` prints the auth URL; `claude`, `openai`,
`gemini`, `copilot` also take `--print-auth-url`, then `--callback-url` or
`--auth-code` to finish out of band. `jcode auth-test --all-configured` checks
everything at once. `/account` switches accounts within one provider.

## Config

`~/.jcode/config.toml` (or `$JCODE_HOME/config.toml`). Empty is valid — every key
has a default.

| Section | Controls |
|---|---|
| `[provider]` | default provider/model, reasoning effort, failover |
| `[providers.*]` | named profiles: base URL, key source, models, context windows |
| `[display]` | theme, centered layout, diff mode, diagrams, animations |
| `[features]` | memory, swarm, mermaid, update channel |
| `[keybindings]` | every rebindable shortcut (`""` disables one) |
| `[agents]` | swarm model routing, spawn mode, concurrency cap, memory sidecar |
| `[hooks]` | shell commands at turn / session / tool boundaries |
| `[notifications]` | turn-complete notifications and sounds |
| `[ambient]` | background ambient mode: schedule, budget, work branches |

```toml
[provider]
default_provider = "openai"

[display]
centered = true

[features]
memory = true
swarm = true

[keybindings]
side_panel_toggle = "alt+m"
new_terminal = "alt+enter"
```

Other files it reads:

| File | Purpose |
|---|---|
| `~/.jcode/mcp.json` · `.jcode/mcp.json` | global / project MCP servers |
| `~/.jcode/swarm-prompt.md` · `.jcode/swarm-prompt.md` | swarm routing policy (project wins) |
| `~/.jcode/skills/<name>/SKILL.md` | installed skills |
| `~/.config/jcode/*.env` | per-provider keys and endpoint overrides |

## MCP

Separate from `config.toml`. Also reads Claude Code's `~/.claude.json` and
`.mcp.json`, and imports Claude Code + Codex servers on first run.

```json
{ "mcpServers": { "filesystem": { "command": "/path/to/server", "args": ["--root", "/workspace"], "env": {} } } }
```

**stdio only.** HTTP/SSE entries are recognized and skipped. Tools are advertised
from an on-disk schema cache at session start, so a slow handshake never blocks
startup or busts the prompt cache.

## Skills

Markdown packs at `~/.jcode/skills/<name>/SKILL.md`; Claude Code plugin skills
load unchanged. Not all loaded at startup: the conversation is embedded as a
vector and a matching skill is injected on demand. Force one with `/skillname`,
or ask the agent to load it; `/skills` shows what's loaded.

## Remote

Simplest: run inside SSH under tmux/zellij. A dropped connection doesn't kill the
turn — the daemon finishes it and `jcode --resume` reattaches.

Local client, remote daemon — forward the socket:

```bash
# remote
jcode serve --server-name mybox
# laptop
ssh -N -L /tmp/jcode-mybox.sock:/run/user/1000/jcode.sock mybox &
jcode --socket /tmp/jcode-mybox.sock -C /local/checkout --remote-working-dir /remote/checkout
```

Socket defaults to `$XDG_RUNTIME_DIR/jcode.sock` on the server. `-C` must exist
**locally**; `--remote-working-dir` must be absolute and is where every tool, git
op, and edit actually runs.

## Gateway (phone / web)

Off by default.

```toml
[gateway]
enabled = true   # port 7643
```

```bash
jcode pair                 # 6-digit code + QR, 5 min TTL
jcode pair --list
jcode pair --revoke <device>
```

Paired clients speak the TUI protocol (streaming, tool cards, interrupts, session
switching, model picking). Tokens stored hashed.

## Scripting

TypeScript SDK launches a private jcode or attaches to a running one via
`jcode api-bridge`; with socket forwarding that includes a remote daemon.

## Slash commands

`/` fuzzy-matches; `/help` lists everything for the installed version.

| Command | Does |
|---|---|
| `/model` · `/effort` | switch model · set reasoning effort |
| `/login` · `/account` | log in · switch accounts |
| `/resume` · `/fork` · `/transfer` | session picker · fork to new window · compact into handoff session |
| `/compact` · `/clear` · `/rewind` | compact · clear · rewind conversation |
| `/todos` | session todo card |
| `/commit` · `/commit-push` | logical commits, optional push |
| `/review` · `/test` | one-shot review · verify a claim with layered tests |
| `/diff` | cycle diff display mode |
| `/memory` · `/swarm` · `/skills` | toggle memory · toggle swarm · loaded skills |
| `/usage` · `/info` · `/config` | usage limits · session info/tokens · show or edit config |
| `/hotkeys` · `/keys` | list hotkeys, find terminal/OS conflicts |
| `/update` · `/selfdev` · `/quit` | background update+reload · self-dev session · exit |

## Keybindings

Defaults on Windows/Linux; macOS in the right column. Everything except Enter and
Shift+Enter is rebindable under `[keybindings]`.

| Action | Win/Linux | macOS |
|---|---|---|
| Send now, interleaved with the working agent | Enter | — |
| Queue until the agent finishes its turn | Shift+Enter | — |
| Scroll transcript one step / one page | Ctrl+Shift+K/J · Alt+U/D | Option+U/D |
| Previous / next user prompt | Ctrl+K / Ctrl+J | — |
| Toggle scroll bookmark | Ctrl+G | — |
| Next / previous model | Ctrl+Tab / Ctrl+Shift+Tab | — |
| Accept fallback offer and resend | Ctrl+Y | — |
| Reasoning effort up / down | Alt+Right / Alt+Left | Cmd+Right/Left |
| Centered layout · side panel · diagram pane | Alt+C · Alt+M · Alt+T | Option+… |
| Move between workspaces | Alt+H/J/K/L | Option+H/J/K/L |
| Copy/selection mode · typing scroll lock | Alt+Y · Alt+S | Option+Y/S |
| Cycle diff mode · info widget · todo card | Alt+G · Alt+I · Alt+X | Option+… |
| Inline swarm panel | Alt+N | Option+N |
| Session picker · spawn session in new terminal | Alt+R · Alt+Shift+; | Cmd+B · Cmd+Shift+; |

## Pitfalls

- **Enter sends immediately** and interleaves with the running agent; Shift+Enter
  queues. Sending "one more thing" mid-turn with Enter does not wait for a turn
  boundary.
- MCP: HTTP/SSE silently skipped — a server that works in Claude Code via URL
  won't load here; wrap it in a stdio bridge.
- Skills aren't auto-loaded at startup; if a skill isn't firing, invoke
  `/skillname` explicitly.
- `-C` is validated on the client, `--remote-working-dir` on the server — getting
  them backwards edits the wrong tree.
- The daemon, not the TUI, owns the session: killing the TUI doesn't kill work.
- `/help`, `/hotkeys`, `jcode --help` are authoritative per version — the tables
  above are a v0.99.x snapshot.
- Two copies exist: this skill and the plugin's bundled `jcode:jcode`. Edit here, then
  re-copy into `~/.hermes/plugins/jcode/SKILL.md` — it is a plain copy, not a symlink,
  so they drift silently.
- When the binary is absent the plugin tools return an install hint instead of raising.
  Run `jcode_status` before diagnosing a config problem — `installed: false` explains
  every other failure.
