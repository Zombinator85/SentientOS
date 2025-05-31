import argparse
import json
from pathlib import Path
from typing import Any, Dict

import reflex_manager as rm
import reflection_stream as rs
import final_approval

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
        mgr.promote_rule(
            args.promote,
            by=args.agent or "cli",
            persona=args.persona,
            policy=args.policy,
            reviewer=args.reviewer,
        )
    if args.demote:
        mgr.demote_rule(
            args.demote,
            by=args.agent or "cli",
            persona=args.persona,
            policy=args.policy,
            reviewer=args.reviewer,
        )
    if args.revert:
        mgr.revert_last()
    if args.revert_rule:
        mgr.revert_rule(args.revert_rule)
    if args.annotate:
        rule, comment = args.annotate
        tags = [args.tag] if args.tag else None
        mgr.annotate(
            rule,
            comment,
            tags=tags,
            by=args.agent or "cli",
            persona=args.persona,
            policy=args.policy,
            reviewer=args.reviewer,
        )

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

    if args.history:
        for entry in mgr.get_history(args.history)[-10:]:
            print(json.dumps(entry))
    if args.audit:
        entries = mgr.get_audit(args.audit)
        if args.filter_agent:
            entries = [e for e in entries if e.get("by") == args.filter_agent]
        if args.filter_persona:
            entries = [e for e in entries if e.get("persona") == args.filter_persona]
        if args.filter_policy:
            entries = [e for e in entries if e.get("policy") == args.filter_policy]
        if args.filter_action:
            entries = [e for e in entries if e.get("action") == args.filter_action]
        for entry in entries:
            print(json.dumps(entry))


def run_dashboard() -> None:
    if st is None:
        ap = argparse.ArgumentParser(description="Reflex dashboard CLI")
        ap.add_argument("--log", type=int, default=0, help="Show last N learn logs")
        ap.add_argument("--list-experiments", action="store_true")
        ap.add_argument("--promote")
        ap.add_argument("--demote")
        ap.add_argument("--revert", action="store_true")
        ap.add_argument("--revert-rule")
        ap.add_argument("--history")
        ap.add_argument("--annotate", nargs=2, metavar=("RULE", "COMMENT"))
        ap.add_argument("--tag")
        ap.add_argument("--audit")
        ap.add_argument("--agent")
        ap.add_argument("--persona")
        ap.add_argument("--policy")
        ap.add_argument("--reviewer")
        ap.add_argument("--final-approvers", help="Comma separated approvers")
        ap.add_argument("--final-approver-file", help="JSON file of approvers")
        ap.add_argument("--filter-agent")
        ap.add_argument("--filter-persona")
        ap.add_argument("--filter-policy")
        ap.add_argument("--filter-action")
        args = ap.parse_args()
        if args.final_approver_file:
            fp = Path(args.final_approver_file)
            if fp.exists():
                final_approval.override_approvers(json.loads(fp.read_text()))
            else:
                final_approval.override_approvers([])
        elif args.final_approvers:
            fp = Path(args.final_approvers)
            if fp.exists():
                final_approval.override_approvers(json.loads(fp.read_text()))
            else:
                final_approval.override_approvers(
                    [a.strip() for a in args.final_approvers.split(",") if a.strip()]
                )
        run_cli(args)
        return

    st.set_page_config(page_title="Reflex Dashboard")
    st.title("Reflex Experiments")
    mgr = rm.ReflexManager()
    mgr.load_experiments()
    data = mgr.experiments
    for name, info in data.items():
        st.subheader(name)
        st.write(info.get("status", "running"))
        cols = st.columns(len(info.get("rules", {})))
        for idx, (r, stats) in enumerate(info.get("rules", {}).items()):
            rate = stats.get("success", 0) / max(1, stats.get("trials", 1))
            cols[idx].metric(r, f"{rate:.2f}", f"{stats.get('trials',0)} trials")
        with st.expander("History"):
            for entry in mgr.get_history(name)[-10:]:
                st.json(entry)

    st.header("Recent Learning Events")
    logs = rs.recent_reflex_learn(20)
    for item in logs:
        st.json(item)

    st.header("Audit Log")
    for entry in mgr.get_audit()[-20:]:
        st.json(entry)


if __name__ == "__main__":
    run_dashboard()
