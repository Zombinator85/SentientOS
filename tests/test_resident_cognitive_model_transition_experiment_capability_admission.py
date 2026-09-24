from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, AUTHORITY_DEFINITION_REGISTRATION,
    DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING,
    LOCAL_MODEL_PRODUCTION_ACTIVATION, RESIDENT_COGNITIVE_MODEL_SERVING,
    RESIDENT_COGNITIVE_MODEL_TRANSITION_EXPERIMENT,
    RESIDENT_COGNITIVE_MODEL_TRANSITION_EXPERIMENT_DEFINITION as DEFINITION,
    RESIDENT_COGNITIVE_MODEL_TRANSITION_EXPERIMENT_OPERATOR_APPROVAL as APPROVAL,
    RESIDENT_DEVELOPMENTAL_WRITEBACK, TaskAuthorityDefinition,
    authority_admission_blockers, authority_definition_digest,
    operator_approval_evidence_digest, register_authority_definition,
)

pytestmark = pytest.mark.no_legacy_skip
TASK = "register_resident_cognitive_model_transition_experiment_authority"
EFFECTS = tuple(sorted(DEFINITION.required_effects))
GOAL = ". ".join(DEFINITION.required_goal_phrases) + "."


def blockers(*, goal: str = GOAL, effects: tuple[str, ...] = EFFECTS,
             subsystem: str = "memory_context_reflection",
             principal: str = "deterministic_resident_cognitive_model_transition_controller") -> tuple[str, ...]:
    return authority_admission_blockers(
        capability_id=RESIDENT_COGNITIVE_MODEL_TRANSITION_EXPERIMENT,
        subsystem_kind=subsystem, principal_kind=principal,
        requested_effects=effects, task_goal=goal,
    )


def catalog_without_definition() -> Mapping[str, TaskAuthorityDefinition]:
    return {key: value for key, value in AUTHORITY_DEFINITIONS.items()
            if key != RESIDENT_COGNITIVE_MODEL_TRANSITION_EXPERIMENT}


def registration(**changes: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION, "task_name": TASK,
        "definitions": [DEFINITION], "operator_approval": dict(APPROVAL),
        "requested_capability_id": "", "authority_principal": "",
        "requested_effects": (), "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "tests/test_resident_cognitive_model_transition_experiment_capability_admission.py",
            "docs/development/resident_cognitive_model_transition_experiment_authority.md",
        ),
    }
    artifact.update(changes)
    return artifact


def test_exact_definition_shape_and_future_request_is_eligible() -> None:
    assert DEFINITION.capability_id == RESIDENT_COGNITIVE_MODEL_TRANSITION_EXPERIMENT
    assert DEFINITION.subsystem_kinds == frozenset({"memory_context_reflection"})
    assert DEFINITION.principal_kinds == frozenset({"deterministic_resident_cognitive_model_transition_controller"})
    assert len(DEFINITION.required_effects) == len(EFFECTS) == 14
    assert blockers() == ()
    forbidden_effect_fragments = ("activation_mutation", "model_load", "inference_request", "developmental_history_append")
    assert not any(fragment in effect for effect in EFFECTS for fragment in forbidden_effect_fragments)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_effect_surface_is_exact_and_duplicate_free(mutation: str) -> None:
    effects = EFFECTS[:-1] if mutation == "missing" else EFFECTS + (("extra_effect",) if mutation == "extra" else (EFFECTS[0],))
    assert "authority_effect_surface_not_exact" in blockers(effects=effects)


def test_wrong_subsystem_and_principal_fail() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem="local_model_chat")
    assert "authority_principal_not_admitted" in blockers(principal="other_controller")


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_every_required_affirmative_phrase_is_mandatory(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, ""))
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, f"without {phrase}"))


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_scope_blocks(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(goal=f"{GOAL} Request {phrase}.")


def test_digest_bound_registration_succeeds_and_grants_nothing() -> None:
    assert authority_definition_digest(DEFINITION) == "83f279d23060d6d378005590c0e0b1311efd826dab91fab1da8b02c090f73f88"
    assert APPROVAL["approved_capability_id"] == DEFINITION.capability_id
    assert APPROVAL["approved_definition_digest"] == authority_definition_digest(DEFINITION)
    assert APPROVAL["approved_task_name"] == TASK
    assert operator_approval_evidence_digest(APPROVAL) == APPROVAL["evidence_digest"]
    result = register_authority_definition(registration(), authority_definitions=catalog_without_definition())
    assert result.definition_registered
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None


@pytest.mark.parametrize("mutation", ["definition", "operator", "task", "evidence_digest", "duplicate"])
def test_registration_binding_mutations_fail(mutation: str) -> None:
    artifact = registration()
    catalog = catalog_without_definition()
    if mutation == "definition": artifact["definitions"] = [replace(DEFINITION, purpose="changed")]
    elif mutation == "operator": artifact["operator_approval"] = {**APPROVAL, "operator_identity_label": "changed"}
    elif mutation == "task": artifact["task_name"] = "changed"
    elif mutation == "evidence_digest": artifact["operator_approval"] = {**APPROVAL, "evidence_digest": "0" * 64}
    else: catalog = AUTHORITY_DEFINITIONS
    assert not register_authority_definition(artifact, authority_definitions=catalog).definition_registered


def test_existing_authorities_runtime_and_startup_binding_are_unchanged() -> None:
    expected = {
        LOCAL_MODEL_PRODUCTION_ACTIVATION: "3f32ffb9d66d3bf097a46e65370961fed257f66fe5a3f13d1e9a6709e677527f",
        RESIDENT_COGNITIVE_MODEL_SERVING: "7f56bbe762db49bde1ae119ad7db1a45a0bf05dcbc1fe262ef4f56812c63d67f",
        RESIDENT_DEVELOPMENTAL_WRITEBACK: "a263a62ee13570a1dd11fc3d9bf25f3d28f8d5e75eadea6ea0dc4000c2252cd6",
        DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING: "b48ad4ae9622f31f5b49f926d9f295dbb5f0154a411204fe06040fef4a18638c",
    }
    assert {key: authority_definition_digest(AUTHORITY_DEFINITIONS[key]) for key in expected} == expected
    assert not Path("sentientos/resident_cognitive_model_transition_experiment.py").exists()
    source = Path("sentientos/resident_cognitive_model_serving.py").read_text(encoding="utf-8")
    assert "expected_activation_state_digest" in source and "serving_operation_id" in source and "serving_config_digest" in source
    assert "exact_transition_stage_resident_serving_binding_write" in DEFINITION.required_effects
    assert "startup resident serving config mutation" in DEFINITION.forbidden_goal_phrases


def test_registration_has_no_runtime_transition_surface() -> None:
    import sentientos.codex_task_authority_admission as admission
    assert not hasattr(admission, "resident_cognitive_model_transition_controller")
    for name in ("quiesce", "activate", "load_model", "infer", "append_history", "write_transition_journal"):
        assert name not in register_authority_definition.__code__.co_names
