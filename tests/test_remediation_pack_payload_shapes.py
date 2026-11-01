from __future__ import annotations

import json

import pytest

from sentientos.remediation_pack import emit_pack_from_trace, find_pack_for_incident_or_trace


pytestmark = pytest.mark.no_legacy_skip


def test_pack_projection_ignores_malformed_collection_fields(tmp_path) -> None:
    trace = {
        "trace_id": "trace-shape-check",
        "context": "merge_train",
        "final_decision": "hold",
        "final_reason": "audit_chain_broken",
        "reason_stack": "do-not-split-into-characters",
        "gates_evaluated": {"evidence_paths": ["unexpected"]},
        "operating_mode": "normal",
        "strategic_posture": "balanced",
        "integrity_metrics_summary": {},
    }

    emitted = emit_pack_from_trace(
        tmp_path,
        trace_payload=trace,
        trace_path="glow/forge/traces/trace.json",
    )

    assert emitted is not None
    pack = json.loads((tmp_path / str(emitted["pack_path"])).read_text(encoding="utf-8"))
    assert pack["reason_stack"] == []
    assert pack["evidence_paths"] == ["glow/forge/traces/trace.json"]

    projected = find_pack_for_incident_or_trace(
        tmp_path,
        incident_id=None,
        governance_trace_id="trace-shape-check",
    )
    assert projected is not None
    assert projected["steps_count"] == len(pack["steps"])
