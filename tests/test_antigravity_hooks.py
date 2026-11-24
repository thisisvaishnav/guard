"""Tests for Antigravity (agy) Stop hook fixes before recording.

Covers items 1 through 8:
1. Baseline: commit broken change, new conversationId, hook blocks (decision: continue).
2. Stdout purity: agy stdout contains exactly one JSON object, logs/warnings to stderr, exits 0.
3. Payload capture: GUARD_DEBUG_PAYLOAD=1 writes raw stdin payload to .guard/last_payload.json.
4. Block message: lists failing tests, changed function, and says 'Fix the source code. Do not edit, skip, or delete tests.'
5. Database down: allows stop with {"decision":"stop","reason":"Guard skipped: database unreachable"} and logs fail_open event (not blocked).
6. Block cap: agent gets 3 blocks, then handback (fixed off-by-one).
7. Hook command: absolute path of guard in .agents/hooks.json, guard doctor verifies path exists.
8. Official docs confirmation: field names, timeout unit in seconds, available events.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from guard_cli import doctor_cmd
from guard_cli.events import read_events
from guard_cli.hook import (
    format_failure_summary,
    read_hook_input,
    run_stop_hook,
)
from guard_cli.integrations import antigravity
from guard_cli.state import (
    get_session_blocks,
    record_session_block,
    set_repo_last_verified_sha,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "agy_stop_payload.json"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True
    )


# 1. Baseline: commit broken change, new conversationId, hook must block
def test_baseline_new_conversation_blocks_on_committed_change(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@guard.dev")
    _git(repo, "config", "user.name", "Guard Tester")
    (repo / ".gitignore").write_text(".guard/\n", encoding="utf-8")

    src = repo / "calc.py"
    src.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "clean initial commit")
    clean_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Ingest clean commit
    guard_dir = repo / ".guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    (guard_dir / "state.json").write_text(json.dumps({"head_sha": clean_sha}), encoding="utf-8")

    # Agent commits a broken change (working tree is clean)
    src.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    _git(repo, "commit", "-am", "break add function")

    # Start a brand new conversationId
    new_conversation_id = "conversation-fresh-uuid-999"
    raw_input = {
        "conversationId": new_conversation_id,
        "workspacePaths": [str(repo)],
        "terminationReason": "NO_TOOL_CALL",
        "fullyIdle": True,
    }

    mock_report = {
        "status": "failed",
        "policy": "subset",
        "trust": 0.85,
        "tests_run_count": 1,
        "failures": ["tests/test_calc.py::test_add"],
        "changed_functions": ["calc.py:add"],
        "output_summary": "1 failed in 0.02s",
    }

    with patch("guard_cli.api.run", return_value=(mock_report, 1)):
        exit_code = run_stop_hook(repo_override=repo, strict=True, raw_input=raw_input)

    assert exit_code == 0  # Antigravity protocol always exits 0
    # Must have recorded block
    assert get_session_blocks(new_conversation_id, repo_path=repo) == 1


# 2. Stdout purity: stdout must contain exactly one JSON object and nothing else
def test_stdout_purity_pipe_json_tool(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()

    raw_input = {
        "conversationId": "conv-stdout-purity",
        "workspacePaths": [str(repo)],
        "terminationReason": "NO_TOOL_CALL",
        "fullyIdle": True,
    }

    mock_report = {
        "status": "failed",
        "policy": "subset",
        "trust": 0.9,
        "tests_run_count": 2,
        "failures": ["tests/test_foo.py::test_fail"],
        "changed_functions": ["foo.py:bar"],
        "output_summary": "1 failed",
    }

    # Simulate stray stdout printing during run to test that sys.stdout redirection protects purity
    def mock_run_with_stray_output(*args, **kwargs):
        sys.stdout.write("Stray stdout from library or subprocess\n")
        print("Another stray print statement")
        return mock_report, 1

    with patch("guard_cli.hook.check_idle_turn", return_value=(False, "python_files_modified", "fp", "sha")), \
         patch("guard_cli.hook.get_session_blocks", return_value=0), \
         patch("guard_cli.api.run", side_effect=mock_run_with_stray_output):
        exit_code = run_stop_hook(repo_override=repo, raw_input=raw_input)

    assert exit_code == 0
    captured = capsys.readouterr()

    # Stdout must be EXACTLY ONE valid JSON object
    stdout_content = captured.out.strip()
    parsed = json.loads(stdout_content)
    assert parsed["decision"] == "continue"
    assert "GUARD SAFETY CHECK FAILED" in parsed["reason"]

    # Verify stdout passes through python -m json.tool without error
    proc = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=captured.out,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    formatted = json.loads(proc.stdout)
    assert formatted["decision"] == "continue"

    # All stray messages must have been redirected to stderr
    assert "Stray stdout from library or subprocess" in captured.err
    assert "Another stray print statement" in captured.err


# 3. Payload capture: if GUARD_DEBUG_PAYLOAD=1, write raw stdin payload to .guard/last_payload.json
def test_payload_capture_with_fixture(tmp_path, monkeypatch):
    assert FIXTURE_PATH.exists()
    fixture_content = FIXTURE_PATH.read_text(encoding="utf-8")
    fixture_data = json.loads(fixture_content)

    repo = tmp_path / "target_repo"
    repo.mkdir()
    fixture_data["workspacePaths"] = [str(repo)]
    updated_raw = json.dumps(fixture_data, indent=2)

    monkeypatch.setenv("GUARD_DEBUG_PAYLOAD", "1")

    # Test via stdin in read_hook_input
    with patch("sys.stdin", io.StringIO(updated_raw)):
        parsed = read_hook_input()
        assert parsed["conversationId"] == fixture_data["conversationId"]

    captured_file = Path.cwd() / ".guard" / "last_payload.json"
    assert captured_file.exists()
    assert json.loads(captured_file.read_text(encoding="utf-8"))["conversationId"] == fixture_data["conversationId"]

    # Also test in run_stop_hook writing to repo's .guard/last_payload.json
    with patch("guard_cli.hook.check_idle_turn", return_value=(True, "clean_tree", None, "sha")):
        run_stop_hook(repo_override=repo, raw_input=fixture_data)

    repo_payload_file = repo / ".guard" / "last_payload.json"
    assert repo_payload_file.exists()
    saved = json.loads(repo_payload_file.read_text(encoding="utf-8"))
    assert saved["conversationId"] == fixture_data["conversationId"]


# 4. Block message: lists failing tests and changed function, and says "Fix the source code. Do not edit, skip, or delete tests."
def test_block_message_content():
    report = {
        "policy": "subset",
        "trust": 0.88,
        "tests_run_count": 3,
        "changed_functions": ["flask.config:Config.from_pyfile"],
        "failures": ["tests/test_config.py::test_config_from_pyfile"],
        "output_summary": "1 failed, 2 passed in 0.15s",
    }

    msg = format_failure_summary(report)
    assert "Changed Function: flask.config:Config.from_pyfile" in msg
    assert "Failing Tests:" in msg
    assert "- tests/test_config.py::test_config_from_pyfile" in msg
    assert "Fix the source code. Do not edit, skip, or delete tests." in msg


# 5. Database down: allow stop with {"decision":"stop","reason":"Guard skipped: database unreachable"} and log fail_open
def test_database_down_allows_stop_and_logs_fail_open(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()

    raw_input = {
        "conversationId": "conv-db-down",
        "workspacePaths": [str(repo)],
        "terminationReason": "NO_TOOL_CALL",
        "fullyIdle": True,
    }

    fail_open_report = {
        "fail_open": True,
        "policy": "fail_open",
        "tests_passed": True,
        "status": "passed",
        "fallback_reason": "FalkorDB unreachable",
    }

    with patch("guard_cli.hook.check_idle_turn", return_value=(False, "python_files_modified", "fp", "sha")), \
         patch("guard_cli.hook.get_session_blocks", return_value=0), \
         patch("guard_cli.api.run", return_value=(fail_open_report, 0)):
        exit_code = run_stop_hook(repo_override=repo, strict=False, raw_input=raw_input)

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["decision"] == "stop"
    assert payload["reason"] == "Guard skipped: database unreachable"

    events = read_events(repo_path=repo)
    # Must not contain any "blocked" event
    assert not any(e.get("event") == "blocked" for e in events)


# 6. Block cap: agent gets 3 blocks, then a handback (fixed off-by-one)
def test_block_cap_gives_three_blocks_then_handback(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    sess_id = "sess-loop-3cap"

    mock_report = {
        "status": "failed",
        "policy": "subset",
        "trust": 0.9,
        "failures": ["tests/test_x.py::test_fail"],
        "changed_functions": ["x.py:func"],
    }

    raw_input = {
        "conversationId": sess_id,
        "workspacePaths": [str(repo)],
    }

    with patch("guard_cli.hook.check_idle_turn", return_value=(False, "modified", "fp", "sha")), \
         patch("guard_cli.api.run", return_value=(mock_report, 1)):

        # Turn 1: 1st failure -> Block 1
        with patch("sys.stdout", io.StringIO()) as out1:
            code1 = run_stop_hook(repo_override=repo, raw_input=raw_input)
            assert code1 == 0
            assert json.loads(out1.getvalue().strip())["decision"] == "continue"
            assert get_session_blocks(sess_id, repo_path=repo) == 1

        # Turn 2: 2nd failure -> Block 2
        with patch("sys.stdout", io.StringIO()) as out2:
            code2 = run_stop_hook(repo_override=repo, raw_input=raw_input)
            assert code2 == 0
            assert json.loads(out2.getvalue().strip())["decision"] == "continue"
            assert get_session_blocks(sess_id, repo_path=repo) == 2

        # Turn 3: 3rd failure -> Block 3 (agent must get 3 blocks, not handed back yet!)
        with patch("sys.stdout", io.StringIO()) as out3:
            code3 = run_stop_hook(repo_override=repo, raw_input=raw_input)
            assert code3 == 0
            assert json.loads(out3.getvalue().strip())["decision"] == "continue"
            assert get_session_blocks(sess_id, repo_path=repo) == 3

        # Turn 4: 4th attempt after 3 blocks -> Handback to human!
        with patch("sys.stdout", io.StringIO()) as out4:
            code4 = run_stop_hook(repo_override=repo, raw_input=raw_input)
            assert code4 == 0
            res4 = json.loads(out4.getvalue().strip())
            assert res4["decision"] == "stop"
            assert "Guard blocked 3 times, handing back to you" in res4["reason"]


# 7. Hook command: write absolute path of guard into .agents/hooks.json, guard doctor checks existence
def test_absolute_path_written_and_checked_by_doctor(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text(".guard/\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("<!-- BEGIN GUARD INTEGRATION -->\n<!-- END GUARD INTEGRATION -->\n", encoding="utf-8")

    # Install hooks with custom mock executable
    fake_guard = tmp_path / "fake_guard_bin"
    fake_guard.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_guard.chmod(0o755)

    ok, msg = antigravity.install(repo, guard_executable=str(fake_guard))
    assert ok is True

    hooks_file = repo / ".agents" / "hooks.json"
    data = json.loads(hooks_file.read_text(encoding="utf-8"))
    stop_cmd = data["guard-stop"]["Stop"][0]["command"]
    assert stop_cmd.startswith(str(fake_guard))

    # Doctor check passes when executable exists
    res = doctor_cmd.check_integrations(repo)
    assert res.status == "pass"

    # Now remove the executable: doctor must fail
    fake_guard.unlink()
    res_fail = doctor_cmd.check_integrations(repo)
    assert res_fail.status == "fail"
    assert "does not exist" in res_fail.message


# 8. Hooks doc verification: field names, timeout unit in seconds, available events
def test_antigravity_hooks_spec_conformance():
    custom_doc = os.environ.get("ANTIGRAVITY_HOOKS_DOC")
    doc_path = Path(custom_doc) if custom_doc else None
    if doc_path and doc_path.exists():
        content = doc_path.read_text(encoding="utf-8")
        assert "conversationId" in content
        assert "stepIdx" in content
        assert "workspacePaths" in content
        assert "terminationReason" in content
        assert "fullyIdle" in content
        assert "timeout in seconds" in content
        for ev in ("SessionStart", "PreToolUse", "PostToolUse", "PreInvocation", "PostInvocation", "Stop"):
            assert f"`{ev}`" in content
    else:
        # Validate required antigravity payload schema fields from fixture
        assert FIXTURE_PATH.exists()
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        for field in ("conversationId", "workspacePaths", "terminationReason", "fullyIdle"):
            assert field in payload
