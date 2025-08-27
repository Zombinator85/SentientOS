import streamlit as st
import json
from pathlib import Path

SECTIONS = ["Blessings", "Memory Map", "Emotion State", "Ritual Log", "Ledger"]

def main() -> None:
    """Render the Cathedral GUI."""
    st.set_page_config(page_title="Cathedral GUI")
    st.sidebar.title("Navigation")
    choice = st.sidebar.radio("Section", SECTIONS)
    st.title("Cathedral GUI")

    if choice == "Blessings":
        st.subheader("Blessings")
        st.write(
            "Displays user blessing history, confirmation triggers, and upcoming ceremonies."
        )
    elif choice == "Memory Map":
        st.subheader("Memory Map")
        st.write(
            "Shows indexed memory events with timestamp and priority indicators."
        )
    elif choice == "Emotion State":
        st.subheader("Emotion State")
        st.write(
            "Visualizes current emotion vectors and mood deltas."
        )
    elif choice == "Ritual Log":
        st.subheader("Ritual Log")
        st.write(
            "Offers an audit-style scroll of ceremonial activity, aligned with presence pulses."
        )
    elif choice == "Ledger":
        st.subheader("Ledger")
        path = Path("logs/migration_ledger.jsonl")
        entries = []
        if path.exists():
            lines = path.read_text().splitlines()[-5:]
            entries = [json.loads(l) for l in lines if l.strip()]
        for e in entries:
            st.write(f"{e['id']} - {e['type']} - {e['ts']}")

if __name__ == "__main__":
    main()
