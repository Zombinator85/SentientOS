from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_OPERATOR_APPROVAL,
    authority_admission_blockers,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)

pytestmark = pytest.mark.no_legacy_skip

TASK = "register_resident_developmental_writeback_authority"
GOAL = (
    "Implement one canonical resident path over selected evidence that performs bounded "
    "developmental writeback with source-bound transformation provenance, preserves the "
    "invariant memory is not current truth; supports subsequent retrieval and measured "
    "changed cognition, and preserve canonical explicit user retention."
)
EFFECTS = tuple(sorted(RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.required_effects))


def blockers(*, goal: str = GOAL, effects: tuple[str, ...] = EFFECTS,
             subsystem: str = "memory_context_reflection",
             principal: str = "deterministic_resident_developmental_writeback_controller") -> tuple[str, ...]:
    return authority_admission_blockers(
        capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK,
        subsystem_kind=subsystem,
        principal_kind=principal,
        requested_effects=effects,
        task_goal=goal,
    )


def registration(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": TASK,
        "definitions": [RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION],
        "operator_approval": dict(RESIDENT_DEVELOPMENTAL_WRITEBACK_OPERATOR_APPROVAL),
        "requested_capability_id": "", "authority_principal": "",
        "requested_effects": (), "runtime_mutations": (),
        "changed_paths": ("sentientos/codex_task_authority_admission.py",),
    }
    value.update(changes)
    return value


def test_exact_definition_and_future_implementation_goal_are_eligible() -> None:
    definition = RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
    assert definition.capability_id == RESIDENT_DEVELOPMENTAL_WRITEBACK
    assert definition.subsystem_kinds == frozenset({"memory_context_reflection"})
    assert definition.principal_kinds == frozenset({"deterministic_resident_developmental_writeback_controller"})
    assert blockers() == ()


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_effect_surface_must_be_exact_and_duplicate_free(mutation: str) -> None:
    effects = EFFECTS[:-1] if mutation == "missing" else EFFECTS + (("extra_effect",) if mutation == "extra" else (EFFECTS[0],))
    assert "authority_effect_surface_not_exact" in blockers(effects=effects)


def test_wrong_subsystem_and_principal_fail() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem="maintenance")
    assert "authority_principal_not_admitted" in blockers(principal="other_controller")


@pytest.mark.parametrize("phrase", RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.required_goal_phrases)
def test_every_required_goal_phrase_is_required_and_must_be_affirmative(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, ""))
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, f"without {phrase}"))


@pytest.mark.parametrize("phrase", RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_scope_phrase_fails(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(goal=f"{GOAL} Also request {phrase}.")


def test_digest_bound_registration_is_definition_only() -> None:
    definition_digest = authority_definition_digest(RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION)
    approval = dict(RESIDENT_DEVELOPMENTAL_WRITEBACK_OPERATOR_APPROVAL)
    assert definition_digest == "a263a62ee13570a1dd11fc3d9bf25f3d28f8d5e75eadea6ea0dc4000c2252cd6"
    assert approval["approved_definition_digest"] == definition_digest
    assert operator_approval_evidence_digest(approval) == approval["evidence_digest"]
    catalog = {key: value for key, value in AUTHORITY_DEFINITIONS.items() if key != RESIDENT_DEVELOPMENTAL_WRITEBACK}
    result = register_authority_definition(registration(), authority_definitions=catalog)
    assert result.definition_registered is True
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None


def test_approval_mutation_or_definition_digest_mismatch_fails() -> None:
    catalog = {key: value for key, value in AUTHORITY_DEFINITIONS.items() if key != RESIDENT_DEVELOPMENTAL_WRITEBACK}
    approval = {**RESIDENT_DEVELOPMENTAL_WRITEBACK_OPERATOR_APPROVAL, "operator_identity_label": "changed"}
    assert register_authority_definition(registration(operator_approval=approval), authority_definitions=catalog).definition_registered is False
    changed = replace(RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION, purpose="changed")
    assert register_authority_definition(registration(definitions=[changed]), authority_definitions=catalog).definition_registered is False


def test_registry_truth_is_bounded_runtime_and_still_non_granting() -> None:
    record = build_default_capability_registry().by_id()[RESIDENT_DEVELOPMENTAL_WRITEBACK]
    assert (record.status, record.authority_level) == ("partial", "bounded_state_transition")
    assert record.requires_control_plane_admission and record.requires_audit_receipt
    assert not record.requires_operator_approval


def test_runtime_writer_exists_and_existing_boundaries_are_unchanged() -> None:
    import sentientos.canonical_memory as canonical_memory
    import sentientos.governed_local_model_invocation as local_model
    import sentientos.world_state_board as world_state

    assert __import__("pathlib").Path("sentientos/resident_developmental_writeback.py").exists()
    assert not hasattr(canonical_memory, "resident_developmental_writeback")
    assert not hasattr(local_model, "resident_developmental_writeback")
    assert not hasattr(world_state, "resident_developmental_writeback")
