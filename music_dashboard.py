"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
from pathlib import Path
from typing import Dict, List


try:
    import streamlit as st  # type: ignore[import-untyped]  # optional dashboard
except Exception:  # pragma: no cover - optional
    st = None


def _load(limit: int = 100) -> List[Dict[str, object]]:
    path = get_log_path("music_log.jsonl")
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, object]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def top_emotions(entries: List[Dict[str, object]]) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    for e in entries:
        for k in ("intended", "perceived", "reported", "received"):
            for emo, val in (e.get("emotion", {}).get(k) or {}).items():
                totals[emo] = totals.get(emo, 0.0) + val
    return totals


def run_dashboard() -> None:
    if st is None:
        print(json.dumps({"data": top_emotions(_load())}, indent=2))
        return
    st.title("Musical Mood Map")
    entries = _load()
    totals = top_emotions(entries)
    st.bar_chart({"emotion": list(totals.keys()), "value": list(totals.values())})
    st.json(entries[-5:])


if __name__ == "__main__":
    run_dashboard()
