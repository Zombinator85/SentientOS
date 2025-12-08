from __future__ import annotations

"""Coordinated deterministic orchestrator for SentientOS inner world."""

from typing import Any, Dict, List

from .ethics_core import EthicalCore
from .identity import IdentityManager
from .inner_experience import InnerExperience
from .metacognition import MetaMonitor


class InnerWorldOrchestrator:
    """Coordinate inner-world subsystems without external side effects."""

    def __init__(self) -> None:
        self.inner_experience = InnerExperience()
        self.identity_manager = IdentityManager()
        self.meta_monitor = MetaMonitor()
        self.ethical_core = EthicalCore()
        self._cycle_counter = 0

    def _summarize_qualia_changes(
        self, previous: Dict[str, float], current: Dict[str, float]
    ) -> str:
        changes: List[str] = []
        for key, value in current.items():
            prev_value = previous.get(key)
            if prev_value != value:
                changes.append(f"{key}:{prev_value}->{value}")

        if not changes:
            return "No qualia changes."
        return "; ".join(changes)

    def _integrate_input_signals(self, input_state: Dict[str, Any]) -> Dict[str, float]:
        previous_qualia = self.inner_experience.get_state()

        signal_updates: Dict[str, float] = {}
        for key in ("errors", "progress", "novelty"):
            if key in input_state and isinstance(input_state[key], (int, float)):
                signal_updates[key] = float(input_state[key])

        if signal_updates:
            self.inner_experience.integrate_signals(**signal_updates)

        qualia_snapshot = self.inner_experience.get_state()
        summary = self._summarize_qualia_changes(previous_qualia, qualia_snapshot)
        self.identity_manager.log_event("qualia_update", summary)
        return qualia_snapshot

    def start_cycle(self, input_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run a deterministic inner-world coordination cycle."""

        self._cycle_counter += 1
        self.identity_manager.log_event(
            "cycle_start", f"Cycle {self._cycle_counter} started."
        )

        qualia_snapshot = self._integrate_input_signals(input_state)

        assembled_state: Dict[str, Any] = dict(qualia_snapshot)
        assembled_state.update(input_state)
        meta_notes = self.meta_monitor.review_cycle(assembled_state)
        if meta_notes:
            messages = "; ".join(note.get("message", "") for note in meta_notes)
            self.identity_manager.log_event("meta_monitor", messages)

        plan = input_state.get("plan", {})
        plan_dict = plan if isinstance(plan, dict) else {}
        ethical_result = self.ethical_core.evaluate_plan(plan_dict)
        if ethical_result.get("conflicts"):
            conflicts = ethical_result.get("conflicts", [])
            summary = "; ".join(
                f"{conflict.get('value')}: {conflict.get('reason')}"
                for conflict in conflicts
            )
            self.identity_manager.log_event("ethical_conflict", summary)

        return {
            "cycle": self._cycle_counter,
            "qualia": qualia_snapshot,
            "meta_notes": meta_notes,
            "ethical": ethical_result,
            "identity_summary": self.identity_manager.summarize(),
        }

    def get_state(self) -> Dict[str, Any]:
        """Return a stable snapshot of current inner-world status."""

        return {
            "qualia": self.inner_experience.get_state(),
            "meta_notes": self.meta_monitor.get_recent_notes(),
            "self_concept": self.identity_manager.get_self_concept(),
            "identity_events": self.identity_manager.get_events(),
        }
