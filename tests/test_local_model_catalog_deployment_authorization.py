from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, LifecyclePhase
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model_catalog import local_model_catalog_digest
from sentientos.local_model_catalog_deployment import verify_catalog_publication_evidence
from sentientos.local_model_catalog_deployment_architecture import EFFECTS, EXPECTED_ABSENT
from sentientos.local_model_catalog_deployment_authorization import (
    APPROVAL_SCHEMA, ISSUANCE_EFFECTS, ISSUER_PRINCIPAL,
    CatalogDeploymentApprovalEvidence, CatalogDeploymentAuthorizationCustody,
    CatalogDeploymentAuthorizationError, CatalogDeploymentAuthorizationRequest,
    _digest_record, issue_catalog_deployment_authorization, project_catalog_deployment_authority,
)
from tests.test_local_model_catalog_deployment import catalog, publication

pytestmark = pytest.mark.no_legacy_skip
START = "2026-09-07T12:00:00Z"
END = "2026-09-07T12:30:00Z"


class Kernel:
    def __init__(self, outcome: AdmissionOutcome = AdmissionOutcome.ALLOW) -> None:
        self.outcome = outcome
        self.requests = []

    def admit(self, request):
        self.requests.append(request)
        return ControlActionDecision(self.outcome, (), LifecyclePhase.RUNTIME, LifecyclePhase.RUNTIME,
            request.authority_class, request.action_kind, request.actor, request.target_subsystem, {},
            request.metadata["correlation_id"])


def fixture(tmp_path: Path, *, synthetic: bool = True):
    handle = InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("fixture"), create=True)
    candidate = catalog(); receipts = [publication(candidate)]
    candidate_digest = local_model_catalog_digest(candidate)
    evidence_digest = verify_catalog_publication_evidence(candidate["models"], receipts)["publication_evidence_set_semantic_digest"]
    custody = CatalogDeploymentAuthorizationCustody.for_installation(handle)
    request = CatalogDeploymentAuthorizationRequest(ISSUER_PRINCIPAL,
        "sentientos.local_model_catalog.deployment_authorization.issue", ISSUANCE_EFFECTS, "corr", "fixture",
        custody.custody_identity, candidate_digest, str(evidence_digest), EXPECTED_ABSENT, START, END, START, END)
    approval = CatalogDeploymentApprovalEvidence("approval-1", "operator-alice", "approved",
        request.issuance_capability_id, ISSUER_PRINCIPAL, "corr", "fixture", custody.custody_identity,
        candidate_digest, EXPECTED_ABSENT, str(evidence_digest), START, END, START, START, "",
        APPROVAL_SCHEMA, synthetic)
    approval = replace(approval, semantic_digest=_digest_record(approval))
    return handle, candidate, receipts, request, approval, custody


def test_exact_issuance_replay_and_projection_are_bounded(tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, custody = fixture(tmp_path)
    first = issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
        created_at=START, allow_synthetic_test_evidence=True)
    second = issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
        created_at=START, allow_synthetic_test_evidence=True)
    assert first.status == "issued" and second.status == "replayed"
    authority = project_catalog_deployment_authority(first.grant, first.lease, first.receipt,
        observed_at=START, allow_synthetic_test_authority=True)
    assert authority.effects == EFFECTS and authority.synthetic_test_authority is True
    assert custody.root.path.parent.name == "authorization"
    assert not (handle.root / "model-catalog" / "grants").exists()


def test_operator_approval_and_control_plane_are_independently_required(tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, custody = fixture(tmp_path)
    with pytest.raises(CatalogDeploymentAuthorizationError, match="synthetic_approval_forbidden"):
        issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(), created_at=START)
    denied = replace(approval, approval_status="denied", semantic_digest="")
    denied = replace(denied, semantic_digest=_digest_record(denied))
    with pytest.raises(CatalogDeploymentAuthorizationError, match="operator_approval_required"):
        issue_catalog_deployment_authorization(handle, request, denied,
            candidate, receipts, Kernel(), created_at=START, allow_synthetic_test_evidence=True)
    with pytest.raises(CatalogDeploymentAuthorizationError, match="control_plane_admission_denied"):
        issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts,
            Kernel(AdmissionOutcome.DENY), created_at=START, allow_synthetic_test_evidence=True)
    assert not custody.root.path.exists()


@pytest.mark.parametrize("field,value,code", [
    ("issuer_principal", "deterministic_catalog_deployment_controller", "issuer_authority_denied"),
    ("issuance_effects", ISSUANCE_EFFECTS[:-1], "issuance_effects_invalid"),
    ("expected_prior_state", "current", "exact_prior_state_required"),
    ("expires_at", "2026-09-07T14:00:00Z", "grant_interval_invalid"),
])
def test_request_fails_closed(field: str, value: object, code: str, tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, _ = fixture(tmp_path)
    request = replace(request, **{field: value})
    with pytest.raises(CatalogDeploymentAuthorizationError, match=code):
        issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
            created_at=START, allow_synthetic_test_evidence=True)


def test_expiry_revocation_and_conflict_prevent_authority(tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, custody = fixture(tmp_path)
    result = issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
        created_at=START, allow_synthetic_test_evidence=True)
    with pytest.raises(CatalogDeploymentAuthorizationError, match="authorization_not_current"):
        project_catalog_deployment_authority(result.grant, result.lease, result.receipt,
            observed_at=END, allow_synthetic_test_authority=True)
    with pytest.raises(CatalogDeploymentAuthorizationError, match="authorization_revoked"):
        project_catalog_deployment_authority(result.grant, result.lease, result.receipt, observed_at=START,
            revocations=[{"schema_version": "sentientos.local_model_catalog_deployment_authorization_revocation:v1",
                          "active": True, "grant_id": result.grant.grant_id}], allow_synthetic_test_authority=True)
    path = custody.grants.child(result.grant.grant_id + ".json").path
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(CatalogDeploymentAuthorizationError, match="authorization_identity_conflict"):
        issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
            created_at=START, allow_synthetic_test_evidence=True)
