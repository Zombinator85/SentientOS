"""Recovery readiness placeholders (non-executing)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


RecoveryLadderRegistry: Mapping[str, str] = {}


@dataclass(frozen=True)
class RecoveryProofArtifact:
    """Placeholder for future recovery proof artifacts."""

    recovery_id: str
    evidence_hash: str
