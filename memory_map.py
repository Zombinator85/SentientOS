import json
import os
from pathlib import Path
from typing import Any, Dict, List

try:
    import pandas as pd  # type: ignore
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - optional
    pd = None
    st = None

import memory_manager as mm

MEMORY_DIR = mm.RAW_PATH


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


if __name__ == "__main__":  # pragma: no cover - CLI fallback
    run_dashboard()
