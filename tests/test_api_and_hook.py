"""Automated test suite for Phase 0 (Contract & API) and Phase 1 (Claude Code Hook).

Verifies:
- Schema versioning (version="1.0", policy, trust, overrides_triggered, selected_tests, failures, reasons)
- Fail-open default behavior vs strict mode
- Event logging in .guard/events.jsonl
- Session state tracking & 3-block loop guard
- Claude Code Stop hook adapter (exit 0 on clean tree, exit 2 on failure, stderr <= 30 lines)
- Claude Code settings writer (merge, preserve, idempotence, uninstall)
"""
import io
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from guard_cli import api, db
from guard_cli.events import log_event, read_events
from guard_cli.ingest.static import StaticResult, FuncDef
from guard_cli.state import (
    get_session_blocks,
    record_session_block,
    reset_session_blocks,
    load_state,
)
from guard_cli.hook import (
    run_stop_hook,
    format_failure_summary,
    is_working_tree_clean,
)
from guard_cli.integrations import claude


@pytest.fixture
def temp_repo(tmp_path):
    """Creates a temporary repository root for test isolation."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


# --- Phase 0: Schema and API Tests -------------------------------------------

_SAMPLE_DIFF = """--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,3 +1,3 @@
 def calc():
-    return 1
+    return 2
"""


@pytest.fixture
def seeded_guard_graph():
    """Seeds a dedicated graph so check() exercises the 'select' path without
    depending on an externally pre-populated 'guard' graph (which may lack
    COVERED_BY evidence and silently fall back to run-all)."""
    backend = db.get_backend()
    if not backend.is_healthy():
        pytest.skip("FalkorDB server is not reachable")
    try:
        g = db.get_graph("guard_api_check_test", backend=backend)
        db.reset_graph(g)
        g = db.get_graph("guard_api_check_test", backend=backend)
        db.ensure_schema(g)
    except Exception as exc:
        pytest.skip(f"FalkorDB server error: {exc}")
    db.write_static(
        g,
        StaticResult(
            files=["pkg/mod.py", "tests/test_mod.py"],
            funcs=[
                FuncDef(id="pkg/mod.py::calc", file="pkg/mod.py", qualname="calc", name="calc", start=1, end=10, cls=None),
                FuncDef(id="tests/test_mod.py::test_calc", file="tests/test_mod.py", qualname="test_calc", name="test_calc", start=1, end=5, cls=None),
            ],
        ),
    )
    db.write_coverage(g, {"tests/test_mod.py::test_calc": ["pkg/mod.py::calc"]}, confidence=0.9)
    yield g
    try:
        db.reset_graph(g)
    except Exception:
        pass


def test_api_check_schema_version_and_keys(temp_repo, seeded_guard_graph):
    """Verify check() produces the version 1.0 schema with all required keys."""
    res = api.check(diff_text=_SAMPLE_DIFF, repo_path=temp_repo, graph_name="guard_api_check_test")
    assert res["version"] == "1.0"
    assert "policy" in res
    assert "trust" in res
    assert "overrides_triggered" in res
    assert "selected_tests" in res
    assert "failures" in res
    assert "reasons" in res
    assert res["status"] == "select"
    assert res["is_fallback"] is False
    assert len(res["selected_tests"]) > 0
    assert isinstance(res["reasons"], dict)


def test_api_check_fail_open_by_default(temp_repo):
    """When graph/database fails, check() fails open instead of throwing."""
    with patch("guard_cli.api.guard_check", side_effect=ConnectionError("FalkorDB unreachable")):
        res = api.check(repo_path=temp_repo, strict=False)
        assert res["version"] == "1.0"
        assert res["policy"] == "fail_open"
        assert res["fail_open"] is True
        assert res["status"] == "run-all"
        assert "fail_open_error" in res["overrides_triggered"]


def test_api_check_strict_mode_raises(temp_repo):
    """When strict=True, exceptions are re-raised."""
    with patch("guard_cli.api.guard_check", side_effect=ConnectionError("FalkorDB unreachable")):
        with pytest.raises(ConnectionError):
            api.check(repo_path=temp_repo, strict=True)


def test_api_run_fail_open_returns_exit_code_zero(temp_repo):
    """When check/database fails in run(), fail-open yields exit code 0."""
    with patch("guard_cli.api.check", side_effect=Exception("Database down")):
        report, code = api.run(repo_path=temp_repo, strict=False)
        assert code == 0
        assert report["fail_open"] is True
        assert report["tests_passed"] is True


def test_api_run_fail_open_check_skips_full_suite(temp_repo):
    """When check() itself fails open (database down), run() must not attempt the
    full-suite fallback; it allows the stop with a loud warning and logs a
    fail_open event (not blocked with policy fail_open)."""
    fail_open_check = {
        "version": "1.0",
        "status": "run-all",
        "policy": "fail_open",
        "trust": 0.0,
        "overrides_triggered": ["fail_open_error"],
        "selected_tests": ["tests"],
        "failures": [],
        "reasons": {"error": "Guard check error: FalkorDB unreachable"},
        "is_fallback": True,
        "fallback_reason": "Guard database/internal error: FalkorDB unreachable",
        "fail_open": True,
        "error": "FalkorDB unreachable",
    }

    stderr_capture = io.StringIO()
    with patch("guard_cli.api.check", return_value=fail_open_check), \
         patch("subprocess.run") as mock_proc, \
         patch("sys.stderr", stderr_capture):
        report, code = api.run(repo_path=temp_repo, strict=False, session_id="sess_failopen")

    assert code == 0
    assert report["fail_open"] is True
    assert report["tests_passed"] is True
    assert report["policy"] == "fail_open"
    assert report["tests_run_count"] == 0
    # The full suite must never be executed on a fail-open check.
    mock_proc.assert_not_called()
    assert "fail-open" in stderr_capture.getvalue()

    events = read_events(repo_path=temp_repo)
    assert events[-1]["event"] == "fail_open"
    assert not any(e["event"] == "blocked" for e in events)


def test_event_logging(temp_repo):
    """Verify log_event appends JSONL entries to .guard/events.jsonl."""
    log_event("hook_fired", session_id="sess_123", repo_path=temp_repo, details={"arg": 1})
    log_event("blocked", session_id="sess_123", repo_path=temp_repo, details={"reason": "test_failed"})
    log_event("passed", session_id="sess_123", repo_path=temp_repo)

    events = read_events(repo_path=temp_repo)
    assert len(events) == 3
    assert events[0]["event"] == "hook_fired"
    assert events[0]["session_id"] == "sess_123"
    assert events[0]["details"]["arg"] == 1
    assert events[1]["event"] == "blocked"
    assert events[2]["event"] == "passed"


def test_session_state_and_loop_guard(temp_repo):
    """Verify session consecutive blocks tracking in .guard/session_state.json without state.json collision."""
    assert get_session_blocks("sess_abc", repo_path=temp_repo) == 0
    
    count1 = record_session_block("sess_abc", repo_path=temp_repo)
    assert count1 == 1
    assert get_session_blocks("sess_abc", repo_path=temp_repo) == 1
    
    count2 = record_session_block("sess_abc", repo_path=temp_repo)
    assert count2 == 2
    
    reset_session_blocks("sess_abc", repo_path=temp_repo)
    assert get_session_blocks("sess_abc", repo_path=temp_repo) == 0

    # Verify session_state.json exists
    assert (temp_repo / ".guard" / "session_state.json").exists()

    # Verify repo state.json is not overwritten by session operations
    repo_state = temp_repo / ".guard" / "state.json"
    repo_state.write_text(json.dumps({"head_sha": "testsha123"}), encoding="utf-8")
    record_session_block("sess_abc", repo_path=temp_repo)
    assert json.loads(repo_state.read_text(encoding="utf-8")) == {"head_sha": "testsha123"}


# --- Phase 1: Claude Code Hook Adapter Tests ---------------------------------

def test_stop_hook_clean_working_tree_exits_zero(temp_repo):
    """Clean git working tree should exit 0 immediately (idle turn)."""
    with patch("guard_cli.hook.is_working_tree_clean", return_value=True):
        code = run_stop_hook(
            repo_override=temp_repo,
            raw_input={"session_id": "sess_1", "cwd": str(temp_repo)},
        )
        assert code == 0


def test_stop_hook_non_python_change_skips_run(temp_repo):
    """Changes to non-python files (e.g. README.md) should be treated as idle turns and exit 0."""
    with patch("subprocess.run") as mock_proc, \
         patch("guard_cli.api.run") as mock_run:
        mock_proc.return_value.returncode = 0
        mock_proc.return_value.stdout = " M README.md\n?? notes.txt\n"
        code = run_stop_hook(
            repo_override=temp_repo,
            raw_input={"session_id": "sess_1", "cwd": str(temp_repo)},
        )
        assert code == 0
        mock_run.assert_not_called()


def test_stop_hook_fingerprint_cache_hit_skips_run(temp_repo):
    """Subsequent stop hook invocations on identical tree after tests passed should skip run."""
    from guard_cli.state import set_last_passed_fingerprint
    fp = "abc1234567890123"
    set_last_passed_fingerprint("sess_1", fp, repo_path=temp_repo)

    def fake_subprocess_run(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        if "rev-parse" in cmd:
            res.stdout = "abc1234"
        elif "--porcelain" in cmd:
            res.stdout = " M calc.py\n"
        return res

    with patch("subprocess.run", side_effect=fake_subprocess_run), \
         patch("guard_cli.hook.compute_turn_fingerprint", return_value=fp), \
         patch("guard_cli.api.run") as mock_run:
        code = run_stop_hook(
            repo_override=temp_repo,
            raw_input={"session_id": "sess_1", "cwd": str(temp_repo)},
        )
        assert code == 0
        mock_run.assert_not_called()


def test_stop_hook_fails_with_exit_2_and_stderr(temp_repo):
    """Test failure causes exit code 2 and outputs concise <= 30 line summary to stderr."""
    mock_report = {
        "policy": "subset",
        "trust": 0.9,
        "overrides_triggered": [],
        "fallback_reason": None,
        "tests_run_count": 5,
        "failures": ["tests/test_mod.py::test_failing_case"],
        "output_summary": "1 failed, 4 passed in 0.12s",
    }
    
    with patch("guard_cli.hook.is_working_tree_clean", return_value=False), \
         patch("guard_cli.api.run", return_value=(mock_report, 1)):
        
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            code = run_stop_hook(
                repo_override=temp_repo,
                raw_input={"session_id": "sess_fail", "cwd": str(temp_repo)},
            )
            
        assert code == 2
        err_output = stderr_capture.getvalue()
        assert "GUARD SAFETY CHECK FAILED (Exit 2 - Blocking Stop)" in err_output
        assert "test_failing_case" in err_output
        lines = err_output.strip().splitlines()
        assert len(lines) <= 30
        assert get_session_blocks("sess_fail", repo_path=temp_repo) == 1


def test_stop_hook_loop_guard_caps_at_3_blocks(temp_repo):
    """After 3 consecutive blocks, hook hands back to user and exits 0."""
    # Pre-record 3 blocks (agent gets 3 blocks, then handback on 4th attempt)
    record_session_block("sess_loop", repo_path=temp_repo)
    record_session_block("sess_loop", repo_path=temp_repo)
    record_session_block("sess_loop", repo_path=temp_repo)
    assert get_session_blocks("sess_loop", repo_path=temp_repo) == 3

    mock_report = {
        "policy": "subset",
        "trust": 0.9,
        "failures": ["tests/test_x.py::test_bad"],
        "tests_run_count": 1,
    }

    with patch("guard_cli.hook.is_working_tree_clean", return_value=False), \
         patch("guard_cli.api.run", return_value=(mock_report, 1)):
        
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            # This is the 3rd block: must hand back and exit 0
            code = run_stop_hook(
                repo_override=temp_repo,
                raw_input={"session_id": "sess_loop", "cwd": str(temp_repo)},
            )
            
        assert code == 0
        assert "Guard blocked 3 times, handing back to you" in stderr_capture.getvalue()


def test_stop_hook_fail_open_on_exception(temp_repo):
    """If hook execution throws an unexpected error, it fails open (exit 0)."""
    with patch("guard_cli.hook.is_working_tree_clean", return_value=False), \
         patch("guard_cli.api.run", side_effect=RuntimeError("Unexpected crash")):
        
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            code = run_stop_hook(
                repo_override=temp_repo,
                strict=False,
                raw_input={"session_id": "sess_crash", "cwd": str(temp_repo)},
            )
            
        assert code == 0
        assert "Warning: Guard encountered an error" in stderr_capture.getvalue()


# --- Phase 1: Claude Code Settings Writer Tests ------------------------------

def test_claude_settings_install_creates_file_and_hook(temp_repo):
    """Installer writes to .claude/settings.local.json with proper structure."""
    ok, msg = claude.install(repo_path=temp_repo, shared=False)
    assert ok is True
    
    settings_file = temp_repo / ".claude" / "settings.local.json"
    assert settings_file.exists()
    
    with open(settings_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "hooks" in data
    assert "Stop" in data["hooks"]
    guard_exe = claude.get_guard_executable()
    assert any(
        h.get("matcher") == ""
        and any(
            sub.get("command") == f"{guard_exe} hook stop" and sub.get("type") == "command"
            for sub in h.get("hooks", [])
        )
        for h in data["hooks"]["Stop"]
    )

    stat = claude.status(repo_path=temp_repo, shared=False)
    assert stat["installed"] is True


def test_claude_settings_merge_preserves_existing_config(temp_repo):
    """Installer merges into existing hooks without clobbering other settings."""
    settings_file = temp_repo / ".claude" / "settings.local.json"
    settings_file.parent.mkdir(parents=True)
    
    initial_data = {
        "user_pref": "dark_mode",
        "hooks": {
            "Stop": [
                {"command": "echo 'custom pre-stop'"}
            ],
            "Start": [
                {"command": "echo 'start'"}
            ]
        }
    }
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)
        
    ok, msg = claude.install(repo_path=temp_repo, shared=False)
    assert ok is True
    
    with open(settings_file, "r", encoding="utf-8") as f:
        merged = json.load(f)
        
    assert merged["user_pref"] == "dark_mode"
    assert len(merged["hooks"]["Start"]) == 1
    assert len(merged["hooks"]["Stop"]) == 2
    assert merged["hooks"]["Stop"][0]["command"] == "echo 'custom pre-stop'"
    guard_entry = merged["hooks"]["Stop"][1]
    assert guard_entry.get("matcher") == ""
    guard_exe = claude.get_guard_executable()
    assert guard_entry["hooks"][0]["command"] == f"{guard_exe} hook stop"
    
    # Backup file should exist
    bak_file = temp_repo / ".claude" / "settings.local.json.bak"
    assert bak_file.exists()


def test_claude_settings_uninstall_only_removes_guard(temp_repo):
    """Uninstaller removes only guard hook stop and leaves custom hooks intact."""
    settings_file = temp_repo / ".claude" / "settings.local.json"
    settings_file.parent.mkdir(parents=True)
    
    initial_data = {
        "hooks": {
            "Stop": [
                {"command": "echo 'custom pre-stop'"},
                {"command": "guard hook stop"}
            ]
        }
    }
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)
        
    ok, msg = claude.uninstall(repo_path=temp_repo, shared=False)
    assert ok is True
    
    with open(settings_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert len(data["hooks"]["Stop"]) == 1
    assert data["hooks"]["Stop"][0]["command"] == "echo 'custom pre-stop'"
    
    stat = claude.status(repo_path=temp_repo, shared=False)
    assert stat["installed"] is False


def test_cli_hook_subcommands(temp_repo, capsys):
    """Test CLI dispatch for hook status, install, and uninstall."""
    from guard_cli.cli import main

    # Status before install
    ret = main(["hook", "status", "--repo", str(temp_repo)])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "claude" in data
    assert "antigravity" in data
    assert data["antigravity"]["installed"] is False

    # Install antigravity hook
    ret = main(["hook", "install", "--repo", str(temp_repo), "--antigravity"])
    assert ret == 0
    capsys.readouterr()

    # Status after install
    ret = main(["hook", "status", "--repo", str(temp_repo)])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["antigravity"]["installed"] is True

    # Uninstall antigravity hook
    ret = main(["hook", "uninstall", "--repo", str(temp_repo), "--antigravity"])
    assert ret == 0


def test_cli_default_graph_resolution(temp_repo):
    """Verify that when graph name is omitted, db and api resolve graph_name from .guard/config.toml."""
    from guard_cli.backend import save_config
    save_config(temp_repo, {"backend": {"type": "server", "graph_name": "custom_repo_graph"}})

    with patch("guard_cli.db.get_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        db.get_graph(name=None, repo_path=temp_repo)
        mock_backend.get_graph.assert_called_with("custom_repo_graph")

    with patch("guard_cli.db.get_backend") as mock_get_backend, patch("guard_cli.db.get_covering_tests") as mock_get_cov:
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        mock_get_cov.return_value = []
        api.covering_tests("pkg/mod.py::calc", repo_path=temp_repo)
        mock_backend.get_graph.assert_called_with("custom_repo_graph")

