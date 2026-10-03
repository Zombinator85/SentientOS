from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from sentientos.codex_task_authority_admission import AUTHORITY_DEFINITIONS, authority_definition_digest
from sentientos.production_chat_resource_provisioning_request_attempt_identity_contract import (
    ATTEMPT_IDENTITY_CONTRACT, ATTEMPT_IDENTITY_CONTRACT_DIGEST, CONTRACT_SCHEMA,
    DENIED_INFERENCES, EVIDENCE_DIGEST_EXCLUDED_FIELDS, FUTURE_EVIDENCE_FIELDS,
    FUTURE_EVIDENCE_SCHEMA, NON_AUTHORITY_POSTURE, PROVENANCE_REQUIREMENTS,
    PUBLISHER_AUTHORITY_DEFINITION_DIGEST, PUBLISHER_CAPABILITY_ID, PUBLISHER_PRINCIPAL,
    attempt_identity_contract_digest,
    build_production_chat_resource_provisioning_request_attempt_identity_contract,
)
from sentientos.production_chat_resource_provisioning_request_recovery_review_contract import RECOVERY_REVIEW_CONTRACT

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "architecture/production_chat_resource_provisioning_request_attempt_identity_contract.json"
RECOVERY_MACHINE = ROOT / "architecture/production_chat_resource_provisioning_request_recovery_review_contract.json"
MODULE = ROOT / "sentientos/production_chat_resource_provisioning_request_attempt_identity_contract.py"
RECOVERY_DOC = ROOT / "docs/architecture/production_chat_resource_provisioning_request_recovery_review_contract.md"
pytestmark = pytest.mark.no_legacy_skip
EXPECTED_RECOVERY_RAW_SHA256 = "3f85a15db694dff01c10f3716ea6d05c9a0a96654fa802dcfbc41927a7ccb422"


def _independent_digest(contract: dict[str, object]) -> str:
    body = dict(contract); body.pop("canonical_contract_digest")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def test_module_machine_agreement_exact_schemas_and_deterministic_digest() -> None:
    frozen = json.loads(MACHINE.read_text(encoding="utf-8"))
    assert CONTRACT_SCHEMA == "sentientos.production_chat_resource_provisioning_request_publisher_attempt_identity_contract:v1"
    assert FUTURE_EVIDENCE_SCHEMA == "sentientos.production_chat_resource_provisioning_request_publisher_attempt_identity:v1"
    assert frozen == ATTEMPT_IDENTITY_CONTRACT == build_production_chat_resource_provisioning_request_attempt_identity_contract()
    assert build_production_chat_resource_provisioning_request_attempt_identity_contract() == frozen
    assert _independent_digest(frozen) == attempt_identity_contract_digest(frozen) == ATTEMPT_IDENTITY_CONTRACT_DIGEST


def test_exact_closed_evidence_schema_and_canonical_digest_law() -> None:
    expected = ("schema_version", "publication_attempt_id", "installation_identity", "resource_provisioning_id",
        "request_digest", "request_storage_sha256", "request_storage_bytes", "intent_digest",
        "publisher_capability_id", "publisher_principal", "publisher_authority_definition_digest",
        "attempt_started_at", "attempt_identity_contract_digest", "synthetic_test_evidence", "identity_digest")
    assert FUTURE_EVIDENCE_FIELDS == expected
    assert ATTEMPT_IDENTITY_CONTRACT["future_evidence_fields"] == list(expected)
    assert ATTEMPT_IDENTITY_CONTRACT["closed_future_evidence_schema"] is True
    law = ATTEMPT_IDENTITY_CONTRACT["canonical_evidence_law"]
    assert law == {"hash_algorithm": "sha256", "encoding": "utf-8", "sort_keys": True,
        "separators": [",", ":"], "ensure_ascii": True, "finite_json_only": True,
        "digest_fields": list(expected[:-1]), "excluded_fields": ["identity_digest"],
        "output": "lowercase_64_hex", "artifact_bytes_must_be_exact_canonical_json": True,
        "semantic_rewrites_are_not_same_durable_bytes": True}
    assert EVIDENCE_DIGEST_EXCLUDED_FIELDS == ("identity_digest",)


def test_exact_request_intent_and_registered_publisher_definition_binding() -> None:
    binding = ATTEMPT_IDENTITY_CONTRACT["publisher_definition_binding"]
    assert PUBLISHER_CAPABILITY_ID == binding["capability_id"] == "production_chat_resource_provisioning_request_publish"
    assert PUBLISHER_PRINCIPAL == binding["principal"] == "deterministic_production_chat_resource_provisioning_request_publisher"
    assert authority_definition_digest(AUTHORITY_DEFINITIONS[PUBLISHER_CAPABILITY_ID]) == PUBLISHER_AUTHORITY_DEFINITION_DIGEST == binding["authority_definition_digest"]
    required = set(ATTEMPT_IDENTITY_CONTRACT["request_binding_law"]["constructed_only_after_publisher_has_deterministically_constructed_and_validated"])
    assert {"exact_actuator_compatible_request_bytes", "request_digest", "request_storage_sha256", "request_storage_bytes", "intent_digest"} == required


def test_one_invocation_attempt_id_law_rejects_aliases_placeholders_and_retrospection() -> None:
    law = ATTEMPT_IDENTITY_CONTRACT["attempt_id_law"]
    assert law["identifies_exactly_one_publisher_invocation"] is law["immutable"] is law["nonempty"] is True
    assert set(("*", "any", "current", "default", "latest", "placeholder", "sample", "test", "wildcard")) == set(law["forbidden_placeholder_values"])
    assert law["wildcard_or_metacharacter_forms_forbidden"] is True
    assert law["must_not_equal_or_alias_resource_provisioning_id"] is True
    assert law["derivation_solely_from_installation_provisioning_and_request_digest_forbidden"] is True
    assert law["retrospective_synthesis_after_observing_failure_forbidden"] is True
    assert law["generated_or_established_by_future_governed_lifecycle_evidence_boundary"] is True
    assert law["unauthenticated_caller_claim_sufficient"] is False


def test_pre_effect_ordering_and_separate_fixed_custody_are_mandatory() -> None:
    ordering = ATTEMPT_IDENTITY_CONTRACT["pre_effect_ordering_law"]
    assert ordering["complete_provenance_verifiable_identity_evidence_required_before_first_publication_custody_mutation"] is True
    assert ordering["attempt_evidence_mutation_precedes_publication_custody_mutation"] is True
    assert ordering["timestamp_comparison_sufficient"] is False
    custody = ATTEMPT_IDENTITY_CONTRACT["future_fixed_custody_law"]
    assert custody["path_template"] == "local-model/resource-provisioning-request-attempts/<publication_attempt_id>/identity.json"
    assert custody["distinct_from_request_publication_custody"] is True
    assert custody["create_only"] is custody["immutable"] is True
    assert custody["overwrite"] is custody["repair"] is custody["automatic_retry"] is False
    assert custody["writer_implemented"] is False


def test_independent_provenance_and_content_digest_insufficiency() -> None:
    provenance = ATTEMPT_IDENTITY_CONTRACT["independently_verifiable_provenance"]
    assert provenance["artifact_self_attestation_sufficient"] is False
    assert provenance["caller_authored_provenance_sufficient"] is False
    assert provenance["synthetic_test_evidence_satisfies_production"] is False
    assert provenance["exact_identity_digest_binding_required"] is True
    assert provenance["pre_effect_ordering_proof_required"] is True
    assert provenance["correct_content_is_sufficient_provenance"] is False
    assert provenance["digest_proves_creator_or_lifecycle_order"] is False
    denied = set(DENIED_INFERENCES)
    assert {"matching_publisher_principal_string", "matching_capability_string",
        "matching_authority_definition_digest_literal", "valid_identity_digest_over_caller_authored_json",
        "synthetic_test_evidence_in_production"} <= denied
    assert PROVENANCE_REQUIREMENTS.items() <= provenance.items()


def test_future_producer_verifier_authority_absent_and_currently_unsatisfied() -> None:
    requirements = ATTEMPT_IDENTITY_CONTRACT["future_provenance_boundary_requirements"]
    assert requirements
    assert all(item == {"future_only": True, "currently_implemented": False,
        "currently_satisfied": False} for item in requirements.values())
    assert set(ATTEMPT_IDENTITY_CONTRACT["future_authority_identifiers"].values()) == {None}
    current = ATTEMPT_IDENTITY_CONTRACT["current_state"]
    assert current["future_evidence_schema_defined"] is True
    assert all(value is False for key, value in current.items() if key != "future_evidence_schema_defined")
    relationship = ATTEMPT_IDENTITY_CONTRACT["publisher_authority_relationship"]
    assert relationship["publisher_request_publication_authority_equals_publisher_attempt_lifecycle_evidence_authority"] is False
    assert relationship["existing_five_effect_surface_reinterpreted_or_widened"] is relationship["publisher_definition_modified"] is False


def test_covers_recovery_identity_bindings_and_frozen_recovery_machine_is_unchanged() -> None:
    existing = RECOVERY_REVIEW_CONTRACT["evidence_classes"]["pre_effect_publisher_attempt_identity_evidence"]
    covered = ATTEMPT_IDENTITY_CONTRACT["recovery_review_relationship"]["covered_bindings"]
    assert set(existing["bindings"]) <= set(covered)
    assert ATTEMPT_IDENTITY_CONTRACT["recovery_review_relationship"]["remaining_open_gap"] == "publisher_attempt_identity_evidence_missing"
    raw = RECOVERY_MACHINE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_RECOVERY_RAW_SHA256
    assert json.loads(raw) == RECOVERY_REVIEW_CONTRACT
    text = RECOVERY_DOC.read_text(encoding="utf-8")
    assert "production_chat_resource_provisioning_request_attempt_identity_contract.md" in text
    assert "publisher_attempt_identity_evidence_missing" in text


def test_metadata_only_no_runtime_or_evidence_emission_surface() -> None:
    assert NON_AUTHORITY_POSTURE and all(NON_AUTHORITY_POSTURE.values())
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"__future__", "hashlib", "json", "typing"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {"open", "publish", "emit", "verify", "time", "datetime", "uuid4", "urandom"}
    source = MODULE.read_text(encoding="utf-8")
    for forbidden in ("subprocess", "requests.", "socket.", "from sentientos.installation_state", "os.getpid", "random."):
        assert forbidden not in source
