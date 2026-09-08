from __future__ import annotations

from dataclasses import fields

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    LOCAL_MODEL_ARTIFACT_ACQUISITION,
    LOCAL_MODEL_CATALOG_DEPLOY,
    LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE,
    MODEL_MIRROR_PUBLISH,
)
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths
from sentientos.control_plane_kernel import AuthorityClass

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_model_artifact_acquisition_controller"
EFFECTS = (
    "exact_operator_approval_evidence_read",
    "exact_authoritative_deployed_catalog_proof_read",
    "exact_model_artifact_acquisition_plan_read",
    "bounded_exact_https_artifact_stream",
    "exact_content_addressed_model_escrow_write",
    "model_artifact_acquisition_receipt_write",
)
GOAL = (
    "Implement bounded exact model artifact acquisition requiring explicit operator approval, "
    "authoritative deployed catalog provenance, and exact artifact identity."
)


def request(**changes: object) -> PlannerRequest:
    values: dict[str, object] = {
        "task_name": "bounded exact model artifact acquisition",
        "task_goal": GOAL,
        "preset_id": "model_distribution",
        "subsystem_kind": "model_distribution",
        "capability_id": LOCAL_MODEL_ARTIFACT_ACQUISITION,
        "authority_principal": PRINCIPAL,
        "requested_effects": EFFECTS,
        "commit_title": "[codex:model-acquisition] harden bounded artifact acquisition",
    }
    values.update(changes)
    return PlannerRequest(**values)  # type: ignore[arg-type]


def test_exact_future_acquisition_definition_is_eligible_without_grant_or_effect() -> None:
    definition = AUTHORITY_DEFINITIONS[LOCAL_MODEL_ARTIFACT_ACQUISITION]
    assert definition.subsystem_kinds == frozenset({"model_distribution"})
    assert definition.principal_kinds == frozenset({PRINCIPAL})
    assert definition.required_effects == frozenset(EFFECTS)
    assert len(EFFECTS) == len(set(EFFECTS))
    planned = plan_codex_task_scaffold_paths(request())
    assert planned.status == "ready"
    bootstrap_fields = {field.name for field in fields(CodexTaskBootstrapRequest)}
    result = bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in request().__dict__.items() if key in bootstrap_fields
    }), include_preset_verifier=False)
    assert result.status in {"ready", "ready_with_warnings"}
    assert result.planner_result_summary["authority_definition_eligibility_only"] is True
    assert result.planner_result_summary["capability_granted"] is False
    assert not hasattr(result, "grant") and not hasattr(result, "lease")
    assert not hasattr(result, "operator_approval")


def test_registry_truthfully_marks_runtime_authority_hardening_partial() -> None:
    record = build_default_capability_registry().by_id()[LOCAL_MODEL_ARTIFACT_ACQUISITION]
    assert record.status == "partial"
    assert record.requires_control_plane_admission and record.requires_operator_approval
    assert "exact catalog-authorized HTTPS streaming with byte and SHA-256 verification" in record.implemented_surfaces
    assert "replacement of caller-constructible operator_confirmed authorization" in record.deferred_surfaces
    assert "task-authority admission is live operator approval" in record.forbidden_implications


@pytest.mark.parametrize("missing", (
    "explicit operator approval", "authoritative deployed catalog", "exact artifact identity",
))
def test_each_acquisition_goal_precondition_is_mandatory(missing: str) -> None:
    planned = plan_codex_task_scaffold_paths(request(task_goal=GOAL.replace(missing, "required evidence")))
    assert planned.status == "blocked"
    assert "authority_goal_missing_required_precondition" in planned.blocker_codes


@pytest.mark.parametrize("goal", (
    "Implement bounded acquisition without explicit operator approval; requiring authoritative deployed catalog and exact artifact identity.",
    "Implement bounded acquisition requiring explicit operator approval but without authoritative deployed catalog; requiring exact artifact identity.",
    "Implement bounded acquisition requiring explicit operator approval and authoritative deployed catalog but no exact artifact identity.",
))
def test_negated_acquisition_preconditions_are_blocked(goal: str) -> None:
    planned = plan_codex_task_scaffold_paths(request(task_goal=goal))
    assert planned.status == "blocked"
    assert "authority_goal_missing_required_precondition" in planned.blocker_codes


def test_wrong_subsystem_and_inexact_effect_surfaces_are_blocked() -> None:
    assert "authority_subsystem_not_admitted" in plan_codex_task_scaffold_paths(
        request(subsystem_kind="local_model_chat")).blocker_codes
    for effects in (EFFECTS[:-1], EFFECTS + ("provider_access",), EFFECTS + (EFFECTS[0],)):
        assert "authority_effect_surface_not_exact" in plan_codex_task_scaffold_paths(
            request(requested_effects=effects)).blocker_codes


@pytest.mark.parametrize("principal", (
    "deterministic_publication_controller",
    "deterministic_catalog_deployment_controller",
    "deterministic_catalog_deployment_authorization_controller",
    "stochastic_model", "commissioned_local_model", "maintenance_implementation_worker",
    "model_curator", "persistent_runtime_activation_controller",
))
def test_all_non_acquisition_principals_are_denied(principal: str) -> None:
    assert "authority_principal_not_admitted" in plan_codex_task_scaffold_paths(
        request(authority_principal=principal)).blocker_codes


@pytest.mark.parametrize("phrase", (
    "arbitrary url", "arbitrary host", "arbitrary network", "generic network authority",
    "arbitrary filesystem", "arbitrary destination", "mutable artifact alias",
    "provider administration", "credential management", "catalog mutation",
    "model commissioning", "activation", "inference", "self-grant", "unbounded transfer",
))
def test_forbidden_acquisition_scope_is_blocked(phrase: str) -> None:
    planned = plan_codex_task_scaffold_paths(request(task_goal=f"{GOAL} Request {phrase}."))
    assert "authority_goal_requests_forbidden_scope" in planned.blocker_codes


def test_other_distribution_contracts_and_narrow_control_plane_identity_remain_distinct() -> None:
    assert AUTHORITY_DEFINITIONS[MODEL_MIRROR_PUBLISH].principal_kinds == frozenset(
        {"deterministic_publication_controller"})
    assert AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOY].principal_kinds == frozenset(
        {"deterministic_catalog_deployment_controller"})
    assert AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE].principal_kinds == frozenset(
        {"deterministic_catalog_deployment_authorization_controller"})
    assert AuthorityClass.MODEL_ARTIFACT_ACQUISITION.value == "model_artifact_acquisition"
    assert AuthorityClass.MODEL_ARTIFACT_ACQUISITION not in {
        AuthorityClass.PRIVILEGED_OPERATOR_CONTROL,
        AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE,
        AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION,
    }


def test_admission_contract_has_no_effectful_or_downstream_result_fields() -> None:
    bootstrap_fields = {field.name for field in fields(CodexTaskBootstrapRequest)}
    result = bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in request().__dict__.items() if key in bootstrap_fields
    }), include_preset_verifier=False)
    rendered = result.planner_result_summary
    assert rendered["capability_granted"] is False
    for field in (
        "network_performed", "artifact_written", "operator_approval",
        "model_commissioned", "model_activated", "inference_performed",
    ):
        assert field not in rendered
