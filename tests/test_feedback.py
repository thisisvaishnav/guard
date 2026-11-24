"""Unit tests for feedback loop and repair edge mechanism (Task T6)."""
import pytest
from guard_cli import db
from guard_cli.feedback import record_miss
from guard_cli.ingest.static import StaticResult, FuncDef


@pytest.fixture
def feedback_test_graph():
    backend = db.get_backend()
    if not backend.is_healthy():
        pytest.skip("FalkorDB server is not reachable")
    try:
        g = db.get_graph("guard_feedback_test", backend=backend)
        db.reset_graph(g)
        g = db.get_graph("guard_feedback_test", backend=backend)
        db.ensure_schema(g)
    except Exception as exc:
        pytest.skip(f"FalkorDB server error: {exc}")
    yield g
    try:
        db.reset_graph(g)
    except Exception:
        pass


def test_record_miss_creates_repair_edge(feedback_test_graph):
    g = feedback_test_graph
    sr = StaticResult(
        files=["pkg/mod.py"],
        funcs=[
            FuncDef(id="pkg/mod.py::fn_uncovered", file="pkg/mod.py", qualname="fn_uncovered", name="fn_uncovered", start=1, end=5, cls=None),
        ],
    )
    db.write_static(g, sr)
    # Mark as no_evidence
    g.query("MATCH (f:Function {id: 'pkg/mod.py::fn_uncovered'}) SET f.no_evidence = true")

    # Record miss
    res = record_miss(g, "pkg/mod.py::fn_uncovered", "tests/test_mod.py::test_repaired", new_confidence=1.0)

    assert res["status"] == "repaired"
    assert res["old_confidence"] == 0.0
    assert res["new_confidence"] == 1.0
    assert res["source"] == "miss_repair"

    # Verify edge in graph
    edge = g.query(
        "MATCH (f:Function {id: 'pkg/mod.py::fn_uncovered'})-[e:COVERED_BY]->(t:Test {id: 'tests/test_mod.py::test_repaired'}) "
        "RETURN e.source, e.confidence, e.old_confidence"
    ).result_set
    assert len(edge) == 1
    assert edge[0][0] == "miss_repair"
    assert edge[0][1] == 1.0
    assert edge[0][2] == 0.0

    # Verify no_evidence is now false
    no_ev = g.query("MATCH (f:Function {id: 'pkg/mod.py::fn_uncovered'}) RETURN f.no_evidence").result_set
    assert no_ev[0][0] is False


def test_record_miss_elevates_existing_confidence(feedback_test_graph):
    g = feedback_test_graph
    sr = StaticResult(
        files=["pkg/mod.py", "tests/test_mod.py"],
        funcs=[
            FuncDef(id="pkg/mod.py::fn_low", file="pkg/mod.py", qualname="fn_low", name="fn_low", start=1, end=5, cls=None),
            FuncDef(id="tests/test_mod.py::test_low", file="tests/test_mod.py", qualname="test_low", name="test_low", start=1, end=4, cls=None),
        ],
    )
    db.write_static(g, sr)
    db.write_coverage(g, {"tests/test_mod.py::test_low": ["pkg/mod.py::fn_low"]}, confidence=0.6)

    # Elevate confidence
    res = record_miss(g, "pkg/mod.py::fn_low", "tests/test_mod.py::test_low", new_confidence=0.95)

    assert res["old_confidence"] == 0.6
    assert res["new_confidence"] == 0.95
    assert res["source"] == "miss_repair"
