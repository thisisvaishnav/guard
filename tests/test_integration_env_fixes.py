"""Tests for integration environment and hook fixes.

Guarantees tested:
1. claude.install() resolves guard executable via get_guard_executable() or explicit parameter.
2. claude status() and uninstall() correctly handle absolute path guard executables.
3. find_test_environment() respects VIRTUAL_ENV environment variable.
4. find_test_environment() respects sys.prefix when no local repo venv exists.
5. find_test_environment() respects CONDA_PREFIX environment variable.
6. antigravity.install() registers SessionStart, but NOT PreInvocation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from guard_cli.init_cmd import find_test_environment
from guard_cli.integrations import antigravity, claude


def test_claude_install_uses_get_guard_executable(tmp_path, monkeypatch):
    """claude.install() should use get_guard_executable() so virtualenv paths are preserved."""
    repo = tmp_path / "claude_repo"
    repo.mkdir()

    custom_guard = "/opt/custom/venv/bin/guard"
    with patch("guard_cli.integrations.claude.get_guard_executable", return_value=custom_guard):
        ok, msg = claude.install(repo_path=repo, shared=False)
        assert ok is True

    settings_file = repo / ".claude" / "settings.local.json"
    assert settings_file.exists()

    data = json.loads(settings_file.read_text(encoding="utf-8"))
    stop_hooks = data.get("hooks", {}).get("Stop", [])
    start_hooks = data.get("hooks", {}).get("SessionStart", [])

    # Verify Stop hook uses custom_guard
    assert any(
        any(sub.get("command") == f"{custom_guard} hook stop" for sub in h.get("hooks", []))
        for h in stop_hooks
    )
    # Verify SessionStart hook uses custom_guard
    assert any(
        any(sub.get("command") == f"{custom_guard} hook session-start" for sub in h.get("hooks", []))
        for h in start_hooks
    )

    # Status should recognize it as installed
    stat = claude.status(repo_path=repo, shared=False)
    assert stat["installed"] is True
    assert stat["session_start_installed"] is True

    # Uninstall should successfully remove it even with absolute path
    ok_un, msg_un = claude.uninstall(repo_path=repo, shared=False)
    assert ok_un is True
    stat_un = claude.status(repo_path=repo, shared=False)
    assert stat_un["installed"] is False


def test_claude_install_with_explicit_guard_executable(tmp_path):
    """claude.install() should accept an optional guard_executable argument."""
    repo = tmp_path / "claude_repo_explicit"
    repo.mkdir()

    explicit_guard = "/explicit/bin/guard"
    ok, msg = claude.install(repo_path=repo, shared=False, guard_executable=explicit_guard)
    assert ok is True

    settings_file = repo / ".claude" / "settings.local.json"
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    stop_hooks = data.get("hooks", {}).get("Stop", [])

    assert any(
        any(sub.get("command") == f"{explicit_guard} hook stop" for sub in h.get("hooks", []))
        for h in stop_hooks
    )


def test_find_test_environment_respects_virtual_env(tmp_path, monkeypatch):
    """find_test_environment() should use VIRTUAL_ENV if pytest is functional there."""
    repo = tmp_path / "empty_repo"
    repo.mkdir()

    custom_venv = tmp_path / "external_venv"
    custom_bin = custom_venv / "bin"
    custom_bin.mkdir(parents=True)
    fake_python = custom_bin / "python"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)

    monkeypatch.setenv("VIRTUAL_ENV", str(custom_venv))
    monkeypatch.delenv("CONDA_PREFIX", raising=False)

    def fake_subprocess_run(cmd, *args, **kwargs):
        if str(fake_python) in str(cmd[0]) and "-m" in cmd and "pytest" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pytest 8.0.0")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stderr="not found")

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        py = find_test_environment(repo)
        assert py.resolve() == fake_python.resolve()


def test_find_test_environment_respects_sys_prefix(tmp_path, monkeypatch):
    """find_test_environment() should use sys.prefix if no repo venv or VIRTUAL_ENV."""
    repo = tmp_path / "empty_repo"
    repo.mkdir()

    custom_prefix = tmp_path / "active_sys_prefix"
    custom_bin = custom_prefix / "bin"
    custom_bin.mkdir(parents=True)
    fake_python = custom_bin / "python"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.setattr(sys, "prefix", str(custom_prefix))

    def fake_subprocess_run(cmd, *args, **kwargs):
        if str(fake_python) in str(cmd[0]) and "-m" in cmd and "pytest" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pytest 8.0.0")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stderr="not found")

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        py = find_test_environment(repo)
        assert py.resolve() == fake_python.resolve()


def test_find_test_environment_respects_conda_prefix(tmp_path, monkeypatch):
    """find_test_environment() should use CONDA_PREFIX if set."""
    repo = tmp_path / "empty_repo"
    repo.mkdir()

    custom_conda = tmp_path / "active_conda_prefix"
    custom_bin = custom_conda / "bin"
    custom_bin.mkdir(parents=True)
    fake_python = custom_bin / "python"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("CONDA_PREFIX", str(custom_conda))

    def fake_subprocess_run(cmd, *args, **kwargs):
        if str(fake_python) in str(cmd[0]) and "-m" in cmd and "pytest" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pytest 8.0.0")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stderr="not found")

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        py = find_test_environment(repo)
        assert py.resolve() == fake_python.resolve()


def test_antigravity_install_uses_session_start_not_pre_invocation(tmp_path):
    """antigravity.install() must register SessionStart, NOT PreInvocation."""
    repo = tmp_path / "agy_repo"
    repo.mkdir()

    ok, msg = antigravity.install(repo)
    assert ok is True

    hooks_file = repo / ".agents" / "hooks.json"
    assert hooks_file.exists()

    data = json.loads(hooks_file.read_text(encoding="utf-8"))
    guard_cfg = data.get("guard-stop", {})

    # Stop must be registered
    assert "Stop" in guard_cfg
    # SessionStart must be registered
    assert "SessionStart" in guard_cfg
    assert any("hook session-start" in h.get("command", "") for h in guard_cfg["SessionStart"])

    # PreInvocation must NOT have hook session-start registered
    pre_handlers = guard_cfg.get("PreInvocation", [])
    assert not any("hook session-start" in h.get("command", "") for h in pre_handlers)

    # Status checks
    stat = antigravity.status(repo)
    assert stat["installed"] is True
    assert stat["session_start_installed"] is True
    assert stat["pre_invocation_installed"] is False
