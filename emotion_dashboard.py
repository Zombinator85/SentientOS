import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# FeedbackManager and rules are optional – only import/use if you want to trigger feedback in the dashboard!
try:
    from feedback import FeedbackManager, FeedbackRule, print_action
except ImportError:
    FeedbackManager = None

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional
    pd = None

try:
    import streamlit as st
except Exception:  # pragma: no cover - optional
    st = None

DEFAULT_LOG = Path(os.getenv("TRACKER_LOG", "logs/vision/vision.jsonl"))

def load_logs(log_path: str | Path = DEFAULT_LOG, limit: int = 1000) -> Dict[int, List[Dict[str, Any]]]:
    """Parse the vision/audio log into per-user timelines."""
    path = Path(log_path)
    timelines: Dict[int, List[Dict[str, Any]]] = {}
    if not path.exists():
        return timelines
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in lines:
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

def run_dashboard(
    log_path: str | Path = DEFAULT_LOG,
    feedback_rules: Optional[str] = None,
) -> None:
    """Launch the SentientOS Streamlit dashboard, with optional feedback layer."""
    if st is None or pd is None:
        print("Streamlit or pandas not available. Install dependencies to run dashboard.")
        return

    st.set_page_config(page_title="SentientOS Dashboard", layout="wide")
    st.title("SentientOS Emotion Dashboard")

    # Optional FeedbackManager integration
    fm = None
    if FeedbackManager is not None:
        fm = FeedbackManager()
        if hasattr(fm, "register_action"):
            fm.register_action("print", print_action)
        if feedback_rules:
            fm.load_rules(feedback_rules)
        hist_box = st.sidebar.empty()

    refresh = st.sidebar.number_input("Refresh interval (sec)", min_value=1, max_value=60, value=2)

    while True:
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

            # Feedback: trigger for new entries
            if fm is not None and history:
                latest = history[-1]
                fm.process(selected, {k: v for k, v in latest.items() if k not in ("timestamp", "dominant")})
                if hasattr(hist_box, "write"):
                    hist_box.write(fm.get_history())

        time.sleep(refresh)
        st.experimental_rerun()

if __name__ == "__main__":
    run_dashboard()
