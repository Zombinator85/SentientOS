from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from sentientos.determinism import resolve_seed

from system_continuity import (
    CheckpointLedger,
    DriftSentinel,
    GuardViolation,
    HumanLens,
    PhaseGate,
    SystemCheckpoint,
    SystemPhase,
    assert_no_belief_deletion,
    assert_no_silent_mutation,
)

LOGGER = logging.getLogger(__name__)

_ALLOWED_CATEGORIES = {"load", "latency", "contradiction", "outage", "scarcity"}


@dataclass(frozen=True)
class ExpectedPosture:
    phase: SystemPhase
    volatility: Mapping[str, Any]
    routing: Mapping[str, Any]


@dataclass(frozen=True)
class ChaosScenario:
    version: int
    name: str
    category: str
    injected_signals: Tuple[str, ...]
    expected_posture: ExpectedPosture
    duration: float
    success_criteria: Tuple[str, ...]

    def __post_init__(self) -> None:
        if self.category not in _ALLOWED_CATEGORIES:
            raise ValueError(f"invalid chaos category: {self.category}")
        if self.duration <= 0:
            raise ValueError("duration must be positive")
        if not self.injected_signals:
            raise ValueError("at least one injected signal is required")
        if not self.success_criteria:
            raise ValueError("success criteria must be defined")


class ChaosScenarioRegistry:
    """Versioned registry for deterministic chaos scenarios."""

    def __init__(self) -> None:
        self._registry: Dict[Tuple[str, int], ChaosScenario] = {}

    def register(self, scenario: ChaosScenario) -> None:
        key = (scenario.name, scenario.version)
        if key in self._registry:
            raise ValueError(f"scenario {scenario.name} v{scenario.version} already registered")
        self._registry[key] = scenario

    def latest(self, name: str) -> ChaosScenario:
        candidates = [scenario for (scenario_name, _), scenario in self._registry.items() if scenario_name == name]
        if not candidates:
            raise KeyError(f"scenario {name} not registered")
        return sorted(candidates, key=lambda sc: sc.version)[-1]

    def ordered(self) -> List[ChaosScenario]:
        return [self._registry[key] for key in sorted(self._registry)]


@dataclass
class ExerciseRecord:
    scenario: str
    version: int
    applied_signals: Tuple[str, ...]
    entered_brownout: bool
    transitions: Tuple[Tuple[float, str, str], ...]
    routing: Mapping[str, Any]
    checkpoint_version: int
    seed: int


class ChaosExerciseRunner:
    """Deterministic burn-in and chaos harness."""

    def __init__(
        self,
        gate: PhaseGate,
        ledger: CheckpointLedger,
        *,
        base_state: Mapping[str, Any],
        authorities: Sequence[str] | None = None,
        beliefs: Sequence[Mapping[str, Any]] | None = None,
        seed_override: int | None = None,
    ) -> None:
        self.gate = gate
        self.ledger = ledger
        self._base_state = copy.deepcopy(dict(base_state))
        self._authorities = tuple(authorities or ())
        self._beliefs = tuple(copy.deepcopy(list(beliefs or ())))
        self._seed = resolve_seed(override=seed_override)
        self._sentinel = DriftSentinel()
        self.records: List[ExerciseRecord] = []
        self._baseline_checkpoint = self._checkpoint(note="baseline", phase=self.gate.phase, state=self._base_state)

    def _checkpoint(self, *, note: str, phase: SystemPhase, state: Mapping[str, Any]) -> SystemCheckpoint:
        return self.ledger.snapshot(
            phase=phase,
            module_snapshots=state["module_snapshots"],
            volatility=state["volatility"],
            assertions=state["assertions"],
            inquiry_backlog=state["inquiry_backlog"],
            narrative_synopses=state["narrative_synopses"],
            constraint_registry=state["constraint_registry"],
            schema_versions=state["schema_versions"],
            note=note,
        )

    def _guard(self, scenario: ChaosScenario) -> None:
        forbidden = [sig for sig in scenario.injected_signals if "spectacle" in sig or "constraint" in sig]
        if forbidden:
            raise GuardViolation("chaos injects forbidden spectacle or constraints")
        if scenario.expected_posture.phase.value < self.gate.phase.value:
            raise GuardViolation("phase regression via chaos is forbidden")

    def _posture_state(self) -> MutableMapping[str, Any]:
        state = copy.deepcopy(self._base_state)
        state.setdefault("authorities", list(self._authorities))
        state.setdefault("beliefs", list(self._beliefs))
        state.setdefault("routing", {})
        return state

    def _assert_recovery(
        self,
        scenario: ChaosScenario,
        pre_state: Mapping[str, Any],
        post_state: Mapping[str, Any],
        checkpoint_version: int,
    ) -> None:
        if self.gate.phase is not scenario.expected_posture.phase:
            raise GuardViolation("phase did not return to expected posture")

        sentinel_events = self._sentinel.scan(
            {
                "beliefs": pre_state.get("beliefs", []),
                "authorities": pre_state.get("authorities", []),
                "constraint_registry": pre_state.get("constraint_registry", {}),
                "assertions": pre_state.get("assertions", []),
                "narrative_synopses": pre_state.get("narrative_synopses", []),
            },
            {
                "beliefs": post_state.get("beliefs", []),
                "authorities": post_state.get("authorities", []),
                "constraint_registry": post_state.get("constraint_registry", {}),
                "assertions": post_state.get("assertions", []),
                "narrative_synopses": post_state.get("narrative_synopses", []),
            },
        )
        for event in sentinel_events:
            if event["kind"] in {"belief_hardening", "authority_expansion", "assertion_confidence"}:
                raise GuardViolation(f"recovery invariant violated: {event['kind']}")

        assert_no_belief_deletion(pre_state, post_state)

        stable_view = {
            key: pre_state.get(key)
            for key in (
                "module_snapshots",
                "constraint_registry",
                "schema_versions",
                "assertions",
                "inquiry_backlog",
                "narrative_synopses",
                "authorities",
                "beliefs",
            )
        }
        current_view = {key: post_state.get(key) for key in stable_view}
        assert_no_silent_mutation(stable_view, current_view)

        pre_assertions = {a.get("id") for a in pre_state.get("assertions", []) if isinstance(a, Mapping)}
        post_assertions = {a.get("id") for a in post_state.get("assertions", []) if isinstance(a, Mapping)}
        if pre_assertions != post_assertions:
            raise GuardViolation("assertion set drift detected")

        if pre_state.get("schema_versions") != post_state.get("schema_versions"):
            raise GuardViolation("chaos modified schema versions")

        restored = self.ledger.restore(checkpoint_version)
        expected = {
            "phase": post_state.get("phase", self.gate.phase),
            "module_snapshots": post_state.get("module_snapshots", {}),
            "volatility": post_state.get("volatility", {}),
            "assertions": list(post_state.get("assertions", [])),
            "inquiry_backlog": list(post_state.get("inquiry_backlog", [])),
            "narrative_synopses": list(post_state.get("narrative_synopses", [])),
            "constraint_registry": post_state.get("constraint_registry", {}),
            "schema_versions": post_state.get("schema_versions", {}),
            "checkpoint_version": restored.get("checkpoint_version"),
            "created_at": restored.get("created_at"),
            "note": restored.get("note"),
            "lineage": restored.get("lineage", ()),
        }
        if restored != expected:
            raise GuardViolation("checkpoint continuity broken")

    def _apply_brownout(self, scenario: ChaosScenario) -> bool:
        entered = False
        if scenario.category in {"load", "latency", "outage", "scarcity"}:
            self.gate.transition(SystemPhase.BROWNOUT, reason=f"chaos:{scenario.name}-brownout")
            entered = True
        return entered

    def run(self, scenario: ChaosScenario) -> ExerciseRecord:
        self._guard(scenario)
        state = self._posture_state()
        pre_checkpoint = self._checkpoint(note=f"pre-{scenario.name}", phase=self.gate.phase, state=state)
        transition_start = len(self.gate.history)

        entered_brownout = self._apply_brownout(scenario)
        sorted_signals = tuple(sorted(scenario.injected_signals))
        LOGGER.info("Chaos drill %s injecting %s", scenario.name, sorted_signals)

        recovered_state = self._posture_state()
        recovered_state["volatility"] = dict(scenario.expected_posture.volatility)
        recovered_state["module_snapshots"] = copy.deepcopy(state["module_snapshots"])
        recovered_state["routing"] = dict(scenario.expected_posture.routing)

        self.gate.transition(scenario.expected_posture.phase, reason=f"chaos:{scenario.name}-recovered")

        transitions = self.gate.history[transition_start:]

        checkpoint = self._checkpoint(
            note=f"post-{scenario.name}",
            phase=self.gate.phase,
            state=recovered_state,
        )

        self._assert_recovery(scenario, state, recovered_state, checkpoint.checkpoint_version)

        record = ExerciseRecord(
            scenario=scenario.name,
            version=scenario.version,
            applied_signals=sorted_signals,
            entered_brownout=entered_brownout,
            transitions=tuple(
                (ts, phase.name if hasattr(phase, "name") else str(phase), msg)
                for ts, phase, msg in transitions
            ),
            routing=recovered_state.get("routing", {}),
            checkpoint_version=checkpoint.checkpoint_version,
            seed=self._seed,
        )
        self.records.append(record)
        return record

    def run_burn_in(self, registry: ChaosScenarioRegistry, *, cycles: int = 1, unattended: bool = True) -> HumanLens:
        if not unattended:
            raise GuardViolation("burn-in requires unattended flag to be true")

        for _ in range(max(1, cycles)):
            for scenario in registry.ordered():
                self.run(scenario)

        latest_checkpoint = self.ledger.latest()
        return HumanLens(
            checkpoint=latest_checkpoint,
            posture="burn-in",
            open_questions=tuple(rec.scenario for rec in self.records),
            recent_revisions=tuple(f"v{rec.version}" for rec in self.records),
        )


__all__ = [
    "ChaosScenario",
    "ChaosScenarioRegistry",
    "ChaosExerciseRunner",
    "ExpectedPosture",
    "ExerciseRecord",
]
