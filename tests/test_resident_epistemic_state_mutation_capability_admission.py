from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION as DEFINITION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_OPERATOR_APPROVAL as APPROVAL,
    TaskAuthorityDefinition,
    authority_admission_blockers,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)
from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner

pytestmark = pytest.mark.no_legacy_skip

TASK = "register_resident_epistemic_state_mutation_definition"
PRINCIPAL = "deterministic_resident_epistemic_state_controller"
EFFECTS = tuple(sorted(DEFINITION.required_effects))
GOAL = ". ".join(DEFINITION.required_goal_phrases) + "."


def catalog_without_definition() -> Mapping[str, TaskAuthorityDefinition]:
    return {
        key: value for key, value in AUTHORITY_DEFINITIONS.items()
        if key != RESIDENT_EPISTEMIC_STATE_MUTATION
    }


def registration(**changes: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": TASK,
        "definitions": [DEFINITION],
        "operator_approval": dict(APPROVAL),
        "requested_capability_id": "",
        "authority_principal": "",
        "requested_effects": (),
        "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "tests/test_resident_epistemic_state_mutation_capability_admission.py",
            "docs/development/resident_epistemic_state_mutation_authority.md",
        ),
    }
    artifact.update(changes)
    return artifact


def blockers(*, goal: str = GOAL, effects: tuple[str, ...] = EFFECTS,
             principal: str = PRINCIPAL) -> tuple[str, ...]:
    return authority_admission_blockers(
        capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION,
        subsystem_kind="epistemics",
        principal_kind=principal,
        requested_effects=effects,
        task_goal=goal,
    )


def test_exact_definition_and_future_admission_surface() -> None:
    assert DEFINITION.capability_id == "resident_epistemic_state_mutation"
    assert DEFINITION.subsystem_kinds == frozenset({"epistemics"})
    assert DEFINITION.principal_kinds == frozenset({PRINCIPAL})
    assert DEFINITION.required_effects == frozenset({
        "exact_epistemic_proposition_read",
        "exact_epistemic_current_state_read",
        "exact_epistemic_evidence_source_artifact_read",
        "exact_epistemic_evidence_binding_validation",
        "bounded_epistemic_evidence_binding_append",
        "exact_epistemic_update_candidate_read",
        "deterministic_epistemic_update_candidate_validation",
        "exact_epistemic_predecessor_state_compare_and_swap",
        "bounded_epistemic_state_generation_append",
        "bounded_epistemic_update_event_append",
        "epistemic_mutation_receipt_write",
        "read_only_epistemic_post_mutation_verification",
    })
    assert not any("*" in value for value in (*DEFINITION.principal_kinds, *EFFECTS))
    assert blockers() == ()


def test_digest_bound_registration_grants_and_performs_nothing() -> None:
    digest = authority_definition_digest(DEFINITION)
    approval = dict(APPROVAL)
    assert digest == "5fef1ee3908208659b6c72ec09bea38d7e1e4918f4b01e12df5b9726abf2392a"
    assert approval["approved_capability_id"] == RESIDENT_EPISTEMIC_STATE_MUTATION
    assert approval["approved_definition_digest"] == digest
    assert approval["approved_task_name"] == TASK
    assert operator_approval_evidence_digest(approval) == approval["evidence_digest"]
    result = register_authority_definition(
        registration(), authority_definitions=catalog_without_definition()
    )
    assert result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.capability_granted is False
    assert result.runtime_authority is None
    assert result.effect_performed is False
    assert result.runtime_mutation_performed is False


def test_registration_request_cannot_request_or_exercise_definition() -> None:
    cases = [
        ("requested_capability_id", RESIDENT_EPISTEMIC_STATE_MUTATION,
         "authority_definition_registration_cannot_request_capability"),
        ("authority_principal", PRINCIPAL,
         "authority_definition_registration_cannot_request_capability"),
        ("requested_effects", EFFECTS,
         "authority_definition_registration_cannot_request_capability"),
        ("runtime_mutations", ("epistemic_state",),
         "authority_definition_registration_runtime_mutation_forbidden"),
    ]
    for field, value, blocker in cases:
        result = register_authority_definition(
            registration(**{field: value}),
            authority_definitions=catalog_without_definition(),
        )
        assert blocker in result.blocker_codes
        assert result.definition_registered is False


@pytest.mark.parametrize("field", [
    "approved_capability_id", "approved_definition_digest",
    "approved_task_name", "evidence_digest",
])
def test_approval_binding_mismatch_fails(field: str) -> None:
    approval = dict(APPROVAL)
    approval[field] = "wrong"
    result = register_authority_definition(
        registration(operator_approval=approval),
        authority_definitions=catalog_without_definition(),
    )
    assert result.definition_registered is False


@pytest.mark.parametrize("principal", ["*", "sentientosd", "model", "agent", "system"])
def test_broad_or_generic_principal_is_not_admitted(principal: str) -> None:
    assert "authority_principal_not_admitted" in blockers(principal=principal)


@pytest.mark.parametrize("effect", [
    "filesystem_mutation", "network_authority", "provider_invocation",
    "model_invocation", "tool_invocation", "memory_mutation", "host_actuation",
])
def test_broad_effect_is_not_admitted(effect: str) -> None:
    assert "authority_effect_surface_not_exact" in blockers(effects=EFFECTS + (effect,))


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_every_required_goal_phrase_is_affirmative_and_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        goal=GOAL.replace(phrase, "")
    )
    assert "authority_goal_missing_required_precondition" in blockers(
        goal=GOAL.replace(phrase, f"without {phrase}")
    )


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_goal_phrase_is_rejected(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(
        goal=f"{GOAL} Request {phrase}."
    )


def test_registration_creates_no_epistemic_custody_or_runtime_bridge(tmp_path: Path) -> None:
    owner = PersistentEpistemicStateOwner(tmp_path / "epistemic", allowed_namespaces=("test",))
    before = {kind: tuple((owner.root / kind).iterdir()) for kind in (
        "propositions", "bindings", "states", "updates",
    )}
    result = register_authority_definition(
        registration(), authority_definitions=catalog_without_definition()
    )
    after = {kind: tuple((owner.root / kind).iterdir()) for kind in before}
    assert result.definition_registered and before == after
    assert all(not paths for paths in after.values())
    assert not Path("sentientos/resident_epistemic_state_mutation.py").exists()
    assert "issue_runtime_admission" not in register_authority_definition.__code__.co_names


def test_changed_definition_fails_exact_approval_binding() -> None:
    changed = replace(DEFINITION, purpose="changed")
    result = register_authority_definition(
        registration(definitions=[changed]),
        authority_definitions=catalog_without_definition(),
    )
    assert result.definition_registered is False
