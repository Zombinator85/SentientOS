from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    TaskAuthorityDefinition,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)
from sentientos.production_chat_resource_provisioning_actuator import (
    REQUEST_SCHEMA,
    load_provisioning_request,
    prepare_provisioning_intent,
)
from tests.test_production_chat_resource_provisioning_actuator import packet

pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "architecture/production_chat_resource_provisioning_request_publication_contract.json"
DOC = ROOT / "docs/architecture/production_chat_resource_provisioning_request_publication_contract.md"
CONTRACT: dict[str, Any] = json.loads(PATH.read_text(encoding="utf-8"))
CAPABILITY = "production_chat_resource_provisioning_request_publish"
DIGEST = "349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5"
TASK = "register-production-chat-resource-provisioning-request-publish-authority-definition"
EXPECTED_PATHS = [
    "sentientos/codex_task_authority_admission.py",
    "tests/test_authority_definition_registration.py",
    "docs/architecture/production_chat_resource_provisioning_request_publication_contract.md",
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


def converted_payload() -> dict[str, Any]:
    raw = CONTRACT["future_registration_task"]["register_authority_definition_payload"]
    approval = dict(raw["operator_approval"])
    approval.update(evidence_id="test-only-request-publication-definition-approval",
                    operator_identity_label="operator:test-fixture-only")
    approval["evidence_digest"] = operator_approval_evidence_digest(approval)
    return {**raw, "definitions": (definition_from_json(raw["definitions"][0]),),
            "operator_approval": approval,
            "requested_effects": tuple(raw["requested_effects"]),
            "runtime_mutations": tuple(raw["runtime_mutations"]),
            "changed_paths": tuple(raw["changed_paths"])}


def frozen_handoff(payload: dict[str, Any]) -> Any:
    if list(payload.get("changed_paths", ())) != EXPECTED_PATHS:
        return None
    return register_authority_definition(payload, authority_definitions=dict(AUTHORITY_DEFINITIONS))


def test_actuator_schema_embedding_and_digest_contract_are_exact(tmp_path: Path) -> None:
    compatibility = CONTRACT["actuator_compatibility"]
    assert CONTRACT["schema"] == "sentientos.production_chat_resource_provisioning_request_publication_contract:v1"
    assert compatibility["request_schema"] == REQUEST_SCHEMA
    assert compatibility["request_fields"] == [
        "schema_version", "installation_identity", "resource_provisioning_id",
        "principal_artifact", "provenance_artifact", "trusted_issuer_catalog_artifact",
        "principal_revocation_registry_artifact", "resource_policy_artifact",
        "requested_bounds", "requested_not_before", "requested_not_after", "request_digest",
    ]
    assert compatibility["artifact_fields"] == ["encoding", "sha256", "data"]
    assert compatibility["artifact_encoding"] == "base64url"
    assert compatibility["base64url_padding"] is False
    assert compatibility["request_digest"]["canonical_json"] == {
        "encoding": "UTF-8", "sort_keys": True, "separators": [",", ":"],
        "ensure_ascii": True, "finite_only": True,
    }
    raw, _, _ = packet(tmp_path, provisioning_id="publication-contract")
    loaded = load_provisioning_request(raw)
    assert loaded._packet == raw
    assert loaded.request_digest == json.loads(raw)["request_digest"]


def test_contract_packet_prepares_deterministic_intent_without_state_access(tmp_path: Path) -> None:
    raw, handle, _ = packet(tmp_path, provisioning_id="publication-contract")
    before = sorted(path.relative_to(handle.root) for path in handle.root.rglob("*"))
    first = prepare_provisioning_intent(raw)
    second = prepare_provisioning_intent(raw)
    assert first == second
    assert first.request_digest == json.loads(raw)["request_digest"]
    assert sorted(path.relative_to(handle.root) for path in handle.root.rglob("*")) == before
    assert CONTRACT["status"] == {
        "runtime_publisher": "not implemented", "runtime_consumer": "not implemented",
        "authority_definition": "candidate only, not registered", "request_writes": 0,
        "installation_state_mutations": 0,
    }


def test_fixed_custody_create_only_receipt_last_and_partial_failure_are_frozen() -> None:
    custody, create = CONTRACT["custody"], CONTRACT["create_only"]
    assert custody["publication_root"] == "local-model/resource-provisioning-requests/<resource_provisioning_id>/"
    assert custody["request_object"] == "request.json"
    assert custody["publication_marker"] == "publication-receipt.json"
    assert custody["lock"] == "local-model/resource-provisioning-request-locks/<resource_provisioning_id>.lock"
    assert create["maximum_generations_per_installation_and_id"] == 1
    assert create["any_existing_object_burns_id"] is True
    assert create["process_local_mutex_sufficient"] is False
    assert CONTRACT["publication_order"][-2:] == [
        "construct publication receipt", "durably create publication-receipt.json LAST"]
    assert CONTRACT["partial_failure"] == {
        "filesystem_wide_atomicity_claimed": False,
        "request_without_receipt": "unpublished production custody",
        "same_id_automatic_retry": False, "automatic_cleanup": False,
        "overwrite_retry": False, "future_recovery": "separately governed",
    }


def test_trusted_exact_byte_verification_and_one_instant_are_frozen() -> None:
    assert len(CONTRACT["trusted_inputs"]) == 11
    assert CONTRACT["exact_byte_law"]["publication_preserves_bytes"] is True
    assert CONTRACT["verification"]["authentication_chain"][-1] == "AuthenticatedRootPrincipalEvidence"
    assert CONTRACT["verification"]["currentness_chain"][-1] == "CurrentAuthenticatedRootPrincipalEvidence"
    assert CONTRACT["verification"]["caller_authored_evidence"] is False
    assert CONTRACT["verification"]["private_signing_authority"] is False
    assert CONTRACT["verification"]["root_minting"] is False
    assert CONTRACT["publication_time"]["count"] == 1
    assert CONTRACT["publication_time"]["uses"] == [
        "principal validity", "provenance authentication", "issuer trust validity",
        "principal currentness", "resource policy currentness",
    ]


def test_receipt_and_read_only_consumer_bind_every_required_identity() -> None:
    receipt = CONTRACT["publication_receipt"]
    assert receipt["schema"] == "sentientos.production_chat_resource_provisioning_request_publication_receipt:v1"
    assert len(receipt["fields"]) == 21
    assert receipt["fields"][-2:] == ["authority_definition_digest", "receipt_digest"]
    assert receipt["authority_definition_digest"] == DIGEST
    assert receipt["receipt_digest"]["excludes"] == ["receipt_digest"]
    assert CONTRACT["published_request_consumer"]["requires"] == ["request.json", "publication-receipt.json"]
    assert CONTRACT["published_request_consumer"]["implemented"] is False


def test_candidate_definition_digest_exact_surface_and_catalog_absence() -> None:
    definition = candidate()
    assert definition.capability_id == CAPABILITY
    assert definition.subsystem_kinds == frozenset({"causal_resource_principal_architecture"})
    assert definition.principal_kinds == frozenset({
        "deterministic_production_chat_resource_provisioning_request_publisher"})
    assert len(definition.required_effects) == 5
    assert authority_definition_digest(definition) == CONTRACT["candidate_definition_digest"] == DIGEST
    assert CAPABILITY not in AUTHORITY_DEFINITIONS
    assert CONTRACT["existing_bundle_authority"] == {
        "capability_id": "production_chat_resource_provisioning_bundle_create",
        "definition_digest": "132f93c32f5490877a4748c0054dfb66aacb9f2a94ce560d69a0e65337c800f5",
        "unchanged": True, "distinct": True,
    }
    text = DOC.read_text(encoding="utf-8")
    assert DIGEST in text and definition.purpose in text


def test_registrar_native_handoff_registers_only_in_copy_without_authority() -> None:
    raw = CONTRACT["future_registration_task"]["register_authority_definition_payload"]
    assert list(raw) == ["task_classification", "task_name", "definitions", "operator_approval",
                         "requested_capability_id", "authority_principal", "requested_effects",
                         "runtime_mutations", "changed_paths"]
    assert raw["task_classification"] == AUTHORITY_DEFINITION_REGISTRATION
    assert raw["task_name"] == TASK and raw["changed_paths"] == EXPECTED_PATHS
    assert raw["requested_capability_id"] == raw["authority_principal"] == ""
    assert raw["requested_effects"] == raw["runtime_mutations"] == []
    canonical_before = dict(AUTHORITY_DEFINITIONS)
    result = register_authority_definition(converted_payload(),
                                            authority_definitions=dict(AUTHORITY_DEFINITIONS))
    assert result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None
    assert result.authority_definitions[CAPABILITY] == candidate()
    assert AUTHORITY_DEFINITIONS == canonical_before and CAPABILITY not in AUTHORITY_DEFINITIONS


@pytest.mark.parametrize(("mutation", "code"), [
    (lambda p: p["operator_approval"].update(approved_definition_digest="0" * 64),
     "authority_definition_operator_approval_binding_mismatch"),
    (lambda p: p["operator_approval"].update(approved_capability_id="wrong"),
     "authority_definition_operator_approval_binding_mismatch"),
    (lambda p: p["operator_approval"].update(approved_task_name="wrong-task"),
     "authority_definition_operator_approval_binding_mismatch"),
    (lambda p: p.pop("task_classification"),
     "authority_definition_registration_classification_required"),
    (lambda p: p.update(requested_capability_id=CAPABILITY),
     "authority_definition_registration_cannot_request_capability"),
    (lambda p: p.update(authority_principal="publisher"),
     "authority_definition_registration_cannot_request_capability"),
    (lambda p: p.update(requested_effects=("publish",)),
     "authority_definition_registration_cannot_request_capability"),
    (lambda p: p.update(runtime_mutations=("request.json",)),
     "authority_definition_registration_runtime_mutation_forbidden"),
])
def test_incorrect_registration_bindings_fail_closed(
    mutation: Callable[[dict[str, Any]], None], code: str,
) -> None:
    payload = converted_payload()
    mutation(payload)
    payload["operator_approval"]["evidence_digest"] = operator_approval_evidence_digest(
        payload["operator_approval"])
    assert code in register_authority_definition(payload).blocker_codes


def test_broadened_registration_paths_are_not_the_frozen_handoff() -> None:
    payload = converted_payload()
    payload["changed_paths"] += ("sentientos/production_chat_resource_provisioning_actuator.py",)
    assert frozen_handoff(payload) is None
    assert CONTRACT["registration_posture"] == {
        "definition_registered": False, "capability_granted": False,
        "runtime_authority": None, "effect_performed": False,
        "runtime_mutation_performed": False,
    }
    assert CONTRACT["selected_next_slice"] == (
        "register the exact production_chat_resource_provisioning_request_publish authority definition")
