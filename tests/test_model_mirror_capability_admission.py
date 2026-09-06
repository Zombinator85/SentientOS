from __future__ import annotations

import pytest

from sentientos.capability_registry import build_default_capability_registry
from sentientos.codex_task_authority_admission import MODEL_MIRROR_PUBLISH
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths


EFFECTS = (
    "exact_curator_artifact_read",
    "canonical_sovereign_create_only_write",
    "bounded_outbound_transfer",
    "publication_receipt_write",
)


def request(**changes: object) -> PlannerRequest:
    values: dict[str, object] = {
        "task_name": "sovereign model mirror publication boundary",
        "task_goal": "Implement a deterministic create-only provider actuator for canonical sovereign model publication",
        "preset_id": "model_distribution",
        "subsystem_kind": "model_distribution",
        "capability_id": MODEL_MIRROR_PUBLISH,
        "authority_principal": "deterministic_publication_controller",
        "requested_effects": EFFECTS,
        "commit_title": "[codex:model-publication] add sovereign model mirror boundary",
    }
    values.update(changes)
    return PlannerRequest(**values)  # type: ignore[arg-type]


@pytest.mark.no_legacy_skip
def test_exact_registered_publication_task_is_definition_eligible_not_granted() -> None:
    result = plan_codex_task_scaffold_paths(request())
    assert result.status == "ready"
    assert result.capability_id == MODEL_MIRROR_PUBLISH
    assert result.authority_principal == "deterministic_publication_controller"
    assert set(result.requested_effects) == set(EFFECTS)
    assert "forbidden_authority_surface_requested" not in result.blocker_codes


@pytest.mark.no_legacy_skip
def test_registry_records_implemented_boundary_without_live_authority() -> None:
    record = build_default_capability_registry().by_id()[MODEL_MIRROR_PUBLISH]
    assert record.status == "implemented"
    assert record.authority_level == "contract_only"
    assert record.requires_control_plane_admission is True
    assert record.requires_operator_approval is True
    assert record.network_required is False
    assert record.metadata_only is True
    assert "production provider adapter and configuration" in record.deferred_surfaces
    assert "catalog deployment authority and deployment" in record.deferred_surfaces


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("capability", ("sentientos.unknown.publish", "external.publish", "network.publish"))
def test_unknown_publication_capabilities_remain_rejected(capability: str) -> None:
    result = plan_codex_task_scaffold_paths(request(capability_id=capability))
    assert result.status == "blocked"
    assert "unregistered_authority_capability" in result.blocker_codes
    assert "forbidden_authority_surface_requested" in result.blocker_codes


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    "principal",
    ("stochastic_model", "commissioned_local_model", "maintenance_implementation_worker", "model_curator"),
)
def test_model_facing_maintenance_and_curator_principals_are_denied(principal: str) -> None:
    result = plan_codex_task_scaffold_paths(request(authority_principal=principal))
    assert result.status == "blocked"
    assert "authority_principal_not_admitted" in result.blocker_codes


@pytest.mark.no_legacy_skip
def test_incorrect_subsystem_and_mixed_effects_are_denied() -> None:
    wrong_subsystem = plan_codex_task_scaffold_paths(request(subsystem_kind="maintenance_implementation_agent_adapter"))
    assert "authority_subsystem_not_admitted" in wrong_subsystem.blocker_codes
    mixed = plan_codex_task_scaffold_paths(request(requested_effects=EFFECTS + ("git_publication",)))
    assert "authority_effect_surface_not_exact" in mixed.blocker_codes


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    "phrase",
    (
        "mutable alias", "arbitrary host", "arbitrary URL", "provider administration",
        "credential management", "self-grant", "Hugging Face", "Git publication",
    ),
)
def test_registered_capability_cannot_enlarge_publication_scope(phrase: str) -> None:
    result = plan_codex_task_scaffold_paths(request(task_goal=f"Implement model publication with {phrase}"))
    assert result.status == "blocked"
    assert "authority_goal_requests_forbidden_scope" in result.blocker_codes


@pytest.mark.no_legacy_skip
def test_capability_id_alone_is_not_an_admission_or_grant() -> None:
    result = plan_codex_task_scaffold_paths(
        PlannerRequest(task_name="publication", task_goal="use provider publication", capability_id=MODEL_MIRROR_PUBLISH)
    )
    assert result.status == "blocked"
    assert "forbidden_authority_surface_requested" in result.blocker_codes
