"""Tests for the jcode Hermes plugin.

They exercise the real handlers against a stub `jcode` binary on PATH, so the
argv the plugin builds and the JSON it returns are what a user would get — no
Hermes install required. Run with `pytest -q`.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("hermes_jcode", PLUGIN_DIR / "__init__.py")
jp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jp)


# --------------------------------------------------------------------------- helpers

def make_stub(dirpath: Path, exit_code: int = 0, stdout: str = "STUB-ARGV") -> Path:
    """Drop a fake `jcode` on disk that echoes its argv. Returns the PATH entry.

    Two flavours because cmd.exe is not bash and never will be: a .cmd batch file
    on Windows, a chmod'd /bin/sh script everywhere else.
    """
    dirpath.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        stub = dirpath / "jcode.cmd"
        stub.write_text(
            f"@echo off\r\necho {stdout}:%*\r\nexit /b {exit_code}\r\n", encoding="utf-8"
        )
    else:
        stub = dirpath / "jcode"
        stub.write_text(
            f'#!/bin/sh\necho "{stdout}:$*"\nexit {exit_code}\n', encoding="utf-8"
        )
        stub.chmod(0o755)
    return dirpath


@pytest.fixture
def no_jcode(monkeypatch, tmp_path):
    """An empty PATH: `shutil.which` finds nothing."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    return empty


@pytest.fixture
def stub_jcode(monkeypatch, tmp_path):
    """A stub jcode that succeeds and echoes its argv."""
    path = make_stub(tmp_path / "bin", exit_code=0)
    monkeypatch.setenv("PATH", str(path) + os.pathsep + os.environ.get("PATH", ""))
    return path


class DummyCtx:
    """Records what register() wires up."""

    def __init__(self):
        self.tools = []
        self.skills = []

    def register_tool(self, name, toolset, schema, handler):
        self.tools.append({"name": name, "toolset": toolset, "schema": schema, "handler": handler})

    def register_skill(self, name, path, description=""):
        self.skills.append({"name": name, "path": Path(path), "description": description})


# --------------------------------------------------------------------------- missing binary

def test_status_without_binary_reports_install_hint(no_jcode):
    out = json.loads(jp.handle_status({}))
    assert out["installed"] is False
    assert "jcode.sh/install" in out["install_hint"]


def test_run_without_binary_fails_cleanly(no_jcode):
    out = json.loads(jp.handle_run({"prompt": "hello"}))
    assert out["success"] is False
    assert "jcode.sh/install" in out["error"]


# --------------------------------------------------------------------------- input validation

def test_run_requires_prompt(stub_jcode):
    for bad in ({}, {"prompt": ""}, {"prompt": "   "}):
        out = json.loads(jp.handle_run(bad))
        assert out == {"success": False, "error": "prompt is required"}


def test_run_rejects_missing_cwd(stub_jcode, tmp_path):
    missing = tmp_path / "nope"
    out = json.loads(jp.handle_run({"prompt": "x", "cwd": str(missing)}))
    assert out["success"] is False
    assert "cwd does not exist" in out["error"]


# --------------------------------------------------------------------------- argv

def test_run_argv_order_and_flags(stub_jcode, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    out = json.loads(jp.handle_run({
        "prompt": "summarize README",
        "model": "claude-sonnet-4-5",
        "provider_profile": "my-api",
        "cwd": str(work),
    }))
    assert out["success"] is True
    assert out["cwd"] == str(work)
    echoed = out["stdout"]
    # flags precede the subcommand, and the prompt is one argv element
    assert "--provider-profile my-api --model claude-sonnet-4-5 run" in echoed
    assert "summarize README" in echoed
    assert out["argv"] == [
        "jcode", "--provider-profile", "my-api", "--model", "claude-sonnet-4-5", "run", "<prompt>",
    ]


def test_run_without_flags_is_just_run(stub_jcode):
    out = json.loads(jp.handle_run({"prompt": "hi"}))
    assert out["stdout"].splitlines()[0].split(":", 1)[1].strip().startswith("run")


def test_run_nonzero_exit_is_reported(stub_jcode, monkeypatch, tmp_path):
    make_stub(tmp_path / "fail", exit_code=3)
    monkeypatch.setenv("PATH", str(tmp_path / "fail") + os.pathsep + os.environ["PATH"])
    out = json.loads(jp.handle_run({"prompt": "boom"}))
    assert out["success"] is False
    assert out["exit_code"] == 3


# --------------------------------------------------------------------------- status

def test_status_with_binary(stub_jcode, monkeypatch, tmp_path):
    jcode_home = tmp_path / "jcodehome"
    (jcode_home / "skills" / "review").mkdir(parents=True)
    (jcode_home / "config.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("JCODE_HOME", str(jcode_home))
    out = json.loads(jp.handle_status({}))
    assert out["installed"] is True
    assert out["config_present"] is True
    assert out["mcp_config_present"] is False
    assert out["skills"] == ["review"]
    assert "STUB-ARGV" in out["version"]
    assert "auth_test" not in out


def test_status_auth_test_is_opt_in(stub_jcode):
    out = json.loads(jp.handle_status({"auth_test": True}))
    assert out["auth_test"]["exit_code"] == 0
    assert "auth-test --all-configured" in out["auth_test"]["output"]


# --------------------------------------------------------------------------- registration

def test_register_wires_two_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(jp, "_hermes_home", lambda: tmp_path)  # no standalone skill
    ctx = DummyCtx()
    jp.register(ctx)
    assert [t["name"] for t in ctx.tools] == ["jcode_run", "jcode_status"]
    assert {t["toolset"] for t in ctx.tools} == {"jcode"}
    assert [s["name"] for s in ctx.skills] == ["jcode"]


def test_register_skips_bundled_skill_when_standalone_exists(monkeypatch, tmp_path):
    (tmp_path / "skills" / "autonomous-ai-agents" / "jcode").mkdir(parents=True)
    (tmp_path / "skills" / "autonomous-ai-agents" / "jcode" / "SKILL.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(jp, "_hermes_home", lambda: tmp_path)
    ctx = DummyCtx()
    jp.register(ctx)
    assert ctx.skills == []
    assert [t["name"] for t in ctx.tools] == ["jcode_run", "jcode_status"]


def test_schemas_match_tool_names():
    assert jp.RUN_SCHEMA["name"] == "jcode_run"
    assert jp.STATUS_SCHEMA["name"] == "jcode_status"
    assert jp.RUN_SCHEMA["parameters"]["required"] == ["prompt"]
    assert jp.RUN_SCHEMA["description"] and jp.STATUS_SCHEMA["description"]


def test_bundled_skill_file_exists():
    assert (PLUGIN_DIR / "skills" / "jcode" / "SKILL.md").is_file()
