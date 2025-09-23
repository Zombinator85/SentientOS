"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

reflection_dashboard.py — Dashboard to review reflection and trust logs.

Usage:
    python -m scripts.reflection_dashboard --help
"""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import reflection_stream as rs
import trust_engine as te
from sentient_banner import streamlit_banner, streamlit_closing, print_banner
import ledger


try:
    import pandas as pd  # type: ignore[import-untyped]  # pandas optional
except Exception:  # pragma: no cover - optional
    pd = None

try:
    import streamlit as st  # type: ignore[import-untyped]  # Streamlit dashboard
except Exception:  # pragma: no cover - optional
    st = None


PRIORITY_FILE = Path(
    os.getenv("ARCHITECT_PRIORITY_BACKLOG", "/glow/codex_reflections/priorities.json")
)


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.min


def load_timeline(limit: int = 200) -> List[Dict[str, Any]]:
    """Load recent reflection and trust events into a single timeline."""
    events: List[Dict[str, Any]] = []
    if rs.STREAM_FILE.exists():
        lines = rs.STREAM_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
        for line in lines:
            try:
                e = json.loads(line)
            except Exception:
                continue
            events.append(
                {
                    "id": e.get("id"),
                    "timestamp": e.get("timestamp"),
                    "component": e.get("source"),
                    "type": e.get("event"),
                    "action": e.get("action"),
                    "cause": e.get("cause"),
                    "explanation": e.get("explanation"),
                    "data": e.get("data", {}),
                    "explain_cmd": f"python reflect_cli.py explain {e.get('id')}",
                }
            )
    if te.EVENTS_PATH.exists():
        lines = te.EVENTS_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
        for line in lines:
            try:
                e = json.loads(line)
            except Exception:
                continue
            events.append(
                {
                    "id": e.get("id"),
                    "timestamp": e.get("timestamp"),
                    "component": e.get("source"),
                    "type": e.get("type"),
                    "action": e.get("cause"),
                    "cause": e.get("cause"),
                    "explanation": e.get("explanation"),
                    "data": e.get("data", {}),
                    "explain_cmd": f"python trust_cli.py explain {e.get('id')}",
                }
            )
    events.sort(key=lambda x: x.get("timestamp", ""))
    return events


def load_priority_backlog() -> Dict[str, Any]:
    """Load the ArchitectDaemon priority backlog, returning defaults if missing."""
    if PRIORITY_FILE.exists():
        try:
            data = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict):
            data.setdefault("updated", "")
            data.setdefault("active", [])
            data.setdefault("history", [])
            data.setdefault("federated", [])
            data.setdefault("conflicts", [])
            return data
    return {"updated": "", "active": [], "history": [], "federated": [], "conflicts": []}


def _last_completed_priority(history: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "done":
            continue
        candidates.append(entry)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: _parse_ts(str(item.get("completed_at", ""))), reverse=True
    )
    return candidates[0]


def filter_events(
    events: Iterable[Dict[str, Any]],
    *,
    event_type: Optional[str] = None,
    component: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter events by type, component, time window, or search text."""
    out: List[Dict[str, Any]] = []
    txt = text.lower() if text else None
    for ev in events:
        if event_type and ev.get("type") != event_type:
            continue
        if component and component not in (ev.get("component") or ""):
            continue
        ts = _parse_ts(ev.get("timestamp", ""))
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        if txt and txt not in json.dumps(ev).lower():
            continue
        out.append(ev)
    return out


def _print_table(events: Iterable[Dict[str, Any]]) -> None:
    for ev in events:
        line = (
            f"{ev.get('timestamp','?')} {ev.get('component','?')} "
            f"{ev.get('type','?')} {ev.get('action','')} {ev.get('explanation','')}"
        )
        print(line)
        cmd = ev.get("explain_cmd")
        if cmd:
            print(f"  -> {cmd}")


def run_cli(args: argparse.Namespace) -> None:
    events = load_timeline(limit=args.last)
    start = None
    end = None
    if args.since:
        start = datetime.utcnow() - timedelta(minutes=float(args.since))
    if args.start:
        start = _parse_ts(args.start)
    if args.end:
        end = _parse_ts(args.end)
    events = filter_events(
        events,
        event_type=args.type,
        component=args.component,
        start=start,
        end=end,
        text=args.search,
    )
    _print_table(events)


def run_dashboard() -> None:
    if st is None or pd is None:
        ap = argparse.ArgumentParser(description="Reflection dashboard CLI")
        ap.add_argument("--type", dest="type")
        ap.add_argument("--component")
        ap.add_argument("--since", type=float, help="Minutes in the past")
        ap.add_argument("--start")
        ap.add_argument("--end")
        ap.add_argument("--search")
        ap.add_argument("--last", type=int, default=20)
        args = ap.parse_args()
        run_cli(args)
        return

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--tail", action="store_true")
    parsed, _ = ap.parse_known_args()

    st.set_page_config(page_title="Reflection Dashboard", layout="wide")
    st.title("Event & Reflection Dashboard")
    streamlit_banner(st)
    ledger.streamlit_widget(st.sidebar if hasattr(st, "sidebar") else st)

    last = st.sidebar.number_input("Load last N", 50, 1000, 200)
    event_filter = st.sidebar.text_input("Event type")
    component_filter = st.sidebar.text_input("Component filter")
    search = st.sidebar.text_input("Search")
    minutes = st.sidebar.number_input("Since minutes", 0, 1440, 0)
    refresh = st.sidebar.number_input("Refresh sec", 1, 60, 5)
    tail = parsed.tail

    while True:
        start = datetime.utcnow() - timedelta(minutes=minutes) if minutes else None
        events = load_timeline(limit=int(last))
        events = filter_events(
            events,
            event_type=event_filter or None,
            component=component_filter or None,
            start=start,
            text=search or None,
        )

        events_tab, reflections_tab = st.tabs(["Events", "Reflections"])

        with events_tab:
            df = pd.DataFrame(events)
            if not df.empty:
                df = df.sort_values("timestamp", ascending=False)
                st.dataframe(df)
            else:
                st.write("No events")

        with reflections_tab:
            backlog = load_priority_backlog()
            st.subheader("Architect Priorities")
            updated = backlog.get("updated") or "unknown"
            st.caption(f"Last updated: {updated}")
            active = backlog.get("active") or []
            active_df = pd.DataFrame(active)
            if not active_df.empty:
                active_df = active_df.sort_values(["status", "text"], ascending=[True, True])
                st.dataframe(active_df)
            else:
                st.write("Backlog empty — awaiting new reflection priorities.")

            history = backlog.get("history") or []
            last_priority = _last_completed_priority(history)
            if last_priority:
                completed_at = last_priority.get("completed_at", "unknown")
                st.markdown(
                    f"**Last completed priority:** {last_priority.get('text', 'unknown')}\n\n"
                    f"Completed at: {completed_at}"
                )
            else:
                st.markdown("**Last completed priority:** none recorded yet.")

            federated = backlog.get("federated") or []
            st.subheader("Federated Priorities")
            if federated:
                federated_rows = []
                for entry in federated:
                    origin_peers = ", ".join(entry.get("origin_peers", []))
                    federated_rows.append(
                        {
                            "text": entry.get("text", ""),
                            "origin_peers": origin_peers,
                            "conflict": bool(entry.get("conflict", False)),
                            "merged": bool(entry.get("merged", False)),
                        }
                    )
                fed_df = pd.DataFrame(federated_rows)
                if not fed_df.empty:
                    fed_df = fed_df.sort_values(["conflict", "text"], ascending=[False, True])
                    st.dataframe(fed_df)
                else:
                    st.write("No federated priorities received yet.")
            else:
                st.write("No federated priorities received yet.")

            conflicts = backlog.get("conflicts") or []
            if conflicts:
                st.subheader("Conflicts Requiring Review")
                conflict_rows = []
                for entry in conflicts:
                    variants = entry.get("variants") or []
                    variant_text = "; ".join(
                        f"{variant.get('peer')}: {variant.get('text')}"
                        for variant in variants
                        if isinstance(variant, dict)
                    )
                    conflict_rows.append(
                        {
                            "text": entry.get("text", ""),
                            "origin_peers": ", ".join(entry.get("origin_peers", [])),
                            "variants": variant_text,
                        }
                    )
                conflict_df = pd.DataFrame(conflict_rows)
                if not conflict_df.empty:
                    conflict_df = conflict_df.sort_values("text", ascending=True)
                    st.dataframe(conflict_df)
                st.info(
                    "Conflicting priorities need manual confirmation."
                    " Use the merge controls' resolve option to accept or dismiss a peer proposal."
                )
            else:
                st.caption("No backlog conflicts detected across peers.")

            backlog_json = json.dumps(backlog, indent=2, sort_keys=True)
            st.download_button(
                "Export backlog JSON",
                data=backlog_json,
                file_name="architect_priorities.json",
                mime="application/json",
            )

        if not tail:
            break
        time.sleep(refresh)
        st.experimental_rerun()
    streamlit_closing(st)


if __name__ == "__main__":
    run_dashboard()
