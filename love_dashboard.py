import json
import time
from typing import List, Dict

import love_treasury as lt
from sentient_banner import streamlit_banner, streamlit_closing, print_banner
import ledger
from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

try:
    import streamlit as st  # type: ignore  # Streamlit optional
except Exception:  # pragma: no cover - optional
    st = None


def run_cli() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    print_banner()
    data = lt.list_treasury()
    print(json.dumps(data, indent=2))


def run_dashboard() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
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
