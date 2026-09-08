from __future__ import annotations

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    LOCAL_MODEL_CATALOG_DEPLOY,
    LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE,
    MODEL_MIRROR_PUBLISH,
)
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_catalog_deployment_authorization_controller"
EFFECTS = (
    "exact_operator_approval_evidence_read",
    "exact_verified_publication_receipt_read",
    "exact_deployment_eligible_catalog_candidate_read",
    "bounded_catalog_deployment_grant_issue",
    "bounded_catalog_deployment_lease_issue",
    "catalog_deployment_authorization_receipt_write",
)
GOAL = "Implement bounded issuance from explicit operator approval for verified publication and exact prior-state"


def request(**changes: object) -> PlannerRequest:
    values: dict[str, object] = dict(
        task_name="catalog deployment authorization issuer", task_goal=GOAL,
        preset_id="model_distribution", subsystem_kind="model_distribution",
        capability_id=LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE,
        authority_principal=PRINCIPAL, requested_effects=EFFECTS,
        commit_title="[codex:model-catalog] implement bounded deployment authorization issuance",
    )
    values.update(changes)
    return PlannerRequest(**values)  # type: ignore[arg-type]


def test_exact_future_issuer_definition_is_eligible_without_grant() -> None:
    definition = AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE]
    assert definition.subsystem_kinds == frozenset({"model_distribution"})
    assert definition.principal_kinds == frozenset({PRINCIPAL})
    assert definition.required_effects == frozenset(EFFECTS) and len(EFFECTS) == len(set(EFFECTS))
    planned = plan_codex_task_scaffold_paths(request())
    assert planned.status == "ready"
    result = bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in request().__dict__.items()
        if key in CodexTaskBootstrapRequest.__dataclass_fields__
    }), include_preset_verifier=False)
    assert result.status in {"ready", "ready_with_warnings"}
    assert result.planner_result_summary["authority_definition_eligibility_only"] is True
    assert result.planner_result_summary["capability_granted"] is False
    assert not hasattr(result, "grant") and not hasattr(result, "lease")


def test_registry_truthfully_records_contract_only_definition() -> None:
    record = build_default_capability_registry().by_id()[LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE]
    assert (record.category, record.status, record.authority_level) == (
        "production_model_catalog_deployment", "implemented", "contract_only")
    assert record.requires_control_plane_admission and record.requires_operator_approval
    assert record.requires_audit_receipt and record.metadata_only
    assert "bounded production deployment grant issuance" in record.deferred_surfaces
    assert "bounded production deployment lease issuance" in record.deferred_surfaces


@pytest.mark.parametrize("missing", ("explicit operator approval", "verified publication", "exact prior-state"))
def test_each_goal_precondition_is_mandatory(missing: str) -> None:
    goal = GOAL.replace(missing, "required evidence")
    assert "authority_goal_missing_required_precondition" in plan_codex_task_scaffold_paths(
        request(task_goal=goal)).blocker_codes


@pytest.mark.parametrize("goal", (
    "Implement bounded issuance without explicit operator approval for verified publication and exact prior-state.",
    "Implement bounded issuance with no explicit operator approval for verified publication and exact prior-state.",
    "Implement bounded issuance not requiring explicit operator approval for verified publication and exact prior-state.",
    "Implement bounded issuance never requiring explicit operator approval for verified publication and exact prior-state.",
    "Implement bounded issuance bypassing explicit operator approval for verified publication and exact prior-state.",
    "Implement bounded issuance omitting explicit operator approval for verified publication and exact prior-state.",
    "Implement bounded issuance skipping explicit operator approval for verified publication and exact prior-state.",
    "Implement bounded issuance where explicit operator approval is not required; requiring verified publication and exact prior-state.",
    "Implement bounded issuance with explicit operator approval but without verified publication and exact prior-state.",
    "Implement bounded issuance with explicit operator approval and verified publication but without exact prior-state.",
    "Implement bounded issuance; must not proceed without explicit operator approval for verified publication and exact prior-state.",
))
def test_negated_or_ambiguous_goal_preconditions_are_denied(goal: str) -> None:
    planned = plan_codex_task_scaffold_paths(request(task_goal=goal))
    assert planned.status == "blocked"
    assert "authority_goal_missing_required_precondition" in planned.blocker_codes


@pytest.mark.parametrize("goal", (
    "Implement bounded issuance requiring explicit operator approval, verified publication, and exact prior-state identity",
    "Implement bounded issuance with explicit operator approval after verified publication using exact prior-state identity",
))
def test_affirmative_goal_precondition_forms_remain_eligible(goal: str) -> None:
    planned = plan_codex_task_scaffold_paths(request(task_goal=goal))
    assert planned.status == "ready"
    assert planned.blocker_codes == ()


def test_wrong_subsystem_and_inexact_effects_are_blocked() -> None:
    assert "authority_subsystem_not_admitted" in plan_codex_task_scaffold_paths(
        request(subsystem_kind="local_model_chat")).blocker_codes
    for effects in (EFFECTS[:-1], EFFECTS + (EFFECTS[0],), EFFECTS + ("provider_access",)):
        assert "authority_effect_surface_not_exact" in plan_codex_task_scaffold_paths(
            request(requested_effects=effects)).blocker_codes


@pytest.mark.parametrize("principal", (
    "stochastic_model", "commissioned_local_model", "maintenance_implementation_worker",
    "model_curator", "deterministic_publication_controller",
    "deterministic_catalog_deployment_controller",
    "deterministic_acquisition_fulfillment_controller",
    "persistent_runtime_activation_controller",
))
def test_ineligible_principals_cannot_issue_deployment_authority(principal: str) -> None:
    assert "authority_principal_not_admitted" in plan_codex_task_scaffold_paths(
        request(authority_principal=principal)).blocker_codes


def test_deployment_and_publication_capabilities_cannot_substitute() -> None:
    assert "authority_principal_not_admitted" in plan_codex_task_scaffold_paths(
        request(capability_id=LOCAL_MODEL_CATALOG_DEPLOY)).blocker_codes
    assert plan_codex_task_scaffold_paths(request(capability_id=MODEL_MIRROR_PUBLISH)).status == "blocked"
    deployment = AUTHORITY_DEFINITIONS[LOCAL_MODEL_CATALOG_DEPLOY]
    publication = AUTHORITY_DEFINITIONS[MODEL_MIRROR_PUBLISH]
    assert deployment.principal_kinds == frozenset({"deterministic_catalog_deployment_controller"})
    assert publication.principal_kinds == frozenset({"deterministic_publication_controller"})


def test_admission_has_no_runtime_or_catalog_effect_surface() -> None:
    forbidden = {"provider_access", "network_access", "credential_access", "model_publication",
                 "artifact_acquisition", "catalog_deployment", "commissioning", "activation", "inference"}
    assert forbidden.isdisjoint(AUTHORITY_DEFINITIONS[
        LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE].required_effects)
