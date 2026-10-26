"""FalkorDB GraphStore implementation for Guard.

Preserves FalkorDB functionality for remote servers, Docker, or distributed setups.
"""
from __future__ import annotations

import time
from typing import Any, Sequence

from guard_cli.store.base import (
    CallerRecord,
    CoveringTestRecord,
    FunctionNode,
    GraphStore,
    TestNode,
)


class FalkorDBGraphStore(GraphStore):
    """Adapter wrapping a FalkorDB Graph object to conform to GraphStore interface."""

    def __init__(self, falkor_graph: Any):
        self.graph = falkor_graph
        self.graph_name = getattr(falkor_graph, "name", "guard")

    @property
    def name(self) -> str:
        return "falkordb"

    def __getattr__(self, name: str) -> Any:
        return getattr(self.graph, name)

    def query(self, q: str, params: dict[str, Any] | None = None) -> Any:
        """Direct query pass-through for legacy FalkorDB callers."""
        return self.graph.query(q, params)

    def ensure_schema(self) -> None:
        indexes = [
            "CREATE INDEX FOR (f:Function) ON (f.id)",
            "CREATE INDEX FOR (t:Test) ON (t.id)",
            "CREATE INDEX FOR (x:File) ON (x.path)",
            "CREATE INDEX FOR (r:Run) ON (r.id)",
            "CREATE INDEX FOR (m:GuardMeta) ON (m.id)",
        ]
        for q in indexes:
            try:
                self.graph.query(q)
            except Exception:
                pass

    def reset_graph(self) -> None:
        try:
            self.graph.delete()
        except Exception:
            pass
        self.ensure_schema()

    def get_schema_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for label in ("File", "Function", "Test", "Run"):
            try:
                res = self.graph.query(f"MATCH (n:{label}) RETURN count(n)").result_set
                counts[label] = res[0][0] if res else 0
            except Exception:
                counts[label] = 0

        for rel in ("CALLS", "IMPORTS", "DEFINED_IN", "COVERED_BY", "FAILED_IN"):
            try:
                res = self.graph.query(f"MATCH ()-[e:{rel}]->() RETURN count(e)").result_set
                counts[rel] = res[0][0] if res else 0
            except Exception:
                counts[rel] = 0

        try:
            res = self.graph.query(
                "MATCH (f:Function {has_dynamic_dispatch: true}) RETURN count(f)"
            ).result_set
            counts["dynamic_functions"] = res[0][0] if res else 0
        except Exception:
            counts["dynamic_functions"] = 0

        return counts

    def get_graph_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        try:
            res = self.graph.query(
                "MATCH (m:GuardMeta {id: 'meta'}) RETURN m.updated_at, m.generation, m.commit_sha"
            ).result_set
            if res and res[0]:
                meta["updated_at"] = res[0][0]
                meta["generation"] = res[0][1]
                if len(res[0]) > 2 and res[0][2]:
                    meta["commit_sha"] = res[0][2]
        except Exception:
            pass
        return meta

    def update_graph_meta(self, commit_sha: str | None = None) -> None:
        ts = time.time()
        try:
            self.graph.query(
                """MERGE (m:GuardMeta {id: 'meta'})
                   SET m.updated_at = $ts,
                       m.generation = coalesce(m.generation, 0) + 1,
                       m.commit_sha = coalesce($sha, m.commit_sha)""",
                {"ts": ts, "sha": commit_sha},
            )
        except Exception:
            pass

    def get_functions_for_file(self, file_path: str) -> list[FunctionNode]:
        q = (
            "MATCH (f:Function) "
            "WHERE f.file = $file OR f.file ENDS WITH $file OR $file ENDS WITH f.file "
            "RETURN f.id, f.file, f.name, f.qualname, f.start, f.end, "
            "coalesce(f.no_evidence, false), coalesce(f.has_dynamic_dispatch, false)"
        )
        res = self.graph.query(q, {"file": file_path}).result_set
        return [
            FunctionNode(
                id=r[0],
                file=r[1],
                name=r[2],
                qualname=r[3] if len(r) > 3 else r[2],
                start=int(r[4]),
                end=int(r[5]),
                no_evidence=bool(r[6]),
                has_dynamic_dispatch=bool(r[7]),
            )
            for r in res
        ]

    def get_all_functions(self) -> list[FunctionNode]:
        q = (
            "MATCH (f:Function) "
            "RETURN f.id, f.file, f.name, f.qualname, f.start, f.end, "
            "coalesce(f.no_evidence, false), coalesce(f.has_dynamic_dispatch, false)"
        )
        res = self.graph.query(q).result_set
        return [
            FunctionNode(
                id=r[0],
                file=r[1],
                name=r[2],
                qualname=r[3] if len(r) > 3 else r[2],
                start=int(r[4]),
                end=int(r[5]),
                no_evidence=bool(r[6]),
                has_dynamic_dispatch=bool(r[7]),
            )
            for r in res
        ]

    def get_covering_tests(
        self, function_id: str, min_confidence: float = 0.0
    ) -> list[CoveringTestRecord]:
        q = (
            "MATCH (f:Function {id: $id})-[e:COVERED_BY]->(t:Test) "
            "WHERE e.confidence >= $min_conf "
            "RETURN t.id AS test_id, e.confidence AS confidence, e.source AS source, e.last_verified_sha AS sha "
            "ORDER BY confidence DESC"
        )
        res = self.graph.query(q, {"id": function_id, "min_conf": min_confidence}).result_set
        return [
            CoveringTestRecord(
                test_id=row[0],
                confidence=float(row[1]),
                source=row[2] or "coverage",
                last_verified_sha=row[3] if len(row) > 3 else None,
            )
            for row in res
        ]

    def get_multi_hop_tests(
        self, function_id: str, max_depth: int = 2, min_confidence: float = 0.0
    ) -> list[CoveringTestRecord]:
        q = (
            f"MATCH (f:Function {{id: $id}})-[:CALLS*1..{max_depth}]->(target:Function)-[e:COVERED_BY]->(t:Test) "
            "WHERE e.confidence >= $min_conf "
            "RETURN DISTINCT t.id, e.confidence, e.source, e.last_verified_sha "
            "ORDER BY e.confidence DESC"
        )
        res = self.graph.query(q, {"id": function_id, "min_conf": min_confidence}).result_set
        return [
            CoveringTestRecord(
                test_id=row[0],
                confidence=float(row[1]),
                source=row[2] or "coverage",
                last_verified_sha=row[3] if len(row) > 3 else None,
            )
            for row in res
        ]

    def get_callers(
        self, function_id: str, hops: int = 4, min_confidence: float = 0.0
    ) -> list[CallerRecord]:
        q = (
            f"MATCH p=(caller:Function)-[:CALLS*1..{hops}]->(target:Function {{id: $id}}) "
            "WHERE all(e IN relationships(p) WHERE coalesce(e.confidence, 0.6) >= $min_conf) "
            "RETURN caller.id AS caller, min(length(p)) AS hops "
            "ORDER BY hops, caller"
        )
        res = self.graph.query(q, {"id": function_id, "min_conf": min_confidence}).result_set
        return [CallerRecord(caller=row[0], hops=int(row[1])) for row in res]

    def get_module_tests(self, mod_stem: str) -> list[str]:
        q = "MATCH (t:Test) WHERE t.file CONTAINS $mod_stem RETURN t.id"
        try:
            res = self.graph.query(q, {"mod_stem": mod_stem}).result_set
            return [r[0] for r in res]
        except Exception:
            return []

    def _batches(self, rows: Sequence[Any], size: int = 500):
        for i in range(0, len(rows), size):
            yield rows[i : i + size]

    def write_static(self, result: Any, commit_sha: str | None = None) -> None:
        self.ensure_schema()
        # 1. File nodes
        for b in self._batches(result.file_rows()):
            self.graph.query("UNWIND $rows AS r MERGE (x:File {path: r.path})", {"rows": b})

        # 2. Function nodes & DEFINED_IN edges
        for b in self._batches(result.function_rows()):
            self.graph.query(
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
            for b in self._batches(result.test_rows()):
                self.graph.query(
                    """UNWIND $rows AS r
                       MERGE (t:Test {id: r.id})
                       SET t.file = r.file, t.name = r.name, t.qualname = r.qualname,
                           t.start = r.start, t.end = r.end
                       WITH t, r
                       MATCH (x:File {path: r.file})
                       MERGE (t)-[:DEFINED_IN]->(x)""",
                    {"rows": b},
                )

        # 4. CALLS edges
        for b in self._batches(result.call_rows()):
            self.graph.query(
                """UNWIND $rows AS r
                   MATCH (a:Function {id: r.src}), (b:Function {id: r.dst})
                   MERGE (a)-[e:CALLS]->(b)
                   SET e.source = 'static',
                       e.confidence = 0.6,
                       e.evidence_count = coalesce(e.evidence_count, 0),
                       e.last_verified_sha = $sha""",
                {"rows": b, "sha": commit_sha},
            )

        # 5. IMPORTS edges
        for b in self._batches(result.import_rows()):
            self.graph.query(
                """UNWIND $rows AS r
                   MATCH (a:File {path: r.src}), (b:File {path: r.dst})
                   MERGE (a)-[e:IMPORTS]->(b)
                   SET e.source = 'static',
                       e.confidence = 0.6,
                       e.last_verified_sha = $sha""",
                {"rows": b, "sha": commit_sha},
            )
        self.update_graph_meta(commit_sha=commit_sha)

    def write_coverage(
        self,
        test_to_funcs: dict[str, list[str]] | list[dict[str, str]],
        commit_sha: str | None = None,
        confidence: float = 0.9,
    ) -> int:
        self.ensure_schema()
        if isinstance(test_to_funcs, dict):
            pairs = [
                {"test": t_id, "func": f_id}
                for t_id, funcs in test_to_funcs.items()
                for f_id in funcs
            ]
        else:
            pairs = list(test_to_funcs)

        for b in self._batches(pairs):
            self.graph.query(
                """UNWIND $rows AS r
                   MATCH (f:Function {id: r.func}), (t:Test {id: r.test})
                   MERGE (f)-[e:COVERED_BY]->(t)
                   SET e.source = 'coverage',
                       e.confidence = $conf,
                       e.evidence_count = coalesce(e.evidence_count, 0) + 1,
                       e.last_verified_sha = $sha""",
                {"rows": b, "conf": confidence, "sha": commit_sha},
            )
        self.update_graph_meta(commit_sha=commit_sha)
        return len(pairs)

    def write_run(
        self,
        run_data: dict[str, Any],
        failures: list[dict[str, Any]] | None = None,
    ) -> None:
        self.graph.query(
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
            for b in self._batches(failures):
                self.graph.query(
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

    def set_function_evidence_flags(
        self, covered_ids: Sequence[str], uncovered_ids: Sequence[str]
    ) -> None:
        if uncovered_ids:
            for b in self._batches([{"id": fid} for fid in uncovered_ids]):
                self.graph.query(
                    """UNWIND $rows AS r
                       MATCH (f:Function {id: r.id})
                       SET f.no_evidence = true""",
                    {"rows": b},
                )
        if covered_ids:
            for b in self._batches([{"id": fid} for fid in covered_ids]):
                self.graph.query(
                    """UNWIND $rows AS r
                       MATCH (f:Function {id: r.id})
                       SET f.no_evidence = false""",
                    {"rows": b},
                )

    def set_test_flake_rates(self, flake_rates: dict[str, float]) -> None:
        flake_rows = [{"test_id": tid, "rate": rate} for tid, rate in flake_rates.items()]
        for b in self._batches(flake_rows):
            self.graph.query(
                """UNWIND $rows AS r
                   MATCH (t:Test {id: r.test_id})
                   SET t.flake_rate = r.rate""",
                {"rows": b},
            )
        self.graph.query("MATCH (t:Test) WHERE t.flake_rate IS NULL SET t.flake_rate = 0.0")

    def record_miss_repair(
        self,
        function_id: str,
        test_id: str,
        new_confidence: float = 1.0,
    ) -> dict[str, Any]:
        q_existing = (
            "MATCH (f:Function {id: $fid})-[e:COVERED_BY]->(t:Test {id: $tid}) "
            "RETURN e.confidence, e.source"
        )
        existing_res = self.graph.query(q_existing, {"fid": function_id, "tid": test_id}).result_set
        if existing_res:
            old_confidence = float(existing_res[0][0])
            prev_source = existing_res[0][1]
        else:
            old_confidence = 0.0
            prev_source = None

        ts = time.time()
        file_part = test_id.split("::")[0] if "::" in test_id else "tests/unknown.py"
        self.graph.query(
            "MERGE (t:Test {id: $tid}) "
            "ON CREATE SET t.file = $file, t.flake_rate = 0.0",
            {"tid": test_id, "file": file_part},
        )
        q_repair = (
            """MATCH (f:Function {id: $fid}), (t:Test {id: $tid})
               MERGE (f)-[e:COVERED_BY]->(t)
               SET e.source = 'miss_repair',
                   e.old_confidence = $old_conf,
                   e.confidence = $new_conf,
                   e.evidence_count = coalesce(e.evidence_count, 0) + 1,
                   e.last_repaired_at = $ts
               WITH f
               SET f.no_evidence = false"""
        )
        self.graph.query(
            q_repair,
            {
                "fid": function_id,
                "tid": test_id,
                "old_conf": old_confidence,
                "new_conf": new_confidence,
                "ts": ts,
            },
        )
        self.update_graph_meta()

        return {
            "status": "repaired",
            "function": function_id,
            "test": test_id,
            "old_confidence": old_confidence,
            "new_confidence": new_confidence,
            "source": "miss_repair",
            "previous_source": prev_source,
        }
