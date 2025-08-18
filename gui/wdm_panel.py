"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import json, yaml
from typing import Dict

try:
    import streamlit as st  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional
    st = None  # type: ignore

from wdm.runner import run_wdm


def render() -> None:
    if st is None:
        print("Streamlit not available.")
        return

    st.title("Wild-Dialogue Mode")
    seed = st.text_input("Seed")
    triggers: Dict[str, bool] = {}
    for t in [
        "user_request",
        "conflicting_sources",
        "low_confidence_high_impact",
        "watchlist_topic",
    ]:
        triggers[t] = st.checkbox(t)
    cheers = st.checkbox("Cheers (drop-in)")

    if st.button("Start"):
        ctx = {k: v for k, v in triggers.items() if v}
        if cheers:
            ctx["cheers"] = True
        with open("config/wdm.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        out = run_wdm(seed, ctx, cfg)
        st.write(out)
        log = out.get("log")
        if log:
            st.write(f"[log]({log})")
        if cheers:
            cheers_log = cfg.get("activation", {}).get("cheers_channel", "logs/wdm/cheers.jsonl")
            st.write(f"[cheers log]({cheers_log})")

