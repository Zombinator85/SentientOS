from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from codex.integrity_daemon import IntegrityDaemon, IntegrityViolation
from codex.proof_verifier import ProofVerifier


@dataclass
class DummyProposal:
    proposal_id: str
    spec_id: str
    summary: str
    original_spec: dict[str, object]
    proposed_spec: dict[str, object]
    ledger_diff: dict[str, object]
    deltas: dict[str, object] | None = None
    context: dict[str, object] | None = None


def _base_spec() -> dict[str, object]:
    return {
        "objective": "preserve covenant",
        "directives": ["log", "report"],
        "testing_requirements": ["pytest"],
        "status": "active",
    }


def test_proof_verifier_accepts_valid_spec() -> None:
    verifier = ProofVerifier()
    payload = {
        "proposed_spec": _base_spec(),
        "ledger_diff": {"removed": []},
    }
    report = verifier.evaluate(payload)
    assert report.valid
    assert report.violations == []


def test_structural_integrity_violation_detected() -> None:
    verifier = ProofVerifier()
    spec = _base_spec()
    spec.pop("objective")
    payload = {
        "proposed_spec": spec,
        "ledger_diff": {"removed": []},
    }
    report = verifier.evaluate(payload)
    assert not report.valid
    assert any(v["invariant"] == "structural_integrity" for v in report.violations)


def test_audit_continuity_violation_detected() -> None:
    verifier = ProofVerifier()
    payload = {
        "proposed_spec": _base_spec(),
        "ledger_diff": {"removed": ["legacy_entry"]},
    }
    report = verifier.evaluate(payload)
    assert not report.valid
    assert any(v["invariant"] == "audit_continuity" for v in report.violations)


def test_forbidden_status_violation_detected() -> None:
    verifier = ProofVerifier()
    payload = {
        "proposed_spec": {**_base_spec(), "status": "retired"},
        "ledger_diff": {"removed": []},
    }
    report = verifier.evaluate(payload)
    assert not report.valid
    assert any(v["invariant"] == "forbidden_status" for v in report.violations)


def test_recursion_guard_violation_detected() -> None:
    verifier = ProofVerifier()
    payload = {
        "proposed_spec": {**_base_spec(), "recursion_break": True},
        "ledger_diff": {"removed": []},
    }
    report = verifier.evaluate(payload)
    assert not report.valid
    assert any(v["invariant"] == "recursion_guard" for v in report.violations)


def test_integrity_daemon_logs_proof_report(tmp_path: Path) -> None:
    daemon = IntegrityDaemon(tmp_path)
    proposal = DummyProposal(
        proposal_id="P-001",
        spec_id="SPEC-1",
        summary="Maintain covenant integrity",
        original_spec=_base_spec(),
        proposed_spec=_base_spec(),
        ledger_diff={"removed": []},
        deltas={"objective": "preserve covenant"},
        context={"author": "tester"},
    )
    daemon.evaluate(proposal)

    ledger_path = tmp_path / "daemon" / "integrity" / "ledger.jsonl"
    content = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert content
    entry = json.loads(content[-1])
    assert entry["status"] == "VALID"
    assert entry["proof_report"]["valid"] is True
    assert entry["proof_report"]["trace"], "expected trace data in proof report"
    assert entry["violations"] == []


def test_integrity_daemon_quarantines_invalid_proof(tmp_path: Path) -> None:
    daemon = IntegrityDaemon(tmp_path)
    proposal = DummyProposal(
        proposal_id="P-002",
        spec_id="SPEC-2",
        summary="Retire amendment",
        original_spec=_base_spec(),
        proposed_spec={**_base_spec(), "status": "retired"},
        ledger_diff={"removed": []},
    )
    with pytest.raises(IntegrityViolation):
        daemon.evaluate(proposal)

    quarantine_path = tmp_path / "daemon" / "integrity" / "quarantine" / "P-002.json"
    stored = json.loads(quarantine_path.read_text(encoding="utf-8"))
    assert stored["proof_report"]["valid"] is False
    assert any(v["invariant"] == "forbidden_status" for v in stored["proof_report"]["violations"])
