from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from policy_digest import policy_digest
from sentientos.constraint_justification import ConstraintJustification, DoctrineReference
from sentientos.decision_narrative import (
    SnapshotLineage,
    compose_decision_narrative,
)
from sentientos.failure_taxonomy import failure_taxonomy, failure_taxonomy_reference
from sentientos.intent_record import build_intent_record
from sentientos.invariant_catalog import invariant_catalog
from sentientos.ontology_version import OntologyVersion, ontology_version


def test_decision_narrative_deterministic_and_non_authoritative() -> None:
    policy = policy_digest()
    intent_a = build_intent_record(
        intent_type="deploy",
        payload={"target": "alpha"},
        originating_context="test",
    )
    intent_b = build_intent_record(
        intent_type="deploy",
        payload={"target": "beta"},
        originating_context="test",
    )
    reference = DoctrineReference(policy_id="policy", policy_hash="hash")
    justification_a = ConstraintJustification(
        constraint_id="constraint-a",
        constraint_scope="runtime",
        doctrine_reference=reference,
        justification_text="Constraint A",
        review_epoch=1,
        status="active",
        failure_taxonomy=failure_taxonomy_reference(),
    )
    justification_b = ConstraintJustification(
        constraint_id="constraint-b",
        constraint_scope="runtime",
        doctrine_reference=reference,
        justification_text="Constraint B",
        review_epoch=1,
        status="active",
        failure_taxonomy=failure_taxonomy_reference(),
    )
    lineage = SnapshotLineage(
        snapshot_id="snap-1",
        superseded_by=("snap-2", "snap-3"),
        parallel_with=("snap-4",),
        amended_by=("snap-5",),
    )

    narrative = compose_decision_narrative(
        snapshot_id="snap-1",
        policy_digest=policy,
        intent_records=[intent_b, intent_a],
        constraint_justifications=[justification_b, justification_a],
        snapshot_lineage=lineage,
    )
    narrative_again = compose_decision_narrative(
        snapshot_id="snap-1",
        policy_digest=policy,
        intent_records=[intent_a, intent_b],
        constraint_justifications=[justification_a, justification_b],
        snapshot_lineage=lineage,
    )

    assert narrative.authoritative is False
    assert narrative.canonical_json() == narrative_again.canonical_json()
    assert [record.intent_id for record in narrative.intent_records] == sorted(
        [intent_a.intent_id, intent_b.intent_id]
    )


def test_invariant_catalog_entries_are_immutable() -> None:
    catalog = invariant_catalog()
    entry = next(iter(catalog.values()))

    with pytest.raises(TypeError):
        catalog["new"] = entry  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        entry.scope = "mutated"  # type: ignore[misc]


def test_failure_taxonomy_is_read_only_and_referenced() -> None:
    taxonomy = failure_taxonomy()
    assert set(taxonomy.keys()) == set(failure_taxonomy_reference())
    assert policy_digest().failure_taxonomy == failure_taxonomy_reference()

    with pytest.raises(TypeError):
        taxonomy["new"] = "not allowed"  # type: ignore[misc]


def test_ontology_version_round_trip_is_stable() -> None:
    marker = ontology_version()
    rehydrated = OntologyVersion.from_json(marker.canonical_json())

    assert marker == rehydrated
    assert marker.canonical_json() == rehydrated.canonical_json()
