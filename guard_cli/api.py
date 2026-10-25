"""Guard Public API and Stable Contract (Phase 0).

Provides the unified contract used across the CLI, Claude Code hook,
MCP server, and external agent loops:
- `check()`: Evaluates diff, returns test selection decision + versioned schema.
- `run()`: Executes the selected test subset according to trust policy.
- `covering_tests()`: Queries graph for tests covering a function.
- `callers()`: Queries multi-hop callers of a function.
- `report_miss()`: Feedback loop repairing graph with a miss_repair edge.

Fail-open by default: If database or graph is unavailable and strict=False,
Guard emits a warning to stderr and fails open instead of blocking the agent.
"""
from __future__ import annotations
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import Any

from guard_cli import db
from guard_cli import feedback
from guard_cli.events import log_event
from guard_cli.thin_slice import (
    guard_check,
    parse_unified_diff,
    resolve_changed_functions,
    thin_slice_decision,
    CheckResult,
)
from guard_cli.agent_integration import (
    REPO_ROOT,
    apply_patch,
    reset_repo,
    count_collected_tests,
)

SCHEMA_VERSION = "1.0"


def _extract_failures(stdout: str, stderr: str) -> list[str]:
    """Parses failing pytest test identifiers or collection errors from output."""
    failures: list[str] = []
    # pytest output lines typically look like:
    # FAILED tests/test_config.py::test_config_class - AssertionError...
    # ERROR tests/test_syntax.py - SyntaxError...
    # ERROR tests/test_config.py::test_1 - Exception...
    # ERROR collecting tests/test_broken.py
    # ERROR: tests/test_broken.py
    fail_regex = re.compile(
        r"^(?:FAILED|ERROR:?|ERRORS:?)\s+(?:collecting\s+)?([^\s]+)",
        re.MULTILINE,
    )
    for text in (stdout, stderr):
        if not text:
            continue
        for match in fail_regex.finditer(text):
            target = match.group(1).rstrip(":")
            if target and target not in ("collecting", "during", "at", "==="):
                failures.append(target)

        # Pytest header style: _ ERROR collecting tests/test_syntax.py _
        header_regex = re.compile(
            r"^_{1,}\s+ERROR\s+(?:collecting\s+|at\s+[^\s]+\s+of\s+)?([^\s_]+)",
            re.MULTILINE,
        )
        for match in header_regex.finditer(text):
            target = match.group(1).strip()
            if target:
                failures.append(target)

    # If pytest failed during collection or emitted ERRORS but no specific identifier matched:
    combined = f"{stdout}\n{stderr}"
    if not failures:
        if (
            "error during collection" in combined
            or re.search(r"^=*\s*ERRORS\s*=*", combined, re.MULTILINE)
            or re.search(r"^ERROR\b", combined, re.MULTILINE)
        ):
            failures.append("collection_error")

    return sorted(list(set(failures)))


def _extract_failure_summary(stdout: str, stderr: str, max_lines: int = 15) -> str:
    """Extracts up to max_lines of actionable failure/traceback summary from pytest output."""
    raw_text = stdout if stdout.strip() else stderr
    if not raw_text.strip():
        return ""

    lines = [line.rstrip() for line in raw_text.splitlines() if line.strip()]

    # Locate where failures or errors start
    start_idx = 0
    for i, line in enumerate(lines):
        if re.search(r"^=+\s*(FAILURES|ERRORS)\s*=+", line):
            start_idx = i
            break
        if re.match(r"^_{2,}\s+(ERROR|test_)", line):
            start_idx = i
            break
        if re.match(r"^(FAILED|ERROR)\s+", line):
            start_idx = i
            break

    relevant_lines = lines[start_idx:]
    if len(relevant_lines) <= max_lines:
        return "\n".join(relevant_lines)

    # Filter out noisy internal frames if too long
    filtered = [
        l for l in relevant_lines
        if not any(noise in l for noise in ("site-packages/_pytest", "<frozen ", "pluggy/"))
    ]
    if len(filtered) <= max_lines:
        return "\n".join(filtered)

    # If still > max_lines, take head + tail to keep context, error message, and summary
    head_count = 4
    tail_count = max(1, max_lines - head_count - 1)
    truncated = filtered[:head_count] + ["  ... [truncated] ..."] + filtered[-tail_count:]
    return "\n".join(truncated[:max_lines])


def _format_reasons(check_res: CheckResult) -> dict[str, str]:
    """Generates a reasons map for selected tests."""
    reasons: dict[str, str] = {}
    if check_res.is_fallback:
        reason_text = check_res.fallback_reason or "Fallback triggered"
        for t in check_res.selected_tests:
            reasons[t] = f"selected: full suite required ({reason_text})"
    else:
        for t in check_res.selected_tests:
            reasons[t] = "selected: covering edge from changed function"
    return reasons


def normalize_test_target_for_pytest(target: str) -> str:
    """Normalizes graph test identifiers into valid pytest CLI invocation targets."""
    if "::" not in target:
        return target
    file_part, func_part = target.split("::", 1)
    if "." in func_part:
        cls_name, method_name = func_part.split(".", 1)
        if method_name.startswith("test"):
            return f"{file_part}::{cls_name}::{method_name}"
        else:
            return f"{file_part}::{cls_name}"
    else:
        if func_part.startswith("test") or func_part.startswith("Test"):
            return target
        else:
            return file_part


def check(
    diff_text: str | None = None,
    diff_file: str | Path | None = None,
    repo_path: str | Path | None = None,
    graph_name: str = "guard",
    strict: bool = False,
    no_confidence_filter: bool = False,
    no_dynamic_widening: bool = False,
    baseline_sha: str | None = None,
) -> dict[str, Any]:
    """Evaluates proposed changes and returns test selection decision.
    
    Returns a versioned JSON dictionary conforming to schema v1.0.
    """
    repo = Path(repo_path).resolve() if repo_path else Path.cwd()
    diff_path = Path(diff_file).resolve() if diff_file else None

    try:
        res = guard_check(
            diff_text=diff_text,
            diff_file=diff_path,
            repo_path=repo,
            graph_name=graph_name,
            no_confidence_filter=no_confidence_filter,
            no_dynamic_widening=no_dynamic_widening,
            baseline_sha=baseline_sha,
        )

        is_fallback = res.is_fallback
        policy = "subset" if not is_fallback else "run_all"
        trust = 0.9 if not is_fallback else 0.0

        overrides = []
        if is_fallback:
            if res.fallback_reason:
                if "Test files" in res.fallback_reason:
                    overrides.append("test_file_touched")
                elif "no_evidence" in res.fallback_reason or "No covering tests" in res.fallback_reason or "No parsed" in res.fallback_reason:
                    overrides.append("no_evidence")
                else:
                    overrides.append("fallback_override")

        reasons = _format_reasons(res)

        return {
            "version": SCHEMA_VERSION,
            "status": res.status,
            "policy": policy,
            "trust": trust,
            "overrides_triggered": overrides,
            "selected_tests": res.selected_tests,
            "selected_tests_count": len(res.selected_tests),
            "failures": [],
            "reasons": reasons,
            "changed_functions": res.changed_functions,
            "is_fallback": res.is_fallback,
            "fallback_reason": res.fallback_reason,
            "execution_time_ms": res.execution_time_ms,
        }
    except Exception as exc:
        if strict:
            raise
        sys.stderr.write(f"Guard warning (fail-open): check failed with {exc}\n")
        log_event(
            event="fail_open",
            repo_path=repo,
            details={"op": "check", "error": str(exc)},
        )
        return {
            "version": SCHEMA_VERSION,
            "status": "run-all",
            "policy": "fail_open",
            "trust": 0.0,
            "overrides_triggered": ["fail_open_error"],
            "selected_tests": ["tests"],
            "selected_tests_count": 1,
            "failures": [],
            "reasons": {"error": f"Guard check error: {exc}"},
            "changed_functions": [],
            "is_fallback": True,
            "fallback_reason": f"Guard database/internal error: {exc}",
            "execution_time_ms": 0.0,
            "fail_open": True,
            "error": str(exc),
        }


def run(
    diff_file: str | Path | None = None,
    diff_text: str | None = None,
    repo_path: str | Path | None = None,
    graph_name: str = "guard",
    strict: bool = False,
    session_id: str | None = None,
    baseline_sha: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Runs Guard check and executes the selected tests.
    
    Returns:
        (report_dict, exit_code)
    """
    repo = Path(repo_path).resolve() if repo_path else Path.cwd()
    diff_path = Path(diff_file).resolve() if diff_file else None

    # 1. Run check
    try:
        check_dict = check(
            diff_text=diff_text,
            diff_file=diff_path,
            repo_path=repo,
            graph_name=graph_name,
            strict=strict,
            baseline_sha=baseline_sha,
        )
    except Exception as exc:
        if strict:
            raise
        sys.stderr.write(f"Guard warning (fail-open): check failed with {exc}\n")
        log_event(
            event="fail_open",
            session_id=session_id,
            repo_path=repo,
            details={"op": "run", "error": str(exc)},
        )
        return {
            "version": SCHEMA_VERSION,
            "status": "passed",
            "policy": "fail_open",
            "trust": 0.0,
            "overrides_triggered": ["fail_open_error"],
            "selected_tests": [],
            "failures": [],
            "reasons": {},
            "tests_run": [],
            "tests_run_count": 0,
            "tests_passed": True,
            "forced_full": False,
            "fallback_reason": str(exc),
            "duration_s": 0.0,
            "exit_code": 0,
            "output_summary": f"Guard bypassed fail-open: {exc}",
            "fail_open": True,
        }, 0

    # Fail-open short-circuit: if check() could not evaluate the diff (database/graph
    # unavailable), do not attempt the full-suite fallback. Running the whole suite on an
    # unknown diff is itself unreliable (e.g. Guard's own tests require FalkorDB), so we
    # allow the stop with a loud warning and record a fail_open event, matching Guard's
    # documented fail-open behavior instead of blocking the agent.
    if check_dict.get("fail_open") or check_dict.get("policy") == "fail_open":
        reason = (
            check_dict.get("fallback_reason")
            or check_dict.get("error")
            or "Guard database/graph unavailable"
        )
        if strict:
            raise RuntimeError(f"Guard fail-open suppressed by strict mode: {reason}")
        sys.stderr.write(
            f"Guard warning (fail-open): {reason}. "
            "Skipping safety check and allowing stop without running tests.\n"
        )
        log_event(
            event="fail_open",
            session_id=session_id,
            repo_path=repo,
            details={"op": "run", "error": reason},
        )
        return {
            "version": SCHEMA_VERSION,
            "status": "passed",
            "policy": "fail_open",
            "trust": 0.0,
            "overrides_triggered": check_dict.get("overrides_triggered", ["fail_open_error"]),
            "selected_tests": [],
            "failures": [],
            "reasons": check_dict.get("reasons", {}),
            "tests_run": [],
            "tests_run_count": 0,
            "tests_passed": True,
            "forced_full": False,
            "fallback_reason": reason,
            "duration_s": 0.0,
            "exit_code": 0,
            "output_summary": f"Guard bypassed fail-open: {reason}",
            "fail_open": True,
        }, 0

    forced_full = check_dict.get("is_fallback", False) or (check_dict.get("status") == "run-all")
    if forced_full:
        tests_to_run = ["tests"]
    else:
        raw_selected = check_dict.get("selected_tests", ["tests"])
        tests_to_run = list(dict.fromkeys(normalize_test_target_for_pytest(t) for t in raw_selected))

    # 2. Apply patch if explicit diff_file was provided
    applied = False
    if diff_path and diff_path.exists():
        reset_repo(repo)
        applied = apply_patch(diff_path, repo)
        if not applied:
            err_dict = {
                "version": SCHEMA_VERSION,
                "status": "error",
                "policy": check_dict.get("policy", "run_all"),
                "trust": check_dict.get("trust", 0.0),
                "overrides_triggered": check_dict.get("overrides_triggered", []),
                "selected_tests": tests_to_run,
                "failures": ["patch_apply_failure"],
                "reasons": check_dict.get("reasons", {}),
                "forced_full": True,
                "fallback_reason": "Failed to apply patch diff",
                "changed_functions": check_dict.get("changed_functions", []),
                "tests_run": [],
                "tests_run_count": 0,
                "duration_s": 0.0,
                "tests_passed": False,
                "exit_code": 1,
                "output_summary": "Error: Failed to apply patch cleanly to target repo.",
            }
            log_event(
                event="failed",
                session_id=session_id,
                repo_path=repo,
                details=err_dict,
            )
            return err_dict, 1

    try:
        # Count collected tests
        test_count = count_collected_tests(tests_to_run, repo)

        # Resolve target repo python interpreter
        py_bin = sys.executable
        if repo:
            try:
                from guard_cli.init_cmd import find_test_environment
                py_bin = str(find_test_environment(repo))
            except Exception:
                pass

        # 3. Execute pytest with configurable timeout
        from guard_cli.hook import get_hook_timeout
        timeout = get_hook_timeout(repo)
        cmd = [py_bin, "-m", "pytest", "-q", "--tb=short"] + tests_to_run
        start = time.time()
        try:
            proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=timeout)
            duration_s = round(time.time() - start, 3)
            passed = (proc.returncode == 0)
            failures = _extract_failures(proc.stdout, proc.stderr)
            if passed:
                summary_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
            else:
                summary_line = _extract_failure_summary(proc.stdout, proc.stderr, max_lines=15)
                if not failures:
                    failures = ["test_execution_failure"]
            proc_exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            duration_s = round(time.time() - start, 3)
            passed = False
            failures = [f"test_suite_timeout_expired_{timeout}s"]
            summary_line = f"Test execution timed out after {duration_s:.1f}s (timeout: {timeout}s)."
            proc_exit_code = 124
            log_event(
                event="timeout",
                session_id=session_id,
                repo_path=repo,
                details={
                    "timeout_s": timeout,
                    "duration_s": duration_s,
                    "tests_run": tests_to_run,
                    "policy": check_dict.get("policy", "subset"),
                },
            )

        report = {
            "version": SCHEMA_VERSION,
            "status": "passed" if passed else "failed",
            "policy": check_dict.get("policy", "subset"),
            "trust": check_dict.get("trust", 0.9 if passed else 0.0),
            "overrides_triggered": check_dict.get("overrides_triggered", []),
            "selected_tests": check_dict.get("selected_tests", []),
            "failures": failures,
            "reasons": check_dict.get("reasons", {}),
            "forced_full": forced_full,
            "fallback_reason": check_dict.get("fallback_reason"),
            "changed_functions": check_dict.get("changed_functions", []),
            "tests_run": tests_to_run,
            "tests_run_count": test_count,
            "duration_s": duration_s,
            "tests_passed": passed,
            "exit_code": proc_exit_code,
            "output_summary": summary_line,
        }

        # Log event
        log_event(
            event="passed" if passed else "blocked",
            session_id=session_id,
            repo_path=repo,
            details={
                "exit_code": proc_exit_code,
                "tests_passed": passed,
                "tests_run_count": test_count,
                "failures": failures,
                "policy": report["policy"],
            },
        )

        return report, proc_exit_code
    finally:
        if applied:
            reset_repo()


def covering_tests(
    function_id: str,
    min_confidence: float = 0.0,
    graph_name: str | None = None,
    repo_path: str | Path | None = None,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Find tests covering a given function, ordered by confidence."""
    try:
        g = db.get_graph(graph_name, repo_path=repo_path)
        return db.get_covering_tests(g, function_id, min_confidence=min_confidence)
    except Exception as exc:
        if strict:
            raise
        sys.stderr.write(f"Guard warning (fail-open): covering_tests failed with {exc}\n")
        return []


def callers(
    function_id: str,
    hops: int = 4,
    min_confidence: float = 0.0,
    graph_name: str | None = None,
    repo_path: str | Path | None = None,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Traverse inbound CALLS edges up to N hops filtered by min_confidence."""
    try:
        g = db.get_graph(graph_name, repo_path=repo_path)
        return db.get_callers(g, function_id, hops=hops, min_confidence=min_confidence)
    except Exception as exc:
        if strict:
            raise
        sys.stderr.write(f"Guard warning (fail-open): callers failed with {exc}\n")
        return []


def report_miss(
    function_id: str,
    test_id: str,
    new_confidence: float = 1.0,
    graph_name: str | None = None,
    repo_path: str | Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Records a missed failure by repairing the graph with a miss_repair edge."""
    try:
        g = db.get_graph(graph_name, repo_path=repo_path)
        return feedback.record_miss(
            g,
            function_id=function_id,
            test_id=test_id,
            new_confidence=new_confidence,
        )
    except Exception as exc:
        if strict:
            raise
        sys.stderr.write(f"Guard warning (fail-open): report_miss failed with {exc}\n")
        return {
            "status": "error",
            "error": str(exc),
            "function": function_id,
            "test": test_id,
            "fail_open": True,
        }
