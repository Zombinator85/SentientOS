"""Consciousness Layer simulation engine scaffold.

Provides the placeholder simulation hooks described in
``docs/CONSCIOUSNESS_LAYER.md`` and exposes a ``run_cycle`` entrypoint.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from sentientos.daemons.pulse_bus import apply_pulse_defaults
from sentientos.glow import self_state

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = Path("/daemon/logs/simulation.jsonl")


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
        pulse_root: Path | str = Path("pulse"),
        self_path: Path | None = None,
    ) -> None:
        self.history: List[SimulationResult] = []
        self._last_cycle: datetime | None = None
        self._seed = deterministic_seed or "sentientos_mindseye"
        self._log_path = Path(log_path)
        self._pulse_root = Path(pulse_root)
        self._self_path = self_path
        self._last_summary: str | None = None
        self._last_transcript: Sequence[SimulationMessage] = []

    def _load_pulse_metadata(self) -> Dict[str, object]:
        def _load(path: Path, default: Mapping[str, object]) -> Mapping[str, object]:
            try:
                return json.loads(path.read_text())
            except FileNotFoundError:
                return dict(default)
            except json.JSONDecodeError:
                return dict(default)

        focus = _load(self._pulse_root / "focus.json", {"topic": None})
        context = _load(self._pulse_root / "context.json", {"summary": "", "window": []})
        return {"focus": focus, "context": context}

    def _deterministic_score(self, *parts: str) -> float:
        seed_material = "|".join([self._seed, *parts])
        digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF

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
        glow_state = self_state.load(path=self._self_path)
        pulse_meta = apply_pulse_defaults(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_daemon": "simulation_engine",
                "event_type": "simulation",
                "payload": {},
                **self._load_pulse_metadata(),
            }
        )
        focus = pulse_meta.get("focus") if isinstance(pulse_meta.get("focus"), Mapping) else {}
        context = pulse_meta.get("context") if isinstance(pulse_meta.get("context"), Mapping) else {}
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
        self_state.update(
            {
                "last_cycle_result": result.summary,
                "last_reflection_summary": result.summary,
                "attention_hint": focus.get("topic") if isinstance(focus, Mapping) else None,
                "last_focus": focus.get("topic") if isinstance(focus, Mapping) else None,
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
