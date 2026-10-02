from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    TaskAuthorityDefinition,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)
from sentientos.governed_local_model_resource_allocation import ALLOCATOR_ID, RESOURCE_KIND
from sentientos.production_chat_resource_provisioning import (
    MANIFEST_SCHEMA,
    validate_resource_provisioning_id,
)

pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "architecture/production_chat_resource_provisioning_bundle_contract.json"
DOC = ROOT / "docs/architecture/production_chat_resource_provisioning_bundle_contract.md"
CONTRACT: dict[str, Any] = json.loads(PATH.read_text(encoding="utf-8"))
DIGEST = "132f93c32f5490877a4748c0054dfb66aacb9f2a94ce560d69a0e65337c800f5"
CAPABILITY = "production_chat_resource_provisioning_bundle_create"
TASK = "register-production-chat-resource-provisioning-bundle-create-authority-definition"
EXPECTED_PATHS = [
    "sentientos/codex_task_authority_admission.py",
    "tests/test_authority_definition_registration.py",
    "docs/architecture/production_chat_resource_provisioning_bundle_contract.md",
]


def definition_from_json(item: dict[str, Any]) -> TaskAuthorityDefinition:
    return TaskAuthorityDefinition(
        capability_id=item["capability_id"],
        subsystem_kinds=frozenset(item["subsystem_kinds"]),
        principal_kinds=frozenset(item["principal_kinds"]),
        required_effects=frozenset(item["required_effects"]),
        forbidden_goal_phrases=tuple(item["forbidden_goal_phrases"]),
        required_goal_phrases=tuple(item["required_goal_phrases"]),
        approval_requirements=tuple(item["approval_requirements"]),
        purpose=item["purpose"],
    )


def candidate() -> TaskAuthorityDefinition:
    return definition_from_json(CONTRACT["candidate_task_authority_definition"])


def converted_payload(*, valid_approval: bool = True) -> dict[str, Any]:
    raw = CONTRACT["future_registration_task"]["register_authority_definition_payload"]
    definition = definition_from_json(raw["definitions"][0])
    approval = dict(raw["operator_approval"])
    if valid_approval:
        approval.update(evidence_id="test-only-producer-definition-approval",
                        operator_identity_label="operator:test-fixture-only")
        approval["evidence_digest"] = operator_approval_evidence_digest(approval)
    return {**raw, "definitions": (definition,), "operator_approval": approval,
            "requested_effects": tuple(raw["requested_effects"]),
            "runtime_mutations": tuple(raw["runtime_mutations"]),
            "changed_paths": tuple(raw["changed_paths"])}


def exact_handoff_result(payload: dict[str, Any]) -> Any:
    """Apply the frozen task surface before calling the generic registrar."""
    if list(payload.get("changed_paths", ())) != EXPECTED_PATHS:
        return None
    return register_authority_definition(payload, authority_definitions=dict(AUTHORITY_DEFINITIONS))


def test_consumer_compatibility_and_identifier_law_are_reused_exactly() -> None:
    consumer = CONTRACT["consumer_contract"]
    assert CONTRACT["schema"] == "sentientos.production_chat_resource_provisioning_bundle_contract:v1"
    assert consumer["manifest_schema"] == MANIFEST_SCHEMA
    assert consumer["required_filenames"] == [
        "manifest.json", "root-principal.json", "root-principal-provenance.json",
        "trusted-issuer-catalog.json", "principal-revocation-registry.json",
        "resource-policy.json", "resource-ledger.json",
    ]
    assert consumer["resource_kind"] == RESOURCE_KIND
    assert consumer["allocator_id"] == ALLOCATOR_ID
    assert validate_resource_provisioning_id("prod.chat_01") == "prod.chat_01"
    for invalid in ("../escape", "a/b", "all", "any", "A", "a" * 129):
        with pytest.raises(ValueError):
            validate_resource_provisioning_id(invalid)
    assert consumer["performs_allocation_issuance"] is False


def test_producer_behavioral_contract_is_create_only_preflighted_and_manifest_last() -> None:
    producer = CONTRACT["producer_contract"]
    assert producer["create_only"] == {
        "one_shot_id": True, "all_required_objects_must_be_absent": True,
        "fail_if_any_target_exists": True,
        "forbidden": ["overwrite", "merge", "repair in place", "append a second allocation",
                      "silently reuse provisioning ID", "automatic retry after partial creation",
                      "cleanup or delete"],
    }
    assert producer["publication_order"][-1] == "durably create manifest.json LAST"
    assert producer["publication_marker"] == "manifest.json"
    assert producer["allocation"]["issue_call"].endswith("exactly once")
    assert producer["allocation"]["post_issue_counts"] == {
        "allocation_count": 1, "attempt_count": 0, "resource_receipt_count": 0}
    assert producer["partial_failure"]["filesystem_wide_atomicity_claimed"] is False
    assert producer["partial_failure"]["retry_same_id_if_any_object_exists"] is False
    assert len(producer["preflight_before_write"]) == 12


def test_concurrency_trust_non_authority_and_restart_laws_are_frozen() -> None:
    producer = CONTRACT["producer_contract"]
    concurrency = producer["concurrency"]
    assert concurrency["lock_location"] == "local-model/resource-provisioning-locks/<resource_provisioning_id>.lock"
    assert "never only a process-local mutex" in concurrency["mechanism"]
    assert concurrency["grants_entitlement"] is False
    forbidden = set(producer["forbidden_operations"])
    assert {"mint_root", "mint_root_with_provenance", "sign issuer provenance",
            "private signing-key custody", "model inference or effect admission",
            "automatic startup integration"} <= forbidden
    assert producer["trusted_instant"]["count"] == 1
    assert producer["trusted_instant"]["later_invocation_clock"] is False
    assert len(producer["restart_inequalities"]) == 4
    assert CONTRACT["consumer_contract"]["restart_behavior"] == (
        "loads the same exact pre-issued allocation and does not replenish entitlement")
    assert "separate from consumer startup" in producer["lifecycle"]


def test_candidate_definition_digest_and_narrow_surface_are_exact() -> None:
    definition = candidate()
    assert definition.capability_id == CAPABILITY
    assert definition.subsystem_kinds == frozenset({"causal_resource_principal_architecture"})
    assert definition.principal_kinds == frozenset({
        "deterministic_production_chat_resource_provisioning_controller"})
    assert definition.required_effects == frozenset({
        "read_exact_preexisting_causal_resource_principal_artifacts",
        "read_exact_resource_trust_currentness_artifacts",
        "read_governed_local_model_resource_policy",
        "issue_one_governed_local_model_resource_allocation",
        "create_only_installation_state_resource_provisioning_bundle",
        "finalize_production_resource_provisioning_manifest",
    })
    assert authority_definition_digest(definition) == CONTRACT["candidate_definition_digest"] == DIGEST
    assert CAPABILITY not in AUTHORITY_DEFINITIONS
    doc = DOC.read_text(encoding="utf-8")
    assert DIGEST in doc and definition.purpose in doc


def test_registrar_native_handoff_registers_only_in_isolated_copy_without_authority() -> None:
    raw = CONTRACT["future_registration_task"]["register_authority_definition_payload"]
    assert list(raw) == ["task_classification", "task_name", "definitions", "operator_approval",
                         "requested_capability_id", "authority_principal", "requested_effects",
                         "runtime_mutations", "changed_paths"]
    assert raw["task_classification"] == AUTHORITY_DEFINITION_REGISTRATION
    assert raw["task_name"] == TASK
    assert raw["changed_paths"] == EXPECTED_PATHS
    assert raw["requested_capability_id"] == raw["authority_principal"] == ""
    assert raw["requested_effects"] == raw["runtime_mutations"] == []
    assert "definition" not in raw and "operator_approval_evidence" not in raw

    canonical_before = dict(AUTHORITY_DEFINITIONS)
    result = exact_handoff_result(converted_payload())
    assert result is not None and result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.authority_definitions[CAPABILITY] == candidate()
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None
    assert AUTHORITY_DEFINITIONS == canonical_before and CAPABILITY not in AUTHORITY_DEFINITIONS


def test_approval_template_is_placeholder_only_and_fails_closed() -> None:
    approval = CONTRACT["operator_approval_template"]
    assert approval["schema_version"] == "sentientos.authority_definition_operator_approval:v1"
    assert approval["approval_status"] == "approved"
    assert approval["approved_capability_id"] == CAPABILITY
    assert approval["approved_definition_digest"] == DIGEST
    assert approval["approved_task_name"] == TASK
    assert approval["evidence_id"].startswith("<operator-supplied")
    assert approval["operator_identity_label"].startswith("<operator-supplied")
    assert approval["evidence_digest"].startswith("<computed only")
    result = register_authority_definition(converted_payload(valid_approval=False))
    assert result.status == "authority_definition_registration_blocked"
    assert "authority_definition_operator_approval_digest_invalid" in result.blocker_codes


@pytest.mark.parametrize("mutation,code", [
    (lambda p: p["operator_approval"].update(schema_version="wrong:v1"),
     "authority_definition_operator_approval_binding_mismatch"),
    (lambda p: p["operator_approval"].update(approved_definition_digest="0" * 64),
     "authority_definition_operator_approval_binding_mismatch"),
    (lambda p: p["operator_approval"].update(approved_task_name="wrong-task"),
     "authority_definition_operator_approval_binding_mismatch"),
    (lambda p: p.pop("task_classification"),
     "authority_definition_registration_classification_required"),
    (lambda p: p.update(requested_capability_id=CAPABILITY),
     "authority_definition_registration_cannot_request_capability"),
    (lambda p: p.update(authority_principal="controller"),
     "authority_definition_registration_cannot_request_capability"),
    (lambda p: p.update(requested_effects=("effect",)),
     "authority_definition_registration_cannot_request_capability"),
    (lambda p: p.update(runtime_mutations=("bundle",)),
     "authority_definition_registration_runtime_mutation_forbidden"),
])
def test_incorrect_registration_bindings_fail_closed(mutation: Any, code: str) -> None:
    payload = converted_payload()
    mutation(payload)
    # Recompute only the evidence digest: binding mismatches must remain visible.
    if "operator_approval" in payload:
        payload["operator_approval"]["evidence_digest"] = operator_approval_evidence_digest(
            payload["operator_approval"])
    assert code in register_authority_definition(payload).blocker_codes


def test_broadened_paths_and_conceptual_payload_keys_are_not_the_frozen_handoff() -> None:
    payload = converted_payload()
    payload["changed_paths"] += ("sentientos/production_chat_resource_provisioning.py",)
    assert exact_handoff_result(payload) is None
    for wrong_key in ("definition", "operator_approval_evidence"):
        malformed = converted_payload()
        proper = "definitions" if wrong_key == "definition" else "operator_approval"
        malformed[wrong_key] = malformed.pop(proper)
        result = register_authority_definition(malformed)
        assert result.status == "authority_definition_registration_blocked"
