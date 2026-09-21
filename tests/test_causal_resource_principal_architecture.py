from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "architecture/causal_resource_principal_architecture.json"
DOC_PATH = ROOT / "docs/architecture/causal_resource_principal_architecture.md"
SCHEMA = "sentientos.causal_resource_principal_architecture:v1"

REQUIRED_KEYS = {
    "schema", "posture", "repository_sha", "decision", "alternatives",
    "principal_identity", "identity_lifecycle", "lineage_rules",
    "propagation_rules", "resource_classes", "allocation_semantics",
    "authority_separation", "feasibility_admission_relationship",
    "durability_semantics", "retry_semantics", "shared_work_policy_boundary",
    "model_role", "security_invariants", "current_repository_crosswalk",
    "implementation_boundaries", "open_questions", "non_goals",
}
REQUIRED_INVARIANTS = {
    "state != authority", "memory != current truth", "proposal != authorization",
    "authorization != execution", "execution != validation", "validation != adoption",
    "capability definition != grant", "grant != operational feasibility",
    "operational feasibility != admission", "admission != execution",
    "resource identity != effect authority", "authority != resource entitlement",
    "resource entitlement != resource consumption",
    "resource need estimate != resource allocation", "resource allocation != enforcement",
    "reservation != consumption", "priority != authority", "urgency != authority",
    "criticality != authority", "deadline != authority",
    "resource scarcity != authorization failure", "budget delegation != budget creation",
    "child creation != entitlement creation", "resource exhaustion != authority escalation",
    "unused allocation != permission", "resource receipt != effect receipt",
}
CROSSWALK_KEYS = {
    "mechanism", "source_paths", "test_paths", "current_principal", "resource_bounded",
    "current_status", "allocation_owner", "consumption_measurement", "durable_state",
    "parent_child_semantics", "cross_service_propagation", "receipt_evidence",
    "current_runtime_composition", "proposed_relationship", "recommendation",
}
RESOURCE_KEYS = {
    "class", "examples", "conservation_mode", "replenishment", "refundability",
    "reclaimability", "reservation_semantics", "measurement_posture",
    "exhaustion_posture", "current_enforcement_feasibility",
}


def contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))


def test_json_parses_with_expected_schema_and_required_sections() -> None:
    value = contract()
    assert value["schema"] == SCHEMA
    assert REQUIRED_KEYS <= value.keys()
    assert DOC_PATH.is_file()


def test_repository_sha_is_exact_full_hex_revision() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", str(contract()["repository_sha"]))


def test_posture_is_explicitly_non_runtime_and_non_authority() -> None:
    posture = contract()["posture"]
    assert posture["kind"] == "non_runtime_non_authority_architecture_design"
    assert posture["implemented"] is False
    assert posture["claims_runtime_change"] is False


def test_crosswalk_source_and_test_evidence_exists_and_rows_are_complete() -> None:
    rows = contract()["current_repository_crosswalk"]
    assert len(rows) >= 10
    for row in rows:
        assert set(row) == CROSSWALK_KEYS
        assert row["current_status"] and row["source_paths"] and row["test_paths"]
        for relative in [*row["source_paths"], *row["test_paths"]]:
            assert (ROOT / relative).is_file(), relative


def test_non_collapse_invariants_are_complete_unique_and_exactly_once() -> None:
    values = contract()["non_collapse_invariants"]
    assert len(values) == len(set(values))
    assert set(values) == REQUIRED_INVARIANTS


def test_principal_is_thin_identity_without_authority_or_universal_resources() -> None:
    principal = contract()["principal_identity"]
    required = set(principal["required_fields"])
    assert not required & {"capability", "grant", "admission", "quota", "amount", "resource_limits"}
    assert principal["carries_effect_authority"] is False
    assert principal["carries_resource_entitlement"] is False
    assert principal["monolithic_resource_envelope"] is False
    assert principal["existing_identity_assessment"]["choice"] == "C"


def test_resource_allocation_and_consumption_are_separate_records() -> None:
    value = contract()
    names = {record["name"] for record in value["conceptual_records"]}
    assert names == {"CausalResourcePrincipal", "ResourceAllocation", "ResourceConsumptionReceipt"}
    assert value["allocation_semantics"]["identity_separate_from_allocation"] is True
    assert value["allocation_semantics"]["universal_amount_law"] is False


def test_each_resource_class_owns_semantics_and_modes_are_not_universal() -> None:
    classes = contract()["resource_classes"]
    assert {row["class"] for row in classes} == {
        "consumable", "replenishing_rate", "capacity", "reservation", "temporal",
        "nonfungible", "environmental", "logical_epistemic",
    }
    assert all(set(row) == RESOURCE_KEYS for row in classes)
    assert len({row["conservation_mode"] for row in classes}) > 1
    assert all("conservation" not in row or row["conservation_mode"] for row in classes)


def test_resource_exhaustion_and_admission_never_expand_authority() -> None:
    separation = contract()["authority_separation"]
    assert separation["resource_exhaustion_cannot_expand_authority"] is True
    assert separation["admission_cannot_mint_allocation"] is True
    assert separation["principal_possession_grants"] == []


def test_model_proposals_cannot_allocate() -> None:
    role = contract()["model_role"]
    assert role["proposal_can_mint_allocation"] is False
    assert role["model_claims_with_authority"] == []
    assert "allocates" in role["deterministic_machinery"]


def test_detached_work_requires_explicit_independent_sponsorship() -> None:
    lineage = contract()["lineage_rules"]
    assert "explicit independent-sponsorship transition" in lineage["detached_work"]
    assert "fresh verified sponsor evidence" in lineage["independent_sponsorship"]


def test_async_propagation_rejects_caller_authored_metadata_as_proof() -> None:
    value = contract()
    insufficient = set(value["propagation_trust"]["solely_insufficient"])
    assert {"caller-authored dictionaries", "tracing baggage", "correlation_id", "work_item_id"} <= insufficient
    async_rule = next(row for row in value["propagation_rules"] if row["surface"] == "asynchronous tasks and queues")
    assert "sealed principal evidence" in async_rule["rule"]


def test_retry_attempts_preserve_history() -> None:
    retry = contract()["retry_semantics"]
    assert retry["history_reset_forbidden"] is True
    assert "same principal" in retry["stable_identity"]
    assert "prior attempted/measured consumption remains" in retry["charging"]


def test_shared_work_leaves_cost_policy_to_resource_subsystem() -> None:
    shared = contract()["shared_work_policy_boundary"]
    assert shared["cost_allocation"] == "owned by each resource-specific subsystem"
    assert shared["universal_policy"] is False
    assert "No current precise" in shared["gpu_precision_claim"]


def test_contract_claims_no_runtime_implementation() -> None:
    value = contract()
    assert value["posture"]["implemented"] is False
    assert value["feasibility_admission_relationship"]["runtime_admission_change_in_this_task"] is False
    assert "runtime principal class" in value["non_goals"]
    assert "resource ledger" in value["non_goals"]


def test_decision_and_recommendation_vocabularies_are_closed() -> None:
    value = contract()
    assert value["decision"]["status"] in {"adopt_design", "reject_design"}
    assert {row["decision"] for row in value["alternatives"]} <= {"adopt", "reject"}
    assert {row["recommendation"] for row in value["current_repository_crosswalk"]} <= {
        "keep_separate", "adapt", "retire", "unknown"
    }


def test_forbidden_current_state_claims_are_explicitly_rejected() -> None:
    forbidden = set(contract()["implementation_boundaries"]["forbidden_current_claims"])
    assert {
        "causal resource principal is implemented",
        "resource ledgers exist",
        "runtime admission allocates resources",
        "work_item_id is trusted entitlement",
        "host governor enforces scheduling",
        "external provider billing is accounted",
        "GPU use is precisely task-accounted",
    } == forbidden


def test_security_threats_are_unique_and_have_enforcement_points() -> None:
    rows = contract()["security_invariants"]
    threats = [row["threat"] for row in rows]
    assert len(threats) == len(set(threats)) == 16
    assert all(row["invariant_or_future_enforcement"] for row in rows)


def test_all_nineteen_acceptance_questions_have_concrete_answers() -> None:
    rows = contract()["acceptance_decisions"]
    assert len(rows) == 19
    assert all(row["question"] and row["answer"] for row in rows)
    assert rows[-1]["question"] == "next_runtime_task"
