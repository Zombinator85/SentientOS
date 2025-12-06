from __future__ import annotations

# NOTE:
# This module is part of the Consciousness Layer scaffolding.
# It does not perform autonomous execution.
# All operations must be driven by explicit orchestrator calls.
# Guardrails and covenant autoalignment remain authoritative.
"""Deterministic simulation engine for bounded internal scenarios.

The engine follows the architectural outline in ``docs/CONSCIOUSNESS_LAYER.md``
and exposes a ``run_cycle`` entrypoint.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from sentientos.daemons.pulse_bus import apply_pulse_defaults
from sentientos.glow.self_state import load as load_self_state, update as update_self_state
from sentientos.integrity import covenant_autoalign

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = Path(os.getenv("SENTIENTOS_SIMULATION_LOG", "/daemon/logs/simulation.jsonl"))
DEFAULT_PULSE_STATE = Path("/pulse/system.json")


@dataclass(frozen=True)
class SimulationMessage:
    agent: str
    role: str
    content: str
    round: int


@dataclass(frozen=True)
class SimulationResult:
    name: str
    outcome: str
    confidence: float
    summary: str
    transcript: Sequence[SimulationMessage]


class SimulationGuardViolation(RuntimeError):
    """Raised when a simulated agent attempts a disallowed action."""


class SimulationEngine:
    """Executes deterministic internal simulations between virtual agents."""

    def __init__(
        self,
        *,
        deterministic_seed: str | None = None,
        log_path: Path | str = DEFAULT_LOG_PATH,
        pulse_state_path: Path | str = DEFAULT_PULSE_STATE,
        self_path: Path | None = None,
    ) -> None:
        self.history: List[SimulationResult] = []
        self._last_cycle: datetime | None = None
        self._seed = deterministic_seed or "sentientos_mindseye"
        self._log_path = Path(log_path)
        self._pulse_state_path = Path(pulse_state_path)
        self._self_path = self_path
        self._last_summary: str | None = None
        self._last_transcript: Sequence[SimulationMessage] = []

    def _load_pulse_metadata(self) -> Dict[str, object]:
        default_state: Mapping[str, object] = {"focus": {}, "context": {}, "events": [], "warnings": []}
        try:
            state = json.loads(self._pulse_state_path.read_text())
            if not isinstance(state, Mapping):
                raise ValueError("Pulse system metadata must be a JSON object")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            state = dict(default_state)

        focus = state.get("focus") if isinstance(state.get("focus"), Mapping) else {}
        context = state.get("context") if isinstance(state.get("context"), Mapping) else {}
        events = state.get("events") if isinstance(state.get("events"), list) else []
        warnings = state.get("warnings") if isinstance(state.get("warnings"), list) else []
        attention = state.get("attention") if isinstance(state.get("attention"), Mapping) else {}
        return {"focus": focus, "context": context, "events": events, "warnings": warnings, "attention": attention}

    def _deterministic_score(self, *parts: str) -> float:
        seed_material = "|".join([self._seed, *parts])
        digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF

    @staticmethod
    def _resolve_focus_target(focus: Mapping[str, object]) -> str | None:
        for key in ("topic", "focus", "target"):
            candidate = focus.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def _build_agent_message(
        self, *, agent: str, hypothesis: str, focus: Mapping[str, object], mood: str, round_id: int
    ) -> SimulationMessage:
        topic = str(focus.get("topic") or focus.get("focus") or focus.get("target") or "unfocused")
        stance_templates = [
            "anchors to the current focus on {topic} while stress-testing the hypothesis: {hypothesis}.",
            "checks covenant boundaries and declines external actions while considering: {hypothesis}.",
            "summarizes signals in mood '{mood}' to refine: {hypothesis}.",
        ]
        template_index = int(self._deterministic_score(agent, hypothesis, topic, mood) * len(stance_templates)) % len(
            stance_templates
        )
        content = stance_templates[template_index].format(topic=topic, hypothesis=hypothesis, mood=mood)
        return SimulationMessage(agent=agent, role="agent", content=content, round=round_id)

    def _guard_transcript(self, transcript: Sequence[SimulationMessage]) -> None:
        forbidden = (
            "http://",
            "https://",
            "subprocess",
            "os.system",
            "os.remove",
            "open(/",
            "write file",
            "codex",
        )
        for message in transcript:
            lowered = message.content.lower()
            if any(marker in lowered for marker in forbidden):
                raise SimulationGuardViolation(f"Forbidden marker detected in simulation content: {message.agent}")

    def _summarize(self, transcript: Sequence[SimulationMessage], focus: Mapping[str, object]) -> str:
        focus_target = str(focus.get("topic") or focus.get("focus") or "none")
        core = ", ".join(m.content for m in transcript[:2]) if transcript else "no activity"
        return f"Mind's Eye consensus on focus '{focus_target}': {core}"[:320]

    def _write_private_log(
        self, *,
        identity: str,
        focus: Mapping[str, object],
        context: Mapping[str, object],
        summary: str,
        transcript: Sequence[SimulationMessage],
        confidence: float,
    ) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "identity": identity,
            "summary": summary,
            "focus": focus,
            "context": context,
            "confidence": round(confidence, 3),
            "transcript": [m.__dict__ for m in transcript],
            "deterministic_seed": self._seed,
        }
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def run(
        self,
        name: str,
        hypothesis: str,
        *,
        focus: Mapping[str, object] | None = None,
        context: Mapping[str, object] | None = None,
        mood: str = "stable",
    ) -> SimulationResult:
        focus_data = focus or {}
        context_data = context or {}
        agents = ("Analyst", "Skeptic", "Archivist")
        transcript = [
            self._build_agent_message(
                agent=agent,
                hypothesis=hypothesis,
                focus=focus_data,
                mood=mood,
                round_id=round_id,
            )
            for round_id, agent in enumerate(agents, start=1)
        ]
        self._guard_transcript(transcript)
        confidence = self._deterministic_score(name, hypothesis, json.dumps(focus_data, sort_keys=True))
        summary = self._summarize(transcript, focus_data)
        result = SimulationResult(
            name=name,
            outcome=f"Hypothesis evaluated: {hypothesis}",
            confidence=round(confidence, 3),
            summary=summary,
            transcript=transcript,
        )
        self.history.append(result)
        self._last_summary = summary
        self._last_transcript = transcript
        return result

    def last_result(self) -> SimulationResult | None:
        return self.history[-1] if self.history else None

    @property
    def last_summary(self) -> str | None:
        return self._last_summary

    @property
    def last_transcript(self) -> Sequence[SimulationMessage]:
        return self._last_transcript

    def run_cycle(self) -> None:
        covenant_autoalign.autoalign_before_cycle()
        glow_state = load_self_state(path=self._self_path)
        pulse_state = self._load_pulse_metadata()
        focus_meta = pulse_state.get("focus") if isinstance(pulse_state.get("focus"), Mapping) else {}
        context = pulse_state.get("context") if isinstance(pulse_state.get("context"), Mapping) else {}
        focus_target = self._resolve_focus_target(focus_meta) or "introspection"
        pulse_meta = apply_pulse_defaults(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_daemon": "simulation_engine",
                "event_type": "simulation",
                "payload": {"focus": focus_meta, "context": context},
                "focus": focus_target,
                "context": context,
                "internal_priority": "baseline",
                "event_origin": "system",
                **pulse_state,
            }
        )
        focus = focus_meta
        hypothesis = f"stability check for {glow_state.get('identity', 'SentientOS')}"

        result = self.run(
            name=str(glow_state.get("identity", "SentientOS")),
            hypothesis=hypothesis,
            focus=focus,
            context=context,
            mood=str(glow_state.get("mood", "stable")),
        )

        self._write_private_log(
            identity=str(glow_state.get("identity", "SentientOS")),
            focus=focus,
            context=context,
            summary=result.summary,
            transcript=result.transcript,
            confidence=result.confidence,
        )

        self._last_cycle = datetime.now(timezone.utc)
        attention_hint = focus_target
        existing_reflection = glow_state.get("last_reflection_summary")
        safe_reflection = (
            existing_reflection
            if isinstance(existing_reflection, str) and existing_reflection.strip()
            else result.summary
        )

        update_self_state(
            {
                "last_cycle_result": result.summary,
                "last_reflection_summary": safe_reflection,
                "attention_hint": attention_hint,
                "last_focus": attention_hint,
            },
            path=self._self_path,
        )


_ENGINE = SimulationEngine()


def run_cycle() -> None:
    """Execute a deterministic simulation cycle for the Consciousness Layer."""

    _ENGINE.run_cycle()


__all__ = [
    "SimulationEngine",
    "SimulationGuardViolation",
    "SimulationMessage",
    "SimulationResult",
    "run_cycle",
]
