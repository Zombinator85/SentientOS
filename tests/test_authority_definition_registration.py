from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    MODEL_MIRROR_PUBLISH,
    TaskAuthorityDefinition,
    authority_admission_blockers,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths


TASK = "inert_fixture_authority_definition_registration"


def definition(**changes: object) -> TaskAuthorityDefinition:
    values: dict[str, object] = {
        "capability_id": "fixture.inert.review",
        "subsystem_kinds": frozenset({"fixture_review"}),
        "principal_kinds": frozenset({"deterministic_fixture_reviewer"}),
        "required_effects": frozenset({"inert_fixture_metadata_read"}),
        "required_goal_phrases": ("explicit fixture approval",),
        "forbidden_goal_phrases": ("execute fixture effect", "self-grant"),
        "approval_requirements": ("exact operator approval evidence",),
        "purpose": "Permit later exact admission for inert fixture metadata review.",
    }
    values.update(changes)
    return TaskAuthorityDefinition(**values)  # type: ignore[arg-type]


def artifact(item: object | None = None, **changes: object) -> dict[str, object]:
    item = definition() if item is None else item
    digest = authority_definition_digest(item) if isinstance(item, TaskAuthorityDefinition) else ""
    approval: dict[str, object] = {
        "schema_version": "sentientos.authority_definition_operator_approval:v1",
        "evidence_id": "operator-event-fixture-1",
        "operator_identity_label": "operator:test-fixture",
        "approval_status": "approved",
        "approved_capability_id": item.capability_id if isinstance(item, TaskAuthorityDefinition) else "",
        "approved_definition_digest": digest,
        "approved_task_name": TASK,
    }
    approval["evidence_digest"] = operator_approval_evidence_digest(approval)
    value: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": TASK,
        "definitions": [item],
        "operator_approval": approval,
        "requested_capability_id": "",
        "authority_principal": "",
        "requested_effects": (),
        "runtime_mutations": (),
        "changed_paths": ("sentientos/codex_task_authority_admission.py", "tests/test_authority_definition_registration.py"),
    }
    value.update(changes)
    return value


@pytest.mark.no_legacy_skip
def test_operator_approved_registration_is_definition_only_and_visible_to_later_exact_admission() -> None:
    before = dict(AUTHORITY_DEFINITIONS)
    result = register_authority_definition(artifact())
    assert result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.capability_granted is result.effect_performed is result.runtime_mutation_performed is False
    assert result.runtime_authority is None
    assert AUTHORITY_DEFINITIONS == before
    assert "fixture.inert.review" in result.authority_definitions
    assert authority_admission_blockers(
        capability_id="fixture.inert.review", subsystem_kind="fixture_review",
        principal_kind="deterministic_fixture_reviewer",
        requested_effects=("inert_fixture_metadata_read",),
        task_goal="Later work requires explicit fixture approval.",
        authority_definitions=result.authority_definitions,
    ) == ()
    assert "authority_effect_surface_not_exact" in authority_admission_blockers(
        capability_id="fixture.inert.review", subsystem_kind="fixture_review",
        principal_kind="deterministic_fixture_reviewer", requested_effects=("different_effect",),
        task_goal="Later work requires explicit fixture approval.", authority_definitions=result.authority_definitions,
    )


@pytest.mark.no_legacy_skip
def test_missing_or_mismatched_operator_approval_fails_closed() -> None:
    assert "authority_definition_operator_approval_missing" in register_authority_definition(artifact(operator_approval=None)).blocker_codes
    bad = artifact()
    approval = bad["operator_approval"]
    assert isinstance(approval, dict)
    bad["operator_approval"] = {**approval, "approved_task_name": "other"}
    result = register_authority_definition(bad)
    assert "authority_definition_operator_approval_binding_mismatch" in result.blocker_codes
    assert "authority_definition_operator_approval_digest_invalid" in result.blocker_codes


@pytest.mark.no_legacy_skip
def test_duplicate_and_multiple_definitions_fail_closed() -> None:
    duplicate = replace(definition(), capability_id=MODEL_MIRROR_PUBLISH)
    assert "authority_definition_capability_id_duplicate" in register_authority_definition(artifact(duplicate)).blocker_codes
    assert "authority_definition_registration_requires_exactly_one_definition" in register_authority_definition(
        artifact(definitions=[definition(), replace(definition(), capability_id="fixture.inert.second")])
    ).blocker_codes


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    ("change", "code"),
    (
        ({"required_effects": ("*",)}, "authority_definition_effect_wildcard"),
        ({"principal_kinds": frozenset({"all"})}, "authority_definition_principal_wildcard"),
        ({"subsystem_kinds": frozenset({"any"})}, "authority_definition_subsystem_wildcard"),
        ({"required_effects": ()}, "authority_definition_effects_empty"),
        ({"principal_kinds": frozenset()}, "authority_definition_principals_empty"),
        ({"subsystem_kinds": frozenset()}, "authority_definition_subsystems_empty"),
        ({"required_effects": ("inert_fixture_metadata_read", "inert_fixture_metadata_read")}, "authority_definition_effect_duplicate"),
        ({"capability_id": "BAD * ID"}, "authority_definition_capability_id_malformed"),
        ({"purpose": ""}, "authority_definition_purpose_missing"),
        ({"approval_requirements": ()}, "authority_definition_approval_requirements_missing"),
        ({"required_goal_phrases": ("same",), "forbidden_goal_phrases": ("same",)}, "authority_definition_contradictory_goal_semantics"),
    ),
)
def test_malformed_incomplete_or_broad_definition_fails(change: dict[str, object], code: str) -> None:
    assert code in register_authority_definition(artifact(definition(**change))).blocker_codes


@pytest.mark.no_legacy_skip
def test_registration_cannot_self_authorize_or_exercise_new_definition() -> None:
    result = register_authority_definition(artifact(
        requested_capability_id="fixture.inert.review",
        authority_principal="deterministic_fixture_reviewer",
        requested_effects=("inert_fixture_metadata_read",),
    ))
    assert "authority_definition_registration_cannot_request_capability" in result.blocker_codes
    assert result.definition_registered is result.effect_performed is False


@pytest.mark.no_legacy_skip
def test_registration_rejects_runtime_mutations_and_bad_paths() -> None:
    assert "authority_definition_registration_runtime_mutation_forbidden" in register_authority_definition(
        artifact(runtime_mutations=("RuntimeGovernor",))
    ).blocker_codes
    assert "authority_definition_registration_changed_paths_malformed" in register_authority_definition(
        artifact(changed_paths=("runtime_actuator.py",))
    ).blocker_codes


@pytest.mark.no_legacy_skip
def test_bootstrap_classification_is_non_authority_and_ordinary_behavior_is_unchanged() -> None:
    registration = plan_codex_task_scaffold_paths(PlannerRequest(
        task_name="register inert definition", task_goal="Register definition metadata only.",
        subsystem_kind=AUTHORITY_DEFINITION_REGISTRATION,
        capability_id="fixture.inert.review", authority_principal="deterministic_fixture_reviewer",
        requested_effects=("inert_fixture_metadata_read",),
    ))
    assert registration.status == "blocked"
    assert "authority_definition_registration_cannot_request_capability" in registration.blocker_codes
    ordinary = plan_codex_task_scaffold_paths(PlannerRequest(task_name="ordinary docs", task_goal="Update a local document."))
    assert ordinary.status == "ready"
    assert "unregistered_authority_capability" in authority_admission_blockers(
        capability_id="fixture.not.registered", subsystem_kind="fixture_review",
        principal_kind="deterministic_fixture_reviewer", requested_effects=("inert_fixture_metadata_read",), task_goal="bounded",
    )


@pytest.mark.no_legacy_skip
def test_existing_catalog_and_forbidden_authority_lexical_gate_are_unchanged() -> None:
    assert MODEL_MIRROR_PUBLISH in AUTHORITY_DEFINITIONS
    blocked = plan_codex_task_scaffold_paths(PlannerRequest(task_name="provider work", task_goal="Invoke provider access."))
    assert blocked.status == "blocked"
    assert "forbidden_authority_surface_requested" in blocked.blocker_codes


@pytest.mark.no_legacy_skip
def test_registration_module_has_no_runtime_authority_consumer() -> None:
    names = register_authority_definition.__code__.co_names
    assert "ControlPlaneKernel" not in names
    assert "RuntimeGovernor" not in names
    assert "AUTHORITY_DEFINITIONS" in names
