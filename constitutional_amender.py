from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence


@dataclass
class CouncilConstitutionalAmender:
    """Manage doctrine amendments with quorum tracking and freeze windows."""

    amendment_log: Path = Path("constitutional_change.jsonl")
    lineage_log: Path = Path("doctrine_amendment_log.md")
    freeze_until: datetime | None = None

    def _is_frozen(self, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        return self.freeze_until is not None and now < self.freeze_until

    def propose(
        self,
        change: Mapping[str, object],
        quorum: Sequence[str] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.utcnow()
        if self._is_frozen(now):
            raise RuntimeError("Doctrine amendments are currently frozen")

        quorum_list = list(quorum or [])
        record = {
            "timestamp": now.isoformat(),
            "change": dict(change),
            "quorum": quorum_list,
            "approved": bool(quorum_list),
        }

        self.amendment_log.parent.mkdir(parents=True, exist_ok=True)
        with self.amendment_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

        lineage_entry = (
            f"- {now.date()}: {change.get('title', 'Amendment')} "
            f"(quorum={len(quorum_list)})"
        )
        prefix = "# Doctrine Amendment Lineage\n\n" if not self.lineage_log.exists() else ""
        with self.lineage_log.open("a", encoding="utf-8") as handle:
            if prefix:
                handle.write(prefix)
            handle.write(lineage_entry + "\n")

        return record


__all__ = ["CouncilConstitutionalAmender"]
