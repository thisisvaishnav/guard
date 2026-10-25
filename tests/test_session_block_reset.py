"""Tests for session block counting and reset functionality in guard_cli.state."""
from __future__ import annotations

import time
from pathlib import Path
import pytest

from guard_cli.state import (
    get_session_blocks,
    record_session_block,
    reset_session_blocks,
    load_state,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return repo


def test_session_block_initial_count(temp_repo: Path) -> None:
    """An untracked session should have 0 consecutive blocks."""
    assert get_session_blocks("unknown_session", repo_path=temp_repo) == 0


def test_record_session_block_increments(temp_repo: Path) -> None:
    """Each record_session_block call should increment consecutive blocks by 1."""
    sess_id = "test_increment_session"
    assert record_session_block(sess_id, repo_path=temp_repo) == 1
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 1

    assert record_session_block(sess_id, repo_path=temp_repo) == 2
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 2

    assert record_session_block(sess_id, repo_path=temp_repo) == 3
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 3

    # State file inspection
    state = load_state(temp_repo)
    session_data = state["sessions"][sess_id]
    assert session_data["consecutive_blocks"] == 3
    assert "last_blocked_at" in session_data


def test_reset_session_blocks(temp_repo: Path) -> None:
    """reset_session_blocks should set consecutive_blocks to 0 and record last_passed_at."""
    sess_id = "test_reset_session"
    record_session_block(sess_id, repo_path=temp_repo)
    record_session_block(sess_id, repo_path=temp_repo)
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 2

    before_reset = time.time()
    reset_session_blocks(sess_id, repo_path=temp_repo)
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 0

    state = load_state(temp_repo)
    session_data = state["sessions"][sess_id]
    assert session_data["consecutive_blocks"] == 0
    assert session_data["last_passed_at"] >= before_reset

    # Recording after reset should start at 1
    assert record_session_block(sess_id, repo_path=temp_repo) == 1
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 1


def test_reset_unknown_session(temp_repo: Path) -> None:
    """Resetting a session that hasn't been blocked before should initialize it with 0 blocks."""
    sess_id = "never_blocked_session"
    reset_session_blocks(sess_id, repo_path=temp_repo)
    assert get_session_blocks(sess_id, repo_path=temp_repo) == 0
    state = load_state(temp_repo)
    assert sess_id in state["sessions"]
    assert state["sessions"][sess_id]["consecutive_blocks"] == 0


def test_multi_session_block_isolation(temp_repo: Path) -> None:
    """Resetting one session must not alter block counts of other sessions."""
    s1 = "sess_1"
    s2 = "sess_2"
    record_session_block(s1, repo_path=temp_repo)
    record_session_block(s1, repo_path=temp_repo)
    record_session_block(s2, repo_path=temp_repo)

    assert get_session_blocks(s1, repo_path=temp_repo) == 2
    assert get_session_blocks(s2, repo_path=temp_repo) == 1

    reset_session_blocks(s1, repo_path=temp_repo)
    assert get_session_blocks(s1, repo_path=temp_repo) == 0
    assert get_session_blocks(s2, repo_path=temp_repo) == 1
