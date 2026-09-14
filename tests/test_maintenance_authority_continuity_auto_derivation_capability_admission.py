from pathlib import Path

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    MAINTENANCE_AUTHORITY_CONTINUITY,
    MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION,
    MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION,
    MAINTENANCE_WAKE_DAEMON_ADOPTION,
    authority_admission_blockers,
)

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_maintenance_authority_continuity_auto_derivation_controller"
EFFECTS = (
    "exact_maintenance_continuity_policy_read",
    "exact_prior_maintenance_authority_generation_read",
    "exact_completed_maintenance_generation_evidence_read",
    "exact_successor_repository_state_read",
    "bounded_successor_maintenance_authority_derive",
    "successor_maintenance_configuration_generation_write",
    "maintenance_authority_continuity_receipt_write",
    "exact_maintenance_successor_generation_adoption_state_read",
    "bounded_canonical_completed_maintenance_transition_discovery",
    "maintenance_authority_continuity_evidence_normalization_write",
    "bounded_maintenance_authority_continuity_auto_derivation_lifecycle",
    "maintenance_authority_continuity_auto_derivation_receipt_write",
    "read_only_maintenance_authority_continuity_auto_derivation_health_projection",
)
GOAL = (
    "Implement bounded automatic continuity derivation for the currently adopted "
    "maintenance generation after canonical successful maintenance closure proves an "
    "exact successor repository state with same or narrower authority."
)
DEFINITION = AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION]


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = {
        "capability_id": MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION,
        "subsystem_kind": "maintenance",
        "principal_kind": PRINCIPAL,
        "requested_effects": EFFECTS,
        "task_goal": GOAL,
    }
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_exact_new_capability_eligibility_is_non_granting() -> None:
    assert MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION == "maintenance_authority_continuity_auto_derivation"
    assert DEFINITION.capability_id == MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION
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
def test_each_affirmative_precondition_is_independently_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, "required canonical evidence")
    )


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_negated_required_preconditions_are_denied(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, f"without {phrase}")
    )


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_scope_is_denied(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(task_goal=f"{GOAL} Request {phrase}.")


def test_canonical_future_auto_derivation_goal_is_admitted() -> None:
    assert blockers() == ()


def test_registry_reports_scaffolded_eligibility_only_truth() -> None:
    record = build_default_capability_registry().by_id()[MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION]
    assert record.category == MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION
    assert record.status == "scaffolded"
    assert record.authority_level == "eligibility_only"
    assert record.requires_control_plane_admission
    assert record.requires_operator_approval
    assert record.requires_audit_receipt
    assert "in-process automatic derivation controller" in record.deferred_surfaces
    assert "eligibility is a grant" in record.forbidden_implications


def test_no_effectful_auto_derivation_runtime_module_exists() -> None:
    assert not Path("sentientos/maintenance_authority_continuity_auto_derivation.py").exists()
    assert not Path("scripts/maintenance_authority_continuity_auto_derivation.py").exists()


def test_existing_continuity_authority_is_unchanged() -> None:
    definition = AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY]
    assert definition.principal_kinds == frozenset({"deterministic_maintenance_authority_continuity_controller"})
    assert definition.required_effects == frozenset(EFFECTS[1:7])


def test_existing_successor_adoption_authority_is_unchanged_and_does_not_derive() -> None:
    definition = AUTHORITY_DEFINITIONS[MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION]
    assert definition.principal_kinds == frozenset({"deterministic_maintenance_successor_generation_adoption_controller"})
    source = Path("sentientos/maintenance_successor_generation_adoption.py").read_text(encoding="utf-8")
    assert "derive_next(" not in source
    assert "bounded_successor_maintenance_authority_derive" not in definition.required_effects


def test_wake_daemon_authority_is_unchanged() -> None:
    definition = AUTHORITY_DEFINITIONS[MAINTENANCE_WAKE_DAEMON_ADOPTION]
    assert definition.principal_kinds == frozenset({"deterministic_maintenance_wake_daemon_controller"})
    assert "automatic authority renewal" in definition.forbidden_goal_phrases


def test_documentation_separates_persistent_approval_and_resident_code() -> None:
    text = Path("docs/development/maintenance_authority_continuity_auto_derivation_authority.md").read_text(encoding="utf-8")
    assert "does not require renewed human approval for every N→N+1 derivation" in text
    assert "Automatic resident-code adoption remains a separate authority boundary" in text
