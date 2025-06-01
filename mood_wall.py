import json
from pathlib import Path
from typing import Dict, List

import ledger

LOG = Path("logs/music_log.jsonl")


def load_wall(limit: int = 20) -> List[Dict[str, object]]:
    if not LOG.exists():
        return []
    lines = LOG.read_text(encoding="utf-8").splitlines()
    events: List[Dict[str, object]] = []
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("event") in ("shared", "mood_blessing"):
            mood = list((e.get("emotion") or {}).get("reported") or (e.get("emotion") or {}))
            events.append({
                "time": e.get("timestamp"),
                "event": e.get("event"),
                "user": e.get("user") or e.get("sender"),
                "peer": e.get("peer") or e.get("recipient"),
                "file": e.get("file"),
                "phrase": e.get("phrase", ""),
                "mood": mood,
            })
    return events[-limit:]


def top_moods(events: List[Dict[str, object]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for e in events:
        for m in e.get("mood", []):
            counts[m] = counts.get(m, 0) + 1
    return counts


def bless_mood(mood: str, user: str, message: str = "") -> Dict[str, str]:
    phrase = message or f"{user} blesses {mood}"
    return ledger.log_mood_blessing(user, "public", {mood: 1.0}, phrase)


def sync_wall(peer_log: Path) -> int:
    if not peer_log.exists():
        return 0
    if not LOG.exists():
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.touch()
    lines = peer_log.read_text(encoding="utf-8").splitlines()
    count = 0
    with LOG.open("a", encoding="utf-8") as f:
        for ln in lines:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            if e.get("event") in ("shared", "mood_blessing"):
                f.write(json.dumps(e) + "\n")
                count += 1
    return count
