"""Base GraphStore protocol and domain models for Guard.

Decouples Guard's test selection, feedback repair, and ingestion pipelines
from specific database implementations (SQLite, FalkorDB, etc.).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class FunctionNode:
    """Represents a function definition node in the code graph."""
    id: str
    file: str
    name: str
    qualname: str
    start: int
    end: int
    has_dynamic_dispatch: bool = False
    no_evidence: bool = False


@dataclass
class TestNode:
    """Represents a discovered test in the test suite."""
    id: str
    file: str
    name: str
    qualname: str = ""
    start: int = 0
    end: int = 0
    flake_rate: float = 0.0


@dataclass
class CoveringTestRecord:
    """A test covering a specific function with a confidence score."""
    test_id: str
    confidence: float
    source: str = "coverage"
    last_verified_sha: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "confidence": self.confidence,
            "source": self.source,
            "last_verified_sha": self.last_verified_sha,
        }

    def __getitem__(self, item: str) -> Any:
        if item == "test_id":
            return self.test_id
        elif item == "confidence":
            return self.confidence
        elif item == "source":
            return self.source
        elif item == "last_verified_sha":
            return self.last_verified_sha
        raise KeyError(item)


@dataclass
class CallerRecord:
    """Inbound caller information from static/dynamic call graphs."""
    caller: str
    hops: int

    def __getitem__(self, item: str) -> Any:
        if item == "caller":
            return self.caller
        elif item == "hops":
            return self.hops
        raise KeyError(item)


class GraphStore(abc.ABC):
    """Abstract interface for Guard graph storage backends."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of storage backend (e.g. 'sqlite', 'falkordb')."""
        pass

    @abc.abstractmethod
    def ensure_schema(self) -> None:
        """Ensure tables/indexes exist and are ready for queries."""
        pass

    @abc.abstractmethod
    def reset_graph(self) -> None:
        """Clear all nodes, relationships, and metadata."""
        pass

    @abc.abstractmethod
    def get_schema_counts(self) -> dict[str, int]:
        """Return counts of nodes (File, Function, Test, Run) and edges."""
        pass

    @abc.abstractmethod
    def get_graph_meta(self) -> dict[str, Any]:
        """Return metadata including updated_at, generation, commit_sha."""
        pass

    @abc.abstractmethod
    def update_graph_meta(self, commit_sha: str | None = None) -> None:
        """Bump generation counter and update timestamp / commit SHA."""
        pass

    @abc.abstractmethod
    def get_functions_for_file(self, file_path: str) -> list[FunctionNode]:
        """Return all function definitions located inside the specified file."""
        pass

    @abc.abstractmethod
    def get_all_functions(self) -> list[FunctionNode]:
        """Return all function definitions in the repository."""
        pass

    @abc.abstractmethod
    def get_covering_tests(
        self, function_id: str, min_confidence: float = 0.0
    ) -> list[CoveringTestRecord]:
        """Find tests covering a given function, ordered by confidence descending."""
        pass

    @abc.abstractmethod
    def get_multi_hop_tests(
        self, function_id: str, max_depth: int = 2, min_confidence: float = 0.0
    ) -> list[CoveringTestRecord]:
        """Find tests covering callees of the given function up to max_depth hops."""
        pass

    @abc.abstractmethod
    def get_callers(
        self, function_id: str, hops: int = 4, min_confidence: float = 0.0
    ) -> list[CallerRecord]:
        """Find callers of a function up to hops distance."""
        pass

    @abc.abstractmethod
    def get_module_tests(self, mod_stem: str) -> list[str]:
        """Return test IDs where test file matches the module stem."""
        pass

    @abc.abstractmethod
    def write_static(self, result: Any, commit_sha: str | None = None) -> None:
        """Write StaticResult files, functions, tests, calls, and imports."""
        pass

    @abc.abstractmethod
    def write_coverage(
        self,
        test_to_funcs: dict[str, list[str]] | list[dict[str, str]],
        commit_sha: str | None = None,
        confidence: float = 0.9,
    ) -> int:
        """Write COVERED_BY edges from functions to tests."""
        pass

    @abc.abstractmethod
    def write_run(
        self,
        run_data: dict[str, Any],
        failures: list[dict[str, Any]] | None = None,
    ) -> None:
        """Record test run results and failed test edges."""
        pass

    @abc.abstractmethod
    def set_function_evidence_flags(
        self, covered_ids: Sequence[str], uncovered_ids: Sequence[str]
    ) -> None:
        """Update no_evidence flags on function nodes."""
        pass

    @abc.abstractmethod
    def set_test_flake_rates(self, flake_rates: dict[str, float]) -> None:
        """Update flake_rate on test nodes."""
        pass

    @abc.abstractmethod
    def record_miss_repair(
        self,
        function_id: str,
        test_id: str,
        new_confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Insert or update a miss_repair edge and unset no_evidence flag."""
        pass

    def close(self) -> None:
        """Release any database connections or resources."""
        pass
