"""Unit tests verifying test file pattern detection in thin slice.

Ensures words like 'attestation.py' or 'contest.py' do NOT trigger
test_files_touched, while 'tests/test_calc.py' and 'calc_test.py' DO.
"""
import pytest
from guard_cli.thin_slice import is_test_file, thin_slice


def test_is_test_file_negative_cases():
    """Ensure non-test files containing the substring 'test' are NOT detected as test files."""
    negative_cases = [
        "attestation.py",
        "contest.py",
        "fastest_path.py",
        "contest/models.py",
        "pkg/attestation_service.py",
        "latest_results.py",
        "detest.py",
    ]
    for path in negative_cases:
        assert not is_test_file(path), f"Expected '{path}' NOT to be recognized as a test file"


def test_is_test_file_positive_cases():
    """Ensure actual test files ARE recognized as test files."""
    positive_cases = [
        "tests/test_calc.py",
        "calc_test.py",
        "test_calc.py",
        "tests/calc.py",
        "tests/conftest.py",
        "src/tests/test_calc.py",
        "pkg/subpkg/calc_test.py",
        "test/test_app.py",
    ]
    for path in positive_cases:
        assert is_test_file(path), f"Expected '{path}' to be recognized as a test file"


def test_thin_slice_test_files_touched_not_triggered_by_attestation(tmp_path):
    """Ensure a diff touching attestation.py does NOT trigger test_files_touched fallback."""
    diff_text = """diff --git a/attestation.py b/attestation.py
--- a/attestation.py
+++ b/attestation.py
@@ -1,3 +1,3 @@
-def verify(): pass
+def verify(): return True
"""
    # Run thin_slice with this diff
    result = thin_slice(
        repo_path=tmp_path,
        diff_text=diff_text,
    )
    # If fallback occurs, it should NOT be because test files were touched
    if result.is_fallback and result.fallback_reason:
        assert "test files" not in result.fallback_reason.lower()


def test_thin_slice_test_files_touched_not_triggered_by_contest(tmp_path):
    """Ensure a diff touching contest.py does NOT trigger test_files_touched fallback."""
    diff_text = """diff --git a/contest.py b/contest.py
--- a/contest.py
+++ b/contest.py
@@ -1,3 +1,3 @@
-def run_contest(): pass
+def run_contest(): return 1
"""
    result = thin_slice(
        repo_path=tmp_path,
        diff_text=diff_text,
    )
    if result.is_fallback and result.fallback_reason:
        assert "test files" not in result.fallback_reason.lower()


def test_thin_slice_test_files_touched_triggered_by_test_file(tmp_path):
    """Ensure a diff touching tests/test_calc.py or calc_test.py DOES trigger test_files_touched fallback."""
    diff_text = """diff --git a/tests/test_calc.py b/tests/test_calc.py
--- a/tests/test_calc.py
+++ b/tests/test_calc.py
@@ -1,3 +1,3 @@
-def test_add(): pass
+def test_add(): assert True
"""
    result = thin_slice(
        repo_path=tmp_path,
        diff_text=diff_text,
    )
    assert result.is_fallback is True
    assert result.fallback_reason is not None
    assert "test files" in result.fallback_reason.lower()


def test_thin_slice_test_files_touched_triggered_by_calc_test(tmp_path):
    """Ensure a diff touching calc_test.py DOES trigger test_files_touched fallback."""
    diff_text = """diff --git a/calc_test.py b/calc_test.py
--- a/calc_test.py
+++ b/calc_test.py
@@ -1,3 +1,3 @@
-def test_calc(): pass
+def test_calc(): assert True
"""
    result = thin_slice(
        repo_path=tmp_path,
        diff_text=diff_text,
    )
    assert result.is_fallback is True
    assert result.fallback_reason is not None
    assert "test files" in result.fallback_reason.lower()

