from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Tuple
import subprocess

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
    version_id: str | None = None
    git_commit: str | None = None
    source: Mapping[str, str] | None = None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "axis": self.axis.value,
            "measurement_method": self.measurement_method,
            "delta": self.delta,
            "notes": self.notes,
        }
        if self.evidence:
            record["evidence"] = dict(self.evidence)
        if self.version_id:
            record["version_id"] = self.version_id
        if self.git_commit:
            record["git_commit"] = self.git_commit
        if self.source:
            record["source"] = {
                "module": str(self.source.get("module", "")),
                "hook": str(self.source.get("hook", "")),
            }
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "CapabilityLedgerEntry":
        axis_value = CapabilityAxis(str(record["axis"]))
        evidence = record.get("evidence")
        source = record.get("source")
        return cls(
            axis=axis_value,
            measurement_method=str(record.get("measurement_method", "")),
            delta=str(record.get("delta", "")),
            notes=str(record.get("notes", "")),
            evidence=dict(evidence) if isinstance(evidence, Mapping) else None,
            version_id=str(record["version_id"]) if record.get("version_id") else None,
            git_commit=str(record["git_commit"]) if record.get("git_commit") else None,
            source={
                "module": str(source.get("module", "")),
                "hook": str(source.get("hook", "")),
            }
            if isinstance(source, Mapping)
            else None,
        )


def _parse_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


class CapabilityGrowthLedger:
    """Append-only ledger for epistemic capability metrics."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_log_path("capability_growth_ledger.jsonl", "CAPABILITY_GROWTH_LEDGER")

    @property
    def path(self) -> Path:
        return self._path

    def record(self, entry: CapabilityLedgerEntry) -> CapabilityLedgerEntry:
        enriched = self._with_source_metadata(entry)
        enriched = self._with_version_metadata(enriched)
        append_json(self._path, enriched.to_record(), emotion="neutral", consent="epistemic")
        return enriched

    def view(self) -> Tuple[CapabilityLedgerEntry, ...]:
        raw_entries: Iterable[Mapping[str, Any]] = read_json(self._path)
        parsed: List[CapabilityLedgerEntry] = [CapabilityLedgerEntry.from_record(row) for row in raw_entries]
        return tuple(parsed)

    def inspect(
        self,
        *,
        axis: CapabilityAxis | str | None = None,
        since: str | None = None,
        until: str | None = None,
        version_id: str | None = None,
        git_commit: str | None = None,
    ) -> Tuple[Mapping[str, Any], ...]:
        """Return raw ledger rows filtered by axis and optional time window."""

        axis_value = CapabilityAxis(axis).value if axis is not None else None
        raw_entries: Iterable[Mapping[str, Any]] = read_json(self._path)

        since_dt = _parse_iso8601(since) if since else None
        until_dt = _parse_iso8601(until) if until else None

        selected: List[Mapping[str, Any]] = []
        for row in raw_entries:
            if axis_value and str(row.get("axis")) != axis_value:
                continue

            if version_id and str(row.get("version_id")) != version_id:
                continue

            if git_commit and str(row.get("git_commit")) != git_commit:
                continue

            timestamp_value = row.get("timestamp")
            entry_dt = _parse_iso8601(str(timestamp_value)) if timestamp_value else None
            if (since_dt or until_dt) and not entry_dt:
                continue
            if since_dt and entry_dt and entry_dt < since_dt:
                continue
            if until_dt and entry_dt and entry_dt > until_dt:
                continue

            selected.append(dict(row))

        return tuple(selected)

    def _with_version_metadata(self, entry: CapabilityLedgerEntry) -> CapabilityLedgerEntry:
        if entry.version_id and entry.git_commit:
            return entry

        resolved_version = entry.version_id or _read_version_id()
        resolved_commit = entry.git_commit or _read_git_commit()

        if resolved_version == entry.version_id and resolved_commit == entry.git_commit:
            return entry

        return replace(entry, version_id=resolved_version, git_commit=resolved_commit)

    def _with_source_metadata(self, entry: CapabilityLedgerEntry) -> CapabilityLedgerEntry:
        if entry.source:
            return entry

        hook = entry.measurement_method or "unspecified"
        return replace(entry, source={"module": "manual", "hook": hook})


_DEFAULT_LEDGER = CapabilityGrowthLedger()


def append(entry: CapabilityLedgerEntry) -> CapabilityLedgerEntry:
    """Record a deterministic capability ledger entry (append-only)."""

    return _DEFAULT_LEDGER.record(entry)


def view() -> Tuple[CapabilityLedgerEntry, ...]:
    """Read-only accessor for audit/inspection of ledger entries."""

    return _DEFAULT_LEDGER.view()


def inspect(
    *,
    axis: CapabilityAxis | str | None = None,
    since: str | None = None,
    until: str | None = None,
    version_id: str | None = None,
    git_commit: str | None = None,
) -> Tuple[Mapping[str, Any], ...]:
    """Inspection accessor returning raw ledger entries with optional filters."""

    return _DEFAULT_LEDGER.inspect(
        axis=axis,
        since=since,
        until=until,
        version_id=version_id,
        git_commit=git_commit,
    )


def _read_version_id() -> str | None:
    try:
        return Path("VERSION").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _read_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
    except (OSError, ValueError):
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


__all__ = [
    "CapabilityAxis",
    "CapabilityLedgerEntry",
    "CapabilityGrowthLedger",
    "append",
    "view",
    "inspect",
]
