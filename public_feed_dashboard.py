"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import json
import argparse
import time
from pathlib import Path
from typing import List, Dict

import doctrine
from sentient_banner import streamlit_banner, streamlit_closing, print_banner
import ledger


try:
    import streamlit as st  # type: ignore[import-untyped]  # Streamlit optional
except Exception:  # pragma: no cover - optional
    st = None

LOG = doctrine.PUBLIC_LOG


def load_feed(last: int = 50, event: str | None = None, date: str | None = None) -> List[Dict[str, object]]:
    if not LOG.exists():
        return []
    lines = LOG.read_text(encoding="utf-8").splitlines()[-last:]
    out: List[Dict[str, object]] = []
    for ln in lines:
        try:
            data = json.loads(ln)
        except Exception:
            continue
        if event and data.get("event") != event:
            continue
        if date:
            ts = time.strftime("%Y-%m-%d", time.gmtime(data.get("time", 0)))
            if ts != date:
                continue
        out.append(data)
    return out


def run_cli(args: argparse.Namespace) -> None:
    print_banner()
    feed = load_feed(args.last, args.event, args.date)
    for entry in feed:
        print(json.dumps(entry))


def run_dashboard() -> None:
    if st is None:
        ap = argparse.ArgumentParser(description="Public ritual feed")
        ap.add_argument("--last", type=int, default=20)
        ap.add_argument("--event")
        ap.add_argument("--date")
        args = ap.parse_args()
        run_cli(args)
        return

    st.title("Public Ritual Feed")
    streamlit_banner(st)
    ledger.streamlit_widget(st.sidebar if hasattr(st, "sidebar") else st)
    event = st.sidebar.text_input("Event filter")
    date = st.sidebar.text_input("Date (YYYY-MM-DD)")
    last = st.sidebar.number_input("Last N", 1, 1000, 20)
    refresh = st.sidebar.number_input("Refresh sec", 1, 60, 5)
    tail = st.sidebar.checkbox("Auto-refresh", True)

    while True:
        feed = load_feed(int(last), event or None, date or None)
        if feed:
            st.json(feed)
        else:
            st.write("No events")
        if not tail:
            break
        time.sleep(refresh)
        st.experimental_rerun()
    streamlit_closing(st)


if __name__ == "__main__":
    run_dashboard()
