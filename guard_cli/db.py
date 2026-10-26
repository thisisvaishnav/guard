"""Database and graph operations facade for Guard.

Delegates core graph interactions to the underlying GraphStore (SQLite or FalkorDB).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from guard_cli.backend import (
    GRAPH_NAME,
    DockerBackend,
    EmbeddedBackend,
    ServerBackend,
    get_backend,
    resolve_backend,
)
from guard_cli.store.base import (
    CallerRecord,
    CoveringTestRecord,
    FunctionNode,
    GraphStore,
    TestNode,
)
from guard_cli.store.falkordb import FalkorDBGraphStore


def _batches(items: list[Any], size: int = 500):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def get_backend_for_env(repo_path: Path | str | None = None):
    """Factory preserving legacy FALKORDB_* overrides while supporting SQLite."""
    if os.getenv("FALKORDB_SERVER_URL"):
        return ServerBackend(url=os.getenv("FALKORDB_SERVER_URL"))
    if os.getenv("FALKORDB_HOST") or os.getenv("FALKORDB_PORT"):
        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", "6379"))
        return ServerBackend(host=host, port=port)
    return resolve_backend(repo_path=repo_path)


def get_graph(
    name: str | None = None,
    backend: Any = None,
    repo_path: Any = None,
):
    """Retrieve GraphStore using resolved backend and repository name."""
    if backend is None:
        backend = get_backend(repo_path=repo_path)
    if name is None:
        from guard_cli.backend import load_config

        cfg = load_config(repo_path)
        name = cfg.get("backend", {}).get("graph_name") or os.getenv(
            "GUARD_GRAPH", GRAPH_NAME
        )

    raw_g = backend.get_graph(name)
    if isinstance(raw_g, GraphStore):
        store = raw_g
    else:
        # Wrap raw FalkorDB graph in FalkorDBGraphStore
        store = FalkorDBGraphStore(raw_g)

    if repo_path is not None and store is not None:
        try:
            store.repo_path = Path(repo_path)
        except Exception:
            pass
    return store


def reset_graph(g) -> None:
    if hasattr(g, "reset_graph"):
        g.reset_graph()
        return
    try:
        g.delete()
    except Exception:
        pass


def ensure_schema(g) -> None:
    """Ensure indexes exist for performance."""
    if hasattr(g, "ensure_schema"):
        g.ensure_schema()
        return
    indexes = [
        "CREATE INDEX IF NOT EXISTS FOR (f:Function) ON (f.id)",
        "CREATE INDEX IF NOT EXISTS FOR (f:Function) ON (f.file)",
        "CREATE INDEX IF NOT EXISTS FOR (t:Test) ON (t.id)",
        "CREATE INDEX IF NOT EXISTS FOR (fi:File) ON (fi.path)",
        "CREATE INDEX IF NOT EXISTS FOR (r:Run) ON (r.id)",
    ]
    for idx in indexes:
        try:
            g.query(idx)
        except Exception:
            pass


def write_static(g, result: Any, commit_sha: str | None = None) -> None:
    """Write StaticResult nodes and edges into FalkorDB or SQLite store with T2 schema requirements."""
    if hasattr(g, "write_static"):
        g.write_static(result, commit_sha=commit_sha)
        return

    ensure_schema(g)

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
               MATCH (c:Function {id: r.caller}), (e:Function {id: r.callee})
               MERGE (c)-[rel:CALLS]->(e)
               SET rel.source = 'static', rel.confidence = 0.6,
                   rel.evidence_count = 0, rel.last_verified_sha = $sha""",
            {"rows": b, "sha": commit_sha},
        )

    # 5. IMPORTS edges (File -> File)
    for b in _batches(result.import_rows()):
        g.query(
            """UNWIND $rows AS r
               MATCH (src:File {path: r.src}), (dst:File {path: r.dst})
               MERGE (src)-[rel:IMPORTS]->(dst)
               SET rel.source = 'static', rel.confidence = 0.6,
                   rel.last_verified_sha = $sha""",
            {"rows": b, "sha": commit_sha},
        )

    update_graph_meta(g, commit_sha=commit_sha)


def write_coverage(
    g,
    test_to_funcs: dict[str, list[str]] | list[dict[str, Any]] | None = None,
    commit_sha: str | None = None,
    confidence: float = 0.9,
    **kwargs: Any,
) -> int:
    """Write COVERED_BY edges connecting Functions to Tests."""
    if test_to_funcs is None:
        test_to_funcs = kwargs.get("pairs", [])
    if "pairs" in kwargs and not test_to_funcs:
        test_to_funcs = kwargs["pairs"]
    if "confidence" in kwargs:
        confidence = kwargs["confidence"]
    if "commit_sha" in kwargs:
        commit_sha = kwargs["commit_sha"]

    if hasattr(g, "write_coverage"):
        return g.write_coverage(test_to_funcs, commit_sha=commit_sha, confidence=confidence)

    ensure_schema(g)

    if isinstance(test_to_funcs, dict):
        pairs = [
            {"func": f_id, "test": t_id}
            for t_id, funcs in test_to_funcs.items()
            for f_id in funcs
        ]
    else:
        pairs = []
        for item in test_to_funcs:
            f = item.get("func") or item.get("function_id")
            t = item.get("test") or item.get("test_id")
            pairs.append({"func": f, "test": t})

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
    update_graph_meta(g, commit_sha=commit_sha)
    return len(pairs)


def update_graph_meta(
    g: Any = None,
    repo_path: Path | str | None = None,
    commit_sha: str | None = None,
) -> None:
    """Updates Guard metadata generation and timestamp in the graph and repository."""
    if g is None and repo_path is None:
        return
    if hasattr(g, "update_graph_meta"):
        g.update_graph_meta(commit_sha=commit_sha)

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
    target_repo = repo_path or (
        getattr(g, "repo_path", None) if g is not None else None
    )
    if target_repo and isinstance(target_repo, (str, Path)):
        try:
            meta_path = Path(target_repo) / ".guard" / "graph_meta.json"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_data = {
                "updated_at": ts,
                "generation": new_gen,
            }
            meta_path.write_text(
                json.dumps(meta_data, indent=2) + "\n", encoding="utf-8"
            )
        except Exception:
            pass

    # 3. FalkorDB query fallback if connected
    if g is not None and not hasattr(g, "update_graph_meta"):
        try:
            g.query(
                "MERGE (m:GuardMeta {id: 'meta'}) "
                "SET m.updated_at = $ts, m.generation = coalesce(m.generation, 0) + 1",
                {"ts": ts},
            )
        except Exception:
            pass


def get_graph_state(
    g: Any = None, repo_path: Path | str | None = None
) -> dict[str, Any]:
    """Returns a dictionary summarizing graph state for cache invalidation."""
    if g is None and repo_path is None:
        return {"status": "none"}

    meta: dict[str, Any] = {}

    # 1. Check store native meta
    if hasattr(g, "get_graph_meta"):
        try:
            meta.update(g.get_graph_meta())
        except Exception:
            pass

    # 2. Check in-memory object metadata
    if g is not None:
        obj_meta = getattr(g, "_guard_meta", None)
        if isinstance(obj_meta, dict):
            meta.update(obj_meta)

    # 3. Check repo-level graph_meta.json or state.json
    target_repo = repo_path or (
        getattr(g, "repo_path", None) if g is not None else None
    )
    if target_repo and isinstance(target_repo, (str, Path)):
        try:
            meta_file = Path(target_repo) / ".guard" / "graph_meta.json"
            if meta_file.exists():
                file_meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if isinstance(file_meta, dict):
                    if int(file_meta.get("generation", 0)) >= int(
                        meta.get("generation", 0)
                    ):
                        meta.update(file_meta)
            else:
                state_file = Path(target_repo) / ".guard" / "state.json"
                if state_file.exists():
                    state_data = json.loads(
                        state_file.read_text(encoding="utf-8")
                    )
                    if isinstance(state_data, dict):
                        if "ingested_at" in state_data:
                            meta.setdefault(
                                "ingested_at", state_data["ingested_at"]
                            )
                        if "head_sha" in state_data:
                            meta.setdefault(
                                "head_sha", state_data["head_sha"]
                            )
        except Exception:
            pass

    # 4. FalkorDB query fallback if connected
    if g is not None and not hasattr(g, "get_graph_meta"):
        try:
            res = g.query(
                "MATCH (m:GuardMeta {id: 'meta'}) RETURN m.updated_at,"
                " m.generation"
            ).result_set
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
    """Write a Run node and optional FAILED_IN edges."""
    if hasattr(g, "write_run"):
        g.write_run(run_data, failures=failures)
        return

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
                   MATCH (t:Test {id: f.test_id}), (r:Run {id: $run_id})\n                   MERGE (t)-[e:FAILED_IN]->(r)
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
    if hasattr(g, "get_schema_counts"):
        return g.get_schema_counts()

    counts = {}
    for label in ("File", "Function", "Test", "Run"):
        try:
            res = g.query(f"MATCH (n:{label}) RETURN count(n)").result_set
            counts[label] = (
                res[0][0] if (res and isinstance(res[0][0], int)) else 0
            )
        except Exception:
            counts[label] = 0

    for rel in ("CALLS", "IMPORTS", "DEFINED_IN", "COVERED_BY", "FAILED_IN"):
        try:
            res = g.query(f"MATCH ()-[e:{rel}]->() RETURN count(e)").result_set
            counts[rel] = (
                res[0][0] if (res and isinstance(res[0][0], int)) else 0
            )
        except Exception:
            counts[rel] = 0

    return counts


def get_covering_tests(
    g, function_id: str, min_confidence: float = 0.0
) -> list[CoveringTestRecord]:
    """Return list of tests that cover this function above confidence threshold."""
    if hasattr(g, "get_covering_tests"):
        return g.get_covering_tests(
            function_id, min_confidence=min_confidence
        )

    res = g.query(
        """MATCH (f:Function {id: $fid})-[e:COVERED_BY]->(t:Test)
           WHERE e.confidence >= $conf
           RETURN t.id, t.file, e.confidence, e.source""",
        {"fid": function_id, "conf": min_confidence},
    ).result_set

    tests = []
    for row in res:
        tests.append(
            CoveringTestRecord(
                test_id=row[0],
                confidence=float(row[2]),
                source=row[3],
            )
        )
    return tests


def get_callers(
    g, function_id: str, hops: int = 4, min_confidence: float = 0.0, **kwargs: Any
) -> list[CallerRecord]:
    """Traverse incoming CALLS edges up to hops."""
    if "max_depth" in kwargs:
        hops = kwargs["max_depth"]
    if hasattr(g, "get_callers"):
        return g.get_callers(function_id, hops=hops, min_confidence=min_confidence)

    res = g.query(
        f"""MATCH path = (caller:Function)-[:CALLS*1..{hops}]->(target:Function {{id: $fid}})
           WHERE all(e IN relationships(path) WHERE coalesce(e.confidence, 0.6) >= $min_conf)
           RETURN caller.id AS caller, min(length(path)) AS hops
           ORDER BY hops, caller""",
        {"fid": function_id, "min_conf": min_confidence},
    ).result_set

    callers = []
    seen = set()
    for row in res:
        cid, depth = row[0], int(row[1])
        if cid not in seen:
            seen.add(cid)
            callers.append(
                CallerRecord(caller=cid, hops=depth)
            )
    return callers
