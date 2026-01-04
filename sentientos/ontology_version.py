"""Immutable ontology marker for frozen vocabulary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class OntologyVersion:
    version_id: str
    definitions: Mapping[str, str] = field(default_factory=dict)
    compatibility_notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "definitions", MappingProxyType(dict(self.definitions)))

    def canonical_payload(self) -> dict[str, object]:
        return {
            "version_id": self.version_id,
            "definitions": dict(self.definitions),
            "compatibility_notes": list(self.compatibility_notes),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_payload())

    @classmethod
    def from_json(cls, payload: str) -> "OntologyVersion":
        data = json.loads(payload)
        definitions = data.get("definitions", {})
        notes = data.get("compatibility_notes", [])
        return cls(
            version_id=str(data.get("version_id", "")),
            definitions=dict(definitions) if isinstance(definitions, dict) else {},
            compatibility_notes=tuple(str(note) for note in (notes or [])),
        )


_ONTOLOGY_VERSION = OntologyVersion(
    version_id="ontology-v1",
    definitions={
        "policy": "A recorded rationale for governance constraints without granting authority.",
        "intent": "A declared attempt or goal, logged without permission semantics.",
        "constraint": "A scoped limit with documented justification and review status.",
        "snapshot": "A deterministic record of system state at a point in time.",
        "supersession": "A lineage link noting replacement without rewriting prior records.",
        "authority": "The power to execute or grant permissions, never implied by logs.",
    },
    compatibility_notes=(
        "Ontology terms are reference-only and do not control runtime behavior.",
    ),
)


def ontology_version() -> OntologyVersion:
    """Return the immutable ontology version marker."""

    return _ONTOLOGY_VERSION


__all__ = ["OntologyVersion", "ontology_version"]
