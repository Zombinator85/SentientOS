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

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover - fallback path
    yaml = None  # type: ignore[assignment]

from .proof_verifier import ProofReport, ProofVerifier


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
    DEFAULT_PROOF_CONFIG = {"enabled": True, "fail_on_invalid": True}

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
        self._proof_conditions_path = self._daemon_root / "proof_conditions.json"
        for directory in (self._daemon_root, self._quarantine_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self._proof_verifier = ProofVerifier(
            required_fields=self.REQUIRED_FIELDS,
            forbidden_statuses=self.FORBIDDEN_STATUSES,
        )
        self._proof_config = self._load_proof_config()

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
        covenant_violations = self._covenant_check(proposal, report)
        proof_payload = self._prepare_proof_payload(proposal)
        proof_payload["timestamp"] = timestamp
        self.generate_proof_conditions(proposal, proof_payload)
        proof_report = self._proof_verifier.evaluate(proof_payload)
        proof_violations = self._proof_violation_entries(proof_report)
        violations = [*covenant_violations, *proof_violations]
        self._health["last_scan"] = timestamp

        status_label = "QUARANTINED" if violations else "VALID"
        ledger_entry = self._record_ledger_entry(
            timestamp=timestamp,
            proposal=proposal,
            probe=report,
            proof_report=proof_report,
            violations=violations,
            status=status_label,
        )

        if violations:
            self._health["quarantined"] = int(self._health["quarantined"]) + 1
            codes = sorted({str(entry["code"]) for entry in violations})
            payload = dict(ledger_entry)
            self._health["status"] = "alert"
            self._health["last_violation"] = {
                "proposal_id": payload["proposal_id"],
                "spec_id": payload["spec_id"],
                "reason_codes": codes,
                "timestamp": timestamp,
            }
            self._quarantine(proposal, payload)
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

    def generate_proof_conditions(
        self, proposal: Any, payload: Mapping[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Persist the current invariant set and proposal context."""

        proof_payload = dict(payload or self._prepare_proof_payload(proposal))
        conditions = {
            "timestamp": self._now().isoformat(),
            "proposal_id": getattr(proposal, "proposal_id", "unknown"),
            "spec_id": getattr(proposal, "spec_id", "unknown"),
            "invariants": self._proof_verifier.describe_invariants(),
            "required_fields": proof_payload.get("required_fields", []),
            "spec_fields": proof_payload.get("spec_fields", []),
            "status": proof_payload.get("status"),
            "ledger_diff": proof_payload.get("ledger_diff", {}),
        }
        self._proof_conditions_path.write_text(
            json.dumps(conditions, indent=2, sort_keys=True), encoding="utf-8"
        )
        return conditions

    # ------------------------------------------------------------------
    # Core stages
    def _prepare_proof_payload(self, proposal: Any) -> Dict[str, Any]:
        spec = self._normalize_mapping(getattr(proposal, "proposed_spec", {}))
        ledger_diff = self._normalize_mapping(getattr(proposal, "ledger_diff", {}))
        payload: Dict[str, Any] = {
            "proposal_id": getattr(proposal, "proposal_id", "unknown"),
            "spec_id": getattr(proposal, "spec_id", "unknown"),
            "summary": getattr(proposal, "summary", ""),
            "proposed_spec": spec,
            "original_spec": self._normalize_mapping(
                getattr(proposal, "original_spec", {})
            ),
            "ledger_diff": ledger_diff,
            "required_fields": sorted(self.REQUIRED_FIELDS),
        }
        if spec:
            payload["spec_fields"] = sorted(spec.keys())
            payload["status"] = spec.get("status")
            payload["recursion_break"] = bool(
                spec.get("recursion_break")
                or str(spec.get("recursion", "")).strip().lower() in {"break", "halt"}
            )
        return payload

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
    def _proof_violation_entries(self, proof_report: ProofReport) -> List[Dict[str, Any]]:
        if not (self._proof_config.get("enabled", True) and not proof_report.valid):
            return []
        entries: List[Dict[str, Any]] = []
        for violation in proof_report.violations:
            detail = str(violation.get("detail") or violation.get("description") or "")
            entry: Dict[str, Any] = {
                "code": "proof_invalid",
                "detail": detail or "proof verification failure",
                "invariant": violation.get("invariant"),
            }
            if violation.get("severity"):
                entry["severity"] = violation["severity"]
            entries.append(entry)
        if not entries:
            entries.append({"code": "proof_invalid", "detail": "proof verification failed"})
        if self._proof_config.get("fail_on_invalid", True):
            return entries
        return []

    def _quarantine(self, proposal: Any, payload: Mapping[str, Any]) -> None:
        path = self._quarantine_dir / f"{payload['proposal_id']}.json"
        stored = {
            "timestamp": payload["timestamp"],
            "proposal": self._serialise_proposal(proposal),
            "violations": payload["violations"],
            "probe": payload["probe"],
        }
        if "proof_report" in payload:
            stored["proof_report"] = payload["proof_report"]
        path.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
        log_entry = dict(payload)
        log_entry["event"] = "quarantined"
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(log_entry, sort_keys=True) + "\n")

    def _record_ledger_entry(
        self,
        *,
        timestamp: str,
        proposal: Any,
        probe: ProbeReport,
        proof_report: ProofReport,
        violations: Iterable[Mapping[str, Any]],
        status: str,
    ) -> Dict[str, Any]:
        entry = {
            "timestamp": timestamp,
            "proposal_id": getattr(proposal, "proposal_id", "unknown"),
            "spec_id": getattr(proposal, "spec_id", "unknown"),
            "summary": getattr(proposal, "summary", ""),
            "status": status,
            "violations": [dict(item) for item in violations],
            "probe": probe.to_dict(),
            "proof_report": proof_report.to_dict(),
        }
        with self._ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def _load_proof_config(self) -> Dict[str, Any]:
        config_path = self._root / "vow" / "config.yaml"
        if yaml is None:
            return dict(self.DEFAULT_PROOF_CONFIG)
        try:
            config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return dict(self.DEFAULT_PROOF_CONFIG)
        except yaml.YAMLError:
            return dict(self.DEFAULT_PROOF_CONFIG)
        if not isinstance(config_data, Mapping):
            return dict(self.DEFAULT_PROOF_CONFIG)
        block = config_data.get("proof_verification", {})
        if not isinstance(block, Mapping):
            return dict(self.DEFAULT_PROOF_CONFIG)
        merged = dict(self.DEFAULT_PROOF_CONFIG)
        if "enabled" in block:
            merged["enabled"] = bool(block.get("enabled"))
        if "fail_on_invalid" in block:
            merged["fail_on_invalid"] = bool(block.get("fail_on_invalid"))
        return merged

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

