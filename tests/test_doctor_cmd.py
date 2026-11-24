"""Unit tests for guard.doctor_cmd (Work Package D)."""
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from guard_cli.doctor_cmd import (
    check_environment,
    check_backend,
    check_graph,
    check_freshness,
    check_target_repo,
    check_integrations,
    apply_fixes,
    run_doctor,
    CheckResult,
)


def test_check_environment():
    res = check_environment()
    assert res.name == "environment"
    assert res.status in ("pass", "warn")

    # If Python < 3.10
    with patch.object(sys, "version_info", (3, 9, 7)):
        res_fail = check_environment()
        assert res_fail.status == "fail"
        assert "Python 3.10 or newer is required" in res_fail.message


def test_check_backend_healthy():
    mock_backend = MagicMock()
    mock_backend.name = "server"
    mock_backend.is_healthy.return_value = True
    mock_backend.describe.return_value = {"healthy": True, "connection_str": "localhost:6379"}

    with patch("guard_cli.doctor_cmd.resolve_backend", return_value=mock_backend):
        res, backend = check_backend(Path.cwd())
        assert res.status == "pass"
        assert "Backend 'server' is healthy" in res.message


def test_check_backend_unreachable():
    mock_backend = MagicMock()
    mock_backend.name = "server"
    mock_backend.is_healthy.return_value = False
    mock_backend.describe.return_value = {"healthy": False}

    with patch("guard_cli.doctor_cmd.resolve_backend", return_value=mock_backend):
        res, backend = check_backend(Path.cwd())
        assert res.status == "fail"
        assert "unreachable" in res.message
        assert res.fix is not None


def test_check_graph_populated(tmp_path):
    mock_backend = MagicMock()
    mock_backend.is_healthy.return_value = True
    mock_graph = MagicMock()
    mock_backend.get_graph.return_value = mock_graph

    with patch("guard_cli.doctor_cmd.db.get_schema_counts", return_value={"Function": 12, "File": 3, "COVERED_BY": 15}):
        res = check_graph(tmp_path, mock_backend)
        assert res.status == "pass"
        assert "12 functions" in res.message


def test_check_graph_empty(tmp_path):
    mock_backend = MagicMock()
    mock_backend.is_healthy.return_value = True
    mock_graph = MagicMock()
    mock_backend.get_graph.return_value = mock_graph

    with patch("guard_cli.doctor_cmd.db.get_schema_counts", return_value={}):
        res = check_graph(tmp_path, mock_backend)
        assert res.status == "fail"
        assert "0 nodes" in res.message
        assert res.fix is not None


def test_check_freshness_missing_state(tmp_path):
    res = check_freshness(tmp_path)
    assert res.status == "warn"
    assert "No recorded ingestion state" in res.message


def test_check_freshness_matching_head(tmp_path):
    state_file = tmp_path / ".guard" / "state.json"
    state_file.parent.mkdir()
    state_file.write_text(json.dumps({"head_sha": "abc1234"}), encoding="utf-8")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "abc1234\n"
        res = check_freshness(tmp_path)
        assert res.status == "pass"
        assert "Graph is fresh" in res.message


def test_check_freshness_diverged(tmp_path):
    state_file = tmp_path / ".guard" / "state.json"
    state_file.parent.mkdir()
    state_file.write_text(json.dumps({"head_sha": "abc1234"}), encoding="utf-8")

    def side_effect(cmd, **kwargs):
        mock_res = MagicMock()
        mock_res.returncode = 0
        if "rev-parse" in cmd:
            mock_res.stdout = "def5678\n"
        elif "diff" in cmd:
            mock_res.stdout = "src/foo.py\nsrc/bar.py\n"
        return mock_res

    with patch("subprocess.run", side_effect=side_effect):
        res = check_freshness(tmp_path)
        assert res.status == "warn"
        assert "2 file(s) changed since ingest" in res.message
        assert res.fix is not None


def test_check_target_repo(tmp_path):
    res = check_target_repo(tmp_path)
    # Depending on active test environment, should be pass or warn
    assert res.status in ("pass", "warn")


def test_check_integrations_and_fixes(tmp_path):
    # Fresh directory has no integrations
    res_before = check_integrations(tmp_path)
    assert res_before.status == "warn"
    assert "Missing integration settings" in res_before.message

    # Apply fixes
    applied = apply_fixes(tmp_path, backend=None, checks=[res_before])
    assert len(applied) > 0

    # Check integrations now pass
    res_after = check_integrations(tmp_path)
    assert res_after.status == "pass"


def test_run_doctor_json_mode(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='sample'", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    exit_code = run_doctor(repo_path=tmp_path, json_mode=True)
    assert exit_code in (0, 1, 2)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "status" in data
    assert "exit_code" in data
    assert "checks" in data
    assert len(data["checks"]) in (6, 7)
