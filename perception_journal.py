"""Lightweight context journal for SentientOS perception modules."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from logging_config import get_log_path


@dataclass
class JournalEntry:
    """Structured perception log entry."""

    timestamp: str
    tags: list[str]
    note: str
    extra: dict[str, object] = field(default_factory=dict)


class PerceptionJournal:
    """Append-only JSONL journal for environmental context tags."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_log_path("perception_journal.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        tags: Iterable[str],
        note: str,
        extra: Mapping[str, object] | None = None,
    ) -> JournalEntry:
        entry = JournalEntry(
            timestamp=datetime.utcnow().isoformat(),
            tags=list(tags),
            note=note,
            extra=dict(extra or {}),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.__dict__, ensure_ascii=False) + "\n")
        return entry


__all__ = ["PerceptionJournal", "JournalEntry"]
