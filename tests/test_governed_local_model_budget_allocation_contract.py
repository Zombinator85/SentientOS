from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    TaskAuthorityDefinition,
    authority_definition_digest,
)
from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "architecture/governed_local_model_budget_allocation_contract.json"
DOC = ROOT / "docs/architecture/governed_local_model_budget_allocation_contract.md"
CONTRACT = json.loads(PATH.read_text(encoding="utf-8"))


def candidate() -> TaskAuthorityDefinition:
    item = CONTRACT["candidate_task_authority_definition"]
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


def test_machine_contract_and_narrative_freeze_same_identity_and_digest() -> None:
    doc = DOC.read_text(encoding="utf-8")
    assert CONTRACT["schema"] == "sentientos.governed_local_model_budget_allocation_contract:v1"
    for exact in (CONTRACT["resource_kind"], CONTRACT["candidate_definition_digest"],
                  CONTRACT["future_registration_task"]["task_name"]):
        assert exact in doc
    assert CONTRACT["candidate_definition_canonical_serialization"] in doc


def test_all_runtime_budget_fields_are_exactly_classified() -> None:
    fields = CONTRACT["resource_specific_bounds"]["fields"]
    assert set(fields) == set(LocalModelInvocationBudget.__dataclass_fields__)
    assert {name for name, value in fields.items() if value["conserved"]} == {
        "max_calls_per_correlation"
    }
    assert fields["max_input_chars"]["unit"] == "Python Unicode code points under current runtime"
    assert fields["max_output_chars"]["unit"] == "UTF-8 bytes under current runtime despite field name"
    assert fields["max_new_tokens"]["measurable_consumption"] is False
    assert fields["timeout_seconds"]["allocation_role"] == "temporal ceiling"


def test_resource_kind_is_exact_non_generic_and_allocation_record_is_compatible() -> None:
    assert CONTRACT["resource_kind"] == "governed_local_model_invocation_call_entitlement.v1"
    assert CONTRACT["resource_kind"] not in {"compute", "model", "*"}
    required = set(CONTRACT["allocation_record"]["required_fields"])
    assert {"allocation_id", "principal_binding_digest", "resource_kind",
            "resource_specific_bounds", "validity", "allocator_id", "epoch",
            "policy_digest", "allocation_digest"} <= required
    assert {"principal_id", "principal_epoch"} <= required


def test_narrowing_and_separate_authority_currentness_and_serving_are_explicit() -> None:
    rules = CONTRACT["resource_specific_bounds"]["comparison_rules"]
    assert "numeric minimum" in rules and "cannot expand" in rules
    assert CONTRACT["resource_specific_bounds"]["caller_budget_authoritative_entitlement"] is False
    assert CONTRACT["principal_prerequisites"]["currentness_allocates"] is False
    effect = CONTRACT["effect_admission_relationship"]
    assert effect["allocation_is_effect_authority"] is False
    assert effect["effect_admission_mints_or_replenishes"] is False
    assert effect["execution_order"].index("existing independent LOCAL_MODEL_INFERENCE effect admission") < effect["execution_order"].index("final current allocation validity check and atomic durable call debit")
    assert CONTRACT["serving_relationship"]["model_authority_ceiling_is_allocation"] is False
    assert CONTRACT["serving_relationship"]["both_required"] is True


def test_attempt_retry_timeout_failure_and_restart_semantics_are_closed() -> None:
    attempt = CONTRACT["attempt_semantics"]
    assert "Consumes zero" in attempt["pre_attempt_rejection"]
    assert "exactly one call" in attempt["generation_begins"]
    assert "does not refund" in attempt["timeout"]
    assert "Consumes one call" in attempt["backend_failure"]
    assert "new attempt_id" in attempt["retry"]
    restart = CONTRACT["retry_and_restart_semantics"]
    assert restart["restart_or_correlation_rollover_replenishes"] is False
    assert "process-local component safeguard only" in restart["current_invocation_counts"]
    assert "not a ledger" in restart["current_invocation_counts"]
    assert "durable atomic" in restart["implementation_requirement"]


def test_measurement_claims_are_truthful_and_resource_receipt_stays_separate() -> None:
    measurement = CONTRACT["consumption_measurement"]
    assert "exact actual token consumption" in measurement["not_truthful_today"]
    for resource in ("CPU consumption", "GPU consumption", "RAM consumption", "energy consumption"):
        assert resource in measurement["not_truthful_today"]
    receipt = CONTRACT["receipt_contract"]
    assert receipt["distinct_from_effect_receipt"] is True
    assert receipt["effect_success_required_for_consumption"] is False
    assert receipt["effect_occurred_implies_reconciled"] is False
    assert "effect_receipt_digest" in receipt["required_fields"]


def test_candidate_definition_is_exact_closed_reproducible_and_not_registered() -> None:
    definition = candidate()
    assert len(definition.subsystem_kinds) == len(definition.principal_kinds) == 1
    assert definition.required_effects
    assert all("*" not in value for value in (
        definition.capability_id, *definition.subsystem_kinds,
        *definition.principal_kinds, *definition.required_effects))
    assert authority_definition_digest(definition) == CONTRACT["candidate_definition_digest"]
    assert definition.capability_id not in AUTHORITY_DEFINITIONS
    assert CONTRACT["posture"]["authority_definition_registered"] is False


def test_approval_is_template_only_and_registration_payload_is_non_exercising() -> None:
    approval = CONTRACT["operator_approval_template"]
    assert approval["evidence_id"].startswith("<operator-supplied")
    assert approval["operator_identity_label"].startswith("<operator-supplied")
    assert approval["approval_status"].startswith("<operator-supplied")
    assert approval["evidence_digest"].startswith("<computed-after")
    payload = CONTRACT["future_registration_task"]["register_authority_definition_payload"]
    assert payload["requested_capability_id"] == payload["authority_principal"] == ""
    assert payload["requested_effects"] == payload["runtime_mutations"] == []


def test_contract_introduces_no_runtime_allocator_or_runtime_behavior_change() -> None:
    assert CONTRACT["posture"]["runtime_allocator_implemented"] is False
    assert CONTRACT["posture"]["entitlement_enforcement_implemented"] is False
    assert CONTRACT["posture"]["allocations_issued"] is False
    assert not (ROOT / "sentientos" / "governed_local_model_resource_allocator.py").exists()
    deferred = set(CONTRACT["deferred"])
    assert {"allocator and durable ledger", "resource gate and debit enforcement",
            "invocation/serving/control-plane changes", "authority-definition registration"} <= deferred


def test_exactly_one_next_slice_is_definition_only_registration() -> None:
    next_slice = CONTRACT["next_runtime_slice"]
    assert next_slice == {
        "count": 1,
        "id": "register-governed-local-model-resource-allocation-adapter-authority-definition",
        "kind": "definition_only_authority_registration",
        "requires": "independent operator approval evidence bound to candidate_definition_digest",
        "allocator_implementation_allowed": False,
    }
