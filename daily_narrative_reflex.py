"""Daily narrative reflex daemon."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Mapping, Optional, Sequence

import memory_manager

from sentientos.embodiment.embodiment_digest import get_recent_embodiment_digest

try:  # pragma: no cover - optional TTS bridge
    import tts_bridge
except Exception:  # pragma: no cover
    tts_bridge = None  # type: ignore

from epu import MOOD_LOG

DIGEST_DIR = Path("glow/digests")
DIGEST_DIR.mkdir(parents=True, exist_ok=True)
DAILY_DIGEST_DIR = memory_manager.DIGEST_DIR / "daily"
DAILY_DIGEST_DIR.mkdir(parents=True, exist_ok=True)


def _load_jsonl(path: Path, *, since: datetime | None = None, limit: int = 100) -> List[Mapping[str, object]]:
    if not path.exists():
        return []
    entries: List[Mapping[str, object]] = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()[-limit:]):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if since is not None:
            ts = payload.get("timestamp") or payload.get("ts")
            if not ts:
                continue
            try:
                instant = datetime.fromisoformat(str(ts))
            except Exception:
                continue
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
            if instant < since:
                continue
        entries.append(payload)
    entries.reverse()
    return entries


@dataclass
class NarrativeContext:
    perception: List[Mapping[str, object]]
    curiosity: List[Mapping[str, object]]
    conversations: List[Mapping[str, object]]
    mood_arc: List[Mapping[str, object]]
    highlights: List[Mapping[str, object]]
    embodiment_activity: List[Mapping[str, object]]


class DailyNarrativeReflex:
    def __init__(
        self,
        *,
        llm: Callable[[NarrativeContext], str] | None = None,
        speak: Callable[[str], None] | None = None,
    ) -> None:
        self._llm = llm or self._fallback_llm
        self._speaker = speak or self._default_speaker

    def run(self, *, day: date | None = None, speak: bool = False) -> Path:
        today = day or datetime.now(timezone.utc).date()
        context = self._gather_context(today)
        story = self._llm(context)
        digest_path = self._write_digest(today, story, context)
        embodiment_path = self._write_embodiment_digest(today, context.embodiment_activity)
        self._persist_memory(story, today)
        self._persist_embodiment_digest(today, embodiment_path)
        if speak:
            self._speaker(story)
        return digest_path

    def read_latest(self, *, speak: bool = False) -> Optional[str]:
        digests = sorted(DIGEST_DIR.glob("*.md"))
        if not digests:
            return None
        latest = digests[-1]
        content = latest.read_text(encoding="utf-8")
        if speak:
            self._speaker(content)
        return content

    def _gather_context(self, day: date) -> NarrativeContext:
        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) - timedelta(hours=24)
        perception = _load_jsonl(memory_manager.OBSERVATION_LOG_PATH, since=start, limit=200)
        curiosity = _load_jsonl(memory_manager.CURIOSITY_REFLECTIONS_PATH, since=start, limit=100)
        conversations = _load_jsonl(memory_manager.TRANSCRIPT_LOG_PATH, since=start, limit=100)
        mood_arc = _load_jsonl(Path(MOOD_LOG), since=start, limit=200)
        highlights = memory_manager.search_by_tags(["highlight"], limit=5)
        embodiment_activity = self._summarize_embodiment_activity(day)
        return NarrativeContext(
            perception=perception,
            curiosity=curiosity,
            conversations=conversations,
            mood_arc=mood_arc,
            highlights=highlights,
            embodiment_activity=embodiment_activity,
        )

    def _write_digest(self, day: date, story: str, context: NarrativeContext) -> Path:
        digest_path = DIGEST_DIR / f"{day.isoformat()}.md"
        sections = [
            f"# Daily Narrative — {day.isoformat()}",
            story.strip(),
            "\n## Highlights",
        ]
        for idx, highlight in enumerate(context.highlights, start=1):
            text = highlight.get("text") or highlight.get("snippet") or ""
            sections.append(f"- ({idx}) {text}")
        digest_path.write_text("\n".join(sections) + "\n", encoding="utf-8")
        return digest_path

    def _persist_memory(self, story: str, day: date) -> None:
        memory_manager.append_memory(
            story,
            tags=["daily_digest"],
            source="daily_narrative",
            meta={"date": day.isoformat()},
        )

    def _persist_embodiment_digest(self, day: date, digest_path: Path) -> None:
        serialized = digest_path.read_text(encoding="utf-8")
        memory_manager.append_memory(
            serialized,
            tags=["narrator_daily_digest"],
            source="narrator_daily_digest",
            meta={"date": day.isoformat(), "path": digest_path.as_posix()},
        )

    def _summarize_embodiment_activity(self, day: date) -> List[Mapping[str, object]]:
        window_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        window_end = window_start + timedelta(days=1)
        entries = get_recent_embodiment_digest(n=math.inf)
        filtered = []
        for entry in entries:
            ts = self._parse_digest_timestamp(entry.get("timestamp"))
            if ts is None:
                continue
            if ts < window_start or ts >= window_end:
                continue
            filtered.append((ts, entry))
        aggregates: dict[str, dict[str, object]] = {}
        for ts, entry in filtered:
            plugin = entry.get("plugin")
            if not isinstance(plugin, str) or not plugin.strip():
                continue
            posture = entry.get("posture")
            posture_value = posture if isinstance(posture, str) else None
            capabilities = entry.get("declared_capability") or []
            capability_values = [
                cap for cap in capabilities if isinstance(cap, str) and cap.strip()
            ]
            slot = aggregates.get(plugin)
            if slot is None:
                slot = {
                    "plugin": plugin,
                    "count": 0,
                    "capabilities": set(),
                    "postures": set(),
                    "first_seen": ts,
                    "last_seen": ts,
                    "source": "embodiment_digest",
                }
                aggregates[plugin] = slot
            slot["count"] = int(slot["count"]) + 1
            for cap in capability_values:
                slot["capabilities"].add(cap)
            if posture_value:
                slot["postures"].add(posture_value)
            if ts < slot["first_seen"]:
                slot["first_seen"] = ts
            if ts > slot["last_seen"]:
                slot["last_seen"] = ts
        summaries: List[Mapping[str, object]] = []
        for plugin in sorted(aggregates.keys()):
            slot = aggregates[plugin]
            summaries.append(
                {
                    "plugin": slot["plugin"],
                    "count": slot["count"],
                    "capabilities": sorted(slot["capabilities"]),
                    "postures": sorted(slot["postures"]),
                    "first_seen": self._format_time(slot["first_seen"]),
                    "last_seen": self._format_time(slot["last_seen"]),
                    "source": slot["source"],
                }
            )
        return summaries

    @staticmethod
    def _parse_digest_timestamp(value: object) -> datetime | None:
        if not value:
            return None
        try:
            instant = datetime.fromisoformat(str(value))
        except Exception:
            return None
        if instant.tzinfo is None:
            return instant.replace(tzinfo=timezone.utc)
        return instant

    @staticmethod
    def _format_time(instant: datetime) -> str:
        return instant.astimezone(timezone.utc).strftime("%H:%M")

    def _build_embodiment_payload(
        self, day: date, entries: Sequence[Mapping[str, object]]
    ) -> dict[str, object]:
        return {
            "date": day.isoformat(),
            "embodiment_activity": list(entries),
            "source": "embodiment_digest",
        }

    def _embodiment_digest_path(self, day: date) -> Path:
        return DAILY_DIGEST_DIR / f"{day.isoformat()}-with-embodiment.json"

    def _write_embodiment_digest(self, day: date, entries: Sequence[Mapping[str, object]]) -> Path:
        payload = self._build_embodiment_payload(day, entries)
        digest_path = self._embodiment_digest_path(day)
        digest_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return digest_path

    def _fallback_llm(self, context: NarrativeContext) -> str:
        lines: List[str] = []
        if context.perception:
            lines.append(f"Observed {len(context.perception)} perception events driving curiosity.")
        if context.curiosity:
            lines.append(f"Curiosity surfaced {len(context.curiosity)} fragments of insight.")
        if context.conversations:
            lines.append(f"Held {len(context.conversations)} conversations that shaped reflection.")
        if context.mood_arc:
            moods = [entry.get("mood") for entry in context.mood_arc[-3:]]
            lines.append(f"Mood trended through {', '.join(str(m) for m in moods if m)}.")
        if context.highlights:
            lines.append("Highlights: " + "; ".join(str(h.get("text", "")) for h in context.highlights))
        if not lines:
            lines.append("A calm day without significant logged activity.")
        return "\n".join(lines)

    def _default_speaker(self, text: str) -> None:
        if not tts_bridge:
            return
        try:  # pragma: no cover - optional audio
            tts_bridge.speak(text, emotions={"calm": 1.0})
        except Exception:
            pass


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Generate daily narrative digests")
    parser.add_argument("--read", action="store_true", help="Read the most recent digest aloud")
    parser.add_argument("--speak", action="store_true", help="Speak the generated digest")
    args = parser.parse_args()
    reflex = DailyNarrativeReflex()
    if args.read:
        content = reflex.read_latest(speak=args.speak)
        if content:
            print(content)
        else:
            print("no digest available")
        return
    path = reflex.run(speak=args.speak)
    print(f"digest written → {path}")


if __name__ == "__main__":
    _cli()
