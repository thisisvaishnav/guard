"""Automated tests for Task T5: the decision engine.

One test per hard override and per policy level, plus the queryable-reason and
frozen-parameter guarantees required by the T5 acceptance section of PLAN.md.
"""
from guard_cli.decision import (
    TRUST_MEDIUM_MIN,
    TRUST_SUBSET_MIN,
    W_CERTAINTY,
    W_EVIDENCE,
    W_FRESHNESS,
    Change,
    CoveringTest,
    FunctionEvidence,
    LEVEL_MEDIUM,
    LEVEL_RUN_ALL,
    LEVEL_SUBSET,
    compute_trust,
    decide,
    is_test_file,
    policy_for_trust,
)


def fn(function_id, tests=(), file="pkg/a.py", dyn=False, sha="new", cur_sha="new"):
    cov = tuple(CoveringTest(t, c, "coverage", sha) for t, c in tests)
    return FunctionEvidence(function_id, file, cov, dyn)


# --- hard override 1: test files touched -------------------------------------

def test_override_test_file_touched_runs_all_with_warning():
    change = Change(
        functions=(fn("pkg/a.py::f", [("tests/test_a.py::test_f", 0.9)]),),
        changed_files=("pkg/a.py", "tests/test_a.py"),
        known_tests=("tests/test_a.py::test_f", "tests/test_b.py::test_g"),
    )
    d = decide(change)
    assert d.run_all is True
    assert d.policy_level == LEVEL_RUN_ALL
    assert "test_file_touched" in d.overrides
    assert any("test files changed" in w for w in d.warnings)
    assert is_test_file("tests/test_a.py") and not is_test_file("pkg/a.py")


# --- hard override 2: no covering evidence -----------------------------------

def test_override_no_evidence_runs_all():
    change = Change(
        functions=(fn("pkg/a.py::f", tests=[]),),
        changed_files=("pkg/a.py",),
        known_tests=("tests/test_b.py::test_g",),
    )
    d = decide(change)
    assert d.run_all is True
    assert "no_evidence" in d.overrides
    assert d.selected_tests == ("tests/test_b.py::test_g",)


def test_override_no_changed_functions_runs_all():
    d = decide(Change(functions=(), changed_files=("pkg/a.py",), known_tests=("t",)))
    assert d.run_all is True
    assert "no_evidence" in d.overrides


# --- hard override 3: dynamic dispatch ---------------------------------------

def test_override_dynamic_dispatch_adds_module_tests():
    change = Change(
        functions=(fn("pkg/a.py::f", [("tests/test_a.py::test_f", 0.9)], dyn=True),),
        changed_files=("pkg/a.py",),
        known_tests=("tests/test_a.py::test_f", "tests/test_a.py::test_mod"),
        module_tests={"pkg/a.py": ("tests/test_a.py::test_mod",)},
        current_sha="new",
    )
    d = decide(change)
    assert "dynamic_dispatch" in d.overrides
    assert d.run_all is False
    assert "tests/test_a.py::test_mod" in d.selected_tests
    reason = d.explain("tests/test_a.py::test_mod")
    assert reason.status == "selected"


# --- policy levels -----------------------------------------------------------

def test_policy_level_subset_high_trust():
    change = Change(
        functions=(
            fn("pkg/a.py::f", [("tests/test_a.py::test_f", 0.9)]),
            fn("pkg/b.py::g", [("tests/test_b.py::test_g", 0.9)]),
        ),
        changed_files=("pkg/a.py", "pkg/b.py"),
        known_tests=("tests/test_a.py::test_f", "tests/test_b.py::test_g", "tests/test_c.py::test_c"),
        current_sha="new",
    )
    d = decide(change)
    assert d.policy_level == LEVEL_SUBSET
    assert d.run_all is False
    assert d.selected_tests == ("tests/test_a.py::test_f", "tests/test_b.py::test_g")


def test_policy_level_medium_mid_trust():
    change = Change(
        functions=(
            fn("pkg/a.py::f", [("tests/test_a.py::test_f", 0.6)], sha="new", cur_sha="new"),
            fn("pkg/b.py::g", [("tests/test_b.py::test_g", 0.6)], sha="old", cur_sha="new"),
        ),
        changed_files=("pkg/a.py", "pkg/b.py"),
        known_tests=("tests/test_a.py::test_f", "tests/test_b.py::test_g", "tests/test_a.py::test_mod"),
        module_tests={"pkg/a.py": ("tests/test_a.py::test_mod",)},
        current_sha="new",
    )
    d = decide(change)
    assert TRUST_MEDIUM_MIN <= d.trust < TRUST_SUBSET_MIN
    assert d.policy_level == LEVEL_MEDIUM
    assert d.run_all is False
    assert "tests/test_a.py::test_mod" in d.selected_tests


def test_policy_level_run_all_low_trust():
    change = Change(
        functions=(
            fn("pkg/a.py::f", [("tests/test_a.py::test_f", 0.4)], sha="old", cur_sha="new"),
            fn("pkg/b.py::g", [("tests/test_b.py::test_g", 0.4)], sha="old", cur_sha="new"),
        ),
        changed_files=("pkg/a.py", "pkg/b.py"),
        known_tests=("tests/test_a.py::test_f", "tests/test_c.py::test_c"),
        current_sha="new",
    )
    d = decide(change)
    assert d.trust < TRUST_MEDIUM_MIN
    assert d.policy_level == LEVEL_RUN_ALL
    assert d.run_all is True


def test_policy_threshold_boundaries():
    assert policy_for_trust(TRUST_SUBSET_MIN) == LEVEL_SUBSET
    assert policy_for_trust(TRUST_SUBSET_MIN - 1e-9) == LEVEL_MEDIUM
    assert policy_for_trust(TRUST_MEDIUM_MIN) == LEVEL_MEDIUM
    assert policy_for_trust(TRUST_MEDIUM_MIN - 1e-9) == LEVEL_RUN_ALL


# --- queryable reasons -------------------------------------------------------

def test_every_test_has_queryable_reason():
    change = Change(
        functions=(fn("pkg/a.py::f", [("tests/test_a.py::test_f", 0.9)]),),
        changed_files=("pkg/a.py",),
        known_tests=("tests/test_a.py::test_f", "tests/test_b.py::test_g"),
        current_sha="new",
    )
    d = decide(change)
    for test_id in change.known_tests:
        reason = d.explain(test_id)
        assert reason.queried_functions == ("pkg/a.py::f",)
        if reason.status == "selected":
            assert reason.evidence and 0.0 <= reason.evidence[0].confidence <= 1.0
        else:
            assert reason.evidence == ()
    assert d.reasons["tests/test_b.py::test_g"].status == "skipped"


# --- frozen parameters and trust formula -------------------------------------

def test_frozen_parameters():
    assert (W_EVIDENCE, W_FRESHNESS, W_CERTAINTY) == (0.5, 0.3, 0.2)
    assert (TRUST_SUBSET_MIN, TRUST_MEDIUM_MIN) == (0.8, 0.5)


def test_trust_formula_components():
    change = Change(
        functions=(fn("pkg/a.py::f", [("tests/test_a.py::test_f", 0.9)]),),
        current_sha="new",
    )
    trust, ev, fresh, unc = compute_trust(change)
    assert (ev, fresh, unc) == (0.9, 1.0, 0.0)
    assert abs(trust - (W_EVIDENCE * 0.9 + W_FRESHNESS * 1.0 + W_CERTAINTY * 1.0)) < 1e-9


def test_stale_edge_lowers_freshness_not_evidence():
    fresh = Change(functions=(fn("pkg/a.py::f", [("t", 0.9)], sha="new", cur_sha="new"),), current_sha="new")
    stale = Change(functions=(fn("pkg/a.py::f", [("t", 0.9)], sha="old", cur_sha="new"),), current_sha="new")
    _, ev_f, fresh_f, _ = compute_trust(fresh)
    _, ev_s, fresh_s, _ = compute_trust(stale)
    assert ev_f == ev_s == 0.9
    assert fresh_f == 1.0 and fresh_s == 0.0
