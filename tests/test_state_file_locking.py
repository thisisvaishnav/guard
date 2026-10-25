"""Tests for file locking and concurrency control in guard_cli.state.

Guarantees:
1. `_state_lock` provides a safe context manager using fcntl.flock on POSIX platforms.
2. Graceful fallback on non-POSIX platforms where fcntl is unavailable.
3. Lock is re-entrant within the same process/thread to prevent self-deadlocks.
4. Concurrent read-modify-write operations (record_session_block) avoid lost updates.
5. Concurrent writes and reads do not cause partial writes, race overwrites, or JSON corruption.
"""
from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from guard_cli.state import (
    _state_file,
    _state_lock,
    get_session_blocks,
    load_state,
    record_session_block,
    reset_session_blocks,
    save_state,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return repo


def test_state_lock_basic_acquisition(temp_repo: Path) -> None:
    """Verify that _state_lock acquires and releases without error in both shared and exclusive modes."""
    with _state_lock(temp_repo, shared=False):
        save_state({"sessions": {"s1": {"consecutive_blocks": 1}}}, temp_repo)

    with _state_lock(temp_repo, shared=True):
        state = load_state(temp_repo)
        assert state.get("sessions", {}).get("s1", {}).get("consecutive_blocks") == 1


def test_state_lock_reentrancy(temp_repo: Path) -> None:
    """Verify that _state_lock is re-entrant within the same thread to prevent self-deadlock."""
    # Nesting exclusive and shared locks should not block or raise
    with _state_lock(temp_repo, shared=False):
        with _state_lock(temp_repo, shared=True):
            with _state_lock(temp_repo, shared=False):
                save_state({"test": 123}, temp_repo)
        state = load_state(temp_repo)
        assert state.get("test") == 123


def test_state_lock_fallback_when_fcntl_missing(temp_repo: Path) -> None:
    """Verify that _state_lock falls back gracefully when fcntl is not available (non-POSIX)."""
    with patch("guard_cli.state.fcntl", None):
        with _state_lock(temp_repo, shared=False):
            save_state({"fallback": True}, temp_repo)
        
        with _state_lock(temp_repo, shared=True):
            state = load_state(temp_repo)
            assert state.get("fallback") is True


def test_state_lock_fallback_when_flock_fails(temp_repo: Path) -> None:
    """Verify that _state_lock falls back gracefully if fcntl.flock raises OSError."""
    with patch("fcntl.flock", side_effect=OSError("Operation not supported")):
        with _state_lock(temp_repo, shared=False):
            save_state({"fallback_os_error": True}, temp_repo)
        state = load_state(temp_repo)
        assert state.get("fallback_os_error") is True


def _concurrent_block_worker(repo_path_str: str, session_id: str, count: int) -> int:
    """Worker function for concurrent multi-process testing."""
    repo_path = Path(repo_path_str)
    for _ in range(count):
        record_session_block(session_id, repo_path=repo_path)
    return get_session_blocks(session_id, repo_path=repo_path)


def test_concurrent_record_session_block_multiprocess(temp_repo: Path) -> None:
    """Simulate multiple processes concurrently updating session blocks.

    Without robust file locking, concurrent read-modify-write calls to
    record_session_block cause lost updates. With flock, all increments must be preserved.
    """
    session_id = "concurrent_proc_test"
    workers = 4
    increments_per_worker = 10
    total_expected = workers * increments_per_worker

    repo_str = str(temp_repo)
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_concurrent_block_worker, repo_str, session_id, increments_per_worker)
            for _ in range(workers)
        ]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    final_blocks = get_session_blocks(session_id, repo_path=temp_repo)
    assert final_blocks == total_expected, (
        f"Expected {total_expected} blocks after concurrent increments, but got {final_blocks} (lost updates)"
    )


def _concurrent_multi_session_worker(repo_path_str: str, worker_id: int) -> None:
    repo_path = Path(repo_path_str)
    sess_id = f"session_{worker_id}"
    record_session_block(sess_id, repo_path=repo_path)


def test_concurrent_multi_session_isolation(temp_repo: Path) -> None:
    """Simulate different processes recording blocks for different sessions.

    All sessions must be preserved in state without race overwrites destroying sessions.
    """
    workers = 8
    repo_str = str(temp_repo)
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_concurrent_multi_session_worker, repo_str, i)
            for i in range(workers)
        ]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    state = load_state(temp_repo)
    sessions = state.get("sessions", {})
    assert len(sessions) == workers, f"Expected {workers} sessions preserved, found {len(sessions)}"
    for i in range(workers):
        assert f"session_{i}" in sessions
        assert sessions[f"session_{i}"]["consecutive_blocks"] == 1


def test_concurrent_read_write_integrity(temp_repo: Path) -> None:
    """Verify that rapid concurrent load_state and save_state calls never corrupt JSON or throw decode errors."""
    stop_flag = False
    errors: list[Exception] = []

    def writer():
        i = 0
        while not stop_flag:
            save_state({"counter": i, "timestamp": time.time(), "payload": [x for x in range(50)]}, temp_repo)
            i += 1
            time.sleep(0.001)

    def reader():
        while not stop_flag:
            try:
                st = load_state(temp_repo)
                assert isinstance(st, dict)
            except Exception as e:
                errors.append(e)
            time.sleep(0.001)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        writer_futures = [executor.submit(writer) for _ in range(2)]
        reader_futures = [executor.submit(reader) for _ in range(4)]
        time.sleep(0.5)
        stop_flag = True
        for f in writer_futures + reader_futures:
            f.result()

    assert not errors, f"Read/write concurrency errors encountered: {errors}"
