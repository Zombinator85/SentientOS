"""Deterministic installation-scoped local-model catalog deployment controller.

This boundary consumes caller-supplied authority records.  It cannot issue authority,
select a destination, contact a provider, acquire a model, or confer consumer trust.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence, cast

from sentientos.codex_task_authority_admission import LOCAL_MODEL_CATALOG_DEPLOY
from sentientos.installation_state import InstallationStateError, InstallationStateHandle
from sentientos.local_model_catalog import LocalModelCatalogError, local_model_catalog_digest, validate_local_model_catalog
from sentientos.local_model_catalog_deployment_architecture import (
    DEPLOYMENT_RECEIPT_SCHEMA, EFFECTS, EXPECTED_ABSENT, PRINCIPAL, TRANSACTION_SCHEMA,
    EvidenceSetContractError, publication_evidence_set_projection, semantic_digest,
)
from sentientos.model_catalog_custody import ModelCatalogCustody
from sentientos.model_mirror_publication import RECEIPT_SCHEMA as PUBLICATION_RECEIPT_SCHEMA

FINALIZATION_SCHEMA = "sentientos.local_model_catalog_deployment_finalization:v1"
AUTHORITY_SCHEMA = "sentientos.local_model_catalog_deployment_authority:v1"
RESULTS = frozenset({"deployed_verified", "recovered_deployed_verified", "already_committed_verified",
                     "stale_prior_state", "authority_denied", "verified_publication_evidence_required",
                     "candidate_invalid", "not_committed", "recovery_required",
                     "manual_recovery_required", "platform_unsupported"})


@dataclass(frozen=True)
class CatalogDeploymentRequest:
    principal: str
    capability_id: str
    effects: tuple[str, ...]
    grant_id: str
    lease_id: str
    correlation_id: str
    installation_identity: str
    custody_identity: str
    proposed_catalog_semantic_digest: str
    expected_prior_state: str


@dataclass(frozen=True)
class CatalogDeploymentAuthority:
    grant_id: str
    lease_id: str
    principal: str
    capability_id: str
    effects: tuple[str, ...]
    correlation_id: str
    installation_identity: str
    custody_identity: str
    candidate_catalog_semantic_digest: str
    expected_prior_state: str
    active: bool
    not_before: str
    expires_at: str
    schema_version: str = AUTHORITY_SCHEMA
    synthetic_test_authority: bool = False


@dataclass(frozen=True)
class CatalogDeploymentResult:
    status: str
    transaction_id: str | None = None
    receipt_id: str | None = None
    resulting_catalog_digest: str | None = None


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _load(data: bytes) -> dict[str, Any]:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("object_not_mapping")
    return value


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(timezone.utc)


def _authority_valid(request: CatalogDeploymentRequest, authority: CatalogDeploymentAuthority,
                     custody: ModelCatalogCustody, now: str) -> bool:
    try:
        exact = tuple(sorted(EFFECTS))
        return (
            authority.schema_version == AUTHORITY_SCHEMA and authority.active is True
            and request.principal == authority.principal == PRINCIPAL
            and request.capability_id == authority.capability_id == LOCAL_MODEL_CATALOG_DEPLOY
            and len(request.effects) == len(set(request.effects)) == len(exact)
            and len(authority.effects) == len(set(authority.effects)) == len(exact)
            and tuple(sorted(request.effects)) == tuple(sorted(authority.effects)) == exact
            and request.grant_id == authority.grant_id and request.lease_id == authority.lease_id
            and request.correlation_id == authority.correlation_id
            and request.installation_identity == authority.installation_identity == custody.installation.identity.value
            and request.custody_identity == authority.custody_identity == custody.custody_identity
            and request.proposed_catalog_semantic_digest == authority.candidate_catalog_semantic_digest
            and request.expected_prior_state == authority.expected_prior_state
            and _instant(authority.not_before) <= _instant(now) < _instant(authority.expires_at)
        )
    except (TypeError, ValueError):
        return False


def _validate_publications(models: Sequence[Mapping[str, Any]], receipts: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    projection = publication_evidence_set_projection(models, receipts)
    by_model = {str(model["model_id"]): model for model in models}
    for receipt in receipts:
        copy = dict(receipt)
        claimed_digest = copy.pop("receipt_semantic_digest", None)
        claimed_id = copy.pop("receipt_id", None)
        identity_body = dict(copy)
        expected_id = "model-publication-" + semantic_digest(identity_body)[:24]
        model = by_model.get(str(receipt.get("model_id")))
        if (
            receipt.get("schema_version") != PUBLICATION_RECEIPT_SCHEMA
            or claimed_id != expected_id
            or claimed_digest != semantic_digest({**identity_body, "receipt_id": claimed_id})
            or model is None
            or receipt.get("artifact_sha256") != model["artifact_sha256"]
            or receipt.get("artifact_size") != model["artifact_size_bytes"]
            or receipt.get("canonical_url") not in model["artifact_urls"]
            or receipt.get("object_exists") is not True or receipt.get("object_verified") is not True
            or receipt.get("remote_verification_method") != "complete_streamed_sha256"
            or receipt.get("remote_digest") != model["artifact_sha256"]
            or receipt.get("remote_size") != model["artifact_size_bytes"]
            or receipt.get("final_publication_status") not in {"published_verified", "already_present_verified"}
        ):
            raise EvidenceSetContractError("publication_receipt_not_independently_verified")
    return cast(dict[str, object], projection)


def _receipt_body(facts: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "schema_version": DEPLOYMENT_RECEIPT_SCHEMA, "transaction_id": facts["transaction_id"],
        "controller_principal": PRINCIPAL, "capability_id": LOCAL_MODEL_CATALOG_DEPLOY,
        "effect_set_digest": semantic_digest(list(EFFECTS)), "grant_id": facts["grant_id"],
        "lease_id": facts["lease_id"], "correlation_id": facts["correlation_id"],
        "candidate_catalog_semantic_digest": facts["candidate_catalog_semantic_digest"],
        "publication_evidence_set_semantic_digest": facts["publication_evidence_set_semantic_digest"],
        "publication_evidence": facts["publication_evidence"], "expected_prior_state": facts["expected_prior_state"],
        "observed_prior_state": facts["observed_prior_state"], "transition_kind": facts["transition_kind"],
        "resulting_authoritative_catalog_semantic_digest": facts["candidate_catalog_semantic_digest"],
        "installation_identity": facts["installation_identity"], "custody_identity": facts["custody_identity"],
        "validation_outcome": "candidate_and_publication_evidence_verified", "deployed_at": facts["deployed_at"],
        "final_state": "deployed_verified",
    }
    body["receipt_id"] = "catalog-deployment-" + semantic_digest(body)[:24]
    body["receipt_semantic_digest"] = semantic_digest(body)
    return body


def verify_deployment_receipt(receipt: Mapping[str, Any]) -> bool:
    copy = dict(receipt); claimed = copy.pop("receipt_semantic_digest", None)
    rid = copy.pop("receipt_id", None)
    return bool(receipt.get("schema_version") == DEPLOYMENT_RECEIPT_SCHEMA
            and rid == "catalog-deployment-" + semantic_digest(copy)[:24]
            and claimed == semantic_digest({**copy, "receipt_id": rid}))


def _catalog_digest(data: bytes | None) -> str:
    if data is None:
        return cast(str, EXPECTED_ABSENT)
    return cast(str, local_model_catalog_digest(validate_local_model_catalog(_load(data))))


def _create_exact(handle: InstallationStateHandle, obj: Any, data: bytes, verify: Callable[[bytes], None]) -> None:
    try:
        handle.durable_create(obj, data, verify=verify)
    except InstallationStateError as exc:
        if exc.code != "state_object_already_exists" or handle.read_regular(obj) != data:
            raise
        verify(data)


def _require(condition: bool, code: str = "durable_evidence_verification_failed") -> None:
    if not condition:
        raise ValueError(code)


def _finalize(custody: ModelCatalogCustody, intent: Mapping[str, Any], outcome: str) -> None:
    receipt = intent["deployment_receipt"]
    final = {"schema_version": FINALIZATION_SCHEMA, "transaction_id": intent["transaction_id"],
             "deployment_receipt_id": receipt["receipt_id"],
             "deployment_receipt_semantic_digest": receipt["receipt_semantic_digest"],
             "resulting_authoritative_catalog_semantic_digest": intent["candidate_catalog_semantic_digest"],
             "terminal_outcome": outcome}
    data = _canonical(final)
    _create_exact(custody.installation, custody.transactions.child(f"{intent['transaction_id']}.final.json"), data,
                  lambda raw: _require(_load(raw) == final, "finalization_conflict"))


def _recover_locked(custody: ModelCatalogCustody) -> CatalogDeploymentResult | None:
    h = custody.installation
    names = h.list_regular_names(custody.transactions)
    intents = [name for name in names if name.endswith(".intent.json") and name[:-12] + ".final.json" not in names]
    if len(intents) > 1:
        return CatalogDeploymentResult("manual_recovery_required")
    if not intents:
        return None
    try:
        intent = _load(h.read_regular(custody.transactions.child(intents[0])))
        if intent.get("schema_version") != TRANSACTION_SCHEMA or intents[0] != f"{intent.get('transaction_id')}.intent.json":
            raise ValueError
        candidate = h.read_regular(custody.transactions.child(f"{intent['transaction_id']}.candidate.json"))
        if _catalog_digest(candidate) != intent["candidate_catalog_semantic_digest"]:
            raise ValueError
        observed = _catalog_digest(h.read_optional_regular(custody.authoritative_catalog))
        receipt = intent["deployment_receipt"]
        receipt_obj = custody.deployment_receipts.child(f"{receipt['receipt_id']}.json")
        receipt_data = h.read_optional_regular(receipt_obj)
        if observed == intent["observed_prior_state"] and receipt_data is None:
            _finalize(custody, intent, "not_committed")
            return CatalogDeploymentResult("not_committed", intent["transaction_id"])
        if observed != intent["candidate_catalog_semantic_digest"]:
            raise ValueError
        expected = _canonical(receipt)
        if receipt_data is None:
            h.durable_create(receipt_obj, expected, verify=lambda raw: _require(verify_deployment_receipt(_load(raw))))
            _finalize(custody, intent, "recovered_deployed_verified")
            return CatalogDeploymentResult("recovered_deployed_verified", intent["transaction_id"], receipt["receipt_id"], observed)
        if receipt_data != expected or not verify_deployment_receipt(_load(receipt_data)):
            raise ValueError
        _finalize(custody, intent, "already_committed_verified")
        return CatalogDeploymentResult("already_committed_verified", intent["transaction_id"], receipt["receipt_id"], observed)
    except (InstallationStateError, ValueError, KeyError, TypeError, json.JSONDecodeError, LocalModelCatalogError):
        return CatalogDeploymentResult("manual_recovery_required")


def deploy_local_model_catalog(handle: InstallationStateHandle, request: CatalogDeploymentRequest,
                               authority: CatalogDeploymentAuthority, candidate: Mapping[str, Any],
                               publication_receipts: Sequence[Mapping[str, Any]], *, now: Callable[[], str]) -> CatalogDeploymentResult:
    """Perform one exact CAS transition, returning only bounded deterministic states."""
    try:
        custody = ModelCatalogCustody.for_installation(handle); custody.initialize_directories()
        timestamp = now()
    except InstallationStateError as exc:
        return CatalogDeploymentResult("platform_unsupported" if exc.code == "durable_state_platform_unsupported" else "recovery_required")
    if not _authority_valid(request, authority, custody, timestamp):
        return CatalogDeploymentResult("authority_denied")
    try:
        validated = validate_local_model_catalog(candidate)
        digest = local_model_catalog_digest(validated)
        if digest != request.proposed_catalog_semantic_digest:
            raise LocalModelCatalogError("proposed digest mismatch")
        candidate_bytes = _canonical(validated)
    except (LocalModelCatalogError, TypeError, ValueError):
        return CatalogDeploymentResult("candidate_invalid")
    try:
        evidence = _validate_publications(validated["models"], publication_receipts)
    except (EvidenceSetContractError, TypeError, ValueError):
        return CatalogDeploymentResult("verified_publication_evidence_required")
    try:
        with handle.exclusive_lock(custody.catalog_lock):
            recovered = _recover_locked(custody)
            if recovered is not None:
                return recovered
            observed = _catalog_digest(handle.read_optional_regular(custody.authoritative_catalog))
            if observed != request.expected_prior_state:
                return CatalogDeploymentResult("stale_prior_state")
            transition = "genesis" if observed == EXPECTED_ABSENT else "replacement"
            facts: dict[str, Any] = {
                "installation_identity": handle.identity.value, "custody_identity": custody.custody_identity,
                "controller_principal": PRINCIPAL, "capability_id": LOCAL_MODEL_CATALOG_DEPLOY,
                "effects": list(EFFECTS), "effect_set_digest": semantic_digest(list(EFFECTS)),
                "grant_id": request.grant_id, "lease_id": request.lease_id, "correlation_id": request.correlation_id,
                "candidate_catalog_semantic_digest": digest,
                "publication_evidence_set_semantic_digest": evidence["publication_evidence_set_semantic_digest"],
                "publication_evidence": evidence["evidence"], "expected_prior_state": request.expected_prior_state,
                "observed_prior_state": observed, "transition_kind": transition, "deployed_at": timestamp,
            }
            transaction_id = "catalog-transaction-" + semantic_digest(facts)[:24]
            facts["transaction_id"] = transaction_id
            receipt = _receipt_body(facts)
            intent = {"schema_version": TRANSACTION_SCHEMA, **facts,
                      "staged_candidate_semantic_digest": digest, "deployment_receipt": receipt}
            intent_data = _canonical(intent)
            handle.durable_create(custody.transactions.child(f"{transaction_id}.intent.json"), intent_data,
                                  verify=lambda raw: _require(_load(raw) == intent))
            handle.durable_create(custody.transactions.child(f"{transaction_id}.candidate.json"), candidate_bytes,
                                  verify=lambda raw: _require(_catalog_digest(raw) == digest))
            try:
                handle.durable_replace(custody.authoritative_catalog, candidate_bytes,
                                       verify=lambda raw: _require(_catalog_digest(raw) == digest))
                receipt_data = _canonical(receipt)
                handle.durable_create(custody.deployment_receipts.child(f"{receipt['receipt_id']}.json"), receipt_data,
                                      verify=lambda raw: _require(verify_deployment_receipt(_load(raw))))
                _finalize(custody, intent, "deployed_verified")
                return CatalogDeploymentResult("deployed_verified", transaction_id, receipt["receipt_id"], digest)
            except (InstallationStateError, ValueError, OSError):
                recovered = _recover_locked(custody)
                return recovered or CatalogDeploymentResult("recovery_required", transaction_id)
    except InstallationStateError as exc:
        return CatalogDeploymentResult("platform_unsupported" if exc.code == "durable_state_platform_unsupported" else "recovery_required")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, LocalModelCatalogError):
        return CatalogDeploymentResult("manual_recovery_required")
