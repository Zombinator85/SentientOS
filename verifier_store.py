from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from sentientos.storage import get_data_root


@dataclass(frozen=True)
class VerifierSummary:
    job_id: str
    script_hash: str
    from_node: str | None
    verdict: str
    created_at: float
    verifier_node: str | None = None
    score: float | None = None

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "job_id": self.job_id,
            "script_hash": self.script_hash,
            "from_node": self.from_node,
            "verdict": self.verdict,
            "created_at": self.created_at,
        }
        if self.verifier_node is not None:
            payload["verifier_node"] = self.verifier_node
        if self.score is not None:
            payload["score"] = self.score
        return payload


class VerifierStore:
    """Persist verification reports on the local filesystem."""

    def __init__(self, root: Optional[Path] = None, *, rotate_bytes: int = 5_000_000) -> None:
        self._root = Path(root) if root else get_data_root() / "verify"
        self._reports_dir = self._root / "reports"
        self._bundles_dir = self._root / "bundles"
        self._index_path = self._root / "reports.jsonl"
        self._rotate_bytes = max(100_000, int(rotate_bytes))
        self._lock = threading.RLock()
        self._root.mkdir(parents=True, exist_ok=True)
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        self._bundles_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def default(cls) -> "VerifierStore":
        return cls()

    # -- persistence helpers -------------------------------------------------

    def save_report(self, report: Mapping[str, object]) -> VerifierSummary:
        """Store the verification ``report`` and append it to the index."""

        job_id = str(report.get("job_id") or "")
        if not job_id:
            raise ValueError("report is missing job_id")
        created_iso = self._extract_timestamp(report)
        created_at = created_iso or time.time()
        summary = VerifierSummary(
            job_id=job_id,
            script_hash=str(report.get("script_hash") or ""),
            from_node=self._optional_string(report.get("from_node")),
            verdict=str(report.get("verdict") or "unknown"),
            created_at=created_at,
            verifier_node=self._optional_string(report.get("verifier_node")),
            score=self._coerce_float(report.get("score")),
        )
        with self._lock:
            self._write_report_file(job_id, report)
            self._rotate_index_if_needed()
            with self._index_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(summary.to_dict(), sort_keys=True) + "\n")
        return summary

    def get_report(self, job_id: str) -> Optional[Dict[str, object]]:
        path = self._reports_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def save_bundle(self, job_id: str, bundle: Mapping[str, object]) -> None:
        path = self._bundles_dir / f"{job_id}.json"
        try:
            path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")

    def load_bundle(self, job_id: str) -> Optional[Dict[str, object]]:
        path = self._bundles_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def get_status(self, job_id: str) -> Optional[VerifierSummary]:
        entries = self._load_index()
        for entry in reversed(entries):
            if entry.get("job_id") == job_id:
                return self._summary_from_entry(entry)
        return None

    def list_reports(self, *, limit: int = 50) -> List[VerifierSummary]:
        entries = self._load_index()
        trimmed = entries[-max(1, limit) :]
        return [self._summary_from_entry(entry) for entry in reversed(trimmed)]

    def verdict_counts(self, *, since: float | None = None) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self._load_index():
            created_at = self._coerce_float(entry.get("created_at"))
            if since is not None and created_at is not None and created_at < since:
                continue
            verdict = str(entry.get("verdict") or "unknown")
            counts[verdict] = counts.get(verdict, 0) + 1
        return counts

    # -- internal helpers ----------------------------------------------------

    def _write_report_file(self, job_id: str, report: Mapping[str, object]) -> None:
        path = self._reports_dir / f"{job_id}.json"
        try:
            path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            # Losing the report is worse than missing pretty formatting: retry
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")

    def _rotate_index_if_needed(self) -> None:
        if not self._index_path.exists():
            return
        try:
            size = self._index_path.stat().st_size
        except OSError:
            return
        if size <= self._rotate_bytes:
            return
        backup = self._index_path.with_name(self._index_path.name + ".1")
        try:
            if backup.exists():
                backup.unlink()
            self._index_path.rename(backup)
        except OSError:
            return

    def _load_index(self) -> List[Dict[str, object]]:
        if not self._index_path.exists():
            return []
        try:
            raw = self._index_path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries: List[Dict[str, object]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                entries.append(record)
        return entries

    @staticmethod
    def _summary_from_entry(entry: Mapping[str, object]) -> VerifierSummary:
        return VerifierSummary(
            job_id=str(entry.get("job_id") or ""),
            script_hash=str(entry.get("script_hash") or ""),
            from_node=VerifierStore._optional_string(entry.get("from_node")),
            verdict=str(entry.get("verdict") or "unknown"),
            created_at=float(entry.get("created_at") or 0.0),
            verifier_node=VerifierStore._optional_string(entry.get("verifier_node")),
            score=VerifierStore._coerce_float(entry.get("score")),
        )

    @staticmethod
    def _extract_timestamp(report: Mapping[str, object]) -> float | None:
        timestamps = report.get("timestamps")
        if isinstance(timestamps, Mapping):
            for key in ("verified", "submitted"):
                value = timestamps.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return _parse_iso_timestamp(value)
                    except ValueError:
                        continue
        return None

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


def _parse_iso_timestamp(value: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


__all__ = [
    "VerifierStore",
    "VerifierSummary",
]
