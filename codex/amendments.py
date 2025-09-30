"""Codex Spec Amendment and Regeneration engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

import json
import uuid


from .integrity_daemon import IntegrityDaemon, IntegrityViolation


__all__ = [
    "AmendmentProposal",
    "SpecAmender",
    "AmendmentReviewBoard",
    "IntegrityViolation",
]


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AmendmentProposal:
    """Structured amendment proposal for an existing spec."""

    proposal_id: str
    spec_id: str
    kind: str
    status: str
    summary: str
    deltas: Dict[str, Any]
    context: Dict[str, Any]
    original_spec: Dict[str, Any]
    proposed_spec: Dict[str, Any]
    created_at: datetime = field(default_factory=_default_now)
    updated_at: datetime = field(default_factory=_default_now)
    ledger_entry: Optional[str] = None
    operator_notes: List[Dict[str, Any]] = field(default_factory=list)
    lineage: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "proposal_id": self.proposal_id,
            "spec_id": self.spec_id,
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
            "deltas": self.deltas,
            "context": self.context,
            "original_spec": self.original_spec,
            "proposed_spec": self.proposed_spec,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ledger_entry": self.ledger_entry,
            "operator_notes": list(self.operator_notes),
        }
        if self.lineage:
            payload["lineage"] = self.lineage
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AmendmentProposal":
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        return cls(
            proposal_id=str(payload["proposal_id"]),
            spec_id=str(payload["spec_id"]),
            kind=str(payload.get("kind", "amendment")),
            status=str(payload.get("status", "pending")),
            summary=str(payload.get("summary", "")),
            deltas=dict(payload.get("deltas") or {}),
            context=dict(payload.get("context") or {}),
            original_spec=dict(payload.get("original_spec") or {}),
            proposed_spec=dict(payload.get("proposed_spec") or {}),
            created_at=created_at,
            updated_at=updated_at,
            ledger_entry=payload.get("ledger_entry"),
            operator_notes=list(payload.get("operator_notes") or []),
            lineage=dict(payload.get("lineage") or {}),
        )

    def add_note(
        self,
        operator: str,
        action: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        entry = {
            "operator": operator,
            "action": action,
            "timestamp": _default_now().isoformat(),
        }
        if metadata:
            entry["metadata"] = dict(metadata)
        self.operator_notes.append(entry)


class SpecAmender:
    """Monitor Codex telemetry and propose spec amendments."""

    DEFAULT_THRESHOLD = 3

    def __init__(
        self,
        root: Path | str = Path("integration"),
        *,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._integration_root = Path(root)
        self._integration_root.mkdir(parents=True, exist_ok=True)
        self._spec_root = self._integration_root / "specs"
        self._amendment_root = self._spec_root / "amendments"
        self._pending_dir = self._amendment_root / "pending"
        self._approved_dir = self._amendment_root / "approved"
        self._archive_root = self._amendment_root / "archive"
        self._archive_original_root = self._archive_root / "original_specs"
        self._archive_proposal_root = self._archive_root / "proposals"
        self._rejected_dir = self._integration_root / "rejected_specs"
        for directory in (
            self._spec_root,
            self._amendment_root,
            self._pending_dir,
            self._approved_dir,
            self._archive_root,
            self._archive_original_root,
            self._archive_proposal_root,
            self._rejected_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._amendment_log = self._integration_root / "amendment_log.jsonl"
        self._spec_log = self._integration_root / "spec_log.jsonl"
        self._state_path = self._amendment_root / "state.json"
        self._now = now

        self._integrity_daemon = IntegrityDaemon(self._integration_root, now=now)

        self._signals: Dict[str, Dict[str, Any]] = {}
        self._state: Dict[str, Any] = {
            "thresholds": {},
            "preferences": {},
            "signal_history": {},
        }
        self._load_state()

    # ------------------------------------------------------------------
    # Public API
    def record_signal(
        self,
        spec_id: str,
        signal_type: str,
        metadata: Mapping[str, Any],
        *,
        current_spec: Mapping[str, Any],
    ) -> AmendmentProposal | None:
        """Record recurring telemetry and emit amendment proposals when warranted."""

        if self._has_active_amendment(spec_id):
            return None

        bucket = self._signals.setdefault(
            spec_id,
            {"signals": [], "counts": {}, "lineage": {}},
        )
        entry = {
            "kind": signal_type,
            "metadata": dict(metadata),
            "timestamp": self._now().isoformat(),
        }
        bucket["signals"].append(entry)
        bucket["counts"][signal_type] = bucket["counts"].get(signal_type, 0) + 1
        self._state["signal_history"].setdefault(spec_id, []).append(entry)
        self._save_state()

        threshold = int(
            self._state.get("thresholds", {}).get(signal_type, self.DEFAULT_THRESHOLD)
        )
        if bucket["counts"][signal_type] < threshold:
            return None

        proposal = self._draft_amendment(
            spec_id,
            bucket["signals"],
            current_spec,
            dominant_signal=signal_type,
        )
        self._signals.pop(spec_id, None)
        return proposal

    def propose_manual(
        self,
        spec_id: str,
        *,
        summary: str,
        deltas: Mapping[str, Any],
        context: Mapping[str, Any],
        original_spec: Mapping[str, Any],
        proposed_spec: Mapping[str, Any],
        kind: str = "amendment",
        lineage: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        """Persist a pre-computed amendment draft."""

        proposal = self._create_proposal(
            spec_id=spec_id,
            kind=kind,
            summary=summary,
            deltas=dict(deltas),
            context=dict(context),
            original_spec=dict(original_spec),
            proposed_spec=dict(proposed_spec),
            lineage=dict(lineage) if lineage else None,
        )
        return proposal

    def regenerate_spec(
        self,
        spec_id: str,
        *,
        operator: str,
        reason: str,
        current_spec: Mapping[str, Any],
    ) -> AmendmentProposal:
        """Draft a regenerated spec version linked to the previous lineage."""

        current_version = str(current_spec.get("version", "v1"))
        next_version = self._next_version(current_version)
        proposed_spec = dict(current_spec)
        proposed_spec["version"] = next_version
        proposed_spec["status"] = "regenerated"
        summary = f"Regenerate {spec_id} to recover from structural failure"
        deltas = {
            "version": {"before": current_version, "after": next_version},
            "status": {"before": current_spec.get("status"), "after": "regenerated"},
        }
        context = {
            "reason": reason,
            "operator": operator,
        }
        lineage = {
            "from_version": current_version,
            "to_version": next_version,
            "operator": operator,
            "reason": reason,
        }
        proposal = self._create_proposal(
            spec_id=spec_id,
            kind="regeneration",
            summary=summary,
            deltas=deltas,
            context=context,
            original_spec=dict(current_spec),
            proposed_spec=proposed_spec,
            lineage=lineage,
        )
        archive_path = self._archive_original_root / f"{spec_id}_{current_version}.json"
        archive_path.write_text(
            json.dumps(current_spec, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        self._append_spec_log(
            "regenerated",
            spec_id,
            {
                "from_version": current_version,
                "to_version": next_version,
                "proposal_id": proposal.proposal_id,
                "reason": reason,
            },
        )
        proposal.add_note(operator, "regenerated", {"reason": reason})
        self._persist(proposal)
        return proposal

    def load_proposal(self, proposal_id: str) -> AmendmentProposal | None:
        for directory in (
            self._pending_dir,
            self._approved_dir,
            self._rejected_dir,
            self._archive_proposal_root,
        ):
            path = directory / f"{proposal_id}.json"
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                return AmendmentProposal.from_dict(payload)
        return None

    def list_pending(self) -> List[Dict[str, Any]]:
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self._pending_dir.glob("*.json"))
        ]

    def active_amendments(self, spec_id: str | None = None) -> List[Dict[str, Any]]:
        items = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self._approved_dir.glob("*.json"))
        ]
        if spec_id is None:
            return items
        return [item for item in items if item.get("spec_id") == spec_id]

    def dashboard_state(self) -> Dict[str, Any]:
        pending = [json.loads(path.read_text(encoding="utf-8")) for path in self._pending_dir.glob("*.json")]
        approved = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in self._approved_dir.glob("*.json")
        ]
        items: List[Dict[str, Any]] = []
        for payload in pending + approved:
            diff = {
                key: value
                for key, value in payload.get("deltas", {}).items()
            }
            items.append(
                {
                    "proposal_id": payload.get("proposal_id"),
                    "spec_id": payload.get("spec_id"),
                    "status": payload.get("status"),
                    "kind": payload.get("kind"),
                    "summary": payload.get("summary"),
                    "diff": diff,
                    "context": payload.get("context", {}),
                    "ledger_entry": payload.get("ledger_entry"),
                }
            )
        return {
            "panel": "Spec Amendments",
            "pending": [item for item in items if item["status"] == "pending"],
            "approved": [item for item in items if item["status"] == "approved"],
            "items": items,
        }

    def integrity_endpoint(self) -> Dict[str, Any]:
        """Expose covenantal health snapshot for other modules."""

        return self._integrity_daemon.health()

    def edit_proposal(
        self,
        proposal_id: str,
        *,
        operator: str,
        summary: str | None = None,
        deltas: Mapping[str, Any] | None = None,
        proposed_spec: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        proposal = self._require(proposal_id)
        changes: Dict[str, Any] = {}
        if summary is not None and summary != proposal.summary:
            proposal.summary = summary
            changes["summary"] = summary
        if deltas is not None:
            new_deltas = dict(deltas)
            if new_deltas != proposal.deltas:
                proposal.deltas = new_deltas
                changes["deltas"] = new_deltas
        if proposed_spec is not None:
            new_spec = dict(proposed_spec)
            if new_spec != proposal.proposed_spec:
                proposal.proposed_spec = new_spec
                changes["proposed_spec"] = new_spec
        if changes:
            proposal.updated_at = self._now()
            proposal.add_note(operator, "edited", {"changes": changes})
            self._persist(proposal)
            self._append_amendment_log(
                "edited",
                proposal.spec_id,
                proposal.proposal_id,
                {"operator": operator, "changes": changes},
            )
        return proposal

    def annotate_lineage(
        self,
        proposal_id: str,
        *,
        lineage: Mapping[str, Any],
        context: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        """Attach lineage metadata to an existing proposal."""

        proposal = self._require(proposal_id)
        merged_lineage = dict(proposal.lineage or {})
        merged_lineage.update(dict(lineage))
        proposal.lineage = merged_lineage

        if context:
            existing_context = dict(proposal.context or {})
            existing_context.update(dict(context))
            proposal.context = existing_context

        stored = self._persist(proposal)
        self._append_amendment_log(
            "annotated",
            proposal.spec_id,
            proposal.proposal_id,
            {"lineage": merged_lineage, "context": dict(context or {})},
        )
        return AmendmentProposal.from_dict(
            json.loads(stored.read_text(encoding="utf-8"))
        )

    # ------------------------------------------------------------------
    # Internal helpers
    def _draft_amendment(
        self,
        spec_id: str,
        signals: Iterable[Mapping[str, Any]],
        current_spec: Mapping[str, Any],
        *,
        dominant_signal: str,
    ) -> AmendmentProposal:
        original = dict(current_spec)
        objective_before = str(original.get("objective", ""))
        directives_before = list(original.get("directives") or [])
        testing_before = list(original.get("testing_requirements") or [])

        descriptions = []
        for entry in signals:
            metadata = entry.get("metadata") or {}
            detail = metadata.get("detail") or metadata.get("reason")
            if detail and detail not in descriptions:
                descriptions.append(str(detail))
        if not descriptions:
            descriptions.append(f"recurring {dominant_signal} signals")

        preferences = self._state.get("preferences", {}).get(dominant_signal, {})
        approved = int(preferences.get("approved", 0))
        rejected = int(preferences.get("rejected", 0))
        verb = "Reinforce" if approved > rejected else "Tighten"

        new_objective = (
            f"{verb} {objective_before or 'the existing objective'} to cover {dominant_signal} gaps."
        )
        added_directives = [
            f"Document remediation for {dominant_signal} contexts: {', '.join(descriptions)}.",
            "Add coverage analysis checkpoints before activation to prevent silent drift.",
        ]
        added_testing = [
            f"Replay {dominant_signal} telemetry until amendment clears the recurrence queue.",
            "Ensure ledger approval is required before the amendment becomes active.",
        ]

        proposed = dict(original)
        proposed["objective"] = new_objective
        proposed["directives"] = directives_before + added_directives
        proposed["testing_requirements"] = testing_before + added_testing

        deltas = {
            "objective": {"before": objective_before, "after": new_objective},
            "directives": {
                "before": directives_before,
                "added": added_directives,
            },
            "testing_requirements": {
                "before": testing_before,
                "added": added_testing,
            },
        }
        context = {
            "signals": list(signals),
            "counts": self._aggregate_counts(signals),
            "dominant_signal": dominant_signal,
        }

        summary = f"Amend {spec_id} for {dominant_signal} coverage gaps"
        proposal = self._create_proposal(
            spec_id=spec_id,
            kind="amendment",
            summary=summary,
            deltas=deltas,
            context=context,
            original_spec=original,
            proposed_spec=proposed,
            lineage=None,
        )
        return proposal

    def _aggregate_counts(self, signals: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in signals:
            kind = str(entry.get("kind"))
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    def _create_proposal(
        self,
        *,
        spec_id: str,
        kind: str,
        summary: str,
        deltas: Mapping[str, Any],
        context: Mapping[str, Any],
        original_spec: Mapping[str, Any],
        proposed_spec: Mapping[str, Any],
        lineage: Mapping[str, Any] | None,
    ) -> AmendmentProposal:
        proposal_id = f"{spec_id}-{uuid.uuid4().hex[:8]}"
        proposal = AmendmentProposal(
            proposal_id=proposal_id,
            spec_id=spec_id,
            kind=kind,
            status="pending",
            summary=summary,
            deltas=dict(deltas),
            context=dict(context),
            original_spec=dict(original_spec),
            proposed_spec=dict(proposed_spec),
            created_at=self._now(),
            updated_at=self._now(),
            lineage=dict(lineage) if lineage else None,
        )
        self._integrity_daemon.evaluate(proposal)
        self._persist(proposal)
        self._append_amendment_log(
            "proposed",
            proposal.spec_id,
            proposal.proposal_id,
            {"kind": kind, "summary": summary},
        )
        return proposal

    def _persist(self, proposal: AmendmentProposal) -> Path:
        proposal.updated_at = self._now()
        directory = self._directory_for_status(proposal.status)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{proposal.proposal_id}.json"
        path.write_text(
            json.dumps(proposal.to_dict(), sort_keys=True, indent=2),
            encoding="utf-8",
        )
        self._cleanup_duplicates(proposal.proposal_id, keep=path)
        return path

    def _cleanup_duplicates(self, proposal_id: str, *, keep: Path) -> None:
        for directory in (
            self._pending_dir,
            self._approved_dir,
            self._rejected_dir,
            self._archive_proposal_root,
        ):
            path = directory / f"{proposal_id}.json"
            if path == keep:
                continue
            if path.exists():
                path.unlink()

    def _directory_for_status(self, status: str) -> Path:
        if status == "pending":
            return self._pending_dir
        if status == "approved":
            return self._approved_dir
        if status == "rejected":
            return self._rejected_dir
        return self._archive_proposal_root

    def _append_amendment_log(
        self,
        event: str,
        spec_id: str,
        proposal_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {
            "timestamp": self._now().isoformat(),
            "event": event,
            "spec_id": spec_id,
            "proposal_id": proposal_id,
        }
        if metadata:
            payload["metadata"] = dict(metadata)
        with self._amendment_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _append_spec_log(
        self,
        event: str,
        spec_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {
            "timestamp": self._now().isoformat(),
            "event": event,
            "spec_id": spec_id,
        }
        if metadata:
            payload["details"] = dict(metadata)
        with self._spec_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _next_version(self, current: str) -> str:
        if current.startswith("v") and current[1:].isdigit():
            return f"v{int(current[1:]) + 1}"
        return "v2"

    def _has_active_amendment(self, spec_id: str) -> bool:
        for directory in (self._pending_dir, self._approved_dir):
            for path in directory.glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("spec_id") == spec_id:
                    return True
        return False

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            self._state.update(payload)

    def _save_state(self) -> None:
        self._state_path.write_text(
            json.dumps(self._state, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    def _require(self, proposal_id: str) -> AmendmentProposal:
        proposal = self.load_proposal(proposal_id)
        if proposal is None:
            raise FileNotFoundError(f"Amendment {proposal_id} not found")
        return proposal


class AmendmentReviewBoard:
    """Operator workflow controller for spec amendments."""

    def __init__(self, engine: SpecAmender) -> None:
        self._engine = engine

    def approve(
        self,
        proposal_id: str,
        *,
        operator: str,
        ledger_entry: str | None,
    ) -> AmendmentProposal:
        if not ledger_entry:
            raise ValueError("Ledger entry required before approval")
        proposal = self._engine._require(proposal_id)
        proposal.status = "approved"
        proposal.ledger_entry = ledger_entry
        proposal.add_note(operator, "approved", {"ledger_entry": ledger_entry})
        self._engine._persist(proposal)
        self._engine._append_amendment_log(
            "approved",
            proposal.spec_id,
            proposal.proposal_id,
            {"operator": operator, "ledger_entry": ledger_entry},
        )
        self._engine._update_preferences(proposal, outcome="approved")
        return proposal

    def reject(
        self,
        proposal_id: str,
        *,
        operator: str,
        reason: str | None = None,
    ) -> AmendmentProposal:
        proposal = self._engine._require(proposal_id)
        proposal.status = "rejected"
        proposal.add_note(operator, "rejected", {"reason": reason})
        self._engine._persist(proposal)
        self._engine._append_amendment_log(
            "rejected",
            proposal.spec_id,
            proposal.proposal_id,
            {"operator": operator, "reason": reason},
        )
        self._engine._update_preferences(proposal, outcome="rejected")
        return proposal

    def edit(
        self,
        proposal_id: str,
        *,
        operator: str,
        summary: str | None = None,
        deltas: Mapping[str, Any] | None = None,
        proposed_spec: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        return self._engine.edit_proposal(
            proposal_id,
            operator=operator,
            summary=summary,
            deltas=deltas,
            proposed_spec=proposed_spec,
        )

    def regenerate(
        self,
        spec_id: str,
        *,
        operator: str,
        reason: str,
        current_spec: Mapping[str, Any],
    ) -> AmendmentProposal:
        return self._engine.regenerate_spec(
            spec_id,
            operator=operator,
            reason=reason,
            current_spec=current_spec,
        )


# Extend SpecAmender with preference tracking utilities

def _update_preferences(self: SpecAmender, proposal: AmendmentProposal, *, outcome: str) -> None:
    context = proposal.context or {}
    signal = context.get("dominant_signal") or context.get("reason")
    if not signal:
        return
    prefs = self._state.setdefault("preferences", {})
    data = prefs.setdefault(signal, {"approved": 0, "rejected": 0})
    if outcome == "approved":
        data["approved"] = int(data.get("approved", 0)) + 1
    elif outcome == "rejected":
        data["rejected"] = int(data.get("rejected", 0)) + 1
    self._save_state()


SpecAmender._update_preferences = _update_preferences  # type: ignore[attr-defined]
