"""Cooldown window for governance proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CooldownRecord:
    proposal_hash: str
    symbols: frozenset[str]
    resolved_cycle: int


class GovernanceCooldown:
    """Suppress near-identical proposals during cooldown windows."""

    def __init__(self, window: int = 3, overlap_threshold: float = 0.6) -> None:
        self.window = max(1, int(window))
        self.overlap_threshold = float(overlap_threshold)
        self._resolved: list[CooldownRecord] = []
        self._hits: list[dict[str, object]] = []

    @property
    def hits(self) -> list[dict[str, object]]:
        return list(self._hits)

    def register_resolution(self, proposal_hash: str, symbols: Iterable[str], cycle: int) -> None:
        self._resolved.append(
            CooldownRecord(proposal_hash=str(proposal_hash), symbols=frozenset(map(str, symbols)), resolved_cycle=int(cycle))
        )

    def allow_submission(self, proposal_hash: str, symbols: Iterable[str], cycle: int) -> dict[str, object]:
        symbol_set = frozenset(map(str, symbols))
        suppressed = False
        for record in self._resolved:
            if cycle - record.resolved_cycle > self.window:
                continue
            if self._is_similar(record, proposal_hash, symbol_set):
                suppressed = True
                self._hits.append(
                    {
                        "proposal_hash": str(proposal_hash),
                        "resolved_hash": record.proposal_hash,
                        "cycle": int(cycle),
                        "resolved_cycle": record.resolved_cycle,
                        "overlap": self._overlap(record.symbols, symbol_set),
                    }
                )
                break

        return {
            "allowed": not suppressed,
            "cooldown": suppressed,
            "hits": self.hits,
        }

    def _is_similar(self, record: CooldownRecord, proposal_hash: str, symbols: frozenset[str]) -> bool:
        if record.proposal_hash == str(proposal_hash):
            return True
        overlap = self._overlap(record.symbols, symbols)
        return overlap >= self.overlap_threshold

    def _overlap(self, existing: frozenset[str], incoming: frozenset[str]) -> float:
        if not existing or not incoming:
            return 0.0
        intersection = len(existing & incoming)
        union = len(existing | incoming)
        return intersection / union if union else 0.0


__all__ = ["CooldownRecord", "GovernanceCooldown"]
