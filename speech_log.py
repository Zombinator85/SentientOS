from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, MutableMapping, Optional

from sentientos.memory.mounts import ensure_memory_mounts
from sentientos.runtime.bootstrap import get_base_dir

_DEFAULT_FILENAME = "speech_log.jsonl"
_DEFAULT_MAX_ENTRIES = 200


def _default_log_path() -> Path:
    base_dir = get_base_dir()
    try:
        mounts = ensure_memory_mounts(base_dir)
        glow_dir = Path(mounts.glow)
    except Exception:
        glow_dir = Path(base_dir) / "memory" / "glow"
    glow_dir.mkdir(parents=True, exist_ok=True)
    return glow_dir / _DEFAULT_FILENAME


def append_speech_log(
    entry: Mapping[str, object], *, log_path: Path | None = None, max_entries: int = _DEFAULT_MAX_ENTRIES
) -> None:
    path = Path(log_path) if log_path is not None else _default_log_path()
    try:
        payload = json.dumps(dict(entry), ensure_ascii=False)
    except Exception:
        return

    try:
        existing = []
        if path.exists():
            existing = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        existing.append(payload)
        limit = max(1, int(max_entries))
        if len(existing) > limit:
            existing = existing[-limit:]
        path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    except OSError:
        return


def get_recent_speech(log_path: Path | None = None) -> Optional[MutableMapping[str, object]]:
    path = Path(log_path) if log_path is not None else _default_log_path()
    if not path.exists():
        return None
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return None
    for raw in reversed(lines):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, Mapping):
            entry: MutableMapping[str, object] = {
                "ts": data.get("ts", datetime.now(timezone.utc).isoformat()),
                "text": data.get("text", data.get("phrase", "")),
                "duration": data.get("duration", data.get("elapsed", 0.0)),
                "viseme_count": data.get("viseme_count", 0),
                "muted": data.get("muted", False),
                "speaking": data.get("speaking", False),
            }
            return entry
    return None


def build_speech_log_entry(
    *,
    text: str,
    viseme_count: int,
    duration: float,
    speaking: bool,
    muted: bool,
    event: str,
    started_at: float | None = None,
    mode: str | None = None,
) -> Mapping[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "ts": timestamp,
        "event": event,
        "text": text,
        "viseme_count": max(0, int(viseme_count)),
        "duration": max(0.0, float(duration)),
        "speaking": bool(speaking),
        "muted": bool(muted),
        "started_at": started_at,
        "mode": mode or "UNKNOWN",
    }


__all__ = [
    "append_speech_log",
    "build_speech_log_entry",
    "get_recent_speech",
]
