from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from avatar_state import AvatarStateEmitter

DEFAULT_BASE_STATE: Dict[str, Any] = {
    "mood": "calm",
    "intensity": 0.0,
    "expression": "rest",
    "motion": "idle",
}

DEFAULT_VISEME_DURATION = 0.12

VisemeTimeline = List[Dict[str, Any]]


def _load_viseme_source(source: Any) -> Mapping[str, Any] | Sequence[Mapping[str, Any]]:
    if source is None:
        return []
    if isinstance(source, (str, Path)):
        try:
            text = Path(source).read_text(encoding="utf-8")
            return json.loads(text)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    return source if isinstance(source, (Mapping, Sequence)) else []


def _coerce_viseme_timeline(source: Any) -> VisemeTimeline:
    data = _load_viseme_source(source)
    raw_cues: Iterable[Mapping[str, Any]]
    if isinstance(data, Mapping) and "mouthCues" in data:
        raw_cues = [cue for cue in data.get("mouthCues", []) if isinstance(cue, Mapping)]
    elif isinstance(data, Mapping) and "visemes" in data:
        raw_cues = [cue for cue in data.get("visemes", []) if isinstance(cue, Mapping)]
    elif isinstance(data, Sequence):
        raw_cues = [cue for cue in data if isinstance(cue, Mapping)]
    else:
        raw_cues = []

    timeline: VisemeTimeline = []
    for cue in raw_cues:
        start = float(cue.get("start", cue.get("time", 0.0)) or 0.0)
        end = cue.get("end")
        duration = float(end) - start if end is not None else float(cue.get("duration", DEFAULT_VISEME_DURATION))
        if duration <= 0:
            duration = DEFAULT_VISEME_DURATION
        viseme_value = str(cue.get("viseme", cue.get("value", cue.get("mouth", "")))) or "neutral"
        if start < 0:
            start = 0.0
        timeline.append({
            "time": start,
            "duration": duration,
            "viseme": viseme_value,
        })

    return sorted(timeline, key=lambda cue: cue["time"])


@dataclass
class SpeechEmitter:
    avatar_state_emitter: AvatarStateEmitter
    base_state: MutableMapping[str, Any] = field(default_factory=lambda: dict(DEFAULT_BASE_STATE))

    def emit_phrase(self, phrase: str, *, visemes: Any | None = None) -> Dict[str, Any]:
        spoken = phrase.strip()
        timeline = _coerce_viseme_timeline(visemes)
        payload: Dict[str, Any] = {
            **DEFAULT_BASE_STATE,
            **dict(self.base_state),
            "current_phrase": spoken,
            "is_speaking": bool(spoken),
            "viseme_timeline": timeline,
            "viseme_events": timeline,
        }
        return self.avatar_state_emitter.emit(payload)

    def emit_idle(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            **DEFAULT_BASE_STATE,
            **dict(self.base_state),
            "current_phrase": "",
            "is_speaking": False,
            "viseme_timeline": [],
            "viseme_events": [],
        }
        return self.avatar_state_emitter.emit(payload)

    def emit_from_tts(self, speech: Mapping[str, Any]) -> Dict[str, Any]:
        phrase = str(speech.get("text", speech.get("utterance", "")))
        viseme_source = speech.get("visemes") or speech.get("viseme_path") or speech.get("viseme_json")
        return self.emit_phrase(phrase, visemes=viseme_source)


__all__ = ["SpeechEmitter", "DEFAULT_VISEME_DURATION"]
