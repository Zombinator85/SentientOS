from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    MAINTENANCE_WAKE_DAEMON_ADOPTION,
    authority_admission_blockers,
)

PRINCIPAL = "deterministic_maintenance_wake_daemon_controller"
EFFECTS = (
    "exact_operator_wake_adoption_configuration_read",
    "exact_maintenance_wake_configuration_read",
    "bounded_maintenance_wake_cycle_invoke",
    "bounded_maintenance_wake_daemon_lifecycle",
    "maintenance_wake_daemon_evidence_write",
    "read_only_maintenance_wake_health_projection",
)
GOAL = (
    "Implement explicit operator adoption of an exact wake configuration for a bounded "
    "wake cycle while preserving separate downstream maintenance authority."
)
FORBIDDEN = AUTHORITY_DEFINITIONS[MAINTENANCE_WAKE_DAEMON_ADOPTION].forbidden_goal_phrases
REQUIRED = AUTHORITY_DEFINITIONS[MAINTENANCE_WAKE_DAEMON_ADOPTION].required_goal_phrases


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = dict(
        capability_id=MAINTENANCE_WAKE_DAEMON_ADOPTION,
        subsystem_kind="maintenance",
        principal_kind=PRINCIPAL,
        requested_effects=EFFECTS,
        task_goal=GOAL,
    )
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_canonical_wake_daemon_authority_eligibility_succeeds_without_grant() -> None:
    definition = AUTHORITY_DEFINITIONS[MAINTENANCE_WAKE_DAEMON_ADOPTION]
    assert definition.subsystem_kinds == frozenset({"maintenance"})
    assert definition.principal_kinds == frozenset({PRINCIPAL})
    assert definition.required_effects == frozenset(EFFECTS)
    assert blockers() == ()


def test_missing_effect_rejected() -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS[:-1])


def test_extra_effect_rejected() -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + ("candidate_admission",))


def test_duplicate_effect_rejected() -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + (EFFECTS[0],))


def test_wrong_principal_rejected() -> None:
    assert "authority_principal_not_admitted" in blockers(principal_kind="sentientosd")


def test_wrong_subsystem_rejected() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="runtime_supervision")


@pytest.mark.parametrize("phrase", REQUIRED)
def test_each_required_precondition_is_independently_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(task_goal=GOAL.replace(phrase, "required boundary"))


@pytest.mark.parametrize("phrase", REQUIRED)
def test_negated_required_precondition_does_not_admit(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(task_goal=GOAL.replace(phrase, f"without {phrase}"))


@pytest.mark.parametrize("phrase", FORBIDDEN)
def test_each_forbidden_goal_phrase_rejected(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(task_goal=f"{GOAL} Request {phrase}.")


def test_registry_reports_bounded_runtime_without_downstream_authority() -> None:
    record = build_default_capability_registry().by_id()[MAINTENANCE_WAKE_DAEMON_ADOPTION]
    assert record.category == "maintenance_wake_daemon_adoption"
    assert record.status == "implemented"
    assert record.authority_level == "bounded_in_process_runner"
    assert record.requires_operator_approval and record.requires_control_plane_admission
    assert record.requires_audit_receipt
    assert "explicit exact operator wake adoption" in record.implemented_surfaces
    assert "authority inheritance or renewal across repository advancement" in record.deferred_surfaces
    assert "eligibility metadata is runtime authority" in record.forbidden_implications


def test_admission_metadata_introduces_no_wake_daemon_runtime() -> None:
    assert not Path("sentientos/maintenance_wake_daemon.py").exists()
    assert not Path("sentientos/maintenance_wake_scheduler.py").exists()
    module = __import__("sentientos.codex_task_authority_admission", fromlist=["x"])
    for method in ("wake_once", "run_forever", "start_daemon", "run_lifecycle"):
        assert not hasattr(module, method)
