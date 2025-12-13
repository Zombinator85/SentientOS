from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Tuple

from logging_config import get_log_path
from log_utils import append_json, read_json


class CapabilityAxis(str, Enum):
    """Capability growth axes (epistemic only)."""

    STRUCTURAL_RICHNESS = "R"
    CAPABILITY_COVERAGE = "C"
    EXPRESSIVE_RANGE = "E"
    INTERNAL_COHERENCE = "K"


@dataclass(frozen=True)
class CapabilityLedgerEntry:
    """Immutable entry describing a capability observation."""

    axis: CapabilityAxis
    measurement_method: str
    delta: str
    notes: str = ""
    evidence: Mapping[str, Any] | None = None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "axis": self.axis.value,
            "measurement_method": self.measurement_method,
            "delta": self.delta,
            "notes": self.notes,
        }
        if self.evidence:
            record["evidence"] = dict(self.evidence)
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "CapabilityLedgerEntry":
        axis_value = CapabilityAxis(str(record["axis"]))
        evidence = record.get("evidence")
        return cls(
            axis=axis_value,
            measurement_method=str(record.get("measurement_method", "")),
            delta=str(record.get("delta", "")),
            notes=str(record.get("notes", "")),
            evidence=dict(evidence) if isinstance(evidence, Mapping) else None,
        )


class CapabilityGrowthLedger:
    """Append-only ledger for epistemic capability metrics."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_log_path("capability_growth_ledger.jsonl", "CAPABILITY_GROWTH_LEDGER")

    @property
    def path(self) -> Path:
        return self._path

    def record(self, entry: CapabilityLedgerEntry) -> CapabilityLedgerEntry:
        append_json(self._path, entry.to_record(), emotion="neutral", consent="epistemic")
        return entry

    def view(self) -> Tuple[CapabilityLedgerEntry, ...]:
        raw_entries: Iterable[Mapping[str, Any]] = read_json(self._path)
        parsed: List[CapabilityLedgerEntry] = [CapabilityLedgerEntry.from_record(row) for row in raw_entries]
        return tuple(parsed)


_DEFAULT_LEDGER = CapabilityGrowthLedger()


def append(entry: CapabilityLedgerEntry) -> CapabilityLedgerEntry:
    """Record a deterministic capability ledger entry (append-only)."""

    return _DEFAULT_LEDGER.record(entry)


def view() -> Tuple[CapabilityLedgerEntry, ...]:
    """Read-only accessor for audit/inspection of ledger entries."""

    return _DEFAULT_LEDGER.view()


__all__ = [
    "CapabilityAxis",
    "CapabilityLedgerEntry",
    "CapabilityGrowthLedger",
    "append",
    "view",
]
