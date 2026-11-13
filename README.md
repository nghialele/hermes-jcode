# hermes-jcode

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that puts the
[jcode](https://jcode.sh) coding agent on your agent's toolbelt — plus the `jcode`
skill that teaches an agent how to install, configure and drive jcode without
inventing commands.

jcode is a Rust TUI coding agent: a daemon owns sessions, tools and provider
calls, and the TUI is a socket client. This plugin drives the same binary
non-interactively, so Hermes can hand it a self-contained task and read the
result back.

## What you get

| Kind | Name | What it does |
|---|---|---|
| Tool | `jcode_run` | One-shot `jcode run "<prompt>"`, with optional `model`, `provider_profile`, `cwd`, `timeout` |
| Tool | `jcode_status` | Binary + version, `~/.jcode/config.toml` and `mcp.json` presence, installed jcode skills, daemon socket, opt-in `auth-test --all-configured` |
| Skill | `jcode` (as `jcode:jcode`) | Install per platform, provider login, `config.toml` map, MCP (stdio-only) gotcha, remote daemon over a forwarded socket, gateway pairing, slash commands, keybindings, pitfalls |

## Install

**Plugin** (tools + bundled skill):

```bash
hermes plugins install nghialele/hermes-jcode
hermes plugins enable jcode
```

From a local checkout (Hermes installs plugins from the catalog or a Git URL, so a
checkout is a drop-in directory):

```bash
git clone https://github.com/nghialele/hermes-jcode
cp -r hermes-jcode ~/.hermes/plugins/jcode
hermes plugins enable jcode
```

**Skill only** (no plugin, no tools — just the instructions):

```bash
hermes skills install nghialele/hermes-jcode/jcode
```

Or copy it by hand — the layout is the standard one:

```bash
cp -r hermes-jcode/skills/jcode ~/.hermes/skills/jcode
```

The plugin registers its bundled skill only when your profile has no standalone
`jcode` skill of its own. Install both and you still get one entry in the skill
index; the standalone copy wins because it's the one you can edit in place.

Prerequisite for the tools to do anything: the `jcode` binary on `PATH`.

```bash
curl -fsSL https://jcode.sh/install | bash          # macOS / Linux
irm https://jcode.sh/install.ps1 | iex              # Windows 11, PowerShell 5.1+
brew tap 1jehuang/jcode && brew install jcode       # macOS, Homebrew
```

## Use

Ask in plain language, or call the tools directly:

```
Run jcode on the auth module refactor in ~/src/api and report what it changed.
```

```python
jcode_run(prompt="explain the failure in tests/test_sync.py", cwd="/home/me/src/api")
jcode_run(prompt="summarize README", model="claude-sonnet-4-5", provider_profile="my-api")
jcode_status()                     # installed? version? config? skills?
jcode_status(auth_test=True)       # also verify every configured provider login
```

`jcode_run` returns JSON:

```json
{
  "success": true,
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "cwd": "/home/me/src/api",
  "argv": ["jcode", "--provider-profile", "my-api", "run", "<prompt>"]
}
```

The prompt is passed as a single argv element (never through a shell), the run is
killed at the timeout (default 600s, clamped 10–3600), and output is capped at
20 KB stdout / 4 KB stderr so one verbose run can't flood the context.

## Design notes

- **Shells out, owns nothing.** No daemon, no background process, no state. If
  `jcode` isn't installed, both tools say so and hand back the install command
  instead of raising.
- **No credential handling.** The plugin never reads, stores or passes an API
  key. jcode uses whatever login it already has; `jcode_status` reports *whether*
  config exists, not what's in it.
- **One skill, not two.** The bundled copy is a fallback for installs without a
  standalone `jcode` skill — checked against `get_hermes_home()/skills/**/jcode/SKILL.md`
  at registration time.
- **Nothing at import time.** `register(ctx)` only wires a toolset and a skill;
  importing the module touches no files and makes no network calls.

## Requirements

- Hermes Agent with the plugin system (any recent release; `manifest_version: 2`)
- Python 3.10+
- The `jcode` CLI on `PATH` for the tools to run anything
- Linux, macOS or Windows

## Development

```bash
uv run --with pytest pytest -q          # 13 tests, no Hermes install needed
hermes plugins doctor .                 # real runtime contracts
hermes plugins validate .               # the check catalog CI runs
```

The tests drive the real handlers against a stub `jcode` on `PATH`, so argv
construction, exit-code handling and the skill-dedupe branch are exercised
rather than mocked.

Layout:

```
plugin.yaml            manifest (2 tools)
__init__.py            handlers + register(ctx)
skills/jcode/SKILL.md  the bundled skill
tests/test_handlers.py stub-binary tests
```

## Uninstall

```bash
hermes plugins disable jcode
hermes plugins remove jcode
```

## License

MIT — see [LICENSE](LICENSE).

jcode itself is a separate project by [1jehuang](https://github.com/1jehuang/jcode);
this plugin only calls its binary. The skill documents jcode's published docs as
of November 2026 — check `jcode --help` and `/help` for your installed version.
