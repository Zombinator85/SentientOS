"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, TypedDict, cast


from logging_config import get_log_path
import ledger
from log_utils import append_json

_LEDGER_PATH: Path | None = None
_PRESENCE_LOG: Path | None = None

_LEDGER_NAME = "user_presence.jsonl"
_LEDGER_ENV = "USER_PRESENCE_LOG"
_PRESENCE_NAME = "presence_log.jsonl"
_PRESENCE_ENV = "PRESENCE_LOG"

# Bridge metadata for presence entries
BRIDGE_NAME = os.getenv("PRESENCE_BRIDGE", os.getenv("BRIDGE", "cli"))


class StatsSummary(TypedDict):
    events: Dict[str, int]
    emotions: Dict[str, float]


class RecapMusicStats(TypedDict):
    emotion_totals: Dict[str, float]
    most_shared_mood: str
    top_tracks: List[Tuple[str, int]]


class RecapVideoStats(TypedDict):
    emotion_totals: Dict[str, float]
    most_shared_mood: str
    top_videos: List[Tuple[str, int]]


class RecapData(TypedDict):
    music: RecapMusicStats
    video: RecapVideoStats
    blessings: int
    reflections: int
    milestones: List[str]


def _ensure_log_paths() -> tuple[Path, Path]:
    global _LEDGER_PATH, _PRESENCE_LOG
    if _LEDGER_PATH is None or _PRESENCE_LOG is None:
        ledger_path = get_log_path(_LEDGER_NAME, _LEDGER_ENV)
        presence_path = get_log_path(_PRESENCE_NAME, _PRESENCE_ENV)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        presence_path.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_PATH = ledger_path
        _PRESENCE_LOG = presence_path
    return _LEDGER_PATH, _PRESENCE_LOG


def log(user: str, event: str, note: str = "", bridge: str | None = None) -> None:
    """Record a general presence event."""
    ledger_path, presence_log = _ensure_log_paths()
    entry = {
        "time": datetime.utcnow().isoformat(),
        "user": user,
        "event": event,
        "note": note,
        "bridge": bridge or BRIDGE_NAME,
    }
    append_json(ledger_path, entry)
    append_json(presence_log, entry)


def log_privilege(
    user: str, platform: str, tool: str, status: str, bridge: str | None = None
) -> None:
    """Record a privilege check attempt."""
    ledger_path, presence_log = _ensure_log_paths()
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "admin_privilege_check",
        "status": status,
        "user": user,
        "platform": platform,
        "tool": tool,
        "bridge": bridge or BRIDGE_NAME,
    }
    append_json(ledger_path, entry)
    append_json(presence_log, entry)


def history(user: str, limit: int = 20) -> List[Dict[str, str]]:
    ledger_path, _ = _ensure_log_paths()
    if not ledger_path.exists():
        return []
    lines = [
        ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
        if f'"user": "{user}"' in ln
    ][-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        entry = cast(Dict[str, str], obj)
        out.append(entry)
    return out


def recent_privilege_attempts(limit: int = 5) -> List[Dict[str, str]]:
    """Return the most recent privilege check entries."""
    ledger_path, _ = _ensure_log_paths()
    if not ledger_path.exists():
        return []
    lines = reversed(ledger_path.read_text(encoding="utf-8").splitlines())
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("event") == "admin_privilege_check":
            entry = cast(Dict[str, str], obj)
            out.append(entry)
            if len(out) == limit:
                break
    return list(reversed(out))


def music_stats(limit: int = 100) -> StatsSummary:
    """Return basic stats from the music ledger."""
    music_path = get_log_path("music_log.jsonl")
    if not music_path.exists():
        return {"events": {}, "emotions": {}}
    lines = music_path.read_text(encoding="utf-8").splitlines()[-limit:]
    events: Dict[str, int] = {}
    emotions: Dict[str, float] = {}
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        info = e.get("data", e)
        evt = info.get("event")
        if evt:
            events[evt] = events.get(evt, 0) + 1
        for k in ("intended", "perceived", "reported", "received"):
            for emo, val in (info.get("emotion", {}).get(k) or {}).items():
                emotions[emo] = emotions.get(emo, 0.0) + val
    return {"events": events, "emotions": emotions}


def video_stats(limit: int = 100) -> StatsSummary:
    """Return basic stats from the video ledger."""
    video_path = get_log_path("video_log.jsonl")
    if not video_path.exists():
        return {"events": {}, "emotions": {}}
    lines = video_path.read_text(encoding="utf-8").splitlines()[-limit:]
    events: Dict[str, int] = {}
    emotions: Dict[str, float] = {}
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        info = e.get("data", e)
        evt = info.get("event")
        if evt:
            events[evt] = events.get(evt, 0) + 1
        for k in ("intended", "perceived", "reported", "received"):
            for emo, val in (info.get("emotion", {}).get(k) or {}).items():
                emotions[emo] = emotions.get(emo, 0.0) + val
    return {"events": events, "emotions": emotions}


def recap(limit: int = 20, user: str = "") -> RecapData:
    """Return music recap, blessings, and reflection milestones."""
    info_raw = ledger.music_recap(limit)
    video_raw = ledger.video_recap(limit)
    info = cast(RecapMusicStats, info_raw)
    video = cast(RecapVideoStats, video_raw)
    bless = 0
    reflections = 0
    mood_counts: Dict[str, int] = {}
    music_path = get_log_path("music_log.jsonl")
    if music_path.exists():
        for ln in music_path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            entry = e.get("data", e)
            if entry.get("event") == "mood_blessing":
                bless += 1
            if entry.get("event") == "reflection":
                reflections += 1
                for m in (entry.get("emotion", {}).get("reported") or {}):
                    mood_counts[m] = mood_counts.get(m, 0) + 1
    milestones = []
    for m, c in mood_counts.items():
        if c == 10:
            milestones.append(f"You are the 10th listener to log '{m}' this week.")
    return {
        "music": info,
        "video": video,
        "blessings": bless,
        "reflections": reflections,
        "milestones": milestones,
    }


def log_video_event(
    user: str,
    prompt: str,
    title: str,
    file_path: str,
    emotion: Dict[str, float] | None = None,
    peer: str | None = None,
) -> Dict[str, Any]:
    """Log a video creation event and presence."""
    entry = ledger.log_video_create(
        prompt,
        title,
        file_path,
        emotion or {},
        user=user,
        peer=peer,
    )
    log(user, "video_created", title)
    return entry


def log_video_watch(
    user: str,
    file_path: str,
    perceived: Dict[str, float] | None = None,
    peer: str | None = None,
    reflection: str = "",
) -> Dict[str, Any]:
    """Log a watched video with emotion reflection."""
    entry = ledger.log_video_watch(
        file_path,
        user=user,
        perceived=perceived,
        peer=peer,
    )
    log(user, "video_watched", reflection or file_path)
    return entry


def log_video_share(
    user: str,
    file_path: str,
    peer: str,
    emotion: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """Log a shared video and presence."""
    entry = ledger.log_video_share(
        file_path,
        peer=peer,
        user=user,
        emotion=emotion,
    )
    log(user, "video_shared", file_path)
    return entry


__all__ = [
    "log",
    "log_privilege",
    "history",
    "recent_privilege_attempts",
    "music_stats",
    "video_stats",
    "recap",
    "log_video_event",
    "log_video_watch",
    "log_video_share",
]
