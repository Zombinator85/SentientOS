from pathlib import Path

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    MAINTENANCE_AUTHORITY_CONTINUITY,
    authority_admission_blockers,
)

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_maintenance_authority_continuity_controller"
EFFECTS = (
    "exact_prior_maintenance_authority_generation_read",
    "exact_completed_maintenance_generation_evidence_read",
    "exact_successor_repository_state_read",
    "bounded_successor_maintenance_authority_derive",
    "successor_maintenance_configuration_generation_write",
    "maintenance_authority_continuity_receipt_write",
)
GOAL = (
    "Implement bounded successor authority after a successful prior maintenance "
    "generation reaches an exact successor repository state while preserving same or "
    "narrower authority."
)
DEFINITION = AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY]


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = {
        "capability_id": MAINTENANCE_AUTHORITY_CONTINUITY,
        "subsystem_kind": "maintenance",
        "principal_kind": PRINCIPAL,
        "requested_effects": EFFECTS,
        "task_goal": GOAL,
    }
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_canonical_continuity_eligibility_is_admitted_without_grant() -> None:
    assert MAINTENANCE_AUTHORITY_CONTINUITY == "maintenance_authority_continuity"
    assert DEFINITION.capability_id == MAINTENANCE_AUTHORITY_CONTINUITY
    assert DEFINITION.subsystem_kinds == frozenset({"maintenance"})
    assert DEFINITION.principal_kinds == frozenset({PRINCIPAL})
    assert DEFINITION.required_effects == frozenset(EFFECTS)
    assert blockers() == ()
    assert not hasattr(DEFINITION, "capability_granted")


def test_wrong_subsystem_and_principal_reject() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="developer_workflow_metadata")
    assert "authority_principal_not_admitted" in blockers(principal_kind="sentientosd")


def test_missing_and_extra_effect_reject() -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS[:-1])
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + ("candidate_admission",))


def test_duplicate_effect_rejects() -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + (EFFECTS[0],))


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_each_required_precondition_is_independently_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, "required continuity evidence")
    )


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_negated_required_preconditions_do_not_admit(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, f"without {phrase}")
    )


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_future_scope_rejects(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(task_goal=f"{GOAL} Request {phrase}.")


def test_registry_truth_is_implemented_bounded_derivation() -> None:
    record = build_default_capability_registry().by_id()[MAINTENANCE_AUTHORITY_CONTINUITY]
    assert record.category == MAINTENANCE_AUTHORITY_CONTINUITY
    assert record.status == "implemented"
    assert record.authority_level == "bounded-orchestrator"
    assert record.requires_control_plane_admission and record.requires_audit_receipt
    assert "same-or-narrower inheritance contract" in record.implemented_surfaces
    assert "same-or-narrower successor activation profile derivation" in record.implemented_surfaces
    assert "automatic daemon rebinding" in record.deferred_surfaces


def test_bounded_controller_is_introduced_without_runtime_adoption() -> None:
    assert Path("sentientos/maintenance_authority_continuity.py").exists()
    assert Path("scripts/maintenance_authority_continuity.py").exists()
    module = __import__("sentientos.codex_task_authority_admission", fromlist=["x"])
    for effectful_name in ("derive_successor", "write_configuration", "rebind_daemon", "adopt_runtime"):
        assert not hasattr(module, effectful_name)


def test_existing_maintenance_authority_contracts_remain_separate() -> None:
    continuity_effects = DEFINITION.required_effects
    for capability_id, definition in AUTHORITY_DEFINITIONS.items():
        if capability_id != MAINTENANCE_AUTHORITY_CONTINUITY:
            assert definition.required_effects != continuity_effects
