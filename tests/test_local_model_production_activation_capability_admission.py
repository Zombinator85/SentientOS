from __future__ import annotations

from dataclasses import fields

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    LOCAL_MODEL_ARTIFACT_ACQUISITION,
    LOCAL_MODEL_CATALOG_DEPLOY,
    LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE,
    LOCAL_MODEL_PRODUCTION_ACTIVATION,
    LOCAL_MODEL_PRODUCTION_COMMISSIONING,
    MODEL_MIRROR_PUBLISH,
)
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths
from sentientos.control_plane_kernel import AuthorityClass

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_local_model_activation_controller"
EFFECTS = (
    "exact_operator_approval_evidence_read",
    "exact_authoritative_deployed_catalog_proof_read",
    "exact_hardened_local_model_commissioning_receipt_read",
    "exact_commissioned_artifact_identity_read",
    "exact_activation_intent_read",
    "exact_current_activation_state_read",
    "authoritative_active_model_compare_and_swap",
    "local_model_activation_receipt_write",
)
GOAL = (
    "Implement bounded production local-model activation requiring explicit operator approval, "
    "authoritative deployed catalog provenance, hardened commissioning receipt evidence, and "
    "exact prior activation state."
)


def request(**changes: object) -> PlannerRequest:
    values: dict[str, object] = {
        "task_name": "implement bounded production local model activation",
        "task_goal": GOAL,
        "subsystem_kind": "local_model_chat",
        "capability_id": LOCAL_MODEL_PRODUCTION_ACTIVATION,
        "authority_principal": PRINCIPAL,
        "requested_effects": EFFECTS,
        "commit_title": "[codex:model-activation] implement bounded production activation",
    }
    values.update(changes)
    return PlannerRequest(**values)  # type: ignore[arg-type]


def bootstrap(**changes: object):  # type: ignore[no-untyped-def]
    planned = request(**changes)
    allowed = {field.name for field in fields(CodexTaskBootstrapRequest)}
    return bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in planned.__dict__.items() if key in allowed
    }), include_preset_verifier=False)


def blockers(**changes: object) -> tuple[str, ...]:
    return plan_codex_task_scaffold_paths(request(**changes)).blocker_codes


def test_future_activation_authority_definition_is_admissible_without_grant() -> None:
    definition = AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_ACTIVATION]
    assert definition.subsystem_kinds == frozenset({"local_model_chat"})
    assert definition.principal_kinds == frozenset({PRINCIPAL})
    assert definition.required_effects == frozenset(EFFECTS)
    assert len(EFFECTS) == len(set(EFFECTS))
    assert plan_codex_task_scaffold_paths(request()).status == "ready"
    result = bootstrap()
    assert result.status in {"ready", "ready_with_warnings"}
    assert result.planner_result_summary["authority_definition_eligibility_only"] is True
    assert result.planner_result_summary["capability_granted"] is False
    assert not hasattr(result, "operator_approval")


@pytest.mark.parametrize("missing", (
    "explicit operator approval", "authoritative deployed catalog",
    "hardened commissioning receipt", "exact prior activation state",
))
def test_each_activation_precondition_is_required(missing: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(missing, "evidence"))


@pytest.mark.parametrize(("phrase", "replacement"), (
    ("explicit operator approval", "without explicit operator approval"),
    ("explicit operator approval", "no explicit operator approval"),
    ("authoritative deployed catalog", "without authoritative deployed catalog"),
    ("authoritative deployed catalog", "no authoritative deployed catalog"),
    ("hardened commissioning receipt", "without hardened commissioning receipt"),
    ("hardened commissioning receipt", "no hardened commissioning receipt"),
    ("exact prior activation state", "without exact prior activation state"),
    ("exact prior activation state", "no exact prior activation state"),
))
def test_negated_activation_preconditions_are_blocked(phrase: str, replacement: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, replacement))


def test_wrong_subsystem_and_inexact_effect_sets_are_blocked() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="model_distribution")
    for effects in (EFFECTS[:-1], EFFECTS + ("model_load",), EFFECTS + (EFFECTS[0],)):
        assert "authority_effect_surface_not_exact" in blockers(requested_effects=effects)


@pytest.mark.parametrize("principal", (
    "deterministic_local_model_commissioning_controller",
    "deterministic_model_artifact_acquisition_controller",
    "deterministic_catalog_deployment_controller",
    "deterministic_catalog_deployment_authorization_controller",
    "deterministic_publication_controller", "persistent_runtime_activation_controller",
    "stochastic_model", "commissioned_local_model", "maintenance_implementation_worker",
    "model_curator", "generic_chat_runtime_caller", "generic_runtime_caller",
))
def test_non_activation_principals_are_denied(principal: str) -> None:
    assert "authority_principal_not_admitted" in blockers(authority_principal=principal)


@pytest.mark.parametrize("phrase", (
    "arbitrary activation path", "arbitrary model path", "arbitrary artifact",
    "arbitrary runtime", "arbitrary filesystem", "arbitrary configuration",
    "arbitrary state root", "blind overwrite", "wildcard prior state",
    "model acquisition", "model commissioning", "model load", "serving",
    "unrestricted serving", "boot load", "automatic boot loading", "inference",
    "autonomous inference", "background inference", "provider invocation",
    "provider administration", "credential management", "network authority",
    "tool authority", "memory authority", "action authority", "repository mutation",
    "self-grant", "self grant",
))
def test_forbidden_activation_scope_is_blocked(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(
        task_goal=f"{GOAL} Request {phrase}.")


def test_registry_truthfully_marks_activation_contract_only() -> None:
    records = build_default_capability_registry().by_id()
    record = records[LOCAL_MODEL_PRODUCTION_ACTIVATION]
    assert record.category == "local_model_chat"
    assert record.status == "scaffolded" and record.authority_level == "contract_only"
    assert record.requires_operator_approval and record.requires_control_plane_admission
    assert "activation-state compare-and-swap" in record.deferred_surfaces
    assert "activated-model load and serving" in record.deferred_surfaces
    assert "local_model_production_activation runtime implementation" in records[
        LOCAL_MODEL_PRODUCTION_COMMISSIONING].deferred_surfaces


def test_neighboring_definitions_remain_unchanged_and_activation_class_is_distinct() -> None:
    expected = {
        MODEL_MIRROR_PUBLISH: "deterministic_publication_controller",
        LOCAL_MODEL_CATALOG_DEPLOY: "deterministic_catalog_deployment_controller",
        LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE:
            "deterministic_catalog_deployment_authorization_controller",
        LOCAL_MODEL_ARTIFACT_ACQUISITION: "deterministic_model_artifact_acquisition_controller",
        LOCAL_MODEL_PRODUCTION_COMMISSIONING: "deterministic_local_model_commissioning_controller",
    }
    for capability, principal in expected.items():
        assert AUTHORITY_DEFINITIONS[capability].principal_kinds == frozenset({principal})
    assert AuthorityClass.MODEL_ACTIVATION.value == "model_activation"
    assert AuthorityClass.MODEL_ACTIVATION not in {
        AuthorityClass.MODEL_COMMISSIONING, AuthorityClass.MODEL_ARTIFACT_ACQUISITION,
        AuthorityClass.LOCAL_MODEL_INFERENCE, AuthorityClass.PRIVILEGED_OPERATOR_CONTROL,
    }


def test_admission_performs_no_activation_model_load_serving_or_inference() -> None:
    summary = bootstrap().planner_result_summary
    assert summary["capability_granted"] is False
    for name in (
        "operator_approval", "activation_state_written", "activation_receipt_written",
        "model_loaded", "serving_started", "inference_performed", "installation_mutated",
        "control_plane_admission",
    ):
        assert name not in summary
