from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex.specs import SpecEngine, SpecReviewBoard


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(seconds=1)
        return current


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_spec_engine_generates_and_routes_proposals(tmp_path: Path) -> None:
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecEngine(root=root, now=clock.now)

    anomalies = [
        {"kind": "missing_template", "severity": "warning", "daemon": "AuditDaemon"},
        {"kind": "missing_template", "severity": "warning", "daemon": "AuditDaemon"},
        {"kind": "missing_template", "severity": "warning", "daemon": "AuditDaemon"},
    ]
    strategies = [
        {"status": "escalated", "reason": "Missing template for anomaly", "strategy_id": "strategy-1"},
        {"status": "escalated", "reason": "Missing template for anomaly", "strategy_id": "strategy-2"},
    ]

    proposals = engine.scan(anomalies, strategies)
    assert proposals, "SpecEngine should emit proposals for repeated gaps"

    anomaly_spec = next(p for p in proposals if p.trigger_key.startswith("anomaly::"))
    proposal_path = root / "specs" / "proposals" / f"{anomaly_spec.spec_id}.json"
    assert proposal_path.exists(), "Draft proposal should be persisted"

    stored_payload = _load_json(proposal_path)
    assert stored_payload["objective"]
    assert stored_payload["directives"]
    assert stored_payload["testing_requirements"]

    board = SpecReviewBoard(engine)

    board.edit(
        anomaly_spec.spec_id,
        operator="aurora",
        objective="Refine missing template resilience gap",
        directives=[
            "Clarify missing template reasons for escalation records.",
            "Retain ledger gating on speculative scaffolds.",
            anomaly_spec.directives[-1],
        ],
    )
    edited = engine.load_spec(anomaly_spec.spec_id)
    assert edited is not None
    assert edited.objective.startswith("Refine")
    assert edited.directives[0].startswith("Clarify")

    board.defer(anomaly_spec.spec_id, operator="aurora", until="post-council-review")
    deferred = engine.load_spec(anomaly_spec.spec_id)
    assert deferred is not None and deferred.status == "deferred"

    approved = board.approve(anomaly_spec.spec_id, operator="aurora", commit_hash="abc123")
    assert approved.status == "queued"
    queue_path = root / "specs" / "queue" / f"{anomaly_spec.spec_id}.json"
    assert queue_path.exists()
    queue_payload = _load_json(queue_path)
    assert queue_payload["status"] == "queued"
    scaffold_path = root / "specs" / "scaffolds" / anomaly_spec.spec_id / "manifest.json"
    assert scaffold_path.exists()

    log_entries = _read_log(root / "spec_log.jsonl")
    events = [entry["event"] for entry in log_entries if entry["spec_id"] == anomaly_spec.spec_id]
    assert {"proposed", "edited", "deferred", "approved"}.issubset(events)

    second_anomalies = [
        {"kind": "audit_gap", "severity": "warning", "daemon": "LedgerDaemon"},
        {"kind": "audit_gap", "severity": "warning", "daemon": "LedgerDaemon"},
        {"kind": "audit_gap", "severity": "warning", "daemon": "LedgerDaemon"},
    ]
    second_specs = engine.scan(second_anomalies, [])
    assert second_specs, "New recurring anomaly should trigger another proposal"

    followup_spec = second_specs[0]
    assert followup_spec.objective.startswith("Refine"), "Style should adapt after operator edits"

    board.reject(followup_spec.spec_id, operator="aurora", reason="Handled elsewhere")
    archive_path = root / "specs" / "archive" / f"{followup_spec.spec_id}.json"
    assert archive_path.exists()
    assert not (root / "specs" / "queue" / f"{followup_spec.spec_id}.json").exists()

    state_payload = _load_json(root / "specs" / "state.json")
    assert state_payload["style"]["objective_prefix"] == "Refine"
    assert state_payload["thresholds"]["anomaly"] >= SpecEngine.DEFAULT_THRESHOLDS["anomaly"]
