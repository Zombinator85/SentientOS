from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from sentientos.local_model_artifact_acquisition import ModelArtifactAcquisitionError, acquire_model_artifact, authorization_for
from sentientos.local_model_artifact_acquisition_authority import AcquisitionApprovalError, verify_external_approval
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass
from tests.test_local_model_artifact_acquisition import FakeTransport, NOW, _HANDLES, approval, case

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("field,value", [
    ("operator_identity", "anonymous"), ("approval_status", "denied"),
    ("target_principal", "other"), ("target_capability", "other"),
    ("correlation_id", "other"), ("installation_identity", "other"),
    ("catalog_custody_identity", "other"), ("authoritative_catalog_proof_digest", "0" * 64),
    ("deployment_receipt_id", "other"), ("deployment_receipt_semantic_digest", "0" * 64),
    ("acquisition_plan_digest", "0" * 64), ("model_id", "other"), ("artifact_id", "other"),
    ("artifact_sha256", "0" * 64), ("artifact_size_bytes", 1),
    ("canonical_source_url", "https://models.sentientos.org/other"), ("escrow_root", "/other"),
    ("final_relative_escrow_path", "sha256/other"),
])
def test_external_approval_rejects_every_inexact_binding(tmp_path, field, value):
    *_, plan = case(tmp_path)
    evidence = approval(plan, **{field: value})
    with pytest.raises(AcquisitionApprovalError):
        verify_external_approval(evidence, plan, correlation_id="acquisition-test", observation_time=NOW)


def test_external_approval_accepts_exact_evidence_and_rejects_time_and_digest(tmp_path):
    *_, plan = case(tmp_path)
    exact = approval(plan)
    assert verify_external_approval(exact, plan, correlation_id="acquisition-test", observation_time=NOW)
    bad = dict(exact); bad["approval_semantic_digest"] = "0" * 64
    with pytest.raises(AcquisitionApprovalError, match="digest"):
        verify_external_approval(bad, plan, correlation_id="acquisition-test", observation_time=NOW)
    for evidence, observed in ((approval(plan, not_before=(NOW + timedelta(minutes=1)).isoformat()), NOW),
                               (exact, NOW + timedelta(hours=1))):
        with pytest.raises(AcquisitionApprovalError):
            verify_external_approval(evidence, plan, correlation_id="acquisition-test", observation_time=observed)


def test_legacy_boolean_authorization_cannot_execute(tmp_path):
    data, *_, plan = case(tmp_path); transport = FakeTransport(data)
    with pytest.raises(ModelArtifactAcquisitionError, match="legacy"):
        acquire_model_artifact(plan, execute=True, authorization=authorization_for(plan, operator_confirmed=True),
            installation_handle=_HANDLES[plan["acquisition_plan_digest"]], transport=transport)
    assert transport.calls == 0 and not (tmp_path / "escrow").exists()


def test_synthetic_approval_is_rejected_in_production(tmp_path):
    data, *_, plan = case(tmp_path); evidence = approval(plan, synthetic_test_evidence=True)
    with pytest.raises(ModelArtifactAcquisitionError, match="synthetic"):
        acquire_model_artifact(plan, execute=True, approval_evidence=evidence, correlation_id="acquisition-test",
            control_plane_kernel=object(), installation_handle=_HANDLES[plan["acquisition_plan_digest"]],
            observation_time=NOW, transport=FakeTransport(data))


@pytest.mark.parametrize("outcome", [AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE])
def test_control_plane_non_allow_has_zero_transport_or_escrow_mutation(tmp_path, outcome):
    data, *_, plan = case(tmp_path); transport = FakeTransport(data)
    class Kernel:
        def admit(self, request):
            return SimpleNamespace(outcome=outcome, authority_class=AuthorityClass.MODEL_ARTIFACT_ACQUISITION,
                actor=request.actor, correlation_id=request.metadata["correlation_id"], action_kind=request.action_kind,
                target_subsystem=request.target_subsystem, admission_decision_ref="kernel:test")
    with pytest.raises(ModelArtifactAcquisitionError, match="not_allowed"):
        acquire_model_artifact(plan, execute=True, approval_evidence=approval(plan), correlation_id="acquisition-test",
            control_plane_kernel=Kernel(), installation_handle=_HANDLES[plan["acquisition_plan_digest"]],
            observation_time=NOW, transport=transport)
    assert transport.calls == 0 and not (tmp_path / "escrow").exists()
