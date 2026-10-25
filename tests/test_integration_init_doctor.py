"""Integration test: guard init then guard doctor on a throwaway repository."""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from guard.init_cmd import run_init, INTEGRATION_MARKER_START
from guard.doctor_cmd import run_doctor
from guard_cli.backend import ServerBackend


@pytest.fixture
def throwaway_repo(tmp_path):
    """Creates a tiny Git repository with 3 tests."""
    repo = tmp_path / "sample_repo"
    repo.mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@guard.dev"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Guard Tester"], cwd=str(repo), check=True, capture_output=True)

    # pyproject.toml
    pyproject = repo / "pyproject.toml"
    pyproject.write_text(
        """[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "sample-calc"
version = "0.1.0"
dependencies = []

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
        encoding="utf-8",
    )

    # Source code
    src_dir = repo / "sample_calc"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    (src_dir / "calc.py").write_text(
        """def add(a: int, b: int) -> int:
    return a + b

def multiply(a: int, b: int) -> int:
    return a * b
""",
        encoding="utf-8",
    )

    # Tests directory with 3 tests
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_calc.py").write_text(
        """from sample_calc.calc import add, multiply

def test_add_positive():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, -1) == -2

def test_multiply():
    assert multiply(3, 4) == 12
""",
        encoding="utf-8",
    )

    # Commit initial state
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True, capture_output=True)

    return repo


def test_init_then_doctor_e2e(throwaway_repo, capsys):
    # Step 1: Run init
    # Choose backend: prefer embedded if 3.12+, otherwise server
    backend_choice = "embedded" if sys.version_info >= (3, 12) else "server"
    if backend_choice == "server" and not ServerBackend().is_healthy():
        pytest.skip("FalkorDB server is not reachable or healthy")

    init_code = run_init(
        repo_path=throwaway_repo,
        backend_preference=backend_choice,
        skip_coverage=True,
        auto_yes=True,
        agents="claude,cursor",
    )
    assert init_code == 0

    # Verify artifacts created by init
    config_file = throwaway_repo / ".guard" / "config.toml"
    assert config_file.exists()
    assert 'type = "' in config_file.read_text(encoding="utf-8")

    state_file = throwaway_repo / ".guard" / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(state["head_sha"]) >= 7

    gitignore = throwaway_repo / ".gitignore"
    assert gitignore.exists()
    assert ".guard/" in gitignore.read_text(encoding="utf-8")

    agents_md = throwaway_repo / "AGENTS.md"
    assert agents_md.exists()
    assert INTEGRATION_MARKER_START in agents_md.read_text(encoding="utf-8")

    claude_settings = (
        throwaway_repo / ".claude" / "settings.local.json"
        if (throwaway_repo / ".claude" / "settings.local.json").exists()
        else throwaway_repo / ".claude" / "settings.json"
    )
    assert claude_settings.exists()
    settings = json.loads(claude_settings.read_text(encoding="utf-8"))
    assert settings.get("commands", {}).get("guard") == "guard run"
    assert any(
        "guard hook stop" in h.get("command", "")
        or any("guard hook stop" in sub.get("command", "") for sub in h.get("hooks", []))
        for h in settings.get("hooks", {}).get("Stop", [])
    )

    # Flush capsys buffer before running doctor
    capsys.readouterr()

    # Step 2: Run doctor
    doctor_code = run_doctor(repo_path=throwaway_repo, json_mode=True)
    # doctor_code is 0 (pass) or 1 (warn, e.g. if guard is not installed globally on PATH or pytest-cov in target)
    assert doctor_code in (0, 1)

    captured = capsys.readouterr()
    doc_json = json.loads(captured.out)
    assert doc_json["status"] in ("pass", "warn")
