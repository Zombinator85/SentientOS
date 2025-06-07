from __future__ import annotations

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Narrator CLI and library for daily summaries.

Usage:
    python narrator.py [--date YYYY-MM-DD] [--log-dir DIR] [--speak] [--voice VOICE] [--dry-run]

This module loads memory and reflection logs for a given day, infers the
system mood from emotion vectors and assembles a prompt for a local
summarisation model. The summary can optionally be spoken through the
configured TTS engine (see ``tts_bridge``).

Dependencies are optional and loaded lazily. ``transformers`` is used for
the summarisation pipeline when available. ``tts_bridge`` handles speech
synthesis with Coqui TTS, pyttsx3 or other engines. Set
``SENTIENTOS_HEADLESS=1`` to disable audio output in tests or headless
systems.
"""

import argparse
import datetime as _dt
import json
import os
from pathlib import Path
from logging_config import get_log_path
from typing import Any, Dict, List, Callable, Optional

pipeline: Optional[Callable[..., Any]]
try:  # summarisation backend
    from transformers import pipeline as hf_pipeline
    pipeline = hf_pipeline
except Exception:  # pragma: no cover - optional dependency
    pipeline = None

tts_bridge: Any
try:
    import tts_bridge as tts_mod  # handles multiple TTS engines
    tts_bridge = tts_mod
except Exception:  # pragma: no cover - optional
    tts_bridge = None

DEFAULT_LOG_DIR = get_log_path("")
MEMORY_LOG = "memory.jsonl"
REFLECTION_LOG = "reflection.jsonl"
EMOTION_LOG = "emotions.jsonl"


# ---------------------------------------------------------------------------
# Loading utilities
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries


def _filter_date(entries: List[Dict[str, Any]], day: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in entries:
        ts = e.get("timestamp", "")
        if str(ts).startswith(day):
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# Mood and prompt assembly
# ---------------------------------------------------------------------------

def infer_mood(entries: List[Dict[str, Any]]) -> str:
    """Infer overall mood from emotion vectors."""
    scores: Dict[str, float] = {}
    for e in entries:
        emo = e.get("emotions", {})
        if not isinstance(emo, dict):
            continue
        if not emo:
            continue
        lab = max(emo, key=lambda k: float(emo.get(k, 0)))
        scores[lab] = scores.get(lab, 0.0) + float(emo.get(lab, 0.0))
    if not scores:
        return "neutral"
    mood = max(scores, key=lambda k: scores.get(k, 0))
    return mood.lower()


def assemble_prompt(day: str, mood: str, events: List[Dict[str, Any]], reflections: List[Dict[str, Any]]) -> str:
    lines = [
        f"System mood: {mood}",
        f"Narration style: {mood}",
        "Events:",
    ]
    for e in events:
        ts = e.get("timestamp", "?")
        txt = str(e.get("text", "")).strip().replace("\n", " ")
        lines.append(f"- {ts} {txt}")
    if reflections:
        lines.append("Reflections:")
        for r in reflections:
            ts = r.get("timestamp", "?")
            txt = str(r.get("text", "")).strip().replace("\n", " ")
            lines.append(f"- {ts} {txt}")
    lines.append("Please summarize today\u2019s system experience in a human-like, emotionally aware story.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------

def generate_narrative(prompt: str, dry_run: bool = False) -> str:
    if dry_run or pipeline is None:
        return prompt
    model = os.getenv("NARRATOR_MODEL", "facebook/bart-large-cnn")
    summarizer = pipeline("summarization", model=model)
    try:
        result = summarizer(prompt, max_length=180, min_length=80, do_sample=False)
        if result:
            return result[0].get("summary_text", "")
    except Exception:
        pass
    return prompt


def speak(text: str, voice: str | None = None, emotions: Dict[str, float] | None = None) -> None:
    if tts_bridge is None:
        return
    try:
        tts_bridge.speak(text, voice=voice, emotions=emotions)
    except Exception:  # pragma: no cover - audio failures
        pass


# ---------------------------------------------------------------------------
# High level run helpers
# ---------------------------------------------------------------------------

def summarize_day(date: str, log_dir: Path = DEFAULT_LOG_DIR, speak_out: bool = False, voice: str | None = None, dry_run: bool = False) -> str:
    mem_entries = _load_jsonl(log_dir / MEMORY_LOG)
    refl_entries = _load_jsonl(log_dir / REFLECTION_LOG)
    emo_entries = _load_jsonl(log_dir / EMOTION_LOG)

    mem_today = _filter_date(mem_entries, date)
    refl_today = _filter_date(refl_entries, date)
    emo_today = _filter_date(emo_entries, date)

    all_for_mood = mem_today + emo_today
    mood = infer_mood(all_for_mood)

    prompt = assemble_prompt(date, mood, mem_today, refl_today)
    narrative = generate_narrative(prompt, dry_run=dry_run)
    if speak_out and not dry_run:
        speak(narrative, voice=voice, emotions={mood: 1.0})
    return narrative


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate daily narrative from logs")
    parser.add_argument("--date", default=_dt.date.today().isoformat(), help="Date YYYY-MM-DD")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--speak", action="store_true", help="Speak the narrative")
    parser.add_argument("--voice")
    parser.add_argument("--dry-run", action="store_true", help="Skip model inference")
    args = parser.parse_args(argv)

    narrative = summarize_day(
        args.date,
        log_dir=Path(args.log_dir),
        speak_out=args.speak,
        voice=args.voice,
        dry_run=args.dry_run,
    )
    print(narrative)


if __name__ == "__main__":
    main()
