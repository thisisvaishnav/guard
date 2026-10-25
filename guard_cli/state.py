"""Session state tracking for Guard Loop Protection.

Maintains block counts per session in `.guard/state.json` to prevent
infinite agent stop-hook loops (capping consecutive blocks at 3).
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Generator

try:
    import fcntl
except ImportError:
    fcntl = None  # Fallback for non-POSIX platforms

from guard_cli.events import get_guard_dir

_thread_locks: dict[str, threading.RLock] = {}
_thread_locks_guard = threading.Lock()
_local_state = threading.local()


def _get_thread_lock(lock_key: str) -> threading.RLock:
    with _thread_locks_guard:
        if lock_key not in _thread_locks:
            _thread_locks[lock_key] = threading.RLock()
        return _thread_locks[lock_key]


def _state_file(repo_path: str | Path | None = None) -> Path:
    return get_guard_dir(repo_path) / "session_state.json"


def _lock_file(repo_path: str | Path | None = None) -> Path:
    return get_guard_dir(repo_path) / "session_state.lock"


@contextmanager
def _state_lock(
    repo_path: str | Path | None = None,
    shared: bool = False,
) -> Generator[None, None, None]:
    """Safe re-entrant file lock context manager for session state.

    Uses fcntl.flock on POSIX platforms and falls back gracefully if fcntl
    is unavailable or unsupported. Re-entrant within the same thread to
    prevent self-deadlocks on nested operations.
    """
    lf = _lock_file(repo_path)
    lock_key = str(lf.resolve())
    tlock = _get_thread_lock(lock_key)

    tlock.acquire()

    if not hasattr(_local_state, "depths"):
        _local_state.depths = {}
        _local_state.fds = {}
        _local_state.flocked = {}
        _local_state.modes = {}

    depth = _local_state.depths.get(lock_key, 0)
    _local_state.depths[lock_key] = depth + 1

    try:
        if depth == 0:
            fd = None
            flocked = False
            mode_str = "shared" if shared else "exclusive"
            try:
                lf.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(lf, os.O_CREAT | os.O_RDWR, 0o666)
                _local_state.fds[lock_key] = fd

                if fcntl is not None:
                    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
                    try:
                        fcntl.flock(fd, mode)
                        flocked = True
                    except (OSError, AttributeError):
                        pass
                _local_state.flocked[lock_key] = flocked
                _local_state.modes[lock_key] = mode_str
            except Exception:
                pass
        else:
            if not shared and _local_state.modes.get(lock_key) == "shared":
                fd = _local_state.fds.get(lock_key)
                if fd is not None and fcntl is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX)
                        _local_state.modes[lock_key] = "exclusive"
                    except (OSError, AttributeError):
                        pass

        yield

    finally:
        current_depth = _local_state.depths.get(lock_key, 1) - 1
        _local_state.depths[lock_key] = current_depth

        if current_depth <= 0:
            _local_state.depths.pop(lock_key, None)
            _local_state.modes.pop(lock_key, None)
            fd = _local_state.fds.pop(lock_key, None)
            was_flocked = _local_state.flocked.pop(lock_key, False)
            if fd is not None:
                if was_flocked and fcntl is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except Exception:
                        pass
                try:
                    os.close(fd)
                except Exception:
                    pass

        tlock.release()


def load_state(repo_path: str | Path | None = None) -> dict[str, Any]:
    """Loads current state dictionary from .guard/session_state.json."""
    with _state_lock(repo_path, shared=True):
        sf = _state_file(repo_path)
        if not sf.exists():
            return {"sessions": {}}
        try:
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"sessions": {}}
                data.setdefault("sessions", {})
                return data
        except Exception:
            return {"sessions": {}}


def save_state(state: dict[str, Any], repo_path: str | Path | None = None) -> None:
    """Saves state dictionary to .guard/session_state.json safely."""
    with _state_lock(repo_path, shared=False):
        try:
            sf = _state_file(repo_path)
            sf.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = sf.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            tmp_file.replace(sf)
        except Exception:
            pass


def get_session_blocks(session_id: str, repo_path: str | Path | None = None) -> int:
    """Returns the number of consecutive blocks for a session."""
    state = load_state(repo_path)
    session_data = state.get("sessions", {}).get(session_id, {})
    return int(session_data.get("consecutive_blocks", 0))


def record_session_block(session_id: str, repo_path: str | Path | None = None) -> int:
    """Increments and returns the consecutive block count for a session."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        sessions = state.setdefault("sessions", {})
        session_data = sessions.setdefault(session_id, {})
        
        current = int(session_data.get("consecutive_blocks", 0)) + 1
        session_data["consecutive_blocks"] = current
        session_data["last_blocked_at"] = time.time()
        
        save_state(state, repo_path)
        return current


def reset_session_blocks(session_id: str, repo_path: str | Path | None = None) -> None:
    """Resets consecutive blocks for a session back to 0."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        sessions = state.setdefault("sessions", {})
        session_data = sessions.setdefault(session_id, {})
        session_data["consecutive_blocks"] = 0
        session_data["last_passed_at"] = time.time()
        save_state(state, repo_path)


def get_last_passed_fingerprint(session_id: str, repo_path: str | Path | None = None) -> str | None:
    """Returns the working-tree fingerprint that last passed for this session."""
    state = load_state(repo_path)
    session_data = state.get("sessions", {}).get(session_id, {})
    return session_data.get("last_passed_fingerprint")


def set_last_passed_fingerprint(
    session_id: str,
    fingerprint: str,
    repo_path: str | Path | None = None,
) -> None:
    """Records working-tree fingerprint that passed tests for this session."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        sessions = state.setdefault("sessions", {})
        session_data = sessions.setdefault(session_id, {})
        session_data["last_passed_fingerprint"] = fingerprint
        session_data["fingerprint_passed_at"] = time.time()
        save_state(state, repo_path)


def clear_last_passed_fingerprint(session_id: str, repo_path: str | Path | None = None) -> None:
    """Clears cached passed fingerprint when a failure occurs."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        sessions = state.setdefault("sessions", {})
        if session_id in sessions and "last_passed_fingerprint" in sessions[session_id]:
            sessions[session_id].pop("last_passed_fingerprint", None)
            save_state(state, repo_path)


def get_baseline_sha(session_id: str, repo_path: str | Path | None = None) -> str | None:
    """Returns the recorded baseline SHA for the session."""
    state = load_state(repo_path)
    session_data = state.get("sessions", {}).get(session_id, {})
    return session_data.get("baseline_sha")


def set_baseline_sha(session_id: str, sha: str, repo_path: str | Path | None = None) -> None:
    """Records the initial baseline SHA for the session."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        sessions = state.setdefault("sessions", {})
        session_data = sessions.setdefault(session_id, {})
        session_data["baseline_sha"] = sha
        session_data["baseline_recorded_at"] = time.time()
        save_state(state, repo_path)


def get_repo_state(repo_path: str | Path | None = None) -> dict[str, Any]:
    """Returns repo-level state (shared across all agent sessions)."""
    state = load_state(repo_path)
    repo = state.get("repo", {})
    return repo if isinstance(repo, dict) else {}


def get_repo_baseline_sha(repo_path: str | Path | None = None) -> str | None:
    """Returns the repo-level baseline SHA recorded at first use / session start."""
    return get_repo_state(repo_path).get("baseline_sha")


def set_repo_baseline_sha(sha: str, repo_path: str | Path | None = None) -> None:
    """Records the repo-level baseline SHA (shared across sessions)."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        repo = state.setdefault("repo", {})
        repo["baseline_sha"] = sha
        repo["baseline_recorded_at"] = time.time()
        save_state(state, repo_path)


def get_repo_last_verified_sha(repo_path: str | Path | None = None) -> str | None:
    """Returns the repo-level SHA of the last commit whose tests passed.

    This is intentionally not scoped to a session: a fresh session ID must not
    be able to reset the baseline to a broken HEAD (commit bypass).
    """
    return get_repo_state(repo_path).get("last_verified_sha")


def set_repo_last_verified_sha(sha: str, repo_path: str | Path | None = None) -> None:
    """Records the repo-level SHA of the last commit whose tests passed."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        repo = state.setdefault("repo", {})
        repo["last_verified_sha"] = sha
        repo["last_verified_at"] = time.time()
        save_state(state, repo_path)


def get_ingest_sha(repo_path: str | Path | None = None) -> str | None:
    """Returns the HEAD SHA recorded at ingest time (.guard/state.json)."""
    try:
        base = Path(repo_path).resolve() if repo_path else Path.cwd()
        state_file = base / ".guard" / "state.json"
        if not state_file.exists():
            return None
        data = json.loads(state_file.read_text(encoding="utf-8"))
        sha = data.get("head_sha") if isinstance(data, dict) else None
        if sha and sha != "unknown":
            return sha
    except Exception:
        pass
    return None


def get_last_verified_sha(session_id: str, repo_path: str | Path | None = None) -> str | None:
    """Returns the most recent commit SHA where tests passed."""
    state = load_state(repo_path)
    session_data = state.get("sessions", {}).get(session_id, {})
    return session_data.get("last_verified_sha")


def set_last_verified_sha(session_id: str, sha: str, repo_path: str | Path | None = None) -> None:
    """Records the commit SHA where tests passed."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        sessions = state.setdefault("sessions", {})
        session_data = sessions.setdefault(session_id, {})
        session_data["last_verified_sha"] = sha
        session_data["last_verified_at"] = time.time()
        save_state(state, repo_path)


def clear_last_verified_sha(session_id: str, repo_path: str | Path | None = None) -> None:
    """Clears the last verified SHA."""
    with _state_lock(repo_path, shared=False):
        state = load_state(repo_path)
        sessions = state.setdefault("sessions", {})
        if session_id in sessions and "last_verified_sha" in sessions[session_id]:
            sessions[session_id].pop("last_verified_sha", None)
            save_state(state, repo_path)
