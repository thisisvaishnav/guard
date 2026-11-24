import pytest
from guard_cli import db
from guard_cli.ingest.static import StaticResult, FuncDef


@pytest.fixture
def test_graph():
    """Provides a fresh test graph in FalkorDB."""
    backend = db.get_backend()
    if not backend.is_healthy():
        pytest.skip("FalkorDB server is not reachable")
    try:
        g = db.get_graph("guard_test", backend=backend)
        db.reset_graph(g)
        g = db.get_graph("guard_test", backend=backend)
        db.ensure_schema(g)
    except Exception as exc:
        pytest.skip(f"FalkorDB server error: {exc}")
    yield g
    try:
        db.reset_graph(g)
    except Exception:
        pass


def test_ensure_schema_creates_indexes(test_graph):
    # Calling ensure_schema multiple times must be idempotent
    db.ensure_schema(test_graph)
    # Ensure index exists on nodes
    counts = db.get_schema_counts(test_graph)
    assert counts["File"] == 0
    assert counts["Function"] == 0
    assert counts["Test"] == 0
    assert counts["Run"] == 0


def test_write_static_creates_nodes_and_edges(test_graph):
    sr = StaticResult(
        files=["pkg/mod.py", "tests/test_mod.py"],
        funcs=[
            FuncDef(id="pkg/mod.py::func_a", file="pkg/mod.py", qualname="func_a", name="func_a", start=1, end=5, cls=None, dynamic=False),
            FuncDef(id="pkg/mod.py::func_b", file="pkg/mod.py", qualname="func_b", name="func_b", start=7, end=12, cls=None, dynamic=True),
            FuncDef(id="tests/test_mod.py::test_func_a", file="tests/test_mod.py", qualname="test_func_a", name="test_func_a", start=1, end=4, cls=None, dynamic=False),
        ],
        call_edges={("pkg/mod.py::func_b", "pkg/mod.py::func_a")},
        import_edges={("tests/test_mod.py", "pkg/mod.py")},
    )

    db.write_static(test_graph, sr, commit_sha="abc1234")
    counts = db.get_schema_counts(test_graph)

    assert counts["File"] == 2
    assert counts["Function"] == 2
    assert counts["Test"] == 1
    assert counts["dynamic_functions"] == 1
    assert counts["CALLS"] == 1
    assert counts["IMPORTS"] == 1
    assert counts["DEFINED_IN"] == 3

    # Check CALLS edge properties
    res = test_graph.query(
        "MATCH (:Function)-[e:CALLS]->(:Function) "
        "RETURN e.source, e.confidence, e.evidence_count, e.last_verified_sha"
    ).result_set
    assert len(res) == 1
    source, conf, count, sha = res[0]
    assert source == "static"
    assert conf == 0.6
    assert sha == "abc1234"


def test_write_coverage_and_query_covering_tests(test_graph):
    sr = StaticResult(
        files=["pkg/mod.py", "tests/test_mod.py"],
        funcs=[
            FuncDef(id="pkg/mod.py::calc", file="pkg/mod.py", qualname="calc", name="calc", start=1, end=10, cls=None),
            FuncDef(id="tests/test_mod.py::test_calc", file="tests/test_mod.py", qualname="test_calc", name="test_calc", start=1, end=5, cls=None),
        ],
    )
    db.write_static(test_graph, sr)

    written = db.write_coverage(
        test_graph,
        test_to_funcs={"tests/test_mod.py::test_calc": ["pkg/mod.py::calc"]},
        commit_sha="cov_sha1",
        confidence=0.9,
    )
    assert written == 1

    counts = db.get_schema_counts(test_graph)
    assert counts["COVERED_BY"] == 1

    covering = db.get_covering_tests(test_graph, "pkg/mod.py::calc")
    assert len(covering) == 1
    assert covering[0]["test_id"] == "tests/test_mod.py::test_calc"
    assert covering[0]["confidence"] == 0.9
    assert covering[0]["source"] == "coverage"


def test_write_run_and_failed_in(test_graph):
    sr = StaticResult(
        files=["tests/test_demo.py"],
        funcs=[
            FuncDef(id="tests/test_demo.py::test_fail", file="tests/test_demo.py", qualname="test_fail", name="test_fail", start=1, end=5, cls=None),
        ],
    )
    db.write_static(test_graph, sr)

    run_data = {
        "id": "run_001",
        "timestamp": "2026-10-16T12:00:00Z",
        "commit_sha": "run_sha",
        "duration_ms": 1420.5,
        "total_tests": 10,
        "passed": 9,
        "failed": 1,
    }
    failures = [{"test_id": "tests/test_demo.py::test_fail", "error": "AssertionError: 1 != 2"}]

    db.write_run(test_graph, run_data, failures=failures)

    counts = db.get_schema_counts(test_graph)
    assert counts["Run"] == 1
    assert counts["FAILED_IN"] == 1

    res = test_graph.query(
        "MATCH (t:Test)-[e:FAILED_IN]->(r:Run) "
        "RETURN t.id, r.id, e.error_message, e.source"
    ).result_set
    assert len(res) == 1
    assert res[0][0] == "tests/test_demo.py::test_fail"
    assert res[0][1] == "run_001"
    assert "AssertionError" in res[0][2]
    assert res[0][3] == "test_run"


def test_get_callers_multi_hop(test_graph):
    sr = StaticResult(
        files=["pkg/chain.py"],
        funcs=[
            FuncDef(id="pkg/chain.py::bottom", file="pkg/chain.py", qualname="bottom", name="bottom", start=1, end=3, cls=None),
            FuncDef(id="pkg/chain.py::mid", file="pkg/chain.py", qualname="mid", name="mid", start=5, end=8, cls=None),
            FuncDef(id="pkg/chain.py::top", file="pkg/chain.py", qualname="top", name="top", start=10, end=15, cls=None),
        ],
        call_edges={
            ("pkg/chain.py::top", "pkg/chain.py::mid"),
            ("pkg/chain.py::mid", "pkg/chain.py::bottom"),
        },
    )
    db.write_static(test_graph, sr)

    callers = db.get_callers(test_graph, "pkg/chain.py::bottom", hops=3)
    caller_hops = {c["caller"]: c["hops"] for c in callers}
    assert caller_hops["pkg/chain.py::mid"] == 1
    assert caller_hops["pkg/chain.py::top"] == 2
