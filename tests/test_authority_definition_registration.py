from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    EXTERNAL_MODEL_INFERENCE,
    EXTERNAL_MODEL_INFERENCE_DEFINITION,
    EXTERNAL_MODEL_INFERENCE_OPERATOR_APPROVAL,
    GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER,
    GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER_DEFINITION,
    GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER_OPERATOR_APPROVAL,
    MODEL_MIRROR_PUBLISH,
    PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE,
    PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_DEFINITION,
    PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_OPERATOR_APPROVAL,
    TaskAuthorityDefinition,
    authority_admission_blockers,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)
from sentientos.codex_task_scaffold_path_planner import PlannerRequest, plan_codex_task_scaffold_paths


TASK = "inert_fixture_authority_definition_registration"
EXTERNAL_MODEL_TASK = "register_governed_external_model_inference_authority_definition"
EXTERNAL_MODEL_DIGEST = "539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c"
SUPERSEDED_EXTERNAL_MODEL_DIGEST = "0b74d6b113f909e9157263b6321864a4bd50a97d8e9ffda080bb21fcd02dcb6c"
EXTERNAL_MODEL_APPROVAL_DIGEST = "a2e33b07a3ed411fefaa5d4f9dbcd05a12ef951eae5fa405bb209ea33203f028"
RESOURCE_ALLOCATION_TASK = "register-governed-local-model-resource-allocation-adapter-authority-definition"
RESOURCE_ALLOCATION_DIGEST = "f6ba71581fa862097cb279fe0ed47d2d008a6af9e9eef21169b01e6cd8605ebc"
RESOURCE_ALLOCATION_APPROVAL_DIGEST = "c86e8fd257f7174b59c6996d534482aa9b04ee518baf1adf4d39d390600f1763"
RESOURCE_ALLOCATION_EFFECTS = (
    "check_and_debit_governed_local_model_call_entitlement",
    "issue_governed_local_model_resource_allocation",
    "read_current_causal_resource_principal_evidence",
    "read_governed_local_model_resource_policy",
    "write_governed_local_model_resource_consumption_receipt",
)
PROVISIONING_TASK = "register-production-chat-resource-provisioning-bundle-create-authority-definition"
PROVISIONING_DIGEST = "132f93c32f5490877a4748c0054dfb66aacb9f2a94ce560d69a0e65337c800f5"
PROVISIONING_APPROVAL_DIGEST = "3103f4ff4ea3ec7ab0a662958eb5f7e4c8061dd814d3af4e9a833ff4089d9dec"
PROVISIONING_EFFECTS = (
    "create_only_installation_state_resource_provisioning_bundle",
    "finalize_production_resource_provisioning_manifest",
    "issue_one_governed_local_model_resource_allocation",
    "read_exact_preexisting_causal_resource_principal_artifacts",
    "read_exact_resource_trust_currentness_artifacts",
    "read_governed_local_model_resource_policy",
)
PROVISIONING_GOAL = (
    "Create a create-only production chat resource provisioning bundle with one "
    "intentional allocation issuance and manifest-last publication, where restart "
    "does not replenish entitlement."
)


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


def external_model_artifact(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": EXTERNAL_MODEL_TASK,
        "definitions": [EXTERNAL_MODEL_INFERENCE_DEFINITION],
        "operator_approval": dict(EXTERNAL_MODEL_INFERENCE_OPERATOR_APPROVAL),
        "requested_capability_id": "",
        "authority_principal": "",
        "requested_effects": (),
        "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "tests/test_authority_definition_registration.py",
            "docs/development/governed_external_model_authority_proposal.md",
        ),
    }
    value.update(changes)
    return value


def resource_allocation_artifact(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": RESOURCE_ALLOCATION_TASK,
        "definitions": [GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER_DEFINITION],
        "operator_approval": dict(
            GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER_OPERATOR_APPROVAL
        ),
        "requested_capability_id": "",
        "authority_principal": "",
        "requested_effects": (),
        "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "tests/test_authority_definition_registration.py",
            "docs/architecture/governed_local_model_budget_allocation_contract.md",
        ),
    }
    value.update(changes)
    return value


def provisioning_artifact(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": PROVISIONING_TASK,
        "definitions": [PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_DEFINITION],
        "operator_approval": dict(
            PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_OPERATOR_APPROVAL
        ),
        "requested_capability_id": "",
        "authority_principal": "",
        "requested_effects": (),
        "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "tests/test_authority_definition_registration.py",
            "docs/architecture/production_chat_resource_provisioning_bundle_contract.md",
        ),
    }
    value.update(changes)
    return value


@pytest.mark.no_legacy_skip
def test_production_provisioning_definition_registration_is_exact_and_inert() -> None:
    definition_value = PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_DEFINITION
    approval = dict(
        PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_OPERATOR_APPROVAL
    )
    assert authority_definition_digest(definition_value) == PROVISIONING_DIGEST
    assert approval == {
        "schema_version": "sentientos.authority_definition_operator_approval:v1",
        "evidence_id": "approval:production_chat_resource_provisioning_bundle_create:132f93c32f54:001",
        "operator_identity_label": "repository_operator",
        "approval_status": "approved",
        "approved_capability_id": PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE,
        "approved_definition_digest": PROVISIONING_DIGEST,
        "approved_task_name": PROVISIONING_TASK,
        "evidence_digest": PROVISIONING_APPROVAL_DIGEST,
    }
    assert operator_approval_evidence_digest(approval) == PROVISIONING_APPROVAL_DIGEST

    catalog_without_definition = {
        key: value for key, value in AUTHORITY_DEFINITIONS.items()
        if key != PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE
    }
    result = register_authority_definition(
        provisioning_artifact(), authority_definitions=catalog_without_definition
    )
    assert result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.capability_granted is False
    assert result.runtime_authority is None
    assert result.effect_performed is False
    assert result.runtime_mutation_performed is False
    assert result.authority_definitions[
        PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE
    ] == definition_value
    assert AUTHORITY_DEFINITIONS[
        PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE
    ] == definition_value


@pytest.mark.no_legacy_skip
def test_production_provisioning_later_admission_is_exact() -> None:
    def blockers(**changes: object) -> tuple[str, ...]:
        request: dict[str, object] = {
            "capability_id": PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE,
            "subsystem_kind": "causal_resource_principal_architecture",
            "principal_kind": "deterministic_production_chat_resource_provisioning_controller",
            "requested_effects": PROVISIONING_EFFECTS,
            "task_goal": PROVISIONING_GOAL,
        }
        request.update(changes)
        return authority_admission_blockers(**request)  # type: ignore[arg-type]

    assert blockers() == ()
    assert "authority_effect_surface_not_exact" in blockers(
        requested_effects=PROVISIONING_EFFECTS[:-1]
    )
    assert "authority_effect_surface_not_exact" in blockers(
        requested_effects=PROVISIONING_EFFECTS + ("extra_effect",)
    )
    assert "authority_principal_not_admitted" in blockers(principal_kind="wrong_principal")
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="wrong_subsystem")
    for phrase in PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_DEFINITION.required_goal_phrases:
        assert "authority_goal_missing_required_precondition" in blockers(
            task_goal=PROVISIONING_GOAL.replace(phrase, "")
        )
    for phrase in PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE_DEFINITION.forbidden_goal_phrases:
        assert "authority_goal_requests_forbidden_scope" in blockers(
            task_goal=f"{PROVISIONING_GOAL} {phrase}."
        )
    assert "unregistered_authority_capability" in blockers(
        capability_id="production_chat_resource_provisioning_bundle_create_substitute"
    )


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    "request_change",
    (
        {"requested_capability_id": PRODUCTION_CHAT_RESOURCE_PROVISIONING_BUNDLE_CREATE},
        {"authority_principal": "deterministic_production_chat_resource_provisioning_controller"},
        {"requested_effects": PROVISIONING_EFFECTS},
    ),
)
def test_production_provisioning_registration_cannot_self_authorize(
    request_change: dict[str, object],
) -> None:
    result = register_authority_definition(provisioning_artifact(**request_change))
    assert result.status == "authority_definition_registration_blocked"
    assert "authority_definition_registration_cannot_request_capability" in result.blocker_codes
    assert result.definition_registered is False
    assert result.capability_granted is result.effect_performed is False
    assert result.runtime_authority is None
    assert result.runtime_mutation_performed is False


@pytest.mark.no_legacy_skip
def test_governed_local_model_resource_allocation_definition_registration_is_inert() -> None:
    definition_value = GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER_DEFINITION
    approval = dict(GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER_OPERATOR_APPROVAL)
    assert authority_definition_digest(definition_value) == RESOURCE_ALLOCATION_DIGEST
    assert approval == {
        "schema_version": "sentientos.authority_definition_operator_approval:v1",
        "evidence_id": "approval:governed_local_model_resource_allocation_adapter:f6ba71581fa8:001",
        "operator_identity_label": "repository_operator",
        "approval_status": "approved",
        "approved_capability_id": GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER,
        "approved_definition_digest": RESOURCE_ALLOCATION_DIGEST,
        "approved_task_name": RESOURCE_ALLOCATION_TASK,
        "evidence_digest": RESOURCE_ALLOCATION_APPROVAL_DIGEST,
    }
    assert operator_approval_evidence_digest(approval) == RESOURCE_ALLOCATION_APPROVAL_DIGEST

    catalog_without_definition = {
        key: value for key, value in AUTHORITY_DEFINITIONS.items()
        if key != GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER
    }
    result = register_authority_definition(
        resource_allocation_artifact(), authority_definitions=catalog_without_definition
    )
    assert result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.capability_granted is False
    assert result.runtime_authority is None
    assert result.effect_performed is False
    assert result.runtime_mutation_performed is False
    assert result.authority_definitions[
        GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER
    ] == definition_value
    assert AUTHORITY_DEFINITIONS[
        GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER
    ] == definition_value


@pytest.mark.no_legacy_skip
def test_governed_local_model_resource_allocation_later_admission_is_exact() -> None:
    exact_goal = (
        "Implement governed local-model resource allocation with durable call "
        "conservation and a resource consumption receipt."
    )

    def blockers(**changes: object) -> tuple[str, ...]:
        request: dict[str, object] = {
            "capability_id": GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER,
            "subsystem_kind": "causal_resource_principal_architecture",
            "principal_kind": "governed_local_model_resource_allocator",
            "requested_effects": RESOURCE_ALLOCATION_EFFECTS,
            "task_goal": exact_goal,
        }
        request.update(changes)
        return authority_admission_blockers(**request)  # type: ignore[arg-type]

    assert blockers() == ()
    assert "authority_effect_surface_not_exact" in blockers(
        requested_effects=RESOURCE_ALLOCATION_EFFECTS[:-1]
    )
    assert "authority_effect_surface_not_exact" in blockers(
        requested_effects=RESOURCE_ALLOCATION_EFFECTS + ("extra_effect",)
    )
    assert "authority_principal_not_admitted" in blockers(principal_kind="wrong_principal")
    assert "authority_subsystem_not_admitted" in blockers(subsystem_kind="wrong_subsystem")
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal="Governed local-model resource allocation with durable call conservation."
    )
    assert "authority_goal_requests_forbidden_scope" in blockers(
        task_goal=exact_goal + " Also permit provider invocation."
    )
    assert "unregistered_authority_capability" in blockers(
        capability_id="governed_local_model_resource_allocation_adapter_substitute"
    )


@pytest.mark.no_legacy_skip
def test_governed_local_model_resource_registration_cannot_self_authorize() -> None:
    result = register_authority_definition(resource_allocation_artifact(
        requested_capability_id=GOVERNED_LOCAL_MODEL_RESOURCE_ALLOCATION_ADAPTER,
        authority_principal="governed_local_model_resource_allocator",
        requested_effects=RESOURCE_ALLOCATION_EFFECTS,
    ))
    assert result.status == "authority_definition_registration_blocked"
    assert "authority_definition_registration_cannot_request_capability" in result.blocker_codes
    assert result.definition_registered is False
    assert result.capability_granted is result.effect_performed is False
    assert result.runtime_authority is None
    assert result.runtime_mutation_performed is False


@pytest.mark.no_legacy_skip
def test_approved_external_model_definition_is_registered_without_runtime_authority() -> None:
    assert authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION) == EXTERNAL_MODEL_DIGEST
    approval = dict(EXTERNAL_MODEL_INFERENCE_OPERATOR_APPROVAL)
    assert approval == {
        "schema_version": "sentientos.authority_definition_operator_approval:v1",
        "evidence_id": "approval:external_model_inference:539ff509bbea:001",
        "operator_identity_label": "operator:primary",
        "approval_status": "approved",
        "approved_capability_id": EXTERNAL_MODEL_INFERENCE,
        "approved_definition_digest": EXTERNAL_MODEL_DIGEST,
        "approved_task_name": EXTERNAL_MODEL_TASK,
        "evidence_digest": EXTERNAL_MODEL_APPROVAL_DIGEST,
    }
    assert operator_approval_evidence_digest(approval) == EXTERNAL_MODEL_APPROVAL_DIGEST

    catalog_without_definition = {
        key: value for key, value in AUTHORITY_DEFINITIONS.items()
        if key != EXTERNAL_MODEL_INFERENCE
    }
    result = register_authority_definition(
        external_model_artifact(), authority_definitions=catalog_without_definition
    )

    assert result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.capability_id == EXTERNAL_MODEL_INFERENCE
    assert result.definition_digest == EXTERNAL_MODEL_DIGEST
    assert result.operator_approval_evidence_id == approval["evidence_id"]
    assert result.authority_definitions[EXTERNAL_MODEL_INFERENCE] == EXTERNAL_MODEL_INFERENCE_DEFINITION
    assert result.capability_granted is False
    assert result.runtime_authority is None
    assert result.effect_performed is result.runtime_mutation_performed is False
    assert "RuntimeGrantAuthority" not in register_authority_definition.__code__.co_names
    assert "RuntimeAdmissionAuthority" not in register_authority_definition.__code__.co_names


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    "approval_change",
    (
        {"approved_definition_digest": SUPERSEDED_EXTERNAL_MODEL_DIGEST},
        {"approved_definition_digest": "f" * 64},
        {"approved_capability_id": "external_model_inference_changed"},
        {"approved_task_name": "other_registration_task"},
        {"operator_identity_label": "operator:other"},
        {"evidence_id": "approval:other"},
    ),
)
def test_external_model_registration_rejects_changed_or_superseded_approval(
    approval_change: dict[str, str],
) -> None:
    approval = {**EXTERNAL_MODEL_INFERENCE_OPERATOR_APPROVAL, **approval_change}
    artifact_value = external_model_artifact(operator_approval=approval)
    catalog_without_definition = {
        key: value for key, value in AUTHORITY_DEFINITIONS.items()
        if key != EXTERNAL_MODEL_INFERENCE
    }
    result = register_authority_definition(
        artifact_value, authority_definitions=catalog_without_definition
    )
    assert result.status == "authority_definition_registration_blocked"
    assert "authority_definition_operator_approval_digest_invalid" in result.blocker_codes
    if "approved_" in next(iter(approval_change)):
        assert "authority_definition_operator_approval_binding_mismatch" in result.blocker_codes


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
