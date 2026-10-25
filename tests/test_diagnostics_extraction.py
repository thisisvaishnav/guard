import pytest
from guard_cli.api import _extract_failures, _extract_failure_summary, run
from guard_cli.hook import format_failure_summary


def test_extract_failures_captures_error_lines():
    """Verify _extract_failures captures ERROR ... lines in addition to FAILED."""
    stdout = (
        "ERROR tests/test_syntax.py - SyntaxError: invalid syntax\n"
        "ERROR tests/test_module.py::test_foo - ImportError: cannot import name 'bar'\n"
    )
    failures = _extract_failures(stdout, "")
    assert "tests/test_syntax.py" in failures
    assert "tests/test_module.py::test_foo" in failures


def test_extract_failures_captures_collection_errors():
    """Verify collection errors like 'ERROR collecting ...' are captured."""
    stdout = (
        "==================================== ERRORS ====================================\n"
        "_ ERROR collecting tests/test_broken.py _\n"
        "ImportError while importing test module 'tests/test_broken.py'\n"
        "E   ModuleNotFoundError: No module named 'does_not_exist'\n"
        "=========================== short test summary info ============================\n"
        "ERROR collecting tests/test_broken.py\n"
        "!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\n"
        "1 error in 0.05s\n"
    )
    failures = _extract_failures(stdout, "")
    assert len(failures) > 0
    assert any("test_broken.py" in f for f in failures)


def test_extract_failures_fallback_on_errors_section():
    """Verify that if pytest outputs ERRORS without specific test identifiers, failures is not empty."""
    stdout = (
        "==================================== ERRORS ====================================\n"
        "Internal collection failure during test run\n"
        "=============================== 1 error in 0.01s ===============================\n"
    )
    failures = _extract_failures(stdout, "")
    assert len(failures) > 0


def test_extract_failures_preserves_standard_failed():
    """Verify standard FAILED lines are still captured."""
    stdout = "FAILED tests/test_calc.py::test_add - AssertionError: assert 1 == 2\n"
    failures = _extract_failures(stdout, "")
    assert failures == ["tests/test_calc.py::test_add"]


def test_format_failure_summary_includes_actionable_details():
    """Verify format_failure_summary includes assertion error message and traceback details."""
    report = {
        "policy": "subset",
        "trust": 0.0,
        "tests_run_count": 1,
        "failures": ["tests/test_calc.py::test_add"],
        "output_summary": (
            "test_calc.py:4: in test_add\n"
            "    assert 1 == 2, 'one does not equal two'\n"
            "E   AssertionError: one does not equal two\n"
            "FAILED tests/test_calc.py::test_add\n"
            "1 failed in 0.02s"
        ),
    }
    summary = format_failure_summary(report, max_lines=30)
    assert "AssertionError: one does not equal two" in summary
    assert "tests/test_calc.py::test_add" in summary
    assert "Failure Details:" in summary
    assert len(summary.splitlines()) <= 30


def test_format_failure_summary_preserves_footer_within_limit():
    """Verify format_failure_summary respects max_lines while preserving critical guidance."""
    long_traceback = "\n".join([f"E   Frame {i}: some details" for i in range(25)])
    report = {
        "policy": "subset",
        "trust": 0.0,
        "tests_run_count": 1,
        "failures": ["tests/test_foo.py::test_bar"],
        "output_summary": long_traceback,
    }
    summary = format_failure_summary(report, max_lines=20)
    lines = summary.splitlines()
    assert len(lines) <= 20
    assert "Fix the source code. Do not edit, skip, or delete tests." in summary


def test_extract_failure_summary_captures_actionable_lines():
    """Verify _extract_failure_summary captures up to 15 actionable lines from pytest failure."""
    stdout = (
        "F                                                                        [100%]\n"
        "=================================== FAILURES ===================================\n"
        "__________________________________ test_calc ___________________________________\n"
        "test_fail.py:4: in test_calc\n"
        "    assert a == 3, 'math is broken'\n"
        "E   AssertionError: math is broken\n"
        "E   assert 2 == 3\n"
        "=========================== short test summary info ============================\n"
        "FAILED test_fail.py::test_calc\n"
        "1 failed in 0.02s\n"
    )
    result = _extract_failure_summary(stdout, "", max_lines=15)
    result_lines = result.splitlines()
    assert len(result_lines) <= 15
    assert "AssertionError: math is broken" in result
    assert "FAILED test_fail.py::test_calc" in result


def test_run_captures_actionable_failure_summary_on_test_failure(monkeypatch, tmp_path):
    """Verify api.run() captures actionable failure summary in report['output_summary']."""
    import subprocess
    from unittest.mock import MagicMock

    mock_check = {
        "policy": "subset",
        "trust": 0.9,
        "selected_tests": ["tests/test_foo.py::test_bar"],
        "is_fallback": False,
        "status": "select",
    }
    monkeypatch.setattr("guard_cli.api.check", lambda **kwargs: mock_check)
    monkeypatch.setattr("guard_cli.api.count_collected_tests", lambda tests, repo: 1)

    fake_stdout = (
        "F                                                                        [100%]\n"
        "=================================== FAILURES ===================================\n"
        "___________________________________ test_bar ___________________________________\n"
        "test_foo.py:10: in test_bar\n"
        "    assert result == 'expected'\n"
        "E   AssertionError: assert 'actual' == 'expected'\n"
        "=========================== short test summary info ============================\n"
        "FAILED tests/test_foo.py::test_bar - AssertionError: assert 'actual' == 'expected'\n"
        "1 failed in 0.04s\n"
    )
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = fake_stdout
    mock_proc.stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_proc)

    report, exit_code = run(repo_path=tmp_path)
    assert exit_code == 1
    assert report["tests_passed"] is False
    assert report["failures"] == ["tests/test_foo.py::test_bar"]
    assert "AssertionError: assert 'actual' == 'expected'" in report["output_summary"]
    assert "FAILED tests/test_foo.py::test_bar" in report["output_summary"]
    assert len(report["output_summary"].splitlines()) <= 15


def test_run_captures_collection_failure(monkeypatch, tmp_path):
    """Verify api.run() captures collection errors in failures and output_summary."""
    import subprocess
    from unittest.mock import MagicMock

    mock_check = {
        "policy": "run_all",
        "trust": 0.0,
        "selected_tests": ["tests"],
        "is_fallback": True,
        "status": "run-all",
    }
    monkeypatch.setattr("guard_cli.api.check", lambda **kwargs: mock_check)
    monkeypatch.setattr("guard_cli.api.count_collected_tests", lambda tests, repo: 0)

    fake_stdout = (
        "==================================== ERRORS ====================================\n"
        "_ ERROR collecting tests/test_syntax.py _\n"
        "tests/test_syntax.py:1: in <module>\n"
        "    def bad_code(:\n"
        "E   SyntaxError: invalid syntax\n"
        "=========================== short test summary info ============================\n"
        "ERROR tests/test_syntax.py\n"
        "1 error in 0.02s\n"
    )
    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.stdout = fake_stdout
    mock_proc.stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_proc)

    report, exit_code = run(repo_path=tmp_path)
    assert exit_code == 2
    assert report["tests_passed"] is False
    assert "tests/test_syntax.py" in report["failures"]
    assert "SyntaxError: invalid syntax" in report["output_summary"]
    assert len(report["output_summary"].splitlines()) <= 15

