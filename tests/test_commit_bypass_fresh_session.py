"""Regression test for the commit-bypass hole.

A brand new session ID must not reset the diff baseline to the current HEAD:
otherwise a broken commit made before the session started looks like a clean
tree and slips past the Stop hook (Guard's central promise).

The baseline is now repo-level (`last_verified_sha`, falling back to the SHA
recorded at ingest), so these tests exercise a *fresh* session against a repo
whose `.guard/state.json` records the pre-mutant ingest commit.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from guard_cli.hook import check_idle_turn, resolve_diff_ref, run_session_start_hook, run_stop_hook
from guard_cli.integrations import antigravity, claude
from guard_cli.state import get_repo_baseline_sha, get_session_blocks


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True
    )


@pytest.fixture
def repo_with_ingest(tmp_path):
    """A git repo whose recorded ingest SHA predates a committed mutant."""
    repo = tmp_path / "mutant_repo"
    repo.mkdir()

    _git(repo, "init")
    _git(repo, "config", "user.email", "tester@guard.dev")
    _git(repo, "config", "user.name", "Guard Tester")

    (repo / ".gitignore").write_text(".guard/\n", encoding="utf-8")
    pkg = repo / "sample_calc"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text(
        "from sample_calc.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "clean baseline")
    clean_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Simulate `guard init` recording the ingest HEAD SHA.
    guard_dir = repo / ".guard"
    guard_dir.mkdir()
    (guard_dir / "state.json").write_text(
        json.dumps({"head_sha": clean_sha}), encoding="utf-8"
    )

    # Commit a mutant that breaks the test (working tree ends clean).
    (pkg / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8"
    )
    _git(repo, "commit", "-am", "mutant")
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() != clean_sha

    return repo


def test_committed_mutant_fresh_session_is_not_idle(repo_with_ingest):
    """A fresh session ID must still diff against the recorded ingest SHA."""
    is_idle, reason, _fp, diff_ref = check_idle_turn(
        repo_with_ingest, session_id="brand_new_session"
    )
    assert is_idle is False
    assert reason == "python_files_modified"
    assert diff_ref != _git(repo_with_ingest, "rev-parse", "HEAD").stdout.strip()


def test_committed_mutant_fresh_session_hook_exits_2(repo_with_ingest):
    """The Stop hook must block (exit 2) a committed mutant under a fresh session ID."""
    mock_report = {
        "status": "failed",
        "policy": "subset",
        "trust": 0.4,
        "failures": ["tests/test_calc.py::test_add"],
        "tests_run_count": 1,
        "output_summary": "1 failed in 0.01s",
    }

    with patch("guard_cli.api.run", return_value=(mock_report, 1)):
        exit_code = run_stop_hook(
            repo_override=repo_with_ingest,
            strict=True,
            raw_input={"session_id": "brand_new_session", "cwd": str(repo_with_ingest)},
        )

    assert exit_code == 2, f"Expected exit 2 on committed mutant, got {exit_code}"
    assert get_session_blocks("brand_new_session", repo_path=repo_with_ingest) == 1


def test_repo_last_verified_sha_wins_over_fresh_session_head(repo_with_ingest):
    """Once tests pass, the repo-level last_verified_sha is the diff baseline."""
    import subprocess as _sp

    head = _sp.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_with_ingest),
        capture_output=True,
        text=True,
    ).stdout.strip()
    # Pretend an earlier turn verified the (mutant) HEAD so the chain is exercised.
    from guard_cli.state import set_repo_last_verified_sha

    set_repo_last_verified_sha(head, repo_path=repo_with_ingest)
    ref, source = resolve_diff_ref(repo_with_ingest, "yet_another_fresh_session", head)
    assert source == "repo_last_verified"
    assert ref == head


def test_session_start_records_repo_baseline_once(tmp_path):
    """SessionStart/PreInvocation records a repo baseline, then never overwrites it."""
    repo = tmp_path / "baseline_repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tester@guard.dev")
    _git(repo, "config", "user.name", "Guard Tester")
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    first_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert run_session_start_hook(repo_override=repo, raw_input={"session_id": "s1"}) == 0
    assert get_repo_baseline_sha(repo_path=repo) == first_sha

    # A later commit must not be latched as the baseline by a new session.
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    _git(repo, "commit", "-am", "second")
    run_session_start_hook(repo_override=repo, raw_input={"session_id": "s2"})
    assert get_repo_baseline_sha(repo_path=repo) == first_sha


def test_claude_install_adds_session_start_hook(tmp_path):
    repo = tmp_path / "claude_repo"
    repo.mkdir()
    ok, _ = claude.install(repo_path=repo)
    assert ok is True
    data = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    start_hooks = data["hooks"]["SessionStart"]
    guard_exe = claude.get_guard_executable()
    assert any(
        sub.get("command") == f"{guard_exe} hook session-start"
        for h in start_hooks
        for sub in h.get("hooks", [])
    )
    assert claude.status(repo_path=repo)["session_start_installed"] is True
    claude.uninstall(repo_path=repo)
    data_after = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert "SessionStart" not in data_after.get("hooks", {})
    assert "Stop" not in data_after.get("hooks", {})


def test_antigravity_install_adds_session_start_hook(tmp_path):
    repo = tmp_path / "agy_repo"
    repo.mkdir()
    ok, _ = antigravity.install(repo)
    assert ok is True
    data = json.loads((repo / ".agents" / "hooks.json").read_text(encoding="utf-8"))
    assert "SessionStart" in data["guard-stop"]
    session_start = data["guard-stop"]["SessionStart"]
    assert any("hook session-start" in h.get("command", "") for h in session_start)
    assert "PreInvocation" not in data["guard-stop"]
    assert antigravity.status(repo)["session_start_installed"] is True
    antigravity.uninstall(repo)
    data_after = json.loads((repo / ".agents" / "hooks.json").read_text(encoding="utf-8"))
    assert "guard-stop" not in data_after
