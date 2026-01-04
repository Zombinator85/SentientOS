"""Read-only invariant catalog for governance legibility."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class InvariantEntry:
    invariant_id: str
    invariant_statement: str
    scope: str
    status: str
    related_references: tuple[str, ...]

    def canonical_payload(self) -> dict[str, object]:
        return {
            "invariant_id": self.invariant_id,
            "invariant_statement": self.invariant_statement,
            "scope": self.scope,
            "status": self.status,
            "related_references": list(self.related_references),
        }


_INVARIANT_CATALOG: Mapping[str, InvariantEntry] = MappingProxyType(
    {
        "invariant::auditability": InvariantEntry(
            invariant_id="invariant::auditability",
            invariant_statement="All governance decisions remain auditable without hidden mutation paths.",
            scope="global",
            status="foundational",
            related_references=("policy_digest", "audit_chain"),
        ),
        "invariant::non_authoritative_intent": InvariantEntry(
            invariant_id="invariant::non_authoritative_intent",
            invariant_statement="Intent capture is informational and never grants execution authority.",
            scope="runtime",
            status="foundational",
            related_references=("intent_record", "constraint_registry"),
        ),
        "invariant::constraint_justification": InvariantEntry(
            invariant_id="invariant::constraint_justification",
            invariant_statement="Constraints must retain explicit justification without becoming enforcement paths.",
            scope="tooling",
            status="derived",
            related_references=("constraint_justification",),
        ),
        "invariant::snapshot_lineage": InvariantEntry(
            invariant_id="invariant::snapshot_lineage",
            invariant_statement="Snapshot lineage preserves supersession context without revisionism.",
            scope="runtime",
            status="derived",
            related_references=("snapshot_lineage", "authority_surface"),
        ),
        "invariant::vocabulary_freeze": InvariantEntry(
            invariant_id="invariant::vocabulary_freeze",
            invariant_statement="Ontology definitions are frozen for reference and do not negotiate authority.",
            scope="global",
            status="foundational",
            related_references=("ontology_version",),
        ),
    }
)


def invariant_catalog() -> Mapping[str, InvariantEntry]:
    """Return the invariant catalog as an immutable mapping."""

    return _INVARIANT_CATALOG


def list_invariants() -> tuple[InvariantEntry, ...]:
    """Return invariants in deterministic order."""

    return tuple(_INVARIANT_CATALOG[key] for key in sorted(_INVARIANT_CATALOG))


__all__ = ["InvariantEntry", "invariant_catalog", "list_invariants"]
