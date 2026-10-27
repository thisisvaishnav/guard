"""Guard CLI.

Commands:
- `check`: Evaluate proposed changes and select tests.
- `run`: Execute selected tests according to trust policy.
- `hook`: Manage and run agent lifecycle hooks (e.g. Claude Code stop hook).
- `covering-tests`: Show tests covering a function.
- `callers`: Show multi-hop callers of a function.
- `feedback`: Record an escape / missed fault for graph repair.
- `ingest-static`: Ingest static AST call graph into FalkorDB.
- `ingest-coverage`: Ingest pytest-cov execution traces into FalkorDB.
- `stats`: Display graph node and relationship counts.
"""
from __future__ import annotations
import argparse
import json
import sys

from guard_cli.ingest.static import analyze_repo


def cmd_ingest_static(args) -> int:
    res = analyze_repo(args.repo, include_tests=args.include_tests)
    print(json.dumps(res.summary(), indent=2))
    for err in res.parse_errors[:5]:
        print("parse error:", err, file=sys.stderr)
    if args.dry_run:
        return 0
    from guard_cli import db

    g = db.get_graph(args.graph)
    db.reset_graph(g)
    g = db.get_graph(args.graph)
    db.ensure_schema(g)
    db.write_static(g, res, commit_sha=args.commit_sha)
    print(f"written to graph '{args.graph}'")
    return 0


def cmd_callers(args) -> int:
    from guard_cli import api

    hops = int(args.hops)
    callers = api.callers(
        args.function,
        hops=hops,
        min_confidence=float(args.min_confidence),
        graph_name=args.graph,
        strict=getattr(args, "strict", False),
    )
    for c in callers:
        print(f"{c['hops']}  {c['caller']}")
    return 0


def cmd_stats(args) -> int:
    from guard_cli import db

    g = db.get_graph(args.graph)
    counts = db.get_schema_counts(g)
    print("=== Nodes ===")
    for label in ("File", "Function", "Test", "Run"):
        print(f"{label}: {counts.get(label, 0)}")
    print("\n=== Edges ===")
    for rel in ("CALLS", "IMPORTS", "DEFINED_IN", "COVERED_BY", "FAILED_IN"):
        print(f"{rel}: {counts.get(rel, 0)}")
    print(f"\nDynamic functions: {counts.get('dynamic_functions', 0)}")
    return 0


def cmd_covering_tests(args) -> int:
    from guard_cli import api

    tests = api.covering_tests(
        args.function,
        min_confidence=float(args.min_confidence),
        graph_name=args.graph,
        strict=getattr(args, "strict", False),
    )
    for t in tests:
        print(f"[{t['confidence']:.2f}] {t['test_id']} (source: {t['source']})")
    return 0


def cmd_ingest_coverage(args) -> int:
    from guard_cli.ingest.coverage import ingest_coverage

    res = ingest_coverage(
        repo_path=args.repo,
        graph_name=args.graph,
        commit_sha=args.commit_sha,
        num_runs=args.runs,
    )
    print(json.dumps(res.summary(), indent=2))
    return 0


def cmd_check(args) -> int:
    from guard_cli import api

    res = api.check(
        diff_file=args.diff,
        repo_path=args.repo,
        graph_name=args.graph,
        strict=getattr(args, "strict", False),
    )
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Status: {res['status']}")
        print(f"Policy: {res['policy']} (Trust: {res['trust']:.2f})")
        print(f"Fallback: {res['is_fallback']}")
        if res.get("fallback_reason"):
            print(f"Reason: {res['fallback_reason']}")
        if res.get("overrides_triggered"):
            print(f"Overrides: {', '.join(res['overrides_triggered'])}")
        print(f"Changed Functions ({len(res.get('changed_functions', []))}): {res.get('changed_functions', [])}")
        print(f"Selected Tests ({len(res.get('selected_tests', []))}): {res.get('selected_tests', [])}")
    return 0


def cmd_feedback(args) -> int:
    from guard_cli import api

    res = api.report_miss(
        function_id=args.function,
        test_id=args.test,
        new_confidence=args.confidence,
        graph_name=args.graph,
        strict=getattr(args, "strict", False),
    )
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Repaired: function='{res['function']}' -> test='{res['test']}'")
        print(f"Confidence: {res.get('old_confidence', 0.0)} -> {res.get('new_confidence', 1.0)} (source: {res.get('source')})")
    return 0


def cmd_run(args) -> int:
    from guard_cli import api

    report, exit_code = api.run(
        diff_file=args.diff,
        repo_path=args.repo,
        graph_name=args.graph,
        strict=getattr(args, "strict", False),
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Status: {report['status']}")
        print(f"Policy: {report['policy']} (Trust: {report['trust']:.2f})")
        print(f"Forced Full Suite: {report.get('forced_full', False)}")
        if report.get("fallback_reason"):
            print(f"Fallback Reason: {report['fallback_reason']}")
        print(f"Tests Run ({report.get('tests_run_count', 0)}): {report.get('tests_run', [])}")
        print(f"Passed: {report.get('tests_passed', False)} in {report.get('duration_s', 0.0)}s")
        if report.get("failures"):
            print(f"Failures ({len(report['failures'])}): {report['failures']}")
        if report.get("output_summary"):
            print(f"Summary: {report['output_summary']}")
    return exit_code


def cmd_hook_stop(args) -> int:
    from guard_cli.hook import run_stop_hook
    return run_stop_hook(
        repo_override=args.repo,
        strict=getattr(args, "strict", False),
    )


def cmd_hook_session_start(args) -> int:
    from guard_cli.hook import run_session_start_hook
    return run_session_start_hook(repo_override=args.repo)


def cmd_hook_install(args) -> int:
    if getattr(args, "antigravity", False):
        from guard_cli.integrations import antigravity
        ok, msg = antigravity.install(repo_path=args.repo)
    else:
        from guard_cli.integrations import claude
        ok, msg = claude.install(repo_path=args.repo, shared=args.shared)
    print(msg)
    return 0 if ok else 1


def cmd_hook_uninstall(args) -> int:
    if getattr(args, "antigravity", False):
        from guard_cli.integrations import antigravity
        ok, msg = antigravity.uninstall(repo_path=args.repo)
    else:
        from guard_cli.integrations import claude
        ok, msg = claude.uninstall(repo_path=args.repo, shared=args.shared)
    print(msg)
    return 0 if ok else 1


def cmd_hook_status(args) -> int:
    from guard_cli.integrations import claude, antigravity
    if getattr(args, "antigravity", False):
        stat = {"antigravity": antigravity.status(repo_path=args.repo)}
    else:
        stat = {
            "claude": claude.status(repo_path=args.repo, shared=getattr(args, "shared", False)),
            "antigravity": antigravity.status(repo_path=args.repo),
        }
    print(json.dumps(stat, indent=2))
    return 0


def cmd_init(args) -> int:
    from guard_cli.init_cmd import run_init

    return run_init(
        repo_path=getattr(args, "repo", None),
        backend_preference=getattr(args, "backend", None),
        skip_coverage=getattr(args, "skip_coverage", False),
        auto_yes=getattr(args, "yes", False),
        agents=getattr(args, "agents", "claude,cursor,codex,antigravity"),
        runs=getattr(args, "runs", None),
    )


def cmd_doctor(args) -> int:
    from guard_cli.doctor_cmd import run_doctor

    return run_doctor(
        repo_path=getattr(args, "repo", None),
        json_mode=getattr(args, "json", False),
        fix_mode=getattr(args, "fix", False),
    )


def main(argv=None) -> int:
    import guard_cli

    p = argparse.ArgumentParser(prog="guard")
    p.add_argument("-v", "--version", action="version", version=f"guard {guard_cli.__version__}")
    p.add_argument("--graph", default=None, help="FalkorDB graph name (defaults to repository graph from .guard/config.toml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ini = sub.add_parser("init", help="Initialize Guard for repository")
    ini.add_argument("repo", nargs="?", default=None, help="target repository path (default: current directory)")
    ini.add_argument("--backend", choices=["sqlite", "server", "docker", "embedded"], default=None, help="database backend")
    ini.add_argument("--skip-coverage", action="store_true", help="skip per-test coverage ingestion")
    ini.add_argument("-y", "--yes", action="store_true", help="non-interactive mode accepting all defaults")
    ini.add_argument("--agents", default="claude,cursor,codex,antigravity", help="comma-separated agents to configure")
    ini.add_argument("--runs", type=int, default=None, help="number of baseline test runs (1 or 3)")
    ini.set_defaults(fn=cmd_init)

    doc = sub.add_parser("doctor", help="Check Guard system health and diagnostics")
    doc.add_argument("repo", nargs="?", default=None, help="target repository path (default: current directory)")
    doc.add_argument("--json", action="store_true", help="output structured JSON")
    doc.add_argument("--fix", action="store_true", help="attempt automated repairs for warnings/failures")
    doc.set_defaults(fn=cmd_doctor)

    rn = sub.add_parser("run")
    rn.add_argument("--diff", default=None, help="path to unified diff file")
    rn.add_argument("--repo", default=None, help="path to target repo")
    rn.add_argument("--json", action="store_true", help="output JSON")
    rn.add_argument("--strict", action="store_true", help="fail closed on guard error")
    rn.set_defaults(fn=cmd_run)

    chk = sub.add_parser("check")
    chk.add_argument("--diff", default=None, help="path to unified diff file")
    chk.add_argument("--repo", default=None, help="path to repo to run git diff HEAD")
    chk.add_argument("--json", action="store_true", help="output JSON")
    chk.add_argument("--strict", action="store_true", help="fail closed on guard error")
    chk.set_defaults(fn=cmd_check)

    hk = sub.add_parser("hook", help="Agent hook management")
    hk_sub = hk.add_subparsers(dest="hook_cmd", required=True)

    hk_stop = hk_sub.add_parser("stop", help="Run Claude Code Stop hook adapter")
    hk_stop.add_argument("--repo", default=None, help="path to repo root")
    hk_stop.add_argument("--strict", action="store_true", help="fail closed on error")
    hk_stop.set_defaults(fn=cmd_hook_stop)

    hk_start = hk_sub.add_parser("session-start", help="Record baseline SHA at session start (Claude Code SessionStart / Antigravity PreInvocation)")
    hk_start.add_argument("--repo", default=None, help="path to repo root")
    hk_start.set_defaults(fn=cmd_hook_session_start)

    hk_inst = hk_sub.add_parser("install", help="Install Stop hook into agent settings (Claude Code by default, Antigravity with --antigravity)")
    hk_inst.add_argument("--repo", default=None, help="path to repo root")
    hk_inst.add_argument("--shared", action="store_true", help="install to settings.json instead of settings.local.json")
    hk_inst.add_argument("--antigravity", action="store_true", help="install to Antigravity .agents/hooks.json instead of Claude Code settings")
    hk_inst.set_defaults(fn=cmd_hook_install)

    hk_uninst = hk_sub.add_parser("uninstall", help="Uninstall Stop hook from agent settings (Claude Code by default, Antigravity with --antigravity)")
    hk_uninst.add_argument("--repo", default=None, help="path to repo root")
    hk_uninst.add_argument("--shared", action="store_true", help="uninstall from settings.json instead of settings.local.json")
    hk_uninst.add_argument("--antigravity", action="store_true", help="uninstall from Antigravity .agents/hooks.json instead of Claude Code settings")
    hk_uninst.set_defaults(fn=cmd_hook_uninstall)

    hk_stat = hk_sub.add_parser("status", help="Check hook installation status (Claude Code by default, Antigravity with --antigravity)")
    hk_stat.add_argument("--repo", default=None, help="path to repo root")
    hk_stat.add_argument("--shared", action="store_true", help="check settings.json instead of settings.local.json")
    hk_stat.add_argument("--antigravity", action="store_true", help="check Antigravity .agents/hooks.json instead of Claude Code settings")
    hk_stat.set_defaults(fn=cmd_hook_status)

    fb = sub.add_parser("feedback")
    fb.add_argument("--function", required=True, help="Function ID where fault was missed")
    fb.add_argument("--test", required=True, help="Test ID that failed and was missed")
    fb.add_argument("--confidence", default=1.0, type=float, help="Confidence of repair edge (default: 1.0)")
    fb.add_argument("--json", action="store_true", help="output JSON")
    fb.add_argument("--strict", action="store_true", help="fail closed on guard error")
    fb.set_defaults(fn=cmd_feedback)

    s = sub.add_parser("ingest-static")
    s.add_argument("repo")
    s.add_argument("--dry-run", action="store_true", help="parse only, no database")
    s.add_argument("--include-tests", action="store_true")
    s.add_argument("--commit-sha", default=None, help="commit SHA to associate with edges")
    s.set_defaults(fn=cmd_ingest_static)

    ic = sub.add_parser("ingest-coverage")
    ic.add_argument("repo")
    ic.add_argument("--runs", default=3, type=int, help="number of test runs for flake measurement")
    ic.add_argument("--commit-sha", default=None, help="commit SHA to associate with edges")
    ic.set_defaults(fn=cmd_ingest_coverage)

    c = sub.add_parser("callers")
    c.add_argument("function", help="function id, e.g. pkg/mod.py::Class.method")
    c.add_argument("--hops", default=4, type=int)
    c.add_argument("--min-confidence", default=0.0, type=float)
    c.add_argument("--strict", action="store_true", help="fail closed on error")
    c.set_defaults(fn=cmd_callers)

    st = sub.add_parser("stats")
    st.set_defaults(fn=cmd_stats)

    cov = sub.add_parser("covering-tests")
    cov.add_argument("function", help="function id, e.g. pkg/mod.py::Class.method")
    cov.add_argument("--min-confidence", default=0.0, type=float)
    cov.add_argument("--strict", action="store_true", help="fail closed on error")
    cov.set_defaults(fn=cmd_covering_tests)

    args = p.parse_args(argv)
    if not hasattr(args, "fn"):
        p.print_help()
        return 1
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
