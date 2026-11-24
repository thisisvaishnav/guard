"""Unit tests for guard.backend (Work Package B)."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from guard_cli.backend import (
    GraphBackend,
    ServerBackend,
    DockerBackend,
    EmbeddedBackend,
    resolve_backend,
    load_config,
    save_config,
    get_repo_graph_name,
)


def test_repo_graph_name():
    name1 = get_repo_graph_name("/path/to/my-project")
    assert name1.startswith("guard_my_project_")
    assert len(name1.split("_")[-1]) == 8

    name2 = get_repo_graph_name(Path("/another/path/AwesomeRepo.v2"))
    assert name2.startswith("guard_awesomerepo_v2_")

    # Different paths with same basename produce distinct graph names
    name_a = get_repo_graph_name("/dir_a/repo")
    name_b = get_repo_graph_name("/dir_b/repo")
    assert name_a != name_b
    assert get_repo_graph_name("").startswith("guard_")


def test_config_save_and_load(tmp_path):
    cfg = {
        "backend": {
            "type": "server",
            "host": "127.0.0.1",
            "port": 6379,
            "graph_name": "guard_test_proj",
        }
    }
    cfg_file = save_config(tmp_path, cfg)
    assert cfg_file.exists()

    loaded = load_config(tmp_path)
    assert loaded["backend"]["type"] == "server"
    assert loaded["backend"]["host"] == "127.0.0.1"
    assert loaded["backend"]["port"] == 6379
    assert loaded["backend"]["graph_name"] == "guard_test_proj"


def test_server_backend_describe_and_graph():
    backend = ServerBackend(host="localhost", port=6379)
    assert backend.name == "server"
    desc = backend.describe()
    assert desc["type"] == "server"
    assert desc["host"] == "localhost"
    assert desc["port"] == 6379
    # is_healthy should be boolean
    assert isinstance(desc["healthy"], bool)

    if desc["healthy"]:
        g = backend.get_graph("guard_unit_test")
        assert g is not None
        assert g.name == "guard_unit_test"


def test_docker_backend_describe():
    backend = DockerBackend(port=6390, container_name="guard-falkordb-test")
    assert backend.name == "docker"
    desc = backend.describe()
    assert desc["type"] == "docker"
    assert desc["port"] == 6390
    assert desc["container"] == "guard-falkordb-test"


def test_embedded_backend_version_gate():
    # If Python < 3.12, initializing EmbeddedBackend must raise RuntimeError
    with patch.object(sys, "version_info", (3, 11, 2)):
        with pytest.raises(RuntimeError, match="Python 3.12 or newer"):
            EmbeddedBackend()


@pytest.mark.skipif(sys.version_info < (3, 12), reason="Embedded backend requires Python 3.12+")
def test_embedded_backend_live(tmp_path):
    db_file = tmp_path / "test_falkor.rdb"
    try:
        backend = EmbeddedBackend(data_path=db_file)
        desc = backend.describe()
        assert desc["type"] == "embedded"
        assert desc["data_path"] == str(db_file)
        if desc["healthy"]:
            g = backend.get_graph("embedded_test_graph")
            assert g is not None
            g.query("CREATE (n:TestNode {val: 42})")
            res = g.query("MATCH (n:TestNode) RETURN n.val").result_set
            assert res[0][0] == 42
    except ImportError:
        pytest.skip("falkordblite/redislite not installed in this environment")


def test_resolve_backend_preference():
    b_server = resolve_backend(preference="server")
    assert isinstance(b_server, ServerBackend)

    b_docker = resolve_backend(preference="docker", autostart=False)
    assert isinstance(b_docker, DockerBackend)

    with pytest.raises(ValueError, match="Unknown backend preference"):
        resolve_backend(preference="nonexistent_backend")


def test_resolve_backend_with_config(tmp_path):
    save_config(tmp_path, {
        "backend": {
            "type": "server",
            "host": "custom_host",
            "port": 9999,
        }
    })
    resolved = resolve_backend(repo_path=tmp_path)
    assert isinstance(resolved, ServerBackend)
    assert resolved.host == "custom_host"
    assert resolved.port == 9999


def test_embedded_backend_platform_check():
    with patch("sys.platform", "win32"):
        with pytest.raises(RuntimeError, match="Embedded backend .* not supported on platform 'win32'"):
            EmbeddedBackend()

