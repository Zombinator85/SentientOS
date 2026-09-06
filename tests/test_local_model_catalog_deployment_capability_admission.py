from __future__ import annotations

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import LOCAL_MODEL_CATALOG_DEPLOY, MODEL_MIRROR_PUBLISH
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_catalog_deployment_controller"
EFFECTS = (
    "exact_verified_publication_receipt_read",
    "exact_deployment_eligible_catalog_candidate_read",
    "authoritative_catalog_compare_and_swap",
    "catalog_deployment_receipt_write",
)
GOAL = "Implement bounded catalog custody transition requiring verified publication and exact prior-state identity"


def request(**changes: object) -> PlannerRequest:
    values: dict[str, object] = dict(task_name="catalog custody controller", task_goal=GOAL,
        preset_id="model_distribution", subsystem_kind="model_distribution",
        capability_id=LOCAL_MODEL_CATALOG_DEPLOY, authority_principal=PRINCIPAL,
        requested_effects=EFFECTS, commit_title="[codex:model-catalog] implement catalog custody controller")
    values.update(changes)
    return PlannerRequest(**values)  # type: ignore[arg-type]


def test_exact_catalog_deployment_definition_is_eligible_without_grant() -> None:
    planned = plan_codex_task_scaffold_paths(request())
    assert planned.status == "ready"
    result = bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in request().__dict__.items()
        if key in CodexTaskBootstrapRequest.__dataclass_fields__
    }), include_preset_verifier=False)
    assert result.status in {"ready", "ready_with_warnings"}
    assert result.planner_result_summary["capability_granted"] is False


def test_registry_is_contract_only_and_requires_operator_control_plane_receipt() -> None:
    record = build_default_capability_registry().by_id()[LOCAL_MODEL_CATALOG_DEPLOY]
    assert (record.category, record.status, record.authority_level) == (
        "production_model_catalog_deployment", "implemented", "contract_only")
    assert record.requires_control_plane_admission and record.requires_operator_approval
    assert record.requires_audit_receipt and record.metadata_only
    assert "catalog deployment controller" in record.deferred_surfaces


@pytest.mark.parametrize("capability", ("deploy", "sentientos.unknown.deploy", MODEL_MIRROR_PUBLISH))
def test_other_capability_cannot_substitute_for_catalog_deployment(capability: str) -> None:
    result = plan_codex_task_scaffold_paths(request(capability_id=capability))
    assert result.status == "blocked"


@pytest.mark.parametrize("principal", (
    "stochastic_model", "commissioned_local_model", "maintenance_implementation_worker",
    "model_curator", "deterministic_publication_controller",
))
def test_ineligible_principals_cannot_hold_catalog_deployment(principal: str) -> None:
    result = plan_codex_task_scaffold_paths(request(authority_principal=principal))
    assert "authority_principal_not_admitted" in result.blocker_codes


def test_capability_id_or_inexact_effect_surface_is_denied() -> None:
    bare = plan_codex_task_scaffold_paths(PlannerRequest(
        task_name="catalog custody", task_goal=GOAL, capability_id=LOCAL_MODEL_CATALOG_DEPLOY))
    assert bare.status == "blocked"
    for effects in (EFFECTS[:-1], EFFECTS + (EFFECTS[0],), EFFECTS + ("generic_filesystem_mutation",),
                    EFFECTS + ("generic_network_authority",)):
        result = plan_codex_task_scaffold_paths(request(requested_effects=effects))
        assert "authority_effect_surface_not_exact" in result.blocker_codes


def test_wrong_subsystem_and_missing_evidence_or_prior_state_are_denied() -> None:
    assert "authority_subsystem_not_admitted" in plan_codex_task_scaffold_paths(
        request(subsystem_kind="local_model_chat")).blocker_codes
    for goal in ("Implement with exact prior-state identity", "Implement with verified publication"):
        assert "authority_goal_missing_required_precondition" in plan_codex_task_scaffold_paths(
            request(task_goal=goal)).blocker_codes


@pytest.mark.parametrize("phrase", (
    "generic deployment", "arbitrary configuration", "network authority", "provider administration",
    "credential management", "Git publication", "model acquisition", "commissioning", "activation",
    "inference", "self-grant", "mutable catalog", "arbitrary destination", "Hugging Face", "blind overwrite",
))
def test_catalog_deployment_definition_cannot_expand_scope(phrase: str) -> None:
    result = plan_codex_task_scaffold_paths(request(task_goal=f"{GOAL}; allow {phrase}"))
    assert "authority_goal_requests_forbidden_scope" in result.blocker_codes
