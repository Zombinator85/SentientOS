from __future__ import annotations

from dataclasses import fields

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    LOCAL_MODEL_PRODUCTION_ACTIVATION,
    LOCAL_MODEL_PRODUCTION_SERVING,
)
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths
from sentientos.control_plane_kernel import AuthorityClass

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_activated_model_serving_controller"
EFFECTS = (
    "authenticated_current_hardened_activation_state_read",
    "exact_current_activation_receipt_read",
    "exact_authoritative_deployed_catalog_proof_read",
    "exact_hardened_local_model_commissioning_receipt_read",
    "exact_activated_artifact_identity_and_bytes_read",
    "exact_activated_runtime_identity_read",
    "bounded_exact_activated_model_load",
    "authoritative_serving_session_bind",
    "stale_serving_session_invalidation",
    "local_model_serving_session_receipt_write",
)
GOAL = (
    "Establish production serving from authenticated current hardened activation state; "
    "require current catalog provenance and exact artifact and runtime identity; require "
    "activation-change invalidation and separate local model inference."
)


def request(**changes: object) -> PlannerRequest:
    values: dict[str, object] = {
        "task_name": "admit activated model consumer authority",
        "task_goal": GOAL,
        "subsystem_kind": "local_model_chat",
        "capability_id": LOCAL_MODEL_PRODUCTION_SERVING,
        "authority_principal": PRINCIPAL,
        "requested_effects": EFFECTS,
        "commit_title": "[codex:model-serving] admit activated-model consumer authority",
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


def test_serving_definition_is_eligible_but_non_effectful() -> None:
    definition = AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_SERVING]
    assert definition.principal_kinds == frozenset({PRINCIPAL})
    assert definition.required_effects == frozenset(EFFECTS)
    assert len(EFFECTS) == len(set(EFFECTS))
    assert plan_codex_task_scaffold_paths(request()).status == "ready"
    result = bootstrap()
    assert result.status in {"ready", "ready_with_warnings"}
    assert result.planner_result_summary["authority_definition_eligibility_only"] is True
    assert result.planner_result_summary["capability_granted"] is False
    for effect in (
        "model_constructed", "model_loaded", "serving_started", "chat_integrated",
        "boot_integrated", "inference_performed", "control_plane_admission",
    ):
        assert effect not in result.planner_result_summary


@pytest.mark.parametrize("missing", (
    "authenticated current hardened activation state", "current catalog provenance",
    "exact artifact and runtime identity", "activation-change invalidation",
    "separate local model inference",
))
def test_each_currentness_precondition_is_required(missing: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(missing, "evidence"))


@pytest.mark.parametrize("phrase", (
    "authenticated current hardened activation state", "current catalog provenance",
    "exact artifact and runtime identity", "activation-change invalidation",
    "separate local model inference",
))
def test_negated_currentness_preconditions_are_denied(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, f"without {phrase}"))


@pytest.mark.parametrize("phrase", (
    "arbitrary activation", "arbitrary model path", "arbitrary artifact",
    "arbitrary runtime", "legacy activation path", "legacy autoload",
    "stale activation", "skip currentness", "retain stale model", "boot integration",
    "chat integration", "perform inference", "generation call", "provider invocation",
    "network authority", "tool authority", "memory authority", "action authority",
    "repository mutation", "self-grant",
))
def test_forbidden_consumer_scope_is_denied(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(task_goal=f"{GOAL} Request {phrase}.")


def test_inexact_effects_wrong_principal_and_wrong_subsystem_are_denied() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="model_distribution")
    assert "authority_principal_not_admitted" in blockers(
        authority_principal="deterministic_local_model_activation_controller")
    for effects in (EFFECTS[:-1], EFFECTS + ("generation_call",), EFFECTS + (EFFECTS[0],)):
        assert "authority_effect_surface_not_exact" in blockers(requested_effects=effects)


def test_serving_class_and_registry_preserve_independent_inference_authority() -> None:
    assert AuthorityClass.MODEL_SERVING not in {
        AuthorityClass.MODEL_ACTIVATION,
        AuthorityClass.MODEL_COMMISSIONING,
        AuthorityClass.MODEL_ARTIFACT_ACQUISITION,
        AuthorityClass.LOCAL_MODEL_INFERENCE,
    }
    record = build_default_capability_registry().by_id()[LOCAL_MODEL_PRODUCTION_SERVING]
    assert record.status == "partial"
    assert record.authority_level == "eligibility_only"
    assert "model construction and loading" in record.deferred_surfaces
    assert "inference" in record.deferred_surfaces
    assert "serving admission grants inference authority" in record.forbidden_implications


def test_activation_definition_remains_selection_only_and_separate() -> None:
    activation = AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_ACTIVATION]
    assert activation.principal_kinds == frozenset({"deterministic_local_model_activation_controller"})
    assert "model load" in activation.forbidden_goal_phrases
    assert "serving" in activation.forbidden_goal_phrases
    assert "inference" in activation.forbidden_goal_phrases
