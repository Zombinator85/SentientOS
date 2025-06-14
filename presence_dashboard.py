"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import json
import time
from urllib import request
from typing import List, Dict
from sentient_banner import (
    print_banner,
    print_closing,
    streamlit_banner,
    streamlit_closing,
)
import ledger


try:
    import streamlit as st  # type: ignore[import-untyped]  # optional dashboard
except Exception:  # pragma: no cover - optional
    st = None


def get_presence(url: str) -> List[Dict[str, str]]:
    try:
        with request.urlopen(f"{url.rstrip('/')}/presence", timeout=0.1) as r:
            data = json.loads(r.read().decode())
            return data.get("users", [])
    except Exception:
        return []


def run_cli(server: str, once: bool = False) -> None:
    """CLI mode showing presence and ledger summary."""
    print_banner()
    ledger.print_snapshot_banner()
    ledger.print_summary()
    recap_shown = False
    try:
        while True:
            pres = get_presence(server)
            print(json.dumps(pres, indent=2))
            if once:
                break
            time.sleep(1)
    finally:
        print_closing(show_recap=not recap_shown)


def run_dashboard(server: str) -> None:
    """Streamlit dashboard showing presence and ledger widget."""
    if st is None:
        run_cli(server, once=True)
        return
    st.title("Presence Dashboard")
    streamlit_banner(st)
    ledger.streamlit_widget(st)
    pres = get_presence(server)
    st.json(pres)
    if st.button("Refresh"):
        st.experimental_rerun()
    streamlit_closing(st)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Presence dashboard")
    parser.add_argument("server")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit dashboard")
    parser.add_argument("--ledger", action="store_true", help="Show living ledger summary and exit")
    args = parser.parse_args()
    if args.ledger:
        print_banner()
        ledger.print_snapshot_banner()
        ledger.print_summary()
        print_closing()
        return
    if args.dashboard:
        run_dashboard(args.server)
    else:
        run_cli(args.server, once=args.once)


if __name__ == "__main__":
    main()
