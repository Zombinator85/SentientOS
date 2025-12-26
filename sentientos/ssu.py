"""Symbolic Screen Understanding (SSU) for non-authoritative UI semantics."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence

import json

from logging_config import get_log_path
from sentientos.cor import Hypothesis, ObservationEvent


_DEFAULT_MIN_CONFIDENCE = 0.6
_DEFAULT_PROPOSAL_CONFIDENCE = 0.8


@dataclass(frozen=True)
class SymbolicElement:
    app: Optional[str]
    element_type: str
    label: Optional[str]
    state: Optional[str]
    confidence: float
    authority: str = "none"
    tentative: bool = False
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "app": self.app,
            "element_type": self.element_type,
            "label": self.label,
            "state": self.state,
            "confidence": self.confidence,
            "authority": self.authority,
            "tentative": self.tentative,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class SymbolicObservation:
    timestamp: str
    app: Optional[str]
    window_title: Optional[str]
    ui_state: Optional[str]
    symbols: tuple[SymbolicElement, ...]
    degraded: bool
    sequence_id: int
    raw_observation: Dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "timestamp": self.timestamp,
            "app": self.app,
            "window_title": self.window_title,
            "ui_state": self.ui_state,
            "symbols": [symbol.to_dict() for symbol in self.symbols],
            "degraded": self.degraded,
            "sequence_id": self.sequence_id,
            "authority": "none",
        }
        if self.raw_observation:
            payload["raw_observation"] = dict(self.raw_observation)
        return payload


@dataclass
class SSUConfig:
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE
    proposal_confidence_threshold: float = _DEFAULT_PROPOSAL_CONFIDENCE


class SymbolicScreenUnderstanding:
    """Convert raw screen observations into non-authoritative symbolic UI elements."""

    def __init__(
        self,
        config: Optional[SSUConfig] = None,
        log_path: Optional[str] = None,
    ) -> None:
        self.config = config or SSUConfig()
        self.log_path = get_log_path(log_path or "ssu_events.jsonl", "SSU_LOG")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence = 0

    def extract(self, observation: Dict[str, object]) -> SymbolicObservation:
        self._sequence += 1
        timestamp = observation.get("timestamp")
        if isinstance(timestamp, str):
            iso_timestamp = timestamp
        else:
            iso_timestamp = datetime.now(timezone.utc).isoformat()

        app = self._string_or_none(observation.get("app"))
        window_title = self._string_or_none(observation.get("window_title"))
        elements = self._list_or_empty(observation.get("elements"))
        text = self._string_or_none(observation.get("text"))
        text_confidence = self._coerce_confidence(observation.get("text_confidence"))
        if text_confidence is None:
            text_confidence = self._coerce_confidence(observation.get("ocr_confidence"))

        symbols = self._build_symbols(app, elements)
        ui_state = self._infer_ui_state(text, symbols)
        if ui_state:
            symbols.append(
                SymbolicElement(
                    app=app,
                    element_type="ui_state",
                    label=ui_state,
                    state=ui_state,
                    confidence=text_confidence or 0.4,
                    tentative=(text_confidence or 0.4) < self.config.min_confidence,
                )
            )

        degraded = not symbols or all(symbol.tentative for symbol in symbols)
        if degraded and (app or window_title):
            symbols.append(
                SymbolicElement(
                    app=app,
                    element_type="app_context",
                    label=window_title or app,
                    state=None,
                    confidence=0.4,
                    tentative=True,
                )
            )

        symbolic = SymbolicObservation(
            timestamp=iso_timestamp,
            app=app,
            window_title=window_title,
            ui_state=ui_state,
            symbols=tuple(symbols),
            degraded=degraded,
            sequence_id=self._sequence,
            raw_observation=self._raw_payload(observation, degraded),
        )
        self._log_symbolic_observation(symbolic)
        return symbolic

    def build_observation_event(
        self,
        observation: Dict[str, object],
        *,
        source: str = "screen",
    ) -> ObservationEvent:
        symbolic = self.extract(observation)
        payload = symbolic.to_payload()
        payload.update(self._context_hints(symbolic))
        return ObservationEvent.from_payload(
            source=source,
            content_type="symbolic",
            payload=payload,
            timestamp=symbolic.timestamp,
        )

    def symbols_for_proposal(self, observation: SymbolicObservation) -> List[SymbolicElement]:
        return [
            symbol
            for symbol in observation.symbols
            if symbol.confidence >= self.config.proposal_confidence_threshold and not symbol.tentative
        ]

    def build_hypothesis_from_symbols(
        self,
        summary: str,
        symbols: Sequence[SymbolicElement],
        *,
        confidence: float,
    ) -> Hypothesis:
        evidence = {
            "symbols": [symbol.to_dict() for symbol in symbols],
            "symbol_confidence": [symbol.confidence for symbol in symbols],
        }
        return Hypothesis(hypothesis=summary, confidence=confidence, evidence=evidence)

    def _build_symbols(self, app: Optional[str], elements: Iterable[object]) -> List[SymbolicElement]:
        symbols: List[SymbolicElement] = []
        for raw in elements:
            if not isinstance(raw, dict):
                continue
            element_type = self._string_or_none(raw.get("element_type"))
            if not element_type:
                continue
            label = self._string_or_none(raw.get("label"))
            state = self._string_or_none(raw.get("state"))
            confidence = self._coerce_confidence(raw.get("confidence"))
            if confidence is None:
                confidence = 0.5
            tentative = confidence < self.config.min_confidence
            metadata = raw.get("metadata")
            symbols.append(
                SymbolicElement(
                    app=app,
                    element_type=element_type,
                    label=label,
                    state=state,
                    confidence=confidence,
                    tentative=tentative,
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        return symbols

    def _infer_ui_state(
        self,
        text: Optional[str],
        symbols: Sequence[SymbolicElement],
    ) -> Optional[str]:
        for symbol in symbols:
            if symbol.state in {"loading", "error", "modal", "fullscreen", "idle"}:
                return symbol.state
        if not text:
            return None
        lowered = text.lower()
        if "loading" in lowered or "please wait" in lowered:
            return "loading"
        if "error" in lowered or "failed" in lowered:
            return "error"
        if "sign in" in lowered or "log in" in lowered:
            return "modal"
        return None

    def _context_hints(self, observation: SymbolicObservation) -> Dict[str, object]:
        hints: Dict[str, object] = {}
        if observation.app:
            hints["activity"] = observation.app
        if observation.ui_state:
            hints["environment"] = {"ui_state": observation.ui_state}
        if observation.ui_state in {"loading", "error"}:
            hints["friction_signal"] = {
                "type": observation.ui_state,
                "confidence": self._max_confidence(observation.symbols),
                "source": "ssu",
            }
        return hints

    def _log_symbolic_observation(self, observation: SymbolicObservation) -> None:
        entry = {
            "timestamp": observation.timestamp,
            "kind": "symbolic_observation",
            "non_authoritative": True,
            "non_executing": True,
            "payload": observation.to_payload(),
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _raw_payload(self, observation: Dict[str, object], degraded: bool) -> Dict[str, object]:
        if not degraded:
            return {}
        raw = {"text": observation.get("text"), "app": observation.get("app"), "window_title": observation.get("window_title")}
        return {key: value for key, value in raw.items() if value is not None}

    def _max_confidence(self, symbols: Sequence[SymbolicElement]) -> float:
        if not symbols:
            return 0.0
        return max(symbol.confidence for symbol in symbols)

    def _coerce_confidence(self, value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return None

    def _string_or_none(self, value: object) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _list_or_empty(self, value: object) -> List[object]:
        if isinstance(value, list):
            return value
        return []


__all__ = ["SSUConfig", "SymbolicElement", "SymbolicObservation", "SymbolicScreenUnderstanding"]
