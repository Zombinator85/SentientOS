"""Machine-readable law for future authoritative local-model catalog custody.

This module describes and validates governance metadata only.  It does not locate an
installation, acquire a lock, issue authority, mutate a catalog, or write a receipt.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    LOCAL_MODEL_CATALOG_DEPLOY,
)

ARCHITECTURE_SCHEMA = "sentientos.local_model_catalog_deployment_architecture:v1"
PUBLICATION_EVIDENCE_SET_SCHEMA = "sentientos.local_model_catalog_publication_evidence_set:v1"
TRANSACTION_SCHEMA = "sentientos.local_model_catalog_deployment_transaction:v1"
DEPLOYMENT_RECEIPT_SCHEMA = "sentientos.local_model_catalog_deployment_receipt:v1"
AUTHORITATIVE_CUSTODY_KIND = "sentientos-installation:model-catalog"
INSTALLATION_ROOT_TOKEN = "<installation-state-root>"
CATALOG_DOMAIN = "model-catalog"
AUTHORITATIVE_CATALOG = "model-catalog/authoritative-catalog.json"
CATALOG_LOCK = "model-catalog/catalog.lock"
TRANSACTIONS = "model-catalog/transactions"
DEPLOYMENT_RECEIPTS = "model-catalog/deployment-receipts"
EXPECTED_ABSENT = "ABSENT"
PRINCIPAL = "deterministic_catalog_deployment_controller"
EFFECTS = tuple(sorted(AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOY].required_effects))


def semantic_digest(value: object) -> str:
    """Return the repository-standard deterministic JSON SHA-256 identity."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CatalogCustodyArchitecture:
    """The fixed, governance-only projection a later controller must implement."""

    schema_version: str = ARCHITECTURE_SCHEMA
    capability_id: str = LOCAL_MODEL_CATALOG_DEPLOY
    principal: str = PRINCIPAL
    effects: tuple[str, ...] = EFFECTS
    custody_scope: str = "installation"
    custody_kind: str = AUTHORITATIVE_CUSTODY_KIND
    authoritative_catalog_relative_path: str = AUTHORITATIVE_CATALOG
    lock_relative_path: str = CATALOG_LOCK
    transactions_relative_path: str = TRANSACTIONS
    deployment_receipts_relative_path: str = DEPLOYMENT_RECEIPTS
    lock_scope: str = "one-exclusive-lock-per-installation-catalog-domain"
    cas_contract: str = "explicit-absent-genesis-or-exact-prior-semantic-digest"
    evidence_contract: str = "complete-duplicate-free-one-receipt-per-candidate-model"
    recovery_contract: str = "durable-intent-staged-candidate-published-catalog-immutable-receipt-finalized"
    controller_status: str = "implemented-without-live-authority"
    consumer_integration_status: str = "deferred"
    runtime_effects_enabled: bool = False


ARCHITECTURE = CatalogCustodyArchitecture()

PATH_SAFETY_REQUIREMENTS = (
    "canonical_installation_root_identity_required",
    "all_objects_contained_by_canonical_installation_root",
    "parent_traversal_forbidden",
    "protected_object_symlink_substitution_forbidden",
    "catalog_intent_stage_and_receipt_are_regular_files",
    "fixed_relative_names_only",
    "arbitrary_destination_redirection_forbidden",
    "least_privilege_installation_state_permissions",
    "platform_appropriate_secure_creation",
)

LOCK_PROTECTED_STEPS = (
    "recovery_inspection", "observed_prior_state", "cas_comparison", "transaction_creation",
    "catalog_publication", "deployment_receipt_publication", "transaction_finalization",
)

TRANSACTION_STATES = (
    "intent_persisted", "candidate_staged", "catalog_published", "receipt_published", "finalized",
)

RECOVERY_OUTCOMES = {
    "prior_catalog_and_no_receipt": "not_committed_abort_staged_candidate",
    "proposed_catalog_and_no_receipt": "recoverably_committed_reconstruct_exact_receipt",
    "proposed_catalog_and_exact_receipt": "already_committed_verify_and_finalize",
    "identity_conflict_or_unreconstructable": "manual_recovery_required_fail_closed_preserve_evidence",
}

DEPLOYMENT_RECEIPT_FIELDS = (
    "schema_version", "transaction_id", "controller_principal", "capability_id", "effect_set_digest",
    "grant_id", "lease_id", "correlation_id", "candidate_catalog_semantic_digest",
    "publication_evidence_set_semantic_digest", "publication_evidence", "expected_prior_state",
    "observed_prior_state", "transition_kind", "resulting_authoritative_catalog_semantic_digest",
    "installation_identity", "custody_identity", "validation_outcome", "deployed_at", "final_state",
    "receipt_id", "receipt_semantic_digest",
)

GRANT_LEASE_BINDINGS = (
    "active", "validity_window", "grant_id", "lease_id", "principal", "capability_id",
    "exact_duplicate_free_effect_set", "correlation_id", "installation_identity", "custody_identity",
    "candidate_catalog_semantic_digest", "expected_prior_state",
)

CONSUMER_PROOF_FIELDS = (
    "installation_identity", "custody_identity", "authoritative_catalog_semantic_digest",
    "deployment_receipt_id", "deployment_receipt_semantic_digest", "resulting_catalog_digest",
    "transaction_final_state",
)

FORBIDDEN_ADJACENT_AUTHORITY = (
    "provider_access", "network_access", "credential_access", "artifact_acquisition", "commissioning",
    "activation", "inference", "git_publication", "model_mirror_mutation", "catalog_mutation",
    "runtime_deployment", "software_deployment", "shell_authority", "arbitrary_filesystem_authority",
    "arbitrary_destination", "mutable_catalog_alias", "self_grant", "publication_authority_inheritance",
)


class EvidenceSetContractError(ValueError):
    """A publication-evidence projection is not exact and complete."""


def publication_evidence_set_projection(
    candidate_models: Sequence[Mapping[str, Any]], receipts: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    """Validate exact model/receipt cardinality and derive its canonical identity.

    Full receipt cryptographic and artifact validation remains the future controller's
    responsibility using the canonical publication verifier.  This governance helper
    only makes the required complete, duplicate-free set relationship executable.
    """
    model_ids = [item.get("model_id") for item in candidate_models]
    if any(not isinstance(item, str) or not item for item in model_ids) or len(model_ids) != len(set(model_ids)):
        raise EvidenceSetContractError("candidate_model_identity_invalid_or_duplicate")
    rows: list[dict[str, str]] = []
    receipt_ids: set[str] = set()
    receipt_models: set[str] = set()
    for receipt in receipts:
        model_id = receipt.get("model_id")
        receipt_id = receipt.get("receipt_id")
        digest = receipt.get("receipt_semantic_digest")
        if not all(isinstance(item, str) and item for item in (model_id, receipt_id, digest)):
            raise EvidenceSetContractError("publication_receipt_identity_missing")
        assert isinstance(model_id, str) and isinstance(receipt_id, str) and isinstance(digest, str)
        if model_id in receipt_models or receipt_id in receipt_ids:
            raise EvidenceSetContractError("duplicate_publication_evidence")
        receipt_models.add(model_id)
        receipt_ids.add(receipt_id)
        rows.append({"model_id": model_id, "publication_receipt_id": receipt_id,
                     "publication_receipt_semantic_digest": digest})
    if receipt_models != set(model_ids):
        raise EvidenceSetContractError("publication_evidence_set_not_exact")
    rows.sort(key=lambda item: item["model_id"])
    semantic = {"schema_version": PUBLICATION_EVIDENCE_SET_SCHEMA, "evidence": rows}
    return {**semantic, "publication_evidence_set_semantic_digest": semantic_digest(semantic)}
