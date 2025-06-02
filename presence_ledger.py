import json
import os
from datetime import datetime
from typing import Dict, List

from logging_config import get_log_path

import ledger

LEDGER_PATH = get_log_path("user_presence.jsonl", "USER_PRESENCE_LOG")
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def log(user: str, event: str, note: str = "") -> None:
    """Record a general presence event."""
    entry = {
        "time": datetime.utcnow().isoformat(),
        "user": user,
        "event": event,
        "note": note,
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def log_privilege(
    user: str, platform: str, tool: str, status: str
) -> None:
    """Record a privilege check attempt."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "admin_privilege_check",
        "status": status,
        "user": user,
        "platform": platform,
        "tool": tool,
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def history(user: str, limit: int = 20) -> List[Dict[str, str]]:
    if not LEDGER_PATH.exists():
        return []
    lines = [
        ln for ln in LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        if f'"user": "{user}"' in ln
    ][-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def recent_privilege_attempts(limit: int = 5) -> List[Dict[str, str]]:
    """Return the most recent privilege check entries."""
    if not LEDGER_PATH.exists():
        return []
    lines = reversed(LEDGER_PATH.read_text(encoding="utf-8").splitlines())
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            entry = json.loads(ln)
        except Exception:
            continue
        if entry.get("event") == "admin_privilege_check":
            out.append(entry)
            if len(out) == limit:
                break
    return list(reversed(out))


def music_stats(limit: int = 100) -> Dict[str, Dict[str, float]]:
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
        evt = e.get("event")
        if evt:
            events[evt] = events.get(evt, 0) + 1
        for k in ("intended", "perceived", "reported", "received"):
            for emo, val in (e.get("emotion", {}).get(k) or {}).items():
                emotions[emo] = emotions.get(emo, 0.0) + val
    return {"events": events, "emotions": emotions}


def video_stats(limit: int = 100) -> Dict[str, Dict[str, float]]:
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
        evt = e.get("event")
        if evt:
            events[evt] = events.get(evt, 0) + 1
        for k in ("intended", "perceived", "reported", "received"):
            for emo, val in (e.get("emotion", {}).get(k) or {}).items():
                emotions[emo] = emotions.get(emo, 0.0) + val
    return {"events": events, "emotions": emotions}


def recap(limit: int = 20, user: str = "") -> Dict[str, object]:
    """Return music recap, blessings, and reflection milestones."""
    info = ledger.music_recap(limit)
    video = ledger.video_recap(limit)
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
            if e.get("event") == "mood_blessing":
                bless += 1
            if e.get("event") == "reflection":
                reflections += 1
                for m in (e.get("emotion", {}).get("reported") or {}):
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
) -> Dict[str, str]:
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
) -> Dict[str, str]:
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
) -> Dict[str, str]:
    """Log a shared video and presence."""
    entry = ledger.log_video_share(
        file_path,
        peer=peer,
        user=user,
        emotion=emotion,
    )
    log(user, "video_shared", file_path)
    return entry

