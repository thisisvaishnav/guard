"""Test verifying Fix 1: Commit Bypass.

Done when: A test commits the Flask mutant and the hook still exits 2.
"""
import subprocess
from pathlib import Path
import pytest

from guard_cli.hook import run_stop_hook, is_working_tree_clean
from guard_cli.state import set_last_verified_sha, set_baseline_sha, load_state


def test_committed_flask_mutant_hook_exits_2():
    flask_dir = Path("target_repos/flask").resolve()
    if not flask_dir.exists():
        pytest.skip(f"Flask repo not found at {flask_dir}")

    session_id = "test_commit_bypass_session"

    # 1. Ensure clean initial state
    subprocess.run(["git", "checkout", "--", "."], cwd=str(flask_dir), capture_output=True)
    subprocess.run(["git", "clean", "-fd", "-e", ".venv", "-e", ".claude"], cwd=str(flask_dir), capture_output=True)

    head_proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(flask_dir), capture_output=True, text=True)
    assert head_proc.returncode == 0
    clean_sha = head_proc.stdout.strip()

    # Record baseline and last_verified at this clean commit
    set_baseline_sha(session_id, clean_sha, repo_path=flask_dir)
    set_last_verified_sha(session_id, clean_sha, repo_path=flask_dir)

    # 2. Apply mutant patch
    patch_file = Path("evals/fixtures/diff_covered.patch").resolve()
    assert patch_file.exists()

    apply_proc = subprocess.run(["git", "apply", str(patch_file)], cwd=str(flask_dir), capture_output=True, text=True)
    if apply_proc.returncode != 0:
        # Fallback to patch -p1
        subprocess.run(["patch", "-p1", "-i", str(patch_file)], cwd=str(flask_dir), check=True)

    committed = False
    try:
        # 3. Commit the mutant
        commit_proc = subprocess.run(
            ["git", "commit", "-am", "test: apply covered mutant"],
            cwd=str(flask_dir),
            capture_output=True,
            text=True,
        )
        assert commit_proc.returncode == 0, f"git commit failed: {commit_proc.stderr}"
        committed = True

        # Verify working tree is clean (excluding .guard internal state)
        assert is_working_tree_clean(flask_dir) is True

        # 4. Invoke Stop Hook
        # Even though working tree is clean, the commit bypass defense must detect that HEAD != last_verified_sha
        # and evaluate git diff <last_verified_sha>, which contains the mutant.
        exit_code = run_stop_hook(
            repo_override=flask_dir,
            strict=True,
            raw_input={"session_id": session_id, "cwd": str(flask_dir)},
        )

        # 5. Assert hook blocked the stop attempt (exit code 2)
        assert exit_code == 2, f"Expected hook to exit 2 on committed mutant, got {exit_code}"

    finally:
        # Cleanup: Revert commit and clean working tree
        if committed:
            subprocess.run(["git", "reset", "--hard", clean_sha], cwd=str(flask_dir), capture_output=True)
        subprocess.run(["git", "checkout", "--", "."], cwd=str(flask_dir), capture_output=True)
        subprocess.run(["git", "clean", "-fd", "-e", ".venv", "-e", ".claude"], cwd=str(flask_dir), capture_output=True)
