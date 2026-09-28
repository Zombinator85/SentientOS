"""Finite, revocable authorization bridge for sovereign mirror publication."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence, cast

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, MODEL_MIRROR_PUBLICATION_AUTHORIZATION_ISSUE, MODEL_MIRROR_PUBLISH,
)
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionRequest, ControlPlaneKernel, LifecyclePhase
from sentientos.installation_state import InstallationStateError, InstallationStateHandle, InstallationStateObject
from sentientos.model_mirror_publication import (
    EFFECTS, HARDENED_GRANT_SCHEMA, PRINCIPAL, PublicationGrant, PublicationRequest, semantic_digest,
)

INTENT_SCHEMA = "sentientos.model_mirror_publication_intent:v1"
APPROVAL_SCHEMA = "sentientos.model_mirror_publication_authorization_approval:v1"
REQUEST_SCHEMA = "sentientos.model_mirror_publication_authorization_request:v1"
GRANT_SCHEMA = "sentientos.model_mirror_publication_authorization_grant:v1"
LEASE_SCHEMA = "sentientos.model_mirror_publication_authorization_lease:v1"
RECEIPT_SCHEMA = "sentientos.model_mirror_publication_authorization_receipt:v1"
REVOCATION_SCHEMA = "sentientos.model_mirror_publication_authorization_revocation:v1"
ISSUER_PRINCIPAL = "deterministic_model_mirror_publication_authorization_controller"
ISSUANCE_CAPABILITY = MODEL_MIRROR_PUBLICATION_AUTHORIZATION_ISSUE
ISSUANCE_EFFECTS = tuple(sorted(AUTHORITY_DEFINITIONS[ISSUANCE_CAPABILITY].required_effects))
TARGET_EFFECTS = tuple(sorted(EFFECTS))
MAX_GRANT_SECONDS = 3600
PLACEHOLDERS = frozenset({"", "anonymous", "default", "operator", "placeholder", "sample", "test", "unknown"})


class ModelMirrorPublicationAuthorizationError(RuntimeError):
    def __init__(self, code: str): self.code = code; super().__init__(code)


@dataclass(frozen=True)
class ModelMirrorPublicationIntent:
    intent_id: str; curator_package_path: str; curator_package_sha256: str; model_id: str
    artifact_path: str; artifact_sha256: str; artifact_size: int; object_name: str; canonical_url: str
    target_publication_principal: str; target_publication_capability: str; target_effect_set_digest: str
    publication_correlation_id: str; provider_configuration_identity: str; provider_configuration_digest: str
    semantic_digest: str; schema_version: str = INTENT_SCHEMA


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationApproval:
    approval_evidence_id: str; operator_identity: str; operator_provenance: str; approval_status: str
    issuance_capability: str; issuer_principal: str; issuance_effects: tuple[str, ...]
    authorization_correlation_id: str; publication_correlation_id: str; publication_intent_id: str
    publication_intent_digest: str; curator_package_digest: str; model_id: str; artifact_sha256: str
    artifact_size: int; object_name: str; canonical_url: str; target_publication_capability: str
    target_publication_principal: str; target_effect_set_digest: str; provider_configuration_identity: str
    provider_configuration_digest: str; requested_grant_not_before: str; requested_grant_expires_at: str
    requested_lease_not_before: str; requested_lease_expires_at: str; synthetic_test_evidence: bool
    semantic_digest: str; schema_version: str = APPROVAL_SCHEMA


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationRequest:
    issuer_principal: str; issuance_capability: str; issuance_effects: tuple[str, ...]
    authorization_correlation_id: str; publication_correlation_id: str; publication_intent_id: str
    publication_intent_digest: str; grant_not_before: str; grant_expires_at: str
    lease_not_before: str; lease_expires_at: str; schema_version: str = REQUEST_SCHEMA


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationGrant:
    grant_id: str; issuer_principal: str; issuance_capability: str; issuance_effects: tuple[str, ...]
    approval_evidence_id: str; approval_evidence_digest: str; admission_reference: str
    target_principal: str; target_capability: str; target_effects: tuple[str, ...]
    publication_intent_id: str; publication_intent_digest: str; curator_package_digest: str
    model_id: str; artifact_sha256: str; artifact_size: int; object_name: str; canonical_url: str
    publication_correlation_id: str; provider_configuration_digest: str; not_before: str; expires_at: str
    active: bool; revocation_posture: str; synthetic_test_authority: bool; semantic_digest: str
    schema_version: str = GRANT_SCHEMA


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationLease:
    lease_id: str; parent_grant_id: str; parent_grant_digest: str; issuer_principal: str
    target_principal: str; target_capability: str; target_effects: tuple[str, ...]
    publication_intent_id: str; publication_intent_digest: str; publication_correlation_id: str
    provider_configuration_digest: str; not_before: str; expires_at: str; active: bool
    synthetic_test_authority: bool; semantic_digest: str; schema_version: str = LEASE_SCHEMA


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationReceipt:
    receipt_id: str; grant_id: str; grant_digest: str; lease_id: str; lease_digest: str
    approval_evidence_id: str; approval_evidence_digest: str; issuer_principal: str
    issuance_capability: str; issuance_effects: tuple[str, ...]; admission_reference: str
    target_principal: str; target_capability: str; target_effects: tuple[str, ...]
    publication_intent_id: str; publication_intent_digest: str; publication_correlation_id: str
    provider_configuration_digest: str; not_before: str; expires_at: str; issuance_status: str
    created_at: str; synthetic_test_authority: bool; semantic_digest: str; schema_version: str = RECEIPT_SCHEMA


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationRevocation:
    revocation_id: str; grant_id: str | None; lease_id: str | None; active: bool
    effective_at: str; reason: str; semantic_digest: str; schema_version: str = REVOCATION_SCHEMA


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationResult:
    status: str; grant: ModelMirrorPublicationAuthorizationGrant
    lease: ModelMirrorPublicationAuthorizationLease; receipt: ModelMirrorPublicationAuthorizationReceipt


@dataclass(frozen=True)
class ModelMirrorPublicationAuthorizationCustody:
    installation: InstallationStateHandle; root: InstallationStateObject; lock: InstallationStateObject
    grants: InstallationStateObject; leases: InstallationStateObject; receipts: InstallationStateObject
    revocations: InstallationStateObject
    @classmethod
    def for_installation(cls, handle: InstallationStateHandle) -> "ModelMirrorPublicationAuthorizationCustody":
        root = handle.fixed_object("authorization/model-mirror-publication")
        return cls(handle, root, root.child("authorization.lock"), root.child("grants"), root.child("leases"),
                   root.child("issuance-receipts"), root.child("revocations"))
    @property
    def custody_identity(self) -> str:
        return f"sentientos-installation:model-mirror-publication-authorization:{self.installation.identity.value}"
    def initialize(self) -> None:
        self.installation.ensure_directory(self.installation.fixed_object("authorization")); self.installation.ensure_directory(self.root)
        for item in (self.grants, self.leases, self.receipts, self.revocations): self.installation.ensure_directory(item)


def _instant(value: str) -> datetime:
    try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc: raise ModelMirrorPublicationAuthorizationError("malformed_timestamp") from exc
    if result.tzinfo is None: raise ModelMirrorPublicationAuthorizationError("timezone_required")
    return result.astimezone(timezone.utc)


def _digest(value: Any) -> str:
    body = asdict(value) if not isinstance(value, Mapping) else dict(value); body.pop("semantic_digest", None)
    return semantic_digest(body)


def with_semantic_digest(value: Any) -> Any: return replace(value, semantic_digest=_digest(value))


def build_publication_intent(**values: Any) -> ModelMirrorPublicationIntent:
    values["target_publication_principal"] = values.get("target_publication_principal", PRINCIPAL)
    values["target_publication_capability"] = values.get("target_publication_capability", MODEL_MIRROR_PUBLISH)
    values["target_effect_set_digest"] = values.get("target_effect_set_digest", semantic_digest(list(TARGET_EFFECTS)))
    values.setdefault("provider_configuration_identity", ""); values.setdefault("provider_configuration_digest", "")
    values.setdefault("semantic_digest", "")
    intent = ModelMirrorPublicationIntent(**values)
    return cast(ModelMirrorPublicationIntent, with_semantic_digest(intent))


def _verify(value: Any, schema: str) -> None:
    if value.schema_version != schema or value.semantic_digest != _digest(value):
        raise ModelMirrorPublicationAuthorizationError("authorization_record_invalid")


def _create(handle: InstallationStateHandle, obj: InstallationStateObject, value: Any) -> bool:
    data = json.dumps(asdict(value), sort_keys=True, separators=(",", ":")).encode()
    def verify(raw: bytes) -> None:
        if raw != data: raise ModelMirrorPublicationAuthorizationError("authorization_custody_verification_failed")
    try: handle.durable_create(obj, data, verify=verify); return False
    except InstallationStateError as exc:
        if exc.code == "state_object_already_exists" and handle.read_regular(obj) == data: return True
        raise ModelMirrorPublicationAuthorizationError("authorization_custody_conflict") from exc


def issue_model_mirror_publication_authorization(handle: InstallationStateHandle,
    request: ModelMirrorPublicationAuthorizationRequest, approval: ModelMirrorPublicationAuthorizationApproval | None,
    intent: ModelMirrorPublicationIntent, kernel: ControlPlaneKernel, *, created_at: str,
    allow_synthetic_test_evidence: bool = False) -> ModelMirrorPublicationAuthorizationResult:
    _verify(intent, INTENT_SCHEMA)
    if approval is None: raise ModelMirrorPublicationAuthorizationError("operator_approval_missing")
    _verify(approval, APPROVAL_SCHEMA)
    if request.schema_version != REQUEST_SCHEMA: raise ModelMirrorPublicationAuthorizationError("request_schema_invalid")
    if request.issuer_principal != ISSUER_PRINCIPAL or request.issuance_capability != ISSUANCE_CAPABILITY:
        raise ModelMirrorPublicationAuthorizationError("issuer_authority_denied")
    if tuple(sorted(request.issuance_effects)) != ISSUANCE_EFFECTS or len(set(request.issuance_effects)) != len(ISSUANCE_EFFECTS):
        raise ModelMirrorPublicationAuthorizationError("issuance_effects_invalid")
    if approval.operator_identity.strip().casefold() in PLACEHOLDERS: raise ModelMirrorPublicationAuthorizationError("operator_identity_invalid")
    if approval.approval_status != "approved": raise ModelMirrorPublicationAuthorizationError("operator_approval_required")
    if approval.synthetic_test_evidence and not allow_synthetic_test_evidence: raise ModelMirrorPublicationAuthorizationError("synthetic_approval_forbidden")
    gs, ge, ls, le = map(_instant, (request.grant_not_before, request.grant_expires_at, request.lease_not_before, request.lease_expires_at))
    if not gs < ge or (ge-gs).total_seconds() > MAX_GRANT_SECONDS: raise ModelMirrorPublicationAuthorizationError("grant_interval_invalid")
    if ls < gs or le > ge or not ls < le: raise ModelMirrorPublicationAuthorizationError("lease_interval_invalid")
    exact = {"issuance_capability": request.issuance_capability, "issuer_principal": request.issuer_principal,
      "issuance_effects": request.issuance_effects, "authorization_correlation_id": request.authorization_correlation_id,
      "publication_correlation_id": request.publication_correlation_id, "publication_intent_id": intent.intent_id,
      "publication_intent_digest": intent.semantic_digest, "curator_package_digest": intent.curator_package_sha256,
      "model_id": intent.model_id, "artifact_sha256": intent.artifact_sha256, "artifact_size": intent.artifact_size,
      "object_name": intent.object_name, "canonical_url": intent.canonical_url,
      "target_publication_capability": intent.target_publication_capability,
      "target_publication_principal": intent.target_publication_principal,
      "target_effect_set_digest": intent.target_effect_set_digest,
      "provider_configuration_identity": intent.provider_configuration_identity,
      "provider_configuration_digest": intent.provider_configuration_digest,
      "requested_grant_not_before": request.grant_not_before, "requested_grant_expires_at": request.grant_expires_at,
      "requested_lease_not_before": request.lease_not_before, "requested_lease_expires_at": request.lease_expires_at}
    if any(getattr(approval, key) != value for key, value in exact.items()):
        raise ModelMirrorPublicationAuthorizationError("approval_intent_binding_mismatch")
    if request.publication_intent_id != intent.intent_id or request.publication_intent_digest != intent.semantic_digest or request.publication_correlation_id != intent.publication_correlation_id:
        raise ModelMirrorPublicationAuthorizationError("request_intent_binding_mismatch")
    if request.authorization_correlation_id == request.publication_correlation_id:
        raise ModelMirrorPublicationAuthorizationError("correlations_must_be_distinct")
    common = dict(issuer_principal=ISSUER_PRINCIPAL, target_principal=PRINCIPAL, target_capability=MODEL_MIRROR_PUBLISH,
      target_effects=TARGET_EFFECTS, publication_intent_id=intent.intent_id, publication_intent_digest=intent.semantic_digest,
      publication_correlation_id=request.publication_correlation_id, provider_configuration_digest=intent.provider_configuration_digest)
    grant_id = "model-mirror-publication-grant-" + semantic_digest({**common, "approval": approval.semantic_digest, "expires": request.grant_expires_at})[:24]
    lease_id = "model-mirror-publication-lease-" + semantic_digest({"grant": grant_id, "not_before": request.lease_not_before, "expires": request.lease_expires_at})[:24]
    decision = kernel.admit(ControlActionRequest("issue_model_mirror_publication_authorization", AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE,
      ISSUER_PRINCIPAL, "model_distribution", LifecyclePhase.RUNTIME, metadata={"correlation_id": request.authorization_correlation_id,
      "publication_correlation_id": request.publication_correlation_id, "publication_intent_digest": intent.semantic_digest,
      "issuance_effects": list(ISSUANCE_EFFECTS), "requested_grant_id": grant_id, "requested_lease_id": lease_id}))
    if decision.outcome != AdmissionOutcome.ALLOW or decision.actor != ISSUER_PRINCIPAL or decision.correlation_id != request.authorization_correlation_id:
        raise ModelMirrorPublicationAuthorizationError("control_plane_admission_denied")
    synthetic = approval.synthetic_test_evidence
    grant = with_semantic_digest(ModelMirrorPublicationAuthorizationGrant(grant_id, ISSUER_PRINCIPAL, ISSUANCE_CAPABILITY,
      ISSUANCE_EFFECTS, approval.approval_evidence_id, approval.semantic_digest, decision.admission_decision_ref,
      PRINCIPAL, MODEL_MIRROR_PUBLISH, TARGET_EFFECTS, intent.intent_id, intent.semantic_digest,
      intent.curator_package_sha256, intent.model_id, intent.artifact_sha256, intent.artifact_size, intent.object_name,
      intent.canonical_url, request.publication_correlation_id, intent.provider_configuration_digest,
      request.grant_not_before, request.grant_expires_at, True, "revocable", synthetic, ""))
    lease = with_semantic_digest(ModelMirrorPublicationAuthorizationLease(lease_id, grant.grant_id, grant.semantic_digest,
      ISSUER_PRINCIPAL, PRINCIPAL, MODEL_MIRROR_PUBLISH, TARGET_EFFECTS, intent.intent_id, intent.semantic_digest,
      request.publication_correlation_id, intent.provider_configuration_digest, request.lease_not_before,
      request.lease_expires_at, True, synthetic, ""))
    receipt_id = "model-mirror-publication-authorization-" + semantic_digest({"grant": grant.semantic_digest, "lease": lease.semantic_digest})[:24]
    receipt = with_semantic_digest(ModelMirrorPublicationAuthorizationReceipt(receipt_id, grant.grant_id, grant.semantic_digest,
      lease.lease_id, lease.semantic_digest, approval.approval_evidence_id, approval.semantic_digest, ISSUER_PRINCIPAL,
      ISSUANCE_CAPABILITY, ISSUANCE_EFFECTS, decision.admission_decision_ref, PRINCIPAL, MODEL_MIRROR_PUBLISH, TARGET_EFFECTS,
      intent.intent_id, intent.semantic_digest, request.publication_correlation_id, intent.provider_configuration_digest,
      request.lease_not_before, request.lease_expires_at, "issued", created_at, synthetic, ""))
    custody = ModelMirrorPublicationAuthorizationCustody.for_installation(handle); custody.initialize()
    with handle.exclusive_lock(custody.lock):
        replay = _create(handle, custody.grants.child(grant.grant_id+".json"), grant)
        replay = _create(handle, custody.leases.child(lease.lease_id+".json"), lease) and replay
        replay = _create(handle, custody.receipts.child(receipt.receipt_id+".json"), receipt) and replay
    return ModelMirrorPublicationAuthorizationResult("replayed" if replay else "issued", grant, lease, receipt)


def project_model_mirror_publication_authority(grant: ModelMirrorPublicationAuthorizationGrant,
    lease: ModelMirrorPublicationAuthorizationLease, receipt: ModelMirrorPublicationAuthorizationReceipt,
    intent: ModelMirrorPublicationIntent, *, observed_at: str, revocations: Sequence[Mapping[str, Any]] = (),
    allow_synthetic_test_authority: bool = False) -> PublicationGrant:
    for value, schema in ((intent, INTENT_SCHEMA), (grant, GRANT_SCHEMA), (lease, LEASE_SCHEMA), (receipt, RECEIPT_SCHEMA)): _verify(value, schema)
    now = _instant(observed_at); gs, ge, ls, le = map(_instant, (grant.not_before, grant.expires_at, lease.not_before, lease.expires_at))
    if not grant.active or not lease.active or not (gs <= now < ge and ls <= now < le) or ls < gs or le > ge:
        raise ModelMirrorPublicationAuthorizationError("authorization_not_current")
    synthetic = grant.synthetic_test_authority or lease.synthetic_test_authority or receipt.synthetic_test_authority
    if synthetic and not allow_synthetic_test_authority: raise ModelMirrorPublicationAuthorizationError("synthetic_authority_forbidden")
    if (lease.parent_grant_id != grant.grant_id or lease.parent_grant_digest != grant.semantic_digest or
      receipt.grant_id != grant.grant_id or receipt.grant_digest != grant.semantic_digest or receipt.lease_id != lease.lease_id or
      receipt.lease_digest != lease.semantic_digest): raise ModelMirrorPublicationAuthorizationError("authorization_cross_binding_mismatch")
    if grant.publication_intent_digest != intent.semantic_digest or grant.publication_intent_id != intent.intent_id:
        raise ModelMirrorPublicationAuthorizationError("authority_intent_mismatch")
    if grant.target_principal != PRINCIPAL or grant.target_capability != MODEL_MIRROR_PUBLISH or grant.target_effects != TARGET_EFFECTS:
        raise ModelMirrorPublicationAuthorizationError("target_authority_invalid")
    for item in revocations:
        body = dict(item); claimed = body.pop("semantic_digest", None)
        if (item.get("schema_version") == REVOCATION_SCHEMA and claimed == semantic_digest(body) and item.get("active") is True
          and (item.get("grant_id") == grant.grant_id or item.get("lease_id") == lease.lease_id)
          and _instant(str(item.get("effective_at"))) <= now): raise ModelMirrorPublicationAuthorizationError("authorization_revoked")
    binding = semantic_digest({"intent_digest": intent.semantic_digest, "grant_id": grant.grant_id, "lease_id": lease.lease_id,
      "correlation_id": grant.publication_correlation_id, "receipt_digest": receipt.semantic_digest})
    projected = PublicationGrant(grant.grant_id, lease.lease_id, PRINCIPAL, MODEL_MIRROR_PUBLISH, frozenset(TARGET_EFFECTS),
      grant.publication_correlation_id, True, HARDENED_GRANT_SCHEMA, intent.semantic_digest, binding, receipt.receipt_id,
      receipt.semantic_digest, grant.provider_configuration_digest, lease.not_before, lease.expires_at, synthetic, "")
    body = asdict(projected); body.pop("authority_semantic_digest"); body["effects"] = sorted(projected.effects)
    return replace(projected, authority_semantic_digest=semantic_digest(body))


def materialize_publication_request(intent: ModelMirrorPublicationIntent, authority: PublicationGrant) -> PublicationRequest:
    _verify(intent, INTENT_SCHEMA)
    expected = semantic_digest({"intent_digest": intent.semantic_digest, "grant_id": authority.grant_id,
      "lease_id": authority.lease_id, "correlation_id": authority.correlation_id,
      "receipt_digest": authority.authorization_receipt_digest})
    if (authority.schema_version != HARDENED_GRANT_SCHEMA or authority.publication_intent_digest != intent.semantic_digest or
      authority.publication_request_binding_digest != expected or authority.correlation_id != intent.publication_correlation_id):
        raise ModelMirrorPublicationAuthorizationError("request_binding_mismatch")
    return PublicationRequest(intent.curator_package_path, intent.curator_package_sha256, intent.model_id,
      intent.artifact_path, intent.artifact_size, intent.artifact_sha256, intent.object_name, intent.canonical_url,
      authority.principal, authority.capability_id, authority.grant_id, authority.lease_id, authority.correlation_id)
