"""Tests for configuration file modification bypass fix and untracked test file detection.

Scenario A:
Modifying configuration files (pyproject.toml, requirements.txt, setup.cfg, .env, etc.)
must NOT bypass checks as 'non_python_only'. They must require test verification.

Scenario B:
Untracked test files (e.g. tests/test_new_feature.py) must be detected as test files touched,
triggering fallback to run-all and the 'test_file_touched' override.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from guard_cli import api
from guard_cli.hook import check_idle_turn, run_stop_hook
from guard_cli.thin_slice import guard_check


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True
    )


@pytest.fixture
def test_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@guard.dev")
    _git(repo, "config", "user.name", "Guard Test")

    (repo / ".gitignore").write_text(".guard/\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (repo / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (repo / "setup.cfg").write_text("[metadata]\nname = demo\n", encoding="utf-8")
    (repo / ".env").write_text("ENV=dev\n", encoding="utf-8")
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")

    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text("def hello():\n    return 'hello'\n", encoding="utf-8")

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_app.py").write_text(
        "from pkg.app import hello\n\ndef test_hello():\n    assert hello() == 'hello'\n",
        encoding="utf-8",
    )

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, head_sha


# ==============================================================================
# Scenario A: Configuration file bypass prevention
# ==============================================================================


@pytest.mark.parametrize(
    "config_filename",
    [
        "pyproject.toml",
        "requirements.txt",
        "setup.cfg",
        ".env",
        "tox.ini",
        "Pipfile",
    ],
)
def test_config_file_modification_requires_verification(
    test_repo: tuple[Path, str], config_filename: str
) -> None:
    """Modifying configuration files must not bypass safety checks as non_python_only."""
    repo, _ = test_repo
    target_file = repo / config_filename
    target_file.write_text("# modified configuration\n", encoding="utf-8")

    is_idle, reason, fingerprint, _ = check_idle_turn(repo, session_id="test_sess")
    assert is_idle is False
    assert reason != "non_python_only"
    assert fingerprint is not None


def test_non_code_documentation_file_still_bypasses(
    test_repo: tuple[Path, str],
) -> None:
    """Modifying only documentation or non-code files should still bypass as non_python_only."""
    repo, _ = test_repo
    readme = repo / "README.md"
    readme.write_text("# Updated Documentation\n", encoding="utf-8")

    is_idle, reason, _, _ = check_idle_turn(repo, session_id="test_sess")
    assert is_idle is True
    assert reason == "non_python_only"


def test_run_stop_hook_does_not_bypass_when_config_modified(
    test_repo: tuple[Path, str],
) -> None:
    """Stop hook must not skip tests when pyproject.toml is modified."""
    repo, _ = test_repo
    (repo / "pyproject.toml").write_text(
        "[project]\nname = 'modified'\n", encoding="utf-8"
    )

    mock_report = {
        "status": "passed",
        "policy": "subset",
        "trust": 0.9,
        "failures": [],
        "tests_run_count": 1,
        "output_summary": "1 passed",
    }
    with patch("guard_cli.api.run", return_value=(mock_report, 0)) as mock_run:
        exit_code = run_stop_hook(
            repo_override=repo,
            raw_input={"session_id": "test_config_sess", "cwd": str(repo)},
        )
        assert exit_code == 0
        assert mock_run.called, "api.run should be called for config file modifications"


# ==============================================================================
# Scenario B: Untracked test file detection
# ==============================================================================


def test_untracked_test_file_detected_in_guard_check(
    test_repo: tuple[Path, str],
) -> None:
    """A brand new untracked test file must trigger test_files_touched fallback."""
    repo, _ = test_repo
    new_test = repo / "tests" / "test_new_feature.py"
    new_test.write_text("def test_feature(): assert True\n", encoding="utf-8")

    # The file is untracked (not added to git)
    status_proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert "?? tests/test_new_feature.py" in status_proc.stdout

    res = guard_check(repo_path=repo)
    assert res.is_fallback is True
    assert res.status == "run-all"
    assert res.fallback_reason == "Test files were modified in diff"


def test_untracked_test_file_with_tracked_code_change(
    test_repo: tuple[Path, str],
) -> None:
    """When both code changes and an untracked test exist, it must trigger test_files_touched."""
    repo, _ = test_repo
    app_file = repo / "pkg" / "app.py"
    app_file.write_text(
        "def hello():\n    return 'world'\n", encoding="utf-8"
    )

    new_test = repo / "tests" / "test_untracked.py"
    new_test.write_text("def test_untracked(): assert True\n", encoding="utf-8")

    res = guard_check(repo_path=repo)
    assert res.is_fallback is True
    assert res.status == "run-all"
    assert res.fallback_reason == "Test files were modified in diff"


def test_untracked_test_file_triggers_override_in_api_check(
    test_repo: tuple[Path, str],
) -> None:
    """Untracked test file must trigger 'test_file_touched' in api.check overrides_triggered."""
    repo, _ = test_repo
    new_test = repo / "tests" / "test_new_feature.py"
    new_test.write_text("def test_new(): pass\n", encoding="utf-8")

    check_res = api.check(repo_path=repo)
    assert check_res["is_fallback"] is True
    assert "test_file_touched" in check_res["overrides_triggered"]


def test_untracked_non_test_file_does_not_trigger_test_files_touched(
    test_repo: tuple[Path, str],
) -> None:
    """Untracked non-test files should not be flagged as test files touched."""
    repo, _ = test_repo
    untracked_data = repo / "data.csv"
    untracked_data.write_text("a,b,c\n", encoding="utf-8")

    res = guard_check(repo_path=repo)
    assert res.fallback_reason != "Test files were modified in diff"
