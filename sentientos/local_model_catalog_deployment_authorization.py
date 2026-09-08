"""Bounded, installation-scoped catalog deployment authorization issuance.

Issuance consumes external operator approval and control-plane admission.  It never
deploys a catalog and deliberately has no provider, acquisition, or activation path.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence, cast

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, LOCAL_MODEL_CATALOG_DEPLOY,
    LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE,
)
from sentientos.control_plane_kernel import (
    AdmissionOutcome, AuthorityClass, ControlActionRequest, ControlPlaneKernel, LifecyclePhase,
)
from sentientos.installation_state import InstallationStateError, InstallationStateHandle, InstallationStateObject
from sentientos.local_model_catalog import local_model_catalog_digest, validate_local_model_catalog
from sentientos.local_model_catalog_deployment import CatalogDeploymentAuthority, verify_catalog_publication_evidence
from sentientos.local_model_catalog_deployment_architecture import EXPECTED_ABSENT, semantic_digest

APPROVAL_SCHEMA = "sentientos.local_model_catalog_deployment_authorization_approval:v1"
GRANT_SCHEMA = "sentientos.local_model_catalog_deployment_authorization_grant:v1"
LEASE_SCHEMA = "sentientos.local_model_catalog_deployment_authorization_lease:v1"
RECEIPT_SCHEMA = "sentientos.local_model_catalog_deployment_authorization_receipt:v1"
REVOCATION_SCHEMA = "sentientos.local_model_catalog_deployment_authorization_revocation:v1"
ISSUER_PRINCIPAL = "deterministic_catalog_deployment_authorization_controller"
TARGET_PRINCIPAL = "deterministic_catalog_deployment_controller"
ISSUANCE_EFFECTS = tuple(sorted(AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE].required_effects))
TARGET_EFFECTS = tuple(sorted(AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOY].required_effects))
MAX_GRANT_SECONDS = 3600
PLACEHOLDER_OPERATORS = frozenset({"", "*", "anonymous", "default", "sample", "test", "placeholder", "sample_operator"})


class CatalogDeploymentAuthorizationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CatalogDeploymentApprovalEvidence:
    approval_evidence_id: str
    operator_identity: str
    approval_status: str
    target_issuance_capability: str
    target_issuer_principal: str
    correlation_id: str
    installation_identity: str
    custody_identity: str
    candidate_catalog_semantic_digest: str
    expected_prior_state: str
    publication_evidence_set_semantic_digest: str
    requested_not_before: str
    requested_expires_at: str
    created_at: str
    approved_at: str
    semantic_digest: str
    schema_version: str = APPROVAL_SCHEMA
    synthetic_test_evidence: bool = False


@dataclass(frozen=True)
class CatalogDeploymentAuthorizationRequest:
    issuer_principal: str
    issuance_capability_id: str
    issuance_effects: tuple[str, ...]
    correlation_id: str
    installation_identity: str
    custody_identity: str
    candidate_catalog_semantic_digest: str
    publication_evidence_set_semantic_digest: str
    expected_prior_state: str
    not_before: str
    expires_at: str
    lease_not_before: str
    lease_expires_at: str


@dataclass(frozen=True)
class CatalogDeploymentAuthorizationGrant:
    grant_id: str; issuer_principal: str; issuance_capability_id: str
    issuance_effects: tuple[str, ...]; approval_evidence_id: str; approval_evidence_digest: str
    control_plane_admission_reference: str; target_principal: str; target_capability: str
    target_effects: tuple[str, ...]; correlation_id: str; installation_identity: str
    custody_identity: str; candidate_catalog_semantic_digest: str
    publication_evidence_set_semantic_digest: str; expected_prior_state: str
    not_before: str; expires_at: str; active: bool; revocation_posture: str
    revocation_reference: str | None; created_at: str; semantic_digest: str
    schema_version: str = GRANT_SCHEMA; synthetic_test_authority: bool = False


@dataclass(frozen=True)
class CatalogDeploymentAuthorizationLease:
    lease_id: str; parent_grant_id: str; parent_grant_digest: str; issuer_principal: str
    target_principal: str; target_capability: str; target_effects: tuple[str, ...]
    correlation_id: str; installation_identity: str; custody_identity: str
    candidate_catalog_semantic_digest: str; publication_evidence_set_semantic_digest: str
    expected_prior_state: str; not_before: str; expires_at: str; active: bool
    semantic_digest: str; schema_version: str = LEASE_SCHEMA; synthetic_test_authority: bool = False


@dataclass(frozen=True)
class CatalogDeploymentAuthorizationReceipt:
    receipt_id: str; issuer_principal: str; issuance_capability_id: str
    issuance_effects: tuple[str, ...]; approval_evidence_id: str; approval_evidence_digest: str
    control_plane_admission_reference: str; grant_id: str; grant_digest: str
    lease_id: str; lease_digest: str; target_principal: str; target_capability: str
    target_effects: tuple[str, ...]; correlation_id: str; installation_identity: str
    custody_identity: str; candidate_catalog_semantic_digest: str
    publication_evidence_set_semantic_digest: str; expected_prior_state: str
    not_before: str; expires_at: str; issuance_status: str; created_at: str
    semantic_digest: str; schema_version: str = RECEIPT_SCHEMA; synthetic_test_authority: bool = False


@dataclass(frozen=True)
class CatalogDeploymentAuthorizationResult:
    status: str
    grant: CatalogDeploymentAuthorizationGrant
    lease: CatalogDeploymentAuthorizationLease
    receipt: CatalogDeploymentAuthorizationReceipt


@dataclass(frozen=True)
class CatalogDeploymentAuthorizationCustody:
    installation: InstallationStateHandle
    root: InstallationStateObject
    lock: InstallationStateObject
    grants: InstallationStateObject
    leases: InstallationStateObject
    receipts: InstallationStateObject
    revocations: InstallationStateObject

    @classmethod
    def for_installation(cls, handle: InstallationStateHandle) -> "CatalogDeploymentAuthorizationCustody":
        root = handle.fixed_object("authorization/model-catalog-deployment")
        return cls(handle, root, root.child("authorization.lock"), root.child("grants"),
                   root.child("leases"), root.child("issuance-receipts"), root.child("revocations"))

    @property
    def custody_identity(self) -> str:
        return f"sentientos-installation:model-catalog-deployment-authorization:{self.installation.identity.value}"

    def initialize(self) -> None:
        self.installation.ensure_directory(self.installation.fixed_object("authorization"))
        self.installation.ensure_directory(self.root)
        for obj in (self.grants, self.leases, self.receipts, self.revocations):
            self.installation.ensure_directory(obj)


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CatalogDeploymentAuthorizationError("malformed_timestamp") from exc
    if parsed.tzinfo is None:
        raise CatalogDeploymentAuthorizationError("timezone_required")
    return parsed.astimezone(timezone.utc)


def _digest_record(value: Any) -> str:
    body = asdict(value) if not isinstance(value, Mapping) else dict(value)
    body.pop("semantic_digest", None)
    return cast(str, semantic_digest(body))


def verify_approval_evidence(evidence: CatalogDeploymentApprovalEvidence, *, allow_synthetic_test_evidence: bool = False) -> None:
    if evidence.schema_version != APPROVAL_SCHEMA or evidence.semantic_digest != _digest_record(evidence):
        raise CatalogDeploymentAuthorizationError("approval_evidence_invalid")
    if evidence.operator_identity.casefold().strip() in PLACEHOLDER_OPERATORS:
        raise CatalogDeploymentAuthorizationError("operator_identity_invalid")
    if evidence.approval_status != "approved":
        raise CatalogDeploymentAuthorizationError("operator_approval_required")
    if evidence.synthetic_test_evidence and not allow_synthetic_test_evidence:
        raise CatalogDeploymentAuthorizationError("synthetic_approval_forbidden")


def _valid_prior(value: str) -> bool:
    return value == EXPECTED_ABSENT or (len(value) == 64 and all(c in "0123456789abcdef" for c in value))


def _exact_tuple(value: Sequence[str], expected: tuple[str, ...]) -> bool:
    return len(value) == len(set(value)) == len(expected) and tuple(sorted(value)) == expected


def _with_digest(record: Any) -> Any:
    return replace(record, semantic_digest=_digest_record(record))


def _verify_record(record: Any, schema: str) -> None:
    if record.schema_version != schema or record.semantic_digest != _digest_record(record):
        raise CatalogDeploymentAuthorizationError("authorization_record_invalid")


def _create_or_verify(handle: InstallationStateHandle, obj: InstallationStateObject, record: Any) -> bool:
    data = json.dumps(asdict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    try:
        handle.durable_create(obj, data, verify=lambda raw: _verify_bytes(raw, data))
        return False
    except InstallationStateError as exc:
        if exc.code != "state_object_already_exists" or handle.read_regular(obj) != data:
            raise CatalogDeploymentAuthorizationError("authorization_identity_conflict") from exc
        return True


def _verify_bytes(observed: bytes, expected: bytes) -> None:
    if observed != expected:
        raise CatalogDeploymentAuthorizationError("durable_authorization_verification_failed")


def issue_catalog_deployment_authorization(
    handle: InstallationStateHandle, request: CatalogDeploymentAuthorizationRequest,
    approval: CatalogDeploymentApprovalEvidence, candidate: Mapping[str, Any],
    publication_receipts: Sequence[Mapping[str, Any]], kernel: ControlPlaneKernel, *,
    created_at: str, allow_synthetic_test_evidence: bool = False,
) -> CatalogDeploymentAuthorizationResult:
    """Issue exact records after independent evidence and control-plane checks."""
    custody = CatalogDeploymentAuthorizationCustody.for_installation(handle)
    if request.issuer_principal != ISSUER_PRINCIPAL or request.issuance_capability_id != LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE:
        raise CatalogDeploymentAuthorizationError("issuer_authority_denied")
    if not _exact_tuple(request.issuance_effects, ISSUANCE_EFFECTS):
        raise CatalogDeploymentAuthorizationError("issuance_effects_invalid")
    if request.installation_identity != handle.identity.value or request.custody_identity != custody.custody_identity:
        raise CatalogDeploymentAuthorizationError("installation_custody_mismatch")
    if not _valid_prior(request.expected_prior_state):
        raise CatalogDeploymentAuthorizationError("exact_prior_state_required")
    start, end = _instant(request.not_before), _instant(request.expires_at)
    lease_start, lease_end = _instant(request.lease_not_before), _instant(request.lease_expires_at)
    if not start < end or (end - start).total_seconds() > MAX_GRANT_SECONDS:
        raise CatalogDeploymentAuthorizationError("grant_interval_invalid")
    if lease_start < start or lease_end > end or not lease_start < lease_end:
        raise CatalogDeploymentAuthorizationError("lease_interval_invalid")
    _instant(created_at)
    verify_approval_evidence(approval, allow_synthetic_test_evidence=allow_synthetic_test_evidence)
    validated = validate_local_model_catalog(candidate)
    candidate_digest = local_model_catalog_digest(validated)
    if candidate_digest != request.candidate_catalog_semantic_digest:
        raise CatalogDeploymentAuthorizationError("candidate_digest_mismatch")
    evidence = verify_catalog_publication_evidence(validated["models"], publication_receipts)
    evidence_digest = str(evidence["publication_evidence_set_semantic_digest"])
    if evidence_digest != request.publication_evidence_set_semantic_digest:
        raise CatalogDeploymentAuthorizationError("publication_evidence_digest_mismatch")
    exact_approval = {
        "target_issuance_capability": request.issuance_capability_id, "target_issuer_principal": request.issuer_principal,
        "correlation_id": request.correlation_id, "installation_identity": request.installation_identity,
        "custody_identity": request.custody_identity, "candidate_catalog_semantic_digest": candidate_digest,
        "expected_prior_state": request.expected_prior_state,
        "publication_evidence_set_semantic_digest": evidence_digest, "requested_not_before": request.not_before,
        "requested_expires_at": request.expires_at,
    }
    if any(getattr(approval, key) != value for key, value in exact_approval.items()):
        raise CatalogDeploymentAuthorizationError("approval_request_binding_mismatch")
    common = {"issuer_principal": ISSUER_PRINCIPAL, "target_principal": TARGET_PRINCIPAL,
              "target_capability": LOCAL_MODEL_CATALOG_DEPLOY, "target_effects": TARGET_EFFECTS,
              "correlation_id": request.correlation_id, "installation_identity": request.installation_identity,
              "custody_identity": request.custody_identity, "candidate_catalog_semantic_digest": candidate_digest,
              "publication_evidence_set_semantic_digest": evidence_digest,
              "expected_prior_state": request.expected_prior_state}
    identity = {**common, "approval_evidence_id": approval.approval_evidence_id,
                "approval_evidence_digest": approval.semantic_digest, "not_before": request.not_before,
                "expires_at": request.expires_at}
    grant_id = "catalog-deployment-grant-" + semantic_digest(identity)[:24]
    lease_id = "catalog-deployment-lease-" + semantic_digest({**identity, "grant_id": grant_id,
                                                               "not_before": request.lease_not_before,
                                                               "expires_at": request.lease_expires_at})[:24]
    admission_metadata = {**identity, "correlation_id": request.correlation_id, "issuance_effects": list(ISSUANCE_EFFECTS),
                          "issuance_effect_set_digest": semantic_digest(list(ISSUANCE_EFFECTS)),
                          "requested_grant_id": grant_id, "requested_lease_id": lease_id}
    decision = kernel.admit(ControlActionRequest("issue_catalog_deployment_authorization",
        AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE, ISSUER_PRINCIPAL, "model_distribution",
        LifecyclePhase.RUNTIME, metadata=admission_metadata))
    if decision.outcome != AdmissionOutcome.ALLOW or decision.authority_class != AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE or decision.actor != ISSUER_PRINCIPAL or decision.correlation_id != request.correlation_id:
        raise CatalogDeploymentAuthorizationError("control_plane_admission_denied")
    admission_ref = decision.admission_decision_ref
    synthetic = approval.synthetic_test_evidence
    grant = _with_digest(CatalogDeploymentAuthorizationGrant(grant_id, ISSUER_PRINCIPAL,
        request.issuance_capability_id, ISSUANCE_EFFECTS, approval.approval_evidence_id, approval.semantic_digest,
        admission_ref, TARGET_PRINCIPAL, LOCAL_MODEL_CATALOG_DEPLOY, TARGET_EFFECTS, request.correlation_id,
        request.installation_identity, request.custody_identity, candidate_digest, evidence_digest,
        request.expected_prior_state, request.not_before, request.expires_at, True, "revocable", None,
        created_at, "", synthetic_test_authority=synthetic))
    lease = _with_digest(CatalogDeploymentAuthorizationLease(lease_id, grant.grant_id, grant.semantic_digest,
        ISSUER_PRINCIPAL, TARGET_PRINCIPAL, LOCAL_MODEL_CATALOG_DEPLOY, TARGET_EFFECTS, request.correlation_id,
        request.installation_identity, request.custody_identity, candidate_digest, evidence_digest,
        request.expected_prior_state, request.lease_not_before, request.lease_expires_at, True, "",
        synthetic_test_authority=synthetic))
    receipt_id = "catalog-deployment-authorization-" + semantic_digest({"grant": grant.semantic_digest, "lease": lease.semantic_digest})[:24]
    receipt = _with_digest(CatalogDeploymentAuthorizationReceipt(receipt_id, ISSUER_PRINCIPAL,
        request.issuance_capability_id, ISSUANCE_EFFECTS, approval.approval_evidence_id, approval.semantic_digest,
        admission_ref, grant.grant_id, grant.semantic_digest, lease.lease_id, lease.semantic_digest,
        TARGET_PRINCIPAL, LOCAL_MODEL_CATALOG_DEPLOY, TARGET_EFFECTS, request.correlation_id,
        request.installation_identity, request.custody_identity, candidate_digest, evidence_digest,
        request.expected_prior_state, request.lease_not_before, request.lease_expires_at,
        "issued", created_at, "", synthetic_test_authority=synthetic))
    custody.initialize()
    with handle.exclusive_lock(custody.lock):
        replay = _create_or_verify(handle, custody.grants.child(grant.grant_id + ".json"), grant)
        replay = _create_or_verify(handle, custody.leases.child(lease.lease_id + ".json"), lease) and replay
        replay = _create_or_verify(handle, custody.receipts.child(receipt.receipt_id + ".json"), receipt) and replay
    return CatalogDeploymentAuthorizationResult("replayed" if replay else "issued", grant, lease, receipt)


def project_catalog_deployment_authority(
    grant: CatalogDeploymentAuthorizationGrant, lease: CatalogDeploymentAuthorizationLease,
    receipt: CatalogDeploymentAuthorizationReceipt, *, observed_at: str,
    revocations: Sequence[Mapping[str, Any]] = (), allow_synthetic_test_authority: bool = False,
) -> CatalogDeploymentAuthority:
    """Verify the full issuance chain and narrowly adapt it to controller authority."""
    _verify_record(grant, GRANT_SCHEMA); _verify_record(lease, LEASE_SCHEMA); _verify_record(receipt, RECEIPT_SCHEMA)
    now = _instant(observed_at); gs, ge = _instant(grant.not_before), _instant(grant.expires_at)
    ls, le = _instant(lease.not_before), _instant(lease.expires_at)
    if not grant.active or not lease.active or not (gs <= now < ge and ls <= now < le) or ls < gs or le > ge:
        raise CatalogDeploymentAuthorizationError("authorization_not_current")
    synthetic = grant.synthetic_test_authority or lease.synthetic_test_authority or receipt.synthetic_test_authority
    if synthetic and not allow_synthetic_test_authority:
        raise CatalogDeploymentAuthorizationError("synthetic_authority_forbidden")
    binding = (lease.parent_grant_id == grant.grant_id and lease.parent_grant_digest == grant.semantic_digest
        and receipt.grant_id == grant.grant_id and receipt.grant_digest == grant.semantic_digest
        and receipt.lease_id == lease.lease_id and receipt.lease_digest == lease.semantic_digest)
    fields = ("issuer_principal", "target_principal", "target_capability", "target_effects", "correlation_id",
              "installation_identity", "custody_identity", "candidate_catalog_semantic_digest",
              "publication_evidence_set_semantic_digest", "expected_prior_state")
    if not binding or any(getattr(grant, f) != getattr(lease, f) or getattr(grant, f) != getattr(receipt, f) for f in fields):
        raise CatalogDeploymentAuthorizationError("authorization_cross_binding_mismatch")
    if grant.issuer_principal != ISSUER_PRINCIPAL or grant.target_principal != TARGET_PRINCIPAL or grant.target_capability != LOCAL_MODEL_CATALOG_DEPLOY or not _exact_tuple(grant.target_effects, TARGET_EFFECTS):
        raise CatalogDeploymentAuthorizationError("target_authority_invalid")
    for revocation in revocations:
        if (revocation.get("schema_version") == REVOCATION_SCHEMA and revocation.get("active") is True
                and (revocation.get("grant_id") == grant.grant_id or revocation.get("lease_id") == lease.lease_id)):
            raise CatalogDeploymentAuthorizationError("authorization_revoked")
    return CatalogDeploymentAuthority(grant.grant_id, lease.lease_id, TARGET_PRINCIPAL,
        LOCAL_MODEL_CATALOG_DEPLOY, TARGET_EFFECTS, grant.correlation_id, grant.installation_identity,
        grant.custody_identity, grant.candidate_catalog_semantic_digest, grant.expected_prior_state,
        True, lease.not_before, lease.expires_at, synthetic_test_authority=synthetic)
