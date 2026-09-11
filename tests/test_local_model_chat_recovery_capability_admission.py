from __future__ import annotations

from dataclasses import fields

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    LOCAL_MODEL_CHAT_RECOVERY,
    LOCAL_MODEL_PRODUCTION_SERVING,
    authority_admission_blockers,
)
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths
from sentientos.control_plane_kernel import AuthorityClass
from sentientos.runtime.local_model_chat_service import (
    SERVICE_ID,
    LocalModelChatStartup,
    build_runtime_service_registry,
)
from sentientos.runtime.supervisor import RuntimeSupervisor

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_local_model_chat_recovery_controller"
EFFECTS = (
    "exact_operator_recovery_approval_evidence_read",
    "exact_runtime_supervisor_local_model_chat_state_read",
    "exact_prior_serving_lifetime_evidence_read",
    "authenticated_current_hardened_activation_state_read",
    "exact_local_model_chat_startup_configuration_read",
    "exact_fresh_serving_operation_identity_read",
    "bounded_exact_local_model_chat_child_restart",
    "post_restart_semantic_readiness_observation",
    "local_model_chat_recovery_receipt_write",
)
GOAL = (
    "Recover failed hardened local-model chat with explicit operator recovery approval; "
    "require exact prior serving lifetime evidence and unchanged activation provenance; "
    "require a fresh serving operation identity; preserve separate model serving and "
    "local model inference authority."
)


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = {
        "capability_id": LOCAL_MODEL_CHAT_RECOVERY,
        "subsystem_kind": "local_model_chat",
        "principal_kind": PRINCIPAL,
        "requested_effects": EFFECTS,
        "task_goal": GOAL,
    }
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_exact_recovery_authority_eligibility_is_admitted_without_effect() -> None:
    definition = AUTHORITY_DEFINITIONS[LOCAL_MODEL_CHAT_RECOVERY]
    assert definition.subsystem_kinds == frozenset({"local_model_chat"})
    assert definition.principal_kinds == frozenset({PRINCIPAL})
    assert definition.required_effects == frozenset(EFFECTS)
    assert len(EFFECTS) == len(set(EFFECTS))
    assert blockers() == ()


@pytest.mark.parametrize("effects", (EFFECTS[:-1], EFFECTS + ("model_load",), EFFECTS + (EFFECTS[0],)))
def test_effect_surface_must_be_exact_and_duplicate_free(effects: tuple[str, ...]) -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=effects)


def test_wrong_principal_and_subsystem_are_blocked() -> None:
    assert "authority_principal_not_admitted" in blockers(principal_kind="stochastic_model")
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="runtime_supervision")


@pytest.mark.parametrize("phrase", (
    "explicit operator recovery approval", "exact prior serving lifetime evidence",
    "unchanged activation provenance", "fresh serving operation identity",
    "separate model serving and local model inference authority",
))
def test_each_affirmative_recovery_precondition_is_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, "required evidence"))


@pytest.mark.parametrize("phrase", (
    "automatic recovery", "automatic restart", "silent recovery",
    "hot activation switching", "hot activation switch", "changed activation recovery",
    "reuse serving operation", "reuse operation id", "arbitrary executable",
    "arbitrary argv", "arbitrary command", "arbitrary model path",
    "arbitrary activation path", "arbitrary runtime", "arbitrary state root",
    "simulation fallback", "provider invocation", "network authority", "tool authority",
    "memory authority", "action authority", "repository mutation", "perform inference",
    "generation call", "self-grant", "self grant",
))
def test_broader_or_effectful_recovery_scope_is_forbidden(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(task_goal=f"{GOAL} Request {phrase}.")


def test_registry_truth_is_partial_eligibility_only() -> None:
    record = build_default_capability_registry().by_id()[LOCAL_MODEL_CHAT_RECOVERY]
    assert record.category == "local_model_chat"
    assert record.status == "partial"
    assert record.authority_level == "eligibility_only"
    assert record.requires_operator_approval
    assert record.requires_control_plane_admission
    assert record.requires_audit_receipt
    assert "unchanged-activation eligibility requirement" in record.implemented_surfaces
    assert "fresh serving-operation identity requirement" in record.implemented_surfaces
    assert "effectful recovery controller" in record.deferred_surfaces


def test_no_recovery_runtime_authority_or_effectful_method_is_introduced() -> None:
    assert not any("RECOVERY" in member.name for member in AuthorityClass)
    assert AuthorityClass.DAEMON_RESTART.value == "daemon_restart"
    for name in ("recover", "restart_now", "recover_local_model_chat"):
        assert not hasattr(RuntimeSupervisor, name)


def test_existing_serving_effects_and_restart_policy_remain_unchanged() -> None:
    assert AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_SERVING].required_effects == frozenset({
        "authenticated_current_hardened_activation_state_read",
        "exact_current_activation_receipt_read",
        "exact_authoritative_deployed_catalog_proof_read",
        "exact_hardened_local_model_commissioning_receipt_read",
        "exact_activated_artifact_identity_and_bytes_read",
        "exact_activated_runtime_identity_read", "bounded_exact_activated_model_load",
        "authoritative_serving_session_bind", "stale_serving_session_invalidation",
        "local_model_serving_session_receipt_write",
    })
    registry = build_runtime_service_registry(LocalModelChatStartup())
    assert registry.descriptors[SERVICE_ID].restart_policy == "never"


def test_bootstrap_remains_metadata_only_eligibility() -> None:
    planned = PlannerRequest(
        task_name="implement explicit local model chat recovery", task_goal=GOAL,
        subsystem_kind="local_model_chat", capability_id=LOCAL_MODEL_CHAT_RECOVERY,
        authority_principal=PRINCIPAL, requested_effects=EFFECTS,
        commit_title="[codex:local-model-chat] implement explicit serving recovery",
    )
    assert plan_codex_task_scaffold_paths(planned).status == "ready"
    allowed = {field.name for field in fields(CodexTaskBootstrapRequest)}
    result = bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in planned.__dict__.items() if key in allowed
    }), include_preset_verifier=False)
    assert result.status in {"ready", "ready_with_warnings"}
    assert result.planner_result_summary["authority_definition_eligibility_only"] is True
    assert result.planner_result_summary["capability_granted"] is False
