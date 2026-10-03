from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, AUTHORITY_DEFINITION_REGISTRATION, TaskAuthorityDefinition,
    authority_admission_blockers, authority_definition_digest, operator_approval_evidence_digest,
    register_authority_definition,
)
from sentientos.production_chat_resource_provisioning_request_attempt_identity_authority_contract import (
    APPROVAL_REQUIREMENTS, CANDIDATE_CAPABILITY_ID, CANDIDATE_DEFINITION,
    CANDIDATE_DEFINITION_DIGEST, CANDIDATE_PRINCIPAL, CANDIDATE_PURPOSE,
    CANDIDATE_SUBSYSTEM, CONTRACT_SCHEMA, EFFECTS, FORBIDDEN_GOAL_PHRASES,
    REQUIRED_GOAL_PHRASES, definition_as_json,
)
from sentientos.production_chat_resource_provisioning_request_attempt_identity_contract import ATTEMPT_IDENTITY_CONTRACT_DIGEST

pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "architecture/production_chat_resource_provisioning_request_attempt_identity_authority_contract.json"
FROZEN_IDENTITY = ROOT / "architecture/production_chat_resource_provisioning_request_attempt_identity_contract.json"
DOC = ROOT / "docs/architecture/production_chat_resource_provisioning_request_attempt_identity_authority_contract.md"
MODULE = ROOT / "sentientos/production_chat_resource_provisioning_request_attempt_identity_authority_contract.py"
CAPABILITY_REGISTRY = ROOT / "sentientos/capability_registry.py"
CONTRACT: dict[str, Any] = json.loads(MACHINE.read_text(encoding="utf-8"))
PUBLISHER = "production_chat_resource_provisioning_request_publish"
PUBLISHER_DIGEST = "349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5"
IDENTITY_RAW_SHA256 = "a14025ce50500a89a3ed4e61a1789072128acdc06b5347a2e282b278d74212f5"
TASK = "register-production-chat-resource-provisioning-request-attempt-identity-evidence-create-authority-definition"
PATHS = ["sentientos/codex_task_authority_admission.py", "tests/test_authority_definition_registration.py", "docs/architecture/production_chat_resource_provisioning_request_attempt_identity_authority_contract.md"]
def _affirmative_goal(phrases: tuple[str, ...] = REQUIRED_GOAL_PHRASES) -> str:
    # Native required-phrase matching permits whitespace while the forbidden matcher is literal.
    # Preserve the affirmative no-recovery requirement without affirmatively requesting that scope.
    return "; ".join(phrases).replace("no request publication or recovery authority",
        "no request publication or recovery\nauthority") + "."


AFFIRMATIVE_GOAL = _affirmative_goal()


def reconstruct(item: dict[str, Any]) -> TaskAuthorityDefinition:
    return TaskAuthorityDefinition(item["capability_id"], frozenset(item["subsystem_kinds"]),
        frozenset(item["principal_kinds"]), frozenset(item["required_effects"]),
        tuple(item["forbidden_goal_phrases"]), tuple(item["required_goal_phrases"]),
        tuple(item["approval_requirements"]), item["purpose"])


def test_candidate_reconstruction_digest_and_exact_contract_surface() -> None:
    assert CONTRACT_SCHEMA == CONTRACT["schema"] == "sentientos.production_chat_resource_provisioning_request_attempt_identity_authority_contract:v1"
    assert (CANDIDATE_CAPABILITY_ID, CANDIDATE_PRINCIPAL, CANDIDATE_SUBSYSTEM) == (
        CONTRACT["candidate_capability"], CONTRACT["candidate_principal"], CONTRACT["candidate_subsystem"])
    assert CONTRACT["exact_effect_surface"] == list(EFFECTS) and len(EFFECTS) == len(set(EFFECTS)) == 4
    assert CONTRACT["required_goal_phrases"] == list(REQUIRED_GOAL_PHRASES)
    assert CONTRACT["forbidden_goal_phrases"] == list(FORBIDDEN_GOAL_PHRASES)
    assert CONTRACT["approval_requirements"] == list(APPROVAL_REQUIREMENTS)
    rebuilt = reconstruct(CONTRACT["candidate_task_authority_definition"])
    assert isinstance(CANDIDATE_DEFINITION, TaskAuthorityDefinition) and rebuilt == CANDIDATE_DEFINITION
    assert authority_definition_digest(rebuilt) == CANDIDATE_DEFINITION_DIGEST == CONTRACT["candidate_definition_digest"]
    text = DOC.read_text(encoding="utf-8")
    assert CANDIDATE_DEFINITION_DIGEST in text and CANDIDATE_PURPOSE == CONTRACT["candidate_purpose"]


def test_candidate_absent_and_existing_publisher_definition_unchanged() -> None:
    assert CANDIDATE_CAPABILITY_ID not in AUTHORITY_DEFINITIONS
    publisher = AUTHORITY_DEFINITIONS[PUBLISHER]
    assert authority_definition_digest(publisher) == PUBLISHER_DIGEST
    assert publisher.principal_kinds == frozenset({"deterministic_production_chat_resource_provisioning_request_publisher"})
    assert publisher.required_effects == frozenset({"create_only_installation_state_resource_provisioning_request", "finalize_production_resource_provisioning_request", "read_exact_preexisting_causal_resource_principal_artifacts", "read_exact_resource_trust_currentness_artifacts", "read_governed_local_model_resource_policy"})
    binding = CONTRACT["current_publisher_definition_binding"]
    assert binding["effect_count"] == 5 and binding["unchanged"] is True
    assert set(CANDIDATE_DEFINITION.required_effects).isdisjoint(publisher.required_effects)
    assert binding["candidate_inherits_publisher_effects"] is binding["publisher_inherits_candidate_effects"] is False


def test_attempt_identity_binding_custody_exclusions_and_verifier_separation() -> None:
    assert CONTRACT["frozen_attempt_identity_contract_binding"]["contract_digest"] == ATTEMPT_IDENTITY_CONTRACT_DIGEST
    custody = CONTRACT["fixed_custody_boundary"]
    assert custody["only_destination"] == "local-model/resource-provisioning-request-attempts/<publication_attempt_id>/identity.json"
    assert custody["excluded_mutation_paths"] == ["local-model/resource-provisioning-requests/<resource_provisioning_id>/request.json", "local-model/resource-provisioning-requests/<resource_provisioning_id>/publication-receipt.json"]
    assert custody["terminal_closure_custody"] is False
    separation = CONTRACT["producer_verifier_separation"]
    assert separation["inequality"] == "attempt_identity_evidence_producer != independent_attempt_identity_provenance_verifier"
    assert separation["independent_verifier_still_required"] is True and separation["self_verification_sufficient"] is False
    ordering = CONTRACT["lifecycle_ordering_boundary"]
    assert ordering["future_producer_must_complete_evidence_before_first_durable_publication_custody_mutation"] is True
    assert ordering["definition_eligibility_proves_ordering"] is ordering["authority_admission_proves_ordering"] is ordering["artifact_creation_alone_proves_ordering"] is False


def test_exact_registrar_handoff_is_inert_and_template_only() -> None:
    future = CONTRACT["future_registrar_handoff"]
    raw = future["register_authority_definition_payload"]
    assert list(raw) == ["task_classification", "task_name", "definitions", "operator_approval", "requested_capability_id", "authority_principal", "requested_effects", "runtime_mutations", "changed_paths"]
    assert raw["task_classification"] == AUTHORITY_DEFINITION_REGISTRATION and raw["task_name"] == TASK
    assert reconstruct(raw["definitions"][0]) == CANDIDATE_DEFINITION
    assert raw["requested_capability_id"] == raw["authority_principal"] == ""
    assert raw["requested_effects"] == raw["runtime_mutations"] == [] and raw["changed_paths"] == PATHS
    approval = raw["operator_approval"]
    assert approval == future["operator_approval_template"] and future["operator_fields_supplied"] is False
    assert approval["evidence_id"].startswith("<operator-supplied") and approval["operator_identity_label"].startswith("<operator-supplied")
    assert approval["evidence_digest"].startswith("<computed only")


def _registrar_payload() -> dict[str, Any]:
    raw = CONTRACT["future_registrar_handoff"]["register_authority_definition_payload"]
    approval = dict(raw["operator_approval"])
    approval.update(evidence_id="test-only-attempt-identity-authority-approval", operator_identity_label="operator:test-fixture-only")
    approval["evidence_digest"] = operator_approval_evidence_digest(approval)
    return {**raw, "definitions": (CANDIDATE_DEFINITION,), "operator_approval": approval,
            "requested_effects": (), "runtime_mutations": (), "changed_paths": tuple(raw["changed_paths"])}


def test_isolated_registration_is_compatible_and_grants_nothing() -> None:
    canonical_before = dict(AUTHORITY_DEFINITIONS)
    result = register_authority_definition(_registrar_payload(), authority_definitions=dict(canonical_before))
    assert result.status == "authority_definition_registered" and result.definition_registered is True
    assert result.authority_definitions[CANDIDATE_CAPABILITY_ID] == CANDIDATE_DEFINITION
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None
    assert dict(AUTHORITY_DEFINITIONS) == canonical_before and CANDIDATE_CAPABILITY_ID not in AUTHORITY_DEFINITIONS


def blockers(*, effects: tuple[str, ...] = EFFECTS, principal: str = CANDIDATE_PRINCIPAL,
             subsystem: str = CANDIDATE_SUBSYSTEM, goal: str = AFFIRMATIVE_GOAL,
             catalog: dict[str, TaskAuthorityDefinition] | None = None) -> tuple[str, ...]:
    return authority_admission_blockers(capability_id=CANDIDATE_CAPABILITY_ID, subsystem_kind=subsystem,
        principal_kind=principal, requested_effects=effects, task_goal=goal,
        authority_definitions=catalog)


def test_isolated_exact_admission_and_canonical_absence() -> None:
    isolated = {**AUTHORITY_DEFINITIONS, CANDIDATE_CAPABILITY_ID: CANDIDATE_DEFINITION}
    assert blockers(catalog=isolated) == ()
    assert blockers() == ("unregistered_authority_capability",)


def test_broadened_or_inexact_effect_admission_fails_closed() -> None:
    isolated = {**AUTHORITY_DEFINITIONS, CANDIDATE_CAPABILITY_ID: CANDIDATE_DEFINITION}
    for effects in (EFFECTS[:-1], EFFECTS + ("extra_effect",), EFFECTS + (EFFECTS[0],)):
        assert "authority_effect_surface_not_exact" in blockers(effects=effects, catalog=isolated)


def test_wrong_principal_and_subsystem_fail_closed() -> None:
    isolated = {**AUTHORITY_DEFINITIONS, CANDIDATE_CAPABILITY_ID: CANDIDATE_DEFINITION}
    assert "authority_principal_not_admitted" in blockers(principal="wrong_principal", catalog=isolated)
    assert "authority_subsystem_not_admitted" in blockers(subsystem="wrong_subsystem", catalog=isolated)


def test_each_missing_required_phrase_fails_closed() -> None:
    isolated = {**AUTHORITY_DEFINITIONS, CANDIDATE_CAPABILITY_ID: CANDIDATE_DEFINITION}
    for missing in REQUIRED_GOAL_PHRASES:
        goal = _affirmative_goal(tuple(phrase for phrase in REQUIRED_GOAL_PHRASES if phrase != missing))
        assert "authority_goal_missing_required_precondition" in blockers(goal=goal, catalog=isolated)


def test_every_forbidden_phrase_fails_closed() -> None:
    isolated = {**AUTHORITY_DEFINITIONS, CANDIDATE_CAPABILITY_ID: CANDIDATE_DEFINITION}
    for forbidden in FORBIDDEN_GOAL_PHRASES:
        assert "authority_goal_requests_forbidden_scope" in blockers(goal=f"{AFFIRMATIVE_GOAL} Also {forbidden}.", catalog=isolated)


def test_frozen_attempt_identity_machine_artifact_is_byte_identical() -> None:
    assert hashlib.sha256(FROZEN_IDENTITY.read_bytes()).hexdigest() == IDENTITY_RAW_SHA256


def test_metadata_only_module_performs_no_runtime_or_evidence_emission() -> None:
    posture = CONTRACT["registration_posture"]
    assert posture == {"candidate_definition_exists": True, "candidate_definition_digest_frozen": True,
        "candidate_present_in_canonical_authority_definitions": False, "operator_approval_supplied": False,
        "definition_registered": False, "capability_granted": False, "runtime_authority": None,
        "effect_performed": False, "runtime_mutation_performed": False}
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"__future__", "typing", "sentientos.codex_task_authority_admission"}
    source = MODULE.read_text(encoding="utf-8")
    for forbidden in ("register_authority_definition(", "AUTHORITY_DEFINITIONS[", "open(", "identity.json\", \"w", "subprocess", "socket", "requests.", "uuid", "random", "datetime"):
        assert forbidden not in source
    assert CAPABILITY_REGISTRY.exists() is False or CANDIDATE_CAPABILITY_ID not in CAPABILITY_REGISTRY.read_text(encoding="utf-8")
