"""Canonical terminology registry for public SentientOS surfaces.

This module provides the normalized vocabulary for documentation, CLI help text,
and reviewer-facing materials. Legacy symbolic terms can remain as compatibility
aliases while migration is in progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PublicTerm:
    legacy_term: str
    normalized_term: str
    migration_status: str
    compatibility_alias: bool
    deprecation_note: str
    rationale: str


PUBLIC_LANGUAGE_MAP: Final[dict[str, PublicTerm]] = {
    "cathedral": PublicTerm(
        legacy_term="cathedral",
        normalized_term="governance control plane",
        migration_status="deprecated_public_term",
        compatibility_alias=True,
        deprecation_note="Use only for historical references or compatibility labels.",
        rationale="Public docs should describe governance and audit function directly.",
    ),
    "council": PublicTerm(
        legacy_term="council",
        normalized_term="governance authority",
        migration_status="deprecated_public_term",
        compatibility_alias=True,
        deprecation_note="Keep only when referring to historical command names or stored log fields.",
        rationale="The semantics are authority, review, and approval—not ceremony.",
    ),
    "blessing": PublicTerm(
        legacy_term="blessing",
        normalized_term="privileged approval",
        migration_status="deprecated_public_term",
        compatibility_alias=True,
        deprecation_note="Use only as a legacy alias in stable APIs or historical logs.",
        rationale="Runtime behavior is procedural approval with explicit gates.",
    ),
    "ritual": PublicTerm(
        legacy_term="ritual",
        normalized_term="operator procedure",
        migration_status="deprecated_public_term",
        compatibility_alias=True,
        deprecation_note="Use only for legacy filenames, commands, or archival docs.",
        rationale="Most references are deterministic procedures and checklists.",
    ),
    "consciousness layer": PublicTerm(
        legacy_term="consciousness layer",
        normalized_term="deterministic state-processing layer",
        migration_status="deprecated_public_term",
        compatibility_alias=True,
        deprecation_note="Avoid on public surfaces except in compatibility notes.",
        rationale="The subsystem is deterministic processing, not agency.",
    ),
    "consciousness cycle": PublicTerm(
        legacy_term="consciousness cycle",
        normalized_term="deterministic state-processing cycle",
        migration_status="deprecated_public_term",
        compatibility_alias=True,
        deprecation_note="Keep only where command or API compatibility requires the legacy wording.",
        rationale="Cycle execution is deterministic and operator-invoked.",
    ),
    "presence": PublicTerm(
        legacy_term="presence",
        normalized_term="activity telemetry",
        migration_status="replace_public_term",
        compatibility_alias=True,
        deprecation_note="Legacy wording may remain in historical event names.",
        rationale="This refers to observability and event signal data.",
    ),
    "observatory": PublicTerm(
        legacy_term="observatory",
        normalized_term="observability",
        migration_status="replace_public_term",
        compatibility_alias=True,
        deprecation_note="Keep as alias only for existing command groups.",
        rationale="The surface provides telemetry/index views.",
    ),
    "forge": PublicTerm(
        legacy_term="forge",
        normalized_term="governed change pipeline",
        migration_status="replace_public_term",
        compatibility_alias=True,
        deprecation_note="Legacy namespace may remain in module names until major-version migration.",
        rationale="This subsystem stages, validates, and promotes changes.",
    ),
    "self-model": PublicTerm(
        legacy_term="self-model",
        normalized_term="runtime identity contract",
        migration_status="replace_public_term",
        compatibility_alias=True,
        deprecation_note="Retain legacy label only where schema keys are externally fixed.",
        rationale="Artifact content defines bounded runtime identity constraints.",
    ),
    "vow": PublicTerm(
        legacy_term="vow",
        normalized_term="integrity contract artifact set",
        migration_status="retained_internal_codename",
        compatibility_alias=True,
        deprecation_note="Internal namespace retained for path compatibility (`/vow`).",
        rationale="Filesystem namespace is stable and externally referenced.",
    ),
    "glow": PublicTerm(
        legacy_term="glow",
        normalized_term="state ledger artifact set",
        migration_status="retained_internal_codename",
        compatibility_alias=True,
        deprecation_note="Internal namespace retained for path compatibility (`/glow`).",
        rationale="Filesystem namespace is stable and externally referenced.",
    ),
    "wild-dialogue": PublicTerm(
        legacy_term="wild-dialogue",
        normalized_term="exploratory dialogue mode",
        migration_status="replace_public_term",
        compatibility_alias=True,
        deprecation_note="Use legacy label only in module names pending migration.",
        rationale="Behavior is bounded exploratory generation, not mystical interaction.",
    ),
}


def translate_public_term(term: str) -> PublicTerm | None:
    """Return terminology metadata for *term* if present."""

    return PUBLIC_LANGUAGE_MAP.get(term.strip().lower())
