"""Unit tests for guard.init_cmd (Work Package C)."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from guard_cli.init_cmd import (
    find_repo_root,
    find_test_environment,
    check_pytest_cov,
    write_integrations,
    record_state,
    INTEGRATION_MARKER_START,
    INTEGRATION_MARKER_END,
)
from guard_cli.backend import ServerBackend


def test_find_repo_root_valid(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    root = find_repo_root(tmp_path)
    assert root == tmp_path.resolve()


def test_find_repo_root_invalid(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="does not appear to be a Python git repository"):
        find_repo_root(empty_dir)


def test_find_test_environment(tmp_path):
    # If no virtualenv in tmp_path, falls back to sys.executable
    py = find_test_environment(tmp_path)
    assert py.exists()
    assert py.is_file()


def test_check_pytest_cov():
    # In active venv pytest-cov is installed
    active_py = Path(sys.executable)
    assert check_pytest_cov(active_py, auto_yes=False) is True


def test_write_integrations_idempotent(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")

    claude_settings = tmp_path / ".claude" / "settings.json"
    claude_settings.parent.mkdir()
    claude_settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Agent Rules\nAlways follow instructions.\n", encoding="utf-8")

    # Run 1
    modified_1 = write_integrations(tmp_path, ["claude", "antigravity"])
    assert len(modified_1) >= 3

    # Check gitignore
    gi_content = gitignore.read_text(encoding="utf-8")
    assert ".guard/" in gi_content

    # Check settings.json preserved existing key
    settings = json.loads(claude_settings.read_text(encoding="utf-8"))
    assert settings["theme"] == "dark"
    assert settings["commands"]["guard"] == "guard run"

    # Check AGENTS.md has marked block
    agents_content = agents_md.read_text(encoding="utf-8")
    assert INTEGRATION_MARKER_START in agents_content
    assert INTEGRATION_MARKER_END in agents_content
    assert "Always follow instructions." in agents_content

    # Check CLAUDE.md was created
    claude_md = tmp_path / "CLAUDE.md"
    assert claude_md.exists()
    assert INTEGRATION_MARKER_START in claude_md.read_text(encoding="utf-8")

    # Run 2 (Idempotency check: must not duplicate markers or entries)
    write_integrations(tmp_path, ["claude", "antigravity"])

    gi_content_2 = gitignore.read_text(encoding="utf-8")
    assert gi_content_2.count(".guard/") == 1

    agents_content_2 = agents_md.read_text(encoding="utf-8")
    assert agents_content_2.count(INTEGRATION_MARKER_START) == 1
    assert agents_content_2.count(INTEGRATION_MARKER_END) == 1


def test_record_state(tmp_path):
    backend = MagicMock()
    mock_graph = MagicMock()
    backend.get_graph.return_value = mock_graph

    state = record_state(tmp_path, "guard_test_repo", backend, commit_sha="abcdef123456")
    assert state["head_sha"] == "abcdef123456"
    assert state["graph_name"] == "guard_test_repo"

    state_file = tmp_path / ".guard" / "state.json"
    assert state_file.exists()
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["head_sha"] == "abcdef123456"
