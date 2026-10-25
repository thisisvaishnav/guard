"""Tests for Loop Guard handback and session block reset.

Guarantees:
1. Turn 4 fix is properly tested (api.run executed) rather than accepted untested.
2. If turn 4 tests pass, stop is allowed without handing back as blocked.
3. If turn 4 tests fail after 3 prior blocks, Guard hands back to user and resets session blocks.
4. Subsequent turns (turn 5+) in that session are not permanently bypassed.
"""
import io
import json
from unittest.mock import patch, MagicMock
import pytest

from guard_cli.hook import run_stop_hook
from guard_cli.state import (
    get_session_blocks,
    record_session_block,
    reset_session_blocks,
)


@pytest.fixture
def temp_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def test_turn4_fix_is_tested_and_accepted_on_pass(temp_repo):
    """When an agent fixes the issue on turn 4 after 3 prior blocks,

    tests must run and pass, rather than being bypassed before testing.
    """
    sess_id = "test_sess_turn4_pass"
    # Agent was blocked on turns 1, 2, and 3
    record_session_block(sess_id, repo_path=temp_repo)
    record_session_block(sess_id, repo_path=temp_repo)
    record_session_block(sess_id, repo_path=temp_repo)
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 3

    pass_report = {
        "policy": "subset",
        "trust": 1.0,
        "failures": [],
        "tests_run_count": 5,
    }

    mock_run = MagicMock(return_value=(pass_report, 0))

    with patch("guard_cli.hook.check_idle_turn", return_value=(False, "modified", "fp", "sha")), \
         patch("guard_cli.api.run", mock_run):
        
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            code = run_stop_hook(
                repo_override=temp_repo,
                raw_input={"session_id": sess_id, "cwd": str(temp_repo)},
            )

    # api.run MUST have been called to verify turn 4
    assert mock_run.called, "api.run was not called on turn 4; fix was accepted untested!"
    assert code == 0
    # Should not say it was handed back due to 3 blocks because tests passed!
    assert "Guard blocked 3 times, handing back to you" not in stderr_capture.getvalue()
    # Consecutive blocks should be reset
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 0


def test_turn4_failure_hands_back_and_resets_session_blocks(temp_repo):
    """After 3 prior blocks, if turn 4 also fails, Guard hands back to user

    and resets session blocks so subsequent turns are not permanently bypassed.
    """
    sess_id = "test_sess_handback_reset"
    # Pre-record 3 blocks
    record_session_block(sess_id, repo_path=temp_repo)
    record_session_block(sess_id, repo_path=temp_repo)
    record_session_block(sess_id, repo_path=temp_repo)
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 3

    fail_report = {
        "policy": "subset",
        "trust": 0.9,
        "failures": ["tests/test_x.py::test_fail"],
        "tests_run_count": 1,
    }
    mock_run = MagicMock(return_value=(fail_report, 1))

    # Turn 4: failure should run tests, then hand back
    with patch("guard_cli.hook.check_idle_turn", return_value=(False, "modified", "fp", "sha")), \
         patch("guard_cli.api.run", mock_run):
        
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            code4 = run_stop_hook(
                repo_override=temp_repo,
                raw_input={"session_id": sess_id, "cwd": str(temp_repo)},
            )

    assert mock_run.called, "api.run was not called on turn 4 before handing back!"
    assert code4 == 0
    assert "Guard blocked 3 times, handing back to you" in stderr_capture.getvalue()
    # Session blocks MUST be reset on handback
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 0

    # Turn 5: New turn in same session with another failure must NOT be bypassed
    mock_run.reset_mock()
    with patch("guard_cli.hook.check_idle_turn", return_value=(False, "modified", "fp", "sha")), \
         patch("guard_cli.api.run", mock_run):
        
        stderr_capture5 = io.StringIO()
        with patch("sys.stderr", stderr_capture5):
            code5 = run_stop_hook(
                repo_override=temp_repo,
                raw_input={"session_id": sess_id, "cwd": str(temp_repo)},
            )

    assert mock_run.called, "api.run was not called on turn 5; Guard was permanently bypassed!"
    # Turn 5 should be blocked (exit 2 for Claude Code)
    assert code5 == 2
    assert "GUARD SAFETY CHECK FAILED" in stderr_capture5.getvalue()
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 1
