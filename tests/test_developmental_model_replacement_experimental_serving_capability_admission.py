from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING,
    DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_DEFINITION,
    DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_OPERATOR_APPROVAL,
    LOCAL_MODEL_PRODUCTION_ACTIVATION,
    LOCAL_MODEL_PRODUCTION_SERVING,
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    TaskAuthorityDefinition,
    authority_admission_blockers,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)

pytestmark = pytest.mark.no_legacy_skip

TASK = "register_developmental_model_replacement_experimental_serving_authority"
DEFINITION = DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_DEFINITION
EFFECTS = tuple(sorted(DEFINITION.required_effects))
GOAL = ". ".join(DEFINITION.required_goal_phrases) + "."


def blockers(*, goal: str = GOAL, effects: tuple[str, ...] = EFFECTS,
             subsystem: str = "local_model_chat",
             principal: str = "deterministic_developmental_model_replacement_experimental_serving_controller") -> tuple[str, ...]:
    return authority_admission_blockers(
        capability_id=DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING,
        subsystem_kind=subsystem, principal_kind=principal,
        requested_effects=effects, task_goal=goal,
    )


def catalog_without_definition() -> Mapping[str, TaskAuthorityDefinition]:
    return {key: value for key, value in AUTHORITY_DEFINITIONS.items()
            if key != DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING}


def registration(**changes: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": TASK,
        "definitions": [DEFINITION],
        "operator_approval": dict(DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_OPERATOR_APPROVAL),
        "requested_capability_id": "", "authority_principal": "",
        "requested_effects": (), "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "tests/test_developmental_model_replacement_experimental_serving_capability_admission.py",
            "docs/development/developmental_model_replacement_experimental_serving_authority.md",
        ),
    }
    artifact.update(changes)
    return artifact


def test_exact_definition_shape_and_future_goal_eligibility() -> None:
    assert DEFINITION.capability_id == DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING
    assert DEFINITION.subsystem_kinds == frozenset({"local_model_chat"})
    assert DEFINITION.principal_kinds == frozenset({
        "deterministic_developmental_model_replacement_experimental_serving_controller"
    })
    assert len(DEFINITION.required_effects) == 8
    assert set(EFFECTS) == set(DEFINITION.required_effects)
    assert not any("inference" in effect or "activation" in effect or
                   "production_serving" in effect for effect in EFFECTS)
    assert blockers() == ()


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_effect_surface_is_exact_and_duplicate_free(mutation: str) -> None:
    effects = EFFECTS[:-1] if mutation == "missing" else EFFECTS + (
        ("extra_effect",) if mutation == "extra" else (EFFECTS[0],)
    )
    assert "authority_effect_surface_not_exact" in blockers(effects=effects)


def test_wrong_subsystem_and_principal_fail() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem="maintenance")
    assert "authority_principal_not_admitted" in blockers(principal="other_controller")


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_each_required_phrase_must_be_affirmative(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, ""))
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, f"without {phrase}"))


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_each_forbidden_scope_fails(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(goal=f"{GOAL} Request {phrase}.")


def test_digest_bound_registration_is_definition_only() -> None:
    digest = authority_definition_digest(DEFINITION)
    approval = dict(DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_OPERATOR_APPROVAL)
    assert digest == "b48ad4ae9622f31f5b49f926d9f295dbb5f0154a411204fe06040fef4a18638c"
    assert approval["approved_capability_id"] == DEFINITION.capability_id
    assert approval["approved_definition_digest"] == digest
    assert approval["approved_task_name"] == TASK
    assert operator_approval_evidence_digest(approval) == approval["evidence_digest"]
    result = register_authority_definition(registration(), authority_definitions=catalog_without_definition())
    assert result.definition_registered is True
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None


@pytest.mark.parametrize("mutation", ["identity", "digest", "definition", "duplicate"])
def test_registration_mutations_and_duplicate_fail(mutation: str) -> None:
    artifact = registration()
    catalog = catalog_without_definition()
    if mutation == "identity":
        artifact["operator_approval"] = {**DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_OPERATOR_APPROVAL,
                                         "operator_identity_label": "changed"}
    elif mutation == "digest":
        artifact["operator_approval"] = {**DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_OPERATOR_APPROVAL,
                                         "evidence_digest": "0" * 64}
    elif mutation == "definition":
        artifact["definitions"] = [replace(DEFINITION, purpose="changed")]
    else:
        catalog = AUTHORITY_DEFINITIONS
    assert not register_authority_definition(artifact, authority_definitions=catalog).definition_registered


def test_registration_has_no_runtime_effect_surface() -> None:
    import sentientos.codex_task_authority_admission as admission
    assert "RuntimeGrantAuthority" not in register_authority_definition.__code__.co_names
    assert "RuntimeAdmissionAuthority" not in register_authority_definition.__code__.co_names
    assert Path("sentientos/developmental_model_replacement_experimental_serving.py").is_file()
    for name in ("load_model", "infer", "activate", "ProductionServingController"):
        assert name not in register_authority_definition.__code__.co_names
    assert not hasattr(admission, "developmental_model_replacement_experimental_serving_controller")


def test_existing_authorities_and_production_serving_invariant_are_preserved() -> None:
    assert authority_definition_digest(AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_ACTIVATION]) == "3f32ffb9d66d3bf097a46e65370961fed257f66fe5a3f13d1e9a6709e677527f"
    assert authority_definition_digest(AUTHORITY_DEFINITIONS[LOCAL_MODEL_PRODUCTION_SERVING]) == "4160ea3f124944bff8dc3339eee4d2bb6705d209fdbd6b8f7274c12a9dc2f94d"
    assert authority_definition_digest(AUTHORITY_DEFINITIONS[RESIDENT_DEVELOPMENTAL_WRITEBACK]) == "a263a62ee13570a1dd11fc3d9bf25f3d28f8d5e75eadea6ea0dc4000c2252cd6"
    source = Path("sentientos/local_model_production_serving.py").read_text(encoding="utf-8")
    assert "current_hardened_activation_invalid" in source


def test_governed_invoker_gap_is_closed_by_runtime_task() -> None:
    authority = Path("sentientos/local_model_authority.py").read_text(encoding="utf-8")
    invocation = Path("sentientos/governed_local_model_invocation.py").read_text(encoding="utf-8")
    purpose = "resident_developmental_model_replacement_experiment"
    assert purpose in authority
    supported = invocation.split("SUPPORTED_PURPOSES =", 1)[1].split("}", 1)[0]
    assert purpose in supported
