from __future__ import annotations

from dataclasses import replace
from typing import Mapping

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS,
    AUTHORITY_DEFINITION_REGISTRATION,
    MODEL_MIRROR_PUBLICATION_AUTHORIZATION_ISSUE as CAPABILITY,
    MODEL_MIRROR_PUBLICATION_AUTHORIZATION_ISSUE_DEFINITION as DEFINITION,
    MODEL_MIRROR_PUBLICATION_AUTHORIZATION_ISSUE_OPERATOR_APPROVAL as APPROVAL,
    MODEL_MIRROR_PUBLISH,
    TaskAuthorityDefinition,
    authority_admission_blockers,
    authority_definition_digest,
    operator_approval_evidence_digest,
    register_authority_definition,
)

pytestmark = pytest.mark.no_legacy_skip

TASK = "register_model_mirror_publication_authorization_issuance_authority"
PRINCIPAL = "deterministic_model_mirror_publication_authorization_controller"
DIGEST = "dc4f1b40ec2ceaeae0b9b1d94850fa66da65e163a10f78308bd954baf6b5ab91"
APPROVAL_DIGEST = "e8e57be80308e22cf8579dab8697d67cb74b7bbf972930003eea4a056c8deee2"
EFFECTS = tuple(sorted(DEFINITION.required_effects))
GOAL = ". ".join(DEFINITION.required_goal_phrases) + "."


def catalog_without_definition() -> Mapping[str, TaskAuthorityDefinition]:
    return {key: value for key, value in AUTHORITY_DEFINITIONS.items() if key != CAPABILITY}


def registration(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_classification": AUTHORITY_DEFINITION_REGISTRATION,
        "task_name": TASK,
        "definitions": [DEFINITION],
        "operator_approval": dict(APPROVAL),
        "requested_capability_id": "",
        "authority_principal": "",
        "requested_effects": (),
        "runtime_mutations": (),
        "changed_paths": (
            "sentientos/codex_task_authority_admission.py",
            "tests/test_model_mirror_publication_authorization_capability_admission.py",
            "docs/development/model_mirror_publication_authorization_capability.md",
        ),
    }
    value.update(changes)
    return value


def blockers(**changes: object) -> tuple[str, ...]:
    values: dict[str, object] = {
        "capability_id": CAPABILITY,
        "subsystem_kind": "model_distribution",
        "principal_kind": PRINCIPAL,
        "requested_effects": EFFECTS,
        "task_goal": GOAL,
    }
    values.update(changes)
    return authority_admission_blockers(**values)  # type: ignore[arg-type]


def test_exact_definition_registration_is_metadata_only() -> None:
    assert authority_definition_digest(DEFINITION) == DIGEST
    approval = dict(APPROVAL)
    assert approval["approved_capability_id"] == CAPABILITY
    assert approval["approved_definition_digest"] == DIGEST
    assert approval["approved_task_name"] == TASK
    assert approval["evidence_id"] == "approval:model_mirror_publication_authorization:dc4f1b40ec2c:001"
    assert approval["evidence_digest"] == APPROVAL_DIGEST
    assert operator_approval_evidence_digest(approval) == APPROVAL_DIGEST

    result = register_authority_definition(
        registration(), authority_definitions=catalog_without_definition()
    )
    assert result.status == "authority_definition_registered"
    assert result.definition_registered is True
    assert result.capability_granted is False
    assert result.runtime_authority is None
    assert result.effect_performed is False
    assert result.runtime_mutation_performed is False
    assert result.authority_definitions[CAPABILITY] == DEFINITION


def test_issuer_and_publication_effect_surfaces_are_disjoint_and_exact() -> None:
    publication = AUTHORITY_DEFINITIONS[MODEL_MIRROR_PUBLISH]
    publication_effects = frozenset({
        "exact_curator_artifact_read",
        "canonical_sovereign_create_only_write",
        "bounded_outbound_transfer",
        "publication_receipt_write",
    })
    issuance_effects = frozenset({
        "exact_operator_approval_evidence_read",
        "exact_curator_publication_package_read",
        "exact_model_mirror_publication_intent_read",
        "bounded_model_mirror_publication_grant_issue",
        "bounded_model_mirror_publication_lease_issue",
        "model_mirror_publication_authorization_receipt_write",
    })
    assert publication.required_effects == publication_effects
    assert DEFINITION.required_effects == issuance_effects
    assert publication_effects.isdisjoint(issuance_effects)
    assert publication.principal_kinds == frozenset({"deterministic_publication_controller"})
    assert DEFINITION.principal_kinds == frozenset({PRINCIPAL})


def test_exact_later_implementation_is_definition_eligible_without_grant() -> None:
    assert blockers() == ()
    assert CAPABILITY in AUTHORITY_DEFINITIONS
    # Admission is definition eligibility only; no runtime grant type is returned.
    assert not hasattr(authority_admission_blockers, "grant")


@pytest.mark.parametrize("missing", DEFINITION.required_goal_phrases)
def test_each_affirmative_precondition_is_required(missing: str) -> None:
    assert "authority_goal_missing_required_precondition" in blockers(
        task_goal=GOAL.replace(missing, "required evidence")
    )


@pytest.mark.parametrize(
    "changes,code",
    (
        ({"principal_kind": "deterministic_publication_controller"}, "authority_principal_not_admitted"),
        ({"subsystem_kind": "local_model_chat"}, "authority_subsystem_not_admitted"),
        ({"requested_effects": EFFECTS[:-1]}, "authority_effect_surface_not_exact"),
        ({"requested_effects": EFFECTS + ("bounded_outbound_transfer",)}, "authority_effect_surface_not_exact"),
        ({"task_goal": GOAL + " arbitrary publication target"}, "authority_goal_requests_forbidden_scope"),
    ),
)
def test_inexact_later_admission_is_blocked(changes: dict[str, object], code: str) -> None:
    assert code in blockers(**changes)


@pytest.mark.parametrize(
    "changes",
    (
        {"operator_approval": None},
        {"task_name": "changed_task"},
        {"definitions": [replace(DEFINITION, purpose="changed")]},
        {"definitions": [DEFINITION, replace(DEFINITION, capability_id=CAPABILITY + ".other")]},
        {"definitions": [replace(DEFINITION, required_effects=frozenset({"*"}))]},
        {"definitions": [replace(DEFINITION, principal_kinds=frozenset({"all"}))]},
        {"definitions": [replace(DEFINITION, subsystem_kinds=frozenset({"any"}))]},
        {"requested_capability_id": CAPABILITY},
        {"authority_principal": PRINCIPAL},
        {"requested_effects": EFFECTS},
        {"runtime_mutations": ("publication",)},
    ),
)
def test_registration_rejects_mismatch_breadth_or_runtime_request(changes: dict[str, object]) -> None:
    result = register_authority_definition(
        registration(**changes), authority_definitions=catalog_without_definition()
    )
    assert result.definition_registered is False
    assert result.capability_granted is False
    assert result.effect_performed is False


def test_changed_capability_or_identity_without_recomputed_approval_is_rejected() -> None:
    changed_definition = replace(DEFINITION, capability_id=CAPABILITY + ".changed")
    for artifact, expected in (
        (registration(definitions=[changed_definition]), "authority_definition_operator_approval_binding_mismatch"),
        (registration(operator_approval={**APPROVAL, "operator_identity_label": "operator:changed"}), "authority_definition_operator_approval_digest_invalid"),
        (registration(operator_approval={**APPROVAL, "approved_definition_digest": "0" * 64}), "authority_definition_operator_approval_digest_invalid"),
    ):
        result = register_authority_definition(
            artifact, authority_definitions=catalog_without_definition()
        )
        assert result.definition_registered is False
        assert expected in result.blocker_codes
