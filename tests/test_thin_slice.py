"""Unit tests for Thin Slice (Task T5a)."""
import pytest
from pathlib import Path
from guard_cli import db
from guard_cli.thin_slice import (
    parse_unified_diff,
    resolve_changed_functions,
    thin_slice_decision,
    guard_check,
    ChangedFunction,
)
from guard_cli.ingest.static import StaticResult, FuncDef


SAMPLE_DIFF = """diff --git a/src/flask/config.py b/src/flask/config.py
--- a/src/flask/config.py
+++ b/src/flask/config.py
@@ -319,3 +319,3 @@
             if key.isupper():
                 self[key] = value
-        return True
+        return False
"""


def test_parse_unified_diff():
    file_lines = parse_unified_diff(SAMPLE_DIFF)
    assert "src/flask/config.py" in file_lines
    lines = file_lines["src/flask/config.py"]
    assert 321 in lines or 320 in lines or 319 in lines


def test_thin_slice_decision_fallback_on_no_evidence():
    changed = [
        ChangedFunction(id="pkg/mod.py::func_a", file="pkg/mod.py", name="func_a", start=1, end=10, no_evidence=True),
    ]
    res = thin_slice_decision(None, changed)
    assert res.status == "run-all"
    assert res.is_fallback is True
    assert "no_evidence" in res.fallback_reason


def test_thin_slice_decision_fallback_on_test_files_touched():
    changed = [
        ChangedFunction(id="pkg/mod.py::func_a", file="pkg/mod.py", name="func_a", start=1, end=10, no_evidence=False),
    ]
    res = thin_slice_decision(None, changed, test_files_touched=True)
    assert res.status == "run-all"
    assert res.is_fallback is True
    assert "Test files" in res.fallback_reason


@pytest.fixture
def slice_test_graph():
    backend = db.get_backend()
    if not backend.is_healthy():
        pytest.skip("FalkorDB server is not reachable")
    try:
        g = db.get_graph("guard_slice_test", backend=backend)
        db.reset_graph(g)
        g = db.get_graph("guard_slice_test", backend=backend)
        db.ensure_schema(g)
    except Exception as exc:
        pytest.skip(f"FalkorDB server error: {exc}")
    yield g
    try:
        db.reset_graph(g)
    except Exception:
        pass


def test_thin_slice_selects_covering_tests(slice_test_graph):
    g = slice_test_graph
    sr = StaticResult(
        files=["pkg/mod.py", "tests/test_mod.py"],
        funcs=[
            FuncDef(id="pkg/mod.py::calc", file="pkg/mod.py", qualname="calc", name="calc", start=1, end=10, cls=None),
            FuncDef(id="tests/test_mod.py::test_calc", file="tests/test_mod.py", qualname="test_calc", name="test_calc", start=1, end=5, cls=None),
        ],
    )
    db.write_static(g, sr)
    db.write_coverage(g, {"tests/test_mod.py::test_calc": ["pkg/mod.py::calc"]}, confidence=0.9)

    changed = [
        ChangedFunction(id="pkg/mod.py::calc", file="pkg/mod.py", name="calc", start=1, end=10, no_evidence=False),
    ]
    res = thin_slice_decision(g, changed)
    assert res.status == "select"
    assert res.is_fallback is False
    assert res.selected_tests == ["tests/test_mod.py::test_calc"]
