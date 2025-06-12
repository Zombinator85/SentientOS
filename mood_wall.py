"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Utility functions for sharing and blessing community moods."""
# No privilege required for this tool.

from logging_config import get_log_path
import json
from pathlib import Path
from typing import Dict, List, Optional

import ledger
try:
    import requests  # type: ignore  # HTTP client optional
except Exception:  # pragma: no cover - optional
    requests = None  # type: ignore  # offline mode

LOG = get_log_path("music_log.jsonl")


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


def sync_wall_http(url: str) -> int:
    """Sync mood wall events from a peer HTTP endpoint."""
    if requests is None:
        raise RuntimeError("requests module not available")
    if not LOG.exists():
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.touch()
    r = requests.get(url.rstrip("/") + "/mood_wall", timeout=10)
    r.raise_for_status()
    data = r.json()
    count = 0
    with LOG.open("a", encoding="utf-8") as f:
        for e in data:
            if e.get("event") in ("shared", "mood_blessing"):
                f.write(json.dumps(e) + "\n")
                count += 1
    return count


def peers_from_federation() -> List[str]:
    """Return unique federation peers from the ledger."""
    path = get_log_path("federation_log.jsonl")
    if not path.exists():
        return []
    peers: List[str] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            p = json.loads(ln).get("peer")
        except Exception:
            continue
        if p and p not in peers:
            peers.append(p)
    return peers


def latest_blessing_for(mood: str) -> Optional[Dict[str, object]]:
    """Return the most recent mood blessing for a given mood."""
    if not LOG.exists():
        return None
    lines = reversed(LOG.read_text(encoding="utf-8").splitlines())
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("event") == "mood_blessing" and mood in (e.get("emotion") or {}):
            return e
    return None
