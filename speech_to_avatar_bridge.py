"""Bridge speech synthesis events into avatar state updates."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional

from avatar_state import AvatarStateEmitter, resolve_mode
from speech_emitter import DEFAULT_BASE_STATE, SpeechEmitter


@dataclass
class SpeechToAvatarBridge:
    """Route speech events (including muted runs) into avatar_state.json."""

    speech_emitter: SpeechEmitter = field(
        default_factory=lambda: SpeechEmitter(AvatarStateEmitter(), base_state=dict(DEFAULT_BASE_STATE))
    )
    mute_local_owner: bool = True
    _last_started_at: Optional[float] = None

    def _should_mute(self, muted: Optional[bool], mode: Optional[str]) -> bool:
        if muted is not None:
            return bool(muted)
        if self.mute_local_owner and resolve_mode(mode) == "LOCAL_OWNER":
            return True
        return False

    def _started_at(self, candidate: Any) -> float:
        try:
            return float(candidate)
        except Exception:
            return time.time()

    def emit_phrase(
        self,
        phrase: str,
        *,
        visemes: Any | None = None,
        muted: Optional[bool] = None,
        mode: Optional[str] = None,
        metadata: Mapping[str, Any] | None = None,
        started_at: Any | None = None,
    ) -> MutableMapping[str, Any]:
        started_value = self._started_at(started_at) if phrase.strip() else None
        self._last_started_at = started_value
        return self.speech_emitter.emit_phrase(
            phrase,
            visemes=visemes,
            started_at=started_value,
            muted=self._should_mute(muted, mode),
            metadata=metadata,
        )

    def emit_idle(self) -> MutableMapping[str, Any]:
        self._last_started_at = None
        return self.speech_emitter.emit_idle()

    def handle_event(self, speech_event: Mapping[str, Any]) -> MutableMapping[str, Any]:
        status = str(speech_event.get("status") or speech_event.get("event") or "start").lower()
        phrase = str(speech_event.get("text") or speech_event.get("utterance") or "")
        viseme_source = speech_event.get("visemes") or speech_event.get("viseme_path") or speech_event.get("viseme_json")
        mode = speech_event.get("mode")
        metadata = speech_event.get("metadata") if isinstance(speech_event.get("metadata"), Mapping) else None

        if status in {"stop", "done", "end", "idle"} or not phrase.strip():
            return self.emit_idle()

        muted = speech_event.get("muted")
        started_at = speech_event.get("started_at", self._last_started_at)
        return self.emit_phrase(
            phrase,
            visemes=viseme_source,
            muted=muted,
            mode=mode,
            metadata=metadata,
            started_at=started_at,
        )


__all__ = ["SpeechToAvatarBridge"]
