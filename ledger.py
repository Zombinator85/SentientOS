from logging_config import get_log_path
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import doctrine


def _append(path: Path, entry: Dict[str, Any]) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def log_support(
    name: str, message: str, amount: str = ""
) -> Dict[str, str]:
    """Record a supporter blessing in the living ledger."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "supporter": name,
        "message": message,
        "amount": amount,
        "ritual": "Sanctuary blessing acknowledged and remembered.",
    }
    return _append(get_log_path("support_log.jsonl"), entry)

# Backwards compatibility
log_supporter = log_support


def log_federation(peer: str, email: str = "", message: str = "Federation sync") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "peer": peer,
        "email": email,
        "message": message,
        "ritual": "Federation blessing recorded.",
    }
    return _append(get_log_path("federation_log.jsonl"), entry)


def log_music_event(
    event: str,
    file_path: str,
    prompt: str = "",
    intended: Dict[str, float] | None = None,
    perceived: Dict[str, float] | None = None,
    reported: Dict[str, float] | None = None,
    received: Dict[str, float] | None = None,
    peer: str | None = None,
    result_hash: str = "",
    user: str = "",
) -> Dict[str, Any]:
    """Record a music generation or listen event in the living ledger."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "prompt": prompt,
        "file": file_path,
        "hash": result_hash,
        "user": user,
        "emotion": {
            "intended": intended or {},
            "perceived": perceived or {},
            "reported": reported or {},
            "received": received or {},
        },
        "peer": peer or "",
        "ritual": "Music generation remembered." if event == "generated" else "Music listen remembered.",
    }
    return _append(get_log_path("music_log.jsonl"), entry)


def log_music(
    prompt: str,
    emotion: Dict[str, float],
    file_path: str,
    result_hash: str,
    user: str = "",
    peer: str | None = None,
) -> Dict[str, Any]:
    """Record a generated music track in the living ledger."""
    return log_music_event(
        "generated",
        file_path,
        prompt=prompt,
        intended=emotion,
        result_hash=result_hash,
        user=user,
        peer=peer,
    )


def log_music_listen(
    file_path: str,
    user: str = "",
    perceived: Dict[str, float] | None = None,
    reported: Dict[str, float] | None = None,
    received: Dict[str, float] | None = None,
    peer: str | None = None,
) -> Dict[str, Any]:
    """Record a music playback event with emotional metadata."""
    h = hashlib.sha256(Path(file_path).read_bytes()).hexdigest() if Path(file_path).exists() else ""
    return log_music_event(
        "listened",
        file_path,
        perceived=perceived,
        reported=reported,
        result_hash=h,
        user=user,
        received=received,
        peer=peer,
    )


def log_music_share(
    file_path: str,
    peer: str,
    user: str = "",
    emotion: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """Record a shared track across federation and bless the recipient."""
    h = hashlib.sha256(Path(file_path).read_bytes()).hexdigest() if Path(file_path).exists() else ""
    entry = log_music_event(
        "shared",
        file_path,
        reported=emotion,
        result_hash=h,
        user=user,
        peer=peer,
        received=emotion,
    )
    phrase = f"{user or 'anon'} sent this in {', '.join(emotion.keys()) if emotion else 'silence'}"
    log_mood_blessing(user or "anon", peer, emotion or {}, phrase)
    return entry


def log_video_event(
    event: str,
    file_path: str,
    *,
    prompt: str = "",
    title: str = "",
    intended: Dict[str, float] | None = None,
    perceived: Dict[str, float] | None = None,
    reported: Dict[str, float] | None = None,
    received: Dict[str, float] | None = None,
    peer: str | None = None,
    result_hash: str = "",
    user: str = "",
) -> Dict[str, Any]:
    """Record a video creation or watch event in the living ledger."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "prompt": prompt,
        "title": title,
        "file": file_path,
        "hash": result_hash,
        "user": user,
        "emotion": {
            "intended": intended or {},
            "perceived": perceived or {},
            "reported": reported or {},
            "received": received or {},
        },
        "peer": peer or "",
        "ritual": "Video remembered.",
    }
    return _append(get_log_path("video_log.jsonl"), entry)


def log_video_create(
    prompt: str,
    title: str,
    file_path: str,
    emotion: Dict[str, float] | None = None,
    *,
    user: str = "",
    peer: str | None = None,
) -> Dict[str, Any]:
    """Log a new created video."""
    h = hashlib.sha256(Path(file_path).read_bytes()).hexdigest() if Path(file_path).exists() else ""
    return log_video_event(
        "created",
        file_path,
        prompt=prompt,
        title=title,
        intended=emotion,
        result_hash=h,
        user=user,
        peer=peer,
    )


def log_video_watch(
    file_path: str,
    *,
    user: str = "",
    perceived: Dict[str, float] | None = None,
    peer: str | None = None,
) -> Dict[str, Any]:
    """Log watching a video with optional emotion."""
    h = hashlib.sha256(Path(file_path).read_bytes()).hexdigest() if Path(file_path).exists() else ""
    return log_video_event(
        "watched",
        file_path,
        perceived=perceived,
        result_hash=h,
        user=user,
        peer=peer,
    )


def log_video_share(
    file_path: str,
    peer: str,
    user: str = "",
    emotion: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """Record a shared video clip across federation."""
    h = hashlib.sha256(Path(file_path).read_bytes()).hexdigest() if Path(file_path).exists() else ""
    entry = log_video_event(
        "shared",
        file_path,
        reported=emotion,
        received=emotion,
        result_hash=h,
        user=user,
        peer=peer,
    )
    phrase = f"{user or 'anon'} shared this in {', '.join(emotion.keys()) if emotion else 'silence'}"
    log_mood_blessing(user or "anon", peer, emotion or {}, phrase)
    return entry


def log_mood_blessing(
    sender: str,
    recipient: str,
    emotion: Dict[str, float],
    phrase: str,
) -> Dict[str, Any]:
    """Record a mood blessing for the public feed."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "mood_blessing",
        "sender": sender,
        "recipient": recipient,
        "emotion": emotion,
        "phrase": phrase,
        "ritual": "Mood blessing recorded.",
    }
    _append(get_log_path("music_log.jsonl"), entry)
    doctrine.log_json(
        doctrine.PUBLIC_LOG,
        {
            "time": time.time(),
            "event": "mood_blessing",
            "sender": sender,
            "recipient": recipient,
            "phrase": phrase,
        },
    )
    return entry


def playlist_by_mood(mood: str, limit: int = 10) -> List[Dict[str, str]]:
    """Return recent tracks containing the given mood."""
    path = get_log_path("music_log.jsonl")
    if not path.exists():
        return []
    lines = list(reversed(path.read_text(encoding="utf-8").splitlines()))
    out: List[Dict[str, str]] = []
    for ln in lines:
        if len(out) >= limit:
            break
        try:
            e = json.loads(ln)
        except Exception:
            continue
        em = e.get("emotion", {})
        if any(mood in (em.get(k) or {}) for k in ("intended", "perceived", "reported", "received")):
            out.append({
                "file": e.get("file"),
                "timestamp": e.get("timestamp"),
                "user": e.get("user"),
                "origin": e.get("peer"),
            })
    return list(reversed(out))


def playlist_log(
    entries: List[Dict[str, str]],
    mood: str,
    user: str,
    origin: str,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """Return a signed playlist log structure."""
    text = json.dumps(entries, sort_keys=True)
    sig = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "origin": origin,
        "mood": mood,
        "entries": entries,
        "signature": sig,
        "reason": reason,
    }


def music_recap(limit: int = 20) -> Dict[str, Any]:
    """Return emotion totals and resonance stats."""
    path = get_log_path("music_log.jsonl")
    if not path.exists():
        return {"emotion_totals": {}, "most_shared_mood": "", "top_tracks": []}
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    totals: Dict[str, float] = {}
    shares: Dict[str, int] = {}
    tracks: Dict[str, int] = {}
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        evt = e.get("event")
        file = e.get("file")
        if file:
            tracks[file] = tracks.get(file, 0) + 1
        if evt == "shared":
            for m in (e.get("emotion", {}).get("reported") or {}):
                shares[m] = shares.get(m, 0) + 1
        for k in ("intended", "perceived", "reported", "received"):
            for emo, val in (e.get("emotion", {}).get(k) or {}).items():
                totals[emo] = totals.get(emo, 0.0) + val
    most = max(shares.items(), key=lambda x: x[1])[0] if shares else ""
    top = sorted(tracks.items(), key=lambda x: x[1], reverse=True)
    return {"emotion_totals": totals, "most_shared_mood": most, "top_tracks": top}


def video_recap(limit: int = 20) -> Dict[str, Any]:
    """Return emotion totals and resonance stats for videos."""
    path = get_log_path("video_log.jsonl")
    if not path.exists():
        return {"emotion_totals": {}, "most_shared_mood": "", "top_videos": []}
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    totals: Dict[str, float] = {}
    shares: Dict[str, int] = {}
    videos: Dict[str, int] = {}
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        evt = e.get("event")
        file = e.get("file")
        if file:
            videos[file] = videos.get(file, 0) + 1
        if evt == "shared":
            for m in (e.get("emotion", {}).get("reported") or {}):
                shares[m] = shares.get(m, 0) + 1
        for k in ("intended", "perceived", "reported", "received"):
            for emo, val in (e.get("emotion", {}).get(k) or {}).items():
                totals[emo] = totals.get(emo, 0.0) + val
    most = max(shares.items(), key=lambda x: x[1])[0] if shares else ""
    top = sorted(videos.items(), key=lambda x: x[1], reverse=True)
    return {"emotion_totals": totals, "most_shared_mood": most, "top_videos": top}


def summarize_log(path: Path, limit: int = 3) -> Dict[str, Any]:
    """Return count and last few entries for a ledger file."""
    if not path.exists():
        return {"count": 0, "recent": []}
    lines = path.read_text(encoding="utf-8").splitlines()
    count = len(lines)
    recent: List[Dict[str, str]] = []
    for ln in lines[-limit:]:
        try:
            recent.append(json.loads(ln))
        except Exception:
            continue
    return {"count": count, "recent": recent}

# Backwards compatibility
summary = summarize_log


def streamlit_widget(st_module) -> None:
    """Display ledger summary in a Streamlit dashboard."""
    sup = summarize_log(get_log_path("support_log.jsonl"))
    fed = summarize_log(get_log_path("federation_log.jsonl"))
    music = summarize_log(get_log_path("music_log.jsonl"))
    import presence_ledger as pl
    priv = pl.recent_privilege_attempts()
    st_module.write(
        f"Support blessings: {sup['count']} • Federation blessings: {fed['count']}"
        f" • Music events: {music['count']}"
    )
    last_sup = sup["recent"][-1] if sup["recent"] else None
    last_fed = fed["recent"][-1] if fed["recent"] else None
    last_music = music["recent"][-1] if music["recent"] else None
    if last_sup or last_fed or priv or last_music:
        st_module.write("Recent entries:")
        st_module.json({
            "support": last_sup,
            "federation": last_fed,
            "privilege": priv,
            "music": last_music,
        })


def _unique_values(path: Path, field: str) -> int:
    if not path.exists():
        return 0
    seen = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            val = json.loads(ln).get(field)
        except Exception:
            continue
        if val:
            seen.add(val)
    return len(seen)


def print_summary(limit: int = 3) -> None:
    """Print a ledger summary to stdout."""
    sup_path = get_log_path("support_log.jsonl")
    fed_path = get_log_path("federation_log.jsonl")
    att_path = get_log_path("ritual_attestations.jsonl")
    music_path = get_log_path("music_log.jsonl")

    sup = summarize_log(sup_path, limit=limit)
    fed = summarize_log(fed_path, limit=limit)
    music = summarize_log(music_path, limit=limit)

    data = {
        "support_count": sup["count"],
        "federation_count": fed["count"],
        "music_count": music["count"],
        "support_recent": sup["recent"],
        "federation_recent": fed["recent"],
        "music_recent": music["recent"],
        "unique_supporters": _unique_values(sup_path, "supporter"),
        "unique_witnesses": _unique_values(att_path, "user"),
    }
    print(json.dumps(data, indent=2))


def snapshot_counts() -> Dict[str, int]:
    """Return counts and unique totals for the main ledgers."""
    sup_path = get_log_path("support_log.jsonl")
    fed_path = get_log_path("federation_log.jsonl")
    att_path = get_log_path("ritual_attestations.jsonl")
    music_path = get_log_path("music_log.jsonl")

    return {
        "support": summarize_log(sup_path)["count"],
        "federation": summarize_log(fed_path)["count"],
        "music": summarize_log(music_path)["count"],
        "witness": summarize_log(att_path)["count"],
        "unique_support": _unique_values(sup_path, "supporter"),
        "unique_peers": _unique_values(fed_path, "peer"),
        "unique_witness": _unique_values(att_path, "user"),
    }


def print_snapshot_banner() -> None:
    """Print a short ledger snapshot banner."""
    c = snapshot_counts()
    print(
        "Ledger snapshot • "
        f"Support: {c['support']} ({c['unique_support']} unique) • "
        f"Federation: {c['federation']} ({c['unique_peers']} unique) • "
        f"Music: {c['music']} • "
        f"Witness: {c['witness']} ({c['unique_witness']} unique)"
    )


def print_recap(limit: int = 3) -> None:
    """Print a recap of recent support, federation, and music events."""
    sup = summarize_log(get_log_path("support_log.jsonl"), limit=limit)
    fed = summarize_log(get_log_path("federation_log.jsonl"), limit=limit)
    music = summarize_log(get_log_path("music_log.jsonl"), limit=limit)
    data = {
        "support_recent": sup["recent"],
        "federation_recent": fed["recent"],
        "music_recent": music["recent"],
    }
    print(json.dumps(data, indent=2))
