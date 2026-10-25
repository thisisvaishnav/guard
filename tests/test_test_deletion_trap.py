"""Tests for test deletion trap handling.

Verifies:
- When selected_tests contains a test target for a deleted or renamed file,
  api.run() prunes the non-existent test target before invoking pytest.
- When all selected tests are deleted, Guard falls back to running available tests in tests/.
- When all selected tests are deleted and no tests remain in repo, Guard allows stop cleanly (exit 0)
  and logs an informational event.
- Stop hook does not trap the agent with Exit 2 ("Fix the source code. Do not edit, skip, or delete tests")
  when test files were deleted.
"""
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from guard_cli import api
from guard_cli.events import read_events
from guard_cli.hook import run_stop_hook, format_failure_summary


@pytest.fixture
def temp_repo(tmp_path):
    """Creates a temporary repository root for test isolation."""
    repo = tmp_path / "repo"
    repo.mkdir()
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    return repo


def test_prunes_deleted_test_target_and_runs_remaining(temp_repo):
    """When some test targets do not exist on disk, api.run() prunes them and runs valid targets."""
    # Create an existing test file
    alive_test = temp_repo / "tests" / "test_alive.py"
    alive_test.write_text("def test_ok(): assert True\n", encoding="utf-8")

    mock_check = {
        "version": "1.0",
        "status": "select",
        "policy": "subset",
        "trust": 0.9,
        "selected_tests": [
            "tests/test_deleted.py::test_fn",
            "tests/test_alive.py::test_ok",
        ],
        "is_fallback": False,
        "overrides_triggered": [],
        "reasons": {},
    }

    with patch("guard_cli.api.check", return_value=mock_check):
        report, exit_code = api.run(repo_path=temp_repo)

    assert exit_code == 0
    assert report["tests_passed"] is True
    assert "tests/test_alive.py::test_ok" in report["tests_run"]
    assert not any("test_deleted.py" in t for t in report["tests_run"])

    events = read_events(repo_path=temp_repo)
    prune_events = [e for e in events if "prun" in e.get("event", "").lower()]
    assert len(prune_events) > 0


def test_all_selected_tests_deleted_falls_back_to_available_tests(temp_repo):
    """When all selected tests were deleted, fall back cleanly to running available tests in tests/."""
    # Another test file exists in tests/
    other_test = temp_repo / "tests" / "test_other.py"
    other_test.write_text("def test_other(): assert True\n", encoding="utf-8")

    mock_check = {
        "version": "1.0",
        "status": "select",
        "policy": "subset",
        "trust": 0.9,
        "selected_tests": [
            "tests/test_deleted.py::test_fn",
        ],
        "is_fallback": False,
        "overrides_triggered": [],
        "reasons": {},
    }

    with patch("guard_cli.api.check", return_value=mock_check):
        report, exit_code = api.run(repo_path=temp_repo)

    assert exit_code == 0
    assert report["tests_passed"] is True
    assert "tests" in report["tests_run"]

    events = read_events(repo_path=temp_repo)
    prune_events = [e for e in events if "prun" in e.get("event", "").lower()]
    assert len(prune_events) > 0


def test_all_selected_tests_deleted_no_tests_remain_allows_stop(temp_repo):
    """When all targeted tests were deleted/missing and no tests remain, allow stop cleanly with exit 0."""
    # Empty tests dir (no test_*.py files)
    mock_check = {
        "version": "1.0",
        "status": "select",
        "policy": "subset",
        "trust": 0.9,
        "selected_tests": [
            "tests/test_deleted.py::test_fn",
        ],
        "is_fallback": False,
        "overrides_triggered": [],
        "reasons": {},
    }

    with patch("guard_cli.api.check", return_value=mock_check):
        report, exit_code = api.run(repo_path=temp_repo)

    assert exit_code == 0
    assert report["tests_passed"] is True
    assert report["tests_run_count"] == 0

    events = read_events(repo_path=temp_repo)
    prune_events = [e for e in events if "prun" in e.get("event", "").lower() or "no_tests" in e.get("event", "").lower()]
    assert len(prune_events) > 0


def test_stop_hook_does_not_trap_agent_on_deleted_test(temp_repo):
    """Stop hook does not block the agent with Exit 2 when a test file was deleted."""
    mock_check = {
        "version": "1.0",
        "status": "select",
        "policy": "subset",
        "trust": 0.9,
        "selected_tests": [
            "tests/test_deleted.py::test_fn",
        ],
        "is_fallback": False,
        "overrides_triggered": [],
        "reasons": {},
    }

    with patch("guard_cli.hook.is_working_tree_clean", return_value=False), \
         patch("guard_cli.api.check", return_value=mock_check):
        exit_code = run_stop_hook(
            repo_override=temp_repo,
            raw_input={"session_id": "test_deletion_session", "cwd": str(temp_repo)},
        )

    # Must allow stop (0) instead of blocking with exit 2
    assert exit_code == 0


def test_format_failure_summary_handles_deleted_test_collection_error():
    """Verify format_failure_summary does not instruct agent to not delete tests when error is file not found."""
    report = {
        "policy": "subset",
        "trust": 0.0,
        "tests_run_count": 0,
        "failures": ["tests/test_deleted.py"],
        "output_summary": "ERROR: file or directory not found: tests/test_deleted.py",
    }
    summary = format_failure_summary(report, max_lines=30)
    assert "Do not edit, skip, or delete tests" not in summary
    assert "not found" in summary.lower() or "deleted" in summary.lower()
