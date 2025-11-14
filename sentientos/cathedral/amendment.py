"""Amendment primitives for the Cathedral governance pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping

__all__ = [
    "Amendment",
    "amendment_digest",
]


def _canonicalize(value: Any) -> Any:
    """Return a structure with deterministically ordered keys."""

    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, datetime):
        # Normalise to ISO8601 with UTC when tz-aware, else assume UTC.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return value


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("created_at is required")
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise TypeError("created_at must be datetime or ISO8601 string")


@dataclass(frozen=True)
class Amendment:
    """Structured description of a proposed Cathedral change."""

    id: str
    created_at: datetime
    proposer: str
    summary: str
    changes: Dict[str, Any]
    reason: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("amendment id is required")
        if not isinstance(self.changes, Mapping):  # type: ignore[arg-type]
            raise TypeError("changes must be a mapping")
        # Normalise created_at for deterministic serialisation.
        object.__setattr__(self, "created_at", _ensure_datetime(self.created_at))
        object.__setattr__(self, "changes", dict(self._canonical_changes()))

    def _canonical_changes(self) -> Dict[str, Any]:
        return _canonicalize(self.changes)  # type: ignore[return-value]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the amendment to a canonical dictionary."""

        return {
            "id": self.id,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "proposer": self.proposer,
            "summary": self.summary,
            "changes": self._canonical_changes(),
            "reason": self.reason,
        }

    def serialize(self) -> str:
        """Return a canonical JSON representation."""

        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Amendment":
        """Construct an amendment from serialized data."""

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        created_at = _ensure_datetime(payload.get("created_at"))
        changes_obj = payload.get("changes")
        if isinstance(changes_obj, Mapping):
            changes = dict(changes_obj)
        else:
            changes = {}
        return cls(
            id=str(payload.get("id") or ""),
            created_at=created_at,
            proposer=str(payload.get("proposer") or "unknown"),
            summary=str(payload.get("summary") or ""),
            changes=changes,
            reason=str(payload.get("reason") or ""),
        )


def amendment_digest(amendment: Amendment) -> str:
    """Return a deterministic SHA256 digest of the amendment."""

    canonical = amendment.serialize().encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
