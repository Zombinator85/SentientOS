"""Spec proposal engine for Codex self-specification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional

import json
import re
import uuid


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip())
    text = re.sub(r"-+", "-", text)
    return text.strip("-").lower() or "spec"


@dataclass
class SpecProposal:
    """Structured specification proposal drafted by the SpecEngine."""

    spec_id: str
    title: str
    objective: str
    directives: List[str]
    testing_requirements: List[str]
    trigger_key: str
    trigger_context: Dict[str, Any]
    status: str = "draft"
    created_at: datetime = field(default_factory=_default_now)
    updated_at: datetime = field(default_factory=_default_now)
    approved_by: List[str] = field(default_factory=list)
    operator_notes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "title": self.title,
            "objective": self.objective,
            "directives": list(self.directives),
            "testing_requirements": list(self.testing_requirements),
            "trigger_key": self.trigger_key,
            "trigger_context": self.trigger_context,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "approved_by": list(self.approved_by),
            "operator_notes": list(self.operator_notes),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecProposal":
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        return cls(
            spec_id=str(payload["spec_id"]),
            title=str(payload["title"]),
            objective=str(payload["objective"]),
            directives=list(payload.get("directives") or []),
            testing_requirements=list(payload.get("testing_requirements") or []),
            trigger_key=str(payload["trigger_key"]),
            trigger_context=dict(payload.get("trigger_context") or {}),
            status=str(payload.get("status", "draft")),
            created_at=created_at,
            updated_at=updated_at,
            approved_by=list(payload.get("approved_by") or []),
            operator_notes=list(payload.get("operator_notes") or []),
        )

    def apply_edits(
        self,
        *,
        title: Optional[str] = None,
        objective: Optional[str] = None,
        directives: Optional[Iterable[str]] = None,
        testing_requirements: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Apply operator edits and return the diff."""

        changes: Dict[str, Any] = {}
        if title is not None and title != self.title:
            self.title = title
            changes["title"] = title
        if objective is not None and objective != self.objective:
            self.objective = objective
            changes["objective"] = objective
        if directives is not None:
            new_directives = list(directives)
            if new_directives != self.directives:
                self.directives = new_directives
                changes["directives"] = new_directives
        if testing_requirements is not None:
            new_testing = list(testing_requirements)
            if new_testing != self.testing_requirements:
                self.testing_requirements = new_testing
                changes["testing_requirements"] = new_testing
        return changes

    def add_note(self, operator: str, action: str, metadata: Mapping[str, Any] | None = None) -> None:
        entry = {
            "operator": operator,
            "action": action,
            "timestamp": _default_now().isoformat(),
        }
        if metadata:
            entry["metadata"] = dict(metadata)
        self.operator_notes.append(entry)


class SpecEngine:
    """Generate and manage Codex specification proposals."""

    DEFAULT_THRESHOLDS = {"anomaly": 3, "strategy": 2}

    def __init__(
        self,
        root: Path | str = Path("integration"),
        *,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._spec_root = self._root / "specs"
        self._proposal_dir = self._spec_root / "proposals"
        self._queue_dir = self._spec_root / "queue"
        self._archive_dir = self._spec_root / "archive"
        self._scaffold_dir = self._spec_root / "scaffolds"
        for directory in (
            self._spec_root,
            self._proposal_dir,
            self._queue_dir,
            self._archive_dir,
            self._scaffold_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._log_path = self._root / "spec_log.jsonl"
        self._state_path = self._spec_root / "state.json"
        self._now = now

        self._thresholds: Dict[str, int] = dict(self.DEFAULT_THRESHOLDS)
        self._style: Dict[str, Any] = {
            "objective_prefix": "Address",
        }
        self._state: Dict[str, Any] = {"rejections": 0}
        self._trigger_index: Dict[str, str] = {}

        self._load_state()
        self._load_existing_specs()

    # ------------------------------------------------------------------
    # Public API
    def scan(
        self,
        anomalies: Iterable[Mapping[str, Any]],
        strategies: Iterable[Mapping[str, Any]],
    ) -> List[SpecProposal]:
        """Inspect telemetry and emit spec proposals for persistent gaps."""

        proposals: List[SpecProposal] = []

        for context in self._anomaly_contexts(anomalies):
            trigger_key = context["trigger_key"]
            if context["count"] < self._thresholds.get("anomaly", 3):
                continue
            if self._has_active_spec(trigger_key):
                continue
            proposals.append(self._draft_spec(context))

        for context in self._strategy_contexts(strategies):
            trigger_key = context["trigger_key"]
            if context["count"] < self._thresholds.get("strategy", 2):
                continue
            if self._has_active_spec(trigger_key):
                continue
            proposals.append(self._draft_spec(context))

        return proposals

    def load_spec(self, spec_id: str) -> SpecProposal | None:
        for directory in (self._proposal_dir, self._queue_dir, self._archive_dir):
            path = directory / f"{spec_id}.json"
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                return SpecProposal.from_dict(payload)
        return None

    def persist(
        self,
        proposal: SpecProposal,
        *,
        event: str,
        details: Mapping[str, Any] | None = None,
    ) -> Path:
        proposal.updated_at = self._now()
        path = self._path_for_status(proposal.status) / f"{proposal.spec_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(proposal.to_dict(), sort_keys=True, indent=2), encoding="utf-8")
        self._cleanup_duplicates(proposal.spec_id, keep=path)
        self._trigger_index[proposal.trigger_key] = proposal.spec_id
        self._log_event(proposal.spec_id, proposal.status, event, details)
        self._save_state()
        return path

    def enqueue_spec(self, proposal: SpecProposal, *, commit_hash: str | None = None) -> Path:
        queue_path = self._queue_dir / f"{proposal.spec_id}.json"
        if not queue_path.exists():
            self.persist(proposal, event="queued", details={"commit": commit_hash or ""})
        else:
            self._log_event(
                proposal.spec_id,
                proposal.status,
                "queued",
                {"commit": commit_hash or ""},
            )
        scaffold_dir = self._scaffold_dir / proposal.spec_id
        scaffold_dir.mkdir(parents=True, exist_ok=True)
        scaffold_manifest = {
            "spec_id": proposal.spec_id,
            "title": proposal.title,
            "objective": proposal.objective,
            "queued_at": self._now().isoformat(),
            "commit": commit_hash,
        }
        (scaffold_dir / "manifest.json").write_text(
            json.dumps(scaffold_manifest, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return queue_path

    def register_feedback(
        self,
        proposal: SpecProposal,
        *,
        action: str,
        changes: Mapping[str, Any] | None = None,
    ) -> None:
        if action == "rejected":
            rejection_count = int(self._state.get("rejections", 0)) + 1
            self._state["rejections"] = rejection_count
            if rejection_count >= int(self._state.get("rejection_batch", 3)):
                self._thresholds["anomaly"] = int(self._thresholds.get("anomaly", 3)) + 1
                self._thresholds["strategy"] = int(self._thresholds.get("strategy", 2)) + 1
                self._state["rejections"] = 0
        elif action == "approved":
            self._state["rejections"] = 0
        elif action == "edited" and changes:
            objective = changes.get("objective")
            if objective:
                prefix = objective.split(" ", 1)[0]
                if prefix:
                    self._style["objective_prefix"] = prefix
            directives = changes.get("directives")
            if directives:
                lead = str(directives[0]).split(" ", 1)[0]
                self._style["directive_lead"] = lead
        self._save_state()

    # ------------------------------------------------------------------
    # Internal helpers
    def _draft_spec(self, context: Mapping[str, Any]) -> SpecProposal:
        spec_id = f"spec-{self._now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        label = str(context.get("label") or context.get("kind") or "Codex Gap")
        summary = str(context.get("summary") or label)
        prefix = str(self._style.get("objective_prefix", "Address"))
        objective = f"{prefix} the {label.lower()} gap surfaced in Codex telemetry."

        directives = [
            f"Document the recurring context: {summary}.",
            f"Design a reusable intervention for {label.lower()} incidents including operator review gates.",
            "Specify ledger checkpoints and activation criteria for the resulting module scaffolds.",
        ]
        lead = self._style.get("directive_lead")
        if lead and directives:
            directives[0] = f"{lead} {directives[0].split(' ', 1)[1]}"

        testing_requirements = [
            f"Simulate {label.lower()} conditions until the SpecEngine replays this trigger and confirm a queued scaffold only after operator approval.",
            "Assert the persisted proposal includes objective, directives, and testing requirements fields.",
            "Verify rejected proposals remain archived and absent from the activation queue.",
        ]

        proposal = SpecProposal(
            spec_id=spec_id,
            title=f"{label} Spec Proposal",
            objective=objective,
            directives=directives,
            testing_requirements=testing_requirements,
            trigger_key=str(context["trigger_key"]),
            trigger_context=dict(context),
            status="draft",
            created_at=self._now(),
            updated_at=self._now(),
        )

        self.persist(
            proposal,
            event="proposed",
            details={
                "title": proposal.title,
                "trigger": proposal.trigger_context,
            },
        )
        return proposal

    def _has_active_spec(self, trigger_key: str) -> bool:
        if trigger_key in self._trigger_index:
            return True
        return False

    def _path_for_status(self, status: str) -> Path:
        if status in {"draft", "deferred"}:
            return self._proposal_dir
        if status in {"queued"}:
            return self._queue_dir
        if status in {"rejected"}:
            return self._archive_dir
        return self._proposal_dir

    def _cleanup_duplicates(self, spec_id: str, *, keep: Path) -> None:
        for directory in (self._proposal_dir, self._queue_dir, self._archive_dir):
            path = directory / f"{spec_id}.json"
            if path == keep:
                continue
            if path.exists():
                path.unlink()

    def _log_event(
        self,
        spec_id: str,
        status: str,
        event: str,
        details: Mapping[str, Any] | None,
    ) -> None:
        payload = {
            "timestamp": self._now().isoformat(),
            "spec_id": spec_id,
            "status": status,
            "event": event,
        }
        if details:
            payload["details"] = dict(details)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _save_state(self) -> None:
        payload = {
            "thresholds": self._thresholds,
            "style": self._style,
            "rejections": self._state.get("rejections", 0),
            "rejection_batch": self._state.get("rejection_batch", 3),
            "trigger_map": self._trigger_index,
        }
        self._state_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        self._thresholds.update({k: int(v) for k, v in payload.get("thresholds", {}).items()})
        self._style.update(payload.get("style", {}))
        self._state["rejections"] = int(payload.get("rejections", 0))
        if "rejection_batch" in payload:
            self._state["rejection_batch"] = int(payload["rejection_batch"])
        trigger_map = payload.get("trigger_map") or {}
        for key, value in trigger_map.items():
            if isinstance(key, str) and isinstance(value, str):
                self._trigger_index[key] = value

    def _load_existing_specs(self) -> None:
        for directory in (self._proposal_dir, self._queue_dir, self._archive_dir):
            for path in directory.glob("*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    proposal = SpecProposal.from_dict(payload)
                except Exception:
                    continue
                self._trigger_index[proposal.trigger_key] = proposal.spec_id

    def _anomaly_contexts(self, anomalies: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        buckets: MutableMapping[str, Dict[str, Any]] = {}
        for entry in anomalies:
            if not isinstance(entry, Mapping):
                continue
            kind = str(entry.get("kind") or entry.get("anomaly") or "").strip()
            if not kind:
                continue
            if entry.get("template") or entry.get("has_template") or entry.get("resolved_template"):
                continue
            bucket = buckets.setdefault(
                kind,
                {
                    "trigger_key": f"anomaly::{kind}",
                    "kind": kind,
                    "label": kind.replace("_", " ").title(),
                    "count": 0,
                    "samples": [],
                },
            )
            bucket["count"] += 1
            bucket["samples"].append(dict(entry))
        contexts: List[Dict[str, Any]] = []
        for bucket in buckets.values():
            samples = bucket.get("samples") or []
            summary = self._summarize_samples(samples, kind=bucket["kind"], label=bucket["label"])
            context = dict(bucket)
            context["summary"] = summary
            contexts.append(context)
        return contexts

    def _strategy_contexts(self, strategies: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        buckets: MutableMapping[str, Dict[str, Any]] = {}
        for entry in strategies:
            if not isinstance(entry, Mapping):
                continue
            status = str(entry.get("status") or "").lower()
            if status not in {"escalated", "blocked"}:
                continue
            reason = str(entry.get("reason") or entry.get("gap") or "missing template").strip()
            slug = _slugify(reason or "missing-template")
            key = f"strategy::{slug}"
            bucket = buckets.setdefault(
                key,
                {
                    "trigger_key": key,
                    "kind": slug,
                    "label": reason.title() if reason else "Escalation",
                    "count": 0,
                    "samples": [],
                },
            )
            bucket["count"] += 1
            bucket["samples"].append(dict(entry))
        contexts: List[Dict[str, Any]] = []
        for bucket in buckets.values():
            summary = self._summarize_samples(bucket.get("samples") or [], kind=bucket["kind"], label=bucket["label"])
            context = dict(bucket)
            context["summary"] = summary
            contexts.append(context)
        return contexts

    def _summarize_samples(
        self,
        samples: Iterable[Mapping[str, Any]],
        *,
        kind: str,
        label: str,
    ) -> str:
        count = 0
        last_seen: Mapping[str, Any] | None = None
        for sample in samples:
            count += 1
            last_seen = sample
        if count == 0:
            return f"Persistent {label.lower()} gap"
        details = []
        if last_seen:
            daemon = last_seen.get("daemon") or last_seen.get("strategy_id")
            if daemon:
                details.append(f"last seen on {daemon}")
            if last_seen.get("reason"):
                details.append(str(last_seen["reason"]))
        summary_bits = ", ".join(details)
        if summary_bits:
            return f"{label} gap ({summary_bits})"
        return f"{label} gap repeated {count}×"


class SpecReviewBoard:
    """Operator workflow for Codex spec proposals."""

    def __init__(self, engine: SpecEngine) -> None:
        self._engine = engine

    def approve(
        self,
        spec_id: str,
        *,
        operator: str,
        commit_hash: str | None = None,
    ) -> SpecProposal:
        proposal = self._require(spec_id)
        proposal.status = "queued"
        if operator not in proposal.approved_by:
            proposal.approved_by.append(operator)
        proposal.add_note(operator, "approved", {"commit": commit_hash})
        self._engine.persist(
            proposal,
            event="approved",
            details={"operator": operator, "commit": commit_hash},
        )
        self._engine.enqueue_spec(proposal, commit_hash=commit_hash)
        self._engine.register_feedback(proposal, action="approved")
        return proposal

    def reject(
        self,
        spec_id: str,
        *,
        operator: str,
        reason: str | None = None,
    ) -> SpecProposal:
        proposal = self._require(spec_id)
        proposal.status = "rejected"
        proposal.add_note(operator, "rejected", {"reason": reason})
        self._engine.persist(
            proposal,
            event="rejected",
            details={"operator": operator, "reason": reason},
        )
        self._engine.register_feedback(proposal, action="rejected")
        return proposal

    def edit(
        self,
        spec_id: str,
        *,
        operator: str,
        title: str | None = None,
        objective: str | None = None,
        directives: Iterable[str] | None = None,
        testing_requirements: Iterable[str] | None = None,
    ) -> SpecProposal:
        proposal = self._require(spec_id)
        changes = proposal.apply_edits(
            title=title,
            objective=objective,
            directives=directives,
            testing_requirements=testing_requirements,
        )
        if changes:
            proposal.add_note(operator, "edited", {"changes": changes})
            self._engine.persist(
                proposal,
                event="edited",
                details={"operator": operator, "changes": changes},
            )
            self._engine.register_feedback(proposal, action="edited", changes=changes)
        return proposal

    def defer(self, spec_id: str, *, operator: str, until: str | None = None) -> SpecProposal:
        proposal = self._require(spec_id)
        proposal.status = "deferred"
        proposal.add_note(operator, "deferred", {"until": until})
        self._engine.persist(
            proposal,
            event="deferred",
            details={"operator": operator, "until": until},
        )
        return proposal

    def _require(self, spec_id: str) -> SpecProposal:
        proposal = self._engine.load_spec(spec_id)
        if proposal is None:
            raise FileNotFoundError(f"Spec {spec_id} not found")
        return proposal


__all__ = ["SpecEngine", "SpecProposal", "SpecReviewBoard"]

