"""Constraint registry enforcing justification and engagement lineage.

The registry is intentionally lightweight and immutable in its contract: a
constraint cannot exist without justification text, and each engagement updates
review metadata without granting new authority. Pressure engines may rely on the
registry to prevent untracked or "cold" constraint identifiers from gathering
pressure silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Dict, Iterable, List, Mapping, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for typing only
    from sentientos.pressure_engagement import ConstraintEngagementRecord


class ConstraintNotRegisteredError(RuntimeError):
    """Raised when a constraint lacks a registered justification."""


@dataclass
class ConstraintRecord:
    constraint_id: str
    justification: str
    lineage_from: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_reviewed_at: Optional[float] = None
    engagements: List["ConstraintEngagementRecord"] = field(default_factory=list)

    def to_payload(self) -> Dict[str, object]:
        return {
            "constraint_id": self.constraint_id,
            "justification": self.justification,
            "lineage_from": self.lineage_from,
            "created_at": self.created_at,
            "last_reviewed_at": self.last_reviewed_at,
            "engagements": [getattr(item, "engagement_id", None) for item in self.engagements],
        }


class ConstraintRegistry:
    """Canonical registry enforcing justification and review lineage."""

    def __init__(self) -> None:
        self._records: Dict[str, ConstraintRecord] = {}

    def register(
        self, constraint_id: str, justification: str, *, lineage_from: str | None = None
    ) -> ConstraintRecord:
        if not isinstance(justification, str) or not justification.strip():
            raise ValueError("justification text is required to register a constraint")
        record = self._records.get(constraint_id)
        now = time.time()
        if record is None:
            record = ConstraintRecord(
                constraint_id=constraint_id,
                justification=justification.strip(),
                lineage_from=lineage_from,
                created_at=now,
                last_reviewed_at=now,
            )
            self._records[constraint_id] = record
        else:
            record.justification = justification.strip()
            record.lineage_from = lineage_from or record.lineage_from
            record.last_reviewed_at = now
        return record

    def record_engagement(self, engagement: "ConstraintEngagementRecord") -> ConstraintRecord:
        record = self.require(constraint_id=engagement.constraint_id)
        record.engagements.append(engagement)
        record.justification = engagement.justification
        record.last_reviewed_at = engagement.created_at
        record.lineage_from = engagement.lineage_from or record.lineage_from
        return record

    def require(self, constraint_id: str) -> ConstraintRecord:
        record = self._records.get(constraint_id)
        if record is None:
            raise ConstraintNotRegisteredError(
                f"constraint '{constraint_id}' must be registered with justification"
            )
        return record

    def registered_constraints(self) -> Iterable[str]:
        return tuple(self._records.keys())

    def as_payload(self) -> Dict[str, Mapping[str, object]]:
        return {key: value.to_payload() for key, value in self._records.items()}

