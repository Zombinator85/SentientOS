from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

try:
    import streamlit as st
except Exception:  # pragma: no cover - optional dependency
    st = None

LOG_PATH = Path(os.getenv("RESONITE_RITUAL_DASHBOARD_LOG", "logs/resonite_ritual_dashboard.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: str, data: dict) -> None:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_dashboard() -> None:
    require_admin_banner()
    if st is None:
        print("Streamlit not installed.")
        return
    st.title("Resonite Ritual Dashboard")
    st.write("Live ritual logs")
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-100:]
        for line in lines:
            st.json(json.loads(line))


if __name__ == "__main__":
    run_dashboard()
