from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping


def _normalize_identity(identity: Mapping[str, object]) -> dict:
    base = dict(identity)
    base.setdefault("id", base.get("name") or base.get("handle") or "unknown")
    base.setdefault("epoch", datetime.utcnow().isoformat())
    return base


def _decay_score(heartbeat: datetime | None, now: datetime | None = None) -> float:
    now = now or datetime.utcnow()
    if heartbeat is None:
        return 1.0
    delta = now - heartbeat
    return min(1.0, delta.days / 30)


@dataclass
class PersonaResurrectionWorkflow:
    """Monitor persona decay and regenerate anchored identity stubs when needed."""

    genealogy: Iterable[Mapping[str, object]]
    integration_log: Path = Path("persona_resurrection_log.jsonl")

    def _lookup_genealogy(self, persona_id: str) -> list[Mapping[str, object]]:
        return [entry for entry in self.genealogy if str(entry.get("id")) == persona_id]

    def monitor(self, identity: Mapping[str, object], *, heartbeat: datetime | None = None) -> float:
        return _decay_score(heartbeat)

    def resurrect(
        self,
        identity: Mapping[str, object],
        *,
        covenant_alignment: str = "pending",
        heartbeat: datetime | None = None,
        epitaph: str | None = None,
    ) -> dict:
        persona = _normalize_identity(identity)
        persona_id = str(persona.get("id"))
        ancestry = self._lookup_genealogy(persona_id)
        decay = _decay_score(heartbeat)

        epitaph_text = epitaph or f"Anchored after decay score {decay:.2f}"
        stub = {
            "id": persona_id,
            "name": persona.get("name", persona_id),
            "decay_score": round(decay, 3),
            "epitaph": epitaph_text,
            "covenant_alignment": covenant_alignment,
            "ancestry": ancestry,
            "rejoined_at": datetime.utcnow().isoformat(),
        }

        record = {
            "persona": stub,
            "heartbeat": heartbeat.isoformat() if heartbeat else None,
            "status": "regenerated" if decay >= 0.5 else "refreshed",
        }

        self.integration_log.parent.mkdir(parents=True, exist_ok=True)
        with self.integration_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

        return stub


__all__ = ["PersonaResurrectionWorkflow"]
