"""Feedback loop and repair edge mechanism for Guard (Task T6).

When a test failure is missed by Guard (an escape), this module repairs
the graph by inserting a high-confidence COVERED_BY edge with source='miss_repair',
logging the old and new confidence values, and unsetting no_evidence flags so that
future decisions widen to include the missed test.
"""
from __future__ import annotations
import time
from typing import Any
from guard_cli import db


def record_miss(
    g,
    function_id: str,
    test_id: str,
    new_confidence: float = 1.0,
) -> dict[str, Any]:
    """Records a missed failure by repairing the graph with a miss_repair edge.

    Args:
        g: GraphStore or FalkorDB graph instance
        function_id: ID of the function where the fault/change occurred
        test_id: ID of the test that failed and was missed
        new_confidence: Confidence score for the repair edge (default: 1.0)

    Returns:
        Dict reporting the repair event including old and new confidence.
    """
    if hasattr(g, "record_miss_repair"):
        return g.record_miss_repair(function_id, test_id, new_confidence=new_confidence)

    # 1. Query existing edge if present
    q_existing = (
        "MATCH (f:Function {id: $fid})-[e:COVERED_BY]->(t:Test {id: $tid}) "
        "RETURN e.confidence, e.source"
    )
    existing_res = g.query(q_existing, {"fid": function_id, "tid": test_id}).result_set
    if existing_res:
        old_confidence = float(existing_res[0][0])
        prev_source = existing_res[0][1]
    else:
        old_confidence = 0.0
        prev_source = None

    ts = time.time()

    # 2. Ensure Test node exists and has basic defined properties if new
    file_part = test_id.split("::")[0] if "::" in test_id else "tests/unknown.py"
    g.query(
        "MERGE (t:Test {id: $tid}) "
        "ON CREATE SET t.file = $file, t.flake_rate = 0.0",
        {"tid": test_id, "file": file_part},
    )

    # 3. Create or update COVERED_BY edge with source='miss_repair'
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
    g.query(
        q_repair,
        {
            "fid": function_id,
            "tid": test_id,
            "old_conf": old_confidence,
            "new_conf": new_confidence,
            "ts": ts,
        },
    )
    db.update_graph_meta(g)

    return {
        "status": "repaired",
        "function": function_id,
        "test": test_id,
        "old_confidence": old_confidence,
        "new_confidence": new_confidence,
        "source": "miss_repair",
        "previous_source": prev_source,
    }
