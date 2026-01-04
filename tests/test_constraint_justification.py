from __future__ import annotations

import pytest

import task_executor
from sentientos.constraint_justification import (
    ConstraintJustification,
    DoctrineReference,
    constraint_justification_catalog,
    enumerate_constraint_review_signals,
)
from sentientos.failure_taxonomy import failure_taxonomy_reference
from sentientos.constraint_registry import ConstraintRegistry

pytestmark = pytest.mark.no_legacy_skip


def test_constraint_justification_deterministic_serialization_and_hash() -> None:
    reference = DoctrineReference(policy_id="policy", policy_hash="abc123")
    justification = ConstraintJustification(
        constraint_id="constraint-alpha",
        constraint_scope="runtime",
        doctrine_reference=reference,
        justification_text="Because the doctrine requires it.",
        review_epoch=7,
        status="active",
        failure_taxonomy=failure_taxonomy_reference(),
    )

    assert justification.canonical_json() == justification.canonical_json()
    assert justification.stable_hash() == justification.stable_hash()
    assert isinstance(hash(justification), int)


def test_constraint_review_signals_surface_missing_and_legacy() -> None:
    reference = DoctrineReference(policy_id="policy", policy_hash="abc123")
    justifications = {
        "constraint-active": ConstraintJustification(
            constraint_id="constraint-active",
            constraint_scope="runtime",
            doctrine_reference=reference,
            justification_text="Active constraint.",
            review_epoch=2,
            status="active",
            failure_taxonomy=failure_taxonomy_reference(),
        ),
        "constraint-legacy": ConstraintJustification(
            constraint_id="constraint-legacy",
            constraint_scope="runtime",
            doctrine_reference=reference,
            justification_text="Legacy constraint.",
            review_epoch=1,
            status="legacy",
            failure_taxonomy=failure_taxonomy_reference(),
        ),
    }

    signals = enumerate_constraint_review_signals(
        ["constraint-active", "constraint-legacy", "constraint-missing"],
        justifications=justifications,
        current_epoch=3,
        review_window=1,
    )

    assert [signal["constraint_id"] for signal in signals] == [
        "constraint-legacy",
        "constraint-missing",
    ]
    assert {signal["reason"] for signal in signals} == {"legacy_status", "missing_justification"}


def test_constraint_justification_does_not_mutate_registry_payload() -> None:
    registry = ConstraintRegistry()
    registry.register("runtime::load-homeostasis", "load homeostasis")
    payload_before = registry.as_payload()

    _ = constraint_justification_catalog()

    payload_after = registry.as_payload()
    assert payload_after == payload_before


def test_constraint_justification_does_not_affect_request_fingerprint() -> None:
    task = task_executor.Task(task_id="t1", objective="Keep scope", constraints=("a", "b"))
    canonical = task_executor.canonicalise_task(task)
    fingerprint_before = task_executor.request_fingerprint_from_canonical(canonical).value

    _ = constraint_justification_catalog()

    fingerprint_after = task_executor.request_fingerprint_from_canonical(canonical).value
    assert fingerprint_after == fingerprint_before
