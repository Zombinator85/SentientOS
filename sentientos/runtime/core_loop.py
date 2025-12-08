"""Core cognition loop integration for SentientOS runtime."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, MutableMapping

from sentientos.innerworld import InnerWorldOrchestrator
from sentientos.logging.events import (
    log_ethics_report,
    log_history_summary,
    log_innerworld_cycle,
    log_debug_reflection,
    log_debug_cognitive_report,
    log_debug_narrative,
    log_debug_spotlight,
    log_debug_dialogue,
    log_debug_value_drift,
    log_debug_autobio,
    log_simulation_cycle,
)

from .interfaces import CycleInput, CycleOutput, InnerWorldReport

LOGGER = logging.getLogger(__name__)


class CoreLoop:
    """Drive deterministic cognition cycles with passive introspection."""

    def __init__(
        self,
        innerworld: InnerWorldOrchestrator | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.innerworld = innerworld or InnerWorldOrchestrator()
        self._logger = logger or LOGGER

    def run_cycle(self, cycle_state: CycleInput) -> CycleOutput:
        """Execute a single cognition cycle with inner-world introspection."""

        state_snapshot: MutableMapping[str, Any] = dict(cycle_state)
        inner_report: InnerWorldReport = {}
        simulation_report: dict[str, Any] = {}
        ethics_report: dict[str, Any] = {}
        try:
            inner_report = self.innerworld.run_cycle(deepcopy(state_snapshot))
        except Exception as exc:  # pragma: no cover - defensive guard
            self._logger.debug("[innerworld-cycle] failed: %s", exc)
            inner_report = {"cycle_id": getattr(self.innerworld, "_cycle_counter", 0), "meta": []}
        else:
            self._logger.debug("[innerworld-cycle] %s", inner_report)
            log_innerworld_cycle(inner_report)

        current_plan = state_snapshot.get("plan")
        try:
            ethics_report = self.innerworld.ethics.evaluate(
                plan=current_plan,
                context=cycle_state,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            self._logger.debug("[innerworld-ethics] failed: %s", exc)
            ethics_report = {}
        else:
            log_ethics_report(ethics_report)

        plan_candidate = state_snapshot.get("plan")
        if plan_candidate is not None:
            hypothetical_state = {
                "plan": deepcopy(plan_candidate),
                "context": deepcopy(state_snapshot.get("context", {})),
                "inputs": deepcopy(state_snapshot),
            }
            try:
                simulation_report = self.innerworld.run_simulation(hypothetical_state)
            except Exception as exc:  # pragma: no cover - defensive guard
                self._logger.debug("[innerworld-simulation] failed: %s", exc)
                simulation_report = {}
            else:
                self._logger.debug("[innerworld-simulation] %s", simulation_report)
                log_simulation_cycle(simulation_report)

        history_summary = self.innerworld.get_history_summary()
        log_history_summary(history_summary)
        reflection_summary = self.innerworld.get_reflection_summary()
        log_debug_reflection(reflection_summary)
        cognitive_report = inner_report.get("cognitive_report", {})
        log_debug_cognitive_report(cognitive_report)
        identity_summary = self.innerworld.get_identity_summary()
        log_debug_narrative(identity_summary)
        narrative_chapters = self.innerworld.get_narrative_chapters()
        log_debug_spotlight(inner_report.get("workspace_spotlight", {}))
        log_debug_dialogue(inner_report.get("inner_dialogue", []))
        log_debug_value_drift(inner_report.get("value_drift", {}))
        log_debug_autobio(inner_report.get("autobiography", []))

        state_snapshot["innerworld"] = inner_report
        return {
            "cycle_state": state_snapshot,
            "innerworld": inner_report,
            "simulation": simulation_report,
            "ethics": ethics_report,
            "innerworld_history_summary": history_summary,
            "innerworld_reflection": reflection_summary,
            "cognitive_report": cognitive_report,
            "narrative_chapters": narrative_chapters,
            "identity_summary": identity_summary,
            "workspace_spotlight": inner_report.get("workspace_spotlight"),
            "inner_dialogue": inner_report.get("inner_dialogue"),
            "value_drift": inner_report.get("value_drift"),
            "autobiography": inner_report.get("autobiography"),
        }
