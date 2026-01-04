"""Deterministic narrative composition for governance artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from policy_digest import PolicyDigest
from sentientos.constraint_justification import ConstraintJustification
from sentientos.intent_record import IntentRecord


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


@dataclass(frozen=True, slots=True)
class SnapshotLineage:
    snapshot_id: str
    superseded_by: tuple[str, ...] = field(default_factory=tuple)
    parallel_with: tuple[str, ...] = field(default_factory=tuple)
    amended_by: tuple[str, ...] = field(default_factory=tuple)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "superseded_by": list(self.superseded_by),
            "parallel_with": list(self.parallel_with),
            "amended_by": list(self.amended_by),
        }


@dataclass(frozen=True, slots=True)
class DecisionNarrative:
    """Composed narrative for a snapshot, with no authority or inference."""

    snapshot_id: str
    policy_reference: Mapping[str, str]
    intent_records: tuple[IntentRecord, ...]
    constraint_justifications: tuple[ConstraintJustification, ...]
    snapshot_lineage: SnapshotLineage | None = None
    authoritative: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_reference",
            MappingProxyType(dict(self.policy_reference)),
        )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "policy_reference": dict(self.policy_reference),
            "intent_records": [record.canonical_payload() for record in self.intent_records],
            "constraint_justifications": [
                justification.canonical_payload() for justification in self.constraint_justifications
            ],
            "snapshot_lineage": (
                self.snapshot_lineage.canonical_payload() if self.snapshot_lineage else None
            ),
            "authoritative": self.authoritative,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_payload())


def compose_decision_narrative(
    *,
    snapshot_id: str,
    policy_digest: PolicyDigest,
    intent_records: Iterable[IntentRecord],
    constraint_justifications: Iterable[ConstraintJustification],
    snapshot_lineage: SnapshotLineage | None = None,
) -> DecisionNarrative:
    """Compose a deterministic narrative from existing governance artifacts."""

    intent_sorted = tuple(sorted(intent_records, key=lambda record: record.intent_id))
    constraint_sorted = tuple(
        sorted(constraint_justifications, key=lambda justification: justification.constraint_id)
    )
    lineage = None
    if snapshot_lineage is not None:
        lineage = SnapshotLineage(
            snapshot_id=snapshot_lineage.snapshot_id,
            superseded_by=_sorted_unique(snapshot_lineage.superseded_by),
            parallel_with=_sorted_unique(snapshot_lineage.parallel_with),
            amended_by=_sorted_unique(snapshot_lineage.amended_by),
        )
    return DecisionNarrative(
        snapshot_id=snapshot_id,
        policy_reference=policy_digest.reference(),
        intent_records=intent_sorted,
        constraint_justifications=constraint_sorted,
        snapshot_lineage=lineage,
    )


__all__ = ["DecisionNarrative", "SnapshotLineage", "compose_decision_narrative"]
