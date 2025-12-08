"""Deterministic orchestrator for SentientOS inner-world introspection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping

from sentientos.ethics_core import EthicalCore
from sentientos.identity import IdentityManager
from sentientos.inner_experience import InnerExperience
from sentientos.metacognition import MetaMonitor
from sentientos.innerworld.simulation import SimulationEngine


class InnerWorldOrchestrator:
    """Coordinate inner-world subsystems without external side effects."""

    def __init__(self) -> None:
        self.inner_experience = InnerExperience()
        self.identity_manager = IdentityManager()
        self.meta_monitor = MetaMonitor()
        self.ethical_core = EthicalCore()
        self._cycle_counter = 0
        self._simulation_engine: SimulationEngine | None = None

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

    def _integrate_input_signals(self, input_state: Mapping[str, Any]) -> Dict[str, float]:
        previous_qualia = self.inner_experience.get_state()

        signal_updates: Dict[str, float] = {}
        for key in ("errors", "progress", "novelty"):
            value = input_state.get(key)
            if isinstance(value, (int, float)):
                signal_updates[key] = float(value)

        if signal_updates:
            self.inner_experience.integrate_signals(**signal_updates)

        qualia_snapshot = self.inner_experience.get_state()
        summary = self._summarize_qualia_changes(previous_qualia, qualia_snapshot)
        self.identity_manager.log_event("qualia_update", summary)
        return qualia_snapshot

    def run_cycle(self, input_state: Mapping[str, Any]) -> Dict[str, Any]:
        """Run a deterministic inner-world coordination cycle."""

        self._cycle_counter += 1
        cycle_id = self._cycle_counter
        state_copy = dict(input_state)
        self.identity_manager.log_event("cycle_start", f"Cycle {cycle_id} started.")

        qualia_snapshot = self._integrate_input_signals(state_copy)

        assembled_state: Dict[str, Any] = dict(qualia_snapshot)
        assembled_state.update(state_copy)
        meta_notes = self.meta_monitor.review_cycle(assembled_state)
        if meta_notes:
            messages = "; ".join(note.get("message", "") for note in meta_notes)
            self.identity_manager.log_event("meta_monitor", messages)

        plan = state_copy.get("plan", {})
        plan_dict = plan if isinstance(plan, dict) else {}
        ethical_result = self.ethical_core.evaluate_plan(plan_dict)
        conflicts = ethical_result.get("conflicts") or []
        if conflicts:
            summary = "; ".join(
                f"{conflict.get('value')}: {conflict.get('reason')}" for conflict in conflicts
            )
            self.identity_manager.log_event("ethical_conflict", summary)

        identity_snapshot = {
            "summary": self.identity_manager.summarize(),
            "events": self.identity_manager.get_events(),
            "self_concept": self.identity_manager.get_self_concept(),
        }

        meta_notes_copy = [note.copy() for note in meta_notes]
        return {
            "cycle_id": cycle_id,
            "qualia": deepcopy(qualia_snapshot),
            "identity": deepcopy(identity_snapshot),
            "metacog": deepcopy(meta_notes_copy),
            "meta": deepcopy(meta_notes_copy),
            "ethics": deepcopy(ethical_result),
            "timestamp": float(cycle_id),
        }

    def run_simulation(self, hypothetical_state: Mapping[str, Any]) -> Dict[str, Any]:
        """Convenience wrapper for SimulationEngine."""

        if self._simulation_engine is None:
            self._simulation_engine = SimulationEngine()

        return self._simulation_engine.simulate(self, dict(hypothetical_state))

    def start_cycle(self, input_state: Mapping[str, Any]) -> Dict[str, Any]:
        """Legacy entrypoint mapped to :py:meth:`run_cycle`."""

        report = self.run_cycle(input_state)
        return {
            "cycle": report.get("cycle_id", 0),
            "qualia": deepcopy(report.get("qualia", {})),
            "meta_notes": deepcopy(report.get("metacog", [])),
            "ethical": deepcopy(report.get("ethics", {})),
            "identity_summary": report.get("identity", {}).get("summary", ""),
        }

    def get_state(self) -> Dict[str, Any]:
        """Return a stable snapshot of current inner-world status."""

        return {
            "qualia": self.inner_experience.get_state(),
            "meta_notes": self.meta_monitor.get_recent_notes(),
            "self_concept": self.identity_manager.get_self_concept(),
            "identity_events": self.identity_manager.get_events(),
        }
