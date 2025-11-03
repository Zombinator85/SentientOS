"""Curiosity-driven reasoning over multimodal perception events."""

from __future__ import annotations

import datetime
import time
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, TypedDict

from curiosity_goal_helper import get_global_helper
import memory_manager as mm
import reflexion_loop
from sentientos.metrics import MetricsRegistry


class ObservationSummary(TypedDict, total=False):
    summary: str
    timestamp: str
    window_start: str
    window_end: str
    transcripts: List[str]
    screen: List[str]
    objects: List[str]
    object_counts: Dict[str, int]
    novel_objects: List[str]
    emotions: Dict[str, float]
    source_events: int
    tags: List[str]
    source: str
    fragment_id: str
    novelty: float
    observation_id: str
    narrative: Dict[str, Any]
    curiosity_goal: Dict[str, Any]


class PerceptionReasoner:
    """Aggregate perception events into structured observations."""

    def __init__(
        self,
        *,
        interval_seconds: float = 10.0,
        novelty_threshold: float = 0.45,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.interval = max(float(interval_seconds), 0.5)
        self.novelty_threshold = max(0.0, float(novelty_threshold))
        self._metrics = metrics
        self._buffer: List[Dict[str, Any]] = []
        self._window_start: float | None = None
        self._last_emit: float | None = None
        self._last_summary: ObservationSummary | None = None

    def ingest(self, event: Mapping[str, Any]) -> ObservationSummary | None:
        """Ingest a raw event from ``multimodal_tracker``."""

        payload = dict(event)
        ts = self._coerce_timestamp(payload.get("timestamp"))
        payload["timestamp"] = ts
        self._buffer.append(payload)
        if self._window_start is None:
            self._window_start = ts
        if self._last_emit is None:
            self._last_emit = ts
            return None
        if ts - self._last_emit >= self.interval:
            return self._summarize(ts)
        return None

    def flush(self) -> ObservationSummary | None:
        """Force a summary with the accumulated events."""

        if not self._buffer:
            return None
        latest_ts = max(event.get("timestamp", time.time()) for event in self._buffer)
        return self._summarize(float(latest_ts))

    def current_summary(self) -> ObservationSummary | None:
        """Return the most recent observation summary."""

        return self._last_summary

    def _summarize(self, now_ts: float) -> ObservationSummary:
        events = self._buffer[:]
        self._buffer.clear()
        timestamps = [self._coerce_timestamp(evt.get("timestamp")) for evt in events]
        if self._window_start is not None:
            timestamps.append(self._window_start)
        start_ts = min(timestamps) if timestamps else now_ts
        end_ts = max(timestamps) if timestamps else now_ts
        summary = self._build_summary(events, start_ts, end_ts)
        record = mm.store_observation_summary(summary)
        self._emit_observation_metrics(record)
        sanitized = {k: v for k, v in record.items() if k != "embedding"}
        narrative = reflexion_loop.narrate_observation(sanitized, record.get("novelty", 0.0))
        sanitized["narrative"] = narrative
        curiosity_goal = None
        novelty = float(record.get("novelty", 0.0))
        helper = get_global_helper()
        curiosity_goal = helper.create_goal(
            sanitized, novelty=novelty, source="perception_reasoner"
        )
        if curiosity_goal:
            sanitized["curiosity_goal"] = curiosity_goal
            if self._metrics is not None:
                self._metrics.increment("sos_curiosity_tasks_spawned_total")
        self._last_summary = sanitized  # type: ignore[assignment]
        self._window_start = None
        self._last_emit = now_ts
        return sanitized  # type: ignore[return-value]

    def _emit_observation_metrics(self, record: Mapping[str, Any]) -> None:
        if self._metrics is None:
            return
        self._metrics.increment("sos_perception_observations_total")
        novelty = float(record.get("novelty", 0.0))
        self._metrics.set_gauge("sos_perception_novelty_ratio", novelty)

    def _build_summary(
        self,
        events: Sequence[Mapping[str, Any]],
        window_start: float,
        window_end: float,
    ) -> ObservationSummary:
        transcripts: List[str] = []
        screen_notes: List[str] = []
        scene_summaries: List[str] = []
        novel_objects: set[str] = set()
        object_counts: Counter[str] = Counter()
        emotion_totals: MutableMapping[str, float] = {}
        emotion_events = 0

        for event in events:
            transcript = event.get("voice_transcript")
            if isinstance(transcript, str) and transcript.strip():
                transcripts.append(transcript.strip())
            voice = event.get("voice")
            if isinstance(voice, Mapping):
                updated = False
                for key, value in voice.items():
                    try:
                        emotion_totals[key] = emotion_totals.get(key, 0.0) + float(value)
                        updated = True
                    except Exception:
                        continue
                if updated:
                    emotion_events += 1
            scene = event.get("scene")
            if isinstance(scene, Mapping):
                summary = scene.get("summary")
                if summary:
                    scene_summaries.append(str(summary))
                objects = scene.get("objects") or []
                if isinstance(objects, Iterable):
                    for obj in objects:
                        label: Optional[str] = None
                        if isinstance(obj, Mapping):
                            label = (
                                obj.get("label")
                                or obj.get("name")
                                or obj.get("class")
                                or obj.get("type")
                            )
                        else:
                            label = str(obj)
                        if label:
                            object_counts[str(label)] += 1
                novel = scene.get("novel") or []
                if isinstance(novel, str):
                    novel = [novel]
                if isinstance(novel, Iterable):
                    for item in novel:
                        if item:
                            novel_objects.add(str(item))
            screen = event.get("screen")
            if isinstance(screen, Mapping):
                summary = screen.get("summary") or screen.get("text")
                if summary:
                    screen_notes.append(str(summary))

        unique_transcripts = list(dict.fromkeys(transcripts))
        unique_screen = list(dict.fromkeys(screen_notes))
        emotions: Dict[str, float] = {}
        if emotion_events:
            for key, total in emotion_totals.items():
                emotions[key] = total / emotion_events

        parts: List[str] = []
        if scene_summaries:
            parts.append(f"Scene: {scene_summaries[-1]}")
        elif object_counts:
            objects_desc = ", ".join(
                f"{count} {label}" for label, count in object_counts.most_common()
            )
            parts.append(f"Objects: {objects_desc}")
        if unique_transcripts:
            sample = "; ".join(unique_transcripts[:2])
            parts.append(f"Speech: {sample}")
        if unique_screen:
            parts.append(f"Screen: {unique_screen[-1]}")
        if novel_objects:
            parts.append("Novel cues: " + ", ".join(sorted(novel_objects)))
        if emotions:
            top_emotions = sorted(emotions.items(), key=lambda item: item[1], reverse=True)[:3]
            emotion_text = ", ".join(f"{name}={value:.2f}" for name, value in top_emotions)
            parts.append(f"Emotions: {emotion_text}")
        if not parts:
            parts.append("Calm interval with no notable perception cues")

        summary: ObservationSummary = {
            "summary": " | ".join(parts),
            "timestamp": self._iso(window_end),
            "window_start": self._iso(window_start),
            "window_end": self._iso(window_end),
            "transcripts": unique_transcripts,
            "screen": unique_screen,
            "objects": sorted(object_counts.keys()),
            "object_counts": dict(object_counts),
            "novel_objects": sorted(novel_objects),
            "emotions": emotions,
            "source_events": len(events),
            "tags": ["observation", "perception"],
            "source": "perception_reasoner",
        }
        return summary

    @staticmethod
    def _iso(ts: float) -> str:
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()

    @staticmethod
    def _coerce_timestamp(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except Exception:
            return time.time()


__all__ = ["ObservationSummary", "PerceptionReasoner"]
