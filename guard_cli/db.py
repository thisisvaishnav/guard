"""FalkorDB connection, complete schema, and batched writers for Guard (Task T2)."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable, Sequence
from falkordb import FalkorDB

GRAPH_NAME = os.getenv("GUARD_GRAPH", "guard")

INDEXES = [
    "CREATE INDEX FOR (f:Function) ON (f.id)",
    "CREATE INDEX FOR (t:Test) ON (t.id)",
    "CREATE INDEX FOR (x:File) ON (x.path)",
    "CREATE INDEX FOR (r:Run) ON (r.id)",
    "CREATE INDEX FOR (m:GuardMeta) ON (m.id)",
]


_active_backend: Any = None


def set_backend(backend: Any) -> None:
    """Explicitly set active GraphBackend instance."""
    global _active_backend
    _active_backend = backend


def get_backend(repo_path: Any = None) -> Any:
    """Return active or resolved GraphBackend."""
    global _active_backend
    if _active_backend is not None:
        return _active_backend
    from guard_cli.backend import resolve_backend, ServerBackend

    if "FALKORDB_HOST" in os.environ or "FALKORDB_PORT" in os.environ:
        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", "6379"))
        return ServerBackend(host=host, port=port)
    return resolve_backend(repo_path=repo_path)


def get_graph(
    name: str | None = None,
    backend: Any = None,
    repo_path: Any = None,
):
    """Retrieve FalkorDB graph using resolved backend and repository name."""
    if backend is None:
        backend = get_backend(repo_path=repo_path)
    if name is None:
        from guard_cli.backend import load_config
        cfg = load_config(repo_path)
        name = cfg.get("backend", {}).get("graph_name") or os.getenv("GUARD_GRAPH", GRAPH_NAME)
    g = backend.get_graph(name)
    if repo_path is not None and g is not None:
        try:
            g.repo_path = Path(repo_path)
        except Exception:
            pass
    return g


def reset_graph(g) -> None:
    try:
        g.delete()
    except Exception:
        pass  # graph did not exist yet


def ensure_schema(g) -> None:
    for q in INDEXES:
        try:
            g.query(q)
        except Exception:
            pass  # index already exists


def _batches(rows: Sequence[Any], size: int = 500) -> Iterable[Sequence[Any]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def write_static(g, result, commit_sha: str | None = None) -> None:
    """Write StaticResult nodes and edges into FalkorDB with T2 schema requirements."""
    # 1. File nodes
    for b in _batches(result.file_rows()):
        g.query("UNWIND $rows AS r MERGE (x:File {path: r.path})", {"rows": b})

    # 2. Function nodes & DEFINED_IN edges
    for b in _batches(result.function_rows()):
        g.query(
            """UNWIND $rows AS r
               MERGE (f:Function {id: r.id})
               SET f.file = r.file, f.name = r.name, f.qualname = r.qualname,
                   f.start = r.start, f.end = r.end,
                   f.has_dynamic_dispatch = r.dyn
               WITH f, r
               MATCH (x:File {path: r.file})
               MERGE (f)-[:DEFINED_IN]->(x)""",
            {"rows": b},
        )

    # 3. Test nodes & DEFINED_IN edges
    if hasattr(result, "test_rows"):
        test_rows = result.test_rows()
    else:
        test_rows = []

    for b in _batches(test_rows):
        g.query(
            """UNWIND $rows AS r
               MERGE (t:Test {id: r.id})
               SET t.file = r.file, t.name = r.name, t.qualname = r.qualname,
                   t.start = r.start, t.end = r.end
               WITH t, r
               MATCH (x:File {path: r.file})
               MERGE (t)-[:DEFINED_IN]->(x)""",
            {"rows": b},
        )

    # 4. CALLS edges (Function -> Function)
    for b in _batches(result.call_rows()):
        g.query(
            """UNWIND $rows AS r
               MATCH (a:Function {id: r.src}), (b:Function {id: r.dst})
               MERGE (a)-[e:CALLS]->(b)
               SET e.source = 'static',
                   e.confidence = 0.6,
                   e.evidence_count = coalesce(e.evidence_count, 0),
                   e.last_verified_sha = $sha""",
            {"rows": b, "sha": commit_sha},
        )

    # 5. IMPORTS edges (File -> File)
    for b in _batches(result.import_rows()):
        g.query(
            """UNWIND $rows AS r
               MATCH (a:File {path: r.src}), (b:File {path: r.dst})
               MERGE (a)-[e:IMPORTS]->(b)
               SET e.source = 'static',
                   e.confidence = 0.6,
                   e.last_verified_sha = $sha""",
            {"rows": b, "sha": commit_sha},
        )
    update_graph_meta(g)


def write_coverage(
    g,
    test_to_funcs: dict[str, list[str]] | list[dict[str, str]],
    commit_sha: str | None = None,
    confidence: float = 0.9,
) -> int:
    """Write COVERED_BY edges from Function to Test nodes.

    Args:
        test_to_funcs: Mapping test_id -> list of function_ids, or list of {'test': id, 'func': id}
        commit_sha: Commit SHA when coverage was verified
        confidence: Confidence score (default 0.9 for dynamic coverage evidence)

    Returns:
        Number of coverage pairs written
    """
    if isinstance(test_to_funcs, dict):
        pairs = [
            {"test": t_id, "func": f_id}
            for t_id, funcs in test_to_funcs.items()
            for f_id in funcs
        ]
    else:
        pairs = list(test_to_funcs)

    for b in _batches(pairs):
        g.query(
            """UNWIND $rows AS r
               MATCH (f:Function {id: r.func}), (t:Test {id: r.test})
               MERGE (f)-[e:COVERED_BY]->(t)
               SET e.source = 'coverage',
                   e.confidence = $conf,
                   e.evidence_count = coalesce(e.evidence_count, 0) + 1,
                   e.last_verified_sha = $sha""",
            {"rows": b, "conf": confidence, "sha": commit_sha},
        )
    update_graph_meta(g)
    return len(pairs)


def update_graph_meta(g: Any = None, repo_path: Path | str | None = None) -> None:
    """Updates Guard metadata generation and timestamp in the graph and repository."""
    if g is None and repo_path is None:
        return
    ts = time.time()
    new_gen = 1

    # 1. Update in-memory fallback on graph object
    if g is not None:
        try:
            prev = getattr(g, "_guard_meta", None)
            if isinstance(prev, dict):
                new_gen = int(prev.get("generation", 0)) + 1
            g._guard_meta = {
                "updated_at": ts,
                "generation": new_gen,
            }
        except Exception:
            pass

    # 2. Persist to repo if repo_path is available
    target_repo = repo_path or (getattr(g, "repo_path", None) if g is not None else None)
    if target_repo and isinstance(target_repo, (str, Path)):
        try:
            meta_path = Path(target_repo) / ".guard" / "graph_meta.json"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_data = {
                "updated_at": ts,
                "generation": new_gen,
            }
            meta_path.write_text(json.dumps(meta_data, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

    # 3. Query FalkorDB if connected
    if g is not None:
        try:
            g.query(
                "MERGE (m:GuardMeta {id: 'meta'}) "
                "SET m.updated_at = $ts, m.generation = coalesce(m.generation, 0) + 1",
                {"ts": ts},
            )
        except Exception:
            pass


def get_graph_state(g: Any = None, repo_path: Path | str | None = None) -> dict[str, Any]:
    """Returns a dictionary summarizing graph state for cache invalidation."""
    if g is None and repo_path is None:
        return {"status": "none"}

    meta: dict[str, Any] = {}

    # 1. Check in-memory object metadata (fallback for offline or mocked graph)
    if g is not None:
        obj_meta = getattr(g, "_guard_meta", None)
        if isinstance(obj_meta, dict):
            meta.update(obj_meta)

    # 2. Check repo-level graph_meta.json or state.json
    target_repo = repo_path or (getattr(g, "repo_path", None) if g is not None else None)
    if target_repo and isinstance(target_repo, (str, Path)):
        try:
            meta_file = Path(target_repo) / ".guard" / "graph_meta.json"
            if meta_file.exists():
                file_meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if isinstance(file_meta, dict):
                    if int(file_meta.get("generation", 0)) >= int(meta.get("generation", 0)):
                        meta.update(file_meta)
            else:
                state_file = Path(target_repo) / ".guard" / "state.json"
                if state_file.exists():
                    state_data = json.loads(state_file.read_text(encoding="utf-8"))
                    if isinstance(state_data, dict):
                        if "ingested_at" in state_data:
                            meta.setdefault("ingested_at", state_data["ingested_at"])
                        if "head_sha" in state_data:
                            meta.setdefault("head_sha", state_data["head_sha"])
        except Exception:
            pass

    # 3. FalkorDB query if connected
    if g is not None:
        try:
            res = g.query("MATCH (m:GuardMeta {id: 'meta'}) RETURN m.updated_at, m.generation").result_set
            if (
                res
                and res[0]
                and isinstance(res[0][0], (int, float, str))
                and isinstance(res[0][1], (int, float))
            ):
                meta["updated_at"] = res[0][0]
                meta["generation"] = res[0][1]
        except Exception:
            pass

    counts: dict[str, int] = {}
    if g is not None:
        try:
            counts = get_schema_counts(g)
        except Exception:
            counts = {}

    return {"counts": counts, "meta": meta}



def write_run(
    g,
    run_data: dict[str, Any],
    failures: list[dict[str, Any]] | None = None,
) -> None:
    """Write a Run node and optional FAILED_IN edges.

    Args:
        run_data: Dict with keys: id, timestamp, commit_sha, duration_ms, total_tests, passed, failed
        failures: List of dicts: {'test_id': str, 'error': str}
    """
    g.query(
        """MERGE (r:Run {id: $r.id})
           SET r.timestamp = $r.timestamp,
               r.commit_sha = $r.commit_sha,
               r.duration_ms = $r.duration_ms,
               r.total_tests = $r.total_tests,
               r.passed = $r.passed,
               r.failed = $r.failed""",
        {"r": run_data},
    )

    if failures:
        for b in _batches(failures):
            g.query(
                """UNWIND $rows AS f
                   MATCH (t:Test {id: f.test_id}), (r:Run {id: $run_id})
                   MERGE (t)-[e:FAILED_IN]->(r)
                   SET e.source = 'test_run',
                       e.error_message = f.error,
                       e.commit_sha = $sha""",
                {
                    "rows": b,
                    "run_id": run_data["id"],
                    "sha": run_data.get("commit_sha"),
                },
            )


def get_schema_counts(g) -> dict[str, int]:
    """Return dictionary with counts of all nodes and relationships."""
    if g is None:
        return {}
    counts = {}
    for label in ("File", "Function", "Test", "Run"):
        try:
            res = g.query(f"MATCH (n:{label}) RETURN count(n)").result_set
            counts[label] = res[0][0] if (res and isinstance(res[0][0], int)) else 0
        except Exception:
            counts[label] = 0

    for rel in ("CALLS", "IMPORTS", "DEFINED_IN", "COVERED_BY", "FAILED_IN"):
        try:
            res = g.query(f"MATCH ()-[e:{rel}]->() RETURN count(e)").result_set
            counts[rel] = res[0][0] if (res and isinstance(res[0][0], int)) else 0
        except Exception:
            counts[rel] = 0

    try:
        res = g.query(
            "MATCH (f:Function {has_dynamic_dispatch: true}) RETURN count(f)"
        ).result_set
        counts["dynamic_functions"] = res[0][0] if (res and isinstance(res[0][0], int)) else 0
    except Exception:
        counts["dynamic_functions"] = 0

    return counts


def get_callers(
    g, function_id: str, hops: int = 4, min_confidence: float = 0.0
) -> list[dict[str, Any]]:
    """Traverse inbound CALLS edges up to N hops filtered by min_confidence."""
    q = (
        f"MATCH p=(caller:Function)-[:CALLS*1..{hops}]->(target:Function {{id: $id}}) "
        "WHERE all(e IN relationships(p) WHERE coalesce(e.confidence, 0.6) >= $min_conf) "
        "RETURN caller.id AS caller, min(length(p)) AS hops "
        "ORDER BY hops, caller"
    )
    res = g.query(q, {"id": function_id, "min_conf": min_confidence}).result_set
    return [{"caller": row[0], "hops": row[1]} for row in res]


def get_covering_tests(
    g, function_id: str, min_confidence: float = 0.0
) -> list[dict[str, Any]]:
    """Find tests covering a given function, ordered by confidence."""
    q = (
        "MATCH (f:Function {id: $id})-[e:COVERED_BY]->(t:Test) "
        "WHERE e.confidence >= $min_conf "
        "RETURN t.id AS test_id, e.confidence AS confidence, e.source AS source "
        "ORDER BY confidence DESC"
    )
    res = g.query(q, {"id": function_id, "min_conf": min_confidence}).result_set
    return [
        {"test_id": row[0], "confidence": row[1], "source": row[2]}
        for row in res
    ]
