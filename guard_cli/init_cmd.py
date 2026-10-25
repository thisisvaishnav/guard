"""Guard init command implementation (Work Package C).

Steps:
1. Find the repo (git root + test configuration)
2. Find the test environment (target repo's own virtualenv / python)
3. Check pytest-cov (offer to install if missing, never silent)
4. Start/resolve backend (Server, Docker, or Embedded)
5. Static ingest (fast static parsing with rich progress summary)
6. Baseline run (time 1 pytest run, estimate 3x cost, exclude failing tests)
7. Coverage ingest (per-test coverage using target environment)
8. Record state (HEAD SHA + timestamp in graph and .guard/state.json)
9. Write integrations (.claude/settings.json, AGENTS.md, CLAUDE.md, .gitignore)
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from guard_cli.backend import (
    GraphBackend,
    get_repo_graph_name,
    resolve_backend,
    save_config,
)

console = Console()

INTEGRATION_MARKER_START = "<!-- BEGIN GUARD INTEGRATION -->"
INTEGRATION_MARKER_END = "<!-- END GUARD INTEGRATION -->"

GUARD_INSTRUCTIONS_BLOCK = f"""{INTEGRATION_MARKER_START}
## Guard Safety Layer

Before declaring any code edits or refactoring complete, run:
```bash
guard run
```

If Guard flags low trust, unverified call paths, or uncovered changes, it enforces a full test suite run. Do not bypass or suppress Guard failures.
{INTEGRATION_MARKER_END}"""


def find_repo_root(start_path: str | Path | None = None) -> Path:
    """Locate the git root and verify test configuration exists."""
    p = Path(start_path).resolve() if start_path else Path.cwd()

    # Try git rev-parse --show-toplevel
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(p),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            root = Path(res.stdout.strip()).resolve()
        else:
            root = p
    except Exception:
        root = p

    # Find test configs or test directory
    test_markers = [
        "pyproject.toml",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        "tests",
        "test",
    ]
    has_test_config = any((root / m).exists() for m in test_markers)
    if not has_test_config and not (root / ".git").exists():
        raise ValueError(
            f"Directory '{root}' does not appear to be a Python git repository with tests. "
            "Could not find pyproject.toml, pytest.ini, setup.cfg, tox.ini, or tests/."
        )

    return root


def find_test_environment(repo_path: Path) -> Path:
    """Find the target repo's own virtualenv or Python executable."""
    raw_candidates: list[Path] = []
    if os.environ.get("VIRTUAL_ENV"):
        raw_candidates.append(Path(os.environ["VIRTUAL_ENV"]))
    if os.environ.get("CONDA_PREFIX"):
        raw_candidates.append(Path(os.environ["CONDA_PREFIX"]))

    raw_candidates.extend([
        repo_path / ".venv",
        repo_path / "venv",
        repo_path / "env",
        repo_path / ".env",
    ])

    if sys.prefix:
        raw_candidates.append(Path(sys.prefix))

    seen: set[Path] = set()
    candidates: list[Path] = []
    for c in raw_candidates:
        resolved = c.resolve() if c.exists() else c
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(c)

    for c in candidates:
        possible_py: list[Path] = []
        if c.is_file():
            possible_py.append(c)
        elif c.is_dir():
            possible_py.extend([
                c / "bin" / "python",
                c / "Scripts" / "python.exe",
                c / "python.exe",
                c / "python",
            ])

        for py in possible_py:
            if py.is_file() and os.access(py, os.X_OK):
                try:
                    res = subprocess.run(
                        [str(py), "-m", "pytest", "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if res.returncode == 0:
                        return py
                except Exception:
                    pass

    # Fallback to current sys.executable
    return Path(sys.executable)


def check_pytest_cov(test_python: Path, auto_yes: bool = False) -> bool:
    """Check if pytest-cov is installed in the target environment; offer to install if missing."""
    try:
        res = subprocess.run(
            [str(test_python), "-c", "import pytest_cov"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return True
    except Exception:
        pass

    console.print("[yellow]pytest-cov is not installed in the target environment.[/yellow]")
    install = False
    if auto_yes:
        install = True
    else:
        # Ask interactively if running in a TTY
        if sys.stdin.isatty():
            ans = input("pytest-cov is required for test coverage tracking. Install it into target environment? [Y/n]: ")
            if ans.strip().lower() in ("y", "yes", ""):
                install = True
        else:
            console.print("[dim]Non-interactive environment and --yes not specified; skipping pytest-cov install.[/dim]")

    if install:
        console.print(f"[cyan]Installing pytest-cov using {test_python}...[/cyan]")
        try:
            res = subprocess.run(
                [str(test_python), "-m", "pip", "install", "pytest-cov"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode == 0:
                console.print("[green]pytest-cov installed successfully.[/green]")
                return True
            else:
                console.print(f"[red]Failed to install pytest-cov:[/red] {res.stderr}")
        except Exception as err:
            console.print(f"[red]Error installing pytest-cov:[/red] {err}")

    return False


def setup_backend(
    repo_path: Path,
    preference: str | None = None,
) -> tuple[GraphBackend, str]:
    """Start and configure backend for repository."""
    graph_name = get_repo_graph_name(repo_path)
    backend = resolve_backend(preference=preference, repo_path=repo_path, autostart=True)

    desc = backend.describe()
    console.print(f"[bold green]Backend selected:[/bold green] [cyan]{backend.name}[/cyan] ({desc.get('status') or desc.get('connection_str') or desc.get('data_path')})")

    # Store in .guard/config.toml
    cfg = {
        "backend": {
            "type": backend.name,
            "host": desc.get("host", "localhost"),
            "port": desc.get("port", 6379),
            "graph_name": graph_name,
        }
    }
    save_config(repo_path, cfg)
    return backend, graph_name


def run_static_ingest(
    repo_path: Path,
    graph_name: str,
    backend: GraphBackend,
    commit_sha: str | None = None,
) -> Any:
    """Analyze static repository structure and ingest into FalkorDB."""
    from guard_cli.ingest.static import analyze_repo
    from guard_cli import db

    console.print(f"[cyan]Parsing static call graph for repository '{repo_path.name}'...[/cyan]")
    res = analyze_repo(repo_path, include_tests=True)

    g = backend.get_graph(graph_name)
    db.reset_graph(g)
    g = backend.get_graph(graph_name)
    db.ensure_schema(g)
    db.write_static(g, res, commit_sha=commit_sha)

    counts = db.get_schema_counts(g)
    console.print(
        f"[green]Static graph ingested:[/green] "
        f"{counts.get('File', 0)} files, {counts.get('Function', 0)} functions, "
        f"{counts.get('Test', 0)} tests, {counts.get('CALLS', 0)} calls."
    )
    return res


def run_baseline_and_coverage(
    repo_path: Path,
    graph_name: str,
    test_python: Path,
    skip_coverage: bool = False,
    runs_requested: int | None = None,
    auto_yes: bool = False,
    commit_sha: str | None = None,
) -> None:
    """Execute baseline suite and per-test coverage ingestion."""
    if skip_coverage:
        console.print("[dim]Skipping coverage ingestion as requested (--skip-coverage).[/dim]")
        return

    # 1. Baseline timing run
    console.print(f"[cyan]Running single baseline test run with {test_python.name}...[/cyan]")
    start = time.time()
    proc = subprocess.run(
        [str(test_python), "-m", "pytest", "-q"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=180,
    )
    baseline_dur = time.time() - start

    failing_tests: list[str] = []
    if proc.returncode != 0:
        for line in proc.stdout.splitlines():
            if line.startswith("FAILED "):
                t_name = line.split()[1]
                failing_tests.append(t_name)
        if failing_tests:
            console.print(
                f"[yellow]Warning: {len(failing_tests)} tests failed during baseline run. "
                "These will be excluded from coverage evidence to avoid poisoning the graph.[/yellow]"
            )

    # Determine num_runs
    if runs_requested is not None:
        runs = runs_requested
    elif auto_yes:
        runs = 3 if baseline_dur < 10.0 else 1
    else:
        if sys.stdin.isatty():
            est_3 = baseline_dur * 3
            ans = input(f"Baseline run took {baseline_dur:.1f}s. A 3-run flake baseline will take ~{est_3:.1f}s. Run 3 runs? [y/N]: ")
            runs = 3 if ans.strip().lower() in ("y", "yes") else 1
        else:
            runs = 1

    console.print(f"[cyan]Ingesting per-test coverage ({runs} run(s))...[/cyan]")
    from guard_cli.ingest.coverage import ingest_coverage

    ingest_coverage(
        repo_path=repo_path,
        graph_name=graph_name,
        commit_sha=commit_sha,
        num_runs=runs,
        python_exe=str(test_python),
    )
    console.print("[green]Per-test coverage successfully ingested into graph.[/green]")
    return baseline_dur


def record_state(
    repo_path: Path,
    graph_name: str,
    backend: GraphBackend,
    commit_sha: str | None = None,
    baseline_duration_s: float | None = None,
) -> dict[str, Any]:
    """Record current git HEAD SHA, ingestion timestamp, and baseline run duration in graph and .guard/state.json."""
    if commit_sha is None:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            commit_sha = res.stdout.strip() if res.returncode == 0 else "unknown"
        except Exception:
            commit_sha = "unknown"

    ts = datetime.now(timezone.utc).isoformat()

    # Record in graph
    try:
        g = backend.get_graph(graph_name)
        g.query(
            """MERGE (s:RepoState {graph: $graph})
               SET s.head_sha = $sha, s.ingested_at = $ts""",
            {"graph": graph_name, "sha": commit_sha, "ts": ts},
        )
    except Exception:
        pass

    state_data = {
        "head_sha": commit_sha,
        "ingested_at": ts,
        "graph_name": graph_name,
        "repo_path": str(repo_path),
    }
    if baseline_duration_s is not None:
        state_data["baseline_duration_s"] = round(baseline_duration_s, 2)

    guard_dir = repo_path / ".guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    state_file = guard_dir / "state.json"
    state_file.write_text(json.dumps(state_data, indent=2) + "\n", encoding="utf-8")
    return state_data


def write_integrations(repo_path: Path, agents: list[str]) -> list[Path]:
    """Safely update .gitignore, .claude/settings.json, AGENTS.md, and CLAUDE.md."""
    modified_files: list[Path] = []

    # 1. Update .gitignore
    gitignore = repo_path / ".gitignore"
    current_content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines_to_add: list[str] = []
    if ".guard/" not in current_content and ".guard" not in current_content:
        lines_to_add.append(".guard/")
    if ("antigravity" in agents or "agy" in agents) and ".agents/hooks.json" not in current_content and ".agents/" not in current_content:
        lines_to_add.append(".agents/hooks.json")

    if lines_to_add:
        new_content = current_content.rstrip() + ("\n" if current_content.strip() else "") + "\n".join(lines_to_add) + "\n"
        gitignore.write_text(new_content, encoding="utf-8")
        modified_files.append(gitignore)

    # 2. Install Claude Code Stop hook and settings via claude integration
    if "claude" in agents:
        from guard_cli.integrations import claude
        ok, msg = claude.install(repo_path=repo_path, shared=False)
        settings_file = claude.get_settings_path(repo_path=repo_path, shared=False)
        if settings_file.exists() and settings_file not in modified_files:
            modified_files.append(settings_file)

    # 3. Install Antigravity CLI Stop hook via antigravity integration
    if "antigravity" in agents or "agy" in agents:
        from guard_cli.integrations import antigravity
        ok, msg = antigravity.install(repo_path=repo_path)
        hooks_file = antigravity.get_hooks_file_path(repo_path=repo_path)
        if hooks_file.exists() and hooks_file not in modified_files:
            modified_files.append(hooks_file)

    # 4. Update AGENTS.md and CLAUDE.md idempotently
    doc_targets = ["AGENTS.md"]
    if "claude" in agents:
        doc_targets.append("CLAUDE.md")

    for doc_name in doc_targets:
        doc_path = repo_path / doc_name
        if doc_path.exists():
            text = doc_path.read_text(encoding="utf-8")
            if INTEGRATION_MARKER_START in text and INTEGRATION_MARKER_END in text:
                # Replace marked block in-place
                prefix = text.split(INTEGRATION_MARKER_START)[0]
                suffix = text.split(INTEGRATION_MARKER_END)[1]
                updated = prefix.rstrip() + "\n\n" + GUARD_INSTRUCTIONS_BLOCK + "\n" + suffix.lstrip()
            else:
                updated = text.rstrip() + "\n\n" + GUARD_INSTRUCTIONS_BLOCK + "\n"
        else:
            updated = f"# {repo_path.name}\n\n{GUARD_INSTRUCTIONS_BLOCK}\n"

        doc_path.write_text(updated, encoding="utf-8")
        modified_files.append(doc_path)

    return modified_files


def run_init(
    repo_path: str | Path | None = None,
    backend_preference: str | None = None,
    skip_coverage: bool = False,
    auto_yes: bool = False,
    agents: str = "claude,cursor,codex,antigravity",
    runs: int | None = None,
) -> int:
    """Execute complete guard init workflow."""
    console.rule("[bold cyan]Guard Repository Initialization[/bold cyan]")

    # Step 1: Find repo
    root = find_repo_root(repo_path)
    console.print(f"[bold]Target Repository:[/bold] {root}")

    # Step 2: Find test environment
    test_python = find_test_environment(root)
    console.print(f"[bold]Target Python Environment:[/bold] {test_python}")

    # Step 3: Check pytest-cov
    cov_available = check_pytest_cov(test_python, auto_yes=auto_yes)
    if not cov_available:
        skip_coverage = True

    # Step 4: Backend setup
    backend, graph_name = setup_backend(root, preference=backend_preference)

    # Step 5: Static ingest
    run_static_ingest(root, graph_name, backend)

    # Step 6 & 7: Baseline and coverage ingest
    baseline_dur = run_baseline_and_coverage(
        root,
        graph_name,
        test_python,
        skip_coverage=skip_coverage,
        runs_requested=runs,
        auto_yes=auto_yes,
    )

    # Step 8: Record state
    state = record_state(root, graph_name, backend, baseline_duration_s=baseline_dur)
    console.print(f"[green]Recorded state:[/green] commit [bold]{state['head_sha'][:7]}[/bold] at {state['ingested_at']}")

    # Step 9: Write integrations
    agent_list = [a.strip().lower() for a in agents.split(",") if a.strip()]
    modified = write_integrations(root, agent_list)
    console.print(f"[green]Configured integrations for:[/green] {', '.join(agent_list)}")
    for m in modified:
        console.print(f"  - Updated: [dim]{m.relative_to(root)}[/dim]")

    console.rule("[bold green]Initialization Complete[/bold green]")
    console.print("Run [bold cyan]guard doctor[/bold cyan] to verify system health.")
    return 0
