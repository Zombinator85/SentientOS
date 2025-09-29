"""Narrative explanations for Codex governance and anomaly activity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import threading
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from .anomalies import Anomaly
from .governance import GovernanceDecision
from .strategy import CodexStrategy

__all__ = ["NarrativeEntry", "CodexNarrator"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp(value: datetime | str | None = None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return _now().isoformat()


def _safe_filename(identifier: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", identifier.strip())
    slug = slug.strip("-")
    return slug or "narrative"


def _sentence(label: str, text: str) -> str:
    body = text.strip() if text else ""
    if not body:
        body = "n/a"
    if body[-1:] not in ".!?":
        body += "."
    return f"{label}: {body}"


@dataclass
class NarrativeEntry:
    """Structured narrative summary for a Codex action."""

    narrative_id: str
    category: str
    trigger: str
    response: str
    reasoning: str
    outcome: str
    next_step: str
    summary: str
    timestamp: str = field(default_factory=lambda: _iso_timestamp())
    version: int = 1
    sources: MutableMapping[str, str] = field(default_factory=dict)
    metadata: MutableMapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "narrative_id": self.narrative_id,
            "category": self.category,
            "trigger": self.trigger,
            "response": self.response,
            "reasoning": self.reasoning,
            "outcome": self.outcome,
            "next_step": self.next_step,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "version": self.version,
            "sources": dict(self.sources),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NarrativeEntry":
        return cls(
            narrative_id=str(payload.get("narrative_id")),
            category=str(payload.get("category", "generic")),
            trigger=str(payload.get("trigger", "")),
            response=str(payload.get("response", "")),
            reasoning=str(payload.get("reasoning", "")),
            outcome=str(payload.get("outcome", "")),
            next_step=str(payload.get("next_step", "")),
            summary=str(payload.get("summary", "")),
            timestamp=_iso_timestamp(payload.get("timestamp")),
            version=int(payload.get("version", 1)),
            sources=dict(payload.get("sources", {})),
            metadata=dict(payload.get("metadata", {})),
        )


class CodexNarrator:
    """Generate operator-facing narratives for Codex activity."""

    def __init__(self, root: Path | str = Path("/integration")) -> None:
        self._root = Path(root)
        self._base_dir = self._root / "narratives"
        self._feedback_path = self._base_dir / "feedback.jsonl"
        self._lock = threading.RLock()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public builders
    def create_governance_narrative(
        self,
        decision: GovernanceDecision | Mapping[str, Any],
        *,
        event_id: str | None = None,
        pulse_path: str | None = None,
        integration_path: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> NarrativeEntry:
        payload = decision.to_dict() if isinstance(decision, GovernanceDecision) else dict(decision)
        narrative_id = event_id or payload.get("event_id") or f"governance-{payload.get('strategy_id', 'unknown')}"
        actions = payload.get("actions") or []
        if isinstance(actions, Mapping):
            actions = list(actions.values())
        actions_text = ", ".join(str(action) for action in actions if str(action).strip())
        if not actions_text:
            actions_text = "Document the deviation and notify the operator"
        status = str(payload.get("status") or payload.get("state") or "pending")
        divergence = float(payload.get("divergence_score", 0.0))
        trigger = (
            f"Governance review noticed drift on pattern {payload.get('pattern', '*')} for strategy {payload.get('strategy_id', 'unknown')}"
        )
        response = f"Codex recommended {actions_text} while the strategy remains {status}"
        tolerance = payload.get("tolerance") or payload.get("details", {}).get("tolerance")
        reasoning = (
            f"The divergence score registered at {divergence:.2f}, compared against tolerance {tolerance if tolerance is not None else 'default'}"
        )
        outcome_hint = payload.get("details", {}).get("outcome") or status
        outcome = f"Current outcome: {outcome_hint}"
        next_hint = payload.get("details", {}).get("next_step") or "Escalate if drift persists on the next cycle"
        next_step = str(next_hint)
        return self._persist_entry(
            NarrativeEntry(
                narrative_id=str(narrative_id),
                category="governance",
                trigger=str(trigger),
                response=str(response),
                reasoning=str(reasoning),
                outcome=str(outcome),
                next_step=str(next_step),
                summary=_build_summary(trigger, response, reasoning, outcome, next_step),
                sources=_sources(pulse_path, integration_path),
                metadata=dict(metadata or {}),
            )
        )

    def create_strategy_narrative(
        self,
        strategy: CodexStrategy | Mapping[str, Any],
        *,
        event_id: str | None = None,
        pulse_path: str | None = None,
        integration_path: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> NarrativeEntry:
        data = strategy.to_dict() if isinstance(strategy, CodexStrategy) else dict(strategy)
        narrative_id = event_id or data.get("strategy_id") or "strategy"
        goal = str(data.get("goal", ""))
        status = str(data.get("status", "proposed"))
        channel_text = ", ".join(str(ch) for ch in data.get("metadata", {}).get("channels", []) if str(ch).strip())
        if not channel_text:
            channel_text = "core channels"
        trigger = f"Strategy {data.get('strategy_id', 'unknown')} proposed goal: {goal}"
        response = f"Codex queued plan {data.get('plan_chain', [{}])[0].get('title', 'primary step')} across {channel_text}"
        priority = data.get("metadata", {}).get("priority")
        horizon = data.get("metadata", {}).get("horizon") or data.get("metadata", {}).get("cycle_horizon")
        reasoning = f"Priority {priority if priority is not None else 'unspecified'} with horizon {horizon if horizon is not None else 'short'} informed the decision"
        outcome = f"Strategy status remains {status}"
        next_hint = data.get("metadata", {}).get("next_step") or data.get("metadata", {}).get("checkpoint")
        if next_hint:
            next_step = str(next_hint)
        else:
            next_step = "Monitor operator feedback before advancing to the next checkpoint"
        return self._persist_entry(
            NarrativeEntry(
                narrative_id=str(narrative_id),
                category="strategy",
                trigger=trigger,
                response=response,
                reasoning=reasoning,
                outcome=outcome,
                next_step=next_step,
                summary=_build_summary(trigger, response, reasoning, outcome, next_step),
                sources=_sources(pulse_path, integration_path),
                metadata=dict(metadata or {}),
            )
        )

    def create_anomaly_narrative(
        self,
        anomaly: Anomaly | Mapping[str, Any],
        *,
        event_id: str | None = None,
        pulse_path: str | None = None,
        integration_path: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> NarrativeEntry:
        payload = anomaly.to_event() if isinstance(anomaly, Anomaly) else dict(anomaly)
        narrative_id = event_id or payload.get("id") or f"anomaly-{payload.get('kind', 'unknown')}"
        description = str(payload.get("description") or payload.get("message") or "Anomaly detected")
        trigger = f"{payload.get('kind', 'anomaly')} triggered: {description}"
        mitigation = payload.get("mitigation") or payload.get("response")
        response = str(mitigation or "Codex initiated containment and requested operator confirmation")
        severity = str(payload.get("severity", "warning"))
        history = payload.get("history") or payload.get("occurrences")
        if isinstance(history, (list, tuple)):
            count = len(history)
        else:
            try:
                count = int(history)
            except (TypeError, ValueError):
                count = 1
        reasoning = f"Severity classified as {severity}; recurrence count at {count} influenced prioritization"
        outcome_text = payload.get("status") or payload.get("outcome") or "tracking"
        outcome = f"Immediate outcome: {outcome_text}"
        next_hint = payload.get("next_step") or payload.get("follow_up") or "Escalate to governance if symptoms repeat"
        next_step = str(next_hint)
        return self._persist_entry(
            NarrativeEntry(
                narrative_id=str(narrative_id),
                category="anomaly",
                trigger=trigger,
                response=response,
                reasoning=reasoning,
                outcome=outcome,
                next_step=next_step,
                summary=_build_summary(trigger, response, reasoning, outcome, next_step),
                sources=_sources(pulse_path, integration_path),
                metadata=dict(metadata or {}),
            )
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    def rewrite_narrative(
        self,
        narrative_id: str,
        *,
        updates: Mapping[str, str],
        operator: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> NarrativeEntry:
        record = self.get_narrative(narrative_id)
        if record is None:
            raise KeyError(f"Narrative {narrative_id} not found")
        trigger = updates.get("trigger", record["trigger"])
        response = updates.get("response", record["response"])
        reasoning = updates.get("reasoning", record["reasoning"])
        outcome = updates.get("outcome", record["outcome"])
        next_step = updates.get("next_step", record["next_step"])
        merged_metadata = dict(record.get("metadata", {}))
        if metadata:
            merged_metadata.update(dict(metadata))
        if operator:
            merged_metadata["operator_override"] = operator
        entry = NarrativeEntry(
            narrative_id=narrative_id,
            category=record.get("category", "generic"),
            trigger=trigger,
            response=response,
            reasoning=reasoning,
            outcome=outcome,
            next_step=next_step,
            summary=_build_summary(trigger, response, reasoning, outcome, next_step),
            sources=dict(record.get("sources", {})),
            metadata=merged_metadata,
        )
        return self._persist_entry(entry)

    def list_narratives(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for path in sorted(self._base_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            history = data.get("history", [])
            if not history:
                continue
            latest = history[-1]
            payload = {
                "narrative_id": data.get("narrative_id", path.stem),
                "category": data.get("category", "generic"),
                "sources": data.get("sources", {}),
                "metadata": data.get("metadata", {}),
                "feedback": data.get("feedback", {}),
            }
            payload.update(latest)
            entries.append(payload)
        entries.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        if limit is not None:
            entries = entries[:limit]
        return entries

    def get_narrative(self, narrative_id: str) -> dict[str, Any] | None:
        path = self._base_dir / f"{_safe_filename(narrative_id)}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        history = data.get("history", [])
        if not history:
            return None
        latest = history[-1]
        payload = {
            "narrative_id": data.get("narrative_id", narrative_id),
            "category": data.get("category", "generic"),
            "sources": data.get("sources", {}),
            "metadata": data.get("metadata", {}),
            "feedback": data.get("feedback", {}),
        }
        payload.update(latest)
        return payload

    def log_feedback(
        self,
        narrative_id: str,
        *,
        operator: str,
        action: str,
        notes: str | None = None,
    ) -> None:
        action_key = action.strip().lower()
        if action_key not in {"approve", "edit", "reject"}:
            raise ValueError("action must be approve, edit, or reject")
        timestamp = _iso_timestamp()
        record = {
            "narrative_id": narrative_id,
            "operator": operator,
            "action": action_key,
            "notes": notes,
            "timestamp": timestamp,
        }
        with self._lock:
            with self._feedback_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            path = self._base_dir / f"{_safe_filename(narrative_id)}.json"
            if not path.exists():
                return
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            feedback = data.setdefault("feedback", {"approve": 0, "edit": 0, "reject": 0})
            feedback[action_key] = int(feedback.get(action_key, 0)) + 1
            history = data.get("history", [])
            if history:
                history[-1] = {
                    **history[-1],
                    "feedback_timestamp": timestamp,
                }
            path.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal helpers
    def _persist_entry(self, entry: NarrativeEntry, *, replace: bool = False) -> NarrativeEntry:
        filename = _safe_filename(entry.narrative_id)
        path = self._base_dir / f"{filename}.json"
        with self._lock:
            existing_data: dict[str, Any] = {}
            if path.exists():
                try:
                    existing_data = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    existing_data = {}
            history = existing_data.get("history", [])
            version = len(history) + 1
            if replace and history:
                version = history[-1].get("version", version)
                history.pop()
            entry.version = version
            entry.timestamp = _iso_timestamp(entry.timestamp)
            history.append(entry.to_dict())
            payload = {
                "narrative_id": entry.narrative_id,
                "category": entry.category,
                "sources": dict(entry.sources),
                "metadata": {**existing_data.get("metadata", {}), **entry.metadata},
                "history": history,
                "feedback": existing_data.get("feedback", {"approve": 0, "edit": 0, "reject": 0}),
                "current_version": version,
                "updated_at": entry.timestamp,
            }
            path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        return entry


def _build_summary(trigger: str, response: str, reasoning: str, outcome: str, next_step: str) -> str:
    parts = [
        _sentence("Trigger", trigger),
        _sentence("Response", response),
        _sentence("Reasoning", reasoning),
        _sentence("Outcome", outcome),
        _sentence("Next Step", next_step),
    ]
    return " ".join(parts)


def _sources(pulse_path: str | None, integration_path: str | None) -> MutableMapping[str, str]:
    sources: MutableMapping[str, str] = {}
    if pulse_path:
        sources["pulse"] = str(pulse_path)
    if integration_path:
        sources["integration"] = str(integration_path)
    return sources

