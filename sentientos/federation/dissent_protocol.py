from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class DissentEvent:
    disagreements: List[Dict[str, object]]
    created_at: datetime
    quarantined: bool
    alert: bool
    override_vote: bool

    def to_dict(self) -> Dict[str, object]:
        return {
            "disagreements": self.disagreements,
            "created_at": self.created_at.isoformat(),
            "quarantined": self.quarantined,
            "alert": self.alert,
            "override_vote": self.override_vote,
        }


class FederatedDissentProtocol:
    def __init__(self, quarantine_after_hours: int = 6, now: Optional[datetime] = None) -> None:
        self.quarantine_after = timedelta(hours=quarantine_after_hours)
        self.now = now or datetime.utcnow()

    def _disagreement_entries(self, local: Dict[str, object], remote: Dict[str, object]) -> List[Dict[str, object]]:
        disagreements: List[Dict[str, object]] = []
        for field in ("glossary", "doctrine_digest", "symbolic_merges"):
            if local.get(field) != remote.get(field):
                disagreements.append({"field": field, "local": local.get(field), "remote": remote.get(field)})
        return disagreements

    def evaluate(
        self, local_state: Dict[str, object], remote_state: Dict[str, object], destination: Path, created_at: Optional[datetime] = None
    ) -> DissentEvent:
        created_at = created_at or self.now
        disagreements = self._disagreement_entries(local_state, remote_state)
        quarantined = False
        alert = False
        override_vote = False

        if disagreements:
            elapsed = self.now - created_at
            if elapsed >= self.quarantine_after:
                quarantined = True
                alert = True
                override_vote = True
            else:
                alert = True

        event = DissentEvent(
            disagreements=disagreements,
            created_at=created_at,
            quarantined=quarantined,
            alert=alert,
            override_vote=override_vote,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict()) + "\n")
        return event
