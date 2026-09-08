from __future__ import annotations

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import AUTHORITY_DEFINITIONS, LOCAL_MODEL_CATALOG_DEPLOY
from sentientos.local_model_catalog_deployment_architecture import (
    ARCHITECTURE, AUTHORITATIVE_CATALOG, CATALOG_LOCK, CONSUMER_PROOF_FIELDS,
    DEPLOYMENT_RECEIPTS, DEPLOYMENT_RECEIPT_FIELDS, EFFECTS, FORBIDDEN_ADJACENT_AUTHORITY,
    GRANT_LEASE_BINDINGS, LOCK_PROTECTED_STEPS, PATH_SAFETY_REQUIREMENTS, PRINCIPAL,
    RECOVERY_OUTCOMES, TRANSACTIONS, EvidenceSetContractError, publication_evidence_set_projection,
)

pytestmark = pytest.mark.no_legacy_skip


def receipt(model: str, identity: str) -> dict[str, str]:
    return {"model_id": model, "receipt_id": identity, "receipt_semantic_digest": identity * 64}


def test_exact_capability_and_non_runtime_architecture_remain_bounded() -> None:
    definition = AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOY]
    assert ARCHITECTURE.principal == PRINCIPAL == "deterministic_catalog_deployment_controller"
    assert frozenset(EFFECTS) == definition.required_effects
    assert ARCHITECTURE.runtime_effects_enabled is False
    assert ARCHITECTURE.controller_status == "implemented-without-live-authority"
    assert ARCHITECTURE.consumer_integration_status == "implemented_for_production_selection_and_acquisition"
    assert "publication_authority_inheritance" in FORBIDDEN_ADJACENT_AUTHORITY
    assert {"provider_access", "artifact_acquisition", "commissioning", "activation", "inference"} <= set(FORBIDDEN_ADJACENT_AUTHORITY)


def test_custody_paths_are_fixed_installation_scoped_and_safe() -> None:
    assert ARCHITECTURE.custody_scope == "installation"
    assert AUTHORITATIVE_CATALOG == "model-catalog/authoritative-catalog.json"
    assert CATALOG_LOCK == "model-catalog/catalog.lock"
    assert TRANSACTIONS == "model-catalog/transactions"
    assert DEPLOYMENT_RECEIPTS == "model-catalog/deployment-receipts"
    assert all(not value.startswith("/") and ".." not in value.split("/") for value in (
        AUTHORITATIVE_CATALOG, CATALOG_LOCK, TRANSACTIONS, DEPLOYMENT_RECEIPTS))
    assert "arbitrary_destination_redirection_forbidden" in PATH_SAFETY_REQUIREMENTS


def test_cas_lock_recovery_receipt_and_future_binding_are_machine_legible() -> None:
    assert ARCHITECTURE.cas_contract == "explicit-absent-genesis-or-exact-prior-semantic-digest"
    assert ARCHITECTURE.lock_scope == "one-exclusive-lock-per-installation-catalog-domain"
    assert {"observed_prior_state", "cas_comparison", "catalog_publication", "deployment_receipt_publication"} <= set(LOCK_PROTECTED_STEPS)
    assert set(RECOVERY_OUTCOMES.values()) == {
        "not_committed_abort_staged_candidate", "recoverably_committed_reconstruct_exact_receipt",
        "already_committed_verify_and_finalize", "manual_recovery_required_fail_closed_preserve_evidence",
    }
    assert {"expected_prior_state", "observed_prior_state", "publication_evidence_set_semantic_digest",
            "installation_identity", "custody_identity", "receipt_semantic_digest"} <= set(DEPLOYMENT_RECEIPT_FIELDS)
    assert {"active", "validity_window", "candidate_catalog_semantic_digest", "expected_prior_state"} <= set(GRANT_LEASE_BINDINGS)
    assert {"installation_identity", "authoritative_catalog_semantic_digest",
            "deployment_receipt_semantic_digest", "transaction_final_state"} <= set(CONSUMER_PROOF_FIELDS)


def test_complete_multi_model_publication_evidence_projection_is_deterministic() -> None:
    models = [{"model_id": "b"}, {"model_id": "a"}]
    result = publication_evidence_set_projection(models, [receipt("a", "a"), receipt("b", "b")])
    reversed_result = publication_evidence_set_projection(models, [receipt("b", "b"), receipt("a", "a")])
    assert result == reversed_result
    evidence = result["evidence"]
    assert isinstance(evidence, list)
    assert [row["model_id"] for row in evidence] == ["a", "b"]


def test_missing_extra_or_duplicate_publication_evidence_fails_closed() -> None:
    invalid_sets = (
        [receipt("a", "a")],
        [receipt("a", "a"), receipt("b", "b"), receipt("c", "c")],
        [receipt("a", "a"), receipt("a", "z"), receipt("b", "b")],
        [receipt("a", "x"), receipt("b", "x")],
    )
    for receipts in invalid_sets:
        with pytest.raises(EvidenceSetContractError):
            publication_evidence_set_projection([{"model_id": "a"}, {"model_id": "b"}], receipts)


def test_registry_describes_controller_but_keeps_live_authority_and_consumers_deferred() -> None:
    record = build_default_capability_registry().by_id()[LOCAL_MODEL_CATALOG_DEPLOY]
    assert record.authority_level == "bounded_operator_confirmed_local_environment_mutation"
    assert "deterministic authority consumption boundary" in record.implemented_surfaces
    assert "production deployment grant or lease issuance" in record.deferred_surfaces
    assert "selection and acquisition authoritative-custody enforcement" in record.deferred_surfaces
