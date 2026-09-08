from __future__ import annotations

from dataclasses import fields

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    LOCAL_MODEL_ARTIFACT_ACQUISITION,
    LOCAL_MODEL_CATALOG_DEPLOY,
    LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE,
    LOCAL_MODEL_PRODUCTION_COMMISSIONING,
    MODEL_MIRROR_PUBLISH,
)
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths
from sentientos.control_plane_kernel import AuthorityClass

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_local_model_commissioning_controller"
EFFECTS = (
    "exact_operator_approval_evidence_read",
    "exact_authoritative_deployed_catalog_proof_read",
    "exact_hardened_model_artifact_acquisition_receipt_read",
    "exact_commissioning_intent_read",
    "bounded_zero_generation_gguf_compatibility_construction",
    "bounded_exact_local_model_load",
    "bounded_commissioning_smoke_inference",
    "local_model_commissioning_receipt_write",
)
GOAL = (
    "Implement bounded local-model commissioning requiring explicit operator approval, "
    "authoritative deployed catalog provenance, and exact acquired artifact identity."
)


def request(**changes: object) -> PlannerRequest:
    values: dict[str, object] = {
        "task_name": "harden bounded production local model commissioning",
        "task_goal": GOAL,
        "subsystem_kind": "local_model_chat",
        "capability_id": LOCAL_MODEL_PRODUCTION_COMMISSIONING,
        "authority_principal": PRINCIPAL,
        "requested_effects": EFFECTS,
        "commit_title": "[codex:model-commissioning] harden bounded production commissioning",
    }
    values.update(changes)
    return PlannerRequest(**values)  # type: ignore[arg-type]


def bootstrap(**changes: object):  # type: ignore[no-untyped-def]
    planned_request = request(**changes)
    allowed = {field.name for field in fields(CodexTaskBootstrapRequest)}
    return bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in planned_request.__dict__.items() if key in allowed
    }), include_preset_verifier=False)


def test_future_commissioning_authority_definition_is_admissible_without_grant() -> None:
    definition = AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_COMMISSIONING]
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
    "exact acquired artifact identity",
))
def test_each_commissioning_precondition_is_required(missing: str) -> None:
    result = plan_codex_task_scaffold_paths(request(task_goal=GOAL.replace(missing, "evidence")))
    assert result.status == "blocked"
    assert "authority_goal_missing_required_precondition" in result.blocker_codes


@pytest.mark.parametrize("goal", (
    "Commission without explicit operator approval; require authoritative deployed catalog and exact acquired artifact identity.",
    "Commission with explicit operator approval but without authoritative deployed catalog; require exact acquired artifact identity.",
    "Commission with explicit operator approval and authoritative deployed catalog but without exact acquired artifact identity.",
))
def test_negated_commissioning_preconditions_are_blocked(goal: str) -> None:
    assert "authority_goal_missing_required_precondition" in plan_codex_task_scaffold_paths(
        request(task_goal=goal)).blocker_codes


def test_wrong_subsystem_and_inexact_effect_sets_are_blocked() -> None:
    assert "authority_subsystem_not_admitted" in plan_codex_task_scaffold_paths(
        request(subsystem_kind="model_distribution")).blocker_codes
    for effects in (EFFECTS[:-1], EFFECTS + ("activation_write",), EFFECTS + (EFFECTS[0],)):
        assert "authority_effect_surface_not_exact" in plan_codex_task_scaffold_paths(
            request(requested_effects=effects)).blocker_codes


@pytest.mark.parametrize("principal", (
    "stochastic_model", "commissioned_local_model", "maintenance_implementation_worker",
    "model_curator", "deterministic_publication_controller",
    "deterministic_catalog_deployment_controller",
    "deterministic_catalog_deployment_authorization_controller",
    "deterministic_model_artifact_acquisition_controller",
    "persistent_runtime_activation_controller", "generic_chat_runtime_caller",
))
def test_non_commissioning_principals_are_denied(principal: str) -> None:
    assert "authority_principal_not_admitted" in plan_codex_task_scaffold_paths(
        request(authority_principal=principal)).blocker_codes


@pytest.mark.parametrize("phrase", (
    "arbitrary model path", "arbitrary artifact", "arbitrary runtime",
    "arbitrary filesystem", "arbitrary output destination", "provider invocation",
    "provider administration", "credential management", "network authority",
    "catalog mutation", "artifact acquisition", "activation", "unrestricted serving",
    "autonomous inference", "background inference", "unbounded inference",
    "tool authority", "memory authority", "action authority", "repository mutation",
    "self-grant",
))
def test_forbidden_commissioning_scope_is_blocked(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in plan_codex_task_scaffold_paths(
        request(task_goal=f"{GOAL} Request {phrase}.")).blocker_codes


def test_bounded_smoke_and_zero_generation_construction_remain_expressible() -> None:
    goal = GOAL + " Perform bounded commissioning smoke inference and bounded zero-generation compatibility construction."
    assert plan_codex_task_scaffold_paths(request(task_goal=goal)).status == "ready"


def test_registry_truthfully_marks_authority_boundary_partial() -> None:
    record = build_default_capability_registry().by_id()[LOCAL_MODEL_PRODUCTION_COMMISSIONING]
    assert record.status == "partial"
    assert record.requires_operator_approval and record.requires_control_plane_admission
    assert "hardened v2 acquisition-receipt verification" in record.implemented_surfaces
    assert "genuine external commissioning approval verification" in record.deferred_surfaces


def test_neighboring_authority_definitions_and_control_plane_identity_are_unchanged_and_distinct() -> None:
    assert AUTHORITY_DEFINITIONS[MODEL_MIRROR_PUBLISH].principal_kinds == frozenset({"deterministic_publication_controller"})
    assert AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOY].principal_kinds == frozenset({"deterministic_catalog_deployment_controller"})
    assert AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE].principal_kinds == frozenset({"deterministic_catalog_deployment_authorization_controller"})
    assert AUTHORITY_DEFINITIONS[LOCAL_MODEL_ARTIFACT_ACQUISITION].principal_kinds == frozenset({"deterministic_model_artifact_acquisition_controller"})
    assert AuthorityClass.MODEL_COMMISSIONING.value == "model_commissioning"
    assert AuthorityClass.MODEL_COMMISSIONING not in {
        AuthorityClass.LOCAL_MODEL_INFERENCE,
        AuthorityClass.MODEL_ARTIFACT_ACQUISITION,
        AuthorityClass.PRIVILEGED_OPERATOR_CONTROL,
    }


def test_admission_performs_no_commissioning_or_downstream_effect() -> None:
    result = bootstrap()
    summary = result.planner_result_summary
    assert summary["capability_granted"] is False
    for name in (
        "operator_approval", "compatibility_construction_performed", "model_loaded",
        "inference_performed", "commissioning_receipt_written", "model_activated",
        "activation_loaded",
    ):
        assert name not in summary
