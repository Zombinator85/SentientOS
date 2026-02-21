from __future__ import annotations

import json
from pathlib import Path

from sentientos.remediation_pack import emit_pack_from_trace
from sentientos.recovery_tasks import list_tasks


def _trace(reason: str, *, mode: str = "normal", quarantine_active: bool = False) -> dict[str, object]:
    return {
        "trace_id": "trace_20260101T000000Z_merge_train",
        "context": "merge_train",
        "created_at": "2026-01-01T00:00:00Z",
        "final_decision": "hold",
        "final_reason": reason,
        "reason_stack": [reason],
        "operating_mode": mode,
        "strategic_posture": "balanced",
        "integrity_pressure_level": 1,
        "integrity_metrics_summary": {},
        "quarantine_state_summary": {"active": quarantine_active},
        "gates_evaluated": [],
    }


def test_pack_generation_audit_chain_broken(tmp_path: Path) -> None:
    emitted = emit_pack_from_trace(tmp_path, trace_payload=_trace("audit_chain_broken"), trace_path="glow/forge/traces/t.json")
    assert emitted is not None
    pack = json.loads((tmp_path / str(emitted["pack_path"])).read_text(encoding="utf-8"))
    commands = [str(step["command"]) for step in pack["steps"]]
    assert "python scripts/audit_chain_doctor.py --repair-index-only" in commands
    assert "python scripts/verify_audits.py --strict" in commands


def test_pack_generation_receipt_chain_broken(tmp_path: Path) -> None:
    emitted = emit_pack_from_trace(tmp_path, trace_payload=_trace("receipt_chain_broken"), trace_path="glow/forge/traces/t.json")
    assert emitted is not None
    pack = json.loads((tmp_path / str(emitted["pack_path"])).read_text(encoding="utf-8"))
    assert any(str(step["command"]) == "python scripts/verify_receipt_chain.py --last 50" for step in pack["steps"])


def test_quarantine_active_auto_queues_non_destructive_steps(tmp_path: Path) -> None:
    emitted = emit_pack_from_trace(
        tmp_path,
        trace_payload=_trace("quarantine_active", mode="normal", quarantine_active=True),
        trace_path="glow/forge/traces/t.json",
    )
    assert emitted is not None
    assert emitted["status"] == "queued"
    rows = list_tasks(tmp_path)
    assert rows
    assert all(str(row.get("kind", "")).startswith("remediation_pack:") for row in rows)


def test_risk_budget_throttle_generates_non_repair_pack_without_queue(tmp_path: Path) -> None:
    emitted = emit_pack_from_trace(tmp_path, trace_payload=_trace("risk_budget_throttle", mode="normal"), trace_path="glow/forge/traces/t.json")
    assert emitted is not None
    pack = json.loads((tmp_path / str(emitted["pack_path"])).read_text(encoding="utf-8"))
    assert pack["status"] == "proposed"
    assert all(str(step.get("kind")) == "suggestion" for step in pack["steps"])
    assert list_tasks(tmp_path) == []
