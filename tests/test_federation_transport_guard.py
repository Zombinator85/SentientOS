import pytest

import task_executor
from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from sentientos.federation import enablement as federation_enablement
from sentientos.federation.handshake_semantics import (
    CompatibilityResult,
    HandshakeDecision,
    HandshakeRecord,
    SemanticAttestation,
)
from sentientos.federation.transport import FederationEnvelope, OpaqueTransportPayload


def _authorization(metadata: dict[str, object] | None = None) -> AuthorizationRecord:
    if federation_enablement.has_federation_artifacts(metadata):
        with federation_enablement.legacy_federation_bypass("legacy federation transport guard"):
            return AuthorizationRecord.create(
                request_type=RequestType.TASK_EXECUTION,
                requester_id="operator",
                intent_hash="intent",
                context_hash="context",
                policy_version="policy-v1",
                decision=Decision.ALLOW,
                reason=ReasonCode.OK,
                metadata=metadata,
            )
    return AuthorizationRecord.create(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="intent",
        context_hash="context",
        policy_version="policy-v1",
        decision=Decision.ALLOW,
        reason=ReasonCode.OK,
        metadata=metadata,
    )


def _provenance(task_id: str) -> task_executor.AuthorityProvenance:
    return task_executor.AuthorityProvenance(
        authority_source="local",
        authority_scope="unit-test",
        authority_context_id=task_id,
        authority_reason="guard",
    )


def _issue_token(
    task: task_executor.Task,
    authorization: AuthorizationRecord,
    provenance: task_executor.AuthorityProvenance,
) -> task_executor.AdmissionToken:
    canonical_request = task_executor.canonicalise_task_request(
        task=task, authorization=authorization, provenance=provenance
    )
    fingerprint = task_executor.request_fingerprint_from_canonical(canonical_request)
    return task_executor.AdmissionToken(
        task_id=task.task_id,
        provenance=provenance,
        request_fingerprint=fingerprint,
    )


def _task(task_id: str, *, epr_actions: tuple[task_executor.EprAction, ...] = ()) -> task_executor.Task:
    steps = (task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok")),)
    return task_executor.Task(
        task_id=task_id,
        objective="guard federation transport",
        steps=steps,
        allow_epr=bool(epr_actions),
        epr_actions=epr_actions,
    )


def _federation_artifacts() -> dict[str, object]:
    attestation = SemanticAttestation(
        node_id="peer-a",
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
        declared_capabilities=("read", "write"),
    )
    handshake = HandshakeRecord(
        remote_node_id="peer-a",
        attestation=attestation,
        compatibility=CompatibilityResult.COMPATIBLE,
        decision=HandshakeDecision.ACCEPT,
    )
    with federation_enablement.legacy_federation_bypass("legacy federation transport guard"):
        envelope = FederationEnvelope(
            envelope_id="env-guard",
            payload_type="handshake_record",
            payload=OpaqueTransportPayload(b"opaque", tag="handshake_record"),
            sender_node_id="peer-a",
            protocol_version="v1",
        )
    return {"federation_envelope": envelope, "handshake": handshake, "attestation": attestation}


def _epr_action(action_id: str, task_id: str) -> task_executor.EprAction:
    return task_executor.EprAction(
        action_id=action_id,
        parent_task_id=task_id,
        trigger_step_id=1,
        authority_impact="none",
        reversibility="guaranteed",
        rollback_proof="none",
        external_effects="no",
    )


def test_federation_transport_artifacts_do_not_affect_executor_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task("guard-task")
    provenance = _provenance(task.task_id)
    base_auth = _authorization()
    token = _issue_token(task, base_auth, provenance)

    federation_auth = _authorization(metadata=_federation_artifacts())
    base_request = task_executor.canonicalise_task_request(
        task=task, authorization=base_auth, provenance=provenance
    )
    federation_request = task_executor.canonicalise_task_request(
        task=task, authorization=federation_auth, provenance=provenance
    )
    assert base_request == federation_request
    assert (
        task_executor.request_fingerprint_from_canonical(base_request).value
        == task_executor.request_fingerprint_from_canonical(federation_request).value
    )

    exhaust_task_id = "guard-exhaust"
    exhaust_actions = tuple(_epr_action(f"action-{idx}", exhaust_task_id) for idx in range(2))
    exhaust_task = _task(exhaust_task_id, epr_actions=exhaust_actions)
    exhaust_provenance = _provenance(exhaust_task_id)
    exhaust_token = _issue_token(exhaust_task, base_auth, exhaust_provenance)
    monkeypatch.setenv("SENTIENTOS_MAX_CLOSURE_ITERATIONS", "1")

    with pytest.raises(task_executor.TaskExhausted) as base_exc:
        task_executor.execute_task(exhaust_task, authorization=base_auth, admission_token=exhaust_token)
    with pytest.raises(task_executor.TaskExhausted) as federation_exc:
        task_executor.execute_task(
            exhaust_task, authorization=federation_auth, admission_token=exhaust_token
        )

    assert base_exc.value.report.exhaustion_type == federation_exc.value.report.exhaustion_type
    assert base_exc.value.report.reason == federation_exc.value.report.reason
    assert base_exc.value.report.cycle_evidence == federation_exc.value.report.cycle_evidence
