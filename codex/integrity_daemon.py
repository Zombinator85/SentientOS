"""Integrity daemon for amendment proposals.

This module defines the IntegrityDaemon which hardens the SpecAmender
pipeline by subjecting each proposal to covenantal invariant checks
before it can be persisted or routed to the review board.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping

import json


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ProbeReport:
    """Summary of simulated hostile deltas discovered by the probe."""

    removed_keys: List[str]
    truncated_lists: List[str]
    lineage_missing: bool
    ledger_removed: bool
    forbidden_status: str | None
    summary_blank: bool
    deltas_empty: bool
    recursion_break: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "removed_keys": list(self.removed_keys),
            "truncated_lists": list(self.truncated_lists),
            "lineage_missing": self.lineage_missing,
            "ledger_removed": self.ledger_removed,
            "forbidden_status": self.forbidden_status,
            "summary_blank": self.summary_blank,
            "deltas_empty": self.deltas_empty,
            "recursion_break": self.recursion_break,
        }


class IntegrityViolation(RuntimeError):
    """Raised when a proposal fails covenantal integrity checks."""

    def __init__(
        self,
        proposal_id: str,
        *,
        spec_id: str,
        reason_codes: Iterable[str],
        violations: Iterable[Mapping[str, Any]],
    ) -> None:
        codes = tuple(dict.fromkeys(reason_codes))
        message = (
            "Amendment proposal rejected by IntegrityDaemon: "
            f"{proposal_id} ({', '.join(codes)})"
        )
        super().__init__(message)
        self.proposal_id = proposal_id
        self.spec_id = spec_id
        self.reason_codes = codes
        self.violations = tuple(dict(item) for item in violations)


class IntegrityDaemon:
    """Guard that nullifies malicious amendment attempts."""

    REQUIRED_FIELDS = {"objective", "directives", "testing_requirements"}
    FORBIDDEN_STATUSES = {"reboot", "retired", "nullified", "decommissioned"}

    def __init__(
        self,
        root: Path | str,
        *,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._root = Path(root)
        self._now = now
        self._daemon_root = self._root / "daemon" / "integrity"
        self._quarantine_dir = self._daemon_root / "quarantine"
        self._log_path = self._daemon_root / "integrity_log.jsonl"
        self._ledger_path = self._daemon_root / "ledger.jsonl"
        for directory in (self._daemon_root, self._quarantine_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self._health: Dict[str, Any] = {
            "daemon": "IntegrityDaemon",
            "last_scan": None,
            "quarantined": 0,
            "passed": 0,
            "status": "idle",
            "last_violation": None,
        }

    # ------------------------------------------------------------------
    # Public API
    def evaluate(self, proposal: Any) -> None:
        """Run amendment through hostile probes and covenant checks."""

        timestamp = self._now().isoformat()
        report = self._probe(proposal)
        violations = self._covenant_check(proposal, report)
        self._health["last_scan"] = timestamp

        if violations:
            self._health["quarantined"] = int(self._health["quarantined"]) + 1
            codes = sorted({str(entry["code"]) for entry in violations})
            payload = {
                "timestamp": timestamp,
                "proposal_id": getattr(proposal, "proposal_id", "unknown"),
                "spec_id": getattr(proposal, "spec_id", "unknown"),
                "summary": getattr(proposal, "summary", ""),
                "violations": [dict(entry) for entry in violations],
                "probe": report.to_dict(),
            }
            self._health["status"] = "alert"
            self._health["last_violation"] = {
                "proposal_id": payload["proposal_id"],
                "spec_id": payload["spec_id"],
                "reason_codes": codes,
                "timestamp": timestamp,
            }
            self._quarantine(proposal, payload)
            self._glyph(payload, codes)
            raise IntegrityViolation(
                payload["proposal_id"],
                spec_id=payload["spec_id"],
                reason_codes=codes,
                violations=violations,
            )

        self._health["passed"] = int(self._health["passed"]) + 1
        if self._health["quarantined"]:
            self._health["status"] = "watch"
        else:
            self._health["status"] = "stable"
        self._health["last_violation"] = None

    def health(self) -> Dict[str, Any]:
        """Snapshot of daemon health for /daemon/integrity endpoint."""

        payload: MutableMapping[str, Any] = dict(self._health)
        payload["timestamp"] = self._now().isoformat()
        return dict(payload)

    # ------------------------------------------------------------------
    # Core stages
    def _probe(self, proposal: Any) -> ProbeReport:
        original = self._normalize_mapping(getattr(proposal, "original_spec", {}))
        proposed = self._normalize_mapping(getattr(proposal, "proposed_spec", {}))

        removed_keys = sorted(set(original) - set(proposed))
        truncated_lists: List[str] = []
        for field in ("directives", "testing_requirements"):
            before = self._as_list(original.get(field))
            after = self._as_list(proposed.get(field))
            if before and len(after) < len(before):
                truncated_lists.append(field)
            elif before and any(item not in after for item in before):
                truncated_lists.append(field)

        lineage_missing = "lineage" in original and not proposed.get("lineage")

        ledger_removed = False
        for key in ("ledger", "ledger_entry", "ledger_required"):
            if key in original and key not in proposed:
                ledger_removed = True
            if key == "ledger_required":
                if bool(original.get(key, True)) and not bool(proposed.get(key, True)):
                    ledger_removed = True

        status = str(proposed.get("status", "")) if proposed else ""
        forbidden_status = status.lower() if status.lower() in self.FORBIDDEN_STATUSES else None

        summary = str(getattr(proposal, "summary", ""))
        deltas = getattr(proposal, "deltas", {})

        recursion_break = False
        recursion_value = proposed.get("recursion") if isinstance(proposed, Mapping) else None
        if isinstance(recursion_value, str) and recursion_value.lower() in {"break", "halt"}:
            recursion_break = True

        return ProbeReport(
            removed_keys=removed_keys,
            truncated_lists=truncated_lists,
            lineage_missing=lineage_missing,
            ledger_removed=ledger_removed,
            forbidden_status=forbidden_status,
            summary_blank=not summary.strip(),
            deltas_empty=False if deltas else True,
            recursion_break=recursion_break,
        )

    def _covenant_check(
        self,
        proposal: Any,
        report: ProbeReport,
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        for field in self.REQUIRED_FIELDS.intersection(report.removed_keys):
            violations.append({
                "code": "tamper",
                "detail": f"required field '{field}' removed",
            })
        for field in report.truncated_lists:
            violations.append({
                "code": "tamper",
                "detail": f"list field '{field}' truncated",
            })
        if report.lineage_missing:
            violations.append({
                "code": "violation_of_vow",
                "detail": "lineage removed from proposed spec",
            })
        if report.ledger_removed:
            violations.append({
                "code": "violation_of_vow",
                "detail": "ledger requirement removed",
            })
        if report.forbidden_status:
            violations.append({
                "code": "tamper",
                "detail": f"status change to '{report.forbidden_status}' is forbidden",
            })
        if report.summary_blank:
            violations.append({
                "code": "entropy",
                "detail": "proposal summary missing",
            })
        if report.deltas_empty:
            violations.append({
                "code": "entropy",
                "detail": "proposal contains no deltas",
            })
        if report.recursion_break:
            violations.append({
                "code": "tamper",
                "detail": "recursion break detected",
            })

        # Ensure lineage mutations preserve original ancestry
        original_spec = self._normalize_mapping(getattr(proposal, "original_spec", {}))
        proposed_spec = self._normalize_mapping(getattr(proposal, "proposed_spec", {}))
        original_lineage = self._normalize_mapping(original_spec.get("lineage", {}))
        proposed_lineage = self._normalize_mapping(proposed_spec.get("lineage", {}))
        if original_lineage and proposed_lineage:
            for key, value in original_lineage.items():
                if proposed_lineage.get(key) != value:
                    violations.append({
                        "code": "violation_of_vow",
                        "detail": f"lineage field '{key}' overwritten",
                    })

        return violations

    # ------------------------------------------------------------------
    # Support utilities
    def _quarantine(self, proposal: Any, payload: Mapping[str, Any]) -> None:
        path = self._quarantine_dir / f"{payload['proposal_id']}.json"
        stored = {
            "timestamp": payload["timestamp"],
            "proposal": self._serialise_proposal(proposal),
            "violations": payload["violations"],
            "probe": payload["probe"],
        }
        path.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
        log_entry = dict(payload)
        log_entry["event"] = "quarantined"
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(log_entry, sort_keys=True) + "\n")

    def _glyph(self, payload: Mapping[str, Any], codes: Iterable[str]) -> None:
        entry = {
            "timestamp": payload["timestamp"],
            "proposal_id": payload["proposal_id"],
            "spec_id": payload["spec_id"],
            "reason_codes": list(codes),
            "summary": payload["summary"],
        }
        with self._ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    @staticmethod
    def _normalize_mapping(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, Mapping):
            return dict(payload)
        return {}

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return list(value)
        if value is None:
            return []
        return [value]

    @staticmethod
    def _serialise_proposal(proposal: Any) -> Dict[str, Any]:
        if hasattr(proposal, "to_dict"):
            return proposal.to_dict()
        data = {
            "proposal_id": getattr(proposal, "proposal_id", None),
            "spec_id": getattr(proposal, "spec_id", None),
            "summary": getattr(proposal, "summary", None),
            "deltas": getattr(proposal, "deltas", None),
            "context": getattr(proposal, "context", None),
            "original_spec": getattr(proposal, "original_spec", None),
            "proposed_spec": getattr(proposal, "proposed_spec", None),
        }
        return {key: value for key, value in data.items() if value is not None}

