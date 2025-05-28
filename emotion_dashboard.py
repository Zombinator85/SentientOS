import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional
    pd = None

try:
    import streamlit as st
except Exception:  # pragma: no cover - optional
    st = None

DEFAULT_LOG = Path(os.getenv("TRACKER_LOG", "logs/vision/vision.jsonl"))


def load_logs(log_path: str | Path = DEFAULT_LOG) -> Dict[int, List[Dict[str, Any]]]:
    """Parse the vision/audio log into per-user timelines."""
    path = Path(log_path)
    timelines: Dict[int, List[Dict[str, Any]]] = {}
    if not path.exists():
        return timelines
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except Exception:
            continue
        ts = entry.get("timestamp")
        for face in entry.get("faces", []):
            fid = face.get("id")
            if fid is None:
                continue
            record = {"timestamp": ts, "dominant": face.get("dominant")}
            for k, v in (face.get("emotions") or {}).items():
                record[k] = v
            timelines.setdefault(int(fid), []).append(record)
    return timelines


def query_state(timelines: Dict[int, List[Dict[str, Any]]], user_id: int, timestamp: float) -> Optional[Dict[str, Any]]:
    """Return the emotion record closest to ``timestamp`` for ``user_id``."""
    history = timelines.get(user_id, [])
    if not history:
        return None
    return min(history, key=lambda r: abs(r.get("timestamp", 0) - timestamp))


def run_dashboard(log_path: str | Path = DEFAULT_LOG) -> None:
    """Launch the Streamlit dashboard."""
    if st is None or pd is None:
        print("Streamlit or pandas not available. Install dependencies to run dashboard.")
        return

    st.set_page_config(page_title="SentientOS Dashboard", layout="wide")
    st.title("SentientOS Emotion Dashboard")

    refresh = st.sidebar.number_input("Refresh interval (sec)", min_value=1, max_value=60, value=2)

    timelines = load_logs(log_path)
    ids = sorted(timelines.keys())
    if not ids:
        st.write("No data found.")
        time.sleep(refresh)
        st.experimental_rerun()
        return

    selected = st.sidebar.selectbox("Tracked ID", ids)
    history = timelines.get(selected, [])
    if not history:
        st.write("No history for selected ID")
    else:
        df = pd.DataFrame(history)
        df = df.sort_values("timestamp")
        emotion_cols = [c for c in df.columns if c not in ("timestamp", "dominant")]
        if emotion_cols:
            st.line_chart(df.set_index("timestamp")[emotion_cols])
        st.dataframe(df.tail(10))

    time.sleep(refresh)
    st.experimental_rerun()


if __name__ == "__main__":
    run_dashboard()
