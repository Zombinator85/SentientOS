import pytest

from advisory_connector import (
    ADVISORY_PHASE,
    AdvisoryAcceptanceWorkflow,
    AdvisoryAuditTrail,
    AdvisoryConnectorGate,
    AdvisoryDecision,
    AdvisoryRequest,
    AdvisoryResponse,
)
from sentientos.innerworld.value_drift import AdvisoryToneSentinel


def _request(**overrides):
    base = {
        "goal": "stabilize advisory boundary",
        "context_slice": ("module_a.py", "secret_notes.md"),
        "constraints": {"must": ("log",), "must_not": ("mutate",)},
        "forbidden_domains": ("payments",),
        "desired_artifacts": ("plan", "tests"),
        "phase": ADVISORY_PHASE,
        "redaction_profile": ("secret",),
    }
    base.update(overrides)
    return AdvisoryRequest(**base)


def _response(**overrides):
    base = {
        "proposed_steps": ("map scope",),
        "risk_notes": ("respect boundaries",),
        "assumptions": ("manual review",),
        "confidence_estimate": 0.5,
        "unknowns": ("user intent",),
        "diff_suggestions": ("placeholder diff",),
    }
    base.update(overrides)
    return AdvisoryResponse(**base)


def test_phase_enforcement_rejects(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    request = _request(phase="EXECUTION")

    decision, response = gate.send(request, lambda _: _response())

    assert decision.status == "rejected"
    assert "phase" in decision.reason
    record = audit.records()[-1]
    assert record["stage"] == "gate"
    assert record["response"] is None


def test_redaction_correctness(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    observed_context: list[str] = []

    def _responder(request: AdvisoryRequest) -> AdvisoryResponse:
        observed_context.extend(request.context_slice)
        return _response()

    decision, response = gate.send(_request(), _responder)

    assert decision.status == "pending"
    assert response is not None
    assert "[REDACTED]" in observed_context
    assert any("secret" in redaction for redaction in audit.records()[-1]["redactions"])


def test_authority_language_is_rejected(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)

    def _responder(request: AdvisoryRequest) -> AdvisoryResponse:  # pragma: no cover - context not needed
        return _response(proposed_steps=("You must obey",))

    decision, response = gate.send(_request(), _responder)

    assert decision.status == "rejected"
    assert "authority" in decision.reason
    assert response is None


def test_no_state_mutation_from_response(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    mutated = {"flag": False}

    def _responder(request: AdvisoryRequest) -> AdvisoryResponse:  # pragma: no cover - intentionally invalid
        return _response(diff_suggestions=(lambda: mutated.__setitem__("flag", True),))

    decision, _ = gate.send(_request(), _responder)

    assert decision.status == "rejected"
    assert mutated["flag"] is False


def test_acceptance_workflow_determinism(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    workflow = AdvisoryAcceptanceWorkflow(audit)

    decision, response = gate.send(_request(), lambda _: _response())
    assert decision.status == "pending"
    assert response is not None

    accepted = workflow.accept(_request(), response, reason="placed on backlog", downstream_effects=("planning backlog",))
    partial = workflow.partial_accept(
        _request(), response, deltas=("trim scope",), reason="only partial use"
    )
    rejected = workflow.reject(_request(), response, cause="not needed")

    assert accepted == AdvisoryDecision(status="accepted", reason="placed on backlog", downstream_effects=("planning backlog",))
    assert partial == AdvisoryDecision(status="partial", reason="only partial use", deltas=("trim scope",))
    assert rejected == AdvisoryDecision(status="rejected", reason="not needed")
    stages = {record["stage"] for record in audit.records()}
    assert {"gate", "acceptance"}.issubset(stages)


def test_drift_and_tone_detection_triggers():
    sentinel = AdvisoryToneSentinel(maxlen=5)
    sentinel.record_response("maybe do this if allowed")
    sentinel.record_response("perhaps we could do this, please")
    sentinel.record_response("optional steps that might be fine; adopt policy")

    tone = sentinel.detect_tone_shift()

    assert tone["increasing_caution"] is True
    assert tone["permission_seeking"] is True
    assert tone["constraint_normalization"] is True
    assert len(tone["history"]) == 3
