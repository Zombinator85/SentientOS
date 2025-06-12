"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict
import workflow_library as wl
import workflow_controller as wc
import workflow_review as wr
import workflow_analytics as wa
import workflow_recommendation as rec
import review_requests as rr
import notification
from sentient_banner import streamlit_banner, streamlit_closing
import ledger

try:
    import yaml  # type: ignore[import-untyped]  # optional YAML parsing
except Exception:  # pragma: no cover - optional
    yaml = None



try:  # optional deps
    import streamlit as st  # type: ignore[import-untyped]  # Streamlit dashboard
    import pandas as pd  # type: ignore[import-untyped]  # pandas for tables
    import graphviz
except Exception:  # pragma: no cover - optional
    st = None
    pd = None
graphviz = None

EVENTS = wc.EVENT_PATH


def record_feedback(workflow: str, helpful: bool) -> None:
    """Log user feedback about a workflow run."""
    notification.send("workflow.feedback", {"workflow": workflow, "helpful": helpful})


class Metrics(TypedDict):
    success: int
    failed: int
    last_status: Optional[str]
    last_ts: Optional[str]


def load_metrics(name: str, last: int = 200) -> Metrics:
    data: Metrics = {
        "success": 0,
        "failed": 0,
        "last_status": None,
        "last_ts": None,
    }
    if not EVENTS.exists():
        return data
    lines = EVENTS.read_text(encoding="utf-8").splitlines()[-last:]
    for line in lines:
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("payload", {}).get("workflow") != name:
            continue
        if ev.get("event") == "workflow.end":
            data["last_status"] = ev.get("payload", {}).get("status")
            data["last_ts"] = ev.get("timestamp")
        if ev.get("event") == "workflow.step":
            status = ev.get("payload", {}).get("status")
            if status == "ok":
                data["success"] += 1
            elif status == "failed":
                data["failed"] += 1
    return data


def visualize_steps(steps: List[Dict[str, Any]]) -> str:
    if graphviz is None:
        return "graphviz not installed"
    dot = graphviz.Digraph()
    for i, st in enumerate(steps):
        label = st.get("name", str(i))
        color = "lightgray"
        if st.get("skip"):
            color = "yellow"
        dot.node(str(i), label, style="filled", fillcolor=color)
        if i > 0:
            dot.edge(str(i - 1), str(i))
    return dot.source


def run_cli(args: argparse.Namespace) -> None:
    if args.list:
        for n in wl.list_templates():
            print(n)
        return
    if args.metrics:
        for n in wl.list_templates():
            m = load_metrics(n)
            print(n, m["last_status"], m["success"], m["failed"])
        return
    if args.review:
        for n in wr.list_pending():
            print("pending:", n)
        return
    if args.analytics:
        print(json.dumps(wa.analytics(), indent=2))
        return
    if args.recommend:
        data = wa.analytics()
        for line in rec.recommend_workflows(data):
            print("-", line)
        return
    if args.review_requests:
        data = wa.analytics()
        for wf in rec.generate_review_requests(data):
            print("flagged", wf)
        for r in rr.list_requests("pending"):
            print(json.dumps(r))
        return
    if args.feedback:
        record_feedback(args.feedback, not args.negative)
        print("feedback recorded")
        return


def run_dashboard() -> None:
    if st is None or pd is None:
        ap = argparse.ArgumentParser(description="Workflow dashboard CLI")
        ap.add_argument("--list", action="store_true")
        ap.add_argument("--metrics", action="store_true")
        ap.add_argument("--review", action="store_true")
        ap.add_argument("--analytics", action="store_true")
        ap.add_argument("--recommend", action="store_true")
        ap.add_argument("--review-requests", action="store_true")
        ap.add_argument("--feedback")
        ap.add_argument("--negative", action="store_true")
        args = ap.parse_args()
        run_cli(args)
        return

    st.set_page_config(page_title="Workflow Dashboard", layout="wide")
    st.title("Workflow Dashboard")
    streamlit_banner(st)
    ledger.streamlit_widget(st.sidebar if hasattr(st, "sidebar") else st)

    names = wl.list_templates()
    search = st.sidebar.text_input("Search")
    if search:
        names = [n for n in names if search.lower() in n.lower()]
    selected = st.sidebar.selectbox("Workflow", names) if names else None

    tabs = st.tabs(["Details", "Analytics", "Recommendations"])
    with tabs[0]:
        if selected:
            fp = wl.get_template_path(selected)
            if fp:
                text = fp.read_text(encoding="utf-8")
                if fp.suffix in {".yml", ".yaml"}:
                    data = yaml.safe_load(text) if yaml else wc._load_yaml(text)
                else:
                    data = json.loads(text)
                steps = data.get("steps", [])
                st.subheader("Steps")
                if graphviz is not None:
                    src = visualize_steps(steps)
                    st.graphviz_chart(src)
                st.json(steps)
                metrics = load_metrics(selected)
                st.subheader("Metrics")
                st.write(metrics)
                if st.button("👍 Was this workflow helpful?"):
                    record_feedback(selected, True)
                if st.button("👎 Not helpful"):
                    record_feedback(selected, False)
                if selected in wr.list_pending():
                    info = wr.load_review(selected)
                    if info:
                        st.subheader("Review auto-heal")
                        st.text_area("Before", info.get("before", ""), height=150)
                        st.text_area("After", info.get("after", ""), height=150)
                        col1, col2 = st.columns(2)
                        if col1.button("Accept"):
                            wr.accept_review(selected)
                            st.experimental_rerun()
                        if col2.button("Revert"):
                            wr.revert_review(selected)
                            st.experimental_rerun()
        else:
            st.write("No workflows found")

    with tabs[1]:
        st.subheader("Usage Analytics")
        st.json(wa.analytics())

    with tabs[2]:
        st.subheader("Recommendations")
        data = wa.analytics()
        for line in rec.recommend_workflows(data):
            st.write("-", line)

    st.sidebar.markdown("## Pending Reviews")
    for wf in wr.list_pending():
        st.sidebar.write(wf)
    st.sidebar.markdown("## Review Requests")
    for req in rr.list_requests("pending"):
        st.sidebar.write(f"{req['kind']}: {req['target']}")
    st.sidebar.write("Reload to refresh")
    streamlit_closing(st)


if __name__ == "__main__":
    run_dashboard()
