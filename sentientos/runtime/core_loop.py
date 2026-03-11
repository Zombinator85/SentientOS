"""Core cognition loop integration for SentientOS runtime."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Callable, Mapping, MutableMapping, cast

from sentientos.cognition import CognitiveSurface
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
    log_debug_federation_digest,
    log_debug_federation_consensus,
    log_debug_config_snapshot,
)

from .interfaces import CycleInput, CycleOutput, InnerWorldReport

LOGGER = logging.getLogger(__name__)


def _as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


class CoreLoop:
    """Drive deterministic cognition cycles with passive introspection."""

    def __init__(
        self,
        innerworld: InnerWorldOrchestrator | None = None,
        cognitive_surface: CognitiveSurface | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.innerworld = innerworld or InnerWorldOrchestrator()
        self.cognitive_surface = cognitive_surface
        self._logger = logger or LOGGER

    def run_cycle(self, cycle_state: CycleInput) -> CycleOutput:
        """Execute a single cognition cycle with inner-world introspection."""

        state_snapshot: MutableMapping[str, Any] = dict(cycle_state)
        inner_report: InnerWorldReport = {}
        simulation_report: dict[str, Any] = {}
        ethics_report: dict[str, Any] = {}
        try:
            inner_report = cast(InnerWorldReport, self.innerworld.run_cycle(deepcopy(state_snapshot)))
        except Exception as exc:  # pragma: no cover - defensive guard
            self._logger.debug("[innerworld-cycle] failed: %s", exc)
            inner_report = {"cycle_id": getattr(self.innerworld, "_cycle_counter", 0), "meta": []}
        else:
            self._logger.debug("[innerworld-cycle] %s", inner_report)
            log_innerworld_cycle(dict(inner_report))

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

        get_history_summary = cast(Callable[[], dict[str, Any]], self.innerworld.get_history_summary)
        history_summary = get_history_summary()
        log_history_summary(history_summary)
        get_reflection_summary = cast(Callable[[], dict[str, Any]], self.innerworld.get_reflection_summary)
        reflection_summary = get_reflection_summary()
        log_debug_reflection(reflection_summary)
        cognitive_report = _as_dict(inner_report.get("cognitive_report", {}))
        log_debug_cognitive_report(cognitive_report)
        get_identity_summary = cast(Callable[[], dict[str, Any]], self.innerworld.get_identity_summary)
        identity_summary = get_identity_summary()
        log_debug_narrative(identity_summary)
        get_narrative_chapters = cast(Callable[[], list[Mapping[str, Any]]], self.innerworld.get_narrative_chapters)
        narrative_chapters = get_narrative_chapters()
        workspace_spotlight = _as_dict(inner_report.get("workspace_spotlight", {}))
        inner_dialogue = _as_list(inner_report.get("inner_dialogue", []))
        value_drift = _as_dict(inner_report.get("value_drift", {}))
        autobiography = _as_list(inner_report.get("autobiography", []))
        federation_digest = _as_dict(inner_report.get("federation_digest", {}))
        federation_consensus = _as_dict(inner_report.get("federation_consensus", {}))
        log_debug_spotlight(workspace_spotlight)
        log_debug_dialogue(inner_dialogue)
        log_debug_value_drift(value_drift)
        log_debug_autobio(autobiography)
        log_debug_federation_digest(federation_digest)
        log_debug_federation_consensus(federation_consensus)

        config_snapshot = None
        if not inner_report.get("simulation_mode"):
            config_snapshot = inner_report.get("config_snapshot")
            if config_snapshot is not None:
                log_debug_config_snapshot(_as_dict(config_snapshot))

        state_snapshot["innerworld"] = inner_report
        cognitive_proposals = []
        cognitive_summary = []
        if self.cognitive_surface is not None and self.cognitive_surface.enabled:
            proposals = self.cognitive_surface.proposals_from_state(state_snapshot)
            cognitive_proposals = [proposal.as_dict() for proposal in proposals]
            cognitive_summary = self.cognitive_surface.preference_usage_summary()
        result: dict[str, Any] = {
            "cycle_state": state_snapshot,
            "innerworld": inner_report,
            "simulation": simulation_report,
            "ethics": ethics_report,
            "innerworld_history_summary": history_summary,
            "innerworld_reflection": reflection_summary,
            "cognitive_report": cognitive_report,
            "narrative_chapters": narrative_chapters,
            "identity_summary": identity_summary,
            "workspace_spotlight": workspace_spotlight,
            "inner_dialogue": inner_dialogue,
            "value_drift": value_drift,
            "autobiography": autobiography,
            "federation_digest": federation_digest,
            "federation_consensus": federation_consensus,
            "cognitive_proposals": cognitive_proposals,
            "cognitive_summary": cognitive_summary,
        }

        if config_snapshot is not None:
            result["config_snapshot"] = config_snapshot

        return cast(CycleOutput, result)
