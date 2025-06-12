"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import json
import time
from typing import List, Dict

import love_treasury as lt
from sentient_banner import streamlit_banner, streamlit_closing, print_banner
import ledger


try:
    import streamlit as st  # type: ignore[import-untyped]  # Streamlit optional
except Exception:  # pragma: no cover - optional
    st = None


def run_cli() -> None:
    print_banner()
    data = lt.list_treasury()
    print(json.dumps(data, indent=2))


def run_dashboard() -> None:
    if st is None:
        run_cli()
        return

    st.title("Treasury of Love")
    streamlit_banner(st)
    ledger.streamlit_widget(st)
    entries: List[Dict[str, object]] = lt.list_treasury()
    if not entries:
        st.write("No enshrined logs")
        return
    for e in entries:
        with st.expander(e.get("title", "")):
            st.json(e)
    if st.sidebar.button("Refresh"):
        st.experimental_rerun()
    streamlit_closing(st)


if __name__ == "__main__":
    run_dashboard()
