from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from sentientos.production_chat_resource_provisioning_request_recovery_review_contract import (
    DENIED_INFERENCES, NON_AUTHORITY_POSTURE, RECOVERY_REVIEW_CONTRACT,
    RECOVERY_REVIEW_CONTRACT_DIGEST, REQUIRED_EVIDENCE_CLASSES, SCHEMA,
    build_production_chat_resource_provisioning_request_recovery_review_contract,
    recovery_review_contract_digest,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "architecture/production_chat_resource_provisioning_request_recovery_review_contract.json"
MODULE = ROOT / "sentientos/production_chat_resource_provisioning_request_recovery_review_contract.py"
PUBLICATION_DOC = ROOT / "docs/architecture/production_chat_resource_provisioning_request_publication_contract.md"
pytestmark = pytest.mark.no_legacy_skip


def _independent_digest(value: dict[str, object]) -> str:
    body = dict(value); body.pop("canonical_contract_digest")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def test_frozen_machine_module_agreement_and_schema() -> None:
    frozen = json.loads(MACHINE.read_text(encoding="utf-8"))
    assert SCHEMA == "sentientos.production_chat_resource_provisioning_request_recovery_review_contract:v1"
    assert frozen == RECOVERY_REVIEW_CONTRACT == build_production_chat_resource_provisioning_request_recovery_review_contract()


def test_deterministic_digest_independently_recomputes() -> None:
    first = build_production_chat_resource_provisioning_request_recovery_review_contract()
    second = build_production_chat_resource_provisioning_request_recovery_review_contract()
    assert first == second
    assert _independent_digest(first) == recovery_review_contract_digest(first) == RECOVERY_REVIEW_CONTRACT_DIGEST


def test_exact_evidence_conjunction_and_bindings() -> None:
    contract = RECOVERY_REVIEW_CONTRACT
    assert tuple(contract["required_evidence_classes"]) == REQUIRED_EVIDENCE_CLASSES
    assert set(contract["evidence_classes"]) == set(REQUIRED_EVIDENCE_CLASSES)
    doctor = contract["evidence_classes"]["bound_bare_request_custody_observation"]
    assert doctor["necessary_but_insufficient"] is True
    assert doctor["claims"] == {"custody_shape": "bare_request", "publication_complete": False,
        "snapshot_is_lock_free": True, "concurrent_publication_excluded": False,
        "terminal_failure_inferred": False}
    identity = contract["evidence_classes"]["pre_effect_publisher_attempt_identity_evidence"]
    closure = contract["evidence_classes"]["exact_publisher_attempt_terminal_closure_evidence"]
    post = contract["evidence_classes"]["post_terminal_same_request_custody_observation"]
    assert identity["created_before"] == "first_durable_publication_mutation"
    assert identity["currently_implemented"] is identity["currently_satisfied"] is False
    assert closure["currently_implemented"] is closure["currently_satisfied"] is False
    assert post["must_occur_after_terminal_closure"] is True
    common = {"installation_identity", "resource_provisioning_id", "request_storage_sha256", "request_digest"}
    assert common <= set(identity["bindings"])
    assert common <= set(closure["same_bindings"])
    assert {"publication_attempt_id", "publisher_authority_definition_digest"} <= set(closure["same_bindings"])
    conjunction = contract["terminal_abandonment_conjunction"]
    assert all(conjunction[key] is True for key in ("all_required_evidence_classes_present",
        "all_evidence_internally_valid", "all_evidence_mutually_bound", "no_contradictory_evidence"))


def test_current_unsatisfiability_and_missing_lifecycle_gaps() -> None:
    current = RECOVERY_REVIEW_CONTRACT["current_state"]
    assert current["terminal_abandonment_classification_available"] is False
    assert current["recovery_authority_available"] is False
    assert current["same_id_reuse_authority_available"] is False
    assert current["blocking_gaps"] == ["publisher_attempt_identity_evidence_missing",
        "publisher_attempt_terminal_closure_evidence_missing",
        "publisher_attempt_lifecycle_provenance_missing"]


def test_denied_time_snapshot_lock_pid_and_unauthenticated_inferences() -> None:
    denied = set(DENIED_INFERENCES)
    assert {"one_bare_request_doctor_report", "multiple_repeated_bare_request_doctor_reports",
        "elapsed_wall_clock_time", "arbitrary_timeout_threshold", "lock_file_existence",
        "lock_file_absence", "pid_absence", "process_list_absence", "caller_assertion",
        "model_output", "log_text_without_authenticated_lifecycle_provenance"} <= denied
    laws = RECOVERY_REVIEW_CONTRACT["emphatic_laws"]
    assert "time_passage_is_not_terminality_evidence" in laws
    assert "lock_pathname_state_is_not_publisher_attempt_lifecycle_evidence" in laws


def test_contradictory_completed_receipt_blocks_classification() -> None:
    contradictions = RECOVERY_REVIEW_CONTRACT["contradictions"]
    assert "valid_completed_publication_receipt" in contradictions
    assert "durable_receipt_creation_completed" in contradictions
    assert RECOVERY_REVIEW_CONTRACT["review_outcomes"] == ["evidence_incomplete",
        "evidence_contradictory", "terminal_abandonment_evidence_complete",
        "completed_publication_observed"]


def test_terminal_classification_grants_no_recovery_authority() -> None:
    separation = RECOVERY_REVIEW_CONTRACT["classification_and_recovery"]
    assert separation["terminal_abandonment_classification_equals_recovery_authorization"] is False
    assert separation["permissions_granted"] == []
    assert {"deletion", "retry", "provisioning_id_reuse", "overwrite", "republication"} <= set(separation["still_forbidden"])
    assert separation["separately_governed_recovery_contract_and_authority_required"] is True


def test_metadata_only_posture_and_runtime_surface_absence() -> None:
    assert NON_AUTHORITY_POSTURE and all(NON_AUTHORITY_POSTURE.values())
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"__future__", "hashlib", "json", "typing"}
    source = MODULE.read_text(encoding="utf-8")
    for forbidden in ("installation_state", "request_publisher", "request_consumer",
                      "actuator", "subprocess", "pathlib", "datetime", "time.time", "open(", "/proc"):
        assert forbidden not in source
    assert RECOVERY_REVIEW_CONTRACT["existing_runtime_schemas_changed"] is False


def test_publication_contract_document_links_downstream_boundary() -> None:
    text = PUBLICATION_DOC.read_text(encoding="utf-8")
    assert "production_chat_resource_provisioning_request_recovery_review_contract.md" in text
    assert "grants no recovery" in text
