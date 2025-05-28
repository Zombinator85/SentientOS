import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from feedback import FeedbackManager, FeedbackRule, print_action

try:
    import pandas as pd  # type: ignore
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - optional
    pd = None
    st = None


def load_log(path: str, limit: int = 1000) -> List[Dict[str, any]]:
    p = Path(path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def run_dashboard(log_path: str = "logs/vision/vision.jsonl", rules: Optional[str] = None) -> None:
    if st is None:
        print("[DASH] Streamlit not available")
        return

    fm = FeedbackManager()
    fm.register_action("print", print_action)
    if rules:
        fm.load_rules(rules)

    st.title("Emotion Dashboard")
    hist_box = st.sidebar.empty()
    data_box = st.empty()

    last_len = 0
    while True:
        data = load_log(log_path)
        if len(data) != last_len:
            last_len = len(data)
            rows = []
            if data:
                for face in data[-1].get("faces", []):
                    fm.process(face["id"], face.get("emotions", {}))
                    row = {"id": face["id"], "dominant": face.get("dominant")}
                    row.update(face.get("emotions", {}))
                    rows.append(row)
            if pd:
                df = pd.DataFrame(rows)
                data_box.dataframe(df)
            else:
                data_box.write(rows)
            hist_box.write(fm.get_history())
        time.sleep(0.5)
