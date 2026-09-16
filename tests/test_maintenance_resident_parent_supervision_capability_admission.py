from dataclasses import fields
from pathlib import Path

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, MAINTENANCE_AUTHORITY_CONTINUITY,
    MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION,
    MAINTENANCE_RESIDENT_PARENT_SUPERVISION, MAINTENANCE_RESIDENT_RUNTIME_ADOPTION,
    MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION, MAINTENANCE_WAKE_DAEMON_ADOPTION,
    authority_admission_blockers,
)
from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths

pytestmark = pytest.mark.no_legacy_skip
PRINCIPAL = "deterministic_maintenance_resident_parent_supervision_controller"
EFFECTS = (
    "exact_sentientosd_parent_supervision_configuration_read",
    "exact_sentientosd_child_specification_read",
    "exact_resident_runtime_transition_custody_read",
    "exact_resident_runtime_launch_provenance_read",
    "exact_sentientosd_child_lifecycle_observation",
    "bounded_exact_sentientosd_child_custody",
    "bounded_exact_sentientosd_process_death_recovery",
    "exact_post_restart_resident_readiness_read",
    "maintenance_resident_parent_supervision_receipt_write",
    "read_only_maintenance_resident_parent_supervision_health_projection",
)
GOAL = ("Implement bounded parent supervision of an exact sentientosd child under resident "
        "transaction custody, permitting only exact maintenance-lineage process-death recovery, "
        "requiring exact resident launch provenance and post-restart resident readiness before "
        "maintenance effects resume.")
DEFINITION = AUTHORITY_DEFINITIONS[MAINTENANCE_RESIDENT_PARENT_SUPERVISION]


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = dict(capability_id=MAINTENANCE_RESIDENT_PARENT_SUPERVISION,
        subsystem_kind="maintenance", principal_kind=PRINCIPAL,
        requested_effects=EFFECTS, task_goal=GOAL)
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_exact_capability_registration_and_effect_surface_admit() -> None:
    assert MAINTENANCE_RESIDENT_PARENT_SUPERVISION == "maintenance_resident_parent_supervision"
    assert DEFINITION.subsystem_kinds == frozenset({"maintenance"})
    assert DEFINITION.principal_kinds == frozenset({PRINCIPAL})
    assert DEFINITION.required_effects == frozenset(EFFECTS)
    assert len(EFFECTS) == len(set(EFFECTS)) and blockers() == ()


def test_wrong_subsystem_and_principal_reject() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="runtime_supervision")
    assert "authority_principal_not_admitted" in blockers(principal_kind="sentientosd")


def test_missing_extra_and_duplicate_effects_reject() -> None:
    for effects in (EFFECTS[:-1], EFFECTS + ("real_service_restart",), EFFECTS + (EFFECTS[0],)):
        assert "authority_effect_surface_not_exact" in blockers(requested_effects=effects)


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_every_required_goal_clause_is_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(task_goal=GOAL.replace(phrase, "required evidence"))


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_negated_required_goal_clause_rejects(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(task_goal=GOAL.replace(phrase, f"without {phrase}"))


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_scope_phrase_rejects(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(task_goal=f"{GOAL} Request {phrase}.")


def test_canonical_future_implementation_goal_admits_non_granting_bootstrap() -> None:
    planned = PlannerRequest(task_name="implement_maintenance_resident_parent_supervision",
        task_goal=GOAL, subsystem_kind="maintenance",
        capability_id=MAINTENANCE_RESIDENT_PARENT_SUPERVISION,
        authority_principal=PRINCIPAL, requested_effects=EFFECTS,
        commit_title="[codex:maintenance] implement resident parent supervision")
    assert plan_codex_task_scaffold_paths(planned).status == "ready"
    allowed = {field.name for field in fields(CodexTaskBootstrapRequest)}
    result = bootstrap_codex_task(CodexTaskBootstrapRequest(**{
        key: value for key, value in planned.__dict__.items() if key in allowed
    }), include_preset_verifier=False)
    assert result.status in {"ready", "ready_with_warnings"}
    assert result.planner_result_summary["authority_definition_eligibility_only"] is True
    assert result.planner_result_summary["capability_granted"] is False


def test_registry_truth_is_scaffolded_eligibility_only() -> None:
    record = build_default_capability_registry().by_id()[MAINTENANCE_RESIDENT_PARENT_SUPERVISION]
    assert (record.category, record.status, record.authority_level) == ("runtime_supervision", "scaffolded", "eligibility_only")
    assert record.requires_control_plane_admission and record.requires_operator_approval
    assert record.requires_panic_stop and record.requires_audit_receipt
    assert not record.requires_rollback_receipt


def test_no_parent_runtime_implementation_or_control_path_exists() -> None:
    assert not Path("sentientos/maintenance_resident_parent_supervision.py").exists()
    assert not Path("scripts/maintenance_resident_parent_supervision.py").exists()
    admission = Path("sentientos/codex_task_authority_admission.py").read_text()
    registry = Path("sentientos/capability_registry.py").read_text()
    assert all(token not in admission + registry for token in ("subprocess.Popen", "os.exec", "os.kill"))


def test_runtime_supervisor_and_generic_restart_truth_are_preserved() -> None:
    records = build_default_capability_registry().by_id()
    assert (records["runtime_supervisor"].status, records["runtime_supervisor"].authority_level) == ("implemented", "bounded-orchestrator")
    assert (records["real_service_restart"].status, records["real_service_restart"].authority_level) == ("blocked", "none")


def test_resident_and_maintenance_authority_definitions_are_preserved() -> None:
    resident = AUTHORITY_DEFINITIONS[MAINTENANCE_RESIDENT_RUNTIME_ADOPTION]
    assert "bounded_exact_sentientosd_self_exec" in resident.required_effects
    assert "parent supervisor installation" in resident.forbidden_goal_phrases
    auto = AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION]
    assert {"bounded_successor_maintenance_authority_derive", "bounded_canonical_completed_maintenance_transition_discovery", "bounded_maintenance_authority_continuity_auto_derivation_lifecycle"} <= auto.required_effects
    assert "bounded automatic continuity derivation" in auto.required_goal_phrases
    assert AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY].principal_kinds == frozenset({"deterministic_maintenance_authority_continuity_controller"})
    assert "bounded_maintenance_wake_owner_generation_handoff" in AUTHORITY_DEFINITIONS[MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION].required_effects
    assert "bounded_maintenance_wake_daemon_lifecycle" in AUTHORITY_DEFINITIONS[MAINTENANCE_WAKE_DAEMON_ADOPTION].required_effects
