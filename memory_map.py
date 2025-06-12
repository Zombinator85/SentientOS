"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import os
from pathlib import Path
from typing import Any, Dict, List

try:
    import pandas as pd  # type: ignore[import-untyped]  # pandas optional
    import streamlit as st  # type: ignore[import-untyped]  # Streamlit dashboard
except Exception:  # pragma: no cover - optional
    pd = None
    st = None

import memory_manager as mm

MEMORY_DIR = mm.RAW_PATH
EEG_LOG = get_log_path("eeg_events.jsonl", "EEG_LOG")
HAPTIC_LOG = get_log_path("haptics_events.jsonl", "HAPTIC_LOG")
BIO_LOG = get_log_path("bio_events.jsonl", "BIO_LOG")
MOOD_LOG = get_log_path("epu_mood.jsonl", "EPU_MOOD_LOG")


def load_entries(limit: int = 200) -> List[Dict[str, Any]]:
    files = sorted(MEMORY_DIR.glob("*.json"))[-limit:]
    out: List[Dict[str, Any]] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        emo = data.get("emotions", {})
        data = {
            "timestamp": data.get("timestamp"),
            "text": data.get("text", "")[:200],
            "persona": data.get("source", "unknown"),
            **{k: float(v) for k, v in emo.items()},
        }
        out.append(data)
    return out


def _load_jsonl(path: Path, limit: int = 200) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def load_eeg(limit: int = 200) -> List[Dict[str, Any]]:
    return _load_jsonl(EEG_LOG, limit)


def load_haptics(limit: int = 200) -> List[Dict[str, Any]]:
    return _load_jsonl(HAPTIC_LOG, limit)


def load_bio(limit: int = 200) -> List[Dict[str, Any]]:
    return _load_jsonl(BIO_LOG, limit)


def load_mood(limit: int = 200) -> List[Dict[str, Any]]:
    return _load_jsonl(MOOD_LOG, limit)


def run_dashboard() -> None:
    if st is None or pd is None:
        for e in load_entries():
            print(json.dumps(e))
        return

    st.set_page_config(page_title="Memory Map", layout="wide")
    st.title("Memory Timeline")
    limit = st.sidebar.number_input("History", 50, 1000, 200)
    data = load_entries(limit=int(limit))
    if not data:
        st.write("No memory entries found")
        return
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    emo_cols = [c for c in df.columns if c not in {"timestamp", "text", "persona"}]
    st.line_chart(df.set_index("timestamp")[emo_cols])
    st.dataframe(df.tail(20))

    mood = load_mood(limit=int(limit))
    if mood:
        rows = []
        for m in mood:
            row = {"timestamp": m.get("timestamp")}
            for k, v in (m.get("mood") or {}).items():
                row[k] = v
            rows.append(row)
        md = pd.DataFrame(rows)
        md["timestamp"] = pd.to_datetime(md["timestamp"])
        st.subheader("Mood Timeline")
        emo_cols2 = [c for c in md.columns if c != "timestamp"]
        st.line_chart(md.set_index("timestamp")[emo_cols2])

    eeg = load_eeg(limit=int(limit))
    if eeg:
        rows = []
        for e in eeg:
            row = {"timestamp": e.get("timestamp")}
            for k, v in (e.get("band_power") or {}).items():
                row[k] = v
            rows.append(row)
        ed = pd.DataFrame(rows)
        ed["timestamp"] = pd.to_datetime(ed["timestamp"])
        st.subheader("EEG Band Power")
        bcols = [c for c in ed.columns if c != "timestamp"]
        st.line_chart(ed.set_index("timestamp")[bcols])

    haptic = load_haptics(limit=int(limit))
    if haptic:
        hd = pd.DataFrame(haptic)
        hd["timestamp"] = pd.to_datetime(hd["timestamp"])
        st.subheader("Haptic Events")
        st.line_chart(hd.set_index("timestamp")[["value"]])

    bio = load_bio(limit=int(limit))
    if bio:
        bd = pd.DataFrame(bio)
        bd["timestamp"] = pd.to_datetime(bd["timestamp"])
        st.subheader("Biosignals")
        st.line_chart(bd.set_index("timestamp")[["heart_rate", "gsr", "temperature"]])


if __name__ == "__main__":  # pragma: no cover - CLI fallback
    run_dashboard()
