from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    MAINTENANCE_AUTHORITY_CONTINUITY,
    MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING,
    MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING_DEFINITION,
    MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING_OPERATOR_APPROVAL,
    MAINTENANCE_RESIDENT_RUNTIME_ADOPTION,
    MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION,
    TaskAuthorityDefinition,
    authority_admission_blockers,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)

pytestmark = pytest.mark.no_legacy_skip

TASK = "register_maintenance_initial_posix_resident_commissioning_authority"
CAPABILITY = MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING
DEFINITION = MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING_DEFINITION
PRINCIPAL = "deterministic_maintenance_initial_posix_resident_commissioning_controller"
EFFECTS = tuple(sorted(DEFINITION.required_effects))
GOAL = ". ".join(DEFINITION.required_goal_phrases) + "."


def blockers(*, goal: str = GOAL, effects: tuple[str, ...] = EFFECTS,
             subsystem: str = "maintenance", principal: str = PRINCIPAL) -> tuple[str, ...]:
    return authority_admission_blockers(
        capability_id=CAPABILITY, subsystem_kind=subsystem,
        principal_kind=principal, requested_effects=effects, task_goal=goal,
    )


def catalog_without_definition() -> Mapping[str, TaskAuthorityDefinition]:
    return {key: value for key, value in AUTHORITY_DEFINITIONS.items() if key != CAPABILITY}


def registration(**changes: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": TASK,
        "definitions": [DEFINITION],
        "operator_approval": dict(MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING_OPERATOR_APPROVAL),
        "requested_capability_id": "",
        "authority_principal": "",
        "requested_effects": (),
        "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "sentientos/capability_registry.py",
            "tests/test_maintenance_initial_posix_resident_commissioning_capability_admission.py",
            "docs/development/maintenance_initial_posix_resident_commissioning_authority.md",
        ),
    }
    artifact.update(changes)
    return artifact


def test_definition_is_structurally_exact_and_future_admission_succeeds() -> None:
    assert DEFINITION.capability_id == CAPABILITY
    assert DEFINITION.subsystem_kinds == frozenset({"maintenance"})
    assert DEFINITION.principal_kinds == frozenset({PRINCIPAL})
    assert len(DEFINITION.required_effects) == 13
    assert blockers() == ()


def test_digest_bound_registration_adds_exactly_one_definition_without_effect() -> None:
    catalog = catalog_without_definition()
    approval = dict(MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING_OPERATOR_APPROVAL)
    assert authority_definition_digest(DEFINITION) == approval["approved_definition_digest"]
    assert operator_approval_evidence_digest(approval) == approval["evidence_digest"]
    result = register_authority_definition(registration(), authority_definitions=catalog)
    assert result.status == "authority_definition_registered"
    assert result.definition_registered
    assert set(result.authority_definitions) == set(catalog) | {CAPABILITY}
    assert result.capability_granted is False
    assert result.effect_performed is False
    assert result.runtime_mutation_performed is False
    assert result.runtime_authority is None


def test_registration_cannot_request_the_capability_it_defines() -> None:
    artifact = registration(
        requested_capability_id=CAPABILITY,
        authority_principal=PRINCIPAL,
        requested_effects=EFFECTS,
    )
    result = register_authority_definition(artifact, authority_definitions=catalog_without_definition())
    assert "authority_definition_registration_cannot_request_capability" in result.blocker_codes
    assert not result.definition_registered


def test_registration_rejects_runtime_mutation_and_definition_drift() -> None:
    assert "authority_definition_registration_runtime_mutation_forbidden" in register_authority_definition(
        registration(runtime_mutations=("launch_sentientosd",)),
        authority_definitions=catalog_without_definition(),
    ).blocker_codes
    assert not register_authority_definition(
        registration(definitions=[replace(DEFINITION, purpose="changed")]),
        authority_definitions=catalog_without_definition(),
    ).definition_registered


def test_future_admission_requires_exact_subsystem_principal_and_effect_set() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem="runtime_supervision")
    assert "authority_principal_not_admitted" in blockers(principal="sentientosd")
    assert "authority_effect_surface_not_exact" in blockers(effects=EFFECTS[:-1])
    assert "authority_effect_surface_not_exact" in blockers(effects=EFFECTS + ("extra_effect",))


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_each_required_goal_phrase_must_be_present_and_affirmative(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(goal=GOAL.replace(phrase, ""))
    assert "authority_goal_missing_required_precondition" in blockers(
        goal=GOAL.replace(phrase, f"without {phrase}")
    )


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_each_forbidden_future_scope_is_rejected(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(
        goal=f"{GOAL} Request {phrase}."
    )


def test_registry_reports_contract_only_and_runtime_commissioning_deferred() -> None:
    record = build_default_capability_registry().by_id()[CAPABILITY]
    assert record.status == "partial"
    assert record.authority_level == "contract_only"
    assert record.requires_control_plane_admission
    assert record.requires_operator_approval
    assert record.requires_audit_receipt
    assert "exact capability definition" in record.implemented_surfaces
    for surface in (
        "commissioning manifest implementation", "generation-zero creation",
        "external custody creation", "continuity-policy creation",
        "initial resident launch", "initial launch provenance",
        "resident commissioning receipt", "live POSIX commissioning evidence",
        "first real production post-adoption campaign",
    ):
        assert surface in record.deferred_surfaces


def test_existing_downstream_authority_definitions_remain_distinct() -> None:
    assert AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY].capability_id == MAINTENANCE_AUTHORITY_CONTINUITY
    assert AUTHORITY_DEFINITIONS[MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION].capability_id == MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION
    resident = AUTHORITY_DEFINITIONS[MAINTENANCE_RESIDENT_RUNTIME_ADOPTION]
    assert "bounded_exact_sentientosd_self_exec" in resident.required_effects
    assert "bounded_exact_initial_sentientosd_launch" not in resident.required_effects
    assert "bounded_exact_sentientosd_self_exec" not in DEFINITION.required_effects
    assert not Path("sentientos/maintenance_initial_posix_resident_commissioning.py").exists()

