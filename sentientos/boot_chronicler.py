"""Boot retrospective narration for SentientOS awakenings.

This module links the existing change narration utilities with the boot
ceremony so that every awakening can include a short retrospective about what
changed since the previous cycle.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Tuple

from .change_narrator import ChangeCollector, ChangeSet, DiffSummarizer, ScopeFilter
from .storage import get_state_file

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ChangeRecall:
    """Retrieve change data that has not yet been narrated during boot."""

    collector: ChangeCollector

    def gather(self, *, now: datetime | None = None) -> Tuple[ScopeFilter, ChangeSet]:
        """Return the unreported change set and scope used for collection."""

        scope = ScopeFilter(since=None, modules=set(), change_types=set(), requested=True)
        change_set = self.collector.collect(scope, now=now)
        return scope, change_set


class Chronicler:
    """Compose a single narrative passage summarising the collected changes."""

    def __init__(self, summarizer: DiffSummarizer | None = None) -> None:
        self._summarizer = summarizer or DiffSummarizer()

    def compose(self, change_set: ChangeSet) -> str | None:
        sentences = self._summarizer.summarize(change_set)
        if not sentences:
            return None

        lead = f"Since my last awakening, {sentences[0].strip()}"
        additions: list[str] = []
        for sentence in sentences[1:]:
            fragment = sentence.strip()
            if not fragment:
                continue
            additions.append(f"Additionally, {fragment}")

        narrative = " ".join([lead, *additions]).strip()
        if narrative and not narrative.endswith(('.', '!', '?')):
            narrative += '.'
        return narrative


@dataclass(slots=True)
class MemoryMark:
    """Persist which changes have been narrated so they are not repeated."""

    collector: ChangeCollector

    def record(
        self,
        change_set: ChangeSet,
        *,
        scope: ScopeFilter,
        response: str,
        timestamp: datetime | None = None,
    ) -> None:
        self.collector.mark_reported(
            change_set,
            scope=scope,
            response=response,
            timestamp=timestamp or change_set.collected_at,
        )


class CeremonyLink:
    """Inject the retrospective into the boot ceremony output."""

    def __init__(
        self,
        emitter,
        change_recall: ChangeRecall,
        chronicler: Chronicler,
        memory_mark: MemoryMark,
        *,
        salutation: str = "Allen",
    ) -> None:
        self._emitter = emitter
        self._change_recall = change_recall
        self._chronicler = chronicler
        self._memory_mark = memory_mark
        self._salutation = salutation.strip()

    def narrate(self, *, now: datetime | None = None) -> None:
        try:
            scope, change_set = self._change_recall.gather(now=now)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Unable to recall boot retrospective changes: %s", exc)
            return

        if not change_set.commits and not change_set.ledger_entries:
            return

        try:
            narrative = self._chronicler.compose(change_set)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Unable to compose boot retrospective: %s", exc)
            return

        if not narrative:
            return

        narrative = narrative.strip()
        if self._salutation:
            message = f"{self._salutation}, {narrative}"
        else:
            message = narrative

        try:
            self._emitter.emit(message, level="info")
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Unable to emit boot retrospective: %s", exc)

        try:
            self._memory_mark.record(
                change_set,
                scope=scope,
                response=message,
                timestamp=change_set.collected_at,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Unable to persist boot retrospective memory: %s", exc)


def build_boot_ceremony_link(emitter, *, collector: ChangeCollector | None = None) -> CeremonyLink:
    """Factory returning a :class:`CeremonyLink` configured for runtime use."""

    if collector is None:
        repo_path = Path(os.getenv("SENTIENTOS_REPO_PATH", Path.cwd()))
        ledger_path_env = os.getenv("CODEX_LEDGER_PATH")
        ledger_path = Path(ledger_path_env) if ledger_path_env else None
        collector = ChangeCollector(
            repo_path=repo_path,
            state_path=get_state_file("boot_chronicler_state.json"),
            ledger_path=ledger_path,
        )

    change_recall = ChangeRecall(collector)
    chronicler = Chronicler()
    memory_mark = MemoryMark(collector)
    return CeremonyLink(emitter, change_recall, chronicler, memory_mark)


__all__ = [
    "ChangeRecall",
    "Chronicler",
    "CeremonyLink",
    "MemoryMark",
    "build_boot_ceremony_link",
]
