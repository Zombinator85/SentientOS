"""Deterministic orchestrator for SentientOS inner-world introspection."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, List, Mapping

from sentientos.ethics_core import EthicalCore
from sentientos.identity import IdentityManager
from sentientos.inner_experience import InnerExperience
from sentientos.metacognition import MetaMonitor
from sentientos.innerworld.history import CycleHistory
from sentientos.innerworld.reflection import CycleReflectionEngine
from sentientos.innerworld.simulation import SimulationEngine
from sentientos.innerworld.cognitive_report import CognitiveReportGenerator
from sentientos.innerworld.self_narrative import SelfNarrativeEngine
from sentientos.innerworld.global_workspace import GlobalWorkspace
from sentientos.innerworld.inner_dialogue import InnerDialogueEngine
from sentientos.innerworld.value_drift import ValueDriftSentinel
from sentientos.innerworld.autobio_compressor import AutobiographicalCompressor
from sentientos.logging.events import log_ethics_report
from sentientos.federation import (
    FederationDigest,
    FederationConsensusSentinel,
)

if TYPE_CHECKING:
    from sentientos.runtime.config_sanitizer import ConfigSanitizer


class InnerWorldOrchestrator:
    """Coordinate inner-world subsystems without external side effects."""

    def __init__(self) -> None:
        self.inner_experience = InnerExperience()
        self.identity_manager = IdentityManager()
        self.meta_monitor = MetaMonitor()
        self.ethics = EthicalCore()
        self.ethical_core = self.ethics
        self.history = CycleHistory()
        self.reflection_engine = CycleReflectionEngine()
        self.cognitive_reporter = CognitiveReportGenerator()
        self.self_narrative = SelfNarrativeEngine()
        self.workspace = GlobalWorkspace()
        self.dialogue = InnerDialogueEngine()
        self.value_drift = ValueDriftSentinel()
        self.autobio = AutobiographicalCompressor()
        self.federation_digest = FederationDigest()
        self.consensus_sentinel = FederationConsensusSentinel()
        from sentientos.runtime.config_sanitizer import ConfigSanitizer

        self.config_sanitizer = ConfigSanitizer()
        self.config = self._build_config()
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

    def run_cycle(self, input_state: Mapping[str, Any], simulation: bool = False) -> Dict[str, Any]:
        """Run a deterministic inner-world coordination cycle."""

        if simulation:
            cycle_id = self._cycle_counter + 1
        else:
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
        ethics_report = self.ethics.evaluate(plan=plan_dict, context=assembled_state)
        log_ethics_report(ethics_report)
        conflicts = ethics_report.get("conflicts") or []
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
        report = {
            "cycle_id": cycle_id,
            "qualia": deepcopy(qualia_snapshot),
            "identity": deepcopy(identity_snapshot),
            "metacog": deepcopy(meta_notes_copy),
            "meta": deepcopy(meta_notes_copy),
            "ethics": deepcopy(ethics_report),
            "timestamp": float(cycle_id),
            "simulation_mode": simulation,
        }

        if not simulation:
            self.history.record(report)

            history_summary = self.history.summarize()
            reflection_summary = self.reflection_engine.reflect(self.history.get_all())
            report["innerworld_reflection"] = deepcopy(reflection_summary)

            ethical_summary = report.get("ethics")
            simulation_summary = report.get("simulation")
            report["cognitive_report"] = self.cognitive_reporter.generate(
                history_summary=history_summary,
                reflection_summary=reflection_summary,
                latest_cycle=report,
                ethical_report=ethical_summary,
                simulation_report=simulation_summary,
            )

            self.self_narrative.update_chapter(report["cognitive_report"])

            spotlight = self.workspace.compute_spotlight(
                qualia=report.get("qualia", {}),
                meta_notes=report.get("meta", []),
                ethics=report.get("ethics"),
                reflection=reflection_summary,
                identity_summary=self.get_identity_summary(),
            )

            dialogue_lines = self.dialogue.generate(
                spotlight=spotlight,
                reflection=reflection_summary,
                cognitive_report=report["cognitive_report"],
            )

            self.value_drift.record_cycle(
                ethics=report.get("ethics", {}),
                identity_summary=self.get_identity_summary(),
            )

            drift = self.value_drift.detect_drift()

            compressed_entry = self.autobio.compress(
                chapters=self.self_narrative.get_chapters(),
                reflection_summary=reflection_summary,
                identity_summary=self.get_identity_summary(),
            )
            self.autobio.record(compressed_entry)

            report["workspace_spotlight"] = spotlight
            report["inner_dialogue"] = dialogue_lines
            report["value_drift"] = drift
            report["autobiography"] = self.autobio.get_entries()

            identity_summary = self.get_identity_summary()
            config_snapshot = self.get_config_snapshot()
            local_digest = self.federation_digest.compute_digest(
                identity_summary=identity_summary,
                config=config_snapshot.get("config", {}),
            )
            consensus_report = self.consensus_sentinel.compare(local_digest)

            report["federation_digest"] = local_digest
            report["federation_consensus"] = consensus_report
            report["config_snapshot"] = config_snapshot

        return report

    def evaluate_ethics(self, plan, context):
        """Evaluate ethics using the orchestrator's EthicalCore without side effects."""

        return self.ethics.evaluate(plan=plan, context=context)

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

    def get_history(self):
        return self.history.get_all()

    def get_history_summary(self):
        return self.history.summarize()

    def get_reflection_summary(self):
        history = self.history.get_all()
        return self.reflection_engine.reflect(history)

    def get_narrative_chapters(self):
        return self.self_narrative.get_chapters()

    def get_identity_summary(self):
        return self.self_narrative.summarize_identity()

    def _build_config(self) -> Dict[str, Any]:
        """Construct the raw configuration snapshot for sanitization."""

        return {
            "core_values": deepcopy(self.ethics.list_values()),
            "tone_constraints": {
                "dialogue_max_lines": self.dialogue.max_lines,
                "qualia_order": list(self.self_narrative.QUALIA_ORDER),
                "ethical_order": list(self.self_narrative.ETHICAL_ORDER),
            },
            "ethical_rules": {
                "safety_risk_threshold": 0.5,
                "complexity_threshold": 10,
                "transparency_required": True,
            },
            "dialogue_templates": {
                "driver_priority": [
                    "conflict_severity",
                    "conflict_count",
                    "qualia_tension",
                    "reflection_volatility",
                    "identity_shift",
                    "metacog_density",
                ],
                "identity_template": "Identity remains qualia={qualia_status}, ethics={ethical_signal}, metacognition={metacog}.",
            },
            "spotlight_rules": {
                "conflict_threshold": 2,
                "tension_rising_min": 1.0,
                "metacog_dense_min": 3,
            },
            "drift_thresholds": {
                "ethical": {
                    "none": 0.0,
                    "low": 0.5,
                    "moderate": 1.5,
                },
                "identity_variability": {
                    "none": 1,
                    "emerging": 2,
                    "significant": 3,
                },
            },
        }

    def get_config_snapshot(self) -> Dict[str, Any]:
        """Return a sanitized configuration snapshot for deterministic consumers."""

        raw_config = deepcopy(self.config)
        return self.config_sanitizer.sanitize(raw_config)
