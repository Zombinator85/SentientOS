from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, AUTHORITY_DEFINITION_REGISTRATION,
    DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING,
    LOCAL_MODEL_PRODUCTION_ACTIVATION, LOCAL_MODEL_PRODUCTION_SERVING,
    RESIDENT_COGNITIVE_MODEL_SERVING,
    RESIDENT_COGNITIVE_MODEL_SERVING_DEFINITION as DEFINITION,
    RESIDENT_COGNITIVE_MODEL_SERVING_OPERATOR_APPROVAL as APPROVAL,
    TaskAuthorityDefinition, authority_admission_blockers,
    authority_definition_digest, operator_approval_evidence_digest,
    register_authority_definition,
)

pytestmark = pytest.mark.no_legacy_skip
TASK = "register_resident_cognitive_model_serving_authority"
EFFECTS = tuple(sorted(DEFINITION.required_effects))
GOAL = ". ".join(DEFINITION.required_goal_phrases) + "."


def blockers(*, goal: str = GOAL, effects: tuple[str, ...] = EFFECTS,
             subsystem: str = "local_model_chat",
             principal: str = "deterministic_resident_cognitive_model_serving_controller") -> tuple[str, ...]:
    return authority_admission_blockers(capability_id=RESIDENT_COGNITIVE_MODEL_SERVING,
        subsystem_kind=subsystem, principal_kind=principal,
        requested_effects=effects, task_goal=goal)


def catalog_without_definition() -> Mapping[str, TaskAuthorityDefinition]:
    return {key: value for key, value in AUTHORITY_DEFINITIONS.items()
            if key != RESIDENT_COGNITIVE_MODEL_SERVING}


def registration(**changes: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": TASK, "definitions": [DEFINITION],
        "operator_approval": dict(APPROVAL), "requested_capability_id": "",
        "authority_principal": "", "requested_effects": (), "runtime_mutations": (),
        "changed_paths": ("sentientos/codex_task_authority_admission.py",
            "tests/test_resident_cognitive_model_serving_capability_admission.py",
            "docs/development/resident_cognitive_model_serving_authority.md",
            "docs/architecture/sentientos_trajectory_and_missing_organs.md"),
    }
    artifact.update(changes)
    return artifact


def test_exact_definition_and_future_admission() -> None:
    assert DEFINITION.capability_id == "resident_cognitive_model_serving"
    assert DEFINITION.subsystem_kinds == frozenset({"local_model_chat"})
    assert DEFINITION.principal_kinds == frozenset({"deterministic_resident_cognitive_model_serving_controller"})
    assert len(DEFINITION.required_effects) == len(EFFECTS) == 12
    assert len(set(EFFECTS)) == 12
    assert not any("inference" in e or "activation_mutation" in e or "transition" in e for e in EFFECTS)
    assert blockers() == ()


@pytest.mark.parametrize("effects", [EFFECTS[:-1], EFFECTS + ("extra_effect",), EFFECTS + (EFFECTS[0],)])
def test_effect_surface_is_exact(effects: tuple[str, ...]) -> None:
    assert "authority_effect_surface_not_exact" in blockers(effects=effects)


def test_wrong_subsystem_and_principal_fail() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem="maintenance")
    assert "authority_principal_not_admitted" in blockers(principal="other_controller")


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_every_required_phrase_is_affirmative_and_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, ""))
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, f"without {phrase}"))


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_goal_fails(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(goal=f"{GOAL} Request {phrase}.")


def test_digest_bound_registration_grants_nothing() -> None:
    digest = authority_definition_digest(DEFINITION)
    approval = dict(APPROVAL)
    assert digest == "7f56bbe762db49bde1ae119ad7db1a45a0bf05dcbc1fe262ef4f56812c63d67f"
    assert approval["approved_capability_id"] == DEFINITION.capability_id
    assert approval["approved_definition_digest"] == digest
    assert approval["approved_task_name"] == TASK
    assert operator_approval_evidence_digest(approval) == approval["evidence_digest"]
    result = register_authority_definition(registration(), authority_definitions=catalog_without_definition())
    assert result.definition_registered is True
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None


@pytest.mark.parametrize("mutation", ["identity", "digest", "definition", "duplicate"])
def test_changed_approval_definition_and_duplicate_fail(mutation: str) -> None:
    artifact = registration(); catalog = catalog_without_definition()
    if mutation == "identity": artifact["operator_approval"] = {**APPROVAL, "operator_identity_label": "changed"}
    elif mutation == "digest": artifact["operator_approval"] = {**APPROVAL, "evidence_digest": "0" * 64}
    elif mutation == "definition": artifact["definitions"] = [replace(DEFINITION, purpose="changed")]
    else: catalog = AUTHORITY_DEFINITIONS
    assert not register_authority_definition(artifact, authority_definitions=catalog).definition_registered


def test_existing_authority_definitions_remain_exact() -> None:
    assert authority_definition_digest(AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_SERVING]) == "4160ea3f124944bff8dc3339eee4d2bb6705d209fdbd6b8f7274c12a9dc2f94d"
    assert authority_definition_digest(AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_ACTIVATION]) == "3f32ffb9d66d3bf097a46e65370961fed257f66fe5a3f13d1e9a6709e677527f"
    assert authority_definition_digest(AUTHORITY_DEFINITIONS[DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING]) == "b48ad4ae9622f31f5b49f926d9f295dbb5f0154a411204fe06040fef4a18638c"


def test_registration_does_not_claim_or_create_runtime_bridge() -> None:
    import sentientos.codex_task_authority_admission as admission
    assert Path("sentientos/resident_cognitive_model_serving.py").is_file()
    assert not hasattr(admission, "resident_cognitive_model_serving_controller")
    names = register_authority_definition.__code__.co_names
    assert all(name not in names for name in ("LocalModel", "load_model", "infer", "ProductionServingController"))
    source = Path("sentientosd.py").read_text(encoding="utf-8")
    assert "model = LocalModel.autoload()" in source
    assert "GovernedLocalModelInvoker(model=model, authority_map=" in source
