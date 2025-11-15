"""Digest helpers for Cathedral governance events."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, TYPE_CHECKING

from .amendment import Amendment

if TYPE_CHECKING:  # pragma: no cover
    from .review import ReviewResult

__all__ = [
    "DEFAULT_CATHEDRAL_CONFIG",
    "CathedralDigest",
]

DEFAULT_CATHEDRAL_CONFIG = {
    "review_log": str(Path("runtime") / "logs" / "cathedral_review.log"),
    "quarantine_dir": "C:/SentientOS/quarantine",
    "ledger_path": "C:/SentientOS/cathedral/ledger.jsonl",
    "rollback_dir": "C:/SentientOS/cathedral/rollback",
}


@dataclass(frozen=True)
class CathedralDigest:
    """Aggregated counters derived from review and rollback outcomes."""

    accepted: int = 0
    applied: int = 0
    quarantined: int = 0
    rollbacks: int = 0
    auto_reverts: int = 0
    last_applied_id: Optional[str] = None
    last_quarantined_id: Optional[str] = None
    last_quarantine_error: Optional[str] = None
    last_reverted_id: Optional[str] = None

    @classmethod
    def from_log(cls, path: Path) -> "CathedralDigest":
        accepted = 0
        quarantined = 0
        last_id: Optional[str] = None
        last_error: Optional[str] = None
        if not path.exists():
            return cls()
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                status = str(entry.get("status") or "").lower()
                if status == "accepted":
                    accepted += 1
                elif status == "quarantined":
                    quarantined += 1
                    last_id = str(entry.get("amendment_id") or "") or last_id
                    errors = entry.get("invariant_errors") or entry.get("validation_errors") or []
                    if isinstance(errors, Iterable) and not isinstance(errors, (str, bytes)):
                        for item in errors:
                            if isinstance(item, str) and item:
                                last_error = item
                                break
        except OSError:
            return cls()
        return cls(
            accepted=accepted,
            applied=0,
            quarantined=quarantined,
            rollbacks=0,
            auto_reverts=0,
            last_applied_id=None,
            last_quarantined_id=last_id,
            last_quarantine_error=last_error,
            last_reverted_id=None,
        )

    def to_dict(self) -> dict[str, Optional[str] | int]:
        return {
            "accepted": self.accepted,
            "applied": self.applied,
            "quarantined": self.quarantined,
            "rollbacks": self.rollbacks,
            "auto_reverts": self.auto_reverts,
            "last_applied_id": self.last_applied_id,
            "last_quarantined_id": self.last_quarantined_id,
            "last_quarantine_error": self.last_quarantine_error,
            "last_reverted_id": self.last_reverted_id,
        }

    def record(self, amendment: Amendment, result: "ReviewResult") -> "CathedralDigest":
        status = getattr(result, "status", "").lower()
        if status == "accepted":
            return replace(self, accepted=self.accepted + 1)
        if status == "quarantined":
            errors = list(getattr(result, "invariant_errors", []) or [])
            if not errors:
                errors = list(getattr(result, "validation_errors", []) or [])
            message = errors[0] if errors else "Quarantined pending review"
            return replace(
                self,
                quarantined=self.quarantined + 1,
                last_quarantined_id=amendment.id,
                last_quarantine_error=message,
            )
        return self

    def record_application(self, amendment: Amendment, status: str) -> "CathedralDigest":
        if status not in {"applied", "partial"}:
            return self
        return replace(
            self,
            applied=self.applied + 1,
            last_applied_id=amendment.id,
        )

    def record_rollback(self, amendment_id: str, status: str, *, auto: bool) -> "CathedralDigest":
        if status not in {"success", "partial"}:
            return self
        auto_increment = 1 if auto else 0
        return replace(
            self,
            rollbacks=self.rollbacks + 1,
            auto_reverts=self.auto_reverts + auto_increment,
            last_reverted_id=amendment_id,
        )

    def record_post_apply_quarantine(self, amendment: Amendment, reason: str) -> "CathedralDigest":
        return replace(
            self,
            quarantined=self.quarantined + 1,
            last_quarantined_id=amendment.id,
            last_quarantine_error=reason,
        )

    def timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()
