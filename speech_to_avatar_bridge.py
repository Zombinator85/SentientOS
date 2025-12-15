"""Bridge speech synthesis events into avatar state updates and TTS playback."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

from avatar_state import AvatarStateEmitter, resolve_mode
from speech_emitter import DEFAULT_BASE_STATE, SpeechEmitter, _coerce_viseme_timeline
from speech_log import append_speech_log, build_speech_log_entry
from utils import is_headless


class TtsAudioPlayer:
    """Lightweight wrapper for pyttsx3 or edge-tts playback."""

    def __init__(self, engine_type: Optional[str] = None):
        self.engine_type = (engine_type or os.getenv("TTS_ENGINE", "pyttsx3")).lower()
        self.headless = is_headless()
        self.engine: Any = None
        self._communicate_cls: Any = None
        if self.headless:
            return

        if self.engine_type == "edge-tts":
            import importlib.util

            if importlib.util.find_spec("edge_tts") is not None:
                from edge_tts import Communicate as EdgeCommunicate  # type: ignore[import-untyped]

                self._communicate_cls = EdgeCommunicate
        elif self.engine_type == "pyttsx3":
            import importlib.util

            if importlib.util.find_spec("pyttsx3") is not None:
                import pyttsx3

                self.engine = pyttsx3.init()

    def is_available(self) -> bool:
        return not self.headless and (self.engine is not None or self._communicate_cls is not None)

    def play(self, phrase: str, *, voice: Optional[str] = None) -> bool:
        """Play ``phrase`` using the detected TTS backend."""

        spoken = phrase.strip()
        if not spoken or not self.is_available():
            return False

        if self.engine_type == "edge-tts" and self._communicate_cls is not None:

            async def _edge_run() -> None:
                comm = self._communicate_cls(text=spoken, voice=voice)
                target = Path(tempfile.gettempdir()) / "sentientos-edge-preview.mp3"
                await comm.save(str(target))

            asyncio.run(_edge_run())
            return True

        if self.engine_type == "pyttsx3" and self.engine is not None:
            if voice:
                try:
                    self.engine.setProperty("voice", voice)
                except Exception:
                    pass
            self.engine.say(spoken)
            self.engine.runAndWait()
            return True

        return False


@dataclass
class SpeechToAvatarBridge:
    """Route speech events (including muted runs) into avatar_state.json."""

    speech_emitter: SpeechEmitter = field(
        default_factory=lambda: SpeechEmitter(AvatarStateEmitter(), base_state=dict(DEFAULT_BASE_STATE))
    )
    tts_player: Optional[TtsAudioPlayer] = field(default_factory=TtsAudioPlayer)
    mute_local_owner: bool = True
    log_path: Optional[Path] = None
    max_log_entries: int = 200
    forward_avatar: bool = True
    _last_started_at: Optional[float] = None
    _last_phrase: str = ""
    _last_viseme_count: int = 0

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
        muted_value = self._should_mute(muted, mode)
        if not self.forward_avatar:
            timeline = _coerce_viseme_timeline(visemes)
            speaking = bool(phrase.strip()) and not muted_value
            phrase_block: MutableMapping[str, Any] = {
                "text": phrase,
                "started_at": started_value,
                "muted": muted_value,
                "speaking": speaking,
                "viseme_count": len(timeline),
            }
            payload: MutableMapping[str, Any] = {
                **DEFAULT_BASE_STATE,
                **dict(self.speech_emitter.base_state),
                "mode": resolve_mode(mode),
                "current_phrase": phrase,
                "phrase_started_at": started_value,
                "phrase": phrase_block,
                "viseme_timeline": timeline,
                "viseme_events": timeline,
                "speaking": speaking,
                "is_speaking": speaking,
                "muted": muted_value,
            }
            if metadata:
                payload["metadata"] = dict(metadata)
        else:
            payload = self.speech_emitter.emit_phrase(
                phrase,
                visemes=visemes,
                started_at=started_value,
                muted=muted_value,
                metadata=metadata,
            )
        phrase_block = payload.get("phrase") if isinstance(payload, Mapping) else {}
        if isinstance(phrase_block, Mapping):
            self._last_phrase = str(phrase_block.get("text", phrase))
            self._last_viseme_count = int(phrase_block.get("viseme_count", 0) or 0)
        else:
            self._last_phrase = phrase
            self._last_viseme_count = len(payload.get("viseme_timeline", [])) if isinstance(payload, Mapping) else 0

        self._log_speech(payload, event="start")
        return payload

    def emit_idle(self, *, log: bool = True) -> MutableMapping[str, Any]:
        self._last_started_at = None
        payload = self.speech_emitter.emit_idle()
        if log:
            self._log_speech(payload, event="stop")
        return payload

    def _log_speech(
        self,
        payload: Mapping[str, Any],
        *,
        event: str,
        phrase_text: Optional[str] = None,
        started_at: Optional[float] = None,
        viseme_count: Optional[int] = None,
    ) -> None:
        mode = resolve_mode(payload.get("mode") if isinstance(payload, Mapping) else None)
        phrase_block = payload.get("phrase") if isinstance(payload, Mapping) else {}
        phrase = phrase_text or (phrase_block.get("text") if isinstance(phrase_block, Mapping) else payload.get("current_phrase", ""))
        start_value = started_at
        if start_value is None and isinstance(phrase_block, Mapping):
            start_value = phrase_block.get("started_at")  # type: ignore[assignment]
        timeline = payload.get("viseme_timeline") if isinstance(payload, Mapping) else []
        viseme_total = viseme_count if viseme_count is not None else 0
        if viseme_total == 0:
            if isinstance(phrase_block, Mapping):
                viseme_total = int(phrase_block.get("viseme_count", 0) or 0)
            if not viseme_total and isinstance(timeline, list):
                viseme_total = len(timeline)
        if start_value is None and self._last_started_at:
            start_value = self._last_started_at
        duration = 0.0
        if start_value is not None:
            try:
                duration = max(0.0, time.time() - float(start_value))
            except Exception:
                duration = 0.0
        speaking = bool(payload.get("speaking", payload.get("is_speaking", False))) if isinstance(payload, Mapping) else False
        muted = False
        if isinstance(phrase_block, Mapping):
            muted = bool(phrase_block.get("muted", payload.get("muted", False)))
        elif isinstance(payload, Mapping):
            muted = bool(payload.get("muted", False))

        entry = build_speech_log_entry(
            text=str(phrase or ""),
            viseme_count=viseme_total,
            duration=duration,
            speaking=speaking,
            muted=muted,
            started_at=start_value if isinstance(start_value, (int, float)) else None,
            mode=mode,
            event=event,
        )
        log_target = Path(self.log_path) if self.log_path else None
        if log_target:
            log_target.parent.mkdir(parents=True, exist_ok=True)
        append_speech_log(entry, log_path=log_target, max_entries=self.max_log_entries)

    def handle_event(self, speech_event: Mapping[str, Any]) -> MutableMapping[str, Any]:
        status = str(speech_event.get("status") or speech_event.get("event") or "start").lower()
        phrase = str(speech_event.get("text") or speech_event.get("utterance") or "")
        viseme_source = speech_event.get("visemes") or speech_event.get("viseme_path") or speech_event.get("viseme_json")
        mode = speech_event.get("mode")
        metadata = speech_event.get("metadata") if isinstance(speech_event.get("metadata"), Mapping) else None

        if status in {"stop", "done", "end", "idle"} or not phrase.strip():
            last_started = self._last_started_at
            last_phrase = phrase or self._last_phrase
            last_viseme_count = self._last_viseme_count
            payload = self.emit_idle(log=False)
            self._log_speech(
                payload,
                event="stop",
                phrase_text=last_phrase,
                started_at=last_started,
                viseme_count=last_viseme_count,
            )
            return payload

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

    def speak_text(
        self,
        phrase: str,
        *,
        visemes: Any | None = None,
        muted: Optional[bool] = None,
        mode: Optional[str] = None,
        metadata: Mapping[str, Any] | None = None,
        started_at: Any | None = None,
        voice: Optional[str] = None,
    ) -> MutableMapping[str, Any]:
        """Speak a phrase through the TTS backend while syncing avatar state."""

        started_value = self._started_at(started_at) if phrase.strip() else None
        start_payload = self.emit_phrase(
            phrase,
            visemes=visemes,
            muted=muted,
            mode=mode,
            metadata=metadata,
            started_at=started_value,
        )

        muted_value = self._should_mute(muted, mode)
        if self.tts_player and not muted_value:
            self.tts_player.play(phrase, voice=voice)

        if self.forward_avatar:
            stop_payload = self.emit_idle(log=False)
        else:
            stop_payload = dict(start_payload)
            phrase_block = stop_payload.get("phrase") if isinstance(stop_payload, Mapping) else None
            if isinstance(phrase_block, Mapping):
                stop_payload["phrase"] = {**phrase_block, "speaking": False}
            stop_payload["speaking"] = False
            stop_payload["is_speaking"] = False
        timeline = start_payload.get("viseme_timeline") if isinstance(start_payload, Mapping) else []
        self._log_speech(
            stop_payload,
            event="stop",
            phrase_text=phrase,
            started_at=started_value,
            viseme_count=len(timeline) if isinstance(timeline, list) else 0,
        )
        return start_payload


__all__ = ["SpeechToAvatarBridge", "TtsAudioPlayer"]
