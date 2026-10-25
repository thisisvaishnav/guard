"""Session state tracking for Guard Loop Protection.

Maintains block counts per session in `.guard/state.json` to prevent
infinite agent stop-hook loops (capping consecutive blocks at 3).
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any
from guard_cli.events import get_guard_dir


def _state_file(repo_path: str | Path | None = None) -> Path:
    return get_guard_dir(repo_path) / "session_state.json"


def load_state(repo_path: str | Path | None = None) -> dict[str, Any]:
    """Loads current state dictionary from .guard/session_state.json."""
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
    try:
        sf = _state_file(repo_path)
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
    state = load_state(repo_path)
    sessions = state.setdefault("sessions", {})
    session_data = sessions.setdefault(session_id, {})
    session_data["last_passed_fingerprint"] = fingerprint
    session_data["fingerprint_passed_at"] = time.time()
    save_state(state, repo_path)


def clear_last_passed_fingerprint(session_id: str, repo_path: str | Path | None = None) -> None:
    """Clears cached passed fingerprint when a failure occurs."""
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
    state = load_state(repo_path)
    sessions = state.setdefault("sessions", {})
    session_data = sessions.setdefault(session_id, {})
    session_data["last_verified_sha"] = sha
    session_data["last_verified_at"] = time.time()
    save_state(state, repo_path)


def clear_last_verified_sha(session_id: str, repo_path: str | Path | None = None) -> None:
    """Clears the last verified SHA."""
    state = load_state(repo_path)
    sessions = state.setdefault("sessions", {})
    if session_id in sessions and "last_verified_sha" in sessions[session_id]:
        sessions[session_id].pop("last_verified_sha", None)
        save_state(state, repo_path)

