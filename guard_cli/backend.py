"""Backend abstraction layer for Guard (Work Package B).

Provides:
- GraphBackend interface (ABC)
- SQLiteBackend: manages embedded SQLite in .guard/graph.db (zero daemon default)
- ServerBackend: connects to existing FalkorDB server (e.g. localhost:6379)
- DockerBackend: manages dedicated docker container 'guard-falkordb' on port 6390
- EmbeddedBackend: manages embedded FalkorDBLite in ~/.guard/data/ (Python 3.12+)
- Backend resolution and fallback chain
- Configuration storage in .guard/config.toml
"""

from __future__ import annotations

import abc
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore


DEFAULT_SERVER_HOST = "localhost"
DEFAULT_SERVER_PORT = 6379
DEFAULT_DOCKER_PORT = 6390
DEFAULT_DOCKER_CONTAINER = "guard-falkordb"
DEFAULT_DOCKER_IMAGE = "falkordb/falkordb:latest"
DEFAULT_DOCKER_VOLUME = "guard-data:/data"
GRAPH_NAME = os.getenv("GUARD_GRAPH", "guard")


def get_repo_graph_name(repo_path: str | Path | None = None) -> str:
    """Derive a unique, safe FalkorDB graph name from the repository path."""
    if repo_path is None:
        p = Path.cwd()
    else:
        p = Path(repo_path).resolve()
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", p.name.lower()).strip("_")
    if not clean_name:
        clean_name = "repo"
    path_hash = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:8]
    return f"guard_{clean_name}_{path_hash}"


def _parse_simple_toml(content: str) -> dict[str, Any]:
    """Fallback simple TOML parser for basic [section] key=val configs."""
    result: dict[str, Any] = {}
    current_section = result
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sec = line[1:-1].strip()
            result[sec] = {}
            current_section = result[sec]
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            elif val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
            elif val.isdigit():
                val = int(val)
            current_section[key] = val
    return result


def load_config(repo_path: str | Path | None = None) -> dict[str, Any]:
    """Loads configuration from .guard/config.toml if present."""
    base = Path(repo_path).resolve() if repo_path else Path.cwd()
    cfg_file = base / ".guard" / "config.toml"
    if not cfg_file.exists():
        return {}
    content = cfg_file.read_text(encoding="utf-8")
    if tomllib is not None:
        try:
            return tomllib.loads(content)
        except Exception:
            return _parse_simple_toml(content)
    return _parse_simple_toml(content)


def save_config(repo_path: str | Path | None, config: dict[str, Any]) -> Path:
    """Saves configuration to .guard/config.toml."""
    base = Path(repo_path).resolve() if repo_path else Path.cwd()
    guard_dir = base / ".guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = guard_dir / "config.toml"

    lines: list[str] = [
        "# Guard configuration file - automatically generated",
        "",
    ]
    for section, values in config.items():
        if isinstance(values, dict):
            lines.append(f"[{section}]")
            for k, v in values.items():
                if isinstance(v, bool):
                    lines.append(f"{k} = {str(v).lower()}")
                elif isinstance(v, (int, float)):
                    lines.append(f"{k} = {v}")
                else:
                    lines.append(f'{k} = "{v}"')
            lines.append("")
        else:
            if isinstance(values, bool):
                lines.append(f"{section} = {str(values).lower()}")
            elif isinstance(values, (int, float)):
                lines.append(f"{section} = {values}")
            else:
                lines.append(f'{section} = "{values}"')

    cfg_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return cfg_file


def check_embedded_platform_support() -> tuple[bool, str]:
    """Checks whether the current operating system and C library satisfy FalkorDBLite requirements.

    Requirements:
    - Python 3.12+
    - macOS 15+ (Sequoia or newer)
    - Linux with glibc >= 2.39
    """
    if sys.platform not in ("darwin", "linux") and not sys.platform.startswith("linux"):
        return False, (
            f"Embedded backend (FalkorDBLite) is not supported on platform '{sys.platform}'. "
            f"no embedded build for this platform, use Docker or a server"
        )

    if sys.version_info < (3, 12):
        return False, (
            f"Embedded backend (FalkorDBLite) requires Python 3.12 or newer. "
            f"Current interpreter is Python {sys.version.split()[0]}. "
            f"no embedded build for this platform, use Docker or a server"
        )

    if sys.platform == "darwin":
        import platform
        mac_ver = platform.mac_ver()[0]
        if mac_ver:
            try:
                major = int(mac_ver.split(".")[0])
                if major < 15:
                    return False, (
                        f"Embedded backend (FalkorDBLite) requires macOS 15 or newer (current: macOS {mac_ver}). "
                        f"no embedded build for this platform, use Docker or a server"
                    )
            except (ValueError, IndexError):
                pass
    elif sys.platform.startswith("linux"):
        import platform
        libc_name, libc_ver = platform.libc_ver()
        if libc_name == "glibc" and libc_ver:
            try:
                parts = [int(p) for p in libc_ver.split(".")[:2]]
                if tuple(parts) < (2, 39):
                    return False, (
                        f"Embedded backend (FalkorDBLite) requires glibc 2.39 or newer (current: {libc_name} {libc_ver}). "
                        f"no embedded build for this platform, use Docker or a server"
                    )
            except (ValueError, IndexError):
                pass

    return True, ""


class GraphBackend(abc.ABC):
    """Abstract interface for Guard backends."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of backend: 'sqlite', 'server', 'docker', or 'embedded'."""
        pass

    @abc.abstractmethod
    def connect(self) -> Any:
        """Return connected client or connection handle."""
        pass

    @abc.abstractmethod
    def is_healthy(self) -> bool:
        """Check if backend is reachable and responsive to queries."""
        pass

    @abc.abstractmethod
    def describe(self) -> dict[str, Any]:
        """Return diagnostic description dictionary."""
        pass

    @abc.abstractmethod
    def get_graph(self, graph_name: str) -> Any:
        """Return graph or GraphStore handle."""
        pass

    def is_available(self) -> bool:
        return True

    def close(self) -> None:
        """Release any held resources."""
        pass


class SQLiteBackend(GraphBackend):
    """Zero-daemon default backend using embedded SQLite in .guard/graph.db."""

    def __init__(self, repo_path: Path | str | None = None) -> None:
        self.repo_path = Path(repo_path).resolve() if repo_path else Path.cwd()
        self._stores: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "sqlite"

    def is_available(self) -> bool:
        try:
            import sqlite3
            return True
        except ImportError:
            return False

    def connect(self) -> Any:
        db_path = self.repo_path / ".guard" / "graph.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3
        return sqlite3.connect(str(db_path))

    def is_healthy(self) -> bool:
        try:
            import sqlite3
            db_path = self.repo_path / ".guard" / "graph.db"
            if not db_path.exists():
                return True
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False

    def describe(self) -> dict[str, Any]:
        db_path = self.repo_path / ".guard" / "graph.db"
        return {
            "type": "sqlite",
            "path": str(db_path),
            "healthy": self.is_healthy(),
            "zero_daemon": True,
        }

    def get_graph(self, graph_name: str) -> Any:
        from guard_cli.store.sqlite import SQLiteGraphStore

        if graph_name and graph_name != "guard" and not graph_name.startswith("guard_"):
            db_path = Path.home() / ".guard" / "graphs" / f"{graph_name}.db"
        else:
            db_path = self.repo_path / ".guard" / "graph.db"

        cache_key = str(db_path)
        if cache_key not in self._stores:
            self._stores[cache_key] = SQLiteGraphStore(db_path=db_path)
        return self._stores[cache_key]

    def close(self) -> None:
        for store in self._stores.values():
            try:
                store.close()
            except Exception:
                pass
        self._stores.clear()


class ServerBackend(GraphBackend):
    """Connects to an existing FalkorDB server instance."""

    def __init__(
        self,
        host: str = DEFAULT_SERVER_HOST,
        port: int = DEFAULT_SERVER_PORT,
        url: str | None = None,
    ):
        self.host = host
        self.port = int(port)
        self.url = url
        self._client: Any = None

    @property
    def name(self) -> str:
        return "server"

    def is_available(self) -> bool:
        try:
            from falkordb import FalkorDB  # noqa: F401
            return True
        except ImportError:
            return False

    def connect(self) -> Any:
        if self._client is None:
            from falkordb import FalkorDB
            if self.url:
                self._client = FalkorDB.from_url(self.url)
            else:
                self._client = FalkorDB(host=self.host, port=self.port)
        return self._client

    def is_healthy(self) -> bool:
        try:
            client = self.connect()
            g = client.select_graph("guard_healthcheck")
            res = g.query("RETURN 1 AS n")
            return bool(res and res.result_set)
        except Exception:
            self._client = None
            return False

    def describe(self) -> dict[str, Any]:
        healthy = self.is_healthy()
        return {
            "type": "server",
            "host": self.host,
            "port": self.port,
            "healthy": healthy,
            "connection_str": f"{self.host}:{self.port}",
        }

    def get_graph(self, graph_name: str) -> Any:
        return self.connect().select_graph(graph_name)

    def close(self) -> None:
        self._client = None


class DockerBackend(GraphBackend):
    """Manages a dedicated FalkorDB container running via Docker on port 6390."""

    def __init__(
        self,
        port: int = DEFAULT_DOCKER_PORT,
        container_name: str = DEFAULT_DOCKER_CONTAINER,
        image: str = DEFAULT_DOCKER_IMAGE,
        volume: str = DEFAULT_DOCKER_VOLUME,
    ):
        self.port = int(port)
        self.container_name = container_name
        self.image = image
        self.volume = volume
        self._client: Any = None

    @property
    def name(self) -> str:
        return "docker"

    def is_available(self) -> bool:
        return self.docker_available()

    @staticmethod
    def docker_available() -> bool:
        if not shutil.which("docker"):
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def container_status(self) -> str | None:
        if not shutil.which("docker"):
            return None
        try:
            res = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    f"name=^/{self.container_name}$",
                    "--format",
                    "{{.Status}}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = res.stdout.strip()
            if not out:
                return None
            if out.lower().startswith("up"):
                return "running"
            return "exited"
        except Exception:
            return None

    def start_container(self) -> bool:
        if not self.docker_available():
            return False

        status = self.container_status()
        if status == "running":
            return True

        if status == "exited":
            res = subprocess.run(
                ["docker", "start", self.container_name],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode != 0:
                return False
        else:
            cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                self.container_name,
                "-v",
                self.volume,
                "-p",
                f"{self.port}:6379",
                self.image,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode != 0:
                return False

        for _ in range(20):
            time.sleep(0.5)
            if self.is_healthy():
                return True
        return self.is_healthy()

    def connect(self) -> Any:
        if self._client is None:
            from falkordb import FalkorDB
            self._client = FalkorDB(host="localhost", port=self.port)
        return self._client

    def is_healthy(self) -> bool:
        try:
            client = self.connect()
            g = client.select_graph("guard_healthcheck")
            res = g.query("RETURN 1 AS n")
            return bool(res and res.result_set)
        except Exception:
            self._client = None
            return False

    def describe(self) -> dict[str, Any]:
        status = self.container_status()
        healthy = self.is_healthy()
        return {
            "type": "docker",
            "container": self.container_name,
            "port": self.port,
            "image": self.image,
            "volume": self.volume,
            "status": status or "not_found",
            "healthy": healthy,
        }

    def get_graph(self, graph_name: str) -> Any:
        return self.connect().select_graph(graph_name)

    def close(self) -> None:
        self._client = None


class EmbeddedBackend(GraphBackend):
    """Manages an embedded FalkorDBLite instance (Python 3.12+ on supported platforms)."""

    def __init__(self, data_path: str | Path | None = None, data_dir: str | Path | None = None):
        ok, msg = check_embedded_platform_support()
        if not ok:
            raise RuntimeError(msg)

        path_to_use = data_path or data_dir
        if path_to_use is None:
            base_dir = Path.home() / ".guard" / "data"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_dir / "falkordb.rdb"
        else:
            self.db_path = Path(path_to_use).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._client: Any = None

    @property
    def name(self) -> str:
        return "embedded"

    def is_available(self) -> bool:
        if sys.version_info < (3, 12):
            return False
        try:
            import falkordblite  # noqa: F401
            return True
        except ImportError:
            return False

    def connect(self) -> Any:
        if self._client is None:
            ok, msg = check_embedded_platform_support()
            if not ok:
                raise RuntimeError(msg)
            try:
                from redislite import FalkorDB
            except (ImportError, OSError) as err:
                try:
                    from falkordblite import FalkorDB  # type: ignore
                except (ImportError, OSError) as inner_err:
                    err_msg = f"{inner_err} {err}"
                    if any(term in err_msg for term in ("GLIBC", "version", "symbol", "dlopen", "image not found")):
                        raise RuntimeError(
                            f"Failed importing embedded FalkorDB: {inner_err}. "
                            f"no embedded build for this platform, use Docker or a server"
                        ) from inner_err
                    raise RuntimeError(
                        f"falkordblite is not installed or not supported: {inner_err}. "
                        f"no embedded build for this platform, use Docker or a server"
                    ) from inner_err

            try:
                self._client = FalkorDB(dbfilename=str(self.db_path))
            except (ImportError, OSError, Exception) as run_err:
                err_msg = str(run_err)
                if any(term in err_msg for term in ("GLIBC", "version", "symbol", "dlopen", "image not found")):
                    raise RuntimeError(
                        f"Failed starting embedded FalkorDB: {run_err}. "
                        f"no embedded build for this platform, use Docker or a server"
                    ) from run_err
                raise
        return self._client

    def is_healthy(self) -> bool:
        try:
            client = self.connect()
            g = client.select_graph("guard_healthcheck")
            res = g.query("RETURN 1 AS n")
            return bool(res and res.result_set)
        except Exception:
            self._client = None
            return False

    def describe(self) -> dict[str, Any]:
        healthy = self.is_healthy()
        return {
            "type": "embedded",
            "data_path": str(self.db_path),
            "python_version": sys.version.split()[0],
            "healthy": healthy,
        }

    def get_graph(self, graph_name: str) -> Any:
        return self.connect().select_graph(graph_name)

    def close(self) -> None:
        self._client = None


def resolve_backend(
    preference: str | None = None,
    repo_path: str | Path | None = None,
    autostart: bool = True,
) -> GraphBackend:
    """Resolve backend using preference, repository config, or fallback chain.

    Priority:
    1. CLI preference flag (--backend)
    2. .guard/config.toml [backend] type
    3. Fallback chain: sqlite (zero daemon default) -> server -> docker -> embedded
    """
    # Accommodate callers passing (repo_path=...) or positional (repo_path, preference)
    if isinstance(preference, (Path, str)) and "/" in str(preference):
        repo_path, preference = preference, repo_path  # type: ignore

    cfg = load_config(repo_path)
    b_cfg = cfg.get("backend", {})

    target = preference or b_cfg.get("type")
    host = b_cfg.get("host") or os.getenv("FALKORDB_HOST", DEFAULT_SERVER_HOST)
    port = int(b_cfg.get("port") or os.getenv("FALKORDB_PORT", DEFAULT_SERVER_PORT))

    if target:
        target = str(target).lower().strip()
        if target == "sqlite":
            return SQLiteBackend(repo_path=repo_path)
        elif target == "server":
            url = b_cfg.get("url")
            return ServerBackend(host=host, port=port, url=url)
        elif target == "docker":
            d_port = int(b_cfg.get("port", DEFAULT_DOCKER_PORT))
            b = DockerBackend(port=d_port)
            if autostart and not b.is_healthy():
                b.start_container()
            return b
        elif target == "embedded":
            return EmbeddedBackend()
        else:
            raise ValueError(f"Unknown backend preference: '{target}'. Choose 'sqlite', 'server', 'docker', or 'embedded'.")

    # Default: SQLite zero daemon
    sqlite_b = SQLiteBackend(repo_path=repo_path)
    if sqlite_b.is_available():
        return sqlite_b

    # Fallback: Server -> Docker -> Embedded
    srv = ServerBackend(host=host, port=port)
    if srv.is_healthy():
        return srv

    if DockerBackend.docker_available():
        dock = DockerBackend(port=DEFAULT_DOCKER_PORT)
        if autostart:
            if dock.start_container() and dock.is_healthy():
                return dock
        elif dock.is_healthy():
            return dock

    if sys.version_info >= (3, 12):
        try:
            emb = EmbeddedBackend()
            if emb.is_healthy():
                return emb
        except Exception:
            pass

    return sqlite_b


_active_backend: GraphBackend | None = None


def set_backend(backend: GraphBackend | None) -> None:
    """Explicitly set active GraphBackend instance."""
    global _active_backend
    _active_backend = backend


def get_backend(repo_path: Path | str | None = None) -> GraphBackend:
    """Return active backend or resolve according to environment and config."""
    global _active_backend
    if _active_backend is not None:
        return _active_backend
    return resolve_backend(repo_path=repo_path)
