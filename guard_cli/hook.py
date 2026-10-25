"""Claude Code Stop Hook Adapter (Phase 1).

Executes when Claude Code attempts to stop/complete a turn:
1. Reads session info from stdin JSON.
2. Checks git diff; if working tree is clean, exits 0 immediately (idle turn).
3. Enforces loop guard: after 3 consecutive blocks, hands back control (exits 0).
4. Runs Guard's test selection via `guard.api.run()`.
5. On failure, outputs <= 30 line summary to stderr and exits 2 (blocking error).
6. Fail-open by default if Guard itself crashes.
"""
from __future__ import annotations
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any

import hashlib
from guard_cli import api
from guard_cli.events import log_event
from guard_cli.state import (
    get_session_blocks,
    record_session_block,
    reset_session_blocks,
    get_last_passed_fingerprint,
    set_last_passed_fingerprint,
    clear_last_passed_fingerprint,
    get_baseline_sha,
    set_baseline_sha,
    get_last_verified_sha,
    set_last_verified_sha,
    clear_last_verified_sha,
    get_repo_baseline_sha,
    set_repo_baseline_sha,
    get_repo_last_verified_sha,
    set_repo_last_verified_sha,
    get_ingest_sha,
)


def _capture_payload(content: str, repo_path: Path | None = None) -> None:
    """Writes the raw stdin payload to .guard/last_payload.json when GUARD_DEBUG_PAYLOAD=1."""
    try:
        base = repo_path or Path.cwd()
        guard_dir = base / ".guard"
        guard_dir.mkdir(parents=True, exist_ok=True)
        (guard_dir / "last_payload.json").write_text(content, encoding="utf-8")
    except Exception:
        pass


def read_hook_input() -> dict[str, Any]:
    """Reads stdin JSON safely if available."""
    if sys.stdin.isatty():
        return {}
    try:
        content = sys.stdin.read()
        if not content.strip():
            return {}
        if os.getenv("GUARD_DEBUG_PAYLOAD") == "1":
            _capture_payload(content)
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_hook_context(
    repo_override: str | Path | None,
    hook_input: dict[str, Any],
) -> tuple[Path, str, bool]:
    """Resolves (cwd, session_id, is_antigravity) from a hook payload."""
    # Antigravity (agy) payloads use camelCase fields.
    is_antigravity = bool(
        "conversationId" in hook_input
        or "terminationReason" in hook_input
        or "workspacePaths" in hook_input
    )
    session_id = (
        hook_input.get("conversationId")
        or hook_input.get("session_id")
        or "default_session"
    )

    workspace_paths = hook_input.get("workspacePaths")
    input_cwd = (
        workspace_paths[0]
        if (isinstance(workspace_paths, list) and workspace_paths)
        else hook_input.get("cwd")
    )
    if repo_override:
        cwd = Path(repo_override).resolve()
    elif input_cwd:
        cwd = Path(input_cwd).resolve()
    else:
        cwd = Path.cwd()
    return cwd, session_id, is_antigravity


def _git_head_sha(repo_path: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return ""


def run_session_start_hook(
    repo_override: str | Path | None = None,
    raw_input: dict[str, Any] | None = None,
) -> int:
    """Records the baseline SHA as early as possible in an agent lifecycle.

    Invoked by the Claude Code `SessionStart` hook and by the Antigravity
    `PreInvocation` hook (which fires before each model call; it records the
    baseline on first use). Recording a repo-level baseline here means a fresh
    session cannot redefine the baseline to a broken HEAD.

    Returns 0 always: baseline recording must never block an agent session.
    """
    hook_input = raw_input if raw_input is not None else read_hook_input()
    cwd, session_id, is_antigravity = resolve_hook_context(repo_override, hook_input)

    head_sha = _git_head_sha(cwd)
    recorded_repo = False
    recorded_session = False
    if head_sha:
        if not get_repo_baseline_sha(repo_path=cwd):
            set_repo_baseline_sha(head_sha, repo_path=cwd)
            recorded_repo = True
        if not get_baseline_sha(session_id, repo_path=cwd):
            set_baseline_sha(session_id, head_sha, repo_path=cwd)
            recorded_session = True

    log_event(
        event="session_start",
        session_id=session_id,
        repo_path=cwd,
        details={
            "head_sha": head_sha,
            "baseline_recorded": recorded_repo,
            "agent_type": "antigravity" if is_antigravity else "claude",
        },
    )

    # Antigravity PreInvocation expects a neutral JSON reply; `{}` is the
    # documented "no opinion, proceed" output. Claude Code needs no output.
    if is_antigravity:
        sys.stdout.write("{}\n")
        sys.stdout.flush()
    return 0


def is_working_tree_clean(repo_path: Path) -> bool:
    """Returns True if the git working tree has no changes (ignoring .guard internal directory and tool/env metadata)."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if proc.returncode == 0:
            ignored_prefixes = (".guard", ".claude", ".agents", ".venv")
            lines = [
                l for l in proc.stdout.splitlines()
                if l.strip() and not any(l[3:].strip().removeprefix("./").startswith(pref) for pref in ignored_prefixes)
            ]
            return len(lines) == 0
        return False
    except Exception:
        return False


def compute_turn_fingerprint(
    repo_path: Path,
    baseline_sha: str | None,
    head_sha: str,
    diff_baseline: str,
    diff_cached: str,
    untracked_files: list[str],
    g: Any = None,
) -> str:
    """Computes a comprehensive turn fingerprint covering modified, staged, and untracked files,
    plus the Guard version and FalkorDB graph state."""
    from guard_cli import __version__
    from guard_cli import db

    # 1. Untracked file contents
    untracked_hashes: list[dict[str, str]] = []
    for rel_path in sorted(untracked_files):
        norm = rel_path.replace("\\", "/")
        if norm.startswith(".guard/") or norm == ".guard":
            continue
        full_p = repo_path / rel_path
        if full_p.is_file():
            try:
                content_sha = hashlib.sha256(full_p.read_bytes()).hexdigest()[:16]
                untracked_hashes.append({"path": norm, "sha": content_sha})
            except Exception:
                pass

    # 2. Graph state
    try:
        graph_state = db.get_graph_state(g, repo_path=repo_path)
    except Exception:
        graph_state = {"status": "unknown"}

    components = {
        "guard_version": __version__,
        "baseline_sha": baseline_sha or "",
        "head_sha": head_sha or "",
        "diff_baseline": diff_baseline,
        "diff_cached": diff_cached,
        "untracked": untracked_hashes,
        "graph_state": graph_state,
    }
    raw = json.dumps(components, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


DEFAULT_HOOK_TIMEOUT = 180


def get_hook_timeout(repo_path: str | Path | None = None) -> int:
    """Resolves hook timeout from GUARD_HOOK_TIMEOUT env var, .guard/config.toml, or default (180)."""
    env_val = os.getenv("GUARD_HOOK_TIMEOUT")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    try:
        from guard_cli.backend import load_config
        cfg = load_config(repo_path)
        hook_cfg = cfg.get("hook", {})
        if "timeout" in hook_cfg:
            return int(hook_cfg["timeout"])
        guard_cfg = cfg.get("guard", {})
        if "timeout" in guard_cfg:
            return int(guard_cfg["timeout"])
    except Exception:
        pass
    return DEFAULT_HOOK_TIMEOUT


def resolve_diff_ref(
    repo_path: Path,
    session_id: str,
    head_sha: str,
) -> tuple[str | None, str]:
    """Resolves the commit to diff against.

    Priority:
        1. session_last_verified (most recent commit that passed tests in this session)
        2. session_baseline (recorded at SessionStart for this session)
        3. repo_last_verified (repo-level commit that last passed tests)
        4. ingest_sha (commit recorded at guard init)
        5. repo_baseline
        6. HEAD
    """
    session_last_verified = get_last_verified_sha(session_id, repo_path=repo_path)
    session_baseline = get_baseline_sha(session_id, repo_path=repo_path)
    repo_last_verified = get_repo_last_verified_sha(repo_path)
    ingest_sha = get_ingest_sha(repo_path)
    repo_baseline = get_repo_baseline_sha(repo_path)

    # Record a repo-level baseline on first ever use so there is always a
    # non-HEAD reference for future sessions. Never overwrite an existing one.
    if head_sha and not any(
        (repo_last_verified, session_last_verified, ingest_sha, repo_baseline, session_baseline)
    ):
        set_repo_baseline_sha(head_sha, repo_path=repo_path)
        repo_baseline = head_sha

    for sha, source in (
        (session_last_verified, "session_last_verified"),
        (session_baseline, "session_baseline"),
        (repo_last_verified, "repo_last_verified"),
        (ingest_sha, "ingest_sha"),
        (repo_baseline, "repo_baseline"),
    ):
        if sha:
            return sha, source

    return (head_sha or None), "head"


def check_idle_turn(
    repo_path: Path,
    session_id: str = "default_session",
    graph_name: str | None = None,
) -> tuple[bool, str, str | None, str | None]:
    """Checks whether the current turn is an idle turn that can skip test runs.
    
    Returns:
        (is_idle: bool, reason: str, fingerprint: str | None, baseline_sha: str | None)
        reason is one of: 'clean_tree', 'non_python_only', 'cached_pass', or error/modification status.
    """
    try:
        # Determine git HEAD SHA
        head_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        head_sha = head_proc.stdout.strip() if head_proc.returncode == 0 else ""

        # Resolve the diff baseline
        diff_ref, _ = resolve_diff_ref(repo_path, session_id, head_sha)

        # Latch session baseline to resolved diff_ref (never unverified head_sha)
        if diff_ref and not get_baseline_sha(session_id, repo_path=repo_path):
            set_baseline_sha(session_id, diff_ref, repo_path=repo_path)

        # Working tree status
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if status_proc.returncode != 0:
            if is_working_tree_clean(repo_path):
                return True, "clean_tree", None, diff_ref
            return False, "git_status_error", None, diff_ref

        status_stdout = status_proc.stdout
        status_lines = [l for l in status_stdout.splitlines() if l.strip()]

        # Diffs against diff_ref and staged diff
        diff_baseline = ""
        if diff_ref:
            db_proc = subprocess.run(
                ["git", "diff", diff_ref],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if db_proc.returncode == 0:
                diff_baseline = db_proc.stdout

        diff_cached = ""
        dc_proc = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if dc_proc.returncode == 0:
            diff_cached = dc_proc.stdout

        untracked_files = [
            l[3:].strip() for l in status_lines if l.startswith("??")
        ]

        wt_clean = is_working_tree_clean(repo_path)
        has_commit_changes = bool(head_sha and diff_ref and head_sha != diff_ref)
        has_diff = bool(diff_baseline.strip() or diff_cached.strip())

        if wt_clean and not has_commit_changes and not has_diff:
            return True, "clean_tree", None, diff_ref

        # Check if python files were affected
        py_files: list[str] = []
        # 1. From status
        for line in status_lines:
            path_part = line[3:].strip()
            if " -> " in path_part:
                sub_paths = [p.strip() for p in path_part.split(" -> ")]
            else:
                sub_paths = [path_part]
            for sp in sub_paths:
                norm = sp.replace("\\", "/")
                if norm.startswith(".guard/") or norm == ".guard":
                    continue
                if norm.endswith(".py"):
                    py_files.append(norm)

        # 2. From diff against diff_ref
        if diff_baseline:
            name_proc = subprocess.run(
                ["git", "diff", "--name-only", diff_ref],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if name_proc.returncode == 0:
                for line in name_proc.stdout.splitlines():
                    norm = line.strip().replace("\\", "/")
                    if norm.startswith(".guard/") or norm == ".guard":
                        continue
                    if norm.endswith(".py"):
                        py_files.append(norm)

        # If working tree was explicitly marked unclean via mock/flag but has no parsed files
        if not wt_clean and not status_lines and not has_diff:
            py_files.append("simulated_change.py")

        if not py_files:
            return True, "non_python_only", None, diff_ref

        # Resolve graph
        g = None
        try:
            from guard_cli import db
            g = db.get_graph(name=graph_name, repo_path=repo_path)
        except Exception:
            pass

        fingerprint = compute_turn_fingerprint(
            repo_path=repo_path,
            baseline_sha=diff_ref,
            head_sha=head_sha,
            diff_baseline=diff_baseline,
            diff_cached=diff_cached,
            untracked_files=untracked_files,
            g=g,
        )

        last_passed = get_last_passed_fingerprint(session_id, repo_path=repo_path)
        if last_passed and last_passed == fingerprint:
            return True, "cached_pass", fingerprint, diff_ref

        return False, "python_files_modified", fingerprint, diff_ref
    except Exception as exc:
        return False, f"error_{exc}", None, None


def format_failure_summary(report: dict[str, Any], max_lines: int = 30) -> str:
    """Formats a concise <= 30 line error summary for the agent context."""
    lines = [
        "GUARD SAFETY CHECK FAILED (Exit 2 - Blocking Stop)",
        "==================================================",
        f"Trust Policy : {report.get('policy', 'unknown')} (Trust Score: {report.get('trust', 0.0):.2f})",
    ]
    
    overrides = report.get("overrides_triggered", [])
    if overrides:
        lines.append(f"Overrides    : {', '.join(overrides)}")
        
    reason = report.get("fallback_reason")
    if reason:
        lines.append(f"Reason       : {reason}")

    changed_funcs = report.get("changed_functions", [])
    if changed_funcs:
        if len(changed_funcs) == 1:
            lines.append(f"Changed Function: {changed_funcs[0]}")
        else:
            lines.append("Changed Functions:")
            for fn in changed_funcs[:5]:
                lines.append(f"  - {fn}")

    lines.append(f"Tests Run    : {report.get('tests_run_count', 0)}")
    
    failures = report.get("failures", [])
    failure_details = report.get("failure_details") or report.get("failure_messages")
    if failures:
        lines.append("Failing Tests:")
        for f in failures[:12]:
            if isinstance(f, dict):
                test_id = f.get("test", f.get("id", str(f)))
                err = f.get("message") or f.get("error") or ""
                lines.append(f"  - {test_id}: {err}" if err else f"  - {test_id}")
            elif isinstance(failure_details, dict) and f in failure_details:
                lines.append(f"  - {f}: {failure_details[f]}")
            else:
                lines.append(f"  - {f}")
        if len(failures) > 12:
            lines.append(f"  ... and {len(failures) - 12} additional failures")
            
    summary = report.get("output_summary")
    if summary:
        if "\n" in summary.strip():
            lines.append("Failure Details:")
            for s_line in summary.strip().splitlines():
                lines.append(f"  {s_line}")
        else:
            lines.append(f"Summary      : {summary}")
        
    footer = [
        "--------------------------------------------------",
        "Fix the source code. Do not edit, skip, or delete tests.",
    ]
    if max_lines >= len(footer) + 2:
        if len(lines) + len(footer) > max_lines:
            lines = lines[: max_lines - len(footer)]
        lines.extend(footer)
        return "\n".join(lines) + "\n"
    else:
        lines.extend(footer)
        return "\n".join(lines[:max_lines]) + "\n"


def run_stop_hook(
    repo_override: str | Path | None = None,
    strict: bool = False,
    raw_input: dict[str, Any] | None = None,
) -> int:
    """Executes the Stop hook workflow (supporting both Claude Code and Antigravity CLI).
    
    Returns:
        0 on pass, clean tree, or loop-cap hand back (allow stop)
        2 on test failure for Claude Code, or 0 with continue decision for Antigravity
    """
    hook_input = raw_input if raw_input is not None else read_hook_input()

    cwd, session_id, is_antigravity = resolve_hook_context(repo_override, hook_input)

    if os.getenv("GUARD_DEBUG_PAYLOAD") == "1":
        guard_dir = cwd / ".guard"
        guard_dir.mkdir(parents=True, exist_ok=True)
        payload_file = guard_dir / "last_payload.json"
        if raw_input is not None or not payload_file.exists():
            payload_file.write_text(json.dumps(hook_input, indent=2) + "\n", encoding="utf-8")

    saved_stdout = sys.stdout
    saved_fd = None
    real_out = None
    if is_antigravity:
        sys.stdout = sys.stderr
        try:
            if hasattr(saved_stdout, "fileno") and saved_stdout.fileno() == 1:
                sys.stdout.flush()
                sys.stderr.flush()
                saved_fd = os.dup(1)
                os.dup2(2, 1)
                real_out = open(saved_fd, "w", encoding="utf-8", closefd=False)
        except Exception:
            saved_fd = None
            real_out = None

    def _allow_stop(reason: str | None = None) -> int:
        if is_antigravity:
            resp: dict[str, Any] = {"decision": "stop", "reason": reason or ""}
            payload = json.dumps(resp) + "\n"
            target_out = real_out if real_out is not None else saved_stdout
            if target_out is not None:
                try:
                    target_out.write(payload)
                    target_out.flush()
                except Exception:
                    pass
        return 0

    def _block_stop(reason_text: str) -> int:
        if is_antigravity:
            resp: dict[str, Any] = {"decision": "continue", "reason": reason_text}
            payload = json.dumps(resp) + "\n"
            target_out = real_out if real_out is not None else saved_stdout
            if target_out is not None:
                try:
                    target_out.write(payload)
                    target_out.flush()
                except Exception:
                    pass
            sys.stderr.write(reason_text)
            return 0
        else:
            sys.stderr.write(reason_text)
            return 2

    try:
        stop_hook_active = bool(hook_input.get("stop_hook_active", False))

        # Log hook entry
        log_event(
            event="hook_fired",
            session_id=session_id,
            repo_path=cwd,
            details={
                "stop_hook_active": stop_hook_active,
                "agent_type": "antigravity" if is_antigravity else "claude",
            },
        )

        # 1. Idle turn check: If working tree is clean, non-python only, or fingerprint cache hit
        is_idle, idle_reason, fingerprint, baseline_sha = check_idle_turn(cwd, session_id=session_id)
        if is_idle:
            log_event(
                event="idle_turn",
                session_id=session_id,
                repo_path=cwd,
                details={"reason": idle_reason, "fingerprint": fingerprint},
            )
            return _allow_stop()

        # 2. Execute Guard run
        try:
            report, exit_code = api.run(
                repo_path=cwd,
                strict=strict,
                session_id=session_id,
                baseline_sha=baseline_sha,
            )
        except Exception as exc:
            if strict:
                return _block_stop(f"Guard error (strict): {exc}\n")
            sys.stderr.write(f"Warning: Guard encountered an error: {exc}. Failing open.\n")
            log_event(
                event="fail_open",
                session_id=session_id,
                repo_path=cwd,
                details={"error": str(exc)},
            )
            return _allow_stop(reason="Guard skipped: database unreachable")

        # 3. Handle test results
        if exit_code == 0:
            if report.get("fail_open"):
                return _allow_stop(reason="Guard skipped: database unreachable")
            reset_session_blocks(session_id, repo_path=cwd)
            if fingerprint:
                set_last_passed_fingerprint(session_id, fingerprint, repo_path=cwd)
            try:
                head_proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(cwd), capture_output=True, text=True)
                if head_proc.returncode == 0 and head_proc.stdout.strip():
                    verified_sha = head_proc.stdout.strip()
                    set_last_verified_sha(session_id, verified_sha, repo_path=cwd)
                    # Repo-level marker: survives new session IDs so a later broken
                    # commit is always diffed against the last verified commit.
                    set_repo_last_verified_sha(verified_sha, repo_path=cwd)
            except Exception:
                pass
            return _allow_stop()

        # Test failure: clear cached fingerprint and increment blocks
        clear_last_passed_fingerprint(session_id, repo_path=cwd)
        new_blocks = record_session_block(session_id, repo_path=cwd)
        if new_blocks > 3:
            reset_session_blocks(session_id, repo_path=cwd)
            msg = "Guard blocked 3 times, handing back to you\n"
            sys.stderr.write(msg)
            log_event(
                event="handed_back",
                session_id=session_id,
                repo_path=cwd,
                details={"consecutive_blocks": new_blocks},
            )
            return _allow_stop(reason=msg.strip())

        # Format failure summary <= 30 lines
        summary_text = format_failure_summary(report, max_lines=30)
        
        log_event(
            event="blocked",
            session_id=session_id,
            repo_path=cwd,
            details={
                "consecutive_blocks": new_blocks,
                "policy": report.get("policy"),
                "failures": report.get("failures", []),
            },
        )
        return _block_stop(summary_text)
    finally:
        sys.stdout = saved_stdout
        if saved_fd is not None:
            try:
                sys.stderr.flush()
                os.dup2(saved_fd, 1)
                os.close(saved_fd)
            except Exception:
                pass
