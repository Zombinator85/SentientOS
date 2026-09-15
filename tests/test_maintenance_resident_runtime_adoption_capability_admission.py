from pathlib import Path

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    MAINTENANCE_AUTHORITY_CONTINUITY,
    MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION,
    MAINTENANCE_RESIDENT_RUNTIME_ADOPTION,
    MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION,
    MAINTENANCE_WAKE_DAEMON_ADOPTION,
    authority_admission_blockers,
)

pytestmark = pytest.mark.no_legacy_skip

PRINCIPAL = "deterministic_maintenance_resident_runtime_adoption_controller"
EFFECTS = (
    "exact_successor_maintenance_authority_generation_read",
    "exact_maintenance_authority_continuity_receipt_read",
    "exact_maintenance_successor_generation_adoption_state_read",
    "exact_successor_repository_state_read",
    "exact_resident_runtime_adoption_configuration_read",
    "exact_resident_runtime_launch_provenance_read",
    "bounded_maintenance_runtime_quiescence",
    "maintenance_resident_runtime_adoption_intent_write",
    "bounded_exact_sentientosd_self_exec",
    "exact_successor_resident_runtime_readiness_read",
    "maintenance_resident_runtime_adoption_receipt_write",
    "read_only_maintenance_resident_runtime_health_projection",
)
GOAL = (
    "Implement bounded sentientosd self replacement to a verified successor maintenance "
    "generation during an exact pending successor wake handoff after exact successor "
    "repository state and resident runtime launch provenance are verified, requiring post "
    "replacement resident readiness before successor wake effects."
)
DEFINITION = AUTHORITY_DEFINITIONS[MAINTENANCE_RESIDENT_RUNTIME_ADOPTION]


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = {
        "capability_id": MAINTENANCE_RESIDENT_RUNTIME_ADOPTION,
        "subsystem_kind": "maintenance",
        "principal_kind": PRINCIPAL,
        "requested_effects": EFFECTS,
        "task_goal": GOAL,
    }
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_exact_capability_registration_and_canonical_goal_admit_without_grant() -> None:
    assert MAINTENANCE_RESIDENT_RUNTIME_ADOPTION == "maintenance_resident_runtime_adoption"
    assert DEFINITION.capability_id == MAINTENANCE_RESIDENT_RUNTIME_ADOPTION
    assert DEFINITION.subsystem_kinds == frozenset({"maintenance"})
    assert DEFINITION.principal_kinds == frozenset({PRINCIPAL})
    assert DEFINITION.required_effects == frozenset(EFFECTS)
    assert blockers() == ()
    assert not hasattr(DEFINITION, "capability_granted")


def test_wrong_subsystem_rejects() -> None:
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="runtime_supervision")


def test_wrong_principal_rejects() -> None:
    assert "authority_principal_not_admitted" in blockers(principal_kind="sentientosd")


def test_missing_extra_and_duplicate_effects_reject() -> None:
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS[:-1])
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + ("real_service_restart",))
    assert "authority_effect_surface_not_exact" in blockers(requested_effects=EFFECTS + (EFFECTS[0],))


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
def test_each_required_future_goal_phrase_is_independently_required(phrase: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, "required exact evidence")
    )


@pytest.mark.parametrize("phrase", DEFINITION.required_goal_phrases)
@pytest.mark.parametrize("negation", ("without", "not"))
def test_negated_required_clause_rejects(phrase: str, negation: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(phrase, f"{negation} {phrase}")
    )


@pytest.mark.parametrize("phrase", DEFINITION.forbidden_goal_phrases)
def test_every_forbidden_scope_phrase_rejects(phrase: str) -> None:
    assert "authority_goal_requests_forbidden_scope" in blockers(
        task_goal=f"{GOAL} Request {phrase}."
    )


def test_registry_reports_implemented_bounded_controller_truth() -> None:
    record = build_default_capability_registry().by_id()[MAINTENANCE_RESIDENT_RUNTIME_ADOPTION]
    assert record.category == MAINTENANCE_RESIDENT_RUNTIME_ADOPTION
    assert record.status == "implemented"
    assert record.authority_level == "bounded-orchestrator"
    assert record.requires_control_plane_admission
    assert record.requires_operator_approval
    assert record.requires_audit_receipt
    assert not record.requires_rollback_receipt
    assert "bounded exact POSIX sentientosd self exec and exact post-exec startup transaction reconciliation" in record.implemented_surfaces
    assert "restart-after-process-death recovery" in record.deferred_surfaces
    assert "eligibility grants resident-runtime adoption authority" in record.forbidden_implications


def test_resident_adoption_runtime_is_narrow_and_has_no_generic_restart() -> None:
    assert Path("sentientos/maintenance_resident_runtime_adoption.py").exists()
    assert Path("scripts/maintenance_resident_runtime_adoption.py").exists()
    changed_runtime = (
        Path("sentientosd.py"),
        Path("sentientos/runtime/supervisor.py"),
        Path("sentientos/runtime/services.py"),
        Path("sentientos/runtime/startup.py"),
    )
    runtime = Path("sentientos/maintenance_resident_runtime_adoption.py").read_text(encoding="utf-8")
    assert "os.execve" in runtime
    assert "subprocess" not in runtime and "os.system" not in runtime and "shell=True" not in runtime


def test_existing_maintenance_authority_definitions_remain_exact() -> None:
    continuity = AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY]
    assert continuity.principal_kinds == frozenset({"deterministic_maintenance_authority_continuity_controller"})
    assert continuity.required_effects == frozenset({
        "exact_prior_maintenance_authority_generation_read",
        "exact_completed_maintenance_generation_evidence_read",
        "exact_successor_repository_state_read",
        "bounded_successor_maintenance_authority_derive",
        "successor_maintenance_configuration_generation_write",
        "maintenance_authority_continuity_receipt_write",
    })

    automatic = AUTHORITY_DEFINITIONS[MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION]
    assert automatic.principal_kinds == frozenset({"deterministic_maintenance_authority_continuity_auto_derivation_controller"})
    assert "bounded_exact_sentientosd_self_exec" not in automatic.required_effects
    assert "runtime code adoption" in automatic.forbidden_goal_phrases

    successor = AUTHORITY_DEFINITIONS[MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION]
    assert successor.principal_kinds == frozenset({"deterministic_maintenance_successor_generation_adoption_controller"})
    assert "bounded_exact_sentientosd_self_exec" not in successor.required_effects
    assert "runtime code adoption" in successor.forbidden_goal_phrases

    wake = AUTHORITY_DEFINITIONS[MAINTENANCE_WAKE_DAEMON_ADOPTION]
    assert wake.principal_kinds == frozenset({"deterministic_maintenance_wake_daemon_controller"})
    assert "bounded_exact_sentientosd_self_exec" not in wake.required_effects
    assert "automatic runtime adoption" in wake.forbidden_goal_phrases


def test_runtime_supervision_and_generic_restart_registry_truth_remain_unchanged() -> None:
    records = build_default_capability_registry().by_id()
    supervision = records["runtime_supervisor"]
    assert supervision.status == "implemented"
    assert supervision.authority_level == "bounded-orchestrator"
    generic_restart = records["real_service_restart"]
    assert generic_restart.status == "blocked"
    assert generic_restart.authority_level == "none"


def test_existing_automatic_n0_n1_n2_recursion_proof_remains_required() -> None:
    proof = Path("tests/test_maintenance_authority_continuity_auto_derivation.py").read_text(encoding="utf-8")
    assert "test_automatic_n0_to_n1_to_n2_recursion_without_manual_derive_next" in proof
    record = build_default_capability_registry().by_id()[MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION]
    assert any("test_automatic_n0_to_n1_to_n2_recursion_without_manual_derive_next" in command for command in record.proof_commands)


def test_resident_adoption_is_implemented_and_persistent_posture_is_documented() -> None:
    record = build_default_capability_registry().by_id()[MAINTENANCE_RESIDENT_RUNTIME_ADOPTION]
    assert record.status == "implemented" and record.authority_level == "bounded-orchestrator"
    document = Path("docs/development/maintenance_resident_runtime_adoption_authority.md").read_text(encoding="utf-8")
    assert "Fresh human\napproval is not required for each N-to-N+1 transition" in document
    assert "This persistent approval is not itself a runtime grant" in document
    assert "This admission task does not make that second sequence real" in document
