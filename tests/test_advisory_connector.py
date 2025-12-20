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
        "constraints": {"must": ("log",), "must_not": ("mutate",)},
        "files_in_scope": ("module_a.py", "secret_notes.md"),
        "forbidden_changes": ("payments",),
        "desired_artifacts": ("plan", "test ideas"),
        "context_redactions": ("secret",),
        "system_phase": ADVISORY_PHASE,
        "minimal_synopsis": "limited synopsis with no doctrine",
    }
    base.update(overrides)
    return AdvisoryRequest(**base)


def _response(**overrides):
    base = {
        "proposed_steps": ("map scope",),
        "risks": ("respect boundaries",),
        "invariants_touched": ("audit log immutability",),
        "confidence": 0.5,
        "uncertainties": ("user intent",),
    }
    base.update(overrides)
    return AdvisoryResponse(**base)


def test_phase_enforcement_rejects(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    request = _request(system_phase="EXECUTION")

    decision, response = gate.send(request, lambda _: _response())

    assert decision.status == "rejected"
    assert "phase" in decision.reason
    record = audit.records()[-1]
    assert record["stage"] == "gate"
    assert record["response"] is None
    assert record["request_hash"] == record["request_hash"]


def test_redaction_correctness(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    observed_context: list[AdvisoryRequest] = []

    def _responder(request: AdvisoryRequest) -> AdvisoryResponse:
        observed_context.append(request)
        return _response()

    decision, response = gate.send(
        _request(goal="Backlog secret fix", minimal_synopsis="contains doctrine"), _responder
    )

    assert decision.status == "pending"
    assert response is not None
    seen_goal = observed_context[-1].goal
    seen_synopsis = observed_context[-1].minimal_synopsis
    assert "[REDACTED]" in seen_goal or "[REDACTED]" in seen_synopsis
    assert any(
        "secret" in redaction or "doctrine" in redaction for redaction in audit.records()[-1]["redactions"]
    )
    assert set(observed_context[-1].files_in_scope) <= set(_request().files_in_scope)


def test_authority_and_policy_guards(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)

    def _responder(request: AdvisoryRequest) -> AdvisoryResponse:  # pragma: no cover - context not needed
        return _response(
            proposed_steps=("escalate privileges to admin",),
            risks=("create new constraint without cause",),
        )

    decision, response = gate.send(_request(), _responder)

    assert decision.status == "rejected"
    assert "authority" in decision.reason or "constraint" in decision.reason
    assert response is None


def test_no_state_mutation_from_response(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    mutated = {"flag": False}

    def _responder(request: AdvisoryRequest) -> AdvisoryResponse:  # pragma: no cover - intentionally invalid
        return _response(invariants_touched=(lambda: mutated.__setitem__("flag", True),))

    decision, _ = gate.send(_request(), _responder)

    assert decision.status == "rejected"
    assert mutated["flag"] is False


def test_decision_logging_integrity(tmp_path):
    audit = AdvisoryAuditTrail(path=tmp_path / "audit.jsonl")
    gate = AdvisoryConnectorGate(audit_trail=audit)
    workflow = AdvisoryAcceptanceWorkflow(audit)

    decision, response = gate.send(_request(), lambda _: _response())
    assert decision.status == "pending"
    assert response is not None

    accepted = workflow.accept(
        _request(), response, reason="placed on backlog", downstream_effects=("planning backlog",)
    )
    partial = workflow.partial_accept(
        _request(), response, deltas=("trim scope",), reason="only partial use"
    )
    rejected = workflow.reject(_request(), response, cause="not needed")

    assert accepted == AdvisoryDecision(
        status="accepted", reason="placed on backlog", downstream_effects=("planning backlog",)
    )
    assert partial == AdvisoryDecision(status="partial", reason="only partial use", deltas=("trim scope",))
    assert rejected == AdvisoryDecision(status="rejected", reason="not needed")
    hashes = {(record["request_hash"], record.get("response_hash")) for record in audit.records()}
    assert all(hash_pair[0] is not None for hash_pair in hashes)
    assert {"gate", "acceptance"}.issubset({record["stage"] for record in audit.records()})


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
