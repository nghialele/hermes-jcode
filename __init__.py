"""jcode for Hermes — drive the jcode agent CLI as a tool.

Tools
-----
``jcode_run``     one-shot ``jcode run "<prompt>"``, optional model / provider
                  profile / working directory / timeout.
``jcode_status``  is it installed, which version, where config and MCP live,
                  which skills jcode has, whether the daemon socket is up, and
                  optionally ``jcode auth-test --all-configured``.

The plugin also bundles the ``jcode`` skill at ``skills/jcode/SKILL.md``,
resolvable as ``jcode:jcode`` — but only when the profile doesn't already have a
standalone ``jcode`` skill of its own, so the same instructions never appear
twice in the skill index.

Nothing is written by importing or registering this module. No API key is ever
read, stored, or placed on a command line: the tools shell out to the binary the
user already installed and return its stdout/stderr verbatim.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).resolve().parent
SKILL_NAME = "jcode"
# Repo layout: skills/<name>/SKILL.md. The root-level fallback keeps an older
# flat install working after an update.
SKILL_MD = PLUGIN_DIR / "skills" / SKILL_NAME / "SKILL.md"
_LEGACY_SKILL_MD = PLUGIN_DIR / "SKILL.md"
TOOLSET = "jcode"
MAX_STDOUT = 20000
MAX_STDERR = 4000

INSTALL_HINT = (
    "jcode is not installed (no `jcode` on PATH). Install it: "
    "macOS/Linux `curl -fsSL https://jcode.sh/install | bash`; "
    "Windows 11 PowerShell `irm https://jcode.sh/install.ps1 | iex`; "
    "macOS Homebrew `brew tap 1jehuang/jcode && brew install jcode`."
)


def _skill_file() -> Path | None:
    """The bundled SKILL.md, wherever this install keeps it."""
    for candidate in (SKILL_MD, _LEGACY_SKILL_MD):
        if candidate.is_file():
            return candidate
    return None


def _binary() -> str | None:
    """Absolute path to the jcode executable, or None. Windows PATHEXT covers .exe/.cmd."""
    return shutil.which("jcode")


def _exec(args: list[str], cwd: str | None = None, timeout: int = 120):
    """Run jcode. Returns (CompletedProcess|None, error_string)."""
    exe = _binary()
    if not exe:
        return None, INSTALL_HINT
    try:
        # Fixed argv, no shell: the prompt is a prompt, not a command line.
        return subprocess.run(  # noqa: S603
            [exe, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        ), ""
    except subprocess.TimeoutExpired:
        return None, f"jcode timed out after {timeout}s: {' '.join(args)}"
    except OSError as exc:
        return None, f"could not run jcode ({exe}): {exc}"


# --------------------------------------------------------------------------- tools

def handle_run(params: dict, **kwargs) -> str:
    """`jcode [--provider-profile P] [--model M] run "<prompt>"`."""
    del kwargs
    prompt = str(params.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"success": False, "error": "prompt is required"})

    cwd = params.get("cwd")
    if cwd:
        cwd = os.path.expanduser(str(cwd))
        if not os.path.isdir(cwd):
            return json.dumps({"success": False, "error": f"cwd does not exist: {cwd}"})

    args: list[str] = []
    if params.get("provider_profile"):
        args += ["--provider-profile", str(params["provider_profile"])]
    if params.get("model"):
        args += ["--model", str(params["model"])]
    args += ["run", prompt]

    try:
        timeout = int(params.get("timeout") or 600)
    except (TypeError, ValueError):
        timeout = 600
    timeout = max(10, min(timeout, 3600))

    proc, err = _exec(args, cwd=cwd, timeout=timeout)
    if proc is None:
        return json.dumps({"success": False, "error": err})

    return json.dumps({
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "")[-MAX_STDOUT:],
        "stderr": (proc.stderr or "")[-MAX_STDERR:],
        "cwd": cwd or os.getcwd(),
        "argv": ["jcode", *args[:-1], "<prompt>"],
    })


def handle_status(params: dict, **kwargs) -> str:
    """Install / version / config / skills / daemon socket, optional auth-test."""
    del kwargs
    exe = _binary()
    out: dict = {"installed": bool(exe), "binary": exe}
    if not exe:
        out["install_hint"] = INSTALL_HINT
        return json.dumps(out)

    proc, err = _exec(["--version"], timeout=30)
    if proc is not None:
        out["version"] = ((proc.stdout or "") + (proc.stderr or "")).strip()[:300]
    else:
        out["version_error"] = err

    home = Path(os.environ.get("JCODE_HOME") or (Path.home() / ".jcode"))
    out["jcode_home"] = str(home)
    out["config_present"] = (home / "config.toml").is_file()
    out["mcp_config_present"] = (home / "mcp.json").is_file()
    skills_dir = home / "skills"
    out["skills"] = sorted(p.name for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []

    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        out["daemon_socket_present"] = os.path.exists(os.path.join(runtime, "jcode.sock"))

    if params.get("auth_test"):
        proc, err = _exec(["auth-test", "--all-configured"], timeout=120)
        if proc is None:
            out["auth_test"] = {"error": err}
        else:
            out["auth_test"] = {
                "exit_code": proc.returncode,
                "output": ((proc.stdout or "") + (proc.stderr or ""))[-MAX_STDERR:],
            }

    return json.dumps(out)


RUN_SCHEMA = {
    "name": "jcode_run",
    "description": (
        "Run a single non-interactive prompt through the jcode agent CLI "
        "(`jcode run \"<prompt>\"`) and return its stdout/stderr. Use for delegating a "
        "self-contained coding or shell task to jcode. Optionally pick a named provider "
        "profile or model, and set the working directory the agent runs in."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task or question to hand to jcode. Must be self-contained: "
                               "jcode starts a fresh session and sees no prior context.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory jcode runs in (defaults to the session's cwd). "
                               "Must already exist.",
            },
            "provider_profile": {
                "type": "string",
                "description": "Named profile from ~/.jcode/config.toml (e.g. 'my-api', 'openrouter').",
            },
            "model": {
                "type": "string",
                "description": "Model id to use, e.g. 'claude-sonnet-4-5' or a provider-specific id.",
            },
            "timeout": {
                "type": "integer",
                "description": "Seconds before the run is killed. Default 600, clamped to 10-3600.",
            },
        },
        "required": ["prompt"],
    },
}

STATUS_SCHEMA = {
    "name": "jcode_status",
    "description": (
        "Report the state of the local jcode install: binary path and version, whether "
        "~/.jcode/config.toml and mcp.json exist, installed jcode skills, whether the "
        "daemon socket is up, and optionally the result of "
        "`jcode auth-test --all-configured` (which contacts every configured provider)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "auth_test": {
                "type": "boolean",
                "description": "Also run `jcode auth-test --all-configured`. Slow and it hits the "
                               "network; leave false unless provider logins are in question.",
            },
        },
    },
}


def _hermes_home() -> Path:
    """The active profile's Hermes home (profile-aware, per the public plugin API)."""
    try:
        from hermes_constants import get_hermes_home  # public plugin API

        return Path(get_hermes_home())
    except Exception:  # noqa: BLE001 - older host, or outside Hermes (tests)
        return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def _standalone_skill_present() -> bool:
    """True when the active profile already has a plain ``jcode`` skill on disk.

    The profile's own skills directory holds the editable copy. Registering the
    bundled one as well would list the same instructions twice (``jcode`` and
    ``jcode:jcode``) and invite edit drift between them, so the bundled copy is
    a fallback for installs that don't have the standalone skill yet.

    Two copies of the same instructions is how you end up with one that's
    current and one that confidently tells you to run a flag that was removed.
    """
    try:
        return any((_hermes_home() / "skills").glob(f"**/{SKILL_NAME}/SKILL.md"))
    except OSError:
        return False


def register(ctx):
    """Wire the tools and the bundled skill into Hermes."""
    skill_md = _skill_file()
    if skill_md is None:
        log.warning("jcode plugin: no bundled SKILL.md found next to %s", PLUGIN_DIR)
    elif _standalone_skill_present():
        log.info("jcode plugin: profile has a standalone 'jcode' skill; skipping the bundled copy")
    else:
        try:
            ctx.register_skill(
                SKILL_NAME,
                skill_md,
                description="Use when installing, configuring, or driving jcode CLI.",
            )
        except Exception as exc:  # noqa: BLE001 - a bad skill file must not kill the tools
            log.warning("jcode plugin: could not register bundled skill: %s", exc)

    ctx.register_tool(name="jcode_run", toolset=TOOLSET, schema=RUN_SCHEMA, handler=handle_run)
    ctx.register_tool(name="jcode_status", toolset=TOOLSET, schema=STATUS_SCHEMA, handler=handle_status)
