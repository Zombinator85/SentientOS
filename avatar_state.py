from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from runtime_mode import SENTIENTOS_MODE
from sentientos.storage import get_state_file

__all__ = ["AvatarState", "AvatarStateEmitter", "resolve_mode"]


@dataclass
class AvatarState:
    mood: str
    intensity: float
    expression: str
    motion: str
    current_phrase: Optional[str] = None
    is_speaking: bool = False
    viseme_timeline: Optional[Mapping[str, Any] | list[Mapping[str, Any]]] = None
    metadata: Optional[Mapping[str, Any]] = None

    def to_payload(self, mode: Optional[str] = None) -> Dict[str, Any]:
        mode_value = resolve_mode(mode)
        normalized_intensity = max(0.0, min(1.0, float(self.intensity)))
        timeline: list[Dict[str, Any]] = []
        if self.viseme_timeline:
            for entry in self.viseme_timeline if isinstance(self.viseme_timeline, list) else [self.viseme_timeline]:
                if isinstance(entry, Mapping):
                    timeline.append({
                        "time": float(entry.get("time", 0.0)),
                        "duration": float(entry.get("duration", 0.0)),
                        "viseme": str(entry.get("viseme", entry.get("value", ""))),
                    })

        payload: Dict[str, Any] = {
            "mode": mode_value,
            "local_owner": mode_value == "LOCAL_OWNER",
            "mood": self.mood,
            "intensity": normalized_intensity,
            "expression": self.expression,
            "motion": self.motion,
            "current_phrase": self.current_phrase or "",
            "is_speaking": bool(self.is_speaking),
            "viseme_timeline": timeline,
            "viseme_events": timeline,
            "timestamp": time.time(),
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def resolve_mode(mode: Optional[str] = None) -> str:
    """Resolve the current runtime mode for avatar emission."""

    return mode or os.getenv("SENTIENTOS_MODE", SENTIENTOS_MODE)


class AvatarStateEmitter:
    """Write avatar state to a JSON file for downstream renderers."""

    def __init__(self, target_path: Optional[Path] = None):
        self.target_path = Path(target_path) if target_path else get_state_file("avatar_state.json")

    def emit(self, state: AvatarState | Mapping[str, Any]) -> Dict[str, Any]:
        payload = self._prepare_payload(state)
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        with self.target_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        return payload

    def _prepare_payload(self, state: AvatarState | Mapping[str, Any]) -> Dict[str, Any]:
        if isinstance(state, AvatarState):
            return state.to_payload()

        required = {"mood", "intensity", "expression", "motion"}
        missing = required - set(state.keys())
        if missing:
            missing_csv = ", ".join(sorted(missing))
            raise ValueError(f"avatar state missing required keys: {missing_csv}")

        metadata = state.get("metadata") if isinstance(state, Mapping) else None
        visemes = None
        if isinstance(state, Mapping):
            visemes = state.get("viseme_timeline") or state.get("viseme_events")
        avatar_state = AvatarState(
            mood=str(state["mood"]),
            intensity=float(state["intensity"]),
            expression=str(state["expression"]),
            motion=str(state["motion"]),
            current_phrase=str(state.get("current_phrase", "")) if isinstance(state, Mapping) else "",
            is_speaking=bool(state.get("is_speaking", False)) if isinstance(state, Mapping) else False,
            viseme_timeline=visemes,
            metadata=metadata if isinstance(metadata, Mapping) else None,
        )
        return avatar_state.to_payload()
