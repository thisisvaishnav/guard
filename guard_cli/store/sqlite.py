"""SQLite embedded GraphStore implementation for Guard.

Zero background daemons, zero external dependencies, standard library sqlite3.
Stores graph nodes, call relationships, and dynamic test coverage in .guard/graph.db.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Sequence

from guard_cli.store.base import (
    CallerRecord,
    CoveringTestRecord,
    FunctionNode,
    GraphStore,
    TestNode,
)


class SQLiteGraphStore(GraphStore):
    """Fast, embedded SQLite storage for Guard's code and coverage graph."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def name(self) -> str:
        return "sqlite"

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            # Performance pragmas
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._init_schema_tables(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _init_schema_tables(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS functions (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    qualname TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    has_dynamic_dispatch INTEGER DEFAULT 0,
                    no_evidence INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_func_file ON functions(file_path);
                CREATE INDEX IF NOT EXISTS idx_func_lines ON functions(file_path, start_line, end_line);

                CREATE TABLE IF NOT EXISTS tests (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    qualname TEXT DEFAULT '',
                    start_line INTEGER DEFAULT 0,
                    end_line INTEGER DEFAULT 0,
                    flake_rate REAL DEFAULT 0.0
                );
                CREATE INDEX IF NOT EXISTS idx_test_file ON tests(file_path);

                CREATE TABLE IF NOT EXISTS calls (
                    caller_id TEXT NOT NULL,
                    callee_id TEXT NOT NULL,
                    source TEXT DEFAULT 'static',
                    confidence REAL DEFAULT 0.6,
                    evidence_count INTEGER DEFAULT 0,
                    last_verified_sha TEXT,
                    PRIMARY KEY (caller_id, callee_id)
                );
                CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller_id);
                CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee_id);

                CREATE TABLE IF NOT EXISTS imports (
                    src_path TEXT NOT NULL,
                    dst_path TEXT NOT NULL,
                    source TEXT DEFAULT 'static',
                    confidence REAL DEFAULT 0.6,
                    last_verified_sha TEXT,
                    PRIMARY KEY (src_path, dst_path)
                );

                CREATE TABLE IF NOT EXISTS covered_by (
                    function_id TEXT NOT NULL,
                    test_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    evidence_count INTEGER DEFAULT 1,
                    last_verified_sha TEXT,
                    old_confidence REAL DEFAULT 0.0,
                    last_repaired_at REAL,
                    PRIMARY KEY (function_id, test_id)
                );
                CREATE INDEX IF NOT EXISTS idx_cov_func ON covered_by(function_id, confidence);
                CREATE INDEX IF NOT EXISTS idx_cov_test ON covered_by(test_id);

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    timestamp REAL,
                    commit_sha TEXT,
                    duration_ms REAL,
                    total_tests INTEGER,
                    passed INTEGER,
                    failed INTEGER
                );

                CREATE TABLE IF NOT EXISTS failed_in (
                    test_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    source TEXT DEFAULT 'test_run',
                    error_message TEXT,
                    commit_sha TEXT,
                    PRIMARY KEY (test_id, run_id)
                );

                CREATE TABLE IF NOT EXISTS guard_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

    def reset_graph(self) -> None:
        self.close()
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass
        # Clean WAL / SHM files if present
        wal = self.db_path.with_name(f"{self.db_path.name}-wal")
        shm = self.db_path.with_name(f"{self.db_path.name}-shm")
        for f in (wal, shm):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
        self.ensure_schema()

    def get_schema_counts(self) -> dict[str, int]:
        conn = self._get_connection()
        counts: dict[str, int] = {}
        for table, label in [
            ("files", "File"),
            ("functions", "Function"),
            ("tests", "Test"),
            ("runs", "Run"),
            ("calls", "CALLS"),
            ("imports", "IMPORTS"),
            ("covered_by", "COVERED_BY"),
            ("failed_in", "FAILED_IN"),
        ]:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                counts[label] = int(row["c"]) if row else 0
            except Exception:
                counts[label] = 0

        # DEFINED_IN is the relationship linking functions and tests to their files
        counts["DEFINED_IN"] = counts.get("Function", 0) + counts.get("Test", 0)

        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM functions WHERE has_dynamic_dispatch = 1"
            ).fetchone()
            counts["dynamic_functions"] = int(row["c"]) if row else 0
        except Exception:
            counts["dynamic_functions"] = 0

        return counts

    def get_graph_meta(self) -> dict[str, Any]:
        conn = self._get_connection()
        meta: dict[str, Any] = {}
        try:
            rows = conn.execute("SELECT key, value FROM guard_meta").fetchall()
            for r in rows:
                meta[r["key"]] = r["value"]
            if "updated_at" in meta:
                try:
                    meta["updated_at"] = float(meta["updated_at"])
                except ValueError:
                    pass
            if "generation" in meta:
                try:
                    meta["generation"] = int(meta["generation"])
                except ValueError:
                    pass
        except Exception:
            pass
        return meta

    def update_graph_meta(self, commit_sha: str | None = None) -> None:
        conn = self._get_connection()
        now = time.time()
        with conn:
            meta = self.get_graph_meta()
            gen = int(meta.get("generation", 0)) + 1
            conn.execute(
                "INSERT OR REPLACE INTO guard_meta (key, value) VALUES ('updated_at', ?)",
                (str(now),),
            )
            conn.execute(
                "INSERT OR REPLACE INTO guard_meta (key, value) VALUES ('generation', ?)",
                (str(gen),),
            )
            if commit_sha:
                conn.execute(
                    "INSERT OR REPLACE INTO guard_meta (key, value) VALUES ('commit_sha', ?)",
                    (str(commit_sha),),
                )

    def ensure_schema(self) -> None:
        conn = self._get_connection()
        self._init_schema_tables(conn)

    def query(self, query_str: str, params: dict[str, Any] | None = None) -> Any:
        class QueryResult:
            def __init__(self, result_set: list[Any]):
                self.result_set = result_set

        conn = self._get_connection()
        q = query_str.strip()
        p = params or {}

        # 1. SET f.no_evidence
        if "SET f.no_evidence" in q:
            m = re.search(r"id:\s*['\"]([^'\"]+)['\"]", q)
            fid = m.group(1) if m else p.get("fid")
            val = 1 if "true" in q.lower() else 0
            with conn:
                conn.execute("UPDATE functions SET no_evidence = ? WHERE id = ?", (val, fid))
            return QueryResult([])

        # 2. MATCH (r:Run) RETURN count(r)
        if "MATCH (r:Run) RETURN count(r)" in q:
            row = conn.execute("SELECT count(*) FROM runs").fetchone()
            return QueryResult([[row[0]]])

        # 3. MATCH (r:Run) RETURN r.id, r.passed
        if "MATCH (r:Run) RETURN r.id, r.passed" in q:
            rows = conn.execute("SELECT id, passed FROM runs").fetchall()
            return QueryResult([[r["id"], r["passed"]] for r in rows])

        # 4. MATCH (t:Test) RETURN count(t)
        if "MATCH (t:Test) RETURN count(t)" in q:
            row = conn.execute("SELECT count(*) FROM tests").fetchone()
            return QueryResult([[row[0]]])

        # 5. MATCH (t:Test) RETURN t.id, t.flake_rate
        if "MATCH (t:Test) RETURN t.id, t.flake_rate" in q:
            rows = conn.execute("SELECT id, flake_rate FROM tests ORDER BY id").fetchall()
            return QueryResult([[r["id"], r["flake_rate"]] for r in rows])

        # 6. MATCH (t:Test) WHERE t.flake_rate IS NULL SET t.flake_rate = 0.0
        if "WHERE t.flake_rate IS NULL SET" in q:
            with conn:
                conn.execute("UPDATE tests SET flake_rate = 0.0 WHERE flake_rate IS NULL")
            return QueryResult([])

        # 7. MATCH (f:Function ... RETURN f.no_evidence
        if "RETURN f.no_evidence" in q:
            m = re.search(r"id:\s*['\"]([^'\"]+)['\"]", q)
            fid = m.group(1) if m else p.get("fid")
            row = conn.execute("SELECT no_evidence FROM functions WHERE id = ?", (fid,)).fetchone()
            val = bool(row["no_evidence"]) if row else False
            return QueryResult([[val]])

        # 8. CALLS edge return
        if "CALLS" in q and "RETURN" in q:
            rows = conn.execute("SELECT source, confidence, evidence_count, last_verified_sha FROM calls").fetchall()
            return QueryResult([[r["source"], r["confidence"], r["evidence_count"], r["last_verified_sha"]] for r in rows])

        # 9. FAILED_IN edge return
        if "FAILED_IN" in q and "RETURN" in q:
            rows = conn.execute("SELECT test_id, run_id, error_message, source FROM failed_in").fetchall()
            return QueryResult([[r["test_id"], r["run_id"], r["error_message"], r["source"]] for r in rows])

        # 10. COVERED_BY edge return
        if "COVERED_BY" in q and "RETURN" in q:
            m_fid = re.search(r"""Function\s*\{id:\s*['"]([^'"]+)['"]""", q)
            m_tid = re.search(r"""Test\s*\{id:\s*['"]([^'"]+)['"]""", q)
            fid = m_fid.group(1) if m_fid else p.get("fid")
            tid = m_tid.group(1) if m_tid else p.get("tid")
            if fid and tid:
                rows = conn.execute("SELECT function_id, test_id, source, confidence, evidence_count, last_verified_sha FROM covered_by WHERE function_id = ? AND test_id = ?", (fid, tid)).fetchall()
            elif fid:
                rows = conn.execute("SELECT function_id, test_id, source, confidence, evidence_count, last_verified_sha FROM covered_by WHERE function_id = ?", (fid,)).fetchall()
            else:
                rows = conn.execute("SELECT function_id, test_id, source, confidence, evidence_count, last_verified_sha FROM covered_by").fetchall()

            ret_part = q.split("RETURN", 1)[1].strip()
            cols = [c.strip() for c in ret_part.split(",")]
            res = []
            for r in rows:
                items = []
                for c in cols:
                    if c in ("f.id", "function_id"):
                        items.append(r["function_id"])
                    elif c in ("t.id", "test_id"):
                        items.append(r["test_id"])
                    elif c == "e.source":
                        items.append(r["source"])
                    elif c == "e.confidence":
                        items.append(float(r["confidence"]))
                    elif c == "e.old_confidence":
                        items.append(0.0)
                    elif c == "e.evidence_count":
                        items.append(r["evidence_count"])
                    elif c == "e.last_verified_sha":
                        items.append(r["last_verified_sha"])
                    else:
                        items.append(None)
                res.append(items)
            return QueryResult(res)

        # 11. Generic fallback
        try:
            cur = conn.execute(q, p)
            if cur.description:
                rows = [list(r) for r in cur.fetchall()]
                return QueryResult(rows)
            return QueryResult([])
        except Exception:
            return QueryResult([])

    def get_functions_for_file(self, file_path: str) -> list[FunctionNode]:
        conn = self._get_connection()
        norm = file_path.replace("\\", "/")
        # Match exact path, prefix match, or suffix match
        sql = """
            SELECT id, file_path, name, qualname, start_line, end_line,
                   has_dynamic_dispatch, no_evidence
            FROM functions
            WHERE file_path = ?
               OR file_path LIKE ('%' || ?)
               OR ? LIKE ('%' || file_path)
        """
        rows = conn.execute(sql, (norm, norm, norm)).fetchall()
        return [
            FunctionNode(
                id=r["id"],
                file=r["file_path"],
                name=r["name"],
                qualname=r["qualname"],
                start=int(r["start_line"]),
                end=int(r["end_line"]),
                has_dynamic_dispatch=bool(r["has_dynamic_dispatch"]),
                no_evidence=bool(r["no_evidence"]),
            )
            for r in rows
        ]

    def get_all_functions(self) -> list[FunctionNode]:
        conn = self._get_connection()
        sql = """
            SELECT id, file_path, name, qualname, start_line, end_line,
                   has_dynamic_dispatch, no_evidence
            FROM functions
        """
        rows = conn.execute(sql).fetchall()
        return [
            FunctionNode(
                id=r["id"],
                file=r["file_path"],
                name=r["name"],
                qualname=r["qualname"],
                start=int(r["start_line"]),
                end=int(r["end_line"]),
                has_dynamic_dispatch=bool(r["has_dynamic_dispatch"]),
                no_evidence=bool(r["no_evidence"]),
            )
            for r in rows
        ]

    def get_covering_tests(
        self, function_id: str, min_confidence: float = 0.0
    ) -> list[CoveringTestRecord]:
        conn = self._get_connection()
        sql = """
            SELECT test_id, confidence, source, last_verified_sha
            FROM covered_by
            WHERE function_id = ? AND confidence >= ?
            ORDER BY confidence DESC
        """
        rows = conn.execute(sql, (function_id, min_confidence)).fetchall()
        return [
            CoveringTestRecord(
                test_id=r["test_id"],
                confidence=float(r["confidence"]),
                source=r["source"],
                last_verified_sha=r["last_verified_sha"],
            )
            for r in rows
        ]

    def get_multi_hop_tests(
        self, function_id: str, max_depth: int = 2, min_confidence: float = 0.0
    ) -> list[CoveringTestRecord]:
        conn = self._get_connection()
        sql = """
            WITH RECURSIVE reachable(target_id, depth) AS (
                SELECT callee_id, 1 FROM calls WHERE caller_id = :fid
                UNION
                SELECT c.callee_id, r.depth + 1
                FROM calls c
                JOIN reachable r ON c.caller_id = r.target_id
                WHERE r.depth < :max_depth
            )
            SELECT DISTINCT cb.test_id, cb.confidence, cb.source, cb.last_verified_sha
            FROM reachable rf
            JOIN covered_by cb ON cb.function_id = rf.target_id
            WHERE cb.confidence >= :min_conf
            ORDER BY cb.confidence DESC
        """
        rows = conn.execute(
            sql,
            {
                "fid": function_id,
                "max_depth": max_depth,
                "min_conf": min_confidence,
            },
        ).fetchall()
        return [
            CoveringTestRecord(
                test_id=r["test_id"],
                confidence=float(r["confidence"]),
                source=r["source"],
                last_verified_sha=r["last_verified_sha"],
            )
            for r in rows
        ]

    def get_callers(
        self, function_id: str, hops: int = 4, min_confidence: float = 0.0
    ) -> list[CallerRecord]:
        conn = self._get_connection()
        sql = """
            WITH RECURSIVE callers_path(caller, hops) AS (
                SELECT caller_id, 1
                FROM calls
                WHERE callee_id = :fid AND confidence >= :min_conf
                UNION
                SELECT c.caller_id, cp.hops + 1
                FROM calls c
                JOIN callers_path cp ON c.callee_id = cp.caller
                WHERE cp.hops < :hops AND c.confidence >= :min_conf
            )
            SELECT caller, MIN(hops) AS hops
            FROM callers_path
            GROUP BY caller
            ORDER BY hops, caller
        """
        rows = conn.execute(
            sql,
            {
                "fid": function_id,
                "hops": hops,
                "min_conf": min_confidence,
            },
        ).fetchall()
        return [CallerRecord(caller=r["caller"], hops=int(r["hops"])) for r in rows]

    def get_module_tests(self, mod_stem: str) -> list[str]:
        conn = self._get_connection()
        sql = "SELECT id FROM tests WHERE file_path LIKE ?"
        rows = conn.execute(sql, (f"%{mod_stem}%",)).fetchall()
        return [r["id"] for r in rows]

    def write_static(self, result: Any, commit_sha: str | None = None) -> None:
        self.ensure_schema()
        conn = self._get_connection()
        with conn:
            # 1. Files
            file_rows = [(r["path"],) for r in result.file_rows()]
            conn.executemany(
                "INSERT OR REPLACE INTO files (path) VALUES (?)",
                file_rows,
            )

            # 2. Functions
            func_rows = [
                (
                    r["id"],
                    r["file"],
                    r["name"],
                    r["qualname"],
                    r["start"],
                    r["end"],
                    1 if r["dyn"] else 0,
                    0,  # initially no_evidence = false
                )
                for r in result.function_rows()
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO functions
                (id, file_path, name, qualname, start_line, end_line, has_dynamic_dispatch, no_evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                func_rows,
            )

            # 3. Tests
            if hasattr(result, "test_rows"):
                test_rows = [
                    (
                        r["id"],
                        r["file"],
                        r["name"],
                        r.get("qualname", ""),
                        r.get("start", 0),
                        r.get("end", 0),
                    )
                    for r in result.test_rows()
                ]
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO tests
                    (id, file_path, name, qualname, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    test_rows,
                )

            # 4. Calls
            call_rows = [
                (
                    r["src"],
                    r["dst"],
                    "static",
                    0.6,
                    0,
                    commit_sha,
                )
                for r in result.call_rows()
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO calls
                (caller_id, callee_id, source, confidence, evidence_count, last_verified_sha)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                call_rows,
            )

            # 5. Imports
            import_rows = [
                (
                    r["src"],
                    r["dst"],
                    "static",
                    0.6,
                    commit_sha,
                )
                for r in result.import_rows()
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO imports
                (src_path, dst_path, source, confidence, last_verified_sha)
                VALUES (?, ?, ?, ?, ?)
                """,
                import_rows,
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

        rows = [
            (
                p["func"],
                p["test"],
                confidence,
                "coverage",
                1,
                commit_sha,
            )
            for p in pairs
        ]

        conn = self._get_connection()
        with conn:
            conn.executemany(
                """
                INSERT INTO covered_by (function_id, test_id, confidence, source, evidence_count, last_verified_sha)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(function_id, test_id) DO UPDATE SET
                    confidence = excluded.confidence,
                    source = excluded.source,
                    evidence_count = covered_by.evidence_count + 1,
                    last_verified_sha = excluded.last_verified_sha
                """,
                rows,
            )

        self.update_graph_meta(commit_sha=commit_sha)
        return len(pairs)

    def write_run(
        self,
        run_data: dict[str, Any],
        failures: list[dict[str, Any]] | None = None,
    ) -> None:
        self.ensure_schema()
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (id, timestamp, commit_sha, duration_ms, total_tests, passed, failed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_data["id"],
                    run_data.get("timestamp"),
                    run_data.get("commit_sha"),
                    run_data.get("duration_ms"),
                    run_data.get("total_tests"),
                    run_data.get("passed"),
                    run_data.get("failed"),
                ),
            )

            if failures:
                fail_rows = [
                    (
                        f["test_id"],
                        run_data["id"],
                        "test_run",
                        f.get("error"),
                        run_data.get("commit_sha"),
                    )
                    for f in failures
                ]
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO failed_in (test_id, run_id, source, error_message, commit_sha)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    fail_rows,
                )

    def set_function_evidence_flags(
        self, covered_ids: Sequence[str], uncovered_ids: Sequence[str]
    ) -> None:
        conn = self._get_connection()
        with conn:
            if uncovered_ids:
                conn.executemany(
                    "UPDATE functions SET no_evidence = 1 WHERE id = ?",
                    [(fid,) for fid in uncovered_ids],
                )
            if covered_ids:
                conn.executemany(
                    "UPDATE functions SET no_evidence = 0 WHERE id = ?",
                    [(fid,) for fid in covered_ids],
                )

    def set_test_flake_rates(self, flake_rates: dict[str, float]) -> None:
        conn = self._get_connection()
        with conn:
            # Default all to 0.0 first
            conn.execute("UPDATE tests SET flake_rate = 0.0 WHERE flake_rate IS NULL")
            if flake_rates:
                conn.executemany(
                    "UPDATE tests SET flake_rate = ? WHERE id = ?",
                    [(rate, tid) for tid, rate in flake_rates.items()],
                )

    def record_miss_repair(
        self,
        function_id: str,
        test_id: str,
        new_confidence: float = 1.0,
    ) -> dict[str, Any]:
        self.ensure_schema()
        conn = self._get_connection()

        # Check existing edge
        old_conf = 0.0
        prev_source = None
        row = conn.execute(
            "SELECT confidence, source FROM covered_by WHERE function_id = ? AND test_id = ?",
            (function_id, test_id),
        ).fetchone()
        if row:
            old_conf = float(row["confidence"])
            prev_source = row["source"]

        now = time.time()
        file_part = test_id.split("::")[0] if "::" in test_id else "tests/unknown.py"

        with conn:
            # Ensure test node exists
            conn.execute(
                """
                INSERT OR IGNORE INTO tests (id, file_path, name, flake_rate)
                VALUES (?, ?, ?, 0.0)
                """,
                (test_id, file_part, test_id.split("::")[-1]),
            )

            # Insert / update repair edge
            conn.execute(
                """
                INSERT INTO covered_by (function_id, test_id, confidence, source, evidence_count, old_confidence, last_repaired_at)
                VALUES (?, ?, ?, 'miss_repair', 1, ?, ?)
                ON CONFLICT(function_id, test_id) DO UPDATE SET
                    confidence = excluded.confidence,
                    old_confidence = covered_by.confidence,
                    source = 'miss_repair',
                    evidence_count = covered_by.evidence_count + 1,
                    last_repaired_at = excluded.last_repaired_at
                """,
                (function_id, test_id, new_confidence, old_conf, now),
            )

            # Unset no_evidence on function
            conn.execute(
                "UPDATE functions SET no_evidence = 0 WHERE id = ?",
                (function_id,),
            )

        self.update_graph_meta()

        return {
            "status": "repaired",
            "function": function_id,
            "test": test_id,
            "old_confidence": old_conf,
            "new_confidence": new_confidence,
            "source": "miss_repair",
            "previous_source": prev_source,
        }
