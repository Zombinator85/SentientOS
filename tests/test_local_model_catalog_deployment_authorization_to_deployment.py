from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model_catalog import local_model_catalog_digest
from sentientos.local_model_catalog_consumer_custody import construct_authoritative_catalog_consumer_proof
from sentientos.local_model_catalog_deployment import CatalogDeploymentRequest, deploy_local_model_catalog
from sentientos.local_model_catalog_deployment_architecture import EFFECTS, EXPECTED_ABSENT
from sentientos.local_model_catalog_deployment_authorization import (
    CatalogDeploymentAuthorizationError,
    issue_catalog_deployment_authorization,
    project_catalog_deployment_authority,
)
from sentientos.model_catalog_custody import ModelCatalogCustody
from tests.test_local_model_catalog_deployment_authorization import Kernel, START, fixture

pytestmark = pytest.mark.no_legacy_skip


def test_real_control_plane_kernel_admits_bounded_issuance(tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, _ = fixture(tmp_path / "state")
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "decisions.jsonl")
    result = issue_catalog_deployment_authorization(
        handle, request, approval, candidate, receipts, kernel, created_at=START,
        allow_synthetic_test_evidence=True,
    )
    assert result.status == "issued"
    assert result.receipt.control_plane_admission_reference


def test_issued_authority_deploys_without_custody_identity_substitution(tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, authorization_custody = fixture(tmp_path)
    target_custody = ModelCatalogCustody.for_installation(handle)
    assert authorization_custody.authorization_custody_identity != target_custody.custody_identity

    issued = issue_catalog_deployment_authorization(
        handle, request, approval, candidate, receipts, Kernel(), created_at=START,
        allow_synthetic_test_evidence=True,
    )
    authority = project_catalog_deployment_authority(
        issued.grant, issued.lease, issued.receipt, observed_at=START,
        allow_synthetic_test_authority=True,
    )
    deployment_request = CatalogDeploymentRequest(
        authority.principal, authority.capability_id, authority.effects, authority.grant_id,
        authority.lease_id, authority.correlation_id, authority.installation_identity,
        authority.custody_identity, authority.candidate_catalog_semantic_digest,
        authority.expected_prior_state,
    )
    target = target_custody.custody_identity
    assert request.custody_identity == approval.custody_identity == issued.grant.custody_identity
    assert target == issued.lease.custody_identity == issued.receipt.custody_identity
    assert target == authority.custody_identity == deployment_request.custody_identity

    result = deploy_local_model_catalog(
        handle, deployment_request, authority, candidate, receipts, now=lambda: START,
    )
    assert result.status == "deployed_verified"
    snapshot = construct_authoritative_catalog_consumer_proof(handle)
    assert snapshot.proof["installation_identity"] == handle.identity.value
    assert snapshot.proof["custody_identity"] == target
    assert snapshot.proof["authoritative_catalog_semantic_digest"] == local_model_catalog_digest(candidate)
    assert snapshot.proof["deployment_receipt_id"] == result.receipt_id
    assert snapshot.proof["deployment_transaction_id"] == result.transaction_id
    assert snapshot.proof["transaction_final_state"] == "deployed_verified"
    assert snapshot.proof["proof_semantic_digest"]

    for obj, record_id in ((authorization_custody.grants, issued.grant.grant_id),
                           (authorization_custody.leases, issued.lease.lease_id),
                           (authorization_custody.receipts, issued.receipt.receipt_id)):
        assert any(record_id in name for name in handle.list_regular_names(obj))
        assert json.loads(handle.read_regular(obj.child(record_id + ".json")))["custody_identity"] == target


@pytest.mark.parametrize("source", ["authorization", "other-installation"])
def test_wrong_request_target_is_rejected_before_catalog_mutation(tmp_path: Path, source: str) -> None:
    handle, candidate, receipts, request, approval, authorization_custody = fixture(tmp_path)
    if source == "authorization":
        wrong = authorization_custody.authorization_custody_identity
    else:
        other = InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("other"), create=True)
        wrong = ModelCatalogCustody.for_installation(other).custody_identity
    request = replace(request, custody_identity=wrong)
    approval = replace(approval, custody_identity=wrong, semantic_digest="")
    from sentientos.local_model_catalog_deployment_authorization import _digest_record
    approval = replace(approval, semantic_digest=_digest_record(approval))
    with pytest.raises(CatalogDeploymentAuthorizationError, match="installation_custody_mismatch"):
        issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
            created_at=START, allow_synthetic_test_evidence=True)
    assert not ModelCatalogCustody.for_installation(handle).authoritative_catalog.path.exists()


def test_wrong_approval_and_issued_record_cross_bindings_fail_closed(tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, authorization_custody = fixture(tmp_path)
    wrong_approval = replace(approval, custody_identity=authorization_custody.authorization_custody_identity,
                             semantic_digest="")
    from sentientos.local_model_catalog_deployment_authorization import _digest_record
    wrong_approval = replace(wrong_approval, semantic_digest=_digest_record(wrong_approval))
    with pytest.raises(CatalogDeploymentAuthorizationError, match="approval_request_binding_mismatch"):
        issue_catalog_deployment_authorization(handle, request, wrong_approval, candidate, receipts, Kernel(),
            created_at=START, allow_synthetic_test_evidence=True)
    issued = issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
        created_at=START, allow_synthetic_test_evidence=True)
    wrong_lease = replace(issued.lease, custody_identity="wrong", semantic_digest="")
    wrong_lease = replace(wrong_lease, semantic_digest=_digest_record(wrong_lease))
    with pytest.raises(CatalogDeploymentAuthorizationError, match="authorization_cross_binding_mismatch"):
        project_catalog_deployment_authority(issued.grant, wrong_lease,
            issued.receipt, observed_at=START, allow_synthetic_test_authority=True)


def test_controller_rejects_projected_or_request_target_mismatch(tmp_path: Path) -> None:
    handle, candidate, receipts, request, approval, _ = fixture(tmp_path)
    issued = issue_catalog_deployment_authorization(handle, request, approval, candidate, receipts, Kernel(),
        created_at=START, allow_synthetic_test_evidence=True)
    authority = project_catalog_deployment_authority(issued.grant, issued.lease, issued.receipt,
        observed_at=START, allow_synthetic_test_authority=True)
    deployment_request = CatalogDeploymentRequest(authority.principal, authority.capability_id, EFFECTS,
        authority.grant_id, authority.lease_id, authority.correlation_id, authority.installation_identity,
        authority.custody_identity, authority.candidate_catalog_semantic_digest, EXPECTED_ABSENT)
    assert deploy_local_model_catalog(handle, deployment_request, replace(authority, custody_identity="wrong"),
        candidate, receipts, now=lambda: START).status == "authority_denied"
    assert deploy_local_model_catalog(handle, replace(deployment_request, custody_identity="wrong"), authority,
        candidate, receipts, now=lambda: START).status == "authority_denied"
    assert deploy_local_model_catalog(handle, replace(deployment_request, installation_identity="other"), authority,
        candidate, receipts, now=lambda: START).status == "authority_denied"
    assert not ModelCatalogCustody.for_installation(handle).authoritative_catalog.path.exists()
