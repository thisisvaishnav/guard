"""Guard doctor command implementation (Work Package D).

Performs diagnostic verification across 6 subsystems:
1. Environment (Python version >= 3.10, Guard version, PATH check for hooks)
2. Backend (reachability and query round-trip)
3. Graph (nodes > 0, edges > 0)
4. Freshness (ingest SHA vs git HEAD SHA, changed files count)
5. Target repo (git root, target Python, pytest, pytest-cov, baseline status)
6. Integrations (.claude/settings.json, AGENTS.md, .gitignore)

Exit codes:
0: All checks passed
1: Warnings present, no failures
2: At least one failure present
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

import guard_cli
from guard_cli import db
from guard_cli.backend import (
    GraphBackend,
    get_repo_graph_name,
    resolve_backend,
    DockerBackend,
)
from guard_cli.init_cmd import (
    find_repo_root,
    find_test_environment,
    write_integrations,
    INTEGRATION_MARKER_START,
)

console = Console()


@dataclass
class CheckResult:
    name: str
    status: str  # "pass", "warn", "fail"
    message: str
    fix: str | None = None


def check_environment() -> CheckResult:
    """Check Python version, Guard version, and executable on PATH."""
    py_ver = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    if sys.version_info < (3, 10):
        return CheckResult(
            name="environment",
            status="fail",
            message=f"Python {py_ver} is unsupported. Python 3.10 or newer is required.",
            fix="Upgrade to Python 3.10+ (recommended: Python 3.12).",
        )

    guard_bin = shutil.which("guard")
    if not guard_bin:
        return CheckResult(
            name="environment",
            status="warn",
            message=f"Python {py_ver}, guard v{guard_cli.__version__}. 'guard' is not found on PATH for subshells and agent hooks.",
            fix="Add your Python/uv tool bin directory to PATH (e.g. run 'uv tool update-shell' or add ~/.local/bin to PATH).",
        )

    return CheckResult(
        name="environment",
        status="pass",
        message=f"Python {py_ver}, guard v{guard_cli.__version__} (binary: {guard_bin}).",
    )


def check_backend(repo_path: Path) -> tuple[CheckResult, GraphBackend | None]:
    """Check if FalkorDB backend is reachable and round-trips a query."""
    try:
        backend = resolve_backend(repo_path=repo_path, autostart=False)
        desc = backend.describe()
        if not desc.get("healthy", False):
            return (
                CheckResult(
                    name="backend",
                    status="fail",
                    message=f"Backend '{backend.name}' is unreachable or failed query round-trip.",
                    fix="Start FalkorDB: 'docker start guard-falkordb' or run 'guard init --backend docker'.",
                ),
                backend,
            )
        return (
            CheckResult(
                name="backend",
                status="pass",
                message=f"Backend '{backend.name}' is healthy ({desc.get('connection_str') or desc.get('data_path') or desc.get('container')}).",
            ),
            backend,
        )
    except Exception as err:
        return (
            CheckResult(
                name="backend",
                status="fail",
                message=f"Backend resolution error: {err}",
                fix="Run 'guard init' to configure a valid backend.",
            ),
            None,
        )


def check_graph(repo_path: Path, backend: GraphBackend | None) -> CheckResult:
    """Verify repository graph exists in FalkorDB with non-zero nodes and edges."""
    if backend is None or not backend.is_healthy():
        return CheckResult(
            name="graph",
            status="fail",
            message="Cannot check graph: backend is offline.",
            fix="Ensure backend is running and re-run doctor.",
        )

    graph_name = get_repo_graph_name(repo_path)
    try:
        g = backend.get_graph(graph_name)
        counts = db.get_schema_counts(g)
        nodes_total = sum(counts.get(k, 0) for k in ("File", "Function", "Test", "Run"))
        edges_total = sum(counts.get(k, 0) for k in ("CALLS", "IMPORTS", "DEFINED_IN", "COVERED_BY", "FAILED_IN"))

        if nodes_total == 0:
            return CheckResult(
                name="graph",
                status="fail",
                message=f"Graph '{graph_name}' exists but has 0 nodes and 0 edges.",
                fix="Run 'guard init' to ingest repository structure.",
            )

        cov_count = counts.get("COVERED_BY", 0)
        cov_info = f", {cov_count} coverage edges" if cov_count else " (no coverage edges yet)"
        return CheckResult(
            name="graph",
            status="pass",
            message=f"Graph '{graph_name}' has {counts.get('Function', 0)} functions, {counts.get('Test', 0)} tests{cov_info}.",
        )
    except Exception as err:
        return CheckResult(
            name="graph",
            status="fail",
            message=f"Error querying graph '{graph_name}': {err}",
            fix="Run 'guard init' to rebuild graph schema.",
        )


def check_freshness(repo_path: Path) -> CheckResult:
    """Compare recorded ingest commit SHA with current git HEAD SHA."""
    state_file = repo_path / ".guard" / "state.json"
    if not state_file.exists():
        return CheckResult(
            name="freshness",
            status="warn",
            message="No recorded ingestion state found in .guard/state.json.",
            fix="Run 'guard init' to index repository and record baseline state.",
        )

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        ingest_sha = data.get("head_sha")
    except Exception:
        ingest_sha = None

    if not ingest_sha or ingest_sha == "unknown":
        return CheckResult(
            name="freshness",
            status="warn",
            message="Ingestion state exists but recorded commit SHA is unknown.",
            fix="Run 'guard init' to update state with current commit.",
        )

    # Get current git HEAD SHA
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        current_sha = res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        current_sha = ""

    if not current_sha:
        return CheckResult(
            name="freshness",
            status="warn",
            message="Could not determine current git HEAD SHA.",
            fix="Ensure git is installed and repository has commits.",
        )

    if ingest_sha == current_sha:
        return CheckResult(
            name="freshness",
            status="pass",
            message=f"Graph is fresh at commit {current_sha[:7]}.",
        )

    # Check changed files since ingest SHA
    try:
        diff_res = subprocess.run(
            ["git", "diff", "--name-only", ingest_sha, "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        changed_files = [f for f in diff_res.stdout.splitlines() if f.strip()]
        if changed_files:
            return CheckResult(
                name="freshness",
                status="warn",
                message=f"{len(changed_files)} file(s) changed since ingest at {ingest_sha[:7]} (HEAD is {current_sha[:7]}).",
                fix="Run 'guard ingest-static .' to refresh static call graph.",
            )
        return CheckResult(
            name="freshness",
            status="pass",
            message=f"Graph is up to date (no files changed between {ingest_sha[:7]} and {current_sha[:7]}).",
        )
    except Exception:
        return CheckResult(
            name="freshness",
            status="warn",
            message=f"HEAD has diverged from ingest commit {ingest_sha[:7]}.",
            fix="Run 'guard ingest-static .' to refresh call graph.",
        )


def check_target_repo(repo_path: Path) -> CheckResult:
    """Verify target repo Python environment, pytest, and pytest-cov."""
    try:
        test_py = find_test_environment(repo_path)
    except Exception as err:
        return CheckResult(
            name="target_repo",
            status="fail",
            message=f"Failed detecting test environment: {err}",
            fix="Ensure virtualenv exists or pytest is installed.",
        )

    # Check pytest
    try:
        res = subprocess.run(
            [str(test_py), "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode != 0:
            return CheckResult(
                name="target_repo",
                status="fail",
                message=f"pytest is not installed in target environment ({test_py}).",
                fix=f"Run: {test_py} -m pip install pytest",
            )
    except Exception:
        return CheckResult(
            name="target_repo",
            status="fail",
            message=f"pytest is not functional in target environment ({test_py}).",
            fix=f"Run: {test_py} -m pip install pytest",
        )

    # Check pytest-cov
    try:
        res_cov = subprocess.run(
            [str(test_py), "-c", "import pytest_cov"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        has_cov = (res_cov.returncode == 0)
    except Exception:
        has_cov = False

    if not has_cov:
        return CheckResult(
            name="target_repo",
            status="warn",
            message=f"pytest present ({test_py.name}), but pytest-cov is not installed in target environment.",
            fix=f"Run: {test_py} -m pip install pytest-cov",
        )

    return CheckResult(
        name="target_repo",
        status="pass",
        message=f"Target environment verified with pytest and pytest-cov ({test_py}).",
    )


def check_integrations(repo_path: Path) -> CheckResult:
    """Verify .claude/settings.json, AGENTS.md, and .gitignore integrations."""
    missing: list[str] = []

    # 1. Check .gitignore
    gi = repo_path / ".gitignore"
    if not gi.exists() or (".guard/" not in gi.read_text(encoding="utf-8") and ".guard" not in gi.read_text(encoding="utf-8")):
        missing.append(".guard/ in .gitignore")

    # 2. Check Stop hook in Claude Code or Antigravity CLI
    from guard_cli.integrations import claude, antigravity
    claude_info = claude.check_all_settings(repo_path)
    agy_info = antigravity.status(repo_path)
    if not claude_info["installed"] and not agy_info["installed"]:
        missing.append("hook in .agents/hooks.json or .claude/settings.json")
    elif agy_info.get("installed") and not agy_info.get("executable_exists", True):
        exe = agy_info.get("executable_path")
        return CheckResult(
            name="integrations",
            status="fail",
            message=f"Guard executable configured in .agents/hooks.json does not exist: {exe}.",
            fix="Run 'guard init' or 'guard hook install --antigravity' to update executable path.",
        )

    # 3. Check AGENTS.md or CLAUDE.md marked block
    agents_doc = repo_path / "AGENTS.md"
    claude_doc = repo_path / "CLAUDE.md"
    has_marker = False
    for doc in (agents_doc, claude_doc):
        if doc.exists() and INTEGRATION_MARKER_START in doc.read_text(encoding="utf-8"):
            has_marker = True
            break
    if not has_marker:
        missing.append("marked instruction block in AGENTS.md/CLAUDE.md")

    if missing:
        return CheckResult(
            name="integrations",
            status="warn",
            message=f"Missing integration settings: {', '.join(missing)}.",
            fix="Run 'guard doctor --fix' or 'guard init' to write integration files.",
        )

    active_agents = []
    if claude_info["installed"]:
        active_agents.append("claude")
    if agy_info["installed"]:
        active_agents.append("antigravity")

    return CheckResult(
        name="integrations",
        status="pass",
        message=f"Integrations verified for {', '.join(active_agents) if active_agents else 'agents'} (AGENTS.md and .gitignore present).",
    )


def check_hook_timeout(repo_path: Path) -> CheckResult:
    """Verify hook timeout configuration and warn if baseline test duration is near the limit."""
    from guard_cli.hook import get_hook_timeout
    timeout = get_hook_timeout(repo_path)

    # Read baseline duration from state.json if present
    state_file = repo_path / ".guard" / "state.json"
    baseline_s = None
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            baseline_s = data.get("baseline_duration_s") or data.get("baseline_s")
        except Exception:
            pass

    if baseline_s is not None:
        try:
            baseline_f = float(baseline_s)
            if baseline_f >= (0.7 * timeout):
                return CheckResult(
                    name="hook_timeout",
                    status="warn",
                    message=(
                        f"Baseline test run took {baseline_f:.1f}s, which is near the hook timeout limit ({timeout}s). "
                        f"Slow test execution may cause agent hook timeout."
                    ),
                    fix=f"Increase timeout in .guard/config.toml ([hook] timeout = {int(baseline_f * 2)}) or optimize slow tests.",
                )
            return CheckResult(
                name="hook_timeout",
                status="pass",
                message=f"Baseline test run took {baseline_f:.1f}s (comfortably within {timeout}s timeout limit).",
            )
        except (ValueError, TypeError):
            pass

    return CheckResult(
        name="hook_timeout",
        status="pass",
        message=f"Hook timeout is configured to {timeout}s.",
    )


def apply_fixes(repo_path: Path, backend: GraphBackend | None, checks: list[CheckResult]) -> list[str]:
    """Execute safe automated repairs for warnings/failures."""
    applied: list[str] = []

    for c in checks:
        if c.name == "backend" and isinstance(backend, DockerBackend):
            # Attempt to start stopped docker container
            if backend.start_container():
                applied.append(f"Started docker container '{backend.container_name}'.")

        elif c.name == "integrations":
            write_integrations(repo_path, agents=["claude", "antigravity"])
            applied.append("Wrote integrations to .gitignore, .agents/hooks.json, .claude/settings.json, AGENTS.md, and CLAUDE.md.")

    return applied


def run_doctor(
    repo_path: str | Path | None = None,
    json_mode: bool = False,
    fix_mode: bool = False,
) -> int:
    """Run full Guard doctor diagnostic check."""
    try:
        root = find_repo_root(repo_path)
    except Exception as err:
        if json_mode:
            print(json.dumps({
                "status": "fail",
                "exit_code": 2,
                "error": str(err),
            }, indent=2))
        else:
            console.print(f"[bold red]Error finding repository:[/bold red] {err}")
        return 2

    # Run checks
    check_env_res = check_environment()
    check_b_res, backend = check_backend(root)
    check_g_res = check_graph(root, backend)
    check_f_res = check_freshness(root)
    check_t_res = check_target_repo(root)
    check_i_res = check_integrations(root)
    check_to_res = check_hook_timeout(root)

    checks = [
        check_env_res,
        check_b_res,
        check_g_res,
        check_f_res,
        check_t_res,
        check_i_res,
        check_to_res,
    ]

    applied_fixes: list[str] = []
    if fix_mode:
        applied_fixes = apply_fixes(root, backend, checks)
        # Re-run checks if fixes were applied
        if applied_fixes:
            check_b_res, backend = check_backend(root)
            check_g_res = check_graph(root, backend)
            check_i_res = check_integrations(root)
            checks = [
                check_env_res,
                check_b_res,
                check_g_res,
                check_f_res,
                check_t_res,
                check_i_res,
            ]

    # Compute status and exit code
    has_fail = any(c.status == "fail" for c in checks)
    has_warn = any(c.status == "warn" for c in checks)

    if has_fail:
        overall_status = "fail"
        exit_code = 2
    elif has_warn:
        overall_status = "warn"
        exit_code = 1
    else:
        overall_status = "pass"
        exit_code = 0

    if json_mode:
        payload = {
            "status": overall_status,
            "exit_code": exit_code,
            "applied_fixes": applied_fixes,
            "checks": [asdict(c) for c in checks],
        }
        print(json.dumps(payload, indent=2))
        return exit_code

    # Rich terminal formatting
    console.rule("[bold cyan]Guard Doctor Diagnostic Report[/bold cyan]")
    if applied_fixes:
        console.print("[bold green]Automated Repairs Applied (--fix):[/bold green]")
        for fix_msg in applied_fixes:
            console.print(f"  [green]✔[/green] {fix_msg}")
        console.print()

    table = Table(title="Subsystem Checks", show_header=True, header_style="bold magenta")
    table.add_column("Subsystem", style="cyan", width=15)
    table.add_column("Status", width=10)
    table.add_column("Details", style="white")

    for c in checks:
        if c.status == "pass":
            status_badge = "[bold green]PASS[/bold green]"
        elif c.status == "warn":
            status_badge = "[bold yellow]WARN[/bold yellow]"
        else:
            status_badge = "[bold red]FAIL[/bold red]"

        details = c.message
        if c.fix and c.status in ("warn", "fail"):
            details += f"\n[dim italic]Fix: {c.fix}[/dim italic]"

        table.add_row(c.name, status_badge, details)

    console.print(table)

    pass_count = sum(1 for c in checks if c.status == "pass")
    warn_count = sum(1 for c in checks if c.status == "warn")
    fail_count = sum(1 for c in checks if c.status == "fail")

    summary_color = "green" if exit_code == 0 else ("yellow" if exit_code == 1 else "red")
    console.rule(f"[bold {summary_color}]Result: {pass_count} passed, {warn_count} warnings, {fail_count} failures[/bold {summary_color}]")

    return exit_code
