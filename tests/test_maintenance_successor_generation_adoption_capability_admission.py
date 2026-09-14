from pathlib import Path

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    MAINTENANCE_AUTHORITY_CONTINUITY,
    MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION,
    MAINTENANCE_WAKE_DAEMON_ADOPTION,
    authority_admission_blockers,
)

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_maintenance_successor_generation_adoption_controller"
EFFECTS = (
    "exact_maintenance_continuity_policy_read",
    "exact_successor_maintenance_authority_generation_read",
    "exact_maintenance_authority_continuity_receipt_read",
    "exact_current_maintenance_wake_adoption_state_read",
    "successor_maintenance_configuration_generation_write",
    "bounded_maintenance_wake_owner_generation_handoff",
    "maintenance_successor_generation_adoption_receipt_write",
    "read_only_maintenance_successor_generation_health_projection",
)
GOAL = (
    "Implement bounded wake owner handoff to a verified successor authority generation "
    "with an exact continuity receipt under the same lineage authority."
)
DEFINITION = AUTHORITY_DEFINITIONS[MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION]


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = {
        "capability_id": MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION,
        "subsystem_kind": "maintenance",
        "principal_kind": PRINCIPAL,
        "requested_effects": EFFECTS,
        "task_goal": GOAL,
    }
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_canonical_new_capability_eligibility_is_exact_and_non_granting() -> None:
    assert MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION == "maintenance_successor_generation_adoption"
    assert DEFINITION.capability_id == MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION
    assert DEFINITION.subsystem_kinds == frozenset({"maintenance"})
    assert DEFINITION.principal_kinds == frozenset({PRINCIPAL})
    assert DEFINITION.required_effects == frozenset(EFFECTS)
    assert blockers() == ()
    assert not hasattr(DEFINITION, "capability_granted")


def test_wrong_subsystem_and_principal_are_denied() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="developer_workflow_metadata")
    assert "authority_principal_not_admitted" in blockers(principal_kind="sentientosd")


def test_missing_extra_and_duplicate_effects_are_denied() -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS[:-1])
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + ("git_mutation",))
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + (EFFECTS[0],))


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_every_required_goal_phrase_is_independently_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, "required canonical evidence")
    )


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
@pytest.mark.parametrize("disclaimer", ("without", "not"))
def test_negated_or_disclaimed_required_phrase_is_denied(phrase: str, disclaimer: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, f"{disclaimer} {phrase}")
    )


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_future_scope_is_denied(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(task_goal=f"{GOAL} Request {phrase}.")


def test_canonical_future_handoff_goal_is_admitted() -> None:
    assert blockers(task_goal=GOAL) == ()


def test_registry_reports_implemented_bounded_truth() -> None:
    record = build_default_capability_registry().by_id()[MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION]
    assert record.category == MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION
    assert record.status == "implemented"
    assert record.authority_level == "bounded_in_process_runner"
    assert record.requires_control_plane_admission and record.requires_audit_receipt
    assert record.requires_operator_approval
    assert "automatic continuity derive-next invocation" in record.deferred_surfaces
    assert "eligibility grants runtime authority" in record.forbidden_implications


def test_successor_adoption_runtime_module_is_implemented() -> None:
    assert Path("sentientos/maintenance_successor_generation_adoption.py").exists()
    assert Path("scripts/maintenance_successor_generation_adoption.py").exists()


def test_existing_wake_daemon_authority_semantics_are_preserved() -> None:
    wake = AUTHORITY_DEFINITIONS[MAINTENANCE_WAKE_DAEMON_ADOPTION]
    assert wake.principal_kinds == frozenset({"deterministic_maintenance_wake_daemon_controller"})
    assert wake.required_effects == frozenset({
        "exact_operator_wake_adoption_configuration_read",
        "exact_maintenance_wake_configuration_read",
        "bounded_maintenance_wake_cycle_invoke",
        "bounded_maintenance_wake_daemon_lifecycle",
        "maintenance_wake_daemon_evidence_write",
        "read_only_maintenance_wake_health_projection",
    })
    assert "automatic authority renewal" in wake.forbidden_goal_phrases


def test_continuity_remains_derivation_only_and_rebinding_deferred() -> None:
    continuity = AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY]
    assert continuity.principal_kinds == frozenset({"deterministic_maintenance_authority_continuity_controller"})
    assert "bounded_maintenance_wake_owner_generation_handoff" not in continuity.required_effects
    record = build_default_capability_registry().by_id()[MAINTENANCE_AUTHORITY_CONTINUITY]
    assert "automatic daemon rebinding" in record.deferred_surfaces
