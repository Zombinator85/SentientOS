import argparse
import json
from pathlib import Path
from typing import Any, Dict

import reflex_manager as rm
import reflection_stream as rs

try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - optional
    st = None


def load_experiments() -> Dict[str, Any]:
    path = rm.ReflexManager.EXPERIMENTS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_cli(args: argparse.Namespace) -> None:
    mgr = rm.ReflexManager()
    mgr.load_experiments()

    if args.promote:
        mgr.promote_rule(args.promote, by="cli")
    if args.demote:
        mgr.demote_rule(args.demote, by="cli")
    if args.revert:
        mgr.revert_last()

    if args.list_experiments:
        data = load_experiments()
        for name, info in data.items():
            print(name, info.get("status", "running"))
            for r, stats in info.get("rules", {}).items():
                rate = stats.get("success", 0) / max(1, stats.get("trials", 1))
                print(f"  {r}: {stats.get('trials',0)} trials, {rate:.2f} success")

    if args.log:
        logs = rs.recent_reflex_learn(args.log)
        for l in logs:
            print(json.dumps(l))


def run_dashboard() -> None:
    if st is None:
        ap = argparse.ArgumentParser(description="Reflex dashboard CLI")
        ap.add_argument("--log", type=int, default=0, help="Show last N learn logs")
        ap.add_argument("--list-experiments", action="store_true")
        ap.add_argument("--promote")
        ap.add_argument("--demote")
        ap.add_argument("--revert", action="store_true")
        args = ap.parse_args()
        run_cli(args)
        return

    st.set_page_config(page_title="Reflex Dashboard")
    st.title("Reflex Experiments")
    data = load_experiments()
    for name, info in data.items():
        st.subheader(name)
        st.write(info.get("status", "running"))
        cols = st.columns(len(info.get("rules", {})))
        for idx, (r, stats) in enumerate(info.get("rules", {}).items()):
            rate = stats.get("success", 0) / max(1, stats.get("trials", 1))
            cols[idx].metric(r, f"{rate:.2f}", f"{stats.get('trials',0)} trials")

    st.header("Recent Learning Events")
    logs = rs.recent_reflex_learn(20)
    for item in logs:
        st.json(item)


if __name__ == "__main__":
    run_dashboard()
