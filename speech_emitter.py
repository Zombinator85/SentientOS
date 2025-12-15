from __future__ import annotations

import json
import json
import time
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

    def emit_phrase(
        self,
        phrase: str,
        *,
        visemes: Any | None = None,
        started_at: float | None = None,
        muted: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        spoken = phrase.strip()
        timeline = _coerce_viseme_timeline(visemes)
        started_value = started_at if started_at is not None else (time.time() if spoken else None)
        speaking = bool(spoken) and not muted
        payload: Dict[str, Any] = {
            **DEFAULT_BASE_STATE,
            **dict(self.base_state),
            "current_phrase": spoken,
            "phrase_started_at": started_value,
            "is_speaking": speaking,
            "speaking": speaking,
            "muted": bool(muted),
            "phrase": {
                "text": spoken,
                "started_at": started_value,
                "muted": bool(muted),
                "speaking": speaking,
                "viseme_count": len(timeline),
            },
            "viseme_timeline": timeline,
            "viseme_events": timeline,
        }
        if metadata:
            payload["metadata"] = dict(metadata)
        return self.avatar_state_emitter.emit(payload)

    def emit_idle(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            **DEFAULT_BASE_STATE,
            **dict(self.base_state),
            "current_phrase": "",
            "is_speaking": False,
            "speaking": False,
            "phrase_started_at": None,
            "muted": False,
            "viseme_timeline": [],
            "viseme_events": [],
            "phrase": {"text": "", "started_at": None, "muted": False, "speaking": False, "viseme_count": 0},
        }
        return self.avatar_state_emitter.emit(payload)

    def emit_from_tts(self, speech: Mapping[str, Any]) -> Dict[str, Any]:
        phrase = str(speech.get("text", speech.get("utterance", "")))
        viseme_source = speech.get("visemes") or speech.get("viseme_path") or speech.get("viseme_json")
        started_at = speech.get("started_at")
        muted = bool(speech.get("muted", False))
        metadata = speech.get("metadata") if isinstance(speech.get("metadata"), Mapping) else None
        return self.emit_phrase(phrase, visemes=viseme_source, started_at=started_at, muted=muted, metadata=metadata)


__all__ = ["SpeechEmitter", "DEFAULT_VISEME_DURATION"]
