"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
from pathlib import Path
from typing import Any, Dict, List, TypedDict, cast


try:
    import streamlit as st  # type: ignore  # optional Streamlit dashboard
except Exception:  # pragma: no cover - optional
    st = None


class VideoEmotion(TypedDict):
    """Emotion metadata for a video entry."""

    intended: Dict[str, float]
    perceived: Dict[str, float]
    reported: Dict[str, float]
    received: Dict[str, float]


class VideoEntry(TypedDict):
    """Data structure for each video_log entry."""

    emotion: VideoEmotion


def _load(limit: int = 100) -> List[VideoEntry]:
    path = get_log_path("video_log.jsonl")
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[VideoEntry] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(cast(VideoEntry, obj))
    return out


def top_emotions(entries: List[VideoEntry]) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    for e in entries:
        emo_block = e["emotion"]
        for k in ("intended", "perceived", "reported", "received"):
            vals = emo_block[k]
            for emo, val in vals.items():
                totals[emo] = totals.get(emo, 0.0) + val
    return totals


def run_dashboard() -> None:
    if st is None:
        print(json.dumps({"data": top_emotions(_load())}, indent=2))
        return
    st.title("Video Memory Map")
    entries = _load()
    totals = top_emotions(entries)
    st.bar_chart({"emotion": list(totals.keys()), "value": list(totals.values())})
    st.json(entries[-5:])


if __name__ == "__main__":
    run_dashboard()
