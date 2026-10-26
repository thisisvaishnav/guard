"""Tests for SQLiteGraphStore implementation."""
from __future__ import annotations

from pathlib import Path
from guard_cli.store.sqlite import SQLiteGraphStore
from guard_cli.ingest.static import StaticResult, FuncDef


def test_sqlite_store_lifecycle_and_static_ingest(tmp_path: Path):
    db_file = tmp_path / "graph.db"
    store = SQLiteGraphStore(db_file)
    store.ensure_schema()

    # Create dummy static result
    result = StaticResult(
        files=["src/app.py", "tests/test_app.py"],
        funcs=[
            FuncDef(
                id="src/app.py::main",
                file="src/app.py",
                qualname="main",
                name="main",
                start=1,
                end=10,
                cls=None,
                dynamic=False,
            ),
            FuncDef(
                id="src/app.py::helper",
                file="src/app.py",
                qualname="helper",
                name="helper",
                start=12,
                end=20,
                cls=None,
                dynamic=True,
            ),
            FuncDef(
                id="tests/test_app.py::test_main",
                file="tests/test_app.py",
                qualname="test_main",
                name="test_main",
                start=1,
                end=5,
                cls=None,
                dynamic=False,
            ),
        ],
        call_edges={("src/app.py::main", "src/app.py::helper")},
        import_edges={("src/app.py", "os")},
    )

    store.write_static(result, commit_sha="abc1234")

    counts = store.get_schema_counts()
    assert counts["File"] == 2
    assert counts["Function"] == 2  # excludes test func
    assert counts["Test"] == 1
    assert counts["CALLS"] == 1
    assert counts["IMPORTS"] == 1
    assert counts["dynamic_functions"] == 1

    # Check function lookup
    funcs = store.get_functions_for_file("src/app.py")
    assert len(funcs) == 2
    f_main = next(f for f in funcs if f.name == "main")
    assert f_main.start == 1
    assert f_main.end == 10
    assert not f_main.has_dynamic_dispatch

    f_helper = next(f for f in funcs if f.name == "helper")
    assert f_helper.has_dynamic_dispatch


def test_sqlite_coverage_and_multi_hop(tmp_path: Path):
    db_file = tmp_path / "graph.db"
    store = SQLiteGraphStore(db_file)
    store.ensure_schema()

    # Set up calls: A -> B -> C
    result = StaticResult(
        files=["src/a.py"],
        funcs=[
            FuncDef(id="fn_A", file="src/a.py", qualname="A", name="A", start=1, end=5, cls=None),
            FuncDef(id="fn_B", file="src/a.py", qualname="B", name="B", start=6, end=10, cls=None),
            FuncDef(id="fn_C", file="src/a.py", qualname="C", name="C", start=11, end=15, cls=None),
            FuncDef(id="tests/test_a.py::test_c", file="tests/test_a.py", qualname="test_c", name="test_c", start=1, end=5, cls=None),
        ],
        call_edges={("fn_A", "fn_B"), ("fn_B", "fn_C")},
    )
    store.write_static(result, commit_sha="sha1")

    # Write coverage: fn_C is covered by test_c
    store.write_coverage([{"func": "fn_C", "test": "tests/test_a.py::test_c"}], confidence=0.95)

    # 1-hop direct coverage for fn_C
    direct = store.get_covering_tests("fn_C", min_confidence=0.8)
    assert len(direct) == 1
    assert direct[0].test_id == "tests/test_a.py::test_c"
    assert direct[0].confidence == 0.95

    # fn_A has no direct coverage
    assert len(store.get_covering_tests("fn_A")) == 0

    # 2-hop coverage: A -> B -> C is 2 hops away!
    multi = store.get_multi_hop_tests("fn_A", max_depth=2, min_confidence=0.8)
    assert len(multi) == 1
    assert multi[0].test_id == "tests/test_a.py::test_c"

    # Multi-hop with max_depth=1 should NOT reach C from A
    multi_1 = store.get_multi_hop_tests("fn_A", max_depth=1, min_confidence=0.8)
    assert len(multi_1) == 0


def test_sqlite_miss_repair(tmp_path: Path):
    db_file = tmp_path / "graph.db"
    store = SQLiteGraphStore(db_file)
    store.ensure_schema()

    # Function starts with no_evidence=True
    result = StaticResult(
        files=["src/calc.py"],
        funcs=[
            FuncDef(id="src/calc.py::add", file="src/calc.py", qualname="add", name="add", start=1, end=5, cls=None),
        ],
    )
    store.write_static(result)
    store.set_function_evidence_flags(covered_ids=[], uncovered_ids=["src/calc.py::add"])

    fn_before = store.get_functions_for_file("src/calc.py")[0]
    assert fn_before.no_evidence is True

    # Record missed test
    rep = store.record_miss_repair("src/calc.py::add", "tests/test_calc.py::test_add", new_confidence=1.0)
    assert rep["status"] == "repaired"
    assert rep["new_confidence"] == 1.0

    # Verify no_evidence is now False
    fn_after = store.get_functions_for_file("src/calc.py")[0]
    assert fn_after.no_evidence is False

    # Verify covering test is returned with 1.0 confidence
    cov = store.get_covering_tests("src/calc.py::add")
    assert len(cov) == 1
    assert cov[0].confidence == 1.0
    assert cov[0].source == "miss_repair"
