"""Unit tests for coverage ingestion module (Task T4)."""
import pytest
from pathlib import Path
from guard_cli import db
from guard_cli.ingest.coverage import (
    normalize_test_id,
    compute_flakiness,
    read_coverage_contexts,
    RunResult,
    CoverageResult,
    _write_to_falkordb,
)
from guard_cli.ingest.static import StaticResult, FuncDef


def test_normalize_test_id():
    # Simple test
    assert normalize_test_id("tests/test_basic.py::test_simple") == "tests/test_basic.py::test_simple"
    # Parameterized test
    assert normalize_test_id("tests/test_basic.py::test_method[get]") == "tests/test_basic.py::test_method"
    assert normalize_test_id("tests/test_basic.py::test_multi[foo-bar-123]") == "tests/test_basic.py::test_multi"
    # Class method
    assert normalize_test_id("tests/test_cli.py::TestRoutes::test_list") == "tests/test_cli.py::TestRoutes.test_list"
    # Class method parameterized
    assert normalize_test_id("tests/test_cli.py::TestRoutes::test_list[json]") == "tests/test_cli.py::TestRoutes.test_list"


def test_compute_flakiness():
    runs = [
        RunResult(
            id="r1", timestamp="t1", duration_ms=10.0, total_tests=3, passed=2, failed=1, failures=[],
            test_outcomes={"t_stable": "passed", "t_fail": "failed", "t_flaky": "passed"},
        ),
        RunResult(
            id="r2", timestamp="t2", duration_ms=10.0, total_tests=3, passed=1, failed=2, failures=[],
            test_outcomes={"t_stable": "passed", "t_fail": "failed", "t_flaky": "failed"},
        ),
        RunResult(
            id="r3", timestamp="t3", duration_ms=10.0, total_tests=3, passed=2, failed=1, failures=[],
            test_outcomes={"t_stable": "passed", "t_fail": "failed", "t_flaky": "passed"},
        ),
    ]

    flake_rates, flaky_tests = compute_flakiness(runs)

    assert flake_rates["t_stable"] == 0.0
    assert flake_rates["t_fail"] == 0.0  # Consistently failing is not flaky
    assert "t_flaky" in flaky_tests
    assert flake_rates["t_flaky"] == round(1 / 3, 3)


@pytest.fixture
def clean_test_graph():
    backend = db.get_backend()
    if not backend.is_healthy():
        pytest.skip("FalkorDB server is not reachable")
    try:
        g = db.get_graph("guard_cov_test", backend=backend)
        db.reset_graph(g)
        g = db.get_graph("guard_cov_test", backend=backend)
        db.ensure_schema(g)
    except Exception as exc:
        pytest.skip(f"FalkorDB server error: {exc}")
    yield g
    try:
        db.reset_graph(g)
    except Exception:
        pass


def test_coverage_write_to_graph(clean_test_graph):
    g = clean_test_graph
    # Setup test file, functions, and tests
    sr = StaticResult(
        files=["pkg/mod.py", "tests/test_mod.py"],
        funcs=[
            FuncDef(id="pkg/mod.py::covered_fn", file="pkg/mod.py", qualname="covered_fn", name="covered_fn", start=1, end=5, cls=None),
            FuncDef(id="pkg/mod.py::uncovered_fn", file="pkg/mod.py", qualname="uncovered_fn", name="uncovered_fn", start=7, end=12, cls=None),
            FuncDef(id="tests/test_mod.py::test_covered", file="tests/test_mod.py", qualname="test_covered", name="test_covered", start=1, end=4, cls=None),
            FuncDef(id="tests/test_mod.py::test_flaky", file="tests/test_mod.py", qualname="test_flaky", name="test_flaky", start=6, end=9, cls=None),
        ],
    )
    db.write_static(g, sr)

    run = RunResult(
        id="run_test_1",
        timestamp="2026-10-16T12:00:00Z",
        duration_ms=150.0,
        total_tests=2,
        passed=2,
        failed=0,
        failures=[],
        test_outcomes={"tests/test_mod.py::test_covered": "passed", "tests/test_mod.py::test_flaky": "passed"},
    )

    cov_res = CoverageResult(
        coverage_pairs=[{"func": "pkg/mod.py::covered_fn", "test": "tests/test_mod.py::test_covered"}],
        covered_functions={"pkg/mod.py::covered_fn"},
        uncovered_functions={"pkg/mod.py::uncovered_fn"},
        flaky_tests={"tests/test_mod.py::test_flaky"},
        test_flake_rates={"tests/test_mod.py::test_covered": 0.0, "tests/test_mod.py::test_flaky": 0.33},
        runs=[run],
    )

    _write_to_falkordb(g, cov_res, commit_sha="cov_sha")

    # Verify Run node
    runs = g.query("MATCH (r:Run) RETURN r.id, r.passed").result_set
    assert len(runs) == 1
    assert runs[0][0] == "run_test_1"

    # Verify flake_rate on Test nodes
    tests = g.query("MATCH (t:Test) RETURN t.id, t.flake_rate ORDER BY t.id").result_set
    test_rates = {t[0]: t[1] for t in tests}
    assert test_rates["tests/test_mod.py::test_covered"] == 0.0
    assert test_rates["tests/test_mod.py::test_flaky"] == 0.33

    # Verify COVERED_BY edge
    edges = g.query(
        "MATCH (f:Function)-[e:COVERED_BY]->(t:Test) RETURN f.id, t.id, e.confidence, e.source"
    ).result_set
    assert len(edges) == 1
    assert edges[0][0] == "pkg/mod.py::covered_fn"
    assert edges[0][1] == "tests/test_mod.py::test_covered"
    assert edges[0][2] == 0.9
    assert edges[0][3] == "coverage"

    # Verify no_evidence flags on Functions
    covered_flag = g.query("MATCH (f:Function {id: 'pkg/mod.py::covered_fn'}) RETURN f.no_evidence").result_set
    assert covered_flag[0][0] is False

    uncovered_flag = g.query("MATCH (f:Function {id: 'pkg/mod.py::uncovered_fn'}) RETURN f.no_evidence").result_set
    assert uncovered_flag[0][0] is True
