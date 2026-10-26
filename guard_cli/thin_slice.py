"""Thin slice test selection algorithm for Guard.

Core logic:
1. Parse diff to find changed lines per file.
2. Query graph for functions covering changed lines.
3. If ANY changed function has no_evidence=true (safe mode), fall back to run-all.
4. If ANY changed function has has_dynamic_dispatch=true, widen to all tests in file.
5. Trace COVERED_BY edges (confidence >= 0.8) to collect tests.
6. Trace incoming CALLS edges (up to 2 hops) to find upstream callers.
7. Return CheckResult with selected tests or fallback reason.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from guard_cli import db
from guard_cli.store.base import FunctionNode


@dataclass
class ChangedFunction:
    id: str
    file: str
    name: str
    start: int
    end: int
    has_dynamic_dispatch: bool = False
    no_evidence: bool = False
    covering_tests: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    status: str  # "select" | "run-all"
    is_fallback: bool
    fallback_reason: str | None = None
    changed_functions: list[str] = field(default_factory=list)
    selected_tests: list[str] = field(default_factory=list)
    graph_state: dict[str, Any] = field(default_factory=dict)
    timing_ms: float = 0.0

    @property
    def execution_time_ms(self) -> float:
        return self.timing_ms


def parse_unified_diff(diff_text: str) -> dict[str, set[int]]:
    """Parse unified diff text into a dict of {file_path: {line_numbers}}."""
    result: dict[str, set[int]] = {}
    current_file: str | None = None
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            raw_path = line[6:].strip()
            # Normalize path: strip quotes if git diff quoted them
            current_file = raw_path.strip('"')
            result.setdefault(current_file, set())
        elif line.startswith("+++ /dev/null"):
            current_file = None
        elif line.startswith("@@ ") and current_file:
            m = hunk_re.match(line)
            if m:
                new_start = int(m.group(1))
                new_len = int(m.group(2)) if m.group(2) is not None else 1
                current_line = new_start
        elif current_file and "current_line" in locals():
            if line.startswith("+") and not line.startswith("+++"):
                result[current_file].add(current_line)
                current_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                # Deleted line: mark current line position as changed
                result[current_file].add(max(1, current_line))
            elif line.startswith(" "):
                current_line += 1

    return result


def is_test_file(path: str) -> bool:
    """Return True if path matches standard test file patterns."""
    p = path.lower()
    return (
        "/tests/" in p
        or p.startswith("tests/")
        or "/test/" in p
        or p.startswith("test/")
        or Path(path).name.startswith("test_")
        or Path(path).name.endswith("_test.py")
    )


def resolve_changed_functions(
    g,
    file_lines: dict[str, set[int]],
) -> list[ChangedFunction]:
    """Find all functions in the graph that overlap with changed line ranges."""
    changed: list[ChangedFunction] = []
    seen: set[str] = set()

    for file_path, lines in file_lines.items():
        if not lines:
            continue

        # Use store method if available
        if hasattr(g, "get_functions_for_file"):
            funcs = g.get_functions_for_file(file_path)
        else:
            norm_path = file_path.replace("\\", "/")
            res = g.query(
                """MATCH (f:Function)
                   WHERE f.file = $path
                      OR f.file ENDS WITH $path
                      OR $path ENDS WITH f.file
                   RETURN f.id, f.file, f.name, f.start, f.end,
                          f.has_dynamic_dispatch, f.no_evidence""",
                {"path": norm_path},
            ).result_set

            funcs = []
            for row in res:
                funcs.append(
                    FunctionNode(
                        id=row[0],
                        file=row[1],
                        name=row[2],
                        qualname=row[2],
                        start=int(row[3]),
                        end=int(row[4]),
                        has_dynamic_dispatch=bool(row[5]) if row[5] is not None else False,
                        no_evidence=bool(row[6]) if row[6] is not None else False,
                    )
                )

        for fn in funcs:
            fn_id = fn.id
            if fn_id in seen:
                continue

            fn_range = set(range(fn.start, fn.end + 1))
            if lines & fn_range:
                seen.add(fn_id)
                changed.append(
                    ChangedFunction(
                        id=fn_id,
                        file=fn.file,
                        name=fn.name,
                        start=fn.start,
                        end=fn.end,
                        has_dynamic_dispatch=fn.has_dynamic_dispatch,
                        no_evidence=fn.no_evidence,
                    )
                )

    return changed


def get_callers(g, function_id: str, hops: int = 2) -> list[str]:
    """Find upstream callers of function_id up to hops distance."""
    if hasattr(g, "get_callers"):
        records = g.get_callers(function_id, hops=hops)
        return [r.caller for r in records]

    res = g.query(
        """MATCH path = (caller:Function)-[:CALLS*1..2]->(target:Function {id: $fid})
           RETURN DISTINCT caller.id""",
        {"fid": function_id},
    ).result_set
    return [r[0] for r in res if r[0] != function_id]


def get_module_tests(g, file_path: str) -> list[str]:
    """Get all tests associated with the module containing file_path."""
    if hasattr(g, "get_module_tests"):
        stem = Path(file_path).stem
        return g.get_module_tests(stem)

    mod_stem = Path(file_path).stem
    res = g.query(
        """MATCH (t:Test)
           WHERE t.id CONTAINS $stem OR t.file CONTAINS $stem
           RETURN t.id""",
        {"stem": mod_stem},
    ).result_set
    return [r[0] for r in res]


def thin_slice_decision(
    g,
    changed_functions: list[ChangedFunction],
    test_files_touched: bool = False,
    no_confidence_filter: bool = False,
    no_dynamic_widening: bool = False,
) -> CheckResult:
    """Core selection algorithm implementing safe-mode contract:

    - If test files were touched or no functions matched -> run all.
    - If ANY changed function has no_evidence=true (and not
    no_confidence_filter) -> run all.
    - Otherwise -> collect covering tests via COVERED_BY edges (with confidence
    filter unless ablated).
    - If dynamic dispatch is present and widening enabled -> include module
    tests.
    """
    if test_files_touched:
        return CheckResult(
            status="run-all",
            is_fallback=True,
            fallback_reason="Test files were modified in diff",
            changed_functions=[f.id for f in changed_functions],
            selected_tests=["tests"],
        )

    if not changed_functions:
        return CheckResult(
            status="run-all",
            is_fallback=True,
            fallback_reason="No parsed functions matched diff line changes",
            changed_functions=[],
            selected_tests=["tests"],
        )

    # In safe-mode: ANY uncovered function forces full-suite fallback
    uncovered = [f for f in changed_functions if f.no_evidence]
    if uncovered and not no_confidence_filter:
        return CheckResult(
            status="run-all",
            is_fallback=True,
            fallback_reason=f"Uncovered function has no_evidence=true: {[f.id for f in uncovered]}",
            changed_functions=[f.id for f in changed_functions],
            selected_tests=["tests"],
        )

    selected: set[str] = set()
    min_conf = 0.0 if no_confidence_filter else 0.8

    for fn in changed_functions:
        tests = db.get_covering_tests(g, fn.id, min_confidence=min_conf)
        fn.covering_tests = [t.test_id for t in tests]
        selected.update(fn.covering_tests)

        # Dynamic dispatch widening
        if fn.has_dynamic_dispatch and not no_dynamic_widening:
            mod_tests = get_module_tests(g, fn.file)
            selected.update(mod_tests)

    # Check callers up to 2 hops for additional test coverage
    for fn in changed_functions:
        callers = get_callers(g, fn.id, hops=2)
        for caller_id in callers:
            c_tests = db.get_covering_tests(g, caller_id, min_confidence=min_conf)
            selected.update(t.test_id for t in c_tests)

    if not selected:
        return CheckResult(
            status="run-all",
            is_fallback=True,
            fallback_reason=(
                f"No covering tests found above confidence {min_conf}"
            ),
            changed_functions=[f.id for f in changed_functions],
            selected_tests=["tests"],
        )

    return CheckResult(
        status="select",
        is_fallback=False,
        changed_functions=[f.id for f in changed_functions],
        selected_tests=sorted(selected),
    )


def check(
    diff_text: str | None = None,
    diff_file: Path | str | None = None,
    repo_path: Path | str | None = None,
    graph_name: str | None = None,
    no_confidence_filter: bool = False,
    no_dynamic_widening: bool = False,
    baseline_sha: str | None = None,
) -> CheckResult:
    """Entry point: parse diff, query graph, return CheckResult."""
    start_t = time.time()
    cwd = Path(repo_path) if repo_path else Path.cwd()

    if diff_file:
        diff_text = Path(diff_file).read_text(encoding="utf-8")
    elif diff_text is None:
        repo = Path(repo_path) if repo_path else Path.cwd()
        try:
            cmd = ["git", "diff", baseline_sha] if baseline_sha else ["git", "diff", "HEAD"]
            res = subprocess.run(
                cmd,
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode == 0:
                diff_text = res.stdout
            elif baseline_sha:
                res2 = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=str(repo),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                diff_text = res2.stdout
            else:
                diff_text = ""
        except Exception:
            try:
                res2 = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=str(repo),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                diff_text = res2.stdout
            except Exception as e:
                dur = (time.time() - start_t) * 1000.0
                return CheckResult(
                    status="run-all",
                    is_fallback=True,
                    fallback_reason=f"Failed to obtain git diff: {e}",
                    changed_functions=[],
                    selected_tests=["tests"],
                    timing_ms=dur,
                )

    file_lines = parse_unified_diff(diff_text) if diff_text else {}

    # Check if test files were touched
    test_files_touched = any(is_test_file(p) for p in file_lines.keys())

    # Inspect untracked files via git status --porcelain
    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if status_proc.returncode == 0:
            untracked_files = [
                line[3:].strip().strip('"')
                for line in status_proc.stdout.splitlines()
                if line.startswith("??")
            ]
            test_files_touched = test_files_touched or any(
                is_test_file(p) for p in untracked_files
            )
    except Exception:
        pass

    if (not diff_text or not diff_text.strip()) and not test_files_touched:
        dur = (time.time() - start_t) * 1000.0
        return CheckResult(
            status="select",
            is_fallback=False,
            fallback_reason="Diff is empty (clean tree)",
            changed_functions=[],
            selected_tests=[],
            timing_ms=dur,
        )

    if repo_path and (graph_name == "guard" or graph_name is None):
        try:
            from guard_cli.backend import get_repo_graph_name

            repo_graph = get_repo_graph_name(repo)
            cand = db.get_graph(repo_graph, repo_path=repo)
            counts = db.get_schema_counts(cand)
            if sum(counts.values()) > 0:
                graph_name = repo_graph
        except Exception:
            pass
    g = db.get_graph(name=graph_name, repo_path=repo_path)
    state = db.get_graph_state(g)

    changed_functions = resolve_changed_functions(g, file_lines)
    result = thin_slice_decision(
        g,
        changed_functions,
        test_files_touched=test_files_touched,
        no_confidence_filter=no_confidence_filter,
        no_dynamic_widening=no_dynamic_widening,
    )
    result.graph_state = state

    end_t = time.time()
    result.timing_ms = (end_t - start_t) * 1000.0
    return result


guard_check = check
thin_slice = check
