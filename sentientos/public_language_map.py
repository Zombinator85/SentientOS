"""Deterministic public-language translation map for external documentation.

This module does not change runtime behavior. It provides a single source of
truth for translating symbolic terms into engineering-facing terms in docs,
CLIs, and public presentations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PublicTerm:
    current_term: str
    public_term: str
    classification: str
    rationale: str
    migration_recommendation: str


PUBLIC_LANGUAGE_MAP: Final[dict[str, PublicTerm]] = {
    "cathedral": PublicTerm(
        current_term="cathedral",
        public_term="governance control plane",
        classification="clarify",
        rationale="The runtime enforces governance and audit constraints, not a religious substrate.",
        migration_recommendation="alias in interfaces",
    ),
    "blessing": PublicTerm(
        current_term="blessing",
        public_term="privileged approval",
        classification="replace",
        rationale="Approval semantics are procedural and binary in code paths.",
        migration_recommendation="docs-only translation",
    ),
    "ritual": PublicTerm(
        current_term="ritual",
        public_term="operator procedure",
        classification="replace",
        rationale="Most usage refers to fixed execution procedures and checklists.",
        migration_recommendation="alias in interfaces",
    ),
    "presence": PublicTerm(
        current_term="presence",
        public_term="activity telemetry",
        classification="clarify",
        rationale="Usage maps to event detection and logging rather than awareness.",
        migration_recommendation="docs-only translation",
    ),
    "glow": PublicTerm(
        current_term="glow",
        public_term="state ledger",
        classification="contextualize",
        rationale="In code this is primarily a storage namespace and artifact root.",
        migration_recommendation="keep as internal codename",
    ),
    "vow": PublicTerm(
        current_term="vow",
        public_term="integrity contract",
        classification="contextualize",
        rationale="References canonical digest and immutable integrity anchors.",
        migration_recommendation="keep as internal codename",
    ),
    "consciousness layer": PublicTerm(
        current_term="consciousness layer",
        public_term="deterministic state-processing layer",
        classification="replace",
        rationale="Documentation explicitly defines modules as non-autonomous state processors.",
        migration_recommendation="docs-only translation",
    ),
    "daemon": PublicTerm(
        current_term="daemon",
        public_term="background worker",
        classification="keep",
        rationale="Daemon is standard engineering vocabulary when used literally.",
        migration_recommendation="rename in code",
    ),
    "observatory": PublicTerm(
        current_term="observatory",
        public_term="observability",
        classification="replace",
        rationale="CLI surfaces expose status, trend, and index reporting functions.",
        migration_recommendation="alias in interfaces",
    ),
    "forge": PublicTerm(
        current_term="forge",
        public_term="change pipeline",
        classification="clarify",
        rationale="Forge commands queue, gate, run, and record change operations.",
        migration_recommendation="alias in interfaces",
    ),
}


def translate_public_term(term: str) -> PublicTerm | None:
    """Return translation metadata for *term* if a deterministic mapping exists."""

    return PUBLIC_LANGUAGE_MAP.get(term.strip().lower())
